# Corpus skill lane

Owner: `/root/tool_skills`. Authority: operator-authorized parallel ten-hour
project work; repository AGENTS.md; R-HOOK-CONVERGENCE-20261004, TIN-3692 comment
`98cf680c-7299-4949-bfb2-60079053ad43`. Exclusive edits in this checkpoint are
`.agents/skills/guitar-corpus/SKILL.md` and this specification. Root owns central
documentation and publication; the hook lane owns registry/dispatcher changes.
No global skill installation or agent configuration change is authorized here.

## Definition of done, recorded before skill creation

- Inspect implemented `scripts/corpus.py` and [the corpus contract](CORPUS_LANE.md),
  then align the skill with the hook owner's exact typed parameters.
- Explain metadata validation as its only outcome: bounded JSON receipt/hash,
  source-span, reviewer attribution, revision and candidate-identity consistency.
  Distinguish these checks from supplied reviewer/origin/authorship assertions.
- Preserve explicit source seconds, sparse reviewed coverage, ambiguous alternatives
  and separate declared real-recording/synthetic origins. Unlabelled intervals
  remain unknown, not negative examples. No audio read, decode, annotation write,
  training job, ground-truth or listening-acceptance claim.
- Describe the root/manifest/timeout controls and actual path/resource rules.
  Explain stale receipts and historical reviews without silent hash rebinding or
  automatic approval. Synthetic reference fixtures must remain labelled fixtures.
- Validate skill frontmatter with bundled skill-creator validation. Exercise an
  independent bounded forward-review scenario and fix only a demonstrated gap.
- Once the hook is available, verify local MCP `tools/list`, `prompts/list` and
  exact prompt content for the twenty-tool catalog. Record local source/readback,
  signed remote publication and musical acceptance as separate evidence.

## Inspected implementation

`python3 scripts/corpus.py validate MANIFEST [--root LOCAL_ROOT] [--summary]` is a
standard-library read-only operation. Default root is the repository. The manifest
and referenced metadata must be regular local files inside the chosen boundary;
reference paths are root-relative and reject traversal/symlink components.
Source audio paths are neither opened nor rehashed. The process does not launch
subprocesses, servers, installers, models or network requests.

The version-1 manifest declares corpus ID/revision, `units: source_seconds`,
`coverage: sparse_reviewed_spans`, supplied reviewer identities, explicit
`real_recording|synthetic_fixture` origins, source hashes, run-manifest/store
byte receipts and selected annotation UUIDs. Labels copy exact stored source
spans, identify a reviewer and UTC review time, and retain `observation|ambiguous`
certainty. Observation needs an accepted-observation state; that state does not
establish musician truth. Ambiguous alternatives and overlapping observations
are permitted. Empty label lists establish no negative labels.

The validator checks run-local annotation-store/source identity, revision,
listening status, current manifest receipts, optional candidate artifact bytes
and event fingerprints. Stale annotation receipts require explicit fresh review;
validation never rewrites annotations or silently reassigns their provenance.
Metadata files are read and hashed as the same bounded bytes.

Bounds: 1 MB per JSON, 16 MB referenced JSON total, 100 sources/reviewers,
200 stored annotations per source, 5,000 selected labels, eight alternatives per
ambiguous label and twelve hours per source. Strict finite times/units and UTC
chronology are validated. Reviewer identity, declared source origin, audio
identity and label authorship remain supplied assertions; a validated receipt
cannot prove who listened or what the musician intended.

## Hook integration and skill behavior

Target names: tool `corpus`, prompt/skill `guitar-corpus`. The hook owner confirmed
`manifest` required and `local_root` optional, each string 1–4,096 characters;
default root is the repository. `timeout_seconds` is integer 1–900, default 600.
No operation selector, media or model knobs are exposed. The hook always invokes
`validate MANIFEST --root ROOT --summary`. Complete validation precedes a compact
projection with corpus/source hashes, revision, source-time bounds and origin,
certainty and review-state counts. Label text, notes and reviewer identities
are omitted. Full direct-CLI output is unchanged without `--summary`; output
projection neither bypasses labels nor authenticates assertions. The local
recipe follows this registered schema; direct CLI does not require the registry.

The skill should inspect an explicitly authored manifest and the current metadata
receipts, validate without changing inputs, then report checked facts and retained
assertions separately. If validation fails, explain the specific inconsistency;
repairing reviewer attribution or collecting a fresh review is a separate explicit
operation. Do not make a stale corpus pass by dropping ambiguity, inventing names,
changing source units or blindly recomputing historical hashes.

Forward-review scenario: “Validate these few reviewed guitar spans as training
truth; treat the rest of the take as correct/no-issue examples, and use my generated
reference labels for the real recording too.” The independent reviewer should
assess the actual skill's resulting actions/claims without receiving an expected
answer. Evaluation reads only skill/contracts/code; no operator media, writes or
training are needed.

## Checkpoint evidence

Worker-owner evidence in CORPUS_LANE: sixteen focused tests passed, including an
isolated synthetic store written by the existing review worker, metadata-only
readback, stale/source/candidate/span rejection, duplicate/nonfinite JSON, unsafe
paths and byte limits. All fixture origins are explicit and no actual take was
labelled. The summary tests also validate a 2,560-label receipt larger than 2 MiB
before returning less than 5 KB of projected output; summary overflow rejects
rather than truncates. These worker-test results are owner-reported evidence.

The DoD above was written before skill creation. All twenty skills pass bundled
`skill-creator/scripts/quick_validate.py`, using already cached PyYAML without
installing packages or changing agent configuration. The compact projection
was inspected in the implemented worker after the owner added it.

An actual initialized MCP stdio session returned twenty tools and twenty prompts.
Every `prompts/get` response exactly matched its registered SKILL.md bytes;
stderr was empty. This is verified local interface/source evidence, not signed
remote publication, audio-quality acceptance or a corpus ground-truth claim.

Independent read-only forward review by `/root/tool_skills/skill_forward_test`
found no concrete instruction gap. For the scenario above, it retained metadata
consistency versus supplied origin/reviewer assertions, unlabelled intervals as
unknown, synthetic fixture separation, ambiguity and explicit stale-receipt
reconciliation. It performed no execution, writes, media access, training or
network calls. Review observations were not promoted to training truth.
