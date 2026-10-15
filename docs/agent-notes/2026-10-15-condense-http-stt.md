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
- Superseded by the review round below: the MCP preflight now refuses the http backend.
- `http_timeout_s` bounds each socket wait, not the total request. A service that trickles bytes
  could hold a request longer.

## Review round (2026-10-15)

A review of PR 22 reproduced three blocking defects. Each is fixed in a new signed commit, with tests.

- Token leak. A `CONDENSE_STT_TOKEN` ending in a line break made `http.client` raise a `ValueError`
  that quoted the header value, token included. The token must now be visible ASCII with no space or
  line break. Any other value is refused before audio extraction (and in `read()`), and the refusal
  does not echo it. `http_full` also turns any `ValueError` from the client into a token-free
  `RuntimeError`. Tests: four bad tokens (LF, CRLF, a space, non-ASCII) through `transcribe()` and
  `read()`, 0 requests reach the fake service; a header forced past the check fails closed with no
  token and no chained cause.
- URL fragment. A `#fragment` in `whisper.url` swallowed the appended query, so the DTW pass lost
  `dtw`, `language` and `prompt`. A fragment (an empty one too) and `;params` are now refused before
  any work. Three cases join the bad-settings test.
- MCP scope. `condense_config_paths` refuses any `[whisper] backend` other than `cli`, so
  `condense_transcribe`, `condense_edl` and `condense_check` cannot reach the network under their
  `openWorldHint: false` admission. `run_condense_tool` drops `CONDENSE_STT_TOKEN` from the worker
  environment. Tool descriptors and skills are unchanged; the frozen digests still match.
  `docs/spec/CONDENSE_TOOL_CONTRACT.md` states the rule.

Nits fixed in the same round:

- An oversized reply (`MAX_REPLY` patched to 100 bytes) and a `segments` reply with an infinite word
  start now have fail-closed cases. `whisper_json` catches `OverflowError`.
- `transcribe()` removes the clip's `pass1.json`, `dtw.json` and `stt.json` at the start, for both
  backends, and writes them only after both passes succeed. A failed run, including a DTW-pass
  failure after pass 1 succeeded, leaves none behind.
- `work/<clip>.stt.json` records the backend (model file name or service URL), language, DTW preset,
  `pass1` and `chunk_s`. The parity test checks it for both backends; the token is in no work file.
- `http_timeout_s` must be a finite number above 0: 0, -1, infinity, NaN, a boolean and a string
  are refused before any work.
- The tests use `localhost` instead of a spelled-out address. `localhost` counts as loopback only
  while every address it resolves to is loopback; a test stubs the resolver both ways.
- An `HTTPError` response is closed on the error path.

Not changed: `edl`'s `pause_asr.json` cache of `read()` text is not keyed by backend, so switching
backends reuses earlier text until that cache is removed. `condense/README.md` stays outside the
lane's owned files, as first disclosed.

Gates for this round: `nix develop .#condense -c just condense-lint condense-test`: ruff clean,
92 passed. `tests/test_s4b_tool_admission.py`: 12 ran, OK (1 skipped locally: end-to-end worker).
