# Narrate CLI and text pipeline (lane W5): receipt

Date: 2026-10-23. Lane W5 of the narrate plan (TIN-7087, parent TIN-7084, milestone N0 Narration v0).
Authority: the operator-approved narrate plan of 2026-10-22, `docs/spec/NARRATE.md`, AGENTS.md and
R-HOOK-CONVERGENCE-20261004 (R-N11, R-N12, R-N13). Branch `feat/narrate-cli`, first stacked on `feat/narrate-spec`
(lane W4, PR #37); rebased onto main after that landed. Root lands it by fast-forward.

## What landed

- `narrate/`: a standard-library Python package (`python -m narrate {render,evaluate,voices,engines,verify}`)
  that mirrors `condense/`: one `narrate.toml`, `config.run` with bounded tool calls, staged run directories
  renamed into place, a hash-bound manifest and a verify step.
- Input adapters for plain text, markdown manuscripts, SRT, WebVTT, condense `words.json` (through the condense
  EDL with `condense.edl.Timeline`) and `SPEAKER:` dialog, all to one script IR (`narrate/ir.py`).
- The pinned xoxd-lexical pass by path and sha256 (no network), advisory Pattern findings, Vale when present,
  and the RewriteCheck (XL-ACC-001/002) over numbers, units, versions, links, paths, tickets, handles and
  identifiers.
- The pronunciation table normaliser (refuses a substitution that changes digits) and a chunker that never
  splits inside a protected span and re-packs chunks whose spoken form runs past the limit.
- The engine client (`POST /v1/audio/speech` with `ref_audio`/`ref_text`, no proxy, no redirect, typed refusal
  codes) and the fake engines `fake://sine` (deterministic) and `fake://espeak`.
- Policy: consent record, stored evidence, revocation, scopes, allowed engines, stored clip and transcript by
  digest, dialog speaker mapping, hosted and confidential refusals; the engine predicates are asserted equal
  to `narrate/dhall/check.py` on the whole truth table.
- QA through condense's whisper path (`condense.transcribe.read`), `not_measured` without whisper, SIM
  `not_measured`, best of `maxTakes` by seed.
- Post: pauses, timing fit (speed knob to 1.15, then atempo within 8%, then an `overrun` flag), placement,
  two-pass loudnorm with an adaptive pre-limiter, captions, the narration EDL and the manifest.
- `just/narrate.just` (`narrate-render`, `-eval`, `-verify`, `-voices`, `-engines`, `-voice-add`, `-bench` stub,
  `-lint`, `-test`), a `narrate` CI job, `//narrate` Bazel targets (stdlib test hermetic, pytest host-tools)
  with `narrate` added to the graph contract's owned packages.
- TIMELINE_CONTRACT amendment `narration_v1`; the refusal matrix runs every guitar consumer case again with a
  zero-stretch narration manifest, and `tests/cli.rs` asserts both `verify-run` refusals.

## Measurements (2026-10-23, the dev host, `nix develop .#condense`)

| Check | Result |
| --- | --- |
| `just narrate-test` | 110 passed (synthetic fixtures; fake engine; FFmpeg 8.1.2) |
| `just narrate-lint` | ruff check and format clean |
| `bazel test //narrate:stdlib_test //condense:stdlib_test` | both passed; `build --nobuild //... --lockfile_mode=error` passed |
| `test_bazel_graph_s3`, `test_timeline_contract` | passed (contract: 29 cases, condense and narration rows) |
| `cargo test --test cli verify_run_refuses_a_narration` | passed |

A local probe (not in CI): the `fake://espeak` engine with the registered whisper `small.en` model (fetched with
`scripts/model_prefetch.py`, sha256 verified, kept out of git) measured WER 0.0 and 0.125 on two chunks; the
0.125 is whisper writing "7" for the spoken "seven". Before the fix in this lane whisper dropped a first
sentence that started on the first sample; takes are now read with 0.5 s of silence on each side. Without the
pre-limiter that run came out at -16.6 LUFS (outside 0.5 LU); with it, -16.1 LUFS and -1.5 dBTP. These are
measurements on synthetic espeak speech only; no real voice, engine or listening claim is made.

## Open

- `ref_audio` travels as a base64 WAV data URI. Which form each server reads (mlx-audio, vLLM-Omni,
  llama.cpp `llama-tts`) is unverified; W6 checks it per engine.
- Captions are timed from the script placement; whisper alignment of the delivered audio is not done.
- SIM has no scorer; it stays `not_measured` until a speaker-verification model is registered.
- FFmpeg loudnorm reports `dynamic` on some limited inputs although the result is within tolerance; the type is
  recorded per run.
- `narrate-bench` is a stub for lane W3.

## Follow-up (2026-10-23, later run)

- `just` exports `WHISPER_MODEL` (just/condense.just) for every recipe. On a host where the whisper model is
  present, that override reached the fixture configs, so two render tests measured WER on fake-engine audio and
  `just narrate-test` failed (108 of 110) while `pytest` alone passed. `narrate/tests/conftest.py` now clears
  `WHISPER_MODEL`, `NARRATE_STORE`, `NARRATE_LEXICAL_DIR` and `NARRATE_ENGINE_TOKEN` for every test; after the
  fix `just narrate-test` passed 110 of 110 with the model present.

## Review fix round (2026-10-23)

A read-only review of PR #38 at `dfe09d5` found no blockers, 6 major and 7 minor findings. Authority: the
operator-approved narrate plan and R-HOOK-CONVERGENCE-20261004 (R-N11, R-N12, R-N13). Commits `859f876`,
`78e7578`, `f00c436`; nothing was force-pushed.

| # | Finding | Disposition |
| --- | --- | --- |
| 1 | runs could land under `artifacts/runs/` | `Config` and `Renderer.run` refuse `out_in_guitar_runs`; `verify` adds a `location` check |
| 2 | WER not bound to a model | the model file is hashed once per path and must match a `program/models.json` sha256, else WER is `not_measured`; `qa.wer` records backend, `model_sha256`, `model_id` or the loopback endpoint |
| 3 | unmeasured chunks published with no flag | `wer_not_measured` and `sim_not_measured` flags, printed in the CLI summary |
| 4 | `voices add` record and clip checks | record is exactly `Voice.dhall`'s fields (test parses the type); non-mono, non-16-bit, unreadable and empty clips, no or unknown `--allow-engine` are typed refusals |
| 5 | slide id with `/` crashed | `slide` must match `[A-Za-z0-9_-][A-Za-z0-9._-]{0,63}`; a file-name default is made safe |
| 6 | contract shape test tested its own fixture | the matrix and `tests/cli.rs` read a real render's timeline and key sets from `narrate/tests/fixtures`; `test_contract_shape.py` renders that run and asserts the fixtures still hold |
| 7 | empty `inputSha256` silently unpinned | recorded as `input.pinned: false` and flagged `input_unpinned`; the Dhall type is unchanged (the W4 types landed, and the test workspace needs unpinned inputs) |
| 8 | `just` overrode the toml model | explicit `[whisper] model` wins, then `NARRATE_WHISPER_MODEL`, then `WHISPER_MODEL` |
| 9 | loose, inconsistent loudness rule | `audio.loudness_verdict` serves render and evaluate: 0.1 dB peak tolerance, `true_peak_over_ceiling`, `loudnorm_dynamic` |
| 10 | token over cleartext to any host | `engine_transport_insecure` unless https, a loopback host or no token; Hosted and RentedOpen always need https |
| 11 | numerals fail WER | number words become digits on both sides (grammatical runs only; "one two three" stays three words) |
| 12 | evaluate scored raw takes | WER cuts each chunk's `out_start_s..out_end_s` from `narration.wav` and says so in `scored` |
| 13 | lexical docstring, verify crash | docstring corrected; a malformed EDL segment returns a failing receipt |
| open | `dhall` missing from the condense shell | added; the narrate CI job runs `narrate-dhall-check` there |

Gates on the dev host: `just narrate-lint` clean; `just narrate-test` 163 passed; `just narrate-dhall-check` in
`nix develop .#condense` errors 0 and 29 mutations; `test_timeline_contract`, `test_public_tree`,
`test_bazel_graph_s3` 85 ran, OK, 2 skipped; `cargo test --test cli narration` 1 passed; `bazel build --nobuild
//... --lockfile_mode=error` passed; `bazel test //tests:rust_cli_test //narrate:stdlib_test` passed;
`gitleaks dir` no leaks.

Still open: the committed `narrate/examples/narrate.toml` pins the real xoxd-lexical 0.2.0 digests, so it renders
only with that private release; no CI renders it. `ref_audio` per server (W6), script-timed captions, no SIM
scorer and the `narrate-bench` stub (W3) are unchanged.
