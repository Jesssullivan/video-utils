# Actual low-register mixture diagnostic — preparation only

Actor/owner `audio_research`. Authority: root's explicitly reattached preparation
lane, operator project goal, repository `AGENTS.md`, R-HOOK-CONVERGENCE-20261004 /
R-N13. Exclusive new writes: this plan and
[`low_register_actual_diagnostic.py`](../../scripts/low_register_actual_diagnostic.py).
The synthetic prototype remains frozen at SHA256
`384a99bca9e72212b5d9631e9b425424ea7b08fc41ce6eb4dde4d647b3ba3bc6`.
No actual PCM was read, processed or rendered while preparing this contract.
Preparation is not a root release, a positive independent audit, elapsed-time
authorization, listening acceptance or master adoption.

## Preregistered input and interval

Original MOV SHA256:
`a522115f4e72e19384fb341bc84369728eceefe49183b8c6367a1008a95176c6`.
Existing decoded float32 source WAV SHA256:
`d68e49688293b1fb8c7c2566e2ecd6e31df9972af013dd23454e15864654bd2a`.
Use only the existing source WAV from the captured8 run
`artifacts/runs/20261005T232627Z-eb7bead2ae74`, never its denoised/normalized master.
The source has 6,657,385 native mono frames at 44.1 kHz. The saved manifest binds
decoded sample zero to media time 0.0; retain decoded and media axes separately.
Rehash original/decoded bytes before and after any later permitted execution;
raw file hashing is provenance work, not a fresh full-take numeric decode.

Neutral fixed diagnostic: `[20,30)` seconds, native samples
`[882000,1323000)`, exactly 441,000 frames. This interval was selected before
reading its diagnostic results. Do not hunt for a favorable passage or rerun a
setting selected from the synthetic scores. Compare all four fixed settings:
P0/P05 low ceiling 0/0.5 dB crossed with fixed noise-density scale 0.5/1.0,
holding broadband ceiling at 8 dB. No normalization, EQ, compressor, dynamic
gain matching, inferred notes or time-shift fit enters this comparison.

Reuse the reviewed capture `[4.10,4.95)` seconds, native samples
`[180810,218295)`. Its music contamination remains unresolved. It is not a
verified fan-only interval, source stem or isolated noise PSD. For an explicit
global processing grid, the first fully contained capture window begins at
sample 182272 (a multiple of hop 2048); there are 14 full 8192-sample windows.
Capture fit uses only the original reviewed interval, not an alternative quiet
selection. Its clipped-to-grid start and unused trailing samples are reported.

Budget distinction for root's exact release: the diagnostic materializes
10.00 seconds of PCM, and existing capture reuse materializes 0.85 seconds
separately; total selected numeric PCM is 10.85 seconds. No FFmpeg decode or
outside diagnostic context is added. The plan does not silently count the
capture as zero-duration PCM. If the authorized maximum means ten seconds
including capture, this exact plan requires revised scope before release;
elapsed time cannot resolve that distinction.

Root subsequently reviewed and explicitly accepted this exact 10.00-second
diagnostic plus separate authorized 0.85-second existing capture reuse, with
no fresh media decode or outside context. The numeric budget distinction is
settled; the exact execution receipt still remains pending.

## Global frame anchor, padding and supported metrics

The frozen prototype uses periodic Hann 8192-sample frames / 2048-sample hop,
FFT/OLA and native cropping. Preserve the source-global frame anchor at sample
zero when comparing an excerpt. Prepend exactly `882000 % 2048 = 1360`
synthetic zero samples to the excerpt before calling the frozen worker; subtract
that prefix when cropping the processed 441,000 source samples. Global native
frame starts are `worker_native_start + 882000 - 1360`, hence lie on the same
hop grid as processing the full source. The prefix is not observed context.

Save each frame's global start, center and full-original-support flag. No
observed samples outside `[20,30)` are supplied. Frames touching outside that
interval contain artificial boundary padding. Retain the exact ten-second
diagnostic arrays with this uncertainty, while using only the conservatively
guarded interior `[890191,1314809)` for numeric descriptors: exclude 8191 samples
at each edge so every overlap-add contributor has original support. This is
424,618 native samples, approximately 9.62853 seconds. The guard is predeclared,
not a region excluded after an unfavorable result.

Welch coherence frames also start on the source-global grid, first native start
890880, and remain wholly inside that supported metric interval. Record window,
hop, number of overlapping averages and native span; overlapping frames are not
independent replicates. Whole-span band-power FFT and Welch coherence are
distinct estimators. No claim that truncated/padded edge outputs equal full-take
processing is allowed, and no AAC/video/media timing proof follows from this
bounded native-WAV operation.

## Descriptors and prohibited interpretations

For the same supported source/output spans, report total mixture RMS change,
20–45 / 45–120 / 140–8000 Hz mixture band-power change, source-power-weighted
mean of per-bin magnitude-squared coherence, and residue RMS. Save fixed gains,
captured density, processed/residue arrays and their hashes as diagnostic `.npy`
files, not a new video, WAV master or latest-run pointer.

[SciPy's coherence definition](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.coherence.html)
uses cross-spectrum magnitude squared divided by the two auto-spectra. A
constant gain can leave coherence equal to one, so high coherence is not unity
gain or preserved guitar. Band averages are descriptive; fine-bin resolution
and short support do not identify C1, fan rotation or musical correctness.
The fixed-mask/window/density limitations remain in the
[frozen research spec](../spec/LOW_REGISTER_NOISE_SEPARABILITY_LANE.md).

This real mixture has no oracle guitar/noise components. Thus
`isolated_fan_reduction` and `musical_component_gain` are explicitly null in
diagnostic results. Reduced low-band mixture energy may remove fan, guitar or
both; the residue contains all changes, not a known unwanted-noise stem.
Synthetic conditional component accounting must not be transplanted to this
recording. A possible AGC transfer mismatch remains unverified. Retaining low
fan energy under protection is a visible tradeoff, not an error to hide.

## Concrete preparation and root release

The stdlib-only metadata operation completed:

```sh
python3 scripts/low_register_actual_diagnostic.py plan \
  --output artifacts/experiments/low-register-actual-diagnostic/plan-20261006T0110-v2.json
```

Plan SHA256:
`ed664a3898ec1e25103fa9062567078cbc2326d4fa01346d9b45565ebda46b75`.
It binds the harness revision, frozen prototype, source metadata/evidence,
capture bounds, global anchor/support, exact four settings and claim/budget
limits. The earlier metadata-only `plan-20261006T0110.json` is preserved as a
superseded preparation draft; v2 additionally fixes Welch frame anchoring.
Neither plan executed actual DSP. Syntax compilation passed without NumPy or
actual-audio processing; validation used saved manifest/comparison metadata.

Execution remains blocked by the explicit assigned preparation scope until
both a positive independent mask/metric audit and root's exact-plan release.
The harness requires a root-owned release JSON with these bindings:

```json
{
  "action": "execute_actual_low_register_diagnostic",
  "root_explicit_release": true,
  "plan_sha256": "ed664a3898ec1e25103fa9062567078cbc2326d4fa01346d9b45565ebda46b75",
  "worker_sha256": "384a99bca9e72212b5d9631e9b425424ea7b08fc41ce6eb4dde4d647b3ba3bc6",
  "audit_verdict": "positive_independent_mask_metric_audit",
  "audit_path": "<root-reviewed independent receipt path>",
  "audit_sha256": "<exact audit receipt SHA256>"
}
```

This records root's assigned release; it is not a new user-approval request or
an inferred plugin/skill permission gate. Root decides whether the final audit
supports that verdict and whether this exact 10.85-second selected-PCM scope is
authorized. A changed source, harness, plan, capture, settings or audit hash
invalidates this execution binding. No elapsed-time fallback exists.

Independent reviewer `clip_baseline` subsequently reported a positive verdict
for frozen worker `384a99…` and synthetic results `72bf70…`, with no must-fix.
It verified all 128 hashes/native dimensions/floors/residue, independently
recomputed capture density, and added seal-before-oracle and PSD DC/Nyquist unit
tests. Coverage is 24 broadband-applicable variants, 16 measured stable-F0
variants/36 channel-event rows and 24 stereo-aggregate attack windows; connected
legato has no stable-F0 fit. The two varying-fan scale-0.5 alerts remain. This
positive synthetic audit does not itself execute or accept the actual take.

Only after root releases the exact bound result:

```sh
.venv/bin/python scripts/low_register_actual_diagnostic.py execute \
  --plan artifacts/experiments/low-register-actual-diagnostic/plan-20261006T0110-v2.json \
  --release-receipt <root-owned-release.json> \
  --output artifacts/experiments/low-register-actual-diagnostic/<new-run>
```

Two numeric threads and 120 seconds maximum, existing locked dependencies,
no installs/models, read-only native WAV mapping and new ignored artifacts.
Publish the diagnostic directory only when all four variants and provenance
checks complete; retain a failure receipt otherwise. Existing masters, videos,
profiles, source files, public tools and latest pointers remain unchanged.
No actual candidate acceptance or next DSP default is implied by preparation.

Process receipt: actor audio_research | target owned actual-diagnostic plan and
new harness | reason preregister bounded neutral real-mixture descriptors |
ruling R-HOOK-CONVERGENCE-20261004 / R-N13 | prior_state synthetic comparison
complete, independent mask/metric audit pending | result metadata-bound plan
and guarded harness only; no actual PCM/DSP execution or core mutation.
