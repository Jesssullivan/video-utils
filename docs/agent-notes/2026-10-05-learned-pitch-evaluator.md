# Learned pitch artifact evaluator candidate

Recorded 2026-10-06 00:36 UTC / October 5 local. Authority: operator's parallel
development goal; repository AGENTS.md; R-HOOK-CONVERGENCE-20261004 / R-N12 /
R-N13; root's explicit new-file acceptance implementation release. Named owner
`guitar_features` implemented only `scripts/learned_pitch_evaluate.py`,
`tests/test_learned_pitch_evaluate.py`, its existing acceptance specification and
this receipt. Root owns admission/publication. Existing learned adapter, its
tests, published pYIN evaluator and 24-tool catalog were not edited by this lane.

CLI candidate:
`python3 scripts/learned_pitch_evaluate.py --fixture-index BANK
--pyin-pilot-index PYIN --learned-pilot-index ML --output NEW --summary`.
The fixed bank is the four selected technical-v2 jobs, exactly 30 seconds.
Existing 12-second model smoke and sparse actual-take receipts are not accepted
as substitutes for that cohort index. No complete ML bank score is claimed.

The worker is stdlib only. It reuses the published hash/native-PCM/header/bank/
truth/pYIN validator, then reads immutable learned comparison JSON and NPZ/NPY
bytes. It verifies exact names, numeric non-object dtypes, shapes, finite values,
20 MiB uncompressed numeric limit, member/file bounds, hashes, three clocks,
independent window/padding maps, source-time extents and fixed decoder settings.
It checks event frame identities by recomputing activation postprocessing; no
model inference, ONNX import, audio decoding or package/model download occurs.
Source bytes/header reads and raw-array reads are explicitly reported.

Metrics preserve whole model-input support, padding, pointwise label scope and
predeclared clock sensitivity separately. Native accuracy, chroma/octave errors,
voicing/absence evidence, thresholded pitch-set TP/FP/FN/cardinality, timestamp
pairing to each pYIN branch and generated-score event matching all retain Ns,
unmatched hypotheses and nulls. Event assignment maximizes cardinality then
minimizes onset residual; signed negative residuals are retained. Generated
score events, rather than condition-region boundaries, provide event references.
The evaluator selects no winning model/branch or real musical verdict.

Outputs are new atomic `learned-pitch-calibration.json`, frame-error CSV and
event-error CSV. Structural failures retain diagnosis without promoted metrics.
Valid metrics with unsupported note/performance/listening claims retain evidence
and exit 1. Poor synthetic quality has visible alerts and exit 0. Existing output
directories are rejected. Main DAG and actual-take artifacts stay unchanged.

Verification: `python3 -m unittest discover -s tests
-p test_learned_pitch_evaluate.py -v` passed **14 tests**, 14.642 seconds. Independent oracles cover max-cardinality matching over
greedy-nearest failure, harmonic/octave mismatch, negative timing residuals and
duplicate predictions and boundary-truncated offset censoring. Bounded structural fixtures cover changed archives,
unbound truth, forged decoder events, false padding maps, unsupported claims,
object/NaN/extent rejection, ZIP paths/uncompressed bombs, actual compact CLI
and output reuse. The constructed missing-C1/C2 estimate reports native raw
pitch accuracy 0, chroma accuracy 1, octave fraction 1 over N=426, and event
TP=0/FP=1/FN=1. These are evaluator oracles, not Basic Pitch accuracy results.

Candidate source SHA256:
`1fb883026b842857f72a70c8bf2fb757330b9ac705be36914f7a4c50cb8f7374`.
Candidate tests SHA256:
`4d13b2256af507ef345cf4536844b0b42440e555d29c717db6263d08d7b683fb`.
Published pYIN evaluator remains
`a91ce8e9386cc7c63c5a5d53b8233f2c46a1f42fdd06ab1ae0eea3dc83405805`.
Root and independent MIR reviewer own final source/contract review before any
MCP/skill/recipe admission. Actual four-job learned-bank discovery remains pending.


## Independent review repairs and final retest

Independent MIR audit identified two concrete gaps: supplied event mean/max
activation summaries were only range-checked, and malformed compressed DEFLATE
could raise an uncaught zlib exception before a structural diagnostic was saved.
The new evaluator now recomputes those summaries from the immutable per-pitch
raw arrays over [start_frame,end_frame_exclusive), after verifying decoder event
identity, with 1e-7 numerical tolerance. Malformed DEFLATE maps to
`invalid_npz_archive` and the existing diagnostic-only failure path.

Final combined verification: `python3 -m unittest discover -s tests
-p 'test_learned_pitch*.py' -v` passed **19 tests**, 29.032 seconds: 14 owner
checks plus five independently authored MIR regression tests, including both
activation-integrity mutations, malformed compressed data, seam clocks, observed
signed offsets and a valid constant receipt. The independent test source is
`tests/test_learned_pitch_audit.py`, owned by the reviewer; its SHA256 is
`fd74adbeff791e4a23369bdf27b70ef4834bd7bfcfcc0ea299b51bd6de60341b`.
The final candidate source SHA above supersedes the earlier planning checkpoint.
No actual bank inference, model score promotion or catalog admission occurred.
