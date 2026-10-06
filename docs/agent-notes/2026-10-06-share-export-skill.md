# Sharing-export skill lane

Owner `/root/tool_skills`; worker owner `/root/rhythm_analysis`; hook owner
`/root/tool_hooks`. Authority: root's explicit new tool30 skill assignment under
the operator's compressed sharing-export request and repository R-N13 doctrine.
Own only new `media-share-export/SKILL.md` and this receipt. The original29 skill
files, API/catalog, recipes, masters and media are outside this lane's edits.

## Definition of done before skill implementation

- Coordinate the fixed worker CLI, supported source/output path bounds, encoder
  choices, height/quality/audio controls, defaults, byte limits and deadlines.
- Explain fresh derivative output, aspect/VFR/source-clock preservation and
  lossy quality limits; copy mode does not resize or imply AAC audio copying.
- Distinguish measured output size/hash/timing/peak checks from minimal possible
  size, listening quality, master acceptance, frame/audio bit identity or upload.
- Guide bounded iteration only through supported knobs and meaningful receipts;
  no arbitrary filter/command/runtime, model, implicit installation or overwrite.
- Validate the new skill and obtain independent forward review against the
  frozen implemented worker/contract. After local catalog30 admission, validate
  all30 bundles and exact initialized MCP prompts using locked Python and
  file-backed protocol I/O. No media/model/tool execution in this lane.

Current proposal: tool `share_export`, skill/prompt `media-share-export`;
required source/output; even height240–1080/default720, CRF18–32/default26,
audio64–192kbps/default96, codecHEVC/H264/copy and bounded timeout. Exact codec/
deadline defaults, path and size semantics await worker/hook confirmation.
Source not yet present on first readback; no tool30 availability is claimed.

## Coordinated worker contract and draft

The owner confirms fixed CLI `python3 scripts/share_export.py SOURCE OUTPUT`
with optional height/CRF/audio-kbps/codec/timeout flags. Codec defaults HEVC;
timeout30–900/default900 passes unchanged through the hook, and the worker
internally reserves ten seconds, operation20–890, exceptional cleanup at most
five seconds plus reporting margin. The earlier wrapper-minus-five proposal is
superseded; there is no doubled budget subtraction or extra cleanup knob.

Output is a fresh local `.mp4` plus fresh `.mp4.receipt.json`, source<=3GiB/
300seconds. Copy mode means video packet copy without resize/CRF and requires
input height already within requested height and MP4-compatible video. AAC is
still a lossy sharing conversion retaining rate/channels, not copied source PCM.
The worker owner proposes actual byte/hash/native-clock/packet checks and at
most two audio-only output-peak attempts toward−1.5dBTP, encoding video once.
Exact diagnostic/recovery schema and source qualification remain pending.

The source skill draft exists and passes the bundled quick validator and
whitespace check. No prior29 skill changes, worker/media/model execution, host
installation, master overwrite or catalog admission occurs in this lane.
Independent forward review and all30 actual prompt proof follow frozen source/
typed integration. Intended sharing quality is not inferred from source validity.

Initial read-only forward review identifies copy codec/input restrictions and
path-scope clarification. The owner locks copy to H.264/HEVC within requested
height, square pixels and no video stream side-data. Direct CLI rejects leaf
symlinks and normalizes ancestor paths. Hook preflight is intentionally narrower:
original traversal/symlink components reject before resolution, so canonical
paths are needed for aliases such as macOS `/tmp`. The draft skill now states
these distinctions; no blanket direct-CLI rejection is claimed. Packet timeline
checks and AAC sample/padding allowances remain separate from waveform identity.

Before source freeze, root revises defaults to H.264 veryfast/CRF27; HEVC remains
opt-in with `hvc1`/`yuv420p`. Height720/AAC96/total900 and closed bounds remain
unchanged. Root/owner cites two actual HEVC500-second timeouts as empirical
motivation; these are not a universal codec-speed claim. The skill table,
codec guidance and direct example now match the revised defaults. Earlier
HEVC26-default proposal above is historical, not the current contract.

## Final source, review and initialized prompt qualification

Frozen worker SHA256 readback:
`6894315f90cb8cbfb5ecd1cf219ac0d70f65a5da45fc0282fc1e63d2d5175d8c`.
Worker contract SHA256:
`fad514be30d59a1e3e1a206ca19c859ab6e4aa5a734f5f67fdf4c0120b3fa55d`.
The owner reports forty-two checks passing in 13.665 seconds, including generated
two-second VFR H.264, opt-in HEVC and copy fixtures. Generated native-audio proof
covers mono/stereo, not all permitted one-to-eight-channel inputs or receiving
players. Independent skill forward review against this exact source finds no
remaining behavioral gap. It performs no edits or worker/media calls.

The hook owner freezes catalog30/API integration after eight final hook tests
passing in 5.309 seconds and two compatibility checks in 0.467 seconds. Source
skill wording now states experimental local integration; this is not remote
publication, actual-take quality or listening/master acceptance. Diagnostic
projection explicitly reports omissions while retaining full failure receipts;
transport success does not convert domain failures into successful exports.

Final source skill SHA256:
`01930c8aeb4227e6dde2d310fc17dcf4e3b1544916a56b78b5a2113956005ae1`.
Ordered catalog skill digest:
`44a2500cf7aad1e88702087563a065559c5a63141d82e035031f310f7e05ad60`.
The [durable validation receipt](2026-10-06-share-export-skill-validation.json)
records all30 bundled validators and local links passing, actual initialized MCP
returning every source skill exactly, empty stderr, zero tool calls, locked Python
3.14.6 and final registry `db8dc65d…` identity. Protocol I/O uses owned temporary
files rather than pipes. No media or model work occurs in this proof.

All prior29 skills remain untouched in this lane. Source, API/catalog, recipes,
actual sharing exports, publication and operator acceptance remain with their
respective owners; this lane creates only the new skill and durable receipts.
