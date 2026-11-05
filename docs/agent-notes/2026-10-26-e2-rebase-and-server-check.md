# E2 CPU engine PR: rebase and server check (2026-10-26)

Linear: TIN-7088 (parent TIN-7084). Ruling: R-HOOK-CONVERGENCE-20261004 R-N13.

## Rebase

The branch was rebased onto main `4df004f`, then onto `e88abfe` (range and amount speech, TIN-7087). The merge
commit of PR #46 was dropped and its two commits were replayed in line. Conflicts were resolved by keeping both
sides:

| File | Resolution |
| --- | --- |
| `narrate/qa.py` | the SIM sentence from main, then the whisper thread ceiling from this branch |
| `narrate/README.md` | the `bounded.sh` recipe commands with main's `--reference-voice` note, both module rows, and main's `amounts.py` row above this branch's `engine.py` row |
| `flake.nix` | main already lists shellcheck; only its comment changes |
| `just/narrate.just` | `narrate-lint` runs shellcheck on `bench/run-bench.sh`, `bounded.sh` and `serve/qwentts.sh` |

## The adapter against the pinned server

The client in `narrate/engine.py` was read against qwentts.cpp `5916bf7c79dbb4e66fc059cdc507a79a23a28bb4`.

| Behaviour | Pinned source | Client |
| --- | --- | --- |
| `POST /v1/audio/voices` takes `name`, optional `ref_text`, and `wav_b64` or `spk_b64` with `rvq_b64` | `src/tts-server.h:446` | sends `name`, `ref_text`, `wav_b64` |
| names are lowercased everywhere | `src/tts-server.h:141` | builds lowercase names |
| registration reply is `{"name":…,"status":"registered"}` | `src/tts-server.h:512` | checks both fields |
| the WAV is decoded and resampled to 24 kHz mono on the server (PCM16, PCM24, float32) | `tools/tts-server.cpp:164` | sends the stored clip unchanged |
| an unknown voice on a base model is status -1, HTTP 400 | `tools/tts-server.cpp:277`, `src/tts-server.h:270` | registers again once, then fails |
| a failed generation is HTTP 502 | `src/tts-server.h:270` | `engine_http`, no retry |
| `seed` must be an integer; `speed` is parsed and ignored | `src/tts-server.h:244` | sends an integer seed and no speed |
| a wav reply is 24 kHz mono 16-bit RIFF | `src/tts-server.h:306` | checks RIFF/WAVE; the engine record says 24000 Hz |
| `DELETE /v1/audio/voices/{name}` answers 404 for an absent name | `src/tts-server.h:525` | treats 404 as already gone |
| request bodies are capped at 32 MiB | `src/tts-server.h:595` | a 30 s 24-bit 48 kHz clip is about 5.8 MiB in base64 |

No request or response shape differed. The test fake (`narrate/tests/test_qwentts.py`) now checks what the
server checks: the registration payload rule, a decodable WAV, a non-empty `input`, an integer `seed` and the
response format. It answers 502 for a failed generation. Two tests cover the 502 path and an undecodable
reference. The fixture reference is now a real 16-bit WAV.

A tts-server built without `qwentts-loopback.patch` keeps the upstream permissive CORS. The client does not depend
on the patch. On such a build, loopback binding and a short-lived tunnel are the only guards.

## Validation

`just narrate-lint` and `just narrate-test` ran in the condense shell inside a user scope with MemoryMax=6G,
MemorySwapMax=0, nice 19 and idle I/O.
