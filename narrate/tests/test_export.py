"""narrate export: a verified run's narration.wav handed to a consumer as <stem>.wav (the TIN-7091 deck layout,
NN-<slide-id>.wav beside camera takes), refusing anything that would replace a file or mislabel a page."""

import json
import os
import shutil
import stat

import pytest
from conftest import SLIDE, Workspace

from narrate import __main__ as cli
from narrate import export, render
from narrate.config import Config
from narrate.ir import sha256_file


@pytest.fixture(scope="module")
def rendered(tmp_path_factory):
    ws = Workspace(tmp_path_factory.mktemp("export") / "ws")
    final, manifest = render.render(Config(ws.write(SLIDE)))
    return final, manifest


@pytest.fixture
def run(rendered, tmp_path):
    """A private copy of the rendered run, so a test may tamper with it."""
    final, manifest = rendered
    copy = tmp_path / "run"
    shutil.copytree(final, copy)
    return copy, manifest


@pytest.fixture
def narration(tmp_path):
    d = tmp_path / "narration"
    d.mkdir()
    return d


def test_a_verified_run_lands_as_its_stem_with_a_receipt(run, narration):
    run_dir, manifest = run
    receipt = export.export(run_dir, narration, "07-3")
    target = narration / "07-3.wav"
    assert target.read_bytes() == (run_dir / "narration.wav").read_bytes()
    assert receipt == {
        "ok": True,
        "state": "written",
        "file": "07-3.wav",
        "sha256": manifest["output_sha256"]["narration.wav"],
        "run_id": manifest["run_id"],
        "content_sha256": manifest["content_sha256"],
        "slide": "3",
        "synthetic": True,
        "sample_rate": manifest["timeline"]["sample_rate"],
        "total_samples": manifest["timeline"]["total_samples"],
    }
    assert sorted(p.name for p in narration.iterdir()) == ["07-3.wav"]
    assert str(narration) not in json.dumps(receipt)


def test_the_same_bytes_again_are_unchanged(run, narration):
    run_dir, _ = run
    export.export(run_dir, narration, "3")
    again = export.export(run_dir, narration, "3")
    assert again["state"] == "unchanged"


@pytest.mark.parametrize("other", ["07-3.wav", "07-3.mp4", "07-3.m4a"])
def test_an_existing_take_is_never_replaced(run, narration, other):
    run_dir, _ = run
    (narration / other).write_bytes(b"the operator's own take")
    with pytest.raises(export.ExportError) as caught:
        export.export(run_dir, narration, "07-3")
    assert caught.value.code == "export_take_exists"
    assert (narration / other).read_bytes() == b"the operator's own take"
    assert not (narration / "07-3.wav").exists() or other == "07-3.wav"


def test_a_symlink_under_the_name_is_refused(run, narration, tmp_path):
    run_dir, _ = run
    (narration / "07-3.wav").symlink_to(run_dir / "narration.wav")
    with pytest.raises(export.ExportError, match="export_take_exists"):
        export.export(run_dir, narration, "07-3")


def test_a_build_take_of_the_page_is_not_this_stem(run, narration):
    """NN-<slide>-b2.wav and NN-<slide>-guitar.wav are other files of the page, not a take under this stem."""
    run_dir, _ = run
    (narration / "07-3-b2.wav").write_bytes(b"build two")
    (narration / "07-3-guitar.wav").write_bytes(b"guitar")
    assert export.export(run_dir, narration, "07-3")["state"] == "written"


@pytest.mark.parametrize("stem", ["07-4", "07-33", "x3"])
def test_a_stem_for_another_slide_is_refused(run, narration, stem):
    run_dir, _ = run
    with pytest.raises(export.ExportError, match="export_slide_mismatch"):
        export.export(run_dir, narration, stem)
    assert list(narration.iterdir()) == []


@pytest.mark.parametrize("stem", ["", "../07-3", "07/3", ".07-3", "07-3.wav", "a" * 129, "07 3"])
def test_a_stem_that_is_not_a_plain_name_is_refused(run, narration, stem):
    run_dir, _ = run
    with pytest.raises(export.ExportError, match="export_stem_invalid"):
        export.export(run_dir, narration, stem)


def test_a_tampered_run_is_not_exported(run, narration):
    run_dir, _ = run
    wav = run_dir / "narration.wav"
    data = bytearray(wav.read_bytes())
    data[-1] ^= 1
    wav.write_bytes(bytes(data))
    with pytest.raises(export.ExportError) as caught:
        export.export(run_dir, narration, "07-3")
    assert caught.value.code == "export_run_unverified" and "outputs" in caught.value.detail
    assert list(narration.iterdir()) == []


def test_a_missing_target_directory_is_refused(run, tmp_path):
    run_dir, _ = run
    with pytest.raises(export.ExportError, match="export_target_missing"):
        export.export(run_dir, tmp_path / "nowhere", "07-3")


def test_no_partial_file_is_left_when_the_copy_fails(run, narration, monkeypatch):
    run_dir, _ = run
    monkeypatch.setattr(
        export, "sha256_file", lambda path: "0" * 64 if path.name.endswith(".partial") else sha256_file(path)
    )
    with pytest.raises(export.ExportError, match="export_copy_changed"):
        export.export(run_dir, narration, "07-3")
    assert list(narration.iterdir()) == []


def test_a_name_that_appears_during_the_copy_is_kept(run, narration, monkeypatch):
    run_dir, _ = run
    real_link = os.link

    def racing_link(src, dst):
        (narration / "07-3.wav").write_bytes(b"arrived first")
        return real_link(src, dst)

    monkeypatch.setattr(export.os, "link", racing_link)
    with pytest.raises(export.ExportError, match="export_take_exists"):
        export.export(run_dir, narration, "07-3")
    assert (narration / "07-3.wav").read_bytes() == b"arrived first"
    assert sorted(p.name for p in narration.iterdir()) == ["07-3.wav"]


def test_the_export_keeps_the_mode_of_the_run(run, narration):
    run_dir, _ = run
    source = run_dir / "narration.wav"
    for mode in (0o644, 0o640):
        source.chmod(mode)
        folder = narration / f"m{mode:o}"
        folder.mkdir()
        export.export(run_dir, folder, "07-3")
        assert stat.S_IMODE((folder / "07-3.wav").stat().st_mode) == mode


def test_a_directory_without_hard_links_is_a_typed_refusal(run, narration, monkeypatch):
    run_dir, _ = run

    def no_link(src, dst):
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(export.os, "link", no_link)
    with pytest.raises(export.ExportError, match="export_link_failed"):
        export.export(run_dir, narration, "07-3")
    assert list(narration.iterdir()) == []


def test_cli_export_prints_the_receipt_and_refuses_with_a_code(run, narration, capsys):
    run_dir, _ = run
    assert cli.main(["export", str(run_dir), "--to", str(narration), "--stem", "07-3"]) == 0
    assert json.loads(capsys.readouterr().out)["file"] == "07-3.wav"
    assert cli.main(["export", str(run_dir), "--to", str(narration), "--stem", "07-4"]) == 1
    assert json.loads(capsys.readouterr().err)["refused"] == "export_slide_mismatch"
