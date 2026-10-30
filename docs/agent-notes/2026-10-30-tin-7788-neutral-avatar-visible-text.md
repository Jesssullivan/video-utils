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

## Review fixes

A review of head `906f832e` found these. Each fix is a new signed commit on the same branch.

| Finding | Fix | Files |
| --- | --- | --- |
| Bazel `//narrate:stdlib_test` failed: its module list lacked `strip` and `visible_text` | both added | `narrate/tests/stdlib_smoke.py` |
| A tagged base clip's title and comment reached `layers/clips.wav` in a `LIST`/`INFO` chunk | `to_mono` drops tags and chapters, and `base` moves to impl 2. handoff reads every layer but `base.mp4` for XMP, EXIF, a local path or an extra WAV chunk, and never rewrites one | `common.py`, `strip.py`, `handoff.py`, `graph.py` |
| A shown asset with no text source left no trace after intake | the marker carries the visible-text state, and `deliver_check` reports the operator gate `visible_text`. `deliver_check` moves to impl 2 | `bundle.py`, `private_terms.py`, `job.py`, `deliver.py` |
| An SVG that embeds a raster, refers to another file or has only paths counted as read | such an SVG is opaque, and the intake state is then `partial` | `visible_text.py`, `bundle.py` |
| A UTF-16 SVG or a late document type got past the byte check | a text source SVG must be UTF-8, the decoded text is searched, and the parser refuses any declaration | `visible_text.py` |

Measured for the fixes, local, non-qualifying, under `tinyland-heavy`. `just narrate-test` gave 2073 passed,
1 skipped and 1 failed. The failure was the compose gate-set test, which now lists `visible_text`. After that fix,
the compose, visible-text, graph, intake, private-terms and VRM suites gave 592 passed. The stdlib smoke passes
with the repository root on the path. Mutation probes: removing the metadata flags from `to_mono` failed 2 tests,
and removing the `visible_text` gate failed the private-lane delivery test.

## Second review fixes

A review of head `0087669d` found these. Each fix is a new signed commit on the same branch.

| Finding | Fix | Files |
| --- | --- | --- |
| An edited marker summary changed the `visible_text` gate: `not_declared` gave `not_applicable`, and `passed` with unread positions gave `passed` | a marker holds only `passed` or `partial`, `passed` exactly when no position is listed, and it must equal the `intake.json` beside the records | `private_terms.py` |
| An overlay's container tags reached `layers/` | handoff probes each MOV and MP4 layer against a tag allowlist and refuses `metadata_present` | `strip.py` |
| `plan`, `status` and `run` showed `deliver_check` fresh while `visible_text` was open | admit lists `visible_text_unread`, so the node shows `pending_operator` | `admit.py`, `graph.py` |
| An SVG with script, an `@import`, a CSS escape or an `xml-stylesheet` instruction was not opaque | each makes the source opaque | `visible_text.py` |

## Open

- A private lane does not refuse a shown asset with no text source or an opaque one at intake. It records
  `visible_text: partial`, and `deliver_check` holds the `visible_text` gate at `pending_operator`. Whether intake
  should refuse is an operator decision.
- No raster text JSON existed before this change, and no OCR dependency exists. The `nv_asset_text` schema is new
  and needs a producer to write it.
- The overlays in `layers/` keep the external's bytes, because their manifests bind them. handoff reads them for
  XMP, EXIF, local paths and container tags, and refuses a tag outside its allowlist. It does not rewrite them.
- An SVG text source with text outlined to paths beside one other string is not opaque. The guard cannot compare
  the SVG with the picture's pixels, so that text stays the producer's review.
