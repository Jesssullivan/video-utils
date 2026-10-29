# VRM offline renderer draft: avatar.manifest/v1 and the second external (2026-10-29)

Authority: SPR-128 (Linear TIN-7125 comment `33022456`) and SPR-120 (comment
`59b5cb12`). This draft is filed under TIN-7084. The dispatch named TIN-7503, but
TIN-7503 is the /call speech-adapter and LiveKit lane (SPR-20). Receipt per
R-HOOK-CONVERGENCE-20261004 (R-N11, R-N12, R-N13).

`vrm offline renderer | narrate seat dispatch | video-utils feat/narrated-video-vrm-renderer from main eb8f2779 | draft PR, stub only | root review; the real renderer page and lockfile, then the 11-14 bench`

## What changed

| Area | Files | Change |
| --- | --- | --- |
| Manifest schema | `narrate/video/avatar_manifest.py` | `avatar.manifest/v1` with `renderer.kind` `kitpip` or `vrm`. `kitpip.manifest/v0` still reads, as kind `kitpip`. A vrm manifest needs the model digest, its VRM meta licence fields, the renderer, the GPU and driver, `frames_identity: per_host`, the face timeline digest, the likeness consent, the approval and an open badge |
| Face timeline | `narrate/video/face.py` | `face.timeline/v1` on the `narration_output` clock, built from narration loudness, with a fixed blink schedule |
| VRM external | `narrate/video/vrm.py`, `narrate/video/avatar.py` | pin, resolve, VRM meta reader, gates, the pipe protocol (raw RGBA to FFmpeg ProRes 4444) and the `avatar` and `avatar_check` runners. `avatar.py` sends each avatar node to its external |
| Graph and admit | `narrate/video/{graph,admit,run,cli,job,kitpip}.py`, `narrate/dhall/check.py` | `avatar.external` takes `vrm`. Avatar stages resolve the job's external. The VRM gates run at admit. `pin-check --external vrm`. `avatars.json` is an optional record. kitpip keys are unchanged |
| Registration | `program/externals.json` | registers `vrm` with no pin value. kitpip lists both manifest schemas |
| Fixtures | `narrate/tests/fixtures/narrated-video/{vrm_renderer_stub.py,vrm_rig_fixture.py,vrm-externals.json}` | a stub renderer with no browser, a synthetic GLB writer with VRM 1.0 and 0.x meta and no mesh, and the test-only pin |
| Hooks and skills | `program/tool-drafts/narrated_video.json`, `.agents/skills/vrm-overlay/SKILL.md`, `just/narrated-video.just` | drafts of tools 71 and 72, not admitted. `just vrm-pin-check` |
| Spec | `docs/spec/NARRATED_VIDEO.md` | SPR-120 and SPR-128 rows, "Avatar externals and `avatar.manifest/v1`", "VRM external (draft)", safety rows and unknowns |
| Tests | `narrate/tests/test_narrated_video_vrm.py`, `narrate/tests/stdlib_smoke.py`, `tests/test_public_tree.py` | 75 VRM tests. The smoke test lists the new modules. The public-tree check refuses any tracked `.vrm`, `.vrma`, `.glb` or `.gltf` |

## Decisions this draft does not make

- The badge. Whether offline VRM video carries a burned-in badge is open. The
  manifest records `badge: {burned_in: false, decision: open}`, and a record
  that sets `badge.burnedIn` refuses `vrm_badge_undecided`.
- Editions. Only `Internal` may carry a VRM overlay (`vrm_edition_unruled`),
  because SPR-120 holds the switch for the 11-14 bench.
- The VRM meta permission fields are recorded, not gated.

## Not built

- The renderer itself: the three-vrm page, its Puppeteer or Playwright driver
  and the lockfile. No package was added and nothing was downloaded. A real pin
  stays `commit_pinned_digest_pending` until the renderer exists.
- A Dhall type for `avatars.json`.
- Aligner word timings for the face timeline.

## States

| State | Value |
| --- | --- |
| Source checks | 2026-10-29 in `nix develop .#condense`, under a 6G memory scope: the narrated-video graph, types, simple, avatar, compose and VRM suites with `test_contract_shape.py` passed (177 and 165 tests, in two runs). `tests/test_public_tree.py` and `tests/test_s5_tool_admission.py` passed (15, 1 skipped). `just narrate-dhall-check` passed (79 self-test mutations). The stdlib smoke and `ruff check` and `ruff format --check` passed |
| Stub render | the executor ran a VRM job on the stub through `deliver_check` |
| Real VRM render | not run |
| Lip sync, badge decision, bench | `pending_operator` |
