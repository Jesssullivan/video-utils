"""Lane W7a (TIN-7090): what the MCP tools need from the CLI, and the SIM scorer.

The CLI half: `render --json` returns the manifest path and a summary; job overrides are range-checked, recorded in
job.overrides and only tighten confidentiality and hosting; `engines --reach` connects without a request.

The SIM half runs with a fake worker interpreter (a script that answers the worker's JSON protocol) so the plumbing,
the model binding by digest, the reference lookup through the store and the decoy override are checked without
torch. The real ECAPA model scores synthetic formant voices against a decoy only when NARRATE_SIM_TEST_MODEL (the
registered embedding_model.ckpt) and NARRATE_SIM_TEST_PYTHON (an interpreter with torch and speechbrain, e.g.
`nix develop .#ml`) are both set; otherwise that case skips and says so. No clip, network or GPU is used.
"""

import array
import json
import math
import os
import random
import shutil
import socket
import stat
import sys
import wave
from pathlib import Path

import pytest
from conftest import SLIDE

from narrate import audio, evaluate, policy, qa, registry, render, sim
from narrate.__main__ import main
from narrate.config import Config

RATE = 16000
VOWELS = {"a": (730, 1090, 2440), "i": (270, 2290, 3010), "u": (300, 870, 2240), "e": (530, 1840, 2480)}


# -- synthetic voices: a glottal pulse train through three formant resonators ----------------------------------
def formant_voice(f0, scale, vowels, seconds, seed, breath=0.02):
    """A deterministic vowel string. f0 sets the pitch, scale the formants (a shorter vocal tract is above 1)."""
    rnd = random.Random(seed)
    per = int(seconds * RATE) // len(vowels)
    out, phase = [], 0.0
    for k, v in enumerate(vowels):
        src = []
        for i in range(per):
            t = (k * per + i) / RATE
            f = f0 * (1 + 0.04 * math.sin(2 * math.pi * 5.5 * t) + 0.06 * math.sin(2 * math.pi * 0.7 * t + k))
            phase += f * (1 + rnd.uniform(-0.01, 0.01)) / RATE
            pulse = 1.0 if phase >= 1 else 0.0
            phase -= pulse
            src.append(pulse + breath * rnd.uniform(-1, 1))
        mixed = [0.0] * per
        for formant, bw in zip(VOWELS[v], (80, 100, 120), strict=True):
            r = math.exp(-math.pi * bw * scale / RATE)
            c, g, y1, y2 = 2 * r * math.cos(2 * math.pi * formant * scale / RATE), 1 - r, 0.0, 0.0
            for i, x in enumerate(src):
                y = g * x + c * y1 - r * r * y2
                y2, y1 = y1, y
                mixed[i] += y
        out += [y * (min(1, i / 400, (per - i) / 400) if i < per * 0.85 else 0) for i, y in enumerate(mixed)]
    peak = max(abs(v) for v in out) or 1.0
    return audio.Pcm(RATE, array.array("h", (int(v / peak * 0.6 * 32767) for v in out)))


# -- the CLI the tools call ---------------------------------------------------------------------------------------
def test_render_json_returns_the_manifest_and_records_overrides(workspace, ffmpeg, capsys):
    toml = workspace.write(SLIDE)
    args = ["render", str(toml), "--json", "--max-takes", "1", "--min-sim", "0", "--confidential", "--no-hosted"]
    assert main(args) == 0
    summary = json.loads(capsys.readouterr().out)
    manifest = json.loads(Path(summary["manifest"]).read_text())
    assert summary["run_dir"] == str(Path(summary["manifest"]).parent) and summary["verified"] is True
    assert summary["synthetic"] is True and summary["kind"] == "narration_render"
    assert summary["overrides"] == {"max_takes": 1, "min_sim": 0.0, "confidential": True, "no_hosted": True}
    assert manifest["job"]["overrides"] == summary["overrides"]
    assert manifest["job"]["confidential"] is True and manifest["job"]["allowHosted"] is False
    assert manifest["job"]["gates"]["maxTakes"] == 1
    assert summary["flags"] == manifest["flags"] and summary["meets_acceptance_gate"] is (not manifest["flags"])
    assert str(workspace.store) not in json.dumps(summary)


@pytest.mark.parametrize(
    "extra",
    [["--max-takes", "4"], ["--fit-max-stretch", "0.2"], ["--min-sim", "1.5"], ["--chunk-max-codepoints", "10"]],
)
def test_out_of_range_overrides_are_refused_before_any_run(workspace, capsys, extra):
    toml = workspace.write(SLIDE)
    assert main(["render", str(toml), *extra]) == 1
    assert json.loads(capsys.readouterr().err)["refused"] == "override_invalid"
    assert workspace.runs() == []


def test_overrides_only_tighten():
    job = {"confidential": True, "allowHosted": False}
    with pytest.raises(render.RenderError):
        render.overrides_from({"confidential": False})
    assert render.apply_overrides(job, render.overrides_from({"no_hosted": True}))["allowHosted"] is False
    assert render.apply_overrides(job, {})["confidential"] is True


def test_a_voice_override_passes_the_same_consent_checks(workspace, capsys):
    toml = workspace.write(SLIDE)
    assert main(["render", str(toml), "--voice", "voice-nobody"]) == 1
    assert json.loads(capsys.readouterr().err)["refused"].startswith("voice")
    assert workspace.runs() == []


def test_engines_reach_connects_without_a_request(workspace):
    cfg = Config(workspace.write(SLIDE))
    assert registry.engines(cfg, probe_reach=True)[0]["reach"] == {"reachable": True, "how": "in process"}
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        found = registry.reach({"backend": "QwenTtsCpp", "endpoint": f"http://127.0.0.1:{port}/v1"})
        assert found["reachable"] is True and found["how"] == "tcp connect"
    closed = registry.reach({"backend": "QwenTtsCpp", "endpoint": f"http://127.0.0.1:{port}/v1"}, timeout=0.5)
    assert closed["reachable"] is False
    assert "127.0.0.1" not in json.dumps(found) + json.dumps(closed)


# -- SIM plumbing with a fake worker ------------------------------------------------------------------------------
FAKE_WORKER = """#!{python}
import json, sys
request = json.loads(sys.stdin.read())
assert request["threads"] <= 8
scores = [{{"id": p["id"], "sim": {match} if "{match_ref}" in p["b"] else 0.11, "a_seconds": 1.0,
            "b_seconds": 10.0}} for p in request["pairs"]]
print(json.dumps({{"ok": True, "scores": scores, "torch": "fake", "speechbrain": "fake"}}))
"""


def sim_workspace(workspace, tmp_path, monkeypatch, match=0.83):
    """A rendered run plus a [sim] block naming a dummy model registered by digest and a fake worker interpreter."""
    model = tmp_path / "embedding_model.ckpt"
    model.write_bytes(b"dummy speaker model")
    digest = qa.model_digest(model)
    monkeypatch.setattr(qa, "registered", lambda d, models=None: sim.SIM_MODEL_ID if d == digest else None)
    worker = tmp_path / "fake-python"
    ref = workspace.voices[0]["refClipSha256"][:16]
    worker.write_text(FAKE_WORKER.format(python=sys.executable, match=match, match_ref=ref))
    worker.chmod(worker.stat().st_mode | stat.S_IXUSR)
    decoy = formant_voice(215, 1.22, "eiua", 10.5, 3)
    decoy_sha = qa.sha256_file(decoy.write(workspace.store / "decoy.wav"))
    workspace.voices.append({**workspace.voices[0], "id": "voice-decoy", "refClipSha256": decoy_sha})
    workspace.extra = f'[sim]\nmodel = "{model}"\npython = "{worker}"\nthreads = 8\n'
    toml = workspace.write(SLIDE)
    final, _ = render.render(Config(toml))
    return toml, final


def test_sim_is_measured_per_chunk_with_wsim(workspace, ffmpeg, tmp_path, monkeypatch):
    toml, final = sim_workspace(workspace, tmp_path, monkeypatch)
    result = evaluate.evaluate(final, ("sim",), Config(toml))["metrics"]["sim"]
    assert result["status"] == "measured" and result["model_id"] == sim.SIM_MODEL_ID
    assert {c["sim"] for c in result["chunks"]} == {0.83}
    assert result["median"] == 0.83 and result["wsim"]["min"] == 0.83 and result["wsim"]["windows"] >= 1
    assert result["reference"]["ref_clip_sha256"] == [workspace.voices[0]["refClipSha256"]]
    assert result["calibrated"] is False and "uncalibrated" in result["note"]
    assert result["threads"] == 8 and result["torch"] == "fake"


def test_reference_voice_scores_against_a_decoy(workspace, ffmpeg, tmp_path, monkeypatch, capsys):
    toml, final = sim_workspace(workspace, tmp_path, monkeypatch)
    decoy = evaluate.evaluate(final, ("sim",), Config(toml), reference_voice="voice-decoy")["metrics"]["sim"]
    assert decoy["status"] == "measured" and {c["sim"] for c in decoy["chunks"]} == {0.11}
    assert {c["voice"] for c in decoy["chunks"]} == {"voice-decoy"}
    unknown = evaluate.evaluate(final, ("sim",), Config(toml), reference_voice="voice-absent")["metrics"]["sim"]
    assert unknown["status"] == "not_measured" and "not in the voice registry" in unknown["reason"]
    assert (
        main(["evaluate", str(final), "--config", str(toml), "--metrics", "sim", "--reference-voice", "voice-decoy"])
        == 0
    )
    assert json.loads(capsys.readouterr().out)["metrics"]["sim"]["median"] == 0.11
    assert main(["evaluate", str(final), "--metrics", "sim,mos"]) == 1
    assert json.loads(capsys.readouterr().err)["refused"] == "metric_unknown"


def test_sim_is_not_measured_without_its_inputs(workspace, ffmpeg, tmp_path, monkeypatch):
    toml, final = sim_workspace(workspace, tmp_path, monkeypatch)
    cfg = Config(toml)
    assert evaluate.evaluate(final, ("sim",), None)["metrics"]["sim"]["status"] == "not_measured"
    cfg.sim = {**cfg.sim, "model": str(tmp_path / "absent.ckpt")}
    assert "absent" in evaluate.evaluate(final, ("sim",), cfg)["metrics"]["sim"]["reason"]
    other = tmp_path / "other.ckpt"
    other.write_bytes(b"an unregistered file")
    cfg.sim = {**cfg.sim, "model": str(other)}
    assert "is not the registered" in evaluate.evaluate(final, ("sim",), cfg)["metrics"]["sim"]["reason"]
    cfg = Config(toml)
    cfg.sim = {**cfg.sim, "python": str(tmp_path / "no-such-python")}
    assert "could not start" in evaluate.evaluate(final, ("sim",), cfg)["metrics"]["sim"]["reason"]
    cfg = Config(toml)
    cfg.store = tmp_path / "empty-store"
    empty = evaluate.evaluate(final, ("sim",), cfg)["metrics"]["sim"]
    assert empty["status"] == "not_measured" and empty["refused"] == "consent_missing"
    cfg = Config(toml)
    clipless = tmp_path / "clipless-store"
    shutil.copytree(cfg.store, clipless)
    ref = policy.store_index(clipless)[workspace.voices[0]["refClipSha256"]]
    Path(ref).unlink()
    cfg.store = clipless
    assert "not in the private store" in evaluate.evaluate(final, ("sim",), cfg)["metrics"]["sim"]["reason"]


def test_a_revoked_consent_stops_sim_before_any_worker(workspace, ffmpeg, tmp_path, monkeypatch):
    toml, final = sim_workspace(workspace, tmp_path, monkeypatch)
    for consent in workspace.consents:
        consent["revokedAt"] = "2026-10-26T00:00:00Z"
    toml = workspace.write(SLIDE)
    cfg = Config(toml)
    cfg.sim = {**cfg.sim, "python": str(tmp_path / "no-such-python")}  # a worker start would say "could not start"
    result = evaluate.evaluate(final, ("sim",), cfg)["metrics"]["sim"]
    assert result["status"] == "not_measured" and result["refused"] == "consent_revoked"


def test_sim_has_no_default_interpreter_and_bounded_threads(workspace, tmp_path):
    cfg = Config(workspace.write(SLIDE))
    assert cfg.sim["python"] == ""
    ok, why = sim.Scorer(cfg).available()
    assert not ok and "no SIM interpreter" in why
    for threads in (0, 9, True, "4"):
        with pytest.raises(ValueError):
            sim.check_threads(threads)


def test_wsim_windows_cover_the_track_and_end_with_it():
    assert sim.window_starts(4.0) == [0.0]
    assert sim.window_starts(20.0) == [0.0, 5.0, 10.0]
    assert sim.window_starts(23.0) == [0.0, 5.0, 10.0, 13.0]
    silent = audio.Pcm(16000)
    silent.silence(20.0)
    assert not sim.wsim_voiced(silent, 0.0)


# -- SIM with the registered model --------------------------------------------------------------------------------
MODEL_ENV, PYTHON_ENV = "NARRATE_SIM_TEST_MODEL", "NARRATE_SIM_TEST_PYTHON"


@pytest.mark.skipif(
    not (os.environ.get(MODEL_ENV) and os.environ.get(PYTHON_ENV)),
    reason=f"{MODEL_ENV} and {PYTHON_ENV} are not set (the registered ECAPA model and an interpreter with torch)",
)
def test_the_registered_model_separates_a_synthetic_voice_from_its_decoys(tmp_path):
    scorer = sim.Scorer(None)
    scorer.model, scorer.python, scorer.threads = Path(os.environ[MODEL_ENV]), os.environ[PYTHON_ENV], 8
    assert scorer.available()[0], scorer.available()[1]
    ref = formant_voice(110, 1.0, "aiueaiue", 10, 1).write(tmp_path / "a-ref.wav")
    same = formant_voice(118, 1.0, "euiaeu", 6, 2).write(tmp_path / "a-chunk.wav")
    higher = formant_voice(215, 1.22, "euiaeu", 6, 3).write(tmp_path / "b-decoy.wav")
    breathy = formant_voice(150, 0.88, "euiaeu", 6, 4, breath=0.2).write(tmp_path / "c-decoy.wav")
    rows = scorer.score([("same", ref, same), ("higher", ref, higher), ("breathy", ref, breathy)])
    same_sim = rows["same"]["sim"]
    assert same_sim > 0.75
    for decoy in ("higher", "breathy"):
        assert same_sim - rows[decoy]["sim"] > 0.15, rows
    with wave.open(str(ref)) as w:
        assert w.getframerate() == RATE
