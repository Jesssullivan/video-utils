---
name: guitar-basic-pitch
description: Compare sparse guitar excerpts using the qualified official Basic Pitch ONNX model and project event decoding, retaining raw activations, window clocks, octave ambiguity and unknown musical correctness.
---

# Compare learned pitch hypotheses

**Hook:** MCP tool `basic_pitch_compare`, prompt `guitar-basic-pitch`. Inspect `tools/list` for current availability and the supported schema. The admitted CPU adapter uses the official model with project decoding; it does not claim authors' full postprocessing parity, complete transcription or musician correctness.

## Use and controls

Required `run_dir` is a 1–4,096-character path to an existing verified restoration run beneath repository `artifacts/runs/`. Original path components reject traversal/symlinks; the hook preflights regular manifest <=1 MiB and denoised WAV <=1 GiB. `max_analysis_seconds` is finite 1–30/default 20; optional `start_seconds` is finite >=0 inside the input and selects a contiguous excerpt. Otherwise coverage is distributed across at most six excerpts, including the ending. `onset_threshold` and `frame_threshold` are finite 0.05–0.95/defaults 0.5/0.3. Shared `timeout_seconds` is integer 1–900/default 600. There is no caller-controlled model, runtime interpreter, BPM, score, duration floor or frequency-grid argument.

Direct worker: `python3 scripts/basic_pitch_compare.py "<run-dir>" --max-analysis-seconds 20 --onset-threshold 0.5 --frame-threshold 0.3`. Recipe: `just tool-run basic_pitch_compare '{"run_dir":"<run-dir>","max_analysis_seconds":20}'`. Read [the implemented comparator contract](../../../docs/spec/BASIC_PITCH_COMPARATOR_LANE.md) and [hook contract](../../../docs/spec/BASIC_PITCH_TOOL_CONTRACT.md).

## Verify model, runtime and source context

Only registered `spotify-basic-pitch-0.4.0-onnx`, SHA256 `2c3c1d144bfa61ad236e92e169c13535c880469a12a047d4e73451f2c059a0ec`, is used. The operator-qualified isolated interpreter and wheel manifest bind runtime bytes/versions; missing or changed identities fail without downloads, installations, alternate models, TensorFlow fallback or GPU migration. Runtime configuration is not an arbitrary MCP executable argument.

For a fresh checkout, use explicit prerequisites:

```sh
just model-prefetch spotify-basic-pitch-0.4.0-onnx
just basic-pitch-runtime-setup /path/to/already-installed/python3.14
just basic-pitch-runtime-check
```

Setup requires an existing ordinary CPython 3.14.6 executable, native macOS arm64 on macOS 14 or newer, and existing `uv`. It downloads only five pinned dependency wheels into the isolated runtime; model acquisition is separate. The committed runtime lock binds wheel hashes. Check is read-only with no download, install or model inference. No Linux/Intel/free-threaded or other Python-version fallback is qualified. These explicit operations do not add an MCP setup executable field; comparison never acquires weights or its runtime implicitly. See [the qualification summary and later worker fix](../../../docs/agent-notes/2026-10-06-basic-pitch-runtime-fresh-ready.json) and [independent fresh-runtime audit](../../../docs/agent-notes/2026-10-06-basic-pitch-runtime-fresh-audit.json).

Input is manifest-verified `denoised.wav`, with native rate/channels/extent and recorded no-time-stretch mapping. Manifest `timeline.audio_start_seconds` must be explicit, finite and nonboolean; missing origin rejects instead of defaulting to zero. Original source identity is lineage from the manifest; do not invent a fresh original-media hash check. Analysis downmix/resampling to 22,050 Hz is separate. Record derivative/manifest, tuning/model registries, model, worker and runtime-manifest hashes. Masters and existing pitch/DAG/latest artifacts remain unchanged; results are fresh `learned-pitch/<nonce>/` descendants.

Inputs are bounded to 300 seconds, requested analysis to thirty seconds, model windows to twenty-four, raw arrays to 20 MiB and events to 5,000 per fixed preset. CPU execution has two numerical threads, a 600-second worker ceiling and 1 GiB RSS monitoring. Failures retain diagnostics and owned-child resource receipts, not completed inference claims.

## Interpret raw arrays and events

A model window has 43,844 mono samples, approximately 1.988 seconds of context. Note/onset heads are `[1,172,88]`; contour is `[1,172,264]`. These are activation frames/bins, not played-note or string counts. Crop/padding/window context is recorded; retained arrays are not independent short-note validations. MIDI 21–108 includes C1, but representability does not establish low-fundamental accuracy.

Two fixed project decoders reuse the same arrays at 127.7/25 ms minimums. They use threshold-active runs with local model-onset splits; no Melodia recovery, inferred onsets, pitch-bend decoding or upstream note-creation parity is implemented. The 25 ms floor is not 25 ms acoustic resolution: ordinary three-hop events span about 34.83 ms, and empirical-clock corrections can change eligibility. Lower floors can add partial/noise hypotheses instead of recovering true notes.

`comparison.json` retains coverage/windows, both event variants and uncertainties; numeric `activations.npz` retains note/onset/contour arrays plus nominal, empirical model and input-window projection clocks. The empirical correction uses 172-index steps while cropped window seams use 142 rows. Neither clock is physical capture-latency calibration. Raw event ends, delivered clipped ends, padding and excerpt-boundary context remain distinct. Sparse gaps must not become continuous notes.

Preserve the observed failure: a generated linear missing-F0 C1 case had zero top-one C1 hits across 258 frames, instead favoring C2/C3/C4 partials. Do not octave-correct with truth to erase this. The earlier immutable actual twenty-second pilot yielded 17/65 event hypotheses at the two floors; those counts are sparse candidates, not seventeen or sixty-five verified played notes. Activations are uncalibrated; voicing, string identity, intended notes and correctness remain unknown. Distortion, custom tuning, polyphony, legato and sweeps require listening/reference evidence. The 178 BPM context never quantizes events or establishes meter/mistakes.

## Agent iteration

Inspect the passage and coverage, compare supported thresholds on fresh bounded runs while holding model/windows fixed, and retain raw activations beside event differences. Research pinned preprocessing/decoder definitions through [qualification research](../../../docs/research/BASIC_PITCH_QUALIFICATION.md). Inspect exclusions and estimator disagreements rather than selecting an octave or clock offset by truth. Generated agreement is generator-only; pYIN agreement is not musician truth. Follow [the agent tool contract](../../../docs/spec/AGENT_TOOLS.md) for durable settings, hashes and limits. No accepted best decoder, real-note grade, listening or AU/Logic acceptance follows from a successful run.
