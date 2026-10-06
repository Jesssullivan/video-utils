# Secondary PCEN frontend ablation checkpoint

Actor `/root/xod_spectrogram`; authority R-HOOK-CONVERGENCE-20261004,
TIN-3692 comment `98cf680c-7299-4949-bfb2-60079053ad43`, R-N12/R-N13.
The operator requested additional full-force parallel work; root assigned a
new optional frontend design and bounded secondary proof. The original XOD
golden proof remains frozen.

Preregistration: [`PCEN_FRONTEND_ABLATION_LANE.md`](../spec/PCEN_FRONTEND_ABLATION_LANE.md),
SHA `1a71efe081ba6867a82fb2e2e9975148f5178af3ea630ad21bc4b4824670f3e3`.
The fixed four-policy/dual-window design was written before any secondary
feature experiment. Seeds/categories and [0,4]-second crop were fixed then;
24 aggregate audio-seconds across three clean/mix pairs. No parameter search,
label scoring, phrase-window change or production admission is authorized by
this receipt.

The metadata-only holdout plan was inspected after freezing knobs; it exposes
construction parameters. The investigation is fixed-knob computation, not an
assertion that the researcher never saw construction metadata. No generated
truth file or labelled detector score has been read for this secondary lane.

## Source/state finding

Pinned `librosa.pcen` 0.11.0 computes default `zi` using `lfilter_zi` for a unit
step. It does not multiply that value by each band's first observed energy.
XOD initializes its smoother to the first energy frame. Explicit
`zi=(1-b)*E[:,0:1]` implements the preregistered `M[0]=E[0]` policy in librosa;
carry returned `zf` across blocks. Record scale, representation and state
conventions independently.

A tiny, non-audio two-band/four-frame numeric check verified explicit first-frame
output against the analytic formula, maximum difference
`1.6653345369377348e-16`. Default versus explicitly conditioned first-frame
PCEN differed by up to `0.2795687390299488` in that constructed check. Those
values establish a state distinction, not guitar detection quality.

## Current checkpoint

Owned ignored worker `artifacts/experiments/pcen-frontends/feature_proof.py`,
SHA `a87586af40aab7aa22e983efbd5a35acdd9f149197cd9861ff33ee57e1e67117`,
has syntax verification and prepares paired log/PCEN features, block parity,
geometry, low-band centers/window-cycle coverage, whole/warm-up cosine and
input-hash checks. Both metrics retain final centered edge padding; the whole
metric also retains initial padding. It does not load labels.
Its fixed settings and source belong only to this investigation; it is not a
catalog tool. Numerical execution is pending frozen holdout admission/index
from root and the generator owner. No holdout waveform proof has run yet.

No dependency installation, ML environment use, private package vendoring,
current frontend edit, latest-pointer update, media rendering or marker change.
Coordinate with `/root/phrase_dag` so optional frontend and pulse/window
factors remain separate. Root owns tracker/publication updates. Append an exact
admission/index/result checkpoint after a run; do not turn the pending state
into a passing detector or phrase-quality claim.

## Released secondary execution, October 6 UTC

Root released the frozen probe after the generator's structural pass. Admitted
holdout bank index:
`artifacts/benchmarks/heldout-211-307-20261006T0020/fixtures.json`, SHA
`3828ef756c3b2d36890e5b2f444c9323960ec9c0b358d02fe02a8c13ba89936b`.
Only the generator-supplied clean/mix path/hash metadata for the preregistered
three cases was used. The index was rehashed, not parsed for truth labels.
No generated score, onset or phrase truth was used to run or evaluate features.

Execution completed in **4.59 seconds**, exit 0, using unchanged worker SHA
`a87586af40aab7aa22e983efbd5a35acdd9f149197cd9861ff33ee57e1e67117`
and unchanged design SHA above. Two numeric threads; exactly six first-four-
second inputs, 24 aggregate audio-seconds. Every full input WAV hash remained
unchanged. Twelve frontend snapshots contain 72 finite spectral-flux vectors,
each with 801 centered frames. Every PCEN policy's full/block difference was
zero. The evidence-only wrapper persists those vectors before returning them
to the comparison worker; it changes no feature extraction or settings.

The comparison is clean-versus-generated-mixture spectral-flux cosine after
one-second startup exclusion. All rows retain the final centered-padding edge.
Higher agreement is an invariance diagnostic, not accuracy or note/phrase
correctness; sustained low-string differences and a denser click stream can
affect this metric without corresponding to player mistakes.

| Holdout category / window | Magnitude log baseline | Magnitude PCEN default | Unit/gain0.5, 0.4 s | Unit/gain0.5, 1.0 s |
|---|---:|---:|---:|---:|
| Seed211 low C1 / 64 ms | 0.51368 | 0.44997 | 0.39643 | 0.39213 |
| Seed211 low C1 / 256 ms | 0.34512 | 0.32746 | 0.39090 | 0.38506 |
| Seed211 palm mute / 64 ms | 0.44000 | 0.50063 | 0.77764 | 0.80591 |
| Seed211 palm mute / 256 ms | 0.58114 | 0.63712 | 0.84573 | 0.87010 |
| Seed307 legato / 64 ms | 0.30389 | 0.20894 | 0.41851 | 0.45730 |
| Seed307 legato / 256 ms | 0.43705 | 0.35325 | 0.67282 | 0.71342 |

These fixed unit/gain0.5 policies improved this metric for palm mutes and legato
in both windows. They worsened short-window low-C1 agreement, while improving
the longer-window version. Representation, scale, smoothing and window support
must remain explicit factors; no universally best frontend follows from these
three examples. The complete receipt also retains power-log/default-power-PCEN
and whole-excerpt comparisons; no unfavorable row was removed.

The windows contain about 2.09 and 8.37 C1 cycles respectively. Their FFT bin
spacing is 15.625 and 3.90625 Hz, but the first three Slaney mel centers are
43.23, 66.46 and 89.68 Hz in **both** windows. A finer FFT cannot undo coarse
mel aggregation or prove C1 semitone/pitch identification. The 256 ms support
also blurs rapid attacks. No pitch, phrase, missed-beat or audible denoising
acceptance is established.

## Frozen durable execution evidence

Evidence copies under [`evidence/pcen-frontends`](evidence/pcen-frontends/receipt.json)
contain owned scripts, component identity metadata, metrics and snapshot hashes;
no generated WAV, private XOD source or spectral matrix enters Git.

| Artifact | SHA-256 |
|---|---|
| receipt.json | 8359ee9f50ce7a1cd74e7412814654dbb200acd31514096049756414eef2b5e2 |
| invocation.json | cf6753fe66247500ae922a896bc750eb2fcaacda4fda832a8da5c616689a7b8b |
| feature_proof.py | a87586af40aab7aa22e983efbd5a35acdd9f149197cd9861ff33ee57e1e67117 |
| run_with_feature_snapshots.py | c1d14d5c5369721d3d922ca9cedd562bc74f95b645c71920d214d8dc46bc5d0a |
| selected-inputs.json | 90da2263562d3316dc785fc3b50c6407d3e0333b4294b307c46825d83e5d734e |
| feature-index.json | 0ac5212c06c010a864aee32ee9d9b9174a8dcc9f6199d70e7722b7369604e221 |

Snapshot files stay ignored at `artifacts/experiments/pcen-frontends/features`;
all twelve saved hashes and 72 vector shapes/finite checks passed. Root owns
publication/tracker facts. This bounded research checkpoint is complete and
frozen, with production frontend/defaults unchanged. Further labelled corpus
or actual-guitar quality qualification is a separately scoped experiment.
