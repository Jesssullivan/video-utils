# Marker export from explicitly selected graph evidence

## Definition of done

1. Generic JSON/CSV marker export accepts hash-bound graph artifacts in nested
   run-local directories, including immutable selected evidence receipts.
2. Artifact names are relative paths with no empty, dot, parent, absolute,
   backslash, URI or drive syntax. Every path component is checked for symbolic
   links; resolved files must remain inside the run directory.
3. Every graph upstream artifact and selected external context digest is verified
   before export, then checked again before publication preparation finishes.
   Stale, missing, escaped or changed evidence fails without publishing markers.
4. Export existing verified graph flags once. Preserve hypothesis wording,
   confidence, original source timestamps and optional spans. Do not independently
   append raw selector candidates or turn a review flag into a confirmed mistake.
5. Meaningful tests cover a successful nested receipt, changed nested evidence,
   path traversal, absolute paths and symbolic-link escapes, including parent
   symlinks. Existing timestamp and CSV round-trip behavior continues to pass.

## Ownership and authority

The root assigned this lane `scripts/markers.py`, `tests/test_markers.py` and
this specification. The graph owner defines explicit evidence selection and
hash receipts; marker export consumes that graph rather than selecting evidence
again. Authority: operator-approved parallel implementation, repository
`AGENTS.md`, R-HOOK-CONVERGENCE-20261004 / R-N13.

JSON and CSV remain a generic interchange pilot. Native Final Cut Pro and
DaVinci Resolve import, frame-rate conforming and application acceptance remain
unverified. Markers do not establish musical mistakes or listening acceptance.

## Implementation checkpoint

Definition of done recorded before implementation. The graph owner's coordinated
schema contains five explicit `selected_evidence` slots: `clicks`, `pitch`,
`meter`, `tonal` and `comparisons`. Verified rows carry a relative `selector`,
`artifact_sha256`, run-relative `upstream_hashes` and optional fixed repository
`external_context_hashes`. Graph `artifact_hashes` binds selected nested JSON
receipts and their validated run-local inputs. The only external context is
`program/instrument.json`; it is checked against the repository, never interpreted
as a run-relative file or an arbitrary external selector.

`flags.evidence_artifacts` projects verified rows as
`slot: {selector, sha256}`. Selected comparison flags carry
`selected_evidence_slot`, `selected_artifact` and
`selected_artifact_sha256`. The exporter rejects a flag whose selection is
missing, rejected or mismatched. Selected flags must retain `needs_review` and
must not assert `performance_issue_confirmed: true`.

The exporter accepts safe nested relative paths and verifies all graph digests
before preparing output and again afterward. Every existing component is checked
for symbolic links, including run metadata and the fixed instrument registry.
Nested-context hashes must agree with the graph's verified hashes. Replaced
parent links and changed bytes during export preparation are rejected.

Only existing graph flags enter the output. Exact duplicate exported markers
are suppressed; distinct evidence remains distinct. Marker JSON carries verified
`evidence_artifacts` and per-marker selection bindings. CSV retains its existing
six columns; evidence remains quoted JSON. The exporter does not append raw
comparison, pitch, tonal, click or meter arrays, select a newer receipt, re-run
analysis, change audio or claim a confirmed musical error.

Validation on October 5, 2026: **15 marker tests passed**, including successful
nested selection/CSV export, duplicate suppression, changed nested receipts,
absolute and parent traversal, leaf/parent symlinks, a parent link replaced after
validation, rejected/mismatched selection bindings, an attempted confirmed-error
promotion, stale/fixed external registry, source metadata symlinks and an
unbound selected flag. Existing source offsets and CSV quoting tests pass.

Read-only export preparation against the actual corrected demo
`artifacts/runs/20261005T211103Z-c6d0bac2fcd2` succeeded for **186 markers**.
That historical graph has no explicit selected-evidence rows; this check proves
legacy compatibility and current upstream integrity, not the still-pending root
integration of selected graph receipts. No artifact was overwritten by the check.
