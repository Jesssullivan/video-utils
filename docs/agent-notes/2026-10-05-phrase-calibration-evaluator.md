# Phrase calibration evaluator implementation receipt

Actor: `/root/phrase_dag`. Authority: operator's active ten-hour implementation
goal; root source-freeze release after
`45a1313ccbcb0ecc097f3a017979254e5719a3c6`; R-HOOK-CONVERGENCE-20261004,
R-N13. Checkpoint: 2026-10-05 22:55 UTC.

Owned files are `scripts/phrase_evaluate.py`, `tests/test_phrase_evaluate.py`,
`docs/spec/PHRASE_CALIBRATION_LANE.md` and this receipt. No existing discovery,
comparator, DAG, marker, actual-take or generated-bank artifact was changed.
Root owns actual bank/discovery execution, recipes, integration and publication.

The standard-library worker reads schema-2 generator-only fixture truth and a
separate hash-bound phrase pilot index. It verifies waveform and component hashes,
native WAV extents and sample-zero origin, truth/bank/instrument context, discovery
source identity and current opaque source-alias bytes, artifact/settings/upstream
receipts and stable input bytes. Paths stay under `artifacts/benchmarks`; generated
references never enter discovery or the comparator. No audio decode, subprocess,
inference or download occurs.

Independent bounded min-cost flow maximizes one-to-one match count before
minimizing boundary displacement or maximizing span/pair IoU. The worker reports
20/50/100 ms boundary and picked-attack scores, 0.50/0.75 span and ordered-pair
scores, applicable micro/macro counts, excluded semantics and sparse alignment
coverage. Raw generated/observed offsets remain alongside warped residuals;
uncovered landmarks are not extrapolated or averaged as zero. Median y-minus-x
is compared to the corresponding reference statistic, separately from affine
intercept and rate. Unknown detector confidence and articulation abstentions
remain producer evidence, not musical mistake labels.

CLI is fixed:

```sh
python3 scripts/phrase_evaluate.py --fixture-index INDEX --pilot-index PILOT \
  --output NEW_DIR --summary
```

Successful baseline measurement publishes new immutable `phrase-evaluation.json`
and compact stdout. Structural/hash failures exit 1 without promoted output.
Unsupported confirmed claims publish a diagnostic receipt with
`generated_fixture_calibration_failed_hard_gates`, `hard_gates_passed:false`,
compact stdout and stderr containing the retained path, then exit 1. Low
audio-derived F1 or high abstention does not invent a new acceptance gate.

Validation: `python3 -m unittest discover -s tests -p test_phrase_evaluate.py`
passed **24 tests** in 0.249 seconds at the frozen checkpoint. Evaluator SHA256 is
`3e503de277b2fd233fe802595a09a655c89669b0eb820f228e677c1b94b828a5`.
Coverage includes an
independent greedy-matching counterexample; duplicate predictions; tolerance and
endpoint/null oracles; span/pair IoU; affine/piecewise arithmetic and no
extrapolation; 100 ms shifted and 0.8-rate synthetic feature motifs; qualified
omission versus legato abstention; stale bytes/settings and changed opaque inputs;
native extent/onset mismatch; JSON duplicate keys/depth/overflow; count/duration
and metadata bounds; path/symlink/new-output guards; explicit empty attack false
positives; and hard-failure diagnostic preservation.

The read-only research lane reviewed the implementation and prompted the actual
stdlib detector-kind correction, empty picked-attack reference treatment,
additional aggregate metrics, native-score validation robustness, and a partial
warp-coverage counterexample. The final regression prevents claiming absorption
of a timing change outside the observed path: changed landmarks or both changed
rate-interval endpoints must be covered with low residual. Uncovered changes
retain an explicit unknown status and affected-coverage counts. Root's
fixture owner confirmed exact schema-2 component/path/native-origin contracts.
Hook and skill owners received the final CLI, bounded output and hard-failure
semantics. A real twelve-case audio-derived calibration remains a separate root
pilot, and is not claimed by these unit/feature checks. Listening, real musician
accuracy, DAW import and AU/Logic acceptance remain unverified.
