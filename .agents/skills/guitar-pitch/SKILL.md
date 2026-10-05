---
name: guitar-pitch
description: Analyze bounded excerpts of nine-string guitar with dual-resolution pYIN pitch candidates, preserving low-register, octave, voicing and string ambiguity without intended-note grading.
---

# Inspect tuning-aware pitch candidates

**Hook:** MCP tool `pitch` and MCP prompt `guitar-pitch`; inspect `tools/list` for publication status and the current schema. The locked-librosa worker is implemented; legacy `notes` remains a separate sparse stdlib tool.

## Use and controls

Use `pitch` with `input`, `run_dir`, `max_analysis_seconds` (1–30, default 20), optional `start_seconds` (nonnegative decoded-input audio-relative seconds) and the bounded tool timeout. Without a start, the budget is distributed across the clip in excerpts of at most five seconds, including the ending; an explicit start selects a contiguous bounded excerpt. Recipe fallback after registry publication: `just tool-run pitch '{"input":"<input>","run_dir":"<run-dir>","max_analysis_seconds":20}'`. Direct worker: `python scripts/pitch.py "<input>" --run-dir "<run-dir>" --max-analysis-seconds 20 [--start-seconds START]`.

Read [the pitch contract](../../../docs/spec/PITCH_LANE.md), [low-tuning research](../../../docs/research/LOW_TUNING.md) and `program/instrument.json`. Use the explicit locked analysis interpreter; no backend selector, model download or implicit dependency installation exists. Native input is limited to 300 seconds; analysis is separate 16 kHz mono with at most two numerical threads and an isolated pYIN child deadline of 180 seconds.

The worker atomically writes `pitch.json` and returns a small JSON summary/artifact pointer. Inspect the summary first, then bounded relevant frame/span records from the full artifact; do not paste a multi-megabyte frame array into agent context. Retain source/derivative and tuning-registry hashes, versions, frame settings, runtime, coverage spans/fraction and source-time window bounds.

## Nine-string evidence and resolution

Fixed low-register analysis uses 256 ms frames over 28–500 Hz; the high-register branch uses 64 ms frames over 200–2000 Hz. Both use 16 ms hops. Low fundamentals near 32 Hz need multiple cycles, while fast sweeps/tapping/legato need shorter windows. A 16 ms hop does not imply 16 ms low-pitch precision: compare branch/window uncertainty, excerpt edges and unvoiced frames. Out-of-range content remains unsupported.

The operator's constant pitch classes are C F Bb Eb Bb Eb Ab C F, lowest to highest. Registry octaves C1 F1 Bb1 Eb2 Bb2 Eb3 Ab3 C4 F4 are inferred; A4=440 frequencies are theoretical. Preserve the supplied Eb2→Bb2 interval. Candidate notes/cents, harmonic/octave alternatives and hypothetical semitones above compatible open strings do not identify a unique played string/fret or measured tuning.

pYIN voicing probability is algorithm evidence, not calibrated musical correctness in a distorted mixture. Chords, strong harmonics, missing fundamentals, bends, clicks and sustain can yield competing hypotheses. Preserve unvoiced/unknown results and both branch alternatives; never convert each voiced branch frame into a distinct performed note. Tonic/mode, intended notes, polyphonic transcription and wrong-note grading remain unsupported by this tool.

## Comparison and acceptance

Start with distributed coverage to inspect sustained lows and the ending. For a specific rapid passage, propose a focused start/budget comparison and retain prior evidence before a rerun replaces `pitch.json`; record changed coverage and hashes. A higher voiced count is not automatically better. Compare pitch stability, octave alternatives, window smearing and abstention against playback/known fixtures.

**Review scenario:** Strong 64/96 Hz harmonics with a weak near-32 Hz fundamental should retain low-octave ambiguity. A fast legato ending may be useful in the high branch while the low branch smears it. Twenty analyzed seconds from a longer clip cannot be presented as full-take transcription or a count of played notes.

## Agent iteration

Identify the target passage and question, inspect coverage/tuning/context, propose one bounded excerpt change, compare candidates with audio and the documented algorithm limits, and retain source/settings/version/confidence receipts. Research uncertain controls in primary pYIN/YIN sources linked from low-tuning research. Follow [the agent tool contract](../../../docs/spec/AGENT_TOOLS.md); preserve masters and keep frame artifacts/media local and ignored.
