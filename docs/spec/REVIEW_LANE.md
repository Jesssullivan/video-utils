# Local listening review

Authority: operator-authorized parallel review lane, October 5, 2026;
R-HOOK-CONVERGENCE-20261004, TIN-3692 comment
`98cf680c-7299-4949-bfb2-60079053ad43`. This lane owns the local review server,
its new browser assets and focused tests. Existing report files stay with root
integration until the first push.

## Intended experience

Open one local review screen beside the run. Play the processed video or compare
the original and cleaned auditions. Filter proposed markers by kind and confidence,
select a region and jump to its source timestamp. Capture the current position as
a span start/end, add a listening note, and save an observation or dismiss a
candidate. Saving does not accept the master or confirm a performance mistake.

The screen distinguishes operator annotations from automatic proposals. Automatic
phrase, recurrence, bar and rhythm candidates are reviewable without a prior
score; intended-note correctness and definite performance grading still need the
appropriate references. Meter, downbeat, tonic and mode may remain unknown.
No action claims Final Cut Pro or DaVinci Resolve import.

## Implementation contract

- Run `python3 scripts/review_server.py serve RUN_DIR --port 8765`; bind only
  `127.0.0.1`. No daemon, remote assets, uploads, model downloads or browser autoplay.
- Serve a dedicated static review UI, a curated JSON session description and only
  verified run-local media/marker artifacts. Reject traversal, external paths,
  symlinks escaping the run, unexpected hosts/origins and oversized requests.
- Reuse existing report provenance checks to discover the video and hash-bound
  graph/markers. Convert original source seconds to decoded-audio/video playback
  coordinates explicitly. Preserve media; byte-range requests support seeking.
- Persist annotations atomically in ignored `RUN_DIR/review-annotations.json`.
  Bind the store to the original source SHA-256 and each note to the session's
  manifest/candidate receipt hashes. Record UTC creation/update times and stable
  annotation IDs. Reload saved notes after browser refresh; reject a mismatched
  store instead of reassigning old notes to another recording.
- Add/update notes through a bounded local JSON API protected by a session token;
  validate finite ordered source spans, allowed review states and bounded text.
  Concurrent writes use a lock and optional revision checks to prevent silent
  lost updates. User data enters the UI through text nodes.
- Stateless tools use `annotations RUN_DIR` for JSON reads and
  `annotate RUN_DIR --input REQUEST.json` for one JSON write. A request contains
  `expected_revision` and an `annotation` object with source start/end seconds,
  category, review state, nonempty note (up to 4,000 characters), optional existing
  annotation UUID and optional current candidate ID. Enforce 200 annotations and
  a 1,000,000-byte store limit. Cross-process writes use a nonblocking file lock;
  changed manifest/candidate receipts and stale revisions require a fresh review.

## Acceptance and checkpoints

First checkpoint: durable UX/contract above and a working local page with media,
marker filters and source-time navigation. Second checkpoint: saved annotations,
privacy/HTTP range tests and a bounded isolated-browser preview if available.

Tests exercise source/marker lineage, path/symlink rejection, byte ranges, origin
and token checks, annotation persistence and stale revisions, invalid/oversized
requests, and escaping. Synthetic server tests and graphical UI verification are
separate from actual take listening acceptance. Root integrates the recipe/tool
entrypoint and performs the final run review and publishing.

## Implemented checkpoint

The loopback worker, stateless annotation commands and separate browser UI are
implemented. Twelve focused tests pass for provenance, locking/revisions, HTTP
ranges, path boundaries, malformed requests and manual-text preservation.

An isolated Chrome/CDP check used the actual
`20261005T203619Z-f94eb8eb2a1a` run, original source SHA-256
`a522115f4e72e19384fb341bc84369728eceefe49183b8c6367a1008a95176c6`.
It loaded 177 candidates, filtered to 9, selected source span 1.348–2.697 seconds,
and decoded the exported video plus all three WAV auditions without media errors.
Muted video playback advanced 0.649 seconds with 45 decoded frames. Desktop and
390-pixel mobile layouts had no horizontal overflow or JavaScript exceptions.
The screenshot was visually inspected. These are decoding/navigation checks;
they do not establish listening quality or human review acceptance.

Repeat the bounded graphical check with
`python3 review/browser_smoke.py RUN_DIR OUTPUT_DIR` using Node 22+ and the local
Chrome binary. It creates an owned isolated profile, binds an ephemeral loopback
server and writes `browser-evidence.json`, `review-preview.png` and a cleanup
receipt. The profile/browser are closed after checking the actual process's
unique profile argument; no user browser is signalled. Startup is bounded to 45
seconds by default, because a 10-second first attempt did not expose CDP here.
The actual checked server was stopped; no background service remains running.

Process receipt: `review-lane | owned Chrome 93072, unique temporary profile and
live command checked | bounded graphical verification | R-N11,
R-HOOK-CONVERGENCE-20261004 | newly spawned owned process | closed with exit 0`.
Detailed local receipts are in ignored `artifacts/review-preview/`; the counts and
acceptance boundary above are the durable record.

A separate synthetic-audio browser fixture verified form submission, editing and
refreshing a saved note through the real local JSON API. The store advanced twice,
preserved the updated note and retained `listening_acceptance: not_established`.
Both audio players decoded and the mobile layout remained within 390 pixels.
The actual take's annotation store was not changed by this check. Reproduce this
optional mutation only with `--annotation-smoke` on a source named `synthetic-*`;
the checker rejects that option for an actual take. Its receipts are in ignored
`artifacts/review-fixture-preview/`.
