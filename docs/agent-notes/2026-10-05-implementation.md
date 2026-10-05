# October 5 implementation receipt

Authority: operator-approved video-utils implementation; repository `AGENTS.md`;
R-HOOK-CONVERGENCE-20261004, TIN-3692 comment
`98cf680c-7299-4949-bfb2-60079053ad43`; R-N11/R-N12/R-N13.

Named lanes own separate files; root integrates, verifies, and publishes the
private GitHub repository and dedicated Tinyland Linear project. No sibling
repository, installed plugin, host daemon, or other live session is a mutation
target. No process escape hatch was required in the clip-baseline/docs lane.

## Measured baseline

Read-only inspection used FFmpeg 8.1.2 and Python standard-library PCM analysis.
The Documents source is `Movie on 10-5-26 at 3.38 PM.mov`: 150.954 s container
duration, H.264 1620×1080 at approximately 23.95 fps, mono AAC 44.1 kHz at
approximately 63 kb/s. A `loudnorm` scan measured −21.24 LUFS integrated,
−4.16 dBTP true peak, and 4.00 LU loudness range. In-memory decoding measured
150.961 s of audio. No derivative was written during this baseline pass.

The first 30 seconds showed high-frequency onset periodicity near 0.678 s.
88.50 BPM and half/double interpretations are candidates, not confirmed tempo.
Quiet-window RMS values came from a resampled 8 kHz analysis: 4–5 s was
−35.19 dBFS and 149–150 s was −34.55 dBFS. These are not verified noise-only
windows. No listening claim was made. The initially available Python did not
contain NumPy, SciPy, librosa, or SoundFile; later environment checks must record
their actual state separately.

## Implemented documentation and initial registry

The docs lane wrote the README, approved project specification, primary-source
research comparisons, this receipt, and an empty schema-version-1 model
registry. The specification records a 35-hour baseline for October 6–12 plus
35 optional hours: stems 8, rhythm 8, robustness 9, native AU spike 10.

The approved demo target is −18 LUFS / −1.5 dBTP. Fixed 3 dB FFT denoising at
a heuristic −40 dB floor requires A/B listening; bypass and mild6 are comparison profiles. Learned models, AU implementation, plugin repair, and automatic
wrong-note grading are not delivery claims.

Later operator steering fixes the instrument context: downtuned nine-string,
approximately 32 Hz lowest fundamental, deathcore and technical virtuoso playing.
Default filtering must preserve that range and intentional distortion. The week
adds versioned tool/MCP contracts, per-tool agent guidance, and tone/noise/note
pilots. Rhythm and phrase suggestions remain estimates; intended-note judgement
requires a reference.

The operator subsequently clarified **musical phrase** mistakes. The ordered
agent graph is denoise → click/BPM → tonic/mode and repeated-phrase confidence →
recurrence comparison → timestamp/span review flags for starts/ends, skips,
rushed passages, missing loops, and unclear riffs. Confirmed references qualify
correctness claims; tonic/mode can remain unknown. Twelve per-tool skills and the
local MCP stdio server are present; external client hookup remains separate.

Graphical video review and Final Cut/DaVinci Resolve marker compatibility are the
next milestone. A generic CSV is not an application-import acceptance receipt.
The specification requires original-timeline offsets, actual frame-rate/time
base, VFR/CFR identity, and explicit drop-frame/frame-rounding treatment. Graph
worker/render validation and application import evidence remain for root's
observed receipts. Revised graph/reference tasks fit within the same 35 hours.

## Integration receipts to append

At docs-lane handoff, root still owns the final build/test receipt, actual demo
run paths and output measurements, private remote visibility verification,
published Linear project/issue IDs, and final commit/push evidence. Append those
observed results here; do not promote a planned action to a completed one.

User listening acceptance remains separate even after a render passes numerical
checks. AU validation and Logic host acceptance require their own future runs.

## Root integration and actual demo receipt

Authority: operator-approved implementation plus nine-string/agent-DAG/musical-phrase
clarifications; R-HOOK-CONVERGENCE-20261004 / R-N11 R-N12 R-N13.

Observed private remote: https://github.com/Jesssullivan/video-utils (PRIVATE).
Linear project: https://linear.app/tinyland/project/video-utils-guitar-restoration-and-performance-analysis-243628f290ab .
D0 TIN-5485; D1–D7 TIN-5486 through TIN-5492; agent hooks TIN-5493;
future editor marker interoperability TIN-5494. Full approved current spec is
published as the project's content; the exact IDs are in program/linear.json.

Implementation: dependency-free Rust CLI and bounded gain DSP; conservative
FFmpeg worker; standard-library rhythm, noise, tone, periodicity and phrase
pilots; 12 actual typed stdio MCP hooks plus 12 validated repository skills;
hash-bound processing graph, optional approved-reference comparator, generic
markers, and local HTML report with manual seek controls. No installed AU,
learned tonic/mode classifier, neural separation, or native editor import claim.

Validation: 81 Python behavior/integration tests passed; seven Rust tests
passed; rustfmt check passed; staged secrets scan found no leaks. The actual
`just demo` invocation completed every media/rhythm/noise/tone/notes/phrases/DAG/
marker stage and generated its report. Optional Python analysis has a full
uv.lock (31 external dependencies with SHA-256 artifacts); offline lock check
passed without installation. Nix shells' package graphs evaluated, but those
shells were not realized or runtime-qualified. Actual local run: Python3.12.14,
FFmpeg8.1.2, Rust1.95.0. Pinned Nix currently supplies different versions.

Actual completed run: `artifacts/runs/20261005T203619Z-f94eb8eb2a1a`. Input SHA-256 `a522115f4e72e19384fb341bc84369728eceefe49183b8c6367a1008a95176c6`.

Source-rate working PCM: 44100Hz / 1channel / 6657385samples. Clean master -18.00LUFS / -1.50dBTP. Encoded video audio -18.01LUFS / -1.51dBTP. Final encoded peak target verified.

Actual picture verification: all 3631 ordered video packets preserve their
encoded payload SHA-256 and PTS/DTS/durations; maximum timestamp delta0. Decoded
frame counts are equal (3621 retained playable decoded frames on both inputs).
The MOV stream-duration header differs by-0.020s; recorded as diagnostic because
packet timing/picture are identical. Relative A/V start delta0; encoded audio
extent differs-0.000113s, within the explicitly recorded AAC tolerance.

Post-denoise fitted grid: 88.801BPM, limited periodic evidence; half/double ambiguity retained. This does not establish metronome identity or intended tempo. No expected-rhythm reference was supplied, so flags/markers are empty rather than invented missed-note or phrase judgments. Tonic/mode and intended notes remain unknown.

The early unnormalized quiet-window comparisons (4–5s and149–150s) reduced
RMS by about0.40/0.53dB; neither interval is confirmed noise-only. This is mild
processing and does not establish SNR improvement or better tone. User listening
and phrase/reference annotation remain separate acceptance steps.

## Advisory findings and owned process receipts

- Local-build wrapper warned on Neo. The authorized dependency-free Rust check
  used one Cargo job, lasted seconds and passed; no full Nix/ML build occurred.
  R-N12 advisory finding retained; no extra permission gate introduced.
- uv's managed wrapper rejected an explicit cache override (exit64). The
  traceable alternative resolved the lock with `--no-cache` and repo-local
  scratch, no install/interpreter download, then passed offline lock verification.
- actor repo_patterns | target own exact Nix evaluation PIDs3879/3885/3893/3894,
  live commands inspected | reason package graph output completed but processes
  lingered | R-HOOK-CONVERGENCE-20261004/R-N11 | prior_state completed drvPath
  output with live owned processes | result TERM only named owned targets,
  tools returned exit0/shutting down; no peer target signalled.
- MCP timeout behavior checks inspect actual new-worker pgid and signal only
  that invocation's owned process group. Structured R-N11 receipts accompany
  timeout errors. Tests do not stop shared services.

Original media and all local derivatives remain ignored. Durable spec, research,
source and these receipts are committed; no unrelated checkout was edited.
Git commit/push identity and browser preview are recorded in the final publication
receipt after their actual readback. User listening acceptance remains pending.
