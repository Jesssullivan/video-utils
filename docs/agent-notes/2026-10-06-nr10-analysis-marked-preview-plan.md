# NR10 candidate analysis and marked-preview preflight

Preparation only. Owner `clip_baseline`; root assigned source/recipe readback
and a bounded plan while the separately released matched NR8/NR10 render runs.
Authority: repository AGENTS.md and R-HOOK-CONVERGENCE-20261004 R-N13. Only
this new receipt is written. No analysis, model inference, decoding, preview
render, source edits or candidate/latest promotion is authorized by this plan.
Root must explicitly release the exact selected candidate workflow after
checking structural delivery and comparison evidence. NR10 remains a possible
separate audition candidate, not an accepted tone/master.

Applied skills: `.agents/skills/guitar-pipeline/SKILL.md` and
`.agents/skills/guitar-marked-video/SKILL.md`.

## Read-only findings and entrypoint

`scripts/run_demo.py` already supports extending an existing verified run,
fresh post-denoise analysis, explicit optional interpreter and
`--no-latest`. No source change is needed. **Do not use `just evaluate` for
this release:** its current recipe omits `--no-latest`, so successful report
generation would overwrite `artifacts/latest.json`. Use the direct existing
CLI below; marked rendering can use the existing typed `just tool-run` hook.

Existing-run mode validates the selected run's source, pure-denoised and
cleaned hashes/native PCM extent; archives only existing derived allowlisted
artifacts; and reuses an existing hash-bound delivery export. It does not
create a missing export. Every analysis stage consumes the selected
`denoised.wav`, before its EQ/compressor/loudness delivery stages. Old NR8,
old 232741 run, masters, report and latest pointer remain separate. Do not
copy old analyses or bind old selectors to a new denoised hash.

The matched application controller is currently the owner of rendering.
Read its immutable verified summary/receipt after completion to obtain
`NR10.result.run_dir`; do not infer a candidate directory from staging files
or an incomplete stdout JSON. At preparation time the NR10 run path,
pure-denoised hash, master hash and export hashes are **pending**. Freeze all
of them and the source below in root's exact execution release.

## Planned commands after root release

`CANDIDATE_RUN_DIR` means the exact verified NR10 directory returned by the
matched application receipt, beneath `artifacts/runs`. It is not the old
`20261005T232741Z-2b5dc43fd009` run. Use the existing FFmpeg/ffprobe binaries
and optional analysis environment; no setup/install/model-prefetch command.

```sh
export FFMPEG=/nix/store/mv3x2v2pr6pwvwj7cdyh8nci2q1wpnjq-ffmpeg-headless-8.1.2-bin/bin/ffmpeg
export FFPROBE=/nix/store/mv3x2v2pr6pwvwj7cdyh8nci2q1wpnjq-ffmpeg-headless-8.1.2-bin/bin/ffprobe
python3 scripts/run_demo.py --existing-run "$CANDIDATE_RUN_DIR" --features extended --backend librosa --analysis-python /Users/jess/git/video-utils/.venv/bin/python --pitch-seconds 20 --bpm 178 --no-latest
```

After a successful analysis receipt with no failed/skipped dependency stages,
inspect `dag.json`, flags and marker counts before rendering. The exact fresh
output directory must not exist. Submit the following structured argument
object through the existing `marked_video` tool (`just tool-run marked_video
'<JSON>'` or MCP):

```json
{
  "run_dir": "<exact verified NR10 directory>",
  "output": "<same NR10 directory>/marked-preview",
  "selection": "phrase-review",
  "timeout_seconds": 900
}
```

The workflow already runs `dag.py`, `markers.py` and `report.py`. Do not
duplicate them gratuitously. If root instead releases separate primitives,
equivalent source-backed stage commands are:

```sh
.venv/bin/python scripts/rhythm.py "$CANDIDATE_RUN_DIR/denoised.wav" --run-dir "$CANDIDATE_RUN_DIR" --backend librosa --bpm 178
python3 scripts/guitar_features.py noise "$CANDIDATE_RUN_DIR/denoised.wav" --run-dir "$CANDIDATE_RUN_DIR"
python3 scripts/guitar_features.py tone "$CANDIDATE_RUN_DIR/denoised.wav" --run-dir "$CANDIDATE_RUN_DIR"
python3 scripts/guitar_features.py notes "$CANDIDATE_RUN_DIR/denoised.wav" --run-dir "$CANDIDATE_RUN_DIR"
.venv/bin/python scripts/guitar_features.py phrases "$CANDIDATE_RUN_DIR/denoised.wav" --run-dir "$CANDIDATE_RUN_DIR" --backend librosa --bpm 178
.venv/bin/python scripts/clicks.py "$CANDIDATE_RUN_DIR/denoised.wav" --run-dir "$CANDIDATE_RUN_DIR" --bpm 178
.venv/bin/python scripts/pitch.py "$CANDIDATE_RUN_DIR/denoised.wav" --run-dir "$CANDIDATE_RUN_DIR" --max-analysis-seconds 20
python3 scripts/meter.py --run-dir "$CANDIDATE_RUN_DIR"
python3 scripts/tonal.py "$CANDIDATE_RUN_DIR"
python3 scripts/phrase_compare.py "$CANDIDATE_RUN_DIR"
```

Then pass only the exact paths returned by these five optional producers to
`dag.py --clicks-artifact ... --pitch-artifact ... --meter-artifact ...
--tonal-artifact ... --comparisons-artifact ...`, followed by `markers.py`
and `report.py`. Selectors are relative to that same new run; do not guess
timestamps or choose an implicit newest file. The orchestrator handles this
binding automatically and is the preferred existing implementation.

## Dependencies, coverage and source axis

```text
Verified candidate source/manifest + denoised.wav + native extent
  -> rhythm + noise/tone/notes + automatic phrases
  -> clicks + sparse dual-resolution pYIN
  -> meter(rhythm), tonal(rhythm+phrases+pitch), recurrence comparison(rhythm+phrases)
  -> DAG(exact newly returned selectors and hashes)
  -> flags -> generic markers -> report
Verified candidate export/cleaned-video.mov + current DAG/flags/markers
  -> separate marked-preview: picture reencode, exact delivery AAC packet copy
```

Operator BPM prior remains approximately 178, not expected note attacks,
confirmed meter or a reference score. Full-duration rhythm/features/phrase
discovery remain automatic. Notes are sparse autocorrelation hypotheses,
at most 120 sampled frames; pYIN has a 20-second aggregate budget in four
five-second distributed excerpts. For decoded native duration 150.961111
seconds the unquantized pYIN starts are approximately 0, 48.6537, 97.3074
and 145.9611 seconds; actual 16 kHz quantized spans must come from the fresh
receipt. Its 4096-sample low branch (28–500 Hz) and 1024-sample high branch
(200–2000 Hz) retain edges, octave alternatives and abstentions. This is not
full-song transcription; no Basic Pitch/learned-model inference or download
is planned. No new L1 localization default is selected; the separate
localization experiment/fresh numerical evaluation remains future work.

Expected native PCM is mono 44100 Hz, 6657385 samples (150.961111 seconds).
Original source audio/container origin is 0 seconds in existing qualified
receipts. Analyze source-axis seconds via hash-bound derivative/no-stretch
manifest mapping; do not shift onsets to the rendered preview, use average
FPS or fit physical capture latency. Expected original video is VFR, with
3621 decoded frames and last picture extent 150.885 seconds in the prior
qualified export. Reverify exact NR10 export frame PTS/extent; decoded PCM
and container/picture tails are distinct. Physical A/V sync remains unknown.

Require DAG `post_denoise` ancestry tied to the **new** denoised SHA, all
five explicitly selected slots `verified`, and no stale/rejected selections
silently interpreted by the report. Definite performance grading is absent:
phrases, low-register riffs, recurrence timing differences and meter/tonal
candidates can be uncertain or null. Automatic findings are musical review
hypotheses, not confirmed skips/rushes/missed notes.

`phrase-review` excludes four-pulse navigation proxies and selects at most
128 uncertain phrase/comparison markers. The preview displays at most two
callouts; overlap suppression and all exclusions must remain in
`selection.json`. Empty supported picture selection fails. Subtitle timing
is quantized to 10 ms; point markers get a one-second presentation dwell.
Preview verification must retain decoded frame PTS/count/tail, rate/channels,
AAC packet payload/timing/priming/padding and decoded delivery PCM identity.
Inspect supported candidate stills/visibility separately; prior visual review
of three old-preview stills does not qualify a fresh preview. Native editor
import, Logic acceptance, musical correctness and listening remain unverified.

## Wall-time limits and checkpoints

Root's latest preparation steering reported approximately 3 hours 35 minutes
remaining in the active goal. Treat that as dated planning context, not a
fresh clock measurement; root should recheck remaining time at release.
The plan fits historically observed work, while hard-stage ceilings and
retained failures remain explicit. No elapsed-time assumption releases work.

Existing-run orchestrator hard stage limits are five base stages ×600 seconds,
five optional stages ×300 seconds and DAG/markers/report ×180 seconds:
**5040 seconds of worker ceilings**, plus bounded validation/snapshot and
cleanup overhead. This is not a 900-second overall workflow timeout. Inner
FFmpeg decoding/probing and pYIN child work are bounded; the orchestrator
caps numerical threads at two and each stream at 2 MiB.

The prior same-source extended run measured 26.32 seconds rhythm, 17.91
seconds sparse pYIN and about 68.86 seconds total analysis stages. These are
historical observations, not a deadline guarantee for the new input/runtime.
If root requires a smaller overall budget, release a separately owned
controller that allocates remaining stage deadlines and cleans up its
recorded workers; do not simply kill the orchestrator's parent group while
its stage workers use separate owned sessions.

For marked rendering use the shared 900-second tool deadline, whose inner
encoder ceiling is 600 seconds and metadata/PCM inspections are individually
bounded. The historical old preview's recorded subprocesses total about
167.42 seconds, including 103.81-second picture encoding. No automatic retry
on failure; retain receipts and diagnose within root's remaining goal budget.

Checkpoints: (1) selected run/native/master/export/source pins and unchanged
old protected hashes; (2) fresh full analysis receipt, exact selections and
coverage; (3) current DAG/marker evidence and proposed visibility; (4) separate
verified preview and sampled visual check; (5) unchanged old/source/latest
hash readback and root publication. No new listening/master acceptance is
inferred at any checkpoint.

## Preparation pins

Preflight repository HEAD is `6d021e515823e5397e090ba31213b049370dda2a`.
The original source pin from root's matched release is
`a522115f4e72e19384fb341bc84369728eceefe49183b8c6367a1008a95176c6`;
its decoded source pin is
`d68e49688293b1fb8c7c2566e2ecd6e31df9972af013dd23454e15864654bd2a`.
NR10 authoring profile SHA is
`3b5eccabb4121fb74bb1eb27cfcda1d5c207bb84bc1b713106d8005a0266c0cd`,
authoring receipt SHA is
`8b3efebe248d3895f5a7872992d953311e06f67a95618e4275d3c4a3fdfab474`.
Pure denoised/master/export hashes are pending matched-render completion.
These are declared input pins, not a claim this preparation reverified audio.

| Current source | SHA-256 |
| --- | --- |
| run_demo.py | `3c03bd68b9bdb77f13e3721db44430aff51c1315e8cfaa09b68a0baea278f23c` |
| rhythm.py | `264b723ca29e4731da0a12d5dce221e7826a38b67f848ce9f4ffcf8bfe4b35b9` |
| guitar_features.py | `2ed031e8000cbcda92b504db10c98de03f456c90573cbff815cbb940c9ac86fe` |
| clicks.py | `31bfd45ea482da53255189cecd7e4bf9ce3e31d822ba9c940a9158e33a902c2f` |
| pitch.py | `22038c7c1a6747f57397e2faa02cb5af438a24a12b2701ddf452304115cddc7b` |
| meter.py | `210ce3e79e624aa490e63dab1c27b72d2cf1ea3931b1e1ce8e0ec060f60a8fe6` |
| tonal.py | `4d3c99b009bbea19cebe818d237ba0057385d83ceb905dd0a900febfb9f329c5` |
| phrase_compare.py | `0ec3f18c0bf72dc1a33745ff19d7517f84db6103e3515ac727cb459195abf475` |
| dag.py | `1776968a74417e8db7c0e7b17500c3ebe02cc04de5224dd2957bc6c6cfdcc445` |
| markers.py | `fdbaa69d43e7d752587db8aa18f12f6fd7d14e4ed76f0804bbf8e2c69d52533a` |
| report.py | `3beb1b502dfd98c64e015e1f93d81e8c0f3ee81d912b9b3b9f3dc25426950b73` |
| marked_video.py | `a39280f22b60814b31a7f1bff2bfce693aacfa3e82c148df82a3513862fba300` |
| program/instrument.json | `bd381207d6615814ebee694148357c00719739ec900aa69c96d71b20779707b0` |
| program/models.json | `ff3d4251a089ca81e6c6a2e7bcbe67023fa52be4f687f619aa1b94be151a5533` |
| program/tools.json | `a4feec5463051a5dcea165c14e8bbcf4b2f3fa59b946b0148a8952db78dd2d6a` |

Metadata-only availability checks find NumPy, SciPy, librosa and numba in the
already-qualified `.venv`; no installation/analysis was performed. Freeze
these worker/context pins again at execution release and abort if unexpected
concurrent source changes appear. Root owns any necessary source changes.
