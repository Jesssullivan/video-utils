# Stem-separation weights licence qualification (2026-10-07)

Lane `model_lanes`, sprint 20261007-s3, Linear TIN-5721. Contract:
`docs/spec/sprints/MODEL_LANES_S3.md` section 5.

All sources were accessed on 2026-10-07 through the GitHub REST API, the Hugging
Face model API, the Zenodo records API, and HTTP `HEAD` on checkpoint URLs (no
body read). **Nothing was downloaded.**

The **code licence is never taken to cover weights**. Any later stem output is
an estimate from a mono mixture, never a recovered stem.

Verdicts:
- `admissible_private_comparator`
- `hold_unresolved_terms`
- `excluded`

## Why this matters for the take

The take is a mono phone capture with:
- one distorted nine-string guitar (fundamentals near 32.7 Hz);
- an in-room click;
- a large box fan.

There are no vocals, bass or drums. A separator's "guitar" or "other" output is
therefore a model's split of the guitar from fan, click and room. That is an
estimate, and its low-end behaviour near 32 Hz is unknown.

Inference: a stem lane is a private listening comparator at most. It is never a
cleanup default.

## Training-data terms shared by most candidates

MUSDB18-HQ (Zenodo record 3338373, <https://doi.org/10.5281/zenodo.3338373>,
licence id `other-nc`) states verbatim:

> "MUSDBHQ: is provided for educational purposes only and the material contained
> in them should not be used for any commercial purpose without the express
> permission of the copyright holders"

It also says the components carry their own terms:
- DSD100 / Mixing Secrets;
- MedleyDB tracks under CC BY-NC-SA 4.0;
- Native Instruments stems;
- The Easton Ellises tracks under CC BY-NC-SA 3.0.

## Candidates

### Demucs v4 (Hybrid Transformer Demucs)

**Code:**
- <https://github.com/facebookresearch/demucs>: MIT, archived. Last commit
  `e976d93ecc3865e5757426930257e200846a520a`.
- <https://github.com/adefossez/demucs>: MIT, "the officially maintained
  Demucs". Commit `2883f3db65617d6d178c6ed10d869dc14e44e59b`, 2026-08-31.
- Both READMEs: "Demucs is released under the MIT license as found in the
  LICENSE file."

**Weights hosting:**
- `demucs/pretrained.py`: `ROOT_URL = "https://dl.fbaipublicfiles.com/demucs/"`.
- `demucs/remote/files.txt` lists files under `hybrid_transformer/`.
- Each filename's suffix after the dash is the first 8 hex digits of the file's
  sha256. Demucs checks this prefix itself. It is a partial upstream hash, not a
  registry digest.

**Weights terms** (maintainer statements, verbatim):
- Alexandre Défossez, 2022-05-23, on "License of pre-trained models":
  > "The model weights are not covered by the MIT license, and are provided only
  > for scientific purposes."

  <https://github.com/facebookresearch/demucs/issues/327#issuecomment-1134828611>
- Alexandre Défossez, 2022-09-29:
  > "the code is free to use for commercial use and released under MIT. The
  > weights themselves are however just a research artefacts and provided only
  > for personal / research usage. The issue is that the licence of MusDB dataset
  > is only for research purpose. … it is your decision to make whether this risk
  > is acceptable to you."

  <https://github.com/facebookresearch/demucs/issues/384#issuecomment-1262197483>

**Training data** (README):
- `htdemucs`: "Trained on MusDB + 800 songs".
- `htdemucs_ft`: "Same training set as `htdemucs`".
- `htdemucs_6s`: "6 sources version of `htdemucs`, with `piano` and `guitar`
  being added as sources". The README adds: "Quick testing seems to show okay
  quality for `guitar`, but a lot of bleeding and artifacts for the `piano`
  source."
- The 800-song set and the guitar/piano training data are not described further.

| Checkpoint | URL | Bytes (`HEAD`) | Last-Modified | Stems | Verdict |
| --- | --- | --- | --- | --- | --- |
| `htdemucs` (`955717e8`) | `https://dl.fbaipublicfiles.com/demucs/hybrid_transformer/955717e8-8726e21a.th` | 84,141,911 | 2022-10-26 | drums/bass/other/vocals | `admissible_private_comparator` (conditions below) |
| `htdemucs_ft` (bag of 4) | `…/f7e0c4bc-ba3fe64a.th`, `…/d12395a8-e57c48e6.th`, `…/92cfc3b6-ef3bcb9c.th`, `…/04573f0d-f3cf25b2.th` | 84,141,271 each (336,565,084 total) | 2022-10-26 | one target stem per model; `92cfc3b6` = other | `admissible_private_comparator` (conditions below) |
| `htdemucs_6s` (`5c90dfd2`) | `https://dl.fbaipublicfiles.com/demucs/hybrid_transformer/5c90dfd2-34c22ccb.th` | 54,996,327 | 2022-12-07 | drums/bass/other/vocals/**guitar**/piano | `admissible_private_comparator` (conditions below), **recommended** |

**Inference: why "admissible" despite no licence file.** The operator's use is
private personal practice review. V6 (2026-10-07) keeps real-take derivatives
private on operator-controlled hosts. The maintainer's stated scope is
"personal / research usage". The conditions for that reading are:
1. personal/research use only, with no commercial use;
2. no redistribution of weights or of real-take stem outputs;
3. outputs stay under ignored `artifacts/` (V6);
4. outputs are labelled as estimates;
5. root records an explicit operator acknowledgement of the maintainer's "risk"
   sentence before first use.

The terms come from issue comments, not a licence file. If the operator reads
"scientific purposes" narrowly, the verdict becomes `hold_unresolved_terms`.

### BS-RoFormer / Mel-Band RoFormer

**Code only, no weights:**
<https://github.com/lucidrains/BS-RoFormer> is MIT. Its README points to
ZFTurbo's repository for trained weights.

**Training code and listings:** <https://github.com/ZFTurbo/Music-Source-Separation-Training>
- Repository licence: MIT.
- Commit `84b1eac0887756b4f1a9d7a1ff49105939749ed2`, 2026-09-26.
- `docs/pretrained_models.md` lists checkpoints. Neither the README nor that
  file states a weights licence.

| Checkpoint | Hosting / URL | Bytes | Stems | Terms found | Training data | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| MSST BS-RoFormer MUSDB18HQ `model_bs_roformer_ep_17_sdr_9.6568.ckpt` | GitHub release `v1.0.12` (2024-11-28) of ZFTurbo/Music-Source-Separation-Training, <https://github.com/ZFTurbo/Music-Source-Separation-Training/releases/download/v1.0.12/model_bs_roformer_ep_17_sdr_9.6568.ckpt> | 527,385,512 | bass/drums/vocals/**other** | None for weights; repo MIT is code. Release body: "BS Roformer model trained on MUSDB18HQ dataset" | MUSDB18-HQ only (`other-nc`, educational, non-commercial) | `hold_unresolved_terms` |
| viperx BS-RoFormer "other" `model_bs_roformer_ep_937_sdr_10.5309.ckpt` | <https://github.com/TRvlvr/model_repo/releases/download/all_public_uvr_models/model_bs_roformer_ep_937_sdr_10.5309.ckpt> (third-party UVR model mirror) | 393,068,365 | **other** | `TRvlvr/model_repo` has no licence (GitHub `license: null`); release body empty | Undisclosed | `excluded` (no terms, undisclosed data, third-party mirror) |
| Kimberley Jensen Mel-Band RoFormer `MelBandRoformer.ckpt` | <https://huggingface.co/KimberleyJSN/melbandroformer> (model revision `ac9b0614ab3cd7f77219e18ba494dfd93956c348`) | 913,106,900 (HF LFS sha256 `87201f4d31afb5bc79993230fc49446918425574db48c01c405e44f365c7559e`) | vocals plus instrumental residual | HF card metadata `license: mit` (the card is otherwise empty). The GitHub repo KimberleyJensen/Mel-Band-Roformer-Vocal-Model has no licence | "training with more data" from contributors. Provenance undisclosed | `excluded` for this lane (see below) |

Why the Kimberley Jensen checkpoint is excluded:
- It is a vocal-target model. Its "instrumental" output is the residual of a
  vocal mask, not a trained guitar or "other" target.
- The take has no vocals, so the model is irrelevant to the purpose.
- The weights are MIT per the HF card, but the dataset provenance is undisclosed.

Why the MSST BS-RoFormer checkpoint is held:
- The weights are distributed in an MIT code repository with no weights
  statement.
- The weights are trained only on a non-commercial, educational dataset.
- Inference: the likely intended use is research or fine-tuning ("These weights
  are useful for fine-tuning"). With no explicit grant, the lane does not infer
  one.

## Recommendation

- **Admissible, conditionally: `htdemucs_6s` only** (54,996,327 B). It is the
  single qualified checkpoint with a trained `guitar` source. It is admissible
  as a private listening comparator under the five conditions above, after an
  explicit operator acknowledgement.
- `htdemucs` and `htdemucs_ft` share the same terms but only offer "other".
  They add nothing over `htdemucs_6s` for a guitar-only take.
- **No RoFormer checkpoint is admissible now.** MSST BS-RoFormer is held; viperx
  and Kimberley Jensen are excluded.

Before any use:
- Root adds a hash-bound `program/models.json` entry. Its sha256 must come from
  root's own fetch; the 8-hex prefix `34c22ccb` is only a cross-check.
- A separate runtime lane is needed. Demucs needs `torch`/`torchaudio` and the
  `demucs` package, which is not qualified here.
- Bounded CPU placement on honey.

Mandatory output semantics:
- "estimate from a mono mixture";
- low-end (~32 Hz) preservation measured, not assumed;
- listening acceptance separate;
- never a master or cleanup default.

"None admissible" would also have been valid completion. The conditional verdict
depends on the operator accepting the maintainer's personal/research scope.

## Unknown

- Whether Meta has a formal licence for the Demucs weights beyond the
  maintainer's comments. None was found.
- The content of the 800-song internal set and of the 6-source training data.
- How any of these separators behave on heavy distortion near 32 Hz.
