# L1 cache-only phrase-support localization source contract

Authority: root admitted source implementation under the frozen
`PHRASE_LOCALIZATION_LANE.md` plan revision
`230022f9a0d059036e8fadb62315b1abcd7108166df81b73ffb72a7828584273`; operator parallel
project goal; repository `AGENTS.md`; R-HOOK-CONVERGENCE-20261004/R-N13. The plan
owner's later source-checkpoint appendix preserves this historical admission.
Numerical execution, fresh-bank generation, product defaults and actual-take
analysis require their separate root admissions.

New source `scripts/phrase_localize.py` is frozen at SHA256
`a64ff3acc5f18931e9975e96d1c6e80a1d454272fbf9dd4925b8b835b8c509de`.
Own source tests `tests/test_phrase_localize.py` are
`a615dc76226a7bdc53de67d6ce82957db2c2b7fef0a631ebc48ed2f60a1659ab`.
Independent tests owned by `/root/phrase_dag`, `tests/test_phrase_localize_audit.py`,
are `a090f1bcfb8ff130205d6abb1da0573202f8de9f201559f0d963408ae2f41232`.
All **40 constructed-feature tests** passed in **8.743 seconds** with
`python3 -S -m unittest discover -s tests -p 'test_phrase_localize*.py' -q`:
18 owner tests and 22 independent tests. No site packages, NumPy, model, audio
decoder, new bank or real cache was needed. This is source evidence, not a
localization accuracy or recording-quality result.

## Closed CLI and input lineage

```sh
python3 scripts/phrase_localize.py \
  --cache CACHED_FEATURES.npz --cache-sha256 CACHE_SHA256 \
  --proposals BORDER_RECEIPT.json --proposals-sha256 PROPOSALS_SHA256 \
  --clock CLOCK.json --clock-sha256 CLOCK_SHA256 \
  --output artifacts/benchmarks/NEW_DIRECTORY --summary
```

All paths are nonsymlink local descendants of repository `artifacts/`; output
must be new. Source WAVs are not read. Input hashes are required and rechecked
before output sealing. The NPZ reader accepts exactly `features`, `times`,
`centroid`, `onsets`: C-order NPY1/2 little-endian float32/64 numeric arrays,
features-by-frame layout, at most 26 dimensions and 512 frames. No object/pickle,
Fortran, unsafe ZIP member, duplicate/unknown member or nonfinite value is allowed.
Archive size is at most 10 MiB; expanded payloads total at most 1 MiB. JSONs are
at most 5 MB, finite, duplicate-key-free and at most 128 nested levels. The pinned
stdlib parser dependency `scripts/pitch_evaluate.py` remains SHA256
`a91ce8e9386cc7c63c5a5d53b8233f2c46a1f42fdd06ab1ae0eea3dc83405805`; its bytes are
checked before import and before sealing alongside the localizer's own bytes.

The proposal receipt supplies original `source_sha256`, `cache_sha256`,
`duration_seconds`, `proposal_universe` (at most 60), and `arms.Border` (at most
10). Retained rows have unique `original_candidate_index` values referring to
the original universe and exact original `first_start_seconds`,
`first_end_seconds`, `second_start_seconds`, `second_end_seconds`. Ordered
nonoverlapping windows must be inside the recording. No raw endpoint, evidence,
ID, order, ranking or competitor/order eligibility is changed or recomputed.
Unsupported confirmed grading or acceptance assertions in supplied metadata
reject. No truth, expected-score, tuning, BPM or audio input argument exists.

The separately hash-bound clock metadata has this schema:

```json
{
  "schema_version": 1,
  "source_sha256": "<original supplied source identity>",
  "cache_sha256": "<exact NPZ identity>",
  "audio_start_seconds": 7.25,
  "duration_seconds": 8.0,
  "native_pcm": {"sample_rate": 48000, "channels": 1, "sample_count": 384000},
  "analysis_pcm": {"sample_rate": 16000, "sample_count": 128000},
  "feature_clock": {
    "hop_samples": 256,
    "fft_samples": 4096,
    "centered": true,
    "timestamp_convention": "frame_centers_audio_relative",
    "frame_indices": [0, 1, 2]
  }
}
```

The abbreviated index list illustrates metadata structure; actual length must
equal the cached frame count. Duration is bounded to 8.192 seconds; sample counts
must agree exactly between native 48 kHz and analysis 16 kHz. Explicit indices
may contain gaps, but cached centers must equal index × 16 ms (plus one 128-ms
half-window only when the supplied cache is uncentered). Centered frames never
receive another half-window shift. This checks supplied coordinate metadata,
not waveform alignment, resampler latency or original-media identity afresh.

## Fixed algorithm and physical support

Fine cached dimensions use population standard deviation greater than `1e-5`
and z clipping at ±4. Candidate center-time ROIs are raw intervals expanded by
256 ms per side and clipped to the recording. Original Border selection stays
fixed. Cosine on a zero-norm vector is undefined and cannot match.

The rolling, tiled diagonal recurrence is exactly
`D[i,j] = max(0, D[i-1,j-1] + cosine[i,j] - 0.8)`: no horizontal/vertical warp,
tempo correction or omitted-bin compression. A missing 16-ms step on either
axis resets continuity. More than 128 ms consecutive nonpositive rewards resets
support; endpoints require positive rewards. Valid support uses at least 500 ms
on each clipped half-hop cell span and remains ordered/nonoverlapping. Different
maximum extents tied within `1e-12` abstain. The chosen path then requires two
internal adjacent-frame changes with dimension-normalized RMS z difference at
least 0.25, separated by at least 128 ms, outside the inclusive 128-ms guards at
each cell-span endpoint. A failed chosen-path guard does not select a lower
scoring alternative.

Logical ROI tiles are at most 256 × 256; only rolling DP rows are retained.
The run cell budget is 2,000,000; candidates beyond remaining budget retain raw
fallbacks and explicit partial coverage. Early empty-active-dimension abstention
reports zero visited DP cells. The stdlib implementation uses no numerical thread
pool; its maximum two-thread declaration is preserved. Feature extraction and
model inference are never invoked.

`phrase-localization.json` keeps each unchanged `raw_candidate`, candidate ID,
ROI, status/reason, null confidence and separate nullable `localized_support`.
Localized support records supplied first/last frame IDs, exact frame centers,
half-open center ± 8-ms cells clipped to the recording, source-axis cell and
center times, and center ± 128-ms FFT support/edge padding separately. Source
origin is added exactly once. ROI bounds select centers; half-hop cell edges and
FFT support are distinct uncertainty geometry. Positive/unsupported cell counts
and durations retain **separate physical clipped durations on both axes**:
64 matched cells beginning at recording zero cover 1.016 seconds on that axis,
while an interior partner covers 1.024 seconds. No endpoint probability is
invented. Clock, source-axis, settings, worker, dependency and input hashes are
recorded. `localization_computed:true` is distinct from false model-inference,
audio-extraction and audio-decoding flags.

## Boundaries and evidence still unknown

Tests include a motif with unlike context, stationary sustain, zero vectors,
different-extent ties, no path, legato without picked onsets, recording edges,
nonzero source origin, native/analysis extents, centered/uncentered clocks,
sparse time gaps, 128-ms gap behavior, 300 × 300 tiled ROIs, raw-ID order,
hash/source/claim guards and hostile archives/JSON. An independently exhaustive
small fixed-diagonal oracle confirms padded motif endpoints. A copied changing
nuisance pattern can pass the variability guard; that test records the limitation
rather than asserting guitar classification.

No old consumed419/523 cache was rerun and no new audio, bank, labels or model
job was generated. L1 cannot recover palm recurrences absent from the proposal
universe or promise whole-phrase localization when an existing ROI covers only
a subsection, including the admitted523 legato limitation. Legitimate stationary
guitar may abstain. Raw fallback is not successful localization. Future evaluation
must retain the full identical reference set, abstentions and raw-control scores.
No intended-note/performance grade, pitch/tonic/meter claim, restored stem,
physical latency calibration, video acceptance or product default is established.

Canonical feature extraction, recurrence search, pitch workers, frozen harness,
old numerical receipts, registry and defaults were not edited by this lane.
Root owns fresh numerical admission and any subsequent tool/skill registration.
