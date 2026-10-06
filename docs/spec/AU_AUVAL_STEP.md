# AU discovery and validator step (read-only)

Operator-facing contract for `native/au-spike/host/auval_step.py`, the
`RegisteredRender.swift` harness and the biquad C export. The lane contract
is `docs/spec/sprints/AU_AUVAL_S2.md` (S2 sprint 20261006-s2, TIN-5612).
The step implements stages 2, 3 (gated) and 5 (gated) of
`docs/spec/AU_HOST_ACCEPTANCE_LANE.md`. Stage 1 (installation) and stage 6
(Logic) are out of scope, as AGENTS.md requires.

## What the step does and does not do

```bash
python3 native/au-spike/host/auval_step.py [--out DIR] [--packaging-receipt PATH]
```

The default `--out` is `artifacts/s2/au_auval/`, which is gitignored. The
default packaging receipt is `.cache/au-packaging/receipt.json`, which is read
only if present.

The step **only runs read-only queries**:

| Order | Command | Timeout | When |
| --- | --- | --- | --- |
| 1 | `/usr/bin/sw_vers`, `/usr/bin/uname -m` | 10 s each | always |
| 2 | `/usr/bin/pluginkit -m -A -D -v -i org.video-utils.gain.prototype.audio-unit` | 30 s | always |
| 3 | `/usr/bin/auval -a` | 60 s | always |
| 4 | `/usr/bin/xcrun swiftc -typecheck -swift-version 6 -module-cache-path <out>/swift-module-cache native/au-spike/host/RegisteredRender.swift` | 180 s | if `/usr/bin/xcrun` exists; otherwise `skipped` with a reason |
| 5 | `/usr/bin/auval -v aufx vuGn Jess` | 120 s, one attempt | only if discovery `passed` |
| 6 | `xcrun swiftc -O …RegisteredRender.swift -o <out>/registered-render`, then run it | 180 s each | only if discovery `passed` |

It never copies, installs, registers, elects, resets caches, launches an app,
uses `sudo` or touches system plugin locations. A static test
(`Guard.test_no_install_or_mutation_tokens`) enforces this. On a timeout it
kills only the identity-checked process group it started and does not retry.
The OS may update its own plugin caches when it answers a query. The receipt
records that effect as `os_managed_side_effects: "unknown"`, which is not a
lane mutation.

## Discovery decision

| pluginkit match lines | `auval -a` rows `aufx vuGn Jess` | `stage_2_discovery` | top-level `status` |
| --- | --- | --- | --- |
| 0 | 0 | `blocked_not_installed` | `blocked_not_installed` |
| 1 | 1 | `passed` | `validated` or `validation_failed` |
| ≥2, or rows ≥2 | any | `ambiguous_duplicates` | `discovery_ambiguous` |
| 1 / 0 or 0 / 1 | — | `ambiguous_partial` | `discovery_ambiguous` |
| any timeout or non-zero exit | — | `error` | `discovery_error` |

`validated` requires all three of the following: `stage_5_auval.status ==
"passed"`, `artifact_binding == "matched"` and a passing registered render. In
every other registered outcome the status is `validation_failed`, and the
stage fields show which part did not pass.

A `blocked_not_installed` receipt is a valid result. It sets
`next_required_decision: "operator-approved stage-1 installation
(AU_HOST_ACCEPTANCE_LANE.md); not requested by this lane"`.

## Receipt (`vu.au_auval_step.v1`)

The step writes `<out>/auval-step-<UTCstamp>.json` and `<out>/receipt.json`
through a temporary file plus an atomic replace, with `allow_nan=False`. Raw
query output (which can list other installed plugins) stays only under
`<out>/raw/`. The receipt keeps only the matching lines, a stdout sha256 and
the line counts.

Fields with fixed values: `stage_1_installation` and `installation` are
`out_of_scope`. `stage_4_parameters_state`, `logic_host_acceptance`, `bypass`,
`state_recall` and `listening` are `not_performed`. `realtime_deadline` is
`unknown`. `audio_device_opened` is `false`. `packaging_artifact_freshness`
is `stale_unknown`, because `src/lib.rs` changed after the last packaging
build. `mutations` holds empty `files_copied`, `registry_writes` and
`writes_outside_out_dir` lists.

`observed_instantiation_mode` stays `unknown` unless the registered harness
reports `AUAudioUnit.isLoadedInProcess`. Requesting `.loadOutOfProcess` alone
never sets it.

`stage_5_auval` holds `status` (`not_performed`, `passed`, `failed`, `timeout`
or `failed_artifact_mismatch`), `artifact_binding`, `artifact_sha256` and
`parsed`. `artifact_binding` is `null` when discovery did not pass. Otherwise
it takes one of these values:

- `matched`
- `mismatch`
- `unknown_no_packaging_receipt`
- `unknown_path_not_reported`

A `mismatch` keeps the transcript but caps the status at
`failed_artifact_mismatch`.

### `auval -v` parser

`parse_auval_transcript` splits the transcript on dashed rule lines. The
following rules apply:

- Text before the first rule is a preamble and is not a section.
- The chunk that carries `AU VALIDATION SUCCEEDED/FAILED` is the summary and
  is not a section.
- A chunk that holds only a title line, such as `VALIDATING AUDIO UNIT: …`,
  becomes the title of the next chunk.

A section result is `fail` if the section contains `* * FAIL`, `FAIL…`,
`ERROR:` or `FATAL ERROR`. Otherwise it is `pass` if the section contains
`* * PASS`, and `no_verdict` if it contains neither. Failure takes precedence.
The overall result is `fatal` when a `FATAL ERROR` line appears (the message is
kept), then `failed` or `passed` from the summary line, and otherwise
`unknown`. The parser never upgrades `unknown` or `no_verdict` to a pass.

The five frozen fixtures in `native/au-spike/tests/fixtures/auval/` are
**synthetic**, modeled on Apple's auval layout (`synthetic_format_model`).
None of them is a recorded run of this unit. The `auval -a` row format was
checked against this host's live listing on 2026-10-06, by format only.

## Registered render harness (`RegisteredRender.swift`)

The harness is a command-line Swift program. It runs these steps:

1. It enumerates exactly `aufx/vuGn/Jess` through
   `AVAudioUnitComponentManager`.
2. It instantiates the unit asynchronously with `.loadOutOfProcess`, servicing
   the main run loop in 50 ms slices for up to 10 s per attempt, with at most
   3 attempts.
3. It sets formats and the gain parameter (address 0) while render resources
   are released, then allocates.
4. It renders 60 fixtures: mono and stereo, gains 0, 0.5, 1, 2 and 16, blocks
   of 128 and 4096 plus a final 37-frame block, and impulse, 32.703 Hz sine and
   LCG noise at 48 kHz. Amplitude is 0.01 for gains of 2 or more.
5. It compares the output with an independent Float32 `input × gain` oracle.
   The limit is max |err| ≤ 2e-6, with zero offset for impulses.

The render path has no prints, file I/O or allocation. All buffers, the
`AudioBufferList` and the pull block are created before the render calls. The
harness prints JSON once, after deallocation. Timings are reported in three
wall-clock categories (startup, processing and teardown) and are not a realtime
deadline measurement.

Exit codes: 0 when all fixtures pass, 1 on a failure, 3 when blocked and 4 on
an instantiation timeout.

## Biquad C export (`include/video_utils_biquad.h`, ABI 1)

`vu_biquad_init`, `vu_biquad_set`, `vu_biquad_reset` and `vu_biquad_process`
wrap the root crate's `video_utils::dsp::Biquad` (RBJ peaking and low shelf).
The storage is caller-preallocated: 128 bytes, 8-byte aligned. The Rust slot
uses 88 bytes. Codes `VU_BQ_*` 0–8 cover these cases:

- pointer, bound, alignment and aliasing checks;
- the uninitialized-slot check;
- `VU_BQ_INTERNAL_PANIC`, which only unwind (test) builds can reach. Release
  builds use `panic = "abort"`.

Every error leaves the samples and the slot bitwise unchanged. There is no
high-pass, low-cut or notch kind, so the ABI cannot remove the ~32.7 Hz C1
fundamental. The export is **not adopted** by the AU render callback,
`GainKernel.mm`, the FFmpeg path or any profile or master. The gain ABI
(`video_utils_gain.h`) is unchanged.

`just au-spike-check` covers the export with these checks:

- the Rust FFI test: 150/150 bit-parity cases, 20/20 atomic refusals and
  0 allocations over 2048 render calls;
- the C harness: 39/39 (9 status assertions plus 30 bit-identical parity cases
  against an independent C DF1 oracle);
- an `llvm-objdump` audit of the release `_vu_biquad_process` direct body:
  0 forbidden references.

## Claim classes

M (measured by these tests and tools), C (configuration inspection), H (host
read-only observation), NP (not performed or out of scope), U (unknown).
Nothing here makes a listening, musical-correctness or restoration claim.
