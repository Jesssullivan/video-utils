# Render stage of the Cade demo DAG

Linear TIN-7788, demo DAG item P9 and the render half of P6. Ruling R-HOOK-CONVERGENCE-20261004. Status: a draft
contract, a task body and an image recipe. No GPU window ran for it, no Lease was taken and no image was pushed.

Cade's `cade-hardware-handoff` workflow renders a demo from a signed producer packet. This document covers the part
of that workflow that runs this repository's tools. It starts after `bs21_privacy_guard` and `readiness_check` pass
and ends when `deliver_check` has run. Delivery is the next task, `deliver_internal`, and lives in Cade.

```
claim_job -> verify_packet -> assets_build -> bs21_privacy_guard -> readiness_check
  -> [render stage: verify_inputs -> claims_gate -> intake -> preflight -> voice_plan -> voice_gpu (Lease)
      -> voice_render -> voice_adopt -> compose ... deliver_check -> collect]
  -> deliver_internal
```

The task body is `python -m narrate video render-stage` (`narrate/video/render_stage.py`). It has three actions:

| Action | What it does | Writes |
| --- | --- | --- |
| `check --request R [--inputs DIR]` | Validates the request and prints its phases. With `--inputs`, the `verify_inputs` phase, it also compares the worker's commit with the request and then re-hashes every input at `DIR/<sha256>` | nothing |
| `check --request R --gpu-draft` | Prints the plan of a `gpu_window` or `mixed` request, which v1 refuses otherwise. It never goes with `--inputs` | nothing |
| `preflight JOB --request R` | Binds the request to the job's intake, removes any earlier report, runs the frame gates on the job the intake wrote and refuses the first finding with its own code. It accepts a `gpu_window` request, because this phase comes before the window | `JOB/intake/preflight.json` |
| `takes JOB --request R [--after-window] [--gpu-draft]` | Compares the voice nodes with the request, one action per segment (see "Mixed takes") | nothing |
| `result JOB --request R [--export DIR]` | Binds the request to the job's intake and to a passed preflight, then reports a job that ran to `deliver_check`, every output by digest, and what ran since its last render. With `--export`, it copies the cut, the report and the result into `DIR` under their sha256 names | `JOB/rerun.json`, `DIR/<sha256>.mp4`, `DIR/<sha256>.json` |

The recipes are `just nv-render-stage-check`, `just nv-render-stage-preflight`, `just nv-render-stage-takes` and
`just nv-render-stage-result`. The other phases run the existing commands: `narrate video claims`,
`narrate video intake`, `narrate plan`, `narrate render --prerendered`,
`narrate video stage JOB voice --from-run` and `narrate video run JOB --until deliver_check`. This stage adds no new
processing primitive, so it has no MCP tool of its own. The `narrated-video-verify` skill points at it.

## Request

A request is `narrate_render_stage_request` at schema version 1. Every string is one token, a digest or a fixed word.
A path, a host, an address or prose refuses `token_invalid` or `digest_invalid`. That keeps store paths and private
terms out of Hatchet payloads and logs.

| Field | Value | Refusal |
| --- | --- | --- |
| `workflow` | `cade-hardware-handoff` | `workflow_mismatch` |
| `run_id`, `packet_id` | one token each. The job ledger keys on `packet_id` plus the bundle digest | `token_invalid` |
| `job_id` | a narrated-video job id | `token_invalid` |
| `edition` | `Internal` or `Campaign`. A client edition waits for its own tenant (T4) | `edition_not_v1` |
| `video_utils_commit` | 40 hex. The worker's own commit must match it | `commit_invalid` |
| `worker_image` | `sha256:<64 hex>`, the OCI digest the task ran in | `image_invalid` |
| `inputs` | digests, listed below | `digest_invalid`, `inputs_keys` |
| `voice` | `{mode: from_run, runs: {segment: narrate content_sha256}}`. `{mode: gpu_window, runs: null}` and `{mode: mixed, runs: {segment: content_sha256 or null}}` refuse in v1 outside `--gpu-draft` | `voice_invalid`, `gpu_window_not_v1` and the codes below |
| `lease` | the window's Lease binding with `gpu_window` or `mixed`. Null with `from_run` | `lease_missing`, `lease_unneeded` |
| `until` | `deliver_check` | `until_invalid` |
| `rerun` | optional. `{scope: any}` or `{scope: compose_only}` marks a new event on a job root that may already hold a render (see "Reruns") | `rerun_invalid`, `rerun_scope_conflict` |
| `spend` | `{window_cap_usd_cents, rate_usd_cents_per_hour}`, required with `gpu_window` or `mixed` and refused with `from_run` (see "Spend cap") | `spend_cap_missing`, `spend_unneeded`, `spend_invalid`, `spend_cap_exceeded` |

## Inputs by digest

Every private input mounts read-only at `/inputs/<sha256>`. The worker re-hashes it there before it reads it. The
image holds none of them.

| Input | Required | Check at `/inputs/<sha256>` |
| --- | --- | --- |
| `bundle_manifest_sha256` | yes | a directory whose `manifest.json` hashes to the name. Intake then checks every asset against that manifest |
| `records_sha256` | yes | a directory whose tree digest is the name |
| `engine_record_sha256` | yes | a file that hashes to the name |
| `lexical_release_sha256` | yes | a directory whose tree digest is the name |
| `kitpip_sha256` | no | a file. Null when the job has no avatar |
| `denylist_sha256` | no | a file. Required by intake when the manifest declares `never_name`, binds a `denylist_sha256` or a pin is set. `ip_private` alone needs none (J168) |

The tree digest is the sha256 of the sorted lines `relative path NUL sha256 LF` over every regular file. A symlink
anywhere refuses `input_symlink`. A FIFO, socket or device refuses `input_irregular` before any file is read. A
missing input refuses `input_missing`, and a changed one refuses `input_digest_mismatch`.

`check --inputs` first compares `VIDEO_UTILS_COMMIT` with `video_utils_commit` and refuses `commit_unknown` or
`commit_mismatch`. A worker on another commit or a dirty image therefore stops before intake, the GPU window or
compose writes anything.

### Binding inputs to the job

`verify_inputs` proves what was mounted. `result` proves what intake read. The intake phase writes its `--out` at
`JOB/intake` in the job's store directory, and `init --from` reads `JOB/intake/narrated-video.json`. `intake.json`
records the bundle's `manifest_sha256`, the tree digest of the records directory it read (`inputs.records_sha256`)
and the denylist digest the guard read. `result` refuses `input_binding_mismatch` unless all of these hold:

- `narrated-video.json` hashes to the digest `intake.json` holds, and the store's `job.json` is that record;
- the intake's job id and edition are the request's;
- the intake's bundle manifest, records tree and denylist digests are the request's.

A missing intake refuses `intake_missing` and an unreadable one `intake_invalid`. The result names `intake_sha256`
and, for each input, how it is bound:

| Input | Bound by | Meaning |
| --- | --- | --- |
| `bundle_manifest_sha256`, `records_sha256`, `denylist_sha256` | `intake` | `intake.json` records the digest it read |
| `lexical_release_sha256` | `records_pin` | the bound records pin the release file by file, and the script stage re-hashes those files |
| `engine_record_sha256`, `kitpip_sha256` | `mount_only` | only `verify_inputs` checked it. No later phase records reading it |

## Phases

| Phase | GPU | Runs | Output |
| --- | --- | --- | --- |
| `verify_inputs` | no | `render-stage check --inputs` | none |
| `claims_gate` | no | `narrate video claims` on the bundle | the claims report. A number no claim backs refuses here |
| `intake` | no | `narrate video intake --out JOB/intake` with the bundle, the records and the denylist, then `init --from` | the job, its narrate jobs and `JOB/intake/intake.json` |
| `preflight` | no | `render-stage preflight JOB --request R --records JOB/intake/records` | `JOB/intake/preflight.json` by digest. A slide in the avatar box, a slide that changed or left the store, a letterboxed slide or an `intake.json` that disagrees with the job refuses here |
| `voice_takes` | no | `render-stage takes`, `mixed` only, before any GPU spend | one action per segment |
| `voice_plan` | no | `narrate plan`, the AudioCppBatch requests | a plan directory and its digest |
| `voice_gpu` | yes | the lease helper's `run`, then `audiocpp_batch.py run` inside it | WAVs and a batch receipt by sha256 |
| `voice_render` | no | `narrate render --prerendered` | a narrate run with its `content_sha256` |
| `voice_adopt` | no | `narrate video stage JOB voice --from-run` for each segment | the voice nodes |
| `voice_ready` | no | `render-stage takes --after-window`, `mixed` only. `ready` must be true | one action per segment |
| `compose` | no | `narrate video run JOB --until deliver_check` | every stage up to `deliver_check` |
| `collect` | no | `render-stage result --export` | the cut, the report and the result by sha256 |

A `from_run` request skips `voice_plan`, `voice_gpu` and `voice_render`. It adopts runs already rendered and names
each by `content_sha256`. The result refuses `voice_run_mismatch` when the voice nodes hold other runs. A
`mixed` request scopes those three phases to the segments it voices, and each of their rows lists them under
`segments`. A `rerun` request re-intakes with `--replace`. A `compose_only` rerun also skips `voice_adopt`.

Every request runs `claims_gate`, `intake` and `preflight` first, so a planted fault refuses before any GPU
spend. The two gates that read the voice or the mix stay after it: `voice_qa` and `deliver_check`. This order is the
plan's. `result` proves that a preflight passed for this job and intake, and it does not prove when, so the caller
must run the phases in plan order and refuse voice work without a passed preflight.

No phase name matches the cade-infra `SEND_TASKS` pattern. If Cade maps phases to Hatchet tasks one to one, the
names stay as they are.

## Reruns

TIN-7125 `3672cb05` rules that a rerun keeps the same job folder and resumes by a new event, stops after 3 FIX rounds
to ask the operator, and holds a spend cap per GPU window with no number set.

A rerun event is a request with a new `run_id`, the same `job_id` and a `rerun` block. It runs on the same job root, so
every stage whose key held stays fresh. Its order is:

1. `narrate video intake --out JOB/intake --replace`. The new intake passes every check first. Only then does the
   earlier one move to `JOB/history/intake--<time>`. A refusal leaves the earlier intake current, and a failed swap
   moves it back. `--replace` takes only a directory that holds an `intake.json`, and refuses `job_mismatch` when that
   intake wrote another job.
2. `init --from JOB/intake/narrated-video.json --replace`.
3. `render-stage preflight`. The earlier `preflight.json` moved to history with its intake, so `result` refuses
   `intake_missing` until this phase runs on the new intake.
4. `narrate video run JOB --until deliver_check` runs what the new job changed, and a resume runs what the last event
   left.
5. `render-stage result` records the render in `JOB/rerun.json` and reports it.

A resume after a crash uses `{scope: any}`, because `JOB/intake` already exists and a plain intake refuses
`out_exists`.

### Compose-only proof

`current.json` counts every commit of a job root, and each stage entry holds the `seq` of its own commit. `result`
records one row per event in `rerun.json`, with the stage keys and that counter, and returns `rerun`:

| Field | Value |
| --- | --- |
| `event`, `previous` | this `run_id`, and the previous render's `run_id` and `video_sha256`. `previous` is null on a job root with no render recorded |
| `ran` | every node committed since the previous render, in commit order. It reads `seq`, never a time. With no previous render it reaches back to the root's first commit |
| `changed_keys`, `repeated` | the nodes whose key moved, and the nodes that ran with the key they already held. Only `run --force` does the second |
| `unchanged_nodes` | how many current nodes did not run |
| `compose_only` | true when something ran and every node of it is `compose`, `deliver_check` or `handoff` |
| `fix` | `rounds`, `cap`, `left` and `answers_round`, the FIX round this render answers |

A `{scope: compose_only}` request turns that into a refusal. `result` refuses `rerun_not_compose_only` when any other
node ran, `rerun_no_previous` with no earlier render and `rerun_no_change` when nothing ran. A refused `result` records
nothing. The test `test_one_slide_rerun_on_the_same_root_runs_only_compose_and_deliver_check` runs the synthetic bundle
through the real stages and swaps one slide. Only `compose` and `deliver_check` run.

A second `result` for the same event, request and render is a no-op that reads the proof against the same previous
render. The same event with another request or render refuses `rerun_event_reused`, because a resume is a new event.
The request is compared by the `request_sha256` its row holds, so a reused event cannot pass another scope or packet.

### FIX rounds

`narrate video fix JOB --decision sp:dec:<ulid> --video-sha256 V` records the operator's FIX of the current cut. Cade
is meant to call it where it calls `nv accept`, and that side is not wired (R10). The forms and `resolution: form_only` are `nv accept`'s. A round stores ids
and digests. FIX notes stay with Cade.

The fourth FIX on a job root refuses `fix_cap_reached` with nothing recorded, so the caller stops and asks the
operator. Rounds count per job root and so span packets, because a producer's fix arrives as a new packet on the same
root. Cade's own cap counts FIX cuts per packet (`docs/DEMO_DELIVERY.md`). The rest of the refusals:

| Refusal | When |
| --- | --- |
| `video_mismatch` | the decision names another cut than the current composed video |
| `fix_already_recorded` | this cut's round holds another decision. The same decision is a no-op, `recorded: false`, and that holds at the cap |
| `fix_extend_unneeded` | `--extend` on a job root that still has rounds left |
| `decision_bound_elsewhere` | the decision already held a round on any job under the store root, or accepted a gate of another cut or job |
| `cut_accepted` | the operator already accepted a gate of this cut |

A decision binds one cut of one job, whether it was a GO or a FIX. `fix` and `nv accept` read every job's
`rerun.json` and `acceptance.json` under the store root, under one root lock. An unreadable record of any job refuses.

A round binds its cut for good. `nv accept` refuses that cut with `cut_sent_back`, and with `decision_bound_elsewhere`
when the decision is the FIX itself. `result` refuses `fix_unchanged_cut` for a cut any round sent back, not only the
last one, so the cut never records. A FIX needs no render row, because it binds the current composed video, so the same
holds on a job root with no render recorded. `result` reports in `answers_round` the last round no render has answered.

The operator's answer at the cap extends the job root by one round per decision, each recorded (TIN-7125 `11296de3`).
`fix --extend` takes that decision: it adds the one round it uses, and its row says `extended: true`, so a grant cannot
wait for a later cut. A fourth FIX without `--extend` still refuses `fix_cap_reached`.

### Machine rounds

A round can also start from a gate's findings, with no Softproxy decision, on a job bound to a campaign (TIN-7125
`52ca88bf`, `0690fe88`). Nothing calls this yet, and no Hatchet row runs it.

`narrate video campaign-bind JOB --campaign ID` writes the binding into `rerun.json`. Its id's form is checked here, and
that a signed campaign record holds it is the caller's check. It refuses `campaign_client_job` for a client edition and
`campaign_after_decision` for a root that holds an operator's FIX or acceptance. A job with no binding keeps its
decision, whatever its edition, because a demo bundle's job is `Internal`.

`narrate video round JOB --findings FILE [--video-sha256 V]` reads a typed report (`docs/spec/NARRATED_VIDEO.md`,
"Findings") and returns one of two results:

| `result` | Means |
| --- | --- |
| `round` | a row in `fixes` with `decision: null`, `resolution: machine`, the campaign, the findings by digest and code count, `reach` and `seq`, the store's commit counter |
| `parked` | the job root used its 3 rounds. A `parked` record holds the last findings by digest, the exit code is 0 and nobody is asked. Every later `round` on that root returns `parked`, and a person may still `fix --extend` it |

A machine round counts against the same 3 rounds and binds its cut the same way, so `nv accept` and `result` refuse a cut
it sent back. `reach` is `graph.reach` of the stages the findings' codes enter at. The render that answers the round
refuses `round_out_of_reach` when any other stage committed after `seq`, so a fix of a slide, which enters at `compose`,
cannot re-voice. That holds on a cut with no render row. A round that named no cut, on a root with no render, has nothing
to compare, because the next run is the whole job.

| Refusal | When |
| --- | --- |
| `findings_invalid` | the file is not a typed report, or a row's code, gate or stage is not one short token |
| `round_needs_decision` | a client edition, or a job root with no campaign bound |
| `round_no_findings` | no row blocks. A lexical finding alone is advisory |
| `findings_stale` | the report names another job or an older `job.json` |
| `round_video_missing` | a finding only a composed cut can show names no cut: profile, loudness, flash, captions, an avatar frame or a slide's layer or shown share |
| `video_mismatch` | as for `fix`, or `--video-sha256` names another cut than the report read |
| `cut_accepted`, `fix_already_recorded` | as for `fix` |

A report that names `job_id`, `job_sha256` or `video_sha256`, as `narrate video findings` does, binds them. The same
findings on the same cut again are a no-op, `recorded: false`. A machine round closes no operator gate.

### Mixed takes

`from_run` adopts every segment and `gpu_window` voices every segment. `{mode: mixed, runs}` names each segment: a
`content_sha256` keeps or adopts that take, and null voices the beat in this window. It holds at least one of each
(`voice_mixed_invalid`) and needs the window's Lease and spend cap.

`render-stage takes` reads the plan and gives each segment one action. The `voice_takes` phase runs it before any GPU
spend, and `voice_ready` runs it with `--after-window`, after `voice_adopt`.

| Action | Means |
| --- | --- |
| `keep` | the fresh voice node holds the named take |
| `adopt` | the node is stale, so `voice_adopt` brings in the named take |
| `revoice` | the node is stale and the request voices the beat |
| `revoiced` | `--after-window` only: the node is fresh and was committed since the last render |

`takes` refuses these, and each refusal before a window comes before any spend:

| Refusal | When |
| --- | --- |
| `revoice_unneeded` | a beat named null is fresh. Before a window this holds for every fresh beat, even one committed since the last render, and on a root with no render. With `--after-window` it holds only for a beat not committed since the last render |
| `voice_run_mismatch` | a fresh node holds another run than the request names, or a stale node holds the run the request names, so that take no longer fits the beat |
| `voice_runs_invalid` | the names are not the job's segments |
| `voice_blocked` | a voice node is blocked or refused |

`ready` is true when every action is `keep` or `revoiced`. A resume whose takes are already in names them, or uses
`from_run`, because a null on a fresh beat refuses. A `gpu_window` request names no runs, so any fresh beat refuses
`revoice_unneeded`, and a job with some fresh beats takes `mixed`.

Each adopted run still passes every check in "Adopting a rendered run" in `docs/spec/NARRATED_VIDEO.md`. Those checks
read the run, so they run at `voice_adopt`, after `voice_gpu`. Only the two take checks above come before the window: a
take the node never held and that fails adoption spends the window first.

### Spend cap

A window names `spend`, with no default number. `window_cap_usd_cents` is a positive integer and
`rate_usd_cents_per_hour` an integer that may be 0, as an on-prem window's is. The window is time-capped, so its
ceiling is `lease.max_seconds` at that rate, rounded up to a cent. A ceiling over the cap refuses
`spend_cap_exceeded` before the window starts, so a cap never stops a window partway. The `voice_gpu` plan row shows
the cap, the rate and `ceiling_usd_cents`. No receipt binds the real spend yet.

## Lease protocol

**v1 runs no GPU window.** A `gpu_window` or `mixed` request refuses `gpu_window_not_v1` in `check` (and so in
`verify_inputs`), in `takes` and in `result`. Only `--gpu-draft` on `check` or `takes` reads one, and that flag never
goes with `--inputs`. Two
gaps keep it closed. Nobody posts the TIN-5397 notice for Cade yet (R3), and no result binds the helper's run receipt
or the batch receipt. A later version needs `lease.receipt_sha256` and `batch_receipt_sha256` in a `gpu_window`
result before it can lift the refusal. The protocol below is the design that version follows.

The task body never takes, reads or writes the GPU Lease. The estate lease helper holds custody. It does a
compare-and-swap acquire, runs one command, passes a GPU census gate and then releases in its own `finally`. This
repository names the helper only by the sha256 the request pins.

1. **Holder.** The `render` worker makes a holder with `just narrate-holder`
   (`narrate/serve/finalize.py holder`). The form is `narrate-bench-YYYYMMDD-sHHMMSS`, the only narrate form the
   Lease guard admits. The worker writes the holder and the run id into the job ledger before anything else. The
   request refuses any other form with `lease_holder_form`. A test keeps this module's form equal to `finalize.py`'s.
2. **Notice.** Before the acquire, Cade posts a TIN-5397 notice comment. It names the holder, the run id and the
   window cap, and no host. The request carries that comment's id. Without one the request refuses
   `lease_notice_missing`. This check has resolution `form_only`, as `nv accept` labels its decision ids: it checks
   the ticket and that the id is UUID-shaped. It never reads Linear, so it does not prove that the comment exists
   or names the holder. Cade's `voice_gpu` must check both before the acquire. The draft plan lists them under
   `verify_before_run`.
3. **Window cap.** `lease.max_seconds` is at most 1800, the 30-minute window `docs/spec/NARRATE.md` sets. The
   helper's `--max-seconds` takes this value. `audiocpp_batch.py --deadline-s` stays under it.
4. **Helper pin.** This module checks only that `lease.helper_sha256` is sha256-shaped (`form_only`). It hashes no
   helper. Cade's `voice_gpu` hashes the helper before it runs it. A helper that differs from
   `lease.helper_sha256` does not run, and the window does not start.
5. **Run.** The window is one helper `run` with `--holder H`, `--duration` of `max_seconds` plus 420,
   `--max-seconds`, `--census-cmd`, `--receipt` and `--execute`. Its command is `audiocpp_batch.py run ...
   --lease-holder H`, with `finalize.py` beside it. This is the argv that xoxd-ai/cade `leaseRunArgv` builds for
   the client-video service.
6. **Preempt.** A ringing call preempts the window. The host that runs the helper calls the helper's
   `finalize --holder H --reason preempted --call-id ID`. The runner stops the engine and writes its receipt. The
   helper then passes its census gate and releases. Hatchet cancellation of the GPU task maps to that finalize and
   never to SIGKILL, because SIGKILL of the helper skips the release.
7. **Release and receipt.** The helper's run receipt is the truth. Cade records its digest in the ledger and
   replies on the notice comment with its `outcome`.
8. **Resume.** A later tick takes a new holder and posts a new notice. It runs `audiocpp_batch.py run --only-missing`
   against the same plan digest, so finished WAVs stay.

Cade classifies the window from the helper's run receipt, not from an exit code, because the helper passes a clean
run's command exit through. The hardware render reuses the client-video lifecycle as merged in xoxd-ai/cade
(`docs/CLIENT_VIDEO_SERVICE.md`, "Run states and failure states", and `runFactsFromReceipt`). A receipt it cannot
read counts as `release-unknown`. In summary:

| Receipt outcome | State | Next |
| --- | --- | --- |
| `released` with command exit 0 | Rendered | `voice_render` |
| `released` and preempted | Preempted | requeue after the call with a new holder, up to the deferral cap |
| `released` with command exit 1 or 20 | Partial or TimeCapped | requeue with `--only-missing` while windows remain |
| `not-acquired` | LeaseBusy | retry later. Not a failure |
| `acquire-unknown`, `census-failed-lease-kept` or `release-unknown` | NeedsReconcile | dead-letter with one operator-class notice. No retry and no takeover |
| `refused`, `refused-input`, command exit 2, helper exit 127 or any other exit | Refused or Failed | stop and alert |

The client-video contract lets `maxSeconds` reach 6780. The hardware render keeps the 1800-second cap of
`docs/spec/NARRATE.md`, which is the stricter of the two.

An expired holder is still a holder. The worker never treats expiry as permission to take over.

## Placement

| Part | Where | Why |
| --- | --- | --- |
| CPU phases | the worker image below, as a pod in Cade's tenant or a transient scope of Cade's worker | no GPU and no private bits in the image |
| GPU window | the GPU host's host batch path, under the lease helper | the census reads the host's GPU processes and device holders. `finalize.py` waits for a local helper ancestor. Both need the host's `/proc` |

The demo DAG design puts every stage in a pod by default. The GPU window cannot run in the CPU pod for the reasons
in the table. A GPU pod under the `deploy/narrate-bench/` contract is the later path. It needs a census that works
from the cluster and a grant for Cade's worker to run the owner's window runner. Which path Cade's first demo uses is
an open decision for the GPU host's owner and the operator.

## Worker image

`nix build .#cade-render-worker-image` (`deploy/cade-render-worker/image.nix`) builds a docker-archive. It holds:

- Python 3, FFmpeg 8.1.2 and whisper.cpp 1.8.4 from the condense nixpkgs pin, the tools the narrate recipes use;
- bash, coreutils, findutils, GNU tar and util-linux;
- this repository's `narrate/`, the condense Python modules and `program/` at the flake's revision, under
  `/share/video-utils`. The narrate tests are left out;
- user 10001, the working directory `/work` for the stage store, empty `/inputs` and `/out`, and the entrypoint
  `python3 -s -B -m narrate video render-stage`. `/work` and `/out` belong to 10001:10001 in the image, so the
  worker can write them without a volume. A volume mounted over either must be writable by uid 10001, for example an
  `emptyDir` or a directory that 10001 owns. `/inputs` stays read-only.

It holds no GPU binary, model, record, voice clip, consent, denylist, kitpip binary or credential. The flake's
revision is baked into `VIDEO_UTILS_COMMIT`. A dirty tree has no revision, so `verify_inputs` and every result
from that image refuse `commit_unknown`. The image is built on demand and never by `just check`. This repository
pushes no image. No container has run from it yet. The layer ownership was read from the built archive, not
observed at runtime.

## Result

A result is `narrate_render_stage_result` at schema version 1. It holds no path.

| Field | Value |
| --- | --- |
| `run_id`, `packet_id`, `job_id`, `request_sha256` | the request's ids and the canonical digest of the request |
| `video_utils_commit`, `worker_image` | the request's pins. The commit was checked against the worker's own. Cade binds the image digest from the pod or unit that ran the task |
| `job_sha256` | the digest of `job.json` that `deliver_check` keyed on |
| `voice` | the mode and each segment's narrate `content_sha256` |
| `rerun` | what ran since the previous render and the FIX count (see "Compose-only proof") |
| `intake_sha256`, `inputs_bound_by` | the digest of the job's `intake.json` and how each input is bound (see "Binding inputs to the job") |
| `preflight_sha256` | the digest of the job's `preflight.json`. A missing one refuses `intake_missing`, one of another schema version `intake_invalid`, one for another job or `intake.json` `preflight_stale` and one with findings `preflight_failed` |
| `lease` | null in v1. Only `from_run` results pass, so no Lease attests the voice |
| `outputs.video_sha256` | the composed cut |
| `outputs.deliver_check` | the stage key, the content digest and `report_sha256` of `deliver_check.json` |
| `outputs.stages` | every current node's content digest |
| `deliver_check` | the gates, `delivery_gate`, `machine_passed`, `frame_review` and the gates still `pending_operator`. `frame_review` is `{unchecked, exempt}`, the page ids no frame gate read. Those pages do not fail `machine_passed`, so Cade must show them to the person who gives the GO (`docs/spec/NARRATED_VIDEO.md`, "Frame gates") |

`result` reads the current render through the same check `nv accept` uses. A `deliver_check` that ran for another
`job.json`, or did not read the current compose, refuses `deliver_check_stale`. A node that fails re-hashing refuses
`stage_corrupt`. `deliver_check` must hold all six machine gates (`profile`, `loudness`, `flash`, `captions`, `avatar_box` and
`slide_match`, `accept.AUTOMATED`), and its `delivery_gate.machine_gates_passed` must agree with them. Otherwise the
result refuses `deliver_check_invalid`. `machine_passed` is true only when every one of the six passed or does not
apply.
`--export` copies by sha256 and re-hashes each copy. A file already there, the result's own JSON included, is
re-hashed, and other content refuses `export_conflict`. A second export of the same result is a no-op.

`deliver_internal` serves the exported `<video_sha256>.mp4`. The served file's sha256 must equal
`outputs.video_sha256`, which is criterion A7 of the demo DAG.

## Open

| Id | Question | Owner |
| --- | --- | --- |
| R1 | GPU window placement for the first demo: host batch path or a GPU pod | the GPU host's owner, then the operator |
| R2 | Which field of the producer's `handoff.json` carries the bundle digest that `bundle_manifest_sha256` takes | Cade and the template owner |
| R3 | Who posts the TIN-5397 notice for Cade before the Cade Linear app exists. Until then v1 refuses `gpu_window`, and only `from_run` requests pass | Cade |
| R8 | Whether `intake` should also record the engine record and kitpip digests it read, so that they are bound like the bundle. Today they are `mount_only` | this repository |
| R4 | Where the hash-pinned VoxCPM2 batch body and its weights live for Cade's worker (P7) | the kit owner |
| R5 | Multi-clip bundles. Intake refuses a second MP4 until P18 | this repository |
| R10 | Whether Cade's FIX cap moves from per packet to the job root's count, and when Cade calls `nv fix`. The Cade side is not wired | Cade |

## Limits

- No test runs a GPU window, the lease helper, FFmpeg or a model. The tests use a fake stage runner, as the accept
  tests do.
- `rerun.json` carries no signature. A hand edit or a deleted file resets the FIX count on this side, so a reader that
  needs the count to hold compares it with its own ledger. A hand edit can also add a campaign binding, so a caller
  that starts a round checks the campaign against its own signed record first.
- `nv accept` does not read `rerun.json`, so a FIX does not stop a later accept of the same cut. `nv fix` refuses a cut
  with an acceptance, but only one direction is checked.
- `result` refuses a `mixed` request until the Lease gaps close, so a real mixed run has no result yet. The tests prove
  `takes` and the keys. A fake engine stands in for the window.
- `check --inputs` proves that the mounted inputs match the request. It does not prove where the request came from.
  Cade's `verify_packet` checks the packet signature first.
- `machine_passed` reads the six machine gates. It closes no operator gate. Listening and lip sync close only through
  `nv accept` with a Softproxy decision id.
