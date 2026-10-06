# S2 cap_ids lane contract: capability metadata pilot and artifact-ID projection

Status: **Phase 1 contract freeze**, 2026-10-06. Lane `cap_ids`, workflow B,
branch `sprint/20261006-s2/cap_ids`, worktree `.local/sprint2/cap_ids`.
Tracker: Linear TIN-5605 (parent TIN-5599; related TIN-5493 CAP, TIN-5549 IDS).
Baseline: `4b87484d725007feca6f3a19d2c967c4ca56f513` (S2 manifest baseline).
Authority: S2 sprint manifest `program/sprints/20261006-s2.json`, repository
`AGENTS.md`, R-HOOK-CONVERGENCE-20261004 / R-N11/R-N12/R-N13. Root administers
review, signed merge, admission, publication and Linear. This lane never
pushes, merges, writes Linear, edits root-owned files or downloads models.

Design sources reused, not re-decided:
[CAPABILITIES_AND_REPO_EVOLUTION](../future/CAPABILITIES_AND_REPO_EVOLUTION.md)
(CAP-1 metadata groups), [WEB_BACKEND](../future/WEB_BACKEND.md) (WEB-1
artifact-ID boundary), `docs/spec/future/linear-ready-tickets.json` rows `CAP`
and `IDS`, [AGENT_TOOLS](../AGENT_TOOLS.md).

## 1. Scope

In scope:

1. `program/capabilities.json`: versioned capability metadata **beside**
   `program/tools.json` for exactly eight pilot tools: `denoise` (worker
   `scripts/media.py clean`), `clicks`, `capture_profile`,
   `apply_capture_profile`, `annotation_v2`, `corpus_split`,
   `editor_marker_plan`, `share_export`.
2. `scripts/capabilities.py`: stdlib-only closed-schema validator, registry
   cross-check against `program/tools.json`, and static traversal
   capability → worker script → skill → test file(s).
3. `scripts/artifact_ids.py`: stdlib-only, hash-derived opaque `source_id` /
   `artifact_id` projection confined to `artifacts/runs`, with re-hash on
   every resolve, `current`/`stale`/`missing` states and explicit refusals.
4. `docs/spec/CAPABILITIES.md`: operator/agent-facing contract for both modules.
5. Two test modules (section 7) and lane receipts under
   `docs/agent-notes/sprints/20261006-s2/cap_ids-*.json`.

Out of scope (explicitly not claimed by this lane): any edit to
`scripts/tool_api.py`, `program/tools.json`, MCP/review servers or recipes;
admission of a new MCP tool or skill; an HTTP route, web job, queue, lease or
durable job service; authorization/identity (an ID derived from SHA-256 is
provenance, **not** an access token); any DSP, rendering or numeric analysis;
default detector/profile/master changes; AU parameter mapping; generated
`CAPABILITY_INDEX.md`; domain extraction (CAP-3); all-tool web admission.

## 2. Owned files

| File | Role |
| --- | --- |
| `program/capabilities.json` | Pilot capability metadata (8 tools), closed schema v1 |
| `scripts/capabilities.py` | Validator, cross-check, traversal, CLI |
| `scripts/artifact_ids.py` | Artifact/source ID projection and resolver, CLI |
| `tests/test_capabilities.py` | Capability schema/traversal/refusal tests |
| `tests/test_artifact_ids.py` | ID derivation/confinement/stale/idempotency tests |
| `docs/spec/CAPABILITIES.md` | Published contract |
| `docs/spec/sprints/CAP_IDS_S2.md` | This lane contract |
| `docs/agent-notes/sprints/20261006-s2/cap_ids-*.json` | Dated receipts |

Generated lane outputs (gitignored) go only under
`.local/sprint2/cap_ids/artifacts/s2/cap_ids/`. Nothing is written under
`artifacts/runs/*`, `/Users/jess/Documents` or `/Users/jess/Desktop`.

## 3. `program/capabilities.json` contract (closed schema v1)

Top level, all keys required, no others accepted:

| Key | Type / constraint |
| --- | --- |
| `schema_version` | integer `1` |
| `capability_contract_version` | integer `1` |
| `registry` | const `"program/tools.json"` |
| `status` | const `"pilot"` |
| `au_realtime_available` | const `false` |
| `not_a_job_service` | const `true` |
| `agent_may_change_defaults` | const `false` |
| `pilot_tools` | array of exactly the 8 names above, unique, sorted as listed |
| `capabilities` | array, one entry per `pilot_tools` name, same order |

Per capability, all keys required (closed):

| Key | Constraint and cross-check against `tools.json` |
| --- | --- |
| `tool` | existing descriptor name |
| `domain` | enum `restoration`, `analysis`, `review`, `corpus`, `delivery` |
| `stage` | enum `render_candidate`, `event_analysis`, `profile_authoring`, `profile_application`, `annotation_store`, `split_validation`, `editor_plan`, `share_derivative` |
| `implementation_status` | must equal descriptor value |
| `evidence_kind` | must equal descriptor value |
| `worker` | `{"script": "scripts/<file>.py", "entry": string\|null}`; `entry` is the fixed subcommand (`clean` for denoise) or null; script must exist as a regular non-symlink file and its repo-relative path must appear literally in `scripts/tool_api.py` source (static allowlist linkage). `apply_capture_profile` additionally lists `via: "scripts/capture_application_adapter.py"`; `via` is otherwise null. |
| `skill` | must equal descriptor `skill`; must exist as `.agents/skills/<dir>/SKILL.md`, regular, non-symlink |
| `tests` | 1–8 unique `tests/test_*.py` paths, each existing regular file |
| `parameters` | object whose key set **equals** the descriptor `inputSchema.properties` key set (no missing, no extra) |
| `effects` | see below |
| `resources` | see below |
| `provenance_emitted` | 1–16 unique enum values (below) |
| `dependencies` | see below |
| `adapters` | see below |
| `unknowns` | object; section 6 |

Per parameter (closed): `unit` (enum: `s`, `ms`, `dB`, `LUFS`, `dBTP`, `Hz`,
`Q`, `ratio`, `fraction_0_1`, `bpm`, `frames`, `px`, `kbps`, `crf`, `count`,
`local_path`, `run_relative_path`, `sha256_hex`, `enum_token`, `boolean`,
`json_object`, `json_array`); `clock` (enum `input_audio_relative`,
`decoded_source_audio_samples`, `original_source_seconds`, or null when not a
time); `default_owner` (enum `operator`, `root`, `none`); `default_policy`
(enum `schema_default`, `explicit_required`, `omitted_means_off`,
`omitted_means_none`, `omitted_means_worker_default`); optional `fields` for
object or array-of-object parameters whose key set equals the nested
`properties` (applies to `capture_profile.peaking_eq` 3 fields and
`capture_profile.compressor` 5 fields).

Default ownership semantics. `operator`: only an explicit operator decision
changes the default (musical/processing defaults, e.g. `denoise.profile`,
`clicks.strength`). `root`: root may change it in a reviewed signed commit
(engineering bounds, e.g. `timeout_seconds`, `share_export.crf`). `none`: the
parameter has no default (explicit per call). The value `agent` is refused; the
top-level `agent_may_change_defaults: false` is the "never-agent" invariant.
Cross-checks: `schema_default` ⇔ descriptor parameter has `default`;
`explicit_required` ⇒ parameter is in `required`; `default_owner: none` ⇔ no
schema default. Ranges/enums are **never re-entered**; they are read from
`inputSchema` so the two files cannot silently diverge.

`effects` (closed): `reads` (unique enum list: `original_source`,
`run_manifest`, `run_pcm`, `run_json_evidence`, `capture_review`,
`profile_receipt`, `annotation_request`, `corpus_metadata`, `delivery_media`);
`writes` (unique enum list: `run_audio`, `run_json_evidence`,
`capture_profile_metadata`, `applied_run`, `annotation_store`, `delivery_media`,
`delivery_receipt`; empty list allowed); `renders_audio` bool; `renders_video`
bool; `overwrites_input` const false; `network` const false;
`model_acquisition` const false; `output_root_policy` enum `run_dir`,
`artifacts_runs_child`, `explicit_fresh_file`, `none`. Cross-check:
descriptor `annotations.readOnlyHint: true` ⇒ `writes` empty and both render
flags false.

`resources` (closed): `resource_class` enum `metadata_light`,
`analysis_cpu`, `media_render_ffmpeg`; `heavy_numeric` bool;
`timeout_seconds` `{min, max, default, status}` where min/max/default must
equal the descriptor's `timeout_seconds` schema and `status` is const
`enforced`; `source_bytes` `{max: integer|null, status: enforced|unknown}`;
`memory_bytes` `{max: null, status: "not_qualified"}` (const in this pilot).

`provenance_emitted` enum: `original_source_sha256`, `analyzed_input_sha256`,
`run_manifest_sha256`, `settings`, `producer_script`, `output_sha256`,
`capture_interval`, `profile_receipt_sha256`, `annotation_revision`,
`idempotency_key`, `split_assignment`, `selection_sha256`, `editor_profile_sha256`,
`delivery_receipt`, `native_clock`. These are **declarations**; traversal
reports them as `declared_unverified` unless a token search (section 4)
finds them, which is still static evidence, not runtime proof.

`dependencies` (closed): `advisory_prior_tools` must equal the descriptor's
`recommended_prior_tools`; `enforced` must equal descriptor `enforced`;
`required_artifacts` (0–8 strings, enum-free short tokens); `external_runtime`
unique enum list (`python_stdlib`, `analysis_python`, `ffmpeg`, `ffprobe`).

`adapters` (closed): `local_cli` const `available`; `mcp_stdio` const
`available`; `web_job` enum `planned`, `unsupported`; `au_render_parameter`
const `unsupported`.

## 4. `scripts/capabilities.py` contract

Library (no global state; every function takes explicit paths for testing):

- `load_capabilities(path, registry_path, root) -> dict` — strict JSON via
  `tool_api.strict_json` (read-only import), bounded 1 MiB, regular non-symlink
  file; then `validate(doc, registry, root)`.
- `validate(doc, registry, root) -> None` raises `CapabilityError(code, message)`.
  Stable codes: `unknown_key`, `missing_key`, `bad_type`, `bad_enum`,
  `bad_const`, `pilot_mismatch`, `unknown_tool`, `registry_drift`,
  `parameter_set_mismatch`, `default_policy_conflict`, `timeout_mismatch`,
  `worker_missing`, `worker_not_allowlisted`, `skill_missing`, `skill_mismatch`,
  `test_missing`, `unsafe_path`, `readonly_conflict`, `duplicate`.
  Registry itself is checked with `tool_api.validate_schema` for each pilot
  descriptor before cross-checking.
- `traverse(doc, root, tool=None) -> dict` — per tool, four edges:
  `capability_present`, `worker_exists` (+ `worker_allowlisted`),
  `skill_exists`, `tests_exist`; plus `test_mentions_worker` (worker module
  stem appears in at least one listed test file) and per-field provenance
  token status (`token_found_in_worker` / `declared_unverified`). Result
  carries `claim_class: "static_repository_check"`, `tests_executed: false`,
  `au_realtime_available: false`, `not_a_job_service: true`.
- CLI: `python3 scripts/capabilities.py validate|traverse [--tool NAME]|describe NAME`
  prints deterministic JSON (sorted keys), exit 0/1; errors as
  `{"status":"error","code":...,"error":...}` on stderr.

Path rules: every repo-relative path in the document must be relative, use
`/`, contain no `..`, `.`-prefixed, empty, `:` or `\` components, and resolve
inside `root` with no symlink component (`unsafe_path`).

## 5. `scripts/artifact_ids.py` contract (WEB-1 prerequisite)

Boundary: `RUNS = <root>/artifacts/runs`. `root` defaults to the repository
containing the module; tests pass a temporary root. `RUNS` itself must be an
existing directory that is not a symlink and resolves inside `root`.

Selector (the only accepted input form): a **runs-relative** POSIX string
`<run_id>/<component>/.../<file>`, 2–16 components, 1–1024 chars, each
component matching `[A-Za-z0-9][A-Za-z0-9._-]{0,127}` (no leading `-` or `.`,
no `.partial`). Repo-relative (`artifacts/runs/...`), absolute and `~` forms are
refused rather than normalized.

Identity derivation (deterministic, opaque, versioned):

```text
content_sha256 = sha256(file bytes)                 # streamed 1 MiB chunks
artifact_id    = "art_" + sha256("video-utils/artifact-id/v1\0" + selector + "\0" + content_sha256)[:32 hex]
source_sha256  = <run>/manifest.json .source.sha256  # 64 lowercase hex
source_id      = "src_" + sha256("video-utils/source-id/v1\0" + source_sha256)[:32 hex]
```

The source ID is bound to the original-source hash only; the host path in
`manifest.source.path` is never read into a record or output. IDs are
provenance identifiers, not authorization; they reveal neither host path nor
selector to a holder.

API:

- `ArtifactIndex(root=None, max_bytes=3 GiB)`; in-memory map `id → record`.
- `project(selector) -> dict` — validates, hashes, returns the public record
  and registers it. Re-projecting identical bytes returns the identical record
  and does not add an entry (idempotent). Same ID with different
  (selector, sha) → `id_collision` refusal.
- `project_source(run_id) -> dict` — reads `<run_id>/manifest.json` through the
  same selector checks (≤20 MiB, strict finite JSON, duplicate keys refused),
  returns `{source_id, source_sha256, run_id, manifest_artifact_id}`; missing or
  malformed `source.sha256` returns `source_id: null` with
  `source_binding: "unknown"` (never guessed).
- `resolve(artifact_id) -> Resolution` — **re-hashes before returning**.
  `state`: `current` (bytes match), `stale` (file exists, hash differs),
  `missing` (selector no longer names a regular file). Only `current` exposes
  the private `path` (for a future server-side worker adapter); `stale` and
  `missing` return `path: None`. `Resolution.public()` never includes a path.
  Resolve never writes; repeated resolves of unchanged bytes are equal.
- `resolve_source(source_id)` — re-reads/re-hashes the bound manifest; changed
  manifest bytes → `stale`.
- `dump(path)` / `load(path)` — deterministic sorted-key JSON index (closed
  schema v1). `dump` refuses any target under `RUNS` (`write_inside_runs`) and
  any existing target (`target_exists`); it writes via temp file + atomic
  replace. Loading re-validates every selector; it never trusts stored paths.
- CLI: `python3 scripts/artifact_ids.py project SELECTOR... | source RUN_ID |
  resolve --index FILE ID [--root DIR] [--write-index FILE]`.

Public record (closed): `artifact_id`, `kind` (suffix class: `json`, `wav`,
`video`, `other`), `sha256`, `size_bytes`, `state`, `source_id` (nullable),
`source_binding` (`bound`/`unknown`), `claim_class`
(`hash_measurement`), `not_a_job_service: true`, `id_version: 1`.

Refusal codes (raise `ArtifactIdError(code)`; no partial registration):
`host_path_refused` (absolute, `~`, drive/URL), `outside_runs_root` (`..`,
repo-relative prefix, resolved escape), `symlink_component` (any component
under `RUNS`, including the run dir and leaf; covers escaping and internal
links), `filter_string_refused` (selector contains filter/shell syntax such as
`=`, `,`, `;`, `[`, `]`, `|`, `$`, backtick, quote, whitespace, `:`; e.g.
`anull,volume=2`, `x;rm`), `unsafe_component` (hidden, `.partial`, empty,
leading `-`, NUL, backslash, over-length), `executable_refused` (any exec mode
bit, or leading bytes `#!`, ELF `\x7fELF`, Mach-O magics), `not_regular_file`
(directory, FIFO, socket, device; opened with `O_NOFOLLOW|O_NONBLOCK`),
`too_large`, `changed_during_hash` (dev/ino/size/mtime_ns differ before vs
after hashing), `malformed_id`, `unknown_id`, `id_collision`,
`write_inside_runs`, `target_exists`, `bad_index`.

`resolve()` of an ID whose stored selector now fails confinement (e.g. a
symlink was swapped in) returns the refusal, never a path.

## 6. Explicit unknown fields outputs must carry

`program/capabilities.json` `unknowns` per tool (closed object, all keys
required, value `null` with a sibling `*_reason` string):
`memory_bytes`, `cpu_threads`, `output_bytes`, `musical_acceptance`
(`"not_established"`), `listening_acceptance` (`"not_established"`),
`web_admission` (`"not_qualified"`), `au_realtime` (`"unsupported"`).

Every traversal result carries `tests_executed: false` and
`claim_class: "static_repository_check"`. Every artifact-ID record carries
`source_binding` (`unknown` when no valid manifest hash), `state`, and
`not_a_job_service: true`. No output may carry note correctness, missed-note,
musical quality, or listening claims.

## 7. Test protocol

Run from the worktree root:

```bash
PYTHONPATH=tests python3 -m unittest test_capabilities test_artifact_ids -v
```

No other module is directly affected (no shared file is edited); root runs the
full suite. Tests are metadata-only: no FFmpeg, no audio decoding, no
recording reads, no network. Fixtures:

- **Real registry, read-only**: worktree `program/tools.json`,
  `program/capabilities.json`, `scripts/`, `.agents/skills/`, `tests/`.
- **Mutated copies**: `copy.deepcopy` of the real capabilities document,
  validated in memory against the real registry; registry drift cases use a
  temp copy of `tools.json`.
- **Synthetic run root**: `tempfile.TemporaryDirectory()` containing
  `artifacts/runs/RUN-A/{manifest.json (source.sha256 = sha256("fixture-source")),
  result.json, audio.wav (generated bytes), export/outcome.json}`, plus hostile
  entries created per test (symlinks to outside and inside, `chmod 0o755` file,
  `#!` file, ELF-magic file, FIFO via `os.mkfifo`, hidden/`.partial` files,
  directory). Fixed byte contents; no randomness, so no seeds are needed.

`tests/test_capabilities.py` (minimum 9):

1. `test_real_document_validates_and_has_eight_pilot_tools`
2. `test_traversal_reaches_worker_skill_and_tests_for_all_eight` (32/32 edges)
3. `test_invariants_au_false_job_service_true_agent_defaults_false`
4. `test_parameter_keys_equal_input_schema_including_nested_fields`
5. `test_timeout_bounds_match_registry`
6. `test_unknown_and_missing_keys_refused` (top level, capability, parameter)
7. `test_const_and_enum_violations_refused` (au true, job service false, owner `agent`, network true, adapter au `available`)
8. `test_registry_drift_refused` (skill, evidence_kind, prior tools, enforced, extra/missing parameter)
9. `test_missing_worker_skill_test_and_unsafe_paths_refused` (temp root: removed file, `..`, absolute, symlink component)
10. `test_readonly_hint_conflict_refused`
11. `test_cli_validate_and_traverse_deterministic_json`

`tests/test_artifact_ids.py` (minimum 12):

1. `test_ids_are_opaque_deterministic_and_versioned`
2. `test_project_and_resolve_current_returns_private_path_public_omits_it`
3. `test_changed_bytes_same_size_resolves_stale_without_path`
4. `test_changed_size_and_deleted_file_resolve_stale_and_missing`
5. `test_touch_without_byte_change_stays_current`
6. `test_repeated_project_and_resolve_are_idempotent_and_write_nothing` (tree hash + mtimes of run root unchanged, index entry count unchanged, n=3)
7. `test_host_paths_and_repo_relative_forms_refused`
8. `test_traversal_and_escaping_symlinks_refused` (`..`, symlinked run dir, leaf link to outside, internal link)
9. `test_executables_refused` (mode bit, shebang, ELF, Mach-O)
10. `test_filter_and_shell_strings_refused`
11. `test_hidden_partial_dir_fifo_refused`
12. `test_source_id_from_manifest_hash_never_exposes_host_path` (fixture manifest includes `source.path` sentinel; assert absent from all output)
13. `test_missing_source_hash_is_unknown_not_guessed`
14. `test_manifest_change_marks_source_stale`
15. `test_symlink_swapped_after_projection_refuses_on_resolve`
16. `test_dump_refuses_runs_root_and_existing_target_and_roundtrips`
17. `test_malformed_unknown_and_colliding_ids_refused`

## 8. Completion metrics (denominators and claim classes)

Claim classes: **M** = measurement by test/run; **S** = static repository
check (existence/token presence, not execution); **D** = lane declaration not
runtime-verified; **NE** = explicitly not established.

| # | Metric | Target / denominator | Class |
| --- | --- | --- | --- |
| 1 | Pilot tools described and valid under closed schema | 8/8, 0 unknown keys | M |
| 2 | Traversal edges capability→worker→skill→tests | 32/32 (4 × 8) | S |
| 3 | Worker path literally allowlisted in `tool_api.py` | 8/8 | S |
| 4 | Parameter metadata key-equal to `inputSchema` with unit + `default_owner` | 48/48 top-level + 8/8 nested | M |
| 5 | Timeout min/max/default equal registry | 8/8 | M |
| 6 | Invariants: `au_realtime_available=false`, `not_a_job_service=true`, `agent_may_change_defaults=false`, `au_render_parameter=unsupported`, `network=false`, `model_acquisition=false`, `overwrites_input=false` | 3 top-level + 4×8 per-tool = 35/35 | M |
| 7 | Schema/drift refusal cases refused with expected code | ≥15 cases, 0 accepted | M |
| 8 | Artifact-ID hostile selector cases refused with expected code | ≥20 cases, 0 resolved to a path | M |
| 9 | Stale/missing detection | same-size change, size change, delete, manifest change: 4/4 correct; touch-only stays current 1/1 | M |
| 10 | Idempotency | 3 repetitions identical records; run-root tree hash unchanged; 0 index growth | M |
| 11 | Tests passing locally | ≥28 named tests (≥12 required), X/X pass, reported with exact count | M |
| 12 | Actual accepted run read-only projection (section 9) | eligible files projected / files enumerated, refused counted by code; accepted run tree hash before = after | M |
| 13 | Diff confined to owned files vs baseline `4b87484` | 0 files outside owned list | M |
| 14 | Provenance fields with worker token found | k/N reported as found, remainder `declared_unverified` | S/D |
| 15 | Resource memory/CPU/output bounds | `not_qualified` / null for 8/8 | D |
| 16 | Web admission, durable jobs, AU realtime, listening/musical acceptance | not claimed | NE |

## 9. Actual-demo read-only check (not an experiment)

After tests pass, one bounded read-only projection over the accepted run
`artifacts/runs/20261006T041633Z-990aa1bd6737` in the main checkout (passed as
`--root /Users/jess/git/video-utils`, read-only): enumerate files (≤256),
project each, record refusals by code (the hidden
`.video-frame-count-cache.json` must refuse `unsafe_component`), and compare a
pre/post tree hash (paths + sha256 + size + mtime_ns). Timeout 300 s, a single
job, hashing only (~180 MB), no FFmpeg, no decoding. Output:
`.local/sprint2/cap_ids/artifacts/s2/cap_ids/accepted-run-projection.json`
(gitignored) and a summarized receipt
`docs/agent-notes/sprints/20261006-s2/cap_ids-accepted-run-readback.json`
containing IDs, hashes, counts and refusal codes but **no host path**. This is
hash measurement; it says nothing about restoration quality.

## 10. Preregistration

Not applicable: this lane runs **no experiment** and no numerics, compares no
arms and has no held-out truth. All tests use fixed deterministic fixtures;
there are no seeds, tuning or scoring. `preregistered: false` is recorded
deliberately rather than an empty preregistration.

## 11. Root-owned changes (requested, optional, not made)

Wiring is a later root decision. If root chooses it, candidate diffs are
returned in the lane's `root_owned_changes_requested`:

1. `just/workflow.just`: optional recipes `capabilities-check` →
   `python3 scripts/capabilities.py validate && python3 scripts/capabilities.py traverse`
   and `artifact-id SELECTOR` → `python3 scripts/artifact_ids.py project`.
2. `scripts/tool_api.py`: none required. Optional future: `describe NAME` could
   attach the matching capability entry read-only. Not proposed for S2 core.
3. CI: add `test_capabilities`/`test_artifact_ids` to the root suite (they are
   discovered automatically if the suite uses unittest discovery).

## 12. Dependencies and risks

- The `fuller_profile` lane may ask root to change `denoise.profile`'s default
  or enum. Capability metadata does not copy enums/defaults; only key sets,
  timeout bounds and `default_policy` agreement are cross-checked. If root
  changes a default, `default_owner: operator` remains correct; a drift error
  would be a true positive requiring a metadata update.
- `tools.json` is read at the worktree's baseline; root re-runs validation
  after integrating other lanes.
- Hash-based IDs are content-addressed: re-rendering an identical file yields
  the same ID by design; a renamed file yields a new ID.
- `changed_during_hash` detects cooperative concurrent changes only; a
  malicious non-cooperating writer is out of scope (same boundary as S1
  annotation store).

## 13. Phase 2 outcome (2026-10-06, appended; sections 1–12 unchanged)

Implementation commit `9fa06e383cac5220aad118affa72693e1868622e`. Receipts:
`docs/agent-notes/sprints/20261006-s2/cap_ids-phase2-receipt.json` and
`cap_ids-accepted-run-readback.json`. Published contract:
[CAPABILITIES.md](../CAPABILITIES.md).

- Tests: 33/33 pass (`test_capabilities` 14, `test_artifact_ids` 19) [M].
- Validation 8/8 tools, 48/48 parameters, 8/8 nested fields, 8/8 timeouts,
  35/35 invariants [M]; traversal 32/32 edges, 8/8 allowlisted (7 direct,
  1 via adapter) [S]; provenance tokens 13/38 found, 25/38
  `declared_unverified` [S/D]; memory/CPU/output bounds not qualified [D].
- Accepted run `20261006T041633Z-990aa1bd6737` (read-only): 12/13 regular
  files projected, 1 refused `unsafe_component` (hidden frame-count cache),
  12/12 resolve `current`, manifest `output_sha256` 6/6 equal where recorded,
  tree hash unchanged. Bytes hashed 607,516,852, larger than the section 9
  estimate of ~180 MB [M]. This is not a quality claim.
- Deviations: `dump` publishes via fsync + hard link (atomic, never clobbers)
  rather than replace. Extra refusals: `MZ` magic, non-ASCII components, and a
  leading `artifacts` component. A file that grows during hashing fails fast
  with `changed_during_hash`. Both modules refuse duplicate JSON keys, which
  `tool_api.strict_json` does not.
- Correction to metadata: `apply_capture_profile.resources.source_bytes`
  is `enforced` 3 GiB (worker uses `capture.MAX_SOURCE_BYTES`).
- Root-owned wiring (optional, not made): section 11 items, returned with exact
  text in the lane's `root_owned_changes_requested`.
