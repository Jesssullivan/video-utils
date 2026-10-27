# Narrated video L2: spec and types (2026-10-27)

Authority: operator direction KP-13 and rulings NV-1 to NV-5, KP-7 and KP-14
(Linear TIN-7476 comments `94248deb`, `9db389dc`, `0f367c48` and `1c16fbda`).
NV-4 starts this lane. Receipt per R-HOOK-CONVERGENCE-20261004 (R-N13).

`narrated-video L2 | narrate seat | video-utils feat/narrated-video-l2-types | spec, types, contract rows and checks; gates below | root review and merge, then L3 graph core`

## What changed

| Area | Files | Change |
| --- | --- | --- |
| Spec | `docs/spec/NARRATED_VIDEO.md` | public stage graph, editions, types, music-bed rules, labels, safety and unknowns. No client, persona value or vendor stack id |
| Contract | `docs/spec/TIMELINE_CONTRACT.md` | 3 mappings: `narrated_video_v1`, `avatar_overlay_v1`, `music_bed_v1`. Each writes `no_time_stretch: false` |
| Types | `narrate/dhall/{Edition,MusicBed,NarratedVideo}.dhall` | `Edition.check` runs at Plan, Place and DeliverCheck. `MusicBed.Acquirer` has one constructor, `Operator`. Union payloads are keyed records, so the JSON keeps the tag |
| Consent | `narrate/dhall/Consent.dhall` | `persona : Optional Text`, `default.persona = None Text` (NV-1) |
| Type tests | `narrate/dhall/narrated-video-test.dhall` | each ClientVoiceOnly code alone at each point, bed clearance, persona rule, NV-2 defaults |
| Examples | `narrate/dhall/examples/{narrated-videos,music-beds}.dhall` and their JSON | 3 jobs (Internal card with bed, Internal with avatar, ClientVoiceOnly deck) and 1 fixture bed |
| Checks | `narrate/dhall/check.py` | generated E-major sine loops and deck placeholders, the Edition port, bed, job and persona checks, 30 new self-test mutations |
| Tests | `narrate/tests/test_narrated_video_types.py`, `tests/test_timeline_contract.py`, `tests/cli.rs` | port pinned to the Dhall table, 9 new refusal-matrix rows, `verify-run` refusals per mapping |
| Bazel | `narrate/BUILD.bazel`, `tests/BUILD.bazel` | exports and `compile_data` for the 3 timeline fixtures |

## Evidence

| Check | Result |
| --- | --- |
| Contract rows red | fixtures set to `no_time_stretch: true`: `tests.test_timeline_contract` FAILED (failures=31, errors=6), across all 9 rows and the shape test |
| Contract rows green | fixtures restored: 74 tests OK |
| Dhall negative controls | a false `Edition.check` assertion fails `dhall type`. `MusicBed.Acquirer.Agent` does not type-check |
| `just narrate-dhall-check` | types, format, renders, `check.py` ok, self-test 61 mutations refused |
| `just narrate-lint narrate-test` | ruff clean, 745 passed, 1 skipped |
| `test_s5_tool_admission` | 11 OK |
| `cargo test --test cli -- narrat` | 2 passed |
| `just test` (inside `just check`) | 2206 tests: 8 failed, 188 skipped. All 8 are marked-video and marked-compact renders raising `No bounded supported installed font found`. `scripts/marked_video.py` `installed_font` looks for 3 fixed font paths, and this host has none of them. This branch changes no file those tests read |
| `scripts/doctor.py --require-media` (the rest of `just check`) | exit 0 |
| `tests.test_public_tree` | OK, private-terms case skipped (no terms file). A manual sweep of added lines found no client, persona or host word |
| `cargo test --locked` (`just test-rust`) | exit 0 |
| `test_bazel_graph_s3` | exit 0 |

The bed level is decided: the deck project's ruling 58 picked 20 dB under the
voice from a matched-loudness A/B, before a 7 dB duck. The 50 ms attack default
is an inference, not measured, and stays an unknown.

## Review fixes (2026-10-27)

Authority: the PR #56 review, with KP-15 (TIN-7476 comment `4ab7fc27`) and the
deck project's ruling 59(d) (`e427ecfc`). Receipt per R-HOOK-CONVERGENCE-20261004
(R-N13).

| Finding | Change |
| --- | --- |
| Tighten was an unconditional refusal | `NarratedVideo.tighten : { enabled : Bool }`, default off (NV-2). `tighten_on_synthetic` refuses only while tighten is off. The spec's "Tighten" section records the per-project override and the `stems.json` binding (edits digest plus pre-tighten take digest) that keeps `place` from `voice_stem_unbound` |
| Visible labels were mandatory | rebased on KP-15. `labels.personaCue` is `Optional Text`, default none. The empty-cue check, the caption prefix and the description notice rules are gone. Manifest labels still only grow |
| No edition fit a client cut with the narrator and avatar | new `ClientNarrated` edition (59(d)): synthetic voice and kitpip allowed, camera PiP refused. The bed gate now covers every client edition. At Plan, `avatar` is any avatar block and `pip` is false |
| Bed level listed as unknown | replaced by the ruling 58 decision. The attack time stays open |

| Check | Result |
| --- | --- |
| `just narrate-dhall-check` | types, format, renders and `check.py` ok. Self-test 66 mutations refused |
| Dhall negative control | gating the bed on `voiceOnly` alone fails `dhall type` (`Assertion failed`) |
| `just narrate-lint narrate-test` | ruff clean, 757 passed, 1 skipped |
| `tests.test_public_tree`, `tests.test_timeline_contract` | 78 tests OK, 1 skipped (no private terms file) |
| `just check` | 2206 tests: 8 failed or errored, 188 skipped. All 8 are the same marked-video and marked-compact renders raising `No bounded supported installed font found`, as in the first run. `scripts/doctor.py --require-media` exit 0 |

Open for the operator: whether `ClientNarrated` applies beyond the deck
project. Open for L8: the deck's `stems.json` must add the pre-tighten take
digest. Narrate's own renderer still writes a caption and VTT label. KP-15 no
longer requires it, and removing it is a narrate change outside L2.

## Next

- Root reviews and merges. L3 (graph core) branches from the merge.
- Root records the narrated-video issue ids in `program/linear.json` when it
  confirms the W8 and W9 lane names.
- L5 decides whether kitpip writes `avatar_overlay_v1` or the stage wraps it.
