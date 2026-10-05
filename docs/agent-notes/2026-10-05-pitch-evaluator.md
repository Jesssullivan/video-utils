# Generated-reference pitch evaluator implementation

Authority: operator-authorized guitar project and ten-hour development goal;
repository AGENTS.md; R-HOOK-CONVERGENCE-20261004, R-N12 and R-N13. Actor and
named owner: `guitar_features`. Root released this new-file lane after private
publication `45a1313ccbcb0ecc097f3a017979254e5719a3c6`; root owns actual pilot,
integration and publication. No published pitch worker or original recording was
changed in this lane.

Implemented `scripts/pitch_evaluate.py` and independent
`tests/test_pitch_evaluate.py` against
[the calibration contract](../spec/PITCH_CALIBRATION_LANE.md). The stdlib worker
verifies generated bank/pilot/truth/pitch fingerprints, canonical and opaque-alias
PCM16 WAV bytes/headers, exact four-job 30-second coverage, instrument and worker
revisions, independent centered window extents and complete frame grids. It does
not decode waveforms or invoke inference. JSON has finite-value, duplicate-key,
128-level nesting and size guards; all paths stay beneath ignored repository
`artifacts/benchmarks`, without symlink traversal.

Per-branch metrics preserve complete-window exclusions, true-voiced denominators
including abstention, raw pitch versus chroma accuracy, octave versus other pitch
errors, voicing recall/precision/false alarms, explicit nulls and sample counts.
Transition scans preserve negative centered-window bias and separately report
range exclusion, insufficient window support and absent target detection.
Algorithm probability is never labeled note-correctness confidence. Aggregates
sum numerators and denominators. No intended-note or actual-take grading occurs.

CLI: `python3 scripts/pitch_evaluate.py --fixture-index BANK --pilot-index PILOT
--output NEW_DIRECTORY --summary`. The output directory must be fresh. Atomic
receipts are `pitch-calibration.json`, `pitch-frame-errors.csv` and
`pitch-transition-errors.csv`. Compact stdout follows full validation. Exit 1
retains either a structural diagnostic without metric cases or a valid metric
receipt that failed unsupported confirmed-claim gates; stderr identifies the
reason and retained receipt. Poor generated model accuracy remains visible with
regression alerts and exit 0. These engineering baselines do not establish
listening, actual guitar correctness or Logic acceptance.

Verification at 2026-10-05 22:58 UTC: `python3 -m unittest discover -s tests
-p test_pitch_evaluate.py -v` passed **17 tests**, 5.597 seconds. Tests include
hand-calculated pitch/chroma/octave/voicing oracles, silence and null denominators,
glide source translation, whole-window context masks, negative transition bias,
small-N p95, hostile JSON, component/hash/grid/edge/revision rejection, nested
confirmed-claim failure and actual subprocess compact stdout/exit behavior.
The portable helper generates structural smoke WAVs and constructed abstaining
estimates; it does not run pYIN or demonstrate technical-v2 model quality.

Frozen evaluator SHA256:
`a91ce8e9386cc7c63c5a5d53b8233f2c46a1f42fdd06ab1ae0eea3dc83405805`.
Final test SHA256:
`28f07b14a3a0cecf427b56c9bbd77c1163e563d1bffe03fa507995a80471e999`.
Root owns the actual complete generated-bank discovery pilot and its numerical
quality receipt; that result is separate from this source-test acceptance.
