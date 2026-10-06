# Actual matched capture rendering: partial result

Root released one NR8 and one NR10 actual-take application in exact receipt
`2026-10-06-root-actual-nr8-nr10-render-release.json` (SHA256
`7d47ca235de555cb3f721c8b6f041e1517e71c5a1d2e87356affc9f47586c531`).
The source-bound profiles had matched capture, EQ, compression and loudness
controls; reduction strength alone differed. Source and capture music/click
uncertainty were retained. Both calls used the frozen standalone application
`00a03ef9…`, original source `a522115f…`, 600-second inner deadlines, 610-second
outer stage limits and two threads. Actor `/root/media_latency` owned controller
session 69864 under R-N11/R-N13; exact per-stage PID/session/argv start receipts
were saved before observing each process. Logs were file-backed and bounded to
4 MiB each; CLI error JSON was retained even on nonzero exit.

NR8 completed in 346.581 seconds and published only the fresh unreviewed candidate
`artifacts/runs/20261006T030345Z-af60acfd29dd`. Its manifest SHA256 is
`036c469d4907468b8087d215162163035f5a7ff08933be1bed7018022c35eb65` and
application receipt SHA256 is
`38a5e54d91ceb39048169b86ee54e2c29bc334b36399bf50aa08346534f74d59`.
It retained 6657385 native mono sample frames at 44100 Hz, source origin zero
and no time stretch. Export reports 3621 decoded frames, 3631 encoded picture
packets, preserved ordered payload hashes and zero PTS/DTS/duration deltas.
Decoded AAC measured −18.01 LUFS and −1.76 dBTP, passing the −1.75 dBTP target
on the first encode without added attenuation. Its video hash equals the
protected current NR8 render, consistent with the same settings; it is not
evidence of stronger cleaning than that existing render.

NR10 exited 2 after 422.896 seconds with `cleanup_failed`. FFmpeg leader 53178
had returned zero, but `/bin/ps -ax -o pid=,pgid=,stat=` exceeded the frozen
one-second inspection timeout during cleanup. The direct child was reaped;
same-session descendant absence was left unverified. No cross-session signalling
was guessed. The worker reports `candidate_publication: not_committed`, with
both committed and possible candidate selectors null. This is an infrastructure
verification failure, not a musical-quality rejection. Its immutable failure
receipt is
`artifacts/application-failures/20261006T031637Z-29f06c8dda9040888e70756b9d9987eb/receipt.json`
at SHA256 `72e88ebd934d20578ec0f56d8aa0f579330c11712d91f7549c985e500f077be7`.

Controller exit was 1. Full stage summaries, error JSON, ownership events and
protected hashes are retained under
`artifacts/experiments/actual-matched-capture-render-20261006T0303/` and bound
by the sibling dated result JSON. All released current/source/master/latest
identities, prior and newly authored profile bytes and pinned worker/context
identities were checked unchanged. There was no retry, bound relaxation,
worker modification, latest promotion, marker burn, listening acceptance or
master adoption.

Next: independent saved-artifact readback of NR8 and root-owned diagnosis of
the NR10 process inspection failure. Any retry requires a new explicit bounded
release; this controller's one-attempt authorization is exhausted.
