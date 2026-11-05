# TIN-7994 rented voice engine draft

Date: November 5, 2026. Base: `e3761ee6`, draft PR 91. Rulings: TIN-7125 `af4ceb3b`,
`704438d7`, `7958a23e` and `e385617a`, with the sprint plan `4f75ce59`, under
R-HOOK-CONVERGENCE-20261004 (R-N13).

Nothing was deployed, run or billed. No Modal account, token or Volume was touched.

## Changed

| Path | Change |
| --- | --- |
| `narrate/serve/modal_batch.py` | Sealed app, `run_plan` as the host side and only upload path, the `voxcpm2-batch-modal` record and the dry run |
| `narrate/serve/audiocpp_batch.py` | `--placement` in the receipt, and `--checkpoint-s` for takes that survive a kill. Defaults keep on-prem runs unchanged |
| `narrate/prerender.py`, `narrate/render.py` | A rented receipt under an on-prem record refuses, the manifest names placements, and `plan.json` lists its consents |
| `narrate/tests/test_modal_batch.py`, `narrate/tests/fake_modal.py` | The deployed function, the host path through a fake client that keeps client 1.6.1's behaviour, and the refusals |
| `narrate/tests/test_narrated_video_adopt.py` | Engine id, profile and voice id bind adoption |
| `narrate/dhall/policy-test.dhall` | The record's predicates |
| `docs/spec/NARRATE.md`, `narrate/README.md`, `just/narrate.just`, `CHANGELOG.md` | "Rented batch on Modal", the recipes and the entry |

## Corrected

The first draft's report said the consent code needed no change. That held only for
the plan gate. A review reproduced a `GpuDirect` job with no hosted consent reaching
the Volume and rendering, because no narrate code ran before the upload and a
receipt held no location. `run_plan` and `placement` close that path.

The first draft's mutation claim was too broad. It held for helpers and removal, and
14 of 16 mutants on the call sites survived. The PR body lists the rerun.

## Evidence state

| Item | State |
| --- | --- |
| Dry run with the fake client and fake `audiocpp_cli` | Measured. All checks passed, run local and non-qualifying |
| Real Modal SDK accepts the app | Measured again with client 1.6.1 and an empty config: the import registered `run_requests`, and `modal run ... --help` shows the options the host side passes. No call reached Modal |
| Client behaviour in `fake_modal.py` | Read from the client 1.6.1 source, not run against a real Volume |
| Mutation controls | Measured on a scratch copy of the tree: 47 mutants, the 16 from the review and 31 new, all fail `test_modal_batch.py`. The PR body lists them |
| `audiocpp_cli` in the Modal image | Unknown. No build exists, so the digest is a placeholder that refuses |
| NVIDIA Vulkan, uid 10001, mid-run Volume commits under the seal | Unknown until a smoke run |
| Audio on this card | Unknown. Listening stays with Jess |

## Limits

| Item | State |
| --- | --- |
| SP-4 | `--health-class none` is the author's statement. No job field carries a class and no code reads the text for health content |
| Pins on the Volume | Run data is wiped and the pins stay. The signed line says nothing stays on a rented disk after a run, and does not say whether that covers public weights and a binary. Open for Jess |
| Preemption cost | Takes copy as they finish, so `nonpreemptible` stays off and the estimate does not change. A preempted run pays again for what the last pass had not copied |
| Client dies mid-run | The run stays on the Volume until `abandon`. Nothing wipes it on its own |
| Merge route | On-prem takes render under the rented record when it pins both binaries, and the manifest says so. Whether that is acceptable stays open |
| Weights digest | Already public in `narrate/bench/sources.json` and `narrate/bench/host-job.json`. Not rechecked against Hugging Face |

Moving a job to this engine re-voices all its segments, because the voice key and
adoption bind the engine and voice records.
