# Independent learned-pitch evaluator code audit

Actor: `clip_baseline/mir_sources`. Authority: root's explicit independent audit
assignment, repository `AGENTS.md`, R-HOOK-CONVERGENCE-20261004 / R-N12 / R-N13.
Owned files: this receipt and `tests/test_learned_pitch_audit.py`. No changes to
the evaluator, pitch worker, model environment, catalog, or runtime registration.

## Audited snapshot and evidence class

| Source | SHA256 at initial inspection |
| --- | --- |
| `scripts/learned_pitch_evaluate.py` | `210bca3b634ac744dc1619d6e9e44fee80f8c7ba53d8daacb9526cecc9dbe14c` |
| `tests/test_learned_pitch_evaluate.py` | `4d13b2256af507ef345cf4536844b0b42440e555d29c717db6263d08d7b683fb` |
| Published `scripts/pitch_evaluate.py` | `a91ce8e9386cc7c63c5a5d53b8233f2c46a1f42fdd06ab1ae0eea3dc83405805` |
| Project `scripts/basic_pitch_compare.py` | `407ff9fe99edbc863b3822c98683026841a3e03d2f6b7705a746bf7c68025cf3` |

This is source review plus constructed structural fixtures. The independently
run owner suite passed **14 tests in 48.117 seconds**. The fixtures contain
generated WAV bytes, handmade arrays and receipts; they do not execute Basic
Pitch. This lane performed no actual-bank numerical pilot, source-audio decode,
model download, ONNX Runtime import, model inference, or listening acceptance.
The source/structural result is not model-quality, actual-recording, or release
acceptance. Root retains admission authority.

## Findings

1. **Event activation receipt integrity needs a fix.** Event frame/pitch
   identities are independently reconstructed from immutable note/onset arrays,
   including local-onset split rules and corrected elapsed duration. However,
   `mean_note_activation` and `maximum_onset_activation` are initially only
   range-checked. A valid receipt with mean changed from 0.8 to 0.4, or maximum
   onset changed from 0.1 to 0.9, is accepted while arrays are unchanged. Neither
   mutation changes scored event identity, but it defeats integrity of the
   declared event confidence measurements. Recompute both over `[a,b)` at the
   event's pitch, with an explicit numerical tolerance.
2. **Malformed DEFLATE needs a structural failure conversion.** A ZIP with
   exactly eight required names and a rebound valid archive hash, whose first
   compressed byte is `0x07` (reserved BTYPE=3), raises `zlib.error`. Neither
   `read_npz` nor the CLI initially catches it, so the promised failed-structural
   output is not written. Convert this exception to the existing
   `invalid_npz_archive` evaluation failure.

Both findings were sent to owner `guitar_features` and root. The independent
five-test suite initially reproduced two confidence subcase failures and one
uncaught decompression error; its other three tests passed. The source owner
owns any fixes. Final retest status is recorded below when available.

## Consistent behavior observed

- Files are read through the published evaluator's benchmark-root, no-symlink,
  regular-file, extent and SHA checks. NPZ members are exact and unique; object
  dtypes, unexpected dimensions, nonfinite values and activation values outside
  `[0,1]` are rejected. ZIP/NPY byte bounds are checked before numeric unpacking;
  no pickle or executable dtype loading occurs.
- Fixed jobs, components and requested 8/8/6/8-second extents are bound to the
  pYIN source/truth hashes. Native WAV headers and bytes are verified, without
  decoding. Generator-only truth validation is inherited from the frozen
  evaluator; supplied generator labels do not become measured real notes.
- Nominal hop, upstream empirical model time and input-window projection are
  separately checked. Independent sample arithmetic gives row 142 model time
  `36352/22050` and projection `36164/22050`; row 172 model time
  `43844/22050 - 0.0018` and projection `43844/22050`. Seam times are not fitted
  to truth and do not establish physical latency.
- Every model input window has independently reconstructed prepend, stride,
  zero padding, crop and clipped source-context bounds. Native metrics first
  exclude any padded input window and then require the whole unpadded input
  inside one reference region. Pointwise and alternative-clock views retain
  separate labels and denominators.
- The native pitch axis retains all MIDI 21–108 note bins. Top-one selection
  uses the highest activation and lowest-MIDI tie break before consulting truth;
  whole thresholded sets retain extra harmonic candidates. Missing-F0 C1 truth
  is not replaced by its strongest octave. No tuning filter repairs outcomes.
- The exclusive end at `b=N` uses last projection row plus one nominal hop;
  event model spans remain unclipped while display/source ends are clipped.
  Frame-zero or excerpt-end event boundary flags are recomputed. Onset-only
  counts retain boundary events; offset scoring excludes boundary estimates
  and truncated references, retaining explicit excluded counts. Offset
  residuals become null when either end is unobserved; observed negative
  residuals stay signed.
- Event references come from `generated_score.events`, separate from condition
  boundaries. One-to-one matching maximizes cardinality before minimizing
  summed absolute onset residual. pYIN pairing is labeled timestamp diagnostics
  rather than an equal-receptive-field or picked-event score. Unsupported
  intended-note/performance claims cause hard-gate failure while metrics remain.

## Upstream applicability and remaining limits

The exact model-clock/window/decoder distinction is documented against pinned
Basic Pitch v0.4.0 [constants](https://github.com/spotify/basic-pitch/blob/9991303bba609a3b93089d13ec80d1d495083596/basic_pitch/constants.py),
[inference](https://github.com/spotify/basic-pitch/blob/9991303bba609a3b93089d13ec80d1d495083596/basic_pitch/inference.py),
and [upstream note creation](https://github.com/spotify/basic-pitch/blob/9991303bba609a3b93089d13ec80d1d495083596/basic_pitch/note_creation.py).
The project decoder does not implement upstream inferred-onset augmentation,
gap tolerance, neighboring-pitch suppression, Melodia or bend extraction.

C1's theoretical period is about 30.578 ms. A requested 25 ms event floor is a
decoder duration rule, not analysis resolution or proof of low-fundamental
tracking. Roughly two-second model input support can leave no eligible fast
ladder/sweep interiors. Synthetic missing-F0 periodicity, isolated glides and
fixed harmonic mixtures do not establish physical string interactions, real
legato/tapping/sweeps, picked attacks or performance correctness. The planned
30-second generated pilot remains separate from these unit fixtures.

## Independent tests and retest

`tests/test_learned_pitch_audit.py` owns five focused tests: a valid constant
activation receipt, raw event-confidence integrity (two mutations), reserved
DEFLATE failure conversion, independent seam sample oracles, and a signed
observed offset residual. Initial test file SHA256:
`7418a661b81723f2e20bde64a3266637e2fe62b0750907fa987ca5941ee3846c`.

Initial commands: `python3 -m unittest discover -s tests -p
test_learned_pitch_evaluate.py` (14 pass), and `python3 -m unittest discover -s
tests -p test_learned_pitch_audit.py` (5 tests; two confidence subcase failures,
one decompression error, remaining checks pass). Owned temporary fixture
directories are automatically removed.

The owner applied both fixes in candidate
`fda2ddca008d5aa4892dab0b80fd96197597ff2e175a0cf817ad5b98064b2d6b`.
The independent combined suite then ran 19 tests in 23.550 seconds: all new
tests passed, but one existing fabricated-pitch rejection test received
`event_activation_array_mismatch` before `event_decoder_array_mismatch`.
Requested preserving diagnostic order by checking activation summaries after
the independent event-identity reconstruction, without weakening rejection.
Latest independent test SHA256, after tightening seam oracles to `1e-12` s:
`fd74adbeff791e4a23369bdf27b70ef4834bd7bfcfcc0ea299b51bd6de60341b`.
The owner preserved identity-first diagnostics and independently reported 19
tests passing in 29.032 seconds. This audit lane then independently ran
`python3 -m unittest discover -s tests -p 'test_learned_pitch*.py'`: **19 tests
passed in 40.598 seconds**. Both original confidence mutations now raise
`event_activation_array_mismatch`; reserved DEFLATE is converted to
`invalid_npz_archive`. No test expectation was weakened.

Final evaluator SHA256:
`1fb883026b842857f72a70c8bf2fb757330b9ac705be36914f7a4c50cb8f7374`.
Final independent test SHA256:
`fd74adbeff791e4a23369bdf27b70ef4834bd7bfcfcc0ea299b51bd6de60341b`.
The published pYIN evaluator and Basic Pitch worker hashes remain the exact
initial values above. **No unresolved must-fix remains in this bounded source
and structural audit.** This conclusion permits root to consider source
admission; it does not establish actual bank/model performance, real-guitar
accuracy, listening acceptance, or release publication.
