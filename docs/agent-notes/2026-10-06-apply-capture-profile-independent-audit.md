# Independent capture-profile application audit

Owner `/root/release_review`; authority root's explicitly authorized source and
fixture audit, operator parallel goal, R-HOOK-CONVERGENCE-20261004/R-N13.

Definition of done: inspect exact tool-25 producer receipts, current source/parent
and native clock/capture bindings, closed controls, path/overwrite guards, whole
deadline and owned-child cleanup, atomic fresh candidate publication, genuine
render/export outcomes and unreviewed status. Preserve old authoring/media/tool
contracts, actual media and latest pointers. Run fixtures only if useful; no
actual DSP, model, host action or future tool admission. Root owns release.

Initial frozen worker SHA:
`41e486cce9eafca885b54b5f840e47b94c72735e536fc296d789f0c3a0be2c94`.

Audit in progress. Initial material finding sent to owner and root: the local
remaining-time wrapper delegates to `media.run`/`subprocess.run`; it creates no
owned process group and therefore does not implement requested descendant
cleanup. A local application runner and inert process-tree regressions can fix
this without changing frozen media source.

## Source and provenance checks

Verified authored-unrendered status/evidence, pinned receipt/profile hashes,
the frozen tool-25 producer identity, current media validator identity, exact
original path and bytes, parent manifest/source PCM, native headers/extents,
review assertions, current instrument/capture contexts and settings digest.
Drafts, rejected capture and changed source/context/profile fail before media
launch. Capture-render authority remains supplied session assertions, not
identity authentication. No repeated operator permission is manufactured.

Profile controls use a closed authored schema and existing media validators.
Native sample mapping, no-time-stretch and explicit finite audio origin must
agree with the parent and receipt. Capture seconds must preserve exact native
indices. Application ceiling is 300 seconds, mono/stereo 8–192 kHz, source
3 GiB/native PCM 1 GiB, two FFmpeg/filter threads and at most 600 seconds.
Pure denoise/residue remain separate from optional processed tone/dynamics.

Existing media functions run in a private owned workspace; inputs are rehashed
before processing and before publication. Rendered files require matching native
headers and hashes, captured-processing provenance and calibrated compensated
bulk delay. Export must retain unreviewed status and matching paths/hashes;
video requires existing source/frame-count/relative-origin/latency/true-peak
verification flags while physical synchronization remains unverified. Candidate
selectors are rewritten before a fresh run is published; commands retain honest
historical staging paths. Original/profile/parent/master/latest remain distinct.
These are control-flow/metadata guarantees, not measured DSP acceptance.

## Independent fixture evidence

New owned test file `tests/test_apply_capture_profile_audit.py` adds five
independent refusal cases using constructed provenance, temporary WAV/header
fixtures and mocked existing clean/export functions. No FFmpeg, model, actual
take processing or host configuration is invoked:

- Every required video verification flag must be present.
- Changed encoded bytes after exporter receipt cannot publish.
- An invented physical-sync acceptance cannot publish.
- Unknown bulk delay or one uncompensated sample cannot export.
- A new decoder's 1 ms origin drift cannot relabel the parent clock.

`.venv/bin/python -m unittest discover -s tests -p test_apply_capture_profile_audit.py -v`
passed all five cases in 0.326 seconds against the initial frozen worker.
Existing owner fixture suite is separately reported as 25/25 passing; this audit
has not repeated it. No current 27-tool source or qualified numerical receipt
was changed. Only this dated note and the independent new test file are owned
here. Process-tree fix/readback remains pending before application readiness.

## Runner follow-up review

The owner implemented an application-local runner, preserving frozen media:
fresh `start_new_session` child, file-backed bounded logs, live PGID/session
inspection, SIGTERM/SIGKILL cleanup, bounded leader reaping and suspension of
only the application's own alarm during cleanup. The five independent refusal
fixtures still pass against this source (1.551 seconds).

Two remaining edge findings were sent to owner before readiness:

1. Process inspection may fail/timeout before cleanup signals or leader wait.
   Always kill/reap the worker's unreaped direct child in a fallback finally;
   report unverified descendant cleanup honestly. An inert inspection-failure
   regression is needed.
2. Successful application receipts retain process authority events, but failure
   currently discards staging and its only event copy. Return bounded events
   in error JSON or a separate ignored failure receipt, preserving actor,
   ownership, reason, ruling, prior state and result under R-N13. Do not publish
   a partial success candidate.

## Final frozen readback: ready for separately released native qualification

All material findings above are closed in frozen application source
`31eafcc8a76a36981945a1f680b21ab986f5a7464c9f8060559ce4b127198621`.
Independent source readback verifies the local owned-session runner, bounded
logs, live ownership checks, alarm-safe bounded cleanup, direct-child reaping
fallback and explicit unverified descendant status on inspection failure.
An outer `finally` waits for the direct child even when group signalling fails.
Successful and failed application paths retain bounded process authority
evidence. Failed processing publishes only a fresh ignored failure receipt,
discards private audio staging and exposes its path/hash plus bounded events in
error JSON; it does not publish a success candidate.

The sixth independently executed fixture combines actual inert-child creation
with injected inspection OSError and group-signal PermissionError. It confirms
the direct child is reaped, `cleanup_failed` and signal errors remain visible,
descendant absence stays unverified, and no media function runs. All six
independent tests pass in 0.854 seconds. The owner reports the final combined
`.venv/bin/python -m unittest discover -s tests -p 'test_apply_capture_profile*.py' -v`
passed **36/36 in 6.231 seconds**: 30 owner and six independent fixtures.
The owner cases additionally qualify timeout, exited leader with surviving
child, outer CLI alarm interruption, injected inspection failure, and durable
failure/error receipt readback. These use only constructed metadata and inert
owned processes, not actual FFmpeg DSP or the operator recording.

Frozen test SHA256:

- Owner: `1bd8f2c44f1ac3dbd9c47fd61df6770bfd093b4c819180b129865e076b1a19b3`.
- Independent: `6dd96ae81c553d2a72919b199053e55d2b7b647f60da3cc37c50064606755c22`.

Independently rehashed frozen tool-25 authoring source
`7d2820878826c87aabf2ab60b73c997b9d406b7f3ff8943d6012ed967444c355` and media source
`91443154251888c9e74670790766b289a2618f85f3be806d60ca26882faa9d94`; both remain
unchanged. Diff checks pass. Cleanup covers the created session/process group,
not arbitrary escaped sessions; its bounded post-interruption cleanup grace is
documented separately from stage execution budget.

**No remaining material source must-fix.** Root owns any generated native
audio/video execution release, actual-take processing, hook/skill admission and
publication. Tool 28 is not admitted by this audit. Structural fixture success
does not establish native FFmpeg runtime, actual low-register fidelity, captured
noise purity, musical correctness, listening acceptance or Logic/AU acceptance.
Current 27-tool contracts, accepted presets, operator media and latest pointers
were not changed by this lane. The note and independent fixture file are frozen
for root integration.
