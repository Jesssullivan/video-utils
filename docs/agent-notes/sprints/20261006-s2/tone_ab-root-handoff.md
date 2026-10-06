# tone_ab root registration handoff (2026-10-06)

`tone_ab | lane-owned drafts | root admission requested, nothing root-owned edited | R-N13 (R-HOOK-CONVERGENCE-20261004; TIN-3692 comment 98cf680c-7299-4949-bfb2-60079053ad43) | no default/profile/master adoption`

Sprint 20261006-s2, Linear TIN-5601. The contract is `docs/spec/sprints/TONE_S2.md`
(frozen at 9bc259d). The lane edited no root-owned file. Root should apply the
following on admission.

## 1. `program/tools.json`

Append the exact object in `tone_ab-tool-descriptor.json` (this folder; equal to
`python3 scripts/tone_ab.py describe`, asserted by
`test_descriptor_draft_closed_schema`) as the next entry after `corpus_eval_s2`.
Keep `json.dumps(..., indent=2) + "\n"` formatting. The closed input schema has
`run_dir`, `candidate_run_dir`, `common_region_start`, `common_region_end` and
`timeout_seconds` (1–1800, default 1200), with `additionalProperties: false`.

## 2. `scripts/tool_api.py`

Add `tone_ab` to the S2 exact-path set:

```python
S2_EXACT_PATH_FIELDS = {'annotation_markers': ('run_dir', 'output_dir'),
                        'flags_triage': ('run_dir', 'output'),
                        'corpus_eval_s2': ('manifest', 'local_root', 'proposals', 'output'),
                        'tone_ab': ('run_dir', 'candidate_run_dir')}
```

Add this worker branch in `worker_command`, next to `flags_triage`:

```python
    if name == 'tone_ab':
        directory = s2_input_directory(args['run_dir'], ('manifest.json',))
        command = head + [str(ROOT / 'scripts/tone_ab.py'), 'run', '--run-dir', str(directory),
                          '--common-region-start', repr(float(args['common_region_start'])),
                          '--common-region-end', repr(float(args['common_region_end'])),
                          '--timeout-seconds', str(args.get('timeout_seconds', 1200))]
        if 'candidate_run_dir' in args:
            candidate = s2_input_directory(args['candidate_run_dir'], ('manifest.json',))
            command += ['--candidate-run-dir', str(candidate)]
        return command
```

- **No output field.** The worker writes only a fresh
  `ROOT/artifacts/s2/tone_ab/<run_id>-<UTC>/` (inside `S2_OUTPUT_ROOT`). It
  refuses any output inside a run dir or `artifacts/runs/*`.
- **Stdout.** It is a compact JSON summary of about 1 KB, well under
  `MAX_WORKER_OUTPUT`.
- **Refusals.** These exit 2 with `{"status":"refused_or_failed","code":...}` on
  stderr.
- **Deadline.** The worker's FFmpeg work stops `min(10 s, 5%)` before
  `timeout_seconds`. A deadline overrun therefore leaves `<output>.failed/tone-ab.failed.json`
  before tool_api's process-group kill fires.

## 3. `just/workflow.just`

```just
# Level-matched stage tone A/B with one unreviewed low-shelf trial; never adopts a master.
tone-ab run_dir start end timeout="1200":
    python3 scripts/tone_ab.py run --run-dir {{quote(run_dir)}} --common-region-start {{quote(start)}} --common-region-end {{quote(end)}} --timeout-seconds {{quote(timeout)}}
```

## 4. Tool-count assertions (36 → 37)

- `tests/test_s2_tool_admission.py`, lines 58 and 343: `len(tools)` 36 → 37.
  Either add `'tone_ab': ('guitar-tone-ab', False, False, {'run_dir', 'common_region_start', 'common_region_end'}, 1800)`
  to `NEW` (prompt, readOnlyHint, idempotentHint, required set, timeout
  maximum), or admit tone_ab in a separate S2 group-C admission test and slice
  `tools[32:36]`.
- `tests/test_s1_tool_admission.py:27` and `tests/test_share_export_tool.py:73`:
  36 → 37.
- The skill `.agents/skills/guitar-tone-ab/SKILL.md` is lane-owned and already
  present, so the MCP prompt `guitar-tone-ab` reads it back unchanged.

## Not requested

- No `program/models.json` change.
- No `program/linear.json` change. Root records the TIN-5601 evidence.
- No `docs/spec/PROJECT.md` change.
- No adoption of the trial shelf, the 100 Hz EQ floor or any master.
  `eq_floor_change_proposed.decision` stays `root_and_operator_review_required`.
