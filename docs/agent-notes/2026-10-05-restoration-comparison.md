# Actual restoration comparison — October 5, 2026

Authority: operator restoration/implementation/ten-hour goal instructions; R-HOOK-CONVERGENCE-20261004/R-N13. Root owns this receipt and its evidence snapshots. This continues the active goal, not a listening acceptance.

Root ran the existing `media.py clean` tool twice with explicit FFmpeg/FFprobe8.1.2: `bypass` and `mild6`. The published conservative3 run stays unchanged. Existing report generation succeeds for both new runs; their analysis is explicitly unavailable, without copied rhythm/phrase results. No video re-encoding or latest-pointer update occurs.

| Profile | Run | Master LUFS / dBTP | 20–45Hz mixture power change before normalization | Candidate 4–5s /149–150s RMS change |
| --- | --- | ---: | ---: | ---: |
| bypass | `20261005T224706Z-2a72efe386ab` | -18.01 /-1.50 | 0.00000dB | 0.000 /0.000dB |
| conservative3 | `20261005T211103Z-c6d0bac2fcd2` | -18.01 /-1.50 | -0.02542dB | -0.368 /-0.542dB |
| mild6 | `20261005T224733Z-0e920a701cf8` | -18.00 /-1.50 | -0.02785dB | -0.490 /-0.709dB |

All candidates retain44.1kHz mono/6,657,385samples and original media hash `a522115f4e72e19384fb341bc84369728eceefe49183b8c6367a1008a95176c6`. Source/denoised/baseline/cleaned/residue hashes are checked before and after analysis. Bypass has identical source/denoised hashes and identical baseline/cleaned hashes. All masters measure−1.50dBTP; integrated levels differ by0.01LU. This is integrated-level matching, not proof of identical instantaneous gain; FFmpeg reports dynamic normalization despite the requested linear mode.

Whole-take Welch PSD uses Hann65536, overlap32768 and mean averaging at native44.1kHz, comparing sums of selected frequency-bin densities in20–45,45–120,120–500,500–2000,2000–8000,8000–20000Hz. Measurements use denoised working PCM before presentation gain. No fitted delay or gain is introduced. The previously calibrated denoiser compensation remains the producer method. Quiet candidates4–5/149–150s are not confirmed noise-only, so these RMS changes do not establish SNR. Low-band mixture power is not identified C1/fundamental preservation or listening quality.

At these two windows,6dB reduction adds only about0.12/0.17dB RMS reduction compared with3dB. All candidates remain available; the conservative exported iteration is retained. No best-tone or noise-free claim, automatic click attenuation, reference grading, capture-sync acceptance or corpus annotation is created.

Immutable evidence: [numeric receipt](evidence/2026-10-05-profile-comparison.json) and [exact investigative worker snapshot](evidence/2026-10-05-profile-comparison.py). Worker is an offline analysis receipt, not a new registered DSP primitive; reproduce existing restores with `just clean INPUT bypass`/`just clean INPUT mild6` and use the locked optional environment for the archived spectral calculation. Media/report artifacts stay local and ignored.

Listening locations:
- `/Users/jess/git/video-utils/artifacts/runs/20261005T224706Z-2a72efe386ab/cleaned.wav` and `report.html`.
- `/Users/jess/git/video-utils/artifacts/runs/20261005T211103Z-c6d0bac2fcd2/cleaned.wav` and `report.html`.
- `/Users/jess/git/video-utils/artifacts/runs/20261005T224733Z-0e920a701cf8/cleaned.wav` and `report.html`.

Actual published video remains `artifacts/runs/20261005T211103Z-c6d0bac2fcd2/export/cleaned-video.mov`.
