# Bounded NR8 / NR10 actual-take comparison method

Owner: `audio_research`. Authority: root's next-iteration planning delegation,
operator's existing stronger-restoration authorization, repository contract,
R-HOOK-CONVERGENCE-20261004 R-N12/R-N13. This receipt precedes profile authoring
and actual rendering. It authorizes no execution itself. This lane read metadata,
prior measurements and primary documentation; it decoded no audio and created
no profile, render, source change, dependency or model.

## Decision and frozen controls

After root's explicit release and positive independent readback of the corrected
application's native qualification, compare exactly two fresh source-bound
candidates. Change only `reduction_db`: **NR8 control / NR10 comparison**. Hold
the reviewed 4.10–4.95-second capture, `noise_floor_db=-40`, `adaptivity=0`,
`gain_smooth=0`, noise/residual tracking disabled, and the complete-take captured
profile application policy fixed. Capture native bounds are [180810,218295) at
44,100 Hz; music/click contamination stays unknown. Do not replace this review
with a noise-only assertion.

Both candidates retain two peaking EQ bands, 300 Hz / −1.5 dB / Q0.8 and
2200 Hz / +1 dB / Q0.8, followed by the same compressor: threshold −18 dB,
ratio 2:1, attack 15 ms, release 100 ms, knee 3 dB, fixed 25% wet and no makeup.
Both target **−18 LUFS / −1.75 dBTP**. No high-pass, notch, low-register mask,
click attenuation, normalization retuning or additional stage is introduced.

Root explicitly accepted a fresh matched pair. The existing authored NR8 profile
`ff8b4f…` targets −1.5 dBTP and remains unchanged, historical and unrendered.
The selected clarity master independently measures −1.75 dBTP despite its
historical profile target of −1.5. Its measured peak is not its requested ceiling.
Rendering the old authoring unchanged would therefore not create this matched
presentation control. A separate old-profile replay is unnecessary for this
comparison; qualification lineage and fresh actual-source binding are separate
evidence. Keep old selected run `20261005T232741Z-2b5dc43fd009` as a historical
audition reference, not a third newly rendered condition.

## Why test NR10, and what the control means

The [independent prior comparison](2026-10-05-captured-restoration-comparison.md)
found native pre-gain 4–5-second RMS changes of −0.368 / −4.445 / −5.433 dB for
conservative3 / captured8 / captured12. Opening 0–1-second changes were
−0.037 / −0.556 / −0.573 dB. NR12 added about 0.99 dB quiet-window reduction
over NR8, with only 0.017 dB extra opening reduction. These are mixture-energy
changes, not isolated fan removal or SNR improvements.

NR8 already reduced whole-take 20–45 Hz power by 2.320 dB; NR12 reduced it by
2.437 dB. In the four previously measured active ten-second regions, NR8's
20–45 Hz reduction ranged from 2.040 to 2.759 dB, with NR12 adding 0.084–0.166 dB
loss. High coherence did not establish preserved low-string gain. This existing
low-region uncertainty remains material even if NR10 adds little further loss.
NR3 differs in several controls and capture behavior, so it is historical
context rather than a one-knob baseline. No numerical interpolation predicts
NR10's response or establishes that it will sound better.

The official [FFmpeg afftdn documentation](https://ffmpeg.org/ffmpeg-filters.html#afftdn)
defines `nr` and `nf` as dB controls, capture start/stop as profile measurement,
and noise tracking as optional. Importantly, `ad=0` gives immediate per-bin gain
adaptation; a fixed floor with tracking off does **not** freeze gains. `gs`
smooths gains across bins and can reduce musical-noise artifacts; `gs=0` leaves
that smoothing disabled. Hold these controls fixed to isolate NR. The documented
NR10 / −40 example concerns white noise and does not validate distorted guitar.
The documentation is current upstream guidance; the actual run must identify
the already installed FFmpeg build. No upstream-trunk implementation is claimed
to be the exact installed binary.

## Predeclared measurement panels

Measure three separate stages: `denoised.wav` / its pure residue, optional
`processed.wav` after EQ/compression, and final mastered WAV / decoded delivery
audio. Compare NR10 to the fresh NR8 at the same stage and also show each pure
denoise change from native source. Never attribute a mastered passage-level
change solely to denoising. Equal whole-take LUFS does not equalize every passage.

Use these fixed audio-relative intervals, with native bounds obtained by exact
rounding of seconds × 44100, no fitted shift or gain:

| Purpose | Intervals in seconds | Report |
| --- | --- | --- |
| Opening | 0–1 | RMS, sample peak/crest, residue RMS, low-band change |
| Quiet candidate | 4–5 | Same; explicitly includes reviewed capture context |
| Reviewed capture | 4.10–4.95 | RMS and residue; contamination remains unknown |
| Tail candidate | 149–150 | Same plus fixed short-window envelope |
| Active comparison | 10–20, 40–50, 90–100, 130–140 | Band powers/coherence, RMS/crest, envelope and residue |
| End-gesture review context | 140–150 | Same native-stage envelope/residue panels; tapping/legato identity remains unverified |

For historical comparability, whole-take Welch uses Hann length65536,
overlap32768, native rate, no detrending, one-sided density; local Welch and
magnitude-squared coherence use Hann length16384 / overlap8192. Integrate
PSD×bin-spacing over lower-inclusive, upper-exclusive bands 20–45, 45–120,
55–70, 190–225, 250–2000, 2000–10000 and 10000–Nyquist Hz. Report actual bin
counts/window counts, absolute powers and source-weighted coherence. Four
overlapping averages in a one-second panel are particularly weak evidence.
The 20–45 Hz band covers theoretical C1; it does not isolate a played C1 note.
Do not import the separate low-register probe's periodogram estimator as if it
were this Welch measure.

For bounded attack/tail diagnostics, freeze panels from the existing selected
run's `broadband_attack_candidate` rows before reading new candidate waveforms:
in each active region select the earliest three rows at least 0.20 seconds from
the start and 0.50 seconds from the end, separated by at least 0.30 seconds.
Use `audio_relative_seconds`, rounded to native samples; leave fewer panels
explicit if selection supplies fewer. Report native pre-gain RMS and peak in
[−20,0), [0,20), [20,50), and [50,250) ms relative to each selected candidate,
plus fixed 20-ms nonoverlapping envelopes across the active regions. Selection
comes from previously denoised audio, so it is a fixed, potentially biased
review anchor, not a validated guitar attack, physical latency reference or
detector-recall test. Short-window and tail changes describe mixtures; a nearby
click or another note may contribute. No sustain, legato or musical-attack
preservation is certified by these windows.

Inspect/listen to residue at unchanged gain when an operator reviews the pair.
Source minus denoise is removed signal, potentially containing guitar; it is
not an isolated fan stem. Arithmetic verification cannot certify its contents.
Report every panel, including unfavorable changes. Do not rank or silently drop
panels after seeing results, fit alignment to improve metrics, or impose
synthetic component-gain thresholds on this mixture-only evidence. A preference
and adoption decision requires operator review of low-string weight, pick
texture, sustain/tapping/legato and audible musical noise, with uncertainty
retained. This plan declares no automatic quality winner or acceptance gate.

## Execution and integrity contract for the later released phase

Use admitted tool25 authoring with the existing reviewed source/run identities,
then the independently qualified CLI `scripts/apply_capture_profile.py` with
each fresh authoring directory and exact authoring-receipt SHA. Do not expand
the current tool catalog, call an unadmitted application hook, or edit media
workers to make a condition succeed. Run the two actual applications serially,
within each root-released finite budget and two numeric/FFmpeg threads. Retain
the existing worker's bounded exceptional cleanup and honest partial-publication
states; inspect durable selectors before retrying an ambiguous transport result.

Before authoring, freeze source, decoded PCM, review, parent manifest, contexts,
profiles, authoring receipts, application/media/FFmpeg revisions and old protected
master/latest hashes. After execution, independently verify each listed output
hash, finite samples, original 44,100-Hz mono extent **6,657,385 frames**, exact
source identity, calibrated capture/preroll/filter-delay mapping and native
origin. Check source−denoise−residue arithmetic with its recorded float storage
precision. Historical captured8/clarity pure denoise identity is a useful
regression reference; new replay identity must be measured, not assumed across
producer revisions. Investigate any mismatch before attributing it to NR.

Verify retained video ordered packet PTS/DTS/durations and counts, decoded audio
extent/offset with disclosed codec padding, and rehash exported bytes. A MOV
header-duration difference alone is not packet-timeline drift; preserved packet
timestamps do not prove original acoustic camera/microphone synchronization.
Independently measure final audio loudness/true peak from meter **input** values;
report achieved LUFS, peak, LRA and normalization mode for both conditions and
decoded AAC. Treat a −18 LUFS target miss or true-peak ceiling breach as a
delivery finding; do not silently retune one condition. Pure denoise remains the
causal comparison even if later normalization paths differ.

Publish only fresh immutable comparison candidates and receipts. No current
master/latest/default replacement, accepted tone, isolated-component gain,
confirmed note/phrase correctness, repaired physical synchronization or AU/Logic
runtime follows from authoring, generated qualification or numerical readback.

Candidate **delivery** eligibility, separate from musical acceptance, requires
all structural identity/finite/native-extent/timeline gates to pass and the full
decoded AAC input measurement to be −18±0.3 LUFS with true peak ≤−1.75 dBTP.
Reject structural failures for delivery and retain their receipts. A candidate
that meets these checks may be delivered for comparison even if its quiet,
opening, low-band, attack/tail or residue differences require listening. No
mixture-derived universal preservation threshold, automatic preference or
current-master adoption is implied.

## Prospective independent measurement implementation

Reuse the dated comparison worker's `sha`, `load`, `db`, and `describe` helpers,
pinning its source **before** analysis to
`e62498f5e00325e37da2b7d6463ae813c98ae3ae0a27d5bfafd5c3d47cf5efef`.
Its fixed whole-WAV/window method is visible in
[the existing worker](2026-10-05-captured-restoration-comparison.py).
Use the exact local Welch/coherence equations from
[the segment worker](2026-10-05-captured-restoration-segments.py), pinned to
`c195d711d42b86585a6bdc9486c5189e459916930df8a8088562c188e7b39294`.
Retain their historical files and receipts unchanged. Their old `main` functions
select historical runs and therefore must not be blindly rerun as the new pair.
Their existing unbounded `loudness` subprocess helper must not be called without
a new explicit remaining-budget subprocess timeout.

After measurement release, a fresh owned driver may select exactly the two new
manifests, verify output hashes, reuse the pinned pure helpers and emit new
exclusive-create JSON. Predeclare a maximum60-second wall budget, two numeric/
FFmpeg threads, and an explicit deadline for any loudness readback. Existing
copied `source.wav` must match the protected decoded-source hash; read that WAV
once and reuse its array. Do not decode the original movie or create another
full-source PCM derivative. New candidate WAVs and decoded delivery AAC can be
read only within that released measurement scope. Native origin/timing and
export hashes remain bound to the new application/export receipts; meter
results are separately measured, never borrowed from predicted loudnorm output.
If the budget expires, publish incomplete/null measurements with the actual
completed coverage; do not extend it or report unmeasured gates as passed.

## Readback pins and next boundary

Current source-only readback matched application
`00a03ef9fad8543be4335cb5cbcd3c9d9580a6b40b8faeb826811b105fd5daa6`,
authoring `7d2820878826c87aabf2ab60b73c997b9d406b7f3ff8943d6012ed967444c355`,
and media `91443154251888c9e74670790766b289a2618f85f3be806d60ca26882faa9d94`.
The [application receipt](2026-10-06-apply-capture-profile-prototype.md) separates
46 constructed tests from real native execution. Root reports its generated
8-second native trial completed; independent readback and actual-phase release
remain separate at this planning checkpoint.

Prior full comparison JSON SHA256:
`16a333af8d6068aabb4215cf183fa2d18b6726d38affcbe439c29d55cf004e0f`;
segment JSON: `9ebea516778d6ccef0c7e897bcd8ae7b6586fc364bf2019492b3a9a16a2fef5b`.
Selected-run `analysis.json` SHA:
`4d32f962c5c59920943217cfb72fbe3c9e3eb9fefa3c6d9b79ee648187cadd0a`;
`events.csv`: `ab640f6370f5eef2ff0f548f94826b3db631a140d058db1578397d3b48a025f1`.
These analysis events came from the selected NR8 `denoised.wav`, hash
`26c9f42c2bb2957fc35e00f0070991895f9120fefb69dce0a95248cd7ad39bfd`,
not independently measured musical truth. Original source remains bound to
`a522115f4e72e19384fb341bc84369728eceefe49183b8c6367a1008a95176c6`.

Process receipt: actor audio_research | target delegated immutable NR10 method |
reason controlled stronger-restoration iteration | ruling R-N12/R-N13 |
prior_state historical NR3/8/12 measurements and source-qualified application,
native independent readback pending | result planning receipt only; no new
profiles, DSP, source samples, media or adoption.
