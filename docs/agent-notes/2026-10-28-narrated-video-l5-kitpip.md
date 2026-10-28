# Narrated video L5: kitpip pin and avatar, NV-6 and KP-15 (2026-10-28)

Authority: operator direction KP-13 and rulings NV-1 (`9db389dc`), KP-15
(`4ab7fc27`), NV-6 (`92605219`), KP-19 (`f446ae28`) and NV-8 (`df0ed8e6`), all
Linear TIN-7476 comments. NV-8 and the L4 review asked for the persona in the
avatar key. Receipt per R-HOOK-CONVERGENCE-20261004 (R-N11, R-N12, R-N13).

`narrated-video L5 | narrate seat | video-utils feat/narrated-video-l5-kitpip from main 0a55e660 | pin, avatar stages, NV-6, KP-15; gates below | root review and merge, then a real kitpip render after the quiet window and a release binary digest`

## What changed

| Area | Files | Change |
| --- | --- | --- |
| Registration | `program/externals.json` | registers kitpip publicly: record shape, manifest schema, mapping, resolution and gate states. No pin value (NV-1) |
| Pin | `narrate/video/kitpip.py` | loads the private pin and refuses a URL, path or host in it, a short commit or a malformed digest. A pin with no release digest resolves `pending` |
| Avatar stages | `narrate/video/kitpip.py`, `narrate/video/run.py` | `run` executes `avatar` and `avatar_check`. avatar_check re-runs `kitpip verify` and checks the frame digest, consent ids and label chain |
| Command shape | `narrate/video/kitpip.py`, stub | `analyze` gets `--rig`. `render` gets `--size WxH` and `--encode mov`. The wrapper never passes `--badge` (KP-19) |
| Persona key | `narrate/video/graph.py` | `labels.persona` is an avatar knob, so a persona change reruns the overlay |
| Pin check | `narrate/video/cli.py`, `just/narrated-video.just` | `pin-check` and `just kitpip-pin-check` |
| NV-6 | `narrate/dhall/{Edition,NarratedVideo}.dhall`, `narrated-video-test.dhall`, `check.py`, `narrate/video/job.py` | `Edition.clientDefault` and `defaults.clientEdition` are `ClientNarrated`. `init --client` uses it. `ClientVoiceOnly` stays per project |
| KP-15 | `narrate/render.py`, `narrate/tests/test_render.py` | no `[Synthetic voice] ` caption prefix and no VTT NOTE. `synthetic: true`, consent ids and `synthetic_label_required` stay in the manifest |
| Hooks and skills | `program/tool-drafts/narrated_video.json`, `.agents/skills/{kitpip-overlay,kitpip-verify,narrated-video}/SKILL.md` | drafts of tools 66 and 67, not admitted. L7 admits them |
| Spec | `docs/spec/NARRATED_VIDEO.md`, `docs/spec/NARRATE.md`, `narrate/README.md` | the decisions table, pin, avatar stages, editions and KP-15 |
| Tests | `narrate/tests/test_narrated_video_avatar.py`, graph, simple, types, `tests/test_public_tree.py` | 28 avatar and pin tests, the NV-6 tests, the persona row and a public-tree check that the registration holds no pin value |

## The pin

NV-1 rules that the kitpip pin lives in a private record. The computed task
asked for the pin in `program/externals.json`. This lane kept the ruling: the
public file registers the shape, and the private record holds the values. It
names the kitpip commit that merged KP-19, the face schema and stream mode,
the default rig `kitpip-v1` revision 2 and the SHA-256 of its rendered JSON.
kitpip has no release build at that commit: no tag, no release and no flake
package. The binary table is empty and `gate_state` is
`commit_pinned_digest_pending`.

| Item | Value |
| --- | --- |
| Private record SHA-256 | `1cf1556d4a6b2d00cc402766d3e20671675047675507a45ee3aca5259393fcbb` |
| `pin-check` on it | refused `kitpip_pin_pending`, exit 1 |
| `pin-check` on the stub's test record | `ok: true` |

## Findings

| Finding | Effect | Fix |
| --- | --- | --- |
| The L3 wrapper passed `--size 512`. kitpip takes `WxH` | kitpip would refuse every real render | `--size {n}x{n}`. The stub now refuses a bare number |
| `analyze` ran without `--rig` | prosody followed kitpip's default rig, not the keyed one | `--rig` on both commands |
| `render` wrote the VP9 sidecar by default | a second encode that nothing reads | `--encode mov` |
| The avatar key had no persona, but its manifest carried one | a persona change left the overlay fresh with stale labels | persona is an avatar knob |

The command shape comes from kitpip's own CLI flag table at the pinned commit.
No real kitpip binary ran.

## Evidence

All runs used `nix develop .#condense` inside `systemd-run --user --scope -p
MemoryMax=6G -p MemorySwapMax=0 nice -n 19`. The quiet window (TIN-6833) ran
no cargo, Bazel, Go or image build.

| Check | Result |
| --- | --- |
| `narrate/tests/test_narrated_video_{graph,simple,types,avatar}.py`, `test_render.py` | 226 passed |
| full `narrate/tests` | 950 passed, 1 skipped |
| narrate-dhall-check steps | every file types, formats and renders. `check.py` ok, self-test 66 mutations |
| Red control | `clientDefaultIsNarrated` set to `ClientVoiceOnly` fails `dhall type` |
| ruff and shellcheck over `narrate/` | clean |
| `tests/test_public_tree.py`, `tests/test_timeline_contract.py`, `tests/test_mcp.py`, `tests/test_s5_tool_admission.py` | 97 passed, 1 skipped (no private terms) |
| `narrate/tests/stdlib_smoke.py` | 7 tests OK |

## Open

- A real local render with a digest-only receipt needs a kitpip release
  binary and its digest in the private pin. Both wait on kitpip L1.
- Bazel, cargo and `just check` wait until the quiet window ends.
- NV-8: L6 turns the avatar on by default.
