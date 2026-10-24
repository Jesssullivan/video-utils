"""Pure private-planner fixtures: no renderer, provider or media decoder runs."""

import copy
import hashlib
import json
import os
import stat
from pathlib import Path

import pytest

from narrate.presentation import PresentationError, asset, plan, write_plan


def descriptor(root, name, value):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)
    return {"path": name, "sha256": hashlib.sha256(value).hexdigest()}


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    extra = [
        descriptor(root, "slides.md", b"# Synthetic slide"),
        descriptor(root, "dist/index.html", b"<html>Synthetic</html>"),
        descriptor(root, "clips.json", b'{"clips": [{"clip": "fixture"}]}'),
        descriptor(root, "stills/01-open.png", b"opaque still fixture"),
    ]
    config = descriptor(
        root,
        "video.json",
        json.dumps(
            {
                "voice_only": True,
                "pip": {"default": "off", "by_slide": {}},
                "speaker": "Original operator",
                "slides": "slides.md",
                "deck_html": "dist/index.html",
                "clip_map": "clips.json",
                "clips_dir": "media",
                "stills_dir": "stills",
                "captures_manifest": "optional-captures.json",
            }
        ).encode(),
    )
    script = descriptor(root, "manuscript/01-open.md", b"---\nslide: open\npip: off\n---\nOriginal factual script.\n")
    clip = descriptor(root, "media/fixture.mp4", b"opaque capture fixture, never decoded")
    return {
        "schemaVersion": 1,
        "projectId": "fixture-private",
        "edition": "internal-cade-pip",
        "projectRoot": str(root),
        "source": {"repository": "example/private", "commit": "1" * 40},
        "clientConfig": config,
        "expectedPages": 1,
        "sourceFiles": [config, *extra],
        "assetsRoot": None,
        "pages": [{"id": "open", "script": script, "targetSeconds": 55, "captures": [clip]}],
    }


def fill(project, tmp_path):
    data = copy.deepcopy(project)
    root = tmp_path / "approved"
    root.mkdir()
    data["assetsRoot"] = str(root)
    rows = {
        "approvedScript": ("open.md", b"---\nslide: open\npip: br\n---\nCade authored fixture.\n"),
        "narration": ("audio.wav", b"approved opaque audio fixture, never decoded"),
        "avatar": ("avatar.mp4", b"approved opaque avatar fixture, never decoded"),
    }
    for role, (name, value) in rows.items():
        row = descriptor(root, name, value)
        row.update({"subjectId": "cade", "scope": "internal-only", "approvalReference": "fixture-authority-review"})
        if role == "avatar":
            row["kind"] = "video"
        data["pages"][0][role] = row
    data["pages"][0]["narration"]["scriptSha256"] = data["pages"][0]["approvedScript"]["sha256"]
    return data


def test_actual_missing_inputs_are_not_readiness(project):
    result = plan(project)
    assert result["pageCount"] == result["captureCount"] == 1
    assert {row["input"] for row in result["missingInputs"]} == {"approvedScript", "narration", "avatar"}
    assert result["inputInspectionReady"] is False
    assert result["privateRenderAuthorized"] is result["publicationAllowed"] is False


def test_private_approved_bundle_preserves_source_and_prepares_only_commands(project, tmp_path):
    data = fill(project, tmp_path)
    original = (tmp_path / "source/video.json").read_bytes()
    incoming = tmp_path / "input.json"
    incoming.write_text(json.dumps(data))
    output = tmp_path / "derived"
    result = write_plan(incoming, output)
    assert result["assemblyBundle"]["prepared"] is True
    assert result["assemblyBundle"]["rendered"] is False
    assert (tmp_path / "source/video.json").read_bytes() == original
    assert "pip: off" in (tmp_path / "source/manuscript/01-open.md").read_text()
    assert (output / "manuscript/01-open.md").read_bytes() == (tmp_path / "approved/open.md").read_bytes()
    assert list((output / "takes").iterdir()) == []
    internal = json.loads((output / "video.internal.json").read_text())
    assert internal["voice_only"] is False and internal["pip"]["default"] == "br"
    assert internal["recording_remote"] is internal["edit_host"] is internal["watch_slug"] is None
    assert "-n" in result["assemblyBundle"]["commands"][0]["argv"]
    for path in output.rglob("*"):
        assert stat.S_IMODE(path.stat().st_mode) == (0o700 if path.is_dir() else 0o600)
    with pytest.raises(FileExistsError):
        write_plan(incoming, output)


@pytest.mark.parametrize("change", ["client-pip", "scope", "subject", "approval", "script-binding", "duplicate-page"])
def test_scope_identity_and_human_authority_are_not_inferred(project, tmp_path, change):
    data = fill(project, tmp_path)
    page = data["pages"][0]
    if change == "client-pip":
        config = {"voice_only": False, "pip": {"default": "br"}}
        data["clientConfig"] = descriptor(tmp_path / "source", "video.json", json.dumps(config).encode())
    elif change == "scope":
        page["avatar"]["scope"] = "public"
    elif change == "subject":
        page["narration"]["subjectId"] = "operator-clone"
    elif change == "approval":
        page["avatar"]["approvalReference"] = ""
    elif change == "script-binding":
        page["narration"]["scriptSha256"] = "0" * 64
    else:
        data["pages"] *= 2
        data["expectedPages"] = 2
    with pytest.raises(PresentationError):
        plan(data)


def test_reference_integrity_and_containment(project, tmp_path):
    root = tmp_path / "source"
    with pytest.raises(PresentationError):
        asset(root, {"path": "../escape", "sha256": "0" * 64})
    with pytest.raises(PresentationError):
        asset(root, {"path": "video.json", "sha256": "0" * 64})
    os.symlink(root / "video.json", root / "link.json")
    with pytest.raises(PresentationError):
        asset(root, {**project["clientConfig"], "path": "link.json"})


def test_missing_bundle_has_no_usable_assembly_or_client_source_writes(project, tmp_path):
    incoming = tmp_path / "input.json"
    incoming.write_text(json.dumps(project))
    output = tmp_path / "blocked"
    result = write_plan(incoming, output)
    assert result["assemblyBundle"]["prepared"] is False
    assert not (output / "video.internal.json").exists()
    with pytest.raises(PresentationError):
        write_plan(incoming, tmp_path / "source/new-output")


def test_frontmatter_not_body_controls_internal_identity(project, tmp_path):
    data = fill(project, tmp_path)
    text = b"---\nslide: open\npip: off\n---\npip: br\n"
    row = descriptor(tmp_path / "approved", "open.md", text)
    data["pages"][0]["approvedScript"].update(row)
    data["pages"][0]["narration"]["scriptSha256"] = row["sha256"]
    with pytest.raises(PresentationError):
        plan(data)


def test_provider_script_projection_is_available_before_media_and_keeps_sources_unspoken(project, tmp_path):
    data = fill(project, tmp_path)
    text = (
        b"---\nslide: open\npip: br\n---\nCade speaks. [clip: fixture] <!-- build 1 --> More.\n"
        b"\nSources: private source refs\nDo not speak this.\n"
    )
    data["pages"][0]["approvedScript"].update(descriptor(tmp_path / "approved", "open.md", text))
    data["pages"][0].pop("narration")
    data["pages"][0].pop("avatar")
    incoming = tmp_path / "input.json"
    incoming.write_text(json.dumps(data))
    output = tmp_path / "derivative"
    result = write_plan(incoming, output)
    assert len(result["spokenScripts"]) == 1
    assert result["narrationJobs"][0]["status"] == "script-prepared"
    assert result["narrationJobs"][0]["synthesisAuthorized"] is False
    spoken = (output / "spoken/01-open.txt").read_text()
    assert spoken == "Cade speaks. More.\n"
    assert (output / "manuscript/01-open.md").read_bytes() == text
    assert result["assemblyBundle"]["prepared"] is False
    assert not (output / "video.internal.json").exists()


def test_avatar_video_does_not_truncate_narration_at_its_own_end(project, tmp_path):
    data = fill(project, tmp_path)
    incoming = tmp_path / "input.json"
    incoming.write_text(json.dumps(data))
    result = write_plan(incoming, tmp_path / "derived")
    argv = result["assemblyBundle"]["commands"][0]["argv"]
    assert argv.index("-stream_loop") < argv.index("-i")
    assert argv[argv.index("-stream_loop") + 1] == "-1"
    assert "-shortest" in argv and "-t" not in argv


@pytest.mark.parametrize("path", ["../outside.json", "/tmp/outside.json"])
def test_inherited_assembly_config_cannot_escape_or_bypass_digest_binding(project, tmp_path, path):
    data = fill(project, tmp_path)
    root = tmp_path / "source"
    client = json.loads((root / "video.json").read_text())
    client["clip_map"] = path
    data["clientConfig"] = descriptor(root, "video.json", json.dumps(client).encode())
    data["sourceFiles"] = [data["clientConfig"] if row["path"] == "video.json" else row for row in data["sourceFiles"]]
    incoming = tmp_path / "input.json"
    incoming.write_text(json.dumps(data))
    with pytest.raises(PresentationError):
        write_plan(incoming, tmp_path / "derived")


def test_existing_stills_need_explicit_digest_inventory_before_usable_config(project, tmp_path):
    data = fill(project, tmp_path)
    data["sourceFiles"] = [row for row in data["sourceFiles"] if not row["path"].endswith(".png")]
    incoming = tmp_path / "input.json"
    incoming.write_text(json.dumps(data))
    result = write_plan(incoming, tmp_path / "derived")
    assert result["assemblyBundle"]["prepared"] is False
    assert not (tmp_path / "derived/video.internal.json").exists()


def test_directory_discovery_cannot_add_unmapped_historical_capture(project, tmp_path):
    data = fill(project, tmp_path)
    descriptor(tmp_path / "source", "media/extra.mp4", b"unadmitted metadata fixture")
    incoming = tmp_path / "input.json"
    incoming.write_text(json.dumps(data))
    result = write_plan(incoming, tmp_path / "derived")
    assert result["assemblyBundle"]["prepared"] is True
    internal = json.loads((tmp_path / "derived/video.internal.json").read_text())
    assert Path(internal["clips_dir"]) == tmp_path / "derived/clips"
    assert {path.name for path in Path(internal["clips_dir"]).iterdir()} == {"fixture.mp4"}
    assert (tmp_path / "source/media/extra.mp4").exists()
    for key in ("clip_map", "captures_manifest"):
        assert Path(internal[key]).is_relative_to(tmp_path / "derived")


def test_clip_map_selected_path_must_be_an_admitted_capture(project, tmp_path):
    data = fill(project, tmp_path)
    mapped = descriptor(tmp_path / "source", "clips.json", b'{"clips":[{"clip":"fixture","path":"../escape.mp4"}]}')
    data["sourceFiles"] = [mapped if row["path"] == "clips.json" else row for row in data["sourceFiles"]]
    incoming = tmp_path / "input.json"
    incoming.write_text(json.dumps(data))
    with pytest.raises(PresentationError):
        write_plan(incoming, tmp_path / "derived")
