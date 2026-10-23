# Narrate qwentts.cpp engine and host placement (2026-10-23, lane E2)

Authority: the operator-approved narrate plan, today's instruction to get the voice work working and landed;
Linear TIN-7088 (narrate W6a interim serving, parent TIN-7084); the host-safety rule after the CPU-host incident
(TIN-7085). R-HOOK-CONVERGENCE-20261004: R-N11 (only this lane's own server process was ever started, and it is
stopped; no other session's process was touched), R-N12 (hooks advisory), R-N13 (this receipt; facts mirrored to
TIN-7088).

**State.** The lane began as a CPU engine on the CPU host. Root stopped it mid-run when narration work drove that
host, a cluster control-plane member, to NotReady at about 17:14Z, and retargeted it. This PR now delivers:

- the generic qwentts.cpp engine support, which is host-agnostic;
- the voice-registry clone adapter;
- the host placement rule, both in the spec and in code.

No TTS server runs on the CPU host, and none was started after the retarget. The private start script there is
retired: it now refuses and exits 2. Reference clips, chunk WAVs, transcripts of the operator's voice, weights and
run directories stay private and outside git. This note carries digests and numbers only.

## What changed after the retarget

| Part | Value |
|---|---|
| Serve script | `narrate/serve/qwentts.sh` (was `qwentts-cpu.sh`):<br>• `NARRATE_QWENTTS_DEVICE` is required: `Vulkan0`, `MTL0` or `CPU`. The cmake backend and the build directory follow it.<br>• `serve` refuses unless `NARRATE_TTS_HOST_ALLOWED=1`. Only an allowed host's private start script sets that.<br>• The server runs through `narrate/bounded.sh` with a 14G ceiling.<br>• Thread and job knobs: 1 to 8, default 4.<br>• The file digest uses python, so the script also runs on macOS. |
| Recipes | `just narrate-serve-qwentts` and `just narrate-build-qwentts` replace `narrate-serve-cpu` and `narrate-build-cpu`. |
| Local patch | `narrate/serve/qwentts-threads.patch` (renamed; content unchanged). `QWENTTS_CPU_THREADS` sets the GGML CPU thread count. Upstream fixes it at half the logical CPUs and offers no override. `taskset` does not lower it: `hardware_concurrency` still returned 32 under `taskset -c 0-15` (measured before the retarget). |
| Bounded steps | `narrate/bounded.sh`:<br>1. Waits while `/proc/pressure/memory` `full avg10` is above 10 (exit 75 after `NARRATE_PSI_WAIT_S`, default 600 s).<br>2. Runs the step at nice 19 with `ionice -c3`.<br>3. Uses `systemd-run --user --scope --collect -p MemoryMax=6G` when a user systemd answers. Otherwise it says so and runs without a ceiling.<br>4. Sets `NARRATE_BOUNDED=1`, so a nested call does not open a sibling scope.<br>`just narrate-render` and `just narrate-eval` run through it. |
| Whisper | `qa.Whisper` caps whisper at 4 threads, whatever `narrate.toml` asks. |
| Docs | "Host placement and memory" and "qwentts.cpp engine" sections in `docs/spec/NARRATE.md`; matching sections in `narrate/README.md`. |
| Tests | `narrate/tests/test_host_placement.py`, 17 tests with fake `systemd-run` and `systemctl`:<br>• the scope argv;<br>• the fallback without systemd;<br>• the nested call;<br>• the pressure hold (exit 75, command not run);<br>• the serve refusals (host opt-in, device, weights, thread and job caps);<br>• that the recipes are bounded;<br>• the whisper thread cap. |

## The real API and the adapter (unchanged from the first push)

The API was read from the pinned source (`tools/tts-server.cpp`, `src/tts-server.h`) at `5916bf7c` and confirmed
against the running server before the retarget.

**Speech route.** `POST /v1/audio/speech` takes `{input, voice, language, instructions, response_format, speed,
seed, sampling overrides}`.
- It reads neither `ref_audio` nor `ref_text`.
- An unregistered voice name gets HTTP 400 `unknown voice '<name>'` (measured).
- `speed` is parsed and ignored.

**Cloning.** Cloning goes through `POST /v1/audio/voices {name, ref_text, wav_b64}`.
- The registry lives in memory and is lost on restart.
- Names are lowercased.
- A voice registered with a `ref_text` synthesises in ICL mode.

**What `engine.py` does for a `QwenTtsCpp` engine:**
1. Registers the reference as `narrate-<voice id>-<16 hex of sha256(sha256(clip) + transcript)>`.
2. Before each chunk, checks `GET /v1/audio/voices` and registers again when the name is missing.
3. Speaks by that name with the seed, with no ref fields and no speed.
4. Records `variant: qwentts_registered_voice`, `conditioning` (`icl`, `x_vector` or `none`), `registered_now` and
   `speed_honoured: false`.

`render.py` skips the speed re-synthesis for an engine that ignores speed, and fits timing with atempo alone. No
shim process is needed.

## Measurements (taken on the CPU host before the retarget; historical)

These runs are why the rule exists. They are kept as measured facts, not as a recommendation. Setup:
- qwentts.cpp `5916bf7c`, built CPU-only (`-DGGML_NATIVE=ON`: AVX2, FMA, F16C), no BLAS.
- 8 GGML threads, pinned to 8 cores of one NUMA node.
- Weights: `Serveurperso/Qwen3-TTS-GGUF@b7ee2e8c`, fetched by `just narrate-fetch --only
  qwen3-tts-1.7b-base-qwentts --apply`, 3 files, each matching its pinned size and sha256:
  - talker BF16 `7f456711…`;
  - tokenizer F32 `b16b9555…`.

The host was shared with other sessions' jobs: the 1-minute load average was 52 to 89 at the sampled points.

| Measured | Value |
|---|---|
| Smoke render, `narrate/bench/smoke-v1.md` (61 words), the operator's reading voice | 2 chunks, 23.1 s of audio |
| Smoke synthesis wall time | 396.6 s: RTF 17.2 overall, 14.7 and 23.5 per chunk |
| Smoke render wall time | 530 s, WER 0.00 on both chunks, -15.9 LUFS, flag `sim_not_measured` |
| Per stage, chunk 1 | prefill 19.5 s (383-frame context); talker 429 ms per frame; code predictor 449 ms per frame; codec decode 41.3 s |
| Voice registration of a 29.9 s clip | 10.4 s |
| Server process (GNU time) | about 16:55Z to 17:44:48Z (49 min 52 s wall); max RSS 8,148,592 kB; 111,483 major page faults; 68,075,848 file-system input blocks; 1877 s user, 270 s system |
| Voice continuity proxy, not SIM | chunk median F0 9.4 % and 15.3 % below the reference clip's; log-mel cosine 0.985 and 0.984 to the reference, 0.995 between the chunks |

**Not measured.** text-v1 and the operator's presenter-voice runs never finished. Root stopped the presenter smoke render
with SIGTERM before its first chunk returned, and its incomplete private staging directory was deleted.
Also not measured: an idle-host RTF, any GPU-host or Mac figure, and the build of the Vulkan or Metal backend
(the build path for those devices has not run).

**Not run after the retarget, by rule.** No build, server or whisper run on the CPU host. The gates below are
source checks only.

## Inferences and unverified claims

- **Inference about the incident.** This lane's server was resident through the incident window, with an 8.1 GB
  RSS and heavy paging (the major faults and input blocks above). It most likely added to the memory pressure
  that drove the host NotReady. Its share is not measured, against the other narration lanes running at the
  same time.
- **Inference about chunk size.** The fixed cost per chunk (prefill of the reference context plus codec decode,
  20 to 41 s each on the CPU host) favours larger chunks on any device.
- **Unverified listening.** Nobody has listened to the smoke render. WER 0 shows that whisper can make out the
  words. It does not show that the voice is the operator's, or that the prosody is acceptable.

## Open problems

1. The Vulkan (`Vulkan0`) and Metal (`MTL0`) builds of this script have not run. The GPU-host inference lane builds
   qwentts.cpp under J79(a). `narrate-build-qwentts` must be proved there, or its build replaced by theirs, before
   E5 uses `narrate-serve-qwentts` in the window.
2. A narrate engine record for qwentts.cpp fits only `GpuDirect`/`GpuSwitch`. `MacMlx` admits `MlxAudio` alone, so
   qwentts.cpp on the Mac build host serves development checks, not a narrate record.
3. Speed is not a knob on this runtime. Timing fit is atempo only, within `fitMaxStretch`.
4. SIM is not measured in narrate. The continuity numbers above are a proxy.
5. On hosts without a user systemd, `bounded.sh` runs without a memory ceiling (macOS, containers). The Mac host's
   own caps (cache in `~/narrate-work`, at most 20 GB, at least 15 GB free, hold markers, one loopback process)
   still apply there.
