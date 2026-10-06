#!/usr/bin/env python3
"""Independent joint-fit spot checks of C1/32 Hz, collision and missing-F0 arrays."""
import hashlib
import json
import math
import os
from pathlib import Path
import sys

os.environ["OPENBLAS_NUM_THREADS"] = "2"
import numpy as np
from scipy.io import wavfile


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    root = Path(sys.argv[1]).resolve()
    result_path = root / "results.json"
    result = json.loads(result_path.read_text())
    checked = {str(result_path): sha(result_path)}
    amplitudes, exclusions = [], []
    for alias in ("lr01", "lr03", "lr07", "lr09"):
        folder = root / alias
        truth_path = folder / "truth.json"
        checked[str(truth_path)] = sha(truth_path)
        truth = json.loads(truth_path.read_text())
        clean_path = folder / "clean.wav"
        checked[str(clean_path)] = sha(clean_path)
        rate, clean = wavfile.read(clean_path)
        clean = (clean[:, None] if clean.ndim == 1 else clean).astype(np.float64)
        events = [event for event in truth["events"] if event["frequency_hz"] is not None and
                  event["end_sample"] - round(.1 * rate) - event["start_sample"] - round(.1 * rate) >= rate]
        harmonics = sorted({1, *[int(item[0]) for item in truth["case"]["parameters"].get(
            "harmonics", [[1, 1], [2, .25], [3, .15], [4, .1]])]})
        for arm in ("bypass", "captured_nr8", "captured_nr10", "protected_mask"):
            output_path = folder / (arm + "-guitar-response.npy")
            checked[str(output_path)] = sha(output_path)
            output = np.load(output_path, allow_pickle=False)
            metric = next(row for row in result["results"] if row["alias"] == alias and row["arm"] == arm)
            assert len(metric["harmonic_fits"]) == len(events)
            for event, observed in zip(events, metric["harmonic_fits"]):
                a, b = event["start_sample"] + round(.1 * rate), event["end_sample"] - round(.1 * rate)
                time = np.arange(a, b, dtype=np.float64) / rate
                columns = []
                for harmonic in harmonics:
                    phase = 2 * np.pi * harmonic * event["frequency_hz"] * time
                    columns.extend([np.sin(phase), np.cos(phase)])
                columns.append(np.ones(b - a))
                basis = np.column_stack(columns)
                # Independent normal-equation solve; owner's scorer uses lstsq.
                gram = basis.T @ basis
                coefficients = np.linalg.solve(gram, basis.T @ np.column_stack((clean[a:b], output[a:b])))
                channels = clean.shape[1]
                for index, harmonic in enumerate(harmonics):
                    expected = np.sqrt(coefficients[2 * index] ** 2 + coefficients[2 * index + 1] ** 2)
                    for channel in range(channels):
                        row = next(item for item in observed["rows"] if item["harmonic"] == harmonic and item["channel"] == channel)
                        before, after = float(expected[channel]), float(expected[channel + channels])
                        assert math.isclose(row["source_amplitude"], before, rel_tol=1e-7, abs_tol=1e-9)
                        assert math.isclose(row["output_amplitude"], after, rel_tol=1e-7, abs_tol=1e-9)
                        if before <= 5e-5:
                            assert row["status"] == "source_harmonic_below_fit_threshold" and row["value_db"] is None
                        elif after == 0:
                            assert row["status"] == "complete_attenuation" and row["value_db"] is None
                        else:
                            assert math.isclose(row["value_db"], 20 * math.log10(after / before), rel_tol=1e-7, abs_tol=1e-6)
                        if harmonic == 1:
                            amplitudes.append({"alias": alias, "arm": arm, "channel": channel,
                                               "frequency_hz": event["frequency_hz"],
                                               "source_amplitude": before, "output_amplitude": after,
                                               "eligible": metric["fundamental_gate_eligible"], "status": row["status"]})
            if alias in ("lr03", "lr07", "lr09"):
                assert metric["fundamental_gate_eligible"] is False
                assert metric["fundamental_eligible_channel_event_denominator"] == 0
                assert metric["missing_f0_recovered"] is False
                exclusions.append({"alias": alias, "arm": arm, "reason": metric["fundamental_exclusion"]})
    assert all(sha(Path(path)) == expected for path, expected in checked.items())
    receipt = {"status": "PASS", "auditor_sha256": sha(__file__), "results_sha256": sha(result_path),
               "files_checked": len(checked), "all_checked_inputs_unchanged": True,
               "joint_fit_cases": ["lr01", "lr03", "lr07", "lr09"],
               "fundamental_channel_event_rows_recomputed": len(amplitudes),
               "amplitudes": amplitudes, "exclusions": exclusions,
               "actual_recording_read": False, "denoising_or_inference_run": False,
               "scope": "Generated conditional/counterfactual fit arithmetic; no real fundamental or stem recovery."}
    Path(sys.argv[2]).write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({key: value for key, value in receipt.items() if key not in ("amplitudes", "exclusions")}, indent=2))


if __name__ == "__main__":
    main()
