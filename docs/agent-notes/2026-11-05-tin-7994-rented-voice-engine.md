# TIN-7994 rented voice engine draft

Date: November 5, 2026. Base: `388c06b5`, draft PR 91. Rulings: TIN-7125 `af4ceb3b`,
`704438d7`, `7958a23e` and `e385617a`, with the sprint plan `4f75ce59`, under
R-HOOK-CONVERGENCE-20261004 (R-N13).

Nothing was deployed, run or billed. No Modal account, token or Volume was touched.

## Changed

| Path | Change |
| --- | --- |
| `narrate/serve/modal_batch.py` | Sealed app, the `voxcpm2-batch-modal` record, custody steps and the dry run |
| `narrate/tests/test_modal_batch.py` | The seal, the record, plan to render on a fake Volume, resume, refusals and the wipe |
| `narrate/tests/test_narrated_video_adopt.py` | Engine id, profile and voice id bind adoption |
| `narrate/dhall/policy-test.dhall` | The record's predicates |
| `docs/spec/NARRATE.md`, `narrate/README.md`, `just/narrate.just`, `CHANGELOG.md` | "Rented batch on Modal", the recipe and the entry |

## Evidence state

| Item | State |
| --- | --- |
| Dry run with the fake `audiocpp_cli` | Measured. All 12 checks passed, run local and non-qualifying |
| Real Modal SDK accepts the app | Measured with client 1.6.1 and an empty config. The import registered `run_requests` with every sealed keyword. An earlier nested function was refused and moved to global scope |
| Mutation controls on the seal | Measured on a scratch copy: retries, `block_network`, the probe, the wipe, the built environment and the root drop each fail a test when changed |
| `audiocpp_cli` in the Modal image | Unknown. No build exists, so the digest is a placeholder that refuses |
| NVIDIA Vulkan, uid 10001, Volume commit under the seal | Unknown until a smoke run |
| Audio on this card | Unknown. Listening stays with Jess |

## Limits

The app has no launcher, so `modal run` is the only way in, and it needs a spend go.
Moving a job to this engine re-voices all its segments, because the voice key and
adoption bind the engine and voice records.
