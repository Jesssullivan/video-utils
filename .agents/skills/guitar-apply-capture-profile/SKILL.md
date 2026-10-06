---
name: guitar-apply-capture-profile
description: Apply a pinned source-bound guitar capture profile to a fresh full-take restoration candidate, preserving native timing, uncertain capture content and publication recovery without adopting or accepting the master.
---

# Apply a source-bound capture profile

**Hook:** MCP tool `apply_capture_profile`, prompt `guitar-apply-capture-profile`. The local typed route is admitted with its application-only bounded supervisor; inspect `tools/list` and [the application contract](../../../docs/spec/APPLY_CAPTURE_PROFILE_TOOL_CONTRACT.md) for current schema and evidence. Existing twenty-seven tools and skills retain their contracts. Local source/timeout qualification is separate from publication, positive generated-native MCP rendering, actual-take quality and listening acceptance.

## Intent, binding and closed inputs

Apply one existing tool25 `authored_unrendered` profile to its complete original through the existing restoration/export chain. Required fields are `input` and `authoring_dir`, local strings 1–4,096 characters, plus `receipt_sha256`, exactly 64 lowercase hexadecimal characters. Original input must equal the parent baseline's current original. Select an exact `RUN/capture-profiles/ID/` beneath repository `artifacts/runs/`, containing its own profile and receipt; pin the receipt SHA returned by authoring. Paths reject traversal/symlink components, URLs and staging paths. Similar tuning or RMS never permits another take's capture.

MCP `timeout_seconds` is integer 12–600/default 600. Its application-only supervisor passes worker work seconds `outer - 10`, range 2–590/default 590. Wrapper fallback begins no later than five seconds before the outer deadline, sharing that deadline for inspection, cleanup and reporting. Direct CLI independently accepts integer 1–600/default 600 work seconds:

```text
python3 scripts/apply_capture_profile.py INPUT --authoring-dir DIR
  --receipt-sha256 SHA [--timeout-seconds INTEGER]
```

No output/name/overwrite, executable, filter, model/runtime, profile object, source-hash override or extra DSP knob is supported. A fresh candidate is allocated automatically. Settings come only from the pinned tool25 profile. Change settings by authoring a fresh profile and pinning its new receipt, not by editing stored hashes or passing overrides.

Verify original, current parent manifest/native PCM, profile/receipt, review/context/settings and producer identities before processing and again before publication. Require native rate/channels/sample count, no-time-stretch mapping and explicit finite source-audio origin. Capture requested/profile seconds must match exact native sample bounds; boundary-only floating-point encoding cannot move a sample. Decoder history retained from the baseline is not freshly authenticated physical A/V synchronization.

Only existing supplied `experimental_capture_render` scope/reference is eligible. Current user processing authority persists; faithfully record it without asking again merely to populate a sidecar. Reviewer identity and authorization fields remain supplied assertions. Draft/reselection results cannot render. Do not promote authoring-only scope or weaken reviewed-present music/click contamination to obtain a runnable profile. Unknown fan, guitar sustain or click overlap stays uncertain; capture shape and absolute floor are neither noise-only proof nor measured SNR.

## Read processing and output evidence

Whole-take captured-shape preroll and calibrated delay compensation preserve source sample extent/rate/channels/origin through the existing media functions. Near-32 Hz nine-string fundamentals, intentional distortion, pick attacks, palm mutes, tuplets, rests, sweeps, tapping, legato and sustain require explicit comparison. No automatic speech denoiser, high-pass/hum notch, artist-derived EQ or ambient-music separation follows from this operation.

- `denoised.wav`: pure pregain denoise; `residue.wav`: source minus pure denoise.
- Optional `processed.wav`: authored EQ then compression.
- `cleaned.wav`: normalization of processed audio when present, otherwise pure denoise. Compare `baseline.wav` at the recorded target presentation level.
- Delivery export/codec checks are separate from native PCM master fidelity; audio-only input has no video verification.

Pure residue cannot certify EQ/compressor/normalization fidelity. Equal whole-take LUFS or coherence does not establish equal passage gain, transparent attacks, physical synchronization or best tone.

Successful `rendered_unreviewed` evidence records fresh run/manifest/application/export hashes and capture mapping, with `dsp_performed:true`, `listening_accepted:false`, `master_adopted:false`. Original, profile, parent run, current master and latest pointer remain unchanged. Structural/export checks establish a candidate, not listening acceptance or intended-note/rhythm correction.

## Recover before retrying

Read publication evidence independently of the exit code:

| Observation | Status / publication | Recovery |
|---|---|---|
| Verified precommit failure | `error` / `not_committed` | Candidate objects null; no committed candidate |
| Commit verified, reporting interrupted | `committed_unreviewed_reporting_interrupted` / `committed_unreviewed` | `committed_candidate` pins an existing unreviewed candidate |
| Publish attempted, outcome unobservable | `publication_outcome_unknown` / `unknown_after_publish_attempt` | `possible_candidate` is prepared identity, not commit or absence proof |

These diagnostics exit 2. Canonical recovery objects carry `run_dir`, source/profile/authoring receipt SHAs and pinned `manifest.json`, `application-receipt.json`, `export/outcome.json` selectors. Join only to the reported directory and verify bytes. A possible object's nested `rendered_unreviewed` is its prepared state, not observed publication. All listening/adoption fields stay false.

Transport timeout, missing stdout or disconnected client leaves publication unknown until bounded receipt/hash inspection establishes it. Inspect exact selectors; do not select newest artifacts, retry blindly, delete a committed run or infer absence from a failed call. Failure-receipt preservation can itself fail. Compact success/combined diagnostics are <=16 KiB; durable application/failure receipts <=64 KiB. `owned_process_events_omitted:true` means compact event tail omission, not that no subprocess ran.

Supervisor errors retain bounded `application_supervision` receipt path/SHA and `worker_diagnostic` when available. `worker_diagnostic_omitted:true` means the inline copy was dropped to fit the complete 16 KiB API diagnostic; the full worker result remains pinned locally. Follow the exact receipt rather than treating omission as absence. Process cleanup and candidate publication are independent: no runnable members in recorded owned sessions does not prove all descendants stopped or that a candidate was never published. Incomplete inventory, identity discontinuity or observation failure remains unknown; this route is not kernel containment.

## Research, iteration and qualification

Inspect uncertainty and control purpose in [restoration refinement](../../../docs/spec/RESTORATION_REFINEMENT_LANE.md) and its primary sources. Hold source/capture fixed; vary one supported authored setting in a fresh candidate. Compare reduction first, then floor/smoothing separately. Keep EQ/compression absent for pure denoise contrasts before adding supported stages. A changed capture requires fresh same-source authoring.

Record commands, settings, hashes, versions, confidence and failures. Compare matched-level quiet/active passages, low-register energy, attack/tail behavior and ending legato; state what was actually auditioned. A small comparison set is a workflow preference, not an enforced trial cap. Master selection and acceptance remain explicit later states.

Bounds: original <=3 GiB, native PCM <=1 GiB, <=300 seconds, 8–192 kHz, one/two channels, two media threads. Worker cleanup has one shared exceptional five-second grace; wrapper headroom is separate and is not a hard real-time guarantee. Process inspection/cleanup failure can retain unknown descendants. Existing generic wrapper-group termination cannot prove cleanup of worker children in distinct sessions; this route uses its separately qualified supervisor. Recorded-session timeout fixtures establish their observation scope, not complete tree containment. Consult the contract for native/MCP source qualifications and remaining quality evidence.
