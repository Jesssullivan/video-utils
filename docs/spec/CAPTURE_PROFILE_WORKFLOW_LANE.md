# Capture-profile authoring for each new take

**Status: authoring worker locally implemented, fixture-qualified and present in the local typed catalog; custom application admission separate.** Root first assigned documentation, then explicitly released the design for new worker/tests on 2026-10-05 under the active parallel goal and R-HOOK-CONVERGENCE-20261004 / R-N13. Published `scripts/media.py`, the six registered profiles and existing masters remain frozen. New `scripts/capture_profile.py` authors settings/receipts only; it does not decode audio or run DSP. Hook/skill owners separately qualified the local authoring interface; root owns actual source verification and publication. The separate custom application route and new DSP/pitch-mask experiments remain unreleased by this lane.

## Intent and definition of done

For each new phone or Photo Booth take, author a fresh validated profile using that input's actual hash and a reviewed capture interval. Preserve approximately 32 Hz nine-string guitar, saturation, pick attacks, palm mutes, tapping, legato and tails while comparing background reduction. Do not clone an old recording's SHA, captured band shape, capture interval or listening assertions into the new take.

The design is complete when it defines the closed controls, source/run/review bindings, immutable artifacts, claim states, comparisons and future tool/skill admission. Implementation readiness additionally requires a qualified authoring worker, typed API validation, failure fixtures, explicit application-route admission and root release. Documentation readiness does not activate a tool or change the six live `denoise` profile choices.

## Evidence that shapes the workflow

The existing actual [captured-restoration comparison](../agent-notes/2026-10-05-captured-restoration-comparison.md) verified native mono 44.1 kHz extent, hashes and source-minus-denoise residue. Captured8/12 reduced total 4–5 s window energy by approximately 4.45/5.43 dB, but the opening 0–1 s changed only about 0.56/0.57 dB before normalization. Active 20–45 Hz mixture losses of roughly 2–3 dB remain unresolved. These are mixture measurements, not fan-only SNR or isolated C1 attenuation. Changing several controls between old and captured runs cannot identify one knob's causal effect.

The [box-fan characterization](../research/BOX_FAN_CAPTURE.md) found different short-interval spectra and possible overlap with the theoretical tuning/harmonic series. Quietness, stationary-looking lines, high coherence or the absence of a visible C1 peak cannot establish noise-only content. Fan speed, microphone position and recorded gain remain per-take unknowns. A new source should therefore obtain new capture evidence instead of a universal fan notch, absolute floor or reusable band shape.

Keep two meanings of separability explicit. The mono mixture does not establish recovered isolated fan or guitar stems. Separately, restoration artifacts and video presentation can be audited: pure `denoised.wav` and `residue.wav` remain distinct from `processed.wav` and normalized `cleaned.wav`; the [marked-video audit](../agent-notes/2026-10-05-marked-video-actual-visual.md) verified copied delivery audio independently from reencoded marked picture. Audio/picture identity checks do not establish musical separation, perceptual quality or physical capture synchronization.

The complementary [low-register separability design](LOW_REGISTER_NOISE_SEPARABILITY_LANE.md) proposes a future mixture-derived mask with separate posthoc component accounting on generated references. That is a separate capability, not a new afftdn profile field or feature of authoring. For the current input-dependent denoiser, paired `D(s+n)-D(n)` is an incremental response, not an isolated guitar output. Keep these methods and their reference scope separate; authoring cannot promise a continuous low-gain floor or a pitch mask through NR/NF/ad/gs.

## Proposed per-take sequence

1. Inspect the original media with the current `probe` contract. Obtain or reuse a source-bound baseline run whose original input SHA, native `source.wav` hash, rate, channels, integer decoded sample count and first decoded audio origin are verified. A new baseline may be created with the currently authorized bypass recipe; the proposed authoring operation itself does not decode or render.
2. Run the current `noise` and relevant click/tone diagnostics. Treat their intervals and identities as candidates. Audition original-source spans and record the selected interval, reviewer assertions, suspected sustain/clicks and capture authority. The 16 kHz diagnostic copy is not a native master or proof of low-note absence.
3. Supply explicit NR/NF/ad/gs controls and the reviewed interval to the proposed authoring worker. It verifies the current original file, baseline manifest and decoded source PCM before writing anything. It writes a new profile and sidecar receipt; it does not learn a band shape or render audio.
4. After implementation and application-route qualification, render a fresh comparison through the existing closed media-profile validator. The rendering worker samples the new source's interval in internal preroll, removes preroll plus calibrated denoiser delay and preserves original native sample extent. The resulting captured shape belongs to this source/render, not the authoring step.
5. Compare native pre-gain denoise, pure residue, optional tone/dynamics stage and matched-presentation masters. Retain rejected trials and uncertainty. Reanalyze changed denoise inputs with fresh hashes; preserve the distinction between music inference on pure denoise and tone/dynamics in the delivered master. Export or mark only the explicitly selected completed run; an audition selection is not master acceptance.

Existing session authorization can cover routine profile authoring and experimental rendering within its stated scope. This workflow does not create a recurring permission prompt. A diagnostic suggestion alone does not supply authorization or listening. Root released bounded metadata authoring after design review; new DSP and typed application admission remain separate assignments.

## Proposed worker and typed MCP input

The tool intent is `capture_profile`; it authors source-bound settings and provenance without applying them. Implemented direct CLI, with MCP advertisement separately controlled:

```text
python scripts/capture_profile.py INPUT --run-dir RUN_DIR
  --capture-start SEC --capture-end SEC
  --reduction-db NR --noise-floor-db NF --adaptivity AD --gain-smooth GS
  --integrated-lufs LUFS --true-peak-dbtp DBTP
  --review REVIEW_JSON
  [--timeout-seconds INTEGER]
  [--eq FREQUENCY_HZ GAIN_DB Q ...]
  [--compressor-threshold-db DB --compressor-ratio RATIO
   --compressor-attack-ms MS --compressor-release-ms MS --compressor-knee-db DB]
```

Repeated `--eq` accepts exactly three numeric arguments per band, at most three bands. Compressor flags are all-or-none. Inputs use an argument vector, never a shell string. The proposed MCP object has `input`, `run_dir`, `capture_start_seconds`, `capture_end_seconds`, `reduction_db`, `noise_floor_db`, `adaptivity`, `gain_smooth`, `integrated_lufs`, `true_peak_dbtp`, `review`, optional `peaking_eq` and optional `compressor`. All numeric range endpoints are inclusive except that EQ frequency must be strictly below Nyquist. Unknown keys, arbitrary filters/argv and booleans used as numbers are rejected.

| Controls | Closed bound and policy |
| --- | --- |
| Capture start/end | Finite decoded-original-audio-relative seconds; start ≥ 0; rounded native interval inside verified PCM extent with duration 0.1–10 s inclusive. Record requested seconds and actual integer sample bounds. |
| `reduction_db` | Explicit finite 0.01–12; no universal NR default. |
| `noise_floor_db` | Explicit finite −80..−20; remains a candidate absolute control, not an inferred consequence of capture RMS or the centered captured shape. |
| `adaptivity` | Explicit finite 0..1. Faster adaptation can change artifacts; no universal optimum. |
| `gain_smooth` | Explicit integer 0..50; reject floats and booleans. |
| `peaking_eq` | Absent by default. At most three exact numeric `{frequency_hz,gain_db,q}` objects: 160–6000 Hz and below source Nyquist, ±3 dB, Q 0.5–2. No high-pass/notch/shelf or free filter text. |
| `compressor` | Absent by default. Exactly `threshold_db` −36..−6, `ratio` 1..3, `attack_ms` 8..20, `release_ms` 60..200, `knee_db` 0..6. Existing fixed linked RMS/downward/no-makeup/25% wet behavior is preserved. Its 2.50 dB stage attenuation bound is not a bound on total restoration or normalization. |
| Loudness | Explicit finite `integrated_lufs` −70..−5 and `true_peak_dbtp` −9..0 fields/flags are required; no undocumented magic default or arbitrary presentation object. |

These authoring bounds reuse frozen `media.load_profile`, `validate_post_controls` and `post_denoise_filters`. Hook-lane qualification separately added the required closed nested-object/array support to the local API validator; worker tests alone do not activate that schema. Its admitted interface remains authoring only.

## Exact review sidecar input, proposed schema 1

Read at most 16 KiB from a regular, nonsymlink review JSON file beneath the verified run. Reject unknown fields, duplicate keys, unsupported values and nonfinite or boolean numeric values. Required fields:

| Field | Type and binding |
| --- | --- |
| `schema_version` | Integer 1, not boolean. |
| `source_sha256` | Lowercase 64-character SHA-256, equal to computed current original `INPUT` and baseline manifest original hash. |
| `source_run_manifest_sha256` | Exact current baseline manifest bytes. A changed manifest needs a new review binding; never silently rebase. |
| `source_pcm_sha256` | Exact verified native `source.wav` bytes and manifest output hash. |
| `start_seconds`, `end_seconds` | Finite values matching typed request after native sample conversion. |
| `time_axis` | Literal `decoded_source_audio_samples`; no guessed media origin. Store original-media spans separately only when verified origin exists. |
| `selected_by`, `reviewed_by` | Nonempty strings up to 128 characters; supplied identity assertions, not authentication. |
| `review_status` | `reviewed_candidate`, `reviewed_possible_contamination`, or `rejected_contaminated`. |
| `authorization_scope` | `profile_authoring` or `experimental_capture_render`; record scope without upgrading it. |
| `authorization_reference` | Nonempty text up to 512 characters identifying the actual session request/delegation/review record. |
| `music_status`, `click_status` | `unknown`, `suspected`, `reviewed_no_obvious_content`, or `reviewed_present`; supplied review, never machine proof. |
| `ambient_music_status` | `not_reported`, `suspected`, `reviewed_absent`, or `reviewed_present`. |
| `note` | Meaningful 1–2000-character review note. |

`rejected_contaminated` or reviewed-present music/clicks in the selected capture returns `needs_reselection` without a runnable profile. Unknown/suspected contamination can remain an explicitly scoped experiment when authorization covers it; the receipt must not certify noise-only content. Broad user-authorized capture with a root-selected interval retains that exact distinction. No new source hash is accepted from the caller as a way to replace the computed identity.

Authorization must not be escalated during authoring. `profile_authoring`-only scope can produce a closed-settings `proposal.json` with `status: draft_authorization_incomplete`, not a runnable `profile.json` containing `noise_capture_authorized: true`. Existing scoped `experimental_capture_render` authority permits authoring a validated runnable profile without invoking DSP. A future application route must recheck that authority and any explicit root hold; file creation itself supplies no new permission.

Ambient music is never automatically imported, uploaded, downloaded, removed or treated as fan noise. When suspected/present, retain the observation and require a separately scoped source-separation plan before that treatment. The default remains guitar-practice restoration; no pretrained stem model, studio-track reference audio or pitch mask is invoked by profile authoring.

## Output identity, provenance and application admission

Write only to a fresh `artifacts/runs/<verified-run>/capture-profiles/<unique-id>/` staging directory, atomically published with no overwrite. Bounds are 16 KiB review input and 64 KiB receipt; original media remains local. The authored profile contains only current worker-supported keys. Extended provenance belongs to a separate `receipt.json`, because the frozen worker correctly rejects unknown profile keys.

Implemented authoring ceilings: path strings 1–4096 characters; original media at most 3 GiB, verified source PCM at most 1 GiB, native sample rate 8–192 kHz, one/two channels and extent at most 600 seconds; baseline manifest at most 1 MiB, each context JSON at most 64 KiB, authored profile at most 16 KiB and compact tool result at most 16 KiB. Reject traversal before resolution, symlink components, nonregular inputs and output collisions. Source input may be outside the repo when explicitly selected; run/review/output stay beneath the verified local run. Hash files in 1 MiB chunks, with checks and rehash before publication. `timeout_seconds` is integer 1–60, default 60; cooperative checks cover the callable function and the standalone Unix CLI also uses its owned SIGALRM to interrupt a blocking read. Header inspection uses bounded stdlib RIFF/WAVE fmt/data parsing and seeks past the PCM payload: no subprocess, decode, network or model work occurs. RIFF PCM integer, float32/64 and supported extensible headers qualify; unsupported compressed/RF64/packed formats reject. These are authoring limits, not limits of every existing media tool.

`profile.json` binds the computed original SHA, selected seconds and authorized capture metadata; its review text identifies root/agent versus operator selection without claiming exact operator choice or verified noise absence. All numeric settings are explicit. The sidecar stores full original/PCM/manifest/review/profile byte hashes, canonical settings digest, selected native sample bounds, actual source/media time origins, context file hashes, authorization/review assertions, producer/version/environment identity and any skipped/unknown evidence. Recheck inputs immediately before publication. A stable profile SHA identifies content; a fresh trial ID preserves repeated authoring and alternative decisions.

For a runnable-profile result, return `status: authored_unrendered`, `evidence_kind: source_bound_profile_authoring`, profile/receipt paths and hashes, source identity, capture review and typed warnings/abstentions. Draft authorization and rejected-selection branches remain distinct and do not return a runnable profile path. Do not emit listening acceptance or a learned-noise claim. Structural failures produce no published profile. Profiles remain per-source artifacts; no global aliases or new universal `captured8`-style names are added for every take.

The current direct recipe accepts a validated profile path. Current MCP `denoise` accepts only its six registered names and cannot apply a new authored receipt. A future typed application selector must be separately reviewed: verify the authored receipt/profile/source hashes, reject stale settings/context as defined by that contract and forward only the validated profile path through a fixed worker invocation. It must not enable arbitrary workers, paths as shell code or filter strings. Authoring admission does not imply rendering, export, hosting or AU admission.

## Six constant artist contexts and agent participation

Carry the exact [`program/capture-context.json`](../../program/capture-context.json) and [`program/instrument.json`](../../program/instrument.json) identities into proposals: Lorna Shore, The Haunted, Meshuggah, Kublai Khan TX, Mgła and Children of Bodom. Preserve the registry's inferred spelling normalization and theoretical octave qualifications. These six references express articulation, saturated texture, string separation and low-register weight across the same fixed nine-string context. They are not six EQ presets, an isolated spectral target, downloaded reference tracks or an expected score.

Agent intent: reduce measured background while retaining that context. Dependencies: `probe`/verified baseline, `noise`, relevant click/tone observations and source-bound `review`; no graph scheduling is implied by `pipeline`. Research/control loop: inspect evidence, propose explicit settings, author, compare qualified immutable renders, retain failures, annotate what was actually heard. The local authoring hook and skill describe exact knobs, source dependencies, bounded output, iteration and claim limits. See the parallel [tool contract](CAPTURE_PROFILE_TOOL_CONTRACT.md) and [skill lane](CAPTURE_PROFILE_SKILL_LANE.md). Their local authoring readiness does not admit custom rendering or establish external discovery/host installation.

## Comparison plan and implementation qualification

Keep source/capture selection fixed while first varying NR, then absolute NF if reduction is weak; test ad/gs changes separately instead of attributing a multi-control comparison to one setting. Initial NR 8/12 and NF −40/−35 may be explicit comparison candidates when authorized, not transferable measured fan floors. Keep EQ and compression off for denoise comparisons. Add them in separate stage contrasts only after checking pure-denoise residue and low-register/attack/sustain behavior.

Measure source/candidate hashes, native extent and calibrated delay; quiet and active region native pre-gain RMS/bands; matched presentation loudness/peak/mode; pure-denoise residue; optional processed-minus-denoise contrast; and restored-input feature ancestry. Listen to original-aligned low palm mutes, long tails, fast articulation and ending tapping/legato. Equal whole-take LUFS and high coherence do not establish equal passage gain, noise-only removal or good tone. Keep visual annotation readability separate from copied audio and listening acceptance.

Before activation, require meaningful checks for new source hash acquisition rather than transplant, wrong original/PCM/manifest/review hashes, changed inputs during authoring, source/media offset mapping, rounded boundaries and short/out-of-range captures, duplicate/unknown keys, bool/NaN/infinity and path/symlink/overwrite rejection, nested schema bounds, optional-stage absence, known mixed guitar/noise and capture-contamination cases, low-register/transient quality limitations and stale application receipts. Reuse the published profile/native-stage tests as references; new authoring tests must exercise provenance and failure behavior rather than mirror serialization. A fresh generated fixture cannot reuse the demo-bound profiles. No new DSP/pitch-mask test render occurs in this metadata-authoring lane.

Acceptance states remain orthogonal: verified source/provenance, authored settings, structural render success, generated-fixture quality measurements, reviewer observation, audition selection, real master listening acceptance, export identity and host/AU proof. A candidate stays a candidate when a later state is missing.

## Implementation checkpoint

The new worker has 45 passing local fixtures: 33 original fixtures and 12 independent audit cases covering all three successful/abstention branches, original path and three review hash bindings, source/context mutation, native float/stereo/nonzero-origin mapping, inclusive settings and exclusive Nyquist, malformed bounded WAV headers and manifest mappings, duplicate/oversized JSON, no subprocess/DSP, fresh atomic publication and deadline interruption/cleanup. Audit fixes translate top/nested integer overflow and path-normalization errors into domain errors. Profiles validate with the frozen media validator. These metadata fixtures do not establish real noise-only content or actual restoration quality. Root performs actual-take authoring verification; no actual new DSP render or prior master mutation was performed by this worker lane.

Capture duration is validated using integer native sample counts: the minimum is `ceil(sample_rate/10)` samples and maximum is `10*sample_rate`. The profile stores native bounds divided by sample rate; only when the frozen validator's seconds subtraction rounds outside the inclusive 0.1/10 boundary, its start changes by one ULP at the interval magnitude. End remains fixed, native rounding must remain exact and source extent must remain valid. Receipts expose `profile_seconds` separately from original `requested_seconds` and exact `native_samples`. Tests confirm both 0.2–0.3 and 8.1–18.1 second boundaries pass the frozen validator without moving a sample.

Compact stdout contains schema/tool/status/evidence kind, run/output directory, current original SHA, nullable runnable profile path/hash and draft proposal path, receipt path/hash, requested/native/source-media interval, `dsp_performed: false` and `listening_accepted: false`. Domain/I/O failure returns a bounded JSON error with exit 2; argparse syntax errors use stderr/exit 2. Receipts retain full settings/context/review assertions, producer-file identity scope and warnings within 64 KiB. Authoring-only scope produces a nonrunnable draft, contaminated selection a reselection receipt, and render-scoped existing authorization an authored-but-unrendered profile. No confirmation prompt occurs.
