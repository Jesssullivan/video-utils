# Per-source noise capture authoring hook

Root admitted `capture_profile` as tool twenty-five on October 5, 2026 after the
stdlib worker qualification. Authority: the operator's capture request and
renewed parallel work, repository `AGENTS.md`, R-HOOK-CONVERGENCE-20261004 and
R-N13. Root owns integration/publication and actual-take authoring verification;
the restoration lane owns the worker, and the hook lane owns this contract.
The worker-owner interval and oversized-number audit fixes are now closed as
recorded below. No existing media/profile worker or custom-profile denoise
application is changed by this hook.

The definition of done was recorded before implementation: obtain the fixed
worker CLI and compact result contract; verify current-source/run/PCM hashes,
review scope, native interval, bounded paths/controls and fresh immutable output;
exercise actual small MCP authoring plus malformed, stale and unsafe requests;
and verify an exact matching intent/research/iteration skill. Profile metadata,
subsequent rendering, measured cleanup and listening acceptance remain separate.

## Fixed typed interface

The command is `scripts/capture_profile.py INPUT --run-dir RUN --review REVIEW --capture-start SEC --capture-end SEC --reduction-db NR --noise-floor-db NF --adaptivity AD --gain-smooth GS --integrated-lufs LUFS --true-peak-dbtp DBTP --timeout-seconds SECONDS`.
Optional EQ uses at most three fixed `--eq FREQUENCY_HZ GAIN_DB Q` triples; an
optional compressor uses five fixed all-or-none numeric flags. The MCP operation
has fourteen closed fields, eleven required. No arbitrary argv, filter string,
profile object, model/runtime control or caller-provided replacement hash exists.

| Field | Type / bounds | Purpose |
|---|---|---|
| `input` | Required string, 1–4096 characters | Explicit current original; may be outside repo; regular nonsymlink file <=3 GiB. |
| `run_dir` | Required string, 1–4096 characters | Current verified run beneath repository `artifacts/runs`. |
| `review` | Required string, 1–4096 characters | Existing exact reviewed sidecar beneath that same run, <=16 KiB. |
| `capture_start_seconds`, `capture_end_seconds` | Required finite numbers; start >=0, interval 0.1–10 seconds and within native extent | Audio-relative native sample selection. |
| `reduction_db` | Required finite number 0.01..12 | Candidate reduction; no inferred optimum. |
| `noise_floor_db` | Required finite number -80..-20 | Explicit absolute floor control. |
| `adaptivity` | Required finite number 0..1 | Explicit adaptation. |
| `gain_smooth` | Required integer 0..50 | Explicit frequency gain smoothing. |
| `integrated_lufs` | Required finite number -70..-5 | Target for a separately admitted later render. |
| `true_peak_dbtp` | Required finite number -9..0 | Peak target for later rendering. |
| `timeout_seconds` | Optional integer 1..60; default 60 | Whole-worker deadline, forwarded to standalone owned SIGALRM. |
| `peaking_eq` | Optional list of 0–3 exact objects | Each requires frequency_hz 160..6000, gain_db -3..3, q 0.5..2; frequency also strictly below native Nyquist. Omitted means none. |
| `compressor` | Optional exact five-field object | Required threshold_db -36..-6, ratio 1..3, attack_ms 8..20, release_ms 60..200, knee_db 0..6. Omitted means off. |

All numeric endpoints are inclusive except Nyquist. Booleans-as-numbers,
non-finite values, missing controls, unknown fields and partial compressor
objects reject before launch. The schema validator intentionally adds bounded
array/items/minItems/maxItems support; unbounded arrays, oversized schemas and
array keywords on nonarrays reject. This extends only the deliberate typed EQ
list rather than silently accepting unsupported schema controls.

The wrapper checks original path components before normalization, prohibits
traversal/symlinks, requires the review beneath the run, and bounds native
`source.wav` to 1 GiB and `manifest.json` to 1 MiB. Worker hashing/native header
checks verify the selected original and all current run/context/review bindings.
Original and native media remain immutable. Output is a fresh atomic
`capture-profiles/<UTC-nonce>/` directory under the run; repeated authoring keeps
prior metadata intact.

## Review, authorization and result

The sidecar is an exact sixteen-field schema version 1; unknown/duplicate keys
reject. Required lower-hex SHA-256 fields are `source_sha256`,
`source_run_manifest_sha256` and `source_pcm_sha256`, each matching live inputs.
Finite start_seconds/end_seconds must match requested native-sample coordinates;
time_axis is `decoded_source_audio_samples`. Asserted selected_by/reviewed_by
identities are nonempty and <=128 characters, authorization_reference nonempty
and <=512, and note 1–2000. They are supplied assertions, not authenticated
identity or independently confirmed listening.

Review status is reviewed_candidate, reviewed_possible_contamination or
rejected_contaminated; authorization scope is profile_authoring or
experimental_capture_render. Music/click status is unknown, suspected,
reviewed_no_obvious_content or reviewed_present. Ambient music status is
not_reported, suspected, reviewed_absent or reviewed_present. Authoring does not
silently classify or separate ambient music or infer scope from a detector.

Three successful metadata branches are explicit:

- `authored_unrendered`: existing render-scoped assertions permit source-bound
  `profile.json`; this operation still performs no render.
- `draft_authorization_incomplete`: authoring-only scope writes `proposal.json`
  with noise_capture_authorized false and nullable runnable-profile fields.
- `needs_reselection`: rejected capture or reviewed-present music/click content
  writes a receipt without a runnable profile or proposal.

Compact stdout includes schema_version, tool, status, evidence_kind, run_dir,
output_dir, current source_sha256, nullable profile_path/profile_sha256 and
proposal_path, receipt_path/receipt_sha256, capture requested_seconds/native_samples/
source_media_span_seconds, dsp_performed false and listening_accepted false.
The output identifies source/context/settings/worker/validator hashes and review
uncertainty; captured band shape is not learned during authoring. Domain failures
produce bounded JSON with exit 2. For this tool only, the dispatcher preserves
that bounded worker diagnostic in the MCP tool error; other tools retain their
existing error behavior. Syntax errors use stderr/exit 2.

Standalone limits are 60 seconds, original <=3 GiB, PCM <=1 GiB, 8–192 kHz,
mono/stereo and <=600 seconds. Manifest <=1 MiB, context JSON <=64 KiB,
review/profile <=16 KiB, receipt <=64 KiB and compact result <=16 KiB. Authoring
uses bounded stdlib hashing and RIFF/WAVE header inspection; it invokes no
subprocess, audio decoding, DSP, model acquisition or network. The original-to-
PCM decoder history is retained, not independently rerun.

## Local evidence and application boundary

Five initial focused hook tests passed in 2.281 seconds. Actual initialized MCP
fixtures with deliberately unavailable FFmpeg/FFprobe exercised all three scope
branches, retained contamination uncertainty, wrote independent immutable
metadata, preserved original/native/manifest hashes and produced no new audio.
Native interval 0.125–0.625 seconds mapped to samples 2000–10000 at 16 kHz and
source-media 7.25–7.75 seconds. Tests covered closed nested controls, unsafe
review paths/symlinks/bytes, literal fixed argv, default deadline and bounded
JSON errors for malformed reviews, unrecognized scope and stale hashes.

Final worker qualification includes decimal minimum-interval, direct-API
oversized-number and path-normalization repairs. Frozen worker SHA-256 is
`7d2820878826c87aabf2ab60b73c997b9d406b7f3ff8943d6012ed967444c355`;
the owner reports 45 combined tests passing, including twelve independent audit
cases, with independent same-SHA verification. The six focused hook tests passed
after those repairs in 4.095 seconds. Real MCP authoring of requested interval
0.2–0.3 seconds with reduction 0.01 produced an unrendered profile accepted by the
frozen media validator and kept exact native sample bounds 3200–4800. Requested
seconds, exact native bounds and floating-point profile encoding remain separate
receipt fields; an encoding adjustment never moves a native sample.

Final integrated checkpoint: **71/71 targeted tests passed**, comprising 52 tool
contracts (102.081 seconds), 11 dispatcher tests (1.998 seconds) and 8 MCP tests
(8.925 seconds), with locked Python 3.14 and explicit pinned FFmpeg/FFprobe
8.1.2. No media checks skipped; authoring itself required neither media binary.
The skill lane independently passed all twenty-five bundled validations,
initialized tools/prompts enumeration and exact content readback for every
prompt, with empty stderr. Final capture skill SHA-256 is
`33cd07d572c653222233e17d935bc589a11dbd32cd76def6d46128c7d65b268e`.
These are local source/hook receipts. Root's actual-take authoring, publication,
hosted CI, later rendering and listening remain separate evidence states.

Portable capture means binding a newly reviewed interval to each current source,
not reusing the old take's identity. Existing captured8/captured12/clarity presets
remain bound to original a522115f4e72e19384fb341bc84369728eceefe49183b8c6367a1008a95176c6
and root-reviewed 4.10–4.95 seconds. They are separate fixed denoise presets and
excluded from synthetic benchmark profiles. A generated profile path does not
become an arbitrary denoise MCP argument: custom application is a separate root
admission. Quiet intervals, box-fan context or measured reduction establish no
noise-only capture, recovered stem, low-note preservation, tone optimum,
separation, restored master, listening acceptance or AU/Logic compatibility.
