# Condense old/new parity on the archived walkthrough sources (2026-10-15)

Authority: operator interview 2026-10-15; Linear TIN-6543 (S4 milestone "Condense on real talks"); R-N13.
Tool: `condense/tools/parity.py` (`python3 -m condense.tools.parity OLD_ROOT NEW_ROOT talk.toml RUN_DIR`).

The media, the private `talk.toml` and both work trees stay on the operator host. This receipt records
hashes, counts, versions and measured numbers only.

## Inputs

| Item | Value |
| --- | --- |
| Archive check | `sha256sum -c SHA256SUMS`: 15 of 15 files OK after the copy |
| Retired tool | talk-condense backup bundle `b97cc721884344eb100b39b4f72bba5bfbfa6aa990fc0d7c4582e87d0ddfd0ed`, checked out at `bf5b9dc29dc0171063c9adc580eaed0d7eccb9d9` (package `talk_condense`) |
| New tool | `./condense` at `15cc8e7` plus parity.py (no stage module changed). Main has since gained `e28dd9f`, which changes only the default model path and an error hint; both runs set `WHISPER_MODEL` |
| Recording `intro` (3294.37 s) | `6385b058865b156b6061ddabb3406c68b64ed15afbcaebbea177aa3c7d9b25a3` |
| Recording `folds` (651.02 s, card clip) | `afff7a519b3f03f2eeafa063696696ae5434b9902704c5b314c4d09ce0163ae9` |
| Recording `iphone` (1138.89 s) | `a40342387c39e8bdbf98d38a5a10ed220a02522a63015ec6b2fa7ae05122548c` |
| `talk.toml`, all three clips | `e46d57e58069017fe87fb639b2119f4e1ff6f7e25f124c5f91d91c35f52b6a1b` |
| `talk.toml`, `iphone` only, 3 corrections | `d0157cfc8273fd151b75c74b351b5105800b7ec609e8ffb4e6c114c06cca2485` |

Versions, the same for both sides (one `nix develop .#condense` shell, nixpkgs `7c8764b`, the retired
flake's own pin): FFmpeg 8.1.2, whisper-cpp 1.8.4, Python 3.13.15, whisper model ggml-small.en
`c6138d6d58ecc8322097e0f987c32f1be8bb0a18532a3f88f734d1bbf9c41e5d` (from `just condense-model`).
Both configs set `[encode] jobs = 2` and `[whisper] threads = 4`, so the two tools' different defaults
(8/16 old, 2/4 new) do not enter the comparison.

## Run 1: all clips through transcribe, events and edl

Exit 0. 12 of 12 files match by sha256. Each stage exited 0 on both sides.

| File | sha256 | Counts |
| --- | --- | --- |
| `intro.pass1.json` | `724f88d0e0d3514e54e7158dfe9b356422ff33f3cdc0bb8fb78ff2e1ad2c3cd3` | 321 segments, 6555 tokens, 4 chunks |
| `intro.dtw.json` | `d4d33606e202b5c6ab89ac64700b9299a2f91d1fd5866ac4d111f517d53f7c0d` | 490 segments, 6081 tokens |
| `intro.words.json` | `b4fefa10f051e45c55c186f443507c00943b28dcecd599aa6f1bd2fc112ed8d2` | 4075 words |
| `intro.events.json` | `b284bd02d9c1836d63594fdd92628b53f9fbca4b6143663ce7db5915d85fc5cd` | 177 fillers, 796 pauses |
| `intro.rms.txt` | `d10468fd4aae972f2ca715956e30bfc680c44e4a5ea861abdfc317f53bfb6e5e` | |
| `iphone.pass1.json` | `49c6425c90a8f5a1624cc7603bdfe98f985e680c18b7961b1156c9a4d0dc1e9e` | 117 segments, 1995 tokens, 1 chunk |
| `iphone.dtw.json` | `adb32eb17bab7d5eb1aaccb2c73b4dbde23dccc02b9726087a7afcfa55785a95` | 157 segments, 1974 tokens |
| `iphone.words.json` | `e59f97c38b848b9b3252bf26fb3b4b7ff7b262261fe70c01603cb8f731789247` | 1457 words |
| `iphone.events.json` | `ec34c3629f222adf24623de307f5de089398f4c7b9d337ea73fe1387d0ed61d1` | 22 fillers, 279 pauses |
| `iphone.rms.txt` | `e05ad92f68115e2ae4d436a7bc7e0184e36183202b8749bd732a3ff4a68c8523` | |
| `iphone.pause_asr.json` | `f828b22b1570057278f471cd88cdefca2955dd06df32363e0f484e1b30eeef96` | 130 pause spans re-read |
| `edl.json` | `93091211dc5bed5f05ed5b6b2a0103f3187957521ef158a6fb2fa5598d25c7e3` | segments 1794 / 1 / 621; 1265.033 s; 37951 frames, validated by `video-utils timeline` |

The `folds` clip is a card, so neither tool transcribes it; it is one card segment in `edl.json`.

## Run 2: `iphone` end to end

The shortest transcribed clip, with each side's work dir seeded from its own Run 1 `iphone.*` files, then
edl, render, captions, overlay and publish. Exit 0 after the publish rerun below. 11 of 11 files match.

| File | sha256 | Measured |
| --- | --- | --- |
| `edl.json` | `3f50843369d2fa2af15f03f1fae25d5cd1834ab8241a4630e031b04c7ef0c89f` | 621 segments, 405.933 s |
| `talk.mp4` | `ca339812e42b5008c125f76048e5ec6158ae196f9838d88173eb26b3c793d6bc` | 12178 decoded frames, 405.938 s, audio 405.938 s |
| `talk.corrected.mp4` | `54243f8b6da415661608dc55c962d6063ca68347cdcb020df019f379a73502ac` | 12178 decoded frames, 405.938 s, 3 corrections |
| `talk.srt` | `6966a86eead4bba70f34bf7c5c6358f08668f2904fc1a142137c0c8e54c941ca` | 125 captions |
| `talk.vtt` | `bff4fcb1e21c40b4b85b98ee8e08bbd742b51f60a01b24d838f7d6b09c49958a` | |

The six `iphone.*` inputs are the Run 1 hashes above. The renders are byte-identical, not only equal in
frame count and duration.

Publish (new side only; the retired tool has no publish stage): `verify-run --timeline edl_v1` exit 0
inside the stage and again run by hand; 5 files, 12178 frames, 1882350226 bytes hashed; the manifest's
timeline frames equal its delivered frames. Manifest sha256
`328717a66500f89914990f77aa96f82549e844d3c2d0784e98be3063ae28efc8`.

## Evidence custody

`publish` writes under the checkout's gitignored `artifacts/condense/`, so the verified run and its
`.failed-<run_id>` sibling first landed in the lane worktree. Both are now copied into the private work dir
beside `talk.toml`, `talk-iphone.toml` and the two parity run dirs, so removing the worktree after merge
keeps the evidence for TIN-6544. The copies are byte-identical (6 of 6 and the failed run's files by
sha256). `verify-run` on the copy exits 1 with `run_dir_mismatch`: the manifest binds the absolute run
directory it was published to, and editing it would change the hashed manifest. So the copy preserves the
bytes; a fresh `verify-run` pass needs the original directory or a new publish.

## Findings

1. Parity holds: every compared intermediate and every output of the `iphone` render is byte-identical
   between `bf5b9dc` and `./condense`. Nothing was tuned.
2. Reduced scope: the 55-minute `intro` ran through transcribe, events and edl only. Its render is not
   compared. On a shared host the old side's transcribe took 7106 s and the new side's 4198 s; a render of
   one 19-minute clip took 2732 s and 1814 s. Wall times are host-load numbers, not a speed comparison.
3. Run 2 reused Run 1's `iphone.pause_asr.json` cache, so the 130 pause re-reads ran once per side in Run 1.
4. The first publish failed: `verify-run` refuses a recording reached through a symlink
   (`source_not_regular`), and the harness first staged recordings as symlinks. The run was kept as
   `.failed-<run_id>`. The harness now stages hard links (symlink only across filesystems); the rerun
   verified. An operator `talk.toml` must name regular files for publish.
5. The private `talk.toml` reproduces the first edit's settings except its intro set-up drop, which has no
   `talk.toml` key. So `intro` runs at the 2.5x cap and 839.1 s against `max_s = 480`. The rebuild of
   the published cut (TIN-6544) owns that gap.
6. Review fix: `parity.py` raised on a media file ffprobe cannot read, so a render that died partway left
   no receipt. It now records `probe: failed` on that side and the row differs (also when both sides hold
   the same unreadable bytes). Synthetic test: two 30-frame sides, one cut in half.

## Gates

- `just condense-lint`: ruff check and format check pass on 29 files.
- `just condense-test`: 65 passed before the hard-link change; `test_parity.py` 12 passed after it.
- `tests/test_condense_public_surface.py`: passes with `condense/tools/parity.py`.
- After the probe fix: `just condense-lint` passes on 29 files; `just condense-test` 67 passed (`test_parity.py` 14).
