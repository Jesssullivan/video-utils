# Independent captured-restoration comparison

Plan recorded before worker execution. Authority: root's delegated independent
measurement lane under the operator's stronger restoration authorization;
R-HOOK-CONVERGENCE-20261004 R-N12/R-N13. Owner: `clip_baseline`. Writes are limited
to this receipt, its dated evidence JSON/worker, and ignored local worker artifacts.

Compare the frozen conservative3 run with root's captured8, captured12 and
captured8-clarity runs. Verify original/artifact hashes, decoded rates/channels
and sample counts, source-minus-denoise residue, captured8/clarity denoise
identity, whole-take Welch bands including 20–45 Hz, quiet-window RMS, stage
differences, master loudness/peak and descriptive dynamics. Use the existing
`.venv`, at most two numeric/FFmpeg threads, and existing FFmpeg. Record source
selection, analysis settings and artifact identity in reproducible evidence.

Noise-window energy is not fan-only SNR. Full-take spectral summaries do not
establish low-note or pick preservation. No automatic best-tone, musical
correctness, physical A/V sync or listening acceptance claim. Do not write
root files, old runs, latest pointers, models or the environment.

## Inputs and verification

Root completed all three new receipts before the worker consumed them:
`artifacts/root-captured8-render.json`, `artifacts/root-captured12-render.json`,
and `artifacts/root-captured8-clarity-render.json`. Run IDs are
`20261005T232627Z-eb7bead2ae74`, `20261005T232714Z-04afdec97f2b`, and
`20261005T232741Z-2b5dc43fd009`; old conservative3 is
`20261005T211103Z-c6d0bac2fcd2`.

The original source SHA-256 is
`a522115f4e72e19384fb341bc84369728eceefe49183b8c6367a1008a95176c6`.
The worker rehashed it before and after analysis; it remained unchanged. Every
manifest-listed WAV hash matched. All stages are mono, 44,100 Hz, exactly
6,657,385 decoded sample frames (150.961111 seconds). This decoded extent is
about 7.05 ms longer than the container's 150.954059-second audio metadata;
preservation is checked against decoded samples, not a rounded metadata duration.
Every candidate's source WAV is byte-identical. Captured8 and clarity denoised
WAVs are byte-identical, as are their pure-denoise residues. Across all four
runs, `source - denoised - residue` has maximum absolute full-scale error no
larger than 1.863e-9, consistent with float32 subtraction rounding. This checks
residue arithmetic, not whether it contains only noise.

Selected capture is 4.10–4.95 seconds with source-hash binding. Root reviewed
nearby RMS, click candidates outside the interval and a 4.3-second video frame;
the absence of guitar sustain remains uncertain. Noise-floor control remains
the explicit −40 dB candidate. New capture runs prepend the selected noise and
a silence guard internally, learn the profile, then discard preroll and
calibrated 1,102-sample filter delay. The measured profile therefore applies
from original sample zero. This supersedes the earlier research/design caveat
about capture occurring midway through the published take. The worker checks
artifact identity/extent; it does not establish complete acoustic A/V sync.

## Independent measurements

Values below are native-level `denoised.wav` minus `source.wav` window RMS in
dB, before loudness makeup. Negative means lower total window energy. The
clarity branch has exactly the captured8 denoise values because it applies
EQ/compression afterward.

| Candidate | 0–1 s | 4–5 s | Capture 4.1–4.95 s | 149–150 s |
| --- | ---: | ---: | ---: | ---: |
| conservative3 | −0.037 | −0.368 | −0.391 | −0.542 |
| captured8 | −0.556 | −4.445 | −4.563 | −3.100 |
| captured12 | −0.573 | −5.433 | −5.601 | −3.641 |

Captured12 adds approximately 0.99 dB reduction in the 4–5-second window and
0.54 dB in the final window compared with captured8. Opening-window reduction
remains modest. These results corroborate root's reported captured8 figures;
they are not fan-only SNR or a claim that every passage improved.

Whole-take band-power differences use native-rate Hann Welch PSD, 65,536-sample
windows, 32,768 overlap and no detrending; bin spacing is approximately 0.673 Hz.
Integrate PSD × bin spacing over lower-inclusive, upper-exclusive frequency
bands. These are mixture changes, not isolated-note attenuation measurements.

| Pure-denoise candidate | 20–45 Hz | 55–70 Hz | 190–225 Hz | 250–2000 Hz | 2–10 kHz | 10 kHz–Nyquist |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| conservative3 | −0.025 | −0.007 | −0.000 | −0.044 | −0.422 | −2.622 |
| captured8 | −2.320 | −0.772 | −0.278 | −0.325 | −0.108 | −0.245 |
| captured12 | −2.437 | −0.808 | −0.284 | −0.335 | −0.109 | −0.257 |

The 20–45 Hz reduction needs low-string/residue listening review. It may remove
fan energy, musical content or both; the measurement cannot identify the split.
The old preset removes substantially more highest-band energy despite weaker
quiet-window reduction, so reduction strength alone does not describe its
spectral behavior. Multiple controls differ between old/new runs: captured
shape, adaptivity and gain smoothing as well as reduction. This comparison
does not isolate one knob's causal contribution.

Root requested six bounded local comparisons after the whole-take result.
Use a separate 16,384-sample Hann / 8,192-overlap Welch and magnitude-squared
coherence estimate (2.692 Hz bins), allowing four overlapped segments in each
one-second quiet candidate and 52 in each ten-second active candidate. The
following coherence is weighted by source PSD within each band; unweighted
means and absolute powers are also in the [segment evidence](2026-10-05-captured-restoration-segments.json).

| Candidate / interval seconds | 20–45 Hz Δ dB | 20–45 Hz coherence | 45–120 Hz Δ dB | 45–120 Hz coherence |
| --- | ---: | ---: | ---: | ---: |
| captured8 / 10–20 | −2.759 | 0.9493 | −0.196 | 0.9988 |
| captured8 / 40–50 | −2.040 | 0.9499 | −0.108 | 0.9987 |
| captured8 / 90–100 | −2.063 | 0.9576 | −0.121 | 0.9985 |
| captured8 / 130–140 | −2.404 | 0.9501 | −0.086 | 0.9994 |
| captured12 / 10–20 | −2.925 | 0.9258 | −0.199 | 0.9986 |
| captured12 / 40–50 | −2.134 | 0.9325 | −0.111 | 0.9984 |
| captured12 / 90–100 | −2.147 | 0.9426 | −0.124 | 0.9982 |
| captured12 / 130–140 | −2.530 | 0.9307 | −0.087 | 0.9993 |
| captured8 / 4–5 | −7.220 | 0.9339 | −6.820 | 0.9869 |
| captured8 / 149–150 | −6.986 | 0.9889 | −5.072 | 0.9854 |
| captured12 / 4–5 | −9.708 | 0.7715 | −9.366 | 0.9564 |
| captured12 / 149–150 | −9.755 | 0.9599 | −6.398 | 0.9631 |

Active/quiet classifications are amplitude/context inferences: active candidates
have total source RMS approximately −22.24 to −20.16 dBFS, quiet candidates
−35.13/−34.30 dBFS. They do not isolate C1 notes or prove fan-only gaps. The
active 20–45 Hz changes remain material review findings even with high coherence.
Coherence can remain high for attenuated signals and correlated noise; it is
not a gain-preservation, phase-alignment or musical-quality score. Quiet-window
coherence is especially limited by four averages. No universal low-frequency
preservation claim is supported. Conservative3 and clarity values are retained
in JSON; clarity's pure-denoise segment measurements equal captured8 exactly.

All mastered WAVs were independently measured with FFmpeg 8.1.2 `loudnorm`.
Use measurement **input** integrated loudness/peak/LRA, rather than the filter's
simulated second normalization output.

| Master | Integrated LUFS | True peak dBTP | LRA LU | Sample crest dB |
| --- | ---: | ---: | ---: | ---: |
| conservative3 | −18.01 | −1.50 | 3.9 | 16.228 |
| captured8 | −18.01 | −1.50 | 4.1 | 16.336 |
| captured12 | −18.01 | −1.50 | 4.1 | 16.340 |
| captured8-clarity | −18.00 | −1.75 | 3.4 | 16.349 |

The source measures −21.24 LUFS, −4.16 dBTP and 4.0 LU LRA. Clarity's separate
pre-normalization `processed.wav` measures −21.95 LUFS, −5.70 dBTP and 3.3 LU
LRA. Compared with its identical captured8 denoise input, the combined
EQ/compression stage lowers whole-take RMS by 0.800 dB and crest by 0.770 dB.
These combined changes do not isolate compressor gain reduction or prove
clearer attacks. Its pre-gain 2–10 kHz band is 0.598 dB higher than captured8's,
while 250–2000 Hz is 1.270 dB lower; EQ and compression both contribute.

## Audition implications and limits

Master quiet-window levels are also affected by loudness normalization. Against
the old −18.01 LUFS master, new master differences are:

| Master | 0–1 s | 4–5 s | 149–150 s |
| --- | ---: | ---: | ---: |
| captured8 | −0.056 dB | −4.186 dB | −2.549 dB |
| captured12 | −0.049 dB | −5.299 dB | −3.086 dB |
| captured8-clarity | −4.855 dB | −9.956 dB | −1.090 dB |

Clarity's stronger mastered opening/quiet-window difference is **not stronger
denoising**: its denoise/residue bytes equal captured8. Post-processing and the
normalization path change relative levels. The receipt's normalization render
mode is dynamic for old/captured8/captured12 and linear for clarity; exact
receipts and independent levels remain in JSON. Equal whole-take LUFS does not
guarantee equal passage gain, noise floors or dynamics.

For the next audition, compare captured12 against captured8 for extra quiet
reduction versus low-note/tail artifacts, then captured8 against clarity for
tone/dynamics preference. Listen to whole-render excerpts with the same source
timestamps, including the end sweep/tapping and low palm mutes. Inspect pure
residue as well as masters; preserve uncertainty about capture contamination.
No winner, pick/legato preservation, intended-note correctness, real listening
acceptance or repaired physical A/V synchronization follows from these checks.
Root selected clarity as the main audition and captured12 as the alternate;
this is an audition selection, not accepted best tone.

## Reproduction and receipt

The dated [worker](2026-10-05-captured-restoration-comparison.py) and
[exact evidence JSON](2026-10-05-captured-restoration-comparison.json) are durable
copies of the ignored worker/evidence. Run from the repository root, selecting
a new output path to preserve existing evidence:

```sh
.venv/bin/python docs/agent-notes/2026-10-05-captured-restoration-comparison.py \
  --ffmpeg /nix/store/mv3x2v2pr6pwvwj7cdyh8nci2q1wpnjq-ffmpeg-headless-8.1.2-bin/bin/ffmpeg \
  --output artifacts/worker-captured-restoration-repeat.json
```

The additional [segment worker](2026-10-05-captured-restoration-segments.py)
imports the dated main worker's read/hash helpers. Reproduce with a new path:

```sh
.venv/bin/python docs/agent-notes/2026-10-05-captured-restoration-segments.py \
  --comparison docs/agent-notes/2026-10-05-captured-restoration-comparison.json \
  --output artifacts/worker-captured-restoration-segments-repeat.json
```

Only the evidence output is written. FFmpeg loudness measurement emits no media
derivatives. The evidence records exact input receipt/artifact hashes, worker
hash, versions, controls, thread bounds and commands. An initial worker attempt
found the manifest hash keys were WAV filenames rather than logical roles;
corrected before measurement. The final run includes master-to-baseline and
master-to-old comparisons and completed all assertions. No packages, models,
root files, old runs or latest pointers were changed.

Process receipt: actor clip_baseline | target delegated immutable actual-run
comparison | reason stronger fan-restoration evidence for operator audition |
ruling R-HOOK-CONVERGENCE-20261004 R-N12/R-N13 | prior_state root-rendered,
unreviewed candidates | result independent hash/extent/residue/spectral/level
evidence; musical preservation and listening preference unresolved.
