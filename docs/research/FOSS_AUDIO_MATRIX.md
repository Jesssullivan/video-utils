# FOSS audio decision matrix

Primary-source review: **October 5, 2026**. This matrix contains **23 bounded
candidates** and **eight implementation decisions**. Branch snapshots describe
the inspected source, not a claim that a package is installed or its API is
stable. Versioned links take precedence over an unversioned README. Licensing
entries report upstream evidence; code, model weights, recordings, and SDKs are
separate artifacts.

The common evaluation case is the operator's distorted nine-string guitar:
stated C F Bb Eb Bb Eb Ab C F pitch classes, inferred C1–F4 octaves, theoretical
**C1=32.703195663 Hz**, approximately 178 BPM context, unknown/changing meter,
syncopation, rests, sweeps, tapping, and legato. **Every recommendation inherits
these cases**, including framework and validator choices; none establishes
fidelity by itself. Instrument-specific risks and choices below are engineering
inferences, unless an upstream limitation is explicitly identified.

The [registered instrument](../../program/instrument.json) preserves the exact
custom tuning; it does not identify played notes. Source inspection found
`uv.lock` pins librosa **0.11.0**, and the inspected
`program/models.json` still has an empty models map. This lane performed no
package installation, checkpoint download, build, recording upload, plugin
repair, or listening assessment. Runtime and publication receipts stay with
their owning lanes. The earlier [research](RESEARCH.md) remains historical
context; this matrix refines current candidate/API/license evidence.

## Restoration and preservation

| # | Candidate and applicable evidence | Interface / license boundary | Instrument risk and bounded choice |
| --- | --- | --- | --- |
| 1 | **FFmpeg `afftdn` / `loudnorm`, 8.1.2**. [Tagged denoiser source](https://github.com/FFmpeg/FFmpeg/blob/n8.1.2/libavfilter/af_afftdn.c), [filter controls](https://ffmpeg.org/ffmpeg-filters.html#afftdn), [build licensing](https://ffmpeg.org/legal.html) | Offline media/filtergraph adapter; denoiser source LGPL-2.1-or-later, effective binary license depends on configured components. No weights. | **Retain baseline.** Fixed mild reduction, explicit noise capture, and residue comparison; protect C1 and intended distortion. Calibrate waveform delay, not just stream timestamps. Do not infer a high-pass from the source's 80 Hz profile-band center. |
| 2 | **Audacity noise reduction**, current official manual and source license. [Profile/residue workflow](https://www.audacityteam.org/manual/effects/noise-removal-and-repair/noise-reduction/), [source licensing](https://github.com/audacity/audacity/blob/master/LICENSE.txt) | Manual comparator; application GPLv3, individual files can differ. No checkpoint needed. | **Adopt review paradigm, not a new default dependency.** Profile only confirmed noise; inspect removed material at matched loudness. Quiet low-string decay or legato is wanted audio even when it resembles steady noise. |
| 3 | **libspecbleach**, inspected main declares **0.4.1**. [Version](https://github.com/lucianodato/libspecbleach/blob/main/CMakeLists.txt), [public C API](https://github.com/lucianodato/libspecbleach/blob/main/include/specbleach_denoiser.h), [license](https://github.com/lucianodato/libspecbleach#license) | LGPL-2.1-or-later C engine; explicit initialize/process/get-latency API. Header separates setup-only calls from declared allocation/lock/I/O-free process calls. No model. | **Optional native comparison.** Pin a commit before ABI work; verify selected backend/worker behavior independently. Low-bin protection, transient veto, residue, and measured latency matter more than the denoiser label; adaptive learning can absorb C1 sustain. |
| 4 | **RNNoise**, inspected Xiph convenience mirror master. [Speech target and 48 kHz example](https://github.com/xiph/rnnoise), [C API](https://github.com/xiph/rnnoise/blob/master/include/rnnoise.h), [BSD-3-Clause license](https://github.com/xiph/rnnoise/blob/master/COPYING) | `rnnoise_process_frame`, queried frame size, model/setup lifecycle; mono 48 kHz example. README points to canonical Xiph GitLab; that endpoint was unavailable in this pass. Custom weights require separate provenance. | **Exclude guitar default.** Speech enhancement is not transparent distorted-guitar cleanup. A negative-control experiment must examine C1 loss, harmonic damage, and weak legato; do not assume a fixed frame API from another RNNoise fork. |
| 5 | **DeepFilterNet 0.5.6**. [Release](https://github.com/Rikorose/DeepFilterNet/releases/tag/v0.5.6), [versioned README](https://github.com/Rikorose/DeepFilterNet/blob/v0.5.6/README.md), [code license](https://github.com/Rikorose/DeepFilterNet/blob/v0.5.6/LICENSE) | Rust/C/Python speech-enhancement ecosystem; code MIT or Apache-2.0. Documented CLI processes 48 kHz WAV and exposes `--compensate-delay` for STFT/model lookahead. A chosen checkpoint still needs artifact-specific terms/hash. | **Exclude guitar default.** Full-band sample rate does not prove C1/metal preservation. Only compare as a bounded speech-domain negative control; record resampling, lookahead, attacks and tails, never infer removal quality from model availability. |

The [8.1.2 source](https://raw.githubusercontent.com/FFmpeg/FFmpeg/n8.1.2/libavfilter/af_afftdn.c)
uses integer hop `floor(sample_rate/80)`, a three-hop window, and a two-hop input
offset while retaining frame properties. The separately owned
[media latency lane](../spec/MEDIA_LATENCY.md) reports **1102 samples at 44.1 kHz**
and **1200 at 48 kHz**, with impulse qualification and tail padding before
compensation. These are that lane's measurements, not a new experiment here.
Container PTS/sample extent can pass while waveform attacks remain delayed.
The formula is version-specific; fail or recalibrate on another implementation.

## Music analysis and optional separation

| # | Candidate and applicable evidence | Interface / license boundary | Instrument risk and bounded choice |
| --- | --- | --- | --- |
| 6 | **librosa beat/CQT/recurrence, 0.11.0**. [Beat API](https://librosa.org/doc/0.11.0/generated/librosa.beat.beat_track.html), [recurrence API](https://librosa.org/doc/0.11.0/generated/librosa.segment.recurrence_matrix.html), [ISC license](https://github.com/librosa/librosa/blob/main/LICENSE.md) | Offline array APIs; recurrence connectivity/distance/affinity and temporal exclusion accept arbitrary feature sequences without a meter declaration. No weights. Versioned docs match the committed lock. | **Adopt bounded feature/recurrence adapter.** Use source-time mappings and a capped feature rate. Chroma folds octaves; combine timbre/energy and pitch-class evidence for different low-string riffs. Beat tracking does not require or establish fixed four-bar form. |
| 7 | **SuperFlux-style onsets in librosa 0.11.0**. [Official reconstruction](https://librosa.org/doc/0.11.0/auto_examples/plot_superflux.html) | ISC code/example; maximum-filter spectral flux, demonstrated vibrato suppression; example uses 5 ms hop, `lag=2`, `max_size=3`, `fmin=27.5 Hz`. No weights. | **Preferred onset comparison.** Contrast raw and maximum-filter flux. Representing C1 in a filterbank does not prove low-register resolution or legato note detection; separately inspect sweep/tapping/hammer-on passages and attack merging. |
| 8 | **pYIN in librosa 0.11.0**. [Versioned API](https://librosa.org/doc/0.11.0/generated/librosa.pyin.html) | ISC algorithmic F0/voiced/probability outputs. Explicit `fmin/fmax/sr/frame_length/hop_length`; `win_length` deprecated in this version. Suggested C2 minimum is not an absolute lower bound. | **Use only qualified monophonic evidence.** Set feasible range below C1 and record window length: 4096/44.1 kHz≈92.9 ms, about three C1 cycles. Longer evidence windows blur fast sweeps; chords, distortion and octave ambiguity can invalidate F0. |
| 9 | **FMP / libfmp**, inspected package **1.3.0**, notebooks **1.2.6**. [Package/version](https://github.com/groupmm/libfmp/blob/master/setup.py), [code MIT](https://github.com/groupmm/libfmp/blob/master/LICENSE), [notebook licensing](https://www.audiolabs-erlangen.de/resources/MIR/FMP/C0/C0.html) | SSM novelty and DTW algorithm references. Package code MIT; notebook text/figures CC BY-NC-SA 4.0; audio retains its original terms. [Novelty](https://www.audiolabs-erlangen.de/resources/MIR/FMP/C4/C4S4_NoveltySegmentation.html), [DTW](https://www.audiolabs-erlangen.de/resources/MIR/FMP/C3/C3S2_DTWbasic.html) | **Adopt references, not bundled copyrighted audio.** Discover candidates without an intended score. Tone/rest changes can mimic boundaries; unconstrained DTW can hide rushing. Retain original times and bound warping for low riffs and legato comparisons. |
| 10 | **Beat This**, inspected main package **1.1.0**. [Packaging](https://github.com/CPJKU/beat_this/blob/main/pyproject.toml), [inference and license](https://github.com/CPJKU/beat_this) | PyTorch beat/downbeat inference. Upstream explicitly grants MIT for code and published weights, while distinguishing training-file rights. Pin the selected release/checkpoint and hash separately. | **Optional rhythm comparator.** Test half/double tempo around 178 BPM, non-strict meter and weak legato; beat/downbeat logits do not establish note count, intended form, or a mistake. No default model download. |
| 11 | **Demucs official successor, 4.1.0**. [Maintained home](https://github.com/adefossez/demucs), [package](https://github.com/adefossez/demucs/blob/main/pyproject.toml), [version](https://github.com/adefossez/demucs/blob/main/demucs/__init__.py) | Code MIT, Python≥3.10; current successor uses Hugging Face hosting. `htdemucs_6s` adds experimental guitar/piano to four-stem music separation. **Weights do not inherit code MIT:** [maintainer statement](https://github.com/facebookresearch/demucs/issues/327#issuecomment-1134828611), [current card without license](https://huggingface.co/adefossez/HTDemucs/blob/main/README.md). | **Hold pretrained admission until exact artifact terms are qualified.** Mono guitar-plus-click outputs are estimated stems. C1 guitar may leak to bass; click attacks may leak to drums; preserve low-string sustain and sweep/tapping before any isolation claim. |
| 12 | **BS-RoFormer / Mel-Band RoFormer**, 2023 papers; inspected lucidrains replication **1.2.4**. [BS paper](https://arxiv.org/abs/2309.02612), [Mel paper](https://arxiv.org/abs/2310.01809), [implementation](https://github.com/lucidrains/BS-RoFormer), [MIT code](https://github.com/lucidrains/BS-RoFormer/blob/main/LICENSE) | PyTorch separation architecture. Replication is not verified as the paper authors' released implementation. Linked independent [ZFTurbo](https://github.com/ZFTurbo/Music-Source-Separation-Training) / [Kimberley Jensen](https://github.com/KimberleyJensen/Mel-Band-Roformer-Vocal-Model) weights need their own grant/config/hash. | **Defer checkpoint selection.** Vocal benchmark results and MIT architecture code do not qualify guitar/click weights. Compare only a qualified guitar-relevant model against C1 leakage, weak legato and artifact/latency evidence; do not promise original stems. |
| 13 | **Basic Pitch 0.4.0**. [Tagged README](https://github.com/spotify/basic-pitch/blob/v0.4.0/README.md), [model directory](https://github.com/spotify/basic-pitch/tree/v0.4.0/basic_pitch/saved_models/icassp_2022), [range constants](https://github.com/spotify/basic-pitch/blob/v0.4.0/basic_pitch/constants.py) | Apache-2.0 repo; TF and converted CoreML/ONNX/TFLite artifacts are bundled there, with no separate model license found in that directory. `predict()` returns outputs/MIDI/note events; input becomes mono 22.05 kHz. 88 semitone bins start at **27.5 Hz**. | **Optional transcription comparator.** C1 is representable, not guaranteed accurate. Qualify the exact bundled artifact rather than arbitrary mirrors; evaluate octave errors, distorted chords and legato merging. Known open-string tuning is a prior, not identified played notes. |
| 14 | **Essentia classical MIR**, inspected docs **2.1-beta6-dev**. [Code license](https://github.com/MTG/essentia/blob/master/COPYING.txt), [PitchYinFFT](https://essentia.upf.edu/reference/std_PitchYinFFT.html), [RhythmExtractor2013](https://essentia.upf.edu/reference/std_RhythmExtractor2013.html), [KeyExtractor](https://essentia.upf.edu/reference/std_KeyExtractor.html) | AGPLv3 code; classical algorithms need no checkpoint. Pitch minimum defaults to 20 Hz; zero-confidence pitch is undefined. RhythmExtractor2013 requires 44.1 kHz; degara has no meaningful confidence. Development docs are not installed-wheel evidence. | **Secondary offline comparator, not another baseline dependency.** Low minimum permits C1 testing but not polyphonic correctness. Key-profile correlation may misread distorted riff harmony. Optional model terms conflict across [licensing](https://essentia.upf.edu/licensing_information.html), [catalog](https://essentia.upf.edu/models.html), and [model LICENSE](https://essentia.upf.edu/models/LICENSE); keep unresolved. |

## Tone ML, native integration, and independent diagnostics

| # | Candidate and applicable evidence | Interface / license boundary | Instrument risk and bounded choice |
| --- | --- | --- | --- |
| 15 | **Neural Amp Modeler**, core **0.6.0**, plugin **0.7.15**. [Core/version/license](https://github.com/sdatkinson/NeuralAmpModelerCore/tree/v0.6.0), [plugin/version/license](https://github.com/sdatkinson/NeuralAmpModelerPlugin/tree/v0.7.15) | Both codebases MIT; amp/pedal modeling/playback. Different core/plugin versions do not establish embedded-core equivalence. Models/IRs have separate artifact terms; [TONE3000 terms](https://www.tone3000.com/terms) retain creator ownership. | **Defer to a qualified DI/reamping experiment.** It is not denoising or inversion of phone-recorded distortion. A model can alter C1 response and legato dynamics intentionally; do not describe new tone as recovered amp settings. |
| 16 | **RTNeural**, inspected commit `95c3c0f987a6fe903e7eec71e797405dbed7caf7`. [API](https://github.com/jatinchowdhury18/RTNeural/blob/95c3c0f987a6fe903e7eec71e797405dbed7caf7/README.md), [BSD-3-Clause](https://github.com/jatinchowdhury18/RTNeural/blob/95c3c0f987a6fe903e7eec71e797405dbed7caf7/LICENSE) | C++ Dense/GRU/LSTM/convolution inference, JSON loading, `reset()`/`forward()`; chosen Eigen/xsimd/STL dependencies need inventory. No supplied guitar restoration model. | **Optional bounded inference adapter only after model qualification.** Parse/load outside render; measure selected backend allocation behavior and latency. Inference throughput proves neither C1 fidelity nor sweep/tapping tone preservation. |
| 17 | **JUCE 9.0.3**. [Release](https://github.com/juce-framework/JUCE/releases/tag/9.0.3), [versioned license](https://github.com/juce-framework/JUCE/blob/9.0.3/LICENSE.md), [formats](https://github.com/juce-framework/JUCE) | C++ AU/AUv3/VST3/LV2/AAX framework; modules AGPLv3 or commercial JUCE terms, examples ISC, dependencies separate. Native CLAP is not advertised by this upstream format list. | **Defer framework migration.** Useful if broad host/UI requirements justify it; not required for the existing native AU spike. Format support and framework licensing say nothing about C1/variable-meter/legato DSP behavior. |
| 18 | **NIH-plug**, inspected commit `de421011f41a6d10fc8c7a6084e4f4dee0143683`. [Pinned README](https://github.com/robbert-vdh/nih-plug/blob/de421011f41a6d10fc8c7a6084e4f4dee0143683/README.md) | Rust CLAP/VST3 exports; framework/examples ISC, selected `vst3-sys` bindings explicitly GPLv3. Maintenance mode; no native AU export documented. Binding terms are not replaced by another SDK's license. | **Defer to separate cross-platform lane.** Rust support does not make it a Logic AU wrapper. Preserve musical fixtures in the common DSP core and independently test each host; do not route offline MIR into render. |
| 19 | **DPF**, inspected commit `4238e1c7f0351bbe488d79f0899c540543ac7583`. [Licensing](https://github.com/DISTRHO/DPF/blob/4238e1c7f0351bbe488d79f0899c540543ac7583/LICENSING.md), [CMake AU target](https://github.com/DISTRHO/DPF/blob/4238e1c7f0351bbe488d79f0899c540543ac7583/cmake/DPF-plugin.cmake), [feature status](https://github.com/DISTRHO/DPF/blob/4238e1c7f0351bbe488d79f0899c540543ac7583/FEATURES.md) | ISC framework; listed AU/VST3 wrappers ISC, CLAP MIT. **AU target exists** despite shorter README; AU sidechain/port/parameter groups remain unfinished in the feature table. Not proof of AUv3. | **Viable later AUv2 comparison; defer now.** Do not incorrectly reject it as lacking AU or imply current Logic acceptance. Low-frequency/legato fidelity belongs to the DSP, while bus/latency/state compatibility needs host fixtures. |
| 20 | **Native Swift AUv3 shell + Rust C ABI**. [Apple AUAudioUnit](https://developer.apple.com/documentation/AudioToolbox/AUAudioUnit), [Swift/C++ effect sample](https://developer.apple.com/documentation/avfaudio/creating-custom-audio-effects), [Rust FFI](https://doc.rust-lang.org/nomicon/ffi.html) | Apple platform SDK/sample terms are separate, **not FOSS SDK claims**. Replacing sample C++ DSP with Rust is our architectural inference. Opaque handles, explicit buffers and `repr(C)` types; control panic/unwind across ABI. | **Retain native integration direction.** Setup/preallocation/model work stays off render; no I/O, subprocesses, locks, allocation or runtime-dependent object work in DSP. Test C1 sustain, legato attacks and variable musical context with no automatic time correction. |
| 21 | **Carla 2.5.10**. [Versioned README](https://github.com/falkTX/Carla/blob/v2.5.10/README.md), [release](https://github.com/falkTX/Carla/releases/tag/v2.5.10) | GPLv2-or-later host; AU/VST3/LV2, rack/patchbay and CoreAudio. Transport sync/bridging are described as experimental. | **Optional independent host diagnosis.** Compare identical low-register/legato fixtures and explicit latency/bypass; do not treat Carla timing or component load as proof of Logic AUv3, musical correctness, or restore quality. |
| 22 | **Ardour**, official site currently advertises **9.8**. [Release notes](https://ardour.org/whatsnew.html), [features/license](https://ardour.org/features.html) | GPLv2 DAW; AU/VST3/LV2, video timeline, automation and loudness analysis. Website/version facts are a dated snapshot, not a local installation. | **Optional audition/automation comparator.** Source-time alignment and gain-matched C1/sweep/tapping review transfer; host success does not establish Logic compatibility or fixed meter. No installation in this lane. |
| 23 | **pluginval 1.0.4**, with Apple `auval`/Logic diagnostics as platform references. [Versioned README](https://github.com/Tracktion/pluginval/blob/v1.0.4/README.md), [Apple validation boundaries](https://developer.apple.com/library/archive/documentation/MusicAudio/Conceptual/AudioUnitProgrammingGuide/AudioUnitDevelopmentFundamentals/AudioUnitDevelopmentFundamentals.html), [Logic diagnosis](https://support.apple.com/en-gb/122179) | pluginval GPLv3; AU/VST/VST3 separate-process checks and headless strictness. Apple documentation for `auval` is archived: verify local OS/tool applicability. Plugin Manager has its own compatibility result. | **Adopt separate receipts, no repair actions.** Component checks omit musical/DSP-quality acceptance. Actual Logic tests need instantiation, automation, state reload, bypass, latency/glitches and C1/legato audition. Unknown meter remains analysis metadata, not a validator conclusion. |

## Eight focused decisions and adapter boundaries

1. **Retain FFmpeg for offline restoration/export.** Keep source rate/channels,
   frame timing and immutable input; record source-time mappings and actual
   executable identity. Accept the owning lane's measured delay compensation,
   then separately verify low-register attacks/tails and output peaks. No blanket
   80 Hz filter, hum notch, or automatic de-clipping of intended distortion.
2. **Use noise-profile and residue review before stronger suppression.** Compare
   bypass/current mild settings; a quiet candidate is not noise-only. Inspect
   C1 decays and legato before accepting a captured profile. RNNoise/DeepFilterNet
   stay out of the guitar default; libspecbleach gets one bounded later comparison
   rather than replacing a working pipeline on name recognition.
3. **Prioritize librosa 0.11.0 onset and recurrence adapters.** Compare source and
   restored analysis with raw/SuperFlux-style flux, timbre/energy, and low-aware
   pitch-class features. Cap duration/feature rate and preserve actual seconds;
   fixed pulse groups and bars remain hypotheses under changing/unknown meter.
4. **Use FMP novelty and constrained alignment for automatic discovery.** No
   intended score is required for repeated riffs, phrase/breakdown candidates,
   or self-consistency flags. Preserve original offsets when comparing recurrences;
   do not let DTW erase rushing or confuse rests/legato with skipped notes.
5. **Keep pitch/transcription qualified and optional.** Start bounded low-range
   pYIN with voiced/unknown output, then one exact Basic Pitch artifact comparison
   if qualified. C1 needs multiple cycles; pitch windows and 5 ms onset hops are
   different clocks. Tuning metadata does not identify played notes, and a chord
   or sweep can make a single F0 meaningless. Definite wrong-note grades need intent.
6. **Limit learned-model admission.** One qualified Beat This comparison can
   fit the optional rhythm lane. Hold Demucs/RoFormer/Essentia checkpoints with
   unresolved terms; neither a model-card badge nor architecture-code license
   substitutes for the selected weight's grant/config/hash. Mono C1 guitar/click
   separation remains an estimated-stem experiment with bleed/legato review.
7. **Keep tone modeling and native delivery separate.** NAM requires qualified
   modeling/reamping material, not inversion of a compressed phone take.
   RTNeural is an inference adapter, not a trained denoiser. Continue the native
   Swift/Rust ABI spike; JUCE/DPF/NIH-plug remain alternatives if actual host/UI
   requirements change. Musical C1/variable-meter/legato fixtures stay common.
8. **Diagnose owned plugins without repairing them.** Record component identity,
   architecture, metadata/signing evidence, OS/host versions, validator output,
   and actual host behavior as different states. External FOSS hosts add comparison
   evidence; they cannot certify Logic, musical quality, or meter. Repairs require
   a separately named authorized target and durable receipt.

Adapters return source/upstream hashes, version/config identity, analysis rate,
sample/window/hop origin, delay compensation, source-time events/spans, confidence
kind, and explicit unknowns. Model adapters also return checkpoint hash and
artifact-license evidence. Offline Python/model workers run outside native render;
agent/MCP invocations expose bounded jobs and supported parameters, not arbitrary
shell or implicit installation. Shared acceptance fixtures cover C1 sustain and
distorted harmonics, pick attacks/palm-mute tails, weak legato/sweeps/tapping,
rests/tuplets/changed meter, no-intent recurrence discovery, and calibrated timing.

## Plugin diagnosis and licensing gaps

Documented diagnosis is not authorization to manipulate an installed plugin.
For an explicitly owned target, read its bundle metadata and architecture,
verify signing evidence, and capture host/OS/tool versions before an isolated
validation run. `auval` exercises component code; successful enumeration, API
validation, host instantiation, saved-state reload, and listening are different
receipts. Cache deletion, resets/rescans, quarantine removal, re-signing,
uninstallation, and stopping shared audio services are not actions of this lane.
[Apple's troubleshooting instructions](https://support.apple.com/en-gb/122179)
describe recovery steps; they do not make those steps part of this research run.

Three unresolved distinctions affect practical admission:

- **Demucs:** the maintainer's 2022 statement explicitly separates weights from
  MIT code; the current author-hosted HTDemucs card has no license grant.
  That historical statement is not a new grant for the exact 4.1-era artifact.
  Obtain artifact-specific evidence before registration; do not blanket-label
  downloaded Demucs weights MIT.
- **Essentia:** official licensing says CC BY-NC-ND 4.0, its model catalog says
  CC BY-NC-SA 4.0, and model LICENSE text/link disagree. Classical code and
  algorithms can be evaluated separately; no selected checkpoint is qualified
  by resolving the conflict ourselves.
- **RoFormer/tone models:** third-party architecture repositories and model/IR
  hosts have independent terms. Record the exact origin and rights statement;
  arbitrary mirrors, shared `.nam` files, or linked vocal models inherit neither
  a code license nor the musical suitability claimed by another model.

## Priority within the existing week

| Allocation | Research-informed delivery priority |
| --- | --- |
| **Baseline 35 h, seven 5 h days** | D1 ingestion/provenance/bounded adapters; D2 restoration/delay/export; D3 click/onset comparison; D4 calibrated timing and self-consistency; D5 feature/recurrence phrase discovery with nullable meter/tonic; D6 labelled examples/reports; D7 failure/marker/host-boundary handoff. pYIN is bounded supporting evidence, not mandatory full transcription. |
| **Optional rhythm 8 h** | Improve recurrence/legato and ambiguous tempo; one qualified Beat This or Basic Pitch comparison after transparent baseline evidence. Do not add every MIR library. |
| **Optional stems 8 h** | Resolve one exact artifact's terms first, then run one preservation/bleed benchmark. If qualification remains unresolved, deliver the evidence gap and adapter design without downloading. |
| **Optional robustness 9 h** | Broaden C1/attack/tail, uncertain-meter, no-intent, stream-offset and interruption fixtures; compare matched-loudness residue and derivative timing. |
| **Optional AU spike 10 h** | Native Swift/Rust ABI, bus/state/latency tests, component validation, and separately observed Logic behavior. No framework migration or installed-plugin repair is assumed. |

These are priorities inside the approved **35+35 hours**, not additional
allocations. Noise attenuation, louder mastering, stem availability,
paper benchmarks, format support, and validator passes do not establish this
take's musical acceptance. Root records installed/tested/rendered states and
operator listening separately.
