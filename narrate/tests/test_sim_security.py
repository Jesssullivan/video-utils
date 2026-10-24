"""Metadata and fake-process regressions; no audio, model, service or network is used."""

import copy
import json
import subprocess
from types import SimpleNamespace

import pytest

from narrate import sim


def reply():
    return {
        "ok": True,
        "scores": [{"id": "c1", "sim": 0.8, "a_seconds": 1.0, "b_seconds": 10.0}],
        "torch": "synthetic",
        "speechbrain": "synthetic",
        "threads": 4,
    }


@pytest.mark.parametrize(
    "change",
    [
        lambda r: [],
        lambda r: {**r, "ok": 1},
        lambda r: {**r, "ok": False},
        lambda r: {**r, "scores": []},
        lambda r: {**r, "scores": [r["scores"][0]] * 2},
        lambda r: {**r, "scores": [{**r["scores"][0], "id": "wrong"}]},
        lambda r: {**r, "scores": [{**r["scores"][0], "id": 1}]},
        lambda r: {**r, "scores": [None]},
        lambda r: {**r, "scores": {}},
        lambda r: {**r, "torch": None},
        lambda r: {**r, "speechbrain": ""},
        lambda r: {**r, "threads": True},
        lambda r: {**r, "threads": 8},
    ],
)
def test_worker_shape_refused(monkeypatch, change):
    result = SimpleNamespace(returncode=0, stdout=json.dumps(change(reply())), stderr="")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: result)
    with pytest.raises(RuntimeError, match="invalid SIM worker response"):
        sim.Scorer().score([("c1", "unopened-a", "unopened-b")])


@pytest.mark.parametrize(
    "key,value",
    [
        ("sim", 5.0),
        ("sim", -1.1),
        ("sim", float("nan")),
        ("sim", float("inf")),
        ("sim", True),
        ("sim", "0.9"),
        ("sim", None),
        ("a_seconds", float("nan")),
        ("a_seconds", 0),
        ("b_seconds", -1),
        ("b_seconds", True),
    ],
)
def test_worker_numbers_refused(monkeypatch, key, value):
    data = reply()
    data["scores"][0][key] = value
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout=json.dumps(data), stderr="")
    )
    with pytest.raises(RuntimeError, match="invalid SIM worker response"):
        sim.Scorer().score([("c1", "unopened-a", "unopened-b")])


def test_nonzero_worker_never_measured(tmp_path):
    worker = tmp_path / "fake-python"
    worker.write_text("#!/bin/sh\nprintf '%s\\n' '" + json.dumps(reply()) + "'\nprintf diagnostic >&2\nexit 9\n")
    worker.chmod(0o700)
    scorer = sim.Scorer()
    scorer.python = str(worker)
    with pytest.raises(RuntimeError, match="exit 9"):
        scorer.score([("c1", "unopened-a", "unopened-b")])
    assert scorer.runtime == {}


@pytest.mark.parametrize(
    "payload", ["{", "null", '"text"', '{"ok":true}', '{"ok":true,"scores":[{"id":"c1","sim":0.8}]}']
)
def test_malformed_worker_refused(monkeypatch, payload):
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout=payload, stderr="diagnostic")
    )
    with pytest.raises(RuntimeError, match="invalid SIM worker response"):
        sim.Scorer().score([("c1", "unopened-a", "unopened-b")])


def test_exact_ids_and_cosine_boundaries(monkeypatch):
    data = reply()
    data["scores"] = [{**data["scores"][0], "id": "c2", "sim": -1}, {**data["scores"][0], "sim": 1}]
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout=json.dumps(data), stderr="library diagnostic"),
    )
    assert set(sim.Scorer().score([("c1", "a", "b"), ("c2", "a", "b")])) == {"c1", "c2"}
    data["scores"][0]["id"] = "c1"
    with pytest.raises(RuntimeError, match="duplicate"):
        sim.Scorer().score([("c1", "a", "b"), ("c2", "a", "b")])


@pytest.mark.parametrize("override", [None, "reference"])
@pytest.mark.parametrize("case", ["revoked", "scope", "voice_scope", "no_consent", "no_evidence", "changed_clip"])
def test_current_reference_consent_precedes_audio(tmp_path, monkeypatch, override, case):
    manifest = {
        "voices": [{"speaker": "s", "voice": "reference", "ref_clip_sha256": "clip"}],
        "timeline": {"edl": {"file": "edl.json"}},
        "chunks": [{"id": "c1"}],
        "job": {"scope": "OwnContent"},
    }
    (tmp_path / "edl.json").write_text(json.dumps({"segments": [{"voice": "reference", "chunks": [{"id": "c1"}]}]}))
    voice = {"consentId": "consent", "scope": "OwnContent", "refClipSha256": "clip"}
    consent = {"revokedAt": None, "scopes": ["OwnContent"], "evidenceSha256": "evidence"}
    registry = {"voices": {"reference": voice}, "consents": {"consent": consent}}
    index = {"clip": tmp_path / "never-opened", "evidence": tmp_path / "never-opened-evidence"}
    if case == "revoked":
        consent["revokedAt"] = "synthetic-revocation"
    elif case == "scope":
        consent["scopes"] = []
    elif case == "voice_scope":
        voice["scope"] = "OtherScope"
    elif case == "no_consent":
        registry["consents"] = {}
    elif case == "no_evidence":
        del index["evidence"]
    else:
        voice["refClipSha256"] = "changed"
    touched = []

    def forbidden(*args, **kwargs):
        touched.append(True)
        raise AssertionError("audio/model read before current reference admission")

    monkeypatch.setattr(sim.policy, "store_index", lambda _: copy.copy(index))
    monkeypatch.setattr(sim.audio, "read", forbidden)
    monkeypatch.setattr(sim, "to16k", forbidden)
    cfg = SimpleNamespace(store=tmp_path, registry=lambda: registry)
    scorer = SimpleNamespace(available=lambda: (True, "synthetic"), score=forbidden)
    result = sim.evaluate(tmp_path, manifest, cfg, reference_voice=override, scorer=scorer)
    assert result["status"] == "not_measured"
    assert "reference consent refused" in result["reason"] or (case == "changed_clip" and override is not None)
    assert touched == []


def test_invalid_worker_response_stays_not_measured(tmp_path, monkeypatch):
    """Exercise evaluate's refusal boundary with in-memory stand-ins, without audio I/O."""
    manifest = {
        "voices": [{"speaker": "s", "voice": "reference", "ref_clip_sha256": "clip"}],
        "timeline": {"edl": {"file": "edl.json"}},
        "chunks": [{"id": "c1", "out_start_s": 0, "out_end_s": 1}],
        "job": {"scope": "OwnContent"},
    }
    (tmp_path / "edl.json").write_text(json.dumps({"segments": [{"voice": "reference", "chunks": [{"id": "c1"}]}]}))
    registry = {
        "voices": {"reference": {"consentId": "c", "scope": "OwnContent", "refClipSha256": "clip"}},
        "consents": {"c": {"revokedAt": None, "scopes": ["OwnContent"], "evidenceSha256": "e"}},
    }
    monkeypatch.setattr(sim.policy, "store_index", lambda _: {"clip": tmp_path / "unopened", "e": tmp_path / "e"})
    monkeypatch.setattr(sim.audio, "read", lambda _: SimpleNamespace(rate=1, seconds=1, samples=[0]))
    monkeypatch.setattr(sim.audio, "Pcm", lambda *a: SimpleNamespace(seconds=1, write=lambda p: p))
    monkeypatch.setattr(sim, "to16k", lambda src, dst: dst)
    monkeypatch.setattr(sim, "run", lambda *a: None)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout=json.dumps({**reply(), "scores": []}), stderr=""),
    )
    scorer = sim.Scorer()
    monkeypatch.setattr(scorer, "available", lambda: (True, "synthetic"))
    result = sim.evaluate(tmp_path, manifest, SimpleNamespace(store=tmp_path, registry=lambda: registry), scorer=scorer)
    assert result["status"] == "not_measured"
    assert "scores must match" in result["reason"]
    assert "passed" not in result and "median" not in result
