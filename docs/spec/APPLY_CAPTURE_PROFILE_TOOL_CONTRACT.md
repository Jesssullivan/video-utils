# Source-bound capture profile application tool

Status: **local typed tool 28 is admitted and implemented; generated-positive MCP and all28 exact prompt proofs passed; publication remains a separate checkpoint**. Root admitted the independently audited source, qualified generated native/video processing, owned-session supervisor and closed hook. This lane owns the catalog/API/recipe integration and its local evidence; root owns actual-take actions, publication and master adoption. Persistent user authorization covers the scoped processing. Repository `AGENTS.md`, R-HOOK-CONVERGENCE-20261004, R-N11/R-N12/R-N13 apply. No new permission gate, runtime installation, editor operation or listening acceptance is implied.

Definition of done was recorded before implementation: fixed source-bound inputs; independently qualified application and supervisor; closed typed hook plus skill/recipe; prelaunch negative cases; native/export generated fixtures; real stdio inner and outer timeouts with separate-session/orphan ownership checks; immutable outputs; exact prompts; preservation of all previous 27 descriptors and their generic runner. Listening, physical synchronization, note correctness and adoption remain independent.

## Closed interface and routing

MCP name `apply_capture_profile`, prompt `guitar-apply-capture-profile`, skill [SKILL.md](../../.agents/skills/guitar-apply-capture-profile/SKILL.md). Operator recipe:

```text
just apply-capture-profile INPUT AUTHORING_DIR RECEIPT_SHA256 [OUTER_SECONDS]
```

| Field | Type and bounds | Meaning |
|---|---|---|
| `input` | Required string, 1–4096 characters | Exact original bound to the authoring parent; regular nonsymlink local file <=3GiB, allowed outside the repository. |
| `authoring_dir` | Required string, 1–4096 characters | Explicit existing `artifacts/runs/RUN/capture-profiles/ID` containing the profile and authoring receipt. |
| `receipt_sha256` | Required string, exactly 64 lowercase hexadecimal characters | Pin tool25's authoring receipt. Syntax is explicitly checked; no unsupported JSON-schema pattern is silently ignored. |
| `timeout_seconds` | Optional integer 12–600 inclusive, default600 | Single outer supervision budget; inner operation is `outer-10` (2–590, default590), fallback begins `outer-5`. |

Unknown keys, booleans/nonfinite numeric values, NUL/traversal/backslash/URL/dot-staging paths, missing/oversized/symlink files and an authoring directory outside the explicit run boundary reject. Relative paths use the repository root. No arbitrary output path, executable, environment object, argv, filter, model, media offset, DSP knob, profile object or overwrite control exists. The recipe shell-quotes paths and routes through this same typed API. Changed settings require a new tool25 profile.

Only this tool uses [capture_application_adapter.py](../../scripts/capture_application_adapter.py); all older hooks retain the exact `run_worker` implementation. The adapter pins [apply_capture_profile.py](../../scripts/apply_capture_profile.py) SHA `790ac58f1924db2607087c6ab1cdae5d813ba24eda610af1f396d77e93d06584`, verifies a regular <=256KiB worker before launch, and passes individual arguments to its fixed CLI:

```text
python scripts/apply_capture_profile.py INPUT --authoring-dir DIR --receipt-sha256 SHA --timeout-seconds INNER_SECONDS
```

The standalone worker still accepts operation1–600, default600, plus bounded exceptional cleanup. Its direct CLI range is distinct from this wrapper's outer12–600 range. Approved interpreter/media paths are operator environment mechanisms, never MCP fields or automatic installations.

## Source, settings and authorization

Before media subprocesses, the worker verifies original, current parent manifest/native PCM, reviewed interval, profile/settings, contexts, authoring receipt and producer hashes. It requires tool25 `capture_profile` / `authored_unrendered` / `source_bound_profile_authoring` with no prior DSP/listening acceptance. Draft/reselection/proposal-only outputs, unknown authorization scope, rejected or reviewed-present capture music/clicks, forged/stale source/hash/native/settings/producer identities cannot render. Authoring producer SHA `7d2820878826c87aabf2ab60b73c997b9d406b7f3ff8943d6012ed967444c355` and the frozen media validator are checked.

Existing supplied `experimental_capture_render` authority and its reference are assertions of session scope, not authenticated reviewer identities. No diagnostic invents authority and no recurring approval is added. Unknown/suspected capture contamination stays explicit; no fan-only/noise-only guarantee, recovered stem or whole-take ambient separation follows. Capture requested seconds, canonical profile seconds, integer native sample bounds and source-media span agree without moving a sample. Parent audio origin is finite/verified and `no_time_stretch=true`.

## Processing, publication and bounded results

Worker ceilings: original3GiB/nativePCM1GiB,8–192kHz,mono/stereo,<=300s; review/profile16KiB, manifest1MiB, context64KiB, application/failure receipt64KiB, compact worker result16KiB. Strict finite duplicate-free/depth-bounded JSON applies. Two codec/filter threads, <=128 owned subprocess receipts and file-backed stdout/stderr with4MiB per-stream refusal ceilings share remaining operation budgets.

The qualified resource revision uses process-inspection cap3s and at most two **TimeoutExpired-only** attempts per observation within one absolute5s cleanup end, reserving direct reaping time when available. Ownership failure is never retried into authority. Stages reserve up to5s or half a short remaining budget. Direct-CLI exceptional cleanup shares5s across inspection, remaining-time waits, signals and fallback; this is not a hard real-time OS scheduling claim.

The worker snapshots verified settings into owned private ignored staging, reuses existing `media.clean`/`media.export`, retains pure `denoised.wav` and residue, optional separate EQ/compression `processed.wav`, normalized master and delivery export. Native rate/channels/sample extent, capture update, measured bulk-delay compensation, source-time mapping, output hashes and export proofs are checked. EQ phase and compression attack/sustain remain quality uncertainties. Video proof uses existing copied-picture packet/frame checks and measured AAC delivery timing/tolerance; physical sync is not established. Audio-only output explicitly has null video.

Inputs are rechecked before atomic publication of a fresh immutable run. Original, authored artifacts, parent/master/latest and prior candidates remain untouched; collisions fail. Rendering returns `rendered_unreviewed`, `dsp_performed:true`, `listening_accepted:false`, `master_adopted:false`. Source/profile/authoring hashes, candidate run, manifest/application receipt paths/hashes, capture requested/profile/native/media coordinates and export identity remain in the compact result; full lineage/stage observations remain local.

Publication failures have three distinct cases:

- Before commit: `error`, `candidate_publication:not_committed`, null recovery objects; only owned private staging is cleaned.
- Confirmed commit followed by reporting failure: `committed_unreviewed_reporting_interrupted`, `candidate_publication:committed_unreviewed`; retain committed unaccepted candidate and `committed_candidate`.
- Attempted publication with uncertain observation: `publication_outcome_unknown`, `candidate_publication:unknown_after_publish_attempt`; `committed_candidate:null`, retain `possible_candidate` as prepared expected evidence, never commit proof.

Confirmed/possible canonical projections have schema1/status`rendered_unreviewed`, one exact `run_dir`, source/profile/authoring hashes, and fixed relative selectors plus hashes for `manifest.json`, `application-receipt.json`, `export/outcome.json`, listening/adoption false. They are mutually exclusive; prepared status does not imply commit. Durable failure receipts retain the complete success/prepared object. Error16KiB includes nullable failure-receipt selectors and last8 owned process events; `owned_process_events_omitted:true` permits dropping only inline events while the full trace stays durable.

The API adds structured `application_supervision:{path,sha256}`, nullable `worker_diagnostic`, `worker_diagnostic_omitted`, and `publication_outcome:inspect_exact_durable_receipts` to tool errors. If the combined inline error would exceed16KiB, it omits the diagnostic copy; the exact supervision receipt pins full local `worker-result.json`. Never infer absence from timeout/transport failure, erase a committed run, select the newest run or promote a possible projection. Inspect exact local receipt/manifest/export hashes before retrying.

## Application-specific supervision and limits

Supervisor source SHA `ea2d27400b98a2c7285f068501100c222fbb969a56d53d497a3b141b1c70f5a8`. It creates one ignored `artifacts/application-supervision/ID` with actor/authority, fixed source/input/profile pins and budgets. It records the fresh directly owned `Popen` root, then samples actual PPID descendants and retains native birth identities, PGID/SID, first/last observations and birth-qualified ancestry chains. Bounds: each observation1s,8192 process rows/1MiB projected table,512 identities,128 groups,depth64. Overflow/unsupported identity/refusal yields uncertainty.

On macOS, public `proc_listallpids` and `PROC_PIDTBSDINFO` avoid repeated expensive `ps` launches that exceeded1s under actual host load. Apple SDK declarations: `/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk/usr/include/libproc.h:92` and `sys/proc_info.h`; native BSDINFO has microsecond birth, PID/PPID/PGID. PID array<=32KiB. Protected unreadable rows retain live PGID/unavailable ancestry, so target-group membership cannot silently omit them; they cannot establish ownership. Linux keeps bounded `ps` and kernel `/proc/PID/stat` start ticks. See [Apple process fields](https://github.com/apple/darwin-xnu/blob/main/bsd/sys/proc_info.h), [Linux process metadata](https://www.kernel.org/doc/html/latest/filesystems/proc.html), [POSIX ID lifetimes](https://pubs.opengroup.org/onlinepubs/009696699/basedefs/xbd_chap04.html), [signals](https://pubs.opengroup.org/onlinepubs/009604499/functions/kill.html).

At fallback `D-5`, freeze the unreaped owned root, reobserve/revalidate recorded descendant groups, signal deeper verified ancestry before root, reap direct worker and check all retained identities, using one shared absolute end<=D. Fresh birth/PGID/SID/membership checks precede group signals; command names and coarse time confer no ownership. Failed inspection can attempt direct owned-root termination/reaping, but refuses ambiguous descendant groups. Signal refusal still attempts bounded reaping. A starting receipt is not finalized cleanup: explicit finalized-error state prevents bypassing cleanup on later reporting-budget errors. Report failures cannot reset cleanup allowance. Terminal report failure returns the last pinned durable receipt and uncertainty.

Successful cleanup reports only `no_runnable_recorded_members` with `containment_scope:observed_owned_sessions_only`. Rapid orphaning before a sample, unrecorded sessions, moved/escaped descendants, PID/group reuse, syscall/filesystem/scheduling delay and check-to-signal races are limits of observation, not kernel containment. A retained identity moving session remains unknown, with no unauthorized signal. Outer worker-group killing alone is not evidence separate sessions stopped. No global process sweep occurs; unrelated same-command sentinels remain untouched.

## Qualification checkpoint

Historical31e source had36 fixture/audit passes; corrected00a had46 and original generated/native8s proof. They remain historical. Root qualified current790 with51 owner/resource tests,9 independent resource cases,16 inert harness cases, a fresh8s generated trial and independent native/VFR/AAC readback. No operator recording was processed by this integration lane.

Exact supervisor ea2d combined23 tests passed48.475s; independent signal/refusal/startup/budget3 passed5.609s. An earlier mixed7df→ea2d pin-only23 run passed42.990s and is explicitly not a single-SHA run. Independent native refusal probes confirmed protected membership/unavailable SID never authorize group signals. Actual initialized inert stdio tests cover ordinary inner cleanup, genuinely stopped outer fallback with distinct SID and unrelated sentinel, retained orphan after leader exit, escaped orphan uncertainty, publication metadata retention, identity reuse, bounds, refusal and one cleanup end. They use a fixed private test harness, never a public executable knob.

Typed integration tests cover schema/path/preflight failures, literal arguments, supervisor-only routing, structured/omitted diagnostics, real initialized wrong-pin failure before DSP, exact prompt/schema, and preserved original27 descriptor/generic-runner digests. Final initialized generated8s MCP passed42.8608s with exact native44100Hz/stereo/352800 samples, protected original/profile/receipt/parent hashes unchanged and fresh candidate `20261006T035515Z-75c5fae6be12`. All five native-stage SHA256 values equal the independently audited790 standalone generated trial; the bridge receipt is [MCP native hash bridge](../agent-notes/2026-10-06-apply-capture-profile-mcp-native-hash-bridge.json). Local source proof is saved in [MCP result](../agent-notes/2026-10-06-apply-capture-profile-mcp-result.json). All28 bundled skill validations and initialized exact prompt readbacks passed in the explicit locked interpreter with empty stderr (skill owner, no tool calls). Root owns publication. Listening, musical quality, physical sync, AU/Logic acceptance and master adoption remain unverified.

The initial tool28 checkpoint preserved all original27 descriptors. The later root-admitted tool29 integration intentionally adds only the optional `marked_video.arrangement_markers` input property (explicit `all-review` required); preservation tests remove exactly that property before comparing the original digest. The generic runner remains unchanged. Seven application-hook regression tests passed in0.667s at this tool29 checkpoint.
