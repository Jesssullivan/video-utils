# Private presentation adapter source

repo | Jesssullivan/video-utils | branch feat/narrate-private-presentation-adapter-20261024 | integration main after existing narration owners' reviewed source | base 9dee72ad401a62d5007f1779febea49ef44a4f3d (rebased 2026-10-27) | head: the PR #48 head that carries this note | active development existing admitted remote seat (exact custody in private tracker) | owner xoxd_lexical_contract | source only | next independent review and private input inspection

Authority: the operator's instruction to continue the existing presentation,
voiceover and separate internal character proof, retaining the original client
voice-only/PIP-off edition. Root assigned isolated source ownership. Original
Claude coordination, dirty worktrees and E2/E4/E7 branches were preserved. This
change adds new files, plus one recipe in `just/narrate.just` (2026-10-27); no
engine, SIM, normalizer or other existing owner source was edited.

The new planner checks private project/source inputs, prepares a separately
namespaced character variant and binds authored scripts to narration inputs.
Provider-neutral audio/avatar inputs remain explicit. Missing files stay blocked.
Original speaker manuscripts are records and never blindly restyled. Source
trailers and control cues are excluded through the existing narration adapter;
caption manuscripts retain their exact approved bytes.

Independent review found two real preparation defects before publication: an
avatar-video EOF could truncate narration, and inherited config paths could escape
input containment. The successor loops the avatar until narration EOF, never cuts
at the planning duration, and validates consumed config files/directories against
contained digest-bound source inputs. Still derivatives require their own inventory.
Regression tests cover both defects. No media or assembly command was executed.

Validation and exact source acceptance are recorded with the final source head.
Actual private input manifests, path custody, client data and qualification outputs
remain outside this public repository, with factual tracker receipts. No private
lexical styles, client text, voice clips, avatar or source recordings are vendored.
A plan is not rendering, listening/SIM, consent, synchronization or publication proof.

Final source validation: 26 pure planner tests passed; owning Dhall render/check
recipes type-check the new normalized input, render its synthetic example exactly
and pass 31 refusal mutations. Ruff and diff checks pass. An earlier first input
fixture correctly remained blocked; a separately reviewed authored-script handoff
can produce speech-provider text before media exists. Actual private project
counts/digests and root internal authoring authority remain in private tracker and
state receipts, not this public note. Selected capture staging closes legacy
directory-discovery fallback without deleting historical source media.

## 2026-10-27 review fixes (L19, TIN-6938)

Sprint lane L19 (TIN-7125 c65bd544) review of PR #48 at 62b97ce3 found five
defects. Ruling: R-HOOK-CONVERGENCE-20261004 (TIN-3692 98cf680c). The fixes:

| Finding | Fix | Regression test |
| --- | --- | --- |
| Blocked plans failed on incomplete source bindings and left an empty output | Bindings are checked before mkdir; while inputs are missing a refusal is a prerequisite; a failed plan removes its own output | `test_blocked_plan_*`, `test_ready_source_refusal_*`, `test_failure_after_output_creation_*` |
| Equal capture names in two directories collided while staging | Captures stage at their path below `clips_dir`; case-folded collisions are refused before output | `test_equal_capture_names_*`, `test_case_folded_capture_collision_*` |
| Stills, slides and deck HTML stayed in the client tree; non-PNG stills skipped the inventory | Every admitted source file stages under `source/`; every still needs an inventory row | `test_uninventoried_still_*`, `test_internal_config_reads_staged_sources_*` |
| Receipt spacing, stale base and mutation count | Corrected above | none |
| Recipe unreachable from the root justfile | `just narrate-presentation-plan` in `just/narrate.just` | none |

Gates at the fix head: `just narrate-test` 745 passed and 1 skipped, `just
narrate-lint` clean, `just narrate-dhall-check` 31 mutations, stdlib smoke 6
tests and `tests/test_public_tree.py` 3 passed and 1 skipped (private terms unset).
