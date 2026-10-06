# Optional learned pitch comparator lane

Implemented bounded worker checkpoint, October 5–6, 2026; owner
`/root/tonal_inference`. Authority: operator's ten-hour parallel goal and root's
explicit isolated-runtime/adapter release; R-HOOK-CONVERGENCE-20261004 / R-N13.
Root owns publication, just/MCP routing and skill admission. A worker pass is
separate from independent musical acceptance or AU/Logic host acceptance.

The adapter uses the exact official Spotify Basic Pitch 0.4.0 ONNX model and
**project decoding**, preserving note/onset/contour activations, polyphonic note
hypotheses and sparse source timestamps. It does not require an expected score.
Generated labels belong only to evaluation; the tuning registry, chroma and
agreement between estimators cannot establish intended-note correctness.

## Qualified artifacts and runtime

Source commit: `9991303bba609a3b93089d13ec80d1d495083596`; model SHA256:
`2c3c1d144bfa61ad236e92e169c13535c880469a12a047d4e73451f2c059a0ec`,
230,444 bytes, explicit registry ID `spotify-basic-pitch-0.4.0-onnx`.
[Byte qualification](../agent-notes/2026-10-05-basic-pitch-qualified-model.json)
remains an immutable historical checkpoint. Repository-wide Apache-2.0 and
bundled-artifact evidence imply weight applicability; no independently stated
weight license was found. Retain upstream LICENSE/NOTICE attribution and the
[primary research](../research/BASIC_PITCH_QUALIFICATION.md).

The isolated optional environment is
`artifacts/model-runtime-env/onnx-1.30.0-cp314/python/bin/python`.
It runs existing Python3.14.6 with pinned wheel-only ONNX Runtime1.30.0,
NumPy2.5.3, flatbuffers25.12.19, packaging26.3 and protobuf7.36.2. Exact official
PyPI URLs, sizes and hashes were recorded before installation in the
[runtime receipt](../agent-notes/2026-10-05-basic-pitch-runtime.json).
The existing `.venv`, uv.lock and main pyproject are unchanged. No source
compilation, alternate interpreter download, GPU or host change was performed.
The initial CPU graph smoke used approximately62.1MiB peakRSS. It establishes
inference feasibility, not musical performance.

The worker checks installed package versions and installed wheel-member bytes
against verified local wheel archives before inference. It accepts only the
fixed isolated venv launcher; resolving its symlink would incorrectly bypass
that environment. Missing or changed runtime, archives or model yield failure;
no runtime installation or model download happens implicitly. An explicitly
prefetched `models/spotify-basic-pitch-0.4.0-onnx.bin` is preferred if present;
otherwise the exact already-qualified local model is used. Every selected
artifact must satisfy the fixed model hash and byte count.

## Implemented CLI and controls

```sh
python3 scripts/basic_pitch_compare.py RUN_DIR \
  --max-analysis-seconds 20 --onset-threshold 0.5 --frame-threshold 0.3
```

| Control | Bounds/default | Meaning |
|---|---|---|
| `run_dir` | Required existing local run | Verified denoised.wav and native PCM/source manifest. |
| `max_analysis_seconds` | Finite1..30; default20 | Total distributed coverage including ending; at most six excerpts. |
| `start_seconds` | Optional finite value≥0, inside input | One explicit passage, clipped to input end. |
| `onset_threshold` | Finite0.05..0.95; default0.5 | Local onset-activation peaks splitting an active pitch-bin run. |
| `frame_threshold` | Finite0.05..0.95; default0.3 | Sustain activation gate, not calibrated correctness confidence. |
| `runtime_python` | Operator CLI only; fixed qualified path | No arbitrary executable or caller-selected MCP interpreter. |

Model, full MIDI21..108 range and two decoding floors (127.7ms and25ms) are
fixed. C1/MIDI24 is represented; reliable C1/distorted-guitar identification is
unqualified. There is no `melodia_trick`, inferred-onset, model-selection,
intended-note or frequency-suppression control in this worker.

Bounds: input≤300seconds, total analysis≤30seconds,≤6 independent excerpts,
≤24 model windows, one sequential CPU session, intra-op2/inter-op1 threads,
600seconds overall deadline,1GiB observed/inference-process RSS ceiling,
20MiB raw numeric arrays,5,000 events per preset over the whole run,10MiB worker
logs. A directly owned subprocess is monitored by PPID and RSS; exceptions,
deadlines and RSS violations reap that subprocess with an R-N11 receipt.
Failures preserve a separate receipt and never silently drop events. RSS is
sampled, supplemented with the macOS process peak measurement; transient
between-poll allocations are not a hard OS memory reservation.

## Model preprocessing, clocks and decoding

FFmpeg produces separate mono22050Hz float32 analysis excerpts. The original
and masters keep native rate/channels/sample extent. Input, manifest, tuning,
model registry, runtime manifest, model and worker hashes are bound before/after
processing. Denoised input must match its declared SHA and native PCM extent
with `no_time_stretch=true`. Source origin requires explicit finite nonboolean manifest audio_start_seconds;
unknown origins fail before media processing and never default to zero.

Authors' preprocessing:43,844 input samples (~1.98839seconds), prepend3,840
zeros, stride36,164 samples,172 output frames, crop15 each edge, retain142,
concatenate within each excerpt and truncate floor(samples×86/22050).
Explicit graph names map note/onset [1,172,88] and contour [1,172,264].

Three clocks remain separate: nominal frame×256/22050; authors' empirical
`model_frames_to_time` correction subtracting10.326077ms per floor(frame/172);
and actual input-window projection from cropped rows/36,164-sample stride.
The empirical correction repeats at172 indices rather than142-row window
seams. None establishes physical capture latency. JSON records every window's
leading/trailing padding and real context; NPZ preserves all three clocks,
window_index and window_frame_index. Event raw frame/model end values remain
unclipped; delivered audio/source ends are clipped at excerpt boundaries.

Project decoder identity:
`project_threshold_active_runs_with_local_model_onset_splits`. Each independent
MIDI bin starts/stops at frame_threshold; strict local model-onset maxima at
onset_threshold split active runs. No sustain-gap tolerance, inferred onsets,
neighbor suppression, Melodia recovery or pitch-bend decoding. It is **not**
upstream note-creation parity. Polyphonic bins and octave ambiguity remain;
identified_string, intended_note and performance_issue are null.

A run qualifies when corrected model end−start≥the requested floor. Away from
clock corrections127.7ms admits11 nominal hops (~127.710ms), while the original
upstream rounded-frame strict inequality would require12 (~139.320ms).
25ms needs3 hops (~34.830ms); a3-hop span crossing correction index172 can fall
below25ms and be rejected. Tests lock this behavior. Thresholds and floors do
not impose the declared178BPM grid or measured pick attacks.

## Output and evidence

Every success creates a fresh private
`RUN_DIR/learned-pitch/UTC_TIMESTAMP-NONCE/` containing comparison.json,
activations.npz (numeric arrays only), analysis PCM excerpts, task.json,
inference.json and resource/log receipts. No latest link or parent run output
is modified. Failed attempts retain failure.json. Stdout is one JSON object:
comparison_json, status, coverage_seconds, model_windows, excerpt_count,
event_counts_by_minimum_ms and performance_grade=`not_graded`. Errors print a
bounded diagnostic to stderr and exit1.

NPZ per-excerpt prefixes are `excerpt_N_`: note(T,88), onset(T,88),
contour(T,264), model_times_seconds, nominal_times_seconds,
input_window_projection_seconds, window_index and window_frame_index.
JSON retains both floor variants, all event bins and raw frame indices,
source/audio/model/nominal/window clocks, uncalibrated activation evidence and
window context/padding. Model contexts are approximately2seconds; never reuse
pYIN64/256ms eligibility or count short model notes as independently validated.

Initial worker8bc17166 verification: all17 tests passed with optional qualified-runtime
integration. The later source-origin-only fix added five invalid-origin subcases:
17 stdlib tests pass and the18th optional inference test is skipped by default.
No model inference was repeated for that fix; the original worker and tests
were archived before editing. See the [source-origin fix receipt](../agent-notes/2026-10-06-basic-pitch-source-origin-fix.json). A12second generated pilot covered lowC1, missing fundamental,
stepped sweep and polyphonic tapping proxies (8windows). These phase-discontinuous
harmonic signals do not validate physical articulation. The missing-F0 case
contains a linear harmonic ladder, avoiding nonlinear intermodulation that
could regenerate the omitted fundamental. In the corrected linear missing-F0 fixture, raw top-one had0/258
C1 truth-membership hits, returning C2/C3/C4 partials. This is a failure case
for missing-fundamental identification, preserved without octave correction
using truth. All-frame synthetic
diagnostics are descriptive, not musical acceptance; full-context eligibility
and event metrics belong to the independent acceptance lane.

The actual source-bound pilot covered four5second spans including ending:
20seconds (13.2484% coverage),16windows,17 events at127.7ms and65 at25ms,
6.329seconds elapsed,170,917,888byte peakRSS. These are sparse model hypotheses;
there are no intended notes, note-mistake claims or listening acceptance.
Exact immutable paths/hashes and fixture results are in the runtime receipt.

A separate enhanced-main pilot uses denoised26c9f42c input from run232741,
with the same20seconds/16windows:18 and67 hypotheses,8.521seconds and
179,191,808byte peakRSS. Independent hashes, arrays, source spans and three
clocks passed readback;24 checked core/original/latest files stayed unchanged.
It does not replace the older pilot or imply improved note accuracy. See the
[additional receipt](../agent-notes/2026-10-06-basic-pitch-enhanced-main.json).

Fresh-checkout optional runtime setup remains under a separate design release,
with no implicit environment acquisition from this inference worker. The
[portability plan](../agent-notes/2026-10-06-basic-pitch-runtime-portability-plan.md)
proposes a committed path-free wheel lock and explicit native-wheel-only setup;
it is not an installed setup tool until root releases implementation.

## Remaining admission

Root integrates a fixed just/MCP hook and skill only after independent audit
and contract readback. The separate pitch comparator acceptance spec defines
same-horizon generated-bank evaluation, conservative whole-model context and
truth-blind selection. Real annotated truth, full-song transcription,
AU render integration and Logic host acceptance remain future work.
