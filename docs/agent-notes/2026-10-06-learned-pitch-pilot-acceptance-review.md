# Independent learned-pitch pilot controller review

Actor `/root/plan_review`; authority root's source/metadata-only assignment,
operator's active parallel goal, repository AGENTS.md and
R-HOOK-CONVERGENCE-20261004/R-N11/R-N13. This lane owns this separate receipt
only. No inference, audio/array scoring, dependency changes, source mutation or
default adoption is authorized by this review. Root retains execution release.

Initial live HEAD/origin is `93f5088ac6377517a69966321e8fa71f726f97ee`.
The controller source was not present at initial inspection; final acceptance
awaits the owner's frozen implementation and exact hash.

## Locked cohort and acceptance boundaries

The existing [preregistration](2026-10-06-learned-pitch-bank-preregistration.json)
fixes four serial jobs, 8/8/6/8 seconds, 19 windows, 2,580 retained rows and
4,623,360 raw numeric bytes. Metadata sums independently reproduce 1,018 padded
rows, 426 native stable-monophonic rows, 1,006 transition-crossing rows and 130
polyphonic rows. Native absence eligibility is **zero**, so its false-alarm
rate must stay null with N=0. Pointwise counts (1,791 monophonic / 659 absence /
130 polyphonic) remain a different context view, not native acceptance.

Only the missing-F0 job supplies native stable-monophonic support. The other
three jobs can still inform pointwise, event and polyphonic diagnostics; they
cannot enter a native monophonic accuracy leaderboard. The corrected bank's
reported rendered F0 joint-fit amplitude is approximately 2.1125e−8 with no
post-sum tanh; this review reads metadata, not waveform evidence, and preserves
the generator's separate qualification receipt.

Required controller checks: byte-identical unprocessed opaque aliases with
explicit synthetic sample-zero timeline, `denoising_performed=false`, no case,
score, truth path or BPM passed to discovery; fixed adapter/model/evaluator/
registry/runtime/source hashes; all predictions and arrays sealed before truth
read/scoring; no label-guided retry; serial aggregate limits and a whole-job
deadline; partial evidence on failure; owned isolated process-group cleanup
under live ownership checks. The existing adapter's inference child inherits
its parent group, so an outer timeout must handle that owned tree rather than
leaving inference behind after signalling only its direct parent.

## Candidate source findings

The first controller candidate was inspected read-only after creation and before
its owner declared a freeze. Preparation copies verified native bytes into
opaque `job-NN/denoised.wav` aliases; manifests explicitly retain synthetic
zero origin/no stretch and unprocessed/no denoise/no gain provenance. Discovery
receives only the opaque directory, fixed coverage and activation thresholds.
Truth content is not opened, and evaluation is a separate CLI after prediction
ledger/index publication. These are appropriate source-level boundaries, not
an adversarial filesystem sandbox or completed execution proof.

Pre-release findings sent to owner and root:

- Enforce exact expected raw numeric bytes plus aggregate 20 MiB and 5,000
  events per preset before accepting the sealed prediction set; per-worker
  limits do not alone establish aggregate limits.
- Recheck actual controller and preregistration bytes against their bound
  release identities at execution start and before final sealing.
- Handle failed/exited worker leaders with surviving inherited descendants.
  The initial exception path checks `child.poll() is None` before group cleanup,
  while nonzero-return handling occurs afterward; neither handles that case.
  Preserve live group ownership checks and a durable R-N11 receipt.
- Start/check the whole controller budget across preparation, inference and
  hashing/sealing; retain bounded cleanup time.
- Preserve a durable failure receipt if preparation creates its owned output
  and then fails. Initially `main` receives the output path only after prepare
  succeeds, leaving that partial directory unreceipted on intermediate errors.

The frozen preregistration SHA is
`0314cb209d9a2113ecb63f5bef48df541337d247d7992f88fc13f677105e4599`.
Adapter `720a1f76…`, evaluator `1fb88302…`, model registry `ff3d4251…` and tuning
registry `bd381207…` matched its declared identities. Corrected missing-F0
truth SHA `b7782fa2…` explicitly records zero F0 synthesis coefficient,
harmonics 2/3/4/5/7, no subsequent nonlinearity and the rendered joint-fit
amplitude 2.1125001369190132e−8. No audio was read to repeat that fit.

Status: controller source acceptance pending owner fixes and frozen readback;
no inference or numerical quality acceptance occurred.

## Frozen source readback and verdict

The owner addressed the findings. Final independently read source identities:

| File | SHA-256 |
| --- | --- |
| `scripts/learned_pitch_pilot.py` | `df7ca74708fa8b9ca09f5db9b06426ed215c409630a4cc8ba13fa9c52650ce38` |
| `tests/test_learned_pitch_pilot.py` | `fdc816025d4dc51948aa0ba7e445ea4e0e3b6f6cdb289f13e9940d343f99cb1a` |

Source syntax parsed without execution. The owner reports 14 controller tests
passing in 1.011 seconds; this audit read their source and did not rerun them
under its source/metadata-only assignment. Tests use fabricated comparison
receipts/generated zero bytes and inert processes, including an exited leader
with a live child, timeout, insufficient budget, plan drift, altered source,
partial preparation, preservation of existing output and no default inference.
These tests do not establish model behavior or numeric array validity.

The final implementation checks closed resource settings, exact per-job numeric
bytes and aggregate raw/event budgets. It rehashes the actual preregistration,
controller, dependencies, original source inputs, opaque aliases/manifests and
prediction files before sealing. Serial discovery uses fixed commands and the
same whole-main deadline, with 610 seconds required before another admitted
600-second worker and deadline checks around final sealing/index publication.
Preparation failures retain their own partial receipt. The owned new-session
group is probed and signalled on failure even when its leader has exited; only
that owned group is addressed. Evaluation remains a separate operation.

The metadata-only independent readback of
`artifacts/benchmarks/learned-controller-final-preparation-20261006T0127/preparation.json`
binds this final controller and preregistration. All four opaque manifest JSON
hashes match; each has equal input/source/output hash declarations, known
synthetic zero origin, no time stretch and explicit no denoise/no gain. The
owner's preparation did read and verify source bytes/native WAV headers; this
audit read only its receipt/manifests and did not independently hash WAVs or
load activations. Preparation is not a numerical pilot.

**Final verdict: no unresolved must-fix remains in this bounded source and
metadata controller review.** Root may issue its exact hash-bound release for
the preregistered four jobs. This verdict is not that release and does not
authorize truth-guided retries, new settings, model downloads or numerical
acceptance. Retain prediction-only ledger sealing before the separate evaluator;
actual execution resources, arrays, clocks, boundaries, denominators and quality
failures still need their resulting receipts. Native false-alarm N=0 remains
null, and the 426 native monophonic rows belong only to missing-F0. No real
guitar, intended-note, listening or host acceptance follows.
