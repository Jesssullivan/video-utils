# Voice-cloning TTS for narration: models, licences and local feasibility (2026-10-22)

Public summary of a read-only research workflow run on 2026-10-22 (18 survey and verification agents; every
model claim below survived an adversarial check against primary sources the same day). It feeds the narrate
engine bench: [`docs/agent-notes/2026-10-22-narrate-bench-plan.md`](../agent-notes/2026-10-22-narrate-bench-plan.md).

Labels: **M** measured or read from a primary source on 2026-10-22; **V** vendor-reported (model cards,
abstracts); **I** inference; **U** unknown. Leaderboard figures are third-party crowd preference (Artificial
Analysis, "AA") and move week to week; each is quoted with the date it was read.

Hardware vocabulary used below:

- **The GPU host**: one AMD RX 9070 XT, gfx1201 (RDNA4), 17,095,983,104 B (15.92 GiB) VRAM, a large amount
  of system RAM, a CPU without AVX-512. ROCm is not installed on the host; it exists only inside container
  images (ROCm 7.2.4). The GPU is a single exclusive claimant resource, used in short attended windows.
- **The Mac host**: Apple M4 with 16 GiB unified memory, running MLX. A smaller 8 GiB Apple device can run
  only tiny models (Kokoro, Pocket TTS) and is not a bench arm.

## 1. Shortlist

| Model | Licence | Size | Output | Cloning input | Local path on the GPU host | Mac (MLX) | Standing (AA, read 2026-10-22) |
|---|---|---|---|---|---|---|---|
| Ming-3.0-tts-0.5B (inclusionAI) | MIT | about 1.48B params, 2.76 GiB BF16 (M); "0.5B" is the backbone only | 44.1 kHz mono | reference audio, optional transcript | audio.cpp `ming3_tts`, Vulkan only, offline only (M) | `mlx-community/Ming-3.0-tts-0.5B-bf16`, mlx-audio 0.6.1 or later (M) | Cloning board #13, 1066 +/-16 (variant unnamed); provider board #19, 1190 |
| Qwen3-TTS-12Hz-1.7B-Base (Alibaba Qwen) | Apache-2.0 | 4.23 GiB incl. speech tokenizer (M) | 24 kHz (U, not re-read) | reference audio plus `ref_text` (ICL) or x-vector only | llama.cpp `llama-tts` (in our 2026-10-04 pin), qwentts.cpp (MIT, Vulkan) | `mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16` | Qwen3 TTS API 930 (provider #87); open weights not on the cloning board |
| VoxCPM2 (OpenBMB) | Apache-2.0 | 4.62 GiB, card says about 8 GB VRAM (V) | 48 kHz | reference audio plus transcript ("ultimate cloning") | audio.cpp `voxcpm2` (Vulkan or early HIP), or PyTorch ROCm with care (section 3) | `mlx-community/VoxCPM2-bf16` | no arena entry found |
| Fish Audio Drama 3 | Fish Audio Community License v1.0 | 35B MoE, about 3B active; 38.65 GiB (M) | 44.1 kHz | multi-reference | not at usable precision; experimental audio.cpp CPU-expert offload, untested on 16 GB cards | MLX 3/4/8-bit and bf16 builds exist; RTF U | Provider board #9, 1248 (top entry with open weights, named "Drama 3 Preview"); cloning board 1058 |
| ElevenLabs Eleven v4 / v4 Turbo | closed, hosted | n/a | n/a | professional clone of your own voice only | n/a | n/a | Provider board 1329 / 1335 (#1-2, tied) |
| HeyGen Voice Turbo | closed, hosted | n/a | n/a | bring-your-own clone key | n/a | n/a | Cloning board #1, 1202 +/-19 |

Not shortlisted, with the reason: Breeze TTS 2 (AA #11 provider, 1225; weights and outputs non-commercial),
Voxtral TTS and OmniVoice weights (CC BY-NC), Fish S2 Pro (research licence, non-commercial), Higgs TTS 3
(research licence; 14.7 GB peak on a 24 GB card), VibeVoice (TTS code withdrawn upstream), Kokoro (no cloning).

### Ming-3.0-tts-0.5B

- Dates (M): HF repo created 2026-09-22, modified 2026-10-21; GitHub repo created 2026-10-19, last commit
  2026-10-21 "improve 0.5B long-text splitting and voice consistency". No releases, tags or technical report.
- Vendor Seed-TTS-eval (V): en WER 1.584 / SIM 0.691; zh 0.800 / 0.758; the Seed-TTS reference row is en
  2.240 / 0.762. English SIM is the weakest figure in its own table.
- AA: the highest-ranked cloning-board entry with a Hugging Face link. The AA page has no open-weights column,
  and two entries above it have no stated weights status, so "best open model" is an inference (I).
- audio.cpp documents CUDA, Vulkan and CPU for this family; HIP is not listed, so Vulkan is the only GPU path
  on the GPU host (M). Its chunker uses a 300-codepoint budget for Latin text; later chunks use the first
  generated chunk as their reference (M, audio.cpp docs).
- The MLX port does not yet extract the CAM++ speaker embedding; it clones from reference audio plus transcript
  only, and its stop head sometimes fails to fire (M, MLX model card). Mac and GPU arms of this model are
  therefore not the same conditioning path.
- Risks: three days old at survey time; cloning, emotion and paralinguistic tags may not combine in one call
  (U); untested on gfx1201.

### Qwen3-TTS-12Hz-1.7B-Base

- Dates (M): weights created 2026-01-21; GitHub last pushed 2026-03-17. The 25 Hz models are still unreleased.
  Qwen's current flagship (Qwen-Audio-3.1-TTS-Plus, AA provider #3, 1301) is API-only.
- The only shortlisted model with a **measured gfx1201 run**: RTF 0.158 to 0.168 on Vulkan with a
  qwentts.cpp fork on a 32 GB R9700, HIP about 18% slower (vendor-adjacent article, M). Not the 16 GB card.
- llama.cpp merged Qwen3-TTS support for `llama-tts` on 2026-08-04 and a non-OpenAI `POST /tts` server
  endpoint on 2026-10-20 (M); our 2026-10-04 pin has the first and not the second. `llama-tts` exposes a
  speaker file but no reference transcript (M, tools/tts README at the pin), so ICL cloning needs qwentts.cpp.
- Independent paper (arXiv 2610.23678, M): leads on intelligibility, trails on prosody; ICL cloning degrades
  sharply with a wrong short transcript. Feed a human-verified `ref_text`.
- Long form (arXiv 2609.16989, M): on the 0.6B, 26% of generations over 1,500-word prompts were catastrophic
  (WER above 30%) without rollback; LACI reduced that below 1%. Chunk and regenerate.
- gfx1201 ROCm/HIP failure reports exist in other projects (koboldcpp #2355, LocalAI #10666). Prefer Vulkan.

### VoxCPM2

- Dates (M): weights created 2026-04-03, modified 2026-08-18; last release 2.0.3 on 2026-05-11.
- Vendor (V): Seed-TTS-eval en WER 1.84 / SIM 75.3; vendor test-EN WER worse than Qwen3-TTS. The AuK paper's
  VoxCPM2 numbers match the vendor's exactly, so they are re-cited, not independent.
- The card admits occasional instability on very long or highly expressive inputs (V).
- No official ROCm path (M); the only AMD success report is RDNA3 under WSL with a torchcodec patch and
  `optimize=False`.

### Fish Audio Drama 3 (optional rented tier)

- Licence (M, verbatim-checked): Fish Audio Community License v1.0, 2026-10-13. Free commercial use only while
  you plus affiliates earn under USD 500k a year; delivering narration for your own content or a client is
  not a "Hosted Service", but offering TTS or cloning as a service needs a separate licence; consent required
  to clone an identifiable person; no watermark removal; a prominent "Built with Fish Audio" notice; outputs
  may not train, distil or improve any speech or generative model. The HF front matter names a different
  licence file that does not exist (unresolved upstream metadata contradiction).
- Hardware: the vLLM-Omni recipe needs a CUDA GPU with at least 48 GB; vLLM-Omni lists no AMD support for it.
  audio.cpp has CPU expert-layer offload with documented 16 GB profiles, measured only on a 96 GB card ("physical
  16 GB and 24 GB GPUs have not been tested").
- Takes vary between renders, and open issues report silent chunks running to the token limit (mlx-audio
  #1026, vLLM-Omni #9157). The model is a beta prerelease.
- The AA entries are named "Preview"; whether they measure the released checkpoint is U.
- Hosted API price ($10 per 1M characters until 2026-11-12, then $50) comes from a secondary source only (U).

### Hosted ceiling (last resort, public non-confidential text only)

- Eleven v4 launched 2026-09-28; the docs warn behaviour "may shift over time", so outputs are not
  reproducible; professional cloning is limited to your own voice after verification. Official API prices:
  $0.08 per 1K characters (v4), $0.04 (Turbo).
- HeyGen Voice Turbo: 2026-10-09 snapshot via OpenRouter, 5,000 characters per request; clone consent flow
  and terms not reviewed (U).
- Both send the script and the reference voice to a third party.

## 2. Leaderboard caveats

- AA has separate provider-voice and controlled-voice (cloning) boards on different scales; never compare
  across boards. A rank range matters more than a rank: Eleven v4 and v4 Turbo are statistically tied.
- Provider-board ranks rate preset voices, not clones of a given speaker.
- Vendor README figures (for example Ming's 1069 / 1188) are older snapshots than the live board.

## 3. Platform risks on the GPU host (gfx1201, 16 GB)

- **Silent fp32 attention corruption.** pytorch/pytorch#201476 (opened 2026-10-19, open): on gfx1201 the
  memory-efficient SDPA backend returns wrong float32 results and is the default dispatch for fp32. The
  reporter used a Nix build (torch 2.13, ROCm 7.2.4, AOTriton 0.12b); official 2.14.1+rocm7.2 wheels did not
  reproduce it. Any PyTorch arm runs in bf16, disables the memory-efficient backend for fp32
  (`torch.backends.cuda.enable_mem_efficient_sdp(False)`) and carries a CPU parity check.
- ROCm 6.x fails on gfx1201; 7.x or later is required, and `HSA_OVERRIDE_GFX_VERSION` must not be set.
- audio.cpp's HIP backend runs on a 9070 XT for another model family but has open allocator failures
  (audio.cpp #1005). One installer (not audio.cpp itself) silently installs a CPU build on non-NVIDIA GPUs.
- `flash-attn` is CUDA-first; models that hard-require FlashAttention 2 degrade on ROCm.
- No TTS real-time factor or VRAM figure exists anywhere for the 16 GB card itself (U). The bench measures it.

## 4. Apple Silicon (MLX)

- mlx-audio lists Qwen3-TTS, VoxCPM2, Ming (dense / bailingmm) and Drama 3 with cloning (M).
- Ming 0.5B MLX card: RTF about 1.0 and 4.4 GB peak on an M4 Pro (V); mlx-audio 0.6.0 and earlier say the
  wrong words with it.
- Other MLX RTF figures circulate without stated hardware (Qwen3-TTS 1.7B 4-bit about 0.79): treat as U.

## 5. Evaluation caveats

- **ASR-WER is a regression gate, not a ranking.** arXiv 2610.31470 (2026-10-22) shows the evaluating ASR misses
  33 to 67% of very rare words even in human speech, and apparent TTS rare-word error falls from 10-13% to
  3-5% when more ASR systems are used. It does not establish a general 2% noise floor; it does show that small
  WER differences on technical text are mostly ASR error. Rare-word misses need human adjudication.
- **Long-form drift is unbenchmarked** for every shortlisted model. Short-prompt SIM hides drift; arXiv
  2609.16989 proposes a sliding-window speaker similarity (wSIM) for long outputs.
- Most comparison tables copy figures from the original papers instead of re-running systems.
- Vendor watermarks: none of the shortlisted open models ships one by default. Codecs and resynthesis strip
  classic audio watermarks (arXiv 2603.05310, 2505.19663), so a watermark is best effort only.
- EU AI Act Art. 50 transparency duties apply from 2026-08-02: label synthetic voice in deliverables.

## 6. Consequences for the bench

1. Three local arms, each run on both hosts: Ming-3.0-tts-0.5B (favoured), Qwen3-TTS-1.7B-Base (baseline
   with the only measured gfx1201 run), VoxCPM2 (48 kHz). Drama 3 only on a rented 48 GB or larger GPU.
2. Pin every runtime commit and every Hub revision; the Ming repository changed long-text behaviour two days
   before the survey.
3. Always supply a human-verified reference transcript; chunk at sentence boundaries and regenerate failed
   chunks.
4. Score WER with a fixed whisper model and adjudicate rare words by hand; add speaker similarity, a
   sliding-window similarity for the full text, and a MOS predictor; keep the operator's blind listening as
   a separate acceptance state.

## Primary sources

- Ming: https://huggingface.co/inclusionAI/Ming-3.0-tts-0.5B, https://github.com/inclusionAI/Ming-3.0-tts,
  https://github.com/0xShug0/audio.cpp/blob/main/docs/models/ming3_tts.md,
  https://huggingface.co/mlx-community/Ming-3.0-tts-0.5B-bf16
- Qwen3-TTS: https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-Base, https://arxiv.org/abs/2601.15621,
  https://arxiv.org/abs/2610.23678, https://github.com/ggml-org/llama.cpp/pull/26254,
  https://github.com/ggml-org/llama.cpp/pull/26603, https://github.com/ServeurpersoCom/qwentts.cpp,
  https://github.com/AMD-AIM/zhihu_rednote_articles/pull/49
- VoxCPM2: https://huggingface.co/openbmb/VoxCPM2, https://github.com/OpenBMB/VoxCPM,
  https://arxiv.org/abs/2606.06928, https://github.com/OpenBMB/VoxCPM/issues/203
- Drama 3: https://huggingface.co/fishaudio/drama-3/blob/main/LICENSE, https://arxiv.org/abs/2610.18010,
  https://github.com/0xShug0/audio.cpp/blob/main/docs/models/fish_drama3.md, https://recipes.vllm.ai/fishaudio/drama-3,
  https://github.com/Blaizzy/mlx-audio/issues/1026, https://github.com/vllm-project/vllm-omni/issues/9157
- Hosted: https://elevenlabs.io/docs/changelog/2026/9/28, https://elevenlabs.io/pricing/api,
  https://openrouter.ai/api/v1/models/heygen/heygen-voice-1-turbo/endpoints, https://arxiv.org/abs/2610.30470
- Leaderboards: https://artificialanalysis.ai/text-to-speech/leaderboard,
  https://artificialanalysis.ai/text-to-speech/leaderboard/controlled-voice
- Platform: https://github.com/pytorch/pytorch/issues/201476, https://rocm.docs.amd.com/en/latest/about/release-notes.html,
  https://github.com/0xShug0/audio.cpp/issues/1005
- Evaluation: https://arxiv.org/abs/2610.31470, https://arxiv.org/abs/2609.16989, https://arxiv.org/abs/2610.19774

## Limitations

- Several pages were read through a summarising fetch tool; figures marked M were re-read on the primary page by
  the verification pass, the rest are V, I or U as labelled.
- The paper search tools returned unrelated results, so arXiv IDs were found by web search and checked on
  their abstract pages; August to October 2026 papers may be missing.
- Nothing was downloaded or run. All hardware statements for the GPU host and the Mac host are about published
  evidence, not local measurements.
