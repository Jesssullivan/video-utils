# Lane E3: GPU-host bench image, staging Job and window pod (2026-10-23)

Linear TIN-7088 (the GPU half of W6a; G1 preparation), parent TIN-7084. Bench preregistration:
[`2026-10-22-narrate-bench-plan.md`](2026-10-22-narrate-bench-plan.md). Authority R-HOOK-CONVERGENCE-20261004:

- R-N11: no Lease taken, no cluster object created, no other owner's process touched.
- R-N12: hooks are advisory.
- R-N13: this receipt, with the facts mirrored to TIN-7088.

**State: built on the CPU host and checked by unit tests and the GPU-host owner's validator. Not applied, not
pushed to a registry, and no model run anywhere.** The operator's 2026-10-23 ruling runs the first bench as a
host process on the GPU host ("host first, pod after"). This lane delivers the pod path for the window after.

## What is here

- `narrate/bench/image/`: a nix-built OCI image, `nix build .#narrate-bench-image`. It is a docker-archive
  from `dockerTools.buildLayeredImage` and contains:
  - audio.cpp `47c2756e`, CLI only. It has the `ming3_tts` and `voxcpm2` targets, Vulkan, portable CPU code
    and compiled-in model specs.
  - qwentts.cpp `5916bf7c` with its ggml submodule `cc5df49a`: `tts-server`, `qwen-tts` and `qwen-codec`.
    Vulkan, static ggml, and a `QWENTTS_CPU_THREADS` bound on the CPU pool.
  - The Vulkan loader 1.4.357.0, `vulkaninfo`, and Mesa 26.2.1 with the RADV and lavapipe ICDs.
  - Python 3.14, coreutils, bash (`/bin/sh`), GNU tar 1.35 and CA certificates.
  - User 10001, and the entrypoints `narrate-bench-arm` and `narrate-bench-window`.

  Every source is pinned by commit and NAR hash, and every package comes from the flake lock.
- `bench_arm.py` (`narrate-bench-arm`) has these subcommands:
  - `run JOB...` first hash-checks every model file the jobs name against the image's `sources.json`, once
    per file. A file outside a pinned `hf/<repo>/<revision>/<path>`, or one whose hash fails, refuses that
    arm, and the other arms still run. The arms then run in order inside one window deadline.
  - `check JOB...` validates jobs and their inputs and runs nothing.
  - `versions` reports the binaries and Vulkan devices.
  - `verify --root` hash-checks the volume tree against `sources.json` and each `SHA256SUMS`.
  - `layout` (CPU host) builds the upload tree. It contains symlinks to narrate-fetch's checked copies and
    SHA256SUMS. It also holds `inputs/`: the shared chunk list, the consented clip and transcript, and the
    job templates filled with their sha256 values. It refuses a destination inside a checkout.
  - `receive` (staging pod) waits for the upload marker, then verifies the weights and every job. It writes a
    dated receipt and prints `NARRATE-STAGE-DONE rc=N`.

  `narrate-bench-window` runs `run`, prints `NARRATE-BENCH-DONE rc=N` and sleeps `NARRATE_LINGER_S` (600 s).
- The per-arm behaviour is unchanged from the first run of this lane:
  - a smoke chunk, then the seeds in order;
  - the per-arm budget, 120 s stall and window deadline stops;
  - out-of-memory and lost device named from the runtime log;
  - 10 Hz `mem_info_vram_used` against a 1 s idle baseline;
  - WAVs plus `receipt.json` with RTF, durations, load time, VRAM peak above baseline and hashes, never the
    clip or its transcript.
- The private chunker this lane first carried is gone. Every job reads the shared
  `narrate/bench/chunks-v1.json` from `narrate/bench/prepare.py` (PR #40), so the pod and the host-process
  bench render the same 17 chunks. The hash is filled in by `layout`, not hard-coded.
- `narrate/bench/image/jobs/` holds the templates: A2-gpu-alt 480 s, D2-preset 90 s, A1-gpu 390 s and
  A3-gpu 420 s, 1380 s in all. Each runs 4 threads. Model paths follow the volume layout:
  `/models/bench/narrate/hf/<repo>/<revision>/<path>`. Outputs go to `/out`.
- `deploy/narrate-bench/bench-pod.yaml`: one Pod, the GPU-host owner's runner input. It is rewritten to the
  owner's L1 contract (TIN-7085 receipt bdeabff4; swb message `01M5MW4JSD…`; their draft PR #2362):
  - name `narrate-bench-<id>` and the four `app.kubernetes.io` labels;
  - `nodeSelector` hostname; `priorityClassName: gpu-exclusive`; `activeDeadlineSeconds: 1800`;
  - uid and gid 10001, `supplementalGroups: [105]`, RuntimeDefault seccomp, a read-only root, and ALL
    capabilities dropped;
  - CPU request 2 and limit 4, memory 12Gi request equal to limit, and `devic.es/dri: "1"`;
  - the PVC read-only at `/models` with no subPath, the `out` emptyDir at `/out`, and `/tmp` holding HOME,
    XDG_CACHE_HOME and the Mesa shader cache.

  The NetworkPolicy is dropped because the runner creates its own (DNS only).
- `deploy/narrate-bench/stage-job.yaml`: NetworkPolicy and Job `models-stage-narrate-bench`. The pod has no
  ingress or egress, no GPU, and the PVC writable at `/models`. It runs `receive`. The model-store route and
  the separate inputs pod are gone, following the owner's finding that the model store is not used for the
  narrate weights.
- The templates hold placeholders only: `__WINDOW_ID__`, `__GPU_NODE__`, `__MODELS_PVC__`, `__IMAGE__` and
  `__IMAGE_DIGEST__`. The README's `render()` fills them.
- `tests/test_narrate_bench_image.py` has 22 cases (1 skips without the owner's validator):
  - the fake-runtime end-to-end cases, now with synthetic weights in the volume layout;
  - tampered and unpinned weights refused at the start;
  - `layout` to tar to `receive` round trip, tamper refusal, marker timeout, and checkout-destination refusal;
  - the rendered pod against an independent copy of the contract rules, and a broken pod caught;
  - the stage Job's no-network policy;
  - the job templates against `sources.json`;
  - the owner's own `validate_pod`, when `NARRATE_BENCH_WINDOW_VALIDATOR` names it.

  `tests/support/mini_yaml.py` reads the manifests without PyYAML.
- `.github/workflows/narrate-bench-image.yml`: a dispatch-only build and push to GHCR by digest. It has
  never run.

## The GPU-host owner's answers (peer information, TIN-7085, 2026-10-23 about 16:51Z and 17:15Z)

- **Registry.** GHCR under the owner's organisation, pushed from repository CI and referenced by digest.
  Namespace `models` pulls through Secret `ghcr-pull`, which every pod must name. The owner's runner checks,
  before any write, that `ghcr-pull` resolves the digest.
- **Staging reaching huggingface.co.** No. Namespace `models` has no internet egress, and a new egress grant
  would need its own operator ruling. The weights come from the CPU host's hash-checked copies instead. The
  in-cluster model store is not used for the narrate weights.
- **Pod contract.** As summarised above. The render group is gid 105. Weights go under `bench/narrate/` on
  the models volume, staged before the window: the inference lane stages them under J79, or this lane's
  staging Job does.

## Measured (CPU host, 2026-10-23)

- Image `nix build .#narrate-bench-image` at this branch: archive sha256
  `aaade3de9b76049796b188633436e382ced0d783686ecfa9f4566c56ca036258`, 399,332,123 bytes, 73 layers, config
  `db34e086…`. The config is user `10001:10001`, entrypoint `/bin/narrate-bench-arm`, workdir `/tmp`, and
  `HOME=/tmp`.
- The customisation layer holds `/bin/sh` (bash 5.3p15), `/bin/tar` (GNU tar 1.35), `/bin/sleep`,
  `/bin/narrate-bench-window`, `/bin/narrate-bench-arm`, `audiocpp_cli`, `tts-server`, `qwen-tts` and
  `vulkaninfo`. It also creates `/out`, `/models` and `/tmp` (1777).
- `--help` smoke only, in a `systemd-run --user --scope -p MemoryMax=2G nice -n 19 ionice -c3` scope:
  - `audiocpp_cli --help` returns rc 0.
  - `audiocpp_cli --version` prints `audio.cpp 47c2756e`, `backends: cpu,vulkan`.
  - `tts-server`, `qwen-tts` and `qwen-codec --help` print `qwentts.cpp 5916bf7 (pinned)` and their usage
    (rc 1, their usage exit).
  - Both runtimes link `libvulkan.so.1` from vulkan-loader 1.4.357.0.
- Unit tests: `python3 -m unittest tests.test_narrate_bench_image` passes 22, with 1 skipped.
  - With `NARRATE_BENCH_WINDOW_VALIDATOR` set to the owner's `scripts/operations/narrate-bench-window.py` at
    their PR head `0c6cad32`, the owner's `validate_pod` returns no problems for the rendered pod.
  - The test substitutes the real node and PVC names, which stay out of git.
- `mini_yaml.load_all` returns the same objects as PyYAML `safe_load_all` for both manifests.
- **No model inference ran on the CPU host in this run.** The earlier attempt of this lane started a
  lavapipe model smoke (A1 and A2-alt). It produced no audio: the A1 arm stopped on its budget with
  0 of 1 requests. It was among the processes stopped in the 17:14Z memory incident (TIN-7085 comment
  e878a04f), and it is not repeated: the CPU host runs no TTS model.

## Inferences and unknowns

- RADV on the card is untested by this lane. The image's Mesa 26.2.1 is newer than the host's 25.2.7, and
  both are newer than RDNA4's minimum. Whether ggml-vulkan runs `ming3_tts`, `voxcpm2` and qwentts on gfx1201
  stays unknown until a window. The host-process bench answers it first.
- A3-gpu passes the VoxCPM2 GGUF file path to `--model`. The audio.cpp docs show a directory; the window's
  smoke chunk will show which one it needs. The host-process bench answers this first as well.
- CPU limit 4 (request 2) is this lane's choice. The owner's reference spec uses a limit of 2, and their
  validator checks only the request.
- The weight check at the start reads about 11.5 GiB inside the 1500 s arm window. Its time is recorded
  (`window.json` `weights.verify_s`) but has not been measured on the GPU host.

## Open

- **Image push.** Dispatch the workflow with a target under the owner's organisation and a
  `NARRATE_BENCH_GHCR_TOKEN`, or push from the CPU host. Whether `ghcr-pull` can read a package pushed from
  this repository is unchecked; the owner's preflight checks it.
- **The PVC directory.** `bench/narrate/` must be writable by uid 10001 for `receive` and the tar stream.
  Otherwise the inference lane's own stage pod puts the same layout there. Asked of the owner over swb.
- **Dependency.** `narrate/bench/chunks-v1.json` lands with PR #40.
- **The window.** An operator GO, or J79(d), and then the owner runs `deploy/narrate-bench/README.md`.
