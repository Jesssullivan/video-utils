---
name: phrase-markers
description: Export guitar rhythm and phrase review flags to generic source-time JSON and CSV markers; native Final Cut Pro and DaVinci Resolve import remains unverified.
---

# Export source-time guitar review markers

**Hook:** MCP tool `markers` and MCP prompt `phrase-markers`. Launch with `just mcp` and inspect `tools/list` before calling.

**Capability:** Current generic local JSON/CSV marker exchange from existing flags. Native editor import, frame/timecode conforming, and overlays are not implemented or host-validated.

## Use and controls

Use MCP `markers` with `run_dir` and optional bounded timeout; fallback: `just markers "<run-dir>"`. The direct worker is `python3 scripts/markers.py "<run-dir>"`.

Read [the marker interface and timeline semantics](../../../docs/spec/PHRASE_DAG.md). Run the pipeline skill first when flags need evaluation. Inspect `flags.json` original source identity and, when present, `dag.json` flags hash; reject tampered or mismatched evidence before exporting.

The worker writes `markers.json` and `markers.csv`. Fields are `source_time_seconds`, `end_seconds`, `name`, `confidence`, `status`, and `evidence`; CSV evidence is quoted JSON. Times add the original audio-stream start to audio-relative observations. Preserve negative starts and spans. Each file is atomically replaced, but the pair is not a transactional write.

The exporter checks current nested run-local artifact hashes, selected evidence
bindings and the fixed instrument registry before publishing generic markers.
Stale selections, symlink/path escapes or mismatched flags fail. Verified selected
comparison flags remain hypotheses and are exported once; raw click, pitch,
meter or tonal candidates are not independently appended. Exact duplicate marker
records are deduplicated. Regenerate the graph with explicit receipts when inputs
change; do not relabel stale evidence as current.

Source seconds and frame numbers are different coordinates. This take has variable
picture cadence and a short audio tail after its final decoded video frame. The
generic exporter leaves frame indices null. Future editor adapters require
recorded source/clip/timecode origins and frame quantization; source marker CSV
is not proof of native editor compatibility.

## Guitar-specific interpretation and acceptance

Markers remain `needs_review`. An uncertain 32 Hz guitar event, possible sweep/legato attack, or phrase recurrence candidate must not become a confirmed mistake through export. Preserve candidate status, confidence and supporting evidence rather than strengthening wording in marker names.

Validate source-time alignment against the actual original video and known annotations. Generic seconds are not native editor frame/timecode positions. Future adapters must account for clip origin, actual frame rate, variable-frame-rate conforming and application import behavior before claiming Final Cut Pro or Resolve compatibility.

**Review scenario:** A source with nonzero or negative audio start must place a span at the original source timeline. A quoted phrase name and JSON evidence must survive CSV round-trip. Successful file generation does not demonstrate a successful editor import.

## Agent iteration

Read [the agent tool contract](../../../docs/spec/AGENT_TOOLS.md) for discovery and receipts. Inspect the input and supported tool schema, propose a small change tied to the intended outcome, run a bounded comparison, and retain the candidate only if its evidence supports that outcome. Research uncertain controls in primary documentation; save findings in `docs/research/` and run settings, versions, source hash, confidence and limitations in the run/receipt. Abstain when the tool cannot establish the requested fact. Never download a model or upload media implicitly.
