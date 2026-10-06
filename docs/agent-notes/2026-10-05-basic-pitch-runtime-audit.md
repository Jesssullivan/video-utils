# Independent Basic Pitch runtime audit

Owner: `/root/tonal_inference/tonal_audit`. Authority: root's explicit
reattachment for independent review under the operator's ten-hour parallel goal;
R-HOOK-CONVERGENCE-20261004 / R-N13. This lane owns this receipt only. Model and
worker implementation remain owned by `/root/tonal_inference`; root owns
integration and publication.

## Verified checkpoints

- Official Basic Pitch 0.4.0 wheel: 758,279 bytes and SHA256
  `738adb503aae7fdfc7d1e1511aa0ce35052315f260a19531ef4c356708425db0`.
  Independently checked 43 unique safe archive members totaling 2,243,620 bytes.
- Extracted ONNX: 230,444 bytes and SHA256
  `2c3c1d144bfa61ad236e92e169c13535c880469a12a047d4e73451f2c059a0ec`.
  Its computed Git blob identity and wheel RECORD digest/size agree with the
  pinned source and archive. Exactly one model plus ten allowlisted text
  evidence members were extracted. LICENSE/NOTICE and durable receipt linkage
  passed independent checks. Bundled-weight license applicability remains a
  documented inference from repository terms.
- Isolated dependency manifest at
  `artifacts/model-runtime-env/onnx-1.30.0-cp314/wheel-manifest-before-install.json`
  has SHA256
  `c0e0a0f01023d5e701c13bcd092d23ef216dd3e96b2bc0320293c355252df23f`.
  All five local wheel archives match their recorded byte counts, SHA256,
  dist-info names, versions and dependency declarations: ONNX Runtime 1.30.0,
  NumPy 2.5.3, flatbuffers 25.12.19, packaging 26.3 and protobuf 7.36.2.
- Independently compared 1,349 installed wheel members with archive bytes.
  All matched. Only the five installer-rewritten RECORD files were excluded;
  there were no relocated `.data` members. `pyvenv.cfg` records the existing
  CPython 3.14.6 interpreter and disables system site-packages.
- Read the existing `runtime-smoke.json`: CPU provider, finite note/onset
  `[1,172,88]` and contour `[1,172,264]` for a zero waveform input
  `[1,43844,1]`; reported 0.171676 seconds and 65,159,168 peak RSS bytes.
  These are the implementation owner's execution measurements, reviewed here
  without repeating inference. They support graph execution, not musical
  accuracy, physical timing calibration or AU suitability.

## Worker review checkpoint

The first visible `scripts/basic_pitch_compare.py` correctly distinguishes an
official model with project threshold decoding from upstream decoder parity.
It retains sparse excerpts, named finite numeric activation arrays, native
source-time conversion, null intended-note/performance judgments, and the
published upstream window/cropping/clock formula. The frame clock's empirical
adjustment remains unqualified physical latency.

The following concrete findings were sent to the implementation owner. Final
source/specification readback closes all six:

1. Resolving the isolated venv launcher's symlink executes the base interpreter
   and bypasses the isolated installed dependencies. Preserve the lexical venv
   launcher for execution.
2. An arbitrary runtime override must not cite the fixed isolated dependency
   manifest without qualification. Bind the approved venv and check actual
   runtime/package identities against that manifest.
3. Capture worker/model identities before execution and recheck before
   publication; computing only the final worker hash can misidentify executed
   code after a concurrent edit. Recheck the qualified model too.
4. Validate the restored derivative's native rate/channels/sample extent against
   the manifest before asserting preserved source-time mapping.
5. Reconcile the implementation's 600-second limit with the planned 180-second
   worker ceiling, and enforce or explicitly revise the total event budget.
   The first implementation applies 5,000 events separately per excerpt.
6. Reap the owned child with an R-N11 receipt when resource monitoring itself
   fails; the initial monitor-exception path can leave its child running.

Independent lightweight verification passed 28 pure-worker checks: bounded
excerpt schedules across 1/5/20/30-second budgets and 0.5–300-second inputs,
monotonic model clock, short/default project duration floors, silence and a
mocked resource-monitor timeout. The timeout fixture launched one owned short
sleep child; the worker terminated/reaped it and saved its `monitor_error`
resource receipt. No model inference was repeated.

The final contract explicitly selects a 600-second overall deadline, sampled
1 GiB worker RSS ceiling supplemented by macOS process-peak measurement, and
5,000 events per preset across the complete run. The reviewed tests distinguish
project-duration floors from upstream strict-frame-count behavior, including
the empirical-clock discontinuity. The implementation owner reports 16 standard
tests plus one qualified-runtime integration test passing; this audit reviewed
their source and preserved outputs rather than repeating model inference.

## Final readback: PASS for bounded adapter and provenance

Reviewed worker SHA256:
`8bc17166c48ff6dccf33fd0eb17d3257535d6d91c83df0afed51b9c59dc75ee1`.
Reviewed final test source SHA256:
`c71400db31f0e5032897cf6a20836f297d4fa72863a188c395fa147c10be66e6`.
The [owner's durable runtime receipt](2026-10-05-basic-pitch-runtime.json)
matches its referenced dependency manifest, generated fixture receipts and
actual comparison artifacts.

Actual comparison:
`artifacts/runs/20261005T211103Z-c6d0bac2fcd2/learned-pitch/20261006T000817Z-3e321db594cc/comparison.json`,
SHA256 `ef86dbcaa1743d44ff24e2aa635deddaadce6a25653b35b537329e2a22b50e37`.
Independently verified current source/manifest/model-registry/tuning/runtime/
worker/activation hashes. The NPZ has 32 named finite numeric arrays, correct
430-by-88 note/onset and 430-by-264 contour shapes per excerpt, and 3,082,240 raw
numeric bytes. Four five-second excerpts cover 20 seconds with 16 model windows;
all event delivery spans stay inside their source excerpts. Totals are 17
project hypotheses at 127.7 ms and 65 at 25 ms. Owner execution measured
6.329 seconds and 170,917,888 peak RSS bytes. Intended notes, strings and
performance issues remain null; the recording remains ungraded.

The final generated checkpoint is
`artifacts/model-comparison/20261006-basic-pitch-generated-12s-final/`.
Its linked hashes and 32 finite numeric arrays independently passed readback.
The corrected linear missing-fundamental signal yields **0/258 C1 top-one truth
membership**, with C2/C3/C4 partials instead. The initial nonlinear fixture could
regenerate the omitted fundamental and is explicitly superseded. Sweep/tapping
labels describe phase-discontinuous stepped harmonic proxies; they establish
neither physical articulation accuracy nor whole-model-context-qualified
musical acceptance. The independent acceptance lane owns that remaining work.

No remaining implementation must-fix was found in this bounded audit. This
does not qualify upstream decoder parity, actual-note correctness, full-song
coverage, calibrated physical timing, AU render behavior or Logic acceptance.
Root owns just/MCP/skill admission and publication. No model inference was
repeated; no upstream-code import, dependency installation, network request,
registry edit or shared worker edit was performed during this runtime audit.
The only repository write is this authorized durable receipt.
