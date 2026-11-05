---
name: music-bed
description: Arrange an operator-acquired music bed from its loops by digest, reproducibly, with its licence gates recorded.
---

# Let an agent build the bed the operator acquired, without ever fetching, searching for or buying a loop.

**Hook:** MCP tool `music_bed_build` (proposed as tool 65, drafted in `program/tool-drafts/narrated_video.json`, not yet admitted). Fallback: `just nv-stage JOB music`, inside `nix develop .#condense`.

**Capability:** the `music` stage reads the job's `MusicBed` record (2 or 3 loops, each by SHA-256 with its byte count, rate, channels, tempo factor and gain). It finds each loop in the private store by digest, checks its byte count, converts it to 48 kHz mono with its gain and, only when the tempo factor is not 1, one FFmpeg `atempo`. The layers are summed into one cycle: the least common multiple of their lengths up to 120 s, so every loop repeats whole, else the longest layer (`cycle_rule: longest`). A sum that would clip is scaled down as a whole (`headroom_gain_db`). It writes `bed.wav` and `bed.json`, and measures the cycle's integrated loudness for `mix`.

## Use and controls

1. The operator acquires the loops and writes the private record (`narrate/dhall/MusicBed.dhall`, `acquiredBy = Operator`, the ruling that allowed the spend). The record and the loops stay in the private store.
2. Name the bed in the job (`init --bed ID`) and run `just nv-stage JOB music`.
3. Read `cycle_s`, `cycle_rule`, `headroom_gain_db` and `integrated_lufs` in the stage manifest. The bed's level under the voice is set in `mix`, not here.

Knobs live in the private record: each layer's `gainDb` and `tempoFactor` (0.5 to 2.0). A tempo factor other than 1 sets `stretch_applied: true` in the `music_bed_v1` timeline.

## Speech, not guitar

The bed sits under a speech workflow; the guitar axioms in AGENTS.md do not apply. The stage manifest writes `no_time_stretch: false` with mapping `music_bed_v1`, so no guitar tool accepts it.

## Limits

- Never purchase, search for or download a loop, and spend no credits: only the operator acquires a bed, and a record that says otherwise refuses `bed_acquisition_agent`. No argument takes a URL.
- A loop off its record refuses `bed_digest_mismatch`. A loop missing from the store is a failure, not recorded.
- No public upload until the record holds the certified licence PDF digest and a clear Content ID result. `music` records no licence state: read the open gates from `pending_operator` in `nv-plan` or `nv-status`, which `deliver_check` decides. A client edition also needs a voice-only listen.
- No loop, bed audio, loop name, vendor stack or asset id enters git, CI or logs. Layers are named by digest.

## Agent iteration

Compare two records' cycles by loudness and cycle length, then compare their mixes (`narrated-video-mix`) at matched voice loudness. Record the comparison in `docs/agent-notes/` with record ids and digests only.
