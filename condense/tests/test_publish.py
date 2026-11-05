"""A published condense run is hash-bound, carries the edl_v1 mapping and passes verify-run; tampering fails it."""

import json
import os
import shutil
import subprocess

import pytest

from condense import check, publish, render, timeline


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


def test_a_newer_failing_partial_check_of_the_same_edit_refuses_the_publish(rendered, report, tmp_path):
    """check.json passed, then `check sync` alone failed on the same edit: check.json no longer stands."""
    partial = rendered.f(*publish.PARTIAL_REPORT)
    try:
        assert check.check(rendered, ["silence"], report=report)
        assert check.check(rendered, ["silence"])
        failing = json.loads(partial.read_text()) | {"status": "failed", "passed": False, "failed": ["sync"]}
        partial.write_text(json.dumps(failing))
        os.utime(report, ns=(partial.stat().st_mtime_ns - 10**9,) * 2)
        with pytest.raises(RuntimeError, match="newer than check.json, says failed for this edit"):
            publish.publish(rendered, tmp_path / "a")
        assert not (tmp_path / "a").exists() or list((tmp_path / "a").iterdir()) == []
        os.utime(partial, ns=(report.stat().st_mtime_ns - 10**9,) * 2)  # an older partial was superseded
        assert publish.publish(rendered, tmp_path / "b")
        os.utime(partial, ns=(report.stat().st_mtime_ns + 10**9,) * 2)
        partial.write_text(json.dumps(failing | {"edl_sha256": "0" * 64}))  # a newer partial of another edit
        os.utime(partial, ns=(report.stat().st_mtime_ns + 10**9,) * 2)
        assert publish.publish(rendered, tmp_path / "c")
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


@pytest.fixture
def uploaded(rendered):
    """talk.upload.mp4 and, beside a stand-in talk.corrected.mp4, talk.corrected.upload.mp4, as render and overlay
    write them with [encode] upload = "h264"; removed afterwards so no other test publishes them."""
    edl = json.loads(rendered.f("edl", "json").read_text())
    corrected = rendered.out.with_suffix(".corrected.mp4")
    made = [corrected, *(rendered.out.with_suffix(s) for s in (".upload.mp4", ".corrected.upload.mp4"))]
    try:
        shutil.copy2(rendered.out, corrected)
        render.upload(rendered, edl)
        render.upload(rendered, edl, suffix=".corrected")
        yield made
    finally:
        for path in made:
            path.unlink(missing_ok=True)


def test_the_upload_copies_are_carried_hash_bound_and_verified(rendered, uploaded, tmp_path):
    run_dir = publish.publish(rendered, tmp_path)
    m = json.loads((run_dir / "manifest.json").read_text())
    names = [u["file"] for u in m["uploads"]]
    assert names == ["talk.upload.mp4", "talk.corrected.upload.mp4"]
    assert [u["of"] for u in m["uploads"]] == ["talk.mp4", "talk.corrected.mp4"]
    for entry in m["uploads"]:
        name = entry["file"]
        assert m["output_sha256"][name] == publish.sha256(run_dir / name) == publish.sha256(rendered.out.parent / name)
        assert render.boxes(run_dir / name) == (entry["moov_offset"], entry["mdat_offset"])
        assert entry["moov_offset"] < entry["mdat_offset"] and entry["faststart"] is True
        assert entry["video_frames"] == m["delivery"]["video_frames"]
        assert (entry["video_first_pts"], entry["video_first_dts"], entry["video_b_frames"]) == (0, 0, 0)
        # the edit's AAC audio is copied: its first packet sits 1024 samples (the encoder's priming) before 0
        assert (entry["audio_first_pts"], entry["audio_time_base"], entry["audio_start_pts"]) == (-1024, "1/48000", 0)
        assert entry["audio_packets_sha256"] == render.audio_packets(rendered.out)
    p = verify(run_dir)
    assert p.returncode == 0, p.stdout + p.stderr
    receipt = json.loads(p.stdout)
    assert [(u["file"], u["status"]) for u in receipt["uploads"]] == [(n, "verified") for n in names]
    # verify-run reads the boxes again: an offset the file does not have is refused
    text = (run_dir / "manifest.json").read_text()
    moov = m["uploads"][0]["moov_offset"]
    (run_dir / "manifest.json").write_text(text.replace(f'"moov_offset": {moov}', f'"moov_offset": {moov + 8}', 1))
    p = verify(run_dir)
    assert p.returncode == 1 and json.loads(p.stdout)["reason"] == "upload_invalid"


def remux(path, *args):
    """Rewrite path in place with stream copies and the given muxer options."""
    out = path.with_name("remux." + path.name)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", path, "-c", "copy", *args, out], check=True)
    out.replace(path)


def test_an_upload_copy_without_faststart_is_refused_before_staging(rendered, uploaded, tmp_path):
    remux(uploaded[1])  # no +faststart: the muxer writes moov after mdat
    moov, mdat = render.boxes(uploaded[1])
    assert mdat < moov
    with pytest.raises(RuntimeError, match="an upload copy is \\+faststart"):
        publish.publish(rendered, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_an_upload_copy_of_another_edit_is_refused(rendered, uploaded, tmp_path):
    other = uploaded[1].with_name("other.mp4")
    # the same picture, the sound encoded again: not this edit's audio packets
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", uploaded[1], "-c:v", "copy", "-c:a", "aac", "-b:a", "48k"]
    subprocess.run([*cmd, "-movflags", "+faststart", other], check=True)
    other.replace(uploaded[1])
    with pytest.raises(RuntimeError, match="does not carry this edit's audio packets"):
        publish.publish(rendered, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_a_corrected_upload_copy_needs_its_corrected_copy(rendered, uploaded, tmp_path):
    uploaded[0].unlink()
    with pytest.raises(RuntimeError, match="has no talk.corrected.mp4 beside it"):
        publish.publish(rendered, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_a_configured_upload_copy_must_exist(rendered, tmp_path, monkeypatch):
    monkeypatch.setitem(rendered.encode, "upload", "h264")
    with pytest.raises(FileNotFoundError, match="upload is set; run the render stage again"):
        publish.publish(rendered, tmp_path)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "data, found",
    [
        (b"\0\0\0\x10ftypisom\0\0\0\0" + b"\0\0\0\x08moov" + b"\0\0\0\x0cmdat\0\0\0\0", (16, 24)),
        (b"\0\0\0\x08ftyp" + b"\0\0\0\x0cmdat\0\0\0\0" + b"\0\0\0\x08moov", (20, 8)),
        (b"\0\0\0\x08moov" + b"\0\0\0\x01mdat" + (24).to_bytes(8, "big") + bytes(8), (0, 8)),
        (b"\0\0\0\x08moov" + b"\0\0\0\0mdat" + bytes(5), (0, 8)),
        (b"\0\0\0\x08ftyp", (None, None)),
    ],
    ids=["faststart", "moov-last", "largesize", "to-end", "none"],
)
def test_boxes_reads_top_level_headers(tmp_path, data, found):
    path = tmp_path / "x.mp4"
    path.write_bytes(data)
    assert render.boxes(path) == found


@pytest.mark.parametrize("data", [b"\0\0\0\x08moov\0\0\0\x40mdat", b"\0\0\0\x08moov\0\0", b"\0\0\0\x04moov"])
def test_boxes_refuses_a_box_that_overruns_the_file(tmp_path, data):
    path = tmp_path / "x.mp4"
    path.write_bytes(data)
    with pytest.raises(RuntimeError, match="box"):
        render.boxes(path)
