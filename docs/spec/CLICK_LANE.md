# Metronome candidate and attenuation experiment

Authority: operator-authorized ten-hour parallel development goal; repository
`AGENTS.md`, R-HOOK-CONVERGENCE-20261004 and R-N11/R-N12/R-N13 apply. This lane
owns `scripts/clicks.py`, `tests/test_clicks.py`, this specification and
`docs/research/CLICK_RESEARCH.md`. Root owns integration and publication.

## Outcome and interface

Detect candidate clicks in the mono recording without equating pick attacks with
metronome identity. Optionally compare a conservative attenuation variant against
the untouched input; never modify the default restored master or original.

```text
python scripts/clicks.py INPUT --run-dir DIR [--bpm BPM]
  [--template-start SECONDS --template-end SECONDS]
  [--attenuate --template-click-only] [--strength 0..0.5]
```

No template means periodic high-frequency transient proposals only. A supplied
single-click template interval must be 5–120 ms and inside decoded audio. The
`--template-click-only` switch records an operator declaration, not machine proof.
Attenuation requires both a template and that declaration; its default strength
is 0.5, capped at 0.5. Detection alone never writes an audio derivative.

Artifacts go to a new immutable `DIR/clicks/<run-id>/`: `clicks.json` and
`click-events.csv`, plus `click-attenuated.wav` and `click-estimate.wav` only when
attenuation is requested. JSON preserves analyzed source hash/path, original
media lineage when hash-bound by the parent run, settings, library versions,
native PCM extent, source timestamps, candidate measurements and abstentions.
The estimate is a mono-mixture component proposal, never a recovered stem.

## Algorithm and bounds

- Decode native-rate native-channel float PCM. Limit duration to 600 seconds,
  channels to two, rates to 8–192 kHz and interleaved PCM to 16 million samples.
  FFmpeg commands have bounded threads/timeouts; NumPy/SciPy use one CPU thread.
  Existing analysis dependencies suffice; no models or network operations occur.
- Use a separate 16 kHz mono copy for proposals. A supplied click waveform is
  matched by normalized cross-correlation in an analysis high-frequency band;
  native-sample alignment is refined locally before measuring a candidate.
- Treat correlation, fitted amplitude and residual energy as heuristics. Reject
  low waveform agreement, excessive non-template residual energy, clipped
  windows, implausible gain or isolated matches unsupported by recurring events.
  Coincident pick attacks and legato/sustain can therefore cause abstention.
- Build the subtraction estimate only from accepted fits. Remove its frequency
  components below 1.2 kHz before subtraction, preserving the measured original
  low-frequency DFT bins including approximately 32 Hz. This protects low content
  but deliberately leaves low-frequency click content; filtering can ring and
  does not establish perceptual transparency.
- Render only an experimental float PCM WAV with identical rate, channels and
  sample count. Never normalize, time-stretch, remux, label missed notes or
  advertise accepted guitar articulation from this worker.

## Acceptance and checkpoints

1. Save scope and primary-source research before implementation.
2. Verify isolated known clicks, no-click/tone/noise input and template mismatch.
3. Verify coincident independent guitar attacks abstain, non-overlap attacks
   remain recognizable, and an accepted click plus 32 Hz sustain preserves the
   32 Hz component while reducing high-frequency click energy.
4. Verify default detection emits no WAV, source hashes stay unchanged, extent
   and source timeline survive opt-in output, and declared template identity is
   never promoted to verified identity.
5. Run a bounded actual-take detection receipt. Attenuation and listening remain
   separate checkpoints until a suitable click-only interval is identified.

## Limitations

AGC, AAC artifacts, accent changes and room reflections can change the click
waveform. A guitar attack resembling the template remains an identification
ambiguity, even with a strong fit. A regular grid does not establish musical
meter, intended subdivisions or performance correctness. The fixed thresholds
are conservative experimental defaults requiring measured and listening review.
