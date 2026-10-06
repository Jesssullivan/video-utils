# Holdout metadata admission checkpoint

Authority: operator reattachment and root's named holdout lane;
R-HOOK-CONVERGENCE-20261004 / R-N12 / R-N13. This checkpoint precedes tests and
generated fixtures. Published v1/v2 runner, helper, configuration and waveforms
are untouched; dirty parallel-owner report/experiment/receipt work is preserved.

Owned files: new benchmark_holdout worker/tests, HOLDOUT_BANK_LANE specification
and this receipt. Root owns admission, the future 120-second generated bank,
actual inference and publication. Initial source exposes metadata-only plan and
validation; no full-bank operation exists. No model, media acquisition, package
installation, heavy build, audio processing or actual-take annotation occurred.

Concrete artifact:
`artifacts/benchmarks/holdout-admission-211-307/holdout-plan.json`.
SHA256 `495ad2f3f553b0bd7030ac797b6e8589f37748df657219c075d0fc4ce7491e74`;
recipe SHA256 `0f8223e9adc4deb113c87a5b231b76bec33f573feabb03ec32bd8f565a5a3c63`.
The exact table is deterministically reconstructible from the admitted recipe
and frozen published dependency hashes recorded in the artifact. Both seeds211
and307 remain withheld from choosing the four preregistered comparison arms.
The original development bank remains the only setting-selection source.

Twelve cases / 120 seconds: six ten-second cohorts per seed, with paired timing
reference/error nuisance parameters. Recipe varies phrase duration/placement/gap,
gain, distortion proxy, independent click timing/level and colored noise. All
generated labels remain evaluator-only. Reading a proof for construction checks
does not qualify model accuracy; using it to tune knobs exposes that seed and
requires an explicitly new holdout generation.

Receipt: `repo_patterns | new holdout metadata/spec and artifact only |
preregister parameters before tests and inference | R-N12/R-N13,
R-HOOK-CONVERGENCE-20261004 | no holdout bank or test |
metadata saved and root admission requested; tests/proof/full generation pending`.

## Root admission and single-case structural checkpoint

Root admitted the exact495ad2f3 metadata hash after reading the full specification,
plan and validator, then authorized focused tests and one ten-second timing-errors
proof. Both seeds remain withheld from setting selection; arm settings are fixed.
The saved metadata is an immutable historical pending-admission artifact; this
receipt records the subsequent admission without changing its bytes.

`python3 -m unittest discover -s tests -p 'test_benchmark_holdout.py' -v`:
**9 PASS**,2.681seconds on the final worker revision. Checks include independently
known SHA-byte arithmetic, paired nuisance/budget identities, read-only validation,
parameter/type/dependency/path tampering, time bounds and native timestamp
rejection. The rendered clean component is actually silent at the omitted attack
and nonzero at the added attack; all note tails remain inside declared phrases.
These are structural checks, not detector performance or musician ground truth.

Saved proof command:

```sh
python3 scripts/benchmark_holdout.py proof \
  --plan artifacts/benchmarks/holdout-admission-211-307/holdout-plan.json \
  --case seed211-timing-errors \
  --output artifacts/benchmarks/holdout-proof-seed211-timing-errors
```

`fixtures.json` SHA256
`e43f045d81671d41584aecaa946233ad67102f878b7500357457dcba6d51959b`;
`truth.json` SHA256
`26ba0e32087fe999632848689dc9d7fe72ce864575a2f99264f2ef4653ef90bf`.
Four480,000-frame mono48kHz PCM16 components, ten source seconds,13 generated
score events and32 independent click events. Maximum rendered mix versus component
sum error is1PCM16 LSB (allowed2). Native/source translations and all component
hashes passed; no inference, quality metric, listening acceptance or full-bank
execution occurred. Labels remain solely generated construction/evaluation data.

Frozen checkpoint source SHA256:

- `scripts/benchmark_holdout.py`:
  `2cfaaf140a1620a8e1af360a0f0d0c735c572742ab77bce068fec32c179252b8`.
- `tests/test_benchmark_holdout.py`:
  `0dbff28f46132440f38578f3f684c98e3a324de829d47c8a538868189ba0f4dc`.

Full12/120 generation still requires root's structural review. The worker has
no full-generation operation; all published v1/v2 dependencies retain their
admitted hashes. New holdout files are frozen at this checkpoint pending root
review; parallel-owner files remain preserved.

## Full-generation implementation checkpoint, execution held

Root subsequently reviewed the metadata,9tests and saved proof, and authorized
full-generation **code implementation only**. The full bank remains ungenerated
until the phrase owner freezes exactA/B/C/D math and harness source and root
releases execution. The original495ad2f3plan and0f8223e9recipe hashes remain exact.

The implementation now exposes:

```sh
python3 scripts/benchmark_holdout.py generate \
  --plan artifacts/benchmarks/holdout-admission-211-307/holdout-plan.json \
  --output artifacts/benchmarks/NEW_DIRECTORY \
  --timeout-seconds 600
```

Serial12case/120second/48WAV aggregation, 600second ceiling, no numeric thread pool
(one math thread; ceiling two), bounded local immutable outputs and schema2
bank-index-relative source/component/truth receipts. It checks native extents,
source origin, event/pitch/click timestamps, source/component byte hashes and
frozen dependencies around each case. Missing-F0 coefficients use the published
independent joint regression after PCM16 rendering; generated32Hz construction
uses a clean-component coefficient check. Clipping or inconsistency rejects.
A structural failure writes a partial failure receipt and no successful index.
Generated labels remain outputs for evaluation only.

Final focused suite: **14 PASS**,2.681seconds. The five new tests use metadata
mocks and deadline/budget rejection: no complete heldout bank or inference is
executed. They check exact aggregation/native receipts, partial failure recovery
and absence of a successful index on failure. Existing proof test still verifies
the previously admitted timing-error construction; published sources remain unchanged.

New frozen source SHA256:

- `scripts/benchmark_holdout.py`:
  `051d8689364564513c34a1ab00a2c23560407e474da12c2bf25e7513dbc81709`.
- `tests/test_benchmark_holdout.py`:
  `60af152f784a29044e3e014b8ae0f2f67146481a3fee83804d90fbd7b73dcaaf`.

The earlier saved one-case truth explicitly retains renderer
`2cfaaf140a1620a8e1af360a0f0d0c735c572742ab77bce068fec32c179252b8`.
It is historical proof of that revision, not a new full-bank runtime receipt.
No new full-bank waveform, discovery prediction, quality score or real musical
claim was produced by this implementation checkpoint.
