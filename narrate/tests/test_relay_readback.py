"""The relay readback and the interim cade-delivery map (narrate/video/relay.py, TIN-7788, SPR-288).

Every host here is synthetic: a temporary HOME and store, a stub relay with the 0.1.0 API that write-map calls, a
fake `swb` that answers `peers` from a file or fails for one host, and a fake Home Manager generation. No ssh, swb,
broker or lab state is reached. The stub's sha256 replaces the real pin for each test.
"""

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from narrate.video import relay

MERGE = "a" * 40
LATER = "b" * 40
SELF = "claude:seat-host:4242:narrate-session"
OTHER = "claude:seat-host:5151:older-session"
FOREIGN = "claude:producer-a:999:someone-else"
HOLDER = "claude:other-host:5151:other-session"  # a holder on another host, so its swb peers call can fail alone
ATTR = "user@producer-a"

STUB = """from __future__ import annotations
import json, os, stat, subprocess, sys
from pathlib import Path
VERSION = "@VERSION@"
LIVE_STATES = ("live", "idle")
ENTRY_KEYS = ("agent_id", "delivery_key", "seat", "ruling", "updated_utc")
SWB_FAILURES = {7: "swb_peers_failed", 75: "swb_timeout", 69: "swb_unavailable"}
class Refusal(Exception):
    def __init__(self, code, where, exit_code=1):
        super().__init__(code)
        self.code, self.where, self.exit_code = code, where, exit_code
def valid_agent_id(a):
    p = a.split(":") if isinstance(a, str) else []
    return len(p) == 4 and p[0] in ("claude", "codex") and p[2].isdigit() and all(p[1:])
def delivery_key(a):
    h, host, _pid, s = a.split(":")
    return f"{h}:{host}:{s}"
def config_path(env):
    if env.get("CADE_HANDOFF_RELAY_CONFIG"):
        return Path(env["CADE_HANDOFF_RELAY_CONFIG"])
    base = env.get("XDG_CONFIG_HOME") or (str(Path(env["HOME"]) / ".config") if env.get("HOME") else "")
    return Path(base) / "cade" / "handoff-relay.json" if base else None
def load_mapping(path):
    if os.stat(Path(path).parent).st_mode & 0o022:
        raise Refusal("recipient_config_unsafe", "dir", 3)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        raise Refusal("recipient_config_absent", "no file", 3)
    except OSError:
        raise Refusal("recipient_config_unsafe", "link", 3)
    with os.fdopen(fd, "rb") as f:
        st = os.fstat(f.fileno())
        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o022:
            raise Refusal("recipient_config_unsafe", "file", 3)
        cfg = json.loads(f.read())
    if cfg.get("schema") != "cade-handoff-relay-recipients/1":
        raise Refusal("recipient_config_invalid", "schema", 3)
    return cfg
def resolve_recipient(name, path, peers):
    entry = load_mapping(path)["recipients"].get(name)
    if entry is None:
        raise Refusal("recipient_unknown", "no entry", 3)
    if not isinstance(entry, dict) or any(k not in ENTRY_KEYS for k in entry):
        raise Refusal("recipient_config_invalid", "unknown field", 3)
    if ("agent_id" in entry) == ("delivery_key" in entry):
        raise Refusal("recipient_config_invalid", "exactly one", 3)
    if "agent_id" in entry and not valid_agent_id(entry["agent_id"]):
        raise Refusal("recipient_config_invalid", "agent_id", 3)
    key = delivery_key(entry["agent_id"]) if "agent_id" in entry else entry["delivery_key"]
    rows = [r for r in peers(key.split(":")[1]) if delivery_key(r["agent_id"]) == key]
    if not rows:
        raise Refusal("recipient_unknown", "no session", 3)
    row = rows[-1]
    if "agent_id" in entry and row["agent_id"] != entry["agent_id"]:
        raise Refusal("recipient_superseded", "new pid", 3)
    if row.get("state") not in LIVE_STATES:
        raise Refusal("recipient_stale", "gone", 3)
    if "delivery_key" in entry and row.get("bound") is not True:
        raise Refusal("recipient_unbound", "not bound", 3)
    return row["agent_id"]
def swb_binary(env):
    s = env.get("CADE_HANDOFF_RELAY_SWB")
    if not s or not os.access(s, os.X_OK):
        raise Refusal("swb_unavailable", "no swb", 4)
    return s
def swb_peers(swb, env):
    def list_host(host):
        r = subprocess.run([swb, "peers", "--all", "--host", host], env=env, capture_output=True)
        if r.returncode:
            raise Refusal(SWB_FAILURES[r.returncode], f"swb peers exit {r.returncode}", 4)
        return json.loads(r.stdout)["peers"]
    return list_host
if __name__ == "__main__" and sys.argv[1:] == ["--version"]:
    print(f"cade-handoff-relay {VERSION} (fab-dag-handoff/1)")
"""


def live(agent_id, state="live"):
    return {"agent_id": agent_id, "state": state}


@pytest.fixture
def host(tmp_path, monkeypatch):
    """A producer host after a switch that delivered MERGE: the wrapper, its generation, and no mapping file."""
    store, home = tmp_path / "store", tmp_path / "home"
    py = store / "aaa-python3" / "bin" / "python3"
    py.parent.mkdir(parents=True)
    py.symlink_to(sys.executable)
    script = store / "bbb-cade-handoff-relay"
    script.write_text(STUB.replace("@VERSION@", "0.1.0"))
    swb = store / "ccc-swb" / "bin" / "swb"
    swb.parent.mkdir(parents=True)
    swb.write_text(
        "#!/bin/sh\n"
        '[ "$4" = "$FAKE_SWB_FAIL_HOST" ] && exit "$FAKE_SWB_FAIL_EXIT"\n'
        "exec " + shlex.quote(sys.executable) + " -c 'import json,os; "
        'print(json.dumps({"peers": json.load(open(os.environ["FAKE_PEERS"]))}))\' "$@"\n'
    )
    swb.chmod(0o755)
    wrap = store / "ddd-cade-handoff-relay" / "bin" / "cade-handoff-relay"
    wrap.parent.mkdir(parents=True)
    wrap.write_text(
        "#!/usr/bin/env bash\nset -o errexit\n\n"
        f'export CADE_HANDOFF_RELAY_SWB="${{CADE_HANDOFF_RELAY_SWB:-{swb}}}"\n'
        f'exec {py} -I {script} "$@"\n'
    )
    wrap.chmod(0o755)
    files = store / "eee-home-manager-files" / ".local" / "bin"
    files.mkdir(parents=True)
    (files / "cade-handoff-relay").symlink_to(wrap)
    gen = store / "fff-home-manager-generation"
    gen.mkdir()
    (gen / "home-files").symlink_to(store / "eee-home-manager-files")
    (home / ".local" / "bin").mkdir(parents=True)
    (home / ".local" / "bin" / "cade-handoff-relay").symlink_to(files / "cade-handoff-relay")
    roots = home / ".local" / "state" / "home-manager" / "gcroots"
    roots.mkdir(parents=True)
    (roots / "current-home").symlink_to(gen)
    state = home / ".local" / "state" / "tinyland" / "pull-switch"
    state.mkdir(parents=True)
    (state / "deployed.json").write_text(
        json.dumps(
            {
                "sha": MERGE,
                "before_gen": "40",  # lab writes generations as digit strings (hm-pull-switch.py parse_generation)
                "after_gen": "41",
                "after_path": str(gen),
                "verdict": "SWITCHED",
                "hm_attr": ATTR,
                "timestamp": "2026-11-01T00:00:00Z",
            }
        )
    )
    (home / ".config").mkdir(mode=0o700)
    peers = tmp_path / "peers.json"
    peers.write_text(json.dumps([live(SELF)]))
    for name in (
        "XDG_CONFIG_HOME",
        "XDG_STATE_HOME",
        "CADE_HANDOFF_RELAY_CONFIG",
        "CADE_HANDOFF_RELAY_SWB",
        "SWB_AGENT_ID",
    ):
        monkeypatch.delenv(name, raising=False)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("XDG_", "CADE_", "SWB_"))}
    env.update(
        HOME=str(home),
        NIX_STORE_DIR=str(store),
        FAKE_PEERS=str(peers),
        PATH=str(home / ".local" / "bin") + os.pathsep + os.environ.get("PATH", ""),
    )
    monkeypatch.setattr(
        relay, "PINS", {hashlib.sha256(script.read_bytes()).hexdigest(): "cade-handoff-relay 0.1.0 (fab-dag-handoff/1)"}
    )
    return {
        "env": env,
        "home": home,
        "store": store,
        "script": script,
        "gen": gen,
        "peers": peers,
        "config": home / ".config" / "cade" / "handoff-relay.json",
        "roots": roots,
        "state": state,
    }


def contains_merge(base, head):
    return head in (MERGE, LATER) and base == MERGE


def failing(rows):
    return sorted(c for c, ok, _ in rows if not ok)


def test_a_fresh_switch_passes_every_check(host):
    p = relay.probe(host["env"], "ssh")
    assert p["command_v"] == "~/.local/bin/cade-handoff-relay" and p["command_is_install_path"]
    assert p["version"]["stdout"] == "cade-handoff-relay 0.1.0 (fab-dag-handoff/1)"
    assert p["wrapper"]["interpreter"] == str(host["store"] / "aaa-python3" / "bin" / "python3")
    assert p["wrapper"]["interpreter_version"].startswith("Python 3")
    assert p["mapping"] == {
        "path": "~/.config/cade/handoff-relay.json",
        "resolved_by": "relay",
        "default": True,
        "override_env": [],
        "state": "absent",
    }
    assert p["generation"]["running"]["generation"] == 41
    assert failing(relay.evaluate(p, MERGE, contains_merge, since_gen=40)) == []
    assert str(host["home"]) not in json.dumps(p)  # a receipt shows HOME as ~


def test_a_mapping_written_before_narrate_writes_it_fails(host):
    host["config"].parent.mkdir(mode=0o700)
    host["config"].write_text("{}")
    p = relay.probe(host["env"], "ssh")
    assert failing(relay.evaluate(p, MERGE, contains_merge)) == ["mapping_absent"]


def test_a_wrong_version_or_unpinned_script_fails(host, monkeypatch):
    host["script"].write_text(STUB.replace("@VERSION@", "0.1.1"))
    p = relay.probe(host["env"], "ssh")
    assert failing(relay.evaluate(p, MERGE, contains_merge)) == ["script_pinned", "version"]


def test_a_relay_the_activated_generation_does_not_link_fails(host):
    other = host["store"] / "ggg-home-manager-generation"
    other.mkdir()
    (host["roots"] / "current-home").unlink()
    (host["roots"] / "current-home").symlink_to(other)
    p = relay.probe(host["env"], "ssh")
    assert failing(relay.evaluate(p, MERGE, contains_merge)) == ["generation_moved", "relay_from_active_generation"]


def test_a_generation_without_the_merge_or_not_past_the_baseline_fails(host):
    p = relay.probe(host["env"], "ssh")
    assert failing(relay.evaluate(p, MERGE, lambda base, head: False)) == ["generation_moved"]
    assert failing(relay.evaluate(p, MERGE, contains_merge, since_gen=41)) == ["generation_moved"]
    assert failing(relay.evaluate(p, MERGE, lambda base, head: None)) == ["generation_moved"]


def test_an_absent_relay_reports_every_row(host):
    (host["home"] / ".local" / "bin" / "cade-handoff-relay").unlink()
    p = relay.probe(host["env"], "ssh")
    assert p["command_v"] is None
    assert failing(relay.evaluate(p, MERGE, contains_merge)) == [
        "command_v",
        "interpreter",
        "relay_from_active_generation",
        "script_pinned",
        "swb",
        "version",
    ]


def test_write_map_dry_run_writes_nothing_and_write_makes_a_private_file(host):
    out = relay.write_map(host["env"], SELF, write=False, now="2026-11-01T00:00:00Z")
    assert out["result"] == "dry-run" and not host["config"].parent.exists()
    out = relay.write_map(host["env"], SELF, write=True, now="2026-11-01T00:00:00Z")
    cfg = json.loads(host["config"].read_text())
    assert out["result"] == "written" and out["mode"] == "0600" and out["path"] == "~/.config/cade/handoff-relay.json"
    assert oct(host["config"].stat().st_mode & 0o777) == "0o600"
    assert oct(host["config"].parent.stat().st_mode & 0o777) == "0o700"
    assert cfg == {
        "schema": "cade-handoff-relay-recipients/1",
        "recipients": {
            "cade-delivery": {
                "agent_id": SELF,
                "seat": "narrate",
                "ruling": "R-DAG-20261030-a",
                "updated_utc": "2026-11-01T00:00:00Z",
            }
        },
    }
    assert out["sha256"] == hashlib.sha256(host["config"].read_bytes()).hexdigest()
    assert [p.name for p in host["config"].parent.iterdir()] == ["handoff-relay.json"]
    assert relay.write_map(host["env"], SELF, write=True)["result"] == "unchanged"
    p = relay.probe(host["env"], "ssh")
    assert failing(relay.evaluate(p, MERGE, contains_merge, expect_agent_id=SELF)) == []
    assert failing(relay.evaluate(p, MERGE, contains_merge, expect_agent_id=OTHER)) == ["mapping_written"]


@pytest.mark.parametrize(
    "rows, code",
    [
        ([live(SELF, "gone")], "agent_id_stale"),
        ([live(SELF), live("claude:seat-host:4343:narrate-session")], "agent_id_superseded"),
        ([live(OTHER)], "agent_id_unknown"),
    ],
)
def test_write_map_refuses_a_stale_id_and_writes_nothing(host, rows, code):
    host["peers"].write_text(json.dumps(rows))
    for write in (False, True):
        with pytest.raises(relay.Refused) as e:
            relay.write_map(host["env"], SELF, write=write)
        assert e.value.code == code
        assert not host["config"].exists()
        assert not host["config"].parent.exists() or list(host["config"].parent.iterdir()) == []


def test_write_map_refuses_a_malformed_id(host):
    with pytest.raises(relay.Refused, match="agent_id_invalid"):
        relay.write_map(host["env"], "claude:seat-host:narrate-session", write=True)


def seed(host, agent_id, extra=None):
    host["config"].parent.mkdir(mode=0o700, exist_ok=True)
    recipients = {"cade-delivery": {"agent_id": agent_id}, **(extra or {})}
    host["config"].write_text(json.dumps({"schema": "cade-handoff-relay-recipients/1", "recipients": recipients}))
    host["config"].chmod(0o600)


def test_write_map_keeps_a_live_holder_unless_told_to_supersede_it(host):
    seed(host, OTHER)
    host["peers"].write_text(json.dumps([live(OTHER), live(SELF)]))
    with pytest.raises(relay.Refused, match="map_held_by_live_session"):
        relay.write_map(host["env"], SELF, write=True)
    assert json.loads(host["config"].read_text())["recipients"]["cade-delivery"]["agent_id"] == OTHER
    out = relay.write_map(host["env"], SELF, write=True, supersede_live=True)
    assert (out["previous_agent_id"], out["previous_state"]) == (OTHER, "live")


@pytest.mark.parametrize("supersede", [False, True])
@pytest.mark.parametrize("exit_code, code", [(7, "swb_peers_failed"), (75, "swb_timeout"), (69, "swb_unavailable")])
def test_write_map_keeps_a_holder_the_switchboard_cannot_answer_for(host, exit_code, code, supersede):
    """A switchboard error says nothing about the holder, so it refuses even when the new id's host answers."""
    seed(host, HOLDER)
    before = host["config"].read_bytes()
    host["peers"].write_text(json.dumps([live(HOLDER), live(SELF)]))
    host["env"].update(FAKE_SWB_FAIL_HOST="other-host", FAKE_SWB_FAIL_EXIT=str(exit_code))
    for write in (False, True):
        with pytest.raises(relay.Refused) as e:
            relay.write_map(host["env"], SELF, write=write, supersede_live=supersede)
        assert e.value.code == code
        assert host["config"].read_bytes() == before
    del host["env"]["FAKE_SWB_FAIL_HOST"]
    with pytest.raises(relay.Refused, match="map_held_by_live_session"):  # the same file, once swb answers
        relay.write_map(host["env"], SELF, write=True)


def seed_entry(host, entry):
    host["config"].parent.mkdir(mode=0o700, exist_ok=True)
    host["config"].write_text(
        json.dumps({"schema": "cade-handoff-relay-recipients/1", "recipients": {"cade-delivery": entry}})
    )
    host["config"].chmod(0o600)
    return host["config"].read_bytes()


@pytest.mark.parametrize("supersede", [False, True])
@pytest.mark.parametrize(
    "entry",
    [
        {"agent_id": HOLDER, "note": "x"},
        {"agent_id": SELF, "note": "x"},
        {"agent_id": HOLDER, "delivery_key": "claude:other-host:other-session"},
        {"agent_id": "not-an-id"},
        {},
        "x",
        ["a"],
        7,
        "",
        None,
    ],
)
def test_write_map_refuses_an_entry_the_relay_rejects(host, entry, supersede):
    before = seed_entry(host, entry)
    host["peers"].write_text(json.dumps([live(HOLDER), live(SELF)]))
    for write in (False, True):
        with pytest.raises(relay.Refused) as e:
            relay.write_map(host["env"], SELF, write=write, supersede_live=supersede)
        assert e.value.code == "existing_map_invalid"
        assert host["config"].read_bytes() == before


def test_write_map_keeps_a_delivery_key_holder_the_relay_calls_unbound(host):
    before = seed_entry(host, {"delivery_key": "claude:other-host:other-session"})
    host["peers"].write_text(json.dumps([live(HOLDER), live(SELF)]))
    with pytest.raises(relay.Refused) as e:
        relay.write_map(host["env"], SELF, write=True, supersede_live=True)
    assert e.value.code == "recipient_unbound"
    assert host["config"].read_bytes() == before


@pytest.mark.parametrize(
    "rows, state",
    [
        ([live(HOLDER, "gone"), live(SELF)], "agent_id_stale"),
        ([live("claude:other-host:6262:other-session"), live(SELF)], "agent_id_superseded"),
        ([live(SELF)], "agent_id_unknown"),
    ],
)
def test_write_map_replaces_a_holder_in_each_stale_state(host, rows, state):
    seed(host, HOLDER)
    host["peers"].write_text(json.dumps(rows))
    out = relay.write_map(host["env"], SELF, write=True)
    assert (out["result"], out["previous_agent_id"], out["previous_state"]) == ("written", HOLDER, state)


def test_write_map_replaces_a_stale_holder_and_keeps_other_recipients(host):
    other = {"cade-later": {"delivery_key": "claude:seat-host:worker"}}
    seed(host, OTHER, other)
    host["peers"].write_text(json.dumps([live(OTHER, "ended"), live(SELF)]))
    out = relay.write_map(host["env"], SELF, write=True)
    cfg = json.loads(host["config"].read_text())
    assert (out["previous_agent_id"], out["previous_state"]) == (OTHER, "agent_id_stale")
    assert cfg["recipients"]["cade-later"] == other["cade-later"]
    assert cfg["recipients"]["cade-delivery"]["agent_id"] == SELF


def test_write_map_refuses_a_link_an_override_and_an_unpinned_relay(host, monkeypatch, tmp_path):
    host["config"].parent.mkdir(mode=0o700)
    target = tmp_path / "elsewhere.json"
    target.write_text("{}")
    host["config"].symlink_to(target)
    with pytest.raises(relay.Refused, match="existing_map_unsafe"):
        relay.write_map(host["env"], SELF, write=True)
    assert host["config"].is_symlink() and target.read_text() == "{}"
    with pytest.raises(relay.Refused, match="config_path_override"):
        relay.write_map({**host["env"], "XDG_CONFIG_HOME": str(tmp_path / "xdg")}, SELF, write=True)
    monkeypatch.setattr(relay, "PINS", {"0" * 64: "cade-handoff-relay 0.1.0 (fab-dag-handoff/1)"})
    with pytest.raises(relay.Refused, match="relay_pin_mismatch"):
        relay.write_map(host["env"], SELF, write=True)


def test_remote_command_enters_the_child_repo_and_wraps_a_login_shell():
    plain = relay.remote_command("~/git/child repo", "ssh", ["probe", "--via", "ssh"])
    assert plain == "cd \"$HOME\"/'git/child repo' && exec just --command python3 -I - probe --via ssh"
    login = relay.remote_command("/srv/child", "login", ["write-map", "--agent-id", SELF])
    assert login == 'exec "$SHELL" -lic ' + shlex.quote(
        f"cd /srv/child && exec just --command python3 -I - write-map --agent-id {SELF}"
    )


class MapArgs:
    host, child_repo, context, write, supersede_live, agent_id = "producer-a", "~/child", "login", True, False, None


@pytest.fixture
def seat(monkeypatch):
    """The narrate seat: `swb whoami` names SELF, whose pid 4242 is an ancestor running claude on seat-host."""
    calls = []
    monkeypatch.setattr(relay, "swb_whoami", lambda env: SELF)
    monkeypatch.setattr(relay, "local_host", lambda: "seat-host")
    monkeypatch.setattr(relay, "ancestor_pids", lambda: [3000, 4242, 1])
    monkeypatch.setattr(relay, "command_of", lambda pid: ["/opt/harness/bin/claude", "--resume", "s"])
    monkeypatch.setattr(relay, "run_on", lambda *a: calls.append(a) or {"result": "written"})
    return calls


def map_args(**kw):
    a = MapArgs()
    for k, v in kw.items():
        setattr(a, k, v)
    return a


def test_map_driver_writes_the_id_swb_whoami_names(seat):
    relay.map_driver(map_args(), {})
    relay.map_driver(map_args(agent_id=SELF), {"SWB_AGENT_ID": SELF})
    assert seat == [("producer-a", "~/child", "login", ["write-map", "--agent-id", SELF, "--write"])] * 2


def test_map_driver_refuses_a_typed_id_without_swb_whoami(seat, monkeypatch):
    monkeypatch.setattr(relay, "swb_whoami", lambda env: None)
    for env in ({}, {"SWB_AGENT_ID": FOREIGN}):
        with pytest.raises(relay.Refused, match="agent_id_missing"):
            relay.map_driver(map_args(agent_id=FOREIGN), env)
    assert seat == []


@pytest.mark.parametrize(
    "args, env",
    [
        ({"agent_id": FOREIGN}, {}),
        ({"agent_id": OTHER}, {"SWB_AGENT_ID": SELF}),
        ({}, {"SWB_AGENT_ID": FOREIGN}),
        ({"agent_id": "seat-host:1:x"}, {}),
    ],
)
def test_map_driver_refuses_an_id_that_is_not_the_sessions_own(seat, args, env):
    with pytest.raises(relay.Refused, match="agent_id_not_self"):
        relay.map_driver(map_args(**args), env)
    assert seat == []


@pytest.mark.parametrize(
    "name, value",
    [
        ("local_host", lambda: "producer-a"),
        ("ancestor_pids", lambda: [3000, 1]),
        ("command_of", lambda pid: ["/usr/bin/python3", "forged"]),
        ("command_of", lambda pid: ["/usr/bin/bash", "-c", "claude --resume s"]),
    ],
)
def test_map_driver_refuses_a_whoami_id_from_another_host_pid_or_harness(seat, monkeypatch, name, value):
    """SWB_* can be set by hand, so the id `swb whoami` builds must also be this machine and this process tree."""
    monkeypatch.setattr(relay, name, value)
    with pytest.raises(relay.Refused, match="agent_id_not_self"):
        relay.map_driver(map_args(), {})
    assert seat == []


def test_map_driver_surfaces_a_write_map_refusal(seat, monkeypatch):
    monkeypatch.setattr(relay, "run_on", lambda *a: {"refused": "agent_id_stale", "where": "gone", "exit": 1})
    with pytest.raises(relay.Refused, match="agent_id_stale: gone"):
        relay.map_driver(map_args(), {})


def test_ancestor_pids_reaches_this_process_parent():
    assert os.getppid() in relay.ancestor_pids()
    assert relay.command_of(os.getpid())[0]


@pytest.mark.parametrize(
    "argv, harness, want",
    [
        (["/opt/x-claude-code/bin/claude", "--resume"], "claude", True),
        (["node", "/usr/local/bin/codex"], "codex", True),
        (["pi-agent", "run"], "pi", True),
        (["/usr/bin/pip", "install"], "pi", False),
        (["python3", "-m", "pip"], "pi", False),
        (["bash", "-c", "pi"], "pi", False),
        ([], "claude", False),
    ],
)
def test_the_harness_is_a_word_of_the_program_name(argv, harness, want):
    assert relay.runs_harness(argv, harness) is want


def fake_run(monkeypatch, stdout=b"", returncode=0, raises=None):
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        if raises:
            raise raises
        return subprocess.CompletedProcess(cmd, returncode, stdout, b"err line\n")

    monkeypatch.setattr(relay.subprocess, "run", run)
    return calls


def test_run_on_reads_the_last_stdout_line_and_a_refusal(monkeypatch):
    calls = fake_run(monkeypatch, b"motd noise\n" + json.dumps({"schema": "x"}).encode() + b"\n")
    assert relay.run_on("user@producer-a", "~/c", "ssh", ["probe"]) == {"schema": "x", "exit": 0}
    assert calls[0][:6] == ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "user@producer-a"]
    assert calls[0][6] == "--"
    fake_run(monkeypatch, json.dumps({"refused": "agent_id_stale", "where": "gone"}).encode(), returncode=1)
    assert relay.run_on("producer-a", "~/c", "login", ["write-map"])["refused"] == "agent_id_stale"
    fake_run(monkeypatch, b"not json\n", returncode=255)
    with pytest.raises(relay.Refused, match="probe_failed: exit 255: err line"):
        relay.run_on("producer-a", "~/c", "ssh", ["probe"])


@pytest.mark.parametrize("bad", ["-oProxyCommand=touch x", "producer a", "", "a\nb", "-p"])
def test_run_on_refuses_a_host_that_ssh_could_read_as_an_option(monkeypatch, bad):
    calls = fake_run(monkeypatch, b"{}\n")
    with pytest.raises(relay.Refused, match="host_invalid"):
        relay.run_on(bad, "~/c", "ssh", ["probe"])
    assert calls == []


@pytest.mark.parametrize(
    "stdout, code, raises, want",
    [
        (b"ahead\n", 0, None, True),
        (b"identical\n", 0, None, True),
        (b"behind\n", 0, None, False),
        (b"diverged\n", 0, None, False),
        (b"", 0, None, None),
        (b"ahead\n", 1, None, None),
        (b"", 0, FileNotFoundError("gh"), None),
        (b"", 0, subprocess.TimeoutExpired("gh", 60), None),
    ],
)
def test_gh_contains_reads_the_compare_status(monkeypatch, stdout, code, raises, want):
    calls = fake_run(monkeypatch, stdout, code, raises)
    assert relay.gh_contains("org/lab")(MERGE, LATER) is want
    assert calls == [["gh", "api", f"repos/org/lab/compare/{MERGE}...{LATER}", "--jq", ".status"]]


def readback_args(**kw):
    base = dict(
        host="producer-a",
        child_repo="~/c",
        merge=MERGE,
        context=None,
        since_gen=40,
        expect_agent_id=None,
        hm_attr=None,
        json=True,
        lab_repo="org/lab",
    )
    return argparse.Namespace(**{**base, **kw})


def test_readback_passes_only_when_every_context_passes(host, monkeypatch, capsys):
    good = relay.probe(host["env"], "ssh")
    bad = {**good, "command_v": None}
    seen = []

    def run_on(h, child, context, args):
        seen.append((context, args))
        return good if context == "ssh" else bad

    monkeypatch.setattr(relay, "run_on", lambda *a: dict(good))
    assert relay.readback(readback_args(), contains_merge) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["verdict"] == "PASS" and [r["context"] for r in out["rows"]] == ["ssh", "login"]
    monkeypatch.setattr(relay, "run_on", run_on)
    assert relay.readback(readback_args(hm_attr=ATTR), contains_merge) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["verdict"] == "FAIL"
    assert [c["check"] for c in out["rows"][1]["checks"] if not c["ok"]] == ["command_v"]
    assert seen[0] == ("ssh", ["probe", "--via", "ssh", "--hm-attr", ATTR])


@pytest.mark.parametrize(
    "context, missing, shown",
    [
        (["ssh"], ["login"], "producer-a"),
        (["login"], ["ssh"], "producer-a"),
        (["ssh", "ssh"], ["login"], "producer-a"),
        (["local"], ["ssh", "login"], "seat-host"),
    ],
)
def test_readback_of_fewer_contexts_is_partial_and_exits_nonzero(host, monkeypatch, capsys, context, missing, shown):
    good = relay.probe(host["env"], "ssh")
    monkeypatch.setattr(relay, "local_host", lambda: "seat-host")
    monkeypatch.setattr(relay, "run_on", lambda *a: dict(good))
    assert relay.readback(readback_args(context=context), contains_merge) == 1
    out = json.loads(capsys.readouterr().out)
    assert (out["verdict"], out["contexts_not_run"]) == ("PARTIAL", missing)
    assert {r["host"] for r in out["rows"]} == {shown}
    assert relay.readback(readback_args(context=context, json=False), contains_merge) == 1
    text = capsys.readouterr().out
    assert f"readback {shown} at lab {MERGE[:12]}: PARTIAL" in text
    assert text.rstrip().endswith("not run: " + ", ".join(missing))


def test_readback_needs_both_contexts_and_a_failing_row_stays_a_fail(host, monkeypatch, capsys):
    good = relay.probe(host["env"], "ssh")
    monkeypatch.setattr(relay, "local_host", lambda: "seat-host")
    monkeypatch.setattr(relay, "run_on", lambda *a: dict(good))
    assert relay.readback(readback_args(context=["login", "ssh", "local"]), contains_merge) == 0
    out = json.loads(capsys.readouterr().out)
    assert (out["verdict"], out["contexts_not_run"]) == ("PASS", [])
    assert [r["host"] for r in out["rows"]] == ["producer-a", "producer-a", "seat-host"]
    monkeypatch.setattr(relay, "run_on", lambda *a: {**good, "command_v": None})
    assert relay.readback(readback_args(context=["login"]), contains_merge) == 1
    assert json.loads(capsys.readouterr().out)["verdict"] == "FAIL"


def test_a_local_map_receipt_names_the_local_host(host, monkeypatch, capsys):
    monkeypatch.setattr(relay, "local_host", lambda: "seat-host")
    monkeypatch.setattr(relay, "self_id", lambda env: SELF)
    receipt = {"result": "dry-run", "path": "~/x", "mode": "0600", "agent_id": SELF, "sha256": "ab" * 32}
    monkeypatch.setattr(relay, "run_on", lambda *a: receipt)
    monkeypatch.delenv("SWB_AGENT_ID", raising=False)
    assert relay.main(["map", "--host", "producer-a", "--child-repo", "~/c", "--context", "local"]) == 0
    assert capsys.readouterr().out.startswith("map seat-host: dry-run")


def test_readback_fails_a_refused_or_unreachable_probe(monkeypatch, capsys):
    replies = iter([{"refused": "relay_unreadable", "where": "x", "exit": 1}])

    def run_on(*a):
        try:
            return next(replies)
        except StopIteration:
            raise relay.Refused("probe_failed", "exit 255") from None

    monkeypatch.setattr(relay, "run_on", run_on)
    assert relay.readback(readback_args(json=False), contains_merge) == 1
    text = capsys.readouterr().out
    assert "| probe | NO | relay_unreadable: x |" in text and "probe_failed: exit 255" in text
    assert text.rstrip().endswith("FAIL")


def test_the_probe_cli_prints_one_json_object(host, monkeypatch, capsys):
    for k, v in host["env"].items():
        monkeypatch.setenv(k, v)
    assert relay.main(["probe", "--via", "login"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["schema"] == "narrate.relay-probe/v1" and out["via"] == "login"
    readback = ["readback", "--host", "producer-a", "--child-repo", "~/c", "--merge", "x"]
    assert relay.main(readback + ["--since-gen", "40"]) == 1
    with pytest.raises(SystemExit):  # the readback needs the generation from before the switch
        relay.main(readback)


@pytest.mark.parametrize("verdict", ["EVAL-FAILED", "INTERRUPTED", "FAILED", None])
def test_a_deployed_record_without_a_success_verdict_does_not_vouch(host, verdict):
    """Lab writes deployed.json only on SWITCHED or NO-OP. A record that says otherwise never passes."""
    dep = json.loads((host["state"] / "deployed.json").read_text())
    dep.update(verdict=verdict, after_gen="40")
    (host["state"] / "deployed.json").write_text(json.dumps(dep))
    p = relay.probe(host["env"], "ssh")
    assert p["generation"]["running"] is None
    rows = relay.evaluate(p, MERGE, contains_merge)
    assert failing(rows) == ["generation_moved"]
    assert f"deployed.json verdict {verdict}" in dict((c, d) for c, _ok, d in rows)["generation_moved"]


def test_a_switched_record_whose_generation_did_not_move_fails(host):
    dep = json.loads((host["state"] / "deployed.json").read_text())
    dep.update(after_gen="40")
    (host["state"] / "deployed.json").write_text(json.dumps(dep))
    p = relay.probe(host["env"], "ssh")
    assert failing(relay.evaluate(p, MERGE, contains_merge)) == ["generation_moved"]


def deployed(host, **fields):
    dep = json.loads((host["state"] / "deployed.json").read_text())
    dep.update(fields)
    (host["state"] / "deployed.json").write_text(json.dumps(dep))
    return relay.probe(host["env"], "ssh")


@pytest.mark.parametrize("before, after", [("40", "41"), (40, 41)])
def test_a_switched_record_passes_with_string_or_int_generations(host, before, after):
    """Lab's receipts carry digit strings. An int is accepted too, and both compare as numbers."""
    p = deployed(host, before_gen=before, after_gen=after)
    assert p["generation"]["running"]["generation"] == 41
    assert failing(relay.evaluate(p, MERGE, contains_merge, since_gen=40)) == []
    assert failing(relay.evaluate(p, MERGE, contains_merge, since_gen=41)) == ["generation_moved"]


@pytest.mark.parametrize(
    "before, after", [(False, True), ("40", True), ("40", "4l"), ("40", "-41"), ("40", 41.0), ("40", None)]
)
def test_a_generation_that_is_not_a_number_never_passes(host, before, after):
    p = deployed(host, before_gen=before, after_gen=after)
    for since_gen in (None, 0, 40):
        assert failing(relay.evaluate(p, MERGE, contains_merge, since_gen=since_gen)) == ["generation_moved"]


def test_a_no_op_record_needs_a_baseline(host):
    """A NO-OP moved nothing, so it passes only when its generation is above --since-gen."""
    p = deployed(host, verdict="NO-OP", before_gen="41", after_gen="41")
    rows = relay.evaluate(p, MERGE, contains_merge)
    assert failing(rows) == ["generation_moved"]
    assert failing(relay.evaluate(p, MERGE, contains_merge, since_gen=40)) == []
    assert failing(relay.evaluate(p, MERGE, contains_merge, since_gen=41)) == ["generation_moved"]
    p = deployed(host, verdict="NO-OP", before_gen=True, after_gen=True)
    assert failing(relay.evaluate(p, MERGE, contains_merge, since_gen=0)) == ["generation_moved"]


def delivered(host, attr, tree="clean", generation="41"):
    (host["state"] / "deployed.json").unlink(missing_ok=True)
    record = {"head": MERGE, "generation_path": str(host["gen"]), "generation": generation, "timestamp": "2026-11-01"}
    if attr:
        record["attr"] = attr
    if tree is not None:
        record["tree"] = tree
    (host["home"] / relay.DELIVERED).write_text(json.dumps(record))


@pytest.mark.parametrize("tree", ["DIRTY", "unknown", None])
def test_hm_delivered_counts_only_for_a_clean_tree(host, tree):
    """A dirty switch built HEAD plus uncommitted edits, so it does not show that the merge was delivered."""
    delivered(host, ATTR, tree)
    p = relay.probe(host["env"], "ssh", ATTR)
    assert p["generation"]["running"] is None
    rows = relay.evaluate(p, MERGE, contains_merge, since_gen=40)
    assert failing(rows) == ["generation_moved"]
    assert f"hm-delivered.json tree {tree}" in dict((c, d) for c, _ok, d in rows)["generation_moved"]


@pytest.mark.parametrize("generation", ["41", 41])
def test_hm_delivered_with_a_clean_tree_names_it(host, generation):
    delivered(host, ATTR, generation=generation)
    rows = relay.evaluate(relay.probe(host["env"], "ssh", ATTR), MERGE, contains_merge, since_gen=40)
    assert failing(rows) == []
    assert "gen 41 from hm-delivered.json tree clean" in dict((c, d) for c, _ok, d in rows)["generation_moved"]


def test_hm_delivered_counts_only_for_the_hosts_attr(host):
    """As lab local_switch_as_delivered: hm-delivered.json vouches only for this host's Home Manager attr."""
    delivered(host, ATTR)
    assert failing(relay.evaluate(relay.probe(host["env"], "ssh", ATTR), MERGE, contains_merge)) == []
    for attr in ("someone@else", None):
        delivered(host, attr)
        p = relay.probe(host["env"], "ssh", ATTR)
        assert failing(relay.evaluate(p, MERGE, contains_merge)) == ["generation_moved"]
    delivered(host, ATTR)
    p = relay.probe(host["env"], "ssh")  # no attr given and no deployed.json to name one
    assert p["generation"]["hm_attr"] is None
    assert failing(relay.evaluate(p, MERGE, contains_merge)) == ["generation_moved"]


def generation_detail(p):
    return dict((c, d) for c, _ok, d in relay.evaluate(p, MERGE, contains_merge, since_gen=40))["generation_moved"]


@pytest.mark.parametrize(
    "name, body, note",
    [
        (relay.PULL_STATE + "/deployed.json", {"sha": "not-a-sha", "verdict": "SWITCHED"}, "deployed.json sha"),
        (relay.PULL_STATE + "/deployed.json", {"verdict": "SWITCHED"}, "deployed.json sha"),
        (relay.PULL_STATE + "/deployed.json", "not json", "deployed.json holds no record"),
        (relay.PULL_STATE + "/deployed.json", "[1]", "deployed.json holds no record"),
        (relay.PULL_STATE + "/deployed.json", {}, "deployed.json holds no record"),
        (relay.DELIVERED, {"head": "A" * 40, "attr": ATTR, "tree": "clean"}, "hm-delivered.json head"),
        (relay.DELIVERED, {"attr": ATTR, "tree": "clean"}, "hm-delivered.json head"),
        (relay.DELIVERED, "{", "hm-delivered.json holds no record"),
    ],
)
def test_a_malformed_record_is_named_as_ignored(host, name, body, note):
    (host["home"] / name).write_text(body if isinstance(body, str) else json.dumps(body))
    p = relay.probe(host["env"], "ssh", ATTR)
    assert any(i.startswith(note) for i in p["generation"]["ignored"])
    assert note in generation_detail(p)


def test_absent_records_add_no_note(host):
    (host["state"] / "deployed.json").unlink()
    assert relay.probe(host["env"], "ssh", ATTR)["generation"]["ignored"] == []


def test_a_record_for_another_generation_or_an_older_one_is_named_as_ignored(host):
    record = json.loads((host["state"] / "deployed.json").read_text())
    delivered(host, ATTR)  # it names the activated generation, with an older timestamp than deployed.json
    (host["state"] / "deployed.json").write_text(json.dumps(record))
    p = relay.probe(host["env"], "ssh", ATTR)
    assert p["generation"]["running"]["source"] == "pull-switch deployed.json"
    assert p["generation"]["ignored"] == ["hm-delivered.json is not the running record"]
    (host["state"] / "deployed.json").write_text(json.dumps({**record, "after_path": "/elsewhere"}))
    p = relay.probe(host["env"], "ssh", ATTR)
    assert p["generation"]["running"]["source"] == "hm-delivered.json"
    assert p["generation"]["ignored"] == ["pull-switch deployed.json is not the running record"]


def test_config_path_default_follows_the_resolved_path(host, tmp_path):
    env = {**host["env"], "XDG_CONFIG_HOME": str(host["home"] / ".config") + "/"}
    p = relay.probe(env, "ssh")
    rows = relay.evaluate(p, MERGE, contains_merge)
    assert failing(rows) == []
    assert "XDG_CONFIG_HOME" in dict((c, d) for c, _ok, d in rows)["config_path_default"]
    p = relay.probe({**host["env"], "XDG_CONFIG_HOME": str(tmp_path / "xdg")}, "ssh")
    assert failing(relay.evaluate(p, MERGE, contains_merge)) == ["config_path_default"]


def test_config_path_without_a_loadable_relay_uses_the_0_1_0_rule(host, tmp_path):
    env = {**host["env"], "CADE_HANDOFF_RELAY_CONFIG": str(tmp_path / "x.json")}
    assert relay.mapping(env, None)["default"] is False
    assert relay.mapping(env, None)["resolved_by"] == "relay 0.1.0 rule"
    assert relay.mapping(host["env"], None)["default"] is True


@pytest.mark.parametrize("entry", ["x", ["a"], 7, ""])
def test_a_mapping_entry_that_is_not_an_object_is_a_refusal_row(host, entry):
    seed(host, SELF)
    cfg = json.loads(host["config"].read_text())
    cfg["recipients"]["cade-delivery"] = entry
    host["config"].write_text(json.dumps(cfg))
    p = relay.probe(host["env"], "ssh")
    assert p["mapping"]["refusal"] == "recipient_config_invalid"
    rows = relay.evaluate(p, MERGE, contains_merge, since_gen=40, expect_agent_id=SELF)
    assert failing(rows) == ["mapping_written"]
    assert "refusal recipient_config_invalid" in dict((c, d) for c, _ok, d in rows)["mapping_written"]


def test_write_map_refuses_an_unchanged_entry_whose_id_is_stale(host):
    seed(host, SELF)
    before = host["config"].read_bytes()
    host["peers"].write_text(json.dumps([live(SELF, "gone")]))
    with pytest.raises(relay.Refused, match="agent_id_stale"):
        relay.write_map(host["env"], SELF, write=True)
    assert host["config"].read_bytes() == before


def test_the_file_runs_on_its_own_with_python_isolated():
    """The driver pipes this file to a host's python3, where the narrate package is not installed."""
    source = Path(relay.__file__).read_text()
    assert "from ." not in source and "import narrate" not in source


def no_local_bin(host):
    """The PATH of a non-interactive lab shell: lab renders ~/.local/bin below the rc files' interactive guard."""
    return {**host["env"], "PATH": os.environ.get("PATH", "")}


def test_a_context_without_local_bin_still_reads_the_installed_relay(host):
    p = relay.probe(no_local_bin(host), "ssh")
    assert p["command_v"] is None and p["relay_path"] == "~/.local/bin/cade-handoff-relay"
    assert p["version"]["stdout"] == "cade-handoff-relay 0.1.0 (fab-dag-handoff/1)"
    assert failing(relay.evaluate(p, MERGE, contains_merge, since_gen=40)) == ["command_v"]


def test_write_map_finds_the_relay_at_the_install_path(host):
    assert relay.write_map(no_local_bin(host), SELF, write=True)["result"] == "written"


def test_only_the_bare_name_row_in_the_ssh_context_is_advisory(host, monkeypatch, capsys):
    good = relay.probe(host["env"], "ssh")
    bare = relay.probe(no_local_bin(host), "ssh")

    def contexts(ssh, login):
        monkeypatch.setattr(relay, "run_on", lambda h, c, context, a: dict(ssh if context == "ssh" else login))

    contexts(bare, good)
    assert relay.readback(readback_args(json=False), contains_merge) == 0
    out = capsys.readouterr().out
    assert "| ssh | command_v | no (advisory) |" in out and ": PASS" in out
    contexts(bare, good)
    assert relay.readback(readback_args(), contains_merge) == 0
    rows = json.loads(capsys.readouterr().out)["rows"]
    assert [c["check"] for c in rows[0]["checks"] if c["advisory"]] == ["command_v"]
    assert not [c for c in rows[1]["checks"] if c["advisory"]]
    contexts(good, bare)
    assert relay.readback(readback_args(), contains_merge) == 1  # the login row is the rendered PATH
    assert json.loads(capsys.readouterr().out)["verdict"] == "FAIL"
    contexts({**bare, "version": {"exit": 1, "stdout": ""}}, good)
    assert relay.readback(readback_args(), contains_merge) == 1  # every other ssh row still counts
    assert json.loads(capsys.readouterr().out)["verdict"] == "FAIL"


@pytest.mark.parametrize("write", [False, True])
def test_a_directory_the_relay_refuses_refuses_a_dry_run_too(host, write):
    host["config"].parent.mkdir()
    host["config"].parent.chmod(0o775)
    with pytest.raises(relay.Refused, match="recipient_config_unsafe"):
        relay.write_map(host["env"], SELF, write=write)
    assert list(host["config"].parent.iterdir()) == []


@pytest.mark.parametrize("write", [False, True])
def test_a_missing_config_directory_refuses_a_dry_run_too(host, write):
    (host["home"] / ".config").rmdir()
    with pytest.raises(relay.Refused, match="config_dir_absent"):
        relay.write_map(host["env"], SELF, write=write)


def test_a_refusal_after_the_rename_says_the_new_entry_is_in_place(host, monkeypatch):
    real = relay.resolve

    def down_after_rename(mod, path, peers):
        if Path(path).name == "handoff-relay.json":
            raise relay.Refused("swb_peers_failed", "down")
        return real(mod, path, peers)

    monkeypatch.setattr(relay, "resolve", down_after_rename)
    with pytest.raises(relay.Refused, match="map_written_unverified: the new entry is in place: swb_peers_failed"):
        relay.write_map(host["env"], SELF, write=True)
    assert json.loads(host["config"].read_text())["recipients"]["cade-delivery"]["agent_id"] == SELF


def test_the_sessions_own_id_in_a_wider_mode_is_rewritten(host):
    relay.write_map(host["env"], SELF, write=True)
    host["config"].chmod(0o644)
    assert relay.write_map(host["env"], SELF, write=False)["result"] == "dry-run"
    assert oct(host["config"].stat().st_mode & 0o777) == "0o644"
    out = relay.write_map(host["env"], SELF, write=True)
    assert out["result"] == "written" and out["previous_state"] == "live"
    assert oct(host["config"].stat().st_mode & 0o777) == "0o600"
    assert relay.write_map(host["env"], SELF, write=True)["result"] == "unchanged"


def test_the_generation_row_names_the_last_tick_and_an_unanswered_compare(host):
    (host["state"] / "tick.json").write_text(json.dumps({"outcome": "deferred-live-sessions", "timestamp": "t"}))
    p = relay.probe(host["env"], "ssh")
    details = {c: d for c, _, d in relay.evaluate(p, MERGE, lambda base, head: None, since_gen=40)}
    assert "contains merge None" in details["generation_moved"]
    assert "last tick deferred-live-sessions" in details["generation_moved"]


def test_run_on_names_the_last_stderr_line(monkeypatch):
    def run(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 127, b"", b"bash: no job control in this shell\njust: not found\n")

    monkeypatch.setattr(relay.subprocess, "run", run)
    with pytest.raises(relay.Refused, match="probe_failed: exit 127: just: not found"):
        relay.run_on("producer-a", "~/c", "login", ["probe"])
