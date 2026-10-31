# Render stage of the Cade demo DAG

Linear TIN-7788, demo DAG item P9 and the render half of P6. Ruling R-HOOK-CONVERGENCE-20261004. Status: a draft
contract, a task body and an image recipe. No GPU window ran for it, no Lease was taken and no image was pushed.

Cade's `cade-hardware-handoff` workflow renders a demo from a signed producer packet. This document covers the part
of that workflow that runs this repository's tools. It starts after `bs21_privacy_guard` and `readiness_check` pass
and ends when `deliver_check` has run. Delivery is the next task, `deliver_internal`, and lives in Cade.

```
claim_job -> verify_packet -> assets_build -> bs21_privacy_guard -> readiness_check
  -> [render stage: verify_inputs -> intake -> voice_plan -> voice_gpu (Lease) -> voice_render -> voice_adopt
      -> compose ... deliver_check -> collect]
  -> deliver_internal
```

The task body is `python -m narrate video render-stage` (`narrate/video/render_stage.py`). It has two actions:

| Action | What it does | Writes |
| --- | --- | --- |
| `check --request R [--inputs DIR]` | Validates the request and prints its phases. With `--inputs`, it re-hashes every input at `DIR/<sha256>` | nothing |
| `result JOB --request R [--export DIR]` | Reports a job that ran to `deliver_check`, every output by digest. With `--export`, it copies the cut, the report and the result into `DIR` under their sha256 names | `DIR/<sha256>.mp4`, `DIR/<sha256>.json` |

The recipes are `just nv-render-stage-check` and `just nv-render-stage-result`. The phases between them run the
existing commands: `narrate video intake`, `narrate plan`, `narrate render --prerendered`,
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
| `edition` | `Internal`. A client or KSL edition waits for its own tenant | `edition_not_v1` |
| `video_utils_commit` | 40 hex. The worker's own commit must match it | `commit_invalid` |
| `worker_image` | `sha256:<64 hex>`, the OCI digest the task ran in | `image_invalid` |
| `inputs` | digests, listed below | `digest_invalid`, `inputs_keys` |
| `voice` | `{mode: gpu_window, runs: null}` or `{mode: from_run, runs: {segment: narrate content_sha256}}` | `voice_invalid` and the codes below |
| `lease` | the window's Lease binding with `gpu_window`. Null with `from_run` | `lease_missing`, `lease_unneeded` |
| `until` | `deliver_check` | `until_invalid` |

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
| `denylist_sha256` | no | a file. Required by intake when the manifest declares `ip_private` or `never_name` |

The tree digest is the sha256 of the sorted lines `relative path NUL sha256 LF` over every regular file. A symlink
anywhere refuses `input_symlink`. A missing input refuses `input_missing`, and a changed one refuses
`input_digest_mismatch`.

## Phases

| Phase | GPU | Runs | Output |
| --- | --- | --- | --- |
| `verify_inputs` | no | `render-stage check --inputs` | none |
| `intake` | no | `narrate video intake` with the bundle, the records and the denylist | the job and its narrate jobs |
| `voice_plan` | no | `narrate plan`, the AudioCppBatch requests | a plan directory and its digest |
| `voice_gpu` | yes | the lease helper's `run`, then `audiocpp_batch.py run` inside it | WAVs and a batch receipt by sha256 |
| `voice_render` | no | `narrate render --prerendered` | a narrate run with its `content_sha256` |
| `voice_adopt` | no | `narrate video stage JOB voice --from-run` for each segment | the voice nodes |
| `compose` | no | `narrate video run JOB --until deliver_check` | every stage up to `deliver_check` |
| `collect` | no | `render-stage result --export` | the cut, the report and the result by sha256 |

A `from_run` request skips `voice_plan`, `voice_gpu` and `voice_render`. It adopts runs already rendered and names
each by `content_sha256`. The result refuses `voice_run_mismatch` when the voice nodes hold other runs.

No phase name matches the cade-infra `SEND_TASKS` pattern. If Cade maps phases to Hatchet tasks one to one, the
names stay as they are.

## Lease protocol

The task body never takes, reads or writes the GPU Lease. The estate lease helper holds custody. It does a
compare-and-swap acquire, runs one command, passes a GPU census gate and then releases in its own `finally`. This
repository names the helper only by the sha256 the request pins.

1. **Holder.** The `render` worker makes a holder with `just narrate-holder`
   (`narrate/serve/finalize.py holder`). The form is `narrate-bench-YYYYMMDD-sHHMMSS`, the only narrate form the
   Lease guard admits. The worker writes the holder and the run id into the job ledger before anything else. The
   request refuses any other form with `lease_holder_form`. A test keeps this module's form equal to `finalize.py`'s.
2. **Notice.** Before the acquire, Cade posts a TIN-5397 notice comment. It names the holder, the run id and the
   window cap, and no host. The request carries that comment's id. Without it the request refuses
   `lease_notice_missing`.
3. **Window cap.** `lease.max_seconds` is at most 1800, the 30-minute window `docs/spec/NARRATE.md` sets. The
   helper's `--max-seconds` takes this value. `audiocpp_batch.py --deadline-s` stays under it.
4. **Helper pin.** The worker hashes the helper before it runs it. A helper that differs from
   `lease.helper_sha256` does not run, and the window does not start.
5. **Run.** The window is one helper `run` with `--holder`, `--duration`, `--max-seconds`, `--census-cmd` and
   `--execute`, whose command is `audiocpp_batch.py run ... --lease-holder H` with `finalize.py` beside it.
6. **Preempt.** A ringing call preempts the window. The preempt watcher calls
   `finalize.py finalize --holder H --reason preempted --call-id ID`. The runner stops the engine and writes its
   receipt. The helper then passes its census gate and releases.
7. **Release and receipt.** The helper's receipt is the truth. The worker records its `outcome` and `rc_source` in
   the ledger and replies on the notice comment with the outcome.
8. **Resume.** A later tick takes a new holder and posts a new notice. It runs `audiocpp_batch.py run --only-missing`
   against the same plan digest, so finished WAVs stay.

| Helper exit | Meaning | Task outcome |
| --- | --- | --- |
| 0 | done, the command's own exit 0 | continue to `voice_render` |
| 1 | refused: held, CAS lost, owner changed or GPU busy before the acquire | re-queue with backoff. Not a failure |
| 2 | bad input | dead-letter. The request or the worker is wrong |
| 3 | needs reconciliation: release or acquire unknown, or the census gate kept the Lease | dead-letter with one operator-class notice. No retry and no takeover |
| 127 | the command did not start. The Lease is released | dead-letter |
| other | the command's own exit, per `rc_source` | `audiocpp_batch.py`'s exit 20 or a stop: resume on a later tick |

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
  `python3 -s -B -m narrate video render-stage`.

It holds no GPU binary, model, record, voice clip, consent, denylist, kitpip binary or credential. The flake's
revision is baked into `VIDEO_UTILS_COMMIT`. A dirty tree has no revision, so every result from that image refuses
`commit_unknown`. The image is built on demand and never by `just check`. This repository pushes no image.

## Result

A result is `narrate_render_stage_result` at schema version 1. It holds no path.

| Field | Value |
| --- | --- |
| `run_id`, `packet_id`, `job_id`, `request_sha256` | the request's ids and the canonical digest of the request |
| `video_utils_commit`, `worker_image` | the request's pins. The commit was checked against the worker's own. Cade binds the image digest from the pod or unit that ran the task |
| `job_sha256` | the digest of `job.json` that `deliver_check` keyed on |
| `voice` | the mode and each segment's narrate `content_sha256` |
| `lease` | the holder, or null |
| `outputs.video_sha256` | the composed cut |
| `outputs.deliver_check` | the stage key, the content digest and `report_sha256` of `deliver_check.json` |
| `outputs.stages` | every current node's content digest |
| `deliver_check` | the gates, `delivery_gate`, `machine_passed` and the gates still `pending_operator` |

`result` reads the current render through the same check `nv accept` uses. A `deliver_check` that ran for another
`job.json`, or did not read the current compose, refuses `deliver_check_stale`. A node that fails re-hashing refuses
`stage_corrupt`. `--export` copies by sha256 and re-hashes each copy. A file already there with other content refuses
`export_conflict`. A second export of the same result is a no-op.

`deliver_internal` serves the exported `<video_sha256>.mp4`. The served file's sha256 must equal
`outputs.video_sha256`, which is criterion A7 of the demo DAG.

## Open

| Id | Question | Owner |
| --- | --- | --- |
| R1 | GPU window placement for the first demo: host batch path or a GPU pod | the GPU host's owner, then the operator |
| R2 | Which field of the producer's `handoff.json` carries the bundle digest that `bundle_manifest_sha256` takes | Cade and the template owner |
| R3 | Who posts the TIN-5397 notice for Cade before the Cade Linear app exists. Until then only `from_run` requests can pass | Cade |
| R4 | Where the hash-pinned VoxCPM2 batch body and its weights live for Cade's worker (P7) | the kit owner |
| R5 | Multi-clip bundles. Intake refuses a second MP4 until P18 | this repository |

## Limits

- No test runs a GPU window, the lease helper, FFmpeg or a model. The tests use a fake stage runner, as the accept
  tests do.
- `check --inputs` proves that the mounted inputs match the request. It does not prove where the request came from.
  Cade's `verify_packet` checks the packet signature first.
- `machine_passed` reads the four machine gates. It closes no operator gate. Listening and lip sync close only through
  `nv accept` with a Softproxy decision id.
