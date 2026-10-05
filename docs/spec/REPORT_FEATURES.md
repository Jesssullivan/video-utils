# Selected feature evidence in the local report

Owner: `/root/plan_review`. Authority: the operator's existing ten-hour parallel
goal, repository AGENTS.md and R-HOOK-CONVERGENCE-20261004 / R-N13. This lane
owns `scripts/report.py`, `tests/test_report.py` and this specification. Root
owns actual-run integration, publication and tracker receipts.

The report will show explicitly selected click, pitch, meter, tonal-context and
within-take phrase-comparison evidence from `dag.json.selected_evidence`. The
graph lane publishes five slots: `clicks`, `pitch`, `meter`, `tonal` and
`comparisons`. Each slot retains selection status, relative selector, artifact
SHA-256, upstream hashes, payload status, timing status and bounded metadata.
Only `verified` slots qualify for payload display. No directory scan or newest
receipt selection is permitted.

Before opening a selected payload, verify the original-source identity, every
graph artifact hash and the selected receipt hash. Reject unsafe paths and
symlinks. A changed upstream artifact invalidates graph-derived flags and
selected displays; rejected/not-selected states remain visible. Missing feature
artifacts are ordinary abstention, not evidence that the recording has no clicks,
notes, meter or musical structure.

Display candidate counts and click overlap abstention; pitch excerpt coverage,
window extent and octave ambiguity; accent-cycle hypotheses separately from
nullable notated meter; tonal profile disagreement and nullable tonic/mode;
bounded phrase alignment spans, relative offsets/rates and attack-edit
abstention. Seek controls use supplied source or decoded-audio coordinates with
the recorded timeline mapping. Candidates cannot become confirmed musical
errors or listening acceptance through report rendering.

Definition of done: meaningful tests for verified selections, no implicit
selection, changed selected/upstream hashes, unsafe selectors, escaped metadata,
sparse pitch coverage, nullable meter/tonic/mode and comparison abstention. Keep
the existing audio/video report and atomic output behavior. All tables have
explicit display limits; no new audio processing, remote assets, downloads or
browser daemon are introduced. Root later checks the calibrated actual run and
browser readability; synthetic checks are source behavior evidence only.

## Implemented source checkpoint

The five slot renderers and current graph checks are implemented. Selected
receipts have a 20 MiB read bound; metadata cells are escaped and limited to
600 characters. The report checks run-relative upstream hashes and the fixed
`program/instrument.json` external-context digest without following arbitrary
external paths. Changed selected files, upstream files, tuning context and
symlink aliases are rejected. Current graph-derived review flags are excluded
when graph freshness fails. Rejected slots are never opened, and no receipt is
discovered by filename convention or modification time.

Display bounds: 20 click events, 12 pitch coverage spans, 16 pitch examples
distributed one per excerpt/resolution branch, three pulse-level meter aliases,
four tonal profile families with two rankings each, and 24 phrase comparisons.
Pitch candidates retain source-time window extent and algorithm voicing distinct
from note-correctness probability. Existing waveform, audio/video players,
baseline features, source privacy and atomic report replacement remain intact.

`python3 -m unittest discover -s tests -p test_report.py` passes 20 tests: the
12 existing report cases plus eight meaningful selection, freshness, bounds
and unknown-value checks. This is local source behavior acceptance. Existing
actual reports were preserved; root owns explicit calibrated-run selection,
actual rendering, browser review and publication. Listening, musical accuracy,
physical sync and detector calibration remain unestablished by these checks.
