---
name: guitar-phrase-timing
description: Measure per-phrase signed offsets of guitar attack candidates from the nearest modelled in-recording click for a distorted nine-string take; descriptive rush/drag evidence with abstention, never a performance grade or missed-note verdict.
---

# Measure per-phrase timing against the recorded click (experimental)

Hook `phrase_timing`; prompt `guitar-phrase-timing`. The worker is `scripts/phrase_timing.py`; operators run `just phrase-timing ANALYSIS PHRASES OUTPUT_ROOT [RUN_KIND]`. Read [the rhythm lane contract](../../../docs/spec/sprints/RHYTHM_S2.md) before relying on any offset.

**Intent.** A musician woodshedding with a click wants to know, phrase by phrase, whether attacks tend to sit ahead of or behind the click that bled into the recording. This tool reports that tendency as a measurement with its uncertainty, or abstains.

**Inputs.** `analysis` is an existing rhythm `analysis.json` (from `rhythm`) carrying broadband attack candidates, the click grid or fitted click drift model, detector-delay medians and the analyzed-input SHA-256. `phrases` is either an arrangement-marker JSON (reference-conditioned alignment candidates) or a `phrases.json` with `proposed_review_spans`; its bound SHA-256 must equal the analysis input or the worker refuses. Both must be bounded regular `.json` files without traversal, URL or symlink components; they are read only. `output_root` is a directory beneath repository `artifacts/`, never `artifacts/runs`; each call writes a fresh `<UTC>-<hex12>/phrase-timing.json` child, so reruns never overwrite. `run_kind` is `real_take` (default) or `synthetic_fixture`. `timeout_seconds` is 1–300, default 120.

**Knobs.** None beyond paths and `run_kind`. The rules are fixed: offset = onset − nearest predicted click (negative is ahead, positive behind); the click-proximal window is min(60 ms, period/4); the nearest onset counts and the rest are counted as additional onsets; off-click onsets are subdivisions or other attacks, not errors; at least 4 click-proximal onsets are required per phrase; the tendency threshold is 5 ms.

**Evidence.** Per phrase: status `measured` or an abstain reason (`fewer_than_4_click_proximal_onsets`, `no_click_grid`, `span_outside_analysis`), median and spread of offsets, and the click-reference basis (`linear_period_drift_model`, else `constant_click_grid`). The receipt always carries `click_identity: unverified`, `physical_capture_latency: uncalibrated`, `listening_ab: not_performed`, `performance_grading: not_performed`, `expected_rhythm_reference: null`, plus input and producer hashes.

**Limits.** Click identity is an unverified periodic high-frequency transient model; a guitar attack can mask or displace a click. Detector-delay compensation uses synthetic-probe medians. Heavy distortion, ~32 Hz low strings, palm mutes, rests, tuplets, tapping, sweeps and legato all move or merge attack candidates. Phrase spans are review candidates or reference-conditioned alignments, not detected musical boundaries. Any ahead/behind tendency label on a real take is descriptive and uncalibrated (physical capture latency unknown); treat it as a place to listen, not a rush/drag finding. No intended-rhythm reference is used, so this never identifies missed or extra notes.

**Research and iteration.** Confirm `rhythm` produced a click grid or fitted drift for the current signal version; rerun `rhythm` and the phrase source after the input changes, then measure into a fresh output and compare per-phrase medians and abstentions across runs. Keep both receipts. Record operator spot-checks separately; until then `real_take_status` stays `unvalidated_until_operator_spot_check`.
