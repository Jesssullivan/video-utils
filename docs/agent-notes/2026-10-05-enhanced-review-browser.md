# Enhanced actual-take browser verification

Owner: `/root/plan_review`. Authority: operator-authorized active parallel goal,
repository AGENTS.md, R-HOOK-CONVERGENCE-20261004 and R-N11/R-N13. This lane owns
this receipt and ignored `artifacts/enhanced-review-browser/` only. The target is
the explicit enhanced run `artifacts/runs/20261005T232741Z-2b5dc43fd009`.

Definition of done: verify hash-bound baseline/clean/residue/video metadata,
source-bound candidate filtering and source-time seeking, muted actual playback
with advancing clock/decoded video frames, desktop/mobile screenshots and
processing/residue/selection-scope report captions. Do not write annotations,
alter target run files, claim listening acceptance, upload media, change global
configuration or signal any unowned browser/session. Root's separate marked-video
render is independent of this read-only check.

Use an owned loopback server and isolated Chrome profile with at most two renderer
processes. Record the spawned PID/command/profile, inspect the actual live target
before any termination, close only owned processes and leave a cleanup receipt
with actor, target/ownership, reason, ruling, prior state and result. Record
pre/post target artifact hashes and annotation revision/count as separate
preservation checks. Browser metadata/decode/navigation is distinct from musical
accuracy, acoustic synchronization and human listening acceptance.

## Actual read-only results

The explicit report revision checked is
`bcb514de612c880d46eb002015c95ab20ea46ebb2aa0c7a2991ec30d20b0dc9b`.
Primary evidence is retained privately under ignored
`artifacts/enhanced-review-browser/`: `browser-evidence.json`, five screenshots,
the bounded CDP harness, Chrome log/profile and `cleanup-receipt.json`.

All four verified baseline/clean/residue/video players loaded media metadata.
The video duration was 150.960998 seconds and each audio audition was
150.961111 seconds. The source-bound candidate session contained 180 proposals;
filtering to automatic recurrence candidates produced eight, and selecting one
sought all four players to source time 1.348 seconds (end 2.697 seconds).
Muted playback advanced 0.747901 seconds and decoded frames from 36 to 55, with
no player error or runtime exception. This proves browser decoding and
navigation, not acoustic synchronization or human listening acceptance.

DOM checks and the provenance screenshot confirm the `captured8-clarity`
processing chain, root-selected capture interval 4.10–4.95 seconds, 300/2200 Hz EQ,
RMS compression, pure source-minus-denoised residue with later processing
excluded, and analysis of pure `denoised.wav` rather than `processed.wav` or
final delivery. The capture is not proven noise-only. The legacy pitch selection visibly declares derived manifest
and settings bindings, reported producer identity rather than current-code
reverification, and sparse coverage of 13.25% / 20 seconds. Its unknown musical
interpretations and pending listening status remain explicit.

The review interface fits desktop and the requested 390 px mobile viewport.
The static report has a mobile defect: requested/screen/client width is 390 px,
but its painted content expands scroll/layout/visual viewport width to 522 px.
Checking scroll width against `innerWidth` alone falsely reports no overflow.
All element boxes remained within 390 px. Text-range diagnostics isolated long
selection/timing captions painting to 481.15625 px and the legacy binding
caption to 423.75 px, with normal wrapping rules. A reversible browser-only
`.caption,.note,footer{overflow-wrap:anywhere}` preview restored client, inner,
screen, visual-viewport and document width to 390 px. The owner received the
exact diagnostics. `viewport-text/report-mobile-wrap-preview.png` visibly fits
the screen, but this preview is not a change to the target report; readiness of
the eventual integrated report still needs its exact new revision checked.

The follow-up also explicitly loaded all four static-report players, with the
same measured durations, readyState four and no media error. Browser teardown
produced benign server broken-pipe diagnostics when Chrome cancelled ongoing
media transfer; successful metadata and browser error checks are retained.

## Owned-process and preservation receipt

Actor `/root/plan_review` started Chrome PID 73245 with its exact isolated
profile `artifacts/enhanced-review-browser/chrome-profile` and loopback server
`127.0.0.1:55528` owned by harness PID 73225. Live command/profile identity was
checked at startup and immediately before termination under R-N11. Only that
owned PID was signalled; it exited zero and the owned server thread closed.
Independent subsequent process inspection found no live matching targets.

All 40 existing target run-file hashes were identical before/after, with no
added or removed run files. Annotation revision zero/count zero stayed
unchanged. Follow-up mobile diagnostic runs use separate owned profiles and
retain their own cleanup receipts under `viewport-check/` and
`viewport-descendants/` and `viewport-text/`, with the same preservation results.
An independent socket check found each owned listener closed; process inspection
found no matching live Chrome or harness process. No annotation
write, listening acceptance, upload, global configuration change or unowned
process signal occurred.

## Source-rendered mobile fix preview

The report owner applied inherited `main{overflow-wrap:anywhere}` and produced
an isolated preview at `artifacts/report-mobile-fix/report.html`, SHA-256
`a47ae9cf342e4bf2c81a7f64dcd6c662984d09a81106399166109b190bcd3cc2`.
The `integrated-preview/` browser check used that exact rendered file and the
same verified media mappings, without injected CSS. With every details section
open, requested, screen, client, inner, visual-viewport and document width were
all 390 px; no element or text-range overflow remained. Desktop captions and all
four player metadata also passed; muted playback advanced 0.805352 seconds and
decoded frames from 38 to 57. Actual run-file hashes and annotation store stayed
unchanged. Owned Chrome PID 82370 and the owned server were closed after live
profile verification.

Status: exact enhanced report desktop/media/navigation/provenance checks passed;
mobile repair passed against the separate source-rendered preview. Root owns
the canonical report rewrite/publication; final mobile proof will bind that
exact resulting report revision when available.

## Separate marked-preview browser decode

A fixed route in the owned harness additionally served only the independently
hash-verified `marked-preview/marked-video.mov`, SHA-256
`13b9d18b80be37de954530f3c1220c256a061136921ffaf3c68f7e677b55dc90`.
Muted browser playback after a 1.5-second seek advanced 0.86013 seconds and
decoded frames from 40 to 61 with no media error. The private screenshot shows
the actual uncertain callout for source span 1.35–2.70 seconds. Evidence is in
`artifacts/enhanced-review-browser/marked-proof/`; the canonical review server
was not changed. Chrome PID 86130 and its owned loopback server closed under
the same live-profile checks, with all run hashes/annotations unchanged.
This supplements the separate frame/packet/visual audit; it does not establish
musical correctness, physical acoustic sync or human listening acceptance.

## Final canonical revision readback

Root rebuilt the canonical `report.html` through the existing CLI, yielding
SHA-256 `a47ae9cf342e4bf2c81a7f64dcd6c662984d09a81106399166109b190bcd3cc2`,
identical to the independently checked preview. The earlier `bcb514de…` bytes
and revision receipt remain archived under
`report-revisions/before-mobile-wrap/`. Earlier marked-render receipts retain
their historical input identities; they are not relabelled as the new report.
Root's mutation receipt is `artifacts/root-report-mobile-revision.json`.

The final owned `canonical-dom/` check opened that exact canonical report.
Processing, residue, analysis-stage, derived binding and pending listening
captions passed again; all four player elements remained present and no
Documents path was exposed. The 1440 px desktop viewport had a normal vertical
scrollbar (client/document/visual width 1425 px), without horizontal overflow.
At 390 px mobile with every details section open, client, document, inner,
screen and visual viewport widths were all 390 px; no overflowing element or
text range remained. Screenshots were inspected and no runtime exception was
recorded. This final pass checks DOM/layout and revision identity; it does not
repeat or replace the existing actual decoding evidence for unchanged media.

The final proof preserved all 42 run-file hashes, including the archived report,
and annotation revision zero/count zero. Chrome PID 3842/profile
`canonical-dom/chrome-profile` was inspected live before owned termination and
exited zero. Its loopback server `127.0.0.1:62593`, owned by harness PID 3748,
closed; subsequent socket and process checks found no owned listener or live
matching process. Cleanup remains scoped under R-N11, with private JSON receipt
and screenshots retained in `artifacts/enhanced-review-browser/canonical-dom/`.

Final status: enhanced canonical report desktop/mobile, media decoding,
source-bound review navigation and provenance checks are complete. Human
listening acceptance, musical correctness and physical capture synchronization
remain unverified.
