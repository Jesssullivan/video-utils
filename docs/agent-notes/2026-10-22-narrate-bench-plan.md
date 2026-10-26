# Narrate engine bench: preregistration (2026-10-22)

Authority: operator-approved narrate plan of 2026-10-22, lane W3 (Linear TIN-7085, parent TIN-7084, milestone
N0 Narration v0); R-HOOK-CONVERGENCE-20261004 R-N11 (ownership and live-session checks before touching the GPU
or any process), R-N12 (hooks advisory), R-N13 (this receipt; facts mirrored to Linear).
Research: [`docs/research/2026-10-22-tts-voice-cloning.md`](../research/2026-10-22-tts-voice-cloning.md).

**State: preregistered, not run.** No weights downloaded, no GPU used, no voice recorded. Two gates are open:
**G1** an attended GPU window, **G2** the operator's consent and reference clips. The bench decides which engine
N0 renders with; the decision is due Saturday 2026-10-24.

This file is frozen once the first scored render exists. Changing a bar, an arm, a decoy, a stop rule or the
text after that is a new bench with a new preregistration (`text-v2`, a new dated file). No render exists yet,
so it is not frozen; revisions made before the first scored render are listed under "Revisions before freeze".

## Inputs

| Input | Where | Binding |
|---|---|---|
| Bench text | [`narrate/bench/text-v1.md`](../../narrate/bench/text-v1.md), 795 spoken words, six sections s1..s6 (opening, technical fault, dialog, numbers and units, results, closing) | sha256 `f7ff6923899b72ade8da6f84678ca9bff81bc3d8ee61b70bda908b95951a704d` |
| Pinned sources | [`narrate/bench/sources.json`](../../narrate/bench/sources.json), printed by `just narrate-fetch` | sha256 `b1931a632c1a41affe06023cb604840eec607a9c17cee228ebf8a0ec783bb10b`; every file declares the Hub's LFS sha256 or, for a non-LFS file, its git blob sha1; the measured sha256 of each file is recorded in `<dest>/fetch-receipt.json` |
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

Weights (Hugging Face, revision-pinned; `sources.json` holds the LFS sha256 of every LFS file and the git blob
sha1 of every non-LFS file, such as configs, tokenizer text and speechbrain's `hyperparams.yaml`). "Converted
from" is the revision the card states; where a card states none, the base repository's HEAD at lookup is shown
in brackets, which is not evidence of what was converted:

| Source id | Repo @ revision | Converted from | Size |
|---|---|---|---|
| ming3-0.5b-gguf | `audio-cpp/Ming-3.0-TTS-0.5B-GGUF@2eb8d37c` (bf16) | `inclusionAI/Ming-3.0-tts-0.5B`, revision not stated [HEAD `8d66b70a`]; card's comparison pinned to upstream code `e999c39f` | 2.79 GiB |
| qwen3-tts-1.7b-base-gguf | `ggml-org/Qwen3-TTS-12Hz-1.7B-Base-GGUF@ca27d74b` (bf16 + mmproj bf16) | `Qwen/Qwen3-TTS-12Hz-1.7B-Base`, not stated [HEAD `fd4b2543`] | 3.86 GiB |
| qwen3-tts-1.7b-base-qwentts | `Serveurperso/Qwen3-TTS-GGUF@b7ee2e8c` (talker BF16, tokenizer F32) | same | 4.21 GiB |
| voxcpm2-gguf | `audio-cpp/audio.cpp-gguf@ef1ab259` (`VoxCPM2-GGUF/voxcpm2-bf16.gguf` only) | `openbmb/VoxCPM2`, not stated [HEAD `32279eff`] | 4.44 GiB |
| ming3-0.5b-mlx | `mlx-community/Ming-3.0-tts-0.5B-bf16@283b3c34` | Ming 0.5B | 2.80 GiB |
| qwen3-tts-1.7b-base-mlx | `mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16@a6eb4f68` | Qwen3-TTS Base | 4.23 GiB |
| voxcpm2-mlx | `mlx-community/VoxCPM2-bf16@a7fb80d9` | VoxCPM2 | 4.62 GiB |
| ecapa-voxceleb | `speechbrain/spkrec-ecapa-voxceleb@0f99f2d0` | | 0.08 GiB |
| utmosv2-fold0 | `sarulab-speech/UTMOSv2@506474f2` (fold 0 only) | | 0.76 GiB |
| wavlm-base-plus-sv (optional) | `microsoft/wavlm-base-plus-sv@feb593a6`; licence not stated on the card | | 0.38 GiB |
| drama3-gguf-q3 (optional) | `Jmica/Drama-3-GGUF@17a5b40c` (Q3_K_S backbone) | `fishaudio/drama-3@dd64a85c` (stated on the card) | 18.93 GiB |
| drama3 (optional, rented host only) | `fishaudio/drama-3@b2b5ee99` | | 38.65 GiB |

Default selection is 27.8 GiB (9 Hub sources); with the optional tier, 85.8 GiB. Three repositories were modified
on the lookup day (the MLX Ming build, the audio.cpp GGUF collection, Ming upstream), which is why every pin is
a full revision rather than a branch.

Both Ming ports predate the upstream long-text fix (M, Hub and GitHub commit dates): the GGUF files were
uploaded 2026-10-21 03:56 UTC and the MLX weights 2026-10-19, while `028c1eac` landed 2026-10-21 11:03 UTC, and
the GGUF card's Python comparison is pinned to `e999c39f`, the commit before it. Whether the fix changes the
converted weights or only upstream's Python splitting is U; the bench's own fixed chunking is the same for
every arm either way.

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
| A2-gpu-alt Qwen3-TTS-1.7B-Base (primary A2 arm) | GPU host | qwentts.cpp, Vulkan | qwen3-tts-1.7b-base-qwentts | ICL cloning with `ref_audio` + verified `ref_text`, the conditioning narrate's client sends (lanes W5, W6) |
| A2-gpu Qwen3-TTS-1.7B-Base (secondary) | GPU host | llama.cpp `llama-tts`, Vulkan build, `-ngl 99` | qwen3-tts-1.7b-base-gguf | `--tts-speaker-file` only (this runtime takes no reference transcript, and the pin has no server endpoint) |
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
arm passes, the N0 fallback is **A2-gpu-alt** (Qwen3-TTS through qwentts.cpp with `ref_audio` and `ref_text`)
with its misses written down, and the pick is reopened in N1. A2-gpu (`llama-tts`, speaker file only) is the
fallback only if A2-gpu-alt does not complete text-v1 on the GPU host; the receipt then states that the
fallback uses a different conditioning path from the approved plan's verified `ref_text` and from the one
narrate's client sends. This choice is an open operator decision (below) and is recorded as such.

## Decoys

Scorer checks that run in the same scoring pass; each must come out on the expected side of the bar or the
metric is invalid for the pick (it is still reported):

1. **Reference self-match**: the second half of the reference clip scored against the first half. Expected SIM
   well above the SIM bar; proves the embedding sees the speaker at all.
2. **Wrong speaker**: two chunks rendered with a built-in preset voice (Ming `UK_George`, no cloning), made in
   the window inside A1-gpu's budget, right after its one-chunk smoke (window step 4). Expected SIM below the
   bar; this is the decoy the SIM bar is defined against.
3. **Robot baseline**: the full text rendered by espeak-ng, pinned through the repository's flake lock
   (`nix shell --inputs-from . nixpkgs#espeak-ng`, `1.52.0.1-unstable-2025-09-09` at the current lock) rather than any host binary;
   the receipt records its store path, `--version` output and binary sha256. Expected UTMOS below 3.0 and SIM
   below the bar, with low WER. Proves UTMOS and SIM are not just measuring intelligibility.
4. **Corrupted chunk**: one espeak-ng chunk from decoy 3 with its second half replaced by silence, and one
   played time-reversed. Expected: both flagged catastrophic. Proves the failure detector fires. After the
   window, the same two corruptions are applied to one A2-gpu-alt chunk and scored again.
5. **Shuffled transcript**: one espeak-ng chunk scored against the text of a different chunk. Expected WER
   over 30%. Proves WER alignment is per chunk and not lenient. Repeated on one A2-gpu-alt chunk after the
   window.

Decoys 3 to 5 need neither G1 nor G2 and are produced and scored before the window from espeak-ng chunks, so a
scorer bug in the WER or catastrophic-chunk detector shows up before GPU time is spent. Decoys 1 and 2 need G2
for their SIM scores; decoy 2 also needs G1 for its render.

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
   file `matched_declared_sha256` or `matched_declared_git_blob_sha1`; the fetch refuses any other outcome.
3. Build audio.cpp, llama.cpp and qwentts.cpp at their pinned commits with the Vulkan backend on an approved
   builder; record each binary's sha256.
4. Generate and record the chunk list; copy the reference clip and verified transcript to the host's private
   store and check their sha256 values.
5. Render decoy 3 with the flake-pinned espeak-ng, build decoys 4 and 5 from its chunks, and score all three
   off the GPU. A decoy on the wrong side of its bar stops the window from starting until the scorer is fixed.

In the window:

1. **Ownership and live-session check (R-N11).** Read the GPU Lease holder and the model coordinator's state.
   If another claimant holds the card, ask the coordinator to release it through its own release call; never stop
   another owner's process. If it cannot be released, the window does not start.
2. **Acquire the Lease** by compare-and-swap on the GPU lease object with this bench as holder, a duration of at
   most 30 minutes, and the arm list in the annotation. Record the lease version before and after, the holder
   and the start time.
3. Record the idle VRAM baseline from sysfs; start the 10 Hz sampler.
4. Run order: A2-gpu-alt (8 min budget), A1-gpu (8 min, including the two decoy-2 preset-voice chunks after
   its smoke), A3-gpu (8 min); A2-gpu and D3-gpu-experimental only with time left. A2-gpu-alt runs first
   because it is both the fallback and the conditioning path narrate uses; the qwentts.cpp fork behind the
   only measured gfx1201 run is close to, not identical with, this pin. Per arm: load, one-chunk smoke, seed 1
   full text, then seeds 2 and 3 if the arm's budget allows. One synthesis process at a time.
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
  `$NARRATE_WEIGHTS_DIR` (or `--dest`), refuses a destination inside any checkout of the repository (the
  running one, the main work tree and every linked worktree), checks declared size and the declared LFS sha256
  or git blob sha1, writes `hf/<source>/SHA256SUMS` plus a dated receipt, and never clones git sources. The
  apply path was exercised only against a local `file://` mirror of synthetic bytes in
  `tests/test_narrate_bench_fetch.py`; it has not downloaded any real weights.
- Bazel: `narrate/bench/` is not a Bazel package; the root `//:repo_data` glob carries it to the Python tests.
  The S3 test classification supplement counts the new module.

## Revisions before freeze

- **Revision 1 (2026-10-23, review of PR #36; no render, download or GPU use had happened).**
  R-HOOK-CONVERGENCE-20261004 R-N13.
  - Hash binding: every non-LFS file now carries the Hub's `git_blob_sha1` (re-read from the pinned tree
    listings; the formula was checked on one 1,919-byte file), and `fetch.py` verifies it at download and for
    files already present. A file with no declared hash is refused. Check labels now say which declared value
    matched.
  - A2: A2-gpu-alt (qwentts.cpp, `ref_text`) is the primary A2 arm, runs first, and is the named fallback.
  - Decoys 3 to 5 come from flake-pinned espeak-ng before the window; decoy 2 is scheduled inside A1-gpu.
  - `converted_from` records the card-stated revision or null; the Drama 3 GGUF states `dd64a85c`.
  - Fetch layout is `<dest>/hf/<id>`; `fish-speech` is optional; `--arm D3-rented` selects its optional sources;
    the plan lists excluded optional ids; malformed entries are refused with a message; hashing runs on Python
    3.9 (checked with CPython 3.9.25).

- **Revision 2 (2026-10-23, host-process runner, lane E6; no render or GPU use had happened).**
  R-HOOK-CONVERGENCE-20261004 R-N13. Operator ruling of 2026-10-23 (TIN-5770): the first window is a host process
  on the GPU host. Runner and its receipt: [`2026-10-23-narrate-host-bench.md`](2026-10-23-narrate-host-bench.md).
  - The chunk list is fixed in `narrate/bench/chunks-v1.json` (17 chunks, 795 words, `chunks_sha256`
    `f6b109c78ffdf3e311dcd95b2b12c623c41a9ea99c170a0f58802ec20398c31e`): narrate's chunker, with each section's
    paragraphs joined so sentences pack across the s3 dialog lines but never across a section.
  - Host-run limits from the ruling: VRAM in use stays at or under 12,000,000,000 bytes (absolute, sampled every
    0.2 s); above it, the window stops. The 14.5 GiB bar above idle is still reported.
  - A1 (Ming): its 512-position context is shared by the reference's acoustic prefix and the output (about 80 ms
    per position), so the 30 to 35 s reference with `reference_text` leaves too little room for a chunk of up to
    300 codepoints. The one-chunk smoke requires at least half the chunk's expected duration; if the planned
    conditioning fails it, A1 runs with speaker-embedding conditioning (the same clip without `reference_text`) and
    the receipt records the deviation.
  - Each runtime loads its model once per pass: qwentts.cpp through `qwen-tts --stream-by-line` (ICL with
    `--ref-wav` and `--ref-text`), audio.cpp through `--request-sequence`. RTF is per-chunk synthesis time over
    audio; load time is recorded apart.

## Open questions

- **Operator decision: which A2 path is the N0 fallback.** This plan names A2-gpu-alt, matching the approved
  plan's "feed it a verified `ref_text`"; the approved plan's other sentence ("already runs through our
  llama.cpp pin with `llama-tts`") describes A2-gpu, which cannot take `ref_text`. Until the operator confirms,
  the receipt records the fallback as "A2-gpu-alt, operator confirmation pending".
- Whether qwentts.cpp's `tts-server` exposes an OpenAI-style `/v1/audio/speech` route with `ref_audio` and
  `ref_text` (U); if not, lane W6 needs a shim, as it would for `llama-server`.

- Whether audio.cpp's Vulkan build runs `ming3_tts` and `voxcpm2` on gfx1201 at all (U until G1).
- Whether `llama-tts` speaker-file cloning without a transcript is competitive with ICL (the reason A2-gpu-alt
  exists).
- The WavLM speaker-verification licence; it stays optional until checked.
- Whether UTMOSv2 fold 0 alone is the package default (U); if not, the receipt states which folds were used.

## Addendum, 2026-10-26: window 2 under J83(a)

Authority: operator ruling **J83(a)** (SSOT doc 3ca6e09afb44, 2026-10-26): re-run the bench with SIM measured and
A3 fixed before any engine pick. Re-run plan: TIN-7085 comment `365540a1`. Two operator decisions of 2026-10-26
shape this addendum:

1. Add matched A1 (Ming) and A2 (Qwen3-TTS) runs on the same word-aligned cut of about 12 s that A3 (VoxCPM2)
   uses, so that SIM compares like for like. A1 and A2 also keep their full-clip runs.
2. Record every change for run 2 here, as a dated addendum, not as a new preregistration.

R-HOOK-CONVERGENCE-20261004 R-N13.

**State:** not run. Window 2 has not started, and no TTS model ran for this addendum.

### What does not change

- **The text.** The bench text is still text-v1, sha256 `f7ff6923…a704d`, with the same chunk list
  (`chunks-v1.json`, 17 chunks).
- **The rules.** The bars, the decoys, the stop rules and the pick rule are as preregistered above.
- **The engines.** The binaries, weights and pins are run 1's: qwentts.cpp `5916bf7c`, audio.cpp `47c2756e`, and
  the weight sha256 values in `sources.json`.
- **The freeze.** The plan froze when run 1 was scored. The operator chose this addendum over a `text-v2`
  preregistration. Each deviation is listed below, so run 2 is read against these rules plus this list.

### Run 1, as context (measured 2026-10-23; re-scored with SIM 2026-10-26)

| Arm | Variant | Chunks | RTF (seed 1 / seed 2) | Load s | Audio s | Seed 1 pass wall s | WER whole (seed 1 / seed 2) | Peak VRAM above idle |
|---|---|---|---|---|---|---|---|---|
| A2-gpu-alt | icl-ref-text | 17/17 ×2 | 0.555 / 0.639 | about 4 | 262 | 150 | 0.043 / 0.034 | 6.28 GiB |
| A1-gpu | speaker-embedding (the ref-text smoke truncated) | 17/17 ×2 | 0.767 / 0.750 | about 12.5 | 218 | 181 | 0.031 / 0.034 | 3.26 GiB |
| A3-gpu | none passed | 0/1 | | | | | | 4.27 GiB, smoke only |

- **Window time.** The window took 884 s. The in-window verify took about 67 s.
- **Smokes and the decoy.** A2's smoke took 18 s. A1 took 19 s for the failed ref-text smoke, 31 s for the
  speaker-embedding smoke and 38 s for decoy 2.
- **A3.** A3 exited 1: `VoxCPM2 AudioVAE encoder sample capacity exceeded`.
- **SIM.** The private numbers are on TIN-7090.
  - Decoys 1, 2, 4 and 5 are valid.
  - A2 meets every SIM bar.
  - A1 meets the median and decoy-margin bars. It misses the wSIM bar at arm level because of one weak seed-2
    window.
  - A3 has no audio.

### SIM bars, as implemented

The bars below come from PR #41: `narrate/sim.py` and `narrate/bench/score.py`, with the fix round in
[`2026-10-26-narrate-sim-fix-round.md`](2026-10-26-narrate-sim-fix-round.md). The preregistered values are
unchanged.

- **Scorer.** The scorer is ECAPA (speechbrain `spkrec-ecapa-voxceleb`, registered in `program/models.json`). It
  runs on the dev host, one scorer at a time under a host-wide lock, inside a 6G memory scope. Before the
  reference is decoded, `policy.check_consent` must pass for every registered voice whose reference clip is that
  clip.
- **Reference.** SIM for every arm is measured against the window voice's **full** consented clip, including the
  arms that clone from a cut. The scorer binds the clip to the window's verified `voice.wav` sha256.
- **Per pass.** Each chunk is scored against the reference, and the pass reports the median and the minimum.
  wSIM uses 10 s windows with a 5 s hop over the joined chunks and reports the minimum, the mean and every window.
  It skips windows with under 3 s of voiced frames. A chunk over 60 s is skipped.
- **Per arm.** An arm is read over the chunks and wSIM windows of its seed passes; smoke and decoy passes do not
  count. The bars are:
  - median at least 0.45;
  - median at least 0.15 above decoy 2;
  - wSIM minimum at least 0.8 × the arm's median.

  `all_met` treats a missing value as unmet.
- **Decoys.**
  - Decoy 1 is the reference's second half scored against its first half. It must be at least 0.60. That number
    reads "well above the bar" as the bar plus the margin. It is an interpretation, not a preregistered value.
  - Decoy 2 is the preset voice. Its median must be below 0.45 and at least 0.15 below decoy 1.
  - Decoy 2 is window-wide: it renders once per window, inside A1-gpu.

### The A3 reference policy

The A3 reference policy comes from PR #47 ([`2026-10-26-narrate-a3-ref-policy.md`](2026-10-26-narrate-a3-ref-policy.md)).

- **The cut.** A3-gpu clones from the voice's `max14s` cut. This is a time-aligned slice of the same consented
  clip, cut at whisper word gaps, with the verified transcript cut at the same words.
- **Its bounds.** The cut runs from 5 to 14.5 s. The VoxCPM2 encoder's padded input is checked to the sample
  against its capacity: 240000 samples at 16 kHz, so at most 14.88 s.
- **Variants.** Variant `ultimate` sends the cut as reference and as prompt audio, with its transcript, which is
  this plan's A3 row. `reference-only` is the fallback.
- **Cut lengths.** The presenter cut is 11.97 s and the read cut is 12.63 s.
- **Preflight.** `run-bench.sh --preflight` refuses a misfit before the lease.

**Deviation:** the plan names one 25 to 30 s reference for every arm. A3's reference is about 12 s instead.

### Matched-cut arms (new; operator decision 1)

Two arms run after A3. Both are scored against the full clip like every arm.

| Arm | Controls | Differs from it only in |
|---|---|---|
| `A2-gpu-alt-cut` | A2-gpu-alt | its reference: the `max14s` cut wav and cut transcript (`--ref-wav`, `--ref-text`), the same files A3-gpu uses |
| `A1-gpu-cut` | A1-gpu | its reference: the same cut and cut transcript. It renders no decoy, because decoy 2 renders once, in A1-gpu |

- **How `host_run` holds them to that.** It refuses a `matched_cut_of` arm unless all of these hold:
  - it names a cut;
  - the arm it controls clones from the full clip;
  - the two have identical runtime, inputs, settings and variants.

  The budget, the decoys and the `about` text may differ.
- **What the receipts record.** Each receipt records `matched_cut_of` and its conditioning reference: the label
  and the wav, text and clip sha256.
- **What `score.py` does with them.**
  - `matched` sets each control beside its native arm: variant, SIM median, wSIM minimum and mean, whether the
    bars are met, seed-1 WER, catastrophic chunks and RTF, plus the cut-minus-full differences.
  - `conditioning.groups` names the like-for-like set. In window 2 that set is A1-gpu-cut, A2-gpu-alt-cut and
    A3-gpu, all on the same cut.
- **A1's variant may differ between the two arms.** In run 1 the full-clip ref-text smoke truncated, because a
  30 to 35 s prompt fills most of Ming's 512 positions. A cut of about 12 s leaves room for a chunk, so
  A1-gpu-cut may pass with `ref-text`, which is this plan's A1 row. A1-gpu, as in run 1, will likely fall back to
  `speaker-embedding`. The scorer notes when the variants differ, because then the conditioning path differs as
  well as the reference.
- **What they answer.**
  - Across A1, A2 and A3 on one reference, whether SIM differences come from the engine or from the reference
    length.
  - Within A1 and within A2, what shortening the reference does.
- **Candidates.** The controls do not add candidates to the pick. The pick rule still reads A2-gpu-alt, A1-gpu
  and A3-gpu. Whether a control could stand in for its native arm is an open operator decision (below).

### Per-voice windows and seeds

- **One voice per window.** Each window clones one voice and has a new holder. The presenter voice goes first.
  The read voice follows in a later window.
- **Naming the voice.** `run-bench.sh HOLDER VOICE` takes the voice on the command line; it replaces bench.env's
  `NARRATE_BENCH_VOICE`. `run-bench.sh --preflight VOICE` checks that voice before the lease.
- **Seeds.** Each arm runs **seed 1 only** (`seeds: [1]`). Its smoke, and for A1-gpu decoy 2, run first.
  - **Deviation:** this plan runs three seeds. The two bars read "best of 3" (catastrophic chunks and whole-text
    WER) **cannot be read from window 2**. They stay not measured until a later window runs seeds 2 and 3.
  - Run 1's seed 2 for A1 and A2 came from another window, and it does not fill this gap for the re-run.
- **Arm order.** A2-gpu-alt, A1-gpu, A3-gpu, A2-gpu-alt-cut, A1-gpu-cut.
  - A2 goes first because it is the N0 fallback.
  - A3 goes before the controls because J83(a) needs it.
  - The controls go last, so the 1500 s arms deadline cuts them first.
- **Scoring.** Each window is scored on its own, with that voice's full clip as `--reference`. Then
  `just narrate-bench-combine DEST DIR_A DIR_B` puts the windows in one table:
  - one row per window and arm;
  - every window's matched-cut rows;
  - per arm, whether the SIM bars were met in every window.

  Windows that share a voice clip are flagged, as are windows that used different SIM models or bars.

### Wall time against the 1500 s arms cap

This is an estimate from run 1's receipts. The inner arms cap is 1500 s. The other limits are:

- scope RuntimeMaxSec 1680;
- `timeout -k 15 1700`;
- the service's RuntimeMaxSec 1740.

| Step | Run-1 basis | Estimate s | Slow case s |
|---|---|---|---|
| In-window verify | 67 s | 67 | 67 |
| A2-gpu-alt: smoke + seed 1 | 18 + 150 (RTF 0.555) | 169 | 190 (seed RTF 0.639) |
| A1-gpu: ref-text smoke (fails) + speaker-embedding smoke + decoy 2 + seed 1 | 19 + 31 + 38 + 181 | 270 | 275 |
| A3-gpu | unknown; its budget is the cap | 480 | 480 |
| A2-gpu-alt-cut | as A2 | 169 | 190 |
| A1-gpu-cut: ref-text smoke (may pass) + seed 1, or both smokes + seed 1 | 31 + 181, or 19 + 31 + 181 | 231 | 235 |
| **Total** | | **1386** | **1437** |

- **Margin.** The set fits with 63 to 114 s to spare, **even if A3 uses its whole 480 s budget**. If A3 finishes
  in its run-1-like range (smoke plus seed 1 at an RTF near 1), the total is about 1150 to 1200 s.
- **If it overruns.** The deadline caps the running arm's budget, and an arm not yet started is recorded
  `not_started`. A1-gpu-cut is the arm at risk. A capped control is reported as such and re-run in the read-voice
  window or a third window. No arm was dropped for window 2.

### Changes for run 2

All of these are on branch `feat/narrate-window2-matched-cut`:

- **`host-job.json`:**
  - `seeds: [1]`;
  - the arms `A2-gpu-alt-cut` and `A1-gpu-cut`, with `matched_cut_of`.
- **`host_run.py`:**
  - the `matched_cut_of` checks;
  - `matched_cut_of` in the arm receipt;
  - the reference label in the window receipt.
- **`run-bench.sh`:**
  - the five default arms;
  - the `VOICE` argument for the window and the preflight;
  - the voice in `window.log`.
- **`score.py`:**
  - `window` identity, with the voice by clip sha256 and never by id;
  - `conditioning.groups`;
  - `matched`;
  - SIM binding to the receipts' clip when no `voice.wav` was verified;
  - `--combine`.
- **`just narrate-bench-combine`:** the new recipe.
- **Tests:** fake binaries and a fake SIM worker only.

### Open

- **Operator decision: can a matched-cut control stand in for its native arm in the pick?** Until there is a
  decision, the answer is no.
- **Seeds 2 and 3.** The "best of 3" bars need a later window.
- **Unobserved until window 2:**
  - whether A3 `ultimate` passes its smoke;
  - VoxCPM2's VRAM and RTF with a prompt;
  - whether A1-gpu-cut passes `ref-text`.
- **Missing scorer checks.** Decoy 3 (espeak-ng) and UTMOS are still not scored.
