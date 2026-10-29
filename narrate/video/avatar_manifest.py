"""The avatar overlay manifest: avatar.manifest/v1, with kitpip.manifest/v0 still accepted (docs/spec/NARRATED_VIDEO.md,
"Avatar manifest v1", SPR-128 on TIN-7125 comment 33022456).

Every avatar external writes one manifest beside its overlay. v1 names the renderer kind, so the avatar stages, compose
and handoff read kitpip and VRM overlays through one view:

  schema           avatar.manifest/v1
  kind             avatar_overlay
  renderer         {kind: kitpip | vrm, name, version, ...}. A vrm renderer also names its engine and the GPU and
                   driver that rasterised the frames
  synthetic        true. consent_ids and voice_ids are the narration's
  rig              {id, sha256}. For a vrm overlay the rig is the VRM model and sha256 is vrm.sha256
  rate, size       the overlay's rational fps and {w, h}
  frames           the frame count. frames_sha256 is the SHA-256 of the frames as the renderer drew them
  frames_identity  bit_exact (the same frames on any host) or per_host (GPU raster is not bit-exact: frames_sha256
                   matches only another render on the same host, renderer and driver). Every vrm overlay is per_host
  outputs          [{file, sha256, bytes}] of every file in the overlay directory except manifest.json
  timeline         {mapping: avatar_overlay_v1, no_time_stretch: false, clock: narration_output}

A vrm manifest also holds vrm {sha256, bytes, spec_version, meta} (meta: the model's licence fields as its VRM meta
states them), face {schema, sha256, clock, source}, likeness_consent_id, approval {ref, evidence_sha256} and badge
{burned_in: false, decision: "open"}: whether offline VRM video carries a burned-in badge is not ruled, so no renderer
draws one and no record may settle it.

kitpip.manifest/v0 (kitpip 0.1.0 and the stub) has no renderer kind. view() reads it as renderer kind kitpip with
frames_identity unstated, so a kitpip overlay rendered before v1 keeps planning fresh.
"""

import hashlib
import json
import re
from pathlib import Path

from .job import JobError

SCHEMA_V1 = "avatar.manifest/v1"
KITPIP_V0 = "kitpip.manifest/v0"
SCHEMAS = (KITPIP_V0, SCHEMA_V1)
KINDS = ("kitpip", "vrm")
MAPPING = "avatar_overlay_v1"
CLOCK = "narration_output"
IDENTITIES = ("bit_exact", "per_host")
HEX64 = re.compile(r"[0-9a-f]{64}")
VRM_SPECS = ("0.x", "1.0")
BADGE_OPEN = {"burned_in": False, "decision": "open"}


def refuse(detail):
    raise JobError("avatar_manifest_invalid", detail)


def digest(value):
    return isinstance(value, str) and HEX64.fullmatch(value) is not None


def text(value):
    return isinstance(value, str) and value != ""


def natural(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def view(manifest, kind=None):
    """The renderer-neutral view of an overlay manifest, or JobError avatar_manifest_invalid.

    kind, when given, is the renderer kind the job's avatar.external names; a manifest of another kind refuses."""
    if not isinstance(manifest, dict) or manifest.get("schema") not in SCHEMAS:
        refuse(f"the overlay manifest is not one of {', '.join(SCHEMAS)}")
    schema = manifest["schema"]
    renderer = manifest.get("renderer") if isinstance(manifest.get("renderer"), dict) else {}
    found = "kitpip" if schema == KITPIP_V0 else renderer.get("kind")
    if found not in KINDS:
        refuse(f"renderer.kind {found!r} is not one of {', '.join(KINDS)}")
    if kind is not None and found != kind:
        refuse(f"the overlay was drawn by {found}, not the job's {kind}")
    rig = manifest.get("rig") if isinstance(manifest.get("rig"), dict) else {}
    size = manifest.get("size") if isinstance(manifest.get("size"), dict) else {}
    out = {
        "schema": schema,
        "renderer_kind": found,
        "renderer": renderer,
        "synthetic": manifest.get("synthetic") is True,
        "consent_ids": sorted(manifest.get("consent_ids") or []),
        "voice_ids": sorted(manifest.get("voice_ids") or []),
        "rig": {"id": rig.get("id"), "sha256": rig.get("sha256")},
        "rate": manifest.get("rate"),
        "size": size,
        "frames": manifest.get("frames"),
        "frames_sha256": manifest.get("frames_sha256"),
        "frames_identity": manifest.get("frames_identity") if schema == SCHEMA_V1 else "unstated",
        "show_badge": manifest.get("show_badge", False),
        "outputs": manifest.get("outputs") or [],
        "vrm": manifest.get("vrm"),
    }
    if schema == SCHEMA_V1:
        check_v1(manifest, out)
    return out


def check_v1(manifest, out):
    if manifest.get("kind") != "avatar_overlay":
        refuse("an avatar.manifest/v1 has kind avatar_overlay")
    if not (text(out["renderer"].get("name")) and text(out["renderer"].get("version"))):
        refuse("renderer needs a name and a version")
    if not natural(out["frames"]) or out["frames"] < 1:
        refuse("frames is a positive count")
    if not digest(out["frames_sha256"]):
        refuse("frames_sha256 is a 64-hex digest")
    if out["frames_identity"] not in IDENTITIES:
        refuse(f"frames_identity is one of {', '.join(IDENTITIES)}")
    rate = out["rate"]
    if not (isinstance(rate, dict) and natural(rate.get("num")) and natural(rate.get("den"))) or 0 in (
        rate["num"],
        rate["den"],
    ):
        refuse("rate is {num, den}, both positive")
    if not (natural(out["size"].get("w")) and natural(out["size"].get("h"))):
        refuse("size is {w, h}")
    if not text(out["rig"]["id"]) or not digest(out["rig"]["sha256"]):
        refuse("rig needs an id and a 64-hex sha256")
    timeline = manifest.get("timeline") if isinstance(manifest.get("timeline"), dict) else {}
    if (timeline.get("mapping"), timeline.get("no_time_stretch"), timeline.get("clock")) != (MAPPING, False, CLOCK):
        refuse(f"timeline is {MAPPING} on the {CLOCK} clock with no_time_stretch false")
    if out["renderer_kind"] == "vrm":
        check_vrm(manifest, out)


def check_vrm(manifest, out):
    renderer = out["renderer"]
    gpu = renderer.get("gpu") if isinstance(renderer.get("gpu"), dict) else {}
    if not all(text(gpu.get(k)) for k in ("vendor", "renderer", "driver")):
        refuse("a vrm renderer names its GPU vendor, renderer string and driver")
    if not isinstance(renderer.get("engine"), dict):
        refuse("a vrm renderer names its engine")
    if out["frames_identity"] != "per_host":
        refuse("GPU raster is not bit-exact: a vrm overlay's frames_identity is per_host")
    vrm = manifest.get("vrm") if isinstance(manifest.get("vrm"), dict) else {}
    if not digest(vrm.get("sha256")) or vrm.get("sha256") != out["rig"]["sha256"]:
        refuse("vrm.sha256 is the model's digest and equals rig.sha256")
    if vrm.get("spec_version") not in VRM_SPECS or not isinstance(vrm.get("meta"), dict):
        refuse("vrm names its spec_version and its meta licence fields")
    face = manifest.get("face") if isinstance(manifest.get("face"), dict) else {}
    if not digest(face.get("sha256")) or face.get("clock") != CLOCK:
        refuse(f"a vrm overlay names its face timeline by digest, on the {CLOCK} clock")
    if not text(manifest.get("likeness_consent_id")):
        refuse("a vrm overlay names its likeness consent")
    approval = manifest.get("approval") if isinstance(manifest.get("approval"), dict) else {}
    if not text(approval.get("ref")) or not digest(approval.get("evidence_sha256")):
        refuse("a vrm overlay names its appearance approval and its evidence digest")
    if manifest.get("badge") != BADGE_OPEN or manifest.get("show_badge") not in (None, False):
        refuse("the burned-in badge decision is open: a vrm overlay records badge {burned_in: false, decision: open}")


def verify_dir(directory, kind=None):
    """Re-hash an overlay directory against its manifest: (view, problems). problems lists unlisted, missing and
    changed files; the view is None when the manifest itself does not read."""
    directory = Path(directory)
    try:
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        seen = view(manifest, kind)
    except (OSError, ValueError, JobError) as exc:
        return None, [f"manifest: {getattr(exc, 'detail', exc)}"]
    listed = {}
    for row in seen["outputs"]:
        if (
            not isinstance(row, dict)
            or not text(row.get("file"))
            or "/" in row["file"]
            or not digest(row.get("sha256"))
        ):
            return seen, ["outputs: each row is {file, sha256} of a file in the overlay directory"]
        listed[row["file"]] = row["sha256"]
    problems = []
    present = {p.name for p in directory.iterdir() if p.name != "manifest.json"}
    problems += [f"unlisted: {name}" for name in sorted(present - set(listed))]
    for name, want in sorted(listed.items()):
        path = directory / name
        if path.is_symlink() or not path.is_file():
            problems.append(f"missing: {name}")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != want:
            problems.append(f"changed: {name}")
    return seen, problems
