# TIN-7092 livecode main merge

Date: November 4, 2026. Direction: Jess, TIN-7125, "Rebase and revive" for video-utils#30.
Ruling: R-HOOK-CONVERGENCE-20261004 R-N13. Parent: TIN-6568.

## Change

This merge brings main `6eb14722` into `feat/livecode-shard` at `7ec79913`. The branch sat 230
commits behind and conflicted on 5 files. Each file takes main's structure and keeps the shard.

| File | Resolution |
| --- | --- |
| `justfile` | main's narrate imports, then `just/livecode.just` |
| `tests/BUILD.bazel` | `//livecode:all_files` beside `//narrate:all_files` |
| `.github/workflows/ci.yml` | the livecode step and the narrate Dhall step both stay |
| `BUILD.bazel` | main's package comment with livecode added |
| `tests/test_bazel_graph_s3.py` | narrate and livecode in all 3 lists |

Two breaks merged without a marker. `flake.nix` defined `packages` twice, which Nix refuses, so
main's block is now the `x86Packages` binding, joined to the shard packages by `recursiveUpdate`.
`REQUIRED_FILES` in `test_bazel_graph_s3` was 15 on both sides and is now 16.

The port from lab #2733 and #2735 is not in this merge, so TIN-7092 acceptance stays open.

## Evidence

All runs are local and non-qualifying. They used a merge of the same 2 parents with a tree equal
to this one apart from this note. Hosted CI has not run on it.

| Check | Result |
| --- | --- |
| `just livecode-check` | pass: shellcheck, 22/22 on source, 22/22 in the Nix check |
| `test_bazel_graph_s3` | 54 run, OK, 1 skipped |
| `test_public_tree`, `test_mcp`, `test_capabilities` | 30 run, OK, 1 skipped |
| `test_public_tree` with a private-term file | OK, no skip, hits checked as counts only |
| Bazel `--batch` test of `//livecode/...` and `//tests:test_bazel_graph_s3` | 2/2 pass |
| Bazel `--batch` query `rdeps(//livecode/..., //:repo_data)` | empty |
| Bazel `--batch` `build --nobuild //... --lockfile_mode=error` | rc 0, 229 targets |
| Bazel `--batch` `mod graph --lockfile_mode=error` | rc 0 |
| `just test` equivalent, 113 modules in 12 chunks | 2,211 run, 188 skipped, 2 failures, 6 errors |
| `condense/tests/test_all.py` | 4 passed |
| `narrate/tests/test_relay_readback.py` | 155 passed |
| `scripts/doctor.py --require-media` | rc 0 |
| `just narrate-dhall-check` | rc 0 |
| `gitleaks dir --redact .` | rc 0, on a tree before the count fix |
| `nix eval` of flake outputs | x86_64-linux has `cade-render-worker-image`, `livecode` and `narrate-bench-audiocpp`. aarch64-darwin has `livecode` |

The 8 unittest failures are the same 8 test IDs on main `6eb14722`. All 8 are real-media tests in
modules this merge does not touch:

| Module | Tests |
| --- | --- |
| `test_arrangement_markers` | `test_alternate_intent_preview_preserves_vfr_and_aac_without_canonical_edits` |
| `test_marked_compact` | `test_audio_shorter_than_picture_refuses`, `test_compose_copies_picture_and_audio_branch_exactly`, `test_edited_arrangement_markers_refuse`, `test_input_mutated_mid_run_refuses` |
| `test_marked_video` | `test_real_nonzero_origin_render_preserves_picture_pts_and_audio`, `test_failed_verification_preserves_diagnostic_preview_and_existing_inputs` |
| `test_tool_contracts` | `test_real_marked_video_mcp_preserves_vfr_audio_and_rejects_stale_evidence` |

The log shows `No bounded supported installed font found` for 7 of them. The eighth logs only
`isError` True, so its cause is inferred. The likely cause is host-specific: `installed_font`
accepts a Debian DejaVu path or macOS fonts (`scripts/marked_video.py:311`). Hosted CI on
`6eb14722` succeeded, so treat these 8 as unverified on this merge until hosted CI runs them.

Not run: `just test-rust`, the full `bazel test //...`, the condense, narrate, web and site CI jobs and hosted CI.
Capture itself stays unverified, because only an operator run on macOS proves it.

## Remaining

| Item | Source | Detail |
| --- | --- | --- |
| Segmented `rec` | lab #2733 | MKV segments in `<recording>.parts/`, concat at stop |
| Supervisor | lab #2733 | restart on exit or stall, give up after 5 fast failures |
| Reconnect | lab #2733 | restart re-reads the default input, `stream` reconnects |
| Capture fixes | lab #2733 | `rec` moves to `-fps_mode vfr`, bounded input queues |
| Screen shear | lab #2735 | uyvy422 default, `LIVECODE_SCREEN_PIXFMT` |
| Audio watchdog | lab #2735 | `astats` and `ametadata`, 8 second stall restart, silent-start warning |
| Tests | both | 9 lab contract tests to port, plus `.parts` concat coverage |
| Docs and version | both | README, skill, `package.nix`, `--version` and the CHANGELOG row move together |
| Deskew | TIN-7095 | `deskew.py` has no located source, so it needs a source or a fresh write |
| Upstream stride report | TIN-7094 | draft here, operator submits |
| Bluetooth drop acceptance | TIN-7093 | operator only |
| Lab package switch | lab PR B | consumes this package after merge |

The port must not carry the lab script's host defaults. Any volume UUID or label stays out of this
public tree.
