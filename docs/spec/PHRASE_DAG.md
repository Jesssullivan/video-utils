# Musical phrase DAG and review markers

The target instrument is a distorted, down-tuned nine-string guitar with intended
fundamentals near 32 Hz. “Phase mistakes” means musical phrase alignment here.
The pilot does not transcribe notes, infer physical signal phase, or decide that
a quiet/low-frequency component is unwanted noise.

## Implemented artifact graph

`program/dags/guitar-take.json` declares denoise → click/BPM → experimental
notes/nullable tonic and mode → phrase/recurrence proposals → review flags →
report. Tone measurement branches from denoise; raw click analysis can remain a
separate diagnostic. `scripts/dag.py` records an existing run's provenance graph;
it is not a scheduler or an agent that automatically changes processing knobs.
Tool intents map to the agent tools and their skills. Knob selection remains an
explicit bounded comparison, with receipts and listening acceptance separate.

```sh
python3 scripts/dag.py artifacts/runs/RUN_ID
python3 scripts/dag.py artifacts/runs/RUN_ID --reference /local/approved-rhythm.json
python3 scripts/markers.py artifacts/runs/RUN_ID
```

`dag.json` stores dependency IDs, original source identity, input/artifact hashes,
settings hashes, the registry hash and reference hash. It accepts worker identity
only for the original source or a hash-verified `denoised.wav`/`cleaned.wav` named
in `manifest.json`. Original-source results are `preliminary_raw_source`;
verified restored inputs are `post_denoise`; unrelated or modified restored
artifacts are rejected as context. Masters keep source rate/channels; mono
analysis copies do not replace masters or establish recovered guitar stems.
An existing report's hash is a prior snapshot in its stage row, rather than a
validated graph input: the report consumes this graph and rewriting it must not
invalidate its own inputs through a hash cycle.

`flags.json` stores nullable tonal context and source-time review spans. Without
an approved reference it exposes uncertain boundary/recurrence candidates and
unresolved tempo context. Envelope resemblance is not a repeated riff. Current
mixture pitch observations do not establish tonic, mode or intended notes.

## Approved reference interface, version 1

An operator may supply this JSON, with real values confirmed against the take:

```json
{
  "schema_version": 1,
  "approved": true,
  "source_sha256": "original recording SHA-256, recommended",
  "bpm": 120,
  "subdivision": 1,
  "expected_onsets_seconds": [1.0, 1.5, 2.0, 3.0],
  "phrase_spans": [{"start_seconds": 1.0, "end_seconds": 3.5, "name": "riff A"}],
  "tolerance_seconds": 0.03,
  "match_window_seconds": 0.12,
  "onset_latency_seconds": 0.0,
  "context": {"tuning": null, "tonic": null, "mode": null}
}
```

Expected onsets and phrase spans use seconds from the first decoded **original
audio sample**, not container/video zero. Chords use one expected attack. Annotate
rests, triplets, grace notes and syncopation explicitly; a BPM/subdivision never
generates an intended rhythm automatically. BPM must be 20–400, subdivision an
integer 1–64, and expected onsets nonnegative and strictly increasing. Approved
references need at least one onset; there are at most 20,000 onsets and 1,000
phrase spans. A supplied source hash must match the original recording.

Tolerance defaults to 30 ms. The match window defaults to the lesser of 200 ms
and half the declared subdivision period; tolerance cannot exceed that window.
`onset_latency_seconds` is an explicit signed correction subtracted from observed
times. Zero explicitly means no correction was requested; it is not evidence of
a calibrated recorder/detector. When the field is absent/null, signed offsets
remain uncalibrated and are not labeled early/late. Keep a real calibration receipt
when making musician-facing timing claims.

The comparator selects only broadband attack candidates, deduplicates identical
timestamps, and maximizes monotonic one-to-one match count before minimizing total
absolute offset. Matches are bounded by the configured window and 200,000 candidate
edges. An observed attack cannot satisfy two expected attacks. Unmatched attacks
outside the explicitly annotated onset range are ignored; within it they remain
review candidates. Missing detections can be legato, merged attacks, masked guitar
or detector failures. Unmatched detections can be clicks or noise. These are **not
confirmed missed or extra notes**.

Phrase flags compare first/last expected attacks inside each approved span. They
can suggest a start/alignment problem or an undetected boundary attack. A last
attack is not the phrase's release/sustain end; phrase-end audio detection and
repeated-riff semantic validation remain future work. Reference context is declared
intent, not inferred tonal evidence.

## Marker exchange and acceptance

`scripts/markers.py` atomically writes `markers.json` and `markers.csv` with columns
`source_time_seconds,end_seconds,name,confidence,status,evidence`. CSV evidence is
quoted JSON. Times add the original audio-stream start to audio-relative event
times; negative stream starts are supported. The exporter verifies source identity
and, when `dag.json` exists, the flags artifact hash. Each file is replaced atomically;
the pair is not a transactional database write.

This is a generic seconds-based review format. Final Cut Pro and DaVinci Resolve
native import, frame rounding, editor clip origins, variable-frame-rate conforming
and graphical overlays need separate adapters and host validation. No successful
native import is implied. Markers remain `needs_review`; exporting them does not
confirm musical mistakes.

Acceptance checks cover missing/early/late observed attacks, explicit capture offset,
uncalibrated abstention, unapproved references, source mismatch/tampering, chord
deduplication, dense one-to-one matching, explicit phrase spans, original stream
offsets and CSV quoting. The actual recording has no approved intended-rhythm
reference yet; its flags are musical review suggestions only.
