# Audio classification candidate research

Reviewed October 6, 2026 by `/root/classification_future`. Authority: explicit
operator future planning request and repository AGENTS.md / R-N13. Read-only
local source inspection and primary web documentation only; no model bytes,
package installation, inference, sibling edits or remote infrastructure action.
The proposed product design is
[future/AUDIO_CLASSIFICATION.md](../spec/future/AUDIO_CLASSIFICATION.md).

## Primary sources and the role they establish

| Source checked | Supported role | Guitar limitation / next evidence |
|---|---|---|
| [llama.cpp official multimodal documentation](https://github.com/ggml-org/llama.cpp/blob/master/docs/multimodal.md) | `libmtmd` audio/vision/video input with model plus projector; CLI and server interfaces | Runtime support is model-specific. Documentation says Qwen2-Audio prequantized examples are withheld for poor results. No local audio-runtime parity was checked. |
| [Qwen2-Audio official repository](https://github.com/QwenLM/Qwen2-Audio) | Audio-language analysis/text response; music chat evaluation uses MusicCaps; it discloses score changes after Transformers conversion | General music conversation does not establish guitar phrase boundaries, exact note/timing labels or mistake accuracy. Need canonical-vs-converted evaluation and held-out guitar labels. |
| [LAION CLAP official README](https://github.com/LAION-AI/CLAP/blob/main/README.md) | Shared audio/text latent representations; music-oriented checkpoint candidates; waveform-data example specifies 48 kHz | Retrieval candidates rather than timestamped note events. Checkpoint-specific rights, source/encoder settings, low-register transfer and ranking calibration need qualification. |
| [TensorFlow YAMNet transfer-learning tutorial](https://www.tensorflow.org/tutorials/audio/transfer_learning_audio) | General 521-class AudioSet predictions and 1024-dimensional embeddings; mono 16 kHz; 0.96-s frames at 0.48-s stride | Optional fixed embedding baseline, with much broader support than rapid technical-guitar attacks. Its generic labels do not establish tapping/sweep/palm-mute classes or note correctness. |
| [librosa PCEN 0.11 documentation](https://librosa.org/doc/0.11.0/generated/librosa.pcen.html) | Spectral gain-control/compression with state and scale-dependent parameters; its example uses magnitude mel and explicit scaling | Feature transform, not audible restoration. Power/magnitude, smoother/warm-up and low-band coverage must be frozen separately. |
| [Wang et al. PCEN paper](https://arxiv.org/abs/1607.05666) | Trainable frontend motivated/evaluated for keyword spotting | The domain differs from distorted guitar; test rather than infer transfer. |
| [Guo et al. calibration paper](https://arxiv.org/abs/1706.04599) | Modern neural scores may be miscalibrated; temperature scaling is a candidate calibration technique | Calibration is not a guitar result and does not resolve new capture-domain shift or unsupported classes. Separate validation/calibration/test groups. |

These live upstream pages are moving documentation, not admitted revision pins.
Any acquisition must first select and record exact repository/checkpoint/runtime
revisions, hashes and applicable licenses. Repository code licensing alone must
not be presented as a verified license for arbitrary weights or their datasets.
Search snippets, third-party runtime summaries and benchmark leaderboards were
not used to qualify audio support or guitar accuracy.

## Inspected local precedents

The in-repo [XOD research](XOD_SPECTROGRAM.md),
[actual PCEN characterization](../agent-notes/2026-10-06-pcen-actual-transfer.md),
[pitch numerical pilot](../agent-notes/2026-10-06-learned-pitch-numerical.md) and
[localization diagnostic](../agent-notes/2026-10-06-phrase-localization-diagnostic.md)
provide relevant positive runtime/feature evidence and negative quality evidence.
They support bounded comparisons, not a current trained guitar classifier.

Read-only sibling paths inspected:

- `/Users/jess/git/xoruby-2026-tin5128/docs/research/recipe-reconstruction-2026.md`,
  `docs/agent-notes/2026-09-29-r2-recipe.md` and `ml/recipe2021/{frontend,model,train}.py`.
  They document a public-audio reconstruction, trainable PCEN, ResNet-18
  multi-label head, recording-level grouping, ablation failures and Ruby/ONNX
  parity receipts. Their target is bird classification; frontend starts at
  400 Hz. No private historic substrate or implementation was copied. Historical
  receipt statements were read, with no rerun or present runtime acceptance.
- `/Users/jess/git/blahaj/docs/applications/searxng/pg-backend-architecture.md`
  discusses Qwen3-Embedding/text query vectors; this is not an audio encoder or
  a verified guitar classifier. Its numerical platform estimates were not adopted.
- `/Users/jess/git/blahaj/docs/sprints/2026-W18-pod-classification.md` concerns
  cluster workload placement/classification and Sting compute ownership, not
  musical class labels. No `/Users/jess/git/sting` checkout was present.

No source receipt for the user-mentioned decision rank models or separate
“runes” audio work was established by these bounded path/content searches.
That pointer remains unknown. The other local Codex sessions were not contacted;
future integration should ask the existing owner for exact source/evaluation
receipts when the work is prioritized. No lack-of-local-hit claim excludes work
on another host, branch, checkout or unpublished agent lane.

## Recommended order

The local label/revision/corpus machinery makes a four-hour label/split/evaluation
contract the useful shared-sprint contribution. Then run one fixed-feature
exemplar retrieval experiment, keeping automatic discovery independent of
operator arrangement labels. Choose a small calibrated multi-label head only
when reviewed positive, negative and ambiguous examples exist in independent
take groups. PCEN/window ablation remains its existing optional lane. Larger
audio-language candidates follow explicit runtime/rights admission and a
representative guitar-transfer evaluation. An agent can already parse and save
an operator observation; this does not require claiming a text model heard the
audio or turning model-generated captions into musician truth.
