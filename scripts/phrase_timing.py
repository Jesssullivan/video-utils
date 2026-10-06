#!/usr/bin/env python3
"""Experimental per-phrase guitar-onset offset from the nearest modelled in-recording click.

Offsets describe detected broadband attack candidates relative to a fitted periodic
high-frequency transient model. They are not performance grades, not note identities
and not intended-rhythm comparisons; the click identity is unverified.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
import math
from pathlib import Path
import statistics
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 1
MIN_CLICK_PROXIMAL_ONSETS = 4
PROXIMAL_MAX_SECONDS = .060
OBSERVED_CLICK_TOLERANCE_SECONDS = .025
WITHIN_MS = 5.0
ONSET_KIND = "broadband_attack_candidate"
CLICK_KIND = "periodic_high_frequency_candidate"
DEFAULT_OUTPUT_ROOT = ROOT / "artifacts" / "s2" / "rhythm_clicks" / "phrase-timing"
MAX_INPUT_BYTES = 64 * 1024 * 1024
FIXED_FIELDS = {"click_identity": "unverified", "physical_capture_latency": "uncalibrated",
                "listening_ab": "not_performed", "performance_grading": "not_performed",
                "expected_rhythm_reference": None, "onset_detector_delay_compensated_in_source_events": False}
ABSTAIN_REASONS = ("fewer_than_4_click_proximal_onsets", "no_click_grid", "span_outside_analysis")

_spec = importlib.util.spec_from_file_location("phrase_timing_rhythm", Path(__file__).with_name("rhythm.py"))
rhythm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rhythm)


def _quantile(ordered: list[float], q: float) -> float:
    return rhythm._quantile(ordered, q)


class ClickReference:
    """Predicted click positions: fitted drift model, else constant grid, else none."""

    def __init__(self, analysis: dict):
        drift = analysis.get("click_grid_drift") or {}
        grid = analysis.get("click_grid")
        self.parameters = None
        self.grid = None
        self.retained_range = None
        if drift.get("status") == "fitted" and drift.get("model_parameters"):
            self.basis = "linear_period_drift_model"
            self.parameters = drift["model_parameters"]
            beats = self.parameters.get("retained_beat_index_range") or [None, None]
            self.retained_range = (beats[0], beats[1])
        elif grid and grid.get("period_seconds") and grid.get("phase_seconds_audio_relative") is not None:
            self.basis = "constant_click_grid"
            self.grid = grid
            observed = [event["beat_index"] for event in grid.get("observed_events", [])]
            self.retained_range = (min(observed), max(observed)) if observed else None
        else:
            self.basis = None

    def describe(self) -> dict:
        if self.basis == "linear_period_drift_model":
            return {"basis": self.basis, "model_parameters": self.parameters,
                    "retained_beat_index_range": list(self.retained_range)}
        if self.basis == "constant_click_grid":
            return {"basis": self.basis, "period_seconds": self.grid["period_seconds"],
                    "phase_seconds_audio_relative": self.grid["phase_seconds_audio_relative"],
                    "observed_beat_index_range": list(self.retained_range) if self.retained_range else None}
        return {"basis": None, "status": "no_click_grid"}

    def click(self, beat: int) -> float:
        if self.parameters:
            return rhythm.drift_click_time(self.parameters, beat)
        return self.grid["phase_seconds_audio_relative"] + beat * self.grid["period_seconds"]

    def local_period(self, click_time: float) -> float:
        if self.parameters:
            return (self.parameters["ioi_intercept_seconds_at_audio_time_zero"]
                    + self.parameters["period_change_per_second"] * click_time)
        return self.grid["period_seconds"]

    def nearest(self, time: float) -> tuple[int, float, float] | None:
        if self.parameters:
            position = rhythm.drift_beat_position(self.parameters, time)
            if position is None:
                return None
        else:
            position = (time - self.grid["phase_seconds_audio_relative"]) / self.grid["period_seconds"]
        options = []
        for beat in (math.floor(position) - 1, math.floor(position), math.floor(position) + 1, math.floor(position) + 2):
            click = self.click(beat)
            if math.isfinite(click):
                options.append((abs(time - click), beat, click))
        if not options:
            return None
        _, beat, click = min(options)
        return beat, click, self.local_period(click)

    def extrapolated(self, beats: list[int]) -> bool | None:
        if not self.retained_range or not beats:
            return None
        return min(beats) < self.retained_range[0] or max(beats) > self.retained_range[1]


def delay_table(analysis: dict) -> dict:
    calibration = (analysis.get("analysis") or {}).get("onset_detector_delay_calibration") or {}
    table = calibration.get("compensation_table") or {}
    attack = (table.get(ONSET_KIND) or {}).get("delay_seconds")
    click = (table.get(CLICK_KIND) or {}).get("delay_seconds")
    status = ("synthetic_probe_medians_applied" if attack is not None and click is not None
              else "analysis_lacks_usable_detector_delay_calibration")
    return {"attack_delay_seconds": attack, "click_delay_seconds": click, "status": status,
            "formula": "(onset - d_attack) - (click - d_click)",
            "interpretation": "detector frame/novelty delay from synthetic probes; physical capture latency uncalibrated"}


def observed_click_times(analysis: dict) -> list[float]:
    times = {round(event["audio_relative_seconds"], 9) for event in analysis.get("events", []) if event.get("kind") == CLICK_KIND}
    drift = analysis.get("click_grid_drift") or {}
    times.update(round(event["audio_relative_seconds"], 9) for event in drift.get("tracked_events", []))
    return sorted(times)


def _nearest_value(ordered: list[float], target: float) -> float | None:
    import bisect
    position = bisect.bisect_left(ordered, target)
    options = [ordered[index] for index in (position - 1, position) if 0 <= index < len(ordered)]
    return min(options, key=lambda value: abs(value - target)) if options else None


def _summary_ms(values: list[float]) -> dict:
    ordered = sorted(values)
    q1, q3 = _quantile(ordered, .25), _quantile(ordered, .75)
    return {"median": statistics.median(ordered) * 1000, "iqr": [q1 * 1000, q3 * 1000], "iqr_width": (q3 - q1) * 1000}


def tendency(median_ms: float | None) -> str | None:
    if median_ms is None:
        return None
    if abs(median_ms) <= WITHIN_MS:
        return "within_5_ms"
    return "ahead_of_click" if median_ms < 0 else "behind_click"


def measure_phrase(phrase: dict, onsets: list[float], reference: ClickReference, delays: dict,
                   observed: list[float], audio_start: float, duration: float) -> dict:
    start, end = phrase["span_source_seconds"]
    span = [start - audio_start, end - audio_start]
    entry = {"phrase_id": phrase["phrase_id"], "label": phrase.get("label"), "label_basis": phrase.get("label_basis"),
             "span_source_seconds": [start, end], "span_audio_relative_seconds": span,
             "onset_count_in_span": 0, "click_proximal_onset_count": 0, "off_click_onset_count": 0,
             "additional_onsets_in_window_count": 0, "median_offset_ms": None, "iqr_ms": None, "iqr_width_ms": None,
             "median_offset_ms_delay_compensated": None, "iqr_ms_delay_compensated": None,
             "observed_click_basis_median_offset_ms": None, "observed_click_basis_count": 0,
             "click_reference_extrapolated": None, "tendency_label": None, "tendency_basis": None,
             "status": "abstained", "abstain_reason": None}
    for key in ("source_marker_name", "source_index"):
        if key in phrase:
            entry[key] = phrase[key]
    in_span = [time for time in onsets if span[0] <= time < span[1]]
    entry["onset_count_in_span"] = len(in_span)
    if reference.basis is None:
        entry["abstain_reason"] = "no_click_grid"
        return entry
    if span[1] <= 0 or span[0] >= duration or span[1] <= span[0]:
        entry["abstain_reason"] = "span_outside_analysis"
        return entry
    by_click: dict[int, list[tuple[float, float, float]]] = {}
    off_click = 0
    for time in in_span:
        nearest = reference.nearest(time)
        if nearest is None:
            off_click += 1
            continue
        beat, click, period = nearest
        offset = time - click
        if abs(offset) <= min(PROXIMAL_MAX_SECONDS, period / 4):
            by_click.setdefault(beat, []).append((abs(offset), offset, click))
        else:
            off_click += 1
    chosen = {beat: min(rows) for beat, rows in by_click.items()}
    entry["off_click_onset_count"] = off_click
    entry["additional_onsets_in_window_count"] = sum(len(rows) - 1 for rows in by_click.values())
    entry["click_proximal_onset_count"] = len(chosen)
    entry["click_reference_extrapolated"] = reference.extrapolated(sorted(chosen))
    if len(chosen) < MIN_CLICK_PROXIMAL_ONSETS:
        entry["abstain_reason"] = "fewer_than_4_click_proximal_onsets"
        return entry
    offsets = [row[1] for row in chosen.values()]
    raw = _summary_ms(offsets)
    entry.update(median_offset_ms=raw["median"], iqr_ms=raw["iqr"], iqr_width_ms=raw["iqr_width"])
    if delays["attack_delay_seconds"] is not None and delays["click_delay_seconds"] is not None:
        compensated = _summary_ms([value - delays["attack_delay_seconds"] + delays["click_delay_seconds"] for value in offsets])
        entry.update(median_offset_ms_delay_compensated=compensated["median"], iqr_ms_delay_compensated=compensated["iqr"])
    observed_offsets = []
    for _, offset, click in chosen.values():
        candidate = _nearest_value(observed, click)
        if candidate is not None and abs(candidate - click) <= OBSERVED_CLICK_TOLERANCE_SECONDS:
            observed_offsets.append(click + offset - candidate)
    if observed_offsets:
        entry["observed_click_basis_median_offset_ms"] = statistics.median(observed_offsets) * 1000
    entry["observed_click_basis_count"] = len(observed_offsets)
    primary = entry["median_offset_ms_delay_compensated"]
    entry["tendency_basis"] = "median_offset_ms_delay_compensated" if primary is not None else "median_offset_ms"
    entry["tendency_label"] = tendency(primary if primary is not None else entry["median_offset_ms"])
    entry["status"] = "measured"
    return entry


def measure(analysis: dict, phrases: list[dict], *, phrase_basis: str, run_kind: str) -> dict:
    """Pure computation over an analysis dict and normalized phrase spans (source seconds)."""
    if run_kind not in ("real_take", "synthetic_fixture"):
        raise ValueError("run_kind must be real_take or synthetic_fixture")
    reference = ClickReference(analysis)
    delays = delay_table(analysis)
    audio_start = float((analysis.get("timeline") or {}).get("audio_stream_start_seconds") or 0.0)
    duration = float((analysis.get("analysis") or {}).get("duration_seconds") or 0.0)
    onsets = sorted(event["audio_relative_seconds"] for event in analysis.get("events", []) if event.get("kind") == ONSET_KIND)
    observed = observed_click_times(analysis)
    entries = [measure_phrase(phrase, onsets, reference, delays, observed, audio_start, duration) for phrase in phrases]
    reasons = {reason: sum(entry["abstain_reason"] == reason for entry in entries) for reason in ABSTAIN_REASONS}
    measured = [entry for entry in entries if entry["status"] == "measured"]
    drift = analysis.get("click_grid_drift") or {}
    result = {"schema_version": SCHEMA_VERSION, "tool": "phrase_timing", "status": "experimental_unvalidated_measurement",
              "run_kind": run_kind,
              "real_take_status": "unvalidated_until_operator_spot_check" if run_kind == "real_take" else "synthetic_fixture",
              **FIXED_FIELDS,
              "phrase_basis": phrase_basis,
              "onset_basis": {"kind": ONSET_KIND, "timestamp": "frame_midpoint_audio_relative",
                              "identity": "broadband_attack_candidate_not_note_identity"},
              "click_reference": {**reference.describe(),
                                  "drift_status": drift.get("status"), "drift_confidence_label": drift.get("confidence_label"),
                                  "identity": "periodic_high_frequency_transients_not_verified_metronome"},
              "detector_delay": delays,
              "rules": {"offset": "onset - nearest predicted click; negative = ahead of click, positive = behind click",
                        "click_proximal_window_seconds": f"min({PROXIMAL_MAX_SECONDS}, local_period/4)",
                        "multiple_onsets_per_click": "nearest counts; the rest are additional_onsets_in_window_count",
                        "off_click_onsets": "subdivisions or other attacks, not errors",
                        "minimum_click_proximal_onsets": MIN_CLICK_PROXIMAL_ONSETS,
                        "observed_click_tolerance_seconds": OBSERVED_CLICK_TOLERANCE_SECONDS,
                        "tendency_threshold_ms": WITHIN_MS,
                        "tendency_meaning": "descriptive sign of the median only; not a performance verdict"},
              "summary": {"phrase_count": len(entries), "measured_count": len(measured),
                          "abstained_count": len(entries) - len(measured), "abstain_reason_counts": reasons},
              "phrases": entries,
              "limitations": [
                  "Broadband attack candidates can include click energy, handling noise or several merged attacks.",
                  "The click model is fitted to unverified periodic high-frequency transients; a guitar attack can displace or mask a click.",
                  "Detector delay compensation uses synthetic-probe medians; real attacks differ and physical capture latency is uncalibrated.",
                  "Phrase spans are review candidates or reference-conditioned alignments, not detected musical boundaries.",
                  "No intended-rhythm reference is used; offsets are descriptive and do not identify note-level or performance faults."]}
    return result


def _read_json(path: Path) -> dict:
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError(f"{path.name} exceeds the input size bound")
    return json.loads(path.read_text(encoding="utf-8"))


def load_phrases(document: dict) -> tuple[str, str | None, list[dict], dict]:
    """Normalize arrangement markers or phrases.json review spans; returns (basis, bound_sha, phrases, notes)."""
    if isinstance(document.get("markers"), list):
        phrases, excluded = [], 0
        for index, marker in enumerate(document["markers"]):
            start, end = marker.get("source_time_seconds"), marker.get("end_seconds")
            if (not isinstance(start, (int, float)) or not isinstance(end, (int, float)) or end <= start
                    or "boundary" in str(marker.get("name", ""))):
                excluded += 1
                continue
            phrases.append({"phrase_id": f"marker-{index}", "label": marker.get("display_label") or marker.get("name"),
                            "label_basis": marker.get("label_basis"), "span_source_seconds": [float(start), float(end)],
                            "source_marker_name": marker.get("name"), "source_index": index})
        return ("reference_conditioned_alignment_candidate", document.get("analyzed_input_sha256"), phrases,
                {"format": document.get("format"), "excluded_marker_count": excluded,
                 "exclusion_rule": "zero-width, non-numeric or boundary markers"})
    observations = document.get("observations") or {}
    spans = observations.get("proposed_review_spans")
    if isinstance(spans, list):
        phrases = []
        for index, span in enumerate(spans):
            start = span.get("source_start_seconds", span.get("start_seconds"))
            end = span.get("source_end_seconds", span.get("end_seconds"))
            if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
                raise ValueError("Review span lacks numeric source times")
            phrases.append({"phrase_id": f"span-{index}", "label": span.get("label"), "label_basis": "automatic_review_span",
                            "span_source_seconds": [float(start), float(end)], "source_index": index})
        lineage = document.get("lineage") or {}
        source = document.get("source") or {}
        bound = lineage.get("input_sha256") or source.get("sha256")
        return "automatic_review_span", bound, phrases, {"format": "phrases.json proposed_review_spans", "excluded_marker_count": 0}
    raise ValueError("Phrase input is neither arrangement markers nor phrases.json proposed_review_spans")


def _under_accepted_runs(path: Path) -> bool:
    parts = path.expanduser().resolve().parts
    return any(parts[index:index + 2] == ("artifacts", "runs") for index in range(len(parts) - 1))


def run(analysis_path: Path, phrases_path: Path, output_root: Path, run_kind: str = "real_take") -> Path:
    analysis_path = analysis_path.expanduser().resolve(strict=True)
    phrases_path = phrases_path.expanduser().resolve(strict=True)
    if _under_accepted_runs(output_root):
        raise ValueError("Output may not be written under accepted run directories")
    analysis = _read_json(analysis_path)
    document = _read_json(phrases_path)
    analyzed = (analysis.get("source") or {}).get("sha256")
    if not isinstance(analyzed, str) or len(analyzed) != 64:
        raise ValueError("Analysis lacks an analyzed-input sha256")
    basis, bound, phrases, notes = load_phrases(document)
    if bound != analyzed:
        raise ValueError("Phrase input is not bound to the analyzed input sha256; refusing to measure")
    result = measure(analysis, phrases, phrase_basis=basis, run_kind=run_kind)
    result["inputs"] = {"analysis_path": str(analysis_path), "analysis_file_sha256": rhythm.file_hash(analysis_path),
                        "phrases_path": str(phrases_path), "phrases_file_sha256": rhythm.file_hash(phrases_path),
                        "analyzed_input_sha256": analyzed, "phrase_binding_sha256": bound, "phrase_input": notes}
    result["producer"] = {"phrase_timing_sha256": rhythm.file_hash(Path(__file__)),
                          "rhythm_sha256": rhythm.file_hash(Path(__file__).with_name("rhythm.py"))}
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:12]
    result["run_id"] = run_id
    destination = output_root.resolve() / run_id
    destination.mkdir(parents=True, exist_ok=False)
    rhythm.atomic_write(destination / "phrase-timing.json", json.dumps(result, indent=2, allow_nan=False) + "\n")
    return destination / "phrase-timing.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", type=Path, required=True, help="rhythm analysis.json")
    parser.add_argument("--phrases", type=Path, required=True, help="arrangement-markers.json or phrases.json")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--run-kind", choices=("real_take", "synthetic_fixture"), default="real_take")
    args = parser.parse_args()
    try:
        path = run(args.analysis, args.phrases, args.output_root, args.run_kind)
        result = json.loads(path.read_text(encoding="utf-8"))
        print(json.dumps({"phrase_timing_json": str(path), "summary": result["summary"],
                          "click_reference": result["click_reference"]["basis"],
                          "real_take_status": result["real_take_status"]}))
        return 0
    except (ValueError, OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        print(f"phrase_timing: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
