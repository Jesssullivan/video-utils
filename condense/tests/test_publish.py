"""A published condense run is hash-bound, carries the edl_v1 mapping and passes verify-run; tampering fails it."""

import json
import shutil
import subprocess

import pytest

from condense import publish, timeline


def verify(run_dir):
    return subprocess.run(
        [timeline.binary(), "verify-run", "--timeline", "edl_v1", run_dir], capture_output=True, text=True
    )


@pytest.fixture(scope="module")
def published(rendered, tmp_path_factory):
    return publish.publish(rendered, tmp_path_factory.mktemp("condense"))


def test_the_manifest_binds_every_output_and_declares_the_edl_mapping(published, rendered):
    m = json.loads((published / "manifest.json").read_text())
    assert m["kind"] == "condense_edit" and m["run_dir"] == str(published.resolve())
    assert m["timeline"]["mapping"] == "edl_v1" and m["timeline"]["no_time_stretch"] is False
    assert m["timeline"]["edl"]["sha256"] == m["output_sha256"]["edl.json"]
    for name, digest in m["output_sha256"].items():
        assert publish.sha256(published / name) == digest
    edl = json.loads((published / "edl.json").read_text())
    assert m["timeline"]["total_frames"] == m["delivery"]["video_frames"]
    assert [c["name"] for c in m["timeline"]["clips"]] == [c["name"] for c in edl["clips"]]
    assert {s["clip"] for s in m["sources"]} == {c["name"] for c in rendered.clips}
    assert "source" not in m and "pcm" not in m


def test_the_published_run_passes_verify_run(published):
    p = verify(published)
    assert p.returncode == 0, p.stdout + p.stderr


@pytest.mark.parametrize(
    "tamper",
    [
        lambda d: (d / "edl.json").write_text((d / "edl.json").read_text().replace('"fps": 30', '"fps": 25')),
        lambda d: (d / "talk.mp4").write_bytes((d / "talk.mp4").read_bytes()[:-1]),
        lambda d: (d / "manifest.json").write_text(
            (d / "manifest.json").read_text().replace('"no_time_stretch": false', '"no_time_stretch": true')
        ),
    ],
    ids=["edl", "delivery", "mapping"],
)
def test_a_tampered_run_fails_verify_run(published, tmp_path, tamper):
    copy = tmp_path / published.name
    shutil.copytree(published, copy)
    m = json.loads((copy / "manifest.json").read_text())
    m["run_dir"] = str(copy.resolve())
    (copy / "manifest.json").write_text(json.dumps(m, indent=2) + "\n")
    assert verify(copy).returncode == 0
    tamper(copy)
    assert verify(copy).returncode == 1


def test_publish_refuses_without_a_render(talk, tmp_path):
    missing = talk.out.with_name("absent.mp4")
    talk_out, talk.out = talk.out, missing
    try:
        with pytest.raises(FileNotFoundError):
            publish.publish(talk, tmp_path)
    finally:
        talk.out = talk_out
    assert list(tmp_path.iterdir()) == []
