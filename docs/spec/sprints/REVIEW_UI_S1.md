# S1 local practice review

Authority: operator-authorized six-lane five-hour S1 and repository AGENTS.md; R-HOOK-CONVERGENCE-20261004 / R-N11/R-N12/R-N13. UI lane edits only `review/*`, its named test and this specification/unique receipts. The annotations lane owns the source-bound v2 store and local server. Root alone integrates and publishes.

## Workflow

`just review RUN` remains the local operator entrypoint. Existing original/clean/residual/video players and v1 listening notes remain available. The separate practice issue form reads and writes `/api/annotations-v2`; it binds session source/manifest hashes and revision, uses the existing review token and a unique idempotency key, and records operator assertions with literal quote, context and expressed certainty. A point is the default (`extent_known:false`, equal endpoints); a checkbox opts into a known ordered span. All coordinates are original recording seconds, bounded by the session timeline.

The form exposes the eleven v2 kinds, expressed certainty uncertain/user-reports-certainty, and existing review states. Recording an observation never sets a musical verdict or listening acceptance. Editing retains supplied candidate/reference hashes and review state. Nonoperator assertions are readable with their original basis and have no edit action in this operator form. Detector hypothesis, operator intent, reference comparison and user report labels remain distinct.

The focused transport supports left/right seeking by one second (Shift: five), brackets to capture start/end and L to toggle a nonzero ordered loop. Native form/range keyboard actions remain native; typing never seeks. Switching listening sources retains source coordinates. Requested seek is clamped to available active-player coverage as well as the source timeline. Looping additionally refuses unknown player duration and spans outside that player’s origin/duration, and revalidates on player change, metadata arrival and live span edits. Seeking, selecting a proposal and arming looping do not start playback; the musician uses the selected player's controls. During playback, source-clock updates drive loop seeking. This browser loop is a practice convenience and makes no sample-accurate or gapless transport claim; a stopped/ended player remains stopped.

## Local graphical callouts

A compact adjacent-player display updates on seek/playback. Known spans are visible in `[start,end)`. Unknown-extent points retain their exact timestamp and use a0.75-second after-timestamp display dwell, labeled **point / display cue only**; this does not invent an annotation span. USER REPORTED reports use a distinct color and label from DETECTOR HYPOTHESIS proposals. Other v2 bases show INTENT or REFERENCE COMPARISON. At most four badges display at once with an explicit additional-entry count. Quotes are visually abbreviated after120characters; saved/downloaded text stays intact. This is a local review display; no media is burned or changed and no native editor import is claimed.

## Save and failure behavior

A successful response saves and rereads the same source-bound report; edits preserve its UUID. An uncertain transport/malformed success/server5xx preserves the exact request and idempotency key, freezes its draft and offers **Retry same report**. Replay reconciles without duplicating a committed report. A definitive stale-revision refusal refreshes the store, keeps the draft and requires an explicit save with a fresh key. Foreign source/manifest responses are refused in the UI. If v2 is unavailable, issue saving is disabled while the v1 listening form remains available; refresh can recover the v2 form. All notes render through text nodes, including literal markup.

## Verification

Behavior suite: `python3 -m unittest discover -s tests -p test_review_ui_s1.py -v`. It runs the shipped JavaScript under Node with isolated DOM/fetch doubles; this is behavioral evidence, separate from browser paint.

Reproducible real-browser fixture:

```bash
python3 review/make_practice_fixture_s1.py artifacts/qa-s1-fresh
python3 review/browser_smoke.py artifacts/qa-s1-fresh artifacts/qa-s1-browser --annotation-smoke
```

The fixture is a newly generated10-second44.1kHz mono low-register tone, with deliberately different format1/audio2source offsets. It carries its actual WAV hash and no real musician verdict. The browser uses an owned headless Chrome process, unique temporary profile, ephemeral loopback server and muted playback. CDP walks v1 save/edit, v2 point save/span edit/readback, loop and keyboard seeking, then1440px/390px viewport layout and screenshots. Browser decode/paint never establishes listening acceptance. Real-demo read-only UI checks use an isolated copy with no annotation smoke; accepted master, Desktop export and actual run stores remain untouched.

Numerical results, screenshot review and exact hashes are recorded in the lane receipts after integrated server qualification.
