"""check writes check.json: per gate its limits, measured values and verdict, bound to the edit it measured."""

import copy
import json
import subprocess

import pytest

from condense import check, publish

LEAD = 0.087  # the v2 bug: the sound started 87 ms after the picture, and the edit played it that much early


def test_the_report_binds_the_edit_and_records_every_measurement(rendered, tmp_path):
    report = tmp_path / "check.json"
    assert check.check(rendered, ["silence", "loud", "sync", "captions"], report=report)
    r = json.loads(report.read_text())
    assert r["kind"] == "condense_check" and r["passed"] and r["failed"] == []
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
    assert sync["limits"] == {"sync_ms": 20} and sync["passed"]
    probe, real = sync["measured"]["probe"], sync["measured"]["real"]
    assert [c["clip"] for c in probe["clips"]] == ["talk"]  # the card has no picture of its own to probe
    assert probe["clips"][0]["windows"]["all"]["max_abs_ms"] <= 20
    assert real["clips"][0]["spots"] and abs(real["clips"][0]["median_ms"]) <= 5
    start = real["thirds"]["start"]
    assert start and start["spots"] >= 1 and abs(start["median_ms"]) <= 5
    joined = sync["measured"]["joined"]  # the whole edit, sped speech too, against the lossless parts
    assert joined["measured"] and set(joined["thirds"]) == {"start", "middle", "end"}
    assert all(third and abs(third["median_ms"]) <= 5 for third in joined["thirds"].values())

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
    assert r["gates"]["loud"]["limits"]["target_lufs"] == -30.0
    assert r["gates"]["loud"]["measured"]["deviation_lu"] == pytest.approx(14, abs=1)
    with pytest.raises(ValueError, match="unknown checks"):
        check.check(rendered, ["loudness"], report=report)


def test_an_87_ms_audio_lead_fails_the_sync_gate(rendered, tmp_path, capsys):
    """Reintroduce the v2 bug on the in-sync edit: its sound plays 87 ms before its picture."""
    lead = copy.copy(rendered)
    lead.out = tmp_path / "talk.lead.mp4"
    early = f"atrim=start={LEAD},asetpts=PTS-STARTPTS,apad"
    remux = ["-i", rendered.out, "-map", "0:v", "-map", "0:a", "-c:v", "copy", "-af", early, "-c:a", "aac"]
    subprocess.run(["ffmpeg", "-v", "error", "-y", *remux, "-shortest", lead.out], check=True)
    report = tmp_path / "check.json"
    assert not check.check(lead, ["sync"], report=report)
    r = json.loads(report.read_text())
    assert r["failed"] == ["sync"] and not r["gates"]["sync"]["passed"]
    probe, real = r["gates"]["sync"]["measured"]["probe"], r["gates"]["sync"]["measured"]["real"]
    assert probe["passed"]  # the coded stand-in never sees the delivered file; the real measure must catch it
    assert not real["passed"] and real["clips"][0]["median_ms"] == pytest.approx(LEAD * 1000, abs=3)
    joined = r["gates"]["sync"]["measured"]["joined"]
    assert not joined["passed"]
    assert [t["median_ms"] for t in joined["thirds"].values()] == pytest.approx([LEAD * 1000] * 3, abs=3)
    assert "FAILED ['sync']" in capsys.readouterr().out
