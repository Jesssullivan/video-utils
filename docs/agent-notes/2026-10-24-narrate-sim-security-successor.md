# SIM security successor

Authority: operator parallel narration source work; R-HOOK-CONVERGENCE-20261004,
R-N11/R-N12/R-N13. Bounded successor to PR #41, based on exact source
`420921858e067cc386eb94965933d82836117dec`. The original branch and work remain
owned by their existing writer. Integration remains the coordinator's act.

SIM evaluation now rechecks the current reference voice and consent for both
historical render references and explicit comparison references. Revoked,
missing, incompatible-scope or missing-evidence consent cannot authorize audio
decoding, conversion or embedding. A historical reference must still match the
current voice's pinned clip. Private-store hashing remains the existing
content-address lookup; no store paths are emitted as measurement evidence.

Worker success requires process exit zero, an explicit boolean success, a
complete unique set of requested string IDs, finite cosine values in [-1, 1],
positive finite durations and valid runtime version strings. Invalid replies
raise the existing refusal boundary, so evaluate reports `not_measured` without
measurement summaries or a passing gate. Successful stderr diagnostics alone
are not failure; a nonzero process can never produce measured evidence.

Validation: 65 passed, 1 skipped across SIM security, policy and contract-shape
regressions; lint and format checks pass. New regressions use metadata,
in-memory audio stand-ins and fake processes only. No real reference audio,
recording, model, server, GPU, download or secret is used. The skipped contract
case requires an unavailable tool. This is source/synthetic proof, not speaker
model qualification or listening acceptance. E7 follows the canonical E2/E4
integration order.
