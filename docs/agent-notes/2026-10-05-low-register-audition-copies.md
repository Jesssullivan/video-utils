# Low-register audition copies and static listening page

Actor/owner `audio_research`. Authority: root's new explicit audition-only
artifact assignment after the positive independent actual-array audit, under
the operator restoration goal, repository `AGENTS.md` and
R-HOOK-CONVERGENCE-20261004 / R-N13. This phase authorizes listening copies
from frozen diagnostic evidence. The earlier diagnostic's no-media-export
scope and recorded `media_exported=false` remain true for that earlier phase;
these new audition WAVs are separately authorized and do not replace a master.

Owned writes: this new dated receipt and ignored exporter/HTML/WAV/provenance
artifacts under `artifacts/experiments/low-register-actual-diagnostic`. No tracked
source worker, core report, profile, public primitive, main master, latest
pointer or server was changed. Browser QA is a separate root-delegated task.

## Bound input and copy operation

Frozen actual diagnostic result:
`e946198d9a88c14045566d114a95deed75b9114afe01162723a517d825783e6b`.
Independent actual readback audit:
`5a25ee767a9980697f940c895c62c4e34d56bb706ddc3a6c09e5412a8b57d03a`,
[`low-register-actual-diagnostic-audit.md`](2026-10-06-low-register-actual-diagnostic-audit.md).
It reports no must-fix and verifies fixed arrays, clock/support, descriptors and
protected hashes; it does not establish musical transparency or an accepted
new master. The [diagnostic results receipt](2026-10-05-low-register-actual-diagnostic-results.md)
retains the mixture/fan/guitar claim distinctions.

Exporter: ignored
`artifacts/experiments/low-register-actual-diagnostic/export-audition-20261006T0128.py`,
SHA256 `2557f9994aa0b6cd20286f728555d9f45290899902aad7de6dff0deb9aacc775`.
Successful conversion used the existing locked interpreter and explicit FFmpeg
8.1.2 tool, two threads and a 120-second deadline. Tool SHA256:
`3a315207e67de78e48c3bbb6b3346663f6a27c02e034d65ac72a12fee74c534a`.
The operation completed in **7.87186925 seconds**. One initial Python HTML-
template syntax error occurred before any conversion or output directory was
created; it was fixed and syntax compilation passed before the successful run.
This did not rerun the diagnostic DSP or alter a source artifact.

```sh
.venv/bin/python artifacts/experiments/low-register-actual-diagnostic/export-audition-20261006T0128.py \
  --output artifacts/experiments/low-register-actual-diagnostic/audition-20261006T0128 \
  --ffmpeg /nix/store/mv3x2v2pr6pwvwj7cdyh8nci2q1wpnjq-ffmpeg-headless-8.1.2-bin/bin/ffmpeg
```

Only source `[882000,1323000)` / `[20,30)` seconds became a numeric original
PCM excerpt; the four processed/four residue arrays were loaded exactly as
already saved/hash-bound. No capture span or observed outside context was read
numerically, and no denoiser, model, filter, normalization, EQ or compressor was
rerun. Original/protected file bytes were stream-hashed separately for identity.
FFmpeg converted float64 PCM to `pcm_s24le` WAV at the same 44.1 kHz mono rate
with dither explicitly disabled. Quantization is the only audio-copy conversion;
there is no resampling, gain alignment or residue boost.

## Outputs and numeric validation

New directory:
`artifacts/experiments/low-register-actual-diagnostic/audition-20261006T0128`.
It contains nine native PCM24 WAVs, static `index.html`, and `audition.json`:

- `original.wav`, original recorded mixture only;
- `p0-n0.5-processed.wav` / `p0-n0.5-residue.wav`;
- `p0-n1-processed.wav` / `p0-n1-residue.wav`;
- `p0.5-n0.5-processed.wav` / `p0.5-n0.5-residue.wav`;
- `p0.5-n1-processed.wav` / `p0.5-n1-residue.wav`.

Each WAV is one channel, 44,100 Hz, 24-bit PCM, exactly 441,000 samples/10
seconds. Local sample zero maps to original decoded source sample 882000 and
media time 20 seconds; end maps to sample 1323000/media time 30 seconds.
Manual signed-24-bit readback verified native headers/extent, finite values,
unclipped input/output peaks, and conversion against the corresponding exact
input samples. Declared absolute error bound is two PCM24 LSBs:
`2.384185791015625e-7` full scale. Observed maximum over all nine tracks was
`1.1897639911467861e-7`. Maximum input peak was `0.3565244972705841`; no limiter
or clipping repair was invoked. WAV total size is 11,907,918 bytes.

Every track carries its WAV/source-array hash, source origin/extent, gain 1.0,
normalization false, finite peak and measured error in the audition manifest.
Readback verified all nine WAV hashes and native headers. Protected hashes
were checked before/after export and at independent delivery readback: all
seven original/decoded source/current clarity master/denoise/residue/run-manifest/
latest targets match the earlier protected snapshot. Current latest remains
`20261005T232741Z-2b5dc43fd009`. The frozen diagnostic and independent audit
hashes also remain unchanged. Verification is scoped to this copy operation.

| Delivered artifact | SHA256 |
| --- | --- |
| `audition.json` | `1bfd585883b153bf010f25fff0f11a7941641dfe3916285aedc0ee40a32eafdb` |
| `index.html` | `f50a07fc64e9190d6c2660bcd8693c99ff627b347274526043883ee1c9814545` |
| Ignored exporter | `2557f9994aa0b6cd20286f728555d9f45290899902aad7de6dff0deb9aacc775` |

## Listening-page behavior and remaining QA

The static page presents the original followed by all four fixed variants and
their residues in neutral order, with no preferred winner. All nine players
start at unity with a visible shared-volume slider; native volume changes are
propagated across players. Only an explicit play action starts playback, and
starting one player pauses the others. No autoplay, hidden volume matching,
automatic gain adjustment or boosted residue is used. Browser/player volume
is separate from unchanged WAV sample levels.

Responsive CSS presents processed/residue players side by side on wider
screens and stacked below 640 px. The page explains ten-second source 20–30
timing, uncertain approximately 0.186-second processed edges, the supported
source 20.186–29.814-second comparison region, overlapping fan/music ambiguity
and unknown tone acceptance. Residue is labelled all removed changes, including
possible musical content. No recovered stem, note correctness or isolated
fan reduction is claimed.

The existing full marked video is linked, without making a copy or changing
its audio/markers, at relative path
`../../../runs/20261005T232741Z-2b5dc43fd009/marked-preview/marked-video.mov`.
The page states that this full video uses the earlier master and automatic
review markers. HTML parser checks found exactly nine controls without any
autoplay attribute, a shared slider default of 1, and resolving media/download/
manifest/full-video links. The page/manifest hashes match delivery readback.

No local server or browser was started by this lane. **Browser QA is assigned
by root to `repo_patterns` and remains pending**: loading/decoding PCM24 in the target browser,
play/pause/shared-volume interaction, desktop/mobile layout and full-video link
behavior are not established by structural HTML checks. Technical player QA,
actual listening observations, musician acceptance and master/default adoption
remain separate evidence classes; none is silently inferred from these copies.

Root received the listening-page path and hashes for browser-QA delegation.
No new public processing primitive or core report integration is implied.

Process receipt: actor audio_research | target new ignored audition-copy
directory/exporter and owned dated receipt | reason deliver listening access to
independently audited frozen diagnostics | ruling root's explicit new audition
phase / R-HOOK-CONVERGENCE-20261004 / R-N13 | prior_state native diagnostic
arrays only | result nine verified unity-level PCM24 copies and static page;
main master/latest unchanged, browser/listening acceptance still pending.
