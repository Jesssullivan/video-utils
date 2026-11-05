# Narrate GPU window: staging Job and window pod (reviewed files, not applied)

Linear TIN-7085, parent TIN-7084. Receipt
[`docs/agent-notes/2026-10-23-e3-gpu-bench-image.md`](../../docs/agent-notes/2026-10-23-e3-gpu-bench-image.md).
Authority R-HOOK-CONVERGENCE-20261004 (R-N11, R-N12, R-N13).

## Status (2026-10-27)

This is the later pod phase. The current path is the host batch path: phase B of an `AudioCppBatch` render
runs [`narrate/serve/audiocpp_batch.py`](../../narrate/serve/audiocpp_batch.py) as a host process on the GPU
host, inside the bounded window unit ([`docs/spec/NARRATE.md`](../../docs/spec/NARRATE.md), "Out-of-process
batch engines"). The pod runs the same script, unchanged, once its image exists. Until then these files are a
reviewed contract only.

The binary both paths pin is `audiocpp_cli` from `nix build .#narrate-bench-audiocpp`
([`narrate/bench/image/audiocpp.nix`](../../narrate/bench/image/audiocpp.nix)): audio.cpp `47c2756e` with the
Vulkan backend. Its sha256 is the `audiocpp_cli` entry of the engine record and the `--binary-sha256` the runner
checks.

## Apply boundary

**Nothing here has been applied, pushed or created on a cluster.** The GPU host's owner runs every cluster
step with the operator credential, under an operator GO for that window (or the operator's pre-approval of
an unattended window of 30 minutes or less once the build, weights and plan are green). Merging these
files is not that GO. No agent lane takes the GPU Lease, creates a pod, or pushes an image.

## What is here

| File | What it is |
|---|---|
| `stage-job.yaml` | NetworkPolicy (no ingress, no egress) and Job `models-stage-narrate-bench`, which receives the upload and checks it |
| `bench-pod.yaml` | Pod `narrate-bench-<window id>`, the input to the GPU-host owner's window runner. It runs `audiocpp_batch.py run` |

## The pod contract (the GPU-host owner's, enforced by their window runner)

- Namespace `models`, name `narrate-bench-<id>`. Labels `app.kubernetes.io/name: narrate-bench`,
  `part-of: narrate`, `component: bench`, `managed-by: narrate`, and no model-store or Lease-peer labels.
  The runner adds its run label and a per-run NetworkPolicy (no ingress, DNS egress only).
- `nodeSelector` is exactly the GPU node's `kubernetes.io/hostname`, filled in at apply time from the
  `__GPU_NODE__` placeholder. The node name never enters git. `restartPolicy: Never`,
  `activeDeadlineSeconds: 1800`, `automountServiceAccountToken: false`, `priorityClassName: gpu-exclusive`,
  `imagePullSecrets: [ghcr-pull]`.
- Pod Security restricted: `runAsNonRoot`, uid and gid 10001, `supplementalGroups: [105]` (the GPU node's
  render group, which owns the render node and kfd), `RuntimeDefault` seccomp. The one container has no
  privilege escalation, drops ALL capabilities, adds none, and has a read-only root filesystem. There are no
  init containers and no ports.
- The image is referenced by digest (`ghcr.io/...@sha256:...`) with `IfNotPresent`.
- Resources: `devic.es/dri: "1"` (exclusive), CPU request 2 (the node is near its request guard) and limit 4,
  memory 12Gi request equal to limit (quota 40Gi; LimitRange 32Gi per container).
- Volumes: the models PVC read-only at `/models` with no subPath; an `emptyDir` named `out` at `/out` (4Gi);
  an `emptyDir` at `/tmp` (2Gi) for HOME, XDG_CACHE_HOME and the Mesa shader cache.
- Behaviour: write everything to `/out/<window id>/`; print `NARRATE-BENCH-DONE rc=N`; sleep 600 s so that
  the runner can stream `/out` with `tar`.

Weights live at `/models/bench/narrate/hf/<repo>/<revision>/<path>`, with a `SHA256SUMS` in each `<revision>`
directory. A `narrate plan` directory (`requests/`, `refs/`, `plan.json`) lives at
`/models/bench/narrate/plans/<plan id>/`. The runner writes into its plan directory, so the pod copies the plan
to `/out/<window id>/plan` and runs there.

## Image

No image is built here. The later pod phase needs one, referenced by digest, that provides:

- `/bin/sh`, `/bin/tar`, coreutils (`sha256sum`, `sleep`, `cp`) and `find`;
- `python3` (3.9 or later) on `PATH`;
- `/bin/audiocpp_cli` from `.#narrate-bench-audiocpp`, with its closure, whose sha256 equals the engine record's;
- `/share/narrate/audiocpp_batch.py`, the file from this repository at the merged commit;
- the Mesa RADV ICD at `/share/vulkan/icd.d/radeon_icd.x86_64.json`, which `VK_DRIVER_FILES` names;
- a non-root user 10001.

The GPU-host owner asked for Mesa RADV 25.x or newer, because RDNA4 (gfx1201) support starts in Mesa 25.

## Answers from the GPU-host owner (2026-10-23, TIN-7085; teammate information)

- **Registry.** GHCR, under the owner's organisation. The image is pushed from repository CI and pulled by
  digest through Secret `ghcr-pull` in namespace `models`. Every pod and Job names that Secret, because the
  default ServiceAccount carries none. The owner's runner checks, before any write, that `ghcr-pull`
  resolves the digest.
- **Hugging Face from the cluster.** No. Namespace `models` has no internet egress, and adding one would need
  a new egress grant and its own operator ruling. The weights instead reach the volume from the CPU host's
  hash-checked copies: `just narrate-fetch --apply`, then a `tar` stream into the staging pod.
  The in-cluster model store is not used for the narrate weights.
- **Pod contract.** As summarised above. The render group is gid 105.

## Runbook

`$W` is narrate-fetch's weights directory and `$U` the upload tree. Both sit on the CPU host, outside any
checkout; none of their contents enter git.

### Render the specs (operator, CPU host, at apply time)

The templates hold placeholders: `__WINDOW_ID__`, `__GPU_NODE__`, `__MODELS_PVC__`, `__IMAGE__`,
`__PLAN_ID__`, `__VOICE__`, `__MODEL_FILE__`, `__MODEL_SHA256__` and `__BINARY_SHA256__`. Each is invalid as
written, so an unrendered spec fails validation. The values live only in the rendered copies under `$U`.

```
render() { sed -e "s|__WINDOW_ID__|$WINDOW_ID|g; s|__GPU_NODE__|$GPU_NODE|g; s|__MODELS_PVC__|$MODELS_PVC|g" \
               -e "s|__IMAGE__|ghcr.io/$IMAGE_PATH@$DIGEST|g; s|__PLAN_ID__|$PLAN_ID|g; s|__VOICE__|$VOICE|g" \
               -e "s|__MODEL_FILE__|$MODEL_FILE|g; s|__MODEL_SHA256__|$MODEL_SHA|g" \
               -e "s|__BINARY_SHA256__|$BINARY_SHA|g" "$1"; }
render deploy/narrate-bench/bench-pod.yaml > "$U/bench-pod.yaml"
render deploy/narrate-bench/stage-job.yaml > "$U/stage-job.yaml"
grep -n '__[A-Z0-9_]*__' "$U"/*.yaml && echo "unrendered placeholder" >&2
```

### Stage (before the window; no GPU, no Lease)

1. **Operator, CPU host:** fetch the weights with `just narrate-fetch --apply`, write the plan with
   `just narrate-plan job.toml "$U/plans/$PLAN_ID" --confidential`, and lay the weights out under
   `$U/hf/<repo>/<revision>/` with a `SHA256SUMS` in each revision directory.
2. **Owner:** apply the rendered `stage-job.yaml`, then wait for the pod to report Running.
3. **Operator, with the owner's kubeconfig:** stream the tree in, then write the marker.

   ```
   POD=$(kubectl -n models get pod -l job-name=models-stage-narrate-bench -o name)
   tar -C "$U" -chf - hf plans | kubectl -n models exec -i "$POD" -- tar -C /models/bench/narrate -xf -
   kubectl -n models exec "$POD" -- sh -c ': > /models/bench/narrate/.upload-complete'
   kubectl -n models logs -f job/models-stage-narrate-bench       # ends with NARRATE-STAGE-DONE rc=0
   ```

   The `-h` flag sends files, not symlinks. `rc=0` means every weight matched its `SHA256SUMS` and every
   requests file passed `audiocpp_batch.py check`.

### Window (30 minutes or less; the owner's runner)

4. **Owner, dry run:** the owner's window runner with `--pod-spec "$U/bench-pod.yaml"`. It validates the
   contract and runs the read-only preflight (Lease empty, no `devic.es/dri` holder, CPU and memory guards,
   quota, PVC, the pull Secret resolving the digest, and a server-side dry-run create). It writes nothing.
5. **Operator:** GO, and the TIN-5397 notice posted.
6. **Owner:** the same command with `--execute`. The runner does the Lease compare-and-swap, the
   NetworkPolicy, the pod and the wait for `NARRATE-BENCH-DONE`. It then collects `pod.log`, `events.json` and
   `bench-out.tar` (that is, `/out`), and deletes the pod and policy in a `finally` before it releases the Lease.
7. **Owner:** post the runner's `receipt.json` to TIN-7085. **Operator:** copy `bench-out.tar` to the CPU
   host's private runs directory.

### After the window

8. Phase C on the CPU host: `just narrate-render job.toml --prerendered PLAN --confidential` against the
   collected plan directory.
9. **Owner:** remove `/models/bench/narrate/plans/` from the volume, because its `refs/` hold the consented
   reference clip. Delete the finished staging Job.

## Hard stops

`audiocpp_batch.py` refuses (exit 2) a request whose id is not its content's digest, a reference that does not
match the sha256 in its name, and a binary or weights whose sha256 differs from the pin. It stops the runtime
at `--deadline-s` (`NARRATE_WINDOW_S`, 1500 s) and after 120 s in which neither its log nor its output directory
grew (exit 20). `activeDeadlineSeconds: 1800` ends the pod whatever the script does, and the owner's runner
deletes it after collection.

## What a run writes

Everything goes under `/out/<window id>/plan/`, as on the host path: `wav/<id>.wav` for every finished,
complete take, `receipts/<voice>.json` (schema `narrate-audiocpp-batch-receipt/1`: the requests and reference
sha256 values, binary and weights sha256, exit code, stop rule, times and every output's sha256), and
`logs/<voice>.log`. Missing outputs are listed, never invented. `--only-missing` finishes a stopped batch in a
later window.
