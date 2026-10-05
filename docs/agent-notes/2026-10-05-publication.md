# First private publication receipt

Authority: operator implementation, fanout, tuning and ten-hour goal requests;
R-HOOK-CONVERGENCE-20261004 / R-N12 / R-N13; repository AGENTS.md.

Observed publication at 2026-10-05 around21:00UTC:
- Private repository https://github.com/Jesssullivan/video-utils .
- Signed initial commit3dfa44ddbcd6cdb2788aee5265f35c65375b3f0d.
- Signed analysis/plan commitbe085b4316c27ba59d66091a01480493ed9c996d.
- `git push -u origin main` succeeded. GitHub's commit API readback returned the
  latter exact SHA with signature verification true. Repository readback returned
  isPrivate:true. Git's direct-main advisory was recorded as advisory underR-N12.
- Hosted CI run37373112479 initially was in_progress, then failed a strict-JSON
  nesting test on Python3.14.7: its parser accepted10kdepth instead of raising
  RecursionError. The worker now imposes an explicit deterministic128level bound;
  a separate repair commit/run verifies that fix. The failed run exercised109
  tests with three optional-librosa skips. Local/hosted/backend states remain
  separate; this receipt is no hosted-pass claim.

108 full Python tests passed with the locked optional environment and explicit
FFmpeg binaries. Subsequent strict-JSON hardening passed27targeted tool/MCP tests
with no skips after explicit media-tool configuration. Unchanged Rust source has
seven passing tests and rustfmt. Staged secrets scan found no leaks; diff whitespace
checks passed. Independent first-release review found no blocker. Its older phrase
tempo-context nit was corrected by rerunning phrases after rhythm, then DAG,
markers and report; source/derivative/graph hashes verify. Its marker upstream-
staleness hardening suggestion is being implemented in the next owned lane.

Actual local run: artifacts/runs/20261005T203619Z-f94eb8eb2a1a .
Audition cleaned.wav, export/cleaned-video.mov and report.html. Media stays ignored
and was not uploaded to GitHub/Linear. Source SHA is
`a522115f4e72e19384fb341bc84369728eceefe49183b8c6367a1008a95176c6`.
Master−18.00LUFS/−1.50dBTP; encoded audio−18.01LUFS/−1.51dBTP.
Source44100Hz mono6657385samples retained;3631picture packets and all timestamps
preserved,3621decodedframes on both inputs. Detailed diagnostic/tolerance results
are in the implementation receipt and private manifest.

Automatic discovery without a score yielded47regions/10recurrence pairs and
177navigation/review markers. Operator178BPM is separate from observed fallback
88.800719BPM/double interpretation177.601438BPM. Tuning is constant C F Bb Eb Bb
Eb Ab C F, with inferred C1..F4 octaves and theoretical frequencies; highestF4
349.228Hz. Hypotheses remain ungraded; listening/meter/tonic/mode/intended-note
correctness, native editor import and AU/Logic acceptance are not established.

Today's prompts and ten-hour plan are durable and published. Goal start
2026-10-05T20:49:34Z; planned end2026-10-06T06:49:34Z (2:49amEDT). Active goal,
not completed. The named next lanes are recorded in WORKSTREAM_BOARD.md; their
uncommitted new work is separate from this tested first publication.

Linear D0TIN-5485 is In Review for listening, while goalTIN-5495 is In Progress.
Project content and D4/D5 definitions reflect automatic discovery without intent
and optional qualified correctness grading. Exact issue/project IDs and comment
receipts are mirrored in program/linear.json.

- TIN-5485 factual comment: 9d2e2ef7-6b74-49b3-972c-d75bd2884804 (https://linear.app/tinyland/issue/TIN-5485/d0-first-cleaned-guitar-wavvideo-and-matched-listening-report#comment-9d2e2ef7).
- TIN-5495 factual comment: 353d44f7-02e8-4706-83d7-8b3e61232060 (https://linear.app/tinyland/issue/TIN-5495/ten-hour-parallel-guitar-toolkit-implementation-goal#comment-353d44f7).

## New benchmark finding after first publication

The next owned benchmark lane measured all three synthetic fixtures: source
click recall1.0 within20ms, post-denoise recall0.0 at that tolerance. Detected
source-to-denoised candidate times shift+25ms (2.5ms→27.5ms relative to generated
truth). This is evidence of processing/detector latency requiring qualified
accounting, not a performance mistake. Source/container/picture checks remain
valid; they do not prove physical audio-event alignment. A new media_latency
lane owns independent waveform/chain measurements and any explicit compensation
before a new render. Existing unreviewed media is preserved. Absolute correctness
grading remains unavailable pending calibration. Strong32Hz coherent gain is
approximately0.000031dB; quiet RMS falls3.44–3.47dB in generated noise fixtures;
these are synthetic measurements, not listening or real-take SNR acceptance.
