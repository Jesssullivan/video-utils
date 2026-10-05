# Explicit feature evidence in the guitar graph

Authority: operator-approved parallel goal and `GRAPH_INTEGRATION_LANE.md`;
R-HOOK-CONVERGENCE-20261004, R-N11/R-N12/R-N13. This lane owns only `scripts/dag.py`,
`tests/test_dag.py` and this specification. Root owns integration and publication.

## Selector contract

Optional CLI flags are `--clicks-artifact`, `--pitch-artifact`, `--meter-artifact`,
`--tonal-artifact` and `--comparisons-artifact`. Each accepts exactly one explicit
run-relative JSON path, length 1–1024. The matching optional MCP fields replace
hyphens with underscores. Python uses `build(..., evidence_selectors={slot:path})`
with slots `clicks`, `pitch`, `meter`, `tonal`, `comparisons`.

Do not guess the newest experiment from directory timestamps. Reject absolute
paths, colons, backslashes, empty/dot/parent components, hidden or `.partial`
components, symlink components, nonregular files and paths outside the run.
Artifacts are ≤20 MB each and ≤40 MB total selected input. Invalid path requests
fail the command. Valid paths with incompatible, stale or malformed evidence are
recorded as `rejected_<reason>` without promoting their payload.

`dag.json.selected_evidence` always contains the five slots. Each records `status`
(`not_selected`, `verified`, `rejected_<reason>`), `selector`, `artifact_sha256`,
`payload_status`, `analysis_input_sha256`, `timing_status`, `metadata`,
`upstream_hashes` and `external_context_hashes`. Nulls remain null. The full payload
stays in its explicitly selected artifact; the graph embeds bounded metadata.
Report consumers may open only `verified` rows after current receipt and graph
input hashes pass; rejected/not-selected rows expose their status only.

Metadata keys are `status`, `confidence_kind`, `identity_status`, `time_signature`,
`tonic`, `mode`, `summary`, `coverage`, `interpretation`, `pitch_context`,
`feature_context`, `comparison_count`, `flag_count`, `requires_expected_intent`,
`performance_grade`. Coverage retains sparse spans/fraction and sampling/frame
precision. Unknown meter, tonic, mode, notes, source identity or confidence must
not become known merely through graph inclusion.
Rows also distinguish producer settings/manifest receipts from hashes derived
retrospectively from the selected payload/current canonical PCM. The published
pitch worker's `lineage: verified_canonical_derivative` may be matched against
current manifest rate/channels/sample count, media hash, recording identity and
timeline even when its older producer manifest/settings hash was not recorded.
That row explicitly says `derived_current_canonical_pcm_not_producer_manifest_hash`
and `derived_from_selected_payload_not_producer_receipt`; it never invents a
producer receipt. Missing worker identity remains `not_recorded`.

## Verification and temporal honesty

Each selected artifact binds the original recording identity, actual analyzed
original/restored media identity, settings hash and declared run-local upstream
hashes. Meter's provenance hash fields normalize to the same upstream map.
Pitch/click derivative lineage must match the manifest. Inconsistent current
inputs, settings or source identities reject the evidence. Verified selected artifacts and
validated upstream hashes join active `artifact_hashes` using safe run-relative
paths. Rejected rows retain their artifact hash as an audit receipt, never as a
trusted active graph input.
Fixed instrument metadata uses separate `external_context_hashes` under
`program/instrument.json`; it is never treated as an arbitrary filesystem path.

Base and selected stages retain bulk DSP timing status. Old denoise manifests
without a measured compensation receipt are `dsp_delay_uncalibrated`, even when
sample count, PTS and `no_time_stretch` match. A measured-and-compensated receipt
with zero remaining bulk samples supports the derivative sample mapping; detector
delay, acoustic travel and physical A/V synchronization remain unverified.
Original-recording diagnostics retain raw-axis/detector uncertainty.

Click identity remains unverified; attenuation is an experimental variant.
Pitch preserves sparse coverage, pYIN/octave/voicing ambiguity and theoretical
tuning evidence. Meter and tonal outputs remain hypothesis sets with nullable
notation/tonic/mode. Recurrence comparison flags need no intended-score reference,
but remain `needs_review` and never confirm musician mistakes.

## History, tests and actual acceptance

Before a CLI rerun replaces graph/flags, archive existing DAG, flags, report and
generic marker artifacts in a content-addressed run-local graph history snapshot.
Record file hashes and snapshot status; a saved snapshot is not revalidated
listening acceptance. Existing history is immutable, including rejected results.

Tests cover absent selectors, explicit safe nested paths, symlinks/traversal,
stale upstream/settings/manifest/media, source mismatch, missing provenance,
unknown/null meter/tonal data, sparse pitch coverage, legacy DSP uncertainty,
calibrated bulk mapping and preserved graph/report history. Root reruns this on
the actual calibrated demo using recorded paths, then reviews source/runtime
evidence separately from listening and editor-import acceptance.

## October 5 checkpoint receipt

Definition of done: selector syntax/source/upstream/settings checks, preserved
nullable/sparse evidence, review-only comparison flags, bulk-delay honesty,
immutable prior presentation snapshots, and an actual calibrated read-only
integration check.

All 39 DAG tests passed. The explicitly recorded selectors in
`artifacts/graph-selected-inputs.json` verify all five slots on calibrated run
`20261005T211103Z-c6d0bac2fcd2`. Its merged candidate set contains 197 flags,
including 11 selected DTW review flags. Sparse pitch coverage remains approximately
0.13248, and missing pitch producer worker/settings/manifest receipts remain
explicitly missing or retrospectively derived. This lane did not replace the
actual graph/report; root owns that archived rerun and publication. Source passes,
graph verification, physical sync and listening acceptance remain separate.
