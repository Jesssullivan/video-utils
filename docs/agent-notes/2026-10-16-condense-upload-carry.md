# Condense upload copies in a run, and admission revision 1 (2026-10-16)

Authority: Linear TIN-6575 and TIN-6574 (S4 milestone "Condense on real talks"); repository AGENTS.md;
R-HOOK-CONVERGENCE-20261004 R-N13. Stacked on PR #29 (TIN-6545). The recordings, the private `talk.toml`, the
work dir, every log and the published run stay on the operator host. This receipt records hashes, counts,
versions and measured numbers only.

## What changed

- `condense/publish.py` (TIN-6575): `talk.upload.mp4` and, beside `talk.corrected.mp4`,
  `talk.corrected.upload.mp4` are carried and hashed when present; `talk.upload.mp4` is required when the config
  sets `[encode] upload`. Before anything is staged, a copy is refused when its video frame count differs from
  the copy whose picture it carries, when its AAC packets (sha256 of `-c copy` packets, not decoded) differ from
  `talk.mp4`'s, when its moov box follows its mdat box, or when its first video packet is not at pts and dts 0
  or it has B-frames. A corrected upload copy without `talk.corrected.mp4` is refused. The manifest's `uploads`
  records per copy `file`, `of`, `video_frames`, `faststart`, `moov_offset`, `mdat_offset`, the video's first
  pts/dts and B-frames, `audio_copied_from`, `audio_packets_sha256`, `audio_first_pts`, `audio_start_pts` and
  `audio_time_base`. The audio's first pts is recorded, not judged.
- `condense/render.py`: `boxes()` reads top-level ISO BMFF box headers (32-bit, 64-bit and to-end sizes);
  `upload_facts()` applies the box, pts and B-frame rules, and `upload()` (render and overlay) runs it after
  writing a copy and prints the moov offset and the audio's first pts.
- `src/run_record.rs` (verify-run `edl_v1`): `uploads` is optional, at most 8 entries, and must describe every
  listed `*.upload.mp4`; `file` and `of` are listed outputs, `video_frames` equals `delivery.video_frames`
  (`upload_invalid`), `faststart` is true with `moov_offset` before `mdat_offset` (`upload_not_faststart`).
  After hashing, it reads each copy's box headers itself (no decode, no subprocess): moov after mdat is
  `upload_not_faststart`; offsets other than the manifest's, a box that overruns the file or no moov/mdat in
  the first 64 boxes is `upload_invalid`. The receipt gains `uploads` (file, of, offsets, status). Identity
  receipts are unchanged; a run with no `uploads` and no upload copy still verifies.
- Admission revision 1 (TIN-6574): descriptors 52, 53, 55 and 57 in `program/tools.json` (and the draft) and
  their four skills restate the upload copies, `work/check.json` (passed / partial / not_measured / failed,
  joined measure, every tried spot, `too_few_spots`, the stale-partial refusal) and what publish records. Only
  `description`, `agent_workflow.identify` and appended `limitations` change.
  `tests/test_s4b_tool_admission.py` keeps the first admission's digests as `ADMITTED_57_REV0_*`, undoes the
  revision from the recorded superseded values (`REVISION_1`) and requires those digests back, so any other
  byte change fails; it pins the revised digests and skill hashes and keeps the superseded skill hashes in a
  comment. The `scripts/tool_api.py` write guard refuses a clip file at either upload copy path (whether or not
  `[encode] upload` is set) or at `work/check.json` / `work/check.partial.json`. The end-to-end admission case
  now renders with `upload = "h264"` through MCP and requires the carried copy verified.
- Docs: `docs/spec/CONDENSE.md` (new "Upload copies in a run"), `docs/spec/TIMELINE_CONTRACT.md`,
  `docs/spec/CONDENSE_TOOL_CONTRACT.md`, `condense/README.md`.

| Pin | Before | After |
| --- | --- | --- |
| tools[:57] sha256 | `965921ff…984318e` | `0464f644801f8106e08a656cd15b11908b322644c1f0210d09d44a5492c4b705` |
| tools[:57] ASCII sha256 | `a434c898…ef004b` | `fdb7c96127737e5fddab23e6313982c04dd50d51cdab0b908db448fa5546d1be` |
| condense-render skill | `77cce736…659c250` | `fb6e3658a99ea65276d5045ed8252ce10e1f45ee5f304ed337de7ffdc05381a4` |
| condense-check skill | `67429e9e…c5c62b0` | `a7f32ecd5f955ea47767de51949527e1880bce83f405215851b96811f506fca4` |
| condense-overlay skill | `9250250b…bb149e` | `f63b32dc2a490b3f015cc5ea397d05bb0cda5935b04457461e2b48b1d5709fb7` |
| condense-publish skill | `1c9e2c14…36497` | `c14b6f702ce12d5f2166f4521ab2855a7315a1f1313c82beba9da39a7734e1a4` |

tools[:48] stays `7489cc74…c884cda`.

## Measured on the synthetic and real copies

FFmpeg 8.1.2. On a synthetic HEVC edit and its H.264 upload copy, the copied audio's first packet is at pts
-1024 (time base 1/48000) with stream `start_pts` 0 in both files; the upload copy's first video packet has pts
0 and dts 0 (the HEVC edit's has dts -1024 at 1/15360); the `-c copy` audio packet sha256 is equal in both.
`condense/tests/test_publish.py` asserts exactly these values on the synthetic talk.

Private v5 rebuild (TIN-6544 edit, 37725 frames), re-published from reflink copies of the TIN-6545 rebase run
with `2026-10-16-condense-upload-carry.sh` (sha256
`e0b28d67e1a0363ed5a434823a9381b1cc52982ce5542fccf4fc44c264581410`, also copied to the s4-parity scripts dir);
nothing was rendered or checked again:

- 5 files published: `check.json`, `edl.json`, `talk.mp4`, `talk.srt`, `talk.upload.mp4`. The four files the
  rebase run also published have its hashes: talk.mp4
  `a0709eb86ccedfbad4f731425cc7e77ec294cf1865cf87be3b7fd4d423c2fb0b`, edl.json
  `767cfcacc3f14e275d0680855ea2e4dcaa47afbf2e415eadf8b8feeadc76d790`, check.json
  `44a9290070ea5daca310097bed0861982a2df3a29b36526807285a070a18a853` (status passed).
- `talk.upload.mp4` `79c1053e33ffc4e3ad9eec442af64f34c66760d6708b30502f0dc3b4d7ace439`, 490280801 bytes: equal
  to the copy the rebase run measured (its `check-upload.json` records the same sha256). moov at byte 32, mdat
  at byte 1088787; 37725 frames; video first pts/dts 0/0, no B-frames; audio first pts -1024, start_pts 0,
  time base 1/48000; audio packets sha256 `0ab82750ad84f2b58fa428e376f070bef2fdb035c1e0668cc2d479b7d100357a`,
  equal to `talk.mp4`'s.
- Publish's own verify-run: verified. Then `verify-run --require-source --timeline edl_v1`: verified, 5 of 5
  outputs, sources verified, upload `talk.upload.mp4` verified at 32 / 1088787, 8317459003 bytes hashed,
  manifest sha256 `e7de5f42fa08d05d8d0797a3f710144309189a50e3d8aead813dd79e96b3e289`. Publish wall 1170 s
  (debug build hashing under host load), whole script 2251 s.

Not established: whether a video site accepts the copy (no upload was made), and listening or picture review
of it. The upload copy's sync and loudness are the rebase run's measures, not new ones.

## Gates

- 2026-10-16, `nix develop .#condense -c just cli condense-lint condense-test`: lint passes, 172 passed.
- `just test-rust`: all pass, including 2 new `tests/cli.rs` cases (positive with 32-bit, 64-bit and to-end
  mdat sizes; 9 refusals plus a changed upload byte).
- `tests/test_s4b_tool_admission.py` in the condense shell, with the s2, s3, s3g, s4a admission tests,
  `test_mcp` and `test_public_tree`: 99 passed, 1 skipped (`VIDEO_UTILS_PRIVATE_TERMS` unset); the
  end-to-end MCP case ran.
- `just check`: 2059 tests, 8 fail locally, all on the known missing-font environment issue
  (`No bounded supported installed font found`) in marked-video, marked-compact, arrangement-markers and the
  marked-video MCP case; none touches this change. Hosted CI is the authority: PR #34 offline, condense, web,
  bazel and site all pass on the first push.

## Files outside the named lane files

`condense/README.md`, `docs/spec/TIMELINE_CONTRACT.md` and `docs/spec/CONDENSE_TOOL_CONTRACT.md` (their upload
and check.json sentences would otherwise be false), `program/tool-drafts/condense.json` (the admission test
requires it to equal the admitted descriptors), and `tests/cli.rs` (verify-run tests).
