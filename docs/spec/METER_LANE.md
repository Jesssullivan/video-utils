# Automatic meter hypothesis lane

Owner: `/root/meter_inference`. Authority: operator-authorized ten-hour parallel
goal, October 5, 2026; repository AGENTS.md and R-HOOK-CONVERGENCE-20261004.

Implement an offline, bounded worker consuming the existing hash-bound
`analysis.json` and its MFCC energy proxy. First rank repeated accent groupings
at the fitted pulse and its half/double aliases. Keep pulse level, accent-cycle
length and notated time signature separate. Uniform clicks, sustained legato,
insufficient repeats and conflicting local patterns must return unknown.

Definition of done: meaningful synthetic tests for triple, quadruple and
seven-unit accent cycles; abstention for uniform clicks, continuous legato,
seven equal subdivisions over four pulses, weak/noisy patterns and tampered
provenance; real-take receipt in an immutable meter subdirectory. Preserve
original source timestamps. No model download, media rewrite or host changes.

Research uses official librosa/FMP documentation and the authors' ISMIR 2013
meter/downbeat paper. This lane implements a small transparent heuristic, not
their learned HMM, and does not claim calibrated confidence or native editor
import. MCP/skill integration is handed to their owning lanes after tests.

## Implemented baseline and receipt

`python3 scripts/meter.py --run-dir RUN_DIR` reads the run-local analyzed media
identity, analysis and manifest. It checks derivative hashes, original-source
identity, manifest lineage, source-time origin and no-stretch mapping. It writes
an exclusive timestamped `RUN_DIR/meter/TIMESTAMP/meter.json`; the main analysis,
report and flag artifacts are not overwritten. Stdlib-only runs without existing
MFCC features return an explicit missing-evidence unknown.

Synthetic acceptance: 12 tests pass, including distinct primitive 3-, 4- and
7-pulse accent cycles, their half/double aliases, no false meter from uniform
clicks or seven equal subdivisions, random/ramp abstention, local cycle changes,
finite bounds, immutable source bytes, media/lineage/source-time tampering.

Actual take receipt at 2026-10-05 21:30 UTC:
`artifacts/runs/20261005T211103Z-c6d0bac2fcd2/meter/20261005T213037470321Z/meter.json`.
SHA256 `67e9acb38fb983429f1d343453c22fa98c2570289c18ce3d40cada995029df21`.
Result: unknown notation and accent cycle at 177.601813, 88.800907 and 44.400453
candidate pulse BPMs. The supplied approximately 178 BPM remains operator
context. Strongest fitted-cycle explained variance is below 0.005; four local
windows also abstain. This is useful evidence of the energy-proxy limitation,
not evidence that the performance lacks a meter.

Next bounded increment: compare low-band/high-band onset accents and existing
phrase recurrence at local windows. Preserve this abstaining baseline as a
control; do not lower thresholds merely to produce a time-signature label. A
7/8 label and a 2+2+3 additive partition need stronger independent evidence;
the current worker deliberately emits nullable additive grouping and notation.
