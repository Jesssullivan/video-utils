# Corpus metadata validation hook

Authority: operator-authorized parallel graph checkpoint,
R-HOOK-CONVERGENCE-20261004 and repository `AGENTS.md`. Root owns publication;
the hook lane owns this contract, tool registry, allowlisted dispatcher and hook
tests. Worker authority remains [CORPUS_LANE.md](CORPUS_LANE.md).

Definition of done, recorded before integration: expose the existing read-only
corpus metadata validator through one typed `corpus` MCP operation and a readable
`guitar-corpus` skill. Require an explicit manifest path; permit an explicit local
corpus root and bounded deadline. Keep manifest and referenced metadata inside
that root without hiding unsafe path components through normalization. Verify a
successful authored synthetic metadata fixture through real stdio, then reject
unsafe or stale metadata without changing files. Read all twenty skill prompts
back exactly. No audio decoding, source-media reads, labels inferred from missing
spans, model downloads, networking, installations or annotation writes.

Source origins, reviewer identities and musical labels remain declared
assertions. Hash and metadata consistency checks cannot establish musician ground
truth, real-take labeling, listening acceptance or performance correctness.

The implemented dispatcher uses the fixed argv command
`python scripts/corpus.py validate MANIFEST --root LOCAL_ROOT --summary`.
Public arguments are `manifest` (required string, 1–4096 characters), `local_root`
(optional string, 1–4096 characters, default repository root), and
`timeout_seconds` (optional integer 1–900, default 600). No operation, audio,
network, model, installation or annotation-write option is accepted. Arguments
are literal argv values; the caller cannot choose a worker or shell.

The manifest must be an existing regular file inside the explicit root. The
dispatcher checks original path components before canonicalization can hide a
symlink, rejects traversal and root escape, and supports ordinary platform aliases
for the explicitly chosen root. A root that is itself a symlink is rejected. The
worker independently opens referenced metadata using bounded nonblocking dirfd
traversal with no-follow semantics; it rejects referenced symlinks, unsafe paths,
nonregular files, changed bytes, stale hashes/revisions and mismatched spans.

The compact summary follows full corpus validation. It contains corpus identity,
revision/hash, source-second units, sparse coverage, reviewer/source/label counts,
separate source-origin and origin-label counts, bytes read and at most 100 source
rows. Each row retains source and metadata receipt identities, annotation
revision, declared origin, source bounds, label count, certainty counts and review
status counts. It includes no raw labels, notes, reviewer identity text or repeated
metadata paths. The direct CLI continues returning full validated metadata unless
`--summary` is explicitly supplied.
Compact JSON stdout is capped at 1,000,000 bytes including its newline; an
oversized summary is rejected rather than truncated. A worker-owned 2,560-label
fixture verified that full receipts can exceed 2 MiB while the fully validated
summary retains counts/hashes in under 5 KB.

Result boundaries remain explicit: `source_audio_read: false`,
`ground_truth_established: false`, `listening_acceptance: not_established` and
`unlabelled_intervals: unknown_not_negative`. Declared real-recording origins
cannot turn generated fixtures or supplied labels into verified musician truth.
Limits are 1 MB per metadata file, 16 MB aggregate, 100 sources and reviewers,
5,000 selected labels, 200 stored annotations per source, eight alternatives per
ambiguous label and twelve hours per source. No source audio is opened or rehashed.

Invalid public schema is a JSON-RPC invalid-params error before a worker starts.
Unavailable/unsafe local files and rejected metadata are MCP `isError` results,
with the worker's bounded rejection code retained in error text. Successful
execution and `metadata_validated` report consistency only; they never mark a
master, performance, reviewer identity or corpus authenticity as accepted.

Local integration passed 47 targeted tests in locked Python 3.14: 28 contracts,
11 dispatcher tests and 8 MCP conversations, with no skips. FFmpeg/FFprobe were
explicitly selected from pinned Nix FFmpeg 8.1.2 for the existing media hook
regressions. Corpus fixtures used fictional source identity and authored synthetic
review metadata only. Actual stdio validated their compact summary and preserved
all bytes, then rejected stale annotation revisions and unsafe referenced paths.
All twenty live skill prompts matched their repository bodies exactly. The skill
owner also independently validated all twenty skill bundles. No actual-take
annotations or labels were created. Root owns source publication, hosted CI and
any actual-recording/listening acceptance evidence.
