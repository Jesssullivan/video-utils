# Future capability and repository audit

Date: October 6, 2026. Actor: `capability_future`. Authority: operator explicitly
requested future capability discovery, shared controls, cleanup/traversal and
parallel planning; repository `AGENTS.md`; R-HOOK-CONVERGENCE-20261004,
R-N11/R-N12/R-N13. Owned files: this receipt and
`docs/spec/future/CAPABILITIES_AND_REPO_EVOLUTION.md`. No live source edits,
publication, service startup, model downloads or AU host actions.

Read current `AGENTS.md`, `PROJECT.md`, tool registry, dispatcher, MCP stdio
adapter, recipe routing, runtime manifests, review server, gain parameter source,
graph selector contract and capture authoring worker/skill. Current working-tree
count is 28 registered tools and 28 skills. Historical docs mention 27; this audit
does not establish remote publication state. The tree was already dirty with
concurrent source/notes changes, all preserved.

Findings: the catalog already supplies closed schemas, skills and workflow
metadata; the dispatcher deliberately accepts a finite schema subset. Output
schemas currently describe a broad common envelope. Adapter parity, result
payload types, unit/default ownership, explicit resource enforcement status and
a traversal index are the next bounded improvements. Existing local paths and
stdio calls need a future server projection and bounded jobs before web exposure.
The AU spike exposes linear gain, not the offline denoise/EQ/compression stack.

Coordination: backend lane favors a generated safe web projection over shared
`tool_api.execute`, with private artifact IDs and independent jobs. Planning lane
received CAP-1/2/3 substitution budgets and later web/AU gates. Tool-hooks lane was
asked to verify interface admission/count; root owns reconciliation.
Backend owner reviewed the completed capability draft and confirmed shared
semantics align: safe artifact-ID projection, enforced/unknown resource metadata,
and current peaking-EQ/fixed-wet-compressor limits. Classification owner supplied
source/model/feature/settings/label-revision and readiness boundaries, included
in the design. Both linked future specifications exist in the working tree.

Primary-source verification on October 6:

- [JSON Schema metadata](https://json-schema.org/draft/2020-12/json-schema-validation#section-9.2): default is metadata; application omission behavior needs its own contract.
- [JSON Schema core](https://json-schema.org/draft/2020-12/json-schema-core): schemas and vocabulary support do not establish the repository validator's full-draft compliance.
- [MCP tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools): output schemas/structured results and annotation trust boundaries.

Validation is documentary and read-only: counts and controls were checked from
current files; proposed metadata example must remain explicitly illustrative.
The embedded JSON example parsed successfully. Registry snapshot SHA-256:
`ee954d8a7b91a7dddcdd1da8d61cab3203722f345878607ea320c5a0ffbf8f83`.
Direct whitespace/final-newline checks passed for both owned documents.
No tests, audio decoding, classification, mastering or musical acceptance are
claimed. Future runtime adapters require the behavioral/property/resource gates
listed in the specification.

Escape-hatch receipt: not applicable; no process signalling or cross-session
actions. Searches of the memory registry produced no relevant project entry;
design conclusions derive from this live checkout and the primary sources above.
