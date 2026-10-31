"""The relay readback and the interim cade-delivery map (narrate/video/relay.py, TIN-7788, SPR-288).

Every host here is synthetic: a temporary HOME and store, a stub relay with the 0.1.0 API that write-map calls, a
fake `swb` that answers `peers` from a file, and a fake Home Manager generation. No ssh, swb, broker or lab state
is reached. The stub's sha256 replaces the real pin for each test.
"""

import hashlib
import json
import os
import shlex
import sys
from pathlib import Path

import pytest

from narrate.video import relay

MERGE = "a" * 40
LATER = "b" * 40
SELF = "claude:seat-host:4242:narrate-session"
OTHER = "claude:seat-host:5151:older-session"

STUB = """from __future__ import annotations
import json, os, stat, subprocess, sys
from pathlib import Path
VERSION = "@VERSION@"
LIVE_STATES = ("live", "idle")
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
    key = delivery_key(entry["agent_id"]) if "agent_id" in entry else entry["delivery_key"]
    rows = [r for r in peers(key.split(":")[1]) if delivery_key(r["agent_id"]) == key]
    if not rows:
        raise Refusal("recipient_unknown", "no session", 3)
    row = rows[-1]
    if "agent_id" in entry and row["agent_id"] != entry["agent_id"]:
        raise Refusal("recipient_superseded", "new pid", 3)
    if row.get("state") not in LIVE_STATES:
        raise Refusal("recipient_stale", "gone", 3)
    return row["agent_id"]
def swb_binary(env):
    s = env.get("CADE_HANDOFF_RELAY_SWB")
    if not s or not os.access(s, os.X_OK):
        raise Refusal("swb_unavailable", "no swb", 4)
    return s
def swb_peers(swb, env):
    def list_host(host):
        r = subprocess.run([swb, "peers", "--all", "--host", host], env=env, capture_output=True)
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
        "#!/bin/sh\nexec " + shlex.quote(sys.executable) + " -c 'import json,os; "
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
                "before_gen": 40,
                "after_gen": 41,
                "after_path": str(gen),
                "verdict": "SWITCHED",
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
    assert login == 'exec "$SHELL" -lc ' + shlex.quote(
        f"cd /srv/child && exec just --command python3 -I - write-map --agent-id {SELF}"
    )


def test_map_driver_writes_only_the_callers_own_id(monkeypatch):
    class A:
        host, child_repo, context, write, supersede_live, agent_id = "producer-a", "~/child", "login", True, False, None

    calls = []
    monkeypatch.setattr(relay, "run_on", lambda *a: calls.append(a) or {"result": "written"})
    with pytest.raises(relay.Refused, match="agent_id_missing"):
        relay.map_driver(A, {})
    A.agent_id = OTHER
    with pytest.raises(relay.Refused, match="agent_id_not_self"):
        relay.map_driver(A, {"SWB_AGENT_ID": SELF})
    A.agent_id = "seat-host:1:x"
    with pytest.raises(relay.Refused, match="agent_id_invalid"):
        relay.map_driver(A, {})
    assert calls == []
    A.agent_id = None
    relay.map_driver(A, {"SWB_AGENT_ID": SELF})
    assert calls == [("producer-a", "~/child", "login", ["write-map", "--agent-id", SELF, "--write"])]


def test_the_probe_cli_prints_one_json_object(host, monkeypatch, capsys):
    for k, v in host["env"].items():
        monkeypatch.setenv(k, v)
    assert relay.main(["probe", "--via", "login"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["schema"] == "narrate.relay-probe/v1" and out["via"] == "login"
    assert relay.main(["readback", "--host", "producer-a", "--child-repo", "~/c", "--merge", "x"]) == 1


def test_the_file_runs_on_its_own_with_python_isolated():
    """The driver pipes this file to a host's python3, where the narrate package is not installed."""
    source = Path(relay.__file__).read_text()
    assert "from ." not in source and "import narrate" not in source
