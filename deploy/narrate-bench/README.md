# Narrate GPU-host bench: image, staging Job and window pod (reviewed files, not applied)

Linear TIN-7088 (GPU half), parent TIN-7084; bench preregistration
[`docs/agent-notes/2026-10-22-narrate-bench-plan.md`](../../docs/agent-notes/2026-10-22-narrate-bench-plan.md);
receipt [`docs/agent-notes/2026-10-23-e3-gpu-bench-image.md`](../../docs/agent-notes/2026-10-23-e3-gpu-bench-image.md).
Authority R-HOOK-CONVERGENCE-20261004 (R-N11, R-N12, R-N13).

This is the pod path. The operator's 2026-10-23 ruling runs the first bench as a host process on the GPU
host (`narrate/bench/run-bench.sh`); the pod path becomes the standard one afterwards. Both render the same
shared chunk list (`narrate/bench/chunks-v1.json`).

## Apply boundary

**Nothing here has been applied, pushed or created on a cluster.** The GPU host's owner runs every cluster
step with the operator credential, under an operator GO for that window (or the operator's pre-approval of
an unattended window of 30 minutes or less once builds, weights, clips and decoys are green). Merging these
files is not that GO. No agent lane takes the GPU Lease, creates a pod, or pushes the image.

## What is here

| File | What it is |
|---|---|
| [`../../narrate/bench/image/default.nix`](../../narrate/bench/image/default.nix) | The OCI image (`nix build .#narrate-bench-image`): audio.cpp `47c2756e` and qwentts.cpp `5916bf7c` with the Vulkan backend, the Vulkan loader, Mesa (RADV, plus lavapipe), Python, `sh` and `tar`, non-root user 10001 |
| [`../../narrate/bench/image/bench_arm.py`](../../narrate/bench/image/bench_arm.py) | `narrate-bench-arm`: `run`, `check`, `versions`, `verify`, `layout`, `receive`. `narrate-bench-window` wraps `run` with the done line and the linger |
| [`../../narrate/bench/image/jobs/`](../../narrate/bench/image/jobs/) | Job templates for A2-gpu-alt, D2-preset (decoy 2), A1-gpu and A3-gpu. Their hash and voice fields are placeholders that `layout` fills |
| `stage-job.yaml` | NetworkPolicy (no traffic at all) and Job `models-stage-narrate-bench`, which receives the upload and verifies it |
| `bench-pod.yaml` | Pod `narrate-bench-<window id>`, the input to the GPU-host owner's window runner |

## The pod contract (the GPU-host owner's, enforced by their window runner)

- Namespace `models`, name `narrate-bench-<id>`. Labels `app.kubernetes.io/name: narrate-bench`,
  `part-of: narrate`, `component: bench`, `managed-by: narrate`, and no model-store or Lease-peer labels.
  The runner adds its run label and a per-run NetworkPolicy (no ingress, DNS egress only).
- `nodeSelector` is exactly the GPU node's `kubernetes.io/hostname`. `restartPolicy: Never`,
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
- Behaviour: hash-check every model file at the start; write everything to `/out/<window id>/`; print
  `NARRATE-BENCH-DONE rc=N`; sleep 600 s so that the runner can stream `/out` with `tar`.

Weights live at `/models/bench/narrate/hf/<repo>/<revision>/<path>`, with a `SHA256SUMS` in each `<revision>`
directory. Inputs live at `/models/bench/narrate/inputs/`: `jobs/*.json`, `chunks-v1.json`, and
`voices/<voice id>.wav` and `.txt`. `tests/test_narrate_bench_image.py` checks the rendered pod against
these rules. The receipt records a pass of the owner's own validator, `validate_pod`.

## Hard stops

The entrypoint starts no arm after `NARRATE_WINDOW_S` (1500 s). Each arm has a budget: A2-gpu-alt 480 s,
D2-preset 90 s, A1-gpu 390 s, A3-gpu 420 s, 1380 s in all. An arm stops after 120 s without output. An
out-of-memory stops that arm; a lost device or ring timeout stops the window. An arm whose weights fail the
start check is refused and the others still run. `activeDeadlineSeconds: 1800` ends the pod whatever the
entrypoint does, and the owner's runner deletes it after collection.

## Image

The image is built from the flake and pushed to GHCR by the manual workflow
[`narrate-bench-image.yml`](../../.github/workflows/narrate-bench-image.yml). It runs only when dispatched,
and it writes the pushed digest to its summary. Pods reference the image by digest only. To build on the CPU
host instead (bounded):

```
nix build --max-jobs 1 --cores 8 .#narrate-bench-image   # docker-archive .tar.gz in ./result
skopeo copy --digestfile digest docker-archive:result docker://ghcr.io/OWNER/PATH:47c2756e-5916bf7c
```

The flake lock pins the packages: Mesa 26.2.1 (RADV and lavapipe ICDs), Vulkan loader 1.4.357.0 and
Python 3.14. `/etc/narrate-bench.json` in the image records them. The GPU-host owner asked for Mesa RADV 25.x
or newer, because RDNA4 (gfx1201) support starts in Mesa 25. 26.2.1 meets that, but nobody has run it on the
card yet. A job's `vulkan_icd` field picks `radv` (the default) or `lavapipe`.

## Answers from the GPU-host owner (2026-10-23, TIN-7085; teammate information)

- **Registry.** GHCR, under the owner's organisation. The image is pushed from repository CI and pulled by
  digest through Secret `ghcr-pull` in namespace `models`. Every pod and Job names that Secret, because the
  default ServiceAccount carries none. The owner's runner checks, before any write, that `ghcr-pull`
  resolves the digest. The workflow pushes to this repository's own GHCR namespace unless it is given a
  target and a `NARRATE_BENCH_GHCR_TOKEN` secret that can write the organisation's package.
- **Hugging Face from the cluster.** No. Namespace `models` has no internet egress, and adding one would need
  a new egress grant and its own operator ruling. The weights instead reach the volume from the CPU host's
  hash-checked copies: `just narrate-fetch --apply`, then `layout`, then a `tar` stream into the staging pod.
  The in-cluster model store is not used for the narrate weights.

## Runbook

`$W` is narrate-fetch's weights directory and `$U` the upload tree. `$V` is the private voice store. All
three sit on the CPU host, outside any checkout; none of their contents enter git.

### Render the specs (operator, CPU host)

The templates hold five placeholders: `__WINDOW_ID__`, `__GPU_NODE__`, `__MODELS_PVC__`, `__IMAGE__` and
`__IMAGE_DIGEST__`. Each is invalid as written, so an unrendered spec fails validation.

```
render() { sed -e "s|__WINDOW_ID__|$WINDOW_ID|g; s|__GPU_NODE__|$GPU_NODE|g; s|__MODELS_PVC__|$MODELS_PVC|g" \
               -e "s|__IMAGE_DIGEST__|$DIGEST|g; s|__IMAGE__|ghcr.io/$IMAGE_PATH@$DIGEST|g" "$1"; }
render deploy/narrate-bench/bench-pod.yaml > "$U/bench-pod.yaml"
render deploy/narrate-bench/stage-job.yaml > "$U/stage-job.yaml"
grep -n '__[A-Z_]*__' "$U"/*.yaml && echo "unrendered placeholder" >&2
```

### Stage (before the window; no GPU, no Lease)

1. **Operator, CPU host:** fetch and lay out the weights and the inputs.

   ```
   NARRATE_WEIGHTS_DIR=$W just narrate-fetch --apply --only qwen3-tts-1.7b-base-qwentts \
       --only ming3-0.5b-gguf --only voxcpm2-gguf
   python3 -I narrate/bench/image/bench_arm.py layout --weights "$W" --dest "$U" \
       --jobs narrate/bench/image/jobs/*.json --chunks narrate/bench/chunks-v1.json \
       --voice-id <voice id> --consent-id <consent id> --ref-wav "$V/<clip>.wav" --ref-text "$V/<clip>.txt"
   ```

2. **Owner:** apply the rendered `stage-job.yaml`, then wait for the pod to report Running.
3. **Operator, with the owner's kubeconfig:** stream the tree in, then write the marker.

   ```
   POD=$(kubectl -n models get pod -l job-name=models-stage-narrate-bench -o name)
   tar -C "$U" -chf - hf inputs | kubectl -n models exec -i "$POD" -- tar -C /models/bench/narrate -xf -
   kubectl -n models exec "$POD" -- sh -c ': > /models/bench/narrate/.upload-complete'
   kubectl -n models logs -f job/models-stage-narrate-bench       # ends with NARRATE-STAGE-DONE rc=0
   ```

   The `-h` flag sends files, not symlinks. `rc=0` means every weight matched `sources.json` and its
   `SHA256SUMS`. It also means every job loaded with its chunk list and reference clip at their declared
   sha256, and with a consent id present.

### Window (30 minutes or less; the owner's runner)

4. **Owner, dry run:** `scripts/operations/narrate-bench-window.py --pod-spec "$U/bench-pod.yaml" --holder
   narrate-bench-$WINDOW_ID`. It validates the contract and runs the read-only preflight (Lease empty, no
   `devic.es/dri` holder, CPU and memory guards, quota, PVC, the pull Secret resolving the digest, and a
   server-side dry-run create). It writes nothing.
5. **Operator:** GO, and the TIN-5397 notice posted.
6. **Owner:** the same command with `--execute`. The runner does the Lease compare-and-swap, the
   NetworkPolicy, the pod and the wait for `NARRATE-BENCH-DONE`. It then collects `pod.log`, `events.json` and
   `bench-out.tar` (that is, `/out`), and deletes the pod and policy in a `finally` before it releases the Lease.
7. **Owner:** post the runner's `receipt.json` to TIN-7085. **Operator:** copy `bench-out.tar` to the CPU
   host's private runs directory.

### After the window

8. Score off the GPU (`just narrate-bench-score`: WER, catastrophic chunks, SIM). Write the bench receipt as
   its own dated note, citing the image digest, `window.json` and every arm's `receipt.json` sha256.
9. **Owner:** remove `/models/bench/narrate/inputs/voices/` from the volume. The reference clip is consented
   for this bench only. Delete the finished staging Job.

## What a run writes

Everything goes under `/out/<window id>/`. `window.json` holds:

- the weight check: each file's sha256, the check that matched, and the hash time;
- the idle VRAM baseline, the sample count, the peak and the end value;
- each arm's state and any bench stop.

`vram.csv` holds the 10 Hz `mem_info_vram_used` samples. Each `<arm>/receipt.json` holds:

- the binary sha256, the image digest, the job sha256 and the chunk-list sha256;
- the voice id, consent id and hashes, never the clip or its transcript;
- the load time and the smoke chunk;
- per chunk: wall time, audio duration from the WAV header, RTF and the WAV sha256;
- per seed: totals and RTF, the peak VRAM above baseline, the stop reason and the state.

Each arm also writes `runtime.log` and its WAVs. A qwentts arm's chunk wall time is its HTTP request. An
audio.cpp arm uses the runtime's own `wall_ms`. If that process was stopped, it uses the gap between output
files, and the receipt labels it.
