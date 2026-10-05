# Guitar tone references and box-fan restoration

Research checked October 5, 2026. The six artist references and large box fan are
**operator-stated project constants**, also recorded in
[`program/capture-context.json`](../../program/capture-context.json). They guide
articulation and listening priorities; they do not identify this recording's
amplifier, pickup, cabinet, played notes or intended score.

The demo is the approximately 150.954-second mono, 44.1 kHz AAC room recording
already probed by this project. This research lane did not listen to or process
the recording. Studio/full-band recordings include other instruments, layers,
microphones and mastering; their spectra are not isolated-guitar EQ targets.

## Primary evidence and transferable priorities

The final column is our proposed application to this capture, not an artist's
prescribed restoration setting. Historical interviews establish their dated
context, not a verified current rig. Manufacturer endorsements are subjective
artist statements or product claims, not independent DSP measurements.

| Reference/context | Primary source and date | Established fact | Proposed audibility priority and limit |
| --- | --- | --- | --- |
| Lorna Shore: deathcore saturation and separation | [Fishman: Andrew O'Connor](https://fishman.com/artist/andrew-oconnor/), undated, accessed 2026-10-05 | O'Connor explicitly values saturation together with clarity and string separation. | Keep distortion texture while exposing successive attacks and simultaneous strings. The pickup endorsement does not establish this take's gear or a spectral target. |
| The Haunted: aggressive melodic-death rhythm | [URM interview with Ola Englund](https://urm.academy/ep17-guitar-month-15-kickoff-w-ola-englund/), 2016-07-01; sections 33:56, 51:07 and 57:50 | Englund discusses a simple home-recording workflow, one-microphone cabinet capture and different roles for real amps and simulations. | Preserve the performance's attack/body relationship. A cabinet microphone and a room camera capture are different inputs; copying a cabinet recipe cannot recover the latter's original amp signal. |
| Meshuggah: low-register definition and rhythmic weight | [Ibanez M80M specifications](https://www.ibanez.com/asia/products/detail/m80m_1p_04.html), undated, accessed 2026-10-05 | The signature eight-string has a 747 mm scale; factory tuning is highest-to-lowest D# A# F# C# G# D# A# F. Ibanez describes high-gain definition and low-note tightness. | Retain low-note weight and mute/attack contrast. This factory setup is not the operator's nine-string tuning or proof of any album's actual settings. Rhythmic emphasis here is a project interpretation. |
| Kublai Khan TX: direct, sparse impact | [Band statement reproduced by Knotfest](https://knotfest.com/blogs/news/kublai-khan-tx-announce-new-album-exhibition-of-prowess), 2024-08-09; [ESP Nolan Ashley interview page](https://www.espguitars.com/videos/2037858), 2020-01-18 | The band's statement describes the opening single through simplicity and directness. ESP establishes a dated guitarist interview; its embedded video was not transcribed in this lane. | Check palm-mute impact, deliberately empty spaces and separation between attacks. Exact tuning, amp settings and gate settings remain unverified; do not invent a hardcore preset. |
| Mgła: abrasive, dry clarity | [Bardo Methodology interview with M](https://www.bardomethodology.com/articles/2021/11/24/mgla-age-of-excuse-interview/), 2021-11-24 | M describes rehearsal-space tracking, home editing/mixing, a colder abrasive but clear result, little artificial space and separately recorded instruments. He emphasizes source performance/timbre. | Preserve intentional abrasive texture and continuous picking while reducing unrelated fan noise. Avoid treating all high-frequency energy as unwanted fizz or adding artificial room/widening to imitate a full mix. |
| Children of Bodom: melodic-death lead articulation | [Premier Guitar interview with Alexi Laiho](https://www.premierguitar.com/artists/interview-children-of-bodoms-alexi-laiho-fast-and-slow?page=1), 2013-05-15 | Laiho discusses legato, alternate and sweep picking; for *Halo of Blood* he chose a Marshall JVM for more low end while retaining his preferred midrange. | Preserve quiet connected notes, sweep transitions, tapping and lead sustain as well as rhythm weight. Amp control positions cannot be converted into a room-recording EQ curve. |

These references support complementary priorities: saturated separation,
percussive low-register definition, abrasive continuous texture and connected
melodic articulation. They do not justify a universal mid scoop, high-pass,
noise gate, compressor or loudness target.

## Fan mechanisms and the low tuning

Fan noise can contain broadband turbulence and rotating tonal components.
LONGWELL's manufacturer engineering reference gives rotation frequency as
RPM/60 and blade-pass frequency as blade count × RPM/60, with harmonics; its
page also distinguishes broadband turbulence. These are conditional mechanisms,
not identified frequencies of this box fan. Its speed, blade count, motor type,
position and room response have not been established. No mains-frequency or
blade-frequency notch follows from knowing that a fan was present.
[LONGWELL fan-frequency reference, updated 2026-08-23](https://www.longwellfans.com/resources/blade-pass-frequency-calculator/).

The supplied low-to-high pitch classes are C F Bb Eb Bb Eb Ab C F. In
[`program/instrument.json`](../../program/instrument.json), inferred octaves
and A4=440 equal temperament give C1 ≈ 32.703 Hz, Bb1 ≈ 58.270 Hz and Ab3 ≈
207.652 Hz. These are computed open-string references, not measured notes.
Broadband fan reduction can overlap these fundamentals, their harmonics and
distorted attacks; a notch near 60 Hz could also damage Bb1. Whether any specific
fan line overlaps them requires this take's measurements.
[UNSW note/MIDI/frequency equations](https://phys.unsw.edu.au/jw/notes.html).

## Current evidence and next comparison

The root restoration lane reports the following quiet-window RMS reductions
relative to its source baseline. This research lane did not independently rerun
them. They are total window-energy changes, not isolated fan SNR measurements.

| Candidate | 4–5 s window | 149–150 s window | Interpretation |
| --- | ---: | ---: | --- |
| Existing fixed 3 dB reduction | 0.37 dB lower | 0.54 dB lower | Operator reports cleanup too mild. |
| Existing fixed 6 dB reduction | Only another 0.12 dB lower | Only another 0.17 dB lower | Increasing the knob alone did little with that assumed noise floor. |

Fixed `nr` is a filter control, not a guarantee of achieved background reduction.
The next authorized implementation comparison is **captured-profile 8 dB and
12 dB candidates**, applied to the complete take, with pure denoising separate
from optional EQ/compression. These are bounded project experiments, not
artist-derived settings or accepted masters. The implementation lane's
[`RESTORATION_REFINEMENT_LANE.md`](../spec/RESTORATION_REFINEMENT_LANE.md)
owns exact contracts and execution.

The implemented refinement copies the selected source interval into private
sampling preroll and applies the learned band shape to the complete take,
including sample zero. It removes the preroll, silence guard and calibrated
denoiser delay before publishing native-length audio. The absolute noise floor
remains an explicit candidate control; captured shape does not establish an
absolute noise floor or a noise-only interval.

FFmpeg `afftdn` supports starting/stopping noise sampling, noise-only output,
optional noise-floor tracking and frequency-bin gain smoothing. Tracking is off
by default; smoothing can reduce musical-noise artifacts. Sampling an interval
containing guitar or clicks would contaminate the profile. Its documentation's
first-0.4-second example is not evidence that this source's first 0.4 seconds
are suitable. [Official FFmpeg afftdn documentation, accessed 2026-10-05](https://ffmpeg.org/ffmpeg-filters.html#afftdn).

| Bounded knob/comparison | Purpose | Preservation risk/check |
| --- | --- | --- |
| Reviewed opening noise capture; compare later quiet candidates | Bind the profile and interval to the current source hash. Check for residual notes, clicks, handling and changing fan level before capture. | A quiet interval is only a candidate until reviewed. Reject contaminated captures; record the selected interval and measured spectrum. |
| Captured `nr=8` versus `nr=12`; tracking initially disabled | Seek meaningful background reduction with the measured profile rather than an arbitrary fixed floor. | Inspect the noise residue for pitched notes/attacks and the output for watery/swirling artifacts, lost low weight or clipped note tails. Do not adopt the stronger version from RMS alone. |
| Gain smoothing 0 versus 3, only if artifacts remain | One bounded follow-up comparison, holding other controls fixed. | Extra smoothing may blur spectral detail; preserve dense pick attacks and legato. These values are experiment settings, not proven optima. |
| Optional broad EQ changes no larger than 1–2 dB | Address a measured/listened masking region after denoising. Record frequency, bandwidth and gain separately. | No blanket 80 Hz high-pass or presumed hum notch. Do not boost an absent fundamental or carve intentional distortion on the strength of a band name. |
| Optional moderate compression, aiming for 1–3 dB actual gain reduction | Compare stability of rhythm/lead level without changing the denoising verdict. Pilot attack 10–30 ms and release 80–150 ms; set threshold from this signal. | These are proposed starting ranges, not measured best settings. Already saturated guitar may need little compression. Check softened attacks, exaggerated fan tails and pumping during rests. |

Process whole-take variants with recorded latency/timeline correction, then
select identical source-timed excerpts for comparison: low-string mutes,
repeated fast attacks, quiet connected notes, and the operator-described end
sweep/tapping passage. Independently denoising isolated snippets changes filter
initialization and profile application; it is not equivalent to reviewing the
full rendered candidate. Keep original channels/rate and source media intact.

## Measurable review targets

These targets define what to report and flag. They are proposed review budgets,
not proof that a variant already sounds better or a replacement for listening.

| Target | Measurement/review | Failure or ambiguity to retain |
| --- | --- | --- |
| Audible fan reduction | Source-aligned RMS and power-spectrum change in every reviewed quiet interval, before final loudness makeup; trial goal 3–6 dB lower quiet-window RMS if achievable without damage. | Total RMS includes all sounds. Profile contamination or a changed fan invalidates a simple fan-only interpretation; a requested 12 dB setting need not deliver 12 dB RMS reduction. |
| C1 weight and related low notes | Compare loudness-matched sustained/muted-note spectra around theoretical fundamentals and harmonics; report 25–45 Hz and 55–70 Hz energy changes alongside noise-window changes. Flag losses above about 1 dB for review. | Band energy combines guitar and fan, so reduction is not proof of lost guitar. A microphone may not have captured much C1; EQ cannot recover missing information. |
| Pick/mute attack readability | Aligned audio envelopes, attack-to-body contrast, mute decay and identical timestamped listening excerpts. Report detector changes separately from audible changes. | Compensate DSP latency before interpreting shifts. Video frame rounding and changed denoising can alter onset detection; neither proves a rushed beat. |
| Continuous picking and abrasive texture | Compare short-time spectral/envelope continuity and inspect for modulation introduced by denoising. | Harmonic distortion and repeated picking are intentional; removing them to lower noise is a failed tradeoff. |
| Sweep/tapping/legato sustain | Compare selected decay envelopes and noise-only residue through connected notes and final tails. | Clearly pitched or recognizable guitar in the removed residue is a preservation warning even if quiet-window RMS improves. Avoid a gate default. |
| Fair tone/dynamics audition | Match excerpt presentation level within approximately 0.2 dB, retain unclipped peaks and label the pure-denoise and EQ/compression paths. | Louder playback can dominate preference. Quiet-window reduction measured after arbitrary makeup gain is not comparable to the pre-makeup result. |

The next-week restoration work should turn these checks into source-bound
reports and operator listening annotations within the already allocated
restoration/benchmark hours. Add no new model or artist-audio dependency for
this comparison. Library alternatives and speech-denoiser limitations remain
in the existing [FOSS audio matrix](FOSS_AUDIO_MATRIX.md). Listening acceptance,
musical correctness and Logic/AU host acceptance remain separate evidence.
