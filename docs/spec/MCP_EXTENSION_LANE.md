# Typed tool extension lane

This lane adds agent hooks to actual local workers for metronome analysis,
recurrence comparison, benchmark evaluation, and operator review annotations.
It does not treat a planned tool, published schema, or successful worker exit as
musical acceptance. Root released the publication freeze after signed CI-repair commit
`9883069b826bc1fcedbc99fe781ee41b54196d4f`. The four verified worker/skill
extensions are integrated locally as one bundle; publication remains root-owned.

Authority: repository `AGENTS.md`; R-HOOK-CONVERGENCE-20261004, TIN-3692 comment
98cf680c-7299-4949-bfb2-60079053ad43. Contributors own named files; root integrates
and publishes. Hooks remain advisory under R-N12. Worker timeout cleanup may
signal only the invocation's recorded, inspected process group under R-N11.

## Extension inventory and status

| Tool | Worker owner | Skill directory | Interface status |
|---|---|---|---|
| `clicks` | rhythm analysis lane | `guitar-clicks` | Hook integrated locally; publication pending |
| `phrase_compare` | phrase DAG lane | `guitar-phrase-compare` | Hook integrated locally; publication pending |
| `benchmark` | repository patterns lane | `guitar-benchmark` | Hook integrated locally; publication pending |
| `review` | report/review lane | `guitar-review` | Hook integrated locally; publication pending |

The four tool names and skill directories above now match actual worker
contracts and readable skills. Source verification and publication remain
separate evidence states. A review HTTP server is a
separate lifecycle; merely exposing annotation tools must never start a server,
change global configuration, or assert editor integration. Root resolves any
worker name conflict before discovery publication.


## Verified worker interfaces

These owner-supplied contracts are implemented and discoverable locally. Remote
publication and hosted-CI acceptance remain root-owned and must be verified.

- **Clicks:** `scripts/clicks.py INPUT --run-dir DIR`, optional `--bpm` 20–400,
  paired `--template-start`/`--template-end` seconds, `--attenuate`,
  `--template-click-only`, and `--strength` 0–0.5 (default 0.5). Default is
  detection-only. Attenuation requires an operator-declared click-only template,
  a 5–120 ms interval inside audio, and fit/overlap abstention. Outputs are under
  immutable unique `DIR/clicks/` children: `clicks.json`, `click-events.csv`, and
  native-rate/channel `click-attenuated.wav`/`click-estimate.wav` only for the
  explicit restoration variant. Maximum source duration 600 seconds, 1–2 audio
  channels, 8–192 kHz; no model download. NumPy/SciPy analysis needs an explicitly
  available analysis interpreter. Actual/source-lineage hashes and time axes
  distinguish click candidates from confirmed metronome identity.
- **Phrase comparison:** `scripts/phrase_compare.py RUN_DIR`, optional
  `--max-pairs` default 30/cap 60, `--band-fraction` default 0.20, `--min-rate`
  default 0.5, `--max-rate` default 2.0. Exact float ranges: band fraction >0 and ≤0.5, minimum rate 0.25–1,
  maximum rate 1–4; the alignment path may abstain when narrowed bounds exclude
  its supported instantaneous ratios.
  Maximum 384 frames per window, 100,000 sparse alignment cells per pair and
  2,000,000 per run. Requires same-source `manifest.json`, librosa analysis
  features, and recurrence candidates from `phrases.json`. Atomic
  `phrase-comparisons.json` records comparisons; existing DAG/markers are not
  rewritten by this worker. Summary keys are `comparisons_json`, `comparison_count`, `status`, and
  `review_flag_count`. Nineteen lane tests passed, and the actual take produced
  ten aligned pairs with attack-edit abstention retained. Relative timing/rate
  hypotheses stay `needs_review`,
  and legato or weak onset evidence must abstain from attack-edit claims.
- **Benchmark:** `scripts/benchmark.py fixtures --output NEW`, or
  `run --output NEW --profile conservative3 [--phrase-backend stdlib|librosa]`.
  Output must be new and under repository `artifacts/benchmarks/`. Three
  deterministic 48 kHz/eight-second synthetic cases; 120-second worker and
  600-second suite bounds, serialized execution. No operator media acquisition,
  package install, model download or network. `benchmark.json` records hashes,
  configuration, runtime, structural failures and separate quality alerts.
  Stdout summary keys are `status`, `output`, `case_count`, and `result`
  (the fixture or benchmark JSON path). Three-case worker execution and six
  lane tests passed; results remain synthetic measurements.
- **Review:** `scripts/review_server.py annotations RUN_DIR` reads JSON;
  `annotate RUN_DIR --input REQUEST_JSON` writes one operator decision. Proposed
  MCP fields are `run_dir`, `operation: read|write` (default read), and existing
  `input` JSON file for writes. The request contains `expected_revision` and an
  annotation with optional update ID, finite source-timeline span, category,
  status, note (maximum 4,000 characters), and optional candidate ID. Store
  `review-annotations.json` binds original source hash, revision, operator
  decision, timestamps and manifest/candidate artifact hashes. Stale revisions
  are rejected. Status distinguishes `annotations_loaded`/`annotations_saved`;
  listening acceptance remains `not_established`. The separate manual `serve`
  subcommand is outside the MCP tool and must not start implicitly.

## Shared contract

- Discoverable descriptors state intent, exact input schema, implementation
  status, evidence kind, skill path, recommended upstream evidence, supported
  knobs and primary-source research/iteration guidance.
- Only explicit, schema-validated parameters reach fixed local worker argument
  arrays. No caller-supplied executable, script, shell command, URL fetch,
  automatic model download or package installation is accepted.
- Local input and reference paths must resolve to existing regular files. Run
  directories and annotation targets are declared per worker. Input audio is
  immutable; compare candidates in fresh directories where reruns replace
  artifacts. Artifact path rules must be tested rather than inferred.
- Common deadlines remain integers from 1 to 900 seconds, default 600. Worker
  success returns finite structured JSON; internal failures are MCP tool errors,
  invalid schemas are protocol errors, and unknown tools fail before dispatch.
- Preserve source identity and timeline through existing worker results. Hashes
  describe original or processed inputs explicitly. Reject mismatched or stale
  upstream evidence instead of attaching it to an unrelated run.
- Operator tuning remains nine-string C F Bb Eb Bb Eb Ab C F, lowest to highest.
  Inferred octaves and theoretical frequencies are context, not detected notes.
  Protect musical fundamentals around 32 Hz, distorted harmonics and attacks.
- Automatic discovery and recurrence review need no predefined intended phrase.
  Confidence and uncertainty remain explicit. Confirmed correctness grading
  requires a qualified approved reference and calibration; relative comparisons
  must not silently become physical-phase or latency-corrected claims.
- Annotations record operator decisions separately from algorithm observations.
  A review acceptance may confirm an annotation, but does not retroactively
  change a measurement, overwrite the original analysis or establish AU/Logic
  acceptance. Each write needs source/run binding and a stale-state check.

## Integration checkpoints

1. Worker owner supplies exact CLI/schema, bounded behavior, provenance, failure
   modes and meaningful fixture results; update the inventory with evidence.
2. Skill owner writes the matching repository skill and checks discovery/research/
   supported-knob guidance against the implemented behavior.
3. After root releases the first publication freeze, add strict registry schema
   and allowlisted dispatch. Keep unsupported knobs absent and planned behavior
   labelled separately. Extend stdio prompt discovery only with readable skills.
4. Verify a real stdio invocation plus invalid arguments, worker failure,
   deadline cleanup, wrong-source/stale-reference rejection and preserved
   unknowns. A benchmark reports measured detector behavior without implying
   accuracy on the operator's take.
5. Root records receipts in `docs/agent-notes/`, publishes factual tracker
   evidence and integrates the hooks. Native editor import and AU validation
   remain their own later proof states.

## Contract tests

`tests/test_tool_contracts.py` will enforce unknown-tool and schema rejection
before subprocess launch; finite result JSON; bounded hard deadlines; inspection
and receipt of owned descendant cleanup; and evidence preserved through the
wrapper. Worker-specific schema/provenance cases are added after exact contracts
arrive. Do not encode invented future worker arguments merely to make tests pass.

## Publication freeze exception: numeric validation

On October 5, 2026, a targeted negative check showed that an enormous JSON
integer supplied to a numeric BPM knob raised an uncaught `OverflowError` in
`math.isfinite`, rather than returning invalid parameters. This could terminate
the stdio server. The root-authorized critical-fix exception was used for a
small finite-number predicate; no tool schema or feature was changed.

Receipt: `actor=tool_hooks | target/ownership=scripts/tool_api.py, existing owned
numeric validator | reason=invalid input could crash MCP stdio | ruling=root
publication-freeze critical-fix exception; R-HOOK-CONVERGENCE-20261004 / R-N12,
R-N13 | prior_state=10**400 BPM raised OverflowError before worker dispatch |
result=ValidationError and JSON-RPC -32602; worker not launched; seven extension
contract tests passed`.

A follow-up negative check also found uncaught parser recursion on 10,000 nested
JSON arrays and a nonfinite float from the standard JSON exponent `1e400`.
The same critical-fix exception adds finite-float parsing and maps parser
recursion to a controlled parse error. Results: excessive nesting returns
JSON-RPC -32700 while the stdio server exits cleanly on EOF; nonfinite worker
numbers become tool failures. No tool capability or schema was added.

Hosted Python 3.14.7 demonstrated that parser recursion is not a portable depth
limit: 10,000 nested arrays could parse successfully. A deterministic pre-parser
scanner now caps nesting at 128 levels while ignoring punctuation inside quoted
strings and handling escapes. Tests cover the exact boundary and quoted braces,
arrays, escaped quotes and backslashes. This replaces reliance on CPython's
parser recursion behavior; finite-number checks are retained.

## Local extension readback

The integrated local catalog has sixteen tools and sixteen corresponding skill
prompts. All skill files were read back through real stdio `prompts/get`.
Thirty-three hook tests passed: fourteen contract tests, eleven dispatcher tests
and eight MCP conversation tests. These include annotation revision/source
rejection, phrase-comparison source mismatch, fixture output-root rejection,
unknown knob rejection before launch and process-group deadline cleanup.

An actual `clicks` MCP call used an explicit `.venv` analysis interpreter on a
three-second synthetic 32 Hz tone with 178 BPM click events. It returned nine
candidates, unverified identity, and no WAV in default detection mode. The local
run envelope is retained at
`artifacts/contracts/clicks-bbc804919ee3/mcp-outcome.json`. This checks the actual
hook/worker/dependency path; it does not establish click accuracy or listening
acceptance on the operator's recording. The benchmark hook distinguishes
synthetic fixture generation from actual tool measurements in its evidence kind.

Publication of source, skills and registry must remain one root-owned bundle;
local test success is not hosted-CI or native-editor acceptance.

## Pitch and meter additions

The local catalog subsequently adds `pitch`/`guitar-pitch` and
`meter`/`guitar-meter`, bringing it to eighteen verified hooks. Pitch accepts
`input`, `run_dir`, `max_analysis_seconds` 1–30 (default 20) and optional
nonnegative `start_seconds`; its fixed librosa backend selects the explicit
analysis interpreter. Full per-frame evidence remains in local `pitch.json`,
while MCP returns a bounded summary containing source, lineage and actual
coverage. A known distorted-C1 MCP fixture passed in the locked Python 3.14
environment: one-second contiguous coverage of a two-second input, C1 within
1 Hz, nonunique string mapping and ungraded intended notes retained.

Meter accepts `run_dir` only besides the deadline and calls
`meter.py --run-dir`. The actual stdio fixture verified immutable output hashes,
unknown notation despite an accent-cycle hypothesis, and rejection after the
analyzed derivative changed. Final readiness and publication remain separate;
these source tests do not establish notation or listening acceptance on the take.

The fixture-generation conversation test now uses an explicit 90-second worker
deadline and a 120-second client deadline. Its earlier 30-second client timeout
expired during a loaded-host run; the bounded retry passed in 40.9 seconds.
This aligns client waiting with the worker's actual hard deadline rather than
changing benchmark measurements or generating a false successful result.

## Tonal addition

The nineteenth local hook is `tonal`/`guitar-tonal`, following independent passage
of all twenty-one locked worker tests including the optional harmonic fixture
and instrument-registry mutation check. Its exact knobs are `run_dir`,
`max_regions` 1–256 (default 128), `max_recurrences` 1–60 (default 30), and the
common deadline. It consumes existing verified restored features and writes an
immutable receipt; no decode, model download, install or expected-score gate.
The actual stdio fixture preserved null tonic/mode, separate theoretical tuning,
ungraded performance and unchanged derivative bytes. A changed derivative
rejected before an additional receipt could be written.

All nineteen catalog entries have corresponding repository skills. These
source/fixture checks do not confirm tonic, mode, intended notes, real-recording
accuracy or listening acceptance.

## Final local hook verification

The integrated nineteen-tool catalog passed all thirty-seven targeted tests in
the locked Python 3.14 environment: eighteen contract tests, eleven dispatcher
tests and eight stdio MCP tests, with no skips. FFmpeg and FFprobe were explicitly
selected from the pinned Nix FFmpeg 8.1.2 installation. The nineteen prompts were
read through real `prompts/get` conversations and matched their corresponding
skill files exactly. Tests include real bounded C1 pitch analysis, immutable
meter/tonal receipts, stale derivative rejection, annotation revision checks,
synthetic fixture output bounds and owned-process timeout cleanup.

This receipt establishes local source and fixture verification. Root owns the
matching worker/skill/registry publication bundle and hosted-CI verification;
these tests do not establish native editor, AU, Logic or listening acceptance.
