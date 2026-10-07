# S2 operator rulings — October 7, 2026 (UTC)

Owner: `/root` Claude session `video-utils-d6`. Authority: operator interview answers in this session ("lets interview on these ratifications / board items"); R-HOOK-CONVERGENCE-20261004 R-N13. Each ruling below is the operator's explicit choice among offered options.

| Item | Ruling | Effect |
| --- | --- | --- |
| V6 privacy (xoruby) | Approved with an amendment: lab-host training allowed | Statement below sent to XORuby and recorded on TIN-5186 |
| V2 holdout bank licence | CC BY 4.0 | Generated synthetic bank only; XORuby keeps evaluation-only use (its own commitment) |
| EQ below 160 Hz | Allow a bounded shelf below 160 Hz | Capped, reversible low-shelf as an explicit profile option; default FULLER unchanged; never a cut or notch near the ~32 Hz fundamental |
| Quarto report (D6) | Approve flake.nix quarto/pandoc fix plus one more bounded render attempt | If it fails again, the plain HTML report is final for D6 |
| phrase_timing descriptor | Rebase the freeze and fix the wording | Descriptor says measured offsets, direction withheld without calibration; first-38 freeze rebased with recorded reason |
| Labelling session | Launch the UI now | Served from a cloned labelling context `artifacts/s2/labelling-20261007` (accepted run untouched) |
| Second take | New take family plus full pipeline | New take_family_id; FULLER with a reviewed fan interval, phrase anchoring, timing, marked compact export; family id reported to XORuby on TIN-5186 |
| report_bundle skill text | Update the wording and re-pin | Skill says admitted; pinned hash updated in the admission test |

## Approved V6 statement (as sent)

All outputs derived from real takes (audio, video, stills, spectrogram images, embeddings, per-window decisions, source-timed annotations) are private. They may live only in the private video-utils repository's ignored `artifacts/` tree on operator-controlled hosts, private Linear attachments, and operator-approved private scratch on lab hosts, and they may be used for private training on operator-controlled lab hosts. They must never appear in public receipts, public repositories, model cards or training corpora outside operator control, and trained weights derived from them stay private unless the operator decides otherwise. Generated synthetic fixtures not derived from a real take carry no such restriction.

The final sentence about trained weights is root's conservative reading of "allow lab-host training" (private training implies private resulting weights); the operator can widen it.

## Actions taken (2026-10-07 ~01:30–01:45Z)

- V6 and V2 rulings posted on TIN-5186 and delivered to the XORuby session (sting PID 264882, cwd xoruby-2026; msg `neo-86778-1791336755`, delivery queued). Receipt: actor root video-utils-d6 | target sting session 264882 by live PID+cwd | reason operator-directed relay of rulings | ruling R-N11 explicit authorization | prior_state tunnel epoch 1791336755 via LAN OpenSSH | result queued.
- Labelling UI started at the operator's request: `scripts/review_server.py serve artifacts/s2/labelling-20261007 --port 8765 --practice-s2 artifacts/s2/ui_core/real-take/bundle`, loopback only, foreground dev process owned by this session (not a daemon). `artifacts/s2/labelling-20261007` is an APFS clone of the accepted run (13 files, hashes identical), so annotations never modify the accepted run.
- Ruling lanes launched (workflow, Opus 5.5): eq_shelf, quarto_fix (one bounded render attempt), descriptor_rebase (incl. report_bundle skill re-pin).
