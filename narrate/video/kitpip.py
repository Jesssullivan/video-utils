"""kitpip as a pinned external binary, and the avatar stage that runs it (docs/spec/NARRATED_VIDEO.md, NV-1).

kitpip is never a flake input and never vendored. Its pin is a private externals record (NARRATED_VIDEO_EXTERNALS or
--externals), shaped like the test-only record narrate/tests/fixtures/narrated-video/kitpip-externals.json: the
version, the source commit, per-system binary digests and byte counts, the manifest schema, the timeline mapping and
the default rig. The binary comes from KITPIP_BIN. Before every spawn its SHA-256 and size are checked against the
pin; a mismatch refuses kitpip_pin_mismatch and nothing runs.

kitpip prints one JSON line on stdout: a result (exit 0), {"refused": code, "detail": ...} (exit 1) or
{"error": ...} (exit 2). The wrapper relays a refusal as KitpipRefused with kitpip's code, which the CLI prints in
the narrate stderr shape. It never passes --allow-unlabelled-test.

A refusal is a verdict or a failure. A verdict (kitpip's own refusal line, or the wrapper's checks on a finished
overlay: kitpip_unlabelled, label_chain_broken, a schema or rig that is not the keyed one) repeats for the same
stage key, because the key holds the binary digest, the rig and the narration digest; the store records it and the
node stays refused until its key changes. A failure (kitpip_timeout, kitpip_error, kitpip_missing, or a binary that
fails its pin at spawn) says nothing about the key: the partial is removed, nothing is recorded and the node stays
stale, so calling run again retries it.

The avatar stage runs `analyze` on a segment's narrate run, then `render` and `verify`, all into the stage's
partial directory under the job store, never inside the narrate run and never under artifacts/runs/. Its manifest
uses timeline mapping avatar_overlay_v1. Public CI runs the stub (narrate/tests/fixtures/narrated-video/
kitpip_stub.py); a real kitpip render is lane L5.
"""

import json
import os
import platform
import subprocess
from pathlib import Path

from ..config import in_guitar_runs
from ..ir import sha256_file
from .job import JobError, read_json

EXTERNALS_ENV = "NARRATED_VIDEO_EXTERNALS"
BIN_ENV = "KITPIP_BIN"
MANIFEST_SCHEMA = "kitpip.manifest/v0"
MAPPING = "avatar_overlay_v1"
FORBIDDEN_FLAGS = ("--allow-unlabelled-test", "--pipe")
TIMEOUT_S = 900


class KitpipRefused(JobError):
    """kitpip, or the wrapper around it, refused. code is kitpip's own code or one the wrapper adds. verdict is
    True when the same key would refuse again (the store records it) and False for a failure a retry may clear."""

    def __init__(self, code, detail, verdict=True):
        super().__init__(code, detail)
        self.verdict = verdict


def system():
    machine = {"amd64": "x86_64", "arm64": "aarch64"}.get(platform.machine().lower(), platform.machine().lower())
    return f"{machine}-{platform.system().lower()}"


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
    for field in ("version", "manifest_schema", "timeline_mapping", "binaries", "default_rig", "visibility"):
        if field not in pin:
            raise JobError("externals_invalid", f"the kitpip pin has no {field}")
    if pin["manifest_schema"] != MANIFEST_SCHEMA or pin["timeline_mapping"] != MAPPING:
        raise JobError("externals_invalid", f"the kitpip pin is not {MANIFEST_SCHEMA} with {MAPPING}")
    return pin


def binary_pin(pin):
    """The pinned {sha256, bytes} of the kitpip binary for this system. 'any' serves only a test fixture pin."""
    table = pin["binaries"].get("kitpip", {})
    entry = table.get(system())
    if entry is None and pin["visibility"] == "test_fixture":
        entry = table.get("any")
    return entry


def resolve(pin, env=None):
    """{state, binary, tool, detail}. state: unregistered (no pin), missing (no binary for this system or no
    KITPIP_BIN file), mismatch (digest or size differs) or resolved. tool is the identity a stage key holds."""
    env = os.environ if env is None else env
    if pin is None:
        return {"state": "unregistered", "binary": None, "tool": None, "detail": "no kitpip pin is registered"}
    want = binary_pin(pin)
    tool = {"name": "kitpip", "version": pin["version"], "binary_sha256": want["sha256"] if want else None}
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
    """The avatar stage for one segment: analyze, render and verify into the store, then commit the stage.

    rig_sha256 is the rig revision the stage key holds (knobs.rigRevisionSha256). When it is set, the overlay's
    rig must report that revision. When it is None (a rig other than the pin's default, with no revision in the
    job), the manifest records the revision kitpip reports."""
    narrate_run = Path(narrate_run).resolve()
    partial = store.partial_dir(node_id, key)
    if (
        narrate_run == partial
        or narrate_run in partial.resolve().parents
        or in_guitar_runs(partial)
        or store.dir.resolve() not in partial.resolve().parents
    ):
        raise KitpipRefused("avatar_outside_store", "kitpip writes only inside the job store")
    manifest, consent_ids, voice_ids = narration(narrate_run)
    partial = store.begin(node_id, key)
    try:
        fps_arg = f"{fps['num']}/{fps['den']}"
        call(
            resolution,
            pin,
            ["analyze", str(narrate_run), "--fps", fps_arg, "--out", str(partial / "analyze")],
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
                str(render_size),
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
        fields = {
            "measurements": {
                "frames": overlay["frames"],
                "fps": fps,
                "size": overlay["size"],
                "rig": {"id": overlay_rig.get("id"), "sha256": overlay_rig.get("sha256")},
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
        return store.commit(node_id, key, document, fields)
    except KitpipRefused as exc:
        store.abort(node_id, key)
        if exc.verdict:
            store.record_refusal(node_id, key, exc.code, exc.detail)
        raise
    except BaseException:
        store.abort(node_id, key)
        raise
