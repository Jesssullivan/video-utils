# Preregistered optional PCEN frontend experiment

Owner `/root/xod_spectrogram`; root integrates. Written before this secondary
experiment on October 5, 2026. Authority R-HOOK-CONVERGENCE-20261004, TIN-3692
comment `98cf680c-7299-4949-bfb2-60079053ad43`. Original XOD golden proof and
production frontend remain frozen. This is feature research, not a new tool.

## Fixed design

Use three fresh generated holdout cases: seed 211 low32-sustain and
palm-muted-recurrence; seed 307 legato-recurrence. Analyze only [0,4] seconds of
clean and mixed conditions, at most 24 aggregate audio-seconds. Select by
preregistered articulation categories, without inspecting onset/phrase labels.
Bind admitted indices and WAV hashes; do not pass seed, category, BPM, intended
events or score to feature computation. Labels remain unused in this proof.

For each input resample to 16 kHz, periodic Hann, 80-sample/5 ms hop, centered
frames, 128 Slaney mel bands, 20–8000 Hz. Compare independently at 1024 FFT/64 ms
attack-window support and 4096 FFT/256 ms low-register support. The latter's
3.90625 Hz bin spacing improves spectral sampling, not proven C1 semitone
resolution or timing accuracy. It cannot alone grade 84.27 ms subdivisions.

Freeze these four compression candidates before execution:

| ID | Mel representation | Input scale | Gain | Time constant |
|---|---|---:|---:|---:|
| power-default | Power | 2**31 | 0.98 | 0.4 s |
| magnitude-default | Magnitude | 2**31 | 0.98 | 0.4 s |
| magnitude-unit-gain05 | Magnitude | 1 | 0.5 | 0.4 s |
| magnitude-unit-gain05-slow | Magnitude | 1 | 0.5 | 1.0 s |

All use bias 2, compression exponent 0.5, epsilon 1e-6, frequency max-size 1.
Power and magnitude each have a corresponding log baseline from the identical
mel matrix. Compare compression within each window/representation first;
window differences and scaling differences are separately identified factors.
These knobs are engineering candidates, not learned parameters or a recommendation.

## Units and state

The original paper's default conditioning is tied to input scale; librosa 0.11
illustrates magnitude mel times 2**31. XOD's Ruby reference uses unit-sum HTK
mel **normalized power**, also times 2**31. They do not establish equivalent
absolute units. Our current Slaney power mel is another convention. Use explicit
matrix kind/normalization/scale rather than silently transferring defaults.
[librosa PCEN](https://librosa.org/doc/0.11.0/generated/librosa.pcen.html),
[original paper](https://getreuer.info/papers/wang2017trainable/index.html).

Smoothing coefficient is computed from time constant in seconds, sample rate
and actual frame hop; 0.4 s means 80 hops here, not XOD's 40. Initialize the
IIR at the first frame's steady state and carry returned state across blocks.
The pinned librosa implementation's default `zi` is the unit-step steady-state
filter value, not that value multiplied by each channel's first observed energy.
Pass explicit `zi=(1-b)*E[:,0:1]` so `M[0]=E[0]`, matching the preregistered XOD
first-frame policy; retain the default-state distinction in interpretation.
Test full/block parity; record first-frame initialization and retain the first
one second as startup-sensitive. Centered STFT remains offline: feature center
time and complete support differ, including padding at excerpt edges.

## Measurements, budget and acceptance

Record finite output, frame geometry, exact source/worker/settings hashes,
low-band spectral coverage, PCEN batch/block maximum difference, and clean/mix
spectral-flux cosine for the whole excerpt and after one-second warm-up.
Cosine compares generated feature invariance; it cannot grade onsets, notes,
musical phrases or timing correctness. There is no score-based parameter tuning.

One worker, two numeric threads, 90-second timeout, existing locked Python;
no rendering, model dependency, private-code vendoring, latest-pointer update,
production default change or package admission. If holdout admission is not
frozen, leave the plan ready and do not substitute unadmitted inputs.

Coordinate with phrase-window experiments: their separate seed/window controls
must not attribute a shortest-window or half-time hypothesis fix to this
frontend. A subsequent full-corpus labelled evaluation remains a distinct run
with prespecified matching tolerances, sparse actual-guitar review and separate
holdout acceptance. Tonight's marked video does not depend on this experiment.
