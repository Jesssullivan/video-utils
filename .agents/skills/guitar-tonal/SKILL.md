---
name: guitar-tonal
description: Compare automatic chroma-based tonal and scale-collection hypotheses in guitar regions, retaining profile disagreement and null tonic/mode without score or correctness grading.
---

# Compare tonal-context hypotheses

**Hook:** MCP tool `tonal` and MCP prompt `guitar-tonal`; inspect `tools/list` for publication status and the current schema. The bounded standard-library worker is implemented and consumes existing analysis; it does not decode audio or install an estimator.

## Use and controls

Use `tonal` with `run_dir`, `max_regions` (1–256, default 128), `max_recurrences` (1–60, default 30) and the supported timeout. Recipe fallback after registry publication: `just tool-run tonal '{"run_dir":"<run-dir>"}'`. Direct worker: `python3 scripts/tonal.py "<run-dir>" [--max-regions 128] [--max-recurrences 30]`.

Read [the tonal contract](../../../docs/spec/TONAL_LANE.md) and [primary research](../../../docs/research/TONAL.md). Required inputs are the manifest and verified post-denoise `analysis.librosa.features.chroma`; discovered phrases and a same-input pitch receipt are optional context. Missing tonal features yields an unavailable receipt, not implicit analysis rerendering. Reject stale/mismatched media, manifest, phrase or tuning identity.

The worker writes a new private immutable `tonal/<UTC>-<random>/tonal.json`; stdout is a bounded summary/artifact pointer. Inspect source/input/artifact/settings/tuning hashes, coverage, region/recurrence counts and source-time spans. Limits include 20 MB per JSON, 36,001 feature frames and 1,800 seconds of analyzed extent. No network, media rewrite, model download or optional Python import occurs.

## Interpretation and abstention

Discover tonal context without an intended score. Compare mean normalized chroma and pitch-presence distributions, two major/minor profile families, all compatible diatonic collection rotations, entropy, margins, local ranking stability and recurrence affinity. Fixed score/abstention thresholds are recorded diagnostics, not exposed knobs or calibrated probabilities.

`tonic` and `mode` remain null in this release. A top correlation is a profile resemblance, not a key verdict. C-major inventory also fits its relative modal rotations; pitch-class inventory cannot choose their tonic. Frequent pitch, stable harmonic texture or open-string tuning must not become a tonic prior. Local ranking changes do not prove modulation.

Distorted nine-string spectra can turn harmonics of a missing near-32 Hz fundamental into a plausible triad. Existing FFT resolution and octave-folded chroma do not uniquely resolve low-register notes. Preserve sparse/power-chord, chromatic/near-uniform, short-context and silence abstentions. The operator's custom tuning remains stated pitch classes with inferred octaves/theoretical frequencies, not detected pitch or intended harmony.

Optional pitch coverage is recorded separately. Do not pool overlapping low/high pYIN branch frames or octave alternatives as independent note votes or manufacture a full-take histogram from distributed excerpts. Scientific pitch spelling, played notes/strings, intended notes and performance correctness remain unverified.

**Review scenario:** Harmonics 2, 3 and 5 of a missing C1 fundamental can resemble three pitch classes without establishing a played triad or key. A near-uniform actual-take distribution should retain unknown tonic/mode despite ranked region hypotheses.

## Agent iteration

Inspect region/recurrence boundaries and provenance, compare supported region budgets or upstream feature evidence, review disagreement/abstentions against playback, and retain all settings/hashes and limitations. Research profile and collection assumptions in the linked primary sources before proposing new controls. Follow [the agent tool contract](../../../docs/spec/AGENT_TOOLS.md); automatic tonal exploration does not gate phrase discovery or authorize wrong-note grading.
