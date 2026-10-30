# TIN-7788: neutral avatar tools, visible slide text and the compose metadata strip

Date: October 30, 2026. Linear: TIN-7788. Authority: SPR-214 (TIN-7125 comment `0cbbe60a`) for the branch, signed
commit and PR. The lane follows the demo DAG plan's P2 row under SPR-254 to SPR-256 (TIN-7788 comments `1d2d80e1`,
`60924f68` and `2b1e530b`). Receipt cites R-HOOK-CONVERGENCE-20261004 (R-N13).

| stream | owner | repo/branch | state/evidence | next |
| --- | --- | --- | --- | --- |
| P2 neutral avatar tools, visible text, metadata strip | narrate-dispatched lane | Jesssullivan/video-utils `feat/tin-7788-neutral-avatar-visible-text-20261030` | PR into main, not merged. Local suites pass, local, non-qualifying | root review and CI; P4 re-pins the stage graph with these names |

## What changed

| Part | Change | Files |
| --- | --- | --- |
| a | The `avatar` and `avatar_check` stage tools are `avatar_overlay` and `avatar_verify`, each with `dispatch: {by: avatar.external, default: kitpip, externals: [kitpip, vrm]}`. The four drafts `kitpip_overlay`, `kitpip_verify`, `vrm_overlay` and `vrm_verify` fold into two. New skills `avatar-overlay` and `avatar-verify` | `program/dags/narrated-video.json`, `program/tool-drafts/narrated_video.json`, `narrate/video/graph.py`, `.agents/skills/` |
| b | An asset may name a text source, `text: {path, sha256}`: the SVG it was drawn from or an `nv_asset_text` JSON list. Intake reads each shown asset's strings as guard source `visible` at `asset#N`. `intake.json` lists shown assets read and unread | `narrate/video/visible_text.py`, `bundle.py`, `private_terms.py` |
| c | compose adds `-map_chapters -1` and checks both MP4s and its text outputs, refusing `metadata_present`. handoff writes each slide layer through a PNG chunk filter and checks `layers/base.mp4`. compose and handoff move to impl 2 | `narrate/video/strip.py`, `compose.py`, `handoff.py` |

## Aliases

None kept. No avatar tool draft was admitted to `program/tools.json`. The cade-infra render row and the cade BS-21
record pin the DAG by commit and blob, so they keep `kitpip_overlay` and `kitpip_verify` until P4 re-pins them. Stage
keys do not change: a key holds the external's own tool and digest, not the MCP tool name.

## Measured

- FFmpeg 8.1.2 in the condense shell: `-map_metadata -1` alone left a synthetic input's chapter in the output, with
  an empty title. With `-map_chapters -1` no chapter remained. The new unit test covers both cases.
- `just narrate-test` under `tinyland-heavy`: 2043 passed and 1 skipped. Local, non-qualifying.
- Mutation probes: dropping the visible-text guard call failed 10 visible-text tests. Reading SVG `metadata`,
  `style` and `script` text failed 2.

## Open

- A private lane does not refuse a shown asset with no text source. It records `visible_text: partial`. Whether
  it should refuse is an operator decision.
- No raster text JSON existed before this change, and no OCR dependency exists. The `nv_asset_text` schema is new
  and needs a producer to write it.
- The overlays in `layers/` keep the external's bytes, because their manifests bind them. They are not
  metadata-checked.
