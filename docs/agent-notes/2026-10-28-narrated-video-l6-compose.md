# Narrated video L6: compose and delivery (2026-10-28)

Authority: operator direction KP-13 and rulings NV-1 to NV-5, KP-15, NV-8 and
KP-16 to KP-19 (Linear TIN-7476 comments `94248deb`, `9db389dc`, `4ab7fc27`,
`df0ed8e6`, `31222dd2` and `f446ae28`). The TIN-7125 rulings the root
workflow named (SP-44 `766f4a8b`, CORE `0ec29400`) were read; none changes
this lane's files. Receipt per
R-HOOK-CONVERGENCE-20261004 (R-N11, R-N12, R-N13).

`narrated-video L6 | narrate seat (W8) | video-utils feat/narrated-video-l6-compose (from main 0a55e660; no L5 PR existed at start) | compose, deliver_check, handoff on fixtures; gates below | rebase onto L5 when it opens, root review and merge, then L7 admits tools 69 and 70`

## What changed

| Area | Files | Change |
| --- | --- | --- |
| Compose | `narrate/video/compose.py` | profile scaling, slide layers, kitpip overlays with straight alpha, avatar-off fades, soft captions, `description.txt`, `chapters.json`, `compose.json`, `video.mp4` and `video.upload.mp4` |
| Deliver check | `narrate/video/deliver.py` | profile, loudness, flash and caption gates; listening, lip sync and bed gates as operator states; `delivery_gate`; Edition.check at DeliverCheck; label chain re-derived from the leaves |
| Handoff | `narrate/video/handoff.py` | `layers/` (bare base, overlays, slide pictures, stems, captions) and `edit.json` with every input's stage key |
| Graph and run | `narrate/video/graph.py`, `narrate/video/run.py` | compose knobs hold `avatarOff`, `fadeS` and the slides block; slide pictures are compose and handoff sources; L6 runners wired |
| Avatar default | `narrate/video/job.py`, `narrate/video/cli.py` | NV-8: `init` turns the avatar on where the edition allows one, `--no-avatar` turns it off, and a missing persona names both ways out |
| Slide card | `narrate/dhall/NarratedVideo.dhall`, `narrate/dhall/check.py`, `narrate/video/admit.py` | `slides` (layout `Full` or `CardLowerLeft`, pages `Base`, `Hold` or a slide by digest) and `avatar.avatarOff`; admit refuses `slides_invalid` and `page_unknown` |
| Fixtures | `narrate/dhall/examples/narrated-videos.{dhall,json}`, `narrate/dhall/narrated-video-test.dhall` | `nv-fixture-slides`; two generated 320x180 slide pictures in stored deflate blocks; 13 new self-test mutations (48 for narrated video); a Dhall assertion of the card defaults |
| Hooks and skills | `program/tool-drafts/narrated_video.json`, `.agents/skills/{narrated-video,narrated-video-compose,narrated-video-verify}/SKILL.md` | drafts for tools 69 and 70 (proposals, not admitted) and their skills |
| Recipes and spec | `just/narrated-video.just`, `docs/spec/NARRATED_VIDEO.md` | `nv-fixture` runs to `deliver_check`; "Compose and delivery (lane L6)", "Slides", "Deliver check", "Handoff", "Avatar default (NV-8)" |
| Tests | `narrate/tests/test_narrated_video_compose.py` and updates to the graph, simple, types, smoke and public-tree tests | 27 compose tests |

## The slide card

Built from the deck seat's description only (design Addendum B: lower left,
42% width, 64 px margin, 0.35 s fades, adjacent slides crossfade in place, the
held next-clip frame dims to 50% and lifts as the card fades out, no card on the
0.4 s end page, flash gate at most 30%). No code, asset or text was read from or
copied out of the private deck repository. The fixtures are generated shapes.

## Evidence

Quiet window on this host until 2026-10-28T16:55Z (TIN-6833): no cargo, bazel,
go or image build ran, and nothing was written under the shared cache. The
`.#condense` dev shell would have built `nix-shell-env`, so it was not entered.
The checks ran on the store paths of the same tool versions the shell pins
(FFmpeg 8.1.2, Python 3.12 with pytest, dhall 1.42.1, dhall-json 1.7.12), each
inside `systemd-run --user --scope -p MemoryMax=6G -p MemorySwapMax=0 nice -n 19`.

| Check | Result |
| --- | --- |
| graph, types, simple-path and compose tests, after the last edit | 202 passed (27 of them new) |
| full narrate suite (`just narrate-test` command) | 947 passed, 1 skipped, before two later test-only edits that the 202 above cover |
| `narrate/tests/stdlib_smoke.py` | 7 tests OK |
| ruff check and format on `narrate/`, shellcheck on the narrate scripts | clean |
| `dhall type` and `dhall format --check` on every type and example, rendered JSON equal to the committed JSON | pass |
| `narrate/dhall/check.py` and `--self-test` | 0 errors; 79 mutations all refused |
| `tests.test_public_tree`, `tests.test_timeline_contract` | 79 tests OK, 1 skipped (no private terms file) |
| First simple narrated video, rendered locally | `just nv-fixture`: card, fixture bed, no avatar, Web1080p30. 13 nodes planned, compose 1920x1080 at 30/1, 330 frames, 11.0 s mono. Mix -15.8 LUFS (drift 0.2 LU), true peak -9.1 dBTP, duck 7.0 dB. Every machine gate passed; listening `pending_operator`; public upload closed. The slides fixture rendered the card, the stub avatar and handoff at 720p in the tests |
| Negative controls (scratch edits, restored) | overlay without alpha, no dim layer, no avatar-off fades, a 1 ms slide fade instead of the crossfade, a 1000% flash limit: each fails its test |

## Decisions in this lane

- deliver_check reports a failed machine gate as a state and refuses only an
  edition refusal or a broken label chain, as the design rules for tool 70.
- With the avatar on and no L5 runner, `compose` stays blocked behind the
  avatar. It never composes a cut without an overlay the job asked for.
- `captions.burn` refuses `captions_burn_unsupported` in v1 (design N5).
- The three delivery profiles are this lane's. The deck project's profiles port
  in phase 2.
- The flash jump is relative to the darker frame with Y 16 as the floor. That
  is an inference from the deck seat's figures (worst 341% in v7), not its code.

## Unknowns and next

- L5 owns the avatar and avatar_check runners. The compose tests stand in for
  them with the stub through the pinned wrapper. When L5 opens, this branch
  rebases onto it and the stand-in goes.
- NV-6 (`ClientNarrated` as the client default) is still a follow-up to the
  spec and types; this lane did not change it.
- The card has no matched A/B against a deck cut. Listening, lip sync, Content
  ID and delivery stay operator states.
- `just check` and the Bazel targets were not run (quiet window). Root runs
  them after 16:55Z.

## Review fixes (2026-10-28, fixer pass)

Receipt per R-HOOK-CONVERGENCE-20261004 (R-N11, R-N12, R-N13), on the
review findings for PR #63 and the same TIN-7476 rulings (NV-2, NV-8, KP-15).
Every check below ran in the same bounded scope, during the quiet window.

| Finding | Outcome |
| --- | --- |
| Flash gate fails at the defaults (`Full`, 0.35 s, `#101820` card, light slide: 39.7% with a linear ramp) | fixed: each `Full` fade is eased against the mean luma under it (`compose.eased_fade`), so the luma moves by one ratio per frame. `compose.json` records both lumas and `min_fade_s`. New test composes the defaults: flash passes. Card fades stay linear |
| `public_upload_allowed` true while listening is pending | fixed: it now also needs `operator_states_open` empty, so deliver_check never reports it true. The old meaning is `upload_gates_closed`. Test, spec, verify skill and tool draft 70 updated |
| Rebase onto #62 hides a ClientVoiceOnly conflict | partly fixed: the `init_job(..., edition="ClientVoiceOnly")` assertion is gone, and `deliver.py` imports `CLIENT_EDITIONS` from `job.py`, added there on the same line as #62. Simplifying `AVATAR_EDITIONS` waits for the rebase, since `init` still accepts ClientVoiceOnly on main |
| An avatarOff page at t=0 shows the first frame | fixed: a span is held at alpha 0 by `lut=a=0` for its whole length, with a fade out only when there is time before it. Pixel test at frame 0 |
| avatarOff ignored for deck bases | fixed: `avatar_off_spans` refuses `page_unknown` (a verdict) for an id with no slide page |
| A tall slide's card leaves the frame | fixed: `card_box` narrows the card to fit the frame height less two margins. Unit test with a portrait slide |
| No test of the held next-clip frame on a video base | fixed: a `CardLowerLeft` run on a `testsrc2` base. Outside the card the frame is still, at 0.45 to 0.55 of the next clip's frame, within 10% of it on the run's last frame, and flash passes |

Negative controls (scratch edits, restored): a linear `Full` fade (flash
39.7% and 79.4%), no `lut` hide, the old upload gate, no card clamp, no held
layer and no unknown-id check each fail their test.

| Check after the fixes | Result |
| --- | --- |
| full narrate suite (`python -m pytest -q` in `narrate/`) | 952 passed, 1 skipped |
| ruff check and format on `narrate/` | clean |
| `narrate/tests/stdlib_smoke.py` | 7 tests OK |
| `narrate/dhall/check.py` and `--self-test` | 0 errors; 79 mutations all refused |
| `tests.test_public_tree`, `tests.test_timeline_contract` | 79 tests OK, 1 skipped |

`just check`, the Bazel targets and the `tests/cli.rs` rows still wait for
root after 16:55Z. The rebase onto #62 is still open.
