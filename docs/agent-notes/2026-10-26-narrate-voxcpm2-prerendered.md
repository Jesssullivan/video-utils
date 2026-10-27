# Narrate VoxCPM2 engine: two-phase rendering through an audio.cpp batch (2026-10-26)

Authority: the operator picked VoxCPM2 as the N0 narration engine after the blind A/B of 2026-10-26 (Linear
TIN-7085 comment 6767db24). Linear TIN-7088 (narrate interim serving, parent TIN-7084). R-HOOK-CONVERGENCE-20261004:
R-N11 (no process of another session was touched; no GPU-host write, no lease), R-N12 (hooks advisory), R-N13 (this
receipt).

**State.** Source checks only. No real VoxCPM2 render ran for this change, and no TTS model ran on the CPU host.
Every test uses a fake `audiocpp_cli`. A real batch, its WER and listening acceptance are separate, later states.

## Why two phases

audio.cpp's `audiocpp_cli` at `47c2756e` has no server. One process loads the model (about 30 s in the bench),
renders every request of a `--request-sequence` file and writes one WAV per request id at 48 kHz. narrate's render
asks for a take per chunk, so it cannot drive that process. The new backend `AudioCppBatch` splits a render:

| Phase | Where | Command |
| --- | --- | --- |
| A | CPU host | `narrate plan CONFIG --out DIR [--takes N]`: the render's text pipeline, then one request per chunk and seed, one requests file per voice |
| B | GPU host, leased window | `narrate/serve/audiocpp_batch.py run DIR --requests requests/VOICE.json ...`: one model load per voice; a receipt with every output's sha256 |
| C | CPU host | `narrate render CONFIG --prerendered DIR`: QA, best of `maxTakes` over the prerendered seeds, fit, loudness, captions, EDL, manifest, verify |

Whisper and the fit run after the lease, so the window holds the GPU for synthesis alone.

## What changed

| Part | Value |
| --- | --- |
| Types | `AudioCppBatch` in `Engine.dhall`'s `Backend`; only `GpuDirect` admits it. Four new assertions in `policy-test.dhall`; the Python ports in `policy.py` and `dhall/check.py`; one more `--self-test` mutation (a batch engine behind `GpuSwitch`, 30 mutations in all). |
| `narrate/prerender.py` | Request ids (32 hex digits of the sha256 of the request's canonical JSON without its id), the plan writer, the clone modes (`ultimate`, `reference`), VoxCPM2's encoder fit (5 to 14.88 s) and the `Pool` that binds each take to its receipt, requests file and the engine's pinned files. |
| `narrate/render.py` | `plan()`; `Renderer(prerendered=...)`; a chunk without a first take is refused before any audio; the fit skips the speed retry for a batch; `engine.synthesis` and `prerendered_test_mode` in the manifest. |
| `narrate/qa.py` | `best_of` stops at the first seed the batch lacks and records `missing_seeds`; the chunk still fails `qa_failed` when no take passed. |
| `narrate/engine.py`, `registry.py` | `synthesize` refuses an `AudioCppBatch` record (`engine_out_of_process`); `probe` and `reach` say it runs out of process. |
| CLI and recipes | `python -m narrate plan`, `render --prerendered DIR`; `just narrate-plan CONFIG DIR`. |
| `narrate/serve/audiocpp_batch.py` | Standard library, Python 3.9: request id and reference digest checks, binary and weights pins, one process group, deadline and signal stops, receipt. `--only-missing` finishes a stopped batch. |
| Docs | "Out-of-process batch engines" in `docs/spec/NARRATE.md`; "The VoxCPM2 engine" in `narrate/README.md`. |
| Tests | `narrate/tests/test_prerender.py` (23 tests) with `narrate/tests/fake_audiocpp.py`: end to end; best of the prerendered seeds; `qa_failed` with `missing_seeds`; the refusals; a changed script; six tampered bindings; id parity between the runner and narrate; reference mode; the encoder limit; the runner's pin and reference refusals; a failed batch finished by `--only-missing`; a deadline stop; the CLI; policy. |

## Gates

| Gate | Result |
| --- | --- |
| `just narrate-lint` | pass |
| `just narrate-test` | pass: 681 passed, 1 skipped |
| `just narrate-dhall-check` | pass |

## Review fix round (2026-10-26)

Direction: the TIN-7088 fix round on PR #53 (R-HOOK-CONVERGENCE-20261004 R-N13).

| Finding | Change |
| --- | --- |
| A stopped batch could keep a half-written take | The pin prints `[TIMING] request.<id>.wall_ms` before it writes a WAV. Only `audio_out=<path>` or `metrics[<id>]` now marks a take finished. A WAV counts only when its RIFF and chunk sizes account for every byte (`wav_complete`, in the runner and in `Pool`). The fake prints in the pin's order and can stop mid-write. |
| Best of N kept the first passing take | A render from a batch scores every take it holds and keeps the best (`best_of(..., exhaustive=True)`). |
| `Pool` checked late and read twice | `prepare_batch` checks every take the render may read before any audio. `Pool.take` reads once and hashes those bytes. |
| `best_of` stopped at the first missing seed | A missing seed is skipped and listed in `missing_seeds`. A chunk needs any take, not the first. |
| No stall stop | `--stall-s` (default 120) stops a runtime whose log and output stop growing. |
| Nits | The receipt drops `model_load_ms` (the pin prints none). `check_engine` refuses only `ref_audio = "omit"`. The weights pin must be the `files` entry named like the receipt's `model_file`, so swapped pins are refused. |

Tests: `test_prerender.py` has 31 tests. The new ones cover a take stopped mid-write, a stall, WAV completeness, scoring every take, a missing middle seed, swapped pins, a truncated WAV with a matching receipt and a deleted WAV.

| Gate | Result |
| --- | --- |
| `just narrate-lint` | pass |
| `just narrate-test` | pass: 702 passed, 1 skipped (after the rebase on main `c8d388a3`); `just narrate-dhall-check` pass |

## Open

- The MCP tools do not expose `plan` or `--prerendered`. W7 owns their admission.
- The first real batch runs in a leased GPU window from a private kit, outside git. Its receipt goes to TIN-7088.
