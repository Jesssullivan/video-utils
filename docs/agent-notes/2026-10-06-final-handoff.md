# Guitar practice toolkit delivery and next actions

Authority: operator's ten-hour implementation goal and subsequent restoration,
arrangement, future-design and Desktop-export requests; repository AGENTS.md;
R-HOOK-CONVERGENCE-20261004 / R-N11 / R-N12 / R-N13.

## Delivery

The operator accepted FULLER audio and then the compact marked composition in
QuickTime. The second exact quote and requested Desktop export are recorded in
[final composite acceptance](2026-10-06-final-composite-listening-acceptance.json).

- Approved marked movie: `artifacts/experiments/accepted-fuller-compact-20261006T0441/accepted-marked-video.mov`.
  SHA256 `4538573ae6dd487874613efe3e30fe0e14ccda8e00a80b148ad2d4ce7f13e7e2`.
- Approved audio run: `artifacts/runs/20261006T041633Z-990aa1bd6737`.
  `cleaned.wav` is PCM24, mono, 44.1 kHz, 6,657,385 samples.
- Listening comparison: `artifacts/experiments/restoration-audition-20261006T0438/index.html`.
  Desktop and 390-pixel browser checks passed; its temporary browser/server closed.
- [Assembly proof](2026-10-06-accepted-fuller-compact-assembly-result.md):
  exact copied picture/AAC clocks and decoded audio, 3,621 VFR frames inherited
  from the checked compact parent, 41 protected inputs unchanged.
- [Restoration results](2026-10-06-nr8-nr10-and-fuller-results.md) retain NR8,
  stronger NR10 and FULLER comparisons, including normalization tradeoffs.

The optimized Desktop derivative is delivered at
`/Users/jess/Desktop/video_util_mvp_demo_1.mp4`: **21,596,491 bytes**, 85.99%
smaller than the accepted marked candidate, SHA256
`34247a4e2deec03f7d7e3bf4f8eef66f64bbe721d88013105a3cf88ed0734f10`.
It has 1080×720 H.264 picture and 96 kbps mono AAC at 44.1 kHz, measured
−18.06 LUFS/−1.81 dBTP. The reusable `just export-share` recipe produced the
final AAC96 derivative; [delivery proof](2026-10-06-share-export-actual-desktop.json)
retains exact picture/timing and audio extent checks. Three representative picture
stills passed root visual review; the new AAC96 compression has no separate
operator listening acceptance. Accepted full quality source, previous compressed
version and `latest` are preserved.

`just export-share INPUT OUTPUT` defaults to 720-pixel height without upscaling,
H.264 CRF27 and AAC96. Height, bitrate, codec, CRF and total deadline are explicit
arguments. HEVC is optional; two bounded local HEVC attempts timed out, while
H.264 completed in 94.6 seconds. These failures are retained rather than hidden.
Size depends on content; the recipe does not guarantee a globally smallest file.

## Source and verification

Final implementation source `9d18aadd8eb8781b510c5efd9c711abe1510e4cb` is signed
and published on private `Jesssullivan/video-utils/main`; remote identity,
GitHub signature and privacy were read back. [Hosted CI37418798796](https://github.com/Jesssullivan/video-utils/actions/runs/37418798796)
passed on that exact source: **902 discovered, 857 passed, 45 optional skips**
in 162.671 seconds; seven Rust tests and the secret scan passed. One skipped
class covers four sharing media fixtures requiring the exact macOS-qualified
FFmpeg binary. All four passed locally; the remaining 44 hosted skips are the
baseline optional-backend scope. See [publication proof](2026-10-06-tools30-publication.json).

The [local affected suite](2026-10-06-tools30-affected-regression.json) passed
**140/140**, no skips, in 92.016 seconds, with frozen worker/API/catalog/test hashes
unchanged. All 30 skill bundles and exact initialized MCP prompt texts passed.
Independent worker/hook/source review closed without a remaining reproduced issue.
The actual demo used the reusable recipe; its saved success also passed the typed
result classifier without a duplicate encode. The staged secret scan passed after
a source-code hash field was renamed to avoid a false generic-key match; no
credential or scanner allowlist was changed.

The prior published29 suite remains separately recorded: local 855 discovered,
854 passed/one optional skip, and hosted 855 discovered/811 passed/44 skips.
Its claims do not substitute for source30 qualification. Source/runtime proof,
actual media, numerical accuracy and operator listening have separate receipts.
The final catalog contains **30 typed tools and 30 skills**, including reversible
capture/restoration, analysis, source-bound arrangement review and sharing export.

## Musical evidence and limits

The supplied arrangement is 404 expected clicks: 24 sixteen-click phrases,
two eight-click breakdowns and a four-click rest. It is intent, not a detected
404-click performance. The [arrangement checker](2026-10-06-arrangement-reference-checker.md)
has independent/property tests, including 320 randomized cases; they validate
alignment and uncertainty behavior, not audio-extractor accuracy.

The final labels retain the NR10 denoised analysis branch and the same original
recording identity. FULLER supplies the accepted delivery audio; labels are not
misrepresented as analysis rerun on FULLER. Expected-arrangement spans, observed
candidate boundaries and operator concerns remain distinguishable. Some compact
callouts are suppressed by overlap; all marker metadata remains available.

The best working notation is quarter-note approximately 178, provisional 4/4,
using the operator's eight-click/two-bar description. The fitted faster pulse
is about 177.6/min. Beat unit, physical click rate and guitar subdivisions remain
separate, per [tempo clarification](2026-10-06-click-rate-and-beat-unit.md).

No classifier establishes confirmed wrong notes or missed/rushed beats here.
The fresh phrase experiment recovered zero of four full reference pairs and
zero of sixteen endpoints; reducing negative false candidates from five to two
does not qualify it for default adoption. Basic Pitch's generated C1 pilot had
34/426 fundamental matches and 392 octave errors. These failures are retained
and direct the next week's work. Fan/guitar spectral collisions and real isolated
32 Hz preservation remain uncertain despite measured mixture panels, generated
tests and accepted guitar tone. No recovered room-response or isolated stem claim.

## Next development work

The original [October 6–12 plan](../spec/PROJECT.md) retains seven five-hour core
packages and an optional 35-hour extension. Prioritize reviewed boundaries and
phrase precision, low-register denoising/articulation, calibrated sparse pitch,
portable per-take capture settings and safe agent iteration.

The requested [future studio package](../spec/future/README.md) is queued under
[TIN-5546](https://linear.app/tinyland/issue/TIN-5546/future-goal-private-guitar-practice-studio-mastering-and-explainable).
Eight new children TIN-5547–5554, four existing future-scope appendices, four future
milestones and dependency relations were independently read back. Proposed
allocation is 35 hours plus ONE optional 35-hour WEB or LOCAL branch. It does not
silently replace current commitments. Web uploads/jobs, Effect/Skeleton/SvelteKit
qualification, classification, score overlays and hosting retain explicit gates.

Current UI is local playback, comparison, seeking and source-bound annotations.
HTTP processing needs an artifact-ID boundary and bounded durable jobs before
binding typed tool controls to upload/iteration/download UX. Native AU is a
compiled gain-only development scaffold; Logic/auval/session automation and
native Final Cut/Resolve import are separate later acceptance milestones.
R/Quarto sources remain optional; plain HTML reporting is the proven fallback.

## Completion checkpoint

The [independent requirement audit](2026-10-06-completion-independent-audit.md)
found the original implementation/media/research/week-plan scope complete, with
root publication/tracker/handoff remaining at its earlier snapshot. Those release
requirements and the subsequent optimized Desktop/recipe request are now fulfilled.
D0 TIN-5485 and goal TIN-5495 are Done; [goal readback](2026-10-06-goal-completion-linear-readback.json)
records the latter at 05:34 UTC. Original planned end remains 06:49:34 UTC; it was
not reset or extended. All named subagents have completed their bounded work.
Root publishes this final documentation and then completes the active goal state.

The substantial next-week accuracy/product work above remains queued. No future
goal, service, plugin installation or unassigned implementation lane is activated.
