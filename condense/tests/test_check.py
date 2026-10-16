"""check writes check.json: per gate its limits, measured values and verdict, bound to the edit it measured."""

import copy
import json
import subprocess

import pytest

from condense import avsync, check, publish

LEAD = 0.087  # the v2 bug: the sound started 87 ms after the picture, and the edit played it that much early


def measured(joined):
    """The thirds of the edit the joined measure had frames to measure in: the synthetic edit ends in a card."""
    return [third for third in joined["thirds"].values() if third["verdict"] != "nothing_to_measure"]


def leading(rendered, tmp_path, lead):
    """The in-sync edit with its sound moved `lead` seconds early."""
    moved = copy.copy(rendered)
    moved.out = tmp_path / "talk.lead.mp4"
    early = f"atrim=start={lead},asetpts=PTS-STARTPTS,apad"
    remux = ["-i", rendered.out, "-map", "0:v", "-map", "0:a", "-c:v", "copy", "-af", early, "-c:a", "aac"]
    subprocess.run(["ffmpeg", "-v", "error", "-y", *remux, "-shortest", moved.out], check=True)
    return moved


def test_the_report_binds_the_edit_and_records_every_measurement(rendered, tmp_path):
    report = tmp_path / "check.json"
    assert check.check(rendered, ["silence", "loud", "sync", "captions"], report=report)
    r = json.loads(report.read_text())
    assert r["kind"] == "condense_check" and r["passed"] and r["failed"] == [] and r["not_measured"] == []
    assert r["status"] == "partial"  # every gate that ran passed, but bounds did not run
    assert r["delivery"]["sha256"] == publish.sha256(rendered.out)
    assert r["edl_sha256"] == publish.sha256(rendered.f("edl", "json"))
    assert r["ran"] == ["silence", "loud", "sync", "captions"] and not r["complete"]  # bounds needs whisper

    silence, loud, sync = (r["gates"][name] for name in ("silence", "loud", "sync"))
    assert silence["measured"]["hits"] == 0 and silence["limits"]["silence_s"] == 1.0
    assert loud["limits"] == {
        "target_lufs": -16.0,
        "loudness_lu": 1.0,
        "true_peak_below_dbtp": 0.0,
        "render_true_peak_dbtp": -1.5,
    }
    assert abs(loud["measured"]["deviation_lu"]) <= 1 and loud["measured"]["true_peak_dbtp"] < 0
    assert sync["limits"] == {"sync_ms": 20, "min_clear_spots": 4, "clear_correlation": 0.75, "clear_sharpness": 1.15}
    assert sync["passed"] and sync["verdict"] == "passed"
    probe, real = sync["measured"]["probe"], sync["measured"]["real"]
    assert [c["verdict"] for c in real["clips"]] == ["passed", "no_1x_speech"]  # the card plays no speech
    assert len(real["clips"][0]["spots"]) >= avsync.MIN_CLEAR
    assert [c["clip"] for c in probe["clips"]] == ["talk"]  # the card has no picture of its own to probe
    assert probe["clips"][0]["windows"]["all"]["max_abs_ms"] <= 20
    assert real["clips"][0]["spots"] and abs(real["clips"][0]["median_ms"]) <= 5
    start = real["thirds"]["start"]
    assert start and start["spots"] >= 1 and abs(start["median_ms"]) <= 5
    joined = sync["measured"]["joined"]  # the whole edit, sped speech too, against the lossless parts
    assert joined["measured"] and set(joined["thirds"]) == {"start", "middle", "end"}
    assert len(measured(joined)) >= 2 and joined["verdict"] == "passed"
    assert all(third["verdict"] == "passed" and abs(third["median_ms"]) <= 5 for third in measured(joined))
    assert all(third["spots"] >= avsync.MIN_CLEAR for third in measured(joined))
    t = [spot["t_s"] for spot in joined["spots"]]
    assert len(set(t)) == len(t)  # every spot is a different frame

    cues = r["gates"]["captions"]
    assert cues["gated"] is False and cues["measured"]["sampled"] >= 2
    # the fake words start where each burst starts, so a caption lands on its sound within about a frame
    assert cues["measured"]["offsets_ms"] and cues["measured"]["max_abs_ms"] <= 40

    s = r["summary"]
    assert s["silence_hits"] == 0 and s["integrated_lufs"] == loud["measured"]["integrated_lufs"]
    assert s["sync_probe_max_abs_ms"] <= 20 and s["sync_real_median_ms"]["start"] == start["median_ms"]


def test_a_failed_gate_is_recorded_and_unknown_checks_are_refused(rendered, tmp_path):
    quiet = copy.copy(rendered)
    quiet.encode = rendered.encode | {"loudness": -30.0}  # a target the -16 LUFS edit misses by 14 LU
    report = tmp_path / "check.json"
    assert not check.check(quiet, ["silence", "loud"], report=report)
    r = json.loads(report.read_text())
    assert not r["passed"] and r["failed"] == ["loud"] and r["gates"]["silence"]["passed"]
    assert r["status"] == "failed"
    assert r["gates"]["loud"]["limits"]["target_lufs"] == -30.0
    assert r["gates"]["loud"]["measured"]["deviation_lu"] == pytest.approx(14, abs=1)
    with pytest.raises(ValueError, match="unknown checks"):
        check.check(rendered, ["loudness"], report=report)


def test_an_87_ms_audio_lead_fails_the_sync_gate(rendered, tmp_path, capsys):
    """Reintroduce the v2 bug on the in-sync edit: its sound plays 87 ms before its picture."""
    lead = leading(rendered, tmp_path, LEAD)
    report = tmp_path / "check.json"
    assert not check.check(lead, ["sync"], report=report)
    r = json.loads(report.read_text())
    assert r["failed"] == ["sync"] and not r["gates"]["sync"]["passed"]
    probe, real = r["gates"]["sync"]["measured"]["probe"], r["gates"]["sync"]["measured"]["real"]
    assert probe["passed"]  # the coded stand-in never sees the delivered file; the real measure must catch it
    assert not real["passed"] and real["clips"][0]["median_ms"] == pytest.approx(LEAD * 1000, abs=3)
    joined = r["gates"]["sync"]["measured"]["joined"]
    assert not joined["passed"]
    medians = [third["median_ms"] for third in measured(joined)]
    assert len(medians) >= 2 and medians == pytest.approx([LEAD * 1000] * len(medians), abs=3)
    assert "FAILED ['sync']" in capsys.readouterr().out


@pytest.mark.parametrize("lead", [1.0, 3.0, 8.0])
def test_a_lead_beyond_the_search_window_fails_the_sync_gate(rendered, tmp_path, lead):
    """The sound search reaches 0.25 s to each side. Beyond it every peak is spurious: no spot is clear, and a
    measure that tried enough spots and found too few clear ones fails, whatever its few spurious spots say."""
    report = tmp_path / "check.json"
    assert not check.check(leading(rendered, tmp_path, lead), ["sync"], report=report)
    r = json.loads(report.read_text())
    sync = r["gates"]["sync"]
    assert r["status"] == "failed" and r["failed"] == ["sync"] and sync["verdict"] == "failed"
    real, joined = sync["measured"]["real"], sync["measured"]["joined"]
    talk = real["clips"][0]
    assert talk["verdict"] == "failed" and talk["tried_spots"] >= avsync.MIN_CLEAR
    assert len(talk["spots"]) < avsync.MIN_CLEAR and real["verdict"] == "failed"
    assert joined["verdict"] == "failed" and len(measured(joined)) >= 2
    assert all(third["verdict"] == "failed" for third in measured(joined))
    assert all(spot["correlation"] >= avsync.CLEAR_CORR for spot in joined["spots"] + talk["spots"])


def test_missing_parts_leave_the_sync_gate_not_measured_and_not_passed(rendered, tmp_path):
    """The joined measure needs the lossless parts in work/. Without them sync does not pass, and the report
    says not_measured rather than passed or failed."""
    bare = copy.copy(rendered)
    bare.work = tmp_path / "work"
    bare.work.mkdir()
    for path in rendered.work.iterdir():
        if path.is_file() and ".part" not in path.name:
            (bare.work / path.name).symlink_to(path)
    report = tmp_path / "check.json"
    assert not check.check(bare, ["sync"], report=report)
    r = json.loads(report.read_text())
    sync = r["gates"]["sync"]
    assert r["status"] == "not_measured" and r["failed"] == [] and r["not_measured"] == ["sync"]
    assert not r["passed"] and not sync["passed"] and sync["verdict"] == "not_measured"
    joined = sync["measured"]["joined"]
    assert joined == {
        "limit_ms": 20,
        "verdict": "not_measured",
        "passed": False,
        "measured": False,
        "spots": [],
        "tried_spots": 0,
        "unclear_spots": 0,
        "thirds": None,
    }
    assert sync["measured"]["real"]["verdict"] == "passed"  # the other measures still ran


def test_a_measure_needs_enough_clear_spots():
    limit = 20
    assert avsync.judged([1.0] * 4, 8, limit) == ("passed", 1.0)
    assert avsync.judged([30.0] * 4, 8, limit) == ("failed", 30.0)
    assert avsync.judged([1.0] * 3, 8, limit) == ("failed", 1.0)  # tried enough, too few clear
    assert avsync.judged([1.0] * 3, 3, limit) == ("not_measured", 1.0)  # too few tried to say
    assert avsync.judged([], 0, limit) == ("not_measured", None)
    assert avsync.overall([]) == "not_measured"
    assert avsync.overall(["passed", "not_measured"]) == "not_measured"
    assert avsync.overall(["not_measured", "failed"]) == "failed"
    assert avsync.overall(["passed", "passed"]) == "passed"


def test_a_partial_run_never_replaces_the_complete_report(rendered):
    complete, partial = rendered.f(*publish.CHECK_REPORT), rendered.f(*publish.PARTIAL_REPORT)
    complete.write_text("the complete report\n")
    try:
        assert check.check(rendered, ["silence"])
        assert complete.read_text() == "the complete report\n"
        r = json.loads(partial.read_text())
        assert r["status"] == "partial" and r["ran"] == ["silence"] and not r["complete"]
    finally:
        complete.unlink(missing_ok=True)
        partial.unlink(missing_ok=True)
