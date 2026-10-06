#!/usr/bin/env python3
"""Compose a read-only, hash-verified S2 practice bundle for the local review page.

The composer copies existing evidence (tone_ab excerpts, flags triage, phrase
anchor spans, detector review spans and phrase timing) into one bundle
directory bound to a session run's original source. It never re-runs a
detector, never adopts a profile, anchor or master, and never writes inside
``artifacts/runs``. The only media job is the optional trial excerpt cut.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import shutil
import struct
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[1]
SCHEMA_ID = "video-utils.practice-s2.bundle"
SCHEMA_VERSION = 1
MAX_JSON_BYTES = 20_000_000
MAX_MEDIA_BYTES = 64 * 1024 * 1024
DEFAULT_TIMEOUT = 600.0
MAX_TIMEOUT = 1800.0
SUBPROCESS_TIMEOUT = 120.0
SHA = re.compile(r"[a-f0-9]{64}\Z")
MEDIA_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}\Z")
TONE_STAGE_FILES = ("denoised.wav", "processed.wav", "cleaned.wav")
CLAIM_BOUNDARY = {
    "listening_acceptance": "not_established",
    "musical_verdict": "not_established",
    "missed_or_extra_notes": "not_assessed_no_approved_reference",
    "default_adopted": False,
    "master_changed": False,
    "operator_preference": "not_recorded",
}
TONE_AB_KEYS = ("schema_version", "tool", "status", "run", "region", "loudness_match", "excerpts",
                "operator_preference", "experiment", "limitations", "unknown_field_reasons", "claims",
                "listening_accepted", "default_adopted", "master_changed", "perceived_fullness",
                "nasal_quality", "fundamental_32hz_presence", "monitoring_device", "true_peak_dbtp",
                "fan_only_gain", "music_only_gain", "room_response_recovered", "spec", "spec_commit")
SPANS_COPY_KEYS = ("status", "claim_class", "default_adoption", "click_identity", "detector_delay",
                   "physical_capture_latency", "meter", "downbeat_confirmed", "breakdown1_execution",
                   "real_take_phrase_correctness", "missed_or_extra_notes", "listening_acceptance",
                   "performance_issue_confirmed", "uncertainty_summary", "limitations", "join_confidence_rules",
                   "arrangement_totals", "source_extent")
TIMING_ROW_SAFE = ("phrase_id", "label", "label_basis", "span_source_seconds", "status", "abstain_reason")


class Refusal(Exception):
    """Whole-bundle refusal: nothing is published."""
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class LayerRefusal(Exception):
    """One layer becomes unavailable; the rest continue."""
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha_file(path, limit=None):
    digest = hashlib.sha256()
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(fd)
        if limit is not None and info.st_size > limit:
            raise LayerRefusal("layer_input_too_large")
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    finally:
        os.close(fd)
    return digest.hexdigest()


def is_sha(value):
    return isinstance(value, str) and SHA.fullmatch(value) is not None


def finite(value):
    return type(value) in (int, float) and math.isfinite(float(value))


def riff_info(data):
    """Return {format_tag, channels, sample_rate, bits_per_sample, frames} from a RIFF/WAVE byte string."""
    if len(data) < 12 or data[:4] not in (b"RIFF", b"RF64") or data[8:12] != b"WAVE":
        raise LayerRefusal("media_extent_mismatch")
    offset, fmt, frames = 12, None, None
    while offset + 8 <= len(data):
        chunk, size = data[offset:offset + 4], struct.unpack("<I", data[offset + 4:offset + 8])[0]
        body = offset + 8
        if chunk == b"fmt " and size >= 16:
            tag, channels, rate, _, block, bits = struct.unpack("<HHIIHH", data[body:body + 16])
            if tag == 0xFFFE and size >= 40:
                tag = struct.unpack("<H", data[body + 24:body + 26])[0]
            fmt = {"format_tag": tag, "channels": channels, "sample_rate": rate,
                   "bits_per_sample": bits, "block_align": block}
        elif chunk == b"data":
            if fmt is None or not fmt["block_align"]:
                raise LayerRefusal("media_extent_mismatch")
            available = min(size, len(data) - body)
            frames = available // fmt["block_align"]
            break
        offset = body + size + (size & 1)
    if fmt is None or frames is None:
        raise LayerRefusal("media_extent_mismatch")
    return {**{key: fmt[key] for key in ("format_tag", "channels", "sample_rate", "bits_per_sample")}, "frames": frames}


class Composer:
    def __init__(self, session_run, output, *, arrangement=None, timeout_seconds=DEFAULT_TIMEOUT,
                 ffmpeg=None, repo=REPO):
        self.repo = Path(repo).resolve()
        self.session_run = Path(session_run).resolve()
        self.output = Path(output).expanduser().resolve()
        self.arrangement = Path(arrangement).resolve() if arrangement else self.repo / "program" / "demo-arrangement.json"
        if not finite(timeout_seconds) or not 1 <= float(timeout_seconds) <= MAX_TIMEOUT:
            raise Refusal("invalid_timeout_seconds")
        self.deadline = time.monotonic() + float(timeout_seconds)
        self.timeout_seconds = float(timeout_seconds)
        self.ffmpeg = ffmpeg
        self.inputs = {}      # path -> {"sha256_before", "layers": set}
        self.media = {}       # name -> record
        self.media_layer = {}  # name -> layer
        self.commands = []
        self.staging = None

    # ----- refusals and IO ------------------------------------------------
    def check_output(self):
        if self.output.exists() or self.output.is_symlink():
            raise Refusal("output_exists")
        parts = self.output.parts
        for index in range(len(parts) - 1):
            if parts[index] == "artifacts" and parts[index + 1] == "runs":
                raise Refusal("output_inside_runs")
        if self.output.is_relative_to(self.session_run.parent) and self.session_run.parent.name == "runs":
            raise Refusal("output_inside_runs")
        artifacts = (self.repo / "artifacts").resolve()
        if not self.output.is_relative_to(artifacts) or self.output == artifacts:
            raise Refusal("output_outside_artifacts")

    def track(self, path, layer, digest):
        record = self.inputs.setdefault(str(path), {"sha256_before": digest, "layers": set()})
        record["layers"].add(layer)
        if record["sha256_before"] != digest:
            raise LayerRefusal("input_changed_during_compose")

    def read_bytes(self, path, layer, limit=MAX_JSON_BYTES, too_large="layer_input_too_large"):
        path = Path(path).resolve()
        try:
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except FileNotFoundError as exc:
            raise LayerRefusal("input_missing") from exc
        except OSError as exc:
            raise LayerRefusal("input_unreadable") from exc
        try:
            info = os.fstat(fd)
            if info.st_size > limit:
                raise LayerRefusal(too_large)
            chunks, remaining = [], info.st_size
            while remaining > 0:
                chunk = os.read(fd, min(remaining, 1024 * 1024))
                if not chunk:
                    raise LayerRefusal("input_changed_during_compose")
                chunks.append(chunk)
                remaining -= len(chunk)
            data = b"".join(chunks)
        finally:
            os.close(fd)
        self.track(path, layer, sha_bytes(data))
        return path, data

    def read_json(self, path, layer):
        path, data = self.read_bytes(path, layer)
        try:
            value = json.loads(data, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))
        except (ValueError, UnicodeDecodeError, RecursionError) as exc:
            raise LayerRefusal("layer_schema_unknown") from exc
        if not isinstance(value, dict):
            raise LayerRefusal("layer_schema_unknown")
        return path, value, sha_bytes(data)

    def remaining(self):
        return self.deadline - time.monotonic()

    def add_media(self, name, data, *, expected_sha, frames, sample_rate, channels, role, layer):
        if not MEDIA_NAME.fullmatch(name) or name in self.media:
            raise LayerRefusal("layer_schema_unknown")
        digest = sha_bytes(data)
        if expected_sha is not None and digest != expected_sha:
            raise LayerRefusal("layer_hash_mismatch")
        info = riff_info(data)
        if info["frames"] != frames or info["sample_rate"] != sample_rate or info["channels"] != channels:
            raise LayerRefusal("media_extent_mismatch")
        target = self.staging / "media" / name
        with open(target, "xb") as stream:
            stream.write(data)
        self.media[name] = {"file": "media/" + name, "sha256": digest, "frames": frames,
                            "sample_rate": sample_rate, "channels": channels, "role": role}
        self.media_layer[name] = layer
        return name

    def drop_layer_media(self, layer):
        for name in [key for key, owner in self.media_layer.items() if owner == layer]:
            (self.staging / "media" / name).unlink(missing_ok=True)
            self.media.pop(name, None)
            self.media_layer.pop(name, None)

    # ----- session ----------------------------------------------------------
    def session_binding(self):
        manifest_path = self.session_run / "manifest.json"
        try:
            path, data = self.read_bytes(manifest_path, "session")
            manifest = json.loads(data)
        except (LayerRefusal, ValueError, UnicodeDecodeError) as exc:
            raise Refusal("session_manifest_unreadable") from exc
        if not isinstance(manifest, dict):
            raise Refusal("session_manifest_unreadable")
        source = manifest.get("source")
        original = source.get("sha256") if isinstance(source, dict) else None
        if not is_sha(original):
            raise Refusal("session_source_hash_required")
        pcm = manifest.get("pcm") if isinstance(manifest.get("pcm"), dict) else {}
        duration = pcm.get("duration_seconds")
        if not finite(duration) and finite(pcm.get("sample_count")) and finite(pcm.get("sample_rate")) and pcm["sample_rate"]:
            duration = pcm["sample_count"] / pcm["sample_rate"]
        timeline = manifest.get("timeline") if isinstance(manifest.get("timeline"), dict) else {}
        self.manifest = manifest
        self.original = original
        self.manifest_sha = sha_bytes(data)
        hashes = manifest.get("output_sha256") if isinstance(manifest.get("output_sha256"), dict) else {}
        self.output_hashes = {key: value for key, value in hashes.items() if is_sha(value)}
        return {"run_id": str(manifest.get("run_id") or self.session_run.name), "manifest_sha256": self.manifest_sha,
                "original_source_sha256": original,
                "source_extent_seconds": float(duration) if finite(duration) else None,
                "audio_start_seconds": float(timeline["audio_start_seconds"]) if finite(timeline.get("audio_start_seconds")) else 0.0,
                "format_start_seconds": float(timeline["format_start_seconds"]) if finite(timeline.get("format_start_seconds")) else 0.0,
                "timeline_no_time_stretch": timeline.get("no_time_stretch") if isinstance(timeline.get("no_time_stretch"), bool) else None}

    def tone_stage(self):
        profile_name, profile_sha = None, None
        try:
            _, profile, profile_sha = self.read_json(self.session_run / "applied-profile.json", "stages")
            profile_name = profile.get("name") if isinstance(profile.get("name"), str) else None
        except LayerRefusal:
            profile_name = None
        return {"run_id": str(self.manifest.get("run_id") or self.session_run.name),
                "profile_name": profile_name, "applied_profile_sha256": profile_sha,
                "denoised_sha256": self.output_hashes.get("denoised.wav"),
                "processed_sha256": self.output_hashes.get("processed.wav"),
                "cleaned_sha256": self.output_hashes.get("cleaned.wav"),
                "hash_basis": "session manifest output_sha256 (verified again when the review server opens served media)",
                "role": "FULLER delivery: pure denoise, tone/dynamics, delivery master"}

    # ----- layers -----------------------------------------------------------
    def layer_tone_ab(self, directory, trial_excerpts):
        directory = Path(directory).resolve()
        path, value, digest = self.read_json(directory / "tone-ab.json", "tone_ab")
        excerpts = value.get("excerpts")
        run = value.get("run")
        if value.get("tool") != "tone_ab" or value.get("schema_version") != 1 or not isinstance(excerpts, dict) \
                or not isinstance(excerpts.get("pairs"), list) or not isinstance(run, dict) \
                or not isinstance(value.get("loudness_match"), dict):
            raise LayerRefusal("layer_schema_unknown")
        if run.get("source_sha256") != self.original:
            raise LayerRefusal("layer_source_mismatch")
        if run.get("manifest_sha256") not in (None, self.manifest_sha):
            raise LayerRefusal("layer_source_mismatch")
        frames = excerpts.get("frames_per_file")
        if type(frames) is not int or frames <= 0:
            raise LayerRefusal("layer_schema_unknown")
        pair_media = []
        for pair in excerpts["pairs"]:
            files = pair.get("files") if isinstance(pair, dict) else None
            if not isinstance(files, dict) or set(files) != {"X", "Y"} or type(pair.get("pair")) is not int:
                raise LayerRefusal("layer_schema_unknown")
            names = {}
            for side, record in files.items():
                name = record.get("file") if isinstance(record, dict) else None
                if not isinstance(name, str) or Path(name).name != name or not is_sha(record.get("sha256")):
                    raise LayerRefusal("layer_schema_unknown")
                _, data = self.read_bytes(directory / name, "tone_ab", MAX_MEDIA_BYTES, "layer_input_too_large")
                names[side] = self.add_media(f"excerpt-{pair['pair']}-{side}.wav", data, expected_sha=record["sha256"],
                                             frames=frames, sample_rate=record.get("sample_rate"),
                                             channels=record.get("channels"), role=f"tone_ab blind excerpt pair {pair['pair']} {side}",
                                             layer="tone_ab")
            pair_media.append({"pair": pair["pair"], "X": names["X"], "Y": names["Y"]})
        layer = {"status": "available", "sha256": digest, "file": path.name,
                 "binding": {"run_id": run.get("run_id"), "source_sha256": run.get("source_sha256"),
                             "manifest_sha256": run.get("manifest_sha256"),
                             "manifest_matches_session": run.get("manifest_sha256") == self.manifest_sha},
                 "pair_media": pair_media}
        for key in TONE_AB_KEYS:
            if key in value:
                layer["tone_ab_status" if key == "status" else key] = value[key]
        layer["trial"] = self.trial(directory, value, excerpts) if trial_excerpts else {
            "status": "unavailable", "reason": "trial_excerpts_not_requested"}
        return layer

    def trial(self, directory, value, excerpts):
        experiment = value.get("experiment") if isinstance(value.get("experiment"), dict) else {}
        per_arm = value["loudness_match"].get("per_arm") if isinstance(value["loudness_match"].get("per_arm"), dict) else {}
        gain = (per_arm.get("trial_lowshelf") or {}).get("gain_db") if isinstance(per_arm.get("trial_lowshelf"), dict) else None
        controls = experiment.get("controls") if isinstance(experiment.get("controls"), dict) else None
        name = experiment.get("file")
        base = {"label_basis": "experiment.controls", "controls": controls, "gain_db": gain,
                "experiment_status": experiment.get("status"), "adopted": False, "blinded": False,
                "role": "TRIAL unreviewed experiment, never adopted"}
        if not isinstance(name, str) or Path(name).name != name or not is_sha(experiment.get("sha256")) \
                or not finite(gain) or controls is None:
            return {**base, "status": "unavailable", "reason": "trial_not_described_in_tone_ab"}
        ffmpeg = self.ffmpeg or os.environ.get("FFMPEG") or shutil.which("ffmpeg")
        if not ffmpeg or not Path(ffmpeg).is_file():
            return {**base, "status": "unavailable", "reason": "ffmpeg_not_resolved"}
        trial_path = (directory / name).resolve()
        try:
            before = sha_file(trial_path, MAX_MEDIA_BYTES)
        except FileNotFoundError:
            return {**base, "status": "unavailable", "reason": "input_missing"}
        except LayerRefusal as error:
            return {**base, "status": "unavailable", "reason": error.code}
        if before != experiment["sha256"]:
            return {**base, "status": "unavailable", "reason": "layer_hash_mismatch"}
        self.track(trial_path, "tone_ab.trial", before)
        frames = excerpts["frames_per_file"]
        pairs, workdir = [], self.staging / "trial-work"
        workdir.mkdir()
        try:
            for pair in excerpts["pairs"]:
                start, end = pair.get("start_sample"), pair.get("end_sample_exclusive")
                if type(start) is not int or type(end) is not int or end - start != frames:
                    return {**base, "status": "unavailable", "reason": "media_extent_mismatch"}
                remaining = self.remaining()
                if remaining <= 1:
                    return {**base, "status": "unavailable", "reason": "compose_timeout"}
                out = workdir / f"trial-{pair['pair']}.wav"
                argv = [str(ffmpeg), "-nostdin", "-hide_banner", "-loglevel", "error", "-i", str(trial_path),
                        "-af", f"atrim=start_sample={start}:end_sample={end},volume={float(gain)!r}dB:precision=double",
                        "-map_metadata", "-1", "-fflags", "+bitexact", "-flags:a", "+bitexact",
                        "-c:a", "pcm_f32le", "-f", "wav", str(out)]
                timeout = min(SUBPROCESS_TIMEOUT, remaining)
                started = time.monotonic()
                try:
                    result = subprocess.run(argv, capture_output=True, timeout=timeout, check=False)
                except subprocess.TimeoutExpired:
                    self.commands.append({"argv": argv[:1] + ["…"], "timeout_seconds": timeout, "returncode": None})
                    return {**base, "status": "unavailable", "reason": "ffmpeg_timeout"}
                self.commands.append({"argv": [Path(argv[0]).name] + argv[1:6] + ["<trial-lowshelf.wav>"] + argv[7:-1] + ["<out>"],
                                      "timeout_seconds": round(timeout, 3), "returncode": result.returncode,
                                      "elapsed_seconds": round(time.monotonic() - started, 3)})
                if result.returncode != 0 or not out.is_file():
                    return {**base, "status": "unavailable", "reason": "ffmpeg_failed"}
                data = out.read_bytes()
                rate = pair["files"]["X"].get("sample_rate")
                channels = pair["files"]["X"].get("channels")
                try:
                    media = self.add_media(f"trial-{pair['pair']}.wav", data, expected_sha=None, frames=frames,
                                           sample_rate=rate, channels=channels,
                                           role=f"TRIAL lowshelf excerpt pair {pair['pair']} (unblinded)", layer="tone_ab.trial")
                except LayerRefusal as error:
                    self.drop_layer_media("tone_ab.trial")
                    return {**base, "status": "unavailable", "reason": error.code}
                pairs.append({"pair": pair["pair"], "media": media, "start_sample": start, "end_sample_exclusive": end})
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
        return {**base, "status": "available", "source_file": name, "source_sha256": before,
                "filter": f"atrim=start_sample=a:end_sample=b, volume={gain}dB:precision=double",
                "pairs": pairs}

    def layer_spans(self, path, arrangement_sha):
        path, value, digest = self.read_json(path, "coverage.intent")
        provenance = value.get("provenance")
        if value.get("tool") != "phrase_anchor" or value.get("schema_version") != 1 \
                or value.get("status") != "intent_projection_not_detection" or not isinstance(provenance, dict) \
                or not isinstance(value.get("units"), list) or not isinstance(value.get("boundaries"), list):
            raise LayerRefusal("layer_schema_unknown")
        if provenance.get("original_source_sha256") != self.original:
            raise LayerRefusal("layer_source_mismatch")
        if arrangement_sha is not None and provenance.get("arrangement_sha256") != arrangement_sha:
            raise LayerRefusal("layer_hash_mismatch")
        anchor = provenance.get("anchor") if isinstance(provenance.get("anchor"), dict) else {}
        units, boundaries = [], []
        for unit in value["units"]:
            if not isinstance(unit, dict) or not finite(unit.get("start_source_seconds")) or not finite(unit.get("end_source_seconds")):
                raise LayerRefusal("layer_schema_unknown")
            units.append({key: unit.get(key) for key in ("id", "kind", "section_id", "section_unit_index", "musical_phrase",
                                                         "coverage", "start_source_seconds", "end_source_seconds",
                                                         "click_count", "basis", "section_provenance")})
        for row in value["boundaries"]:
            if not isinstance(row, dict) or not finite(row.get("source_seconds")):
                raise LayerRefusal("layer_schema_unknown")
            grid = row.get("grid") if isinstance(row.get("grid"), dict) else {}
            checker = row.get("checker_cross_reference") if isinstance(row.get("checker_cross_reference"), dict) else {}
            structural = row.get("structural_status")
            boundaries.append({"id": row.get("id"), "source_seconds": row["source_seconds"],
                               "join_confidence": row.get("join_confidence"),
                               "structural_status": structural if isinstance(structural, list) else [],
                               "on_interpolated_half_period": grid.get("on_interpolated_half_period"),
                               "grid_label": grid.get("grid_label"), "checker_status": checker.get("checker_status"),
                               "coverage": row.get("coverage"), "confidence_kind": row.get("confidence_kind")})
        entry = {"file": path.name, "sha256": digest, "k0": anchor.get("k0"), "anchor_status": anchor.get("status"),
                 "anchor_adopted": False, "anchor_adopted_as_recorded": anchor.get("adopted"),
                 "arrangement_sha256": provenance.get("arrangement_sha256"),
                 "grid_analyzed_input_sha256": provenance.get("grid_analyzed_input_sha256"),
                 "timeline_no_stretch_verified": provenance.get("timeline_no_stretch_verified"),
                 "units": units, "boundaries": boundaries}
        for key in SPANS_COPY_KEYS:
            if key in value:
                entry[key] = value[key]
        return entry

    def layer_detector(self, path):
        path, value, digest = self.read_json(path, "coverage.detector")
        observations = value.get("observations")
        lineage = value.get("lineage") if isinstance(value.get("lineage"), dict) else {}
        spans = observations.get("proposed_review_spans") if isinstance(observations, dict) else None
        if value.get("tool") != "phrases" or not isinstance(spans, list):
            raise LayerRefusal("layer_schema_unknown")
        if lineage.get("original_source_sha256") != self.original:
            raise LayerRefusal("layer_source_mismatch")
        source = value.get("source") if isinstance(value.get("source"), dict) else {}
        analyzed = lineage.get("input_sha256") or source.get("sha256")
        return {"status": "available", "file": path.name, "sha256": digest, "analyzed_input_sha256": analyzed,
                "lineage_status": lineage.get("status"), "timeline_basis": lineage.get("timeline_basis"),
                "timeline_no_stretch_verified": lineage.get("timeline_no_stretch_verified"),
                "proposed_review_spans": spans, "interpretation": value.get("interpretation")}

    def layer_triage(self, path):
        path, value, digest = self.read_json(path, "flags_triage")
        if value.get("schema_id") != "video-utils.flags-triage.s2" or value.get("schema_version") != 1:
            raise LayerRefusal("layer_schema_unknown")
        if value.get("source_sha256") != self.original:
            raise LayerRefusal("layer_source_mismatch")
        denominators = value.get("denominators")
        lists = [value.get(key) for key in ("shown", "suppressed", "hidden_navigation")]
        if not isinstance(denominators, dict) or not all(isinstance(item, list) for item in lists) \
                or not isinstance(value.get("window_basis"), dict):
            raise LayerRefusal("layer_schema_unknown")
        if [len(item) for item in lists] != [denominators.get("shown"), denominators.get("suppressed_lower_priority"),
                                             denominators.get("navigation_hidden")] \
                or sum(len(item) for item in lists) != denominators.get("total_flags"):
            raise LayerRefusal("layer_schema_unknown")
        return {"status": "available", "file": path.name, "sha256": digest, "document": value}

    def layer_timing(self, path, bound_inputs):
        path, value, digest = self.read_json(path, "phrase_timing")
        inputs = value.get("inputs") if isinstance(value.get("inputs"), dict) else {}
        if value.get("tool") != "phrase_timing" or value.get("schema_version") != 1 or not isinstance(value.get("phrases"), list):
            raise LayerRefusal("layer_schema_unknown")
        analyzed = inputs.get("analyzed_input_sha256")
        if analyzed not in bound_inputs:
            raise LayerRefusal("layer_source_mismatch")
        return {"status": "available", "file": f"{path.parent.name}/{path.name}", "sha256": digest, "analyzed_input_sha256": analyzed,
                "source_binding": bound_inputs[analyzed], "document": value}

    # ----- compose ----------------------------------------------------------
    def compose(self, *, tone_ab=None, flags_triage=None, detector_phrases=None, phrase_spans=(),
                phrase_timing=(), trial_excerpts=False):
        self.check_output()
        binding = self.session_binding()
        self.output.parent.mkdir(parents=True, exist_ok=True)
        self.staging = self.output.parent / f".{self.output.name}.staging-{os.getpid()}-{secrets.token_hex(4)}"
        self.staging.mkdir()
        (self.staging / "media").mkdir()
        try:
            bundle = self.build(binding, tone_ab, flags_triage, detector_phrases, phrase_spans, phrase_timing, trial_excerpts)
            text = json.dumps(bundle, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
            (self.staging / "bundle.json").write_text(text, encoding="utf-8")
            if self.output.exists():
                raise Refusal("output_exists")
            os.rename(self.staging, self.output)
            self.staging = None
            return bundle
        finally:
            if self.staging is not None:
                shutil.rmtree(self.staging, ignore_errors=True)

    def guarded(self, layer, function, *args):
        try:
            return function(*args)
        except LayerRefusal as error:
            self.drop_layer_media(layer)
            return {"status": "unavailable", "reason": error.code}

    def build(self, binding, tone_ab, flags_triage, detector_phrases, phrase_spans, phrase_timing, trial_excerpts):
        tone = self.tone_stage()
        arrangement_sha = None
        try:
            _, data = self.read_bytes(self.arrangement, "stages.arrangement")
            arrangement_sha = sha_bytes(data)
        except LayerRefusal:
            arrangement_sha = None
        layers = {}
        layers["tone_ab"] = self.guarded("tone_ab", self.layer_tone_ab, tone_ab, trial_excerpts) if tone_ab else \
            {"status": "unavailable", "reason": "input_not_supplied"}
        intent_files, intent_refusals = [], []
        for path in phrase_spans:
            entry = self.guarded("coverage.intent", self.layer_spans, path, arrangement_sha)
            if entry.get("status") == "unavailable":
                intent_refusals.append({"file": Path(path).name, "reason": entry["reason"]})
            else:
                intent_files.append(entry)
        intent_files.sort(key=lambda item: (item["k0"] if type(item.get("k0")) is int else 1 << 30, item["file"]))
        intent = {"status": "available" if intent_files else "unavailable", "files": intent_files, "refused": intent_refusals}
        if not intent_files:
            intent["reason"] = intent_refusals[0]["reason"] if intent_refusals else "input_not_supplied"
        detector = self.guarded("coverage.detector", self.layer_detector, detector_phrases) if detector_phrases else \
            {"status": "unavailable", "reason": "input_not_supplied"}
        coverage = {"status": "available" if "available" in (intent["status"], detector["status"]) else "unavailable",
                    "source_min_seconds": min(binding["audio_start_seconds"], binding["format_start_seconds"]),
                    "source_max_seconds": binding["audio_start_seconds"] + (binding["source_extent_seconds"] or 0.0),
                    "intent": intent, "detector": detector,
                    "overlap_is_not_agreement": "Overlap between lanes is not agreement, accuracy or correctness."}
        if coverage["status"] == "unavailable":
            coverage["reason"] = intent.get("reason") or detector.get("reason")
        layers["coverage"] = coverage
        layers["flags_triage"] = self.guarded("flags_triage", self.layer_triage, flags_triage) if flags_triage else \
            {"status": "unavailable", "reason": "input_not_supplied"}
        bound_inputs = {}
        for name in TONE_STAGE_FILES + ("source.wav",):
            if name in self.output_hashes:
                bound_inputs[self.output_hashes[name]] = "session manifest output " + name
        if detector.get("status") == "available" and is_sha(detector.get("analyzed_input_sha256")):
            bound_inputs.setdefault(detector["analyzed_input_sha256"], "detector phrases lineage to original source")
        for entry in intent_files:
            if is_sha(entry.get("grid_analyzed_input_sha256")):
                bound_inputs.setdefault(entry["grid_analyzed_input_sha256"], "phrase_anchor grid provenance to original source")
        timing_files, timing_refusals = [], []
        for path in phrase_timing:
            entry = self.guarded("phrase_timing", self.layer_timing, path, bound_inputs)
            if entry.get("status") == "unavailable":
                timing_refusals.append({"file": f"{Path(path).parent.name}/{Path(path).name}", "reason": entry["reason"]})
            else:
                timing_files.append(entry)
        timing = {"status": "available" if timing_files else "unavailable", "files": timing_files, "refused": timing_refusals}
        if not timing_files:
            timing["reason"] = timing_refusals[0]["reason"] if timing_refusals else "input_not_supplied"
        layers["phrase_timing"] = timing

        # Recheck every input after composition.
        changed_layers = set()
        for path, record in self.inputs.items():
            try:
                after = sha_file(path)
            except (OSError, LayerRefusal):
                after = None
            record["sha256_after"] = after
            if after != record["sha256_before"]:
                changed_layers |= record["layers"]
        if "session" in changed_layers:
            raise Refusal("session_manifest_unreadable")
        for layer in changed_layers:
            self.drop_layer_media(layer)
            if layer == "tone_ab.trial" and layers["tone_ab"].get("status") == "available":
                layers["tone_ab"]["trial"] = {"status": "unavailable", "reason": "input_changed_during_compose"}
            elif layer in ("tone_ab", "flags_triage"):
                layers[layer] = {"status": "unavailable", "reason": "input_changed_during_compose"}
            elif layer == "phrase_timing":
                layers["phrase_timing"] = {"status": "unavailable", "reason": "input_changed_during_compose", "files": [], "refused": []}
            elif layer.startswith("coverage"):
                layers["coverage"] = {"status": "unavailable", "reason": "input_changed_during_compose",
                                      "intent": {"status": "unavailable", "reason": "input_changed_during_compose", "files": []},
                                      "detector": {"status": "unavailable", "reason": "input_changed_during_compose"}}

        analysis = []
        denoised = tone["denoised_sha256"]

        def add_analysis(layer, analyzed, no_stretch):
            analysis.append({"layer": layer, "analyzed_input_sha256": analyzed if is_sha(analyzed) else None,
                             "matches_tone_denoised": bool(is_sha(analyzed) and analyzed == denoised),
                             "timeline_no_stretch_verified": no_stretch if isinstance(no_stretch, bool) else None})
        coverage = layers["coverage"]
        if coverage["detector"].get("status") == "available":
            add_analysis("coverage.detector", coverage["detector"]["analyzed_input_sha256"],
                         coverage["detector"].get("timeline_no_stretch_verified"))
        for entry in coverage["intent"].get("files", []):
            add_analysis(f"coverage.intent:{entry['file']}", entry.get("grid_analyzed_input_sha256"), entry.get("timeline_no_stretch_verified"))
        if layers["flags_triage"].get("status") == "available":
            add_analysis("flags_triage", None, None)
        for entry in layers["phrase_timing"].get("files", []):
            add_analysis(f"phrase_timing:{entry['file']}", entry["analyzed_input_sha256"], None)
        if layers["tone_ab"].get("status") == "available":
            add_analysis("tone_ab", None, None)
            analysis[-1].update({"analyzed_input_sha256": None, "note": "tone_ab reads the session stage files directly"})

        stages = {
            "source": {"original_sha256": self.original, "source_wav_sha256": self.output_hashes.get("source.wav"),
                       "role": "original recording identity and decoded native source PCM"},
            "tone": tone,
            "arrangement": {"arrangement_sha256": arrangement_sha, "arrangement_file": self.arrangement.name,
                            "spans": [{"file": entry["file"], "sha256": entry["sha256"], "k0": entry.get("k0"),
                                       "anchor_status": entry.get("anchor_status")} for entry in coverage["intent"].get("files", [])],
                            "adopted": False, "role": "operator arrangement intent projected on the fitted grid"},
            "analysis": analysis,
        }
        bundle = {"schema_id": SCHEMA_ID, "schema_version": SCHEMA_VERSION, "generated_utc": utc_now(),
                  "session_binding": binding, "stages": stages, "layers": layers, "media": self.media,
                  "claim_boundary": dict(CLAIM_BOUNDARY), "unknown_fields": self.unknown_fields(layers),
                  "composer_sha256": sha_file(Path(__file__).resolve()),
                  "inputs": [{"path": self.display_path(path), "sha256_before": record["sha256_before"],
                              "sha256_after": record.get("sha256_after"), "layers": sorted(record["layers"])}
                             for path, record in sorted(self.inputs.items())],
                  "commands": self.commands, "timeout_seconds": self.timeout_seconds,
                  "evidence_kind": "composed_existing_evidence_not_new_analysis"}
        return bundle

    def display_path(self, path):
        path = Path(path)
        for base in (self.repo, self.repo.parents[2] if len(self.repo.parents) > 2 else self.repo):
            try:
                return str(path.relative_to(base))
            except ValueError:
                continue
        return path.name

    def unknown_fields(self, layers):
        tone = layers["tone_ab"] if layers["tone_ab"].get("status") == "available" else {}
        reasons = tone.get("unknown_field_reasons") if isinstance(tone.get("unknown_field_reasons"), dict) else {}
        intent_files = layers["coverage"]["intent"].get("files", []) if layers["coverage"].get("intent") else []
        spans = intent_files[0] if intent_files else {}
        timing_files = layers["phrase_timing"].get("files", [])
        timing = timing_files[0]["document"] if timing_files else {}
        delay = timing.get("detector_delay") if isinstance(timing.get("detector_delay"), dict) else None

        def from_tone(key, default_reason):
            return {"value": tone.get(key) if key in tone else None,
                    "reason": reasons.get(key, default_reason),
                    "basis": "copied from tone-ab.json" if key in tone else "tone_ab layer unavailable"}

        return {
            "operator_preference": {"value": None, "reason": "not recorded"},
            "listening_acceptance": {"value": "not_established", "reason": "No operator listening review exists for these renders."},
            "perceived_fullness": from_tone("perceived_fullness", "Perceived fullness is a listening judgement."),
            "nasal_quality": from_tone("nasal_quality", "Nasal quality is a listening judgement."),
            "fundamental_32hz_presence": from_tone("fundamental_32hz_presence", "A band level is not a measured played C1 fundamental."),
            "monitoring_device": {"value": None, "reason": reasons.get("monitoring_device", "The operator's playback device and level are unknown.")},
            "true_peak_dbtp": {"value": tone.get("true_peak_dbtp") if tone else None,
                               "reason": reasons.get("true_peak_dbtp", "True peak was not measured; only sample peak is reported.")},
            "fan_only_gain": {"value": None, "reason": reasons.get("fan_only_gain", "Fan and music are not separated.")},
            "music_only_gain": {"value": None, "reason": reasons.get("music_only_gain", "Fan and music are not separated.")},
            "click_identity": {"value": "unverified", "reason": "Periodic high-frequency transients are not a verified metronome."},
            "physical_capture_latency": {"value": "uncalibrated", "reason": "Microphone and capture-chain latency were never measured."},
            "detector_delay": ({"value": {"status": delay.get("status"), "attack_delay_seconds": delay.get("attack_delay_seconds"),
                                          "click_delay_seconds": delay.get("click_delay_seconds")},
                                "reason": "Copied from phrase_timing; synthetic-probe medians, physical capture latency uncalibrated."}
                               if delay else {"value": "uncalibrated", "reason": "No detector delay calibration was supplied."}),
            "meter": {"value": "unknown", "reason": "Meter and downbeat are not identified by any layer."},
            "downbeat_confirmed": {"value": False, "reason": "The anchor is a review candidate, not a confirmed downbeat."},
            "anchor_adopted": {"value": False, "reason": "k29/k30/k31 anchors are review candidates; none is adopted."},
            "breakdown1_execution": {"value": spans.get("breakdown1_execution", "unknown_operator_reported_possible_rush_or_skip"),
                                     "reason": "Operator context copied verbatim; execution of breakdown 1 is unknown."},
            "real_take_phrase_correctness": {"value": "unknown_until_operator_marks_boundaries",
                                             "reason": "Phrase correctness needs operator-marked boundaries."},
            "missed_or_extra_notes": {"value": "not_assessed_no_approved_reference",
                                      "reason": "No approved expected-rhythm or note reference exists."},
            "phrase_timing.real_take_status": {"value": timing.get("real_take_status", "unvalidated_until_operator_spot_check"),
                                               "reason": "Phrase timing offsets are unvalidated until an operator spot check."},
            "browser_level_match": {"value": "excerpt files pre-gained by tone_ab; browser output level and device unmeasured",
                                    "reason": "The page applies no gain; playback level depends on the device."},
            "walkthrough_listening": {"value": "not_performed", "reason": "Automated browser checks are muted; nobody listened."},
        }


def compose(session_run, output, **options):
    composer_options = {key: options.pop(key) for key in ("arrangement", "timeout_seconds", "ffmpeg", "repo") if key in options}
    return Composer(session_run, output, **composer_options).compose(**options)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("compose", help="Compose one bundle directory")
    build.add_argument("--session-run", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--tone-ab", type=Path)
    build.add_argument("--flags-triage", type=Path)
    build.add_argument("--detector-phrases", type=Path)
    build.add_argument("--phrase-spans", type=Path, nargs="*", default=[])
    build.add_argument("--phrase-timing", type=Path, nargs="*", default=[])
    build.add_argument("--arrangement", type=Path)
    build.add_argument("--trial-excerpts", action="store_true")
    build.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT)
    args = parser.parse_args(argv)
    try:
        bundle = compose(args.session_run, args.output, arrangement=args.arrangement, timeout_seconds=args.timeout_seconds,
                         tone_ab=args.tone_ab, flags_triage=args.flags_triage, detector_phrases=args.detector_phrases,
                         phrase_spans=args.phrase_spans, phrase_timing=args.phrase_timing, trial_excerpts=args.trial_excerpts)
    except Refusal as error:
        print(json.dumps({"status": "refused", "error": error.code}), file=sys.stderr)
        return 1
    except OSError:
        print(json.dumps({"status": "refused", "error": "output_or_input_io_failed"}), file=sys.stderr)
        return 1
    layers = bundle["layers"]
    print(json.dumps({"status": "practice_s2_bundle_written", "output": str(Path(args.output).resolve()),
                      "layers": {name: value.get("status") for name, value in layers.items()},
                      "trial": layers["tone_ab"].get("trial", {}).get("status") if layers["tone_ab"].get("status") == "available" else None,
                      "media": len(bundle["media"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
