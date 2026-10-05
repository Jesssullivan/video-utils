# Composite calibration pilot lane — October 5, 2026

Owner: `media_latency`; exclusive files `scripts/calibration_pilot.py`,
`tests/test_calibration_pilot.py` and this specification. Root owns recipes,
actual pilot execution, integration and publication. Authority: operator-approved
ten-hour parallel goal, repository AGENTS.md, R-HOOK-CONVERGENCE-20261004;
R-N11 owned process-group checks and R-N13 durable evidence.

Definition of done: accept an explicit hash-bound generated fixture index and a
fresh output directory. Run unseeded discovery on each raw mixture, preserving measured tempo or
abstention, then bounded phrases and optional recurrence comparison. Run four
agreed pitch jobs with 30 seconds TOTAL coverage (8+8+6+8). Produce separate exact
`pitch-pilot-index.json` flat jobs and `phrase-pilot-index.json` cases contracts
for evaluators. Original generated audio remains unchanged. Generator truth labels
are passed only to evaluation, after discovery has produced hash-bound artifacts.

Plan before implementation: agree index/audio and evaluator schemas with their
owners, use existing bounded worker invocation primitives with two numerical
threads, save per-job settings/worker identities and failure receipts, and test
execution order, exact receipt selection and truth isolation with toy workers.
No newest scan, dependency installation, model download, media restoration,
operator latest-pointer update or claim of musician correctness is part of this
workflow. Root runs the complete bank only after source/contracts freeze.

Root correction before implementation: the default is unseeded across the entire
bank, including variable tempo. Discovery receives neither `--bpm` nor a supplied
reference grid. Pitch coverage is 30 seconds aggregate, not per job.

Implemented interface:

```
python3 scripts/calibration_pilot.py --fixture-index artifacts/benchmarks/BANK/fixtures.json --output artifacts/benchmarks/NEW-PILOT --analysis-python /absolute/path/to/python
```

`--backend stdlib|librosa` defaults to `librosa`; pitch always uses the explicit
analysis interpreter. `--overall-timeout` defaults to 900 seconds and is bounded
to 30–1800. Each discovery/evaluation job has a 120-second wall deadline;
pitch jobs have 240 seconds, clipped to the remaining overall deadline. Audio
coverage and wall deadlines are separate budgets. Existing `run_demo.invoke`
actively bounds each output stream to 2 MiB and checks owned live process groups
before timeout cleanup under R-N11. Numerical libraries receive two threads.

The controller validates all twelve mixture hashes/native PCM headers, the two
additional clean-component identities and the current instrument registry before
starting workers. Discovery receives opaque byte-identical audio aliases and
generic raw PCM/sample-zero manifests. No semantic case names, generator score,
phrase boundaries, note labels, attacks or time warps are passed in its arguments,
environment or manifests. This is input isolation, not a filesystem sandbox.
The 120-second case bank remains raw: no denoise, gain change or restoration.

Each case produces rhythm, phrase and optional comparison receipts. Pitch jobs
are clean C1-missing-fundamental 8 seconds, clean tuning-ladder 8 seconds, mixed
legato-transition 6 seconds and mixed sweep-and-polyphony 8 seconds, all from
sample zero. Separate flat pitch jobs and phrase case indexes use exact returned
or documented fixed artifact paths with source/settings hashes. No newest scan
occurs. Full indexes are presented to standalone evaluators only after discovery.

`pilot.json` checkpoints stage execution, explicit failures, generator/config
identities and original hashes. Nine named controller/worker/helper sources are
snapshotted and checked for drift. Failed workers retain completed artifacts;
incomplete indexes skip their evaluator. Comparison absence remains nullable.
An evaluator hard-gate failure keeps its exact finite JSON artifact and hash
even when the worker exits 1. Unknown references, empty estimates, genuine false
negatives and quality baselines remain evaluator judgments; the controller never
turns them into success scores. Exit 0 means the composite completed and evaluator
hard gates passed, not that detection quality or real-musician behavior is accepted.

Validation: ten generated-WAV/toy-output orchestration tests cover all-case order,
unseeded inputs, exact aggregate pitch budget, current receipt selection,
truth/environment isolation, original preservation, alias modification,
dependency failures, nullable comparisons, hard-gate artifact retention, freshness,
symlink/traversal rejection and deadline exhaustion. A real bounded child verifies
the operational environment, two-thread setting and worker identity. These tests
establish controller behavior; root separately runs real discovery and evaluation
on the complete generated bank before any calibration claim.
