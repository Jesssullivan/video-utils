# Preregistered learned-pitch bank pilot

Authority: operator's parallel guitar development goal, repository AGENTS.md and
R-HOOK-CONVERGENCE-20261004 / R-N12 / R-N13. Root released metadata design and
controller preparation only; model inference requires root's exact follow-up.
No new downloads, environment changes, inference or model-quality score occurred
in this preregistration. Source/array byte reads and model import are absent.

The [machine preregistration](2026-10-06-learned-pitch-bank-preregistration.json)
locks the existing technical-v2 bank, pYIN index and four component hashes.
Bank identity is `3a6d117a50b32ad4f9e1b60921ee1b8a1d4376cc821ebcb31f14f4b8d80fdc73`;
pYIN index identity is
`5c183df75f67dfa4b6d4a7b3c13b7d79d9fcbfa0408ce90d58a80017948ed343`.
Model/evaluator/current adapter identities and source extents are explicit.
The model owner confirmed current adapter `720a1f76103426d1cc7580d213d3516f31b184295a50d873bda545ccc5a2d40e`
preserves the three clocks/window geometry after the missing-model CI fix.
Evaluator `1fb883026b842857f72a70c8bf2fb757330b9ac705be36914f7a4c50cb8f7374`
and its independent 19-test acceptance stay frozen.

| Opaque job | Evaluation-only case/component | Excerpt | Rows/windows |
| --- | --- | --- | --- |
| job-01 | c1-missing-fundamental / clean | 0–8 s | 688 / 5 |
| job-02 | tuning-ladder / clean | 0–8 s | 688 / 5 |
| job-03 | legato-transition / mix | 0–6 s | 516 / 4 |
| job-04 | sweep-and-polyphony / mix | 0–8 s | 688 / 5 |

Total: exactly 30 analyzed seconds, 19 model windows, 2,580 retained rows and
4,623,360 expected raw numeric bytes with the admitted dtypes. Aliased native
assets total 36 seconds because the last two sources are ten seconds each;
their unrequested tails do not enter coverage. All nine supplied tuning pitches
remain unchanged. Ordinary C1 and distortion are represented by ladder pointwise
cohorts; absent-F0 periodicity has the one longer fully supported cohort.

## Honest eligibility and plots

Analytic metadata/clock geometry preregisters 1,018 padded rows and 1,562 wholly
unpadded input rows. Only missing-F0 has stable-monophonic **whole-input** support:
426 rows. Ladder and legato have zero; sweep has zero monophonic whole-input rows,
with 130 polyphonic-center rows separately excluded. Native guitar-absence
eligibility is zero throughout, so native false-alarm rate is **null, N=0**, not
zero or successful silence detection. These are expected eligibility counts,
not measured estimator success.

At the audited primary model clock, pointwise expected cohorts are 1,791
monophonic, 659 guitar-absent and 130 polyphonic timestamps. Pointwise/alternative
clock metrics remain explicitly outside whole-input support acceptance. Plot
per-case native versus pointwise raw/chroma accuracy with their own Ns; use hollow
or unknown marks at N=0. Plot missing-F0 fundamental/extra-octave pitch-set counts,
pointwise absence false positives, chord voice TP/FP/FN/cardinality, and event
onset residuals beside unmatched/truncated counts. Never place native N=0 cohorts
on an accuracy leaderboard or treat a padded-window top-one score as equal to
pYIN's short-window eligibility. Keep every raw head and all three clocks.

## Execution preparation and release

Use fresh private `artifacts/benchmarks` output only. Copy selected WAV bytes to
opaque `discovery/job-NN/denoised.wav` compatibility aliases, with SHA equality,
48 kHz mono PCM16 native extent and ordinary file checks. The manifest records
`source.sha256`, matching `output_sha256["denoised.wav"]`, explicit
`timeline.audio_start_seconds: 0`, `no_time_stretch: true` and native PCM metadata.
It explicitly records `input_role: unprocessed_component_alias` and
`denoising_performed: false`: the required filename is not evidence of cleanup.
Source sample zero follows known synthetic origin rather than missing WAV PTS.

Public command, per opaque job:
`python3 scripts/basic_pitch_compare.py OPAQUE_RUN_DIR --start-seconds 0
--max-analysis-seconds 8 --onset-threshold 0.5 --frame-threshold 0.3`;
the six-second job uses `6`. The parent build emits a full lineage-bound
comparison receipt and NPZ; direct internal `--infer-task` does not replace this
packaging. Default qualified isolated runtime stays unchanged. No truth path,
case name, expected notes, score, BPM seed or classification reaches the worker.

Run four jobs serially after explicit release, reusing each array for project
127.7/25 ms presets. No truth-guided retries or alternate thresholds. Freeze raw
comparison/array/resource hashes and the prediction-only index before loading
truth or scoring. Recheck original source/bank/index/worker/model identities.
Then assemble schema-1 learned index with full comparison/NPZ/input/truth paths
and hashes, fixed budget and four completed statuses; invoke the frozen pure
evaluator in a fresh directory. Preserve its quality alerts and native nulls.

The controller budget is 900 seconds, with 600-second admitted worker deadline,
two numerical threads, 1 GiB worker RSS, 24 aggregate windows, 20 MiB aggregate
raw arrays and 5,000 events per preset. Launch only when the remaining budget
can accommodate the worker plus bounded cleanup, or stop with partial evidence.
Any outer termination must address only the controller's owned isolated child
session, verify its ownership/live state and retain an R-N11 receipt; never kill
only a parent and leave inference running. No source is overwritten or trimmed.
Setup/model absence is a preflight failure, not permission to download or retry.

Current state: preregistration and controller source preparation authorized;
actual learned-bank execution, numerical evaluation and any tool admission await
root release. Earlier actual 20-second comparison and 12-second stepped proxy
remain separate evidence and cannot satisfy this fixed 30-second cohort.
