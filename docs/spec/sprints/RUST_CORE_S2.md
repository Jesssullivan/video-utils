# S2 rust_core lane contract: streaming SHA-256, typed RunRecord verify-run, allocation-free DSP

Sprint 20261006-s2, lane `rust_core`, Linear TIN-5607 (parent TIN-5599, roadmap
D1 TIN-5486). Branch `sprint/20261006-s2/rust_core`, worktree
`.local/sprint2/rust_core`, baseline `4b87484`. Authority: operator S2 decision
"d1: minimum credible Rust move with explicit FFmpeg-orchestration deviation"
(`program/sprints/20261006-s2.json`), repository AGENTS.md and
R-HOOK-CONVERGENCE-20261004 R-N11/R-N12/R-N13. Phase 1 froze this contract
before any build, test or numerical execution.

## Scope

The lane adds three Rust capabilities. Python remains the FFmpeg orchestration
owner and the lane changes no Python worker, profile, detector or master.

1. `src/hash.rs` provides a dependency-free FIPS 180-4 SHA-256 implementation.
   The streaming `Sha256` hasher accepts arbitrary update splits, and
   `hash_file`/`hash_reader` use a fixed 1 MiB read buffer. The CLI command is
   `video-utils hash FILE...`. For each file it prints `<64 lowercase hex>  <FILE>\n`,
   which is the `shasum -a 256` text-mode line. A name containing `\` or newline
   uses the shasum/coreutils escaping rule: the line starts with `\`, and
   backslash and newline are escaped. Directories and unreadable paths produce a
   typed error on stderr and exit 1. The remaining files are still processed.
   Paths are taken as `OsString` and never pass through a shell.
2. `src/run_record.rs` provides a typed `RunRecord` for the subset of the run
   manifest that is consumed elsewhere: `scripts/run_demo.py`
   `validate_existing`/`snapshot_existing` and `scripts/rhythm.py`
   `input_timeline`. The CLI command is `video-utils verify-run RUN_DIR`. It is
   metadata-only, meaning it does not decode media or run ffprobe/FFmpeg, and it
   is read-only and bounded. It prints one JSON receipt on stdout and exits:
   - 0 when the receipt is `verified`;
   - 1 when the receipt is `failed` and carries one typed `reason` code (also
     printed to stderr as `video-utils: verify-run failed: <code>: <detail>`);
   - 2 on usage errors.
3. `src/dsp.rs` provides allocation-free, bounded, atomic-failure DSP:
   - an RBJ `Biquad` with `peaking` coefficients that match the FFmpeg
     `equalizer=f=F:t=q:w=Q:g=G:b=0:r=f64` formulas used by
     `scripts/media.py post_denoise_filters`. It runs Direct Form I with f64
     coefficients and state on f32 samples;
   - an RBJ `low_shelf` with Q parameterization;
   - a `PeakRms` meter.

   All three use `MAX_BLOCK_SAMPLES` and follow the `apply_gain` convention:
   when an error is detected, the buffer and the filter or meter state stay
   bitwise unchanged. `apply_gain`, `GainError`, `MAX_BLOCK_SAMPLES` and
   `MAX_LINEAR_GAIN` keep their names, signatures and behavior. `src/lib.rs`
   only adds `pub mod dsp; pub mod hash; pub mod run_record;`.

Out of scope: adopting these filters in the rendering path, replacing FFmpeg
`equalizer`, changing the FULLER/accepted profile, any default change, AU
render-callback changes, MCP tool/skill admission (root-owned), the export
receipt (`export/outcome.json`) and decoded PCM extent checks. All of these are
reported as explicit unknowns.

## Owned files

`Cargo.toml`; `Cargo.lock`; `src/lib.rs`; `src/main.rs`; `src/hash.rs`;
`src/run_record.rs`; `src/dsp.rs`; `tests/cli.rs`; `tests/dsp.rs`;
`native/au-spike/Cargo.toml`; `native/au-spike/Cargo.lock`;
`docs/spec/sprints/RUST_CORE_S2.md`;
`docs/agent-notes/sprints/20261006-s2/rust_core-*.json`. Generated outputs go
under `artifacts/s2/rust_core/` in the worktree, which is gitignored. Reads of
`artifacts/runs/*` and the original take are read-only.

## Dependency decision (recorded before implementation)

The contract allowed serde/serde_json behind a default-on `records` feature
when `Cargo.lock` can be updated offline with the pinned 1.95.0 toolchain. An
inspection of the local Cargo registry cache (metadata only) found the
following:

| Present | Absent |
| --- | --- |
| `serde-1.0.228`, `serde_core`, `serde_derive`, `proc-macro2`, `quote`, `syn`, `unicode-ident`, `memchr` | `serde_json`, `itoa`, `ryu` |

An offline lock update with serde_json is therefore not possible, and network
crate fetching is not part of this lane. **Decision:** implement a minimal
strict JSON reader inside `src/run_record.rs` and add no external dependencies
and no cargo features. Consequences:

- Both `Cargo.lock` files keep only workspace-local packages.
- `native/au-spike/Cargo.toml` stays unchanged, because there is no default
  feature to disable.
- The AU staticlib remains dependency-free. This is proven with
  `cargo build --locked -j 1` in `native/au-spike`.

The decision is restated in the acceptance receipt.

The reader follows RFC 8259 and is at least as strict as `strict_json`:

- It requires an object root.
- It rejects NaN, Infinity and non-finite or overflowed numbers, trailing data,
  lone surrogates, control characters in strings and invalid escapes.
- Nesting is limited to 128 levels and input to 2 MiB, which is the
  `MAX_MANIFEST_BYTES` value in `run_demo.py`.
- It rejects duplicate object keys. This is a declared strictness deviation:
  Python keeps the last duplicate, and S1 manifests come from `json.dumps`, so
  they contain none.
- Integers are parsed exactly as u64 from their raw text, never through f64.

## RunRecord model (typed subset)

| Field | Type / rule | Failure reason code |
| --- | --- | --- |
| `schema_version` | integer == 1 | `schema_version_unsupported` |
| `run_id` | non-empty string == RUN_DIR basename | `run_id_mismatch` |
| `run_dir` | absolute; canonical path == canonical RUN_DIR | `run_dir_mismatch` |
| `source.path` | absolute path string (Unicode preserved, e.g. U+202F) | `manifest_field_invalid` |
| `source.sha256` | `[0-9a-f]{64}` | `hash_malformed` |
| `output_sha256` | object, 1..=64 entries; plain basename keys (no `/`, `\`, `..`, leading `.`, `:`); `[0-9a-f]{64}` values | `unsafe_output_name` / `hash_malformed` |
| `timeline.no_time_stretch` | must be JSON `true` | `time_stretch_not_excluded` |
| `timeline.audio_start_seconds` | finite number | `timeline_start_invalid` |
| `timeline.format_start_seconds` | `Option<f64>`; absent = unknown | none |
| `pcm.sample_rate` / `pcm.channels` / `pcm.sample_count` | positive exact integers (u32/u16/u64) | `pcm_invalid` |
| `pcm.codec` | `Option<String>` | none |
| `dsp_latency.denoise.delay_samples`, `.status`; `dsp_latency.physical_audio_video_sync_verified` | `Option`; absent stays `null` (unknown), never coerced to false/0 | none |
| `status` | `Option<String>`, echoed | none |

Every file named in `output_sha256` is checked in sorted key order. The file
must be a regular non-symlink file inside RUN_DIR, and its streamed digest must
equal the manifest value. The possible reason codes are `output_missing`,
`output_not_regular` and `output_hash_mismatch`.

The source file is hashed when it exists. A mismatch is a failure with reason
`source_hash_mismatch`. An absent source yields
`source.status = "absent_unverified"` and does not fail the run. The
`--require-source` option turns absence into the failure `source_missing`.

Integrity checks:

- The manifest must be a regular non-symlink file of at most 2 MiB
  (`manifest_missing` / `manifest_not_regular` / `manifest_too_large`).
- It must be valid JSON (`manifest_invalid_json`).
- It is re-hashed at the end (`manifest_changed`).
- Each file's length is checked before and after hashing
  (`file_changed_during_verification`).
- The total number of hashed bytes is capped at 8 GiB (`read_budget_exceeded`).

The first failing check determines the reason. The receipt still lists
per-file results computed up to that point.

The receipt includes these explicit unknown or unverified fields, which are
always present:

- `pcm_extent_verified: false`, with basis `metadata_only_no_decode`
- `export_receipt_verified: "not_checked"`
- `listening_accepted: null`
- `physical_audio_video_sync_verified`, echoed from the manifest or `null`
- `source.status` in {`verified`, `absent_unverified`}
- `verifier: "video-utils <version> verify-run"`
- `manifest_sha256`

A `verified` receipt establishes only byte identity and typed field validity.
It does not establish media quality, timing accuracy or listening acceptance.

## DSP definitions (frozen)

- **Peaking**
  - `A = 10^(G/40)`, `w0 = 2π f0/fs`, `alpha = sin(w0)/(2Q)`
  - `b = [1+αA, −2cos w0, 1−αA]`, `a = [1+α/A, −2cos w0, 1−α/A]`
  - All coefficients are normalized by `a0`.
  - This is the FFmpeg `af_biquads` equalizer with `t=q`. The parity claim
    comes from reading the source, so it is an inference until the optional
    M11 measurement is run.
- **Low shelf** (RBJ cookbook, Q form): `alpha = sin(w0)/(2Q)`.
  - `b0 = A[(A+1)−(A−1)cos w0+2√A α]`
  - `b1 = 2A[(A−1)−(A+1)cos w0]`
  - `b2 = A[(A+1)−(A−1)cos w0−2√A α]`
  - `a0 = (A+1)+(A−1)cos w0+2√A α`
  - `a1 = −2[(A−1)+(A+1)cos w0]`
  - `a2 = (A+1)+(A−1)cos w0−2√A α`
  - FFmpeg `lowshelf` parity is an unknown.
- **Parameter bounds** (`DspError::InvalidParameter`):
  - `fs` must be in [8000, 384000].
  - `f0` must be in (0, 0.49·fs).
  - `Q` must be in [0.1, 40].
  - `|G|` must be at most 24 dB.
  - All parameters must be finite.
- **Errors**: `BlockTooLarge`, `InvalidParameter`, `NonFiniteSample` and
  `Overflow` (a non-finite output). Error checking is two-pass: the first pass
  runs on a stack copy of the state, then the results are committed. Nothing
  allocates in the constructor or in `process`. `reset()` zeroes the state.
- Processing is single-channel. Multichannel audio uses one instance per planar
  channel. No high-pass and no notch are provided or defaulted.
- **`PeakRms`**:
  - `process(&mut self, &[f32])` accumulates the peak absolute value, the sum
    of squares (f64) and the sample count.
  - `peak()`, `rms()` and `*_dbfs()` return `Option`. An empty meter returns
    `None`, which means unknown, not −∞.
  - A non-finite sample leaves the meter unchanged.

## Test protocol

Run everything from the worktree root with `CARGO_BUILD_JOBS=1` and one heavy
job at a time:

1. `cargo test --locked -j 1`, which runs the unit tests in `src/*.rs`,
   `tests/cli.rs` and `tests/dsp.rs`.
2. `cargo clippy --locked -j 1 --all-targets -- -D warnings`, if clippy is
   available (clippy 0.1.95 is installed).
3. In `native/au-spike`: `cargo build --locked -j 1`, then
   `cargo test --locked -j 1`, then clippy with the same flags.
4. Real-run check:
   `cargo run --locked -j 1 -- verify-run /Users/jess/git/video-utils/artifacts/runs/20261006T041633Z-990aa1bd6737 > artifacts/s2/rust_core/verify-run-s1.json`,
   with a 300 s timeout. It reads about 140 MB of outputs and, when present, the
   228 MB source.
5. Real-run hash parity: `video-utils hash` on the 6 output WAVs, compared with
   `shasum -a 256` on the same paths. The output goes to
   `artifacts/s2/rust_core/hash-parity.txt`.
6. Optional: `cargo test --locked -j 1 --test dsp -- --ignored ffmpeg_parity`,
   with `FFMPEG` exported to the nix ffmpeg-headless 8.1.2 path and a 30 s
   in-test deadline.

No Python modules are affected. The lane edits no `.py` files, so it runs no
Python unittest modules.

Fixtures:

- **`tests/cli.rs`.** The 4 existing tests stay unchanged and must pass. New
  tests:
  - `hash_matches_fips_digest_and_shasum_for_unicode_space_paths`. The file name
    contains a space, U+202F and `$(x);`. The contents are `abc` and also
    1,000,000 × `a` (crossing buffer boundaries). Digests must equal the FIPS
    values. The test also checks against `/usr/bin/shasum -a 256` or
    `sha256sum` when one exists. When neither exists, it records the
    cross-check as skipped through test output and does not fail.
  - `verify_run_accepts_matching_temp_run_dir`. A temp run dir whose name
    contains a space has a schema-1 manifest, 3 small output files and a source
    file with a Unicode/space name outside the dir. Expected: exit 0, receipt
    `verified`, 3/3 outputs, `source.status = verified`, and the unknown fields
    present with their declared values.
  - `verify_run_refuses_tamper_with_typed_reasons`. A table of mutations, each
    applied to a fresh copy:
    - one byte flipped in an output → `output_hash_mismatch`
    - `no_time_stretch: false` → `time_stretch_not_excluded`
    - `no_time_stretch` missing → `time_stretch_not_excluded`
    - `schema_version: 2` → `schema_version_unsupported`
    - the source changed → `source_hash_mismatch`
    - an output replaced with a symlink → `output_not_regular`
    - key `../x` → `unsafe_output_name`
    - a duplicate key → `manifest_invalid_json`
    - a `NaN` literal → `manifest_invalid_json`
    - a manifest over 2 MiB → `manifest_too_large`
    - a wrong `run_dir` → `run_dir_mismatch`

    Each case requires exit 1, the exact reason code, and byte-identical fixture
    files before and after (verify-run is read-only).
- **`tests/dsp.rs`** uses a counting `#[global_allocator]` with a const
  thread-local counter.
  - `impulse_matches_closed_form_rbj`. The grid is:
    - peaking (300 Hz, +1 dB, Q 0.8), (160 Hz, +2 dB, Q 0.7) and
      (32.703 Hz, −3 dB, Q 1.0);
    - low shelf (100 Hz, +3 dB, Q 0.707) and (40 Hz, +2 dB, Q 0.5);
    - each at fs 44100 and 48000, which gives 10 cases.

    For each case, the 4096-sample impulse response must match the closed-form
    pole-residue expansion `h[n] = (b2/a2)δ[n] + 2·Re(R·pⁿ)` with absolute
    error ≤ 1e-6. If the poles are real, a two-real-pole form is used. The
    coefficients are re-derived from the cookbook formulas in the test, not
    imported from `src`.
  - `low_string_tone_passes_300hz_peaking_band`. A 32.703 Hz sine at
    amplitude 0.5 runs through peaking (300 Hz, +1 dB, Q 0.8) at fs 44100 and
    48000. After a 1 s settle, a 4 s Goertzel measurement at exactly
    32.703 Hz is taken on input and output. Pass if |gain| ≤ 0.05 dB and the
    result agrees with the analytic |H(e^{jw})| within 0.005 dB, for 2/2 rates.
    Disclosure only, not gated: the same measurement through the accepted
    profile's 160 Hz +2 dB Q 0.7 band is printed as a measured value.
  - `peaking_center_and_shelf_asymptotes`. Peaking gain at f0 must be within
    0.01 dB of G. Low-shelf DC gain must be within 0.01 dB of G. Low-shelf gain
    at 0.45·fs must be within 0.1 dB of 0.
  - `bounds_and_atomic_refusal`. Cases:
    - a block of `MAX_BLOCK_SAMPLES + 1`;
    - NaN and Inf samples at the last index;
    - an overflow input (`f32::MAX` with +24 dB);
    - each invalid parameter (f0 ≤ 0, f0 ≥ 0.49·fs, Q out of range, |G| > 24,
      fs out of range, NaN).

    Each must return the typed error with the buffer, filter state and meter
    state bitwise unchanged. The state is compared through a pure accessor or a
    subsequent identical-output check.
  - `process_paths_do_not_allocate`. The Biquad, low shelf, `PeakRms` and
    `apply_gain` process calls (4/4) make 0 allocations on a 4096-sample block,
    after construction outside the counted region.
  - `ffmpeg_parity` (`#[ignore]`, optional). An `aevalsrc` unit impulse at
    44100 Hz runs through
    `equalizer=f=300:t=q:w=0.8:g=1:b=0:r=f64`, output as f32le to stdout. The
    first 4096 samples are compared with Rust, with max |diff| ≤ 1e-6. If
    `FFMPEG` is unset, the test reports `unmeasured`.
- **Unit tests in `src/hash.rs`.** The 5 FIPS 180-4 / NIST vectors are empty,
  `abc`, the 448-bit `abcdbcde…nopq`, the 896-bit `abcdefgh…nopqrstu` and
  1,000,000 × `a`. Split invariance: every split point of the 448- and 896-bit
  messages, plus chunk sizes {1, 63, 64, 65, 1 MiB+1} on the 1M message.
- **Unit tests in `src/run_record.rs`.** JSON reader accept/reject tables
  (escapes, surrogate pairs including U+202F, depth 129, exponent overflow,
  trailing data, duplicate keys) and exact u64 parsing of `sample_count`.

## Completion metrics (denominators and claim classes)

Claim classes:

- **measured**: produced by an executed test or command.
- **inference**: derived from reading source or specs.
- **unknown**: not established.

No listening claims are made.

| ID | Metric | Pass condition | Class |
| --- | --- | --- | --- |
| M1 | SHA-256 vectors | 5/5 FIPS vectors; all split-invariance cases equal | measured |
| M2 | CLI hash on Unicode/space paths | 2/2 contents equal FIPS digests; external shasum agreement k/k where available (skips are counted and reported) | measured |
| M3 | Real-media hash parity | `video-utils hash` equals `shasum -a 256` for 6/6 S1 output WAVs | measured |
| M4 | verify-run on the real S1 run dir | exit 0; outputs 6/6 verified; source 1/1 verified or `absent_unverified`, reported as is | measured |
| M5 | verify-run on the temp positive fixture | exit 0; 3/3 outputs; source verified | measured |
| M6 | verify-run tamper refusals | 11/11 mutations exit 1 with the exact typed reason; 11/11 leave the fixture byte-identical. The 3 contract-required cases (hash mismatch, no_time_stretch, schema) are among them | measured |
| M7 | Impulse vs closed-form RBJ | 10/10 cases with max abs error ≤ 1e-6 over 4096 samples | measured |
| M8 | 32.703 Hz through the 300 Hz +1 dB Q 0.8 band | 2/2 rates with \|gain\| ≤ 0.05 dB and ≤ 0.005 dB from analytic. The 160 Hz band value is disclosed without a gate | measured |
| M9 | Bounds and atomic refusal | all listed refusal cases typed and bitwise-unchanged (n/n, with n reported) | measured |
| M10 | Allocation-free process paths | 4/4 with 0 allocations | measured |
| M11 | FFmpeg equalizer parity | max \|diff\| ≤ 1e-6 if run; otherwise `unknown`/`unmeasured` | measured or unknown |
| M12 | Build hygiene | `cargo test --locked -j 1` green at root (4 existing + 3 new cli tests, dsp and unit tests) and in `native/au-spike`; `cargo build --locked -j 1` in au-spike; clippy `-D warnings` clean at both, or `unavailable` recorded; 0 external packages in both locks | measured |
| M13 | D1 acceptance map | 6/6 phrases (Unicode/space paths, explicit tools, source hashing, isolated runs, versioned API/hooks, ordered graph provenance) each mapped to an existing test or file; `ffmpeg_orchestration_owner: "python"` recorded as the declared deviation | inference (mapping), with cited tests measured by root's full suite |

## D1 acceptance receipt plan

`docs/agent-notes/sprints/20261006-s2/rust_core-d1-acceptance.json` will map
each phrase to evidence. The intended mapping is below; final test names are
verified before the receipt is written.

| Phrase | Evidence |
| --- | --- |
| Unicode/space paths | `tests/cli.rs` forwarding test and new hash test |
| explicit tools | `program/tools.json`, `tests/test_tools.py`, `tests/test_tool_contracts.py` |
| source hashing | `src/hash.rs`, `verify-run`, `scripts/run_demo.py validate_existing`, `tests/test_demo.py` |
| isolated runs | per-`run_id` `artifacts/runs/` and the `run_dir`/`run_id` checks in `verify-run`, plus `tests/test_demo.py` |
| versioned API/hooks | `scripts/mcp_server.py` and `tests/test_mcp.py` version negotiation |
| ordered graph provenance | `scripts/dag.py`, `tests/test_dag.py`, `docs/spec/PHRASE_DAG.md` |

The receipt also records:

- the dependency decision;
- `ffmpeg_orchestration_owner: "python"`, which is the declared deviation from
  "Rust owns the CLI" for media orchestration;
- the exact commands, exit codes and digests.

A run receipt `rust_core-s2-run.json` carries the M1–M12 values.

## Root-owned changes requested (not made by this lane)

- `just/workflow.just`:
  ```
  # Stream SHA-256 of one or more files (shasum -a 256 compatible lines)
  hash +FILES:
      CARGO_BUILD_JOBS=1 cargo run --locked -j 1 --quiet -- hash {{FILES}}

  # Metadata-only, read-only hash/typed-field verification of a run directory
  verify-run RUN_DIR:
      CARGO_BUILD_JOBS=1 cargo run --locked -j 1 --quiet -- verify-run "{{RUN_DIR}}"
  ```
  The final text quotes paths so that space and Unicode paths reach the binary
  intact.
- `docs/spec/PROJECT.md`, after the sentence "The Rust CLI exposes `probe`,
  `clean`, …":
  > The Rust CLI natively implements streaming SHA-256 (`hash`) and typed,
  > metadata-only run-manifest verification (`verify-run`); FFmpeg/ffprobe
  > orchestration remains owned by the Python workers that the CLI dispatches,
  > a declared D1 deviation recorded in
  > `docs/agent-notes/sprints/20261006-s2/rust_core-d1-acceptance.json`.
- Optional and deferred for root decision: MCP tool and skill admission for
  `verify-run` (`program/tools.json`, `scripts/mcp_server.py`,
  `.agents/skills/`). It is not required for this lane's acceptance.
- CI: `.github/workflows/ci.yml` has no cargo step. Root may add
  `cargo test --locked -j 1` (root and `native/au-spike`). That file is outside
  lane ownership.

## Preregistration

This lane is verification, not a tuning experiment. All thresholds, fixture
grids, tone frequencies, filter parameters, mutation tables and the real-run
target were frozen in this commit before any build or numerical execution. The
grid includes the accepted profile's actual 160/300 Hz bands, and the 32.703 Hz
value is the C1 low string from `program/instrument.json`.

- There is no random seed. Every fixture is deterministic.
- There is no held-out truth set and no parameter is fitted. No threshold or
  grid may be relaxed after results are observed.
- A failed metric is reported as failed, with its value and denominator, and is
  not retuned.
- An M11 disagreement with FFmpeg is a measured non-parity result. It does not
  change `media.py` or any profile.
- Experimental non-improvement is valid completion. No default
  detector/profile/master adoption follows from any result.

## Phase 2 results (added after implementation; frozen text above unchanged)

Implementation commit `e40733861cbe48e7f73e4a9b032944c3796a039f`. Run receipt:
`docs/agent-notes/sprints/20261006-s2/rust_core-s2-run.json`. D1 map:
`docs/agent-notes/sprints/20261006-s2/rust_core-d1-acceptance.json`. No
threshold, grid or mutation table was changed after results were observed.

| ID | Result | Class |
| --- | --- | --- |
| M1 | 5/5 FIPS vectors; 170/170 split points (57 + 113); 5/5 chunk sizes | measured |
| M2 | 2/2 FIPS digests; 2/2 byte-identical with `/usr/bin/shasum -a 256` | measured |
| M3 | 6/6 S1 WAV lines byte-identical to `shasum -a 256` (release binary) | measured |
| M4 | exit 0; outputs 6/6; source 1/1 `verified` (228,291,885 bytes) | measured |
| M5 | exit 0; 3/3 outputs; source `verified`; unknown fields present | measured |
| M6 | 11/11 exact typed reasons; 11/11 fixtures byte-identical | measured |
| M7 | 10/10; max abs error 1.776e-9 to 3.976e-8 | measured |
| M8 | 2/2; +0.018396/+0.018397 dB (analytic +0.018695/+0.018696; diff −0.000299 dB). 160 Hz +2 dB Q 0.7 disclosure: +0.169815/+0.169817 dB | measured |
| M9 | 37/37 (6 process, 28 parameter, 3 meter) typed and bitwise unchanged | measured |
| M10 | 4/4 zero allocations | measured |
| M11 | 300 Hz +1 dB Q 0.8, 44.1 kHz, 4096 samples: max abs diff 0 (bit-identical f32) vs FFmpeg 8.1.2. Other bands, rates and `lowshelf` parity: unknown | measured (one configuration) |
| M12 | root `cargo test --locked -j 1` green (15 unit, 7 cli, 5 dsp + 1 ignored run separately); root clippy clean; au-spike build/release/test green (3/3); au-spike clippy **fails** on a pre-existing finding; 0 external packages in both locks | measured |
| M13 | 6/6 phrases mapped; `ffmpeg_orchestration_owner: "python"` | inference (mapping) |

Deviations and findings, stated as they occurred:

- The first M7 run compared two Q 0.5 shelf cases against a NaN reference.
  RBJ Q 0.5 shelves have an exactly repeated real pole, the two-real-pole
  residues divide by zero, and `f64::max` ignores NaN, so those cases passed
  vacuously. This was caught before any receipt. The test now uses the exact
  repeated-pole limit form, `h[n] = (b2/a2)δ[n] + n0(n+1)pⁿ + n1·n·pⁿ⁻¹`, and
  asserts a finite, non-degenerate reference. Both cases then measured
  1.9e-8 and 1.5e-8 against the unchanged 1e-6 gate.
- A non-preregistered unit test expected a 0 dB peaking filter to be bitwise
  identity. It now uses a 1e-12 tolerance, because the f64 recursion leaves
  3.6e-16 rounding residue.
- M4 with the contract command (`cargo run` debug, 300 s timeout) timed out
  (exit 124). The host load average was 186–393 on 6 cores. The debug build
  spends about 2.1 s of CPU per 20 MB, and wall time is dominated by
  contention. M4 was measured with the release binary instead: exit 0, 47.9 s
  wall, 2.54 s user. A debug retry with a 1500 s timeout
  then exited 0 in 866 s and produced a receipt identical to the release one.
- au-spike clippy `-D warnings` reports `clippy::manual_is_multiple_of` at
  `native/au-spike/src/lib.rs:50`. That file is not lane-owned and is
  unchanged since baseline `4b87484`. The fix is requested from root.
- `video-utils hash -` hashes a file literally named `-`. Unlike `shasum`, it
  does not read stdin. verify-run refuses a symlinked source with
  `source_not_regular`, which is stricter than following the link.
