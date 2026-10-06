# S1 corpus lane handoff

Authority: operator S1 sprint, TIN-5566, R-HOOK-CONVERGENCE-20261004 and
R-N12/R-N13. Owner `/root/s1_corpus`, isolated branch
`sprint/20261006-s1/corpus`. Root alone owns admission, signed integration,
publication and Linear. No commit, push, merge, tracker change, additional agent,
media read, inference or actual annotation write occurred in this lane.

The read-only split validator and closed contract are frozen. Worker SHA256:
`308300de48b0395ecf8e572a54f07abd36d2f8b6764106efc63b222c1ed60a0d`.
Tests: `f0b023e82f05cf3ebdc21f7ac511a7f3a0875a50187fcb50333a672bec506664`.
Spec: `300ae5139d9bf104b37db412e19559efed3950a4e4ea21a30d9f217103a766af`.
The old `scripts/corpus.py` remains
`399afa9fbe8e7ab0511d4b3413d051b48df6fc66d9d6fb588ac1a4e572421cff`.

`python3 scripts/corpus_split_s1.py validate MANIFEST --root ROOT --summary`
validates hash-bound metadata and complete annotation stores before a compact
projection. All declared family/source/artifact/parent/augmentation/store/selected
annotation connections group together. Cross-split assignment, cyclic/missing
parents, forged conflicting family/source/origin, stale metadata and invalid
annotation provenance refuse. `unassigned` rows remain unassigned. Supplied
lineage cannot authenticate a wholly fabricated unlinked identity.

The owner command selected `test_corpus*.py`: **53 passed, zero skips**, including
37 new and16 unchanged legacy tests. Four fixed seeds exercise240 generated
graph leakage/order properties. The 500-node chain, Unicode text/path, duplicate
JSON/nonfinite/UTF8, file/aggregate/result ceilings, FIFO/symlink/traversal,
full/summary parity, V1 receipt and actual V2 store roundtrips are covered.
Source guards were unchanged across the2.682-second suite
(2.898-second process). Exact commands, runtime, hashes and retained log are in
`corpus-owner-test-result.json` and `corpus-owner-tests.log`.

The independent audit passed **five separately generated tests** against the
same frozen worker, including transitive leaks, unknown/absence0 and V2 candidate
staleness. Audit receipt is owned by the audit lane:
`audit-corpus-source-tests.json`. An initial audit finding was corrected: pure V2
store validation did not check current candidate artifact bytes. Both versions
now also delegate the existing candidate receipt/source/event identity check for
every stored item. Old marker bytes, foreign candidate source and absent event
fingerprints refuse. No annotation taxonomy or claim label was redefined.

The V2 integration test used the annotation-owner worktree read-only via
`PYTHONPATH`. Exact dependency was annotation worker
`237d6b53ac1a73f0e981d1bcaa3fa73e3b5f9ab417bc7bf051575b3d6cf0cab6`
and review server
`05bc9cc753a312c96ab822afaceb91f5a4d44bf288d281c201c8bc918b221ef0`.
Root must run combined checks after the final annotation source is integrated;
this receipt is not that later dependency/publication proof.

`corpus-demo-draft.json` is one original source-bound real-recording identity,
**unreviewed, unassigned, zero selected annotations**. Validation opens only this
metadata and the byte-bound existing arrangement. The source audio hash is
declared, not rehashed. The approximate10–11-second anchor and404 expected clicks
remain operator intent; no detections/ground truth were manufactured. The saved
compact validation is `corpus-demo-draft-validation.json`.

`corpus-readiness.json` reads the saved primary numerical report and independent
audit with byte receipts: native missing-F0 C1 fundamental matches34/426,
octave errors392/426, chroma426/426, native absence denominator0 and false-voicing
rate null. These are prior generated-fixture results, not new inference or
actual-take musical accuracy. The draft has no real heldout evaluation coverage.
Every validated corpus keeps absence0, unknown unlabelled intervals,
`ground_truth_established:false` and `listening_acceptance:not_established`.

Root admission is pending: add the typed read-only `corpus_split` hook, matching
skill and recipe, integrate the frozen annotation dependency, perform appropriate
combined checks, then record separate private/signature/CI/Linear evidence. No
new model, AU, hosted backend or detector default is requested by this lane.

Receipt: `/root/s1_corpus | named corpus files and generated fixtures only |
authorized family-split validator/readiness slice | S1, R-N12/R-N13 and
R-HOOK-CONVERGENCE-20261004 | existing v1 corpus and accepted media unchanged |
own source frozen;53 owner/legacy checks and5 independent generated checks
passed; root admission/publication remains separate`.
