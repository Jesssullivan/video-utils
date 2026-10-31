# Handoff relay readback and the cade-delivery map

Linear: TIN-7788. Rulings: R-DAG-20261030-a (TIN-7788 comment `60fca3e8`) and SPR-288 (TIN-7788 comment
`ac4bd797`). Code: `narrate/video/relay.py`. Tests: `narrate/tests/test_relay_readback.py`. Recipes:
`just nv-relay-readback` and `just nv-relay-map` in `just/narrated-video.just`.

A fab child repo's `just mfg-handoff <packet> --send` pipes its fab-dag-handoff/1 record to `cade-handoff-relay`.
The relay contract is xoxd-ai/cade `docs/HANDOFF_RELAY.md` at the cade#222 merge `64f10799`. Its activation has
four steps. Lab installs the relay, narrate writes the mapping file, a child sets `notify` and the operator gives
the GO for a live send. SPR-288 makes the merge of lab#3167 the install on the two producer hosts it names. The
lab pull-switch delivers it, with the canary first. This page covers the narrate side of steps 1 and 2. Children
keep `notify` unset until narrate posts the readback on TIN-7788.

Host names and checkout paths are arguments. This repository is public, so none of them are written here.

## Readback

`just nv-relay-readback <host> <child> <merge> <since-gen>` runs once per producer host and changes nothing there.
`<child>` is a fab child repo checkout on that host, such as the one whose `mfg-handoff` will call the relay.
`<merge>` is the lab#3167 merge commit. `<since-gen>` is the host's generation before the merge's switch, and the
driver refuses to run without it. The driver pipes `relay.py` over ssh to the host's own `python3`, so nothing is
copied to the host. In `<child>` it runs `just --command python3 -I - probe`, and the probe runs `bash -c`. That
is the chain the template's `mfg.py` follows: `just` runs the recipe, Python runs `bash -c <notify>`, and the
relay inherits that environment.

| Check | Passes when |
|---|---|
| `generation_moved` | The delivered record for the activated generation names a lab commit that contains `<merge>`, checked with `gh api` compare. The record is `deployed.json` with verdict `SWITCHED` or `NO-OP`, or `hm-delivered.json` for the host's Home Manager attr with `tree` equal to `clean`, as lab `local_switch_as_delivered` reads it. The attr is `--hm-attr`, else the one `deployed.json` records. A generation is an int or a digit string, the form lab writes. A bool or any other value is no generation. A `SWITCHED` record also needs `after_gen` above `before_gen`. The generation must be above `<since-gen>`, and a `NO-OP` record passes only through that comparison. The detail names the source, the `hm-delivered.json` tree and every record it ignored: a file that holds no JSON object, a missing or malformed commit id, a failed verdict, attr or tree, and a record that is not the running one |
| `relay_from_active_generation` | The relay on PATH is the file the activated generation's `home-files` links |
| `command_v` | `command -v cade-handoff-relay` prints a path in this launch context |
| `version` | `cade-handoff-relay --version` prints `cade-handoff-relay 0.1.0 (fab-dag-handoff/1)` and exits 0 |
| `interpreter` | The wrapper execs a Nix store `python3` with `-I`, and that interpreter runs. The row names it and its version |
| `script_pinned` | The wrapped script's sha256 is in `relay.PINS`, the pin lab#3167 vendors |
| `swb` | The wrapper's default `CADE_HANDOFF_RELAY_SWB` is an executable |
| `config_path_default` | The path the relay resolves is `~/.config/cade/handoff-relay.json`. An `XDG_CONFIG_HOME` set to `~/.config` passes. The row names any `CADE_HANDOFF_RELAY_CONFIG` or `XDG_CONFIG_HOME` that is set |
| `mapping_absent` | No mapping file exists yet. After narrate writes it, `--expect-agent-id ID` replaces this row with `mapping_written`: a regular file, mode 0600, owned by the user, naming ID |

The driver runs two contexts by default. `ssh` is the plain remote command and `login` wraps it in the user's
login shell, so lab-rendered PATH lines load. Neither one is the producer seat's own harness. The readback says
which context each row came from. The producer seat gives the third row from its own session, in its child repo:

```sh
just --command bash -c 'command -v cade-handoff-relay && cade-handoff-relay --version'
```

A PASS needs every row in both contexts on both hosts, plus that producer row. A missing `command_v` row in the
plain `ssh` context blocks the PASS: that context fails, so the verdict is FAIL. Narrate then posts the FAIL with
its rows and does not tell a child to set `notify`. Lab `docs/operations/AGENT_SWITCHBOARD.md` says a producer
started from such a context must name the absolute install path. That does not turn the row into a pass.

The verdict is PASS only when `ssh` and `login` both ran and every row passed. A failing row gives FAIL. `--context`
can narrow the run to fewer contexts, and every row passing then gives PARTIAL, which names the contexts not run.
Both exit nonzero. `local` runs on the machine that runs the driver, so its rows name that host and not `<host>`.
Neither FAIL nor PARTIAL lets a child set `notify`.

## The cade-delivery map

swb v0.5.0 addresses only a per-session agent id, so the relay maps `cade-delivery` to the narrate seat's id
through `~/.config/cade/handoff-relay.json`. Lab leaves that file unmanaged. `just nv-relay-map <host> <child>`
writes it on one host. It is a dry run unless `--write` is passed.

1. The driver takes the id `swb whoami` prints for this session. It does not pass `--register`, so nothing is
   written. The id's host must be this machine's host name. Its pid must be an ancestor of the driver process, and
   the id's harness must be a whole `-`, `_` or `.` separated word of the basename of that process's `argv[0]` or
   `argv[1]`. So `pi` matches `pi-agent` and not `pip`. `--agent-id` and `SWB_AGENT_ID` are optional, and each one
   that is set must equal that id. A typed id is never the source: without a `swb whoami` id the driver refuses
   `agent_id_missing`.
2. On the host, write-map finds the installed relay the way the probe does. It loads the relay only when the
   script's sha256 is pinned, and it loads the bytes it hashed.
3. When the file already maps `cade-delivery`, it resolves that entry first. Only `agent_id_stale`,
   `agent_id_superseded` or `agent_id_unknown` lets it replace the entry. A live holder refuses
   `map_held_by_live_session` unless `--supersede-live` is passed. Any other result refuses with its own code, even
   with `--supersede-live`, because it says nothing about the holder. Those results are a switchboard error on the
   holder's host, an unbound delivery key and an entry the relay rejects.
4. It builds the entry `{agent_id, seat: narrate, ruling: R-DAG-20261030-a, updated_utc}` and keeps any other
   recipient in an existing file.
5. It writes the bytes to a mode 0600 file and calls the installed relay's own `resolve_recipient` on them, with
   the swb the wrapper names. A dry run uses a private scratch directory. A write uses a temporary file beside the
   target, then renames it into place and resolves the final file again. The directory is created with mode 0700.
6. It prints a receipt: the result, the path shown under `~`, the sha256, the mode, the new id and the id it
   replaced with that id's state.

| Refusal | Meaning |
|---|---|
| `agent_id_missing` | `swb whoami` named no id for this session |
| `agent_id_mismatch` | After the write, the installed relay resolves another id than the one written |
| `agent_id_not_self` | The id's host, pid or harness is not this session, or `--agent-id` or `SWB_AGENT_ID` names another id |
| `agent_id_invalid` | The id is not `harness:host:pid:session_id` |
| `host_invalid` | The host argument could be read as an ssh option. It must be a host or `user@host` that starts with a letter or digit |
| `merge_invalid` | `--merge` is not a full 40-character commit id |
| `probe_failed` | ssh or `just` failed, timed out or printed no JSON object as its last line |
| `agent_id_stale` | swb peers lists the id as gone or ended |
| `agent_id_superseded` | The session restarted under a new pid. The map is written from the new session |
| `agent_id_unknown` | swb peers lists no session for the id |
| `map_held_by_live_session` | The file maps another id that is still live. `--supersede-live` replaces it |
| `existing_map_unsafe`, `existing_map_invalid` | The current file is a link, writable by others or not the schema, or its `cade-delivery` entry is one the relay rejects: not an object, an unknown field, or not exactly one valid `agent_id` or `delivery_key`. Nothing is changed |
| `config_path_override` | The relay would read another path in this context |
| `config_path_absent` | The relay resolves no mapping path, because HOME is unset |
| `config_dir_absent` | The parent of the mapping directory, `~/.config` by default, does not exist |
| `relay_absent`, `relay_unreadable`, `relay_pin_mismatch`, `relay_module_unloadable` | No relay, an unreadable wrapper, an unpinned script or one that does not load |
| `wrapper_unparsed` | The wrapper has no `exec <python> -I <script> "$@"` line |
| `file_too_large` | The wrapper or the mapping file is over 64 KiB, or the script is over 1 MiB |
| `recipient_config_invalid` | In the probe's `mapping_written` row: the file's `recipients` or its `cade-delivery` entry is not an object |
| `swb_unavailable` and the other relay switchboard codes | The relay's own `swb peers` refusal, for the new id or for the current holder |
| `recipient_unbound` | The current holder is a delivery key that swb lists as not bound |

Every refusal leaves the existing file as it was. The relay checks the same id again at every send. When the narrate
session changes, the relay refuses `recipient_superseded` or `recipient_stale` until the new session runs
`nv-relay-map --write`. The old id is then no longer live, so no `--supersede-live` is needed.

## Order after the merge

1. The canary's `lab/pull-switch/<canary>` status is `success` on a commit that contains the merge. Then the
   follower switches.
2. `just nv-relay-readback` for each host with `<since-gen>` N, where N is that host's generation before the
   merge's switch. Take N from a readback before the merge, or from the `before_gen` of the merge's `SWITCHED`
   receipt, and say which in the comment. The rows include `mapping_absent`. The producer seat posts its own row.
3. `just nv-relay-map` for each host as a dry run, then with `--write`.
4. `just nv-relay-readback` again for each host with the same N and `--expect-agent-id`.
5. One TIN-7788 comment carries both hosts' rows and the map receipts. Then the producer seat may set
   `notify = Some "cade-handoff-relay"`.

Each host step is a host act. It needs a run that may act on that host.

## Limits

- The readback does not check that the lab `swb` wrapper builds a sender id inside a `just mfg-handoff`
  subprocess. The relay contract leaves that to the first dry run on each host.
- The relay checks only that `manifest.signature` is present and named `<packet_rel>/manifest.json.asc` or
  `.sig`. It never verifies the signature. Narrate must verify the manifest sha256 and signature of each forwarded
  record before it acts on one. No code here does that yet. It is `verify_packet`, step 9b of the Activeplug plan
  in TIN-7788 comment `8121fcfd`, which narrate drafts and CADE-1 lands. A readback PASS shows only that the relay
  is installed. It is not that verification.
- A new relay version changes the vendored sha256. The probe then fails `script_pinned`, and write-map refuses until
  `relay.PINS` names the new pin.
