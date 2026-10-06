# Report mobile viewport repair

Authority: root-assigned report implementation and independent browser review;
operator-approved parallel work; repository `AGENTS.md`;
R-HOOK-CONVERGENCE-20261004 / R-N13. This lane owns `scripts/report.py`, report
tests if behavior changes warrant them, and this receipt. The previously
published stage-boundary receipt is frozen.

## Definition of done

Identify the actual overflowing content in the enhanced report, correct its
responsive layout, then verify both the requested CSS viewport and document
extent. A requested 390-pixel mobile viewport must retain `clientWidth`,
`innerWidth` and visual-viewport width of 390 without horizontal expansion.
Long processing-chain/provenance text must remain readable and escaped. Repeat
the browser check with feature details open, and verify desktop readability.
Do not hide overflow merely to produce a passing scroll-width comparison.

Preserve source/media/analysis, selected evidence and the published report
snapshot at `artifacts/runs/20261005T232741Z-2b5dc43fd009`. Source changes and an
isolated preview are permitted; root alone releases a regenerated actual report.
Browser checks do not establish acoustic or musical listening acceptance.

## Observed failure before edits

Independent actual-browser review requested a 390-pixel viewport. `screen.width`
and document client width were 390, while `innerWidth`, visual-viewport width
and document scroll width expanded to 522. Thus comparing only scroll width to
`innerWidth` produced a false pass. All queried element bounding rectangles
remained within 390 pixels, pointing to painted descendant/text overflow;
the reviewer is measuring text ranges to identify the exact content.

All forty run-file hashes and annotation revision/count remained unchanged
during those read-only checks. Browser ownership and cleanup receipts belong
to the independent reviewer. Implementation and final preview evidence will be
appended after the focused measurements.

## Exact cause and frozen source fix

The independent text-range diagnostic identified the caption token
`bulk_dsp_delay_compensated_detector_and_physical_sync_unverified`, painted to
right coordinate **481.15625 px** with range width **463.15625 px**. The legacy
manifest-binding caption painted to **423.75 px**. Both had normal wrapping;
their containing elements themselves fit within 390 pixels.

One inherited rule, `main { overflow-wrap: anywhere; }`, now allows long report
text to break when necessary. It covers provenance, processing captions,
filenames, footer text and descendant report content. No overflow is hidden or
clipped, no text/evidence is removed, and table layout is unchanged. The existing
HTML escaping and bounded caption rendering remain in place. This CSS-only
repair adds no implementation-mirroring unit test; the actual browser viewport
and text-range check is its layout regression test.

**23 existing report behavior tests passed in 0.205 seconds.**
`git diff --check` passed for the changed source. Frozen renderer SHA-256:
`3beb1b502dfd98c64e015e1f93d81e8c0f3ee81d912b9b3b9f3dc25426950b73`.

An isolated preview was rendered from the actual enhanced run's manifest,
analysis, graph, flags and selected receipts at
`artifacts/report-mobile-fix/report.html`; all five selected evidence slots
remained verified. Preview SHA-256:
`a47ae9cf342e4bf2c81a7f64dcd6c662984d09a81106399166109b190bcd3cc2`.
The original report SHA-256 remained
`bcb514de612c880d46eb002015c95ab20ea46ebb2aa0c7a2991ec30d20b0dc9b`;
before/after hashes of the report, manifest, analysis, DAG, flags and markers
matched. No actual run artifact was rewritten. A local preview render receipt is
saved beside the preview. Independent 390-pixel/detail-expanded and desktop
browser rechecks were requested; root owns release of a regenerated actual report.

## Independent source-rendered preview acceptance

The reviewer served the generated preview with **no injected CSS**. At the
requested 390-pixel mobile viewport with **all feature details open**, requested,
inner, document client, screen, visual-viewport and document scroll widths all
measured **390 px**. No oversized element or overflowing text range remained.
Desktop caption/provenance checks passed. All four report players loaded
metadata with ready state 4 and no media errors. The same proof run's separate
review UI muted playback advanced approximately 0.805 seconds and decoded 19
video frames. This is browser decode/navigation evidence, not acoustic listening
acceptance or a static-report playback claim.

Independent proof artifacts:
`artifacts/enhanced-review-browser/integrated-preview/`. The reviewer verified
all forty actual run-file hashes and annotation revision/count 0 remained
unchanged. Owned isolated Chrome PID 82370 and the proof server were closed;
the reviewer's cleanup receipt records ownership and R-N11 inspection.
The minimal source repair is ready for root integration and publication.
