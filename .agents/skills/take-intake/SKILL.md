---
name: take-intake
description: Turn a NEW guitar take into its own take family and run the full existing pipeline (FULLER with a reviewed per-take fan interval, phrase timing, marked preview, sharing export) with resume, then build a path-free evidence packet and a TIN-5186 draft; read-only plan first; no verdicts, no default adoption.
---

# Intake a new take

Hook `take_intake` with `operation` `plan` or `packet` (drafted in `program/tool-drafts/take_intake.json`; root admits it); prompt `take-intake`. Worker `scripts/take_intake.py`; operators run `just take-plan`, `just take-run`, `just take-resume` and `just take-packet`. Read [the frozen contract](../../../docs/spec/sprints/TAKE_INTAKE_S3.md) before relying on any output. Authority: the operator ruling of 2026-10-07 ("Second take | New take family plus full pipeline", `docs/agent-notes/2026-10-07-s2-operator-rulings.md`) and repository `AGENTS.md`.

**Intent.** A practice take becomes a shareable restored clip with source-timed phrase and timing review and reproducible evidence. The second take gets a **new** `take_family_id`, so it never shares a family or split with the October 5 take. The orchestrator only sequences existing entrypoints (`run_demo.py`, `flags_triage.py`, `arrangement_reference.py`, `arrangement_markers.py`, `phrase_anchor.py`, `phrase_timing.py`, `marked_video.py`, `marked_compact.py`, `share_export.py`). It adds no DSP, filter, profile or detector.

**Plan first (read-only).** `just take-plan SOURCE` prints the source sha256 and size, an ffprobe summary (including `cfr_vfr_status`), the proposed family id `take-<16 hex>` (a domain-separated hash of the source sha256, the same at any path), the registry files it checked, a corpus row draft with `split: null` (`pending_operator_choice`), the ten ordered steps with exact argv and placeholders, and the inputs only the operator can supply. The plan writes nothing. A small admissibility file under `<state-root>/.scratch` is deleted before the plan exits.

**Knobs (operator inputs, never inferred).**
- `--capture-interval START END` and `--capture-review TEXT` are required. Review the interval per take on the web route `/sources/[id]/capture` or with `just review`. Duration must be 0.1–10 s. The first 5.0 s are setup (guitar and amp sounds, possible mechanical windup) and are never auto-confirmed. Starting earlier needs `--interval-reviewed-includes-setup`, which is recorded as an operator assertion and never as proof that the interval is noise-only.
- `--arrangement REF` is optional. It must bind this source's sha256. `program/demo-arrangement.json` belongs to the first take and is refused. Expected phrase lengths and click totals are intent, not observed counts.
- `--anchor-seconds S --anchor-source TEXT --clicks-per-grid-period 1|2` are optional and need `--arrangement` and `--features extended`. The projection is never adopted.
- `--bpm X` is an approximate operator pulse, not an intended score. `--features base|extended` defaults to base. `--family ID` overrides the derived id.

**Dependencies and refusals.** FFmpeg/FFprobe come from `FFMPEG`/`FFPROBE`. The source must not be a symlink, inside `artifacts/runs`, or a tracked or unignored repository path. A source already registered to a family (for example the October 5 take) refuses `source_already_registered`: it is not a new take. An id that exists with another source refuses `family_collision`. Rerunning a finished intake refuses `intake_exists`; use `--resume` or a new `--family`. The tool draft lists every refusal code.

**Resume.** `just take-resume INTAKE_ID` replays the recorded settings. Passing any setting refuses `resume_settings_conflict`. A live lock refuses `intake_locked`. A still-running worker group refuses `prior_stage_worker_alive`; nothing is ever signalled. A completed stage is skipped only if all its output hashes re-verify. Otherwise that stage and every later one rerun, and their old outputs move to `resume-<n>/displaced/` (never deleted). The demo stage binds exactly one `run_demo` invocation by source sha256 and interval, and resumes it with `run_demo.py --resume`. It never re-renders a bound invocation fresh. The source sha256, size and mtime are checked before and after the run and on every resume.

**Evidence.** `evidence-packet.json` records:
- stage counts (completed out of planned, abstained, failed)
- stage output hashes
- the analyzed signal each analysis declares, marked current or stale
- tool and script versions
- the capture record (review text kept only as its sha256)
- phrase timing as measured signed offsets (median, IQR, count) with `direction_status: withheld_uncalibrated`
- triage denominators
- deliverables marked `exported_unreviewed`
- a static low-register filter-graph guard (no high-pass, notch or sub-60 Hz low-pass)
- claim classes and the fixed unknowns

`tin-5186-message-draft.json` is `draft_not_sent` and carries only the family id and non-media metadata (V6). Root sends it after the operator reviews the packet. Real-take outputs stay in ignored `artifacts/`.

**Research and iteration.** Heavy distortion, the ~32 Hz low string (C1 of C1 F1 Bb1 Eb2 Bb2 Eb3 Ab3 C4 F4), palm mutes, rests, tuplets, tapping, sweeps and legato all move detector attacks. Treat flags and phrase spans as places to listen. Reading the packet:
- **Measured:** hashes, probe fields, loudness and true peak against −18 LUFS and −1.75 dBTP, frame counts, offsets, denominators.
- **Inferred:** detector hypotheses.
- **Needs listening:** restoration quality, fan residue, low-end fullness, whether the interval is noise-only.
- **Operator input required:** split, arrangement reference, latency calibration, at least 10 boundary marks.
- **Not performed:** timing direction, note correctness, missed or extra notes, editor import.

To compare settings, start a new intake with another `--family` or a fresh state root. Never edit a packet by hand. A synthetic end-to-end result shows that the orchestration works. It says nothing about restoration or musical correctness on a real take. Experimental non-improvement is a valid outcome.
