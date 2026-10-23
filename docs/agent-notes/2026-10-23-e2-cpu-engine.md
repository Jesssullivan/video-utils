# Narrate CPU engine: qwentts.cpp on the CPU host (2026-10-23, lane E2)

Authority: the operator-approved narrate plan, today's instruction to get the voice work working and landed;
Linear TIN-7088 (narrate W6a interim serving, parent TIN-7084). R-HOOK-CONVERGENCE-20261004: R-N11 (the server
is this lane's own process on loopback; no other session's process was touched), R-N12 (hooks advisory),
R-N13 (this receipt; facts mirrored to TIN-7088).

**State:** the CPU engine serves, `just narrate-render` renders through it end to end, and every render
verified. It works but is slow on this host: synthesis RTF is 15 to 23 under the shared load measured below.
The server is left **stopped**; E5 starts it. Reference clips, chunk WAVs, transcripts of the operator's voice,
weights and run directories are private and outside git; this note carries digests and numbers only.

## What runs

| Part | Value |
|---|---|
| Runtime | qwentts.cpp `5916bf7c79dbb4e66fc059cdc507a79a23a28bb4` (the `sources.json` pin), CPU only, `-DGGML_NATIVE=ON` (AVX2, FMA, F16C; no AVX-512 on this host), no BLAS, built in `$TMPDIR` by `narrate/serve/qwentts-cpu.sh build` |
| Local patch | `narrate/serve/qwentts-cpu-threads.patch`: `QWENTTS_CPU_THREADS` overrides the GGML thread count, which upstream sets to half the logical CPUs (16 here) with no flag or environment override. Process CPU affinity does not lower it (`std::thread::hardware_concurrency` returned 32 under `taskset -c 0-15`, measured) |
| Weights | `Serveurperso/Qwen3-TTS-GGUF@b7ee2e8c`: `qwen-talker-1.7b-base-BF16.gguf` (sha256 `7f456711…`), `qwen-tokenizer-12hz-F32.gguf` (`b16b9555…`), fetched by `just narrate-fetch --only qwen3-tts-1.7b-base-qwentts --apply`; 3 files, each matched its pinned size and hash |
| Server | `tts-server --device CPU --host 127.0.0.1 --lang English`, 8 GGML threads, pinned to 8 cores of one NUMA node, `max_batch` 1 |
| Recipe | `just narrate-serve-cpu` (and `narrate-build-cpu`); paths and knobs come from `NARRATE_WEIGHTS_DIR`, `NARRATE_QWENTTS_BUILD`, `NARRATE_QWENTTS_THREADS` (1 to 8, refused above), `NARRATE_QWENTTS_CPUS`, `NARRATE_QWENTTS_PORT`, `NARRATE_QWENTTS_LANG` |

## The real API, and the adapter

Read from the pinned source (`tools/tts-server.cpp`, `src/tts-server.h`) and confirmed against the running
server:

- `POST /v1/audio/speech` takes `{input, voice, language, instructions, response_format: pcm|wav, speed, seed,
  sampling overrides}`. It does not read `ref_audio` or `ref_text`. With the Base model, a voice name that is not
  registered is refused: HTTP 400 `unknown voice '<name>'` (measured).
- `speed` is parsed and ignored ("no time stretch in the ABI").
- Cloning goes through a registry: `POST /v1/audio/voices {name, ref_text, wav_b64}` extracts the speaker
  embedding and the reference codes server side (any WAV rate, resampled to 24 kHz); a registered voice with a
  `ref_text` synthesises in ICL mode. The registry lives in memory and is lost on restart. Names are lowercased.

So narrate's generic request does not work here, and `engine.py` now maps a `QwenTtsCpp` engine (the backend
already in `Engine.dhall`) onto the registry: register the clip and verified transcript under
`narrate-<voice id>-<16 hex of sha256(sha256(clip) + transcript)>`, check `GET /v1/audio/voices` before each
chunk and register again when the name is missing, then speak by name with the seed and no ref fields. A changed
clip or transcript gets a new name, so stale latents are never reused. Each take records
`variant: qwentts_registered_voice`, `ref_audio_used`, `ref_text_used`, `conditioning` (`icl`, `x_vector` or
`none`), `registered_now` and `speed_honoured: false`; `render.py` skips the speed re-synthesis for an engine
that ignores speed and fits with atempo alone. No shim process is needed. Ten tests in
`narrate/tests/test_qwentts.py` run against a loopback fake of the pinned server's routes, validation and error
envelope, including restart, refusal and the render fit.

## Measurements

Host: the CPU host, two 8-core AVX2 sockets (32 logical CPUs), no usable GPU. The host was shared with other
sessions' compile and analysis jobs throughout: 1-minute load average 52 to 89 at the sampled points, which
inflates every time below. These numbers bound what E5 will see on a busy day; an idle-host figure is not
measured.

Render jobs (private, outside git): Markdown input, `chunkMaxCodepoints` 300, seed 1, `maxTakes` 1 (no retakes,
so every per-chunk WER is the first take's), WER gate 0.1, whisper.cpp small.en (registered) with 4 threads,
empty pronunciation table, xoxd-lexical 0.3.0 dist pinned by digest. SIM is `not_measured` in narrate (no
speaker-verification model registered), so voice continuity uses a proxy, below.

Smoke text `narrate/bench/smoke-v1.md` (61 words, sha256 `3c6af2bd…`):

| Voice | Chunks | Audio | Synthesis wall (server) | RTF | Render wall | Chunk WER | Loudness | Flags |
|---|---|---|---|---|---|---|---|---|
| the operator's reading voice (29.9 s reference) | 2 | 23.1 s | 396.6 s | 17.2 (14.7, 23.5) | 530 s | 0.00, 0.00 | -15.9 LUFS | `sim_not_measured` |

Per-stage (server `[Perf]`, smoke chunk 1 of the operator's reading voice): prompt prefill 19.5 s for a 383-frame context
(373 of them the reference codes), talker 429 ms per frame, code predictor 449 ms per frame, codec decode 41.3 s,
total 242.6 s for 207 frames (16.6 s). An earlier single-sentence probe on a less loaded moment ran the talker
at 221 ms per frame and the code predictor at 258 ms per frame (RTF 21.0 for 2.7 s, dominated by the fixed
20 s prefill and 20 s codec decode).

Other measured facts: voice registration of the 29.9 s clip took 10.4 s; server resident set after load 8.1 GB,
peak (VmHWM) 8.15 GB after the smoke render; build 72 s wall with 8 jobs.

Voice continuity proxy (not SIM): per-chunk median F0 by autocorrelation and the cosine of each chunk's mean
log-mel spectrum against the reference clip and the first chunk. reading-voice smoke: chunk median F0 9.4 % and 15.3 % below
the reference clip's; log-mel cosine to the reference 0.985 and 0.984, to chunk 1 0.995. The proxy is
coarse; it flags gross drift only, and says nothing about whether the voice sounds like the operator.

text-v1 (795 words) and the operator's presenter-voice runs: in progress at the time of the first push; this section is
updated in the same PR.

## Inferences and unverified claims

- Inference: the per-chunk fixed cost (about 20 to 31 s prefill of the reference context, 20 to 41 s codec
  decode) makes many short chunks expensive; larger chunks amortise it.
- Inference, untested: a Q8_0 talker (`quantize.sh` in the runtime) would roughly halve the talker's memory
  traffic; it is a derived, unpinned file and was not built.
- Unverified listening: nobody has listened to these renders. WER 0 says the words are intelligible to whisper,
  not that the voice is the operator's or that prosody is acceptable.

## Open problems

1. `Engine.dhall`'s `Profile` has no CPU entry. The private CPU engine record uses `GpuDirect`, the profile its
   `QwenTtsCpp` backend fits, so its manifests say `GpuDirect`. A `CpuLocal` profile needs the W4 type, the policy
   port and the spec table.
2. Speed is not a knob on this runtime; timing fit is atempo only (within `fitMaxStretch`).
3. RTF 15 to 23 under load: the CPU engine suits overnight or short renders, not interactive iteration.
4. SIM is not measured in narrate; the continuity numbers here are a proxy.
