# Independent L1 phrase-support source audit

Authority: operator's score-free guitar-analysis goal; repository AGENTS.md;
R-HOOK-CONVERGENCE-20261004/R-N13; root's named source-only L1 admission.
Actor: `/root/phrase_dag`. Owned files: independent test module, this receipt,
and the appended source-status paragraph in the localization plan. Worker and
owner tests belong to `/root/guitar_features`; root integrates and publishes.

State: **independent source checks passed; numerical and musical quality remain
unverified**. No new bank, generated waveform, decoded source, real-take/cache
analysis, model job, canonical change, default change or marker render occurred.
The only worker inputs were constructed feature arrays and temporary metadata/
NPZ fixtures created by these source tests. Temporary outputs were removed by
their owning test context. No process signals were sent.

## Exact evidence

- Frozen implementation `scripts/phrase_localize.py` SHA256:
  `a64ff3acc5f18931e9975e96d1c6e80a1d454272fbf9dd4925b8b835b8c509de`.
- Independent `tests/test_phrase_localize_audit.py` SHA256:
  `a090f1bcfb8ff130205d6abb1da0573202f8de9f201559f0d963408ae2f41232`.
- Owner `tests/test_phrase_localize.py` SHA256:
  `a615dc76226a7bdc53de67d6ce82957db2c2b7fef0a631ebc48ed2f60a1659ab`.
- Pinned imported strict JSON guard `scripts/pitch_evaluate.py` SHA256:
  `a91ce8e9386cc7c63c5a5d53b8233f2c46a1f42fdd06ab1ae0eea3dc83405805`.
- Historical admitted localization plan SHA256 before the source-status append:
  `230022f9a0d059036e8fadb62315b1abcd7108166df81b73ffb72a7828584273`.

Independent command on Python3.12.14:

```sh
python3 -S -m unittest discover -s tests -p test_phrase_localize_audit.py -v
```

Result: **22 tests passed**, 6.924s, exit0. `-S` disables site packages; the
module, its NPY/NPZ writer and the worker CLI subprocess use only the standard
library. This avoids qualifying the worker solely in a NumPy-equipped host.
The CLI fixture also uses `-S` and rejects a changed cache digest before creating
its proposed output. The owner separately runs its own18 tests and the combined
suite; those results are owned by its implementation receipt.

## Independent oracles and findings

An exhaustive small fixed-diagonal interval enumeration supplies the padded
motif's score and endpoints independently of the worker's rolling DP. Its unique
optimum begins at frame10 and ends at73 on each axis, with 64 positive cells and
reward12.8. First frame centers .160–1.168s yield cell edges .152–1.176s; the
second span is displaced3.2s. The .256s FFT support is separately .032–1.296s.
Source origin7.25s is added exactly once. These expected values live in tests,
not proposal or feature inputs.

Other fixtures verify centered/uncentered frame conventions, native48k versus
analysis16k sample extents, recording-edge clipping, supplied original frame
indices, missing-bin continuity breaks, nonunique maximum abstention and source
clock/hash failures. An eight-cell nonpositive run (.128s) remains supported;
a ninth cell breaks the path. Internal-change tests distinguish two separated
interior changes from one change, nearby changes or endpoint-only changes.
No-picked-onset feature variation can produce support; this is a cache-level
eligibility proof, not validation of actual legato recordings.

Raw candidate IDs/order/deep-copied rows, original universe counts, retained
counts, exact .256s ROI context and raw fallback remain visible. Stationary and
zero-norm inputs return complete localization uncertainty; raw fallback is not
counted as localized. The tests freeze the admitted thresholds and prohibit an
implicit warp arm. A300×300 fixture checks90,000 visited cells and logical tiles
no larger than256×256. Source inspection confirms rolling rows rather than a
whole-recording cross-matrix. Candidate61, retained11 and frame513 are rejected;
the total guard remains2,000,000 cells with an explicit partial state. This is a
bounded-source claim, not a real-recording runtime benchmark.

Hostile metadata checks reject extra NPZ members, >1MiB expansion, object and
Fortran NPY representations, nonfinite floats, malformed extents, duplicate/
deep/overflow JSON and symlink paths. The cache/source/clock digests and native
extents are checked; reading only supplied clock metadata does not verify the
waveform's physical latency or the original resampling process.

The initial audit found three claim/provenance defects which the worker owner
corrected before this freeze: a confirmed mistake assertion could be carried
inside a raw candidate; clipped edge cells had scalar frame-count durations;
and an imported parser was absent from the bound source proof. Current tests
reject confirmed assertions and verify physical durations by axis: a64-frame
span beginning at recording zero has first support1.016s, while its interior
copy has1.024s. The worker now binds the parser source, exposes separate cell
counts, and states localization computation separately from absent model and
audio-feature extraction jobs. None of these corrections retunes localization.
An additional pre-freeze telemetry correction records zero visited DP cells for
an empty active-dimension set, rather than the merely planned rectangle size;
both this full-unknown case and an empty retained set are independently tested.
Final source/independent-test hashes above bind that correction. The worker
owner reported its separate combined40-test `python3 -S` run passed8.743s;
the independently executed22-test result is the6.924s run reported here.

## Limits and next state

A deliberately copied, changing pseudo-noise sequence **passes** the acoustic
guard. That counterexample is retained as a passing limitation test: L1 is not
a guitar/phrase classifier. Stationary legitimate guitar can abstain, and equal
repeated submotifs can remain ambiguous. Confidence stays null and no musical
performance is graded.

The consumed419/523 error-analysis geometry is unchanged: missing palm proposals
cannot be recovered by L1, and the523 legato ROI ceiling is approximately.724871
mean pair IoU even under perfect trimming, below the strict.75 target. No feature
array source pass removes those limits. Finer scaling and localization remain
bundled; their contributions are not isolated by this arm.

Root must separately admit fresh617/719 metadata, generator proof and numerical
execution. All control/treatment predictions must seal before truth reads; full
identical references, unknown coverage, lost/gained/common-reference Ns and both
IoU.5/.75 remain required. No discovery score labels, BPM or intended arrangement
are introduced by these source tests. There is no default-adoption recommendation.
