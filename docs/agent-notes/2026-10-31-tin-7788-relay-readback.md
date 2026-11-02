# Relay readback and cade-delivery map, October 31, 2026

Linear: TIN-7788. Receipt per R-HOOK-CONVERGENCE-20261004 (R-N13). Authority: the narrate W4 workflow lane brief
"relay readback" under SPR-288 (TIN-7788 `ac4bd797`), which asks for a runnable read-only readback and a drafted
map procedure, with no host act.

| stream | owner | repo/branch | state/evidence | next |
|---|---|---|---|---|
| relay readback | narrate lane | video-utils `feat/tin-7788-relay-readback-20261031` | draft, checks below | root review. After the lab#3167 merge, run the order in `docs/spec/HANDOFF_RELAY_READBACK.md` in a run that may act on hosts |

## Inputs read

- xoxd-ai/cade `docs/HANDOFF_RELAY.md` and `scripts/handoff-relay/cade-handoff-relay` at the cade#222 merge
  `64f10799`. The script's sha256 is `19b287a5`, the same as the lab pin.
- lab#3167 at head `53e494ad`: the wrapper module `nix/home-manager/cade-handoff-relay.nix`, the pin
  `vars/cade_handoff_relay.json` and the `AGENT_SWITCHBOARD.md` section.
- lab main `b2ce9ec9`: `scripts/validation/hm-pull-switch.py` for the delivered record and the activated
  generation, and `LOCAL_CONSOLIDATION_DELIVERY.md` section 7 for the state files.
- fab-agent-template v0.5.0 `15dd05d`: `just/mfg.just` and `mfg.py`, which runs notify with `bash -c`.

## Choices

- The procedure lives here, not in cade. `HANDOFF_RELAY.md` names the narrate seat as the writer of the mapping
  file and names no repository for the procedure.
- write-map calls the installed relay's own functions, loaded only from pinned bytes. So a stale, superseded or
  unknown id refuses exactly as the relay refuses it at send time.
- The readback runs a plain and a login ssh context. Neither one is the producer seat's harness, so the procedure
  asks that seat for its own `command -v` row.

## Checks

Local and non-qualifying. load1 was 28 to 42, so the full narrate suite was not run. It needs tinyland-heavy at
load1 below 24.

- `tests/test_relay_readback.py`: 18 passed.
- Mutation probes: each of 8 removed guards fails 1 to 3 tests. The guards are the dry-run and write stale checks,
  the generation link, the absent-map row, the live-holder guard, the pin, the self-id check and mode 0600.
- `narrate.tests.stdlib_smoke`: 7 OK, with `relay` added to its module list.
- `tests/test_public_tree.py`: 4 passed and 1 skipped. The skip is the private-terms file, which is unset.
- ruff check and ruff format: clean. The file parses under the Python 3.9 grammar.
- `just --command python3 -I - probe` with the file on stdin ran in a scratch justfile here. That host has no
  relay, so the probe reported `command_v` as none and the mapping as absent.

Nothing ran on a producer host, and nothing was written outside this branch.

## Review fixes, October 31, 2026

Authority: the lane readback brief on TIN-7788, which lists seven findings against head `966902bf`. Receipt per
R-HOOK-CONVERGENCE-20261004 (R-N13).

| Finding | Fix | Test |
|---|---|---|
| High: the map driver's self check failed open with `SWB_AGENT_ID` unset | The id comes from `swb whoami`. Its host must be this machine, its pid an ancestor of the driver and that process's command its harness. A typed `--agent-id` or `SWB_AGENT_ID` must equal it. Without a `swb whoami` id the driver refuses `agent_id_missing` | a foreign `--agent-id` with no `SWB_AGENT_ID` refuses. So does a forged host, pid or harness |
| Medium: `generation_moved` matched a record by path only | `deployed.json` counts only with `SWITCHED` or `NO-OP`. A `SWITCHED` record needs `after_gen` above `before_gen`. `hm-delivered.json` counts only for the host's attr. Step 2 of the procedure now passes `--since-gen` | EVAL-FAILED, INTERRUPTED, FAILED, an unmoved generation and three attr cases |
| Medium: the spec claimed a signature check | The Limits section states it as an open obligation, `verify_packet`, step 9b in TIN-7788 `8121fcfd` | none, a doc fix |
| Low: driver half untested | Tests for `readback()` across two contexts, a refused or unreachable probe, `run_on` parsing, a write-map refusal through the driver and `gh_contains` | 8 `gh_contains` cases |
| Low: `config_path_default` failed on `XDG_CONFIG_HOME=~/.config` | The row compares the resolved path. Without a loadable relay the probe applies the relay 0.1.0 rule | both cases |
| Low: an ssh host could be read as an option | `run_on` refuses a host that does not match `HOST_RE` | 5 bad hosts, no ssh call |
| Low: the hook trailer names the host | Not changed. History is not rewritten, since force-push is barred. The conflict is open for the operator | none |

One premise did not reproduce. At lab `b2ce9ec9`, `write_receipt` writes `deployed.json` only for `SWITCHED` or
`NO-OP` (line 1336). EVAL-FAILED and INTERRUPTED receipts go to `last.json` and `receipts/`. The verdict filter
stays as a guard on that contract.

Checks, local and non-qualifying: load1 was 27 to 42. `tests/test_relay_readback.py` gives 53 passed. Each of 11
mutation probes, one per new guard, fails 1 test. `narrate.tests.stdlib_smoke` gives 7 OK.
`tests/test_public_tree.py` gives 4 passed and 1 skipped. Ruff is clean, and the file parses under Python 3.9.

## Second review fixes, October 31, 2026

Authority: the narrate seat brief on TIN-7788, which lists seven findings against head `e556f191`. Receipt per
R-HOOK-CONVERGENCE-20261004 (R-N13).

| Finding | Fix | Test |
|---|---|---|
| Medium: lab writes generations as digit strings, so `generation_moved` never passed | `as_generation` turns an int or a digit string into an int. A bool, a sign, a float or other text is no generation. The `SWITCHED` and `--since-gen` comparisons use those ints | the fixture uses `"40"` and `"41"`. One case uses ints, six use values that are not numbers |
| Medium: a dirty local switch passed | `hm-delivered.json` counts only with `tree` equal to `clean`. Otherwise it is ignored with its tree value. The detail names the tree | `DIRTY`, `unknown` and a missing tree fail. A clean tree names it in the detail |
| Low: a mapping entry that is not an object crashed the probe | The probe reports `recipient_config_invalid` in the mapping row | four entry types |
| Low: a `NO-OP` record and bool generations passed without `--since-gen` | `--since-gen` is required, and the recipe takes it as a positional argument. A `NO-OP` record fails without a baseline | the CLI exits without `--since-gen`. A `NO-OP` passes only above the baseline |
| Low: the refusal table left out codes, and the PASS rule contradicted itself | The table adds the 7 missing codes and `recipient_config_invalid`. A missing `command_v` row in the `ssh` context blocks the PASS | none, a doc fix |
| Low: the harness check was a substring match | The harness must be a whole `-`, `_` or `.` separated word of the basename of `argv[0]` or `argv[1]` | 7 cases, including `pip` and `bash -c pi` |
| Low: the hook trailer names the host | Not changed. History is not rewritten, since force-push is barred. It is the operator's decision | none |

Checks, local and non-qualifying: load1 was 31 to 87, so the full narrate suite and tinyland-heavy were not run.
`tests/test_relay_readback.py` gives 79 passed. Each of 7 mutation probes, one per new guard, fails 1 to 14
tests. `narrate.tests.stdlib_smoke` gives 7 OK. `tests/test_public_tree.py` gives 4 passed and 1 skipped. Ruff
check and format are clean, and the file parses under the Python 3.9 grammar.

## Third review fixes, October 31, 2026

Authority: the narrate seat brief on TIN-7788, which lists findings against head `12cbbfed`. Receipt per
R-HOOK-CONVERGENCE-20261004 (R-N13).

| Finding | Fix | Test |
|---|---|---|
| Medium: the live-holder guard in `write_map` failed open, so a holder on another host was replaced when its `swb peers` failed | Only `agent_id_stale`, `agent_id_superseded` or `agent_id_unknown` lets a holder be replaced. Any other refusal keeps the file and refuses with its own code, also with `--supersede-live`. An entry the relay rejects, or a non-object or null entry, refuses `existing_map_invalid` | a fake swb fails only for the holder's host, with 3 codes, both flag values and dry run and write. 10 bad entries. One unbound delivery key. Each asserts the file bytes are unchanged. 3 stale states still replace |
| Low: the Linear receipt said both new commits carry the hook trailer | Corrected on TIN-7788 and in the correction below. The commit is unchanged | none |
| Low: `readback` printed PASS for a reduced context set | PASS needs `ssh` and `login`. A narrower set with every row passing prints PARTIAL, names the contexts not run and exits 1. `local` rows and the summary name the local host. The map receipt does the same, which the finding did not ask for | 4 narrow sets, both output forms, a failing row stays FAIL, a local map receipt |
| Low: the spec said the detail names every record ignored, and a malformed record was dropped with no note | `generation` notes a file that holds no JSON object, a missing or malformed commit id and a record that is not the running one | 8 malformed records, absent files add no note, 2 unused records |
| Info: #80 and #81 overlap in `just/narrated-video.just` | Not changed here. The second to land needs a signed merge of main that keeps both `nv-test` entries | none |

Correction to the second review receipt: Linear comment `93b63598` said both new commits carry the hook-written
trailer. Only `a6893db` has the Huskycat-Receipt trailer. The signed merge `12cbbfe` has only the `Linear` and
`Signed-off-by` lines. The commit is not changed.

The test stub now follows relay 0.1.0 for entry validation, `swb peers` failures and `recipient_unbound`. The same
cases ran once in scratch against the real relay bytes, sha256 `19b287a5`, with a fake swb, and all 11 gave the
expected result. The real file is not vendored here.

A holder whose host stays unreachable now blocks the write. `--supersede-live` does not clear it, so the operator
has to edit or remove the entry by hand.

## Final review, November 2, 2026

Authority: the narrate seat lane brief vu80 on TIN-7788, on Jess's word to run wide, which asks for a final adversarial
review at `0959c699` and the findings applied. Rulings: SPR-288 (TIN-7788 `ac4bd797`) and R-HOOK-CONVERGENCE-20261004
(R-N13). The earlier reviews used a stub relay and a PATH that held `~/.local/bin`, so this pass ran the real tools.

| Finding | Fix | Test |
|---|---|---|
| High: no PASS was reachable. Lab renders `~/.local/bin` below the interactive guard, so `bash -lc` and a plain shell lack it. Then `command_v` failed in both contexts, every wrapper row failed with it, and `nv-relay-map` refused `relay_absent` in its default context. The spec line that `login` loads the lab PATH was false | `login` runs `-lic`. The probe and write-map fall back to the install path. Every other row stays gating in `ssh`. The bare-name row in `ssh` is advisory, because SPR-288 names the producer's real launch context and a plain ssh command is not one | no `~/.local/bin` on PATH for the probe and write-map. Only the `ssh` bare-name row is advisory, a `login` miss and any other `ssh` miss still FAIL |
| Low: a dry run passed a mapping directory the write then refused, with a code the table did not list. It also missed `config_dir_absent` | `check_new_map_dir` runs for both, through the relay's own `load_mapping`. The table adds the code | group-writable and missing directories, dry run and write |
| Low: a refusal after the rename broke the spec line that every refusal keeps the file | `map_written_unverified` says the new entry is in place. The spec names both post-rename codes | a resolve that fails only for the final file |
| Low: the session's own id at a wider mode gave `unchanged`, and step 5's `mapping_written` could not then pass | That file is rewritten to 0600 | mode 0644 on dry run and write |
| Low: a deferred switch and a failed compare looked like a commit without the merge | The row names the last tick's outcome and the compare answer | deferred tick, unanswered compare |
| Low: the spec's pre-merge N had no command, and `probe_failed` printed the shell's tty notes | The order adds step 1 with the command. `probe_failed` prints the last stderr line | last stderr line |

These held against the real tools:

| Claim | Evidence |
|---|---|
| `just --command python3 -I -` passes `--via`, `--hm-attr`, `--agent-id`, `--write` and `--supersede-live` | just 1.51.0 with the real relay bytes, sha256 `19b287a5`, in a scratch HOME |
| `self_id` accepts a real harness | the real `swb whoami` and process tree on the seat |
| The relay's `swb peers` call and its live and superseded answers | a real broker read with a scratch map. The session's old pid gave `recipient_superseded` |
| The pin is current | cade main still has blob `4cb1a3a2`. Lab main still has `cliPackage` and `commissioned` |
| The lab record shapes are current | lab main `52437c22` keeps `VERDICTS_SUCCESS`, `write_receipt`, `activated_generation_path` and `local_switch_as_delivered` as at `b2ce9ec9` |
| The exact `login` string runs with a piped script | `bash -c` on that string with the rendered rc files, in a clean environment, with no bash process growth |

Checks, local and non-qualifying: load1 was 34 to 42, so the full narrate suite was not run.
`tests/test_relay_readback.py` gives 136 passed. Each of 16 mutation probes, one per new guard, fails a test.
`narrate.tests.stdlib_smoke` gives OK. Ruff check and format are clean. Nothing ran on a producer host.

The PATH measurement comes from a seat with the same lab shell modules, not from a producer host. The first
readback confirms it there.

## First readback checklist

Authority: the same lane brief. Every box is open. All of them wait on lab#3167 and need a run that may act on hosts.
`<canary>` and `<follower>` are the two hosts SPR-288 names. TIN-7788 carries the names.

| stream | owner | repo/branch | state/evidence | next |
|---|---|---|---|---|
| relay readback | narrate | video-utils#80 | reviewed, awaiting CI and root merge | the checklist below |
| relay install | lab landing lane | lab#3167 | draft at `53e494ad`, 98 commits behind main, merge state blocked | HOLD on its merge |

Before the merge:

- [ ] Root merges video-utils#80, so the recipes exist at the seat.
- [ ] Name `<child>` on each host: a fab child repo with a justfile, and the seat that gives the producer row.
- [ ] Record N on each host with the pre-merge command in step 1 of the order. After the merge, N comes only from a
      receipt on the host.
- [ ] Confirm lab#3167 still pins sha256 `19b287a5` at its final head, and that `relay.PINS` names it.

After the merge:

- [ ] The `<canary>` status `lab/pull-switch/<canary>` is `success` on a commit that contains the merge.
- [ ] If it stays `pending` with `deferred-live-sessions`, stop and take the deferral to Jess.
- [ ] `<follower>` switches, and its receipt is `SWITCHED`.
- [ ] Readback on each host with N. Expect `no (advisory)` on the `ssh` `command_v` row and PASS overall.
- [ ] The producer seat posts its row. If the bare name is missing, take the absolute `notify` path to the child.
- [ ] Map dry run, then `--write`, on each host, from the live narrate session. The id binds that session's pid.
- [ ] Readback on each host with N and `--expect-agent-id`.
- [ ] One TIN-7788 comment with both hosts' rows, the map receipts and the source of N.

Outside this checklist: the first relay `--dry-run` on each host, which the relay contract keeps for the sender id
question, then `notify` in the child and Jess's GO for a live send. A narrate restart makes the map stale, and the
relay then refuses `recipient_superseded` until the new session runs the map again.
