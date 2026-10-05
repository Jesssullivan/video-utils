# video-utils

Local-first restoration and rhythm analysis for guitar takes recorded on a phone
or in Photo Booth. Rust provides the CLI and reusable DSP; FFmpeg handles media;
bounded Python handles offline analysis; R and Quarto support research reports.

The reference instrument is a downtuned nine-string guitar reaching approximately
32 Hz. Restoration must preserve its low fundamentals, palm-mute weight, and
intentional distortion; low-frequency energy is not automatically noise.

The operator's constant tuning, lowest to highest, is **C F Bb Eb Bb Eb Ab C F**.
Octaves below are inferred from the approximately 32 Hz low string, the high F
being a semitone above standard high E4, and ascending string order. Frequencies
are theoretical A4=440 Hz values, not measurements or identified played notes.

| String | Open note (octave inferred) | MIDI | Theoretical Hz |
| --- | --- | ---: | ---: |
| 9 (lowest) | C1 | 24 | 32.70 |
| 8 | F1 | 29 | 43.65 |
| 7 | Bb1 | 34 | 58.27 |
| 6 | Eb2 | 39 | 77.78 |
| 5 | Bb2 | 46 | 116.54 |
| 4 | Eb3 | 51 | 155.56 |
| 3 | Ab3 | 56 | 207.65 |
| 2 | C4 | 60 | 261.63 |
| 1 (highest) | F4 | 65 | 349.23 |

The Eb2→Bb2 interval is intentional metadata; preserve the supplied tuning.
Machine-readable context lives in [program/instrument.json](program/instrument.json).
Frequency/MIDI calculation follows [UNSW's note reference](https://phys.unsw.edu.au/jw/notes.html);
[Fender's standard-tuning reference](https://www.fender.com/articles/setup/standard-tuning-how-eadgbe-came-to-be)
provides the standard high-E context.

Source repository: [Jesssullivan/video-utils](https://github.com/Jesssullivan/video-utils)
(private). The approved [project specification](docs/spec/PROJECT.md) separates
the October 5 demo from the October 6–12 development plan. Primary-source
comparisons live in [research](docs/research/RESEARCH.md); tracker receipts live in
[`program/linear.json`](program/linear.json).

[Linear project and week schedule](https://linear.app/tinyland/project/video-utils-guitar-restoration-and-performance-analysis-243628f290ab).

## Quickstart

```bash
nix develop
just doctor
just demo "$HOME/Documents/Movie on 10-5-26 at 3.38 PM.mov"
```

`FFMPEG` and `FFPROBE` may name explicit executables; otherwise tools are found
on `PATH`. `just doctor` checks the available toolchain. Keep recordings outside
Git. Runs write local, ignored artifacts under `artifacts/runs/` and never
overwrite the input.

## Recipes

| Recipe | Purpose |
| --- | --- |
| `just doctor` | Inspect tools and optional capabilities |
| `just demo INPUT` | Clean/export the take, analyze rhythm, and build its report |
| `just clean INPUT PROFILE` | Render a named restoration profile |
| `just analyze INPUT` | Estimate rhythm with uncertainty |
| `just report RUN_DIR` | Build a report from an existing run |
| `just export RUN_DIR` | Export delivery artifacts from an existing run |
| `just test` / `just check` | Run behavior tests / source checks |
| `just model-prefetch MODEL` | Fetch only a registered, hash-qualified model |
| `just mcp` / `just tool-info NAME` | Serve agent hooks / inspect the schema |
| `just tool-run NAME JSON` | Invoke a tool through its typed contract |
| `just dag RUN_DIR [REFERENCE]` | Verify ancestry, review self-consistency, optionally compare a reference |
| `just markers RUN_DIR` | Export generic timestamp/span review markers |

The conservative demo target is **−18 LUFS integrated / −1.5 dBTP**, with source
sample rate, channel count, and timeline retained. Its fixed denoising heuristic
is an audition candidate, not a measured noise-only profile. The `bypass` and `mild6` profiles provide listening comparisons. Plain HTML reporting is
available without Quarto; Quarto/R reports are optional.

BPM and click detections are estimates. The operator states the metronome was
approximately **178 BPM**; the fitted periodic grid supports approximately
**177.6 BPM** at that interpretation. Automatic phrase/bar/breakdown discovery
does not require a predeclared song or intended arrangement. Missing or extra
notes become definite mistakes only against an approved reference. Improved guitar tone requires user listening
acceptance; measurements alone do not establish it. No Apple AU is implemented,
and this project does not repair installed plugins. Model inference is optional:
the initial registry contains no downloaded, hash-qualified models.

The repository includes a versioned tool contract, a local MCP stdio server,
and twelve per-tool skills for researching and tuning tone, noise, and note analysis.
Inspect `just tool-info NAME` or launch
`just mcp` from the repository root. Local invocation is
separate from connecting an external agent client; see
[agent tools](docs/spec/AGENT_TOOLS.md).

The processing graph follows denoise → click/BPM → tonic/mode and repeated-phrase
candidates → recurrence comparison → timestamp/span review flags. The user's
requested mistakes concern **musical phrases**. Features and recurrence discover
candidate boundaries, repeated riffs, bar groupings, and breakdowns automatically;
internal self-consistency can flag timestamped spans for review. A confirmed
reference is needed for definite error verdicts, not for discovery or review
flags. Tonic/mode and meter may remain unknown; four-bar phrases are not assumed.

Graphical video review and Final Cut/DaVinci Resolve marker compatibility are the
next development milestone. Initial generic marker data does not establish that
either editor can import it. Timeline, frame-rate, and drop-frame handling need
an explicit format spike and application validation.

Optional music-research dependencies are fully pinned in `uv.lock`.
Run `just analysis-setup` to install that environment explicitly, then use
`uv run --frozen python scripts/rhythm.py INPUT --backend librosa --run-dir RUN_DIR`.
The baseline demo does not require those packages.

To reproduce the richer pass with an approximate 178 BPM operator seed:

```bash
just analysis-setup
VIDEO_UTILS_ANALYSIS_PYTHON="$PWD/.venv/bin/python" just demo INPUT 178 librosa
```

Today's operator requests are preserved in [the prompt record](docs/agent-notes/2026-10-05-user-prompts.md).
The active [ten-hour work plan](docs/spec/TEN_HOUR_PLAN.md) and
[parallel lane board](docs/agent-notes/WORKSTREAM_BOARD.md) define ownership and checkpoints.

The actual local comparison report includes manual audio/video seeking to review
spans. Native editor imports and video overlays remain a future milestone.
