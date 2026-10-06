# Capability metadata and artifact IDs (pilot, contract v1)

Status: **pilot**, S2 lane `cap_ids` (Linear TIN-5605; related TIN-5493 CAP,
TIN-5549 IDS). Lane contract: [sprints/CAP_IDS_S2.md](sprints/CAP_IDS_S2.md).
Design sources: [future/CAPABILITIES_AND_REPO_EVOLUTION.md](future/CAPABILITIES_AND_REPO_EVOLUTION.md)
(CAP-1), [future/WEB_BACKEND.md](future/WEB_BACKEND.md) (WEB-1 artifact-ID
boundary), [AGENT_TOOLS.md](AGENT_TOOLS.md).

Two stdlib-only library modules sit **beside** the tool registry. They do not
change `program/tools.json`, `scripts/tool_api.py`, MCP, the review server,
recipes or any default. Wiring either one into an operator surface is a later
root decision.

| Module | Purpose | Never does |
| --- | --- | --- |
| `program/capabilities.json` + `scripts/capabilities.py` | Closed-schema metadata for 8 pilot tools: units, default ownership, effects, resources, provenance declarations, dependencies, adapters, unknowns; static traversal capability → worker → skill → tests | Execute a worker, a test, FFmpeg or DSP; copy ranges/enums/defaults from `inputSchema` |
| `scripts/artifact_ids.py` | Opaque `art_`/`src_` IDs derived from SHA-256 and confined to `artifacts/runs`; re-hash on every resolve | Render, decode, launch a subprocess, write under `artifacts/runs`, authorize anyone, queue a job |

Invariants carried explicitly in data and outputs: `au_realtime_available: false`,
`not_a_job_service: true`, `agent_may_change_defaults: false`.

## 1. Capability metadata (`program/capabilities.json`)

Pilot tools, in this order: `denoise` (worker `scripts/media.py clean`),
`clicks`, `capture_profile`, `apply_capture_profile`, `annotation_v2`,
`corpus_split`, `editor_marker_plan`, `share_export`.

Every object is **closed**: an unknown key is `unknown_key` and an absent key is
`missing_key`. The full key and enum tables are frozen in the lane contract,
section 3. The cross-checks below make it impossible for the two files to
diverge silently.

| Field | Cross-check against `program/tools.json` |
| --- | --- |
| `implementation_status`, `evidence_kind` | equal to the descriptor (`registry_drift`) |
| `skill` | equal to the descriptor skill (`skill_mismatch`); a regular non-symlink `.agents/skills/<dir>/SKILL.md` (`skill_missing`) |
| `worker.script` | regular non-symlink `scripts/<file>.py` (`worker_missing`) whose repo-relative path appears literally in `scripts/tool_api.py` (`worker_not_allowlisted`). `apply_capture_profile` is linked `via` `scripts/capture_application_adapter.py`, which `tool_api.py` imports and which names the worker literally. `worker.entry` is the fixed subcommand (`clean`) or null |
| `tests` | 1–8 existing regular `tests/test_*.py` (`test_missing`) |
| `parameters` | key set **equals** `inputSchema.properties` (`parameter_set_mismatch`); nested `fields` for `capture_profile.peaking_eq` (3) and `.compressor` (5) |
| `default_policy` | `schema_default` ⇔ descriptor `default`; `explicit_required` ⇔ in `required`; `default_owner: none` ⇔ no default (`default_policy_conflict`) |
| `unit` | `boolean`/`json_object`/`json_array` must match the schema type, and scalar units may not label booleans, objects or arrays (`registry_drift`) |
| `resources.timeout_seconds` | `min`/`max`/`default` equal the descriptor `minimum`/`maximum`/`default` (`timeout_mismatch`) |
| `dependencies` | `advisory_prior_tools` = `recommended_prior_tools`, `enforced` = `enforced` (`registry_drift`) |
| `effects` | descriptor `readOnlyHint: true` ⇒ no writes, no renders, `output_root_policy: none` (`readonly_conflict`) |

Ranges, enums and defaults are **never re-entered**. `describe NAME` reads them
live from `inputSchema` and labels the source.

### Default ownership

| `default_owner` | Who may change the default | Pilot examples |
| --- | --- | --- |
| `operator` | Only an explicit operator decision. Covers musical and processing defaults | `denoise.profile`, `clicks.strength`, `clicks.attenuate`, `clicks.template_click_only` |
| `root` | Root, in a reviewed signed commit. Covers engineering bounds and delivery encoding | every `timeout_seconds`, `share_export.crf/height/audio_kbps/codec`, `annotation_v2.operation` |
| `none` | Nobody: the parameter has no default and is supplied explicitly per call or omitted with a declared meaning | inputs, run dirs, `capture_profile` knobs |

The value `agent` is refused (`bad_enum`). The top-level
`agent_may_change_defaults: false` encodes the never-agent invariant. A lane or
agent may *propose* a default change. Only the owner adopts it.

### Effects, resources, provenance, unknowns

- `effects`: `reads`/`writes` enums, `renders_audio`/`renders_video`. Three
  fields are constant: `overwrites_input: false`, `network: false` and
  `model_acquisition: false`. `output_root_policy` is one of `run_dir`,
  `artifacts_runs_child`, `explicit_fresh_file` or `none`.
- `resources`: `resource_class` (`metadata_light`, `analysis_cpu`,
  `media_render_ffmpeg`), `heavy_numeric`, and the enforced timeout bounds.
  `source_bytes` is `enforced` only where the worker has a literal byte bound
  on its primary input. The pilot has five:
  - `capture_profile`, `apply_capture_profile`, `share_export`: 3 GiB.
  - `editor_marker_plan`: 20,000,000-byte JSON files.
  - `annotation_v2`: 20,000-byte request.

  The other three are `unknown`/null. `memory_bytes` is `not_qualified`/null
  for 8/8.
- `provenance_emitted` lists **declarations**. Traversal labels each field
  `token_found_in_worker` (the literal token appears in the worker or adapter
  source, which is static evidence) or `declared_unverified`. Neither label is
  runtime proof.
- `unknowns` (all required, value `null`, with a `*_reason`): `memory_bytes`,
  `cpu_threads`, `output_bytes`, `musical_acceptance` (`not_established`),
  `listening_acceptance` (`not_established`), `web_admission`
  (`not_qualified`), `au_realtime` (`unsupported`).
- `adapters`: `local_cli` and `mcp_stdio` are `available`; `web_job` is
  `planned`/`unsupported`; `au_render_parameter` is const `unsupported`.

No capability field carries note correctness, missed-note, musical-quality or
listening claims.

## 2. `scripts/capabilities.py`

```bash
python3 scripts/capabilities.py validate              # closed schema + registry cross-check
python3 scripts/capabilities.py traverse [--tool NAME]  # static edges; exit 1 if any edge fails
python3 scripts/capabilities.py describe NAME         # entry + live inputSchema bounds + traversal
```

Output is deterministic sorted-key JSON on stdout. Errors go to stderr as
`{"status":"error","code":...,"error":...}` with exit 1. The library exposes
`load_capabilities(path, registry_path, root)`, `validate(doc, registry, root)`,
`traverse(doc, root, tool=None)`, `describe(doc, registry, name, root)` and
`CapabilityError(code, message)`. It has no global state, and every path is
explicit.

Loading is bounded (1 MiB, regular non-symlink file) and parsed with
`tool_api.strict_json`. Duplicate object keys are additionally refused
(`duplicate`) because `strict_json` keeps the last value. Each pilot descriptor
is checked with `tool_api.validate_schema` before cross-checking. Every
repository path must be relative and `/`-separated. It may contain no `..`,
`.`, empty, hidden (except the `.agents` head of a skill path), `:` or `\`
component, and it must resolve inside the root with no symlink component
(`unsafe_path`).

A traversal result reports four edges per tool: `capability_present`,
`worker_exists`, `skill_exists` and `tests_exist`. It also carries
`worker_allowlisted`/`worker_linkage`, `test_mentions_worker` and per-field
provenance token status, and always `claim_class: "static_repository_check"`
and `tests_executed: false`.

## 3. Artifact and source IDs (`scripts/artifact_ids.py`)

Boundary: `RUNS = <root>/artifacts/runs`. It must be an existing directory, and
neither it nor `artifacts` may be a symlink. The only accepted input is a
**runs-relative** selector `<run_id>/<component>/…/<file>` with 2–16
components, each matching `[A-Za-z0-9][A-Za-z0-9._-]{0,127}`, and at most 1024
characters. Absolute, `~`, URL, drive and repo-relative (`artifacts/runs/…`)
forms are refused, never normalized.

```text
content_sha256 = sha256(file bytes)                         # streamed 1 MiB chunks
artifact_id    = "art_" + sha256("video-utils/artifact-id/v1\0" + selector + "\0" + content_sha256)[:32]
source_sha256  = <run>/manifest.json .source.sha256          # 64 lowercase hex, else unknown
source_id      = "src_" + sha256("video-utils/source-id/v1\0" + source_sha256)[:32]
```

The manifest's `source.path` (a host path) is never copied into a record, index
or output. An ID is content-addressed: identical bytes under the same selector
give the same ID, and a rename or a byte change gives a new one. **IDs are
provenance identifiers, not access tokens.** They contain neither host path nor
selector, but anyone who holds a candidate selector and content hash can
confirm a guess, so IDs must not be treated as secrets or authorization.

### Public record (closed)

`artifact_id`, `kind` (`json`/`wav`/`video`/`other`, by suffix), `sha256`,
`size_bytes`, `state`, `source_id` (nullable), `source_binding`
(`bound`/`unknown`), `claim_class: "hash_measurement"`,
`not_a_job_service: true`, `id_version: 1`.

### Resolve semantics

`resolve(id)` re-hashes before returning and never writes:

| State | Meaning | Private `path` |
| --- | --- | --- |
| `current` | bytes hash to the projected SHA-256 (a touch without a byte change stays current) | set; intended only for a future server-side worker adapter |
| `stale` | file exists, bytes differ (same or different size) | `None` |
| `missing` | the selector no longer names a regular file (deleted, now a directory or FIFO, parent gone) | `None` |

If a stored selector now fails confinement, for example because a symlink was
swapped in for the leaf, a directory or the run directory, `resolve` raises
that refusal and never returns a path. A file that has gained an exec bit
raises `executable_refused`. `Resolution.public()` never contains a path.
`resolve_source(src_id)` re-hashes the bound manifest, and changed manifest
bytes make the source `stale`.

`project()` is idempotent: identical bytes return the identical record and add
no index entry. If the same ID would name a different (selector, sha), the call
fails with `id_collision`.

### Refusal codes (`ArtifactIdError.code`, no partial registration)

| Code | Trigger |
| --- | --- |
| `host_path_refused` | absolute, `~`, `//`, UNC, drive letter, `file:` or URL |
| `outside_runs_root` | `..` component, `artifacts/…` repo-relative prefix, resolved escape, missing runs root |
| `symlink_component` | any symlink at or below `RUNS`: run dir, intermediate dir, leaf (escaping or internal) |
| `filter_string_refused` | ``= , ; [ ] \| $ ` ' " : & < > ( ) { } * ? ! # % ^ @ + ~`` or whitespace, e.g. `anull,volume=2`, `x;rm` |
| `unsafe_component` | hidden, `.partial`, empty, leading `-`, NUL, backslash, non-ASCII, over-length, too few or too many components |
| `executable_refused` | any exec mode bit, or leading `#!`, ELF, Mach-O (thin/fat, both endians) or `MZ` |
| `not_regular_file` | directory, FIFO, socket, device or absent file at projection (leaf is `lstat`-checked before an `O_NOFOLLOW\|O_NONBLOCK` open) |
| `too_large` | over `max_bytes` (default 3 GiB) or manifest over 20 MiB |
| `changed_during_hash` | dev/ino/size/mtime_ns differ between the pre-open lstat, the open fstat, the post-hash fstat and lstat, or the file grows past its pre-open size |
| `malformed_id`, `unknown_id`, `id_collision` | ID shape, unregistered ID, conflicting registration |
| `write_inside_runs`, `target_exists`, `bad_index` | `dump`/`load` guards |

`changed_during_hash` detects cooperative concurrent writers only. A malicious
non-cooperating writer is out of scope, the same boundary as the S1 annotation
store.

### Index persistence

`dump(path)` writes deterministic sorted-key JSON (`schema:
"video-utils/artifact-index"`, `schema_version: 1`). The temp file is fsynced
and then **hard-linked** into place, which is atomic and never clobbers. A
target under `RUNS` (including through a symlinked parent) is refused, and so
is an existing target. The index stores runs-relative selectors and is a
private server-side file, not a public record. `load(path)` is closed-schema
and refuses duplicate keys. It re-derives every `artifact_id` and `source_id`
and re-validates every selector. It never trusts stored paths, and content is
re-hashed on resolve.

```bash
python3 scripts/artifact_ids.py [--root DIR] [--write-index FILE] project SELECTOR...
python3 scripts/artifact_ids.py [--root DIR] source RUN_ID
python3 scripts/artifact_ids.py [--root DIR] resolve --index FILE ID   # art_… or src_…; exit 1 unless current
```

## 4. Evidence classes

| Claim | Class |
| --- | --- |
| Document validity, registry key/timeout/default-policy agreement, refusal codes, stale/missing/idempotency behavior | measurement by unit test |
| Worker/skill/test existence, allowlist linkage, provenance tokens | static repository check (nothing executed) |
| Provenance fields marked `declared_unverified`, resource classes, `heavy_numeric` | lane declaration, not runtime-verified |
| Memory/CPU/output bounds, web admission, durable jobs, AU realtime, listening or musical acceptance | **not established** |

## 5. Not in scope

The pilot adds no HTTP route, queue, lease or durable job, and no
authorization, identity or access tokens. It does not change `tool_api.py` or
`tools.json` and admits no new MCP tool or skill. It runs no DSP and changes no
detector, profile or master default. It has no AU parameter mapping, does not
generate `CAPABILITY_INDEX.md` and covers 8 tools, not all of them.
