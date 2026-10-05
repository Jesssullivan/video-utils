# Within-take phrase comparison lane

## Intended result and research basis

Compare already discovered recurrence windows without requiring a score, intended
phrase, tonic or mode. Expose bounded feature alignment, relative time/rate changes
and observed attack-edit hypotheses. These compare take regions, not correctness;
no output establishes a missed note or a definite musician error.

Primary references reviewed October 5, 2026:

- [librosa 0.11 DTW interface](https://librosa.org/doc/0.11.0/generated/librosa.sequence.dtw.html)
  exposes custom steps, additive penalties, global band constraints and path
  backtracking. Its API supports feature matrices or a distance matrix; a whole
  recording distance matrix is unnecessary for this bounded recurrence task.
- [AudioLabs/FMP DTW variants](https://www.audiolabs-erlangen.de/resources/MIR/FMP/C3/C3S2_DTWvariants.html)
  demonstrates steps `(1,1),(2,1),(1,2)` to bound local path slopes and avoid long
  horizontal/vertical stalls. Such steps can omit feature frames; they do not
  establish deletion of musical notes.
- [AudioLabs/FMP music synchronization](https://www.audiolabs-erlangen.de/resources/MIR/FMP/C3/C3_MusicSynchronization.html)
  separates musical feature representation from temporal alignment. Chroma can
  help compare musical material but does not solve distorted nine-string
  transcription or prove identical intended riffs.

The engineering choice is a small standard-library implementation with those
explicit steps and sparse band storage, operating only on existing 50 ms
feature windows. This avoids another dependency and permits deterministic bounds
and synthetic acceptance checks. It is not a newly validated MIR model.

## Interface and implementation plan

CLI: `python3 scripts/phrase_compare.py RUN_DIR [--max-pairs 30]
[--band-fraction 0.20] [--min-rate 0.5] [--max-rate 2.0]`.
The worker atomically writes `phrase-comparisons.json`, never modifies audio or
existing DAG/marker artifacts, downloads no model, and uses no subprocesses.

- Read hash-consistent `manifest.json`, `analysis.json` and `phrases.json`.
  Verify any restored analysis source against actual manifest-bound media.
  Raw analysis stays preliminary. Different phrase/feature inputs are rejected.
- Consume `analysis.librosa.features`: feature-by-frame MFCC/chroma matrices and
  explicit audio-relative frame times. Select only discovered recurrence spans;
  cap 384 frames/window, 60 pairs, 100,000 band cells/pair and 2,000,000 cells/run.
- Jointly standardize comparative MFCC coefficients; use normalized chroma and
  feature costs. Apply an endpoint-connected normalized diagonal band with local
  steps `(1,1),(2,1),(1,2)` whose second-time/first-time rates satisfy the selected
  bounds. Record rate constraints, skipped-frame limitations and no-path status.
- Backtrack sparse predecessors; export path samples, feature mismatch, matched
  relative time offsets and local/global duration changes. Uniform feature
  texture and poor mismatch evidence abstain from strong alignment claims.
- Compare phrase-relative onset motifs through the feature time mapping using
  bounded one-to-one matching. Unknown/weak detector or boundary confidence, or
  a legato hint, abstains from attack-edit hypothesis flags; retain numerical
  detection differences as uncertain diagnostics. No onset stream blending.
- Record original/input hashes, artifact/settings hashes, comparison spans,
  nullable detector/boundary confidence and articulation context. Every proposed
  review marker retains `needs_review` and `performance_issue_confirmed:false`.

## Acceptance and integration boundary

Synthetic cases: identical motif; fixed relative shift; compressed/rushed motif;
an omitted attack under qualified synthetic detector evidence; repeated attacks;
legato/unknown confidence abstention; silence/constant features; feature mismatch;
source tampering; no valid constrained path; resource caps; nonzero source timing.

Run on the actual 150-second take after source publication and compare the
proposed regions against playback. No synthetic pass is real-recording accuracy.
Root owns later DAG, MCP registry, marker and report integration. This lane creates
only its new worker, tests and specification until root authorizes integration.
