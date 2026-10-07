# Beat This qualification (S3 model_lanes, TIN-5721)

Accessed on 2026-10-07 from primary sources: the GitHub REST API for
`CPJKU/beat_this`, the PyPI JSON API, and HTTP `HEAD` / WebDAV `PROPFIND`
metadata on the JKU Nextcloud share. **No weights were downloaded.** No
response body larger than a metadata listing was read. The comparator is
experimental and never a default, per `docs/spec/sprints/MODEL_LANES_S3.md`.

Claim classes used below:
- **documentary**: quoted or read from a primary source;
- **inference**: the lane's reading of those facts;
- **unknown**: not established.

## M1 fact groups (6/6)

### 1. Licence (code and weights recorded separately)

| Item | Statement | Source |
| --- | --- | --- |
| Code | `LICENSE` is MIT, "Copyright (c) 2024 Institute of Computational Perception, JKU Linz, Austria". `pyproject.toml` has `license = "MIT"`. GitHub reports the SPDX id `MIT`. | <https://github.com/CPJKU/beat_this/blob/ad7974846029835307ba19a3d5cefbf40b243041/LICENSE> (tag `v1.1.0`) |
| Weights | "The code and the published model weights are released under the [MIT license](LICENSE). Note that some of the training files are fully copyrighted or under limited Creative Commons licenses, and it is up to the user to assess whether this may impact their use case." | README `## License`, added by commit `b95c8ab0c58c2d9fcfd40508ae8dffbc05ac4f5c` "Clarify license for model checkpoints" (2026-05-28): <https://github.com/CPJKU/beat_this/commit/b95c8ab0c58c2d9fcfd40508ae8dffbc05ac4f5c> |
| Training data | `final*` models were "trained on all data except the GTZAN dataset". The README warns that results "may be unfairly good if you run inference on any file from the training datasets". | README, same commit |

These points are kept apart:
- **Documentary.** The weights licence is an explicit upstream statement on
  `main`. The code licence is a `LICENSE` file.
- **Documentary.** The weights statement was added *after* tag `v1.1.0`
  (2026-04-14). The tagged README does not contain it.
- **Inference.** The statement covers the checkpoints on the Nextcloud share,
  because those are the "published model weights" that the inference code
  fetches.
- **Unknown.** The training-data rights are separate, and upstream itself flags
  them.
- **Inference.** For a private, local, non-redistributed comparator the
  training-data caveat does not block use. It is recorded, not resolved.

### 2. Checkpoint URL and hosting

- **Code pin.** `beat_this/inference.py` at `v1.1.0` sets
  `CHECKPOINT_URL = "https://cloud.cp.jku.at/public.php/dav/files/7ik4RrBKTS273gp"`
  and resolves a short name to `f"{CHECKPOINT_URL}/{name}.ckpt"`.
- **Exact `final0` URL:**
  `https://cloud.cp.jku.at/public.php/dav/files/7ik4RrBKTS273gp/final0.ckpt`.
- **Human share page:** <https://cloud.cp.jku.at/index.php/s/7ik4RrBKTS273gp>
  (README "Models are available for manual download at our cloud space").
- **Upstream auto-download.** `load_checkpoint()` tries
  `torch.load(path, weights_only=True)` first. Only on `FileNotFoundError` does it
  fall back to `torch.hub.load_state_dict_from_url`.
- **How the comparator prevents downloads:**
  - It replaces `beat_this.inference.load_checkpoint` with a local-only loader
    that refuses anything except the verified path.
  - It replaces `torch.hub.load_state_dict_from_url` with a function that raises.
  - It points `TORCH_HOME`, `HF_HOME`, `XDG_CACHE_HOME` and `HOME` at an empty
    lane directory.
  - It sets `HTTP(S)_PROXY` to the closed loopback port `127.0.0.1:9`.

### 3. Checkpoint bytes and server checksums (metadata only)

`HEAD` on `final0.ckpt` (2026-10-07T04:55:42Z) returned:
- `content-length: 81058141`
- `last-modified: Mon, 01 Jul 2024 19:40:19 GMT`
- `etag: "16b9fd56ab436abbf2779aa85e2b5a87"`
- `oc-checksum: SHA1:e1506282faf66ca10e8ab50ee26bd542b7b9ff0a`

A `PROPFIND` (Depth 1) on the share listed 44 checkpoints. Selected rows:

| Checkpoint | Bytes | Server SHA1 (`oc:checksums`) | Last modified |
| --- | --- | --- | --- |
| `final0.ckpt` | 81,058,141 | `e1506282faf66ca10e8ab50ee26bd542b7b9ff0a` | 2024-07-01 |
| `final1.ckpt` | 81,058,141 | `f595e12ad29259a891b44626adb21eb7e479f486` | 2024-07-02 |
| `final2.ckpt` | 81,058,141 | `2d9f2f135a3a849a953de455646d12ec148f2794` | 2024-07-02 |
| `small0.ckpt` | 8,451,101 | `77a7ef5c21f628578f2b259ac29d2d680412efcc` | 2024-07-11 |
| `single_final0.ckpt` | 81,065,078 | `83811d287a221b3b1f53dc5543ecd29705562f6c` | 2024-07-25 |
| `fold0.ckpt` | 81,054,590 | `ef1ba4478a8e0829d26a4ccaff8eaf67c94e81b0` | 2024-07-25 |

What these numbers support:
- **Documentary.** The README says "About 78 MB per model" for `final*`.
  81,058,141 B is 77.3 MiB, which is consistent.
- **Unknown, by design.** No SHA-256 has been observed. The server SHA1 is
  server-reported metadata. It is not a substitute for the registry's sha256.
  Root fills the registry sha256 from its own explicit hash-bound fetch.
- **Inference.** Root may use the SHA1 only as a cross-check of its fetched
  bytes.

### 4. Runtime dependencies

**Package metadata** (PyPI `beat-this` 1.1.0, MIT, `requires_python >=3`):
`numpy>=1.20`, `torch>=2`, `torchaudio`, `einops`, `rotary-embedding-torch`,
`soxr`.

**Wheel:** `beat_this-1.1.0-py3-none-any.whl`, 40,060 B, sha256
`3f2b2d1e027c6dac380bf80c71555e3c28a4036a7f1af20129a945915a72a645`.

**Imports on the inference path** (`v1.1.0`):

| Module | Imports |
| --- | --- |
| `inference.py` | `numpy`, `soxr`, `torch` |
| `preprocessing.py` | `torchaudio` |
| `model/beat_tracker.py` | `einops`, `rotary_embedding_torch` |
| `model/postprocessor.py` | `einops` (`madmom` only when `dbn=True`) |

- **Documentary.** `requirements.txt` lists `tqdm==4.66.4` as a "known working"
  version, but no inference-path module imports `tqdm`.
- **Inference.** The lane therefore drops `tqdm` from the lock. This deviates
  from the contract text, which named `tqdm`.

**Upstream "known working" inference versions** (`requirements.txt`):

| Package | Version |
| --- | --- |
| einops | 0.8.0 |
| numpy | 1.26.4 |
| rotary_embedding_torch | 0.6.4 |
| soxr | 0.3.7 |
| torch | 2.3.1 |
| torchaudio | 2.3.1 |

**Flake `ml` shell.** The pinned nixpkgs is
`2c423e03bbafcff28bfadc6781a4a8257f205cb5`. `nix eval --offline` for
`x86_64-linux` gave:

| Package | Version |
| --- | --- |
| python | 3.14.7 |
| torch | 2.12.0 |
| torchaudio | 2.11.0 |
| numpy | 2.5.1 |
| einops (in nixpkgs, not in the shell) | 0.8.2 |
| rotary-embedding-torch (in nixpkgs, not in the shell) | 0.8.9 |
| soxr (in nixpkgs, not in the shell) | 1.1.0 |

Notes on the nixpkgs versions:
- **Unknown.** torch 2.12 / torchaudio 2.11 differ from the known-working
  2.3.1. Numerical parity with the paper setup is unverified.
- **Unknown.** Whether the nixpkgs `torchaudio` 2.11 pairs cleanly with
  `torch` 2.12 on honey is unverified. The comparator never calls
  `torchaudio.load`: it passes a decoded array to `Audio2Beats`. It still needs
  `torchaudio.transforms.MelSpectrogram`.

**Lock chosen** (embedded in `scripts/beat_this_runtime_setup.py`, lock sha256
`5cd29f827825973ad0dd30391919382449b807be4a4b87251d010313ec78d593`):

| Package | Version | Wheel bytes | Licence |
| --- | --- | --- | --- |
| beat-this | 1.1.0 | 40,060 | MIT |
| einops | 0.8.0 | 43,223 | MIT |
| rotary-embedding-torch | 0.6.4 | 5,366 | MIT |
| soxr | 1.1.0, cp312-abi3 manylinux, x86_64 or aarch64 | 240,413 / 206,529 | **LGPL-2.1-or-later** |

Notes on the lock:
- The upstream known-working versions are used where wheels exist for Python
  3.14. `soxr` 0.3.7 has no cp314 wheel, so the lock takes `soxr` 1.1.0, which
  is also the nixpkgs version.
- **Documentary.** `soxr` is a compiled extension, not pure Python. The contract
  called it pure Python; that was wrong.
- **Inference.** Its LGPL licence is acceptable for a private, unmodified,
  dynamically loaded comparator dependency, and it is recorded.
- torch, torchaudio and numpy come from the ml shell through
  `include-system-site-packages = true`. This is recorded explicitly and is not
  hash-pinned by the lane lock.

### 5. Input rate, frame rate and preprocessing

From `beat_this/preprocessing.py` and `inference.py` at `v1.1.0` (documentary):

**Audio input:**
- `Audio2Frames.signal2spect` downmixes 2-D input by mean.
- If `sr != 22050`, it resamples with `soxr.resample(signal, in_rate=sr, out_rate=22050)`.

**`LogMelSpect` parameters:**

| Parameter | Value |
| --- | --- |
| `sample_rate` | 22050 |
| `n_fft` | 1024 |
| `hop_length` | 441 (50 frames/s) |
| `f_min` | 30 |
| `f_max` | 11000 |
| `n_mels` | 128 |
| `mel_scale` | "slaney" |
| `normalized` | "frame_length" |
| `power` | 1 |
| `log1p` multiplier | 1000 |

**Inference chunking:**
- Chunks of 1500 frames (30 s) with `border_size=6`.
- `overlap_mode="keep_first"`.

**Postprocessing (`Postprocessor(type="minimal", fps=50)`):**
- Max-pool peak picking over ±3 frames (±70 ms).
- Logit > 0.
- Adjacent-peak deduplication.
- Downbeats snapped to the nearest beat.

**Tone context.** Inference: `f_min = 30 Hz` puts the nine-string's C1
(~32.7 Hz) at the lowest mel band edge. The front end neither removes nor
specifically represents that content. This is a property of the model's input,
not a processing change to any video-utils signal. Masters are untouched.

### 6. Checkpoint format and safe loading

- **Documentary.** The checkpoints are PyTorch Lightning checkpoints "stripped
  of the optimizer state", with `hyper_parameters` and `state_dict` (prefix
  `model.`).
- **Documentary.** The `v1.1.0` changelog says: "Load checkpoints with
  `weights_only=True` when supported".
- **Unknown until root's fetch.** Whether `final0.ckpt` loads under
  `torch.load(..., weights_only=True)` with torch 2.12 without allow-listing
  extra globals is unverified. If it fails, the worker raises and records the
  error. It never retries with `weights_only=False`.

## Registry entry (handed to root; M2)

Root adds the entry only after its own explicit fetch. It replaces the
placeholder with the measured sha256 before committing.
`model_prefetch.py` rejects non-hex digests, and that refusal is intended.

```json
"cpjku-beat-this-final0": {
  "url": "https://cloud.cp.jku.at/public.php/dav/files/7ik4RrBKTS273gp/final0.ckpt",
  "sha256": "TO_BE_FILLED_BY_ROOT_HASH_BOUND_FETCH",
  "max_bytes": 81058141,
  "format": "pytorch-lightning-ckpt (torch.load weights_only=True; optimizer state stripped upstream)",
  "license": "MIT (code LICENSE; published weights per upstream README commit b95c8ab0c58c2d9fcfd40508ae8dffbc05ac4f5c, 2026-05-28); training-data rights distinct and unresolved",
  "source_commit": "ad7974846029835307ba19a3d5cefbf40b243041",
  "server_sha1_cross_check": "e1506282faf66ca10e8ab50ee26bd542b7b9ff0a"
}
```

- `max_bytes` is the exact published `content-length`. A changed upstream file
  therefore fails the fetch rather than being silently accepted.
- `server_sha1_cross_check` is an extra key. `model_prefetch.py` ignores it, so
  root may drop it.

## Use in the project

- The comparator is never a default. Its fixed settings:
  - CPU
  - `float16` off
  - DBN off (`madmom` is not qualified)
  - upstream minimal postprocessing
  - no tunable knobs
- Beats and downbeats are model hypotheses. Downbeats are never bar lines, and
  `meter_claim` is always `"none"`.
- F-measure at 70 ms is computed only against generated fixture truth (suite
  `s3-beat-1`, contract section 7). Real-take accuracy remains unknown.
- The model was trained mostly on popular-music corpora. Whether it transfers to
  a distorted nine-string with an in-room click, a box fan, odd groupings and
  half-time feels is the open question. The preregistered experiment measures it
  on generated fixtures only.

## Limitations

- No bytes of any checkpoint were read, so no sha256 is known to the lane.
- The honey architecture (x86_64 or aarch64) is unverified. The lock carries
  both `soxr` wheels and selects by `platform.machine()`.
- Whether a venv created from the nix `python3.withPackages` interpreter sees
  the nix torch through `--system-site-packages` is expected, not verified. The
  runtime `--check` verifies it before any use.
