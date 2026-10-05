---
name: guitar-pitch-evaluate
description: Evaluate a fixed generated nine-string pitch pilot with hash-bound native timing, separate pitch branches, voicing and exclusion metrics; do not promote synthetic scores into real-note correctness.
---

# Evaluate generated pitch hypotheses

**Hook:** MCP tool `pitch_evaluate`, prompt `guitar-pitch-evaluate`. Inspect `tools/list` for the currently available schema. Evaluation consumes existing bank/pilot/pitch receipts; it does not invoke pYIN, decode audio, generate fixtures, transcribe the phone take or grade a musician.

## Use and controls

Required `fixture_index`, `pilot_index` and `output` are paths of 1–4,096 characters. `timeout_seconds` is integer 1–900, default 120. All paths remain beneath this repository's `artifacts/benchmarks/`; inputs must exist and output must be new. Preserve unsafe-path rejection. No pitch threshold, branch, octave, cents tolerance, source offset, backend or analysis-budget knob is exposed here.

Direct worker: `python3 scripts/pitch_evaluate.py --fixture-index "<bank-index>" --pilot-index "<pitch-pilot-index>" --output "<new-directory>" --summary`. Recipe: `just tool-run pitch_evaluate '{"fixture_index":"<bank-index>","pilot_index":"<pitch-pilot-index>","output":"<new-directory>"}'`. Read [the pitch calibration contract](../../../docs/spec/PITCH_CALIBRATION_LANE.md).

## Fixed coverage and provenance

The schema-2 `technical-v2` bank has twelve cases/120 seconds. Its schema-1 pilot must contain four completed jobs totaling thirty analyzed seconds: missing-fundamental clean eight, tuning-ladder clean eight, legato-transition mixture six, and sweep/polyphony mixture eight. Each starts at zero with explicit contiguous coverage. Other bank cases are unrequested, not successful evaluations. A clean-component score cannot establish mixture behavior.

Verify bank/pilot/truth/source/component/pitch hashes, instrument context, worker/library versions, fixed settings, exact frame grid and coverage. Generated WAV bytes are read to verify hashes, PCM headers and extent, without waveform decoding or inference. Require explicit `synthetic_generator_sample_zero`; never guess an origin from missing timestamps. JSON indices/truth are bounded to 5 MB, pitch artifacts to 64 MB/4,000 branch frames and each generated WAV to 3 MB. Structural failure remains failure even when a receipt is written.

## Read scores with exclusions

Inspect compact stdout plus `pitch-calibration.json`, `pitch-frame-errors.csv` and `pitch-transition-errors.csv`. Keep statuses, `hard_gates_passed`, unsupported-claim counts, hard failures and quality alerts distinct. Structural failures emit diagnostics without metrics; valid inputs containing unsupported confirmed claims retain numerical measurements but fail their hard gates. Completion with regression alerts is a measured baseline, not a quality pass or real-performance verdict.

Evaluate low/high branches independently; never select the branch or octave nearest truth. Native reference samples are rounded from recorded frame centers. Stable monophonic scoring requires a whole analysis window within one eligible reference region. Excerpt edges, transitions, out-of-range frequencies, unknown references and polyphony stay separate. Short sweep notes may provide no complete low-branch window; zero eligible frames produce null metrics, not perfect accuracy.

Raw pitch accuracy uses ±50 cents and counts voiced-reference abstentions as misses. Raw chroma accuracy is separate and cannot hide ±1,200-cent octave errors. Retain signed/absolute cents, octave/non-octave counts, voicing false alarms, denominators and per-condition abstentions. Algorithm voicing probability is not calibrated note-correctness confidence. Transition offsets are unshifted and may be censored by window resolution; no fitted delay, tuning correction or time warp is applied. Report p95 only with enough applicable samples.

Preserve the custom tuning ladder and its Eb2→Bb2 interval. Its theoretical frequencies become exact generator parameters only in this bank. C1 near 32.703 Hz, a 32.000 Hz preservation sentinel and harmonics without a synthesized fundamental are different cases. Harmonic/octave alternatives and polyphony never establish unique strings, intended notes or player mistakes.

## Agent iteration

Inspect fixed pilot coverage, run bounded evaluation, research pYIN framing and pitch/voicing metric definitions through the contract's primary sources, and inspect exclusions before interpreting an aggregate. Compare supported analysis settings only through the owning pitch tool and a separately recorded compatible pilot; this fixed evaluator rejects changed settings. Keep truth, seeds, branch policy and scoring offsets frozen. Save source/tool/version receipts, coverage and regressions in fresh outputs. Follow [the agent tool contract](../../../docs/spec/AGENT_TOOLS.md); synthetic measurements, actual-take evidence, listening and musical acceptance remain separate.
