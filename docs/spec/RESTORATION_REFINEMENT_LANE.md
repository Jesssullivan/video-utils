# Source-bound restoration refinement

Authority: R-HOOK-CONVERGENCE-20261004 / R-N13; user authorized stronger fan/background restoration and comparative compression/clarity candidates on 2026-10-05. This lane owns `scripts/media.py`, `tests/test_media.py`, three new captured profiles and this specification. Existing bypass, conservative3 and mild6 profiles remain frozen. Root owns actual source listening, interval selection, renders and publication.

## Plan and definition of done

1. Validate a short operator-selected opening noise interval against the original source SHA-256. Selection denotes supplied review, not an automatic guarantee that guitar or metronome is absent. Reject mismatched hashes, invalid numeric controls and intervals outside the decoded recording.
2. Add captured8 and captured12 denoise candidates with disabled ongoing noise tracking. Keep calibrated afftdn insertion-delay compensation and native sample rate, channels and extent.
3. Add an optional captured8-clarity candidate: bounded peaking EQ followed by moderate RMS compression before the existing measured loudness normalization. Preserve pure denoise and source-minus-denoise artifacts; write a separate processed pre-gain artifact when these stages are present.
4. Verify each stage independently with source-bound negative controls, high amplitude transients, 32 Hz sustain, attack/tail support, stereo and 44.1/48 kHz fixtures. Do not infer whole-chain acoustic alignment from an impulse whose amplitude compression intentionally changes.
5. Report exact controls, source/capture lineage, stage order and timing limitations. Root renders new immutable comparison runs and evaluates quieter background, pick attack, legato/sustain and residue before selecting a listening candidate. Synthetic evidence is not real-recording acceptance.

## Primary evidence and choices

[FFmpeg afftdn](https://ffmpeg.org/ffmpeg-filters.html#afftdn) supports explicit noise-sampling commands. The worker now trains with a copied source interval before the original body, inserts a100ms silence guard around frame-quantized stop delivery, then removes this preroll and the independently calibrated denoiser delay. Native-rate tail padding precedes filtering; exact source sample extent is checked after trimming. This applies the captured shape from original sample zero.

[FFmpeg acompressor](https://ffmpeg.org/ffmpeg-filters.html#acompressor) provides linked RMS gain control. The proposed candidate uses2:1,15ms attack,100ms release, -18dB threshold and3dB knee with no makeup gain. A fixed25% wet/75% dry blend bounds this stage's sample-amplitude reduction to2.50dB, rather than promising that a ratio alone limits reduction. Numeric dB controls become linear FFmpeg values; maximum-channel linking retains channel relationships. These remain experimental comparison settings.

[FFmpeg equalizer](https://ffmpeg.org/ffmpeg-filters.html#equalizer) provides the peaking filters. Broad300Hz -1.5dB and2200Hz +1dB, Q0.8, are comparison settings, not recovered microphone/amp response. Forward IIR phase varies with frequency; a single acoustic-delay scalar cannot establish all-frequency alignment. Reverse-IIR block processing is disabled.

[FFmpeg's afftdn implementation](https://ffmpeg.org/doxygen/trunk/af__afftdn_8c_source.html) centers/clips captured15-band shape values while retaining the separately specified absolute floor. The worker therefore records that absolute floor as an explicit candidate control. Publication requires one observed `bn=` update containing15 finite values per source channel; its values and source/sample selection are retained in the manifest. A sampled shape does not prove fan identity or absence of guitar/click contamination.

## Closed controls and artifact contract

The existing `clean INPUT PROFILE` interface is retained. Unknown profile keys, filter strings, boolean numeric values and nonfinite/out-of-range controls are rejected. Noise capture requires a lowercase64-character original SHA-256 and authorized0.1–10sec sample interval. Optional adaptivity0–1 is numeric. Optional peaking EQ allows up to three160–6000Hz bands, each±3dB and Q0.5–2; source Nyquist is checked. Compressor limits are threshold -36..-6dB, ratio1..3, attack8..20ms, release60..200ms and knee0..6dB. No arbitrary filters, makeup boost, lookahead or channel remix is exposed.

`denoised.wav` and `residue.wav` remain pure pre-gain denoise and source-minus-denoise. Optional `processed.wav` contains serial EQ then compression; `cleaned.wav` normalizes that artifact when present. Every WAV is hash-bound and native extent verified. Manifest additions are `noise_capture`, `restoration_stages`, and `dsp_latency.post_denoise`; source/media export fields remain compatible.

## Fixture claim boundaries

Independent44.1kHz mono and48kHz stereo generated fan/C1/harmonic/pick fixtures exercise nr8/nr12 with instant adaptation and zero gain smoothing. Explicit proposed budgets are at least3dB lower opening noise, at least90% coherent32Hz amplitude, at most1.5dB5ms pick-burst peak loss and3dB leading-sample loss. These budgets do not establish fidelity of a real recorded attack. Single-sample delta impulses can lose substantially more amplitude; a negative control keeps that damage visible. Separate forward-stage tests exercise causal support, high peaks, channel relation, extent and tails. The completed real-recording timing calibration remains unchanged and does not certify EQ phase or compression envelope fidelity.

No high-pass, mains notch, gating, declipping, metronome removal, model download or tempo correction is added. Fundamentals near 32 Hz, intentional distortion, pick attacks and tails remain review targets. Stronger denoising can remove guitar energy and compression can increase relative background audibility after normalization.

## Status

Worker implemented and18/18 media tests passed with actual FFmpeg8.1.2. Three new profiles are bound to original SHA-256 `a522115f4e72e19384fb341bc84369728eceefe49183b8c6367a1008a95176c6`, selected decoded-audio interval4.10–4.95sec and explicit -40dB floor. Root reviewed the interval under user-authorized capture; it is not an operator-exact selection. Lowest nearby quarter-second RMS was about -35.8dBFS; nearby click-like candidates3.8075/5.2375sec were outside the interval. A4.3sec frame was viewed. Sustained guitar/music absence remains uncertain and the worker does not certify noise-only audio. Captured8/captured12 use ad0/gs0; captured8-clarity adds the stated serial comparison stages. Root owns actual renders and measurements and may compare a separately recorded -35dB absolute-floor candidate if -40dB remains weak. No real take listening or stronger-restoration acceptance is claimed here. Existing actual-recording calibration pilot remains frozen and does not certify these new stages.
