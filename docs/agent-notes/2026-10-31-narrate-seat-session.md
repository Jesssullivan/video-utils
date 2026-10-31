# Narrate seat session receipt, 2026-10-30 to 10-31

Authority: R-HOOK-CONVERGENCE-20261004 (R-N13) and repository AGENTS.md. The standing authorization for narrate-dispatched lanes is SPR-214 (TIN-7125 comment 0cbbe60a). Rulings are on Linear. TIN-7125 holds the wider programme and TIN-7788 the demo delivery DAG. TIN-7735 and TIN-7088 hold narrate work. The full ruling list is the register, Linear document 335943703835 on TIN-7125. Private material stays outside this repository. That covers voice clips, rendered narration, client text, decks and the work directories that hold them.

`narrate seat notes | narrate seat | video-utils docs/tin-7125-narrate-seat-session-20261031 | receipt for #74 to #78 | root review and merge`

## Landed in this repository

| PR | Ticket | Head | Merge | What it does |
| --- | --- | --- | --- | --- |
| #74 | TIN-7735 | e8d483dc | 4f1fa4aa | The claims gate refuses private terms when a bundle declares them. This is the ip_private guard of SPR-220 |
| #75 | TIN-7088 | 2a00cfd3 | 5663ddff | WER normalises words the same way on both sides. Names no longer fold as units |
| #76 | TIN-7788 | 4953c679 | fc0eca97 | `nv accept` records an operator gate by Softproxy decision id and binds it to the reviewed cut. Demo DAG item P1 |
| #77 | TIN-7788 | 6d594a42 | 44231111 | Neutral avatar tools, visible slide text in the guard and a metadata strip at compose. Demo DAG item P2 |
| #78 | TIN-7788 | 24e65095 | 94d2fcbd | Low findings from the #76 and #77 reviews. `status` recomputes the operator view and `accept` binds `job.json` |

Root merged each head with `--match-head-commit` after a final adversarial review. CI was green with 12 of 12 checks on each. The Linear receipts for #76, #77 and #78 are TIN-7788 comments 87fac6c4, 20354041 and edfa1a3a. The #75 receipt is on TIN-7088.

The per-PR receipts sit beside this note:

- [2026-10-30-tin-7735-spr220-private-terms.md](2026-10-30-tin-7735-spr220-private-terms.md) for #74
- [2026-10-30-tin-7788-nv-accept.md](2026-10-30-tin-7788-nv-accept.md) for #76
- [2026-10-30-tin-7788-neutral-avatar-visible-text.md](2026-10-30-tin-7788-neutral-avatar-visible-text.md) for #77
- [2026-10-30-tin-7788-accept-visible-text-lows.md](2026-10-30-tin-7788-accept-visible-text-lows.md) for #78

## Rulings that bind this repository

| Id | Linear anchor | What it means here |
| --- | --- | --- |
| SPR-239 | TIN-7125 dc152f20 | #74 may keep its internal ids: the guard step code, ruling references and the ruleset id |
| SPR-240 | TIN-7125 dc152f20 | Public commits keep the plain host label in the hook-written receipt trailer. No salt is needed |
| SPR-254, SPR-255 | TIN-7788 1d2d80e1, 60924f68 | The demo delivery DAG is its own lane. Its bar is a render and delivery with no seat and no operator dev work in the loop |
| SPR-256 | TIN-7788 2b1e530b, clarified in 3e02e9be | The content scope of a demo |
| SPR-258 | TIN-7788 bce70191 | A link plus a Softproxy Ask counts as delivery. One GO closes listening and lip sync for a render version, which #76 records |
| SPR-263 | TIN-7788 301d657b | Demo elements include rendered boards, simulation animations and product renders |
| SPR-295 | TIN-7125 300adc2e | The live face on calls comes first. Demo videos keep kitpip until it is done |
| SPR-296 | TIN-7125 300adc2e | Client services lead revenue work. Hardware demos through the demo DAG come second |

## Other rulings the seat recorded

These ids are listed by anchor only. Their content concerns other repositories.

| Ids | Linear anchor |
| --- | --- |
| SPR-215 to SPR-223 | decisions from the autonomy audit, document fefbd8cf033c on TIN-7125 |
| SPR-231 | TIN-7125 ba81eb1d |
| SPR-232 to SPR-234 | TIN-7699 |
| SPR-235 to SPR-238, SPR-253 | TIN-7580, SPR-253 in 4e980d3b |
| SPR-241, SPR-257 | TIN-7125 dc152f20 and 6ecfdcf3 |
| SPR-242 to SPR-245 | TIN-7252 |
| SPR-246 to SPR-248, SPR-264 to SPR-267, SPR-285, SPR-287 | TIN-7418, SPR-285 in 27f5a4b7 |
| SPR-249 to SPR-252, SPR-271, SPR-272 | TIN-7579, SPR-249 to SPR-252 in 9eab5fde |
| SPR-259 to SPR-261 | TIN-7788 bce70191 |
| SPR-262, SPR-276 to SPR-279 | TIN-7806 |
| SPR-268 to SPR-270 | TIN-7125 457152f3 |
| SPR-288, R-DAG-20261030-a | TIN-7788 ac4bd797 and 60fca3e8 |
| SPR-289 to SPR-294, SPR-297 to SPR-300 | TIN-7125 300adc2e. SPR-300 is tracked as TIN-7821 |

The Softproxy register holds SPR-280 to SPR-284 and SPR-286. The next narrate id is SPR-301.

## Open

| Item | Owner | State |
| --- | --- | --- |
| #78 lows: reword one spec sentence, and an optional CSS `src()` check | narrate | queued in TIN-7788 edfa1a3a |
| WER: whether a split name counts as an error | narrate | open after #75 |
| Re-score the demo tracking takes with the #75 normaliser, then re-render | narrate | queued |
| Live call face before the VRM demo avatar (SPR-295) | narrate, Softproxy seat | kitpip stays the demo avatar |
| Demo DAG render-check PR | narrate | no PR found on 10-30, per document 6fb6f03dd829 |
| Demo footage and acts J4 and J6 (SPR-261) | operator | waiting |
| `program/linear.json` narrate block | root | last updated 10-23. Its evidence state predates any narrate code, and it does not list TIN-7476, TIN-7580, TIN-7735 or TIN-7788. The seat opened no issue in the video-utils project this session |
