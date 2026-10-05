# Automatic tonal-context candidate lane

Owner: `/root/tonal_inference`, October 5, 2026. Authority: the operator's
ten-hour parallel goal and R-HOOK-CONVERGENCE-20261004 / R-N13. This lane owns
`scripts/tonal.py`, `tests/test_tonal.py`, this specification and
`docs/research/TONAL.md`; root owns integration and publication.

Implement a bounded, dependency-free reader of the existing hash-bound
post-denoise `analysis.librosa.features.chroma` matrix. Compare two documented
major/minor profile families and seven diatonic collection masks. Return ranked
profile fits, scale-collection compatibility, pitch-class entropy, score margins
and local ranking stability. Keep tonic and mode nullable; none of these scores
is a calibrated probability or an intended-note/performance verdict.

First checkpoint: primary-source research and this durable plan. Next: validate
input identity, finite matrices and source-time extents; implement bounded local
contexts and recurrence-window comparisons; test transposition, known triad and
modal collections, chromatic/uniform/single-pitch/power-chord abstention, harmonic
ambiguity, tampering and output immutability. Last: run on the actual calibrated
take and send root exact counts, outputs, limitations and hook contract.

Protect custom tuning C1 F1 Bb1 Eb2 Bb2 Eb3 Ab3 C4 F4. Open-string metadata is
context, not prior evidence that the recording is in C or F. A 4096-point chroma
FFT at the current 16 kHz rate has about 3.91 Hz bin spacing; C1-to-Db1 is
only about 1.95 Hz. The worker reports the actual configured rate/window.
Harmonics may dominate this representation and create plausible false triads.

Inputs: run directory containing `manifest.json`, `analysis.json` and optional
`phrases.json`. Only verified restored derivatives qualify; no implicit media
processing or dependency/model installation. Resource bounds: 20 MB per JSON,
36,001 feature frames, 1,800 seconds, 256 regions, 60 recurrence comparisons. Missing tonal
features produces an explicit unavailable receipt. Output is a new immutable
`tonal/<UTC>-<random>/tonal.json`, separate from current analysis and DAG files.

Candidate discovery requires no expected score. Scientific-pitch labels,
enharmonic spelling, true tonic, modal interpretation, key changes and played
notes remain unverified. Root may expose this operation through MCP/skill after
worker tests and actual-run evidence; the lane does not alter shared registries.

## Implemented worker contract

`python3 scripts/tonal.py RUN_DIR [--max-regions 128] [--max-recurrences 30]`
accepts integer region bounds 1..256 and recurrence bounds 1..60. It requires
the current analysis lineage's exact manifest hash, matching restored media
hashes and a no-time-stretch receipt. Optional `pitch.json` must match the same
analysis input; its sparse coverage is recorded separately and its dependent
branches/octave alternatives are not pooled as note votes. No network access,
media decode, weights or optional Python imports occur in this worker.

Stdout is one JSON object with `tonal_json`, `status`, `region_count`,
`recurrence_count`, nullable `tonic` and nullable `mode`. The result records
input/settings/tuning hashes, theoretical tuning, whole-take and discovered
region contexts, two profile rankings, grouped diatonic collection rotations,
entropy/margins/local agreement and recurrence distribution affinity. A missing
feature matrix yields `tonal_features_unavailable` without rerunning analysis.
Outputs retain private file permissions and never replace current artifacts.

## Runtime checkpoint, 21:34 UTC

The standard-library interpreter passes 20 tests with one explicit optional
fixture skipped. The locked `.venv` passes **all 21 tests**, including a waveform
with only harmonics 2, 3 and 5 of theoretical C1 and no C1 fundamental. This
fixture explicitly leaves tonic/mode null. No real-take accuracy follows.

Actual calibrated run `20261005T211103Z-c6d0bac2fcd2` produced an independent
receipt at `tonal/20261005T213445Z-ca446d4dbef9/tonal.json` in approximately
2.50 seconds. It contains **48 discovered regions and 14 recurrence context
comparisons**. Whole-take entropy is approximately **0.975755**, causing
near-uniform/chromatic-distribution abstention. Eleven region contexts retain
ranked hypotheses; 37 abstain (some contexts have several abstention reasons).
The two whole-take profile families disagree and correlate weakly, approximately
0.334 and 0.350. **No tonic or mode is asserted.** Pitch coverage is recorded
as approximately 13.2484% and not used to manufacture a full note histogram.

The immutable receipt records exact input artifact hashes. Root must regenerate
tonal context after changing the manifest, analysis, phrases or pitch receipt;
this checkpoint does not claim a main DAG, MCP, report or tracker integration.

Independent read-only review found and closed a tuning-registry read/hash race.
The worker now parses and hashes the same bounded registry bytes and rejects
registry changes during processing. A temporary-root regression proves both
mutation rejection and agreement of retained metadata with its digest. The
reviewer independently passed this regression and the duration-limit test.
