# video-utils

Local-first restoration and rhythm analysis for guitar takes recorded on a phone
or in Photo Booth. Rust provides the CLI and reusable DSP; FFmpeg handles media;
bounded Python handles offline analysis; R and Quarto support research reports.

The reference instrument is a downtuned nine-string guitar reaching approximately
32 Hz. Restoration must preserve its low fundamentals, palm-mute weight, and
intentional distortion; low-frequency energy is not automatically noise.

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
| `just dag RUN_DIR [REFERENCE]` | Verify graph ancestry and compare an approved reference |
| `just markers RUN_DIR` | Export generic timestamp/span review markers |

The conservative demo target is **−18 LUFS integrated / −1.5 dBTP**, with source
sample rate, channel count, and timeline retained. Its fixed denoising heuristic
is an audition candidate, not a measured noise-only profile. The `bypass` and `mild6` profiles provide listening comparisons. Plain HTML reporting is
available without Quarto; Quarto/R reports are optional.

BPM and click detections are estimates. Missing or extra notes require an
approved expected-rhythm reference. Improved guitar tone requires user listening
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
requested mistakes concern **musical phrases**. Expected starts/ends, skips,
rushed passages, missing loops, and unclear riffs need a confirmed musical
reference before they become error verdicts. Tonic/mode may remain unknown.

Graphical video review and Final Cut/DaVinci Resolve marker compatibility are the
next development milestone. Initial generic marker data does not establish that
either editor can import it. Timeline, frame-rate, and drop-frame handling need
an explicit format spike and application validation.

Optional music-research dependencies are fully pinned in `uv.lock`.
Run `just analysis-setup` to install that environment explicitly, then use
`uv run --frozen python scripts/rhythm.py INPUT --backend librosa --run-dir RUN_DIR`.
The baseline demo does not require those packages.

The actual local comparison report includes manual audio/video seeking to review
spans. Native editor imports and video overlays remain a future milestone.
