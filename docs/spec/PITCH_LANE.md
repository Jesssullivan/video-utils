# Tuning-aware pitch lane: bounded ten-hour implementation

Authority: operator-approved local-first guitar tools and October 5 tuning
statement; repository AGENTS.md; R-HOOK-CONVERGENCE-20261004 / R-N13.
Begin implementation after the first project publication. This lane owns
`scripts/pitch.py`, `tests/test_pitch.py` and the low-tuning research note;
root integrates the tool registry, recipes, pipeline and published receipts.

## Result and evidence boundary

Add a dedicated optional locked-librosa pitch worker for reproducible, tuning-aware
pitch-candidate pilot for the exact operator pitch classes C F Bb Eb Bb Eb Ab C F.
Read `program/instrument.json` unchanged: C1 F1 Bb1 Eb2 Bb2 Eb3 Ab3 C4 F4 and
A4=440 frequencies are inferred/theoretical metadata, not measured tuning.
Preserve the supplied Eb2→Bb2 interval. Output candidate notes/cents, alternate
harmonic/octave possibilities and possible semitone offsets above open strings.
Do not choose a played string, tonic/mode, intended note or performance grade.
No model download, automatic correction or polyphonic-transcription claim.

## Implementation sequence and time budget

1. **Two hours: benchmark and interfaces.** Retain the stdlib snapshot baseline.
   Add `scripts/pitch.py INPUT --run-dir DIR` with no dependency installation.
   After first publication, root routes the notes tool to this new worker when
   its optional backend is selected; the existing feature worker stays intact. Bound media to
   300 seconds and numerical threads to two. Record library versions, source
   hashes, tuning registry hash, detector settings, frame-center timestamps,
   time-window extent and canonical derivative lineage. Benchmark warm/cold
   runtime before selecting the full-recording maximum frame count.
2. **Three hours: dual-resolution candidate extraction.** Use low-register pYIN
   with 4096-sample/256 ms frames, 256-sample hops and a 28–500 Hz search. Use a
   separate 1024-sample/64 ms high-register branch with a 200–2000 Hz search
   and the same 16 ms hop. Record out-of-range notes as unsupported rather than
   guessing a pitch. Keep both hypotheses; recording the long
   low-register window's smearing is mandatory. Compare short-window YIN and
   pYIN where a rapid sequence cannot be resolved by the low-frequency branch.
   Preserve unvoiced/unknown frames. Report algorithm voicing probabilities
   separately from uncalibrated musical confidence.
3. **Two hours: harmonic and tuning mapping.** Assess spectral support near
   candidate fundamental and harmonics, retain octave alternatives, and map
   each supported frequency to nearest equal-tempered note plus signed cents.
   List hypothetical semitone distances from every compatible supplied open
   string without inventing a fret count or selecting a unique string. Label
   every mapping conditional on inferred octaves and theoretical A4=440 tuning.
4. **Two hours: tests and actual take.** Run fixtures below, then the denoised
   actual take at bounded settings. Compare branches on sustained lows and
   the operator-described sweep/tapping/legato ending. Save failures, abstention
   rates and sparse-versus-continuous coverage in the research/run receipt.
5. **One hour: handoff.** Supply root the worker interface and evidence for
   notes/MCP/skill/report integration. Refresh the durable tracker receipt;
   intended-note grading stays a separate reference-enabled lane.

## Acceptance tests

- Clean and tanh-distorted C1 (32.703 Hz), weak/missing fundamental with strong
  C2/C3 harmonics, nearby detuned C1, and low notes followed by rests. Retain
  low-octave alternatives; report measured cents without confusing a harmonic
  for a uniquely identified played note.
- Known single-note sweep across several semitones and a phase-continuous
  legato pitch glide. Verify useful high-register candidates and window-scale
  boundary uncertainty; do not require a broadband onset for every new note.
- Two simultaneous notes, metronome clicks and mixed interference. Preserve
  ambiguity/abstention and never label a chord as validated monophonic truth.
- Exact registry pitch classes and unusual interval; octave evidence remains
  inferred. Candidate string mappings remain nonexclusive.
- Nonzero original media offset, hash-mismatched manifest, silence, short
  recordings and subprocess timeouts. Candidate time extents remain inside
  the decoded recording, with no guessed source-time rebasing.

## Defaults and release decision

Existing stdlib behavior remains available. New notes backend parameters and
runtime limits are fixed and recorded for the first candidate release; root
exposes supported controls through the registry and skill only after successful
benchmarking. If full pYIN exceeds the agreed runtime limit, use explicit
bounded excerpts/frame coverage and report the analyzed spans rather than
silently truncating or claiming full transcription. Release requires passing
fixtures plus an actual rendered analysis artifact; listening and note accuracy
on the actual take remain separate acceptance states.
