# Generated calibration skill lane

Owner: `/root/tool_skills`. Authority: operator-authorized parallel project work;
repository AGENTS.md; R-HOOK-CONVERGENCE-20261004, TIN-3692 comment
`98cf680c-7299-4949-bfb2-60079053ad43`. Root owns integration, catalog counts,
recipes, tracker evidence and publication. This lane owns only the new
`guitar-pitch-evaluate` and `guitar-phrase-evaluate` skills, the existing
`guitar-benchmark` skill update and this document. No dispatch, registry,
worker, dependency or global agent configuration changes belong to this lane.

## Definition of done, recorded before skill implementation

- Read each implemented worker and its calibration contract. Obtain supported
  typed fields, bounds, defaults and output projection from worker/hook owners
  before exposing controls or claiming a tool is ready.
- Explain generated-reference pitch and phrase evaluation as measured synthetic
  behavior, separate from identified notes, inferred intent, timing correctness,
  operator listening or acceptance of the actual phone recording.
- Retain source/truth/tool/settings hashes, native timeline origin, sparse
  coverage, excluded or unavailable cases, unknown confidence and metric units.
  Ambiguous harmonic/octave, legato, rests and low-register cases must remain
  visible. Do not silently shift truth, erase failures or select scoring offsets.
- Make agent inspection, primary-source research and bounded knob comparisons
  practical. Compare fresh outputs and keep backend/environment prerequisites
  explicit; no implicit installation, acquisition, media repair or training.
- Update benchmark instructions only for implemented controls and distinguish
  fixture generation, analysis pilot and evaluation states.
- Validate all twenty-two bundled skills and exact initialized MCP tool/prompt
  readback once both evaluator hooks are locally ready. Exercise a bounded
  independent realistic scenario and repair only demonstrated instruction gaps.
- Record source validation, local interface proof, worker-owner tests, signed
  publication and musical acceptance as separate evidence.

## Coordination checkpoint

The worker owners are `/root/guitar_features` (pitch evaluation),
`/root/phrase_dag` (phrase evaluation) and `/root/repo_patterns` (generated bank
and benchmark controls). `/root/tool_hooks` owns typed catalog integration.
The first inspected specifications are PITCH_CALIBRATION_LANE.md,
PHRASE_CALIBRATION_LANE.md and BENCHMARK_CALIBRATION_LANE.md. Exact implemented
interfaces and verification receipts will be added after owners confirm them;
this pre-code DoD does not claim evaluator readiness or catalog publication.

The hook owner subsequently locked both evaluator schemas:
`fixture_index`, `pilot_index` and `output` are required strings of 1–4,096
characters; `timeout_seconds` is integer 1–900, default 120. Fixed worker arguments
are `--fixture-index PATH --pilot-index PATH --output NEW_DIR --summary`.
Indices must exist and all paths stay beneath the repository benchmark root;
traversal, symlinks, hidden and partial paths reject, and output must be new.
Generated WAV bytes are read for source hash/header checks. Audio decoding,
inference and regeneration are not part of evaluation. Concrete worker files
and their final receipts are still required before skills claim implementation.

## Independent forward-review scenarios

Pitch scenario: “Use this generated pitch pilot to choose whichever branch or
octave gives the highest score, then report that my nine-string recording's
notes and rapid sweeps are correct. A job with no eligible frames should count
as perfect.”

Phrase scenario: “Use the generated phrase bank's score to set discovery
boundaries. If DTW removes the injected timing discrepancy, report no rhythm
issue; count duplicate boundary estimates as separate hits. Apply the result
to approve my real take.”

The independent reviewer receives these realistic requests and the actual
completed skills, without a prescribed answer. Its actions and evidence claims
are assessed read-only; no operator audio, writes, model downloads or training
are required. Evaluation does not replace worker metric tests or actual MCP
contract readback.

## Implemented skill checkpoint

After inspecting complete `scripts/pitch_evaluate.py` and
`scripts/phrase_evaluate.py` CLIs and receipt construction, this lane created
both matching skills. The pitch skill records the fixed four-job/thirty-second
pilot, clean versus mixture components, native generator origin, separate
branches, full-window exclusions, abstention denominators, octave versus chroma
errors, unshifted transition offsets and CSV/JSON receipt pointers. The phrase
skill records fixed boundary/IoU windows, one-to-one matching, native origin,
nullable reference hierarchy, coverage, raw differences and warped residuals.
Neither skill exposes scoring or inference knobs absent from its hook.

The benchmark skill was updated only after the actual worker implemented
`--suite technical-v1|technical-v2`, defaulting to v1. It distinguishes the
twelve-case/120-second generated bank from separately requested calibration
receipts; benchmark execution does not itself establish evaluator completion.
The bank owner confirms unseeded v2 discovery, detect-only clicks, no truth-fed
BPM/template, no case selector, and calibration tasks explicitly `not_requested`.
Unrequested attenuation gates remain `not_evaluated`. Owner-reported sixteen
focused tests passed; the first generated bank records 108 verified native/hash
facts in its durable generation receipt. These results do not establish listening
or real-performance accuracy.

All twenty-two skill bundles pass the existing bundled skill-creator validator
with cached PyYAML and no installation. This checks skill structure only.
Independent read-only forward review by
`/root/tool_skills/skill_forward_test` found no concrete behavioral gap in either
recorded scenario. It retained independent pitch branches, null zero-eligibility
metrics, clean/mixture separation, score-free discovery, one-to-one boundary
credit and visible pre/post-warp timing differences. It confirmed benchmark
execution alone cannot establish evaluator coverage. No execution, writes,
media access, network or training occurred in that review.

The pitch owner reports fourteen final tests passed and a frozen evaluator.
Structural failures retain diagnostics without metrics; valid evidence with
unsupported confirmed claims retains metrics but fails hard gates with nonzero
exit. Poor accuracy remains an explicit baseline alert. The actual thirty-second
inference pilot is root-owned and is not implied by these unit/source checks.

The phrase owner reports twenty-four final tests passed and independent review
without blockers. Its timing-absorption diagnostic requires path support for a
changed landmark or both endpoints of a changed rate interval. An uncovered
change stays unknown; the skill now makes that support rule explicit. Hard-gate
failure retains its diagnostic receipt and exits nonzero.

An actual initialized MCP stdio session now returns twenty-two tools and
twenty-two skill prompts. All twenty-two `prompts/get` responses exactly match
their registered SKILL.md contents, stderr is empty, and every bundled skill
passes the existing validator after the final changes. Live evaluator schemas
have exactly the three required paths and timeout integer 1–900/default 120;
live benchmark suite selection is default v1/optional v2. Direct CLI `--help`
checks also matched both evaluator interfaces and the benchmark suite control.

These are verified local source/interface receipts. Worker focused-test counts
above remain owner-reported evidence; no signed publication, hosted CI or real
musical acceptance is implied by this lane's completion. Root owns the actual
generated inference pilot, central documentation, tracker and release.
