#!/usr/bin/env python3
"""Independent sealed-array accounting; no owner scorer or inference invoked."""
from pathlib import Path
import hashlib
import json
import math
import os
import sys

for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[key] = "2"
import numpy as np
from scipy.io import wavfile


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def ratio(after, before, factor=10):
    if before == 0:
        return None, "zero_reference"
    if after == 0:
        return None, "complete_attenuation"
    return factor * math.log10(after / before), "measured"


def check_ratio(observed, after, before, factor=10):
    expected, status = ratio(after, before, factor)
    assert observed["status"] == status, (observed, expected, status)
    if expected is None:
        assert observed["value_db"] is None
    else:
        assert math.isclose(observed["value_db"], expected, rel_tol=1e-10, abs_tol=1e-9), (observed, expected)


def band_energy(data, rate, low, high):
    # Independently derive one-sided Hann periodogram integral over sample values.
    n = len(data)
    # Periodic analysis window: the endpoint sample of a length n+1 Hann is omitted.
    window = np.hanning(n + 1)[:-1]
    spectrum = np.fft.rfft(data * window[:, None], axis=0)
    weights = np.full(len(spectrum), 2.0)
    weights[0] = 1.0
    if n % 2 == 0:
        weights[-1] = 1.0
    frequencies = np.fft.rfftfreq(n, d=1 / rate)
    bins = (frequencies >= low) & (frequencies < high)
    return float(np.sum(np.abs(spectrum[bins]) ** 2 * weights[bins, None]) /
                 (n * np.sum(window ** 2)))


def energy(array):
    return float(np.sum(array ** 2))


def normalized(array):
    return array[:, None] if array.ndim == 1 else array


def main():
    folder = Path(sys.argv[1]).resolve()
    output = Path(sys.argv[2])
    sources = [p for p in folder.rglob("*") if p.is_file()]
    initial = {str(p.relative_to(folder)): sha(p) for p in sources}
    result = json.loads((folder / "results.json").read_text())
    seal = json.loads((folder / "sealed-mixtures.json").read_text())
    assert result["sealed_mixtures_sha256"] == sha(folder / "sealed-mixtures.json")
    for job in seal["jobs"]:
        case = folder / job["alias"]
        assert sha(case / "mixture.wav") == job["mixture_sha256"]
        for name, expected in job["sealed_hashes"].items():
            assert sha(case / name) == expected
    assert len(result["results"]) == 36
    rows = []
    for observed in result["results"]:
        case = folder / observed["alias"]
        truth = json.loads((case / "truth.json").read_text())
        arm = observed["arm"]
        arrays = {}
        for role in ("clean", "fan", "mixture"):
            rate, data = wavfile.read(case / (role + ".wav"))
            assert rate == truth["case"]["sample_rate"]
            arrays[role] = normalized(data).astype(np.float64)
        guitar, noise = arrays["clean"], arrays["fan"]
        y, g, n, s = [np.load(case / (arm + "-" + role + ".npy"), allow_pickle=False)
                      for role in ("mixture", "guitar-response", "noise-control", "clean-control")]
        for array in (guitar, noise, y, g, n, s):
            assert array.shape == (truth["case"]["sample_frames"], truth["case"]["channels"])
            assert np.isfinite(array).all()
        conditional = arm in ("bypass", "protected_mask")
        assert observed["noise_control_is_mixture_residual"] is conditional
        assert observed["metric_scope"] == ("conditional_known_components" if conditional else "paired_counterfactual_not_stems")
        assert observed["real_stem_recovered"] is False and observed["missing_f0_recovered"] is False
        if not conditional:
            assert np.array_equal(g, y - n)
        interaction = y - s - n
        if conditional:
            expected = float(np.max(np.abs(interaction)))
            assert math.isclose(expected, observed["conditional_additivity_max_abs"], abs_tol=1e-15)
            assert expected <= 4e-7
        else:
            assert observed["conditional_additivity_max_abs"] is None
        for label, after, before in (
            ("guitar_response_energy", energy(g), energy(guitar)),
            ("guitar_response_relative_error", energy(g - guitar), energy(guitar)),
            ("processed_mixture_relative_error", energy(y - guitar), energy(guitar)),
            ("interaction_relative_energy", energy(interaction), energy(guitar)),
            ("noise_control_energy", energy(n), energy(noise)),
        ):
            check_ratio(observed[label], after, before)
        check_ratio(observed["guitar_response_low_band"], band_energy(g, rate, 20, 45), band_energy(guitar, rate, 20, 45))
        for low, high in ((20, 45), (45, 120), (140, 8000)):
            check_ratio(observed["noise_control_band_power_change"][f"{low}-{high}"],
                        band_energy(n, rate, low, high), band_energy(noise, rate, low, high))
        active = np.zeros(len(guitar), dtype=bool)
        for event in truth["events"]:
            active[event["start_sample"]:event["end_sample"]] = True
        assert observed["active_sample_frame_denominator"] == int(active.sum())
        check_ratio(observed["guitar_response_active_energy"], energy(g[active]), energy(guitar[active]))
        assert observed["sample_value_denominator"] == y.size
        assert observed["clipped_sample_values"] == int((np.abs(y) >= 1).sum())
        assert math.isclose(observed["processed_peak_abs"], float(np.abs(y).max()), abs_tol=1e-15)
        assert observed["palm_event_denominator"] == sum(e["kind"] == "palm_mute" for e in truth["events"])
        assert observed["legato_event_denominator"] == sum(e["kind"] == "connected_legato_no_internal_pick_attacks" for e in truth["events"])
        assert observed["broadband_noise_gate_eligible"] is (truth["case"]["parameters"].get("noise_rms", 0) > 0)
        eligible = bool(truth["fundamental_gain_applicable"] and not truth["non_identifiable"]
                        and truth["case"].get("s1_collision_scope") is None)
        assert observed["fundamental_gate_eligible"] is eligible
        assert observed["fundamental_eligible_channel_event_denominator"] == sum(
            eligible and row["status"] in ("measured", "complete_attenuation")
            for row in observed["fundamental_gain_rows"])
        # Temporal windows are independently indexed from source samples.
        for metric in observed["palm_attack_tail"]:
            onset, stop = metric["start_sample"], metric["end_sample"]
            width = round(.020 * rate)
            before, after = guitar[onset:onset+width], g[onset:onset+width]
            check_ratio(metric["attack_energy"], energy(after), energy(before))
            a, b = onset + round(.05 * rate), min(onset + round(.25 * rate), stop)
            if b > a:
                check_ratio(metric["tail_energy"], float(np.mean(g[a:b] ** 2)), float(np.mean(guitar[a:b] ** 2)))
            if energy(before) and energy(after):
                offsets = np.arange(len(before)) / rate
                expected = 1000 * (float(offsets @ np.sum(after ** 2, axis=1)) / energy(after)
                                   - float(offsets @ np.sum(before ** 2, axis=1)) / energy(before))
                assert math.isclose(metric["centroid_shift_ms"], expected, abs_tol=1e-9)
            else:
                assert metric["centroid_shift_ms"] is None
        for metric in observed["legato_sustain"]:
            a, b = metric["start_sample"], metric["end_sample"]
            check_ratio(metric, energy(g[a:b]), energy(guitar[a:b]))
        rows.append({"alias": observed["alias"], "arm": arm,
                     "clipped_sample_values": observed["clipped_sample_values"],
                     "sample_value_denominator": y.size,
                     "fundamental_denominator": observed["fundamental_eligible_channel_event_denominator"],
                     "active_sample_frame_denominator": int(active.sum()),
                     "palm_event_denominator": observed["palm_event_denominator"],
                     "legato_event_denominator": observed["legato_event_denominator"],
                     "noise_case_eligible": observed["broadband_noise_gate_eligible"],
                     "collision": observed["exact_collision"] or observed["near_collision"]})
    summaries = {}
    for arm in ("bypass", "captured_nr8", "captured_nr10", "protected_mask"):
        selected = [row for row in rows if row["arm"] == arm]
        summary = {
            "rows": len(selected),
            "clipped_sample_values": sum(row["clipped_sample_values"] for row in selected),
            "sample_value_denominator": sum(row["sample_value_denominator"] for row in selected),
            "fundamental_eligible_channel_event_denominator": sum(row["fundamental_denominator"] for row in selected),
            "palm_event_denominator": sum(row["palm_event_denominator"] for row in selected),
            "legato_event_denominator": sum(row["legato_event_denominator"] for row in selected),
            "broadband_noise_case_denominator": sum(row["noise_case_eligible"] for row in selected),
            "collision_case_count": sum(row["collision"] for row in selected),
        }
        for key, value in summary.items():
            assert result["summary"][arm][key] == value
        summaries[arm] = summary
    assert initial == {str(p.relative_to(folder)): sha(p) for p in sources}, "Sealed arrays changed"
    receipt = {"status": "PASS", "input_results_sha256": sha(folder / "results.json"),
               "sealed_mixtures_sha256": sha(folder / "sealed-mixtures.json"),
               "auditor_sha256": sha(__file__), "source_files_checked": len(initial),
               "all_checked_inputs_unchanged": True, "rows_recomputed": len(rows), "summary": summaries,
               "actual_audio_read": False, "inference_run": False,
               "scope": "Sealed generated array arithmetic; harmonic fit amplitudes and listening are not qualified by this receipt.",
               "limitations": ["Afftdn noise controls are not mixture residual stems.",
                               "Near/exact collisions remain nonidentifiable.",
                               "Missing-F0 low-band ratios against tiny leakage are descriptive, never recovered fundamental."]}
    output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
