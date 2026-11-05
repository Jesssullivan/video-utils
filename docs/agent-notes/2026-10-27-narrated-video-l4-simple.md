# Narrated video L4: simple path without avatar (2026-10-27)

Authority: operator direction KP-13 and rulings NV-1 to NV-5 (Linear TIN-7476
comments `94248deb`, `1c16fbda` and `9db389dc`). NV-4 starts this lane after L3.
Receipt per R-HOOK-CONVERGENCE-20261004 (R-N13).

`narrated-video L4 | narrate seat | video-utils feat/narrated-video-l4-simple (stacked on PR #58) | script to mix run on fixtures; gates below | root review and merge after #58, then L5 kitpip pin and avatar`

## What changed

| Area | Files | Change |
| --- | --- | --- |
| Speech stages | `narrate/video/speech.py` | `script` (spoken-text digest, advisory lexical findings), `voice` (one narrate run in the stage directory), `voice_qa` (verify, evaluate, the job's gates; listening stays `pending_operator`) |
| Picture and placement | `narrate/video/place.py` | `base` (card, still, video; deck refuses `base_deck_pending` until L8) and `place` (48 kHz, sample-exact, Edition.check at Place) |
| Bed | `narrate/video/music.py` | one cycle from the operator's loops by digest: LCM up to 120 s, gains, `atempo` only when the factor is not 1, loudness measured |
| Mix | `narrate/video/mix.py` | bed 20 LU under the re-measured voice, 7 dB duck (Sidechain or EdlEnvelope), 3 s and 5 s fades, one limiter at -2.0 dBFS, drift and true-peak gates |
| Executor | `narrate/video/run.py`, `narrate/video/common.py`, `narrate/video/labels.py` | `run` and `stage`, verdicts recorded and failures retried, `--stages`, `--until`, `--force`, monotone labels |
| Store | `narrate/video/keys.py`, `narrate/video/store.py` | `volatile_outputs`: a narrate run's own `manifest.json` is re-hashed but left out of the stage content digest, so an identical rerun stops the cascade |
| CLI and recipes | `narrate/video/cli.py`, `narrate/video/fixture.py`, `just/narrated-video.just` | `run`, `stage`, `fixture`; `nv-run`, `nv-stage`, `nv-quick`; `nv-fixture` runs `nv-quick` on a synthetic workspace |
| Hooks and skills | `program/tool-drafts/narrated_video.json`, `.agents/skills/{narrated-video,narrated-video-place,music-bed,narrated-video-mix}/SKILL.md` | drafts for tools 63, 64, 65 and 68 (proposals, not admitted) and their skills |
| Spec | `docs/spec/NARRATED_VIDEO.md` | "Simple path (lane L4)", the commands table, `volatile_outputs` and three unknowns |
| Tests | `narrate/tests/test_narrated_video_simple.py`, `narrate/tests/stdlib_smoke.py`, `tests/test_public_tree.py` | 27 simple-path tests. The smoke imports every `narrate/video` module. The public tree covers the new skill directories |

## Evidence

All runs used `nix develop .#condense` inside `systemd-run --user --scope -p
MemoryMax=6G -p MemorySwapMax=0 nice -n 19`. Inputs were generated: the fake
engine's sine voice, the two E-major bed loops, colour cards, an FFmpeg test
pattern with a -40 dB tone and AM noise bursts. No recording was used.

| Check | Result |
| --- | --- |
| `just nv-fixture` | 7 stages ran, `verify` ok. Mix -15.8 LUFS (drift 0.2 LU), voice -15.8 LUFS, true peak -9.1 dBTP, duck 7.0 dB, 11.0 s mono, no flags |
| `narrate/tests/test_narrated_video_simple.py` with the L3 graph tests | 128 passed |
| Acoustic duck check | EdlEnvelope with the voice at 4.0 s: the bed sits 20 LU (within 0.5) under the voice un-ducked, 7 dB (within 0.3) under it while it speaks, untouched before it |
| Negative controls (scratch edits, restored) | bed level ignoring `bedBelowVoiceLu`, drift gate removed, music tail ignored, `volatile_outputs` ignored, overlap check removed, sidechain never keying: each fails at least 1 test |
| `just narrate-test` | 885 passed, 1 skipped |
| `just narrate-lint` | ruff and shellcheck clean |
| `just narrate-dhall-check` | exit 0 |
| `narrate/tests/stdlib_smoke.py` | 7 tests OK, every `narrate/video` module imports |
| `tests.test_public_tree`, `tests.test_timeline_contract` | 79 tests OK, 1 skipped (no private terms file) |
| `just check` (`just test`) | 2207 tests: 26 failed, 7 errors, 151 skipped. 8 are the marked-video, marked-compact and marked-video MCP renders (`No bounded supported installed font found`) and the `test_media` AAC overshoot (-1.39 dBTP), as in the L3 receipt. 25 are `test_web_stack` and `test_web_runs_s3`: `pnpm install --offline` cannot resolve `@pnpm/exe@11.25.0` in this host's package mirror. No failing test reads a file this branch changes |
| `scripts/doctor.py --require-media` (the rest of `just check`) | exit 0 |

## Decisions in this lane

- `run` executes one stage at a time in one process. `nv-run` and `nv-quick`
  wrap it in `narrate/bounded.sh`. The spec's limit of 2 parallel stages holds.
- The voice stage keeps the narrate run inside its stage directory, under the
  fixed name `narration/`. kitpip (L5) reads that run, and the store re-hashes it.
- `Stereo` is the mono mix on both channels at -3.01 dB each, so integrated
  loudness holds. Mono stays the default (NV-2).
- With a bed on a card or still, the program runs to the last narration plus
  the music tail (5 s), so the fade-out follows the voice. `compose` (L6)
  renders the length `mix` records.

## Unknowns and next

- The sidechain threshold (-45 dBFS per 10 ms block) has not been compared on a
  real narration. The fixture voice is a sine.
- Listening acceptance, Content ID and delivery stay operator states. No stage
  marks them passed.
- L5: the kitpip pin record and the avatar stage in `run`, reading
  `voice/<segment>/narration/`. L6: `compose`, `deliver_check`, `handoff`.

## Review fixes (2026-10-27)

Authority: the PR #60 review findings relayed by the root workflow under
TIN-7476 and R-HOOK-CONVERGENCE-20261004 (R-N13).

| Finding | Change | Test |
| --- | --- | --- |
| `voice` stayed fresh after a pronunciation edit or an engine re-pin | `load_records` reads `engines.json` and `pronunciation.json`. The `voice` knobs hold the engine record (no endpoint, files by digest only) and the pronunciation table's id and digest. The `voice` tool's `binary_sha256` is the digest of the engine's sorted file digests | graph rows "pronunciation entry", "engine model", "engine files"; a real run where each edit reruns `voice/seg-1` and what follows |
| A stale persona in fresh `voice` and `voice_qa` manifests, then a recorded `label_chain_broken` | `voice` and `voice_qa` write no persona. It joins at `place`, whose knobs hold `labels.persona` | graph row "persona"; a real run: two persona changes and a `tailS` change each rerun `place` and `mix` only, with no refusal |
| `music` reported a licence state its key does not hold | The `music` manifest drops `states.licence`. The skill and draft 65 point to `pending_operator` in plan and status, which `deliver_check` decides | the music test asserts the states |
| No run-time bound on a bed layer's `tempoFactor` | `admit.bed_record` refuses `knob_out_of_bounds` outside `check.BED_TEMPO_RANGE` (0.5 to 2.0) | two admit rows; a real run refuses at admit with nothing run |

Open: `kitpip.run_avatar` (L3, used by L5) writes the persona into the
`avatar` labels, but the `avatar` knobs hold no persona. L5 should key it or
leave it to `avatar_check`.

Gates (`nix develop .#condense` in the bounded scope above):

| Check | Result |
| --- | --- |
| narrated-video graph, simple and types tests | 175 passed |
| `just narrate-test` | 894 passed, 1 skipped |
| `just narrate-lint`, `just narrate-dhall-check` | clean, exit 0 |
| `narrate/tests/stdlib_smoke.py`, `tests.test_public_tree`, `tests.test_timeline_contract` | 7 OK; 79 OK, 1 skipped |
| `just check` (`just test`) | 2207 tests: 26 failed, 7 errors, 151 skipped. The same marked-video, marked-compact, `test_media` AAC and `test_web_stack`/`test_web_runs_s3` failures as above. `scripts/doctor.py --require-media` exit 0 |
