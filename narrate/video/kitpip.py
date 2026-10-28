"""kitpip as a pinned external binary, and the avatar and avatar_check stages that run it (docs/spec/NARRATED_VIDEO.md,
NV-1, lane L5).

kitpip is never a flake input and never vendored. program/externals.json registers it publicly: the record shape,
the manifest schema, the timeline mapping and how a binary resolves, with no pin values. The pin itself is a private
externals record (NARRATED_VIDEO_EXTERNALS or --externals), shaped like the test-only record
narrate/tests/fixtures/narrated-video/kitpip-externals.json: the version, the source commit, per-system binary
digests and byte counts, the manifest schema, the timeline mapping and the default rig. A pin whose release binary
does not exist yet pins the commit and leaves its binary table empty (gate_state commit_pinned_digest_pending);
it resolves `pending` and blocks the avatar stages. The binary comes from KITPIP_BIN. Before every spawn its SHA-256
and size are checked against the pin; a mismatch refuses kitpip_pin_mismatch and nothing runs.

kitpip prints one JSON line on stdout: a result (exit 0), {"refused": code, "detail": ...} (exit 1) or
{"error": ...} (exit 2). The wrapper relays a refusal as KitpipRefused with kitpip's own code, which the CLI prints
in the narrate stderr shape. It never passes --allow-unlabelled-test, --pipe or --badge: the overlay is kitpip's
unadorned default character (KP-19) with no visible label (KP-7, KP-15).

A refusal is a verdict or a failure. A verdict (kitpip's own refusal line, or the wrapper's checks on a finished
overlay: kitpip_unlabelled, label_chain_broken, a schema or rig that is not the keyed one) repeats for the same
stage key, because the key holds the binary digest, the rig, the persona and the narration digest; the store
records it and the node stays refused until its key changes. A failure (kitpip_timeout, kitpip_error,
kitpip_missing, or a binary that fails its pin at spawn) says nothing about the key: the partial is removed, nothing
is recorded and the node stays stale, so calling run again retries it.

The avatar stage runs `analyze` on a segment's narrate run, then `render` and `verify`, all into the stage's
partial directory under the job store, never inside the narrate run and never under artifacts/runs/. The command
shape is kitpip's at the pinned commit: `analyze RUN --fps N/D --rig ID --out DIR`, `render PROSODY --rig ID --size
WxH --encode mov --out DIR` and `verify DIR`. Its manifest uses timeline mapping avatar_overlay_v1. avatar_check
re-runs `verify` on the stored overlay and checks the label chain against the segment's narration. Public CI runs
the stub (narrate/tests/fixtures/narrated-video/kitpip_stub.py).
"""

import json
import os
import platform
import re
import subprocess
from pathlib import Path

from ..config import in_guitar_runs
from ..ir import sha256_file
from . import labels
from .common import StageRefused, upstream, write_json
from .graph import knobs_for
from .job import JobError, read_json

EXTERNALS_ENV = "NARRATED_VIDEO_EXTERNALS"
BIN_ENV = "KITPIP_BIN"
MANIFEST_SCHEMA = "kitpip.manifest/v0"
MAPPING = "avatar_overlay_v1"
FORBIDDEN_FLAGS = ("--allow-unlabelled-test", "--pipe", "--badge")
TIMEOUT_S = 900
REGISTRY = Path(__file__).resolve().parents[2] / "program" / "externals.json"
VISIBILITIES = ("private", "test_fixture")
PENDING = "commit_pinned_digest_pending"
HEX40 = re.compile(r"[0-9a-f]{40}")
HEX64 = re.compile(r"[0-9a-f]{64}")
NARRATION = "narration"  # the narrate run directory inside a voice stage directory (speech.RUN)


class KitpipRefused(JobError):
    """kitpip, or the wrapper around it, refused. code is kitpip's own code or one the wrapper adds. verdict is
    True when the same key would refuse again (the store records it) and False for a failure a retry may clear."""

    def __init__(self, code, detail, verdict=True):
        super().__init__(code, detail)
        self.verdict = verdict


def system():
    machine = {"amd64": "x86_64", "arm64": "aarch64"}.get(platform.machine().lower(), platform.machine().lower())
    return f"{machine}-{platform.system().lower()}"


def no_locator(value, where="pin"):
    """Refuse a URL, an absolute path or a home path anywhere in a pin: it holds digests and ids only (NV-1)."""
    if isinstance(value, dict):
        for k, v in value.items():
            no_locator(v, f"{where}.{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            no_locator(v, f"{where}[{i}]")
    elif isinstance(value, str) and ("://" in value or value.startswith(("/", "~")) or "@" in value):
        raise JobError("externals_invalid", f"{where} holds a URL, path or host; a pin holds digests and ids only")


def load_registry(path=REGISTRY):
    """The public kitpip registration in program/externals.json: shape and resolution rules, never pin values."""
    record = read_json(path, "externals registry")
    entry = (record.get("externals") or {}).get("kitpip") if isinstance(record, dict) else None
    if record.get("schema_version") != 1 or not isinstance(entry, dict):
        raise JobError("externals_invalid", "program/externals.json has no schema_version 1 kitpip entry")
    leaked = sorted(set(entry) & {"source_commit", "binaries", "default_rig", "version"})
    if entry.get("pin") != "private_record" or leaked:
        raise JobError("externals_invalid", f"the public kitpip entry holds pin values {leaked} (NV-1)")
    return entry


def load_pin(path):
    """The kitpip entry of an externals record, or None when no record is named."""
    if path is None:
        return None
    record = read_json(path, "externals")
    if not isinstance(record, dict) or not isinstance(record.get("externals"), dict):
        raise JobError("externals_invalid", "the externals record is not an object with an externals table")
    pin = record["externals"].get("kitpip")
    if record.get("schema_version") != 1 or not isinstance(pin, dict):
        raise JobError("externals_invalid", "the externals record has no schema_version 1 kitpip entry")
    for field in (
        "version",
        "source_commit",
        "manifest_schema",
        "timeline_mapping",
        "binaries",
        "default_rig",
        "visibility",
        "gate_state",
    ):
        if field not in pin:
            raise JobError("externals_invalid", f"the kitpip pin has no {field}")
    if pin["manifest_schema"] != MANIFEST_SCHEMA or pin["timeline_mapping"] != MAPPING:
        raise JobError("externals_invalid", f"the kitpip pin is not {MANIFEST_SCHEMA} with {MAPPING}")
    if pin["visibility"] not in VISIBILITIES:
        raise JobError("externals_invalid", f"the kitpip pin's visibility is not one of {', '.join(VISIBILITIES)}")
    if not isinstance(pin["source_commit"], str) or not HEX40.fullmatch(pin["source_commit"]):
        raise JobError("externals_invalid", "the kitpip pin's source_commit is not a full 40-hex commit")
    rig = pin["default_rig"]
    if not isinstance(rig, dict) or not isinstance(rig.get("id"), str) or not HEX64.fullmatch(str(rig.get("sha256"))):
        raise JobError("externals_invalid", "the kitpip pin's default_rig needs an id and a 64-hex sha256")
    table = pin["binaries"].get("kitpip") if isinstance(pin["binaries"], dict) else None
    if not isinstance(table, dict):
        raise JobError("externals_invalid", "the kitpip pin has no binaries.kitpip table")
    for name, entry in table.items():
        if (
            not isinstance(entry, dict)
            or not HEX64.fullmatch(str(entry.get("sha256")))
            or not isinstance(entry.get("bytes"), int)
            or entry["bytes"] < 1
        ):
            raise JobError("externals_invalid", f"binaries.kitpip.{name} needs a 64-hex sha256 and a byte count")
    if not table and pin["gate_state"] != PENDING:
        raise JobError("externals_invalid", f"a pin with no binary digest must say gate_state {PENDING}")
    no_locator(pin)
    return pin


def binary_pin(pin):
    """The pinned {sha256, bytes} of the kitpip binary for this system. 'any' serves only a test fixture pin."""
    table = pin["binaries"].get("kitpip", {})
    entry = table.get(system())
    if entry is None and pin["visibility"] == "test_fixture":
        entry = table.get("any")
    return entry


def resolve(pin, env=None):
    """{state, binary, tool, detail}. state: unregistered (no pin), pending (the pin names a commit whose release
    binary digest is not recorded yet), missing (no binary for this system or no KITPIP_BIN file), mismatch (digest
    or size differs) or resolved. tool is the identity a stage key holds."""
    env = os.environ if env is None else env
    if pin is None:
        return {"state": "unregistered", "binary": None, "tool": None, "detail": "no kitpip pin is registered"}
    want = binary_pin(pin)
    tool = {"name": "kitpip", "version": pin["version"], "binary_sha256": want["sha256"] if want else None}
    if want is None and pin["gate_state"] == PENDING:
        detail = f"the pin names commit {pin['source_commit'][:12]}; its release binary digest is pending"
        return {"state": "pending", "binary": None, "tool": tool, "detail": detail}
    if want is None:
        return {"state": "missing", "binary": None, "tool": tool, "detail": f"the pin has no binary for {system()}"}
    path = env.get(BIN_ENV)
    if not path or not Path(path).is_file():
        return {"state": "missing", "binary": None, "tool": tool, "detail": f"{BIN_ENV} names no file"}
    real = Path(path).resolve()
    if real.stat().st_size != want["bytes"] or sha256_file(real) != want["sha256"]:
        return {"state": "mismatch", "binary": None, "tool": tool, "detail": "the binary's digest is not its pin's"}
    return {"state": "resolved", "binary": str(real), "tool": tool, "detail": None}


def call(resolution, pin, args, timeout_s=TIMEOUT_S):
    """Run one kitpip command after re-checking the binary against its pin. The parsed stdout result on exit 0."""
    if any(flag in args for flag in FORBIDDEN_FLAGS):
        raise KitpipRefused("contract_invalid", "the wrapper never passes a CLI-only kitpip flag")
    again = resolve(pin, {BIN_ENV: resolution.get("binary") or ""})
    if again["state"] != "resolved":
        code = "kitpip_pin_mismatch" if again["state"] == "mismatch" else "kitpip_missing"
        raise KitpipRefused(code, again["detail"], verdict=False)
    try:
        done = subprocess.run(
            [again["binary"], *args],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
            env={"PATH": os.environ.get("PATH", ""), "LC_ALL": "C"},
        )
    except subprocess.TimeoutExpired:
        raise KitpipRefused("kitpip_timeout", f"kitpip {args[0]} ran past {timeout_s} s", verdict=False) from None
    lines = [line for line in done.stdout.splitlines() if line.strip()]
    try:
        result = json.loads(lines[-1]) if lines else None
    except json.JSONDecodeError:
        result = None
    if done.returncode == 1 and isinstance(result, dict) and isinstance(result.get("refused"), str):
        raise KitpipRefused(result["refused"], str(result.get("detail", "")))
    if done.returncode != 0 or not isinstance(result, dict):
        raise KitpipRefused("kitpip_error", f"kitpip {args[0]} exited {done.returncode}", verdict=False)
    return result


def narration(run_dir):
    """The narrate manifest of a run, with the labels kitpip's admission reads."""
    manifest = read_json(Path(run_dir) / "manifest.json", "narrate run")
    voices = manifest.get("voices", [])
    return manifest, sorted({v["consent_id"] for v in voices}), sorted({v["voice"] for v in voices})


def guard_partial(store, partial, narrate_run):
    """Refuse avatar_outside_store unless partial lies in the job store, outside the narrate run and artifacts/runs/."""
    partial, narrate_run = Path(partial).resolve(), Path(narrate_run).resolve()
    if (
        narrate_run == partial
        or narrate_run in partial.parents
        or in_guitar_runs(partial)
        or store.dir.resolve() not in partial.parents
    ):
        raise KitpipRefused("avatar_outside_store", "kitpip writes only inside the job store")


def render_overlay(partial, narrate_run, fps, rig, render_size, persona, resolution, pin, timeout_s, rig_sha256):
    """analyze, render and verify one segment's narration into partial. The stage manifest fields."""
    narrate_run = Path(narrate_run).resolve()
    manifest, consent_ids, voice_ids = narration(narrate_run)
    fps_arg = f"{fps['num']}/{fps['den']}"
    call(
        resolution,
        pin,
        ["analyze", str(narrate_run), "--fps", fps_arg, "--rig", rig, "--out", str(partial / "analyze")],
        timeout_s,
    )
    call(
        resolution,
        pin,
        [
            "render",
            str(partial / "analyze" / "prosody.json"),
            "--rig",
            rig,
            "--size",
            f"{render_size}x{render_size}",
            "--encode",
            "mov",
            "--out",
            str(partial / "overlay"),
        ],
        timeout_s,
    )
    verdict = call(resolution, pin, ["verify", str(partial / "overlay")], timeout_s)
    if verdict.get("labelled") is not True:
        raise KitpipRefused("kitpip_unlabelled", "kitpip verify did not report labelled: true")
    overlay = read_json(partial / "overlay" / "manifest.json", "kitpip manifest")
    overlay_rig = overlay.get("rig") if isinstance(overlay.get("rig"), dict) else {}
    if overlay.get("schema") != pin["manifest_schema"] or overlay_rig.get("id") != rig:
        raise KitpipRefused("kitpip_pin_mismatch", "the overlay manifest's schema or rig is not the pinned one")
    if rig_sha256 is not None and overlay_rig.get("sha256") != rig_sha256:
        raise KitpipRefused("kitpip_pin_mismatch", "the overlay's rig revision is not the one the stage key holds")
    if (
        overlay.get("synthetic") is not True
        or sorted(overlay.get("consent_ids", [])) != consent_ids
        or sorted(overlay.get("voice_ids", [])) != voice_ids
    ):
        raise KitpipRefused("label_chain_broken", "the overlay dropped or altered the narration's labels")
    return {
        "measurements": {
            "frames": overlay["frames"],
            "frames_sha256": overlay.get("frames_sha256"),
            "fps": fps,
            "size": overlay["size"],
            "rig": {"id": overlay_rig.get("id"), "sha256": overlay_rig.get("sha256")},
            "show_badge": overlay.get("show_badge", False),
        },
        "labels": {"synthetic": True, "consent_ids": consent_ids, "voice_ids": voice_ids, "persona": persona},
        "synthetic": True,
        "timeline": {
            "mapping": MAPPING,
            "no_time_stretch": False,
            "stretch_applied": False,
            "fps": fps,
            "total_frames": overlay["frames"],
            "narration": {"run_id": manifest["run_id"], "content_sha256": manifest["content_sha256"]},
            "output_axis": "overlay frame index / fps on its segment's narration clock; compose places frame 0 "
            "at the segment anchor",
            "source_axis": "none: the overlay is drawn from narration loudness; no source media is time-stretched",
        },
        "states": {
            "source_checks": "passed",
            "render": "stub" if pin["visibility"] == "test_fixture" else "local",
            "lip_sync": "pending_operator",
        },
    }


def run_avatar(
    store,
    node_id,
    key,
    document,
    narrate_run,
    fps,
    rig,
    render_size,
    persona,
    resolution,
    pin,
    timeout_s=TIMEOUT_S,
    rig_sha256=None,
):
    """The avatar stage for one segment outside the executor: begin, render the overlay, commit.

    rig_sha256 is the rig revision the stage key holds (knobs.rigRevisionSha256). When it is set, the overlay's
    rig must report that revision. When it is None (a rig other than the pin's default, with no revision in the
    job), the manifest records the revision kitpip reports."""
    guard_partial(store, store.partial_dir(node_id, key), narrate_run)
    partial = store.begin(node_id, key)
    try:
        fields = render_overlay(
            partial, narrate_run, fps, rig, render_size, persona, resolution, pin, timeout_s, rig_sha256
        )
        return store.commit(node_id, key, document, fields)
    except KitpipRefused as exc:
        store.abort(node_id, key)
        if exc.verdict:
            store.record_refusal(node_id, key, exc.code, exc.detail)
        raise
    except BaseException:
        store.abort(node_id, key)
        raise


def stage_context(rc):
    pin, resolution = rc.ctx.get("pin"), rc.ctx.get("kitpip")
    if pin is None or not resolution or resolution.get("state") != "resolved":
        raise KitpipRefused("kitpip_missing", "no resolved kitpip binary for its pin", verdict=False)
    return pin, resolution


def run_avatar_stage(rc, row, partial):
    """The executor's avatar runner (run.RUNNERS): one segment's overlay from its narrate run, at the base's fps."""
    pin, resolution = stage_context(rc)
    segment = next(s for s in rc.job["segments"] if s["id"] == row["segment"])
    _, voice_dir = upstream(rc.store, f"voice/{segment['id']}")
    base, _ = upstream(rc.store, "base")
    knobs = knobs_for("avatar", segment, rc.job, rc.records, pin)
    narrate_run = voice_dir / NARRATION
    guard_partial(rc.store, partial, narrate_run)
    return render_overlay(
        partial,
        narrate_run,
        base["measurements"]["fps"],
        knobs["rig"],
        knobs["renderSize"],
        knobs["persona"],
        resolution,
        pin,
        TIMEOUT_S,
        knobs["rigRevisionSha256"],
    )


def run_avatar_check(rc, row, partial):
    """The executor's avatar_check runner: kitpip verify on the stored overlay, then the label chain.

    The overlay must re-hash under kitpip's own manifest, report labelled: true, keep the frame digest the avatar
    stage measured and carry the narration's consent ids. The labels must hold everything the voice and avatar
    stages carry, with the job's persona."""
    pin, resolution = stage_context(rc)
    segment = row["segment"]
    voice, _ = upstream(rc.store, f"voice/{segment}")
    avatar, avatar_dir = upstream(rc.store, f"avatar/{segment}")
    verdict = call(resolution, pin, ["verify", str(avatar_dir / "overlay")], TIMEOUT_S)
    if verdict.get("labelled") is not True:
        raise KitpipRefused("kitpip_unlabelled", "kitpip verify did not report labelled: true")
    frames_sha256 = avatar["measurements"].get("frames_sha256")
    if "frames_sha256" in verdict and verdict["frames_sha256"] != frames_sha256:
        raise KitpipRefused("label_chain_broken", "the stored overlay's frames are not the ones the avatar measured")
    want = labels.of(avatar)["consent_ids"]
    if "consent_ids" in verdict and sorted(verdict["consent_ids"]) != want:
        raise KitpipRefused("label_chain_broken", "the overlay's consent ids are not the narration's")
    persona = rc.job["labels"]["persona"]
    grown = labels.grow([voice, avatar], persona)
    try:
        labels.check(grown, [voice, avatar], persona)
    except StageRefused as exc:
        raise KitpipRefused(exc.code, exc.detail) from None
    write_json(
        partial / "check.json",
        {
            "verified": True,
            "labelled": True,
            "frames_sha256": frames_sha256,
            "consent_ids": grown["consent_ids"],
            "avatar_content_sha256": avatar["content_sha256"],
        },
    )
    return {
        "synthetic": True,
        "measurements": {"labelled": True, "frames_sha256": frames_sha256},
        "labels": grown,
        "states": {"source_checks": "passed", "lip_sync": "pending_operator"},
    }


def pin_check(pin, env=None, registry=REGISTRY):
    """kitpip pin-check: the public registration, the private pin against it, and KITPIP_BIN against the pin.

    {ok, state, pin: {version, source_commit, gate_state, default_rig}, binary_sha256, detail}. ok only when the
    binary resolves. A pin with no release binary yet is state pending: the commit is pinned, the digest is not."""
    entry = load_registry(registry)
    if pin is None:
        return {"ok": False, "state": "unregistered", "detail": f"no pin record: set {EXTERNALS_ENV}"}
    for field in ("manifest_schema", "timeline_mapping"):
        if pin[field] != entry[field]:
            raise JobError("externals_invalid", f"the pin's {field} is not the registered one")
    resolution = resolve(pin, env)
    return {
        "ok": resolution["state"] == "resolved",
        "state": resolution["state"],
        "pin": {k: pin[k] for k in ("version", "source_commit", "gate_state", "default_rig", "visibility")},
        "binary_sha256": (resolution["tool"] or {}).get("binary_sha256"),
        "detail": resolution["detail"],
    }
