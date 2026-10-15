# Optional HTTP speech-to-text backend for condense transcribe (2026-10-15)

Authority: S4 sprint plan (`docs/spec/sprints/20261015-S4.md`, milestone "Hygiene and peers"); Linear
TIN-6514; R-HOOK-CONVERGENCE-20261004 R-N13. Lane L10-stt, branch `feat/condense-http-stt`.

## Change

- `condense/config.py`: three `[whisper]` defaults. `backend = "cli"` keeps the current whisper-cli
  behaviour. `url = ""` and `http_timeout_s = 3600` apply only to `backend = "http"`.
- `condense/transcribe.py`: `transcribe()` and `read()` dispatch on the backend. The http path POSTs
  each 16 kHz chunk to a loopback URL with the stdlib `urllib`, and returns whisper-cli `-ojf` JSON.
  It also adapts a `segments[].words[]` reply. The pass-1 and DTW files keep their names, and the
  no-DTW check is unchanged. `events.words_from` is unchanged.
- The bearer token comes only from `CONDENSE_STT_TOKEN`. The opener bypasses proxies and refuses
  redirects. The URL must name a loopback host and carry no user info. Errors, timeouts, oversized
  replies and wrong shapes raise. Nothing is retried, and no pass JSON is written after a failure.
- `docs/spec/CONDENSE.md` gains an "Optional HTTP speech-to-text backend" section, and
  `condense/README.md` gains one transcribe bullet.
- `condense/tests/test_transcribe_http.py` (new): 22 cases. They use an in-process loopback fake
  service and FFmpeg-made synthetic media.

No new dependency. The tool contract (`program/tools.json`) and `.agents/skills/condense-transcribe`
are unchanged: no MCP input knob is needed, and both are hash-frozen by `tests/test_s4b_tool_admission.py`.

## Evidence

- Parity holds at one chunk (`chunk_s` 800) and at two chunks (`chunk_s` 10). The http path and a
  stood-in whisper-cli receive the same canned whisper JSON per chunk. `pass1.json`, `dtw.json`,
  `words.json` and `events.json` are byte-identical between them. The words are the 20 synthetic
  words, each once.
- Requests carry `response_format=whisper_full`, the language and the prompt. Only the DTW pass
  carries `dtw=small.en`. `read()` sends neither the prompt nor `dtw`. The Authorization header is
  present only when the variable is set.
- These fail closed: HTTP 500, HTTP 401, a non-JSON reply, a text-only reply, a float offset, a JSON
  array, a 0.5 s timeout against a 2 s reply, a 307 redirect (the target received 0 requests), a
  closed port and all `t_dtw` = -1. The service failures write neither `pass1.json` nor `dtw.json`. The
  no-DTW case writes no `dtw.json`. The token string never appears in an error, stdout or stderr.
- These are refused before audio extraction: an unknown backend, an empty URL, a non-loopback
  hostname, a non-loopback IP from the documentation range, a non-http scheme, user info in the URL
  and `whisper_args` with the http backend.

## Gates

- `nix develop .#condense -c just condense-lint condense-test`: ruff clean, 75 passed (53 existing,
  22 new).
- `just check` (local): 2013 tests ran. The first run failed `test_condense_public_surface` because
  the tests spelled out a loopback address literal. The tests now build that address at run time, and
  the rerun passes. The other 32 failures and errors are local environment issues: an offline pnpm
  mirror that lacks `pnpm@11.25.0` (web stack and web-runs builds), and no supported installed font
  (marked-video previews). This change touches none of those files.
- `tests/test_s4b_tool_admission.py`: 11 ran, OK (1 skipped locally: end-to-end worker). The frozen
  digests are unchanged.
- No Rust change, so `just test-rust` was not run. Hosted CI (offline, condense, web, bazel) is
  recorded on the PR.

## Findings

- The tubebrain-stt request and reply shapes are a contract that this repository states. No real
  service was contacted, so whether tubebrain-stt serves it is unverified.
- Treating word starts from a `segments/words` reply as DTW times is an inference. No measurement
  compares them with whisper.cpp DTW onsets.
- The MCP tool `condense_transcribe` is frozen with `openWorldHint: false`, and the worker requires the
  registered model. A talk.toml with `backend = "http"` run through MCP would still need the model,
  and it would contact the loopback URL. A later admission revision should either refuse the http
  backend under MCP or declare it.
- `http_timeout_s` bounds each socket wait, not the total request. A service that trickles bytes
  could hold a request longer.
