# Narrate N0: engine pick and the golden voice setup (2026-10-26)

Authority: operator rulings J83(a) and J97(b) (re-run the bench with SIM and the A3 fix, then a blind A/B tonight);
operator answers in the narrate session on 2026-10-26; R-HOOK-CONVERGENCE-20261004 R-N13. Linear: TIN-7085, TIN-7084.

## Decision

| Item | Value |
|---|---|
| N0 engine | VoxCPM2 through audio.cpp at 47c2756e, "ultimate" clone (the reference is sent as the voice and as the continuation prompt, with its transcript) |
| Fallback | Qwen3-TTS-12Hz-1.7B-Base through qwentts.cpp at 5916bf7c, in-context clone |
| Rejected | Ming-3.0-tts (a read-voice window broke; windowed SIM fell to 0.03) |
| Reference length | 14 s or less, cut on word boundaries by `narrate/bench/ref_cut.py`; VoxCPM2's encoder holds 240000 samples |
| Persona tempo | 1.1×, pitch preserving, applied after synthesis and before page fitting (operator: "1.1x is great") |

## Evidence

Windows 2a (presenter voice) and 2b (read voice), seed 1, scored on the CPU host with whisper small.en and ECAPA SIM against
each voice's full consented clip. Decoys were valid in both windows (self-match 0.876 and 0.882, wrong speaker −0.047 and −0.125).

| Arm | SIM median 2a | SIM median 2b | Bars | WER | RTF (2a) | Peak VRAM |
|---|---|---|---|---|---|---|
| VoxCPM2 (14 s cut) | 0.792 | 0.812 | met | 3.9% | 0.58 | 6.6 GB |
| Qwen3-TTS (full clip) | 0.747 | 0.788 | met | 4.3% | 0.66 | 6.8 GB |
| Ming-3.0 (full clip) | 0.523 | 0.575 | windowed SIM missed in 2b | 3.1% | 0.77 | 3.5 GB |

Blind A/B, operator: the VoxCPM2 sample was preferred in both voice sets; the Ming read sample "sounds completely broken". A
later persona read on an external microphone gave samples the operator called excellent. The output sound follows the
reference recording, so reference quality (microphone, room, gain) is now the main lever on voice quality.

## Durability

The voice references, consent evidence, voice registry, style profile, render kits and scores are private. They live
outside git, bound by sha256, with a second verified copy on the estate archive host. Engine binaries and weights are pinned
by sha256 in `narrate/bench/sources.json` and the bench job, and can be rebuilt and re-fetched.

## Open

- Seeds 2 and 3 for VoxCPM2 and Qwen3-TTS (stability check; decision of 2026-10-26).
- A VoxCPM2 batch engine path in narrate (planning, one GPU batch, then QA and fitting) and a per-voice default tempo field.
- Switch serving for VoxCPM2 (TIN-7368, N1).
