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
