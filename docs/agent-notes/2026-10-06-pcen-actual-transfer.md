# Fixed PCEN characterization on the restored actual take

Actor `/root/xod_spectrogram`; authority R-HOOK-CONVERGENCE-20261004,
TIN-3692 comment `98cf680c-7299-4949-bfb2-60079053ad43`, R-N12/R-N13.
Root explicitly authorized characterization of the existing new denoised WAV,
with the same frozen four policies and two windows. The original XOD golden
proof and secondary generated holdout proof remain unchanged.

Before reading excerpt features, the neutral intervals **20–24, 90–94 and
130–134 seconds** were preregistered as `time20`, `time90`, `time130`. There is
no articulation label, clean reference, intended score or musical correctness
label for these intervals. Exactly 12 actual audio-seconds were analyzed.

## Execution and provenance

Input: `artifacts/runs/20261005T232741Z-2b5dc43fd009/denoised.wav`, SHA
`26c9f42c2bb2957fc35e00f0070991895f9120fefb69dce0a95248cd7ad39bfd`.
Producer manifest SHA:
`4a75b4e352075114a7b6026c74acab3ab6c64eedddd52fc2b8514adfed80549c`.
Original movie SHA:
`a522115f4e72e19384fb341bc84369728eceefe49183b8c6367a1008a95176c6`.
The current mono float32/44.1-kHz waveform was cropped on its native sample
grid, then resampled separately to 16 kHz for features. Per-excerpt native and
analysis PCM hashes are retained in the receipt.

Reused the unchanged frozen extraction worker, SHA
`a87586af40aab7aa22e983efbd5a35acdd9f149197cd9861ff33ee57e1e67117`.
Both windows have 80-sample hops, 128 Slaney mel bands spanning 20–8000 Hz,
centered Hann frames. Power-default and magnitude-default use input scale
2**31, gain 0.98 and 0.4-second memory; the other magnitude policies use scale
1, gain 0.5 and 0.4/1.0-second memory. Bias 2, compression exponent 0.5 and
epsilon 1e-6 remain fixed. Explicit first-frame `M[0]=E[0]` initialization and
returned state carry are unchanged from the preregistered generated probe.

Execution finished in **7.22 seconds**, exit 0, two numeric threads. All six
feature snapshots were saved and hashed before any cross-policy comparisons.
Their 36 spectral-flux vectors are finite, each with 801 centered frames.
Every PCEN full/block maximum difference was zero. Original movie, denoised
input and producer manifest remained byte-identical. Latest pointer SHA before
and after execution:
`8ed66efb8f81f06db6c1abb0a5962c38218d6c8bd1fb3c2d46432dc1693fa5ee`.

## Descriptive comparison

These cosines compare a PCEN spectral-flux vector with its same-representation
log baseline after excluding the first one second. They describe feature
agreement, **not** denoising preservation, detection accuracy or better musical
analysis. Both retain final centered-padding frames. Feature quantiles in the
full receipt have different policy-dependent units and cannot be ranked as
audible noise reduction.

| Neutral interval / window | Power default vs power log | Magnitude default vs magnitude log | Unit/gain0.5, 0.4 s vs magnitude log | Unit/gain0.5, 1.0 s vs magnitude log |
|---|---:|---:|---:|---:|
| time20 / 64 ms | 0.92155 | 0.97484 | 0.97781 | 0.97562 |
| time20 / 256 ms | 0.96621 | 0.99305 | 0.97652 | 0.97330 |
| time90 / 64 ms | 0.89127 | 0.96093 | 0.95054 | 0.94149 |
| time90 / 256 ms | 0.94356 | 0.98611 | 0.96145 | 0.94418 |
| time130 / 64 ms | 0.91219 | 0.97096 | 0.97569 | 0.97383 |
| time130 / 256 ms | 0.96892 | 0.99368 | 0.97491 | 0.97185 |

All policies ran successfully, with high but nonidentical envelope agreement
on these excerpts. This does not select a winner: the log baseline is another
transform, not ground truth. The actual characterization cannot test the
generated probe's clean/mix invariance findings because there is no clean
recording of these same performances.

The 64/256 ms windows contain about 2.09/8.37 theoretical C1 cycles and have
15.625/3.90625 Hz FFT-bin spacing. Both aggregate the low end into the same
coarse mel bands, whose first centers are approximately 43.23/66.46/89.68 Hz.
Those representations do not qualify C1 semitone identification. Longer
support blurs rapid subdivisions; centered padding and sparse excerpt coverage
remain explicit limits. No onsets, notes, phrases or missed beats were graded.

## Frozen evidence and handoff

Durable metadata and owned investigative source:
[`evidence/pcen-actual-transfer`](evidence/pcen-actual-transfer/receipt.json).

| Artifact | SHA-256 |
|---|---|
| plan.json | a5c95ac0b418828e6290b6d6df1952f04b4ece847e75d4f83a2b5d263fb9a6b3 |
| characterize.py | 5d5dc5eeeda871f7641c25791ea3f206044e5c32227dffda8c153f61e21ab57a |
| receipt.json | e28ea63e9b2fc86d98d1a9c18d92c77ea4c07de075c7f6b3b063a62e8965fb92 |
| feature-index.json | d10d18d5ffc5cf2804b30d346d5f0b951d7d7a2813dd0fec5aaa303225a62194 |

The original plan was saved under ignored
`artifacts/experiments/pcen-actual-transfer` before execution; the copied plan
retains its timestamp and hash. Generated features stay ignored there. The
owned characterization script imports the already frozen owned frontend worker;
it imports no private XOD core or ML model/environment. Root owns publication
and factual tracker updates. Current frontend, tool catalog, masters, markers
and latest pointer were not changed by this lane. This characterization is
complete and frozen; listening, preservation and performance accuracy remain
separate acceptance states.
