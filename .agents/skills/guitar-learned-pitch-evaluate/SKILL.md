---
name: guitar-learned-pitch-evaluate
description: Evaluate existing hash-bound generated learned-pitch and pYIN pilot artifacts with separate clock, input-support, pitch-set and articulation metrics; retain exclusions and synthetic-only claim boundaries without inference or model acquisition.
---

# Evaluate generated learned-pitch evidence

**Hook:** MCP tool `learned_pitch_evaluate`, prompt `guitar-learned-pitch-evaluate`. Inspect `tools/list` for the current closed schema. This stdlib evaluator consumes existing generated references, pYIN receipts and learned arrays; it does not decode audio, invoke inference, download/install models or runtimes, analyze the actual take, or grade a musician.

## Inputs and fixed controls

Required `fixture_index`, `pyin_pilot_index`, `learned_pilot_index` and `output` are local paths of 1–4,096 characters beneath repository `artifacts/benchmarks/`. Inputs are existing regular nonsymlink JSON indices <=5,000,000 bytes; output must be new. Reject traversal, unsafe components, URLs, stale bindings and reused output. Optional `timeout_seconds` is integer 1–120/default 120. The hook's owned process-group deadline bounds evaluation; the direct worker has no internal deadline. No backend, model, executable, threshold, decoder, tolerance, clock offset, tuning correction or analysis-budget knob is exposed.

Direct CLI: `python3 scripts/learned_pitch_evaluate.py --fixture-index "<bank-index>" --pyin-pilot-index "<pyin-index>" --learned-pilot-index "<learned-index>" --output "<fresh-directory>" --summary`. Typed fallback: `just tool-run learned_pitch_evaluate '<arguments-json>'`. Read [the acceptance contract](../../../docs/spec/PITCH_COMPARATOR_ACCEPTANCE_LANE.md) and [the preregistered cohort](../../../docs/agent-notes/2026-10-06-learned-pitch-bank-preregistration.md).

## Coverage and provenance before scoring

Exactly four completed generated jobs total thirty analyzed seconds, each from sample zero: missing-F0 clean eight, tuning ladder clean eight, legato-transition mixture six, sweep/polyphony mixture eight. Unrequested source tails and other bank cases are not evaluated. A twelve-second model smoke or sparse phone-take receipt cannot substitute for this pilot. Preserve full native source extent separately from requested analysis coverage.

Verify bank, truth, source/component, pYIN and learned indices; comparison/array, instrument registry, adapter, qualified model and runtime-manifest hashes; exact coverage, fixed decoder settings and all window/padding maps. Generated WAV bytes and PCM headers are read for identity/extent; no waveform decoding occurs. Numeric NPZ bytes are read and validated without NumPy, pickle or executable objects. Model/runtime identities are receipt bindings, not fresh weight installation or runtime qualification.

Retain three distinct clocks: primary empirical `model_times_seconds`, nominal hop `nominal_times_seconds`, and `input_window_projection_seconds`. Window index/crop/prepend/stride, raw event endpoints, clipped display/source endpoints and excerpt boundaries must agree with recorded arrays. Empirical correction is not physical capture latency. No fitted offset, interpolation, time warp or truth-selected clock improves scores.

## Denominators, decoders and interpretations

Native monophonic scoring requires the entire approximately two-second model input inside one eligible reference region with no input padding. Pointwise label views and alternate-clock sensitivity keep separate denominators. The preregistered geometry has 2,580 rows, including 426 eligible native monophonic rows supplied only by missing-F0; ladder/legato/sweep native monophonic denominators are zero. These are expected support counts, not model accuracy. Native guitar-absence support is zero: false-alarm rate remains null with N=0, never zero or successful silence detection. Pointwise absence diagnostics remain available with their own scope.

Raw pitch within ±50 cents counts voiced-reference abstentions as misses. Chroma agreement cannot hide octave errors; preserve signed/absolute cents, octave/non-octave counts and voicing exclusions. Top-one activation uses deterministic lowest-MIDI tie breaking before truth; uncalibrated activation is not probability of a correct note. Thresholded polyphonic sets retain TP/FP/FN, missing/extra harmonic voices and cardinality errors. Compare each pYIN branch separately at predeclared paired timestamps; agreement is not independent musician truth or equal model-input support. Never choose a branch or octave by reference proximity.

Both project decoders, 127.7/25-ms floors with fixed 0.5/0.3 thresholds, reuse the same arrays and remain separate. Event identity and mean/max activation summaries are independently reconstructed from arrays. Short floor is not 25-ms acoustic resolution, and project decoding is not complete upstream postprocessing parity. Generated score events provide references; condition boundaries are not new notes. Keep one-to-one onset-only and onset-plus-offset matching, unmatched events and articulation-specific recall. Both event views require ±50 cents pitch and 50 ms onset tolerance; offset view adds max(50 ms, 20% of reference duration). Preserve signed timing residuals; boundary-truncated/unobserved offsets are excluded or null, not fabricated zero errors.

Custom nine-string C1 near 32 Hz, missing fundamentals, distortion, glides, rests, legato and sweeps shape the interpretation. A partial can match chroma while failing fundamental pitch. Generated pitches/attacks do not identify real strings/frets, intended notes, technique or missed/rushed beats. This tool selects no winning estimator or decoder and makes no default adoption, real-performance or listening claim.

## Outputs, failures and bounded iteration

Fresh output contains `learned-pitch-calibration.json`, `learned-pitch-frame-errors.csv` and `learned-pitch-event-errors.csv`; individual files are atomic, not a transactional trio. Compact summary follows full evaluation and points to these artifacts. Read nested status, `hard_gates_passed`, unsupported claims and quality alerts. Structural failures retain diagnostics without metrics; unsupported confirmed claims retain valid numerical evidence but fail hard gates and exit 1. Regression alerts can complete with exit 0 and still report poor synthetic quality. Invalid/reused output rejects with exit 2. A written receipt or successful dispatch is not a quality pass.

Bounds include indices/truth <=5 MB, comparison/pYIN JSON <=64 MB, generated WAV <=3 MB, NPZ archives <=100 MiB, numeric arrays <=20 MiB, at most twenty-four aggregate windows and 5,000 events per decoder preset. Existing bank, predictions, media, model/runtime and actual-run artifacts remain unchanged.

Inspect fixed coverage, hashes, clock/support exclusions and failed cases first. Research pinned clock/window/decoder and metric definitions through the contract's primary sources; compare compatible sealed prediction indices in fresh outputs only within separately authorized discovery work. This evaluator never reruns discovery or tunes by truth. Keep cohort, branches, thresholds, tolerances and clock policy fixed; retain quality failures and nulls. Follow [the agent evidence contract](../../../docs/spec/AGENT_TOOLS.md) for durable settings, versions, source hashes and generated-only scope.
