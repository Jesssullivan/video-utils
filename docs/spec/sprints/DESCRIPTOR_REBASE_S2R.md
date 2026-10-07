# S2R descriptor_rebase: phrase_timing descriptor wording and report_bundle skill re-pin

Lane `descriptor_rebase`, sprint 20261007-s2r, Linear TIN-5492. Branch
`sprint/20261007-s2r/descriptor_rebase`, base `7d0e11e`. Authority: operator
interview rulings of 2026-10-07 recorded in
`docs/agent-notes/2026-10-07-s2-operator-rulings.md` (rows "phrase_timing
descriptor: rebase the freeze and fix the wording" and "report_bundle skill
text: update the wording and re-pin"), repository AGENTS.md, and
R-HOOK-CONVERGENCE-20261004 (R-N11/R-N12/R-N13). This closes S2 follow-ups 7
and 8 in [S2_FOLLOWUPS](S2_FOLLOWUPS.md) once root merges the lane.

This file is the Phase 1 contract freeze. No numerics ran before this commit.
The only computation was SHA-256 hashing of the registry and skill files at the
base, recorded below as the "before" state.

## Question and scope

The `phrase_timing` descriptor (`program/tools.json` `tools[37]`) still says it
shows "whether each phrase tends ahead of or behind the recorded click". Since
`scripts/phrase_timing.py` schema 2 (root_admission_d), the worker withholds
direction on real takes (`direction: null`, `direction_status:
withheld_uncalibrated`). It reports direction only for generated known-offset
fixtures (`run_kind: synthetic_fixture`). The descriptor wording is therefore
stronger than the worker's behaviour. The `tools[:38]` freeze kept the old text.
The `report_bundle` skill still says "once admitted by root", although the tool
was admitted as tool 40 by root_admission_e.

In scope:

1. Change only the `description`, `intent` and `limitations` strings of the
   `phrase_timing` descriptor. Name, title, `inputSchema`, `skill`,
   `implementation_status`, `evidence_kind`, `annotations`, `dependencies` and
   `agent_workflow` stay byte-identical. The argv that `tool_api.worker_command`
   builds stays the same, because `scripts/tool_api.py` and
   `scripts/phrase_timing.py` are not touched.
2. Rebase the freeze in `tests/test_s2_tool_admission.py`. Add a new first-37
   freeze that proves `tools[:37]` is byte-identical. Update the first-38 and
   first-39 freezes and add a first-40 freeze. Each updated constant gets a
   comment that cites the 2026-10-07 operator ruling and keeps the superseded
   value.
3. Change `.agents/skills/guitar-report-bundle/SKILL.md` from "(once admitted
   by root)" to admitted wording, then re-pin `REPORT_BUNDLE_SKILL_SHA256`.
4. Align `.agents/skills/guitar-phrase-timing/SKILL.md` with the new descriptor
   wording: median/IQR/count, and direction only for generated known-offset
   fixtures or with an operator calibration. The skill has no hash pin.
5. Write the receipt
   `docs/agent-notes/sprints/20261007-s2r/descriptor_rebase-receipt.json` with
   the old and new hashes and the reason.

Out of scope: any change to `phrase_timing` behaviour, its schema version, its
argv or its output fields. Also out of scope: adding a calibration input, which
is S2 follow-up 3 and stays open; any other descriptor; the `tools[:30]` and
`tools[:32]` freezes; and all root-owned files. No media or numerics run in any
phase. Nothing here supports a timing, ahead/behind, rush/drag, note or
missed-note claim about the real take.

## Owned files

| File | Role in this lane |
| --- | --- |
| `program/tools.json` | `tools[37]` description/intent/limitations only. This file is normally root-owned; the lane rules assign it to this lane for that text. Written as `json.dumps(obj, indent=2) + '\n'` (ASCII-escaped) so the existing serializer round-trip assertion still holds. |
| `tests/test_s2_tool_admission.py` | Freeze rebase, first-37 proof, phrase_timing invariance and consistency tests, report_bundle re-pin |
| `tests/test_s1_tool_admission.py` | Read-only for this lane; its first-30 freeze must pass unchanged |
| `tests/test_sprint1_audit.py` | Read-only for this lane; its first-30 freeze must pass unchanged |
| `tests/test_tool_contracts.py` | Read-only unless a wording pin there breaks (none expected) |
| `.agents/skills/guitar-phrase-timing/SKILL.md` | Wording alignment |
| `.agents/skills/guitar-report-bundle/SKILL.md` | Admitted wording |
| `docs/spec/sprints/DESCRIPTOR_REBASE_S2R.md` | This contract |
| `docs/agent-notes/sprints/20261007-s2r/descriptor_rebase-*.json` | Receipt(s) |

Root-owned files (`scripts/tool_api.py`, `scripts/mcp_server.py`,
`docs/spec/PROJECT.md`, `program/linear.json`, `just/workflow.just`, and
others) are not edited. The lane expects to need no root-owned change. Root may
mark S2 follow-ups 7 and 8 closed in `S2_FOLLOWUPS.md`/`PROJECT.md` at merge;
that text goes in `root_owned_changes_requested`.

## Base state (measured at 7d0e11e, before any edit)

Serializer A is `json.dumps(tools[:n], sort_keys=True, separators=(',', ':'),
ensure_ascii=False)`. Serializer B is the same with `ensure_ascii=True`. Both
are hashed as UTF-8 SHA-256.

| Prefix | A (ensure_ascii False) | B (ensure_ascii True) | After the lane |
| --- | --- | --- | --- |
| `tools[:30]` | `85fa376c…3a06c7` | `c13b2f89…ca64aa` | unchanged (asserted by test_s1/test_sprint1_audit) |
| `tools[:32]` | `932d3e26…8e8863` | `358ce0ae…d313bb` | unchanged |
| `tools[:36]` | `82bdb747…7073ba` | `51dd154f…749d31` | unchanged |
| `tools[:37]` | `72ed9aadd9ce065e93b47d6d00b22782d2b3a3ba45bc36a0508921f59374a7c3` | `71977d3cace1baa00044925fb9da3e973d5d0c53830302c9050dee2e66271d21` | unchanged; new constants `FROZEN_37_*` |
| `tools[:38]` | `4005da2b6960de2b973078b272b678e9b995a8bb755888960944cfc8e2e187c5` | `f079cffc30d6c2b19a6dab746fe76915642fef8a77bf3d9add4899a78f3eac54` | rebased |
| `tools[:39]` | `eada780f79f40516db8583bd13c0f9a8b9bf7386f1f94a3ff1147a165165436f` | `aa60371ab37c791ed3b27cd9d940948a555bdbb5a5a9b4560c4ac48b75737259` | rebased |
| `tools[:40]` | `b77d5243ed0ee3b797a5c2869a012120a29e6377b343666751dfe27863ed89b4` | `38dfb867168d41cec9536bab2b44956c3110a26ba4124eceeee13ea8eec86245` | rebased (newly pinned) |

Invariance anchors for `tools[37]` (serializer A):

- `inputSchema`: `ec6401f8ec660ab07fbe2dee11ff8d6a4f093f85bc3dcd7aaf9f440905ba272e`
- the descriptor without `description`, `intent` and `limitations`:
  `93ac74d44468c9bc36c49173468cf9629e2a19f4b579bc45d173b07c4ff21945`
- the whole `tools[37]` before the change: `2a08d8c6fdef7d89da686e16afe982d627686a98a60fa8eac0da09053a5c1842`

File SHA-256 values at base: `program/tools.json` `79ea4ab3…cf772`;
`guitar-report-bundle/SKILL.md`
`33045f113109c0d4cdaa73908ee49871677eb4b3c7c47df1fbb112c78c919ea9` (the
current pin); `guitar-phrase-timing/SKILL.md` `691650c1…1b676a`;
`scripts/tool_api.py` `78821c67…f3bc19`; `scripts/phrase_timing.py`
`0d3c248b…a70b5b`. The receipt records the full values.

## Frozen replacement wording for tools[37]

The text is plain ASCII. It must not contain "tends", "tendency", "rush" or
"drag" as claims.

- `description`: "Measure, per phrase span, signed onset offsets of broadband
  attack candidates from the nearest modelled in-recording click (fitted drift
  model, else constant grid) from an existing rhythm analysis.json and
  hash-bound arrangement markers or phrases.json review spans. Reports measured
  per-phrase median offset, IQR and click-proximal onset count, writes one fresh
  phrase-timing.json and abstains below 4 click-proximal onsets. Ahead/behind
  direction is reported only for generated known-offset fixtures or with an
  operator calibration, and is withheld on real takes. Click identity unverified
  and capture latency uncalibrated; never a performance grade or missed-note
  verdict."
- `intent`: "Show a musician the measured signed onset offsets of each phrase
  against the recorded click (median, IQR, count), with abstention and
  uncertainty and without an intended-rhythm reference; whether a phrase is
  ahead of or behind the click is withheld on real takes until an operator
  calibration exists."
- `limitations[0..2]`: unchanged.
- `limitations[3]`: "Ahead/behind direction is reported only for generated
  known-offset fixtures (run_kind synthetic_fixture) or with an operator
  calibration, and no calibration input exists yet; on real takes direction is
  null with direction_status withheld_uncalibrated. No intended-rhythm reference
  is used: no performance grade, missed/extra note or mistake verdict. Inputs
  are read only; one fresh output child is written beneath artifacts/."

The phrase "or with an operator calibration" follows the ruling. The added
clause "no calibration input exists yet" stops the text from claiming a
capability that the schema lacks (`direction_policy.operator_calibration_input_supported`
is false). If Phase 2 needs a wording change, record it as a deviation in the
receipt. Do not change the wording silently.

## Report_bundle skill wording

Replace `**Hook:** MCP tool \`report_bundle\` (once admitted by root).` with
`**Hook:** MCP tool \`report_bundle\` (admitted as tool 40).` Leave every other
byte unchanged. Re-pin `REPORT_BUNDLE_SKILL_SHA256` to the new file hash.
Comment the pin with the 2026-10-07 ruling and keep the superseded value
(`33045f11…`) in the comment. The test also asserts that "once admitted by
root" is absent and that "Never adopt a detector, profile or master default"
is still present.

## Test protocol

Run from the worktree root with no media access. FFmpeg env vars are exported
anyway (`FFMPEG`/`FFPROBE` as given in the lane rules):

```
PYTHONPATH=tests python3 -m unittest test_s2_tool_admission test_s1_tool_admission test_sprint1_audit test_tool_contracts -v
PYTHONPATH=tests python3 -m unittest test_mcp test_tools test_phrase_timing test_share_export_tool -v
```

The second line covers directly affected modules: MCP tools/prompts listing,
registry loading, the phrase_timing worker (unchanged; this confirms schema 2
behaviour) and the share_export prior-descriptor pin. The full suite is not run
(root runs it).

Fixtures are synthetic or registry-only. The existing temporary
`artifacts/` boundary patch in `test_s2_tool_admission` stays. No recording,
accepted run or repository artifact is read or written.

New or changed assertions in `tests/test_s2_tool_admission.py`:

| ID | Test | Asserts |
| --- | --- | --- |
| T1 | `test_first_32_descriptors_frozen_and_four_appended` (extended) | 32/36/37/38/39/40 freezes, both serializers. 37 equals the base, 38/39/40 equal the rebased values. Names, count 40 and the `indent=2` round-trip are unchanged. |
| T2 | `test_descriptor_rebase_phrase_timing_only_text_changed` (new) | `inputSchema` hash and the non-text-fields hash equal the base anchors. `limitations[0..2]` equal the base strings. Only the three text keys differ from the base. |
| T3 | `test_descriptor_rebase_phrase_timing_argv_unchanged` (new) | `tool_api.worker_command('phrase_timing', …)` on a synthetic `analysis`/`phrases`/`output_root` under the patched boundary gives the fixed argv shape `[…, scripts/phrase_timing.py, --analysis, A, --phrases, P, --output-root, O, --run-kind, real_take]`. The default `run_kind` is `real_take` and the enum is `[real_take, synthetic_fixture]`. |
| T4 | `test_descriptor_rebase_phrase_timing_skill_consistency` (new) | The descriptor text contains "median", "IQR", "count", "withheld on real takes", "known-offset fixtures" and "operator calibration". It has no "tends", "tendency", "rushing" or "dragging". The skill contains `withheld_uncalibrated`, `synthetic_known_offset_fixture`, "median", "IQR" and "operator calibration", and its frontmatter name is `guitar-phrase-timing`. |
| T5 | `test_admission_e_report_bundle_descriptor_equals_lane_draft_and_skill_exists` (pin updated) | New `REPORT_BUNDLE_SKILL_SHA256`; "once admitted by root" is absent and the hook text is present. |
| T6 | `test_real_mcp_lists_tools_and_reads_back_each_new_skill_prompt` (unchanged) | The MCP prompt readback equals both edited skill files byte for byte. This is S2 follow-up 8 evidence. |

The `tools[:30]` assertions in `test_s1_tool_admission` and
`test_sprint1_audit`, and the `tools[:32]` constants, stay unchanged and must
pass.

Known environmental errors: five `test_tool_contracts` real-evaluator tests
(`test_real_learned_evaluator_mcp_preserves_octave_failure_and_inputs`,
`test_real_learned_evaluator_stale_raw_retains_structural_receipt`,
`test_real_learned_evaluator_unsupported_claim_keeps_metrics_and_fails`,
`test_real_phrase_evaluator_summary_stale_proof_and_failed_hard_gate`,
`test_real_pitch_evaluator_summary_keeps_abstentions_and_structural_failure`)
error only because the worktree path contains `.local` (root_admission_d/e
receipts). If exactly these five appear, they are recorded as known and not
counted as lane failures. Any other error or failure blocks completion.

## Completion metrics

Claim classes: **M** = measured by a hash or a test run in this lane;
**I** = inference; **L** = listening (none in this lane).

1. **M** Freeze preservation: 8/8 base hashes unchanged (`tools[:30]`,
   `[:32]`, `[:36]` and `[:37]`, each under serializers A and B). The
   test_sprint1_audit `canonical()` hash of `tools[:30]` equals serializer B.
2. **M** Rebased freezes: 6/6 new constants (38/39/40 × 2 serializers) match
   the committed registry, and each has a ruling-citing comment plus its
   superseded value.
3. **M** `tools[37]` invariance: 3/3 anchors hold (inputSchema hash,
   non-text-fields hash, `limitations[0..2]` equality). The argv shape is equal
   for 1/1 synthetic call. `git diff 7d0e11e -- scripts/tool_api.py
   scripts/phrase_timing.py` is empty.
4. **M** Wording: the descriptor text has 0 occurrences of the forbidden tokens
   and 6/6 required phrases. The skill has 5/5 required tokens.
5. **M** report_bundle: 1 changed line in the skill diff, the pin is updated,
   and the MCP readback equals the file for 2/2 edited skills (and for all
   admitted prompts that the test already covers).
6. **M** Tests: for each listed module, report the `Ran N tests` line and the
   result line verbatim. Pass = 0 failures and 0 errors other than the five
   known `.local` errors. N is whatever the run reports.
7. **I** Doctrine: the new text makes no real-take ahead/behind, rush/drag,
   grade or missed-note claim. This is an inference from T4 token checks plus
   a manual read, recorded as such.
8. **L** None. `listening_acceptance` stays `not_performed`.

## Unknown and abstain fields the receipt must carry

`descriptor_rebase-receipt.json` keeps these explicit, even when null:

- `real_take_direction`: `"withheld_uncalibrated"` (unchanged worker behaviour)
- `operator_calibration`: `null`; `operator_calibration_input_supported`: `false`
- `capture_latency`: `"uncalibrated"`; `click_identity`: `"unverified"`
- `listening_acceptance`: `"not_performed"`; `performance_grading`: `"not_performed"`;
  `expected_rhythm_reference`: `null`
- `full_suite`: `"not_run_by_lane"`; `hosted_ci`: `"not_run_by_lane"`;
  `root_merge`/`signature`: `"pending_root"`; `linear_sync`: `"not_performed_by_lane"`
- `known_errors`: the five `.local` tests, or `[]` when they do not appear
- `deviations`: `[]`, or each deviation from this contract with its reason
- `old_hashes`/`new_hashes` for every prefix in the table, `tools[37]`, both
  skills and `program/tools.json`, plus `reason` citing the 2026-10-07 ruling
  and S2 follow-ups 7 and 8

## Experiment and preregistration

Not applicable. This lane runs no experiment, has no arms, seeds or held-out
data, and adopts no detector, profile or master default. The only "truth" is
the set of base hashes above. They were sealed in this commit before any edit,
and Phase 2 verifies against them.
