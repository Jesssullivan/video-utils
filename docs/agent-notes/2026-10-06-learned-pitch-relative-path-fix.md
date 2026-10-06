# Learned-pitch evaluator relative-index repair

Authority: root-authorized separate source fix after the frozen old evaluator's
actual numerical, independent audit and MCP proofs; repository `AGENTS.md`;
R-HOOK-CONVERGENCE-20261004/R-N13. Existing prediction, numerical and publication
evidence remains bound to the revision that produced it.

Direct CLI and `just` calls with repository-relative indices previously passed
the index-file read but failed downstream relative artifact lookups with
`path_outside_benchmark_root`: a relative index's parent was itself relative.
`evaluate` now normalizes all three supplied indices using the existing guarded
`base.safe_path` before any parent lookup. Absolute inputs retain their behavior;
the path traversal, symlink and benchmark-root checks remain active.

Frozen new source `scripts/learned_pitch_evaluate.py` has SHA256
`26e2b1be69bca6de58ee0debbe0b598ee81826a394efa10e62f77b532755cdf9`.
`tests/test_learned_pitch_evaluate.py` now has SHA256
`6d5bb9f2be371deef02dd8680421533bb0470cff9043d4cc7dc44f39370b82f5`.
The complete former source is archived read-only in ignored
`artifacts/benchmarks/learned-evaluator-source-snapshot-20261006T0145/learned_pitch_evaluate.py`,
verified SHA256
`1fb883026b842857f72a70c8bf2fb757330b9ac705be36914f7a4c50cb8f7374`.
Removing only the normalization comment and three normalization statements from
the new source reproduces that archived source byte-for-byte. No scoring,
decoder, clock, tolerance, model, duration, corpus or inference changes occurred.

`python3 -m unittest discover -s tests -p 'test_learned_pitch_*.py' -v` passed
all 34 tests in 61.025 seconds: 15 owner evaluator tests, five independent audit
tests and 14 controller tests. The new regression makes both pilot indices use
relative artifact references, compares complete results and frame rows for
relative versus absolute index arguments (excluding only creation time), and
executes the direct CLI with relative indices/output. Actual CLI scores agree
with the absolute result. These are constructed metadata/activation fixtures;
tests perform no model inference, downloads or real-guitar grading.

The frozen controller remains
`df7ca74708fa8b9ca09f5db9b06426ed215c409630a4cc8ba13fa9c52650ce38`, and the original
preregistration remains
`0314cb209d9a2113ecb63f5bef48df541337d247d7992f88fc13f677105e4599`.
A read-only invocation of the controller's identity check against that original
plan correctly rejected the changed evaluator with `sha256_mismatch`, before
preparation or inference. The original release and all historical numerical and
audit receipts were not changed to authorize the new revision retroactively.

Root owns a fresh direct `just` relative-path readback using the already sealed
pilot and any live MCP/version-reference qualification. Those are separate from
these passing source regressions and from the earlier old-revision numerical
proof. Hook and skill owners received the new hash; no model inference or
truth-guided numerical retry was performed for this fix.
