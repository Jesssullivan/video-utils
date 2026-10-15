# Condense and timeline tool contract

Authority: operator decision of 2026-10-15 (Linear TIN-6511), repository
AGENTS.md and R-N13. Drafts: `program/tool-drafts/condense.json`. Skills:
`.agents/skills/edl-timeline/` and `.agents/skills/condense-*/`.

## Tools

| Tool | Worker | Reads | Writes | Admission |
| --- | --- | --- | --- | --- |
| `timeline_validate` | `video-utils timeline validate` | edl.json | nothing | tool 47 |
| `timeline_map` | `video-utils timeline map` | edl.json, queries | nothing | tool 48 |
| `condense_transcribe` | `python3 -m condense transcribe` | recordings, model | work/ | second admission |
| `condense_events` | `python3 -m condense events` | whisper JSON | work/ | second admission |
| `condense_edl` | `python3 -m condense edl` | words, events | work/edl.json | second admission |
| `condense_render` | `python3 -m condense render` | edl.json | work/, out/ | second admission |
| `condense_check` | `python3 -m condense check` | out/, edl.json | report only | second admission |
| `condense_captions` | `python3 -m condense captions` | words, edl.json | out/ | second admission |
| `condense_overlay` | `python3 -m condense overlay` | corrections, parts | out/ | second admission |
| `condense_recover` | `python3 -m condense recover` | two .mov files | one new .mov | second admission |
| `condense_publish` | `python3 -m condense publish` | out/, edl.json | artifacts/condense/ | after C11 |

## Rules every condense tool enforces before a worker starts

- The config is a regular file, not a symlink, at most 4096 characters of path.
- Every clip `file`, the `work` directory and the `out` path in it resolve
  beneath the config's directory. No `..` component and no symlink on the way.
- No output path equals a clip file.
- `condense_recover` refuses an existing output.
- Each call has an outer `timeout_seconds`; each tool call inside it is bounded
  by `CONDENSE_TOOL_TIMEOUT_S` (7200 s).
- Nothing downloads the whisper model. `condense_transcribe` refuses when the
  registered model is absent or its hash differs.

## Shared rules

- Condense tools never read or write `artifacts/runs/`. Their runs carry the
  `edl_v1` timeline mapping (`docs/spec/TIMELINE_CONTRACT.md`).
- Admission appends to `program/tools.json`. The first 46 tools stay frozen
  against the `ADMITTED_46_*` hashes in `tests/test_s3g_tool_admission.py`.
