---
name: narrated-video-mix
description: Mix placed narration, kept clip sound and a ducked music bed through one limiter, with the loudness gates checked.
---

# Let an agent compare bed level and duck settings at matched voice loudness, with every delivery gate measured.

**Hook:** MCP tool `narrated_video_mix` (proposed as tool 68, drafted in `program/tool-drafts/narrated_video.json`, not yet admitted). Fallback: `just nv-stage JOB mix` or `just nv-run JOB`, inside `nix develop .#condense`.

**Capability:** the `mix` stage re-measures the placed voice (EBU R128) and refuses `foreground_not_normalised` when it is further than `driftLu` from `targetLufs`; nothing loudness-normalises the voice or the mix. It tiles the bed to the program's length, sets it `bedBelowVoiceLu` under the measured voice, and ducks it `duckDb` under the foreground: `Sidechain` keys on voice plus kept clip sound (-45 dBFS per 10 ms block), `EdlEnvelope` on the placed segments. The gain moves `duckDb` per `attackMs` down and per `releaseMs` back up. The bed fades `fadeInS` in and `fadeOutS` out. One limiter sits 0.5 dB under `truePeakDbtp`. The mix is measured: drift over `driftLu` refuses `loudness_drift`, and a true peak above `truePeakDbtp` refuses `true_peak_exceeded`. Outputs: `mix.wav`, `bed-ducked.wav` (before the limiter) and `mix.json`.

## Use and controls

1. `place` and, with a bed, `music` must be fresh (`narrated-video-place`, `music-bed`).
2. `just nv-stage JOB mix`, then read `integrated_lufs`, `drift_lu`, `true_peak_dbtp`, `voice_integrated_lufs`, `bed_gain_db`, `duck_depth_db`, `flags` and `gates`.
3. Change one knob in the job and run again: only `mix` reruns.

Defaults (NV-2, the deck project's ruling 58): bed 20 LU under the voice, duck 7 dB, attack 50 ms, release 400 ms, fades 3 s in and 5 s out, -16 LUFS, -1.5 dBTP, drift 0.5 LU, mono. Knobs worth comparing: `duckDb` (6 to 8), `bedBelowVoiceLu`, `duckMode`, `attackMs`. A depth outside 6 to 8 dB adds `duck_outside_6_8_db`; the deck playbook's gate, at least 3 dB, is `gates.duck_min_3db`.

## Speech, not guitar

Speech workflow, not a guitar default: the guitar axioms in AGENTS.md do not apply. The mix manifest writes `no_time_stretch: false` with mapping `narrated_video_v1`, so every guitar tool refuses it. Labels only grow; a stage that drops one refuses `label_chain_broken`.

## Limits

- `duck_depth_db` is the median gain the stage applied over keyed blocks: a measurement, not a listening result. Listening stays `pending_operator`.
- `Stereo` writes the mono mix on both channels at -3.01 dB each, so the integrated loudness holds. Mono is the default until an A/B (NV-2).
- The sidechain threshold is a starting value, not yet compared on a real narration with breaths and room tone.
- No mix, stem or bed audio enters git. Results carry ids, keys and numbers.

## Agent iteration

Change one knob, run `mix`, and compare the two `mix.json` files at the same `voice_integrated_lufs`. Record the comparison as a dated receipt in `docs/agent-notes/` with job ids, stage keys and measurements only: no audio, transcript, store path or host name.
