# Actual low-register mixture diagnostic — bounded results

Actor/owner `audio_research`. Authority: root's exact bound execution release,
operator restoration goal, repository `AGENTS.md`, R-HOOK-CONVERGENCE-20261004 /
R-N13. The [preregistered plan](2026-10-05-low-register-actual-diagnostic-plan.md)
and root release followed the independent positive synthetic mask/metric audit.
This lane executed only the four fixed native source diagnostics; canonical
prototype `384a99…`, public/default DSP, masters, videos and latest pointers
remain unchanged. Actual musical acceptance and isolated sources are unknown.

## Bound provenance and execution

All raw diagnostic artifacts are private ignored files beneath
`artifacts/experiments/low-register-actual-diagnostic/run-20261006T0117`.

| Evidence | SHA256 |
| --- | --- |
| Exact prepared plan `plan-20261006T0110-v2.json` | `ed664a3898ec1e25103fa9062567078cbc2326d4fa01346d9b45565ebda46b75` |
| Root execution release | `26bb0a5cc3a1d72e95471830f72ceeb706e5aed21c3474dc48c838e0e2a8225b` |
| Independent synthetic mask/metric audit | `48a47efe16a291c6afa497d55a0653b0f0f7c8ff80e2aa109b030dd0e6dea7cb` |
| Actual diagnostic harness | `2b84f9f7f7b49b691cec68b83546fbf378fa172296e6339aa03c5552fc42c284` |
| Frozen mask worker | `384a99bca9e72212b5d9631e9b425424ea7b08fc41ce6eb4dde4d647b3ba3bc6` |
| Original recording | `a522115f4e72e19384fb341bc84369728eceefe49183b8c6367a1008a95176c6` |
| Existing decoded source WAV | `d68e49688293b1fb8c7c2566e2ecd6e31df9972af013dd23454e15864654bd2a` |
| Result `run-20261006T0117/results.json` | `e946198d9a88c14045566d114a95deed75b9114afe01162723a517d825783e6b` |
| Protected-before snapshot | `1201227e4bdf1446a148c01461193937dbfd1be01b964f362a3ea59143e88845` |
| Protected-after snapshot | `6db61838bd3138d1fe4333f0e6e54a88e47b755d5d6badbf7dc1c3f47fa2908a` |

Plan/snapshot paths are under the parent diagnostic artifact directory. The
[root release](2026-10-06-root-low-register-diagnostic-release.json) and
[independent audit](2026-10-06-low-register-probe-audit.md) remain separately owned
receipts. Root explicitly accepted 10.00 seconds of diagnostic PCM plus the
separate 0.85-second reviewed existing capture, 10.85 selected numeric seconds,
without new media decoding or outside diagnostic context. The command was:

```sh
.venv/bin/python scripts/low_register_actual_diagnostic.py execute \
  --plan artifacts/experiments/low-register-actual-diagnostic/plan-20261006T0110-v2.json \
  --release-receipt docs/agent-notes/2026-10-06-root-low-register-diagnostic-release.json \
  --output artifacts/experiments/low-register-actual-diagnostic/run-20261006T0117
```

Completed successfully in 8.541342375 seconds, within the fixed 120-second
deadline/two-numeric-thread bound, using existing locked dependencies. No
normalization, EQ, compression, limiter, time stretch, fitted alignment, media
export, model/dependency acquisition or full-take numeric processing occurred.
The diagnostic arrays are `.npy`, not delivered/accepted audio masters.

## Clock, capture and exclusions

Native mono 44.1 kHz source interval: `[882000,1323000)`, exact `[20,30)` seconds,
441,000 samples. All four outputs retain that source extent. Prefix 1360
synthetic zero samples preserves the global 2048-sample frame anchor, then is
removed from the retained output. Each variant exports 221 global native frame
starts/centers and original-support flags; 211 frames have complete original
support, ten touch padding. No source context outside the fixed interval was
read. Padded boundary samples do not establish whole-take equivalence.

Descriptive metrics use the preregistered complete-OLA-support interior
`[890191,1314809)`, 424,618 samples/about 9.62853 seconds. Coherence uses 203
fully contained periodic-Hann 8192-sample Welch frames, hop 2048, no detrending,
first global start 890880. Overlapped frames are not 203 independent trials.
Band-power ratios use a separate whole-supported-span Hann FFT; do not equate
that estimator with the coarser Welch bins.

Capture reads only the previously reviewed `[180810,218295)` / `[4.10,4.95)`
source samples. Fourteen fully contained globally anchored capture windows
start at 182272 and stop before the reviewed end. No replacement quiet span
was selected. Music contamination remains unresolved; capture PSD is an
estimator of this mixture interval, not verified isolated fan truth.

## Measured mixture changes

All values below are pre-gain changes against the original supported mixture;
negative dB means lower mixture energy. P0/P05 impose continuous 0/0.5 dB bin
attenuation ceilings through 80 Hz, tapered to ordinary behavior over 80–140 Hz.
All settings retain an 8 dB broadband ceiling and fixed density; scale N05/N10
is 0.5/1.0. Requested gain constraints are not observed source-component gains.

| Fixed variant | Total RMS change dB | 20–45 Hz power change dB | 45–120 Hz power change dB | 140–8000 Hz power change dB | Residue RMS, full scale |
| --- | ---: | ---: | ---: | ---: | ---: |
| P0-N05 | −0.186818 | −0.0000249 | −0.049019 | −0.219238 | 0.00408050 |
| P0-N10 | −0.333510 | −0.0000407 | −0.092227 | −0.391856 | 0.00653696 |
| P05-N05 | −0.189924 | −0.395073 | −0.075656 | −0.219238 | 0.00408946 |
| P05-N10 | −0.338373 | −0.467096 | −0.133071 | −0.391856 | 0.00654774 |

| Fixed variant | 20–45 Hz coherence | 45–120 Hz coherence | 140–8000 Hz coherence |
| --- | ---: | ---: | ---: |
| P0-N05 | 0.999999996 | 0.999957915 | 0.997949278 |
| P0-N10 | 0.999999991 | 0.999874944 | 0.995025368 |
| P05-N05 | 0.999898958 | 0.999937778 | 0.997949278 |
| P05-N10 | 0.999974356 | 0.999837698 | 0.995025368 |

Coherence is the source-power-weighted mean of per-bin magnitude-squared Welch
coherence, with five / fourteen / 1460 bins in the displayed bands. Values are
descriptive, not confidence intervals or a note/fan classifier. Coherence can
remain one under constant attenuation; these numbers do not prove unity guitar
gain, undamaged transients or musical acceptance. The slightly changed low-band
mixture in P0 and the roughly 0.4–0.47 dB change in P05 are observed behaviors,
not isolated guitar-preservation or fan-removal results.

The actual output contains no known clean/noise components. Every band record
therefore keeps `isolated_fan_reduction=null` and `musical_component_gain=null`.
Residue is the complete difference between input and diagnostic output; it is
not a recovered fan stem. Higher density scale removes more mixture energy in
this fixed region; removed energy may include wanted guitar. Do not select a
best setting from these metrics alone, transplant synthetic guitar-gain scores
to this source, infer musician errors or claim the box fan's spectral identity.
No source-time A/B or residue listening acceptance was performed by this lane.

## Readback, preservation and next evidence

Post-run readback rehashed all sixteen mask/density/processed/residue arrays,
checked four nested diagnostic receipts against the aggregate, and verified
null component-claim fields. All seven protected targets have identical before/
after size and SHA256: original MOV, decoded source WAV, current clarity run's
manifest, `cleaned.wav` master, `denoised.wav`, `residue.wav` and
`artifacts/latest.json`. Protected snapshots explicitly bind those paths.
The latest run remains `20261005T232741Z-2b5dc43fd009`; this diagnostic replaces
neither its master nor its pointer. Its preexisting listening-acceptance state
remains false. Verification is scoped to this execution window.

Root and independent timing/fixture reviewers received the frozen result path
and hashes for read-only descriptor/support checks; no repeat DSP is needed to
inspect them. This receipt reports completed bounded diagnostics, not independent
actual-output audit completion. Actual candidate rendering/adoption, full-take
coverage, transient/tail listening and downstream musical analysis remain
separate root decisions. The frozen prototype, publication and prior synthetic
quality alerts retain their original evidence scope.

Process receipt: actor audio_research | target exact released new diagnostic
artifact directory and owned outcome receipt | reason test fixed low-register
mask behavior on neutral original-mixture interval | ruling exact root release
26bb0a5c… / R-HOOK-CONVERGENCE-20261004 / R-N13 | prior_state accepted bound
preparation, actual diagnostics absent | result four native diagnostic variants,
hash-bound descriptive evidence and exclusions; source/current master/latest
unchanged, isolated-source and listener acceptance unknown.
