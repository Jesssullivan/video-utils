# S2 release record (TIN-5492)

Sprint `20261006-s2`. Linear parent TIN-5599; release issue TIN-5492 (D7).
Written October 6, 2026 on branch `sprint/20261006-s2/release_closeout` from
base `e3ef39b` (local `main` with every S2 lane merged). This is a
documentation-only closeout. It changes no code, tests, tool descriptors or
profiles, and it did not read or write Linear.

Authority: the operator S2 prompt and interview in the
[S2 resume](../../2026-10-06-s2-resume.md); R-HOOK-CONVERGENCE-20261004
(TIN-3692 comment `98cf680c-7299-4949-bfb2-60079053ad43`) R-N11/R-N12/R-N13.
Attribution: fable ultracode (workflow), video-utils-d6.

```
actor: release_closeout writer (workflow lane under /root video-utils-d6)
target: docs/spec/PROJECT.md, docs/spec/sprints/S2_FOLLOWUPS.md, this file
reason: S2 closeout for TIN-5492
ruling: R-HOOK-CONVERGENCE-20261004 R-N13 (receipt); R-N11 no foreign targets signalled
prior_state: worktree clean at e3ef39b; remote main 4ec475e (git ls-remote)
result: one unsigned (--no-gpg-sign) docs commit on the lane branch; root signs, merges, pushes and updates Linear
```

## Product status

The per-day and per-lane statuses (done / partial / unknown / deferred), with
their evidence and limits, are in
[PROJECT.md § S2 status](../../../spec/PROJECT.md#s2-status--october-6-2026).
Queued work is in [S2_FOLLOWUPS.md](../../../spec/sprints/S2_FOLLOWUPS.md). In
short: D1 is done with its declared FFmpeg-orchestration deviation. D2–D7 are
partial. Robustness is done for its stated scope. The WEB branch is done locally
and the hosted service is LATER. The native AU spike is partial. Stems are
deferred because the weights have no qualified licence.

## Merged lanes

`git log --format='%h %G?' --merges 4b87484..e3ef39b` reports `G` (good
signature, key `D34D0D8F65EE5C88`) for every merge listed here and for `e3ef39b`.

| Lane | Linear | Merge commit | Recorded Linear state |
|---|---|---|---|
| rust_core | TIN-5607 | `f563807` | Done |
| cap_ids | TIN-5605 | `abaf7b7` | Done |
| editor_export | TIN-5606 | `09d64c5` | Done (TIN-5494 future interop In Progress: application import unverified) |
| lowreg_spec_v4 | TIN-5608 | `2a1adfe` | Done |
| annot_corpus | TIN-5604 | `e0da4ca` | Done |
| root_admission_b (4 tools, D1 deviation) | TIN-5599 | `739427c` | n/a |
| web_jobs | TIN-5614 | `885ca69` | Done |
| web_stack | TIN-5613 | `1b72abe` | Done |
| au_auval | TIN-5612 | `076993d` | Done |
| fuller_profile | TIN-5600 | `34629dc` (handoff `a586ee9`) | Done |
| rhythm_clicks | TIN-5602 | `736f406` (handoff `0cdca01`) | Done |
| share_export_fix | — | `7ad3548` | n/a |
| root_admission_c (FULLER default, frozen S1 rhythm, tools 37–38) | TIN-5599 | `ccf47b3` | n/a |
| tone_ab | TIN-5601 | `94614c9` | Done |
| phrase_anchor_riff | TIN-5603 | `af3db44` | Done |
| root_admission_d (tool 39, timing direction withheld) | TIN-5599 | `ef31930` | n/a |
| web_ui_binding | TIN-5615 | `d6247e6` | Done |
| gitleaks_fixture_fix | — | `2252c89` | n/a |
| ui_core | TIN-5610 | `1741e33` | Done |
| robustness | TIN-5609 | `4be2812` | Todo at last record; not updated after merge |
| report_d6 | TIN-5611 | `ebaf72d` | Todo at last record; not updated after merge |
| web_reliability | TIN-5616 | `3e397ad` | Todo at last record; not updated after merge |
| root_admission_e (tool 40 `report_bundle`, demo-resume recipe) | TIN-5599 | `46aee65` | n/a |
| share_export web_job adapter admission (direct root commit) | — | `e3ef39b` | n/a |

The Linear states above come from `verified_state` in
`program/sprints/20261006-s2.json` and from [HANDOFF.md](HANDOFF.md). That file
also records parent issues as follows. D1–D5 (TIN-5486 to TIN-5490), CAP
TIN-5493, IDS TIN-5549, CORPUS TIN-5548 and STACK TIN-5551 are Done. JOBS
TIN-5550, TIN-5494 and TIN-5599 are In Progress. **No state is recorded for D6
TIN-5491 or D7 TIN-5492.** Root must set and read back TIN-5609, TIN-5611,
TIN-5616, TIN-5550, TIN-5491, TIN-5492 and TIN-5599. A Done state does not
upgrade the product statuses in PROJECT.md.

## Hosted CI

| Run | Head | Conclusion | Counts (from the root record) |
|---|---|---|---|
| [37475103398](root-hosted-ci-37475103398.json) | `739427c` | success | 1169 Python OK / 64 optional skips; Rust OK; no leaks |
| [37522614603](root-hosted-ci-37522614603.json) | `ef31930` | success | 1375 OK / 97 skips; Rust OK; no leaks |
| [37525406189](root-hosted-ci-37525406189.json) | `5436b2d` | failure | Python and Rust passed. Secret scan failed on high-entropy synthetic web fixture idempotency keys, fixed by `2252c89`. |
| [37530756098](root-hosted-ci-37530756098.json) | `2252c89` | success | 1399 OK / 106 skips; Rust OK; no leaks |
| [37531977858](root-hosted-ci-37531977858.json) | `1741e33` | success | 1423 OK / 106 skips; Rust OK; no leaks |

**Not yet qualified by hosted CI:** `4ec475e`..`e3ef39b`. That covers the
robustness, report_d6, web_reliability and root_admission_e merges and the
web_job adapter commit. When this was written, `git ls-remote origin
refs/heads/main` returned `4ec475e`, and `gh run list` showed no run after
37531977858. Local verification of those merges is in their lane handoffs and
in [root_admission_e](root_admission_e-receipt.json). Local runs inside
`.local/` worktrees show five known environmental `test_tool_contracts` errors
(the calibration-path check refuses the `.local` dot component). These are
expected to pass from the main checkout path. This is an inference and has not
been verified at this head.

## Tool count

40 typed tools and 40 skill directories. Counted at `e3ef39b`: 40 entries in
`program/tools.json` `tools`, and 40 directories under `.agents/skills/`. The S2
additions are 32 → 36 (`739427c`), 38 (`ccf47b3`), 39 (`ef31930`) and 40
(`46aee65`). The freeze hashes for `tools[:30]`, `[:32]`, `[:36]`, `[:38]` and
`[:39]` are recorded in the admission receipts. `tools[:40]` is not frozen in
tests.

## Protected media unchanged

Both checks were read-only and were run at closeout on October 6, 2026.

- **Desktop export.** `shasum -a 256` of Desktop `video_util_mvp_demo_1.mp4`
  (21,596,491 bytes, mtime Oct 6 01:22 local) returned
  `34247a4e2deec03f7d7e3bf4f8eef66f64bbe721d88013105a3cf88ed0734f10`. This
  **matches** the protected value in `program/sprints/20261006-s2.json`.
- **Accepted run `artifacts/runs/20261006T041633Z-990aa1bd6737`.** It holds 13
  regular files, and none was modified after the S2 start (2026-10-06T08:35:05Z;
  the newest mtime is 00:21:50 local). The `manifest.json` sha256 is
  `61c9b3930c36d050818901138eb1820d5dc940e3603d38f019bde793da750a5f`, which
  equals the value in [editor_export-real-take-receipt.json](editor_export-real-take-receipt.json).
  The lane receipts also record it as unchanged: a tree digest of `f641b367…`
  before and after in [web_reliability-real-web-job.json](web_reliability-real-web-job.json),
  and 13/13 files in the tone A/B run.
- The original take in Documents was read by lanes only. Its sha256 matched
  `a522115f…6c6` in the editor_export real-take receipt. This closeout did not
  open it.

## Deferred and not performed

The prioritized list with completion evidence is in
[S2_FOLLOWUPS.md](../../../spec/sprints/S2_FOLLOWUPS.md). The highest-impact
open states are:

- **Quarto render** `render_blocked_on_host`. Pandoc 3.7.0.2 rejects
  `syntax-highlighting`. The one approved attempt exited 1 after 1172 s. A
  retry needs a flake fix plus operator approval.
- **Editor import**: FCPXML/Resolve export exists, but application import was
  not performed. Neither application was found in `/Applications`.
- **AU**: stage 2 discovery is `blocked_not_installed`. The Logic host check
  was not performed. Installation is out of scope.
- **Stems** are deferred because the pretrained Demucs weights have no licence
  grant. **Beat This** was not run.
- **Real-take phrase correctness** is unknown until the operator marks at
  least 10 boundaries. **Per-phrase timing direction** is withheld until capture
  latency is calibrated.
- **Pitch**: the C1 result of 34/426 stands. No note verdicts are made.
- **Listening**: the tone A/B preference is not recorded, and there is no
  listening acceptance for any S2 output.
- **Memory ceiling** is unknown. **Hosted web access** is LATER (TIN-5552).

## Worktrees

- **Keep all six** `.local/sprint1/*` worktrees: annotations, audit, corpus,
  low_register, phrases and review_ui (review_ui is intentionally dirty).
- **S2 worktrees** under `.local/sprint2/*` can be reclaimed once landed. Every
  remaining S2 branch head is an ancestor of `e3ef39b`
  (`git merge-base --is-ancestor`). The au_auval worktree has an untracked
  `native/au-spike/target/`. Before any removal, copy the gitignored lane
  artifacts that are still only in their worktrees: au_auval, fuller_profile,
  report_d6 (render log and bundle), rhythm_clicks, share_export_fix, web_jobs,
  web_reliability, and the tone A/B listening excerpts. Main `artifacts/s2/`
  already holds phrase_anchor_riff, robustness, tone_ab, ui_core and
  web_ui_binding. "Landed" here means merged on local `main`. Root may want the
  push and hosted CI first.

## Peer exchange (sting lanes)

Source: [peer note](../../2026-10-06-s2-peer-sting.md) and HANDOFF.md.

- **xoruby**: the V2 holdout bank is used for evaluation only, never training.
  V3, V4 and V5 were posted on TIN-5186. The
  [V2 receipt](../../peers/xoruby/V2-holdout-bank-receipt.json) is merged and was
  posted on TIN-5186 by root after hosted CI 37522614603 (root fact, recorded here). **V6 privacy wording
  and the V2 licence line await operator approval.** Real-take-derived outputs
  stay private.
- **Inference lane (llama.cpp)**: it got the V4 low-register spec and golden
  (`2a1adfe`) and the receipt schema example (09:08Z). The generated fixtures
  for its calibration study are routed through XORuby. TIN-5619 (Backlog) holds
  the later `guitar_noul` read-only gateway slot. No real-take audio left
  video-utils.

## Facts this record could not verify

- Linear states after `4ec475e`, and any state for TIN-5491 or TIN-5492. Linear
  was not read.
- Hosted CI for `4be2812`..`e3ef39b` (none had run).
- `program/sprints/20261006-s2.json` is stale. It shows robustness/report_d6 as
  `running`, web_reliability as `queued_wave2`, `tool_count` 39 and
  `integration_head` `1741e33`. It is root-owned and was not edited here.
