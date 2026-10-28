# Narrate seat session receipt, 2026-10-27 to 10-28

Authority: R-HOOK-CONVERGENCE-20261004 (R-N13). Rulings are on Linear: TIN-7097 and TIN-7085 (narrate), TIN-7476 (kitpip and the narrated-video pipeline) and TIN-7125 (the wider programme). Private material (voice clips, rendered narration, client text, deck files and the work directories that hold them) stays outside this repository.

## Landed in this repository

| PR | Merge | What it does |
| --- | --- | --- |
| #48 | 6a1e320c | Private presentation adapter, fixed after review |
| #56 | baad4e05 | Narrated-video spec and types (NV-1 to NV-7) |
| #57 | 48d397bc | Narrate pins xoxd-lexical 0.7.0. The pronunciation table is unchanged, and 22 register rules are added |
| #58 | 7a7a30dc | Narrated-video graph core: stage keys, the content-addressed store, admit, and init, plan, status and explain |
| #59 | 10f8a87a | Reproducible Vulkan build of the audio.cpp batch binary, plus the pod-phase contract, salvaged from #42 |
| #60 | 0a55e660 | Narrated-video simple path: script, voice, voice_qa, base, place, music and mix, plus `just nv-quick` |

#42 was closed as superseded. Its unique parts are in #59.

## Rulings that bind this repository

- NV-6: ClientNarrated is the default edition for client videos. The spec and type default still need to follow.
- NV-8: the kitpip avatar is opt-in until the L6 avatar stage lands, then on by default.
- KP-15, VRM-2 and VRM-17: no visible synthetic or AI-persona label is required. The labels stay in manifest metadata. Narrate's caption prefix removal is a follow-up.
- Music bed: Splice licence terms were read from primary sources. The operator holds the licence certificate, and raw loops never enter git.

## Open

| Item | Owner | State |
| --- | --- | --- |
| ClientNarrated default in spec and types (NV-6) | narrate | to do |
| Narrate caption prefix removal (KP-15) | narrate | to do |
| Avatar persona in the avatar knobs key (L5) | narrate | to do |
| Slide-card port, pipeline L5 to L10, co-owned with the deck seat | narrate | sprint 3, week one |
| audio.cpp binary parity: the host build differs from the #59 Nix build (native CPU flags) | narrate, inference lane | parity render and re-pin before any pod phase |
| Bed level reading (un-ducked against ducked) | narrate | matched-loudness A/B |
| 8 marked-video font failures on the build host | unowned | predate this session |
