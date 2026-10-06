# S1 source-bound annotation v2 contract

Status: implemented narrow slice, pending final independent/root admission. Authority:
operator's five-hour six-lane sprint, repository AGENTS.md, and
R-HOOK-CONVERGENCE-20261004 / R-N11/R-N12/R-N13. Owner: annotations lane;
root administers signed integration, MCP/skill admission and publication.

The v1 `review-annotations.json`, `/api/annotations`, and CLI are unchanged.
There is no implicit migration or write to an accepted demo run. The separate
v2 file is `review-annotations-v2.json` inside the selected run directory.

## Callable and transport

- `scripts/annotation_v2.py read RUN_DIR`
- `scripts/annotation_v2.py write RUN_DIR --input REQUEST_JSON`
- `AnnotationStore(review_server.Session).read()` and `.write(request)`
- `Session.read_annotations_v2()` and `.annotate_v2(request)` map stable errors
  to existing `ReviewError(code, status)`.
- Existing loopback server: `GET /api/annotations-v2` and
  `POST /api/annotations-v2`. Write requires the same explicit matching Origin
  and `X-Review-Token` supplied by `/api/session`; no CORS/external server.
- `request_schema()` returns the closed structural JSON schema. Contextual
  identity, span, authorship and claim invariants are worker-enforced.
- Pure validators: `validate_annotation(item, *, source_min_seconds,
  source_max_seconds, stored=False)`; `validate_store(value, *, source_sha256,
  manifest_sha256, source_min_seconds, source_max_seconds, public=False)`.
  `public=True` validates GET projections, which omit internal replay receipts.
  POST adds `mutation`, and CLI adds `count/status`; strip those transport fields
  before using the public-store validator. No filesystem reads in validators.

## Closed request

All top-level fields below and the eight annotation content fields are required.
Only optional annotation fields are `id` (existing canonical UUID for edit),
`candidate_id` (nullable hash-bound current marker ID), and `reference_sha256`
(nullable lowercase 64-hex hash, required for reference comparison).

```json
{
  "schema_version": 2,
  "expected_revision": 0,
  "idempotency_key": "example-request-0001",
  "source_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "manifest_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "annotation": {
    "kind": "rhythm_timing",
    "basis": "operator_assertion",
    "status": "needs_review",
    "source_span": {
      "start_seconds": 47.25,
      "end_seconds": 47.25,
      "extent_known": false
    },
    "reported_by": {"actor": "operator", "via": "browser"},
    "operator_certainty": "uncertain",
    "operator_quote": "Known rhythmic issue around 47.25 seconds.",
    "note": "Exact expected rhythmic pattern has not been supplied."
  }
}
```

Example identities and timestamp are illustrative, not a saved real annotation.
Actual source/manifest hashes and bounds come from the selected run session.

Kinds: `rhythm_timing`, `rhythm_pattern`, `phrase_omission`, `phrase_duration`,
`melodic_pitch`, `articulation`, `rest_execution`, `meter_mismatch`, `tone`,
`noise`, `other`. Context-value objects, staff, rendered annotation overlays,
nullable calibrated confidence and decoded frame mappings remain future work.
`note` and `operator_quote` are bounded literal text, not markup commands.
Consumers must render escaped text; storage deliberately preserves wording.

| Basis | Required authorship | Quote/certainty | Saved label |
| --- | --- | --- | --- |
| `operator_assertion` | actor `operator`; via `browser`, `agent`, or `cli` | literal nonempty quote; `uncertain` or `confirmed` | `USER REPORTED` |
| `operator_context` | actor `operator` | both null | `INTENT` |
| `detector_hypothesis` | actor `detector` | both null | `REVIEW` |
| `reference_comparison` | actor `operator`, `agent`, or `detector`; reference hash required | both null | `REFERENCE REVIEW` |

All bases use existing states `needs_review`, `accepted_observation`,
`dismissed_candidate`. Every saved item has `musical_verdict: not_established`.
`operator_certainty: confirmed` records the user's certainty and does not change
that verdict. Client labels/verdicts/confidence/master acceptance are refused.
Actor fields preserve reported provenance; local authentication does not establish
an independently verified musician identity or validate musical correctness.

## Source clock and binding

Coordinates are original-source seconds, never processed zero-origin seconds or
frame indices. Every v2 store/read/write requires explicit finite `audio_start_seconds`
and `format_start_seconds` in the pinned manifest, plus a positive finite declared
duration or duration derived from positive integer native sample count/rate.
Missing/null/bool/nonfinite clocks are unknown and refuse409
`annotation_source_clock_unknown`; v1 zero-origin defaults remain unchanged.
Finite ordered points/spans must lie within the session's verified
source min/max. Negative source origins and zero-duration points are legal.
`extent_known: false` requires equal start/end; it never invents a duration.
The upper bound may include audio beyond available picture. Annotation storage
makes no claim about a video frame existing at that time.

The request and store bind both source SHA and manifest SHA. Manifest mutation
invalidates the pinned session and requires a restart. A new manifest cannot
silently adopt the old v2 store; cross-run/reanalysis import is future explicit
work. Candidate links are accepted only from the current session's hash-bound
marker set. Changed auxiliary artifacts refuse subsequent writes; old human
wording is not rewritten. Reference hash is provenance metadata rather than
reference audio or calibration validation.

## Transactions and replay

Public GET returns schema version, source/manifest SHA, revision, annotations and
`listening_acceptance: not_established`. Each record includes stable UUID, content,
UTC creation/update timestamps, original/updated manifest/candidate receipts,
claim label and the fixed musical verdict. POST additionally returns:

```json
{"mutation":{"outcome":"saved","annotation_id":"<uuid>","committed_revision":1}}
```

An identical complete request with the same key returns `outcome: replayed`, the
original committed ID/revision, and the **current** store. Replay does not replace
subsequent edits or increment revision. Content or expected-revision changes under
that key return409 `idempotency_key_conflict`. Replay is checked before expected
revision, after current identity/provenance and request validation. A new stale key
returns409 `stale_annotation_revision`; refresh/reconcile and send a fresh key for
a revised operation. IDs are server-generated; edits require an existing ID.

One per-session mutex and nonblocking process file lock protect each transaction.
Writes serialize to a fresh0600 temporary, fsync, and atomically replace only the
v2 store. Existing v1 and media bytes remain unchanged. Lock conflict returns409
`annotation_store_busy_retry`; there is no blind retry loop. Refusals and failures
before publication preserve prior store bytes. This narrow implementation does
not claim crash durability of the parent directory or resistance to a malicious
noncooperating process replacing the run directory mid-transaction.

Bounds:200 records,512 committed replay receipts,1,000,000 UTF8 store bytes,
20,000 UTF8 request bytes,4,000 Unicode characters per text field,8–128 ASCII
idempotency key characters (`[A-Za-z0-9][A-Za-z0-9._:-]{7,127}`). Limits refuse
without eviction. A replay receipt is retained for every committed revision;
filling the limit requires explicit future archival rather than unsafe key reuse.
Reader rejects duplicate keys/nonfinite JSON, leaf symlinks and nonregular files;
nonblocking opens bound FIFO rejection. Pinned metadata hashing is bounded20MB,
streamed64KiB, and checks file identity/size/mtime across hashing.

The new standalone v2 CLI constructs `Session(..., bounded_metadata=True)`.
Its `MetadataAccess` captures immutable parsed JSON plus hashes of the exact
bounded bytes:20MB per metadata file,40MB aggregate JSON and256 selected files.
All session hashes share a separate512MiB streamed-byte budget. This includes
DAG-selected artifacts and optional derivative-audio lineage verification, so
legitimate raw audio larger than20MB can be hashed; no audio processing occurs.
The two narrow report helpers accept explicit injected loader/hash callables and
preserve their default legacy behavior. Snapshot hashes are rechecked before a
v2 write; changed selected raw media or metadata refuses without altering store.
JSON/file size changes during bounded reads are rejected. The existing v1 and
normal loopback-server startup retain their prior session construction; this
slice does not claim to repair every inherited metadata path. The new v2 HTTP
store/request/provenance operations remain bounded after server startup.

Stable refusals include source/manifest mismatch409, stale revision409, changed
idempotency content409, unknown edit404, source span bounds400, invalid schema400,
changed pinned metadata409, and capacity413. HTTP structural JSON failures return
400; CLI errors return nonzero with a compact `{error: code}` on stderr. Legacy
v1 HTTP/CLI success and refusal codes are preserved.

## Verification

Owner tests cover isolated synthetic HTTP/CLI read/save/replay, v1 coexistence,
user-versus-detector claims, unknown-origin/duration refusal across v2 paths,
revision conflicts across two sessions, literal text,
negative origins and audio tails, source/manifest/candidate changes, capacity,
symlink/FIFO/oversize/duplicate JSON refusal and atomic prepublication failure.
A deterministic100-case origin-translation/serialization property loop verifies
clock relationships without forcing musical detections or creating ground truth.
Independent audit reproduced an initially blocking FIFO reader; nonblocking opens
and bounded provenance hashing fix that defect. Added pre-session tests reject
oversize/FIFO metadata before the legacy loader, qualify larger raw-file hashes
under the separate budget, compare candidate semantics with legacy construction,
and refuse changed selected artifacts. The23 existing report tests pass with the
explicit loader/hash dependency seams; no global monkeypatch is used. Exact source hashes and subsequent
independent closure belong in the dated lane receipts, not this evolving contract.
No annotation renderer, automatic musical grading, native editor/AU acceptance or
real accepted-run annotation write is implied by these checks.
