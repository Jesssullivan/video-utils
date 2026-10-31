"""The cade-handoff-relay post-switch readback and the interim cade-delivery map (TIN-7788, SPR-288).

A fab child repo's `just mfg-handoff <packet> --send` pipes its fab-dag-handoff/1 record to its notify command,
`cade-handoff-relay` (xoxd-ai/cade docs/HANDOFF_RELAY.md). Lab installs the relay on the producer hosts through the
pull-switch when lab#3167 merges (SPR-288, TIN-7788 ac4bd797). The relay sends to `cade-delivery`, which it resolves
through ~/.config/cade/handoff-relay.json. Lab leaves that file unmanaged, and the narrate seat writes it. Children
keep `notify` unset until narrate posts this readback.

One stdlib file, so the driver can pipe it to a host's own python3 and nothing is copied to the host:

  probe      on a producer host, read-only. It runs where the producer runs: `just --command` in a child repo,
             then `bash -c`, the way the template's mfg.py runs notify. It prints one JSON object
  write-map  on a producer host. It writes the cade-delivery entry, mode 0600, after the installed relay's own
             resolve_recipient accepts the exact bytes. A dry run unless --write
  readback   the driver at the narrate seat. It runs probe on one host per context, checks the delivered lab commit
             with `gh api` and prints one row per check
  map        the driver for write-map. It writes only the calling session's own switchboard id: `swb whoami`
             names it, its host is this machine and its pid is an ancestor of this process

The relay stays the authority on the mapping: write-map loads the installed copy only when its sha256 is in PINS
and calls its config_path, load_mapping, swb_peers and resolve_recipient, so a stale, superseded or unknown id
refuses here exactly as the relay would refuse it at send time. Host names and checkout paths are arguments.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
import types
from pathlib import Path

RELAY = "cade-handoff-relay"
RECIPIENT = "cade-delivery"
# The vendored relay's sha256 and the version line it prints: cade#222 merge 64f10799, pinned by lab
# vars/cade_handoff_relay.json at lab#3167 head 53e494ad. A re-vendor changes the sha, and write-map refuses until
# this table names it.
PINS = {
    "19b287a53596a85ba7d1d34a456790a18e02a8aa4b02445d6f1da699b860ba59": "cade-handoff-relay 0.1.0 (fab-dag-handoff/1)",
}
CONFIG_SCHEMA = "cade-handoff-relay-recipients/1"
DEFAULT_CONFIG = ".config/cade/handoff-relay.json"  # under HOME; lab vars/cade_handoff_relay.json unmanaged_config
INSTALL_PATH = ".local/bin/cade-handoff-relay"  # under HOME; lab vars/cade_handoff_relay.json install_path
PULL_STATE = ".local/state/tinyland/pull-switch"  # under HOME; lab LOCAL_CONSOLIDATION_DELIVERY.md section 7.2
DELIVERED = ".local/state/tinyland/hm-delivered.json"  # under HOME; written by nix-switch-local.sh (R-C136)
RULING = "R-DAG-20261030-a"
SEAT = "narrate"
HARNESS_KINDS = ("claude", "kimi", "codex", "junie", "opencode", "pi", "hermes", "kimicode")  # relay 0.1.0
ID_PART_RE = re.compile(r"\A[A-Za-z0-9._-]+\Z")
SHA_RE = re.compile(r"\A[0-9a-f]{40}\Z")
# An ssh destination: a host or user@host that cannot be read as an ssh option.
HOST_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._@-]{0,252}\Z")
# The verdicts lab hm-pull-switch.py writes to deployed.json (VERDICTS_SUCCESS at lab b2ce9ec9).
VERDICTS_SUCCESS = ("SWITCHED", "NO-OP")
EXEC_RE = re.compile(r'^\s*exec (\S+) -I (\S+) "\$@"\s*$', re.M)
SWB_RE = re.compile(r'^\s*export CADE_HANDOFF_RELAY_SWB="\$\{CADE_HANDOFF_RELAY_SWB:-(\S+)\}"\s*$', re.M)
STALE = {
    "recipient_unknown": "agent_id_unknown",
    "recipient_superseded": "agent_id_superseded",
    "recipient_stale": "agent_id_stale",
}
# The contexts a PASS needs: the plain remote command and the user's login shell (docs/spec/HANDOFF_RELAY_READBACK.md).
PASS_CONTEXTS = ("ssh", "login")
MAX_WRAPPER_BYTES = 65536
MAX_SCRIPT_BYTES = 1 << 20


class Refused(Exception):
    def __init__(self, code: str, where: str):
        super().__init__(f"{code}: {where}")
        self.code, self.where = code, where


def store_dir(env: dict) -> str:
    return (env.get("NIX_STORE_DIR") or "/nix/store").rstrip("/") + "/"


def home_of(env: dict) -> Path:
    return Path(env.get("HOME") or str(Path.home()))


def tilde(path, env: dict) -> str | None:
    """A path with HOME shown as ~, so a receipt carries no home directory."""
    if path is None:
        return None
    text, home = str(path), str(home_of(env))
    return "~" + text[len(home) :] if text == home or text.startswith(home + "/") else text


def sha256_file(path, limit: int) -> tuple[str, bytes]:
    data = Path(path).read_bytes()
    if len(data) > limit:
        raise Refused("file_too_large", str(path))
    return hashlib.sha256(data).hexdigest(), data


def read_json(path) -> dict | None:
    try:
        value = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def read_record(path, ignored: list) -> dict:
    """A delivery record, or {} with a note in `ignored` when the file exists and holds no JSON object."""
    value = read_json(path)
    if not value and os.path.lexists(path):
        ignored.append(f"{Path(path).name} holds no record")
    return value or {}


def in_context(command: str, env: dict, timeout: int = 30) -> subprocess.CompletedProcess:
    """`bash -c COMMAND`, as fab-agent-template mfg.py handoff_packet runs the notify command."""
    return subprocess.run(
        ["bash", "-c", command], env=env, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL
    )


def first_line(b: bytes) -> str:
    lines = b.decode("utf-8", "replace").strip().splitlines()
    return "".join(c if c.isprintable() else "?" for c in (lines[0] if lines else ""))[:200]


# ------------------------------------------------------------------ the installed relay


def locate(env: dict) -> str | None:
    r = in_context(f"command -v {RELAY}", env)
    path = r.stdout.decode("utf-8", "replace").strip()
    return path if r.returncode == 0 and path.startswith("/") else None


def wrapper(path: str, env: dict) -> dict:
    """What ~/.local/bin/cade-handoff-relay execs: lab's writeShellApplication wrapper (lab#3167)."""
    real = os.path.realpath(path)
    _sha, data = sha256_file(real, MAX_WRAPPER_BYTES)
    text = data.decode("utf-8", "replace")
    m = EXEC_RE.search(text)
    if not m:
        raise Refused("wrapper_unparsed", 'no `exec <python> -I <script> "$@"` line')
    interpreter, script = m.group(1), m.group(2)
    swb = SWB_RE.search(text)
    store = store_dir(env)
    script_sha, _ = sha256_file(script, MAX_SCRIPT_BYTES)
    v = subprocess.run([interpreter, "-V"], capture_output=True, timeout=15, stdin=subprocess.DEVNULL)
    return {
        "interpreter": interpreter,
        "interpreter_in_store": interpreter.startswith(store) and os.access(interpreter, os.X_OK),
        "interpreter_version": first_line(v.stdout or v.stderr) if v.returncode == 0 else None,
        "isolated": True,
        "script": script,
        "script_in_store": script.startswith(store),
        "script_sha256": script_sha,
        "pinned": script_sha in PINS,
        "swb": swb.group(1) if swb else None,
        "swb_executable": bool(swb) and os.access(swb.group(1), os.X_OK),
    }


def load_relay(script: str) -> types.ModuleType:
    """The installed relay as a module, from the bytes that hashed to a pin, so no other bytes run."""
    sha, data = sha256_file(script, MAX_SCRIPT_BYTES)
    if sha not in PINS:
        raise Refused("relay_pin_mismatch", f"the installed relay's sha256 {sha[:12]} is not pinned")
    mod = types.ModuleType("cade_handoff_relay")
    mod.__file__ = script
    sys.modules[mod.__name__] = mod
    try:
        exec(compile(data, script, "exec"), mod.__dict__)
    except Exception as e:  # any failure to load is one refusal
        raise Refused("relay_module_unloadable", type(e).__name__) from None
    finally:
        sys.modules.pop(mod.__name__, None)
    return mod


def relay_env(env: dict, info: dict) -> dict:
    """The environment the wrapper gives the relay: CADE_HANDOFF_RELAY_SWB defaults to lab's swb (`${VAR:-x}`)."""
    out = dict(env)
    if not out.get("CADE_HANDOFF_RELAY_SWB") and info.get("swb"):
        out["CADE_HANDOFF_RELAY_SWB"] = info["swb"]
    return out


def installed(env: dict) -> tuple[dict, types.ModuleType]:
    path = locate(env)
    if not path:
        raise Refused("relay_absent", f"`command -v {RELAY}` found nothing in this context")
    try:
        info = wrapper(path, env)
    except (OSError, subprocess.SubprocessError) as e:
        raise Refused("relay_unreadable", type(e).__name__) from None
    return info, load_relay(info["script"])


# ------------------------------------------------------------------ probe (read-only, on the host)


def active_generation(env: dict) -> str | None:
    """The store path Home Manager last finished activating (lab hm-pull-switch.py activated_generation_path)."""
    state = env.get("XDG_STATE_HOME") or str(home_of(env) / ".local/state")
    target = Path(state) / "home-manager" / "gcroots" / "current-home"
    if not target.is_symlink():
        return None
    try:
        for _ in range(8):
            if not target.is_symlink():
                break
            link = Path(os.readlink(target))
            target = link if link.is_absolute() else target.parent / link
    except OSError:
        return None
    return str(target) if target.is_dir() and not target.is_symlink() else None


def as_generation(value) -> int | None:
    """A Home Manager generation number. Lab writes it as a digit string (hm-pull-switch.py parse_generation and
    nix-switch-local.sh), so an int or a digit string counts. A bool or anything else is no generation."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, str) and value.isascii() and value.isdigit() and len(value) <= 18:
        return int(value)
    return None


def generation(env: dict, state_dir: Path, delivered: Path, hm_attr: str | None = None) -> dict:
    """The commit the running Home Manager generation came from: deployed.json or hm-delivered.json, whichever
    names the activated generation's store path (the newer when both do), as the pull-switch reads it.

    deployed.json counts only with a success verdict. hm-delivered.json counts only for this host's Home Manager
    attr and a clean tree, as lab local_switch_as_delivered requires. The attr is `hm_attr`, else the one
    deployed.json records. With no attr known, hm-delivered.json is ignored."""
    active = active_generation(env)
    records, ignored = [], []
    dep = read_record(state_dir / "deployed.json", ignored)
    rec = read_record(delivered, ignored)
    tick = read_json(state_dir / "tick.json") or {}
    attr = hm_attr or (dep.get("hm_attr") if isinstance(dep.get("hm_attr"), str) else None)
    if SHA_RE.match(str(dep.get("sha") or "")):
        if dep.get("verdict") not in VERDICTS_SUCCESS:
            ignored.append(f"deployed.json verdict {dep.get('verdict')}")
        else:
            records.append(
                {
                    "sha": dep["sha"],
                    "path": dep.get("after_path"),
                    "generation": as_generation(dep.get("after_gen")),
                    "before_generation": as_generation(dep.get("before_gen")),
                    "verdict": dep.get("verdict"),
                    "timestamp": str(dep.get("timestamp") or dep.get("finished_at") or ""),
                    "source": "pull-switch deployed.json",
                }
            )
    elif dep:
        ignored.append("deployed.json sha is missing or malformed")
    if SHA_RE.match(str(rec.get("head") or "")):
        if not attr or rec.get("attr") != attr:
            ignored.append(f"hm-delivered.json attr {rec.get('attr')} is not the host attr {attr}")
        elif rec.get("tree") != "clean":
            ignored.append(f"hm-delivered.json tree {rec.get('tree')}")
        else:
            records.append(
                {
                    "sha": rec["head"],
                    "path": rec.get("generation_path"),
                    "generation": as_generation(rec.get("generation")),
                    "tree": rec.get("tree"),
                    "timestamp": str(rec.get("timestamp") or ""),
                    "source": "hm-delivered.json",
                }
            )
    elif rec:
        ignored.append("hm-delivered.json head is missing or malformed")
    matching = [r for r in records if active and r["path"] == active]
    running = max(matching, key=lambda r: r["timestamp"]) if matching else None
    ignored += [f"{r['source']} is not the running record" for r in records if r is not running]
    return {
        "active_path": active,
        "hm_attr": attr,
        "running": running,
        "ignored": ignored,
        "deployed": {k: dep.get(k) for k in ("sha", "before_gen", "after_gen", "verdict", "finished_at")}
        if dep
        else None,
        "tick": {k: tick.get(k) for k in ("outcome", "timestamp") if k in tick} or None,
    }


def from_active(env: dict, active: str | None, command: str | None) -> bool | None:
    """True when the relay on PATH is the one the activated generation's home-files link."""
    if not active or not command:
        return None
    home = str(home_of(env))
    if not command.startswith(home + "/"):
        return False
    linked = Path(active) / "home-files" / command[len(home) + 1 :]
    try:
        return os.path.realpath(linked) == os.path.realpath(command) and linked.exists()
    except OSError:
        return False


def config_path_0_1_0(env: dict) -> Path | None:
    """The relay 0.1.0 config_path rule (cade 64f10799), for a probe that could not load the relay."""
    if env.get("CADE_HANDOFF_RELAY_CONFIG"):
        return Path(env["CADE_HANDOFF_RELAY_CONFIG"])
    base = env.get("XDG_CONFIG_HOME") or (str(Path(env["HOME"]) / ".config") if env.get("HOME") else "")
    return Path(base) / "cade" / "handoff-relay.json" if base else None


def mapping(env: dict, mod: types.ModuleType | None) -> dict:
    configured = mod.config_path(env) if mod else config_path_0_1_0(env)
    path = Path(configured) if configured else home_of(env) / DEFAULT_CONFIG
    out = {
        "path": tilde(path, env),
        "resolved_by": "relay" if mod else "relay 0.1.0 rule",
        "default": os.path.normpath(path) == os.path.normpath(home_of(env) / DEFAULT_CONFIG),
        "override_env": sorted(k for k in ("CADE_HANDOFF_RELAY_CONFIG", "XDG_CONFIG_HOME") if env.get(k)),
    }
    if not os.path.lexists(path):
        return {**out, "state": "absent"}
    st = os.lstat(path)
    out.update(
        state="present",
        link=stat.S_ISLNK(st.st_mode),
        mode=f"{stat.S_IMODE(st.st_mode):04o}",
        owner_is_user=st.st_uid == os.getuid(),
    )
    if stat.S_ISREG(st.st_mode):
        out["sha256"] = sha256_file(path, 65536)[0]
    if mod:
        try:
            cfg = mod.load_mapping(path)
            recipients = cfg.get("recipients") if isinstance(cfg, dict) else None
            entry = recipients.get(RECIPIENT, {}) if isinstance(recipients, dict) else None
            if isinstance(entry, dict):
                out["agent_id"] = entry.get("agent_id")
                out["delivery_key"] = entry.get("delivery_key")
            else:
                out["refusal"] = "recipient_config_invalid"
        except mod.Refusal as r:
            out["refusal"] = r.code
    return out


def probe(env: dict, via: str, hm_attr: str | None = None) -> dict:
    home = home_of(env)
    command = locate(env)
    out = {
        "schema": "narrate.relay-probe/v1",
        "via": via,
        "python": sys.version.split()[0],
        "child_justfile": any(Path(n).is_file() for n in ("justfile", "Justfile", ".justfile")),
        "command_v": tilde(command, env),
        "command_is_install_path": command == str(home / INSTALL_PATH),
    }
    v = in_context(f"{RELAY} --version", env)
    out["version"] = {"exit": v.returncode, "stdout": first_line(v.stdout)}
    mod = None
    if command:
        try:
            out["wrapper"] = wrapper(command, env)
            mod = load_relay(out["wrapper"]["script"]) if out["wrapper"]["pinned"] else None
        except (Refused, OSError, subprocess.SubprocessError) as e:
            out["wrapper"] = {"error": getattr(e, "code", type(e).__name__)}
    out["mapping"] = mapping(env, mod)
    gen = generation(env, home / PULL_STATE, home / DELIVERED, hm_attr)
    out["generation"] = gen
    out["relay_from_active_generation"] = from_active(env, gen["active_path"], command)
    return out


def evaluate(
    p: dict, merge: str, contains, since_gen: int | None = None, expect_agent_id: str | None = None
) -> list[tuple[str, bool, str]]:
    """One (check, ok, detail) per readback item. `contains(base, head)` is True when head contains base."""
    rows = []
    gen = p.get("generation") or {}
    run = gen.get("running")
    since = as_generation(since_gen)
    moved = bool(run) and contains(merge, run["sha"]) is True
    after = as_generation(run.get("generation")) if run else None
    if moved and run.get("source") == "pull-switch deployed.json":
        moved = run.get("verdict") in VERDICTS_SUCCESS
        if moved and run.get("verdict") == "SWITCHED":
            before = as_generation(run.get("before_generation"))
            moved = after is not None and before is not None and after > before
        elif moved and since is None:
            moved = False  # a NO-OP moved nothing, so only a baseline shows the generation is past it
    if moved and since_gen is not None:
        moved = since is not None and after is not None and after > since
    dep = gen.get("deployed") or {}
    ignored = f" (ignored: {'; '.join(gen['ignored'])})" if gen.get("ignored") else ""
    rows.append(
        (
            "generation_moved",
            moved,
            f"running {run['sha'][:12]} gen {after} from {run['source']}"
            + (f" tree {run.get('tree')}" if "tree" in run else "")
            + f"; deployed {dep.get('before_gen')}->{dep.get('after_gen')} {dep.get('verdict')}"
            + f"; since gen {since_gen}"
            + ignored
            if run
            else "no delivered record names the activated generation" + ignored,
        )
    )
    rows.append(
        (
            "relay_from_active_generation",
            p.get("relay_from_active_generation") is True,
            str(p.get("relay_from_active_generation")),
        )
    )
    rows.append(("command_v", bool(p.get("command_v")), f"{p.get('command_v')} via {p.get('via')}"))
    w = p.get("wrapper") or {}
    want = PINS.get(w.get("script_sha256") or "", next(iter(PINS.values())))
    ver = p.get("version") or {}
    rows.append(("version", ver.get("exit") == 0 and ver.get("stdout") == want, f"{ver.get('stdout')!r}"))
    rows.append(
        (
            "interpreter",
            bool(w.get("interpreter_in_store")) and bool(w.get("interpreter_version")),
            f"{w.get('interpreter') or w.get('error')} {w.get('interpreter_version')} -I",
        )
    )
    rows.append(
        (
            "script_pinned",
            bool(w.get("pinned")) and bool(w.get("script_in_store")),
            f"sha256 {str(w.get('script_sha256'))[:12]}",
        )
    )
    rows.append(("swb", bool(w.get("swb_executable")), str(w.get("swb"))))
    m = p.get("mapping") or {}
    rows.append(
        (
            "config_path_default",
            bool(m.get("default")),
            f"{m.get('path')} by {m.get('resolved_by')}, env set {m.get('override_env')}",
        )
    )
    if expect_agent_id is None:
        rows.append(("mapping_absent", m.get("state") == "absent", str(m.get("state"))))
    else:
        ok = (
            m.get("state") == "present"
            and not m.get("link")
            and m.get("mode") == "0600"
            and m.get("owner_is_user") is True
            and m.get("agent_id") == expect_agent_id
        )
        rows.append(
            (
                "mapping_written",
                ok,
                f"{m.get('state')} mode {m.get('mode')} agent_id {m.get('agent_id')}"
                + (f" refusal {m['refusal']}" if m.get("refusal") else ""),
            )
        )
    return rows


# ------------------------------------------------------------------ write-map (on the host)


def write_private(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0), 0o600)
    try:
        os.fchmod(fd, 0o600)
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view) :]
        os.fsync(fd)
    finally:
        os.close(fd)


def resolve(mod: types.ModuleType, path: Path, peers) -> str:
    try:
        return mod.resolve_recipient(RECIPIENT, path, peers)
    except mod.Refusal as r:
        raise Refused(STALE.get(r.code, r.code), r.where) from None


def existing_map_refusal(code: str, where: str) -> Refused:
    return Refused("existing_map_" + ("unsafe" if code.endswith("unsafe") else "invalid"), where)


def resolve_existing(mod: types.ModuleType, path: Path, peers) -> str:
    """resolve for the file already in place, where a recipient_config_* refusal means that file is bad."""
    try:
        return resolve(mod, path, peers)
    except Refused as r:
        if r.code.startswith("recipient_config_"):
            raise existing_map_refusal(r.code, f"{r.code}: {r.where}") from None
        raise


def write_map(
    env: dict,
    agent_id: str,
    write: bool,
    supersede_live: bool = False,
    allow_override: bool = False,
    now: str | None = None,
) -> dict:
    info, mod = installed(env)
    if not mod.valid_agent_id(agent_id):
        raise Refused("agent_id_invalid", "not harness:host:pid:session_id")
    configured = mod.config_path(env)
    if not configured:
        raise Refused("config_path_absent", "the relay resolves no mapping path (HOME is unset)")
    path = Path(configured)
    if path != home_of(env) / DEFAULT_CONFIG and not allow_override:
        raise Refused("config_path_override", f"the relay reads {tilde(path, env)} in this context")
    renv = relay_env(env, info)
    try:
        peers = mod.swb_peers(mod.swb_binary(renv), renv)
    except mod.Refusal as r:
        raise Refused(r.code, r.where) from None
    others, previous, previous_state = {}, None, None
    if os.path.lexists(path):
        try:
            cfg = mod.load_mapping(path)
        except mod.Refusal as r:
            raise existing_map_refusal(r.code, r.code) from None
        others = {k: v for k, v in cfg["recipients"].items() if k != RECIPIENT}
        if RECIPIENT in cfg["recipients"]:
            entry = cfg["recipients"][RECIPIENT]
            if not isinstance(entry, dict):
                raise existing_map_refusal("recipient_config_invalid", f"recipients.{RECIPIENT} is not an object")
            previous = entry.get("agent_id") or entry.get("delivery_key")
            if previous == agent_id:
                resolve_existing(mod, path, peers)
                st = os.lstat(path)
                return {
                    "schema": "narrate.relay-map/v1",
                    "result": "unchanged",
                    "path": tilde(path, env),
                    "sha256": sha256_file(path, 65536)[0],
                    "mode": f"{stat.S_IMODE(st.st_mode):04o}",
                    "agent_id": agent_id,
                    "previous_agent_id": previous,
                    "previous_state": "live",
                }
            try:
                resolve_existing(mod, path, peers)
                previous_state = "live"
            except Refused as r:
                if r.code not in STALE.values():  # any other refusal says nothing about the holder, so it stays
                    raise
                previous_state = r.code
            if previous_state == "live" and not supersede_live:
                raise Refused("map_held_by_live_session", f"{previous} is live; pass --supersede-live to replace it")
    now = now or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    entry = {"agent_id": agent_id, "seat": SEAT, "ruling": RULING, "updated_utc": now}
    data = (json.dumps({"schema": CONFIG_SCHEMA, "recipients": {**others, RECIPIENT: entry}}, indent=1) + "\n").encode()
    receipt = {
        "schema": "narrate.relay-map/v1",
        "path": tilde(path, env),
        "sha256": hashlib.sha256(data).hexdigest(),
        "mode": "0600",
        "agent_id": agent_id,
        "previous_agent_id": previous,
        "previous_state": previous_state,
        "updated_utc": now,
    }
    if not write:
        scratch = Path(tempfile.mkdtemp(prefix="relay-map-"))
        try:
            write_private(scratch / "handoff-relay.json", data)
            resolve(mod, scratch / "handoff-relay.json", peers)
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
        return {**receipt, "result": "dry-run"}
    if not path.parent.exists():
        if not path.parent.parent.is_dir():
            raise Refused("config_dir_absent", f"{tilde(path.parent.parent, env)} does not exist")
        os.mkdir(path.parent, 0o700)
    tmp = path.parent / f".handoff-relay.json.{os.getpid()}.tmp"
    write_private(tmp, data)
    try:
        resolve(mod, tmp, peers)
        os.replace(tmp, path)
    finally:
        if os.path.lexists(tmp):
            os.unlink(tmp)
    dfd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)
    if resolve(mod, path, peers) != agent_id:
        raise Refused("agent_id_mismatch", "the relay resolves a different id after the write")
    st = os.lstat(path)
    return {**receipt, "result": "written", "mode": f"{stat.S_IMODE(st.st_mode):04o}"}


# ------------------------------------------------------------------ drivers (at the narrate seat)


def valid_agent_id(agent_id) -> bool:
    parts = agent_id.split(":") if isinstance(agent_id, str) and len(agent_id) <= 512 else []
    return (
        len(parts) == 4
        and parts[0] in HARNESS_KINDS
        and parts[2].isascii()
        and parts[2].isdigit()
        and all(ID_PART_RE.match(x) for x in parts[1:])
    )


def remote_command(child_repo: str, context: str, args: list[str]) -> str:
    """The command for the host's shell: cd into the child repo, then `just --command python3 -I - ARGS`, the
    script on stdin. `login` wraps it in the user's login shell, so lab-rendered PATH lines load."""
    where = '"$HOME"/' + shlex.quote(child_repo[2:]) if child_repo.startswith("~/") else shlex.quote(child_repo)
    inner = f"cd {where} && exec just --command python3 -I - " + " ".join(shlex.quote(a) for a in args)
    return 'exec "$SHELL" -lc ' + shlex.quote(inner) if context == "login" else inner


def run_on(host: str, child_repo: str, context: str, args: list[str], timeout: int = 120) -> dict:
    if context != "local" and not HOST_RE.match(host or ""):
        raise Refused("host_invalid", "a host or user@host that does not start with '-'")
    source = Path(__file__).read_bytes()
    if context == "local":
        cmd, cwd = ["just", "--command", "python3", "-I", "-", *args], os.path.expanduser(child_repo)
    else:
        cmd = [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=15",
            host,
            "--",
            remote_command(child_repo, context, args),
        ]
        cwd = None
    try:
        r = subprocess.run(cmd, input=source, capture_output=True, timeout=timeout, cwd=cwd)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise Refused("probe_failed", type(e).__name__) from None
    lines = r.stdout.decode("utf-8", "replace").strip().splitlines()
    try:
        out = json.loads(lines[-1]) if lines else None
    except ValueError:
        out = None
    if not isinstance(out, dict):
        raise Refused("probe_failed", f"exit {r.returncode}: {first_line(r.stderr)}")
    out["exit"] = r.returncode
    return out


def gh_contains(lab_repo: str):
    def contains(base: str, head: str) -> bool | None:
        try:
            r = subprocess.run(
                ["gh", "api", f"repos/{lab_repo}/compare/{base}...{head}", "--jq", ".status"],
                capture_output=True,
                timeout=60,
                stdin=subprocess.DEVNULL,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        status = r.stdout.decode("utf-8", "replace").strip()
        return status in ("ahead", "identical") if r.returncode == 0 and status else None

    return contains


def shown_host(host: str, context: str) -> str:
    """The host a row or receipt names. The local context runs on this machine, whatever --host says."""
    return local_host() if context == "local" else host


def readback(a, contains=None) -> int:
    contains = contains or gh_contains(a.lab_repo)
    report, ok_all = [], True
    contexts = a.context or list(PASS_CONTEXTS)
    for context in contexts:
        try:
            hm_attr = getattr(a, "hm_attr", None)
            p = run_on(
                a.host, a.child_repo, context, ["probe", "--via", context] + (["--hm-attr", hm_attr] if hm_attr else [])
            )
            if p.get("refused"):
                raise Refused(p["refused"], p.get("where", ""))
            rows = evaluate(p, a.merge, contains, a.since_gen, a.expect_agent_id)
        except Refused as r:
            p, rows = None, [("probe", False, f"{r.code}: {r.where}")]
        ok_all &= all(ok for _, ok, _ in rows)
        report.append(
            {
                "host": shown_host(a.host, context),
                "context": context,
                "probe": p,
                "checks": [{"check": c, "ok": ok, "detail": d} for c, ok, d in rows],
            }
        )
    missing = [c for c in PASS_CONTEXTS if c not in contexts]
    verdict = "FAIL" if not ok_all else "PARTIAL" if missing else "PASS"
    if a.json:
        print(
            json.dumps(
                {
                    "schema": "narrate.relay-readback/v1",
                    "merge": a.merge,
                    "verdict": verdict,
                    "contexts_not_run": missing,
                    "rows": report,
                },
                indent=1,
            )
        )
    else:
        print("| host | context | check | ok | detail |\n|---|---|---|---|---|")
        for item in report:
            for c in item["checks"]:
                print(
                    f"| {item['host']} | {item['context']} | {c['check']} | {'yes' if c['ok'] else 'NO'} "
                    f"| {c['detail']} |"
                )
        hosts = ", ".join(dict.fromkeys(item["host"] for item in report))
        print(f"\nreadback {hosts} at lab {a.merge[:12]}: {verdict}")
        if verdict == "PARTIAL":
            print(f"not run: {', '.join(missing)}")
    return 0 if verdict == "PASS" else 1


def swb_whoami(env: dict) -> str | None:
    """This session's agent id as `swb whoami` builds it, without --register, so nothing is written."""
    swb = shutil.which("swb", path=env.get("PATH"))
    if not swb:
        return None
    try:
        r = subprocess.run([swb, "whoami"], env=env, capture_output=True, timeout=15, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None
    lines = r.stdout.decode("utf-8", "replace").strip().splitlines()
    try:
        value = json.loads(lines[-1]) if r.returncode == 0 and lines else None
    except ValueError:
        return None
    agent_id = value.get("agent_id") if isinstance(value, dict) else None
    return agent_id if isinstance(agent_id, str) else None


def local_host() -> str:
    return socket.gethostname().split(".")[0]


def parent_pid(pid: int) -> int | None:
    try:
        return int(Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[1])
    except (OSError, ValueError, IndexError):
        pass
    try:
        r = subprocess.run(
            ["ps", "-o", "ppid=", "-p", str(pid)], capture_output=True, timeout=5, stdin=subprocess.DEVNULL
        )
        return int(r.stdout.decode().strip()) if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def ancestor_pids() -> list[int]:
    out, pid = [], os.getpid()
    for _ in range(64):
        pid = parent_pid(pid)
        if not pid or pid in out:
            break
        out.append(pid)
        if pid == 1:
            break
    return out


def command_of(pid: int) -> list[str]:
    """The pid's argv. The `ps` fallback splits on whitespace, which is exact for the first two words."""
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
        return [x.decode("utf-8", "replace") for x in raw.split(b"\0") if x]
    except OSError:
        pass
    try:
        r = subprocess.run(
            ["ps", "-o", "command=", "-p", str(pid)], capture_output=True, timeout=5, stdin=subprocess.DEVNULL
        )
        return r.stdout.decode("utf-8", "replace").split() if r.returncode == 0 else []
    except (OSError, subprocess.SubprocessError):
        return []


def runs_harness(argv: list[str], harness: str) -> bool:
    """True when the program, or the script an interpreter runs, is named for the harness: `harness` is a whole
    `-`, `_` or `.` separated word of the basename of argv[0] or argv[1]. A substring is not enough, so `pi`
    matches `pi` or `pi-agent` and not `pip` or `python3 -m pip`."""
    for word in argv[:2]:
        base = word.rstrip("/").rsplit("/", 1)[-1].lstrip("-")
        if harness in re.split(r"[-_.]", base):
            return True
    return False


def self_id(env: dict) -> str:
    """The calling session's own id. `swb whoami` names it, and the id's host, pid and harness must be this
    machine, an ancestor of this process and that ancestor's command. A typed id is never the source."""
    own = swb_whoami(env)
    if not own:
        raise Refused("agent_id_missing", "`swb whoami` names no id for this session; a typed id is not accepted")
    if not valid_agent_id(own):
        raise Refused("agent_id_invalid", "`swb whoami` printed an id that is not harness:host:pid:session_id")
    harness, host, pid, _session = own.split(":")
    if host.lower() != local_host().lower():
        raise Refused("agent_id_not_self", "the id's host is not this machine")
    if int(pid) not in ancestor_pids():
        raise Refused("agent_id_not_self", "the id's pid is not an ancestor of this process")
    if not runs_harness(command_of(int(pid)), harness):
        raise Refused("agent_id_not_self", f"the id's pid does not run {harness}")
    return own


def map_driver(a, env: dict) -> dict:
    agent_id = self_id(env)
    for given, name in ((a.agent_id, "--agent-id"), (env.get("SWB_AGENT_ID"), "SWB_AGENT_ID")):
        if given and given != agent_id:
            raise Refused("agent_id_not_self", f"{name} is not this session's own id; narrate writes only its own")
    args = (
        ["write-map", "--agent-id", agent_id]
        + (["--write"] if a.write else [])
        + (["--supersede-live"] if a.supersede_live else [])
    )
    out = run_on(a.host, a.child_repo, a.context, args)
    if out.get("refused"):
        raise Refused(out["refused"], out.get("where", ""))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="relay", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("probe", help="read-only probe, on a producer host")
    pr.add_argument("--via", default="local")
    pr.add_argument("--hm-attr", help="this host's Home Manager attr; default: the one deployed.json records")
    wm = sub.add_parser("write-map", help="write the cade-delivery entry, on a producer host")
    wm.add_argument("--agent-id", required=True)
    wm.add_argument("--write", action="store_true")
    wm.add_argument("--supersede-live", action="store_true")
    wm.add_argument("--allow-config-override", action="store_true")
    for name in ("readback", "map"):
        d = sub.add_parser(name)
        d.add_argument("--host", required=True)
        d.add_argument("--child-repo", required=True, help="the child repo checkout on that host")
        d.add_argument("--json", action="store_true")
    rb, mp = sub.choices["readback"], sub.choices["map"]
    rb.add_argument("--merge", required=True, help="the lab#3167 merge commit")
    rb.add_argument("--context", action="append", choices=("ssh", "login", "local"))
    rb.add_argument(
        "--since-gen", type=int, required=True, help="the host's generation before the merge's switch (spec step 2)"
    )
    rb.add_argument("--expect-agent-id")
    rb.add_argument("--hm-attr", help="the host's Home Manager attr, for hm-delivered.json")
    rb.add_argument("--lab-repo", default="xoxd-ai/lab")
    mp.add_argument("--agent-id", help="optional; must equal this session's own id")
    mp.add_argument("--write", action="store_true")
    mp.add_argument("--supersede-live", action="store_true")
    mp.add_argument("--context", default="login", choices=("ssh", "login", "local"))
    a = ap.parse_args(argv)
    env = dict(os.environ)
    try:
        if a.cmd == "probe":
            print(json.dumps(probe(env, a.via, a.hm_attr)))
            return 0
        if a.cmd == "write-map":
            print(json.dumps(write_map(env, a.agent_id, a.write, a.supersede_live, a.allow_config_override)))
            return 0
        if a.cmd == "readback":
            if not SHA_RE.match(a.merge):
                raise Refused("merge_invalid", "--merge is a full commit id")
            return readback(a)
        out = map_driver(a, env)
        print(
            json.dumps(out, indent=1)
            if a.json
            else f"map {shown_host(a.host, a.context)}: {out['result']} {out['path']} mode {out['mode']} "
            f"agent_id {out['agent_id']} (previous {out.get('previous_agent_id')}: {out.get('previous_state')}) "
            f"sha256 {out['sha256'][:12]}"
        )
        return 0
    except Refused as r:
        if a.cmd in ("probe", "write-map"):
            print(json.dumps({"refused": r.code, "where": r.where}))
        print(f"relay {a.cmd}: refused: {r.code}: {r.where}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
