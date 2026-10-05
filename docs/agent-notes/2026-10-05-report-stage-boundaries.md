# Report stage and selected-evidence scope receipt

Authority: root-assigned parallel implementation for the operator's guitar
toolkit; repository `AGENTS.md`; R-HOOK-CONVERGENCE-20261004 / R-N13. Owned
source: `scripts/report.py` and `tests/test_report.py`. Root owns integrated
actual-run rendering, publication and tracker facts.

## Implemented and frozen

The clean audition caption now describes the manifest's recorded restoration
stages in order. It shows the profile, configured afftdn reduction/noise floor,
recorded capture interval and capture review, subsequent peaking EQ/compressor
controls where present, measured loudness normalization and pending listening.
Dynamic metadata is bounded and HTML-escaped. Old manifests without a stage
list explicitly say the chain was not recorded rather than inventing controls.

The residue caption identifies **source.wav minus denoised.wav**, a pure
pre-gain denoise diagnostic excluding subsequent EQ, compression and loudness
normalization. It is neither an isolated source nor the complete final-master
difference. Analysis matching the denoised hash is labeled as pure denoise;
when final delivery includes EQ/compression the report states that those findings
do not describe `processed.wav` or the complete mastering chain. Analysis
lineage acceptance was not expanded to `processed.wav`.

Selected-feature receipts preserve and display `manifest_binding_kind`,
`settings_binding_kind`, `producer_worker_status` and `producer_worker_sha256`.
Legacy derived canonical-PCM/selected-payload bindings remain distinct from
recorded producer receipts. Missing producer identity stays `not_recorded`;
reported producer hashes do not become current-worker runtime verification.
The report result includes these receipts under `selected_evidence_receipts`.

## Validation

**23 report tests passed in 0.223 seconds.** The added cases exercise captured
EQ/compressor stage captions and hostile-string escaping, legacy missing-stage
compatibility, unchanged rejection of processed audio as analysis input, and
preservation/display of derived-versus-producer scope fields without runtime
promotion. `git diff --check` passed for the owned source/tests.

Read-only manifest inspection confirmed the generated captions for:

- `artifacts/runs/20261005T232627Z-eb7bead2ae74`: captured8, source interval
  4.10–4.95 seconds, configured NR 8 dB / NF −40 dBFS, noise-only unverified,
  followed by loudness normalization.
- `artifacts/runs/20261005T232741Z-2b5dc43fd009`: captured8-clarity, the same
  uncertain capture, peaking EQ at 300 Hz/−1.5 dB and 2200 Hz/+1 dB, RMS
  compression at −18 dB/2:1 with 15 ms attack/100 ms release/25% wet, then
  loudness normalization. Analysis scope remains pure `denoised.wav`.

Frozen report source SHA-256:
`e7444bf6d60652e1d9f6fe2d5ffe916fb74c0363a2c736f824ed0f2e821e07c9`.
Root was notified of the freeze before the fresh extended run's report stage.
This lane did not overwrite actual report/media artifacts. Actual fresh-run
completion, browser inspection and listening acceptance require their separate
root/operator receipts.
