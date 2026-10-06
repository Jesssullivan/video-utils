# Capture application post-commit reporting audit

Owner `/root/release_review`. Root explicitly requested this focused
transaction/reporting review before native execution; authority operator goal,
AGENTS.md and R-HOOK-CONVERGENCE-20261004/R-N13. The previous source/fixture
readiness is reopened for this concrete failure invariant. Frozen worker source
remains unchanged by this lane.

Definition of done: reproduce with constructed owner fixtures and mocked media,
perform a real temporary candidate rename, and verify post-commit errors retain
the truthful candidate identity. No actual DSP, model, operator recording or
host action. Root owns source re-release and native execution.

## Verified counterexample against frozen `31eafcc8…`

New independent regression `test_post_commit_fault_cannot_claim_no_candidate_was_published`
wraps the real `publish_directory`, performs its rename, then raises `ApplyError`.
The final manifest and application receipt exist; private staging is removed.
The retained failure receipt nevertheless reports `failed_no_candidate_published`
and says `no success candidate`. The targeted fixture fails exactly on that
false status (one case, 0.768 seconds). Existing original and sentinel master
remain protected. The fixture makes no media subprocess call.

The second independent regression injects a one-shot print interruption after
real mocked-media `apply` returns its published candidate. It requires the CLI
error to retain the committed candidate path. This distinguishes completed
publication from a failure to report the result; a generic error cannot imply
that publication was undone.

The CLI case also fails against `31eafcc8…` (one case, 0.059 seconds). Its
error JSON has `status: error`, null failure-receipt fields and no committed
candidate path, while the final application receipt exists. Both regressions
are intentionally red until the separately released source repair. The original
six independent cases are unchanged; no old 27-tool source or operator media
was modified.

The owner and root received the concrete finding. A fix must preserve committed
candidate files, report committed-unreviewed identity separately from precommit
failure, and handle the CLI alarm/reporting boundary honestly. Root must release
any frozen source change; no implicit mutation was performed here.

## Independent corrected-source readback, awaiting final freeze

On worker SHA `c55536fcf40c6674eb6773f416c7903983b81b6cbda0efd79d3d1ed16a740c23`,
this lane independently ran its eight constructed/inert cases with
`.venv/bin/python -m unittest discover -s tests -p test_apply_capture_profile_audit.py -v`:
eight passed in 2.076 seconds. The renamed candidate is retained with truthful
`committed_unreviewed` publication and exact manifest, application-receipt and
export-outcome hashes. The CLI timer is already zero at the first result print;
the interrupted report retains canonical run-relative selectors and all three
artifact hashes. Listening and master adoption remain false.

Audit test source is frozen at
`7ba57baeed6dab31425505ca00b4e78ba23aebb90082806ce538168f7becad36`.
Only the owned inert Python direct child provides real process evidence; all
media processing remains mocked. No native or operator recording was processed.
The owner is investigating a separate combined-suite process-inspection result;
final source freeze and combined-suite closure are still required before root
releases generated native execution. The initial `31eafcc8…` counterexamples and
readiness reopening remain historical facts.

## Immediate publication observation failure

Before the corrected source froze, the owner requested one additional narrow
observation fixture. Against the same `c55536fc…` revision, a real temporary
candidate rename succeeds, then `Path.stat` is made to raise only for that exact
new final directory during immediate commit observation. After the patch exits,
both manifest and application receipt exist. The failure receipt still says
`failed_no_candidate_published`. The targeted ninth independent test fails
exactly on that false status (one case, 0.149 seconds); no media command runs.

The expected correction is truthful uncertainty: `publication_outcome_unknown`
with `candidate_publication: unknown_after_publish_attempt`, null confirmed
`committed_candidate`, and canonical `possible_candidate` selectors preserving
prepared run/manifest/receipt/export hashes and false listening/adoption. It
must retain the possible final directory and require byte readback before reuse.
Failed immediate observation proves neither commitment nor absence. This
finding was sent to root and the implementation owner; final admission remains
held pending the new regression and full owner suite.

## Independent unknown-outcome correction readback

This lane independently reran all nine cases after the owner's correction:
nine passed in 0.644 seconds on observed worker SHA
`3c715a9b399c174e89b42dd50fe46482df730e27e288170db1bcee3abcbbd746`.
The source now distinguishes exact final device/inode observation, an exact
retained original staging identity proving no move, and failed observation of
both. The last case retains canonical possible-candidate hashes with unknown
publication in both failure receipt and CLI diagnostic. The actual temporarily
moved directory remains intact. The original eight cases also remain green.

Nine-case audit source SHA:
`f7e58891a9f2250737d48b02b67830199ab5d077c3d1d8e0c86b24d9c3903fa3`.
Authoring `7d282087…` and media `91443154…` remain unchanged. The owner separately
received root authorization to bound process inspections and cleanup grace;
the observed revision is still transient pending final combined-suite freeze.
No native execution or musical/listening acceptance is claimed by this readback.

Root's separately authorized resource adjustment was source-read at
`00a03ef9fad8543be4335cb5cbcd3c9d9580a6b40b8faeb826811b105fd5daa6`:
one-second inspection covers subprocess and parse, verified cleanup and fallback
share the same five-second deadline, and waits/polls/sleeps consume remaining
time instead of resetting the allowance. No additional material source blocker
was found. Owner budget fixtures, combined-suite closure and final frozen identity
remain required; this observation is not a native timing/resource result.

The independent nine-case suite also passed on unchanged `00a03ef9…` in
1.571 seconds. A complete ignored log is
`artifacts/release-review-application-audit.log`, SHA
`f8105cc40d6ac2be22da7a7415e13f2cd26cb6c27f9b1d09fdba68477fc1b9e1`.
An earlier console capture exited zero but omitted its final summary, so this
bounded repeat retained the complete result rather than inferring timing from
partial output. No media/DSP execution occurred.

## Final corrected application freeze

The owner froze the same independently checked application bytes
`00a03ef9fad8543be4335cb5cbcd3c9d9580a6b40b8faeb826811b105fd5daa6`.
This lane read back unchanged authoring/media hashes, owner test SHA
`d21e6671bffec00d5d410ff5321786abe9cd185e70b50ab08118d5ba5aea7c13`,
and the nine-case audit SHA above. The complete fresh combined owner log records
46 passing tests in 26.087 seconds (37 owner plus nine independent), SHA
`23dd2fedd709f11677d67fef9da527fb93e98517dc0559fdf77eec8079e47933`.
This is a log readback, not a duplicate combined-suite run. There is no remaining
application source/fixture blocker. Native qualification still needs the frozen
harness/application/preregistration/release identity binding and root execution.
These corrected proofs do not reconstruct or reproduce absent historical31e
source bytes; their earlier findings remain recorded observations.
