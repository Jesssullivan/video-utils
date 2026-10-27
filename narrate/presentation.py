"""Private presentation input planner. Never generates media or invokes providers.

The original client voice-only configuration and source manuscripts are read-only.
Only separately authored, authority-bound character scripts can feed the internal
variant. Approval references are caller declarations, never manufactured proof.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
from pathlib import Path

from . import adapters


class PresentationError(ValueError):
    pass


def fail(message):
    raise PresentationError(message)


def private_root(value):
    if not isinstance(value, str) or not Path(value).is_absolute():
        fail("An explicit absolute input root is required")
    root = Path(value)
    if root.is_symlink() or not root.is_dir():
        fail("Input root must be a nonsymlink directory")
    return root.resolve()


def contained_path(root, value):
    if not isinstance(value, str):
        fail("A root-relative project path is required")
    relative = Path(value)
    if relative.is_absolute() or any(part in ("", ".", "..") for part in value.split("/")):
        fail("Input paths must remain under their declared root")
    path = root
    for part in relative.parts:
        path = path / part
        if path.is_symlink():
            fail("Symlink input paths are not accepted")
    return path


def asset(root, row):
    if not isinstance(row, dict):
        fail("An input descriptor is required")
    path = contained_path(root, row.get("path"))
    if not re.fullmatch(r"[a-f0-9]{64}", str(row.get("sha256", ""))):
        fail("A complete input digest is required")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 2 * 1024**3:
            fail("A bounded regular input file is required")
        digest = hashlib.sha256()
        with os.fdopen(fd, "rb", closefd=False) as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != row["sha256"]:
            fail("An input digest no longer matches")
    finally:
        os.close(fd)
    return path


def header_value(text, key):
    header = re.match(r"\A---\n(.*?)\n---(?:\n|$)", text, re.DOTALL)
    if not header:
        fail("A manuscript requires explicit front matter")
    values = re.findall(r"(?m)^" + re.escape(key) + r":\s*([^\n]+)$", header[1])
    if len(values) != 1:
        fail("A manuscript identity/layout field is missing or duplicated")
    return values[0].strip()


def normalize_manifest(value):
    """Canonical optional fields for the matching Dhall input type."""
    result = json.loads(json.dumps(value))
    result.setdefault("assetsRoot", None)
    for page in result["pages"]:
        for role in ("approvedScript", "narration", "avatar"):
            page.setdefault(role, None)
            if page[role] is not None:
                page[role].setdefault("kind", None)
                page[role].setdefault("scriptSha256", None)
    return result


def approved(root, row, role):
    if root is None:
        fail("Approved inputs require an explicit assets root")
    if row.get("subjectId") != "cade" or row.get("scope") != "internal-only":
        fail("Character inputs require the internal Cade scope")
    reference = row.get("approvalReference")
    if not isinstance(reference, str) or not reference.strip() or len(reference) > 512:
        fail("An existing authority reference is required")
    if role == "avatar" and row.get("kind") not in ("image", "video"):
        fail("An avatar input must declare image or video")
    return asset(root, row)


def plan(manifest):
    if manifest.get("schemaVersion") != 1 or manifest.get("edition") != "internal-cade-pip":
        fail("An explicit versioned internal character edition is required")
    identifier = manifest.get("projectId", "")
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,79}", identifier):
        fail("A bounded project identity is required")
    root = private_root(manifest.get("projectRoot"))
    assets_root = private_root(manifest["assetsRoot"]) if manifest.get("assetsRoot") else None
    client_path = asset(root, manifest.get("clientConfig"))
    client = json.loads(client_path.read_text())
    if client.get("voice_only") is not True or client.get("pip", {}).get("default") != "off":
        fail("The original client edition must remain voice-only with PIP off")
    if any(value != "off" for value in client.get("pip", {}).get("by_slide", {}).values()):
        fail("The client edition contains an enabled PIP override")
    source = manifest.get("source", {})
    if not re.fullmatch(r"[a-f0-9]{40}", str(source.get("commit", ""))) or not source.get("repository"):
        fail("The original source repository and commit must be recorded")
    seen = set()
    for row in manifest.get("sourceFiles", []):
        asset(root, row)
        if row["path"] in seen:
            fail("Duplicate source file descriptors are not accepted")
        seen.add(row["path"])
    pages = manifest.get("pages")
    count = manifest.get("expectedPages")
    if type(count) is not int or not 1 <= count <= 128 or not isinstance(pages, list) or len(pages) != count:
        fail("Every expected page must have one mapping")
    rows, missing, identities, captures = [], [], set(), set()
    for number, page in enumerate(pages, 1):
        identity = page.get("id", "")
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,79}", identity) or identity in identities:
            fail("Page identities must be unique and bounded")
        identities.add(identity)
        seconds = page.get("targetSeconds")
        if type(seconds) is not int or not 0 < seconds <= 3600:
            fail("Page timing must be finite, positive and bounded")
        original = asset(root, page.get("script"))
        text = original.read_text()
        if header_value(text, "slide") != identity:
            fail("A source manuscript page does not match its identity")
        for clip in page.get("captures", []):
            asset(root, clip)
            captures.add(clip["path"])
        inputs = {}
        for key in ("approvedScript", "narration", "avatar"):
            descriptor = page.get(key)
            if descriptor is None:
                missing.append({"page": identity, "input": key})
                continue
            path = approved(assets_root, descriptor, key)
            inputs[key] = {**descriptor, "absolutePath": str(path)}
        if "approvedScript" in inputs:
            authored = Path(inputs["approvedScript"]["absolutePath"]).read_text()
            if header_value(authored, "slide") != identity:
                fail("The authored character script has a different page identity")
            if header_value(authored, "pip") != "br" or any(
                cue != "br" for cue in re.findall(r"\[pip:\s*([a-z]+)\]", authored)
            ):
                fail("The internal authored manuscript must explicitly select its PIP layout")
        if "narration" in inputs and (
            "approvedScript" not in inputs
            or inputs["narration"].get("scriptSha256") != inputs["approvedScript"]["sha256"]
        ):
            fail("Narration must bind the actual approved character script")
        rows.append(
            {
                "number": number,
                "id": identity,
                "targetSeconds": seconds,
                "sourceScript": page["script"],
                "captures": page.get("captures", []),
                "inputs": inputs,
            }
        )
    return {
        "schemaVersion": 1,
        "projectId": identifier,
        "edition": "internal-cade-pip",
        "source": source,
        "clientConfig": manifest["clientConfig"],
        "pages": rows,
        "sourceFiles": manifest.get("sourceFiles", []),
        "missingInputs": missing,
        "pageCount": len(rows),
        "captureCount": len(captures),
        "targetSeconds": sum(row["targetSeconds"] for row in rows),
        "inputInspectionReady": not missing,
        "mediaProbeRequired": True,
        "privateRenderAuthorized": False,
        "publicationAllowed": False,
        "approvalEvidence": "caller-declared authority references, not independent human approval proof",
        "clientEditionChanged": False,
    }


def private_json(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def script_bundle(manifest, result, output):
    """Preserve approved Markdown and derive narration with the existing adapter."""
    manuscript = output / "manuscript"
    spoken = output / "spoken"
    manuscript.mkdir(mode=0o700)
    spoken.mkdir(mode=0o700)
    rows = []
    for row in result["pages"]:
        descriptor = row["inputs"].get("approvedScript")
        if descriptor is None:
            continue
        source = asset(private_root(manifest["assetsRoot"]), descriptor)
        data = source.read_bytes()
        if hashlib.sha256(data).hexdigest() != descriptor["sha256"]:
            fail("An approved script changed during preparation")
        name = f"{row['number']:02d}-{row['id']}"
        fd = os.open(manuscript / (name + ".md"), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        # The original assembly grammar treats these as timed controls, not words.
        authored = re.sub(r"\[(?:clip|media|pip):[^\]\n]+\]", " ", data.decode())
        script = adapters.markdown(authored, name=name)
        text = "\n\n".join(segment.text for segment in script.segments) + "\n"
        fd = os.open(spoken / (name + ".txt"), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(text)
        rows.append(
            {
                "page": row["id"],
                "path": str(spoken / (name + ".txt")),
                "sha256": hashlib.sha256(text.encode()).hexdigest(),
                "approvedScriptSha256": descriptor["sha256"],
                "authorityReference": descriptor["approvalReference"],
            }
        )
    return rows


def assembly_sources(manifest, client):
    root = private_root(manifest["projectRoot"])
    rows = {row["path"]: row for row in manifest["sourceFiles"]}
    paths = {}
    for key in ("slides", "deck_html", "clip_map"):
        value = client.get(key)
        contained_path(root, value)
        if value not in rows:
            fail("An assembly source file lacks its admitted digest")
        paths[key] = str(asset(root, rows[value]))
    for key in ("clips_dir", "stills_dir"):
        path = contained_path(root, client.get(key))
        if path.exists() and not path.is_dir():
            fail("An assembly media directory is invalid")
        paths[key] = str(path)
    for page in manifest["pages"]:
        for clip in page.get("captures", []):
            if not contained_path(root, clip["path"]).is_relative_to(Path(paths["clips_dir"])):
                fail("A mapped capture is outside the selected clips directory")
    declared = {}
    for page in manifest["pages"]:
        for row in page.get("captures", []):
            if row["path"] in declared and declared[row["path"]] != row:
                fail("Conflicting capture descriptors are not accepted")
            declared[row["path"]] = row
    mapping = json.loads(Path(paths["clip_map"]).read_text())
    if not isinstance(mapping, dict) or mapping.get("media") or not isinstance(mapping.get("clips"), list):
        fail("The adapter requires an explicit list-form project clip map")
    clip_names = {}
    for row in mapping["clips"]:
        name = row.get("clip") if isinstance(row, dict) else None
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name):
            fail("A mapped clip identity is invalid")
        relative = row.get("path") or str(Path(client["clips_dir"]) / (name + ".mp4"))
        contained_path(root, relative)
        if relative not in declared or name in clip_names:
            fail("The clip map selects undeclared or duplicate capture input")
        asset(root, declared[relative])
        clip_names[name] = relative
    for page in manifest["pages"]:
        source = page.get("approvedScript")
        if source is None:
            continue
        text = asset(private_root(manifest["assetsRoot"]), source).read_text()
        references = re.findall(r"\[(?:clip|media):\s*([^\]\n]+)\]", text)
        raw_media = re.findall(r"(?m)^media:\s*(\[[^\n]*\])\s*$", text)
        for value in raw_media:
            references.extend(part.strip(" \"'") for part in value[1:-1].split(",") if part.strip())
        if any(name.strip() not in clip_names for name in references):
            fail("The authored manuscript selects a capture outside the admitted map")
    # Existing stills are derivatives, not authenticated by the original deck hash.
    # Every file the assembler may select needs its own explicit inventory row.
    stills = Path(paths["stills_dir"])
    files = list(stills.rglob("*")) if stills.exists() else []
    if len(files) > 4096:
        fail("The stills inventory is oversized")
    pngs = [path for path in files if path.suffix.lower() == ".png"]
    if not pngs:
        return paths, ["digest-bound slide stills"]
    for path in pngs:
        relative = str(path.relative_to(root))
        if relative not in rows:
            return paths, ["digest-bound slide stills"]
        asset(root, rows[relative])
    if client.get("captures_manifest"):
        value = client["captures_manifest"]
        optional = contained_path(root, value)
        if optional.exists():
            if value not in rows:
                fail("An optional capture manifest lacks its admitted digest")
            asset(root, rows[value])
        paths["captures_manifest"] = str(optional)
    return paths, []


def stage_captures(manifest, output):
    """Freeze only declared capture bytes, excluding historical directory discovery."""
    root = private_root(manifest["projectRoot"])
    directory = output / "clips"
    directory.mkdir(mode=0o700)
    copied = {}
    for page in manifest["pages"]:
        for row in page.get("captures", []):
            if row["path"] in copied:
                continue
            source = asset(root, row)
            target = directory / source.name
            read_fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            write_fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            digest = hashlib.sha256()
            with os.fdopen(read_fd, "rb") as incoming, os.fdopen(write_fd, "wb") as outgoing:
                for chunk in iter(lambda: incoming.read(1024 * 1024), b""):
                    digest.update(chunk)
                    outgoing.write(chunk)
                outgoing.flush()
                os.fsync(outgoing.fileno())
            if digest.hexdigest() != row["sha256"]:
                fail("A staged capture differs from its admitted digest")
            copied[row["path"]] = str(target)
    client = json.loads(asset(root, manifest["clientConfig"]).read_text())
    rows = {row["path"]: row for row in manifest["sourceFiles"]}
    original = json.loads(asset(root, rows[client["clip_map"]]).read_text())
    mapped = []
    captures = []
    for row in original["clips"]:
        relative = row.get("path") or str(Path(client["clips_dir"]) / (row["clip"] + ".mp4"))
        path = copied[relative]
        mapped.append({**row, "path": path})
        captures.append({"name": row["clip"], "path": path, "audio": row.get("audio") is True})
    clip_map = output / "clip-map.verified.json"
    capture_map = output / "captures.verified.json"
    private_json(clip_map, {**original, "clips": mapped})
    private_json(capture_map, {"clips": captures})
    return {"clips_dir": str(directory), "clip_map": str(clip_map), "captures_manifest": str(capture_map)}


def assembly_bundle(manifest, result, output):
    """Prepare the existing project's assembly inputs; never run its commands."""
    if not result["inputInspectionReady"]:
        return {"prepared": False, "reason": "character script/audio/avatar inputs are incomplete"}
    root = private_root(manifest["projectRoot"])
    client = json.loads(asset(root, manifest["clientConfig"]).read_text())
    paths, missing_sources = assembly_sources(manifest, client)
    if missing_sources:
        return {"prepared": False, "sourcePrerequisites": missing_sources, "rendered": False}
    manuscript = output / "manuscript"
    takes = output / "takes"
    takes.mkdir(mode=0o700)
    commands = []
    for row in result["pages"]:
        inputs = row["inputs"]
        name = f"{row['number']:02d}-{row['id']}"
        avatar, audio = inputs["avatar"], inputs["narration"]
        argv = ["ffmpeg", "-nostdin", "-n"]
        if avatar["kind"] == "image":
            argv += ["-loop", "1"]
        else:
            argv += ["-stream_loop", "-1"]
        argv += [
            "-i",
            avatar["absolutePath"],
            "-i",
            audio["absolutePath"],
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-shortest",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(takes / (name + ".mp4")),
        ]
        commands.append(
            {
                "page": row["id"],
                "mediaProbeRequired": True,
                "argv": argv,
                "inputDigests": {"avatar": avatar["sha256"], "narration": audio["sha256"]},
            }
        )
    internal = dict(client)
    internal.update(paths)
    internal.update(stage_captures(manifest, output))
    internal.update(
        {
            "speaker": "Cade, virtual spokesperson",
            "voice_only": False,
            "pip": {"default": "br", "width": 0.22, "by_slide": {}},
            "manuscript": str(manuscript),
            "narration": str(takes),
            "out_dir": str(output / "build" / "video"),
            "recording_remote": None,
            "edit_host": None,
            "edit_dest": None,
            "watch_slug": None,
            "output_name": "internal-cade-{date}",
        }
    )
    config = output / "video-internal.json"
    private_json(config, internal)
    return {
        "prepared": True,
        "rendered": False,
        "commands": commands,
        "assembly": {
            "cwd": str(root),
            "environment": {"PHR_VIDEO_CONFIG": str(config)},
            "argv": ["python3", str(root / "scripts/video/assemble/assemble.py"), "assemble"],
        },
        "captionSource": "exact approved character manuscripts, not the original speaker's script",
        "publicationAllowed": False,
        "renderAuthorizationRequired": True,
    }


def write_plan(manifest_path, output):
    raw = Path(manifest_path).read_bytes()
    if len(raw) > 2 * 1024**2:
        fail("Presentation manifest is oversized")
    result = plan(json.loads(raw))
    output = Path(output)
    if not output.is_absolute() or output.is_symlink():
        fail("A new absolute private output directory is required")
    root = private_root(json.loads(raw)["projectRoot"])
    if output.resolve().is_relative_to(root):
        fail("Derived outputs must not be written into the original client project")
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    info = output.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        fail("Output custody must be private and owned")
    paths, missing_sources = assembly_sources(
        json.loads(raw), json.loads(asset(root, json.loads(raw)["clientConfig"]).read_text())
    )
    result["assemblySourceReadiness"] = {"missingPrerequisites": missing_sources, "paths": paths}
    result["inputManifestSha256"] = hashlib.sha256(raw).hexdigest()
    private_json(output / "presentation-input.normalized.json", normalize_manifest(json.loads(raw)))
    result["spokenScripts"] = script_bundle(json.loads(raw), result, output)
    spoken_by_page = {row["page"]: row for row in result["spokenScripts"]}
    result["narrationJobs"] = [
        {
            "page": row["id"],
            "targetSeconds": row["targetSeconds"],
            "register": "narration",
            "sourceScript": row["sourceScript"],
            "approvedScript": row["inputs"].get("approvedScript"),
            "spokenScript": spoken_by_page.get(row["id"]),
            "voiceSubject": "cade",
            "engine": None,
            "status": "script-prepared" if row["id"] in spoken_by_page else "blocked-no-approved-script",
            "synthesisAuthorized": False,
            "voiceConsentVerified": False,
        }
        for row in result["pages"]
    ]
    result["assemblyBundle"] = assembly_bundle(json.loads(raw), result, output)
    path = output / "presentation-plan.json"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    marker = os.open(output / ".gitignore", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(marker, "w") as stream:
        stream.write("*\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest")
    parser.add_argument("output")
    args = parser.parse_args()
    try:
        result = write_plan(args.manifest, args.output)
    except (OSError, ValueError, KeyError, TypeError):
        parser.exit(2, "Private presentation planning failed; check typed inputs, scope and digests.\n")
    print(
        json.dumps(
            {
                "pages": result["pageCount"],
                "captures": result["captureCount"],
                "missingInputs": len(result["missingInputs"]),
                "inputInspectionReady": result["inputInspectionReady"],
                "rendered": False,
            }
        )
    )


if __name__ == "__main__":
    main()
