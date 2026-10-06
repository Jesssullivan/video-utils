# Capability contracts and incremental repository evolution

Status: proposed future design, October 6, 2026. Owner: `capability_future`;
root integrates. Authority: operator-requested future planning and repository
`AGENTS.md`; R-HOOK-CONVERGENCE-20261004, R-N11/R-N12/R-N13. This document does
not admit a tool, refactor a worker, expose an HTTP service, or qualify AU behavior.

The next useful architecture improvement is to make existing capabilities easier
to discover and compare, then build additional adapters from the same contracts.
Keep the current local CLI/MCP workflows usable throughout the transition.
Prioritize reference-aware phrase validation and low-register restoration over
an estate-wide rewrite.

## Verified starting point

The current working tree contains **28** descriptors in `program/tools.json` and
28 repository skills. Historical specifications still describe 27 entries;
publication and runtime qualification must be checked independently. Current
discovery paths are `just tool-info NAME`, `scripts/tool_api.py list/describe`,
MCP `tools/list`, and MCP `prompts/list/get`.

| Area | Existing owner and boundary |
| --- | --- |
| Operator entrypoint | Root `justfile` imports `just/workflow.just`; Rust `src/main.rs` supplies the native CLI. |
| DSP / media | Rust `src/lib.rs` owns reusable DSP; Python workers orchestrate bounded FFmpeg and analysis. |
| Tool definition | `program/tools.json`: closed input schemas, implementation/evidence status, skills, advisory prerequisites, workflow guidance. |
| Validation / dispatch | `scripts/tool_api.py`: bounded schema subset, source/path-specific validation, fixed worker commands, hard deadlines and result envelope. |
| Agent transport | `scripts/mcp_server.py`: serial local stdio, tools and skill prompts, common output envelope. No HTTP job or cancellation service. |
| Existing UI | `review/` and `scripts/review_server.py`: private loopback playback and source-bound annotations. No general upload/processing application. |
| Analysis runtime | `pyproject.toml`, `uv.lock`, analysis requirements locks; optional learned-pitch runtime remains separately qualified. |
| Native integration | `native/au-spike/`: gain parameter at address 0, linear range 0–16, initial value 1; host acceptance is separate. |

Some results describe internal failure, rejected evidence or incomplete
authorization inside a successfully dispatched envelope. `status=completed`
must not be converted to musical acceptance or an automatically adopted master.
The graph evaluates existing artifacts; its catalog prerequisites are generally
discovery guidance, not an automatic scheduler. `apply_capture_profile` has an
enforced authoring dependency and dedicated supervision.

## One capability model, several adapters

Retain `program/tools.json` as the capability source. Add a **versioned metadata
object beside** each existing `inputSchema`; avoid inventing unsupported schema
keywords. The current validator deliberately rejects keywords outside its
explicit subset. Adding `$ref`, `oneOf`, `format`, nullable schema types or
custom `unit` keys requires a separate validator migration and qualification.

Generate compact catalog/documentation and CLI/MCP/web projections from this
source. Handwritten worker implementations and domain checks still own behavior;
generation does not establish that a control works or make an unsupported
adapter available. Keep pure shape validation separate from source-binding,
filesystem and runtime validation.

| Metadata group | Required meaning |
| --- | --- |
| Identity | Stable existing tool name, contract version, domain, stage and implementation status. |
| Parameters | Unit; source clock where relevant; default ownership; inclusive/exclusive bounds from the actual schema; omission behavior; cross-field rules. |
| Dependencies | Distinguish advisory predecessor tools, required existing artifact types, enforced hashes and external/model/runtime dependencies. |
| Effects | Reads/writes, immutable or replaceable artifacts, output root policy, network/model acquisition policy; annotate rather than infer from a friendly title. |
| Resources | Enforced wall deadline, input/output bytes, duration, channels/rate, threads, subprocess output and memory/CPU limits, plus whether each bound is measured, enforced or unknown. |
| Provenance | Original source, analyzed input, settings, producer/version and selected upstream identities; native/source/analysis clock mapping and coverage. |
| Results | Versioned payload schema, nested domain outcomes, unknown/null behavior, compact summary and artifact references; retain existing envelope compatibility. |
| Adapters | Per-adapter availability and qualification; mapping to local CLI, MCP, web job and AU parameter, with explicit unsupported values. |
| UI hints | Label, grouping, unit display, advanced flag, reversible comparison affordance and applicability. Hints never relax validation or supply authority. |
| Guidance | Skill, research/spec links, interpretation limits, accepted evidence classes, minimum comparison artifacts and recommended next action. |

Schema `default` is metadata rather than an instruction to populate a request;
the domain must specify whether omission preserves a worker default or requires
an explicit value. This separation follows the
[JSON Schema metadata vocabulary](https://json-schema.org/draft/2020-12/json-schema-validation#section-9.2).
Our compatibility target is the repository's implemented subset, not a claim
that the present validator implements the whole draft.

### Illustrative metadata fragment

This **future proposal** describes existing `capture_profile` semantics; it is
not an object the current tool accepts. Parameter ranges are derived from the
current `inputSchema`, not independently re-entered in this fragment.

```json
{
  "tool": "capture_profile",
  "capability_contract_version": 1,
  "domain": "restoration",
  "stage": "profile_authoring",
  "parameter_metadata": {
    "reduction_db": {
      "unit": "dB",
      "default_policy": "explicit_required",
      "ui": {"label": "Noise reduction", "group": "denoise"}
    },
    "capture_start_seconds": {
      "unit": "s",
      "clock": "decoded_source_audio_samples",
      "default_policy": "explicit_required",
      "ui": {"label": "Reviewed capture start", "group": "capture"}
    }
  },
  "effects": {"writes": "immutable_source_bound_profile_metadata", "renders_audio": false},
  "dependencies": {"required_artifacts": ["verified_native_source_run", "scoped_capture_review"]},
  "resource_policy": {
    "wall_seconds": {"max": 60, "status": "enforced"},
    "source_bytes": {"max": 3221225472, "status": "enforced"},
    "memory_bytes": {"max": null, "status": "not_qualified"}
  },
  "result_contract": {
    "domain_outcomes": ["authored_unrendered", "draft_authorization_incomplete", "needs_reselection"],
    "musical_acceptance": "separate_review"
  },
  "adapters": {
    "local_cli": "available",
    "mcp_stdio": "available",
    "web_job": "planned",
    "au_render_parameter": "unsupported"
  }
}
```

At the typed boundary, implement the following concepts in the owning language
when its adapter is introduced. This notation is a proposed protocol structure,
not generated code or a new runtime dependency:

```text
CapabilityDescriptor = identity + inputSchema + outputSchema + metadata
ValidatedInvocation  = tool + contractVersion + effectiveArguments + inputBindings
ArtifactBinding      = artifactId + sha256 + kind + clock + coverage
ExecutionReceipt     = invocationHash + producerHash + resources + domainOutcome
ReviewObservation    = sourceBinding + sourceSpan + category + provenance + reviewState
```

Keep unknown musical values distinct from omitted fields and rejected evidence.
Error contracts need machine-readable codes for invalid requests, stale source
bindings, unavailable runtime, deadline, partial output and domain rejection.
Retain full bounded receipts in artifacts while returning small summaries.
For future classification jobs, bind original and analyzed hashes, source-time
regions, feature/model/settings identities, label-revision hash and optional
reference branch. Separate model-byte/license availability, runtime readiness,
guitar evaluation and calibration. Raw similarity scores remain scores; no
request-path training or download is implicit.
MCP supports structured results and optional output schemas; clients should
validate those results, and annotations are not trusted enforcement. See the
[MCP tools contract](https://modelcontextprotocol.io/specification/2025-11-25/server/tools).

## Shared controls without pretending every adapter can run every stage

The user, an agent and a future web interface should refer to the same domain
controls and units. Adapter exposure is capability-specific.

| Control or task | Current contract | Future adapter rule |
| --- | --- | --- |
| Noise interval / reduction | `capture_profile`: explicit source-reviewed interval and bounded reduction/floor/adaptivity/smoothing; `apply_capture_profile` consumes exact authoring receipt. | Web selection maps to native source samples and a source-bound review. Never infer that 0–5 s contains only fan noise. |
| EQ | Authoring allows ≤3 peaking bands, 160–6000 Hz and below Nyquist, gain ±3 dB, Q 0.5–2. | Show these admitted controls; low shelf, narrower/wider bands and other processors need distinct qualification. Do not claim this range restores missing ~32 Hz capture. |
| Compression | Five all-or-none bounded fields; fixed 25% wet and no makeup gain. | Preserve coupled validation; a generic intensity knob needs an explicit mapped recipe and comparison evidence. |
| Loudness / peak target | Explicit bounded authoring controls; later render and output measurements. | Display requested and achieved values separately; pipeline completion does not adopt the candidate. |
| Phrase classification | Automatic discovery and reference-aware branch; some newer arrangement workers are outside the admitted catalog. | Admission needs an input/output contract, skill and tests; preserve reference intent, sparse coverage and abstention. |
| User issue at timestamp | `review` reads/writes source-bound observations; graphical review has current broad categories. | Future richer mistake taxonomy maps through versioned observations without silently treating a user report as calibrated detector proof. |
| AU gain | Native spike gain address 0, finite linear 0–16, initial 1; scheduled automation qualification is separate. | Stable native address/unit/state semantics; host and render evidence gates remain explicit. |
| Noise capture / FFmpeg / ML in AU | No admitted real-time implementation. | Offline companion action only; never execute I/O, subprocesses, allocation, model inference/download or blocking work in the render callback. |

Use separate IDs for similarly named controls with different semantics: offline
`gain_db` and AU `gain_linear` are not interchangeable. Any conversion must state
its formula, finite-value policy and treatment of zero. Artifact references and
capture intervals are control-plane data, never AU render parameters.

## Traversal, documentation and cleanup

Create a generated `docs/spec/CAPABILITY_INDEX.md` later with tool → recipe →
worker → skill → contract → tests → output kinds. Add a short domain map and
ownership column so a new agent can find the correct surface without reading
every worker. Discovery should return implemented capabilities separately from
planned designs; queued tickets never become runnable tool names.

Functions at important boundaries should document what clock and units they
consume, what they write, which checks they enforce, what remains uncertain,
and failure/partial-output behavior. Use typed signatures for value structures
where practical and small examples for the public invocation path. Avoid
duplicating long parameter tables inside every function; point to the manifest
and name domain invariants that a shape schema cannot express.

Refactor by moving one domain behind compatibility shims after evidence parity.
A candidate future Python layout is `scripts/video_utils/{contracts,provenance,
media,analysis,review,restoration}`; the first extraction should be selected by
measured coupling and tests, rather than an assumed file-count target. Keep old
`scripts/*.py`, `just` recipes and local import paths during migration. Rust and
Swift remain in their current ownership boundaries until a demonstrated reuse
need justifies another package.

Do not clean up concurrent artifacts or worktrees to achieve visual neatness.
Inventory owner and retained evidence first. Split new tests/receipts by domain,
add navigation to accumulated notes, and archive only root-owned superseded
material with a durable pointer. This lane performs no cleanup/deletion.

## Milestones and candidate tickets

These are proposed planning allocations; the planning lane decides substitutions
within the existing 35-hour core/35-hour extension. They are not additional hours.

| ID / priority | Candidate work and budget | Acceptance evidence |
| --- | --- | --- |
| CAP-1 / next-week core | Inventory + metadata pilot, 2 h substituted from workflow/robustness. Pilot `probe`, `capture_profile`, `apply_capture_profile`, `review`. | All current names/args/defaults are frozen; metadata distinguishes enforced vs unknown bounds; traversal finds each pilot worker/skill/test; no DSP behavior changes. |
| CAP-2 / extension | Typed requests/results and generated documentation, 3 h from robustness. | Generated output deterministic; stale output fails CI; pilot domain outcomes validate without masking rejections; direct/tool/MCP request parity and error parity pass. |
| CAP-3 / extension | One domain extraction, 3 h from robustness after CAP-2. | Existing public entrypoints stay compatible; exact sample/source/hash behavior, rejection paths and deadline receipts pass; one representative demo retains lineage. |
| CAP-4 / future web sprint | Safe capability projection + worker adapter, estimate after backend spike. | Artifact-ID inputs resolve only inside job ownership; HTTP lifecycle performs no DSP; unsupported knobs reject; uploaded-source/analysis/delivery bindings remain intact. |
| CAP-5 / future AU sprint | Generate mappings for separately qualified native DSP controls. | Stable addresses, unit conversions, state migration and automation tests; allocation/block/I/O audit and actual host receipts. No inferred noise/EQ/compression support. |

Property tests for CAP-2/CAP-4 should randomize numeric edges, NaN/infinity,
booleans-as-numbers, absent vs explicit defaults, coupled EQ/compressor fields,
timestamp units, changed hashes, path/artifact mismatches and partial outputs.
Check that equivalent admitted invocations select equivalent worker controls
across adapters, while UI hints cannot change legality. Resource tests exercise
actual deadline/output bounds, not metadata declarations. Pin source clocks and
retained coverage so web rounding cannot shift or fabricate a musical marker.

The capability work succeeds when a musician or agent can discover the controls,
make a bounded comparison, inspect rejection/uncertainty, and keep the exact
source-timed evidence through iteration. It does not close phrase accuracy,
listening acceptance, remote-service reliability or native-host acceptance.

Related future designs: [web backend](WEB_BACKEND.md) and
[audio classification](AUDIO_CLASSIFICATION.md). Overlay taxonomy,
mastering and UI design have separate owner lanes; root links their final paths.
