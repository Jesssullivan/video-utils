#!/usr/bin/env python3
"""Render a private, portable run report using only the Python standard library."""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import math
import os
from pathlib import Path
import struct
import tempfile
from urllib.parse import quote


def escape(value):
    return html.escape(str(value), quote=True)


def load_json(path):
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value


def finite(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def artifact(root, value):
    """Accept existing run-local files, including safe nested artifact paths."""
    if isinstance(value, dict):
        value = value.get("path", value.get("file"))
    if not isinstance(value, str) or not value or "\\" in value:
        return None
    candidate = Path(value)
    if candidate.is_absolute() or ":" in value or ".." in candidate.parts:
        return None
    resolved = (root / candidate).resolve()
    if not resolved.is_relative_to(root.resolve()) or not resolved.is_file():
        return None
    return candidate.as_posix()


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def source_identity(payload):
    source = payload.get("source", {})
    return source.get("sha256") if isinstance(source, dict) else None


def analysis_lineage(root, manifest, analysis):
    if not analysis:
        return "unavailable"
    fingerprint = source_identity(analysis)
    original = source_identity(manifest)
    if not fingerprint or not original:
        return "rejected_missing_source_identity"
    if fingerprint == original:
        return "original_source_hash_bound"
    hashes = manifest.get("output_sha256", {})
    if isinstance(hashes, dict):
        for name, expected in hashes.items():
            if name not in {"source.wav", "denoised.wav", "cleaned.wav"} or expected != fingerprint:
                continue
            local = strict_artifact(root, name)
            if local and sha256(root / local) == expected:
                return "verified_run_derivative_hash_bound"
    return "rejected_unrelated_or_modified_source"


def export_evidence(root, manifest):
    outcome = load_json(root / "export" / "outcome.json")
    if not outcome:
        return {}, "unavailable"
    if not source_identity(manifest) or outcome.get("source_sha256") != source_identity(manifest):
        return {}, "rejected_export_source_identity"
    value = outcome.get("video")
    if isinstance(value, str) and Path(value).is_absolute():
        try:
            value = Path(value).resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            return {}, "rejected_export_path"
    local = artifact(root, value) if value else None
    if value and not local:
        return {}, "rejected_export_path"
    hashes = outcome.get("output_sha256", {})
    expected = hashes.get(Path(local).name) if local and isinstance(hashes, dict) else None
    if expected and sha256(root / local) != expected:
        return {}, "rejected_export_hash_mismatch"
    result = dict(outcome)
    result["video"] = local
    return result, "source_and_video_hash_verified" if expected else "source_hash_bound_export_unverified"


def auxiliary_evidence(root, manifest):
    original = source_identity(manifest)
    payloads = {}
    statuses = {}
    for name in ("dag", "flags", "markers"):
        payload = load_json(root / f"{name}.json")
        if not payload:
            statuses[name] = "unavailable"
        elif not original or payload.get("source_sha256") != original:
            statuses[name] = "rejected_source_identity"
        else:
            payloads[name] = payload
            statuses[name] = "source_hash_bound"
    graph = payloads.get("dag", {})
    hashes = graph.get("artifact_hashes", {})
    if isinstance(hashes, dict):
        for name, expected in hashes.items():
            local = strict_artifact(root, name)
            if not local or sha256(root / local) != expected:
                statuses["dag"] = "rejected_stale_artifact_hash"
                payloads.pop("dag", None)
                break
    external = graph.get("external_context_hashes", {})
    registry = Path(__file__).resolve().parents[1] / "program" / "instrument.json"
    if external and (not isinstance(external, dict) or set(external) != {"program/instrument.json"}
                     or not registry.is_file() or registry.is_symlink()
                     or sha256(registry) != external["program/instrument.json"]):
        statuses["dag"] = "rejected_stale_external_context"
        payloads.pop("dag", None)
    for name in ("dag", "markers"):
        expected = payloads.get(name, {}).get("flags_sha256")
        if expected and (not (root / "flags.json").is_file() or sha256(root / "flags.json") != expected):
            statuses[name] = "rejected_stale_flags_hash"
            payloads.pop(name, None)
            if name == "dag":
                statuses["flags"] = "rejected_stale_dag_flags_binding"
                payloads.pop("flags", None)
    if statuses.get("dag", "").startswith("rejected"):
        for name in ("flags", "markers"):
            if name in payloads:
                statuses[name] = "rejected_stale_graph_context"
                payloads.pop(name)
    return payloads, statuses


def review_section(manifest, payloads, statuses):
    flags = payloads.get("flags", {})
    items = flags.get("flags", [])
    if not isinstance(items, list):
        items = []
    timeline = manifest.get("timeline", {})
    if not isinstance(timeline, dict):
        timeline = {}
    audio_start = finite(timeline.get("audio_start_seconds")) or 0
    format_start = finite(timeline.get("format_start_seconds")) or 0
    rows = []
    for item in items[:1000]:
        if not isinstance(item, dict):
            continue
        start = finite(item.get("source_time_seconds"))
        end = finite(item.get("end_seconds", start))
        if start is None or end is None or end < start:
            continue
        audio = finite(item.get("audio_relative_seconds"))
        audio = max(0, audio if audio is not None else start - audio_start)
        video = max(0, start - format_start)
        kind = item.get("kind", "review_candidate")
        status = item.get("status", "needs_review")
        confidence = item.get("confidence", "unknown")
        rows.append(f'<tr><th>{escape(kind)}</th><td>{start:.3f}–{end:.3f}s</td><td>{escape(status)}<br><span class="caption">{escape(confidence)}</span></td><td><button data-media="audio" data-time="{audio:.6f}">Seek audio</button> <button data-media="video" data-time="{video:.6f}">Seek video</button></td></tr>')
    body = '<table><thead><tr><th>Review candidate</th><th>Original source time</th><th>Review state</th><th>Navigate</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table>' if rows else '<p class="unavailable">No source-bound review spans are available. This does not establish an error-free performance.</p>'
    stages = payloads.get("dag", {}).get("stages", [])
    stage_rows = ''.join(f'<tr><th>{escape(stage.get("id", "stage"))}</th><td>{escape(stage.get("status", "unknown"))}</td></tr>' for stage in stages if isinstance(stage, dict)) if isinstance(stages, list) else ''
    graph = f'<details><summary>Artifact graph evidence</summary><table>{stage_rows}</table><p class="caption">Artifact provenance graph; no autonomous execution or listening acceptance claim.</p></details>' if stage_rows else ''
    marker_count = len(payloads.get("markers", {}).get("markers", [])) if isinstance(payloads.get("markers", {}).get("markers", []), list) else 0
    boundary = f'Review state: {escape(flags.get("status", "unavailable"))}. {len(items)} exported flags; showing at most 1,000. {marker_count} source-bound generic markers; native editor import is unvalidated.'
    identities = ' · '.join(f'{escape(name)}: {escape(status)}' for name, status in statuses.items())
    return f'<section><h2>Rhythm and phrase review</h2><p class="note">Flags are review hypotheses, including reference-comparison candidates where supplied; detector misses do not prove missed notes. Seeking does not start playback. Listen before accepting a finding.</p><p class="caption">{boundary}</p>{body}{graph}<p class="caption">{identities}</p><p id="seek-status" class="caption" role="status"></p></section>'


def feature_evidence(root, manifest):
    payloads, statuses = {}, {}
    for name in ("noise", "tone", "notes", "phrases"):
        payload = load_json(root / f"{name}.json")
        status = analysis_lineage(root, manifest, payload)
        statuses[name] = status
        if payload and not status.startswith("rejected"):
            payloads[name] = payload
    return payloads, statuses


SELECTED_FEATURES = ("clicks", "pitch", "meter", "tonal", "comparisons")
MAX_SELECTED_JSON_BYTES = 20 * 1024 * 1024


def strict_artifact(root, value):
    """Graph selectors cannot traverse symlinks, including run-local aliases."""
    if not isinstance(value, str) or len(value) > 1024:
        return None
    local = artifact(root, value)
    if not local or any((root / Path(*Path(local).parts[:index])).is_symlink()
                        for index in range(1, len(Path(local).parts) + 1)):
        return None
    if any(part.startswith(".staging") for part in Path(local).parts):
        return None
    return local


def selected_feature_evidence(root, manifest, auxiliary, auxiliary_status):
    """Read only explicit verified graph selections; never infer a newest receipt."""
    payloads, statuses, receipts = {}, {}, {}
    graph = auxiliary.get("dag", {})
    selected = graph.get("selected_evidence", {})
    if not isinstance(selected, dict):
        selected = {}
    graph_valid = bool(graph) and auxiliary_status.get("dag") == "source_hash_bound"
    hashes = graph.get("artifact_hashes", {})
    if graph_valid:
        graph_valid = isinstance(hashes, dict) and bool(hashes)
        if graph_valid:
            for path, expected in hashes.items():
                local = strict_artifact(root, path)
                if not local or sha256(root / local) != expected:
                    graph_valid = False
                    break
        external = graph.get("external_context_hashes", {})
        if not isinstance(external, dict):
            graph_valid = False
        elif external:
            registry = Path(__file__).resolve().parents[1] / "program" / "instrument.json"
            graph_valid = (graph_valid and set(external) == {"program/instrument.json"}
                           and registry.is_file() and not registry.is_symlink()
                           and sha256(registry) == external["program/instrument.json"])
    for name in SELECTED_FEATURES:
        row = selected.get(name, {})
        if not isinstance(row, dict):
            row = {}
        state = row.get("status", "not_selected")
        statuses[name] = state[:128] if isinstance(state, str) else "rejected_invalid_status"
        if not graph and auxiliary_status.get("dag", "").startswith("rejected"):
            statuses[name] = "rejected_stale_or_unavailable_graph"
        if state != "verified":
            continue
        if not graph_valid:
            statuses[name] = "rejected_stale_or_unavailable_graph"
            continue
        local = strict_artifact(root, row.get("selector"))
        expected = row.get("artifact_sha256")
        if not local or not expected or hashes.get(local) != expected:
            statuses[name] = "rejected_selected_binding"
            continue
        path = root / local
        if path.stat().st_size > MAX_SELECTED_JSON_BYTES:
            statuses[name] = "rejected_selected_size_limit"
            continue
        raw = path.read_bytes()
        if len(raw) > MAX_SELECTED_JSON_BYTES or hashlib.sha256(raw).hexdigest() != expected:
            statuses[name] = "rejected_selected_hash"
            continue
        try:
            payload = json.loads(raw)
        except (ValueError, UnicodeError):
            statuses[name] = "rejected_selected_json"
            continue
        if not isinstance(payload, dict):
            statuses[name] = "rejected_selected_json"
            continue
        upstream = row.get("upstream_hashes", {})
        if not isinstance(upstream, dict) or any(hashes.get(key) != value for key, value in upstream.items()):
            statuses[name] = "rejected_selected_upstream_binding"
            continue
        payloads[name] = payload
        receipts[name] = {"selector": local, "artifact_sha256": expected,
                          "timing_status": row.get("timing_status", "unknown"),
                          "payload_status": row.get("payload_status", payload.get("status", "unknown")),
                          **{key: row.get(key, None if key == "producer_worker_sha256" else "not_recorded")
                             for key in ("manifest_binding_kind", "settings_binding_kind",
                                         "producer_worker_status", "producer_worker_sha256")}}
    # Detect changed graph inputs before promoting any selected payload.
    if payloads and any(not strict_artifact(root, path) or sha256(root / path) != expected
                        for path, expected in hashes.items()):
        for name in payloads:
            statuses[name] = "rejected_changed_graph_inputs"
        payloads, receipts = {}, {}
    return payloads, statuses, receipts


def objects(value, limit):
    return [item for item in value[:limit] if isinstance(item, dict)] if isinstance(value, list) else []


def feature_escape(value):
    return escape(str(value)[:600])


def shown(value, digits=3, suffix=""):
    number = finite(value)
    return f"{number:.{digits}f}{suffix}" if number is not None else "unknown"


def selected_seek(manifest, audio=None, source=None):
    timeline = manifest.get("timeline", {})
    timeline = timeline if isinstance(timeline, dict) else {}
    audio_origin = finite(timeline.get("audio_start_seconds")) or 0
    video_origin = finite(timeline.get("format_start_seconds")) or 0
    audio, source = finite(audio), finite(source)
    if source is None and audio is not None:
        source = audio_origin + audio
    if audio is None and source is not None:
        audio = source - audio_origin
    if audio is None or source is None or audio < 0:
        return ""
    return f'<button data-media="audio" data-time="{audio:.6f}">Seek audio</button> <button data-media="video" data-time="{max(0, source-video_origin):.6f}">Seek video</button>'


def evidence_table(headers, rows):
    return '<table><thead><tr>' + ''.join(f'<th>{escape(value)}</th>' for value in headers) + '</tr></thead><tbody>' + ''.join(rows) + '</tbody></table>' if rows else '<p class="unavailable">No candidate rows available; this is not an absence-of-music finding.</p>'


def selected_click_section(manifest, payload):
    summary = payload.get("summary", {})
    summary = summary if isinstance(summary, dict) else {}
    counts = ' · '.join(f'{label}: {shown(summary.get(key), 0)}' for key, label in [("candidate_count", "Candidates"), ("accepted_fit_count", "Accepted template fits"), ("attenuated_count", "Attenuated"), ("abstained_count", "Abstained")])
    rows = []
    for event in objects(payload.get("events"), 20):
        rows.append(f'<tr><th>{shown(event.get("source_timeline_seconds"))}s</th><td>{feature_escape(event.get("decision", "unknown"))}</td><td>{feature_escape(event.get("reason", "unknown"))}</td><td>{selected_seek(manifest, event.get("audio_relative_seconds"), event.get("source_timeline_seconds"))}</td></tr>')
    return f'<p class="caption">{counts}. Click identity: {feature_escape(payload.get("identity_status", "unknown"))}. Showing at most 20 events.</p><p class="note">A template fit can overlap a guitar attack. Accepted fitting and experimental attenuation do not establish a recovered metronome stem or listening acceptance. The main audition remains the selected cleanup master.</p>' + evidence_table(["Source time", "Decision", "Overlap / fit evidence", "Navigate"], rows)


def selected_pitch_section(manifest, payload):
    analysis = payload.get("analysis", {})
    analysis = analysis if isinstance(analysis, dict) else {}
    fraction = finite(analysis.get("coverage_fraction"))
    coverage = f'{fraction*100:.2f}%' if fraction is not None and 0 <= fraction <= 1 else "unknown"
    spans = objects(analysis.get("coverage_spans_source_timeline"), 12)
    span_rows = [f'<tr><th>{shown(span.get("start_seconds"))}–{shown(span.get("end_seconds"))}s</th><td>{selected_seek(manifest, source=span.get("start_seconds"))}</td></tr>' for span in spans]
    rows = []
    observations = payload.get("observations", {})
    observations = observations if isinstance(observations, dict) else {}
    for excerpt in objects(observations.get("analyzed_excerpts"), 12):
        for branch in objects(excerpt.get("branches"), 4):
            for frame in objects(branch.get("frames"), 400):
                frequency = finite(frame.get("frequency_hz"))
                if frequency is None:
                    continue
                mapping = frame.get("note_mapping", {})
                mapping = mapping if isinstance(mapping, dict) else {}
                label = feature_escape(mapping.get("note", "unknown"))
                window_start = frame.get("window_start_seconds_source_timeline")
                window_end = frame.get("window_end_seconds_source_timeline")
                branch_name = feature_escape(branch.get("name", "branch unknown"))
                probability = finite(frame.get("voicing_probability"))
                voicing = f'{probability:.3f}' if probability is not None and 0 <= probability <= 1 else "unknown"
                rows.append(f'<tr><th>{shown(frame.get("source_timeline_seconds"))}s<br>{branch_name}</th><td>{frequency:.2f} Hz · {label}</td><td>{shown(window_start)}–{shown(window_end)}s</td><td>{voicing}</td><td>{selected_seek(manifest, frame.get("audio_relative_seconds"), frame.get("source_timeline_seconds"))}</td></tr>')
                # Show distributed excerpts and both resolution branches, rather
                # than filling the display with adjacent low-branch frames.
                break
            if len(rows) >= 16:
                break
        if len(rows) >= 16:
            break
    summary = payload.get("summary", {})
    summary = summary if isinstance(summary, dict) else {}
    return f'<p class="caption">Pitch excerpt coverage: {coverage} · {shown(analysis.get("coverage_seconds"), 2)} seconds. Sampling: {feature_escape(analysis.get("sampling", "unknown"))}. Abstained branch frames: {shown(summary.get("abstained_frame_count"), 0)}.</p><p class="note">Unanalyzed spans remain unknown. Low/high branches and octave alternatives are overlapping mixture hypotheses, not unique notes or string identities. Long low-register windows blur fast changes; pYIN voicing is not note-correctness probability. Tuning is operator context with inferred octaves.</p><details><summary>Analyzed source spans · first 12</summary>{evidence_table(["Source span", "Navigate"], span_rows)}</details><details><summary>Periodic pitch examples · one per excerpt and branch, at most 16</summary>{evidence_table(["Source center / branch", "Conditional pitch mapping", "Analysis window", "Algorithm voicing", "Navigate"], rows)}</details>'


def selected_meter_section(manifest, payload):
    rows = []
    for alias in objects(payload.get("aliases"), 3):
        selected = alias.get("selected")
        selected = selected if isinstance(selected, dict) else {}
        rows.append(f'<tr><th>{shown(alias.get("pulse_bpm"), 2)} BPM</th><td>{feature_escape(alias.get("status", "unknown"))}</td><td>{shown(selected.get("cycle_pulses"), 0)} pulses</td><td>{feature_escape(alias.get("reason", "unknown"))}</td></tr>')
    return f'<p>Notated time signature: <strong>{feature_escape(payload.get("time_signature") or "unknown")}</strong>.</p><p class="note">An energy accent cycle is not a verified downbeat or notated meter. Quarter/eighth pulse units and additive grouping remain unresolved; uniform clicks, compressed distortion and legato can conceal accents.</p>{evidence_table(["Pulse interpretation", "Accent evidence", "Selected cycle", "Boundary"], rows)}<p class="caption">Local windows: {len(objects(payload.get("local_windows"), 256))} · {feature_escape(payload.get("local_structure", "unknown"))}. {feature_escape(payload.get("reason", "unknown"))}.</p>'


def selected_tonal_section(manifest, payload):
    context = payload.get("whole_take", payload.get("global_context", {}))
    context = context if isinstance(context, dict) else {}
    # Worker context name is explicit; no pooling sparse pitch into note votes.
    if not context:
        context = payload.get("whole_recording", {})
        context = context if isinstance(context, dict) else {}
    reasons = context.get("abstention_reasons", [])
    reason_text = ', '.join(str(value) for value in reasons[:12]) if isinstance(reasons, list) else "unknown"
    rows = []
    families = context.get("profile_families", {})
    for family, record in list(families.items())[:4] if isinstance(families, dict) else []:
        if not isinstance(record, dict):
            continue
        for candidate in objects(record.get("ranked_hypotheses"), 2):
            rows.append(f'<tr><th>{feature_escape(family)}</th><td>{feature_escape(candidate.get("tonic_candidate", "unknown"))} {feature_escape(candidate.get("mode_candidate", "unknown"))}</td><td>{shown(candidate.get("profile_correlation"))}</td><td>{feature_escape(record.get("top_hypothesis_screen", "unknown"))}</td></tr>')
    regions = objects(payload.get("regions"), 256)
    abstained = sum(region.get("status") == "abstained" for region in regions)
    return f'<p>Tonic: <strong>{feature_escape(payload.get("tonic") or "unknown")}</strong> · Mode: <strong>{feature_escape(payload.get("mode") or "unknown")}</strong>.</p><p class="caption">Whole-take context: {feature_escape(context.get("status", "unknown"))} · normalized pitch-class entropy: {shown(context.get("normalized_pitch_class_entropy"))}. {feature_escape(reason_text)}. Regions: {len(regions)}; abstained: {abstained}.</p><p class="note">Ranked tonal profiles can disagree. Distorted harmonics, chromatic material and unresolved low fundamentals can create plausible false keys. Profile correlation is not calibrated tonal confidence; sparse pitch branches are not independent note votes.</p>{evidence_table(["Profile family", "Ranked hypothesis", "Correlation", "Candidate screen"], rows)}'


def selected_comparison_section(manifest, payload):
    rows = []
    for comparison in objects(payload.get("comparisons"), 24):
        spans = comparison.get("spans", {})
        spans = spans if isinstance(spans, dict) else {}
        motif = comparison.get("motif_comparison", {})
        motif = motif if isinstance(motif, dict) else {}
        first = spans.get("first_start_seconds")
        second = spans.get("second_start_seconds")
        rows.append(f'<tr><th>{shown(first)}–{shown(spans.get("first_end_seconds"))}s / {shown(second)}–{shown(spans.get("second_end_seconds"))}s</th><td>{feature_escape(comparison.get("status", "unknown"))}<br>{feature_escape(motif.get("status", "attack edits unknown"))}</td><td>{shown(comparison.get("median_relative_offset_seconds"), 3, "s")} / {shown(comparison.get("interior_rate_median"))}</td><td>{selected_seek(manifest, audio=first)} {selected_seek(manifest, audio=second)}</td></tr>')
    return '<p class="note">DTW compares feature motion within discovered recurrences. Relative shifts or rate changes can reflect boundary bias and deliberate variation. Omitted feature frames and unmatched attack detections do not prove omitted notes; unknown detector/boundary confidence abstains from attack-edit claims.</p><p class="caption">Spans below are decoded-audio time. Rate is elapsed second-phrase time per first-phrase time; no absolute rushed/late grade follows. Showing at most 24 comparisons.</p>' + evidence_table(["Compared audio spans", "Alignment / attack evidence", "Relative offset / rate", "Navigate"], rows)


def selected_feature_section(manifest, payloads, statuses, receipts):
    renderers = {"clicks": selected_click_section, "pitch": selected_pitch_section,
                 "meter": selected_meter_section, "tonal": selected_tonal_section,
                 "comparisons": selected_comparison_section}
    labels = {"clicks": "Click fit and overlap", "pitch": "Sparse pitch evidence",
              "meter": "Accent cycles and meter", "tonal": "Tonal context", "comparisons": "Within-take phrase alignment"}
    sections = []
    for name in SELECTED_FEATURES:
        status = statuses.get(name, "not_selected")
        receipt = receipts.get(name, {})
        body = renderers[name](manifest, payloads[name]) if name in payloads else '<p class="unavailable">No graph-verified selection is displayed. Candidate absence is not established.</p>'
        link = f'<a href="{escape(quote(receipt["selector"]))}">Selected evidence JSON</a>' if receipt else ''
        caption = f'<p class="caption">Selection: {feature_escape(status)}. Payload: {feature_escape(receipt.get("payload_status", "unknown"))}. Timing: {feature_escape(receipt.get("timing_status", "unknown"))}. {link}</p>'
        if receipt:
            scope = [('Manifest binding', receipt.get('manifest_binding_kind')),
                     ('Settings binding', receipt.get('settings_binding_kind')),
                     ('Producer worker', receipt.get('producer_worker_status')),
                     ('Producer worker SHA-256', receipt.get('producer_worker_sha256') or 'not_recorded')]
            caption += '<p class="caption">' + ' · '.join(f'{label}: {feature_escape(value)}' for label, value in scope) + '. Derived bindings do not establish a producer manifest receipt or reverify current worker code.</p>'
        sections.append(f'<details><summary>{labels[name]} · {feature_escape(status)}</summary>{caption}{body}</details>')
    return '<section><h2>Selected feature evidence</h2><p class="caption">Only explicit graph selections with current artifact and upstream hashes appear here. DSP timing verification does not establish physical capture delay, detector calibration, musical correctness or listening acceptance.</p>' + ''.join(sections) + '</section>'


def feature_section(payloads, statuses):
    tone = payloads.get("tone", {}).get("observations", {})
    bands = tone.get("sampled_band_energies", []) if isinstance(tone, dict) else []
    band_rows = []
    for band in bands if isinstance(bands, list) else []:
        if not isinstance(band, dict):
            continue
        low, high, energy = [finite(band.get(key)) for key in ("low_hz", "high_hz_exclusive", "rms_dbfs")]
        if low is None or high is None or energy is None:
            continue
        fraction = finite(band.get("fraction_of_ac_energy"))
        share = f"{fraction * 100:.2f}%" if fraction is not None else "Unknown"
        band_rows.append(f'<tr><th>{low:g}–{high:g} Hz</th><td>{energy:.2f} dBFS</td><td>{share}</td></tr>')
    band_table = '<table><thead><tr><th>Analysis band</th><th>Sampled RMS</th><th>Share of sampled AC energy</th></tr></thead><tbody>' + ''.join(band_rows) + '</tbody></table>' if band_rows else '<p class="unavailable">Source-bound band measurements unavailable.</p>'
    noise = payloads.get("noise", {}).get("observations", {})
    windows = noise.get("quiet_candidate_windows", []) if isinstance(noise, dict) else []
    quiet_rows = []
    for window in windows[:20] if isinstance(windows, list) else []:
        if not isinstance(window, dict):
            continue
        start, end, energy = [finite(window.get(key)) for key in ("start_seconds", "end_seconds", "rms_dbfs")]
        if start is None or end is None or energy is None or start < 0 or end < start:
            continue
        quiet_rows.append(f'<tr><th>{start:.3f}–{end:.3f}s</th><td>{energy:.2f} dBFS</td><td><button data-media="audio" data-time="{start:.6f}">Seek audio</button></td></tr>')
    quiet_table = '<details><summary>Quiet passage candidates · audition before profiling</summary><table><thead><tr><th>Decoded audio interval</th><th>Measured RMS</th><th>Navigate</th></tr></thead><tbody>' + ''.join(quiet_rows) + '</tbody></table></details>' if quiet_rows else '<p class="unavailable">Quiet candidate intervals unavailable.</p>'
    notes = payloads.get("notes", {})
    observations = notes.get("observations", {})
    frames = observations.get("sparse_analysis_frames", []) if isinstance(observations, dict) else []
    pitch_rows = []
    for frame in frames if isinstance(frames, list) else []:
        if not isinstance(frame, dict):
            continue
        candidate = frame.get("periodicity_candidate", {})
        if not isinstance(candidate, dict):
            continue
        frequency = finite(candidate.get("frequency_hz"))
        start = finite(frame.get("start_seconds"))
        score = finite(candidate.get("normalized_autocorrelation_score"))
        if frequency is None or start is None:
            continue
        pitch_rows.append(f'<tr><th>{start:.3f}s</th><td>{frequency:.2f} Hz</td><td>{score:.3f} heuristic score</td></tr>' if score is not None else f'<tr><th>{start:.3f}s</th><td>{frequency:.2f} Hz</td><td>Confidence unknown</td></tr>')
        if len(pitch_rows) >= 8:
            break
    interpretation = notes.get("interpretation", {})
    if not isinstance(interpretation, dict):
        interpretation = {}
    context = ' · '.join(f'{label}: {escape(interpretation.get(key) or "unknown")}' for key, label in [("tonic", "Tonic"), ("mode", "Mode"), ("note_transcription", "Note transcription")])
    pitch_table = '<details><summary>Sparse-mixture periodicity candidates · first eight available</summary><table><thead><tr><th>Decoded audio time</th><th>Periodic frequency candidate</th><th>Evidence</th></tr></thead><tbody>' + ''.join(pitch_rows) + '</tbody></table></details>' if pitch_rows else '<p class="unavailable">No source-bound periodic-frequency candidates displayed.</p>'
    identities = ' · '.join(f'{escape(name)}: {escape(status)}' for name, status in statuses.items())
    return f'<section><h2>Low register, noise and tonal context</h2><p class="note">The intended low register near 32 Hz is musical content. These sampled analysis-copy bands describe the mixture and do not prove preserved fundamentals, guitar identity or preferred tone. A quiet interval may contain sustain or metronome; approve a noise-only region before profiling. Speech denoisers are outside these guitar cleanup presets.</p>{band_table}{quiet_table}<p class="caption">{context}. Exact tuning, intended notes and string identity require a confirmed reference. Distorted harmonics can create octave ambiguity; sparse frequency candidates do not establish note mistakes.</p>{pitch_table}<p class="caption">{identities}</p></section>'


def subdivision_section(analysis):
    payload = analysis.get("subdivisions", {})
    if not isinstance(payload, dict):
        return ""
    candidates = payload.get("candidates", [])
    if not isinstance(candidates, list) or not candidates:
        return ""
    rows = []
    for item in candidates[:12]:
        if not isinstance(item, dict):
            continue
        divisions = finite(item.get("subdivisions_per_declared_or_fitted_pulse"))
        fraction = finite(item.get("within_tolerance_fraction"))
        tolerance = finite(item.get("tolerance_ms"))
        offset = finite(item.get("median_absolute_offset_ms"))
        if divisions is None:
            continue
        coverage = f"{fraction * 100:.1f}%" if fraction is not None else "Unknown"
        timing = f"{offset:.2f} ms" if offset is not None else "Unknown"
        window = f"±{tolerance:g} ms" if tolerance is not None else "Unknown"
        rows.append(f'<tr><th>{divisions:g} per pulse</th><td>{coverage} within {window}</td><td>{timing}</td></tr>')
    if not rows:
        return ""
    return '<details><summary>Automatic pulse-subdivision candidates</summary><p class="caption">Detected attack alignment is measured against possible subdivisions. Increasing grid density can improve coverage by chance; these candidates do not establish intended notes, tuplets or rests.</p><table><thead><tr><th>Subdivision hypothesis</th><th>Candidate coverage</th><th>Median absolute offset</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table></details>'


def phrase_section(manifest, payloads):
    phrases = payloads.get("phrases", {})
    observations = phrases.get("observations", {})
    spans = observations.get("proposed_review_spans", []) if isinstance(observations, dict) else []
    if not isinstance(spans, list) or not spans:
        return '<section><h2>Automatic phrase and section proposals</h2><p class="unavailable">No source-bound phrase spans have been exported yet.</p><p class="caption">Phrase boundaries, repeated regions and possible bars can be proposed from the recording without an intended score. Semantic section names and performance correctness remain review decisions.</p></section>'
    timeline = manifest.get("timeline", {})
    audio_start = finite(timeline.get("audio_start_seconds")) or 0 if isinstance(timeline, dict) else 0
    format_start = finite(timeline.get("format_start_seconds")) or 0 if isinstance(timeline, dict) else 0
    source = phrases.get("source", {})
    feature_origin = finite(source.get("audio_stream_start_seconds")) if isinstance(source, dict) else None
    rows = []
    for span in spans[:1000]:
        if not isinstance(span, dict):
            continue
        start = finite(span.get("start_seconds"))
        end = finite(span.get("end_seconds", start))
        if start is None or end is None or start < 0 or end < start:
            continue
        source_start = finite(span.get("source_start_seconds"))
        source_end = finite(span.get("source_end_seconds"))
        source_start = source_start if source_start is not None else start + (feature_origin if feature_origin is not None else audio_start)
        source_end = source_end if source_end is not None else source_start + end - start
        kind = span.get("kind", "phrase_region_candidate")
        label = span.get("label", str(kind).replace("_", " "))
        evidence = span.get("evidence", "automatic proposal")
        score = finite(span.get("score"))
        reference_start = finite(span.get("reference_start_seconds"))
        reference_link = f' <button data-media="audio" data-time="{reference_start:.6f}">Compare recurrence</button>' if reference_start is not None and reference_start >= 0 else ''
        score_label = f" · {score:.3f} heuristic score" if score is not None else ''
        confidence = finite(span.get("confidence"))
        confidence_label = f" · {confidence:.3f} novelty heuristic" if confidence is not None else ''
        rows.append(f'<tr><th>{escape(label)}<br><span class="caption">{escape(str(kind).replace("_", " "))}</span></th><td>{source_start:.3f}–{source_end:.3f}s</td><td>{escape(evidence)}{score_label}{confidence_label}</td><td><button data-media="audio" data-time="{max(0, source_start-audio_start):.6f}">Seek audio</button> <button data-media="video" data-time="{max(0, source_start-format_start):.6f}">Seek video</button>{reference_link}</td></tr>')
    bars = observations.get("bar_proxy_candidates", [])
    bar_rows = []
    for index, bar in enumerate(bars[:24] if isinstance(bars, list) else []):
        if not isinstance(bar, dict):
            continue
        start, end = finite(bar.get("start_seconds")), finite(bar.get("end_seconds"))
        if start is None or end is None or start < 0 or end < start:
            continue
        source_start = finite(bar.get("source_start_seconds"))
        source_start = source_start if source_start is not None else start + (feature_origin if feature_origin is not None else audio_start)
        bar_rows.append(f'<tr><th>Four-pulse region {index+1}</th><td>{source_start:.3f}–{source_start+end-start:.3f}s</td><td><button data-media="audio" data-time="{max(0,source_start-audio_start):.6f}">Seek audio</button></td></tr>')
    bar_table = '<details><summary>Four-pulse bar hypotheses · first 24</summary><p class="caption">Four pulses are grouped for navigation. Time signature and downbeat are unknown; these are bar proxies, not established 4/4 bars.</p><table>' + ''.join(bar_rows) + '</table></details>' if bar_rows else ''
    curve = observations.get("novelty_curve", [])
    points = [(finite(item.get("seconds")), finite(item.get("score"))) for item in curve if isinstance(item, dict)] if isinstance(curve, list) else []
    points = [(time, score) for time, score in points if time is not None and score is not None and time >= 0]
    novelty = ''
    if len(points) > 1:
        duration = max(time for time, _ in points) or 1
        scale = max(max(score for _, score in points), .001)
        line = ' '.join(f'{35+890*time/duration:.2f},{145-110*max(0,score)/scale:.2f}' for time, score in points[:20000])
        novelty = f'<svg class="timeline" viewBox="0 0 960 185" role="img" aria-label="Automatic structural novelty in decoded audio seconds"><line x1="35" y1="145" x2="925" y2="145" class="axis"/><polyline points="{line}" fill="none" stroke="#dbba76" stroke-width="2"/><text x="35" y="173">0s</text><text x="865" y="173">{duration:.1f}s</text></svg><p class="caption">Beat-synchronous feature novelty, scaled for display. Peaks suggest structural changes; their scores are unvalidated heuristics.</p>'
    segments = observations.get("segment_candidates", [])
    recurrences = observations.get("recurrence_candidates", [])
    counts = f'{len(segments) if isinstance(segments, list) else 0} region proposals · {len(recurrences) if isinstance(recurrences, list) else 0} recurrence proposals · {len(bars) if isinstance(bars, list) else 0} four-pulse proxies · {len(spans)} review spans'
    return '<section><h2>Automatic phrase and section proposals</h2><p class="note">Boundaries and repeated regions are inferred directly from this take. Structural differences can flag passages for review without an intended score. Proposed bars, riffs and breakdown regions remain hypotheses; a reference is needed to judge whether a passage was played as intended.</p><p class="caption">' + counts + '</p>' + novelty + '<table><thead><tr><th>Proposal</th><th>Original source span</th><th>Evidence</th><th>Navigate</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table>' + bar_table + '<p class="caption">Automatic labels describe review candidates, not confirmed verse/chorus/breakdown identities. Recurrence can reflect spectral or rhythmic resemblance without matching notes. Showing at most 1,000 spans.</p></section>'


def media_paths(root, manifest, outcome=None):
    outputs = manifest.get("outputs", manifest.get("artifacts", {}))
    if not isinstance(outputs, dict):
        outputs = {}
    groups = {
        "original": (["baseline", "original_audio", "original_wav", "source_audio", "raw_audio", "original", "source"], ["baseline.wav", "original.wav", "source.wav", "working.wav"]),
        "source": (["source", "source_audio", "original_wav"], ["source.wav", "original.wav", "working.wav"]),
        "clean": (["cleaned", "clean_audio", "clean_wav", "processed_audio", "master_audio", "clean"], ["cleaned.wav", "clean.wav", "master.wav"]),
        "residual": (["residue", "residual_audio", "residue_audio", "residual_wav", "residual"], ["residue.wav", "residual.wav"]),
        "video": (["processed_video", "clean_video", "video"], ["processed.mp4", "clean.mp4", "cleaned.mp4"]),
    }
    result = {}
    for role, (keys, fallback) in groups.items():
        found = next((artifact(root, outputs[key]) for key in keys if artifact(root, outputs.get(key))), None)
        result[role] = found or next((name for name in fallback if artifact(root, name)), None)
    if outcome and artifact(root, outcome.get("video")):
        result["video"] = outcome["video"]
    return result


def waveform(path, bins=480):
    """Read PCM integer/float RIFF WAV; return peak bins and sample duration."""
    with path.open("rb") as stream:
        if stream.read(4) != b"RIFF":
            return None
        stream.read(4)
        if stream.read(4) != b"WAVE":
            return None
        fmt = None
        data = None
        while True:
            header = stream.read(8)
            if len(header) != 8:
                break
            tag, size = struct.unpack("<4sI", header)
            if tag == b"fmt ":
                fmt = stream.read(size)
            elif tag == b"data":
                data = (stream.tell(), size)
                break
            else:
                stream.seek(size, 1)
            if size % 2:
                stream.seek(1, 1)
        if not fmt or len(fmt) < 16 or not data:
            return None
        encoding, channels, rate, _, align, bits = struct.unpack("<HHIIHH", fmt[:16])
        if encoding == 65534 and len(fmt) >= 40:
            encoding = struct.unpack("<H", fmt[24:26])[0]
        if encoding not in (1, 3) or bits not in (8, 16, 24, 32, 64) or not channels or not rate or not align:
            return None
        if encoding == 3 and bits not in (32, 64):
            return None
        width = bits // 8
        if width * channels != align:
            return None
        frames = data[1] // align
        if not frames:
            return None
        peaks = []
        count = min(bins, frames)
        for index in range(count):
            start = frames * index // count
            end = frames * (index + 1) // count
            stream.seek(data[0] + start * align)
            samples = stream.read((end - start) * align)
            peak = 0.0
            # Bound rendering work on long recordings without changing the audio.
            stride = max(1, (end - start) // 1024) * align
            for offset in range(0, len(samples) - align + 1, stride):
                for channel in range(channels):
                    raw = samples[offset + channel * width:offset + (channel + 1) * width]
                    if encoding == 3:
                        value = struct.unpack("<f" if bits == 32 else "<d", raw)[0]
                    elif bits == 8:
                        value = (raw[0] - 128) / 128
                    else:
                        value = int.from_bytes(raw, "little", signed=True) / (2 ** (bits - 1))
                    if math.isfinite(value):
                        peak = max(peak, abs(value))
            peaks.append(peak)
        return peaks, frames / rate


def read_events(root):
    path = root / "events.csv"
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def visualization(root, paths, events, analysis):
    audio = paths.get("source") or paths.get("original")
    try:
        wave = waveform(root / audio) if audio else None
    except (OSError, ValueError, struct.error):
        wave = None
    if not wave:
        return '<p class="unavailable">Waveform unavailable for this audio format.</p>'
    peaks, duration = wave
    width, left, span = 960, 35, 890
    points = []
    for i, peak in enumerate(peaks):
        x = left + i * span / max(1, len(peaks) - 1)
        amp = min(1.0, peak) * 65
        points.append(f'M{x:.2f} {100-amp:.2f}V{100+amp:.2f}')
    marks = []
    offsets = []
    for event in events[:10000]:
        time = finite(event.get("audio_relative_seconds", event.get("time_s", event.get("time_seconds", event.get("time")))))
        if time is None or not 0 <= time <= duration:
            continue
        kind = str(event.get("kind", event.get("type", event.get("event_type", "onset"))))
        click = "click" in kind.lower() or "beat" in kind.lower() or "periodic_high_frequency" in kind.lower()
        x = left + time * span / duration
        marks.append(f'<circle cx="{x:.2f}" cy="{195 if click else 215}" r="2.3" class="{"click" if click else "onset"}"><title>{escape(kind)} at {time:.3f}s</title></circle>')
        offset = finite(event.get("grid_offset_ms"))
        if not click and offset is not None:
            y = 330 - max(-100, min(100, offset)) * 0.45
            offsets.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.4" class="onset"><title>Candidate attack at {time:.3f}s; grid offset {offset:+.2f}ms (uncalibrated)</title></circle>')
    ticks = ''.join(f'<text x="{left+i*span/4:.1f}" y="245">{duration*i/4:.1f}s</text>' for i in range(5))
    offset_plot = f'<text x="35" y="278">Candidate attack offset to proposed periodic grid · uncalibrated</text><line x1="35" y1="330" x2="925" y2="330" class="axis"/><text x="35" y="312">+100 ms</text><text x="35" y="371">−100 ms</text>{"".join(offsets)}' if offsets else ''
    return f'''<svg class="timeline" viewBox="0 0 {width} {390 if offsets else 260}" role="img" aria-label="Original PCM waveform and available detected event times">
<line x1="35" y1="100" x2="925" y2="100" class="axis"/>
<path d="{' '.join(points)}" class="wave"/>{''.join(marks)}{ticks}{offset_plot}
</svg><p class="caption">Original PCM amplitude, sampled for display; times are relative to the first decoded audio sample. Gold: periodic high-frequency / click candidates. Coral: broadband attack candidates. Neither lane establishes instrument identity. {len(events)} exported events. {'Offset display is limited to ±100 ms; hover a point for its complete value. Offsets are not performance grades or confirmed rhythm issues.' if offsets else 'No calibrated attack-to-grid offsets are displayed.'}</p>'''


def metric_rows(manifest, analysis, outcome=None):
    rows = []
    metrics = manifest.get("measurements", manifest.get("metrics", {}))
    if not isinstance(metrics, dict):
        metrics = {}
    metrics = dict(metrics)
    loudness = manifest.get("loudness", {})
    if isinstance(loudness, dict):
        for role, measurement in loudness.items():
            if isinstance(measurement, dict) and isinstance(measurement.get("output"), dict):
                metrics[role] = measurement["output"]
    if outcome and isinstance(outcome.get("final_audio_loudness"), dict):
        metrics["final encoded delivery"] = outcome["final_audio_loudness"]
    aliases = [("Integrated loudness", "LUFS", ["integrated_lufs", "input_i", "lufs_i"]),
               ("True peak", "dBTP", ["true_peak_dbtp", "input_tp", "true_peak_db"]),
               ("Loudness range", "LU", ["lra_lu", "input_lra", "loudness_range_lu"])]
    for label, unit, keys in aliases:
        for role, values in metrics.items():
            if not isinstance(values, dict):
                continue
            value = next((finite(values[k]) for k in keys if finite(values.get(k)) is not None), None)
            if value is not None:
                rows.append(f'<tr><th>{escape(role)} · {label}</th><td>{value:.2f} {unit}</td><td>Measured</td></tr>')
    declared = analysis.get("declared_tempo", {})
    if isinstance(declared, dict):
        bpm = finite(declared.get("bpm"))
        if bpm is not None:
            rows.append(f'<tr><th>Operator-declared tempo</th><td>{bpm:g} BPM</td><td>Approximate user reference; separate from the fitted audio pulse</td></tr>')
    tempo = analysis.get("tempo", {})
    if isinstance(tempo, dict):
        bpm = finite(tempo.get("bpm", tempo.get("estimated_bpm")))
        if bpm is not None:
            rows.append(f'<tr><th>Tempo candidate</th><td>{bpm:.2f} BPM</td><td>Inferred; metrical interpretation unverified</td></tr>')
    candidates = analysis.get("tempo_candidates", [])
    if isinstance(candidates, list):
        bpms = [finite(item.get("bpm")) for item in candidates if isinstance(item, dict)]
        bpms = [value for value in bpms if value is not None]
        if bpms:
            values = " / ".join(f"{value:.2f}" for value in bpms[:5])
            rows.append(f'<tr><th>Periodicity candidates</th><td>{values} BPM</td><td>Inferred; metronome identity and meter unverified</td></tr>')
    interpretations = analysis.get("metrical_interpretations", [])
    if isinstance(interpretations, list):
        bpms = [finite(item.get("bpm")) for item in interpretations if isinstance(item, dict)]
        bpms = [value for value in bpms if value is not None]
        if bpms:
            values = " / ".join(f"{value:.2f}" for value in bpms[:5])
            rows.append(f'<tr><th>Metrical interpretations</th><td>{values} BPM</td><td>Derived half/double pulse ambiguity; not independent detections</td></tr>')
    grid = analysis.get("click_grid")
    if isinstance(grid, dict):
        bpm = finite(grid.get("bpm"))
        if bpm is not None:
            rows.append(f'<tr><th>Fitted periodic grid</th><td>{bpm:.2f} BPM</td><td>Recorded-pulse estimate; click identity and subdivisions remain uncertain</td></tr>')
        residual = finite(grid.get("median_absolute_residual_ms"))
        if residual is not None:
            rows.append(f'<tr><th>Periodic-candidate grid residual</th><td>{residual:.2f} ms</td><td>Heuristic grid fit; not a guitar performance grade</td></tr>')
    bands = manifest.get("low_frequency_metrics", {})
    if isinstance(bands, dict):
        for role, values in bands.items():
            if not isinstance(values, dict):
                continue
            value = finite(values.get("rms_32_80_hz_dbfs"))
            if value is not None:
                rows.append(f'<tr><th>{escape(role)} · 32–80 Hz band RMS</th><td>{value:.2f} dBFS</td><td>Measured band energy; not a pitch or tone-quality grade</td></tr>')
    return ''.join(rows) or '<tr><td colspan="3">Measurements unavailable in this run manifest.</td></tr>'


def restoration_caption(manifest):
    """Describe recorded delivery stages without inferring successful audition."""
    stages = objects(manifest.get("restoration_stages"), 16)
    if not stages:
        return "Cleanup delivery; stage chain not recorded in this legacy manifest. Listening acceptance pending."
    profile = manifest.get("profile") or {}
    profile = profile if isinstance(profile, dict) else {}
    capture = manifest.get("noise_capture") or {}
    capture = capture if isinstance(capture, dict) else {}
    chain = []
    for item in stages:
        name = str(item.get("stage", "unknown"))[:100]
        controls = item.get("controls") or {}
        controls = controls if isinstance(controls, dict) else {}
        if name == "afftdn":
            label = f'afftdn (NR {shown(profile.get("reduction_db"), 2)} dB; NF {shown(profile.get("noise_floor_db"), 2)} dBFS)'
            interval = capture.get("actual_selected_seconds", capture.get("selected_seconds", profile.get("noise_capture_seconds")))
            if isinstance(interval, list) and len(interval) == 2 and all(finite(v) is not None for v in interval):
                label += f'; captured {shown(interval[0], 2)}–{shown(interval[1], 2)}s of decoded source'
                label += '; noise-only verified' if capture.get("noise_only_verified_by_worker") is True else '; noise-only unverified'
            chain.append(label)
        elif name.startswith("peaking_eq_"):
            chain.append(f'peaking EQ {shown(controls.get("frequency_hz"), 0)} Hz / {shown(controls.get("gain_db"), 2)} dB / Q {shown(controls.get("q"), 2)}')
        elif name == "rms_compressor":
            chain.append(f'RMS compression {shown(controls.get("threshold_db"), 1)} dB / {shown(controls.get("ratio"), 2)}:1 / attack {shown(controls.get("attack_ms"), 1)} ms / release {shown(controls.get("release_ms"), 1)} ms / wet {shown(finite(item.get("fixed_parallel_wet_fraction")) * 100 if finite(item.get("fixed_parallel_wet_fraction")) is not None else None, 0)}%')
        elif name == "measured_loudness_normalization":
            chain.append("measured loudness normalization")
        else:
            chain.append(name.replace("_", " "))
    label = str(profile.get("name", "unnamed profile"))[:100]
    review = capture.get("review", profile.get("noise_capture_review"))
    review_note = f' Capture review: {str(review)[:300]}.' if isinstance(review, str) and review else ''
    return f'Recorded delivery chain [{label}]: ' + ' → '.join(chain) + '.' + review_note + ' Listening acceptance pending.'


def analysis_stage_caption(manifest, analysis):
    identity = source_identity(analysis)
    denoised = manifest.get("output_sha256", {}).get("denoised.wav")
    stages = objects(manifest.get("restoration_stages"), 16)
    post = any(str(item.get("stage", "")).startswith("peaking_eq_") or item.get("stage") == "rms_compressor" for item in stages)
    if identity and denoised and identity == denoised:
        scope = "Analysis input: pure denoised.wav before delivery loudness normalization."
        if post:
            scope += " The rendered cleaned.wav audition includes subsequent EQ/compression; these analysis findings do not describe processed.wav or the final mastering chain."
        return scope
    return "Analysis scope follows the verified input lineage; a rendered final audition does not establish that its full mastering chain was analyzed."


def render(root, manifest, analysis, events, outcome=None, identity_status="unavailable", export_status="unavailable", auxiliary=None, auxiliary_status=None, features=None, feature_status=None, selected=None, selected_status=None, selected_receipts=None):
    paths = media_paths(root, manifest, outcome)
    source = manifest.get("source", manifest.get("input", {}))
    if isinstance(source, dict):
        source = source.get("filename", source.get("name", source.get("path", "Private recording")))
    source_name = str(source).replace("\\", "/").split("/")[-1]
    cards = []
    baseline = artifact(root, manifest.get("outputs", {}).get("baseline")) if isinstance(manifest.get("outputs"), dict) else None
    matched = bool(baseline) and paths.get("original") == baseline
    original_note = "Original recording with playback-level normalization for A/B comparison." if matched else "Unprocessed decoded recording; match playback loudness manually."
    residue_note = "Pure pre-gain denoise diagnostic: source.wav minus denoised.wav. Excludes subsequent EQ, compression and loudness normalization; it is not an isolated source or the final mastering difference. Inspect for removed guitar detail."
    for role, title, note in [("original", "Original · audition", original_note), ("clean", "Clean iteration", restoration_caption(manifest)), ("residual", "Removed signal", residue_note)]:
        name = paths[role]
        player = f'<audio controls preload="none" src="{escape(quote(name))}"></audio><a href="{escape(quote(name))}" download>Download WAV</a>' if name else '<p class="unavailable">Artifact unavailable.</p>'
        cards.append(f'<article class="card"><h3>{title}</h3><p>{escape(note)}</p>{player}</article>')
    video = paths["video"]
    video_html = f'<video controls preload="none" playsinline src="{escape(quote(video))}"></video>' if video else '<p class="unavailable">Processed video unavailable.</p>'
    availability = "Analysis exported" if analysis else "Rhythm analysis unavailable"
    style = '''*{box-sizing:border-box}body{margin:0;background:#171614;color:#ece7dd;font:16px/1.65 ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}main{max-width:1120px;margin:auto;padding:64px 28px 48px}h1,h2,h3{line-height:1.2;font-weight:550;letter-spacing:-.035em}h1{font-size:clamp(35px,6vw,64px);margin:14px 0 20px}h2{font-size:25px;margin:0 0 20px}h3{font-size:21px;margin:0 0 12px}.eyebrow{color:#ceb179;text-transform:uppercase;letter-spacing:.17em;font-size:12px}.lead{color:#bdb6aa;max-width:780px}section{border-top:1px solid #38342e;margin-top:40px;padding-top:30px}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}.card{background:#211f1b;border:1px solid #3d372e;padding:24px;border-radius:12px}.card p,.caption{color:#aaa294;font-size:14px}audio{width:100%;margin:12px 0}a{color:#d8ba80;text-underline-offset:4px;font-size:14px}video{width:100%;max-height:660px;border-radius:10px;background:#0e0d0c}.unavailable{color:#a99f90}table{border-collapse:collapse;width:100%;font-size:15px}th,td{padding:14px 12px;text-align:left;border-bottom:1px solid #38342e}th{font-weight:500}td:last-child{color:#b0a696}.status{display:inline-block;border:1px solid #574a32;color:#d1b67e;border-radius:30px;padding:5px 13px;font-size:12px}.timeline{width:100%;background:#1e1c18;border-radius:10px}.wave{stroke:#a69980;stroke-width:1;fill:none}.axis{stroke:#413c32}.click{fill:#dbba76}.onset{fill:#ca8772}.timeline text{fill:#aaa294;font-size:13px}.note{border-left:2px solid #a88a55;padding-left:18px;color:#bbb2a4}footer{font-size:12px;color:#928879;margin-top:48px}@media(max-width:760px){main{padding:36px 18px}.cards{grid-template-columns:1fr}th,td{padding:11px 5px;font-size:13px}}'''
    style += 'th,td{overflow-wrap:anywhere}code{overflow-wrap:anywhere}button{background:#302a20;color:#d8ba80;border:1px solid #655238;border-radius:6px;padding:7px 10px;cursor:pointer;margin:3px 0;font:inherit;font-size:12px}button:focus-visible{outline:2px solid #e3c98f;outline-offset:3px}details{margin-top:20px}summary{cursor:pointer;color:#c4ad82}'
    seek_script = '''<script>document.addEventListener("click",function(event){const button=event.target.closest("button[data-media]");if(!button)return;const time=Number(button.dataset.time);if(!Number.isFinite(time)||time<0)return;const players=document.querySelectorAll(button.dataset.media==="video"?"video":"audio");const status=document.getElementById("seek-status");if(!players.length){status.textContent="This media artifact is unavailable.";return;}players.forEach(function(player){const seek=function(){try{player.currentTime=Number.isFinite(player.duration)?Math.min(time,player.duration):time;}catch(error){status.textContent="Seeking is unavailable in this browser; use the player controls.";}};if(player.readyState<1){player.addEventListener("loadedmetadata",seek,{once:true});player.load();}else{seek();}});status.textContent="Position set to "+time.toFixed(3)+" seconds. Start playback with the player controls.";});</script>'''
    review = review_section(manifest, auxiliary or {}, auxiliary_status or {})
    feature_report = feature_section(features or {}, feature_status or {})
    phrase_report = phrase_section(manifest, features or {})
    selected_report = selected_feature_section(manifest, selected or {}, selected_status or {}, selected_receipts or {})
    subdivisions = subdivision_section(analysis)
    fingerprint = source_identity(manifest)
    source_receipt = f'<p class="caption">Original source SHA-256: <code>{escape(fingerprint)}</code></p>' if isinstance(fingerprint, str) and len(fingerprint) == 64 and all(char in "0123456789abcdefABCDEF" for char in fingerprint) else ''
    profile = manifest.get("profile", {})
    settings = []
    if isinstance(profile, dict):
        for key, label, unit in [("reduction_db", "Denoise reduction", "dB"), ("noise_floor_db", "Configured noise floor", "dBFS"), ("integrated_lufs", "Loudness target", "LUFS"), ("preserve_low_fundamental_hz", "Low-register design target", "Hz")]:
            value = finite(profile.get(key))
            if value is not None:
                settings.append(f'{label}: {value:g} {unit}')
    settings_receipt = f'<p class="caption">{escape(" · ".join(settings))}. Settings are processing controls, not measurements or acceptance.</p>' if settings else ''
    verification = (outcome or {}).get("verification", {})
    checks = []
    if isinstance(verification, dict):
        for field, label in [("video_frame_count_preserved", "Video frame count preserved"), ("relative_audio_video_start_verified", "Relative audio/video start verified"), ("final_true_peak_within_target", "Final encoded true peak within target")]:
            if field in verification:
                value = verification[field]
                checks.append(f'{label}: {"passed" if value is True else "failed" if value is False else "unknown"}')
    export_caption = f'Export evidence: {escape(export_status)}. ' + escape(' · '.join(checks))
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="referrer" content="no-referrer"><title>Guitar take · local run report</title><style>{style}</style></head><body><main>
<header><div class="eyebrow">VIDEO UTILS / LOCAL SESSION</div><h1>A guitar take, examined.</h1><p class="lead">Compare the original recording with a conservative cleanup and inspect the evidence behind the iteration. Playback is manual; all media stays beside this report.</p><p class="lead">Source: {escape(source_name)}<br>Instrument context: 9-string downtuned deathcore / technical guitar; preserve the intended low register around 32 Hz and distorted tone.</p><span class="status">{availability} · listening acceptance pending</span></header>
<section><h2>Listen and compare</h2><p class="note">{'Original and cleaned auditions target the same integrated loudness; check their measured values below.' if matched else 'These files may have different playback loudness; match levels manually.'} A louder iteration or less distortion does not establish better tone. The removed-signal player is a diagnostic at its own level.</p><div class="cards">{''.join(cards)}</div></section>
<section><h2>Processed video</h2>{video_html}<p class="caption">{export_caption}</p><p class="caption">A rendered video is a delivery artifact; audiovisual sync and listening quality require separate acceptance.</p></section>
<section><h2>Waveform and timing candidates</h2>{visualization(root, paths, events, analysis)}{subdivisions}</section>
<section><h2>Run evidence</h2><p class="caption">Analysis lineage: {escape(identity_status)}. Unrelated or modified analysis inputs are excluded from this report.</p><p class="caption">{escape(analysis_stage_caption(manifest, analysis))}</p>{source_receipt}{settings_receipt}<table><thead><tr><th>Measure</th><th>Value</th><th>Evidence boundary</th></tr></thead><tbody>{metric_rows(manifest, analysis, outcome)}</tbody></table></section>
{review}
{phrase_report}
{feature_report}
{selected_report}
<section><h2>What remains uncertain</h2><p class="note">A mono room recording combines distorted guitar, metronome, room sound and recorder processing. Denoising can remove intended harmonics and low-string fundamentals; residuals are diagnostic estimates. Operator-declared tempo and fitted recording pulse are separate evidence. Automatic phrase, recurrence and bar proposals are available without an intended score, while meter and semantic section identity remain uncertain. Missed-note, extra-note and intended phrase-correctness judgments require stronger references. Acoustic travel time and detector bias affect onset offsets. Intended-note and tone-quality judgments remain unverified.</p><p class="caption">{'Source-bound analysis exports are available; review them before interpreting performance.' if analysis else 'Source-bound rhythm analysis is unavailable or rejected. Review any independently source-bound phrase proposals separately.'}</p></section>
<footer>Static standard-library HTML report · no remote assets · not a Quarto-rendered report. Preserve the complete run directory when sharing.</footer>
</main>{seek_script}</body></html>'''


def write_report(root):
    root = Path(root).resolve()
    manifest = load_json(root / "manifest.json")
    if not manifest:
        raise ValueError("manifest.json is required and must not be empty")
    analysis = load_json(root / "analysis.json")
    identity_status = analysis_lineage(root, manifest, analysis)
    if identity_status.startswith("rejected"):
        analysis = {}
    exported_events = analysis.get("events")
    events = exported_events if isinstance(exported_events, list) else read_events(root) if analysis else []
    events = [event for event in events if isinstance(event, dict)]
    outcome, export_status = export_evidence(root, manifest)
    auxiliary, auxiliary_status = auxiliary_evidence(root, manifest)
    features, feature_status = feature_evidence(root, manifest)
    selected, selected_status, selected_receipts = selected_feature_evidence(root, manifest, auxiliary, auxiliary_status)
    document = render(root, manifest, analysis, events, outcome, identity_status, export_status, auxiliary, auxiliary_status, features, feature_status, selected, selected_status, selected_receipts)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=root, prefix=".report-", suffix=".html", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(document)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, root / "report.html")
    finally:
        if temporary and temporary.exists():
            temporary.unlink()
    return {"report": "report.html", "analysis_available": bool(analysis), "analysis_lineage": identity_status, "export_evidence": export_status, "auxiliary_evidence": auxiliary_status, "feature_evidence": feature_status, "selected_evidence": selected_status, "selected_evidence_receipts": selected_receipts, "event_count": len(events), "renderer": "python-stdlib-html", "listening_acceptance": "pending"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    arguments = parser.parse_args()
    try:
        result = write_report(arguments.run_dir)
    except (OSError, ValueError, csv.Error) as error:
        parser.exit(1, f"Report failed: {type(error).__name__}; inspect run files.\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
