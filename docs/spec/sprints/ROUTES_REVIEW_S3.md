# S3 routes_review lane contract: run graph, compare, review, deliver, jobs and tools routes over read-only run APIs

Status: **Phase 1 contract freeze**, 2026-10-07. Lane `routes_review`, sprint
`20261007-s3`, branch `sprint/20261007-s3/routes_review`, worktree
`.local/sprint3/routes_review`. Tracker: Linear TIN-5719 (parent TIN-5717,
related TIN-5547 and TIN-5550). Baseline: `4bd806db3944d05fb4b5cca16a87642a71f5458f`.
Authority: the operator route-map decision recorded in
[20261007-S3](20261007-S3.md) (build order capture -> process -> compare -> review
-> deliver -> runs/jobs/tools; prototype stubs removed), repository `AGENTS.md`,
and R-HOOK-CONVERGENCE-20261004 R-N11/R-N12/R-N13 (TIN-3692 comment
98cf680c-7299-4949-bfb2-60079053ad43).

Root reviews, signs the merge, admits recipes, publishes and writes Linear. This
lane never pushes, merges, writes Linear, edits root-owned files, downloads
models, starts a daemon, deploys anything, or writes under `artifacts/runs/*`,
`/Users/jess/Documents` or `/Users/jess/Desktop`.

Design sources are reused here, not re-decided:

- [WEB_UI_DESIGN](../future/WEB_UI_DESIGN.md): step indicator (Clip, Capture,
  Process, Review, Download); player on the left and inspector on the right with
  Cleanup, Tone, Markers and Notes tabs; a persistent **Mark here**; one column
  at narrow widths without horizontal page scroll.
- [OVERLAYS_AND_ANNOTATIONS](../future/OVERLAYS_AND_ANNOTATIONS.md): the
  operator's compact default, quoted verbatim: “Compact: section/phrase label,
  BPM, and brief issue badges.” It also sets the basis labels INTENT, REVIEW and
  USER REPORTED, and hides unavailable context by default while the inspector
  shows “unknown” with the reason.
- [REVIEW_UI_S2](REVIEW_UI_S2.md) with `review/practice_s2.js`,
  `review/practice_s2_bundle.py` and `review/practice_s2_routes.py`: matched A/B,
  the coverage strip, triaged flags with proxies hidden, labelling quick marks
  through annotations-v2, phrase timing as measurements with direction withheld,
  the 21 required unknown keys, the keyboard map and the banned-word list.
- [WEB_UI_S2](WEB_UI_S2.md) and [WEB_JOBS_S2](WEB_JOBS_S2.md): the `/api/v1`
  conventions, the error body `{status:"error", code, error}`, the loopback,
  Host, Origin and bearer checks, artifact-ID download, and the BFF/Effect
  Schema pattern.
- [TONE_S2](TONE_S2.md), [PHRASES_S2](PHRASES_S2.md), [RHYTHM_S2](RHYTHM_S2.md),
  [LOWREG_SPEC_S2](LOWREG_SPEC_S2.md), [EDITOR_EXPORT_S2](EDITOR_EXPORT_S2.md),
  [FULLER_S2](FULLER_S2.md) and [CAP_IDS_S2](CAP_IDS_S2.md): the field meanings
  of the layers these routes display.

## 1. Scope

In scope:

1. **Read API** in a new `scripts/web_runs_api.py` (section 4). It is read-only,
   confined to `artifacts/`, hash-checked and host-path-free. It is mounted into
   `scripts/web_api.py` by a root-applied registration hunk (section 11.1). The
   lane never edits `web_api.py`.
2. **BFF** server-only Effect client plus Effect Schemas in
   `web/src/lib/server/runs/`, and BFF JSON endpoints under
   `web/src/routes/api/runs/` and `web/src/routes/api/capabilities/` (section 5).
3. **Routes** (section 6): `/runs/[id]`, `/runs/[id]/compare`,
   `/runs/[id]/review`, `/runs/[id]/deliver`, the `/jobs` index and `/tools`.
   The `/compare`, `/review` and `/download` prototype stubs are replaced by run
   pickers or redirects, the root page `/` gains a runs entry, and the shared
   `+layout.svelte` gets the step bar and navigation, including the processing
   lane's routes.
4. **Review components** in `web/src/lib/components/review/`. These are Svelte
   5 ports of the S2 practice UI behaviours. They are not new analysis.
5. **Tests**: `tests/test_web_runs_s3.py` (section 8), `pnpm check` and
   `pnpm build` offline, and a synthetic-fixture walkthrough receipt.

Out of scope, and not claimed by this lane:

- new analysis, a detector re-run, DSP or numerics inside the API or the UI;
- any write route except the existing annotations-v2 write (reused unchanged);
- job submission types beyond what `web_jobs` already admits;
- adopting a default detector, profile, anchor or master;
- listening acceptance;
- note-correctness, missed-note, extra-note or phrase verdicts;
- low-register (~32 Hz) preservation claims about lossy share derivatives;
- FCPXML or Resolve import (it is labelled unverified);
- Range requests or HTTP streaming beyond the existing whole-file behaviour;
- hosted deployment and auth (lane `auth_hosting`);
- capture and process routes (lane `routes_processing`, which this lane only
  links to);
- new npm dependencies (`web/pnpm-lock.yaml` must stay byte-unchanged);
- registering new tools in `program/tools.json`. The read API is a view over
  existing evidence, not a processing primitive, so it needs no MCP tool or
  skill admission.

## 2. Owned files

| Path | Role |
| --- | --- |
| `scripts/web_runs_api.py` | Read API: runs index, run graph, layers, layer media, run artifacts, capabilities (new) |
| `tests/test_web_runs_s3.py` | Confinement, hash binding, schema, routes, static UI and walkthrough tests (new) |
| `web/src/routes/+layout.svelte` | Step bar and primary navigation (shared shell) |
| `web/src/routes/+page.svelte` | Clip library page: adds a runs entry. `+page.server.ts` is not owned |
| `web/src/routes/runs/**` | `/runs` index, `[id=runid]` graph, `compare`, `review` and `deliver` pages, plus `[id=runid]/+layout.server.ts` (step context) |
| `web/src/routes/compare/**`, `review/**`, `download/**` | Run pickers or redirects that replace the prototype stubs |
| `web/src/routes/jobs/+page.svelte`, `jobs/+page.server.ts` | `/jobs` index (`jobs/[id=jobid]` is not owned) |
| `web/src/routes/tools/**` | `/tools` page |
| `web/src/routes/api/runs/**`, `web/src/routes/api/capabilities/**` | BFF JSON and media pass-through endpoints |
| `web/src/params/runid.ts` | Run-ID param matcher |
| `web/src/lib/components/review/**` | Player, inspector, overlay ribbon, A/B, flags, timing, spectrogram, Mark here, step bar |
| `web/src/lib/server/runs/**` | Effect client, Effect Schemas, decode helpers and schema fixtures for the runs API |
| `docs/spec/sprints/ROUTES_REVIEW_S3.md` | This contract. Later changes are appended as dated sections |
| `docs/agent-notes/sprints/20261007-s3/routes_review-*.json` | Receipts: contract, tests, check/build, walkthrough, handoff |

Generated outputs (gitignored) go only under
`.local/sprint3/routes_review/artifacts/s2/routes_review/`. Tests use
`tempfile.TemporaryDirectory()` repository roots. They never read
`artifacts/runs/*` in the main checkout, and they never open the real take.

Reused modules are imported and never edited: `artifact_ids` (selector checks,
`artifact_id_for`, `source_id_for`, `check_run_id`, `ArtifactIndex.project`),
`annotation_v2` (`LABELS`, `BASES`, `KINDS`), `capabilities` (`load`/check
helpers), `web_jobs` (`WebJobsError`, `ARTIFACT_ID`, `file_signature`), and
`review/practice_s2_routes.py` (its `read_bundle` verification pattern, reused
by import or mirrored). Web modules are imported and never edited:
`$lib/server/config` (`readControlApiConfig`), `$lib/server/control-client`
(error classes, `toBffError`, `openArtifact`, `openSourceMedia`,
`readAnnotations`, `writeAnnotation`), `$lib/schema/control` (`JobList`,
`ArtifactId` and other existing schemas), `$lib/components/AnnotationPanel.svelte`,
`UnknownValue.svelte`, `UnknownsBlock.svelte` and `JobStateBadge.svelte`.

## 3. Data model the routes read

### 3.1 Run

A run is a directory `artifacts/runs/<run_id>/` that passes
`artifact_ids.check_run_id` and contains a regular, non-symlink
`manifest.json` of at most 20 MiB. The API reads only these manifest fields:
`run_id`, `status`, `schema_version`, `source.sha256` (never `source.path`),
`pcm`, `timeline`, `outputs`, `output_sha256`, `restoration_stages`,
`frequency_preservation`, `profile` (the name plus the numeric knobs exactly as
recorded), `loudness.*.target_*`, `capture_profile_application.listening_accepted`,
`noise_capture.selected_seconds` and `noise_capture.review`, and `dsp_latency.*.status`.
`run_dir`, `source.path`, `authoring_dir`, `commands` and `tools` are never
projected, because they carry host paths or command strings.

**Signal versions.** Each file in `outputs` is a stage node. Its signal version
is `sha256:<output_sha256[file]>`. Its state comes from a re-hash, cached by a
`(dev, ino, size, mtime_ns, ctime_ns)` signature, and is one of:

- `current`: the bytes match the manifest;
- `stale`: the bytes differ;
- `missing`: no regular file is present;
- `unbound`: the manifest records no hash.

`export/*` video files are projected through `artifact_ids.ArtifactIndex.project`.
They are hash-identified but not manifest-bound unless `export/outcome.json`
records their hash.

**Stage roles.** Stage roles come from a lane-owned filename map, with
`role_basis: "routes_review filename map; not a manifest field"`:

| File | Role |
| --- | --- |
| `source.wav` | Decoded native source PCM |
| `denoised.wav` | Pure denoise (afftdn) |
| `processed.wav` | Tone and dynamics |
| `cleaned.wav` | Delivery master |
| `baseline.wav` | Normalization-only baseline |
| `residue.wav` | Removed-signal estimate |
| any other file | `unknown` |

Graph edges come from the same map: source -> denoised -> processed -> cleaned,
source -> baseline, and source and denoised -> residue. Each edge carries
`edge_basis` with the same wording.

**Listening acceptance.** It is shown as accepted only through a pinned
acceptance receipt: a constant list in `web_runs_api.py` of `(repo-relative
path, sha256)`, which initially holds the one entry
`docs/agent-notes/2026-10-06-fuller-listening-acceptance.json` with
`0f8d3dbf…8e92`. The receipt must re-hash to its pin, and its `run_id`,
`manifest_sha256` and `cleaned_wav_sha256` must equal the current values.
Accepted output then carries the receipt's `scope` sentence verbatim and
`master_adopted: false`. In every other case the output carries
`listening_acceptance: {value: "not_established", reason}`. This is the only
read outside `artifacts/`. It is pinned by path and hash and never resolves a
caller-supplied path.

### 3.2 Evidence attachments (layers)

Evidence that belongs to a run lives outside `artifacts/runs`. Discovery is a
bounded walk of `EVIDENCE_ROOTS = ("s2", "s3", "experiments")` under
`artifacts/`, with these limits:

- maximum depth 5;
- at most 20 000 directory entries examined per request;
- no symlink is followed at any component;
- files at most 20 MiB;
- `artifacts/runs` is never entered.

Over the limit the response says `discovery_truncated: true`. The walk accepts
only these closed kinds:

| Kind | File name and schema | Binding rule (all must hold) |
| --- | --- | --- |
| `practice_bundle` | `bundle.json`, `schema_id == "video-utils.practice-s2.bundle"`, `schema_version == 1` | `session_binding.run_id == run_id`; `session_binding.manifest_sha256 ==` the current manifest sha256; `original_source_sha256 ==` the manifest `source.sha256` |
| `lowreg_render` | `render.json`, `schema == "lowreg-render-v1"` | The resampler record's parent input sha256 is the `output_sha256` of a `current` stage of this run. Without a resampler record the result is `unbound` and nothing is displayed |
| `editor_marker_export` | `editor-marker-export.sidecar.json` | `source_sha256 ==` the run source sha256. The staged `Info.fcpxml` or `resolve-operations.json` re-hashes to the sidecar record |
| `marked_compact` | `receipt.json` with the `marked_compact` tool marker | Its run identity and audio hash equal this run's `cleaned.wav` `output_sha256`. The `.mov` re-hashes to the receipt |

Each attachment gets an opaque evidence ID:
`evd_ + sha256("video-utils/run-evidence/v1\0" + path-relative-to-artifacts + "\0" + file_sha256)[:32]`.
The path itself is never returned.

An attachment whose binding fails because the run changed is listed as
`invalidated`. The reasons are:

- `bound_manifest_changed`;
- `analyzed_input_not_current`;
- `file_hash_mismatch`;
- `source_mismatch`.

An invalidated attachment is never drawn on an overlay. A document that fails
its schema check is listed as `refused` with a code. When several
`practice_bundle` attachments are `current`, the newest `generated_utc` wins
(ties go to the lowest evidence ID). The others are listed as `alternatives`,
and `?evidence=evd_…` selects one of them explicitly.

**Layers.** The practice bundle supplies:

| Layer | Content |
| --- | --- |
| `tone_ab` | Excerpts, `loudness_match`, `region`, `trial`, `claims`, `unknown_field_reasons` |
| `coverage` | Intent spans from the `phrase_anchor` projection, with `join_confidence`, uncertain joins and `breakdown1_execution`, plus detector spans. `overlap_is_not_agreement` is kept |
| `flags_triage` | `shown`, `suppressed` and `hidden_navigation` proxies, denominators |
| `phrase_timing` | Schema 2 rows; schema 1 is refused as `layer_schema_superseded` |
| `unknown_fields` | The bundle's unknown fields, carried as recorded |

The layers are copied with their own status values. A layer that is
`unavailable` keeps its reason.

**BPM and the click grid.** These come only from fields already present in
those layers: the `phrase_timing` `click_reference` and the `flags_triage`
`timeline` and `window_basis`. If none is present, `bpm` is
`{value: null, reason: "no fitted click grid in bound evidence"}`. The API never
fits a grid.

### 3.3 Capabilities

`GET /api/v1/capabilities` projects three files:

- **`program/tools.json`**: all 40 tools with `name`, `title`,
  `implementation_status`, `evidence_kind`, `annotations`, `skill`, the
  `limitations` count and `dependencies`. `inputSchema` is summarized by
  property names and required keys. Ranges are not re-entered.
- **`program/capabilities.json`**: `domain`, `stage`, `effects`, `resources`
  and per-parameter `default_owner` and `default_policy` for the 8 pilot tools.
  The other 32 tools carry `capability: null` with the reason
  "capability pilot covers 8 tools".
- **`program/models.json`**: each entry with `format`, `license`, `sha256`,
  `max_bytes`, `source_commit` and the URL host only. A model is
  `registered_hash_bound` if it has a sha256 and a max_bytes, otherwise
  `registered_incomplete`. `local_presence` is `not_checked`.

Unknown extra model fields named `lane`, `gate`, `gate_state` or `status` pass
through as bounded strings, so a later root edit by the `model_lanes` lane
appears without an API change. When they are absent, `gate_state` is
`{value: null, reason: "not recorded in program/models.json"}`.

**Area grouping.** A tool's area is its `capabilities.json` `domain` when one
exists. Otherwise it comes from a lane-owned `TOOL_AREAS` map, carried with
`area_basis: "routes_review presentation map; not a registry field"`. The map's
areas are:

- `restoration`
- `analysis`
- `phrase_rhythm`
- `pitch`
- `review`
- `delivery`
- `corpus_eval`
- `pipeline_report`

A tool absent from both appears as `area: "unmapped"`. A test fails if any
registry tool is unmapped.

## 4. Read API (`scripts/web_runs_api.py`)

Every route is `GET` only (any other method returns `405 method_not_allowed`).
They run inside the existing web_api trust boundary: 127.0.0.1, the Host and
Origin checks and the bearer token are applied by `web_api.Handler._trusted()`
before dispatch. Errors are raised as `web_jobs.WebJobsError`, so the body is
`{status:"error", code, error}`. A response never contains a host path, a
selector, a username, the repository root, the state root, a token or a command
string. Every JSON response has `schema_id` and `schema_version: 1`, is strict
finite JSON (`allow_nan=False`), and is capped at 4 MiB (`layers_too_large`
returns 507 when exceeded).

| Method and path | Query | Success | Refusals |
| --- | --- | --- | --- |
| `GET /api/v1/runs` | `limit=1..500` (default 100) | `200 {schema_id:"video-utils.web-runs.list", runs:[RunSummary], truncated}`. The newest run ID sorts first. No re-hash is done; each row carries `state_basis:"listing does not re-hash"` | `400 bad_query` |
| `GET /api/v1/runs/{run_id}` | none | `200 RunGraph` (section 4.1) | `400 malformed_id`, `404 unknown_run`, `403 confinement_refused`, `422 manifest_unreadable` |
| `GET /api/v1/runs/{run_id}/layers` | `evidence=evd_…` (optional) | `200 RunLayers` (section 4.2) | as above, plus `404 unknown_evidence`, `409 evidence_invalidated` (an explicitly selected attachment that is no longer current) |
| `GET /api/v1/runs/{run_id}/layers/media/{evidence_id}/{name}` | none | `200` bytes, inline, `X-Artifact-Sha256`, `Accept-Ranges: none`. The name must be in the attachment's media table and re-hash to its recorded sha256 | `404 unknown_media`, `409 media_stale`, `410 media_missing`, `403 confinement_refused` |
| `GET /api/v1/runs/{run_id}/artifacts/{artifact_id}` | `disposition=inline\|attachment` (default `attachment`) | `200` bytes for a file of this run (`outputs`, `export/*`) or of a bound `editor_marker_export` or `marked_compact` attachment. Re-hashed before sending, with the same bytes guard as `web_api._send_file` | `400 malformed_id`, `404 unknown_artifact`, `409 artifact_stale`, `410 artifact_missing` |
| `GET /api/v1/capabilities` | none | `200 Capabilities` (section 3.3) | `500 registry_unreadable` (generic text, no path) |

### 4.1 `RunGraph` (closed keys)

```
schema_id "video-utils.web-runs.run", schema_version 1,
run_id, run_status, manifest_sha256, source_sha256, source_id (src_… | null),
admitted_sources: [{source_artifact_id, kind, has_annotation_clock: bool|null}],
pcm: {sample_rate, channels, sample_count, duration_seconds},
timeline: {audio_start_seconds, format_start_seconds, no_time_stretch, axis: "decoded source audio seconds"},
stages: [{stage, file_role, role_basis, artifact_id, signal_version, state, size_bytes}],
edges: [{from, to, edge_basis}],
processing: {profile_name, denoise:{filter, delay_samples, status}, tone:{peaking_eq, compressor},
             loudness_targets, high_pass_applied, hum_notches_applied, intentional_low_fundamental_hz},
evidence: [{evidence_id, kind, state: current|invalidated|refused|unbound, reason, bound_signal_version,
            generated_utc|null}],
invalidation: [{evidence_id, reason, was_bound_to, now}],
listening_acceptance: {value, reason, scope|null, receipt_sha256|null},
claim_boundary: {listening_acceptance_scope, musical_verdict:"not_established",
                 missed_or_extra_notes:"not_assessed_no_approved_reference",
                 default_adopted:false, master_changed:false},
unknown_fields: {...section 7...}, discovery_truncated
```

`admitted_sources` is a read-only lookup in the web_jobs `sources` table. A row
matches when its `source_id` equals the run's `source_id`, or its selector
begins with `<run_id>/`. Only artifact IDs are returned.
`has_annotation_clock` is true when a succeeded `share_export` job exists for
that source, false when none exists, and null when the lookup is unavailable.

### 4.2 `RunLayers` (closed keys)

```
schema_id "video-utils.web-runs.layers", schema_version 1, run_id, manifest_sha256,
selected_evidence_id | null, alternatives: [evidence_id],
layers: {tone_ab, coverage, flags_triage, phrase_timing, spectrogram, bpm},
media: {name: {evidence_id, sha256, frames, sample_rate, channels, role}},
spectrogram: {status, evidence_id, signal_version, shape:{frames,bands}, band_centre_hz_range,
              hop_seconds, window_seconds, matrices:[{name, media_name, sha256, dtype, layout}],
              claim:"visualisation only; no pitch, note or stem claim"} | {status:"unavailable", reason},
clock: {layer_axis:"original source decoded-audio seconds", annotation_axis, alignment:"unverified", reason},
unknown_fields, claim_boundary
```

## 5. BFF (`web/src/lib/server/runs/`, `web/src/routes/api/{runs,capabilities}/`)

- `client.ts` reads the control config through `readControlApiConfig()` and
  reuses the existing error classes and `toBffError`. `requestJson` in
  `control-client.ts` is module-private, so the lane implements an equivalent
  bounded fetch with these limits:
  - 5 s request timeout;
  - JSON response cap of 4 MiB (layers can exceed the 1 MiB default);
  - streaming idle timeout of 30 s;
  - the same token header and host checks.

  An optional consolidation request is in section 11.3.
- `schema.ts` holds Effect Schemas for `RunSummary`, `RunList`, `RunGraph`,
  `RunLayers` and `Capabilities`, decoded closed
  (`onExcessProperty: "error"`, `errors: "all"`). Nullable unknown fields stay
  nullable and keep their reasons. Copied layer documents (tone_ab, flags
  triage, phrase timing) are decoded as closed envelopes with the inner
  documents typed as far as the UI reads them, and passed on as
  `Schema.Unknown` beyond that, so a producer field addition cannot break the
  page. A decode failure returns BFF `502 control_api_decode_error` with issue
  paths and no values.
- These BFF endpoints accept GET only. IDs are validated before any upstream
  call; an invalid ID returns 404 at routing time.
  - `api/runs/+server.ts`
  - `api/runs/[id]/+server.ts`
  - `api/runs/[id]/layers/+server.ts`
  - `api/runs/[id]/layers/media/[evidence]/[name]/+server.ts`, a streaming
    pass-through that keeps `X-Artifact-Sha256`
  - `api/runs/[id]/artifacts/[artifact]/+server.ts`, a streaming pass-through
  - `api/capabilities/+server.ts`
- `params/runid.ts` matches `artifact_ids.COMPONENT`
  (`^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$`) and rejects `.partial`.
- The client bundle must contain no token, no control URL and no
  `$lib/server` import. This is checked by the existing `test_web_stack` s10
  pattern, re-run as a directly affected module.

## 6. Routes and UI behaviour

### 6.1 Shell (`+layout.svelte`)

Primary navigation, in order:

1. Clips `/`
2. Upload `/upload`
3. Runs `/runs`
4. Jobs `/jobs`
5. Tools `/tools`

**Step bar.** It shows Clip, Capture, Process, Review and Download, and it
appears whenever `page.data.stepContext` is present. It is a cross-lane
interface:

```
stepContext = {current: "clip"|"capture"|"process"|"review"|"download",
               source_artifact_id: string|null, run_id: string|null,
               disabled_reasons: {step: reason}}
```

Steps link to these routes:

| Step | Route |
| --- | --- |
| Clip | `/sources/[source_artifact_id]` |
| Capture | `/sources/[source_artifact_id]/capture` (routes_processing) |
| Process | `/sources/[source_artifact_id]/process` (routes_processing) |
| Review | `/runs/[run_id]/review`, with Compare and Graph as sub-tabs |
| Download | `/runs/[run_id]/deliver` |

A step without a target renders as text with its disabled reason. It never
renders as a dead link. Run routes provide `stepContext` from
`runs/[id=runid]/+layout.server.ts`. The routes_processing lane provides it on
source routes. If that lane does not, the bar still renders from the run side.

The shell also has a skip link and visible focus. The loopback pilot banner and
the claim footer are kept.

### 6.2 `/runs` and `/runs/[id]`

- `/runs` is a table of runs: ID, status, source ID and a link.
- `/runs/[id]` is the run graph. It shows:
  - the stage list with role, signal version (short sha with the full value in
    a title), state badge (text and shape, never colour alone) and its basis;
  - the edges as an ordered list, not a drawing;
  - processing knobs as recorded, with "no high-pass" and "no hum notch" shown
    from manifest fields;
  - evidence attachments with state and reason, and the invalidation list;
  - listening acceptance with its scope sentence;
  - the unknowns block.

### 6.3 `/runs/[id]/compare`

This page shows matched-level A/B from the `tone_ab` layer.

- **Arms** are listed with `lufs_before`, `gain_db` and `lufs_after`, the match
  status, the per-arm `abs_delta_lu`, and the region with its excluded setup
  interval.
- **Excerpt pairs** (X/Y): the blind mapping stays hidden until a local reveal
  toggle. The reveal is never saved.
- **Trial** excerpts are labelled "unreviewed trial; not adopted".
- **Players**: one active player at a time. Starting one pauses the others.
  `preload="none"`, no autoplay.
- **Band and attack measurements** are shown as measurements with denominators.
- `operator_preference` is shown as "not recorded" with no control.
- `browser_level_match` is shown verbatim.

If no bundle or `tone_ab` layer is available, the page states the reason and
links to the run graph.

### 6.4 `/runs/[id]/review`

**Layout.** The player is on the left. The source video comes from the
existing `api/sources/[id]/media` of the admitted source that has an annotation
clock; when several qualify the operator picks one, and the default is the most
recent. Below the player sit the source-time tracks: intent spans, detector
spans, flags, the click grid and the spectrogram. The inspector is on the right,
with Cleanup, Tone, Markers and Notes tabs. The selected span and source time
stay visible in every tab. Below 768 px everything forms one column. The
timeline pans inside its own labelled viewport.

**Compact overlay toggles.** By default the phrase/section label, BPM and at
most two issue badges are on. The basis labels are INTENT, REVIEW and USER
REPORTED. Optional toggles are:

- uncertain joins, shown as a dashed boundary with the text "uncertain join";
- breakdown execution unknown;
- the click grid;
- navigation proxies (four-pulse groups), off by default and labelled
  "navigation proxy; not a confirmed bar";
- suppressed flags, off by default;
- the spectrogram, with log-power dB by default and PCEN labelled experimental.

Overlap between intent and detector spans is rendered with the text "overlap is
not agreement".

**Phrase timing.** Per-phrase rows show the signed median, the IQR and the
count, as measurements. A real-take row reads "direction withheld
(uncalibrated)". An abstained row shows `—` plus its reason, never 0. A
direction class appears only for a `synthetic_fixture` run kind, labelled
"synthetic known-offset fixture".

**Spectrogram.** The page fetches the bound log-power matrix through layer
media and draws it to a canvas with a fixed colour map, adding a text legend.
The y axis uses `band_centre_hz` labels and marks the C1 32.7 Hz string as
"theoretical C1 (instrument.json)". It is a visualisation only, with no claim.

**Mark here.** It is persistent and never covers the transport. It writes
through the existing `api/sources/[id]/annotations`, which uses annotations-v2
semantics with no new route. It accepts a point or an ordered span, a kind
(`annotation_v2.KINDS`), certainty, text and an optional candidate link (only
for an ID present in the session's markers). The time is the player
`currentTime` plus the clock's `source_start_seconds`, as in S2. The clock
alignment between layers and annotations is shown as "unverified". Saved items
render with `annotation_v2.LABELS`:

- `operator_assertion` is USER REPORTED (solid marker, "User report");
- `operator_context` is INTENT;
- `detector_hypothesis` is REVIEW (hollow marker, "Review candidate");
- `reference_comparison` is REFERENCE REVIEW.

Each basis has its own shape and text, in addition to colour. A user item and
a detector item at the same time are rendered as two items. Without an admitted
source that has a clock, Mark here is disabled with the reason
`run_source_not_admitted` or `annotation_source_clock_unknown`, and the layers
still render.

**Labelling session.** The S2 quick-mark queue is ported with the same save,
retry and stale semantics as REVIEW_UI_S2 section 5.7. It shows an
unsaved-changes prompt while the queue is non-empty.

**Keyboard parity.** The keys match the S2 practice UI exactly:

| Key | Action |
| --- | --- |
| `←` / `→` | Seek −/+ step |
| `[` / `]` | Set span start/end |
| `L` | Loop selected span |
| `B` | Queue a phrase_duration point mark |
| `I` | Queue a mark of the selected kind |
| `N` / `P` | Next/previous intent boundary |
| `Shift+N` / `Shift+P` | Next/previous shown flag |
| `U` | Undo the last queued mark |

The keys fire only when focus is in the transport or the quick-mark bar. They
never fire in `input`, `select` or `textarea` or with Alt, Ctrl or Meta held.
No key starts playback.

**No autoplay.** No owned file contains an `autoplay` attribute or a `.play(`
call site.

### 6.5 `/runs/[id]/deliver`

Each item is listed with its artifact or evidence ID, sha256, size and a
download link that goes through the BFF pass-through by ID only:

- **Restored video**: the run `export/*.mov`.
- **Delivery WAV**: `cleaned.wav`, with the native rate and channels stated.
- **Share MP4s**: the succeeded `share_export` jobs of admitted sources, through
  the existing `api/artifacts/[id]`. They are labelled "lossy sharing
  derivative; low-register preservation not claimed".
- **Marked compact movie**: when bound.
- **Marker files**: when an `editor_marker_export` attachment is bound, FCPXML
  and Resolve operations are each labelled "import unverified (no editor
  application proof)". When none is bound, the page states "not exported or
  calibration_required" and offers no button.

The accepted-listening label appears only on the exact files the receipt names.

### 6.6 `/jobs`

The jobs page is a table from `GET /api/v1/jobs?limit=200`, decoded with the
existing `JobList` schema. It shows state badge, tool, reason code, attempts,
artifacts, created and updated times, and a link to `/jobs/[id]`. If the upstream
list is truncated, that is stated. Cancel and retry stay on `/jobs/[id]`, which
is unchanged.

### 6.7 `/tools`

The tools page groups the 40 tools by area. Each card shows:

- status, evidence kind and the annotation hints;
- the skill path;
- the limitations count with an expandable list;
- dependencies.

The 8 pilot tools also show capability effects (reads, writes, renders,
network, model acquisition), resources (resource class, heavy numeric, timeout
bounds) and default ownership.

A model section lists the `models.json` entries with their gate state and
`local_presence: not_checked`. A static note says that S3 model lanes (Beat
This, guitar_noul, stems) are tracked in TIN-5721 and appear here only once
root registers them in `program/models.json`.

### 6.8 Stub replacement

Each prototype stub becomes a run picker, and a picker with exactly one run
redirects (303). Their `PrototypeNotice` imports are removed.

| Stub | Run picker target |
| --- | --- |
| `/compare` | `/runs/[id]/compare` |
| `/review` | `/runs/[id]/review` |
| `/download` | `/runs/[id]/deliver` |

## 7. Unknown fields the outputs must carry

`RunGraph.unknown_fields` and `RunLayers.unknown_fields` carry each key below
as `{value, reason}`. The UI's `UnknownsBlock` must render every key with its
reason.

The 21 S2 keys are carried as the bundle records them, or with the S2 default
when no bundle is bound:

- `operator_preference`
- `listening_acceptance`
- `perceived_fullness`
- `nasal_quality`
- `fundamental_32hz_presence`
- `monitoring_device`
- `true_peak_dbtp`
- `fan_only_gain`
- `music_only_gain`
- `click_identity`
- `physical_capture_latency`
- `detector_delay`
- `meter`
- `downbeat_confirmed`
- `anchor_adopted`
- `breakdown1_execution`
- `real_take_phrase_correctness`
- `missed_or_extra_notes`
- `phrase_timing.real_take_status`
- `browser_level_match`
- `walkthrough_listening`

The S3 additions, with their required values:

| Key | Value | Reason |
| --- | --- | --- |
| `clock_alignment` | `unverified` | Layer axis is decoded source audio. Annotation axis is the web clock manifest (share_export packet extent) |
| `bpm` | `null` unless copied from bound evidence | "no fitted click grid in bound evidence" |
| `annotation_source` | `null` when no admitted source has a clock | — |
| `editor_import` | `unverified` | — |
| `share_low_register_preservation` | `not_claimed` | Lossy AAC derivative |
| `model_local_presence` | `not_checked` | — |
| `model_gate_state` | `null` unless recorded | — |
| `tool_area_basis` | the presentation-map basis | — |
| `physical_av_sync` | copied from `dsp_latency.physical_audio_video_sync_verified` | Currently false |
| `spectrogram_binding` | `unbound` or `unavailable` | When there is no bound render |
| `room_response_recovered` | `false` | — |
| `stems` | `not_available` | No stem lane is admitted, and an estimate would never be an original stem |

## 8. Test protocol

Run from the worktree root:

```bash
PYTHONPATH=tests python3 -m unittest test_web_runs_s3 -v
PYTHONPATH=tests python3 -m unittest test_web_stack test_web_parity test_artifact_ids -v   # directly affected
```

Never run the full suite (root does). Media jobs run with
`FFMPEG=/nix/store/mv3x2v2pr6pwvwj7cdyh8nci2q1wpnjq-ffmpeg-headless-8.1.2-bin/bin/ffmpeg`
and the matching `FFPROBE`. There is at most one heavy job at a time, each
with an explicit timeout.

**Fixtures.** All fixtures are synthetic. They are built per test in a
`TemporaryDirectory` laid out as a repository root:

| Fixture | Content |
| --- | --- |
| `artifacts/runs/<run>/manifest.json` | Generated by the test |
| Stage files | Small deterministic WAVs: 1 s of a 32.7 Hz + 196 Hz sine at 8 kHz, PCM16, written by `wave` |
| Practice bundle | Built from the S2 synthetic shapes. The test writes JSON shaped like `artifacts/s2/ui_core/synthetic/bundle/bundle.json` but generated in-test; the real file is never read |
| `lowreg_render` | `render.json` plus a 4×160 float64 matrix, hand-built with no DSP |
| Editor marker sidecar | Plus `Info.fcpxml` |
| Pinned acceptance receipt | A test-local pin list replaces the constant through a constructor argument |

The real take, `artifacts/runs/*` in the main checkout,
`/Users/jess/Documents` and `/Users/jess/Desktop` are never touched.

**Test classes in `tests/test_web_runs_s3.py`.** The names are frozen; cases
may be added.

1. **`Confinement`.** 16 adversarial cases, each refused with a typed code and
   never a 200:
   - run IDs: `..`, `%2e%2e`, `a/b`, an absolute path, a `.partial` suffix,
     a 129-character ID, a non-ASCII ID, and an empty segment;
   - a symlinked run directory, a symlinked manifest and a symlinked stage file;
   - an evidence file reached through a symlinked directory;
   - an evidence root that is a symlink out of `artifacts/`;
   - a media name not in the table, and a media name with `/`;
   - an artifact ID belonging to another run.
2. **`NoHostPath`.** The bodies of every 2xx and 4xx response across all six
   routes contain none of: the temp root, `/Users/`, `/private/`, `/tmp/`, the
   repository root, `run_dir`, `source.path` or `authoring_dir` values.
3. **`HashBinding`.** 9 mutation cases:
   - a stage byte flip gives `stale`;
   - a deleted stage gives `missing`;
   - a manifest edit invalidates the bundle (`bound_manifest_changed`);
   - a bundle media flip gives `409 media_stale`;
   - a bundle JSON edit after first read re-reads and re-binds;
   - a render whose parent is not current gives `analyzed_input_not_current`;
   - a marker file flip gives `file_hash_mismatch`;
   - an artifact changed between hash and send gives a short body and a
     closed connection (the existing `_send_file` guard pattern);
   - a receipt whose pin does not match gives `not_established`.
4. **`Schema`.** Every success response validates against a closed-key checker
   in the test, and the strict JSON parser refuses NaN and duplicate keys.
   Required unknown keys must be present with value and reason: 21 S2 keys plus
   12 S3 keys, 33 in total. The closed key sets of `RunGraph`, `RunLayers` and
   `Capabilities` are compared against the TypeScript schema key lists, which
   are parsed statically from `web/src/lib/server/runs/schema.ts`.
5. **`Selection`.** With three bundles (two current, one invalidated), the
   newest current one is chosen, `alternatives` has length 1, the invalidated
   bundle is listed in `invalidation`, `?evidence=` selects an alternative, and
   `?evidence=` naming the invalidated bundle gives 409.
6. **`Capabilities`.** All 40 of 40 `program/tools.json` tools are present, read
   from the worktree's real registry (read-only). 8 of 8 pilot tools carry
   capability metadata and 32 of 32 carry the null reason. 0 tools are
   unmapped. 1 of 1 `models.json` entries is present, with `local_presence`
   `not_checked` and the URL reduced to its host. Extra `gate_state` and `lane`
   fields in a temp registry copy pass through.
7. **`Policy`.** Static checks over owned web files:
   - 0 `autoplay`;
   - 0 `.play(`;
   - 0 banned words in timing, flag and phrase generated text: rushed,
     dragged, late, early, mistake, wrong, missed, sloppy, tight;
   - all 12 keyboard bindings present with guards for inputs and modifiers;
   - `operator_preference` is rendered as "not recorded";
   - all 4 bases have a distinct label and shape token;
   - every marker-file download is labelled "import unverified";
   - "direction withheld (uncalibrated)" is used on real-take rows;
   - 0 `PrototypeNotice` imports in `/compare`, `/review` and `/download`;
   - no `$lib/server` import in client components.
8. **`Registration`.** Once root applies section 11.1, `web_api` dispatches
   `/api/v1/runs*` and `/api/v1/capabilities` through `web_runs_api`. A request
   without a bearer is still 401, a bad Host is still refused, and POST gives
   405. If the hunk is absent this class is skipped with the reason "root
   registration hunk not applied". Lane tests do not depend on it: the other
   classes drive `web_runs_api` through a test-owned loopback handler that
   calls the same `match` and `serve` entry points.
9. **`WebBuild`.** `pnpm install --frozen-lockfile --offline`, then
   `pnpm run check` and `pnpm run build`, with the same skip policy as
   `test_web_stack` (no pnpm, an empty store, or the exit-75 gate gives a skip
   with the reason). `web/pnpm-lock.yaml` and `web/package.json` must be
   byte-unchanged.
10. **`Walkthrough`.** This runs on the synthetic fixture only:
    - start `web_api` in-process on an ephemeral port (with the hunk, or a
      test-local subclass applying it) and the built BFF as a test-owned child,
      terminated in `tearDown`;
    - admit a synthetic 2 s source in the temp run;
    - run one `share_export` job under a 120 s timeout to obtain the annotation
      clock;
    - fetch `/runs`, `/runs/[id]`, `/compare`, `/review` and `/deliver`, plus
      `/jobs`, `/tools`, and the `/compare`, `/review` and `/download` stubs
      (303 or 200), checking status and a key text marker on each;
    - write one USER REPORTED Mark here annotation through the BFF and read it
      back;
    - download one run artifact and one layer media file by ID, re-hashing
      both.

    The output is the receipt
    `docs/agent-notes/sprints/20261007-s3/routes_review-walkthrough.json`, with
    no host paths. Browser automation (a 390 px and a desktop screenshot, keys,
    players paused) runs only if a local headless browser is already available.
    Otherwise it is recorded as `not_performed`, with no claim.

## 9. Completion metrics

The claim classes are:

- **M**: measured by an automated test on a synthetic fixture;
- **S**: static inspection by a test;
- **B**: automated browser check, muted, with no listening;
- **U**: unknown or not claimed.

| # | Metric | Denominator | Class | Pass |
| --- | --- | --- | --- | --- |
| 1 | Confinement refusals with typed code | 16 adversarial cases | M | 16/16 refused, 0 × 200 |
| 2 | Responses free of host paths | all responses in classes 1–6 and 10 (count recorded) | M | 100 %, 0 leaks |
| 3 | Hash-binding mutations detected with the specified state or code | 9 cases | M | 9/9 |
| 4 | Schema conformance of success responses (Python closed check) | all success responses (count recorded) | M | 100 % |
| 5 | Required unknown keys present with value and reason | 33 keys × {RunGraph, RunLayers} | M | 66/66 |
| 6 | TS/Python schema key-set parity | 5 schemas | S | 5/5 identical |
| 7 | Tools rendered with an area; pilot capability metadata; models | 40 tools; 8 pilot tools; 1 model | M | 40/40, 0 unmapped; 8/8; 1/1 |
| 8 | Routes reachable in the walkthrough (200, or 303 for redirects) | 11 route fetches | M | 11/11 |
| 9 | Mark here write and readback, with basis label USER REPORTED | 1 synthetic write | M | 1/1, revision +1 |
| 10 | User vs detector bases visibly distinct (label and shape) | 4 bases | S | 4/4 |
| 11 | Keyboard parity with S2 keys and guards | 12 bindings | S (+B if a browser is available) | 12/12 |
| 12 | No autoplay or play call sites | owned web files | S | 0 and 0 |
| 13 | Real-take timing rows show direction withheld; abstentions show `—` | all synthetic real_take rows | S + M | 100 %; 0 directions on real_take |
| 14 | Marker downloads labelled import unverified | all marker entries | S | 100 % |
| 15 | Prototype stubs replaced | 3 stubs | S | 3/3 |
| 16 | `pnpm check` and `pnpm build` offline; lock and package unchanged | 1 run each | M | 0 errors, build ok, 0 lock bytes changed (skip only with a recorded reason) |
| 17 | Directly affected modules still pass | `test_web_stack`, `test_web_parity`, `test_artifact_ids` | M | 0 new failures versus baseline |
| 18 | Listening, musical verdicts, default adoption | n/a | U | not claimed |

Experimental or partial outcomes are valid completion when recorded with a
reason. Examples are a skipped browser check, a skipped pnpm store, or a
walkthrough without FFmpeg. They are never upgraded to a pass.

## 10. Experiment and preregistration

This lane runs **no experiment**. It compares no detectors, profiles or
settings and computes no new numeric result. It only displays existing
measurements, with their denominators, as recorded by their producers.
`preregistered: false`, and no held-out data is touched. If a later phase
proposes an experiment, it is appended here as a dated, sealed
preregistration before any truth is read.

## 11. Root-owned changes requested

### 11.1 `scripts/web_api.py` registration hunk (required for real mounting)

This hunk applies to baseline `4bd806d`. `web_runs_api` exposes
`match(path) -> route | None` and `serve(handler, route, query)`. `serve`
enforces the GET-only rule and the query policy, raises `WebJobsError`, and
uses `handler._json`, `handler._headers`, `handler.wfile` and
`handler.server.read_only()` for the read-only `sources`/`jobs` lookup. It
writes nothing.

```diff
--- a/scripts/web_api.py
+++ b/scripts/web_api.py
@@ -16,4 +16,10 @@
     POST /api/v1/jobs/{job_id}/retry              explicit retry of interrupted/failed jobs (attempt n+1)
     GET  /api/v1/artifacts/{artifact_id}          published job output bytes, re-hashed before sending
+    GET  /api/v1/runs                             run listing (scripts/web_runs_api.py, read-only)
+    GET  /api/v1/runs/{run_id}                    run graph: stages, signal versions, evidence, invalidation
+    GET  /api/v1/runs/{run_id}/layers             bound review layers (tone_ab, spans, timing, flags, spectrogram)
+    GET  /api/v1/runs/{run_id}/layers/media/{evidence_id}/{name}   re-hashed layer media
+    GET  /api/v1/runs/{run_id}/artifacts/{artifact_id}             re-hashed run/attachment file
+    GET  /api/v1/capabilities                     tools, capability metadata and model registry
 
 The six unversioned web_jobs routes (``/sources``, ``/jobs``, ``/jobs/{id}``,
@@ -60,4 +66,5 @@
 import tool_api  # noqa: E402  (import only, never edited)
 import web_jobs  # noqa: E402  (import only, never edited)
+import web_runs_api  # noqa: E402  (S3 routes_review read API; import only)
 from web_jobs import WebJobs, WebJobsError  # noqa: E402
 
@@ -564,6 +571,10 @@
             if self.server.shutting_down or self.server.jobs.closed:
                 raise WebJobsError('shutting_down', 503, 'server is shutting down')
             parts = urlsplit(self.path)
+            runs_route = web_runs_api.match(parts.path)
+            if runs_route is not None:  # read-only S3 runs/capabilities API, after the trust checks
+                web_runs_api.serve(self, runs_route, parts.query)
+                return
             name, identifier, methods, flavour = self._route(parts.path)
             if name is None:
                 raise WebJobsError('route_not_found', 404, 'unknown route')
```

### 11.2 `just/workflow.just` (optional)

```
# S3 routes_review read API and route tests (foreground, synthetic fixtures only)
web-runs-test:
    PYTHONPATH=tests python3 -m unittest test_web_runs_s3 -v
```

### 11.3 `web/src/lib/server/control-client.ts` (optional consolidation; not owned by this lane)

Exporting `requestJson` with an optional `capBytes` and exporting `decodeWith`
would let `runs/client.ts` drop its duplicate bounded fetch. Without that
change the lane keeps its own client. Nothing breaks either way.

### 11.4 Not requested

The lane requests no changes to `program/tools.json`, `program/models.json`,
`program/linear.json`, `scripts/tool_api.py`, `scripts/mcp_server.py`,
`scripts/review_server.py` or `docs/spec/PROJECT.md`. The read API is not a new
tool.

## 12. Risks and limits

- **Whole-file media without Range.** Seeking in large videos may be limited by
  the browser. This is the same accepted S2 risk, and it is recorded rather
  than fixed here.
- **Discovery cost.** The evidence walk is bounded and signature-cached. A
  truncated walk is reported, never hidden.
- **Bundles bound to a superseded manifest.** They show as invalidated by
  design. Re-composing a bundle is a root or processing action, not this
  lane's.
- **The real accepted run.** `20261006T041633Z-990aa1bd6737` and its S2
  practice bundle (`manifest_sha256 61c9b393…0a5f`, which currently matches)
  may be inspected read-only by root for an optional non-test smoke check. No
  test uses them.

## 13. Phase 2 implementation notes (appended 2026-10-07)

This section is additive. Sections 1 to 12 stay as frozen at `828b678`. It
records where the implementation is more specific than the frozen text, and the
one root-owned change that the stub replacement forces.

### 13.1 Additive response keys

All keys below are additive and closed in both `scripts/web_runs_api.py` and
`web/src/lib/server/runs/schema.ts`. The `Schema` test class compares the
top-level key sets of the five schemas (Python and TypeScript, 5/5).

- `RunSummary` is `{run_id, run_status, source_id, source_sha256,
  manifest_sha256, manifest_readable, stage_count, state_basis}`.
- `RunGraph.admitted_sources_lookup` is `available` or `unavailable`. When it is
  unavailable, `admitted_sources` is `[]` and every `has_annotation_clock` is
  unknown, not false.
- `RunGraph.processing` adds `noise_capture {selected_seconds, review}`,
  `dsp_latency_status {name: status}` and `manifest_listening_accepted_field`.
  The last one is the manifest's own `capture_profile_application.listening_accepted`
  copied as recorded, and it is never treated as an acceptance.
- `listening_acceptance` adds `master_adopted: false` and
  `accepted_file_sha256`, which holds the cleaned WAV and export video hashes
  that the pinned receipt names. The deliver page puts the accepted label only on
  files whose SHA-256 is in that list.
- `evidence[].files` lists `{name, role, artifact_id, sha256, size_bytes,
  import_verified}` for current `editor_marker_export` and `marked_compact`
  attachments. Marker payloads carry `import_verified: false`. An attachment file
  ID is `artifact_id_for("evidence/<evidence_id>/<name>", sha256)`. It is opaque
  and has no selector.
- `RunLayers` adds `selected_generated_utc`, `source_extent {audio_start_seconds,
  duration_seconds}` and `discovery_truncated`.
- The `tone_ab`, `coverage`, `flags_triage` and `phrase_timing` layers are
  closed envelopes `{status, reason, document}`. `document` is the bundle layer
  copied and scrubbed (13.3). `phrase_timing.document` is `{files, refused}`,
  where each kept file is `{file, sha256, analyzed_input_sha256, source_binding,
  run_kind, document}`.
- `layers.spectrogram` is `{status, reason, document: null}`. The top-level
  `spectrogram` always carries the full key set, with nulls when unavailable. It
  adds `stage`, `band_centre_hz` (copied from `render.json`),
  `first_frame_centre_seconds`, `axis_offset_seconds`, `pcen_status` and
  `reference_lines`. The reference line is read from `program/instrument.json`
  string 9 and labelled "theoretical C1 (instrument.json)".
- `layers.bpm` is `{value, reason, basis, grid}`. `value` is copied only from an
  explicit `bpm` or `tempo_bpm` field and is never derived. `grid` is the
  `flags_triage` `window_basis` period and phase, labelled as a navigation grid.
  The reason is "no fitted click grid in bound evidence" when nothing is
  recorded, or the grid-only reason when only a period is recorded.

### 13.2 Unknown-field precedence

The 21 S2 keys are copied from the selected bundle. They fall back to the
composer defaults, with `basis: "S2 default (no practice bundle value bound)"`.
There is one override. When the pinned acceptance receipt matches,
`listening_acceptance` becomes `accepted_exact_files_only`, with the receipt's
scope sentence as its reason. This stops the page from showing both "accepted"
and "not established" for the same file. The 12 S3 keys follow section 7. The
override applies only to the files the receipt names.

### 13.3 Copied-document scrub

Copied layer documents drop the keys `path`, `run_dir`, `output_dir`,
`authoring_dir`, `commands`, `command`, `argv`, `inputs`, `output`,
`input_path`, `filter`, `audio_master` and `picture_preview`. Any string that
looks like a host path becomes `[host path withheld]`. Bundle `inputs` and
`commands` are never projected.

### 13.4 Binding details

- A `lowreg_render` binds through `resampler.source_sha256`, which must equal the
  recorded output hash of a `current` stage. A render whose `input.sha256` equals
  a stage hash but that has no resampler record is listed as `unbound` and is not
  drawn. The spectrogram prefers the stages cleaned, then processed, then
  denoised, then source, then baseline.
- A `marked_compact` receipt binds when `audio_branch.cleaned_sha256` equals the
  run's recorded `cleaned.wav` hash. Its `audio_branch.manifest_sha256`, when
  present, must equal the current manifest. If it does not, the receipt is
  `bound_manifest_changed`.
- An `editor_marker_export` binds by `source_sha256`. Every `payload_sha256`
  entry must re-hash. If one does not, the attachment is `file_hash_mismatch`.
- `export/*` videos are `current` when `export/outcome.json` records the same
  hash under the same name, `stale` when it records another hash, and `unbound`
  otherwise.
- Discovery skips dot-prefixed entries, such as producer staging directories.

### 13.5 UI behaviour details

- Keyboard: `←` and `→` step 1 s, and holding Shift makes the step 5 s (S1
  `transportKey` parity). As in S2, `B`, `I`, `N`, `P`, `Shift+N`, `Shift+P` and
  `U` act only while the labelling session is on.
- Without an admitted source, the review page shows a position slider in place
  of the player, and the tracks still render.
- The compact overlay sits in the top corner of the player and has
  `pointer-events: none`. It never covers the native transport controls.

### 13.6 Real-run read-only smoke (root may repeat it)

Root can repeat this read-only check against the main checkout's
`20261006T041633Z-990aa1bd6737`. No test uses that run.

- **Graph.** All 6 stages are `current`. `export/cleaned-video.mov` is `current`
  through `outcome.json`. `export/photoboof_demo_lega.mov` is `unbound`, with the
  same bytes and no outcome entry. Listening acceptance is `accepted` with the
  receipt scope.
- **Evidence.** Three practice bundles and one marked-compact receipt are found.
  `discovery_truncated` is false.
- **Timing.** A cold request took 10.3 s, almost all of it hashing about 600 MB.
  Repeat requests use the signature cache.
- **Selection.** Two real-take bundles share `generated_utc`
  `2026-10-06T20:09:03+00:00`. Under the frozen tie rule (lowest evidence ID) the
  default is a schema-1 refusal-check bundle, so the default layers read
  `phrase_timing: layer_schema_superseded` and `tone_ab: input_not_supplied`.
  The fuller bundle is offered as an alternative (`?evidence=`). The rule was
  not changed. This is recorded for root, and a sub-second composer timestamp
  or an explicit root selection would resolve it.
- **Schemas.** The `RunGraph`, `RunLayers`, `RunList` and `Capabilities`
  outputs from this run decode with the closed TypeScript schemas (4/4).
- **Cold-request limit.** The 10.3 s cold graph request is longer than the
  frozen 5 s BFF request timeout. On the real take, the first page load after
  `web_api` starts can therefore show `control_api_timeout`. The Python side
  finishes hashing and caches by file signature, so a reload succeeds. The frozen
  timeout was not raised. A root-owned cache warm-up or a longer graph timeout
  would be a later decision.

### 13.7 Root-owned change forced by the stub replacement

`tests/test_web_stack.py` `test_s8_prototype_routes_label_only` asserts that
`/compare`, `/review` and `/download` still import `PrototypeNotice` and have no
`+page.server.ts`. Section 6.8 replaces those stubs with run pickers, so s8 fails
until root applies the rescope requested in the lane handoff. That request
replaces the stub assertions with picker assertions: no `PrototypeNotice`, a
`+page.server.ts` with `redirect(303`, no `<form` and no `<input`. Every other
s8 check, including the client-fetch and secret checks, is kept unchanged.
`ComparePanel.svelte` (not owned by this lane) still uses `PrototypeNotice`, so
the notice component itself remains.

### 13.8 Phase 4 repair (2026-10-07): host-path metric and merge coupling

**Metric 2 correction.** The earlier receipt reported `responses_checked: 80,
leaks: 0`. That overstated the denominator. Of the 80 recorded API responses
(41 2xx, 37 4xx, 2 5xx), the request-time assertion and the `NoHostPath` sweep
both skipped 5xx bodies, so 78 of 80 were checked. The two unchecked responses
were `GET /api/v1/capabilities` (500 `registry_unreadable`) and
`GET /api/v1/runs/RUN-S3/layers` (507 `layers_too_large`). The sweep itself saw
only 53 responses, because test classes load alphabetically and `Schema`,
`Selection` and `SelectionSchemaOne` run after `NoHostPath`.

The check now covers every status class:

- `request()` asserts each response body at request time, 5xx included, and
  counts it in `leak_checked`;
- `NoHostPath` keeps a mid-module sweep (`sweep_at_no_host_path`);
- `tearDownModule` runs a final sweep over every recorded response
  (`sweep_final`), records the tally by status class and fails the module on a
  leak.

Measured after the change, on synthetic fixtures: 0 leaks in 80 checked of 80
recorded responses (41 2xx, 37 4xx, 2 5xx; 0 excluded). The mid-module sweep
covers 53 of those (29 2xx, 23 4xx, 1 5xx). Walkthrough BFF responses are
asserted separately at request time and are not part of this count.

**Merge coupling (root action).** This branch must not land on `main` without
the two required root-owned hunks recorded in
`docs/agent-notes/sprints/20261007-s3/routes_review-handoff.json`
(`merge_coupling`):

1. `tests/test_web_stack.py` s8 rescope. Without it,
   `test_s8_prototype_routes_label_only` fails on 3 subtests (compare, review,
   download).
2. `scripts/web_api.py` registration hunk (section 11.1). Without it, every new
   page shows a refusal and the `Registration` test stays skipped.

Both target files on this branch are byte-identical to `main` at `18dd984`, and
both hunks apply cleanly with `patch -p1`. With both applied in a scratch clone,
`Registration` passes (1/1) and `test_web_stack` passes 33 of 33, the rescoped
s8 included. Neither root-owned file was edited by this lane.

Rerun on this branch without the hunks (one invocation, 87 tests):
`test_web_runs_s3` 35 ok and 1 skipped of 36, `test_web_stack` 32 ok of 33 (the
3 expected s8 subtest failures), `test_web_parity` 17 ok and 1 opt-in skip of
18. `cargo test --locked -j 1`: 27 passed, 0 failed, 1 ignored.
