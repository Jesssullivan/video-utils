# Low-register noise separability — research/design receipt

Actor/owner: `audio_research`. Authority: root's independent low-register
noise/preservation lane under the operator's active project goal, repository
`AGENTS.md`, R-HOOK-CONVERGENCE-20261004 and R-N13. Exclusive writes are this
receipt and `docs/spec/LOW_REGISTER_NOISE_SEPARABILITY_LANE.md`. Reviewed primary
sources and frozen local measurements; no source/audio decode, candidate render,
core worker/profile change, package/model acquisition, host change or sibling
write was performed. The previous published calibration receipt is preserved.

Applied the repository `guitar-noise` and `guitar-denoise` skills: a quiet interval
and stable spectral line are candidates, not proof of noise-only content; retain
intentional approximately 32 Hz nine-string content. Skills do not create a
permission gate. The implementation/render hold here comes from root's explicit
documentation-only file ownership.

## Existing actual evidence reviewed

Original source identity is
`a522115f4e72e19384fb341bc84369728eceefe49183b8c6367a1008a95176c6`.
Actual captured8 has verified pre-gain 4–5 s RMS reduction of 4.445 dB. Active
intervals 10–20, 40–50, 90–100 and 130–140 s lose 2.759/2.040/2.063/2.404 dB
of 20–45 Hz **mixture** power; 45–120 Hz loses only
0.196/0.108/0.121/0.086 dB. Neither total quiet-window RMS nor active mixture
attenuation establishes isolated fan removal or C1 gain. The captured8-clarity
branch has identical pure denoise/residue bytes; later EQ, compression and
normalization are separate comparisons.

`clip_baseline` independently characterized 2.85 seconds of selected original
samples, with bounded repeat checks documented in
[`BOX_FAN_CAPTURE.md`](../research/BOX_FAN_CAPTURE.md). Its 0.85–1 s intervals
support only three/four overlapped Hann Welch averages at 2.692 Hz bin spacing.
Capture/tail/opening spectra differ unevenly; AGC is only one possible cause.
The approximately 43 Hz maximum is a rising band edge in capture/tail, not an
isolated peak with measurable linewidth. A theoretical C1-nearest bin is not a
local maximum, which does not establish C1 absence. Higher harmonic-like lines
overlap the theoretical tuning, including an Eb2-like comb, without identifying
notes, fan RPM or pure fan components. No additional actual samples were read
by this lane; these are reviewed producer measurements, not new listening claims.

| Frozen evidence | SHA256 at review |
| --- | --- |
| Captured-restoration comparison JSON | `16a333af8d6068aabb4215cf183fa2d18b6726d38affcbe439c29d55cf004e0f` |
| Captured-restoration segment JSON | `9ebea516778d6ccef0c7e897bcd8ae7b6586fc364bf2019492b3a9a16a2fef5b` |
| Box-fan research Markdown | `20564e781eb005ea57090cd322a0a92879e94d19deb7d917d9fb1e07afd3234b` |
| Published calibration-pilot results receipt | `749280a2d684d876ace869ebc4cd4c24b93175a9e48bdb87d85de92d2a6707c8` |
| Published calibration-contract review receipt | `3f54003b5dc8d448c38c5aa2aecd1588560d2a314f4173095c0b6cbde1a00989` |

## Primary-source findings

Sources checked October 5, 2026, local operator date:

| Primary source | Supported finding and project implication |
| --- | --- |
| [FFmpeg filter documentation](https://ffmpeg.org/ffmpeg-filters.html#afftdn) and [upstream afftdn code](https://raw.githubusercontent.com/FFmpeg/FFmpeg/master/libavfilter/af_afftdn.c) | Captured shape/floor/reduction/tracking controls exist. Reviewed upstream windows are about 37.5 ms and profile centers begin at 80 Hz; these are coarse controls rather than a dedicated 32 Hz mask. Installed-source applicability must be checked before implementation. |
| [Martin 2001, original paper](https://www.iks.rwth-aachen.de/fileadmin/publications/martin01c.pdf) | Spectral-minimum tracking estimates noise without an activity detector. Sustained musical energy makes blind minimum tracking a contamination risk; keep the reviewed initial capture fixed and compare tracking separately. |
| [Ephraim–Malah 1984, author-hosted paper](https://malah.net.technion.ac.il/files/2017/08/Ephraim_Speech_Enhancement_ASSP84.pdf) | MMSE spectral estimation relies on an additive statistical model. Prior mismatch and uncertain noise PSD remain relevant for saturation/long guitar tails; model estimates are not separated ground truth. |
| [FitzGerald 2010, original proceedings paper](https://dafx10.iem.at/papers/DerryFitzGerald_DAFx10_P15.pdf) | Median filters emphasize harmonic/percussive geometry. Fan lines and guitar sustain may share one geometry; pick/click events may share another, so component names do not identify wanted guitar versus noise. |
| [RNNoise, author explanation](https://jmvalin.ca/demo/rnnoise/) | The model targets speech communication with coarse band gains and pitch processing. This does not establish preservation of 32 Hz distorted guitar. |
| [DeepFilterNet, original paper](https://arxiv.org/abs/2110.05588) | Its design is speech enhancement with spectral-envelope and periodic processing. Treat it as a separate music-preservation experiment if ever admitted, not the default. |
| [SciPy Welch documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.welch.html) | PSD density and integrated band power need distinct units and window support; overlapped short estimates do not justify physical linewidth or sub-bin certainty. |

These are method/risk findings, not evidence that a specific speech model or
new estimator was run on this recording. No paper PDF or model was copied into
the repository. Fan-mechanism claims remain in the complementary characterization.

## Design decisions and adoption evidence

The owned specification defines a reversible, explicit continuous low-register
protection comparison: 0 or 0.5 dB bin-gain ceiling over 20–80 Hz, tapering over
80–140 Hz, plus fixed captured-PSD scale comparisons. These are **proposed future
controls**, not current MCP/profile options or a preservation guarantee. A mixture-
derived harmonic prior may widen protection but never identify intended notes.
No blanket high-pass, mains notch, fixed C1 deletion or hidden transient bypass
is introduced. Retaining uncertain low fan energy is a declared tradeoff.

An additive mono mixture permits infinitely many source assignments. A separate
fan sample improves statistical evidence, not instantaneous phase cancellation.
Possible recording AGC changes capture transfer; its actual presence remains
unverified. Longer same-device muted-string captures, a contemporaneous reference
mic or DI track help different parts of this uncertainty but are not mandatory
to proceed with reversible comparisons.

Adoption uses an eight-case/64-second bounded separability bank: clean C1,
fan-only, exact-frequency collision, separated-frequency control, walking low
notes, palm mutes/decay, missing F0 and declared time-varying noise/gain. Include
native extent/latency controls and held-out phase/SNR/distortion/decay conditions.
Synthetic captures bind their own sources; never spoof the actual take's SHA.

The decisive accounting distinction is recorded in the spec. Save a mask
computed from mixture evidence alone, then evaluate that **same frozen mask**
against known guitar/noise components afterward. Conditional linear decomposition
separately measures noise residual and musical damage. For a black-box adaptive
denoiser, `D(s+n)-D(n)` is only incremental response because filtering can depend
on its input; it is not an isolated guitar stem. Keep clean-only damage, noise-only
reduction and mixed-reference error separate. Exact collisions must expose
ambiguity/remaining noise instead of promising simultaneous perfect removal
and preservation.

The initial proposed clean/identifiable C1 preservation gate is no more than
0.5 dB coherent fundamental attenuation; a per-bin floor alone does not establish
that result after overlap-add. Record attack/tail tolerances before future runs.
Use noise-versus-damage Pareto comparisons, then original-aligned actual A/B and
residue listening. Whole-mixture band power, high coherence, matched LUFS or a
synthetic score cannot replace musical acceptance.

Coordination: root received the evidence/proposed tests; `clip_baseline` supplied
bounded characterization; `rhythm_analysis` received the distinction between
source-bound capture-profile authoring and the separate future STFT/mask route.
Current profiles, captures, masters and the published pitch/phrase pilot remain
unchanged. This lane's result is a concrete next-stage design, not an admitted
new restoration method or accepted best candidate.

Closeout validation: local Markdown targets resolve and `git diff --check` passes
for the two owned files. All five frozen evidence SHA256 values in the table
match at readback. No actual audio was decoded or processed by this lane.

Process receipt: actor audio_research | target owned noise-separability spec and
dated research receipt | reason measured quiet improvement with unresolved
active 20–45 Hz attenuation | ruling R-HOOK-CONVERGENCE-20261004 / R-N13 |
prior_state source-bound audition candidates, musical preservation unresolved |
result primary-source research and bounded separability/adoption plan; no DSP
render, source/core/host mutation or isolated-stem claim.
