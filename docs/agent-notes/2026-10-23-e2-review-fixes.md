# Narrate qwentts.cpp engine: review fix round (2026-10-23, lane E2)

Authority: the operator-approved narrate plan and today's instruction to get the voice work working and landed;
Linear TIN-7088 (parent TIN-7084); the host-safety rule after the CPU-host incident (TIN-7085). This note answers
the adversarial review of PR #39 (no blockers, 4 major, 6 minor). R-HOOK-CONVERGENCE-20261004: R-N11 (no process
was started on any host except the test suites and one compiler syntax check, each in a bounded user scope; no
other session's process was touched), R-N12 (hooks advisory; the huskycat advisories on commit were noted, none
denied), R-N13 (this receipt; facts mirrored to TIN-7088).

## Findings and what changed

| # | Finding | Disposition |
|---|---|---|
| 1 | Major. Registered clones stayed on the server; any local client or page could list, use or replace them; the client trusted the listing | Fixed. A render opens one voice session (`engine.session`). Names are `narrate-<voice>-<16 hex>-<16 hex nonce>`; the session deletes every name it registered when the render ends, on failure too. The client never reads `GET /v1/audio/voices`. A 400 on a later take registers again and asks once more. `qwentts-loopback.patch` removes `Access-Control-Allow-Origin: *` and the OPTIONS handler, and refuses before routing any request with an `Origin` header or a `Host` header that does not name the loopback interface. |
| 2 | Major. The host gate was an environment variable | Fixed in part. Build and serve need the private allow file `~/.config/narrate/tts-host`, owned by the user, writable by no one else, not a symlink, holding this host's machine id. `NARRATE_TTS_HOST_ALLOWED` is gone. `serve` refuses the `CPU` device. **Not adopted: refusing hosts with control-plane or etcd markers.** The GPU host carries the same cluster role as the CPU host, so that check would refuse the one approved synthesis host. The allow file is the distinguishing control. |
| 3 | Major. The build ran unbounded on any host, and `serve` built inside the window | Fixed. `build` passes the same host gate and runs both cmake steps through `bounded.sh` (8G, `NARRATE_QWENTTS_BUILD_MEMORY_MAX`). `serve` never builds; it refuses a missing or stale build. |
| 4 | Major. "One at a time" was not enforced; pressure was read once | Fixed. `bounded.sh` takes a per-user `flock`. A second step waits and exits 75 after `NARRATE_LOCK_WAIT_S` (default 3600 s); without `flock` it says so. The spec now says pressure is read before the start only and the scope's ceiling bounds the run. Servers use `--no-lock`. |
| 5 | Minor. An inherited `NARRATE_BOUNDED=1` dropped every bound | Fixed. The flag is gone. A call is nested only when `NARRATE_BOUNDED_PID` is its own pid or an ancestor's. A leaked value (tested: `NARRATE_BOUNDED=1`, pid 1, a pid that is not an ancestor) gets the full scope, lock and wait. The scope is named `narrate-bounded-<pid>`. |
| 6 | Minor. The weights check trusted the receipt | Fixed. `serve` streams sha256 over both GGUF files at nice 19 and checks them against the pin and the receipt. |
| 7 | Minor. The binary was trusted from a mutable build directory | Fixed. The default tree is `~/narrate-work/qwentts`; it must be the user's own with mode 0700. Git runs with `core.hooksPath=/dev/null` and `protocol.file.allow=never`. The origin URL and HEAD are held to the pin. The stamp records `tts-server`'s sha256, and `serve` checks it. |
| 8 | Minor. Test gaps; no shellcheck in CI | Fixed. New tests cover the end-to-end serve argv (loopback host, 14G scope, thread export, no lock), the allow-file refusals, the CPU refusal, corrupt same-size weights, a receipt that disagrees with the pin, a missing, stale or replaced build, the current-build path, the 0700 rule, the loopback patch content, the lock, nesting and the leaked marker. `narrate-lint` runs shellcheck; shellcheck is in the condense shell. |
| 9 | Minor. Private and infrastructure detail in tracked files | Fixed in history. The voice registry ids and the reference clip's absolute F0 are replaced by "the operator's reading voice" and relative F0 figures (9.4 % and 15.3 % below the reference). "An etcd voter" became "a cluster control-plane member". The edits were folded into the commits that introduced the text, so no landed commit carries them. |
| 10 | Minor. A commit subject still said "CPU engine" | Fixed. It was reworded to `build(narrate): serve the pinned qwentts.cpp engine on loopback`. Every commit on the branch is re-signed. |

## Gates (measured on the CPU host, each in a `MemoryMax=6G` user scope at nice 19, `ionice -c3`)

- `memory full avg10` was between 0.00 and 0.13 before each run.
- `just narrate-lint` (ruff, ruff format, shellcheck 0.11.0): passes.
- `just narrate-test`: 217 passed (190 before this round).
- `just narrate-dhall-check`: ok, with 29 self-test mutations.
- `git apply --check` of both local patches on a clean checkout at the pin: both apply.
- `c++ -std=c++17 -fsyntax-only` of `tools/tts-server.cpp` with the loopback patch applied: exit 0. This is a syntax
  check of one translation unit, not a build or a run.

## Not done, by rule or out of reach

- No TTS server, model, build or Vulkan run on the CPU host.
- The patched server has not been built or run anywhere. The Origin and Host refusals are checked by the syntax
  check and the patch-content test only.
- The allow file does not exist yet on the GPU host or the Mac build host. Whoever runs the window or the Mac
  checks must create it there (`narrate/README.md` gives the one-line command).

## Inferences and open problems

1. **Inference.** Registering once per render costs one speaker encode per voice per render: about 10 s on the
   CPU host for a 29.9 s clip, measured before the retarget. On the GPU host it is not measured.
2. **Residual.** Any local process on the serving host can still reach the loopback port and, while a render
   runs, list the nonce name. The nonce and the deletion bound the exposure to that render. They do not remove it.
3. **Not solved.** On macOS and in containers, `bounded.sh` has no memory ceiling, and without `flock` no
   serialisation. The Mac host's own caps still apply.
4. **Unchanged from the first push.** The Vulkan and Metal builds have not run, SIM is not measured, nobody has
   listened to a render, and timing fit is atempo only for this runtime.
