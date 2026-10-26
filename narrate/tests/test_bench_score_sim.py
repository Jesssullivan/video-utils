"""narrate/bench/score.py's SIM (TIN-7090): per-chunk SIM, wSIM over a pass, decoys 1 and 2, the preregistered bars.

A synthetic window directory (formant voices, no recording) and a fake worker interpreter that answers the SIM
worker's JSON protocol: a pair whose take is a preset-voice decoy scores low, the reference self-match scores high.
No torch, whisper model, clip, network or GPU is used.
"""

import importlib.util
import json
import stat
import sys
from pathlib import Path

import pytest
from test_tools_sim import formant_voice

from narrate import qa, sim

BENCH = Path(__file__).resolve().parents[1] / "bench"
CHUNKS = json.loads((BENCH / "chunks-v1.json").read_text(encoding="utf-8"))

FAKE_WORKER = """#!{python}
import json, sys
request = json.loads(sys.stdin.read())
def score(p):
    if p["id"] == "self":
        return {self_sim}
    return {decoy_sim} if "decoy-" in p["a"] else {take_sim}
scores = [{{"id": p["id"], "sim": score(p), "a_seconds": 1.0, "b_seconds": 1.0}} for p in request["pairs"]]
print(json.dumps({{"ok": True, "scores": scores, "torch": "fake", "speechbrain": "fake"}}))
"""


@pytest.fixture
def score_module():
    spec = importlib.util.spec_from_file_location("narrate_bench_score", BENCH / "score.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(path):
    return qa.sha256_file(path)


def window(tmp_path, reference_sha):
    """A runs/<holder> directory with one arm: a complete two-chunk pass and a one-chunk preset-voice decoy pass."""
    out = tmp_path / "runs" / "holder"
    arm = out / "A9-fake"
    (out / "inputs-verified.json").parent.mkdir(parents=True)
    (out / "inputs-verified.json").write_text(json.dumps({"verified": {"voice.wav": {"sha256": reference_sha}}}))
    ids = [c["id"] for c in CHUNKS["chunks"][:2]]
    passes = []
    for name, decoy, picked, f0 in (("seed1", None, ids, 112), ("decoy-preset", "preset", ids[:1], 220)):
        rows = []
        for k, chunk_id in enumerate(picked):
            path = arm / name / f"{chunk_id.replace('.', '_')}.wav"
            path.parent.mkdir(parents=True, exist_ok=True)
            formant_voice(f0 + k, 1.0, "aeiu", 12.0, 7 + k).write(path)
            rows.append({"chunk": chunk_id, "file": path.name, "sha256": sha(path), "audio_s": 12.0})
        record = {"name": name, "variant": decoy or "ref-text", "complete": True, "chunks_done": len(rows)}
        record.update({"chunk_ids": picked, "chunks": rows, "audio_s": 12.0 * len(rows), "rtf": 0.5, "load_s": 3.0})
        if decoy:
            record["decoy"] = decoy
        passes.append(record)
    # a smoke that produced nothing, as a crashed variant leaves it
    passes.append({"name": "smoke-crashed", "variant": "ref-text", "complete": False, "chunks_done": 0})
    passes[-1].update({"chunk_ids": ids[:1], "chunks": []})
    receipt = {"arm": "A9-fake", "chunk_list": {"chunks_sha256": CHUNKS["chunks_sha256"]}, "passes": passes}
    (arm / "receipt.json").write_text(json.dumps(receipt))
    return out


@pytest.fixture
def bench(tmp_path, monkeypatch):
    model = tmp_path / "embedding_model.ckpt"
    model.write_bytes(b"dummy speaker model")
    digest = qa.model_digest(model)
    monkeypatch.setattr(qa, "registered", lambda d, models=None: sim.SIM_MODEL_ID if d == digest else None)
    reference = formant_voice(110, 1.0, "aiueaiue", 20.0, 1).write(tmp_path / "reference.wav")

    def worker(take_sim=0.8, decoy_sim=0.05, self_sim=0.9):
        path = tmp_path / f"fake-python-{take_sim}-{decoy_sim}-{self_sim}"
        path.write_text(
            FAKE_WORKER.format(python=sys.executable, take_sim=take_sim, decoy_sim=decoy_sim, self_sim=self_sim)
        )
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
        return path

    out = window(tmp_path, sha(reference))
    base = [str(out), "--whisper-model", str(tmp_path / "absent-whisper.bin"), "--sim-model", str(model)]
    return {"out": out, "reference": reference, "worker": worker, "base": base, "tmp": tmp_path}


def scored(score_module, bench, *extra):
    assert score_module.main([*bench["base"], *extra]) == 0
    return json.loads((bench["out"] / "scored.json").read_text(encoding="utf-8"))


def passes(doc):
    return {p["pass"]: p for arm in doc["arms"] for p in arm["passes"]}


def test_sim_median_wsim_and_decoys_against_the_bars(score_module, bench, ffmpeg):
    doc = scored(score_module, bench, "--reference", str(bench["reference"]), "--sim-python", str(bench["worker"]()))
    assert doc["sim"]["status"] == "measured" and doc["sim"]["model_id"] == sim.SIM_MODEL_ID
    assert doc["sim"]["reference"]["window_voice_wav"] == "matched"
    checks = doc["sim"]["checks"]
    assert checks["1-reference-self-match"]["observed"] == 0.9 and checks["1-reference-self-match"]["valid"]
    assert checks["2-wrong-speaker"]["observed"] == 0.05 and checks["2-wrong-speaker"]["valid"]
    seed1, decoy = passes(doc)["seed1"], passes(doc)["decoy-preset"]
    assert seed1["sim"]["median"] == 0.8 and seed1["sim"]["min"] == 0.8
    assert seed1["sim"]["wsim"]["windows"] >= 3 and seed1["sim"]["wsim"]["min"] == 0.8
    assert {c["sim"] for c in seed1["chunks"]} == {0.8}
    bars = seed1["sim"]["bars"]
    assert bars["decoy_checks_valid"] and bars["median_at_least_bar"] and bars["over_decoy_ok"] and bars["wsim_ok"]
    assert bars["over_decoy"] == 0.75
    assert decoy["decoy"] == "preset" and decoy["sim"]["median"] == 0.05 and "bars" not in decoy["sim"]
    crashed = passes(doc)["smoke-crashed"]
    assert crashed["sim"]["status"] == "not_measured" and crashed["catastrophic"] == 1
    assert "SIM decoy 2-wrong-speaker: observed 0.050" in (bench["out"] / "scored.md").read_text()


def test_a_decoy_on_the_wrong_side_invalidates_the_bars(score_module, bench, ffmpeg):
    worker = bench["worker"](take_sim=0.8, decoy_sim=0.7, self_sim=0.9)
    doc = scored(score_module, bench, "--reference", str(bench["reference"]), "--sim-python", str(worker))
    assert doc["sim"]["checks"]["2-wrong-speaker"]["valid"] is False
    bars = passes(doc)["seed1"]["sim"]["bars"]
    assert bars["decoy_checks_valid"] is False and bars["over_decoy_ok"] is False
    low_self = bench["worker"](take_sim=0.8, decoy_sim=0.05, self_sim=0.5)
    doc = scored(score_module, bench, "--reference", str(bench["reference"]), "--sim-python", str(low_self))
    assert doc["sim"]["checks"]["1-reference-self-match"]["valid"] is False


def test_sim_is_not_measured_without_its_inputs(score_module, bench, ffmpeg, tmp_path):
    def reason(*extra):
        doc = scored(score_module, bench, *extra)
        assert all(p["sim"]["status"] == "not_measured" for p in passes(doc).values())
        assert "checks" not in doc["sim"]
        return doc["sim"]["reason"]

    python = str(bench["worker"]())
    assert "no --reference" in reason("--sim-python", python)
    assert "no SIM interpreter" in reason("--reference", str(bench["reference"]))
    other = formant_voice(150, 0.9, "aeiu", 20.0, 9).write(tmp_path / "other-reference.wav")
    assert "is not the window's voice.wav" in reason("--reference", str(other), "--sim-python", python)
    assert "sim.threads" in reason("--reference", str(bench["reference"]), "--sim-python", python, "--sim-threads", "9")


def test_decoys_4_and_5_rebuild_beside_sim_and_serialise(score_module, bench, ffmpeg):
    worker = str(bench["worker"]())
    doc = scored(
        score_module,
        bench,
        "--reference",
        str(bench["reference"]),
        "--sim-python",
        worker,
        "--decoys",
        "--decoy-arm",
        "A9-fake",
    )
    names = [d["decoy"] for d in doc["decoys"]]
    assert names == ["4-half-silence", "4-reversed", "5-shuffled-transcript"]
    assert all(set(d["observed"]) >= {"audio_s", "catastrophic"} and "pcm" not in d["observed"] for d in doc["decoys"])
    assert doc["decoys"][0]["valid"] is True and doc["decoys"][1]["valid"] is None
    assert "Decoy 4-half-silence: expected catastrophic, valid True" in (bench["out"] / "scored.md").read_text()
