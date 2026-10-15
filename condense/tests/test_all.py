"""`condense all` runs every stage on the synthetic talk and ends in a run that verify-run accepted.

Only whisper is faked: the transcribe stage writes the conftest's whisper JSON. A refused run exits non-zero.
"""

import json
import shutil
import subprocess

import pytest
from conftest import TOML, fake_whisper, fake_words

from condense import __main__ as cli
from condense import audio, publish, timeline, transcribe

CHECKS = ["silence", "loud"]  # sync and bounds have their own tests; bounds needs whisper


def fake_transcribe(cfg, clip):
    audio.extract(cfg, clip)
    cfg.f(clip, "dtw.json").write_text(json.dumps(fake_whisper(fake_words())))


@pytest.fixture(scope="module")
def fresh(talk, tmp_path_factory):
    """A talk.toml with no stage run yet, on the synthetic recording."""
    base = tmp_path_factory.mktemp("all")
    shutil.copy2(talk.clips[0]["file"], base / "talk.mkv")  # verify-run refuses a symlinked source
    (base / "talk.toml").write_text(TOML.format(extra=""))
    return base / "talk.toml"


@pytest.fixture(scope="module")
def ran_all(fresh, tmp_path_factory):
    root = tmp_path_factory.mktemp("published")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(transcribe, "transcribe", fake_transcribe)
        mp.setattr(publish, "ARTIFACTS", root)
        cli.main(["all", str(fresh), *CHECKS])
    return root


def runs(root):
    return sorted(p.name for p in root.iterdir())


def test_all_ends_in_publish():
    assert cli.ALL == [*cli.STAGES, "publish"]


def test_the_just_recipe_runs_the_same_stages():
    dump = subprocess.run(
        ["just", "--justfile", timeline.ROOT / "justfile", "--dump", "--dump-format", "json"],
        capture_output=True,
        text=True,
        check=True,
    )
    deps = json.loads(dump.stdout)["recipes"]["condense-all"]["dependencies"]
    assert [d["recipe"] for d in deps] == [f"condense-{name}" for name in cli.ALL]


def test_all_publishes_one_verified_run(ran_all):
    (name,) = runs(ran_all)
    run_dir = ran_all / name
    m = json.loads((run_dir / "manifest.json").read_text())
    assert m["kind"] == "condense_edit" and m["run_id"] == name
    assert {"talk.mp4", "edl.json", "talk.srt", "talk.vtt", "talk.corrected.mp4"} <= set(m["output_sha256"])
    p = subprocess.run([timeline.binary(), "verify-run", "--timeline", "edl_v1", run_dir], capture_output=True)
    assert p.returncode == 0, p.stdout + p.stderr


def test_all_exits_non_zero_when_verify_run_refuses(fresh, ran_all, tmp_path, monkeypatch):
    real = publish.manifest

    def tampered(*args):
        record = real(*args)
        record["output_sha256"]["talk.mp4"] = "0" * 64
        return record

    monkeypatch.setattr(transcribe, "transcribe", fake_transcribe)
    monkeypatch.setattr(publish, "ARTIFACTS", tmp_path)
    monkeypatch.setattr(publish, "manifest", tampered)
    with pytest.raises(SystemExit) as refused:
        cli.main(["all", str(fresh), *CHECKS])
    assert refused.value.code not in (0, None)
    assert "verify-run refused" in str(refused.value.code)
    (name,) = runs(tmp_path)
    assert name.startswith(".failed-")
