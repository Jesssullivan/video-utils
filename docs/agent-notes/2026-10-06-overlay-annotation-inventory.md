# Overlay and annotation inventory receipt

Actor: `/root/overlay_future`. Target/ownership: new future overlay specification
and this note only. Reason: operator requested exact current marker types/counts,
timestamp annotation dispatch, mistake overlays and CC0 research. Authority:
R-HOOK-CONVERGENCE-20261004, R-N13; parent-owned integration and publication.
Prior state: shared dirty tree with active arrangement renderer changes. Result:
read-only inventory and future design; no app, renderer, media or tracker mutation.

Read root `AGENTS.md`, current workers (`dag.py`, `markers.py`, `marked_video.py`,
`review_server.py`, `arrangement_markers.py`), `program/tools.json`, review browser
assets, current review/marked-video contracts and actual visual receipt. Applied
skills: [phrase-markers](../../.agents/skills/phrase-markers/SKILL.md),
[guitar-marked-video](../../.agents/skills/guitar-marked-video/SKILL.md),
[guitar-review](../../.agents/skills/guitar-review/SKILL.md). A lightweight memory
registry search found no relevant entries; no memory-derived fact is used.

## Live local metadata readback

Run `artifacts/runs/20261005T232741Z-2b5dc43fd009`, source
`a522115f4e72e19384fb341bc84369728eceefe49183b8c6367a1008a95176c6`.
Metadata hashes computed directly on October 6, 2026:

| Artifact | SHA256 |
| --- | --- |
| `flags.json` | `3d6b403fc2eeba90f9ea078d039e46bab427287b1c048a54933da66622e5ef0e` |
| `markers.json` | `b2d2cf4aa6ed18b489815c7f9a6ccc75e5ecd82b372a561bf3627fa7b3b13a84` |
| `marked-preview/selection.json` | `915990d487466e9f9adcd571ad960df94ba94af0e07c6c5b4b99fd3b1eaef462` |
| `marked-preview/outcome.json` | `48c4d60759a0b328ec7975c2d4eff455934cd2ddf5a8ed6efcabcd909a91bac2` |

Python `json`/`Counter` readback found 180 flags and 180 markers with identical
kind totals: four-pulse112; spectral-texture44; recurrence8; low-register3;
attack-density4; rate-difference3; alignment-shift1; motif-timing5. Default selected
24 markers across six kinds, excluded156 across two kinds, composed25 callouts.
Selection records two maximum visible lines,10ms subtitle quantization,
`performance_issue_confirmed:false`, and `listening_accepted:false`.

Visibility readback confirms six fully suppressed IDs:
`marker-0002-7b2b29456c75`, `marker-0011-3896be0621c6`,
`marker-0014-f4c819aef1a2`, `marker-0018-fdb2bfbf6b29`,
`marker-0019-8d2468650d7c`, `marker-0022-35a887d3b5e1`.
The prior sampled visual receipt reports13 at least partly suppressed markers
(including these six); it does not establish continuous-playback readability.

Outcome metadata reports3,621 decoded frames, preserved VFR PTS/last extent,
AAC payload/timing/padding and decoded mono44.1kHz PCM identity, with physical
A/V sync unverified. This lane did not rerender, decode media or independently
repeat those media checks. Existing evidence:
[sampled actual visual receipt](2026-10-05-marked-video-actual-visual.md).

## Interface readback

`review` is typed read/write over a request file; closed v1 annotation fields
include ordered source span, five categories, three states, note, optional stable
ID and optional current candidate ID. Server storage binds source/manifest and
candidate artifacts; writes lock, check revision and atomically replace the store.
Limits20kB/request,200 annotations,1MB/store. No current melodic category or
structured user-confirmed mistake basis. User timestamp notes already work with
no automatic candidate. MCP review writes do not start an HTTP server.

`markers` exports generic JSON/CSV, with native frame indices null and native
Final Cut/Resolve import explicitly unverified. `marked_video` registry selection
is `phrase-review|recurrences|all-review`; no current annotation input, staff,
tonic/meter badge or configurable graphical mistake assets. Arrangement helpers
in the current dirty worktree are a separate active lane, not counted in the
canonical NR8 render or presented as published/validated runtime support.

## Primary research checked October 6, 2026

- [Kenney Game Icons](https://kenney.nl/assets/game-icons): creator declares105
  files under CC0. Candidate for generic controls; no archive downloaded or
  file-level license audited. Music-specific symbols should use authored SVG
  primitives with explicit ownership/project licensing.
- [CC0 deed](https://creativecommons.org/publicdomain/zero/1.0/): public-domain
  dedication permits copying/modification/distribution; site declaration does
  not independently audit every downloaded asset's provenance.
- [W3C use of color](https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html):
  pair color with text/shape.
- [W3C contrast minimum](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html):
  ordinary text4.5:1 minimum; rasterized text needs legibility checks too.

Future design, payload examples, evidence gates, priority/visibility ledger,
estimated8–14h next-week slices and PBT cases:
[OVERLAYS_AND_ANNOTATIONS.md](../spec/future/OVERLAYS_AND_ANNOTATIONS.md).
These are proposed tickets, not published Linear IDs or completed implementation.

Root relayed the operator-selected default during this lane: **“Compact:
section/phrase label, BPM, and brief issue badges.”** This exact choice is durable
in the future spec and was sent to the current clip and future UI owners. Detailed
timeline/staff remains review UI or an explicitly chosen optional output.
