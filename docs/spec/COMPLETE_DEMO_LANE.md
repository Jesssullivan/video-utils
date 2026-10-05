# Complete optional demo orchestration — October 5, 2026

Owner: `media_latency`, exclusive implementation files `scripts/run_demo.py`,
`tests/test_demo.py`, and this specification. Root owns recipes and integration.
Authority: operator-approved ten-hour parallel goal and repository AGENTS.md;
R-HOOK-CONVERGENCE-20261004, R-N11 owned-process checks, R-N13 durable receipts.

Definition of done: retain default `--features base` behavior; explicit
`--features extended` runs clicks, bounded pitch, meter, tonal and recurrence
comparison after base analysis, then evaluates the DAG using only exact artifact
paths returned by successful stages, then markers and report. A validated existing
run can be extended without rerendering or touching source/master media. Dependency
installation and model downloads are never orchestration side effects.

Before coding: inspect primitive worker argument/output contracts, agree exact DAG
selector fields with its owner, and make subprocess output/time limits and own
process-group signalling auditable. Tests must cover order, failed-stage receipts,
existing-run hash rejection before workers, exact artifact forwarding, and bounded
worker execution. Root performs the complete real-recording integration separately.

## Implemented operator contract

`run_demo.py INPUT` retains the base default. `--features extended` opts into the
five optional primitives; `--backend librosa` controls base rhythm/phrase features.
`--analysis-python PATH` chooses an already provisioned interpreter, falling back
to `VIDEO_UTILS_ANALYSIS_PYTHON` and then the current interpreter. Optional packages
are never installed. `--pitch-seconds` bounds pYIN excerpt coverage to 1–30 seconds
(default 20), including the ending according to the pitch tool's own schedule.
`--no-latest` leaves the operator's latest pointer unchanged for fixture runs.

`--existing-run RUN_DIR` replaces positional input. Before workers run, verify the
bounded manifest, original source hash, denoised/master hashes and native sample
rate/channel/sample extent. Verify media identity again after analysis. Existing
exports are reused only through their exact source/output hash receipt; no encoder
runs. New-input rendering uses separate clean/export stages so a delivery failure
retains the known completed master and run receipt while analysis remains possible.

Execution order is media and delivery (new input), rhythm, noise, tone, notes,
phrases, clicks, pitch, meter, tonal context, recurrence comparison, graph, generic
markers, report. Clicks run detection only; the workflow never authorizes template
attenuation. The master receives no optional-stage audio edits. Meter requires the
current rhythm result. Tonal requires current rhythm, phrase and pitch results;
this avoids a primitive's optional read of an older root pitch file after pitch
fails. Recurrence comparison requires current rhythm and phrases. A rhythm/phrase
failure skips graph and markers; a graph failure skips markers. Reports and
per-stage diagnostics remain available. Extended mode returns a nonzero status for
failed/skipped required stages; base mode retains the earlier optional-analysis
failure behavior while exposing partial status. No report or stage completion is
listening acceptance, confirmed notes, or performance correctness.

Only successful current optional stage receipts supply graph arguments:
`--clicks-artifact`, `--pitch-artifact`, `--meter-artifact`, `--tonal-artifact`,
`--comparisons-artifact`. The workflow validates exact run-relative path identity,
regular files, symlink-free components and artifact hashes. No directory timestamp
ranking or newest-file scan occurs. It then requires the graph to verify every
selected receipt and leave all omitted slots `not_selected`; rejected evidence
makes the workflow partial. Unknown meter, tonic, mode and confidence remain in
primitive payloads unchanged.

## Existing-run history and failure durability

Before any existing-run stage mutation, preserve the fixed `HISTORY_ARTIFACTS`
allowlist under `demo-history/<content hash>/`. This includes previous base
analysis JSON/CSV, pitch, legacy root tonal result, recurrence comparison, graph,
flags, report, markers, demo receipt and immutable manifest/export metadata.
Unique click/meter/tonal experiment directories remain in place and are selected
by explicit receipt. Media and the instrument registry are never copied, retired
or modified. Snapshot bounds are 20 MB per file, 40 MB total JSON and 64 MB total
content. Symlinks, bound failures and changes during capture stop before analysis
mutation. Existing snapshots are immutable and hash checked.

Before replacing a known mutable tool result, retire its current path only after
its bytes match the saved snapshot. Failed current tools therefore cannot leave a
previous root result masquerading as their new output. Graph's own independent
`graph-history` archive remains compatible: its presentation snapshot is separate
from this pre-analysis preservation of upstream bytes. Snapshot receipts explicitly
say `prior_artifact_snapshot_not_revalidated`.

Invocation receipts checkpoint before and after each stage under the exact run's
`demo-invocations/<invocation id>/receipt.json`, with `demo.json` as the current
receipt and a bootstrap pointer in `artifacts/demo-invocations/`. Failed analysis
retains media and earlier stage receipts. Original source and master identities
are rechecked before the workflow updates the latest pointer.

Worker stdout and stderr are actively bounded to 2 MiB each, rather than captured
without a memory limit. Each worker has a bounded deadline and a new recorded
process session/group. Deadline or output overflow inspects the actual process or
still-live owned descendant group before signalling, then records the R-N11 actor,
target ownership, reason, authority, prior state and result in the stage receipt.
Numerical worker threads are bounded to two. JSON must be one finite object; source
changes during invocation reject the result. No host daemon or external session is
managed.

## Verification

Fifteen tests passed, including execution order, exact older-looking returned
artifacts instead of a newer-looking decoy, explicit interpreter/pitch budget,
failed-stage receipts, omitted stale pitch, graph rejection, preserved prior
analysis/pitch bytes, snapshot caps and symlinks, immutable media, existing delivery
reuse and an unchanged latest pointer. Process fixtures independently verify finite
JSON, active output limiting, and termination of a recorded descendant group even
when its parent has already exited.

The actual eight-second MOV fixture completed all fifteen stages with every
optional graph slot `verified`; source/master hashes remained bound. Evidence:
`artifacts/complete-demo-mov-fixture.json` and its exact run receipt. A first WAV
fixture exposed the existing media manifest's absent stream start; its failed
rhythm/click stages were retained, dependent stages skipped, and it returned
nonzero. Root separately repaired decoded-frame origin recording. A fresh WAV
fixture then completed all fifteen stages with all five optional slots verified:
`artifacts/complete-demo-wav-fixture.json`. These fixtures are synthetic execution
and provenance evidence, not musician or listening acceptance. Root owns the
subsequent complete actual-take run and publication.

The WAV fixture was subsequently extended with the real existing-run workflow.
All five selected graph slots again verified, media was not rerendered, and the
750,166-byte prior artifact set was preserved at
`demo-history/c70e1f4ab8c5071898908c1852bb11841a41b7c3657fcd87e39dcbec01fb1c6f`.
The workflow rechecked original source and native PCM hashes/extents and left the
latest pointer unchanged. Receipt: `artifacts/complete-demo-existing-fixture.json`.
Exact fixture runs are `20261005T221316Z-bab23ca2075a` (MOV) and
`20261005T221616Z-9548ce3fe0fb` (WAV and its archived reextension). The first MOV
smoke used the old latest-update default; root must restore the explicit operator
actual-take pointer during integration. Later WAV/reextension runs used
`--no-latest` and did not change it.
