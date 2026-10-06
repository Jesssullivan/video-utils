# Independent pitch comparator acceptance plan

Authority: operator's full-force parallel development instruction, repository
AGENTS.md and R-HOOK-CONVERGENCE-20261004 / R-N12 / R-N13. Actor and named owner:
`guitar_features`. Scope: new acceptance specification and this durable planning
receipt only. Root owns integration and actual inference; `tonal_inference` owns
the isolated model runtime/adapter, with its nested `tonal_audit` auditing model,
dependency, graph, normalization, window/unwrap and source-clock evidence.

Delivered [PITCH_COMPARATOR_ACCEPTANCE_LANE.md](../spec/PITCH_COMPARATOR_ACCEPTANCE_LANE.md).
The plan reuses the four fixed generated pitch jobs totaling 30 seconds, preserves
the 24-window resource ceiling, and keeps actual-take comparison separate from
generated scoring. Cohorts cover C1/missing-F0, all nine custom-tuning pitches,
clean/tanh conditions, legato glides and sustain, 80 ms sweeps, three-note chords,
rests, nuisance mixtures, event boundaries and coverage gaps.

The published pYIN eligible scores remain 319/319 high-register and 745/745
low-register frames among 3,750 branch frames, with three silence false-voiced
frames and explicit exclusions. This plan does not promote those results into
all-frame, arbitrary-sweep or real-recording accuracy. It proposes separate native
context scores, paired-timestamp diagnostics and generated-score event metrics.
ML activations, event decoding and pYIN hypotheses retain independent meanings;
no truth-guided branch, octave, decoder or harmonic suppression is permitted.

Primary-source review inspected the pinned Basic Pitch inference, constants and
note-creation sources linked in the specification. Required evidence includes
raw activation and corrected event clocks, every model-window/overlap/padding
mapping, effective decoder floor, unshifted negative timing residuals, source and
model/dependency hashes. A nominal two-second model input is not a proven short
DSP receptive field; conservative full-input eligibility may be empty on rapid
notes. Explicit Ns/nulls and separate point/event diagnostics preserve that fact.

Independent metric-oracle proposals include octave-only chroma agreement,
abstentions in true-voiced denominators, silence false positives, extra harmonics,
one-to-one chord/event matching, merged/split hypotheses, short-note omissions,
legato without a picked attack, grid/seam/coverage differences and source offsets.
No new numerical result, learned runtime success, listening acceptance, model
license interpretation or confirmed musical mistake is asserted by this receipt.

Read-only source-integrity verification preserved:

| Published source | SHA256 |
| --- | --- |
| `scripts/pitch_evaluate.py` | `a91ce8e9386cc7c63c5a5d53b8233f2c46a1f42fdd06ab1ae0eea3dc83405805` |
| `tests/test_pitch_evaluate.py` | `28f07b14a3a0cecf427b56c9bbd77c1163e563d1bffe03fa507995a80471e999` |

The existing 17-test evaluator acceptance remains unchanged. The model owner
reports a qualified CPU ORT 1.30.0 graph with input `[1,43844,1]`, note/onset
`[1,172,88]` and contour `[1,172,264]`, explicit array clocks, and two array-reuse
127.7/25 ms decoder presets. These graph results are the owner's report, not
independent inference by this lane. Event decoding is project threshold-active
runs with local onset splits; upstream Melodia/postprocessing parity is not
claimed. The specification records this distinction. Concrete array/event
receipts and final schema were pending at the planning checkpoint; the concrete
readback below supersedes that pending status without duplicating heavy inference.

## Concrete immutable readback, October 6 UTC

Independently read the frozen runtime JSON, actual comparison and corrected
generated inference/NPZ receipts with NumPy numeric-array loading only. No ONNX
Runtime import, audio decode, model inference, model download or dependency
installation occurred. Verified 32 named finite numeric arrays per NPZ, expected
note/onset shapes, deterministic nominal/model/input-projection clocks at rows
0/142/172/final, event frame bounds and duration-floor gates, and null intended
note/string/performance fields. Full model/runtime package qualification remains
the separately linked nested auditor's evidence.

Actual comparison identity is
`ef86dbcaa1743d44ff24e2aa635deddaadce6a25653b35b537329e2a22b50e37`,
raw activation identity
`61c6bbbe235a5ae9386854cd9d855294b08b8abbdbb71b63961113483d6429ff`.
Its four five-second excerpts cover 20 seconds of the **earlier conservative**
211103 run, with 16 windows and 17/65 project events at 127.7/25 ms. Input
hash matches that run's pYIN snapshot; independently quantized excerpt endpoints
differ by at most 30.167 microseconds. It does not analyze the newer clarity
delivery or establish its pitch quality. Only 142/430 rows per excerpt derive
from wholly unpadded input windows; that is not monophonic truth eligibility.

Corrected generated inference identity is
`67cd53bcebc357c9469e208455e02fb1c6e9a719a4d66cde273d16ea8f85f8dc`,
raw identity
`fa35adc5d24b8081e5f523e03aa055d3d012c3e21094d4959949e05f68576590`.
The linear missing-F0 fixture's raw threshold-active top-one histogram independently
recomputes to C2=133, C3=29, C4=95, one abstention and **0/258 C1 membership**.
The prior nonlinear proxy is superseded. All four three-second generated excerpts
have zero rows from completely unpadded model windows; no conservative whole-input
context-qualified accuracy follows. Stepped-harmonic sweep/tapping names do not
qualify physical articulation. The specification retains these negative findings.

Updated the specification with concrete three-clock examples, project elapsed
duration gates and an unimplemented pure `learned_pitch_evaluate.py` interface.
Its future indices cross-bind fixed bank/component/source/model/runtime/adapter/
array hashes and the four 30-second jobs. Existing pYIN evaluator remains frozen.
Pending metrics include native/common-grid denominators, absence false alarms,
fundamental and extra-harmonic sets, event matching/residuals, chord voice counts,
glides, rapid sweeps and sustain/legato cohorts. The current 12-second model smoke
and admitted experimental hook do not establish those acceptance results.
