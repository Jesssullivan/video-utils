# S2 au_auval lane contract: auval discovery step, out-of-process render harness, biquad C export

Sprint 20261006-s2, lane `au_auval`, Linear TIN-5612. Branch
`sprint/20261006-s2/au_auval`, worktree `.local/sprint2/au_auval`, baseline
`e0da4ca`. Authority: operator-approved S2 sprint, repository AGENTS.md and
R-HOOK-CONVERGENCE-20261004 R-N11/R-N12/R-N13. This contract was frozen in
phase 1 before any build, test, host query or numerical execution. The lane
writes no Linear, pushes nothing and merges nothing; root signs and integrates.

This lane continues the staged protocol in `docs/spec/AU_HOST_ACCEPTANCE_LANE.md`.
It implements tooling for stage 2 (discovery), the gated stage 3 harness
(registered out-of-process render) and the gated stage 5 step (targeted
`auval`). Stage 1 (installation) and stage 6 (Logic) stay out of scope.
The AGENTS.md rule holds: plugin installation and repairs are outside this
release's scope.

## Scope

1. **Biquad C export.** `native/au-spike/src/lib.rs` gains a second C ABI that
   wraps the S2-merged root crate `video_utils::dsp::Biquad` (RBJ peaking and
   low shelf, Direct Form I, f64 coefficients/state, f32 samples). It does not
   reimplement the filter. Header: `native/au-spike/include/video_utils_biquad.h`.
   The existing gain ABI (`vu_gain_*`, `video_utils_gain.h`, ABI version 1)
   keeps its bytes and behavior unchanged.
2. **Discovery/validator step.** `native/au-spike/host/auval_step.py` is a
   stdlib-only, bounded, read-only host step that writes a receipt.
3. **Registered render harness.** `native/au-spike/host/RegisteredRender.swift`
   is an out-of-process render harness. The lane typechecks it and runs it only
   when discovery passes.
4. **Check integration.** `native/au-spike/check.py` compiles and runs the
   biquad C harness and audits the direct `vu_biquad_process` body.
   `just au-spike-check` and `just au-package-check` must still pass.

Out of scope (each is reported as an explicit unknown or not-performed field,
never as a pass):

- Copying anything to `/Applications`, `~/Library` or any other install
  location; `pluginkit -a/-r/-e`; `lsregister`; AudioUnit cache deletion;
  launching the containing app; any plugin repair.
- Logic, audio devices, state/preset recall, bypass, hard realtime deadlines.
- Adopting the biquad in the AU render callback, `GainKernel.mm`, the FFmpeg
  `equalizer` path or any profile/master. No detector, profile or master
  default changes.
- MCP tool or skill admission. These are root-owned; see requests below.

## Owned files

- `native/au-spike/src/lib.rs`
- `native/au-spike/include/` (new `video_utils_biquad.h`; `video_utils_gain.h` unchanged)
- `native/au-spike/tests/` (new `biquad_ffi.rs`, `biquad_abi_harness.c`,
  `fixtures/auval/*.txt`; existing harnesses unchanged)
- `native/au-spike/check.py`
- `native/au-spike/host/` (new `auval_step.py`, `RegisteredRender.swift`)
- `tests/test_au_auval.py`
- `docs/spec/AU_AUVAL_STEP.md`
- `docs/spec/sprints/AU_AUVAL_S2.md`
- `docs/agent-notes/sprints/20261006-s2/au_auval-*.json`

Generated outputs go only under `artifacts/s2/au_auval/` in the worktree, which
is gitignored, and under the existing gitignored `.cache/au-spike/` build cache
used by `check.py`. `native/au-spike/Cargo.toml` is not owned and needs no
change: `video-utils` is already a dependency, and Cargo auto-discovers
`tests/*.rs`. Reads of `artifacts/runs/*`, the main checkout's
`.cache/au-packaging/receipt.json` and `program/*.json` are read-only.

## 1. Biquad C ABI (`video_utils_biquad.h`, ABI version 1)

### Storage

The caller preallocates storage and the library never allocates it:

```c
#define VU_BIQUAD_STORAGE_WORDS 16
typedef struct vu_biquad { uint64_t opaque[VU_BIQUAD_STORAGE_WORDS]; } vu_biquad; /* 128 bytes, 8-byte aligned */
```

On the Rust side the storage is a `#[repr(C)] struct Slot { magic: u64, kind: u32, abi: u32, biquad: Biquad }`.
Compile-time asserts require `size_of::<Slot>() <= 128` and
`align_of::<Slot>() <= 8`. `vu_biquad_storage_size()` and
`vu_biquad_storage_align()` return the real Rust values, and the C harness
asserts that `sizeof(vu_biquad)` and `_Alignof(vu_biquad)` are at least those
values. Storage must be zero-initialized or initialized by `vu_biquad_init`.
`magic` (`0x5655_4251_0000_0001`, "VUBQ" plus version) is set last by a
successful init and is cleared by nothing else. The C caller must not
interpret or modify the opaque words.

### Functions

| Function | Thread role | Contract |
| --- | --- | --- |
| `uint32_t vu_biquad_abi_version(void)` | any | returns 1 |
| `uint32_t vu_biquad_max_samples(void)` | any | returns `MAX_BLOCK_SAMPLES` (65536) |
| `uint32_t vu_biquad_storage_size(void)` / `_align(void)` | any | real Rust slot size and alignment |
| `int32_t vu_biquad_init(vu_biquad *f, uint32_t kind, double sample_rate, double frequency, double q, double gain_db)` | control | validates through `BiquadCoefficients::{peaking,low_shelf}`, then writes a fresh slot with zero delay line. On error the storage is bitwise unchanged |
| `int32_t vu_biquad_set(vu_biquad *f, uint32_t kind, double sample_rate, double frequency, double q, double gain_db)` | control (never concurrent with process) | retunes with `set_peaking`/`set_low_shelf` and keeps the delay line. Requires an initialized slot. Atomic on error |
| `int32_t vu_biquad_reset(vu_biquad *f)` | control | zeroes the delay line only. Requires an initialized slot |
| `int32_t vu_biquad_process(vu_biquad *f, float *samples, uint32_t count)` | render | `Biquad::process` in place. No allocation, lock, I/O, logging or syscall. Atomic on error |

The only kinds are `VU_BIQUAD_PEAKING = 1` and `VU_BIQUAD_LOW_SHELF = 2`. There
is deliberately no high-pass, low-cut or notch kind, so the ABI cannot remove
the approximately 32.7 Hz C1 fundamental by construction. The parameter bounds
are those of `src/dsp.rs`: fs 8000–384000 Hz, 0 < f < 0.49·fs, Q 0.1–40 and
|gain| ≤ 24 dB.

### Status codes

The codes use their own prefix, so both headers can be included together:

| Code | Value | Meaning |
| --- | --- | --- |
| `VU_BQ_OK` | 0 | success |
| `VU_BQ_INVALID_POINTER` | 1 | NULL or misaligned filter; or NULL or misaligned samples with count > 0 |
| `VU_BQ_BLOCK_TOO_LARGE` | 2 | count > 65536 |
| `VU_BQ_INVALID_PARAMETER` | 3 | `DspError::InvalidParameter` or an unknown kind |
| `VU_BQ_NON_FINITE_SAMPLE` | 4 | `DspError::NonFiniteSample` |
| `VU_BQ_OVERFLOW` | 5 | `DspError::Overflow` |
| `VU_BQ_UNINITIALIZED` | 6 | magic, kind or abi mismatch on set, reset or process |
| `VU_BQ_ALIASED` | 7 | the sample range overlaps the filter storage (detectable aliasing only) |
| `VU_BQ_INTERNAL_PANIC` | 8 | a Rust panic was caught. Reachable only in unwind builds, as described below |

The checks run in this order: filter pointer, then count bound, then (for
count == 0) return OK with NULL samples allowed, then samples pointer, then
aliasing, then magic. Every error leaves the samples and the slot bitwise
unchanged. Invalid or dangling foreign pointers cannot be made safe by these
checks, and the header says so, as `video_utils_gain.h` does.

### Panic and unwind semantics

Each exported body runs inside `std::panic::catch_unwind(AssertUnwindSafe(..))`.
Under the release profile (`panic = "abort"`, already in the au-spike
`Cargo.toml`) a panic aborts the process and never unwinds into C. Rust 1.95
also aborts on any unwind out of an `extern "C"` function. Under the test
profile (unwind) a caught panic returns `VU_BQ_INTERNAL_PANIC`, and the slot
and samples stay unchanged because `Biquad::process` commits only after
validation. A `#[cfg(test)]`-only fault hook in `lib.rs` unit tests exercises
this path. No validated input is expected to panic; the code has no indexing or
unwrap in the render path. `catch_unwind` allocates only on the panic path.

## 2. Discovery and validator step (`host/auval_step.py`)

Invocation: `python3 native/au-spike/host/auval_step.py [--out DIR] [--packaging-receipt PATH]`.
The default `--out` is `artifacts/s2/au_auval/`. The default packaging receipt
is `<ROOT>/.cache/au-packaging/receipt.json`, which is read only if present.
Darwin is required; any other platform gets the receipt `status: "unsupported"`
and exit 2.

Each subprocess uses absolute tool paths, `stdin=DEVNULL`,
`start_new_session=True` and an explicit timeout. On timeout, only the
identity-checked process group that this step started is killed, following the
`check.py` pattern. A timeout is recorded and is never retried.

| Order | Command (exact) | Timeout | Runs when |
| --- | --- | --- | --- |
| 1 | `/usr/bin/sw_vers`, `/usr/bin/uname -m` | 10 s each | always |
| 2 | `/usr/bin/pluginkit -m -A -D -v -i org.video-utils.gain.prototype.audio-unit` (the stage-2 form; superset of `-m -i`) | 30 s | always |
| 3 | `/usr/bin/auval -a` | 60 s | always |
| 4 | `/usr/bin/xcrun swiftc -typecheck -swift-version 6 native/au-spike/host/RegisteredRender.swift` | 180 s | always, if `xcrun swiftc` resolves; otherwise `skipped` with a reason |
| 5 | `/usr/bin/auval -v aufx vuGn Jess` | 120 s, single attempt | only if `stage_2_discovery == "passed"` |
| 6 | compile (`swiftc -O`, 180 s) and run `RegisteredRender` (180 s total) | 180 s each | only if `stage_2_discovery == "passed"` |

The step contains no install, copy, registration, election, cache-reset,
launch, `sudo`, `killall` or `/Applications`/`~/Library` path. A static test
enforces this. A pluginkit match query and `auval -a` enumeration are read-only
queries, as the lane rules authorize.

### Discovery decision

The step reads pluginkit match lines containing the bundle ID and `auval -a`
lines matching `^\s*aufx\s+vuGn\s+Jess\b`.

| pluginkit matches | auval -a triple | `stage_2_discovery` |
| --- | --- | --- |
| 0 | 0 | `blocked_not_installed` |
| 1 | 1 | `passed` |
| ≥2, or triple ≥2 | any | `ambiguous_duplicates` (no auval -v, no render) |
| 1 | 0, or 0 / 1 | `ambiguous_partial` (no auval -v, no render) |
| any timeout or non-zero exit | — | `error` with exit code and stderr tail |

On `blocked_not_installed` nothing is copied anywhere. The receipt records
`stage_1_installation: "out_of_scope"` and `next_required_decision:
"operator-approved stage-1 installation (AU_HOST_ACCEPTANCE_LANE.md); not
requested by this lane"`. Stages 3 and 5 stay `not_performed` with
`blocked_by: "stage_2_discovery"`.

### Artifact binding (registered path only)

The registered appex path comes from pluginkit `-v` output. The step hashes its
`Contents/MacOS/VideoUtilsGain` (read-only, streamed SHA-256) and compares it to
the extension executable hash in the packaging receipt.
`artifact_binding` takes one of these values: `matched`, `mismatch`,
`unknown_no_packaging_receipt` or `unknown_path_not_reported`. The parsed
`auval -v` result carries this hash. A `mismatch` keeps the transcript but
caps `stage_5_auval.status` at `failed_artifact_mismatch`.

### auval -v transcript parser

`parse_auval_transcript(text) -> dict` is a pure function. It splits on the
dashed rule lines (`^-{10,}$`) and takes each section title from the first
non-empty line. A section's result is `pass` when it contains `* * PASS`,
`fail` when it contains `* * FAIL` or `FAIL`/`ERROR:` lines, and `no_verdict`
otherwise. Warning lines are counted per section. The overall result is `passed` on
`AU VALIDATION SUCCEEDED`, `failed` on `AU VALIDATION FAILED`, `fatal` on
`FATAL ERROR` (with the message preserved), and `unknown` otherwise. The parser
never upgrades `unknown` or `no_verdict` to a pass. Output fields:
`overall`, `sections: [{title, result, warnings, line_span}]`, `section_count`,
`pass_count`, `fail_count`, `no_verdict_count`, `fatal_message`,
`transcript_sha256`. `parse_auval_listing(text)` returns the triples that match
the target and the total row count.

### Receipt

The step writes `artifacts/s2/au_auval/auval-step-<UTCstamp>.json` and
`receipt.json` through a temp file plus atomic replace, with `allow_nan=False`.
Schema `vu.au_auval_step.v1`:

| Field | Values / rule |
| --- | --- |
| `schema`, `created_at`, `host` (`os_version`, `architecture`), `tool_paths` | strings |
| `authority` | `"R-HOOK-CONVERGENCE-20261004 R-N11/R-N12/R-N13; S2 20261006-s2 TIN-5612"` |
| `source_sha256` | sha256 of `auval_step.py`, `RegisteredRender.swift`, `targets.json` |
| `target` | `{bundle_id, component: {type: aufx, subtype: vuGn, manufacturer: Jess}}` from `packaging/targets.json` |
| `stage_0_local_checks` | `"see au-spike-check receipt"` plus its sha256 if present, else `"unknown"` |
| `stage_1_installation` / `installation` | always `"out_of_scope"` |
| `stage_2_discovery` | enum above. `discovery.pluginkit` and `discovery.auval_list` hold the exit code, timeout flag, matching lines and stdout sha256/line count. Raw full output stays only under `artifacts/` because it can list other installed plugins |
| `swift_typecheck` | `{status: passed / failed / skipped, reason, seconds}` |
| `stage_3_registered_render` | `not_performed` (with `blocked_by`), or the harness JSON with `status` |
| `observed_instantiation_mode` | `"unknown"` unless the API reports it. Requesting `.loadOutOfProcess` alone never sets `out_of_process` |
| `stage_4_parameters_state` | `"not_performed"` |
| `stage_5_auval` | `{status: not_performed / passed / failed / timeout / failed_artifact_mismatch, artifact_binding, artifact_sha256, parsed}` |
| `logic_host_acceptance` | `"not_performed"` |
| `realtime_deadline` | `"unknown"` |
| `bypass`, `state_recall`, `listening` | `"not_performed"` |
| `audio_device_opened` | `false` |
| `mutations` | `{files_copied: [], registry_writes: [], writes_outside_out_dir: []}` (empty by construction; enforced by test) |
| `commands` | `[{argv, timeout_s, exit_code, timed_out, seconds}]` |
| `status` | top-level summary: `blocked_not_installed`, `discovery_ambiguous`, `discovery_error`, `validated` or `validation_failed` |

Exit codes: 0 when the receipt is written, whatever the stage outcome (a
blocked receipt is a valid result); 1 on an internal or receipt-write error;
2 on an unsupported platform.

## 3. Registered out-of-process render harness (`host/RegisteredRender.swift`)

This is a command-line Swift program (AVFAudio and AudioToolbox only). It never
constructs `GuitarGainAudioUnit` directly.

1. Enumerate `AVAudioUnitComponentManager.shared().components(matching:)` for
   exactly `(aufx, vuGn, Jess)`. Unless exactly one component matches, it
   prints `{status: "blocked", reason}` and exits 3.
2. Call `AUAudioUnit.instantiate(with:options: [.loadOutOfProcess])`
   asynchronously. The main run loop is serviced in 50 ms slices up to a
   10 s deadline per attempt, with at most 3 attempts. The returned unit is
   retained. The requested mode is recorded; the observed mode is `unknown`.
3. Preallocate all input, output and pull buffers before
   `allocateRenderResources()`. Set the gain parameter (address 0) while
   resources are released, then allocate.
4. Fixtures (reduced S2 subset of stage 3): mono and stereo at 48 kHz; blocks
   of 128 and 4096 plus a final non-divisible block of 37 frames; gains 0, 0.5,
   1, 2 and 16 (amplitude 0.01 for gains of 2 or more). Signals are a unit
   impulse with distinct L/R positions, a 32.703 Hz sine and seeded LCG noise
   (seed 20261006). The oracle is an independent Float32 `input×gain`;
   max |err| ≤ 2e-6, with zero sample-offset tolerance for impulses.
5. The render path contains no prints, file I/O or allocation. JSON is printed
   once after `deallocateRenderResources()`. Timing categories (startup,
   processing, teardown) are reported separately, as wall-clock values only.

Exit codes: 0 when all fixtures pass, 1 on a fixture failure, 3 when blocked
and 4 on an instantiation timeout.

## Completion metrics (with denominators and claim classes)

Claim classes: **M** = measurement made by this lane's tests or tools on this
host; **C** = configuration/source inspection; **H** = host observation
(read-only query); **NP** = not performed / out of scope; **U** = unknown.
The lane makes no listening claim (L) and no musical restoration claim.

| # | Metric | Denominator / target | Class |
| --- | --- | --- | --- |
| 1 | FFI vs Rust `Biquad` bit parity: output samples and final state bits are identical | 150 cases = 3 signals × 5 configs × 2 rates × 5 partitions, 48000 samples each (7,200,000 samples). Target 150/150 | M |
| 2 | Refusal atomicity: the expected code and bitwise-unchanged samples and slot | 20 frozen refusal cases (list below). Target 20/20 | M |
| 3 | Render-call allocations (counting `GlobalAlloc`, calling thread) | 2 kinds × 1024 calls × 4096 samples = 2048 calls. Target 0 allocations. Scope: Rust global allocator on the test thread, not raw `malloc` from foreign code | M |
| 4 | Compiled direct-body audit of `_vu_biquad_process` in the release staticlib (`xcrun llvm-objdump`) | forbidden references (`_malloc`, `_calloc`, `_realloc`, `__rust_alloc`, `__rust_dealloc`, `pthread_mutex`, `dispatch_`, `_printf`, `_write`, `_objc_`). Target 0. Scope: the direct body only, not every callee | M |
| 5 | C harness (`xcrun clang -std=c11 -Wall -Wextra -Werror -ffp-contract=off`): layout, status codes and parity with an independent C DF1 oracle on the same coefficients | 5 configs × 2 signals (32.703 Hz sine, seeded noise) at 48 kHz × 3 partitions (single, 128, seeded irregular) = 30 bit-identical cases, plus 9 status assertions. Target 39/39. If clang is unavailable: `skipped_with_reason`, which is not a pass | M |
| 6 | Unwind-profile panic path returns `VU_BQ_INTERNAL_PANIC` with the slot unchanged | 1/1 | M |
| 6b | Release `panic = "abort"` and no unwind across the ABI | profile line present; Rust ≥1.81 extern-"C" abort-on-unwind | C |
| 7 | `auval` parser on frozen fixtures | 5 fixtures (below). Target 5/5 exact expected dicts | M |
| 8 | Receipt schema and decision table with an injected fake runner | 7 decision scenarios (blocked, passed, 2 ambiguous, pluginkit timeout, auval -v timeout, artifact mismatch). Target 7/7 | M |
| 9 | Static no-install guard on `auval_step.py` and `RegisteredRender.swift` | forbidden-token hits. Target 0 | M |
| 10 | Live discovery receipt on this host | 1 receipt. Expected (inference, not yet measured) `blocked_not_installed`, with 0 files copied and 0 registry writes | H |
| 11 | `swiftc -typecheck` of `RegisteredRender.swift` | passed, failed or skipped with a reason; recorded as is | M |
| 12 | `just au-spike-check` and `just au-package-check` | 2/2 exit 0. Receipts and source hashes recorded in the handoff note | M |
| 13 | `tests/test_au_auval.py` | all tests pass. The count is recorded and fixed by the protocol below | M |
| — | Stage 3 registered render, stage 5 auval | `not_performed` unless discovery passes; expected `not_performed` | NP |
| — | Logic, state recall, bypass, installation, listening | `not_performed` / `out_of_scope` | NP |
| — | Realtime deadline, observed instantiation mode, packaging artifact freshness | `unknown` | U |

Packaging freshness: `src/lib.rs` changes in this lane. Any previously built
`.cache/au-packaging` bundle predates it, so the receipt marks
`packaging_artifact_freshness: "stale_unknown"`. The lane does not run
`au-package-build`. The gain render path does not reference the new exports,
so the AU's gain behavior is unchanged in source. Whether the linked binary is
bit-identical is unknown until a rebuild.

## Test protocol (exact)

Python (stdlib only, run from the worktree root):

```bash
PYTHONPATH=tests python3 -m unittest test_au_auval -v
python3 native/au-spike/packaging/tests.py        # au-package-check, unchanged
```

Rust and C, through the existing recipe (`check.py` runs `cargo test --offline
--locked -j1 -- --test-threads=1`, the release build, the C harnesses and the
audits):

```bash
just au-spike-check
just au-package-check
cargo test --offline --locked --manifest-path native/au-spike/Cargo.toml \
  --target-dir .cache/au-spike/rust --jobs 1 -- --test-threads=1
```

The live host step (read-only, bounded) is run once after the tests pass:

```bash
python3 native/au-spike/host/auval_step.py --out artifacts/s2/au_auval
```

Only one heavy job runs at a time. FFmpeg is not used by this lane.

### `tests/test_au_auval.py` (module `test_au_auval`)

The test imports `native/au-spike/host/auval_step.py` through `importlib`, and
the step accepts an injectable `runner` and `which`. Real host commands are
never executed by unit tests.

- `ReceiptSchema.test_required_fields_and_enums`: covers every receipt field
  in the table, the enum membership, `allow_nan=False` round trip and the
  explicit unknown/not-performed values.
- `BlockedPath.test_not_installed_runs_only_readonly_queries`: the fake
  pluginkit returns no match and the fake `auval -a` has no triple. The test
  asserts `stage_2_discovery == "blocked_not_installed"`, exactly the read-only
  argv list for steps 1–4, no `auval -v`, no harness run, empty mutations, and
  that the receipt is written only under the temporary `--out`.
- `BlockedPath.test_ambiguous_partial` and `test_ambiguous_duplicates`.
- `BlockedPath.test_pluginkit_timeout_is_error_not_retry`.
- `RegisteredPath.test_passed_runs_auval_once_with_timeout`: covers
  `auval -v` argv, `timeout=120`, a single call, the parsed result and
  artifact hash binding against a temporary fake appex and packaging receipt.
- `RegisteredPath.test_auval_timeout_recorded` and
  `test_artifact_mismatch_caps_status`.
- `Parser.test_fixture_<name>` for each frozen fixture.
- `Parser.test_listing_matches_only_exact_triple`. Near misses such as
  `aufx vuGn Jesz`, `aumf vuGn Jess` and comment lines are rejected.
- `Guard.test_no_install_or_mutation_tokens` scans the source text of both
  host files for `ditto`, `cp `, `/Applications`, `Library/Audio`,
  `pluginkit", "-a"`, `-e`, `-r` election flags, `lsregister`, `killall`, `sudo`,
  `rm ` and `open -n`.
- `Guard.test_swiftc_missing_skips_with_reason`.

### Frozen `auval` fixtures (`native/au-spike/tests/fixtures/auval/`)

All five are **synthetic transcripts modeled on Apple auval's published section
layout**. Their provenance is `synthetic_format_model`; none is a recorded run
of this unit, which is not installed. If discovery ever passes, the real
transcript is kept under `artifacts/` and added only as an extra fixture. It
never replaces these.

1. `pass.txt`: 6 sections, all `* * PASS`, then `AU VALIDATION SUCCEEDED`. Expect overall `passed`, 6/6 pass.
2. `fail_param.txt`: 6 sections, one with `* * FAIL` plus `ERROR:` lines, then `AU VALIDATION FAILED`. Expect overall `failed`, fail_count 1.
3. `fatal_not_found.txt`: `FATAL ERROR: didn't find the component`. Expect overall `fatal` and the message preserved.
4. `warn_no_verdict.txt`: one section with `WARNING:` lines and no verdict, and no final line. Expect overall `unknown`, no_verdict_count 1.
5. `listing.txt`: `auval -a`-style rows including near misses. Expect exactly 1 target triple and the total row count.

Root may optionally authorize recording a real transcript of an Apple system
unit, for example `auval -v aufx lpas appl`, as a format-validation fixture.
This lane does not run it without that authorization.

### Biquad fixtures (frozen; used by `native/au-spike/tests/biquad_ffi.rs`)

- Rates: 44100 and 48000 Hz. Length: 48000 samples per signal.
- Signals:
  - unit impulse at sample 0;
  - a 0.5-amplitude 32.703 Hz sine (C1, from `program/instrument.json`);
  - seeded LCG noise: seed 20261006, Numerical Recipes 32-bit LCG,
    `(u32 >> 8) / 2^24 * 2 − 1` scaled by 0.25.
- Configs (kind, f, Q, dB):
  - peaking 160, 0.7, +2.0 and peaking 300, 0.8, +1.0. These are the
    `peaking_eq` bands of the accepted FULLER run
    `artifacts/runs/20261006T041633Z-990aa1bd6737/applied-profile.json`
    (sha256 `a1229c84f1c9c1731c4d6733b4d3516301b39947bf9e325d7e663f9437c4b826`;
    metadata read only, no media opened);
  - peaking 32.703, 1.0, +3.0 (low-string boost, not a cut);
  - low shelf 80, 0.707, +4.0;
  - peaking 2500, 1.2, −3.0.
- Partitions: a single block; fixed 64; fixed 128; fixed 4096; seeded irregular
  sizes from 1 to 997 (same LCG, seed 20261007).
- The reference is a single `video_utils::dsp::Biquad` processing the whole
  signal in one call. The FFI result is processed through `vu_biquad_init` and
  repeated `vu_biquad_process` over the partition. The comparison uses
  `f32::to_bits` on every sample and `BiquadState::to_bits` on the final state
  (read via a Rust test-only accessor).
- The 20 refusal cases:
  1. NULL filter on process;
  2. misaligned filter;
  3. NULL samples with count 1;
  4. misaligned samples;
  5. count 65537;
  6. uninitialized (zeroed) slot on process;
  7. uninitialized slot on set;
  8. uninitialized slot on reset;
  9. NaN sample;
  10. +Inf sample;
  11. overflow (`f32::MAX` with +24 dB peaking);
  12. init with f = 0;
  13. init with f = 0.49·fs;
  14. init with Q = 0.05;
  15. init with gain = 24.5 dB;
  16. init with NaN sample rate;
  17. init with fs = 7999;
  18. kind 0;
  19. kind 3 (no high-pass exists);
  20. samples aliasing the slot.
- Plus: count 0 with NULL samples returns `VU_BQ_OK` with the state
  unchanged. This is a positive case outside the denominator.

## Preregistration

There is none. This lane runs no experiment: no arms, no held-out data, no
scored comparison and no tuning. The fixtures, seeds, tolerances and
denominators above are frozen as deterministic verification inputs, and
changing them after phase 1 requires a recorded amendment. Experimental
non-improvement does not apply. A blocked discovery receipt is a valid
completion state.

## Doctrine checks

- There is no high-pass, low-cut or notch kind and no default filter. The
  32.703 Hz fixture is a boost, and the biquad is not adopted anywhere.
- Measurements (M), configuration inspection (C), host observations (H) and
  not-performed/unknown fields stay separate in every receipt. The lane makes
  no listening, musical-correctness or missed-note claim.
- No install, registration, plugin repair, daemon, model download, Linear
  write or root-owned file edit.

## Root-owned changes requested (not made by this lane)

1. `just/workflow.just`: an optional recipe that root may admit:
   ```just
   # Read-only AU discovery/auval step; never installs, registers or repairs.
   au-auval-step:
       python3 native/au-spike/host/auval_step.py
   ```
2. `native/au-spike/packaging/build.py` `FROZEN`: optionally append
   `"include/video_utils_biquad.h"`, so that packaging receipts hash the new
   header. This is not required, because the bundle does not use it.
3. MCP and skill admission: the biquad export is a native, unadopted primitive,
   and the step is a developer host check comparable to `au-spike-check`. The
   lane requests no `program/tools.json` entry. If root decides to admit
   either one, the typed hook and skill should state the read-only and
   no-install contract above.

## Deliverables at phase close

- Source and tests in owned paths.
- `docs/spec/AU_AUVAL_STEP.md`: the operator-facing step contract.
- `docs/agent-notes/sprints/20261006-s2/au_auval-contract-freeze.json` (this phase).
- `au_auval-handoff.json`: commit, test counts against the denominators above,
  the `au-spike-check` and `au-package-check` receipt hashes, the live
  discovery receipt summary (matching lines only) and every unknown field.
