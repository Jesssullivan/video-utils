# video-utils

Local-first restoration and rhythm analysis for guitar takes recorded on a phone
or in Photo Booth. Rust provides the CLI and reusable DSP; FFmpeg handles media;
bounded Python handles offline analysis; R and Quarto support research reports.

## Product axioms

This project centers **woodshedding and technical-guitar practice**: turn a room
recording into a clear, shareable clip with useful musical feedback for working
bands. Three axioms shape the implementation:

- **Technical playing drives detection.** Low-tuned riffs, fast subdivisions,
  palm mutes, intentional rests, sweeps, tapping and legato need phrase/rhythm
  review that preserves ambiguity and does not equate every attack with a note.
- **Agents participate in take processing.** Each tool exposes its intent,
  supported knobs, evidence and skill through MCP. Agents inspect capture/noise,
  research options, run bounded comparisons and retain the result and provenance.
- **Heavy distortion and unusual low tuning drive the defaults.** Protect the
  nine-string instrument's approximately32Hz fundamentals, saturated texture,
  pick attacks and sustain in denoising, dynamics, EQ and analysis benchmarks.

The intended output combines restored video, source-timed phrase/timing review,
BPM and uncertainty, listening comparisons, and optional estimated stems. A
musician should be able to communicate a riff or practice issue through a clip
and its evidence without assembling a large studio workflow. Stem estimation
remains an optional extension; a mono mixture does not identify original tracks.

Our product hypothesis is that this complete local, agent-guided practice
workflow is underserved. Existing products cover many individual features,
including practice video, stems, tempo, looping and custom nine-string notation;
the [dated landscape comparison](docs/research/PRACTICE_LANDSCAPE.md) records that
overlap and leaves specialized distorted-low-guitar accuracy unverified.
Automatic review markers remain hypotheses until musical intent and calibration
support stronger missed-beat, wrong-note or phrase-error judgments.

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

Project constants also include a **large box fan in the recording background**
and tone references **Lorna Shore, The Haunted, Meshuggah, Kublai Khan TX,
Mgła and Children of Bodom**. They guide string separation, low-string weight,
pick articulation and saturated texture. Store this context in
[program/capture-context.json](program/capture-context.json); measure the fan
spectrum and usable noise-capture interval per take. Artist references supply
context rather than an expected score or universal EQ curve. Restoration
comparisons include stronger captured-noise processing, controlled compression
and bounded EQ, with source preservation and listening review.

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
| `just marked-video RUN_DIR OUTPUT [SELECTION]` | Render a separate preview with phrase review callouts |
| `just clicks INPUT RUN_DIR [BPM]` | Detect click candidates without modifying audio |
| `just phrase-compare RUN_DIR` | Compare discovered recurring regions |
| `just benchmark OUTPUT [BACKEND] [SUITE]` | Evaluate generated technical-guitar fixtures |
| `just benchmark-fixtures OUTPUT [SUITE]` | Generate a component-labelled fixture bank |
| `just calibrate FIXTURES OUTPUT [BACKEND] [TIMEOUT]` | Run unseeded discovery, then evaluate generated truth |
| `just pitch-evaluate FIXTURES PILOT OUTPUT` | Score existing synthetic pitch receipts |
| `just phrase-evaluate FIXTURES PILOT OUTPUT` | Score existing synthetic phrase receipts |
| `just basic-pitch RUN_DIR [SECONDS]` | Compare sparse learned pitch hypotheses with a qualified local CPU runtime |
| `just basic-pitch-runtime-setup PYTHON` / `just basic-pitch-runtime-check` | Explicitly install or verify the isolated five-wheel CPU environment |
| `just capture-profile INPUT RUN_DIR REVIEW START END` | Author fresh source-bound settings without rendering audio |
| `just editor-marker-plan RUN_DIR SELECTION PROFILE` | Plan source-timed editor metadata; native import remains unverified |
| `just holdout-plan OUTPUT` / `just holdout-validate PLAN` | Declare or verify the fixed generated holdout design |
| `just holdout-generate PLAN OUTPUT [TIMEOUT]` | Generate the declared component bank without inference |
| `just review RUN_DIR [PORT]` | Open a local video/audio review and annotation screen |
| `just pitch INPUT RUN_DIR [SECONDS]` | Inspect bounded pitch candidates including the ending |
| `just meter RUN_DIR` | Rank metrical hypotheses or retain unknown |
| `just tonal RUN_DIR` | Inspect tonal collection hypotheses with abstention |
| `just evaluate RUN_DIR [BPM] [BACKEND] [SECONDS]` | Extend an existing validated render through optional evidence tools |
| `just corpus MANIFEST [LOCAL_ROOT]` | Validate sparse review metadata without reading audio |
| `just au-state-check` | Check isolated native parameter-state behavior |
| `just au-spike-check` | Check the compiled Darwin development scaffold |
| `just au-package-plan` / `just au-package-check` | Inspect the AUv3 development bundle plan and contracts |
| `just au-package-build` | Build a development bundle without installation or host activation |
| `just au-automation-check` | Check isolated native event/ramp behavior |

The conservative demo target is **−18 LUFS integrated / −1.5 dBTP**, with source
sample rate, channel count, and timeline retained. Its fixed denoising heuristic
is an audition candidate, not a measured noise-only profile. The `bypass` and `mild6` profiles provide listening comparisons. Plain HTML reporting is
available without Quarto; Quarto/R reports are optional.

BPM and click detections are estimates. The operator states the metronome was
approximately **178 BPM**; the fitted periodic grid supports approximately
**177.6 BPM** at that interpretation. Automatic phrase/bar/breakdown discovery
does not require a predeclared song or intended arrangement. Missing or extra
notes become definite mistakes only against an approved reference. Improved guitar tone requires user listening
acceptance; measurements alone do not establish it. The native AU development scaffold
has compiled ABI and lifecycle checks; Logic hosting remains a separate validation
milestone. Model inference is optional. The registry now includes a hash-qualified
official Basic Pitch ONNX artifact; downloading it through `model-prefetch` is
explicit. Its isolated CPU runtime is separately qualified and required for
`basic-pitch`; the baseline demo never installs it. Runtime success does not
establish accurate distorted C1 notes, and the generated missing-fundamental
pilot failed C1 identification. Explicit setup requires an existing CPython 3.14.6
on native macOS arm64, macOS 14 or newer, and downloads only the five pinned wheels;
it leaves the main analysis environment intact. Run `just model-prefetch
spotify-basic-pitch-0.4.0-onnx`, then `just basic-pitch-runtime-setup /path/to/python3.14`
and `just basic-pitch-runtime-check`. See [runtime qualification](docs/research/BASIC_PITCH_QUALIFICATION.md).

The repository includes a versioned tool contract, a local MCP stdio server,
and twenty-six per-tool skills for researching and tuning restoration, analysis, comparison, and review.
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

Local graphical review is available through `just review RUN_DIR`, with manual playback,
marker filtering and source-bound annotations. Final Cut/DaVinci Resolve marker compatibility is the
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
VIDEO_UTILS_ANALYSIS_PYTHON="$PWD/.venv/bin/python" just demo INPUT 178 librosa extended
```

Today's operator requests are preserved in [the prompt record](docs/agent-notes/2026-10-05-user-prompts.md).
The active [ten-hour work plan](docs/spec/TEN_HOUR_PLAN.md) and
[parallel lane board](docs/agent-notes/WORKSTREAM_BOARD.md) define ownership and checkpoints.

The actual local comparison report includes manual audio/video seeking to review
spans. `just marked-video` renders separate synchronized previews with uncertain
review callouts. Native editor imports remain a future milestone.

For an already rendered take, run the optional evidence workflow without encoding
media again:

```bash
VIDEO_UTILS_ANALYSIS_PYTHON="$PWD/.venv/bin/python" just evaluate RUN_DIR 178 librosa 20
```

It preserves a bounded snapshot before analysis changes, uses exact returned
receipt paths for graph selections, and records failures without discarding the
master. Dependency/model installation remains explicit. The `pipeline` MCP tool
evaluates these receipts; the CLI workflow executes the tools.
