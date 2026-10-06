# Source-only editor marker planner implementation

Actor `resolve_marker_sources`; recorded October 6, 2026, approximately
00:36 UTC. Authority: root's explicit operator-authorized worker/test lane;
R-HOOK-CONVERGENCE-20261004 / R-N12 / R-N13. Ownership: new worker, new tests,
owned adapter specification and this dated receipt. Shared/sibling work preserved.

Implemented [worker](../../scripts/editor_marker_plan.py) and
[tests](../../tests/test_editor_marker_plan.py). CLI takes run directory,
run-relative selection JSON and run-relative profile JSON; returns standards
JSON on stdout. It never launches/connects an editor, writes an import file,
reads an editor project, installs anything, changes recipes/MCP or emits an
executable native action. Every profile retains `native_contract_unverified`.
Pure planning retains source timestamps and unconfirmed candidate evidence;
source frame containment, fixture host grids and display origin are separate.

Frozen implementation SHA-256:

| Owned file | SHA-256 |
| --- | --- |
| `scripts/editor_marker_plan.py` | `738e6cd3ee84b0c41ec93bb19987c1b2b7f5ab59e06eea4fedadda5bac4b8e3d` |
| `tests/test_editor_marker_plan.py` | `87fed25463a7d8261de3fe415319e5dd3b908ce5f6aa76a3bce131f675dfe825` |

Validation command:

```text
python3 -m unittest discover -s tests -p test_editor_marker_plan.py -v
```

**16 tests passed**: nonzero/negative origin and parent placement; local trim;
rational 24 versus `24000/1001`, tie rounding and narrow outward ranges;
containing VFR frame distinct from nearest grid; gaps, duplicate PTS and missing
durations; overlapping reported duration unable to bridge later gaps; tails;
missing origins without rate defaults; atomic FCP boundary abstention;
planned/existing-marker collision preservation; Unicode and uncertainty;
stale identity, reversed span, promotion and retiming rejection; action bounds;
real CLI stdout-only input preservation; stale digests; duplicate/nonfinite JSON
and symlink/traversal rejection. Diff whitespace checks passed for both new files.
The sixteenth test preserves exact source JSON numeric text
`0.100000000000000001` as its exact rational, without changing existing canonical
marker-ID serialization. Source time is not silently reduced to binary-float
precision during input parsing.

Read-only actual check: current generic JSON was compared with `markers.build`
against the actual run `artifacts/runs/20261005T232741Z-2b5dc43fd009`, then passed
with its selection and an in-memory profile to `make_plan`. Original/derivative
media was neither decoded nor modified; existing graph file digests were checked
by the established verifier. No new run artifacts were written.

| Actual result | Value |
| --- | --- |
| Generic marker count | 180 |
| Selected / excluded | 24 / 156 |
| State | `calibration_required` / `native_contract_unverified` |
| Proposed actions | 0 |
| Native / preview frame indices | All null |
| Ending recurrence original end | `1207689/8000` s = 150.961125 s |
| Ending disposition | `outside_clip` for explicit clip out 150.885 s |

The six preview-suppressed selected observations remain in the plan: selection
membership comes from the original marker ID list, never the compositor's visible
lines. The ending observation's original start/end is preserved instead of its
clipped centisecond subtitle span. Known complete decoded PTS were previously
hashed in memory but not persisted; three sampled audit frames and a digest do
not constitute a full table. No rate-based reconstruction was attempted.

The timing reviewer received the frozen source/test hashes and owns a separate
audit/new regression file. It found a real defect in initial freeze `4bcf7f85…`:
an original point inside the final VFR frame could round to its exclusive end
while still producing a hypothetical action. The owner corrected this by
inverse-mapping the quantized extent to source coordinates and checking coverage
before every action, including the full FCP END marker frame. Outside coverage
records `fixture_quantization_outside_video_coverage` with no actions; original
times and quantization errors remain. The final frozen hash above includes this
fix and decimal preservation. The independent reviewer accepted that final freeze:
**21/21 combined tests pass**, including five new regressions in its separately
owned `tests/test_editor_marker_timing_audit.py`. It independently reproduced the
180/24/156 actual counts, all six hidden observations, null native frame IDs,
zero actions and the original ending interval. The
[dated audit](2026-10-06-editor-marker-timing-audit.md) and its JSON contain the
review evidence. The owner also reran the combined tests successfully:

```text
python3 -m unittest discover -s tests -p 'test_editor_marker*.py' -v
```

root owns integration, broader checks, `just`/MCP decisions and tracker evidence.
Native SDK verification, calibration, actual editor imports, visible alignment,
listening and confirmed musical intent remain separate pending states.

`resolve_marker_sources | new assigned planner/tests and owned specification
| implement bounded source-only editor planning for next-week work
| operator parallel authorization; R-HOOK-CONVERGENCE-20261004 R-N12/R-N13
| source-time markers/preview exist; native editor contracts unavailable
| worker and 16 fixtures pass; actual 24-row plan honestly abstains from frame
mapping; independent 21-test timing audit passes; root integration pending`
