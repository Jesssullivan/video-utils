# Optional PCEN and xoxd-spectrogram lane

Owner: `xod_spectrogram`; root integrates. Authority:
R-HOOK-CONVERGENCE-20261004, TIN-3692 comment
`98cf680c-7299-4949-bfb2-60079053ad43`. User explicitly requested this parallel
lane on October 5, 2026. Enhanced restoration and marked video remain independent.

Current state: canonical private revision identified; bounded feature proof
complete; no runtime/default/frontend package admission. Research and dependency
limits are in [`XOD_SPECTROGRAM.md`](../research/XOD_SPECTROGRAM.md).

## Next-week experiment, approximately 5–7 hours

1. **Contract and reference, 1 hour.** Keep the current log-mel configuration as
   the control. Add an optional PCEN feature artifact using existing librosa,
   whose dependency is already locked. Record magnitude/power, scale, FFT,
   window, hop, filter norm, centering, smoothing coefficient, startup state,
   warm-up and source time. Qualify streaming/batch parity and source timing.
   The TypeScript package remains a reference until its license is established.
2. **Frozen feature ablation, 1–2 hours.** Use the full fixed technical-v2 corpus,
   without passing labels, case identity, intended BPM or score to discovery.
   Prespecify power and magnitude log controls plus PCEN gain `{0.5, 0.98}`,
   smoothing `{0.1, 0.4, 1.0}` seconds, fixed bias 2/power 0.5/explicit scale.
   Cap at 12 PCEN settings, two numeric threads, one worker and 15 minutes per
   run. Compare raw and hash-bound denoised inputs as distinct conditions.
3. **Low register and phrase windows, 1–2 hours.** Keep short-window attacks
   separate from 2048/4096-sample low-frequency features at 16 kHz. Report
   temporal blur and coverage. Cross frontend with half/double-time and bounded
   2/4/8-pulse plus absolute-seconds recurrence-window hypotheses; hold each
   factor fixed while measuring another. Do not attribute a pulse-window fix
   to PCEN. Preserve unwarped timing alongside aligned recurrence comparisons.
4. **Evaluation and review, 1–2 hours.** Use labels only after discovery. Report
   onset one-to-one precision/recall at 20/50/100 ms, low sustain/legato missed
   events, click overlap, phrase boundary/recurrence scores and silent false
   positives, stratified by articulation. Audit actual bounded excerpts with
   sparse musician annotations and retain unknowns. Promote no default on
   aggregate onset-count or unlabelled similarity alone.

## Agent interface and adoption gate

If implemented, expose an analysis-only primitive with a typed MCP hook and a
repo skill stating its role, supported knobs, source/producer hashes, maximum
duration, frame support, warm-up and comparison obligations. It returns feature
and evaluation paths; it does not write the master, confirmed errors or latest
markers. Musical phrase review remains possible without an intended score;
definite missed-note/beat claims require intent and calibrated evidence.

Acceptance requires reproducible input/version/settings hashes, finite bounded
outputs, streaming state parity, timestamp tests, low-register preservation in
the analysis representation and no regression concealed by corpus averages.
Select defaults only after held-out guitar review and the separate recurrence
window ablation. AU render integration and GUI package admission are later
milestones, each with independent license, packaging and host proof.

The completed proof already met its limited gate: exact PCEN/reference parity,
bounded real/generated feature execution and honest negative findings. No
further activity from this lane is required for tonight's video render.
