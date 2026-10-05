# Basic Pitch comparator qualification

Initial research-only checkpoint, October 5, 2026. Owner: `/root/tonal_inference`.
Authority: operator's ten-hour parallel goal; R-HOOK-CONVERGENCE-20261004 / R-N13.
This checkpoint inspected primary source text, Git refs/tree metadata and PyPI
metadata. It downloaded no checkpoint, wheel or source archive; installed
nothing; changed no model registry or host configuration; ran no inference.
The explicitly released **23:04 UTC archive acquisition** is recorded below;
it supersedes the initial unknown ONNX digest while leaving runtime unqualified.

## Decision and source pin

An **optional CPU ONNX comparator is technically plausible**, with a small
official model and a matching current Apple arm64 wheel. Ordinary installation
of Basic Pitch 0.4.0 into this repo's Python 3.14.6 environment is unsuitable:
its macOS dependency markers require an older TensorFlow package that has no
matching interpreter wheel. Prefer an explicitly audited ONNX adapter in an
isolated optional environment. This is a plan, not an available tool.

The selected official release is [Spotify Basic Pitch
v0.4.0](https://github.com/spotify/basic-pitch/releases/tag/v0.4.0), published
**2024-08-16T17:16:26Z**, at commit
**`9991303bba609a3b93089d13ec80d1d495083596`**. Git `ls-remote` verified this
lightweight tag. GitHub's authenticated release and recursive tree metadata
verified the date and artifact sizes; unauthenticated API access returned a
403 rate-limit diagnostic and the read-only authenticated alternative succeeded.
No model blob was requested.

Exact configuration/adapter text was read at that commit and hashed in memory
without saving source files. SHA256 identities:

| Pinned text path | SHA256 |
|---|---|
| `basic_pitch/constants.py` | `3374330dbf374cc4ba3d76eba6aad06e089a40252c4c68b3bf93510bd7b37214` |
| `basic_pitch/inference.py` | `b2dd343a318b85ee91c6d660eae2f48d7e39a8678d82575ab606c1c3617a6269` |
| `basic_pitch/note_creation.py` | `9c813509acf57ed9b902d2b9fcd9f8118b2c5ffe568a06df9cfa60f5c5ee2572` |
| `basic_pitch/models.py` | `31303f7198d9e0c4a3aa2141427c9855fa32add7f964adf0557abd242330375c` |
| `pyproject.toml` | `3d37cecfe0e9ba3fa6b03f1db491788fbceb5f4dfa324f13609270bbe91afc1b` |
| `LICENSE` | `929c910bae2152fa87199a5d0660e09263419b7eee6d4b301d05ee2aaf211c37` |
| `NOTICE` | `b810e55c0e3b520fabb45fc2ccc74880187bf84e309971968541cc812dcde905` |

These configuration/code/license identities do not supply a model-file digest
or establish parity of converted serializations.

The official [paper](https://arxiv.org/abs/2203.09893) describes a compact
instrument-agnostic polyphonic note/multipitch system. Polyphonic output means
overlapping pitch activations/note events, not recovered guitar strings, stems,
fingers, frets, intended notes or correct playing. The versioned model and
decoding code, rather than paper benchmark numbers, define this comparator.

## Exact artifacts and rights evidence

All paths below are relative to `basic_pitch/saved_models/icassp_2022/` at the
pinned commit. Git blob identities are **SHA-1 Git object IDs, not SHA256 file
digests**. At the initial research checkpoint, binary SHA256 values were unknown
because no model bytes had been retrieved. The later acquisition below supplies
the ONNX digest only; the other serializations remain unqualified. Root retains
ownership of any `program/models.json` admission.

| Serialization | Official pinned artifact | Size / identity | Decision |
|---|---|---|---|
| ONNX | `nmp.onnx` | 230,444 bytes; blob `c30e5f9438e798604b7177aa26be1fe64482f767` | Preferred small single-file candidate; graph/runtime compatibility untested. |
| TFLite | `nmp.tflite` | 204,448 bytes; blob `85a41befdd036e9b365a052b7c704c6810288b95` | No current `tflite-runtime` macOS wheel found; not selected. |
| CoreML | `nmp.mlpackage/` | 123,027-byte `model.mlmodel`, 145,956-byte `weight.bin`, 617-byte `Manifest.json`; package tree `0fd45f1cc8c5f5fff7a951ca1473944dee4a25aa` | Package, not one binary; no coremltools cp314 wheel found. |
| TensorFlow | `nmp/` | 1,084,140-byte `saved_model.pb`, 219,309-byte variables data, 4,794-byte variables index; tree `0e641eac8d201c60df436ca2897d0afcb257ea42` | Heavy legacy runtime incompatibility; not selected. |

The paths are browsable in the [pinned official model
directory](https://github.com/spotify/basic-pitch/tree/9991303bba609a3b93089d13ec80d1d495083596/basic_pitch/saved_models/icassp_2022).
The repository-wide [Apache-2.0
license](https://github.com/spotify/basic-pitch/blob/9991303bba609a3b93089d13ec80d1d495083596/LICENSE)
and [Spotify NOTICE](https://github.com/spotify/basic-pitch/blob/9991303bba609a3b93089d13ec80d1d495083596/NOTICE)
are established for the distributed project; its [package
manifest](https://github.com/spotify/basic-pitch/blob/9991303bba609a3b93089d13ec80d1d495083596/MANIFEST.in)
explicitly bundles these serializations. No separate model license or model
exclusion appeared in the inspected model tree. Treat applicability of the
repository-wide terms to these bundled artifacts as a documented inference,
not discovery of an independent weight license. Preserve the exact source,
LICENSE and NOTICE in qualification receipts; arbitrary mirrors or separately
trained checkpoints do not inherit that evidence.

[PyPI's official 0.4.0 metadata](https://pypi.org/pypi/basic-pitch/0.4.0/json)
provides a 758,279-byte universal wheel,
`basic_pitch-0.4.0-py2.py3-none-any.whl`, SHA256
`738adb503aae7fdfc7d1e1511aa0ce35052315f260a19531ef4c356708425db0`.
This is an archive digest, not the ONNX digest or proof of its extracted
contents. A later explicitly requested acquisition can verify this archive,
inspect its license notices, safely extract only allowlisted paths and compare
the model's Git object identity with the pinned source blob. Record the
resulting file SHA256 and exact byte count before registry admission. The
wheel was not downloaded or inspected in this initial checkpoint.

## Explicit archive qualification, 23:04 UTC

Root released exactly the official PyPI wheel acquisition and bounded inspection
under the operator's audio-ML task. The known 758,279-byte archive's SHA256
matched **before ZIP parsing**. Its 43 entries advertise 2,243,620 uncompressed
bytes, below the 200-entry / 100,000,000-byte limits; the download itself was
capped at 20,000,000 bytes. All entries were checked for duplicate/unsafe paths,
symlinks, unusual file types and encryption before any extraction. Only the
official ONNX and allowlisted configuration/license/metadata evidence were
extracted; bundled CoreML/TFLite/TensorFlow weights remained inside the verified
container and were not individually extracted or requested elsewhere.

The verified ONNX is **230,444 bytes**, SHA256
**`2c3c1d144bfa61ad236e92e169c13535c880469a12a047d4e73451f2c059a0ec`**.
Its computed Git blob identity matches
`c30e5f9438e798604b7177aa26be1fe64482f767` at the pinned Spotify commit. The
wheel's `RECORD` provides a matching internal file digest and size; that is
container consistency evidence, not a second external authority.

Actual license members are `basic_pitch-0.4.0.dist-info/LICENSE` and
`basic_pitch-0.4.0.dist-info/NOTICE`; their hashes match the pinned repository
texts. Wheel METADATA declares both `License-File` fields, with no populated
`License` field. There is **no separate model-local license member** in this
archive. This strengthens the repository-wide Apache-2.0/bundled-artifact
inference; it supplies neither an independent weight-license guarantee nor
evidence that use is prohibited. The extracted constants/inference/decoder/model
source hashes also match the previously pinned text bytes.

The durable [qualified-model manifest](../agent-notes/2026-10-05-basic-pitch-qualified-model.json)
contains archive/model/evidence identities, limits, current status and a proposed
registry entry. Its local full inventory is
`artifacts/model-qualification/20261005T230424Z-33788bf0000a/qualification.json`;
the model is the adjacent private `nmp.onnx`. This directory is ignored by Git.
No dependency was installed, no existing environment changed, no model was
registered, and no model inference or graph-runtime validation was performed.

An independent agent verified the archive/model hashes and sizes, pinned Git
blob, internal RECORD digest, all extracted evidence hashes, durable receipt
linkage and exactly one extracted model using local reads only. It reported
verification PASS with no must-fix; it performed no imports, inference,
installation, network request or edits. This review qualifies recorded bytes
and evidence consistency, not learned-model runtime or musical accuracy.

## Audio and pitch representation

The pinned [constants](https://github.com/spotify/basic-pitch/blob/9991303bba609a3b93089d13ec80d1d495083596/basic_pitch/constants.py)
define mono **22,050 Hz**, a **43,844-sample** input window (about 1.98839 s),
256-sample analysis hop, 88 note bins starting at **27.5 Hz / MIDI 21 (A0)**,
and three contour bins per semitone. The top note-bin center is **MIDI 108
(C8), about 4186.009 Hz**, computed from equal temperament. **C1 / MIDI 24 /
32.703 Hz is representable**; representability does not establish low-string
accuracy. Model architecture uses a CQT/harmonic representation; no external
chroma matrix is accepted as equivalent model input.

[Model source](https://github.com/spotify/basic-pitch/blob/9991303bba609a3b93089d13ec80d1d495083596/basic_pitch/models.py)
defines waveform input with batch/sample/channel axes and distinct note,
onset and contour heads. Inspect actual ONNX runtime tensor metadata after
qualified acquisition before accepting inferred shapes or graph operator
support. The selected model has never been loaded on this host in this lane.

The [inference source](https://github.com/spotify/basic-pitch/blob/9991303bba609a3b93089d13ec80d1d495083596/basic_pitch/inference.py)
resamples/downmixes, overlaps 30 output frames, adds half-overlap leading
padding and removes overlapping frame margins. ONNX expects named waveform
input `serving_default_input_2:0`; outputs map `StatefulPartitionedCall:1` to
note, `:2` to onset and `:0` to contour. Preserve these names explicitly;
avoid runtime-priority autodetection. `predict()` returns raw arrays, MIDI and
note events. Neural activation or note amplitude is not a calibrated
probability of a played/correct note.

## Decoder and source-clock concerns

The pinned [note decoder](https://github.com/spotify/basic-pitch/blob/9991303bba609a3b93089d13ec80d1d495083596/basic_pitch/note_creation.py)
can infer additional onsets from frame changes, apply minimum-duration and
frequency filters, and recover remaining activations with its Melodia-style
step. Its clock uses a window-index adjustment containing an explicit 1.8 ms
empirical offset; copying only `frame * 256 / 22050` would silently diverge.
Frequency upper-cutoff slicing is exclusive after rounding to a MIDI index:
avoid claiming an inclusive endpoint unless the adapter implements and tests
that explicitly. Contour bends and overlapping-note bend handling require
separate interpretation; MIDI output does not identify the guitar technique.

The public `predict()` duration default is **127.70 ms**. At 178 BPM, a
sixteenth lasts about **84.27 ms**, a thirty-second about **42.13 ms**, and an
eighth-note triplet about **112.36 ms**. Thus a faithful default run may suppress
intentional fast events before comparison. Keep raw activations and contrast
the upstream default with one fixed shorter-duration decoding preset. Lower
thresholds may instead add distortion partials or noise; neither variant is
accepted automatically. Model frame spacing is about **11.61 ms**, which is
not an onset-accuracy guarantee. `midi_tempo` is export metadata, not detected
BPM.

## Current-host wheel feasibility

Read-only local inspection verified macOS **26.7.1 arm64**, default Python
3.12.14 and the locked analysis `.venv` Python **3.14.6**, NumPy 2.5.3,
SciPy 1.18.1, librosa 0.11.0 and numba 0.68.0. ONNX Runtime, TensorFlow,
coremltools, pretty-midi, mir_eval and resampy are currently absent.

| Runtime | Live primary wheel/metadata evidence | Consequence |
|---|---|---|
| ONNX Runtime 1.30.0 | [PyPI](https://pypi.org/pypi/onnxruntime/1.30.0/json) lists `onnxruntime-1.30.0-cp314-cp314-macosx_14_0_arm64.whl`, 21,545,313 bytes, SHA256 `8b6169c16a48429890d2f4a0c774ebf54dfe9066a998514aad0518a16d398547`; dependencies flatbuffers, NumPy>=1.21.6, packaging, protobuf>=4.25.8. | Matching wheel exists; installation, ABI compatibility, graph support, memory and inference remain untested. |
| coremltools 9.0 | [PyPI](https://pypi.org/pypi/coremltools/9.0/json) lists arm64 wheels through cp313, no cp314 wheel. | Cannot satisfy this interpreter's wheel-only policy with this version. |
| tensorflow-macos 2.15.0 | [PyPI](https://pypi.org/pypi/tensorflow-macos/2.15.0/json) lists arm64 cp39/cp310/cp311 wheels and NumPy<2.0; pinned Basic Pitch requires TensorFlow-macos<2.15.1 on Darwin Python>3.11. | Ordinary package dependency resolution conflicts with current interpreter/NumPy. |
| tflite-runtime 2.14.0 | [PyPI](https://pypi.org/pypi/tflite-runtime/2.14.0/json) has no macOS arm64 wheel. | Not selected. |

ONNX Runtime [source license](https://github.com/microsoft/onnxruntime/blob/v1.30.0/LICENSE)
is MIT; runtime/dependency distribution notices remain separate from Spotify's
model/code evidence. [Session options](https://onnxruntime.ai/docs/api/python/api_summary.html)
support explicit CPU provider, thread counts and execution-mode selection.

Do not use an unrecorded `--no-deps` installation to imply normal Basic Pitch
compatibility. The preferred future adapter uses only the qualified ONNX
artifact and explicitly locked ONNX/NumPy plus existing resampling workers,
with reviewed, attributed upstream windowing/decoding logic. An isolated
environment may reuse compatible already-pinned wheels, but must not mutate
the main analysis lock silently. No CoreML/GPU/ANE execution, performance or
real-time AU suitability is qualified by this research.
