"""A published condense run is hash-bound, carries the edl_v1 mapping and passes verify-run; tampering fails it."""

import json
import shutil
import subprocess

import pytest

from condense import check, publish, timeline


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
    assert m["check"] == {"status": "not_run"} and "check.json" not in m["output_sha256"]


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


@pytest.fixture
def report(rendered):
    """work/check.json of the rendered edit, removed afterwards so no other test publishes it."""
    path = rendered.f(*publish.CHECK_REPORT)
    yield path
    path.unlink(missing_ok=True)


def bounds_read(cfg, tl):
    """bounds needs whisper, which the synthetic tests never run: a stand-in with nothing to read."""
    return {"limits": None, "measured": {"spots": []}, "passed": True, "review": "a person reads the printed text"}


def test_a_complete_check_report_is_published_hash_bound_and_summarised(rendered, report, tmp_path, monkeypatch):
    monkeypatch.setitem(check.CHECKS, "bounds", bounds_read)
    assert check.check(rendered, [])
    run_dir = publish.publish(rendered, tmp_path)
    m = json.loads((run_dir / "manifest.json").read_text())
    r = json.loads(report.read_text())
    assert r["status"] == "passed" and r["complete"]
    assert m["check"] == {
        "status": "passed",
        "file": "check.json",
        "sha256": publish.sha256(report),
        "complete": True,
        "gates": {"silence": True, "loud": True, "sync": True, "bounds": True, "captions": True},
        "summary": r["summary"],
    }
    assert m["output_sha256"]["check.json"] == m["check"]["sha256"]
    assert m["status"] == "rendered_unreviewed"  # a machine check is not a listening review
    assert verify(run_dir).returncode == 0
    (run_dir / "check.json").write_text((run_dir / "check.json").read_text().replace('"passed": true', '"passed": 1'))
    assert verify(run_dir).returncode == 1


def test_a_partial_check_is_never_published_as_passed(rendered, report, tmp_path):
    assert check.check(rendered, ["silence", "loud"])  # writes work/check.partial.json, not check.json
    partial = rendered.f(*publish.PARTIAL_REPORT)
    try:
        assert not report.exists() and json.loads(partial.read_text())["status"] == "partial"
        m = json.loads((publish.publish(rendered, tmp_path / "a") / "manifest.json").read_text())
        assert m["check"] == {"status": "not_run"}
        # a partial report placed where the complete one goes is published as partial, never as passed
        report.write_text(partial.read_text())
        m = json.loads((publish.publish(rendered, tmp_path / "b") / "manifest.json").read_text())
        assert m["check"]["status"] == "partial" and m["check"]["complete"] is False
        older = json.loads(partial.read_text())
        del older["status"]  # an older report without a status
        report.write_text(json.dumps(older))
        m = json.loads((publish.publish(rendered, tmp_path / "c") / "manifest.json").read_text())
        assert m["check"]["status"] == "partial"
    finally:
        partial.unlink(missing_ok=True)


def test_a_check_report_of_another_edit_is_refused(rendered, report, tmp_path):
    assert check.check(rendered, ["silence"], report=report)
    stale = json.loads(report.read_text())
    stale["delivery"]["sha256"] = "0" * 64
    report.write_text(json.dumps(stale))
    with pytest.raises(RuntimeError, match="checked another edit"):
        publish.publish(rendered, tmp_path)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("text", ['{"kind": "condense_check", "deliv', "[]", '{"kind": "condense_check"}', "\xff"])
def test_a_broken_check_report_is_refused_not_a_traceback(rendered, report, tmp_path, text):
    report.write_bytes(text.encode("latin-1"))
    with pytest.raises(RuntimeError, match="is not a (readable|condense) check report"):
        publish.publish(rendered, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_no_binary_stops_publish_before_anything_is_staged(rendered, tmp_path, monkeypatch):
    def missing():
        raise RuntimeError("no video-utils binary: run `just cli`, or set VIDEO_UTILS_BIN")

    monkeypatch.setattr(publish.timeline, "binary", missing)
    with pytest.raises(RuntimeError, match="no video-utils binary"):
        publish.publish(rendered, tmp_path / "root")
    assert not (tmp_path / "root").exists()


def fake_verifier(tmp_path, body):
    """The real binary, except that verify-run runs `body`."""
    script = tmp_path / "fake-video-utils"
    script.write_text(f'#!/bin/sh\nif [ "$1" = verify-run ]; then {body}; fi\nexec "{timeline.binary()}" "$@"\n')
    script.chmod(0o755)
    return str(script)


@pytest.mark.parametrize(
    "body, kept",
    [
        ('echo \'{"status": "failed"}\'; exit 1', False),  # a verdict: refused
        ("echo usage >&2; exit 2", True),  # not a verdict
        ("kill -9 $$", True),  # a crash
    ],
    ids=["refused", "usage", "crash"],
)
def test_only_a_refusal_renames_the_run_failed(rendered, tmp_path, monkeypatch, body, kept):
    verifier = fake_verifier(tmp_path, body)
    monkeypatch.setattr(publish.timeline, "binary", lambda: verifier)
    root = tmp_path / "root"
    with pytest.raises(RuntimeError) as caught:
        publish.publish(rendered, root)
    entries = sorted(root.iterdir())
    if kept:
        assert "unverified, not refused" in str(caught.value)
        marker, entry = entries
        assert not entry.name.startswith(".") and (entry / "manifest.json").is_file()
        assert marker.name == f".unverified-{entry.name}" and "gave no verdict" in marker.read_text()
    else:
        (entry,) = entries
        assert str(caught.value).startswith("verify-run refused") and entry.name.startswith(".failed-")


def test_a_verify_run_timeout_is_not_a_refusal(rendered, tmp_path, monkeypatch):
    real = subprocess.run

    def slow(args, **kw):
        if "verify-run" in args:
            raise subprocess.TimeoutExpired(args, kw.get("timeout"))
        return real(args, **kw)

    monkeypatch.setattr(publish.subprocess, "run", slow)
    root = tmp_path / "root"
    with pytest.raises(RuntimeError, match="unverified, not refused.*ran over") as caught:
        publish.publish(rendered, root)
    marker, entry = sorted(root.iterdir())
    assert not entry.name.startswith(".") and not str(caught.value).startswith("verify-run refused")
    assert marker.name == f".unverified-{entry.name}" and "ran over" in marker.read_text()
    monkeypatch.undo()
    assert verify(entry).returncode == 0  # the run itself was good all along
