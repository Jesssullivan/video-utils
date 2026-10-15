# condense-all ends in publish and verify-run (2026-10-15)

Authority: S4 sprint plan (`docs/spec/sprints/20261015-S4.md`); Linear TIN-6546; R-HOOK-CONVERGENCE-20261004
R-N13.

## Change

| File | Change |
| --- | --- |
| `just/condense.just` | `condense-all` ends with `condense-publish`. |
| `condense/__main__.py` | `all` runs `ALL` = every stage plus `publish`. A verify-run refusal exits 1 with one line, not a traceback. `main(argv)` runs only under `__main__`, so tests can call it. |
| `just/workflow.just` | `verify-run RUN_DIR TIMELINE=""`. Empty keeps the old command. `edl_v1` adds `--timeline edl_v1`. |
| `condense/README.md` | The quick start names `just condense-all` as the one command. The publish section shows the re-check. |
| `condense/tests/test_all.py` | New. `all` on the synthetic talk, with only whisper faked. |

`publish` already ran `video-utils verify-run --timeline edl_v1` and renamed a refused run to
`.failed-<run_id>`. `condense-all` does not run verify-run a second time. `just verify-run <run_dir> edl_v1`
re-checks a published run.

## Tests (`condense/tests/test_all.py`)

- `ALL` is `STAGES` plus `publish`, and `just --dump` shows `condense-all` depends on the same recipes in the
  same order.
- `condense all talk.toml silence loud` on a fresh copy of the synthetic recording publishes exactly one run.
  The run's manifest binds `talk.mp4`, `edl.json`, both captions and the corrected copy. `verify-run --timeline
  edl_v1` accepts it.
- With the manifest's `talk.mp4` digest zeroed, `condense all` exits non-zero with "verify-run refused". The
  only entry left in the root is `.failed-<run_id>`.
- The check stage runs `silence` and `loud` only. `sync` has its own tests. `bounds` needs whisper.

## Measured

| Gate | Result |
| --- | --- |
| `nix develop .#condense -c just cli condense-lint condense-test` | ruff clean; 57 passed (was 53), 63 s idle, 174 s under load, after the rebase on `e28dd9f` too |
| `condense/tests/test_all.py` alone | 4 passed, 14-22 s |
| Synthetic `all` run | 332 frames, 11.067 s; silence 0 hits; loudness -15.6 LUFS, true peak -4.2 dBTP |
| `just verify-run <run> edl_v1` on that run | exit 0, 9668828 bytes hashed |
| `just verify-run <run>` (default) | exit 1, `time_stretch_not_excluded`: unchanged default behaviour |
| `just test-rust` | 42 passed, 0 failed |
| `just check` in a fresh worktree | 2013 run; 26 failures and 6 errors, all outside this change: 24 need the web pnpm offline mirror, which a fresh worktree lacks, and 2 need an installed font. Hosted `offline` is the authority. |

No real recording, transcript or model was used. Hosted CI results are on the PR.
