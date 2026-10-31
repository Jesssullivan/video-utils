# Render stage task body and worker image (October 31, 2026)

Linear TIN-7788, demo DAG P9 and the render half of P6. Ruling R-HOOK-CONVERGENCE-20261004: R-N11, R-N12 and
R-N13. A narrate W4 workflow lane drafted this from its brief, the hardware DAG lane `renderstage`.

`renderstage | narrate lane | Jesssullivan/video-utils feat/tin-7788-render-stage-20261031 | draft PR, checks below | root review. Cade side drafted separately`

## What changed

| File | Change |
| --- | --- |
| `docs/spec/RENDER_STAGE.md` | The render stage contract: request, inputs by digest, phases, Lease protocol, placement, image and result |
| `narrate/video/render_stage.py` | `check` validates a request and prints its phases. `result` reports a job by digest and `--export` writes by sha256 |
| `narrate/video/cli.py` | the `render-stage` subcommand |
| `just/narrated-video.just` | `nv-render-stage-check` and `nv-render-stage-result` |
| `deploy/cade-render-worker/image.nix`, `flake.nix` | `.#cade-render-worker-image`, a docker-archive with no private input and no GPU binary |
| `narrate/tests/test_narrated_video_render_stage.py` | 30 tests with a fake stage runner |
| `narrate/tests/stdlib_smoke.py`, the `narrated-video-verify` skill | the new module and a pointer |

## Decisions in this draft

- The task body never touches the Lease. A GPU window needs the guard's holder form, a pinned helper digest and a
  TIN-5397 notice comment id in the request.
- The Lease token in the request is the neutral word `gpu-lease`. The cluster name of the Lease names a host, and
  this repository is public.
- v1 serves `Internal` editions only.
- The GPU window stays on the host batch path. The census and `finalize.py` both need the host's `/proc`. The demo
  DAG design's pod default holds for the CPU phases only. This is open decision R1 in the spec.

## Checks

All runs were local and non-qualifying, inside `nix develop .#condense`.

| Check | Result |
| --- | --- |
| `pytest tests/test_narrated_video_render_stage.py tests/test_narrated_video_accept.py` | 159 passed before the Lease token rename. The render-stage file alone passed 30 of 30 after it |
| `PYTHONPATH=. python3 narrate/tests/stdlib_smoke.py` | 7 tests OK |
| `pytest tests/test_public_tree.py` | 4 passed, 1 skipped |
| `ruff check` and `ruff format --check` on `narrate/` | clean |
| `nix eval .#packages.x86_64-linux.cade-render-worker-image.drvPath` | evaluates |
| `nix build .#cade-render-worker-image` under `tinyland-heavy`, dirty tree | built a docker-archive of 438,605,212 bytes. User 10001 and the entrypoint as specified. The tag read `dirty` |
| The image's `share/video-utils` tree run with a synthetic GPU request | the module imported and refused as the code then stood |

Not run: a container runtime, a GPU window, the lease helper, FFmpeg stages and any model.

## Review fixes (second commit round)

A review of PR #82 and the Cade PR raised nine findings. Eight needed a change, and the ninth is the open trailer
decision. Ruling R-HOOK-CONVERGENCE-20261004 (R-N13).

| Finding | Change |
| --- | --- |
| A private tenant word in a comment, a refusal and the spec | removed. The text now says a client edition needs its own tenant (T4). No tracked denylist entry was added, because a short word's digest is easy to reverse. The untracked `VIDEO_UTILS_PRIVATE_TERMS` file is the place for it |
| The result attested inputs it never checked | `result` binds the request to `JOB/intake/intake.json`: the bundle manifest, the records tree and the denylist digests, the job id, the edition and the job record. Intake now records `inputs.records_sha256`. The result names `intake_sha256` and `inputs_bound_by` |
| The GPU window admission was form only and failed open | the Lease checks are labelled `form_only`, and the draft plan lists what `voice_gpu` must verify. v1 refuses `gpu_window` outside `check --gpu-draft`, and the result's `lease` is null |
| `machine_passed` failed open on a missing gate | all four `accept.AUTOMATED` gates must be present, and `delivery_gate.machine_gates_passed` must agree |
| The commit pin was checked only at collect | `check --inputs` compares the worker's commit first |
| Root-owned writable directories in the image | `fakeRootCommands` chowns `/work` and `/out` to 10001. `WorkingDir` is `/work` |
| The Cade task named `deliver_check` | renamed `collect`, effect render. R7 now covers `verify_inputs` only |
| Test gaps, an export that skipped a re-hash, a FIFO that could block the tree hash | the tests listed in the finding, a re-hash of an existing result JSON, and `store.tree_sha256` refuses a non-regular file |
| The hook-written trailer that names a host | no change. It stays a Jess decision |

Checks for this round were local and non-qualifying. They ran inside `nix develop .#condense` under `tinyland-heavy`.

| Check | Result |
| --- | --- |
| render-stage, intake, accept, private-terms and visible-text tests with `tests/test_public_tree.py` | 661 passed, 1 skipped. The render-stage file alone passed 48 of 48 |
| `PYTHONPATH=. python3 narrate/tests/stdlib_smoke.py` | 7 tests OK |
| `ruff check` and `ruff format --check` on `narrate/` | clean |
| `nix build .#cade-render-worker-image`, dirty tree | 438,607,622 bytes. The customisation layer lists `./work/` and `./out/` as 10001/10001, and `./inputs/` as 0/0. The config holds User `10001:10001`, WorkingDir `/work` and no commit, as a dirty tree should |

Not run: a container runtime, a GPU window, the lease helper and any model.
