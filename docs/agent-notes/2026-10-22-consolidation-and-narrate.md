# Consolidation and the narrate lane (2026-10-22)

Authority: operator decisions of 2026-10-22 in the planning session; R-HOOK-CONVERGENCE-20261004 R-N11/R-N12/R-N13.

Linear receipts:
- The tracker diff is comment `950e73fb` on TIN-3692.
- The video-utils hand-off closure is comment `6a0617aa` on TIN-6569.

The sprint contract is `docs/spec/sprints/20261022-S5.md`, mirrored in `program/linear.json`.

The private research behind this note stays on an operator host, outside git:
- an estate survey of 18 read-only lanes;
- an adversarially checked synthesis;
- licence copies.

Only public-safe facts are recorded here.

## Operator decisions

| Topic | Decision |
| --- | --- |
| Narrate owner | A `narrate/` lane in this repository: client, CLI, spec, Dhall, MCP tools and evaluation. Serving, deployment and agent exposure are proposed to their owning repositories. Voice data stays outside git |
| GPU | Attended windows of 30 min or less on the GPU host, each holding the single GPU lease, with a receipt. Development on the Mac host with MLX. Switch-native serving in N1, after P-TIN-193 M3 |
| Voices | v0 clones the operator's own voice only. A 10–30 s clip with a verified transcript and a consent record, hash-bound and outside git |
| Engine order | On-prem open weights, then rented GPUs with open weights, then hosted APIs last. Hosted calls are refused for confidential jobs |
| Lexical rules | Pinned xoxd-lexical `slides` register plus a local pronunciation table. A narration register is a later upstream bump (TIN-7097) |
| Sprint shape | S5 operator sessions and condense v5 closeout (11-06), S5 livecode shard (11-06), N0 (10-25), N1 (11-07). Project target 11-14 |

## S4 outcome per milestone (closed 2026-10-22, main 5f676a9)

| Milestone | Done | Carried to S5 | Closing evidence |
| --- | --- | --- | --- |
| Condense on real talks | TIN-6543, 6545, 6546, 6573, 6574, 6575 | TIN-6544, which now also covers the long-clip full render | Parity receipt (#25) with 12/12 and 11/11 matches; the long clip's full render was not compared; hash-bound `check.json`; `condense-all` ends in a verified run. Measured: the tool tier is still +194 frames and 0/520 cues, unchanged by TIN-6573; the seeded tier is −1 frame and 520/520 |
| Close the guitar core | none | TIN-5491 (labelling hour), TIN-5494 (Mac editor import) | The onset scorer landed (#27). No operator labels, so no precision/recall figure |
| S3 hosting and site | TIN-5722 | TIN-5723 (Pages deploy go), TIN-5717 (parent) | The bazel job is blocking. The blocking site job landed (#26). No deploy |
| Hygiene and peers | TIN-6515, 6514, 6577 | none | The whole-tree scan is in place. The HTTP STT backend landed. The site link is lock-neutral |

TIN-6578 is Done, but only partly. It had no milestone; it was attached to "S4 — Hygiene and peers" on 2026-10-23
after review. The STT cache key and the provenance URL landed in 5f676a9. Two items moved to
TIN-7083: MCP admission of the HTTP STT backend, and the archived-receipt residue. TIN-6576 and TIN-6579 are Low and
in S5. TIN-5720 and TIN-5721 are Backlog under the Future hosting milestone; TIN-5721 is blocked by TIN-5619 and
TIN-5590.

## Hygiene actions taken

All of this happened in the operator's checkout of this repository. Nothing was pushed or deleted on the remote.

- **R-N11 check first.** For each of the 5 worktrees: process cwd scan, `lsof +D` and the live-session sockets.
  None had a holder.
- **Salvage.** Every worktree's `git diff HEAD`, untracked list and archive, ignored run artifacts and HEAD went to a
  private salvage directory on an operator host, as 643 files under one sha256 manifest. The superseded review UI work
  in progress is kept there as a patch.
- **Bulkload hand-off.** Its `--check` refuses because its plan state is gone. It was closed by a Linear comment, not
  by editing the block. That matches the precedent in another repository's lane.
- **Removed.**
  - 5 linked worktrees: the condense-parity worktree and the 4 sprint-1 worktrees.
  - 1 patch-equivalent branch with `-D`, after `git cherry` showed 5 of 5 commits already on main.
  - 50 merged `sprint/*` branches with `-d`.
    The synthesis had counted 51. The pre-deletion branch list was not saved, and the reflog keeps only 6 of the
    names, so the difference of one is unexplained. `-d` refuses unmerged branches, so no unmerged work was lost.
- **Main checkout.**
  - 4 stale untracked paths were moved into salvage, not deleted. Each had been superseded by the RU1 site uplift
    or was a private session note, and none is referenced by tracked files.
  - The editor tool's local cache directory was added to `.git/info/exclude`.
- **Left alone.**
  - `origin/feat/livecode-shard` (PR #30).
  - A concurrent narrate worktree.
  - Every other owner's repositories and PRs. Those get proposal comments only.

## Model plan (verified claims; every pin is still to be recorded)

The bench (W3, TIN-7085) has three arms, on the GPU host over Vulkan and on the Mac host over MLX:

- **Ming-3.0-tts-0.5B**, the favoured primary.
  - MIT licence, about 1.48B parameters in total, 44.1 kHz output.
  - It is the highest open-weight entry on the Artificial Analysis cloning board.
  - It runs offline in audio.cpp over Vulkan.
  - The repository is days old, so pin the commit and the model revision.
  - Sources: [model](https://huggingface.co/inclusionAI/Ming-3.0-tts-0.5B), [code](https://github.com/inclusionAI/Ming-3.0-tts), [audio.cpp](https://github.com/0xShug0/audio.cpp).
- **Qwen3-TTS-12Hz-1.7B-Base**, the fallback and baseline.
  - Apache-2.0.
  - It is the only candidate with a measured run on this GPU family, at RTF about 0.16 over Vulkan.
  - It needs a verified `ref_text`, plus chunking with rollback for long text.
  - Sources: [model](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-Base), [llama.cpp #26254](https://github.com/ggml-org/llama.cpp/pull/26254), [qwentts.cpp](https://github.com/ServeurpersoCom/qwentts.cpp), [long-form failure rate](https://arxiv.org/abs/2609.16989).
- **VoxCPM2**, the third arm.
  - Apache-2.0, 48 kHz output.
  - On PyTorch ROCm, force bf16 and add a CPU parity check, because fp32 SDPA silently corrupts on this GPU family.
  - Sources: [model](https://huggingface.co/openbmb/VoxCPM2), [pytorch#201476](https://github.com/pytorch/pytorch/issues/201476).

Rented tier: **Fish Audio Drama 3**.
- It is the top open-weight entry on the AA provider board. That entry is named a preview, so whether it measures the
  released checkpoint is unproven.
- It needs a rented card of 48 GB or more, served with vLLM-Omni or SGLang-Omni.
- Its Community License requires:
  - estate revenue under USD 500k;
  - consent for cloning;
  - a "Built with Fish Audio" notice;
  - no training on its outputs.
- Sources: [model and licence](https://huggingface.co/fishaudio/drama-3), [code](https://github.com/fishaudio/fish-speech), [vLLM-Omni](https://docs.vllm.ai/projects/vllm-omni/en/latest/serving/speech_api/).

Hosted, as a last resort and for public content only: ElevenLabs v4, then the Fish API.
- Source: [ElevenLabs v4](https://elevenlabs.io/docs/overview/capabilities/text-to-speech/eleven-v4.md).

Leaderboards: [AA controlled voice](https://artificialanalysis.ai/text-to-speech/leaderboard/controlled-voice) and
[AA provider voice, open weights](https://artificialanalysis.ai/text-to-speech/leaderboard/provider-voice/open-weights).

Limitations:
- No RTF or VRAM figure exists for any candidate on the 16 GB card itself.
- Long-form drift is unbenchmarked everywhere.
- Which Ming variant the AA board tested is unknown.
- WER is a regression gate, not a ranking. Rare-word ASR errors are adjudicated by hand.
- Hosted prices come from secondary sources and are unverified.
- None of these is a listening claim. The operator's blind A/B receipt is its own state.

## Open problems

1. **S4 milestone dates.** They still read 10-22 in the tracker. Only the project date moved, to 11-14.
2. **Hand-off tooling.** The bulkload hand-off for this repository could not be cleared by its own tool, because its
   state is gone. That is an issue for the tool's owner.
3. **TIN-6978.** Its readback dates from the 10-22 survey. Nobody has re-read the cluster since.
