# Narrate engine bench: preregistration (2026-10-22)

Authority: operator-approved narrate plan of 2026-10-22, lane W3 (Linear TIN-7085, parent TIN-7084, milestone
N0 Narration v0); R-HOOK-CONVERGENCE-20261004 R-N11 (ownership and live-session checks before touching the GPU
or any process), R-N12 (hooks advisory), R-N13 (this receipt; facts mirrored to Linear).
Research: [`docs/research/2026-10-22-tts-voice-cloning.md`](../research/2026-10-22-tts-voice-cloning.md).

**State: preregistered, not run.** No weights downloaded, no GPU used, no voice recorded. Two gates are open:
**G1** an attended GPU window, **G2** the operator's consent and reference clips. The bench decides which engine
N0 renders with; the decision is due Saturday 2026-10-24.

This file is frozen once the first scored render exists. Changing a bar, an arm, a decoy, a stop rule or the
text after that is a new bench with a new preregistration (`text-v2`, a new dated file).

## Inputs

| Input | Where | Binding |
|---|---|---|
| Bench text | [`narrate/bench/text-v1.md`](../../narrate/bench/text-v1.md), 795 spoken words, six sections s1..s6 (opening, technical fault, dialog, numbers and units, results, closing) | sha256 `f7ff6923899b72ade8da6f84678ca9bff81bc3d8ee61b70bda908b95951a704d` |
| Pinned sources | [`narrate/bench/sources.json`](../../narrate/bench/sources.json), printed by `just narrate-fetch` | sha256 `af4596f3ef9218605e5f7e452e03da721ca88bd26b6e7d73883658d6a96e207d`; per-file sha256 recorded at download in `<dest>/fetch-receipt.json` |
| Consent clip | private voice store, never in Git | sha256 plus consent id in the receipt; script in [`narrate/bench/recording-script.md`](../../narrate/bench/recording-script.md) |
| Reference clip, 25 to 30 s | private voice store, never in Git | clip sha256, verified-transcript sha256, consent id |
| ASR model | `ggerganov-whisper-cpp-ggml-small.en`, already registered in `program/models.json` | existing registry hash |

The bench text is spoken as written: digits, times, currency and units are left for each engine's own text
normaliser, and number-reading errors are counted as a separate diagnostic (narrate's own normaliser is lane W5).

## Pinned sources (looked up read-only on 2026-10-22)

Runtimes (git, cloned by each arm's build step, never by `narrate-fetch`):

| Source | Commit | Ref |
|---|---|---|
| audio.cpp | `47c2756ec72c4e67cad7fb762fd0d5f2798096fd` | main; newest tag v0.9.2 predates `ming3_tts` |
| llama.cpp | `11fe02151f79c41d0d4af7da708755d73b9c0da6` | estate pin, 2026-10-04 (`llama-tts` Qwen3-TTS; no server `/tts`) |
| qwentts.cpp | `5916bf7c79dbb4e66fc059cdc507a79a23a28bb4` | HEAD, no tags |
| mlx-audio | `4510ba631faf5676b2bf4633161756664d154e28` | v0.6.1 (the Ming MLX card requires 0.6.1 or later) |
| Ming-3.0-tts (reference only) | `028c1eace193e7acdb256453da89b6e9207e052b` | HEAD (2026-10-21 long-text fix) |
| VoxCPM (reference, PyTorch fallback) | `19b6bf7590025418821a86dcb817504e0ad7e5df` | 2.0.3 |
| fish-speech (optional rented tier) | `1ff3c3ed2f80d3106a83909dd25b83129c3d816f` | v3.0.0-beta |
| UTMOSv2 | `14a281c6072d6fad2bf31f992ed2e60304400075` | v1.3.0 |

Weights (Hugging Face, revision-pinned; LFS sha256 values are in `sources.json`):

| Source id | Repo @ revision | Converted from | Size |
|---|---|---|---|
| ming3-0.5b-gguf | `audio-cpp/Ming-3.0-TTS-0.5B-GGUF@2eb8d37c` (bf16) | `inclusionAI/Ming-3.0-tts-0.5B@8d66b70a` | 2.79 GiB |
| qwen3-tts-1.7b-base-gguf | `ggml-org/Qwen3-TTS-12Hz-1.7B-Base-GGUF@ca27d74b` (bf16 + mmproj bf16) | `Qwen/Qwen3-TTS-12Hz-1.7B-Base@fd4b2543` | 3.86 GiB |
| qwen3-tts-1.7b-base-qwentts | `Serveurperso/Qwen3-TTS-GGUF@b7ee2e8c` (talker BF16, tokenizer F32) | same | 4.21 GiB |
| voxcpm2-gguf | `audio-cpp/audio.cpp-gguf@ef1ab259` (`VoxCPM2-GGUF/voxcpm2-bf16.gguf` only) | `openbmb/VoxCPM2@32279eff` | 4.44 GiB |
| ming3-0.5b-mlx | `mlx-community/Ming-3.0-tts-0.5B-bf16@283b3c34` | Ming 0.5B | 2.80 GiB |
| qwen3-tts-1.7b-base-mlx | `mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16@a6eb4f68` | Qwen3-TTS Base | 4.23 GiB |
| voxcpm2-mlx | `mlx-community/VoxCPM2-bf16@a7fb80d9` | VoxCPM2 | 4.62 GiB |
| ecapa-voxceleb | `speechbrain/spkrec-ecapa-voxceleb@0f99f2d0` | | 0.08 GiB |
| utmosv2-fold0 | `sarulab-speech/UTMOSv2@506474f2` (fold 0 only) | | 0.76 GiB |
| wavlm-base-plus-sv (optional) | `microsoft/wavlm-base-plus-sv@feb593a6`; licence not stated on the card | | 0.38 GiB |
| drama3-gguf-q3 (optional) | `Jmica/Drama-3-GGUF@17a5b40c` (Q3_K_S backbone) | `fishaudio/drama-3@b2b5ee99` | 18.93 GiB |
| drama3 (optional, rented host only) | `fishaudio/drama-3@b2b5ee99` | | 38.65 GiB |

Default selection is 27.8 GiB (9 Hub sources); with the optional tier, 85.8 GiB. Three repositories were modified
on the lookup day (the MLX Ming build, the audio.cpp GGUF collection, Ming upstream), which is why every pin is
a full revision rather than a branch.

## Arms

All arms clone the same consented reference clip with its verified transcript, synthesise the same chunk list,
and run three seeds (1, 2, 3). Chunking is fixed for every arm: split text-v1 at sentence boundaries, greedily
packed to at most 300 codepoints, never across a section boundary; the chunk list and its sha256 are recorded
before the first render. Engine-internal chunking is disabled where the runtime allows it (`raw_text=true` for
audio.cpp), so every arm sees identical chunks. Temperature and guidance stay at each runtime's documented
default unless listed.

| Arm | Host | Runtime | Weights | Settings |
|---|---|---|---|---|
| A1-gpu Ming-3.0-tts-0.5B | GPU host | audio.cpp `--family ming3_tts --task clon --backend vulkan` | ming3-0.5b-gguf (bf16) | `reference_text` = verified transcript, `language=en`, seed per run |
| A1-mac | Mac host | mlx-audio 0.6.1 `mlx_audio.tts.generate` | ming3-0.5b-mlx | `--ref_audio`, `--ref_text`; note: no CAM++ embedding in the MLX port |
| A2-gpu Qwen3-TTS-1.7B-Base | GPU host | llama.cpp `llama-tts`, Vulkan build, `-ngl 99` | qwen3-tts-1.7b-base-gguf | `--tts-speaker-file` only (this runtime takes no reference transcript) |
| A2-gpu-alt | GPU host | qwentts.cpp, Vulkan | qwen3-tts-1.7b-base-qwentts | ICL cloning with `ref_text` |
| A2-mac | Mac host | mlx-audio 0.6.1 | qwen3-tts-1.7b-base-mlx | `ref_audio` + `ref_text` |
| A3-gpu VoxCPM2 | GPU host | audio.cpp `voxcpm2`, Vulkan | voxcpm2-gguf (bf16) | prompt audio + transcript; `voxcpm2.mem_saver=true` only if the default run exceeds the VRAM bar |
| A3-mac | Mac host | mlx-audio 0.6.1 | voxcpm2-mlx | `ref_audio` + `ref_text` |
| D3-rented Drama 3 (optional) | rented NVIDIA GPU, 48 GB or more | vLLM-Omni or fish-speech v3.0.0-beta | drama3 | only after the operator confirms the licence's revenue threshold and the "Built with Fish Audio" notice; never with confidential text |
| D3-gpu-experimental (optional) | GPU host | audio.cpp `fish_drama3`, CPU expert offload, 16 GB profile | drama3-gguf-q3 | only if window time remains; never counts toward the pick |

The PyTorch ROCm route for VoxCPM2 is not an arm. It may replace A3-gpu only if the audio.cpp Vulkan build fails,
and then only in bf16, with the memory-efficient SDPA backend disabled, from official ROCm wheels, and after a
CPU parity check on one chunk (pytorch#201476).

Arm cost: local arms cost nothing but GPU-window minutes. The rented arm is priced before it is approved: GPU
hourly rate times at most 1 hour, plus egress, recorded in the bench receipt; no hosted API arm runs in this
bench.

## Metrics

- **RTF**: synthesis wall time divided by output audio duration, per chunk and for the whole text, measured
  after the model is loaded; load time is recorded separately.
- **Peak VRAM** (GPU host): `mem_info_vram_used` from the card's sysfs node, sampled at 10 Hz during each arm,
  minus the idle baseline taken just before the arm. ROCm tools are not on the host, so sysfs is the source.
  **Peak memory** (Mac host): the runtime's reported peak memory, else `/usr/bin/time -l` maximum resident size.
- **WER**: whisper.cpp `small.en` round trip of each chunk and of the concatenated render, scored against the
  chunk text with the Whisper English normaliser applied to both sides. A regression gate, not a ranking. The
  rare-word list (Okonkwo, Lindqvist, Marguerite, anemometer, oscilloscope, kilohertz, epoxy, councillor) is
  adjudicated by listening; an ASR miss on a correctly spoken rare word is not a TTS error.
- **Number reading** (diagnostic): each of the 14 expressions text-v1 writes with digits (years, clock times, a
  price, decimals, an ordinal date, a percentage) marked read correctly, read
  wrongly or skipped, by listening.
- **SIM**: ECAPA (speechbrain) cosine similarity between each chunk and the reference clip; report the median.
  **wSIM**: the same embedding over 10 s windows with 5 s hop across the concatenated render; report the minimum
  and the mean, which shows drift over the five-minute text.
- **UTMOS**: UTMOSv2 fold 0, mean over chunks, after loudness matching to -16 LUFS.
- **Failures**: catastrophic chunk (chunk WER over 30%, silence over 2 s inside a chunk, or a chunk longer than
  twice its expected duration at 150 words per minute), crash, out-of-memory, hang.

## Bars

| Metric | Pass bar | Direction | A miss means |
|---|---|---|---|
| Fits | completes text-v1 on its host with no out-of-memory or device reset | must hold | arm is out for that host |
| Peak VRAM (GPU host) | at most 14.5 GiB above idle baseline | lower is better | arm cannot share the card with its own server overhead; out for serving |
| RTF (GPU host) | at most 0.5 | lower is better | too slow for N0 renders inside a window; out unless no arm passes |
| RTF (Mac host) | at most 1.5 | lower is better | Mac arm is development-only, still reported |
| Catastrophic chunks, seed 1 | at most 1 of all chunks | lower is better | arm needs rollback by design; counted against it |
| Catastrophic chunks, best of 3 per chunk | 0 | must hold | arm is out: narrate's best-of-3 policy cannot rescue it |
| Whole-text WER after adjudication, best of 3 | at most 5% | lower is better | intelligibility regression; out |
| Median chunk SIM | at least 0.15 above the preset-voice decoy and at least 0.45 | higher is better | not recognisably the reference voice; out |
| wSIM minimum | at least 0.8 times the arm's median chunk SIM | higher is better | voice drifts over long text; flagged, ranks lower |
| UTMOS | at least 3.0 | higher is better | audibly degraded; out |

**Pick rule.** Among arms that pass every "out" bar on the GPU host, the operator's blind A/B preference decides.
Metrics break a tie or a no-preference result, in this order: catastrophic chunks (seed 1), wSIM minimum, median
SIM, RTF. Without a listening receipt by Saturday, the provisional pick is the passing arm with the highest median
SIM, recorded as "metrics pick, listening pending", which is a separate state from listening acceptance. If no
arm passes, A2 (Qwen3-TTS) is the N0 fallback with its misses written down, and the pick is reopened in N1.

## Decoys

Scorer checks that run in the same scoring pass; each must come out on the expected side of the bar or the
metric is invalid for the pick (it is still reported):

1. **Reference self-match**: the second half of the reference clip scored against the first half. Expected SIM
   well above the SIM bar; proves the embedding sees the speaker at all.
2. **Wrong speaker**: two chunks rendered with a built-in preset voice (Ming `UK_George`, no cloning). Expected
   SIM below the bar; this is the decoy the SIM bar is defined against.
3. **Robot baseline**: the full text rendered by espeak-ng. Expected UTMOS below 3.0 and SIM below the bar,
   with low WER. Proves UTMOS and SIM are not just measuring intelligibility.
4. **Corrupted chunk**: one A2 chunk with its second half replaced by silence, and one played time-reversed.
   Expected: both flagged catastrophic. Proves the failure detector fires.
5. **Shuffled transcript**: one correct chunk scored against the text of a different chunk. Expected WER over
   30%. Proves WER alignment is per chunk and not lenient.

Decoys 1 and 2 need G2; 3 to 5 can be produced and scored before the window.

## Stop rules

- **GPU window**: 30 minutes from Lease acquisition, hard. At minute 25 the running arm is stopped wherever it is.
- **Arm stop**: the first out-of-memory, device reset or 120 s without output progress stops that arm; it is
  not retried in the same window.
- **Bench stop**: any amdgpu reset or ring timeout in the kernel log stops the whole window; the receipt records it.
- **Parity stop**: a PyTorch arm whose CPU parity check fails is dropped, not tuned.
- **Consent stop**: without a consent record matching the reference clip, no cloned render is made. Only decoys
  3 to 5 and a preset-voice smoke test may run.
- **Confidentiality stop**: the bench text is public. No other text is synthesised in this bench, and no text
  marked confidential ever goes to the rented arm.
- **Spend stop**: the rented arm stops at its approved hour; there is no hosted API arm.
- **Freeze**: a change to text, bars, arms, decoys or stop rules after the first scored render ends this bench.

## Held-out exposure

- text-v1 was written fresh for this bench on 2026-10-22 and has not been rendered or scored by any system. It is
  public from this commit, so it is single use: a later bench that must be unseen gets a new text.
- The reference clip is private; only its hashes leave the voice store. No arm trains or fine-tunes on it, and
  Drama 3 outputs may not be used for training under its licence.
- No other held-out set is touched.

## GPU window procedure (attended, at most 30 minutes)

Before the window (no GPU use):

1. Recording (G2): the operator records the consent clip, then the reference clip, per
   `narrate/bench/recording-script.md`; consent record and hashes are created in the private voice store.
2. `just narrate-fetch` (dry run) on the GPU host, review the plan, then `just narrate-fetch --apply --arm A1-gpu
   --arm A2-gpu --arm A3-gpu --arm scoring` into the private weights directory. Check `fetch-receipt.json`: every
   LFS file `matched_declared`.
3. Build audio.cpp, llama.cpp and qwentts.cpp at their pinned commits with the Vulkan backend on an approved
   builder; record each binary's sha256.
4. Generate and record the chunk list; copy the reference clip and verified transcript to the host's private
   store and check their sha256 values.
5. Score decoys 3 to 5 off the GPU.

In the window:

1. **Ownership and live-session check (R-N11).** Read the GPU Lease holder and the model coordinator's state.
   If another claimant holds the card, ask the coordinator to release it through its own release call; never stop
   another owner's process. If it cannot be released, the window does not start.
2. **Acquire the Lease** by compare-and-swap on the GPU lease object with this bench as holder, a duration of at
   most 30 minutes, and the arm list in the annotation. Record the lease version before and after, the holder
   and the start time.
3. Record the idle VRAM baseline from sysfs; start the 10 Hz sampler.
4. Run order (known-good first): A2-gpu (8 min budget), A1-gpu (8 min), A3-gpu (8 min); A2-gpu-alt and
   D3-gpu-experimental only with time left. Per arm: load, one-chunk smoke, seed 1 full text, then seeds 2 and 3
   if the arm's budget allows. One synthesis process at a time.
5. At minute 25 at the latest: stop this bench's own processes, confirm VRAM is back to baseline, then **release
   the Lease** by compare-and-swap and record the release version and time. Restore the prior claimant through
   the coordinator if one was released in step 1.
6. The receipt records the window start, end, lease versions, per-arm runtime and binary hashes, VRAM samples
   summary and any stop rule that fired.

After the window, all scoring (whisper, ECAPA, UTMOSv2) runs off the GPU. Mac arms need no Lease and run at any
time, one process at a time.

## Operator blind A/B listening protocol

Run after scoring, only on arms that passed every "out" bar.

1. **Stimuli.** Three fixed excerpts per arm, taken from seed 1 (never the best seed, to avoid cherry-picking):
   s3 (the dialog), s4 (numbers and units), s6 (closing). Each about 20 to 30 seconds, cut at the same chunk
   boundaries for every arm, loudness-matched to -16 LUFS and peak-limited to -1.5 dBTP.
2. **Blinding.** Each stimulus gets a random id; the id-to-arm key is written to a private file and sealed
   (its sha256 recorded in the receipt) before the operator listens. File names, durations and metadata carry no
   arm information.
3. **Pairs.** For each excerpt, every pair of passing arms, each pair presented once in a random order with a
   random A/B side. The operator answers: A better, B better, or no preference; and may tick "wrong word",
   "not my voice", "robotic", "artefact".
4. **Voice rating.** Separately, every stimulus plus one hidden anchor (an excerpt of the operator's real
   reference clip) and one hidden decoy (the preset voice) is rated 1 to 5 on "sounds like me". The anchor must
   rate at least 4 and the decoy at most 2, or the rating block is discarded and recorded as such.
5. **Listening setup.** Same headphones throughout, one sitting of at most 20 minutes, replay allowed.
6. **Receipt.** The response sheet's sha256, then the unsealed key, then per-arm tallies (wins, losses, ties,
   mean voice rating). This is recorded as its own state, "listening acceptance", separate from the source
   checks, the metric bars and the engine pick.

## Evidence and receipts

- The bench receipt is a new dated note, `docs/agent-notes/2026-10-2x-narrate-bench.md`, keeping measurements,
  inferences and listening claims apart, and citing R-HOOK-CONVERGENCE-20261004. Facts and the pick go to TIN-7085.
- Renders, reference audio, consent evidence, VRAM traces and scoring outputs stay outside Git; the receipt
  carries their sha256 values only.
- Host names, private paths and addresses never appear in the receipt.

## Prep receipt (branch `feat/narrate-bench-prep`, 2026-10-22)

Lane W3 prep only; files are disjoint from the `narrate/` Python package of lane W5 (everything here is under
`narrate/bench/`, `docs/`, `just/narrate-bench.just` and one test).

- `narrate/bench/text-v1.md`, `narrate/bench/recording-script.md`: written fresh for this bench.
- `narrate/bench/sources.json`: pins looked up read-only (Hub API tree listings, `git ls-remote`); nothing downloaded.
- `narrate/bench/fetch.py` and `just narrate-fetch`: the default prints the plan. `--apply` downloads into
  `$NARRATE_WEIGHTS_DIR` (or `--dest`), refuses a destination inside the repository, checks declared size and
  LFS sha256, writes `<source>/SHA256SUMS` plus a dated receipt, and never clones git sources. The apply path
  was exercised only against a local `file://` mirror of synthetic bytes in
  `tests/test_narrate_bench_fetch.py`; it has not downloaded any real weights.
- Bazel: `narrate/bench/BUILD.bazel` (filegroup) is a data dependency of the Python tests; the S3 test
  classification supplement counts the new module.

## Open questions

- Whether audio.cpp's Vulkan build runs `ming3_tts` and `voxcpm2` on gfx1201 at all (U until G1).
- Whether `llama-tts` speaker-file cloning without a transcript is competitive with ICL (the reason A2-gpu-alt
  exists).
- The WavLM speaker-verification licence; it stays optional until checked.
- Whether UTMOSv2 fold 0 alone is the package default (U); if not, the receipt states which folds were used.
