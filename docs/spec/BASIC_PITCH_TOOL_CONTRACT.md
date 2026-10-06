# Optional Basic Pitch hook contract

Root admitted `basic_pitch_compare` as the twenty-fourth typed tool on October
5, 2026 after isolated runtime qualification, seventeen worker tests and
independent adapter review. Authority: the operator's renewed parallel request,
repository `AGENTS.md`, R-HOOK-CONVERGENCE-20261004 and R-N13. Root owns
integration/publication; the comparator lane owns its adapter/runtime and the
hook lane owns this interface. Source implementation, local runtime proof,
publication, generated quality and real-note/listening acceptance remain
separate. Capture-profile authoring is admitted as tool twenty-five in the
[final authoring contract](CAPTURE_PROFILE_TOOL_CONTRACT.md); later custom-profile
application remains separate.

The definition of done was recorded before integration: use the worker's fixed
CLI, bind exact local model/source/runtime identities, document every typed knob
and resource ceiling, exercise meaningful small subprocess success and failure
cases, and verify a matching intent/research/iteration skill. No arbitrary
executable, argv, URL, model ID or decoder JSON enters this operation.

## Fixed interface

The worker is `scripts/basic_pitch_compare.py RUN_DIR --max-analysis-seconds SECONDS --onset-threshold VALUE --frame-threshold VALUE [--start-seconds SECONDS]`.
The hook forwards only those fixed flags. The worker selects its pinned qualified
isolated runtime; `VIDEO_UTILS_ANALYSIS_PYTHON` does not choose that inference
child. Existing `VIDEO_UTILS_PYTHON` is operator configuration for the stdlib
parent launcher, with no caller-controlled executable field. Running this tool
never installs dependencies, downloads models or falls back to another runtime.

| Hook field | Type / bounds / default | Purpose |
|---|---|---|
| `run_dir` | Required string, 1–4096 characters | Existing run beneath repository `artifacts/runs`; relative paths use repository root. |
| `max_analysis_seconds` | Finite number 1..30; default 20 | Total sparse excerpt budget. |
| `start_seconds` | Optional finite number >=0 and inside input | A contiguous audio-relative excerpt instead of distributed coverage. |
| `onset_threshold` | Finite number 0.05..0.95; default 0.5 | Uncalibrated onset activation threshold. |
| `frame_threshold` | Finite number 0.05..0.95; default 0.3 | Uncalibrated sustain activation threshold. |
| `timeout_seconds` | Integer 1..900; default 600 | Outer owned process-group deadline including inference descendants. |

Unknown fields, booleans as numbers and non-finite values reject before launching.
The wrapper checks every original path component for symlinks/traversal and
requires regular nonsymlink `manifest.json` (<=1 MiB) and `denoised.wav` (<=1 GiB).
The worker verifies the derivative hash, no-time-stretch mapping, original source
lineage and exact native PCM rate/channels/sample extent. Maximum source duration
is 300 seconds; there are at most six excerpts, thirty analyzed seconds and
twenty-four model windows. No source, master, existing pitch result or DAG is
changed. Default sparse scheduling includes the beginning and ending.

## Runtime, model and output

The fixed model is registered `spotify-basic-pitch-0.4.0-onnx`, 230,444 bytes,
SHA-256 `2c3c1d144bfa61ad236e92e169c13535c880469a12a047d4e73451f2c059a0ec`.
The worker selects the registered exact local cached/qualified file and rejects
missing, changed or unregistered bytes with no implicit prefetch. Its isolated
launcher is `artifacts/model-runtime-env/onnx-1.30.0-cp314/python/bin/python`.
Package versions, acquired wheel hashes and installed package bytes are checked
against the qualified wheel manifest; CPU provider and explicit model tensor
contracts are required. The worker rechecks source/model/context identities
before promotion. Qualification provenance is in the
[comparator lane](BASIC_PITCH_COMPARATOR_LANE.md) and
[runtime receipt](../agent-notes/2026-10-05-basic-pitch-runtime.json).

Inference uses CPU two threads, sequential execution and one inter-op thread.
The worker monitors a 1 GiB child RSS ceiling, 600-second overall deadline,
20 MiB raw arrays and 5,000 events per preset. Numerical, shape, duration, window
and log limits reject excess rather than silently drop evidence. Timeout cleanup
belongs only to the recorded child; the outer dispatcher additionally owns its
new process group under R-N11. Failures retain local diagnostic artifacts and
return an error, never a successful comparison.

Each success writes a fresh immutable `learned-pitch/<UTC-nonce>/` with raw named
numeric NPZ arrays, model/source/runtime/settings/worker identities and the full
comparison. Compact stdout contains `comparison_json`, `status`,
`coverage_seconds`, `model_windows`, `excerpt_count`,
`event_counts_by_minimum_ms` and `performance_grade: not_graded`; it remains
subject to the dispatcher's 2 MiB output bound. Coverage, original-source mapping,
model clock adjustment, raw arrays, event ambiguity and the exact worker/context
hashes stay available in the full local artifact.

Two fixed project decoders, 127.7 and 25 ms minimum duration, reuse identical raw
arrays. The adapter is threshold-active-run/onset-split decoding with the
qualified official model; `upstream_decoder_parity` is false. It does not claim
upstream Melodia/postprocessing parity. Approximately two-second model context,
seam clocks and truncated excerpts are not latency calibration or complete
musical phrasing.

## Local hook proof and claim boundary

Five focused tests passed in 5.695 seconds with locked Python 3.14 and explicit
pinned FFmpeg/FFprobe 8.1.2. Real initialized stdio MCP execution analyzed a
generated two-second tone, used two model windows through the qualified CPU
runtime, produced the compact/full artifacts, preserved input hashes and
reported ungraded performance. Tests checked model/source identities, provider,
RSS/raw-array bounds, both fixed decoder variants and nullable intended-note,
string and performance fields. Wrong start/changed source errors were exercised
through MCP. Direct fixtures proved missing/changed model and absent qualified
launcher reject before decoding. Negative schemas, literal argv, preflight
byte/symlink limits and the fixed child-runtime selection were checked.

The combined hook checkpoint passed **65/65 targeted tests**, with no skipped
media checks: 46 tool contracts (55.122 seconds), 11 dispatcher tests and 8 MCP
tests. The new five tests also passed separately as recorded above. Local hook
success does not imply private-remote publication or hosted CI qualification;
root owns those separate receipts.

The skill lane independently passed all twenty-four bundled validations,
initialized tools/prompts enumeration and exact content readback of every
`prompts/get`, with empty stderr. Live Basic Pitch fields/defaults matched this
contract and included no model or interpreter argument. No skill changes
followed that final local proof.

Activations remain `uncalibrated_model_activation`; no calibrated correctness or
voicing probability follows. The model's corrected linear missing-fundamental
C1 fixture retained a raw top-one failure, **0/258** frames. Never hide that result
or use agreement with pYIN as independent musician truth. Sparse excerpts do not
recover every legato/sweep/tap note or grade the full take. No identified string,
original stem, intended-note correctness, tonic/mode, missed note, listening
acceptance or AU/Logic host acceptance follows from successful inference.
Generated agreement retains generator-only eligibility and exclusion scope.
