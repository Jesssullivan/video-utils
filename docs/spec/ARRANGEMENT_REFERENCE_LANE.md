# Source-bound arrangement reference and review

The operator supplied this take's intended arrangement and confirmed sixteen metronome clicks per chorus phrase. The verbatim import is [the operator prompt](../agent-notes/2026-10-06-operator-arrangement-prompt.md); `program/demo-arrangement.json` is its machine-readable reference. Reference-aware analysis supplements the existing unsupervised baseline. Intent never overwrites an observed section count, metronome fit or phrase boundary.

`rhythm_analysis` owns `scripts/arrangement_reference.py` and worker tests; `goal_plan` owns the demo fixture. `phrase_dag` owns this integration specification and `tests/test_arrangement_reference_audit.py`. Root integrates recipes, hooks and publication. This checkpoint uses existing bounded JSON evidence, with no new waveform decoding, model job or canonical phrase detector change.

## Expected structure

Schema one binds the original source SHA-256 and operator-supplied provenance. Ordered sections declare ID, label, kind, phrase count and clicks per phrase. Twenty-four sixteen-click phrases, two eight-click breakdowns and a four-click rest total **404 intended clicks**. The second chorus's four phrases inherit “chorus again”; preserve that assumption. Rest and breakdown kinds are distinct from ordinary repeated phrases.

The first musical phrase starts between source seconds 10 and 11, approximately. Metronome start around five seconds and a preceding windup are separate approximate statements. Setup contains fan plus minor guitar/amp sounds, not verified pure noise. Tempo 178 BPM is supplied and approximate. None is a newly measured or calibrated timestamp.

Compute cumulative half-open click intervals and propagate the complete first-phrase anchor range to expected boundary ranges. Do not select an exact midpoint or imply calibrated millisecond accuracy. An expected end beyond the recording is incomplete coverage, not a completed observed section.

## Observation and clock contract

`validate_reference(reference, source_hash=None)` expands units, boundaries and totals. `align_arrangement(reference, observations)` assesses independent normalized observations. Observations have schema one, original `source_sha256`, optional `analyzed_input_sha256`, `timeline` with source start, duration and boundary latency status (default uncalibrated), and boundary rows with ID, source seconds, uncertainty seconds, confidence (`unvalidated`, `operator_reviewed` or `ambiguous`) and evidence text. Bounds are 2,048 observations, 128 expected units and 300 seconds. The CLI selects an exact reference plus either a run directory or explicit observations, and writes a fresh output directory.

Existing events distinguish source and audio-relative timestamps; existing phrase segments and recurrence pairs have both source and audio-relative spans. Novelty samples and four-pulse proxies are evidence, not confirmed section identity or meter. One inspected cached canonical take fits about 88.8009 BPM while the operator supplied approximately 178 BPM. Half/double interpretations must remain explicit. Do not silently double a fitted tempo or label extrapolated grid positions as detected mechanical clicks.

Bind exact input JSON bytes, original and analyzed source hashes, settings and worker hashes. Map a verified source origin once; reject inconsistent source hashes or invalid coordinates. Preserve uncertain DSP latency rather than deriving calibration from PCM extent alone. Explicit paths and receipts replace newest-file scanning.

The run adapter rehashes the canonical analyzed PCM file without decoding it and binds the manifest, analysis and phrase JSON bytes. Original encoded media is not rehashed by this checker; its identity remains the manifest assertion. A resampling endpoint extending beyond native coverage by at most one 16 kHz analysis sample is clipped to the canonical end, with the original coordinate and adjustment retained. Larger overruns fail. This extent rule does not calibrate detector latency.

## Alignment and review limits

Use monotonic one-to-one matching with bounded search and explicit skips. Alternative equally supported assignments must yield ambiguity or nulls. A unique matched boundary can report the signed range `[observed - expected_high, observed - expected_low]`; never compute a midpoint residual silently. An observed unit duration divided by the declared nominal period is `reference_equivalent_clicks`, not detected metronome clicks; actual observed click count remains null without a qualified click detector.

Observed boundary uncertainty widens each signed difference. Unit durations retain nominal center differences alongside `duration_seconds_range`, equivalent-click ranges and deviation ranges; uncertainty is not discarded. These ranges remain conditional on the supplied approximate tempo, whose error is not estimated by the checker.

Repeated musical phrases can lack novelty at their joins. Riff similarity does not prove that a join occurred on time. Missing boundary support remains unknown or needs review, and never becomes a confirmed skip or rush. The operator suspects a rushed/skipped breakdown; that is a question, not a detector calibration label. Palm muting, pinch harmonics, tapping and sweeps remain intended labels until independently supported.

Keep extra and omitted observations, duplicate riff identities, intentional rests and partial tails visible. Right-censor expected endpoints beyond available source coverage. Never reuse one observation for several expected joins or grade notes from phrase counts. Output remains uncertain review evidence with no intended-note score.

## Independent proof and integration

Tests cover arithmetic, half-open order, exact source binding, approximate anchors, observation separation, monotonic one-to-one matching, repeated-riff ambiguity, empty evidence, partial tails, rests and hostile bounded metadata. Deterministic property cases check common source-origin shifts and missing/extra observations without inference. Generated reference labels test only the checker and never enter detection.

The first integration is a standalone immutable comparison receipt with source-time review spans. Preserve all unsupervised artifacts and rendered markers. Root can later select the exact receipt into the graph and show distinct expected/observed tracks; native editor import and musician acceptance remain separate. Source tests and the supplied arrangement do not establish that the real take was played correctly.

The fixed CLI is `python3 scripts/arrangement_reference.py REFERENCE --run-dir RUN --output NEW_DIRECTORY`, or `--observations OBSERVATIONS_JSON` instead of the run selector. The output contains `assessment.json`, `review-candidates.json` and `receipt.json`. Assessment rows separate `expected`, `observed` and `deviation`; unobserved or ambiguous rows keep the latter two null. Boundary and unit review candidates explicitly identify whether navigation coordinates come from an observation, an observed pair or an intended interval. All use `needs_review` and `performance_issue_confirmed:false`.

The receipt binds every input and output SHA-256, producer SHA-256 and fixed settings SHA-256. Run-local manifest/analysis/phrase/PCM bindings and the separate source-bound reference selector support later marker freshness checks. Consumers must preserve intended-versus-observed time basis and uncalibrated latency. Do not present intended-only spans as discovered phrases or automatic correctness findings.
