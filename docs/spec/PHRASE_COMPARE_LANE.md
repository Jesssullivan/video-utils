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
Pair count accepts 1–60, band fraction `(0,0.5]`, minimum rate `0.25–1`, maximum
rate `1–4`. Rate means elapsed second-phrase time per elapsed first-phrase time.
Local steps admit only rates allowed by those bounds: tightening around 1 can
exclude the non-diagonal 0.5/2 steps and leave no valid path. Increasing the limits
does not add new steps. No-path is an explicit abstention, never a silent fallback.

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

The retained MFCC coefficients exclude MFCC0 (absolute energy). Coefficients are
jointly standardized and L2-normalized; chroma is independently normalized with
equal family weights. Comparative chroma/tone is weak evidence for highly
distorted/polyphonic 32 Hz guitar. Constant temporal texture abstains; mean
feature cost above 0.35 rejects timing/edit flags. These thresholds are fixed pilot
settings, not validated musician-error detectors. Path cost includes a 0.05
non-diagonal step penalty; every setting is recorded/hash-bound.

Attack-edit hypotheses require detector score ≥0.7, both boundary scores ≥0.6 and
at least three detected attacks in each motif. Scores remain heuristics. Explicit
legato, tapping or sweeping hints abstain from attack-edit flags even with high
scores. Unknown scores retain unmatched numerical detections without labeling
them omissions/additions. Absolute capture latency is not required for relative
comparison; detector/boundary bias remains unknown. Invalid/outside-target mapped
onsets also abstain from edit flags.

## Acceptance and integration boundary

Synthetic cases: identical motif; fixed relative shift; compressed/rushed motif;
an omitted attack under qualified synthetic detector evidence; repeated attacks;
legato/unknown confidence abstention; silence/constant features; feature mismatch;
source tampering; no valid constrained path; resource caps; nonzero source timing.

Run on the actual 150-second take after source publication and compare the
proposed regions against playback. No synthetic pass is real-recording accuracy.
Root owns later DAG, MCP registry, marker and report integration. This lane creates
only its new worker, tests and specification until root authorizes integration.

## October 5 implementation evidence

Synthetic worker and actual-CLI tests pass. The actual demo run
`20261005T203619Z-f94eb8eb2a1a` produced ten aligned recurrence comparisons using
4,159 sparse cells in approximately 0.109 seconds. It proposed five relative
alignment-shift and four relative rate-difference review flags. All ten motif-edit
comparisons abstained because detector/boundary confidence was unqualified;
none established missing notes, phrase mistakes or listening acceptance.

The comparison artifact is stored separately at
`experiments/phrase-compare/phrase-comparisons.json` under that ignored run.
This benchmark did not overwrite the main DAG, report, flags or markers.
Future source/runtime revisions must rerun comparison from their own hash-bound
artifacts; this timing snapshot is not a throughput guarantee.

The released marker exporter also now rejects changed upstream DAG inputs before
export, even when the flags hash itself still matches. It validates local artifact
paths/hashes and stable inputs. A changed-analysis regression and an escaped-path
regression verify that direct marker calls cannot bypass this provenance check.
