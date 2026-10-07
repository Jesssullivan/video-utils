# Capture-latency calibration for click-relative guitar timing (research note)

Lane `timing_calibration`, sprint `20261007-s3`, Linear TIN-5488. Contract:
[TIMING_CALIBRATION_S3.md](../spec/sprints/TIMING_CALIBRATION_S3.md). Sources were
accessed 2026-10-07. Bibliographic metadata was checked against Crossref (DOI),
publisher, BIPM or vendor pages, as marked. Paywalled full texts were **not** read;
for those, only the metadata and the abstract were verified.

## Question

On a phone or Photo Booth recording, the metronome is an acoustic click in the room,
and the guitar comes from an amp. A measured "onset minus click" offset (from
`phrase_timing`) is therefore not yet a rush/drag direction. Which terms separate the
two, which can be calibrated with a short operator clip, and which stay unknown?

```
measured = emission_offset + (d_mic_amp - d_mic_metronome)/c + amp_chain
         + (b_attack(class) - b_click) + residual
```

## 1. Onset-detection latency and bias depend on the transient

- **Bello et al. (2005)**, "A tutorial on onset detection in music signals", *IEEE
  Trans. Speech Audio Process.* 13(5):1035–1047. DOI
  [10.1109/TSA.2005.851998](https://doi.org/10.1109/TSA.2005.851998) (Crossref
  verified).
  - The tutorial frames detection as reduction to a detection function followed by
    peak picking.
  - It distinguishes the physical onset, the attack and the transient. It notes that
    a detection function peaks during the attack, not at its start. (Inference from
    the tutorial's framework: the reported time is biased by the attack shape, so a
    click and a slow-rising low-string attack get different biases.)
- **Dixon (2006)**, "Onset Detection Revisited", *Proc. DAFx-06*, Montreal.
  [DAFx archive](https://dafx.de/paper-archive/details/_kscRgr98aSFW4l-j1YJuA)
  (archive entry verified).
  - Compares spectral-flux, phase and complex-domain detection functions on
    annotated datasets. Evaluation uses tolerance windows of tens of milliseconds,
    which is coarse relative to our 5 ms decision margin.
- **Böck, Krebs and Schedl (2012)**, "Evaluating the online capabilities of onset
  detection methods", *Proc. ISMIR 2012*, pp. 49–54.
  [ISMIR archive PDF](https://archives.ismir.net/ismir2012/paper/000049.pdf),
  [Zenodo 1416036](https://zenodo.org/records/1416036) (entries verified).
  - Online (causal) detectors carry a systematic reporting delay compared with
    offline peak picking, and the delay depends on the method.
- **Vos and Rasch (1981)**, "The perceptual onset of musical tones", *Perception &
  Psychophysics* 29(4):323–335. DOI
  [10.3758/BF03207341](https://doi.org/10.3758/BF03207341) (Crossref verified).
- **Gordon (1987)**, "The perceptual attack time of musical tones", *JASA*
  82(1):88–105. DOI [10.1121/1.395441](https://doi.org/10.1121/1.395441) (Crossref
  verified). From the abstract: perceptual attack time "is dependent on both rise
  time and listening level, indicating that the slope of the rise function is a key
  factor".
  - Implication: a palm-muted pick attack, an open C1 (32.70 Hz) attack and a
    metronome click have different rise slopes. Their perceived times, and any
    detector's reported times, differ by a class-dependent amount.

**Repository measurements (M-syn, existing).** These come from
`rhythm.onset_detector_delay_calibration()`, 16 probes per cell:
- `high_frequency_novelty` on a 3.5 kHz click: median +0.16 ms;
- `broadband_rms_novelty` on a distorted C1 attack: +2.34 ms.

The difference (about 2.2 ms) is the size of term `b_attack − b_click`. It is large
relative to the 5 ms decision margin.

**This lane's approach.** It measures the bias **on the operator's real click and
real isolated attacks** against a fine-onset reference: a 20 % threshold crossing
on a 0.5 ms smoothed |x|. The fine reference's own per-class bias comes from
noise-free probes. On dev fixtures the recovered class biases matched generator
truth within 0.21 ms (9/9; spec §10.10).

## 2. Acoustic path delay

- **Cramer (1993)**, "The variation of the specific heat ratio and the speed of sound
  in air with temperature, pressure, humidity, and CO2 concentration", *JASA*
  93(5):2510–2516. DOI [10.1121/1.405827](https://doi.org/10.1121/1.405827) (Crossref
  verified). The abstract states a speed-of-sound uncertainty below 300 ppm over
  0–30 °C.
- **Wong (1995)**, comment on Cramer, *JASA* 97(5):3177–3179. DOI
  [10.1121/1.411818](https://doi.org/10.1121/1.411818). It confirms c0 = 331.29 m/s
  at 0 °C.
- The lane uses the ideal-gas approximation c(T) = 331.3·√(1 + T/273.15) m/s. That
  gives 343.2 m/s at 20 °C, so **2.91 ms per metre**; humidity is ignored. Over
  15–30 °C, c varies by ≈ 2.6 %. On a 2.7 m path difference (the maximum in the
  fixtures) that is ≈ 0.2 ms, small next to the distance uncertainty.
- The term that matters is the **difference** (d_mic_amp − d_mic_metronome). A tape
  measure (±5 cm) gives ±0.15 ms per distance; an eyeballed estimate (±30 cm) gives
  ±0.87 ms. Placing the phone equidistant from the amp speaker and the metronome
  drives the estimate towards 0.
- Not modelled, and covered only by the residual floor (uniform ±1 ms): room
  reflections, the acoustic centre of a 4×12 or 1×12 cabinet compared with the
  metronome body, and the near-field of the cabinet.

## 3. Device input latency is common-mode within one recording (inference)

- **Apple**, `AVAudioSession.inputLatency`: "The latency for audio input, in
  seconds." It is a `TimeInterval`, read-only.
  [developer.apple.com](https://developer.apple.com/documentation/avfaudio/avaudiosession/inputlatency)
  (documentation JSON verified). It is a per-route, per-session hardware/driver
  quantity.
- **Android Open Source Project**, "Audio latency measurement":
  > audio latency is measured as round-trip latency, which represents the combined
  > input and output latency

  It is measured by loopback and correlation.
  [source.android.com](https://source.android.com/docs/core/audio/latency/measure)
  (page verified).
- **Inference, not a measurement.** The click and the guitar reach the *same*
  microphone and pass through the *same* ADC, buffer and AAC encoder in one
  continuous recording. A constant input latency shifts both by the same amount, so
  it cancels in onset − click. This holds only for time-invariant, signal-independent
  delay.
  - It does **not** cover adaptive or signal-dependent processing, such as voice
    processing, AGC, noise suppression or a codec's transient handling. That
    processing could treat a 3.5 kHz click and a distorted low-string attack
    differently. The lane records `phone_input_latency:
    "common_mode_within_one_recording_inference"` and leaves this unmeasured.
  - The A/V picture offset is a separate question (`av_picture_offset:
    "not_applicable_audio_only"`).

## 4. "Played on the click" is not ground truth (sensorimotor synchronization)

- **Repp (2005)**, "Sensorimotor synchronization: A review of the tapping
  literature", *Psychonomic Bulletin & Review* 12(6):969–992. DOI
  [10.3758/BF03206433](https://doi.org/10.3758/BF03206433) (Crossref verified;
  full text paywalled, not read).
- **Repp and Su (2013)**, "Sensorimotor synchronization: A review of recent research
  (2006–2012)", *PBR* 20(3):403–452. DOI
  [10.3758/s13423-012-0371-2](https://doi.org/10.3758/s13423-012-0371-2) (Crossref
  verified).
- **Aschersleben (2002)**, "Temporal control of movements in sensorimotor
  synchronization", *Brain and Cognition* 48(1):66–79. DOI
  [10.1006/brcg.2001.1304](https://doi.org/10.1006/brcg.2001.1304) (Crossref
  verified).
- What these reviews establish is the *negative mean asynchrony*: taps tend to
  precede the beat although they feel synchronous. Secondary summaries put it at
  roughly 20–80 ms, smaller for trained musicians. **The exact magnitude was not
  read from the paywalled primary text** and is treated as unverified.
- Consequence: segment 4 (palm mutes deliberately "on the click") is a
  **consistency check only**. It can fail a calibration when its calibrated median
  lies outside [−60, +30] ms, which would indicate a wrong segment, a half-period
  association or moved equipment. It never sets or tunes the offset. Dev fixtures
  draw μ_player from U[−40, +10] ms to reflect this.

## 5. Prior art on metronome-relative and beat-relative timing measurement

- **Anglada-Tort, Harrison and Jacoby (2022)**, "REPP: A robust cross-platform
  solution for online sensorimotor synchronization experiments", *Behavior Research
  Methods* 54(5):2271–2285. DOI
  [10.3758/s13428-021-01722-2](https://doi.org/10.3758/s13428-021-01722-2) (Crossref
  verified).
  - This is the closest prior art. The metronome is played through laptop speakers
    and recorded **in a single channel** together with the participant's taps. The
    stimulus and response are then aligned by signal processing, so device latency
    largely cancels.
  - The abstract reports latency and jitter within 2 ms on average.
  - The difference here is that their response was a finger tap, not a distorted
    low-tuned guitar through an amp at a different distance. That is why this lane
    adds the acoustic path and the class-dependent detector bias.
- **Goebl (2001)**, "Melody lead in piano performance: Expressive device or
  artifact?", *JASA* 110(1):563–572. DOI
  [10.1121/1.1376133](https://doi.org/10.1121/1.1376133) (Crossref verified).
  - An apparent ~30 ms timing lead at the hammer-string level almost vanishes at the
    finger-key level. A measurement-chain artifact can therefore mimic an expressive
    timing offset, which is the same risk this lane guards against.
- **Friberg and Sundström (2002)**, "Swing ratios and ensemble timing in jazz
  performance", *Music Perception* 19(3):333–349. DOI
  [10.1525/mp.2002.19.3.333](https://doi.org/10.1525/mp.2002.19.3.333) (Crossref
  verified).
  - Soloists playing "behind the beat" were measured relative to the cymbal. It is
    prior art for beat-relative timing as a descriptive (not normative) quantity.
- **Rhythm-game calibration.** Harmonix, "How to Calibrate" (Rock Band 4),
  [harmonixmusic.com](https://www.harmonixmusic.com/blog/how-to-calibrate) (page
  verified).
  - Automatic audio calibration holds the controller's sensor to the speaker.
    Manual calibration strums "in time with drum beats".
  - The manual mode folds the player's own asynchrony into the calibration. This
    lane avoids that by never using segment 4 to set the offset.
  - A related patent (US 2009/0310027, "separate audio and video lag calibration")
    could not be fetched (HTTP 403). It is **unverified and not cited**.

## 6. Uncertainty combination

- **JCGM 100:2008**, *Evaluation of measurement data — Guide to the expression of
  uncertainty in measurement* (GUM), BIPM. DOI
  [10.59161/JCGM100-2008E](https://doi.org/10.59161/JCGM100-2008E) (BIPM publications
  page verified).
- The lane follows the GUM pattern:
  - type B uniform terms with u = half-width/√3 (distances, speed of sound, amp
    chain, residual, fine-estimator spread, sub-hop quantization when phase-locked);
  - type A order-statistic CIs of medians, with u = CI half-width/1.96;
  - root-sum-square combination, with an expanded uncertainty at coverage factor
    k = 2.
- The decision rule (abstain when U > 5 ms; emit direction only when |calibrated
  median| > max(U_phrase, 5 ms)) is a lane policy, not a GUM requirement.

## What the operator clip calibrates, and what stays uncalibrated

| Term | Calibrated by | Status |
| --- | --- | --- |
| Acoustic path | Distances (measured ±5 cm or estimated ±30 cm) and temperature | Inferred from geometry; reflections are in the residual floor |
| Amp chain | Operator declaration (`analog` 0 ± 0.1 ms, or `declared:X` ± 0.5 ms) | `unknown` always abstains (U ≥ 5.77 ms) |
| Click detector bias | Segments 1 and 5 (click only), measured on the real click | M-real once a clip exists; none in this lane |
| Palm-muted and open attack bias | Segments 2 and 3, isolated offbeat attacks | Same |
| Legato, tapping, sweep bias | Nothing | `uncalibrated` |
| Phone input latency | Nothing (inference: common-mode) | Not measured |
| Player intent | Nothing (segment 4 is a consistency check) | `human_intent_is_ground_truth: false` |
| Click identity in the take | Nothing | `unverified` |

## Results of this lane (M-syn only; receipts in `docs/agent-notes/sprints/20261007-s3/`)

| Run | Seeds | E1 calibrated | E1 median abs error (withheld = inf) | E1 coverage | Sign-correct, E1 + E2 | On-time emissions | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| R1 (eval commit `4ad7e01`) | 5501–5508 | 4/8 | inf over 48 (1.08 ms over 18 measured) | 17/18 | 34/34 | 0/24 | **S1 failed**: click-grid seeding was corrupted by fan-noise peaks |
| R2 (fix `339ae09`, new seeds) | 5601–5608 | 8/8 | 0.98 ms over 48 (0.72 ms over 41 measured) | 41/41 | 62/62 | 0/24 | S1, S2 and S3 met |

- **E2 (estimated distances).** In R2, 0/8 abstained; median |error| was 1.18 ms and
  coverage 41/41.
- **E3 (amp moved 1.5 m after calibration).** Median |error| was 4.75 ms, coverage
  16/38, with 1 wrong sign in 27 emitted. A moved placement invalidates the record.
- R1 is not rescored. Both runs are reported.

## Limitations

- **The sealed results are synthetic (M-syn).** The generator's click and attack
  models (exponential sine click, resonant wood click, tanh-driven attacks with a
  1.5 ms rise) are simplifications. A real metronome, cabinet, room and phone DSP
  may produce transients whose fine-onset bias differs from the probe table. On dev
  fixtures, the open-attack fine bias of higher strings differed from the C1 probe by
  ≈ 0.3 ms.
- **The click-coincidence confound in `phrase_timing` is a measured dev finding.**
  For phrases played after the click, the nearest-onset rule can measure the click's
  own broadband event. The calibrated view withholds such phrases instead of
  correcting them. On the real take, 74/216 click-proximal onsets lay within 2.5 ms
  of an observed click candidate (S2 receipt), so this guard is material there.
- **A hop-locked tempo weakens the click term.** When the click period is a multiple
  of the 5 ms hop (e.g., 150 BPM at 16 kHz), the detector's quantization phase is
  fixed per recording. The phase-lock term (±2.5 ms uniform) covers the
  session-to-take mismatch but widens U.
- **The record is only as good as the declared placement.** The E3 stress arm moves
  the amp 1.5 m, about 4.4 ms, and shows what happens when that declaration is wrong.
- **Nothing here is a listening claim.** No real take was processed, and no real-take
  direction is claimed.
