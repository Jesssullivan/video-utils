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

- Run `python3 scripts/review_server.py RUN_DIR --port 8765`; bind only
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

## Acceptance and checkpoints

First checkpoint: durable UX/contract above and a working local page with media,
marker filters and source-time navigation. Second checkpoint: saved annotations,
privacy/HTTP range tests and a bounded isolated-browser preview if available.

Tests exercise source/marker lineage, path/symlink rejection, byte ranges, origin
and token checks, annotation persistence and stale revisions, invalid/oversized
requests, and escaping. Synthetic server tests and graphical UI verification are
separate from actual take listening acceptance. Root integrates the recipe/tool
entrypoint and performs the final run review and publishing.
