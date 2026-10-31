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
