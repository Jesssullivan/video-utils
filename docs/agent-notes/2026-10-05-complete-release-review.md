# Complete release review — October 5, 2026

Independent release audit by `/root/audio_research` under
R-HOOK-CONVERGENCE-20261004, TIN-3692 comment
`98cf680c-7299-4949-bfb2-60079053ad43`; R-N11/R-N12/R-N13 apply.
Read-only inspection covered source changes, authoritative root job logs and
completed artifact receipts. No root jobs were restarted, no media was decoded
again, no listening review or annotation was performed, and this receipt is the
only file written by the audit lane.

**Verdict: no blocking regression found in the reviewed release evidence.**
This is a local implementation and artifact review, not listening acceptance,
hosted CI acceptance, AU validation or Logic/editor host proof.

- `artifacts/twenty-tool-complete-release-tests.log` ends with **291 tests in
  53.583 seconds, OK**. The current registry contains twenty named tools.
  Relevant coverage includes corpus full/summary parity, unchanged metadata
  bytes, stale revisions and unsafe paths, real corpus MCP summary dispatch,
  demo workflows and measured WAV origin handling. These are the existing
  root-run results; the audit did not rerun the suite.
- `artifacts/complete-actual-existing-result.json` and its run-local invocation
  receipt report `completed_unreviewed`, zero failed stages, and successful
  report/marker generation. All five explicit selectors—clicks, pitch, meter,
  tonal and comparisons—have `verified` DAG verdicts. Independent byte hashes
  of all five selected artifacts match the returned receipts. The DAG registry
  and instrument-context hashes match their current source files.
- The actual run is `artifacts/runs/20261005T211103Z-c6d0bac2fcd2`; its latest
  reviewed invocation is `20261005T221943Z-9f2a37bcca5c`. Independent streaming
  SHA-256 checks match the original source and every recorded WAV output:
  source, denoised, baseline, cleaned and residue. Current manifest bytes and
  all native media identities also match the retained prior manifest. Existing
  media/export stages explicitly record `media_rerendered:false`.
- Every byte hash in the invocation's sixteen-artifact prior snapshot matches
  its archived file, including `analysis.json` and `events.csv`. The history
  retains the explicit `prior_artifact_snapshot_not_revalidated` status; stored
  prior analysis is not promoted to a current measurement.
- The actual DAG and marker outputs contain **197 automatic review
  candidates**, with `performance_grade:not_graded_human_review_required`, no
  supplied expected reference and `listening_accepted:false`. Timing remains
  `bulk_dsp_delay_compensated_detector_and_physical_sync_unverified`. Verified
  provenance is not confirmation of meter, pitch, musical mistakes or physical
  audio/video synchronization.
- The retained export measurement is **−18.07 LUFS integrated / −1.56 dBTP**
  (`final_audio_loudness.input_i/input_tp`), with its −1.5 dBTP check passing.
  The receipt distinguishes **3,631 encoded video packets** from **3,621
  decoded frames**, preserved in both source and export. Ordered packet PTS,
  DTS, durations and encoded-payload hashes agree; the −20 ms container-header
  duration difference remains diagnostic. This audit verified the export byte
  receipt and read those completed measurements; it did not redo video decoding.

The completed WAV fixture in `artifacts/complete-demo-wav-fixture.json` preserves
missing source stream-start metadata as `null`. Its manifest separately records
an actual first-decoded-frame timestamp of `0.0` and the bounded FFprobe command
that measured it. All five graph selections verify against that decoded origin.
The MOV fixture also completes with five verified selections. The WAV repair
does not invent a container/BWF time reference or establish acoustic latency.

The corpus hook is metadata validation only. Source inspection confirms that
`validate()` runs before compact projection; summary mode retains source-origin,
certainty and review-state counts while omitting reviewer identities and label
text. Reads use bounded regular-file checks and read-only descriptors. Returned
boundaries remain `source_audio_read:false`, `ground_truth_established:false`,
`listening_acceptance:not_established`, unknown unlabelled spans and supplied,
unauthenticated origin/reviewer/authorship assertions. The root test evidence
uses synthetic authored metadata; it does not establish actual-take labels or
human musical ground truth.

Remaining acceptance is explicit: actual-recording listening and musical review,
independent detector/physical-sync calibration where required, and future AU,
Logic, Final Cut Pro or Resolve host validation. None was inferred from this
release audit.
