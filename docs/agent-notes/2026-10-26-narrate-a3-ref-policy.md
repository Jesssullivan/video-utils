# Narrate bench A3 reference policy (2026-10-26, lane A3, TIN-7085)

Authority: operator ruling J83(a) (2026-10-26): re-run the narrate bench with SIM measured and the A3 VoxCPM2 crash
fixed before any engine pick. Re-run plan: Linear TIN-7085 comment `365540a1`, step 2.
R-HOOK-CONVERGENCE-20261004: R-N12 (hooks advisory), R-N13 (this receipt).

**State: source-read, fake-tested, cuts made and checked privately. A3 has not run again.** No TTS model ran on any
host for this lane. Whisper ran four times on the dev host (two word-timing reads, two cut read-backs), one at a
time, each inside `systemd-run --user --scope -p MemoryMax=6G -p MemorySwapMax=0 nice -n 19 ionice -c3`, with
`-t 4`. Memory PSI was checked before each run, and was 0.00–0.45 avg10. The GPU host was not touched.

## Root cause, from the pinned source (audio.cpp `47c2756e`)

Run 1's A3 smoke failed when `audiocpp_cli` exited 1 with `VoxCPM2 AudioVAE encoder sample capacity exceeded`.

- **The check.** It is in `src/models/voxcpm2/audiovae.cpp` `encode_audio`:
  1. the reference is mixed to mono;
  2. it is resampled with soxr to `audio_vae_config.sample_rate`, which is ceil(n × 16000 / rate);
  3. it is padded up to a multiple of `patch_size × prod(encoder_rates)`;
  4. the result must be at most `encoder_sample_capacity` samples.
- **The values.**

  | Value | Number | Source |
  |---|---|---|
  | Encoder sample rate | 16000 | embedded `config.json` of `voxcpm2-bf16.gguf` (sha256 `dc48028e…`), read from the GGUF header only |
  | Encoder rates | [2, 5, 8, 8] | same |
  | Patch size | 4 | same |
  | Pad multiple | 2560 samples | patch size × product of the encoder rates (4 × 640) |
  | Capacity | 240000 samples | default of session option `voxcpm2.audiovae_encoder_sample_capacity` (`loader.cpp`) |

  The largest reference that fits is therefore 238080 samples, 14.88 s.
- **Run 1, checked against those values.** The 34.75 s presenter clip needs 558080 padded samples, and the
  29.87 s read clip needs 478720. Both exceed the capacity.
- **The flag.** `--session-option voxcpm2.audiovae_encoder_sample_capacity=N` raises the capacity. N must be a
  multiple of 640. We did not take this route: its effect on VRAM is not measured, and the VoxCPM2 usage guide's
  practical reference range is 5–30 s ("short clip" on the card).
- **Second finding.** At this pin, a request's `voice_ref` becomes the speaker reference, and `reference_text`
  becomes the prompt text. The prompt text is used only when the request also has prompt audio (`audio`). See
  `session.cpp`, where `encoded_prompt_for_request(request.audio_input, …)` is called, and `generator.cpp`
  `build_prefill_sequence`.
  - Run 1's A3 variant sent `voice_ref` and `reference_text` without `audio`. Its transcript would have been
    unused; the crash came first.
  - The model card's ultimate clone passes the same clip as both reference and prompt. This is an inference from
    the source, not a run.

## Change (PR on branch `feat/narrate-a3-ref-policy-20261026`)

- **`host-job.json` A3-gpu.**
  - **`reference` policy:** `cut: max14s`, `max_seconds: 14.5`, `min_seconds: 5.0` and
    `encoder: {rate 16000, capacity_samples 240000, pad_samples 2560}`.
  - **Variant `ultimate`:** `voice_ref` + `audio` (the same cut) + `reference_text`. This matches the bench plan's
    A3 row, "prompt audio + transcript".
  - **Fallback `reference-only`:** `voice_ref` alone.
  - A1 and A2 are unchanged: they still use the full clip.
- **`host_run.py`.**
  - **Cut lookup.** A policy's `cut` names `voices.<id>.cuts.<cut>` in the private voices file. The cut's wav and
    text are hash-bound, and its `source_sha256` must equal the voice clip's sha256.
  - **Checks in `verify`.** `verify` hashes the cut and then checks the reference's WAV-header duration against
    max and min. It also checks the encoder's padded length, to the sample, against the capacity. A misfit refuses
    the inputs with exit 2 before any engine starts. Each arm's check is recorded as `<arm>.reference` in the
    verified inputs and the arm receipt.
  - **`prompt_audio`.** A `prompt_audio` variant, which needs the audiocpp runtime and `reference_text`, also sends
    the reference as `audio`.
- **`run-bench.sh --preflight`.** The pre-lease check:
  - it parses `bench.env` and checks the three runner hashes;
  - it runs `host_run.py verify` for the window's arms, with no engine, no scope and no `runs/` directory;
  - it prints `NARRATE-BENCH-PREFLIGHT rc=N`.

  An oversized reference is refused here, before the lease. The in-window verify refuses it again.
- **`ref_cut.py`.** The prepare step on the dev host:
  - `words` gets word timings from whisper-cli: small.en, DTW onsets, `-t 4` at most, via an ffmpeg 16 kHz copy.
  - `cut` (stdlib only):
    - aligns the verified transcript to whisper's words;
    - cuts only at gaps between matched neighbours, in the quietest 10 ms frame, and only within 12 dB of the
      clip's floor;
    - ranks candidate cuts by their boundaries (sentence 2, clause 1, word 0), then by length;
    - copies the PCM frames byte for byte;
    - cuts the transcript at the same words.

  The record holds no transcript text.
- **Tests.** `tests/test_narrate_bench_host.py` now has 42 tests, all passing; the new ones use only the fake
  binary and fake tools.
  - **Reference policy:** refusal before any engine; the cut's hash and source binding; the exact encoder
    boundary (238080 fits, 238081 needs 240640); the minimum length; malformed policies; `prompt_audio` without a
    transcript.
  - **Preflight:** refusal with no `runs/` directory and no engine call, and the runner-hash refusal.
  - **`ref_cut`:** a byte-identical slice; boundary ranking; no cut beside a word whisper did not hear; 24-bit
    sign handling; whisper run with DTW at most 4 threads (fake ffmpeg and whisper-cli).
  - **Tracked job:** the A3 policy.

## Measured: the cuts (private store; sha256 only here)

| Voice | Source | Cut | Words | Boundaries | Encoder padded / capacity | Cut read-back WER |
|---|---|---|---|---|---|---|
| presenter voice | 34.75 s, 44.1 kHz s24 | 11.97 s (0.965–12.935 s) | 25 (2..26) | sentence start, word end | 192000 / 240000 | 0.16 |
| read voice | 29.87 s, 48 kHz s24 | 12.63 s (0.835–13.465 s) | 31 (0..30) | sentence, sentence | 202240 / 240000 | 0.032 |

- **Read-back WER.** WER is whisper small.en reading the cut, scored against the cut transcript. Three of the
  presenter's four errors fall in a 3-word stretch. Whisper also misreads that stretch in the uncut clip, where
  verified words 9–11 align to one 50 ms whisper word. So the errors come from recognition, not from misalignment.
- **Why the presenter cut ends mid-phrase.** The presenter transcript has one 68-word sentence from 7.4 s to the
  end. No sentence- or clause-bounded cut of 5–14.5 s has trusted gaps at both ends.
- **Hashes.**

  | Voice | Cut wav sha256 | Cut txt sha256 |
  |---|---|---|
  | presenter voice | `f84b5a02…85fa2` | `3386e0bc…7014` |
  | read voice | `ca36f179…cf4d` | `7fdab163…4e9b` |

  The staged bench voices registry has sha256 `eb89ec45…9227`. The private store's `voices.json` records each
  cut (`refCuts.max14s`) with its source sha256, times, word range and record. `MANIFEST.sha256` covers the new
  files.
- **Dry check.** The tracked job, loaded against the staged registry, sends:
  - A3 to the cut, with fits true for both voices;
  - A1 and A2 to the full clips.

  Without the cut, both full clips are refused for max_seconds and encoder samples.

## Re-stage plan (for root)

The voice files were deleted from the GPU host after run 1. A private staging set and its PLAN.md are in the
voice work area, outside git: `voices-stage-20261026/` under the private host-window directory.

1. Re-stage 9 files to `~/narrate-bench/voices/`, with dirs 700 and files 600:
   - `voices.json`;
   - per voice, the full clip wav and txt and the max14s cut wav and txt;
   - `SHA256SUMS`.
2. Run `sha256sum -c SHA256SUMS` on the GPU host.
3. Set `NARRATE_BENCH_VOICES_SHA256` in `bench.env` to the new registry sha256.
4. Rebuild the pack from the landed PR and recompute the three `NARRATE_BENCH_EXPECT_*` hashes. All three runner
   files changed.
5. Run `run-bench.sh --preflight` before asking for the lease.
6. Delete the voices again after the window and record the deletion.

## Open

- **Freeze.** The bench plan says it freezes once a scored render exists, and run 1 was scored. This change makes
  A3 match the plan's preregistered conditioning (prompt audio + transcript). The reference length is a deviation
  made under J83(a). Root decides whether that needs a plan addendum or a `text-v2` preregistration.
- **Unequal reference lengths.** A3 now clones from about 12 s and A1/A2 from about 30–35 s. SIM across arms is
  therefore not like for like. A matched control would run A1/A2 with the same cut; it needs a decision.
- **Not yet observed.**
  - Whether `ultimate` passes its smoke on the GPU host.
  - VoxCPM2's VRAM with a prompt.
  - Whether audio.cpp reads the extensible 24-bit WAV cut. It reads the same format in the full clip, which got
    as far as the encoder in run 1.
