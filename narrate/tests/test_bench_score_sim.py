"""narrate/bench/score.py's SIM (TIN-7090): per-chunk SIM, wSIM over a pass, decoys 1 and 2, the preregistered bars.

A synthetic window directory (formant voices and silence, no recording) and a fake worker interpreter that answers
the SIM worker's JSON protocol with one score per file: the score is looked up by the scratch file's name (arm,
pass, chunk or window), so every chunk and window can sit on its own side of a bar. Like the real worker it refuses
a file over 60 s; it also refuses a wSIM window over 10 s, a chunk not scored against the reference, a decoy-1 pair
that is not the second half against the first, and any file it has no score for. The reference clip's consent is
checked through a synthetic narrate.toml workspace. No torch, whisper model, clip, network or GPU is used.
"""

import array
import functools
import importlib.util
import json
import stat
import sys
from pathlib import Path

import pytest
from test_tools_sim import RATE
from test_tools_sim import formant_voice as synthesise

from narrate import audio, qa, sim

BENCH = Path(__file__).resolve().parents[1] / "bench"
CHUNKS = json.loads((BENCH / "chunks-v1.json").read_text(encoding="utf-8"))
IDS = [c["id"] for c in CHUNKS["chunks"][:3]]
STEM = [i.replace(".", "_") for i in IDS]

FAKE_WORKER = """#!{python}
import json, os, sys, wave
SCORES = sorted(json.loads({scores!r}).items(), key=lambda kv: -len(kv[0]))  # the most specific name wins
def refuse(reason):
    print(json.dumps({{"ok": False, "reason": reason}}))
    sys.exit(1)
request = json.loads(sys.stdin.read())
out = []
for p in request["pairs"]:
    a, b = os.path.basename(p["a"]), os.path.basename(p["b"])
    with wave.open(p["a"]) as w:
        seconds = w.getnframes() / w.getframerate()
    if seconds > 60:
        refuse(a + " is over 60 s")
    if "-window-" in a and seconds > 10.001:
        refuse(a + " is a wSIM window over 10 s")
    if b != ("reference.first.wav" if a == "reference.second.wav" else "reference.16k.wav"):
        refuse(a + " was paired with " + b)
    score = next((v for k, v in SCORES if k in a), None)
    if score is None:
        refuse("no score for " + a)
    out.append({{"id": p["id"], "sim": score, "a_seconds": seconds, "b_seconds": 1.0}})
print(json.dumps({{"ok": True, "scores": out, "torch": "fake", "speechbrain": "fake"}}))
"""

# seed1: c01 voice, c02 silence, c03 voice (36 s). Windows start 0, 5, 10, 15, 20, 25 and 26: 2 and 3 lie in the
# silence and must be skipped, so the pass fallback (0.01) would show up in the minimum if they were scored.
# seed2: two voiced chunks (24 s, windows 0, 5, 10, 14); window 1 is the weak stretch. seed3: a 61 s chunk (over
# the worker's limit) and one voiced chunk. The smoke repeats seed1's first chunk with a score that would move the
# arm's median, and decoy 3 scores high: neither may count.
SCORES = {
    "reference.second": 0.9,
    f"A9-fake-seed1-{STEM[0]}.s16": 0.70,
    f"A9-fake-seed1-{STEM[1]}.s16": 0.60,
    f"A9-fake-seed1-{STEM[2]}.s16": 0.74,
    "A9-fake-seed1-window": 0.01,
    "A9-fake-seed1-window-0.": 0.72,
    "A9-fake-seed1-window-1.": 0.66,
    "A9-fake-seed1-window-4.": 0.70,
    "A9-fake-seed1-window-5.": 0.69,
    "A9-fake-seed1-window-6.": 0.71,
    f"A9-fake-seed2-{STEM[0]}.s16": 0.62,
    f"A9-fake-seed2-{STEM[1]}.s16": 0.66,
    "A9-fake-seed2-window-0.": 0.60,
    "A9-fake-seed2-window-1.": 0.40,
    "A9-fake-seed2-window-2.": 0.58,
    "A9-fake-seed2-window-3.": 0.61,
    f"A9-fake-seed3-{STEM[1]}.s16": 0.68,
    "A9-fake-seed3-window": 0.65,
    "A9-fake-smoke-ref-text-": 0.99,
    "A9-fake-decoy-decoy2-preset-fake-": 0.05,
    "A9-fake-decoy-decoy3-espeak-": 0.95,
}
formant_voice = functools.cache(synthesise)  # deterministic and slow in pure Python: each voice is made once
ARM_MEDIAN = 0.67  # median of 0.70 0.60 0.74 0.62 0.66 0.68: seed chunks only, the 61 s chunk skipped


@pytest.fixture
def score_module():
    spec = importlib.util.spec_from_file_location("narrate_bench_score", BENCH / "score.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(path):
    return qa.sha256_file(path)


def voice(seconds, seed):
    return formant_voice(110 + seed, 1.0, "aeiu", seconds, seed)


def write_arm(out, arm_name, passes):
    """passes: [(name, decoy or None, [(chunk index, Pcm)])]; a pass with no takes is a crashed one."""
    arm = out / arm_name
    records = []
    for name, decoy, takes in passes:
        rows = []
        for index, pcm in takes:
            path = arm / name / f"{STEM[index]}.wav"
            path.parent.mkdir(parents=True, exist_ok=True)
            pcm.write(path)
            rows.append({"chunk": IDS[index], "file": path.name, "sha256": sha(path), "audio_s": pcm.seconds})
        record = {"name": name, "variant": decoy or "ref-text", "complete": bool(rows), "chunks_done": len(rows)}
        record.update({"chunk_ids": [IDS[i] for i, _ in takes] or IDS[:1], "chunks": rows, "rtf": 0.5})
        if decoy:
            record["decoy"] = decoy
        records.append(record)
    receipt = {"arm": arm_name, "chunk_list": {"chunks_sha256": CHUNKS["chunks_sha256"]}, "passes": records}
    arm.mkdir(parents=True, exist_ok=True)
    (arm / "receipt.json").write_text(json.dumps(receipt))


def window(tmp_path, reference_sha):
    out = tmp_path / "runs" / "holder"
    out.mkdir(parents=True)
    (out / "inputs-verified.json").write_text(json.dumps({"verified": {"voice.wav": {"sha256": reference_sha}}}))
    silence = audio.Pcm(RATE, array.array("h", [0] * (12 * RATE)))
    long_take = audio.Pcm(RATE, array.array("h", list(voice(12.2, 5).samples) * 5))  # 61 s
    write_arm(
        out,
        "A9-fake",
        [
            ("smoke-ref-text", None, [(0, voice(12.0, 1))]),
            ("decoy-decoy2-preset-fake", "decoy2-preset-fake", [(0, formant_voice(220, 1.2, "eiua", 12.0, 3))]),
            ("decoy-decoy3-espeak", "decoy3-espeak", [(0, formant_voice(180, 1.1, "eiua", 12.0, 4))]),
            ("seed1", None, [(0, voice(12.0, 1)), (1, silence), (2, voice(12.0, 2))]),
            ("seed2", None, [(0, voice(12.0, 6)), (1, voice(12.0, 7))]),
            ("seed3", None, [(0, long_take), (1, voice(12.0, 8))]),
            ("smoke-crashed", None, []),
        ],
    )
    # a worker failure on this arm (the fake has no score for it) must leave only this pass not_measured
    write_arm(out, "A7-broken", [("seed1", None, [(0, voice(12.0, 9))])])
    return out


@pytest.fixture
def bench(tmp_path, monkeypatch, workspace):
    model = tmp_path / "embedding_model.ckpt"
    model.write_bytes(b"dummy speaker model")
    digest = qa.model_digest(model)
    monkeypatch.setattr(qa, "registered", lambda d, models=None: sim.SIM_MODEL_ID if d == digest else None)
    reference = formant_voice(110, 1.0, "aiueaiue", 20.0, 1).write(tmp_path / "reference.wav")
    # the window's voice is a registered, consented voice of a synthetic narrate.toml whose store holds the clip
    (workspace.store / "reference.wav").write_bytes(reference.read_bytes())
    workspace.voices[0]["refClipSha256"] = sha(reference)
    toml = workspace.write("A line.\n")

    def worker(**changes):
        path = tmp_path / f"fake-python-{len(list(tmp_path.glob('fake-python-*')))}"
        scores = {k: v for k, v in (SCORES | changes).items() if v is not None}
        path.write_text(FAKE_WORKER.format(python=sys.executable, scores=json.dumps(scores)))
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
        return str(path)

    out = window(tmp_path, sha(reference))
    base = [str(out), "--whisper-model", str(tmp_path / "absent-whisper.bin"), "--sim-model", str(model)]
    ready = ["--reference", str(reference), "--config", str(toml)]
    return {"out": out, "reference": reference, "worker": worker, "base": base, "ready": ready, "ws": workspace}


def scored(score_module, bench, *extra):
    assert score_module.main([*bench["base"], *extra]) == 0
    return json.loads((bench["out"] / "scored.json").read_text(encoding="utf-8"))


def measured(score_module, bench, **changes):
    return scored(score_module, bench, *bench["ready"], "--sim-python", bench["worker"](**changes))


def passes(doc, arm="A9-fake"):
    return {p["pass"]: p for a in doc["arms"] if a["arm"] == arm for p in a["passes"]}


def arm_sim(doc, arm="A9-fake"):
    return next(a for a in doc["arms"] if a["arm"] == arm)["sim"]


def test_each_chunk_and_window_scores_and_the_arm_reads_against_the_bars(score_module, bench, ffmpeg):
    doc = measured(score_module, bench)
    assert doc["sim"]["status"] == "measured" and doc["sim"]["model_id"] == sim.SIM_MODEL_ID
    assert doc["sim"]["reference"]["window_voice_wav"] == "matched"
    assert doc["sim"]["reference"]["consent"]["voices"] == 1
    # the full clip is the one SIM reference; these receipts name no conditioning reference, so that is flagged
    assert doc["sim_reference"]["sha256"] == doc["sim"]["reference"]["ref_clip_sha256"] == sha(bench["reference"])
    assert doc["conditioning"]["equal"] is False
    assert "conditioning reference not recorded for A7-broken, A9-fake" in doc["conditioning"]["flags"]
    assert "| arm | conditioning | pass |" in (bench["out"] / "scored.md").read_text(encoding="utf-8")
    checks = doc["sim"]["checks"]
    assert checks["1-reference-self-match"]["observed"] == 0.9 and checks["1-reference-self-match"]["valid"] is True
    # decoy 3 (0.95) is another decoy, not the preset voice: only decoy2-* sets decoy 2
    wrong = checks["2-wrong-speaker"]
    assert (wrong["observed"], wrong["passes"], wrong["arms"], wrong["valid"]) == (0.05, 1, ["A9-fake"], True)

    seed1 = passes(doc)["seed1"]["sim"]
    assert seed1["median"] == 0.7 and seed1["min"] == 0.6
    assert seed1["wsim"]["windows"] == 5 and seed1["wsim"]["skipped_silent"] == 2
    assert [w["start_s"] for w in seed1["wsim"]["values"]] == [0.0, 5.0, 20.0, 25.0, 26.0]
    assert seed1["wsim"]["min"] == 0.66 and seed1["wsim"]["mean"] == 0.696
    seed2 = passes(doc)["seed2"]["sim"]
    assert seed2["wsim"]["min"] == 0.4 and seed2["wsim"]["windows"] == 4

    # one chunk over the worker's 60 s is skipped; the rest of its pass and every later pass still scores
    seed3 = passes(doc)["seed3"]
    long_row, short_row = seed3["chunks"]
    assert long_row["sim_skipped"] == "too_long" and "sim" not in long_row and "too_long" in long_row["catastrophic"]
    assert short_row["sim"] == 0.68 and seed3["sim"]["skipped_too_long"] == 1
    assert seed3["sim"]["wsim"]["windows"] >= 12 and seed3["sim"]["wsim"]["min"] == 0.65

    arm = arm_sim(doc)
    assert arm["passes"] == ["seed1", "seed2", "seed3"] and arm["chunks"] == 6
    assert arm["median"] == ARM_MEDIAN and arm["min"] == 0.6  # the smoke's 0.99 and the decoys are left out
    assert arm["wsim"]["min"] == 0.4 and arm["wsim"]["weakest_pass"] == "seed2"
    windows = [w["sim"] for p in ("seed1", "seed2", "seed3") for w in passes(doc)[p]["sim"]["wsim"]["values"]]
    assert arm["wsim"]["windows"] == len(windows) and arm["wsim"]["mean"] == round(sum(windows) / len(windows), 4)
    bars = arm["bars"]
    assert bars["decoy_checks_valid"] is True and bars["median_at_least_bar"] is True
    assert bars["over_decoy"] == 0.62 and bars["over_decoy_ok"] is True
    assert bars["wsim_ratio"] == round(0.4 / ARM_MEDIAN, 4) and bars["wsim_ok"] is False
    assert bars["unmet"] == ["wsim_ok"] and bars["all_met"] is False
    assert "bars" not in passes(doc)["decoy-decoy2-preset-fake"]["sim"]

    crashed = passes(doc)["smoke-crashed"]
    assert crashed["sim"]["status"] == "not_measured" and crashed["catastrophic"] == 1
    broken = passes(doc, "A7-broken")["seed1"]["sim"]
    assert broken["status"] == "not_measured" and "SIM scorer failed" in broken["reason"]
    assert arm_sim(doc, "A7-broken")["status"] == "not_measured"
    text = (bench["out"] / "scored.md").read_text()
    assert "SIM decoy 2-wrong-speaker: observed 0.050" in text
    assert "SIM arm A9-fake (seed1, seed2, seed3): median 0.670" in text and "unmet wsim_ok" in text


def test_every_bar_met(score_module, bench, ffmpeg):
    doc = measured(score_module, bench, **{"A9-fake-seed2-window-1.": 0.55})
    bars = arm_sim(doc)["bars"]
    assert bars["wsim_ratio"] == round(0.55 / ARM_MEDIAN, 4) and bars["wsim_ok"] is True
    assert bars["unmet"] == [] and bars["all_met"] is True


def test_a_median_under_the_bar(score_module, bench, ffmpeg):
    low = {k: round(v - 0.3, 2) for k, v in SCORES.items() if k.startswith("A9-fake-seed") and ".s16" in k}
    doc = measured(score_module, bench, **low, **{"A9-fake-seed2-window-1.": 0.55})
    arm = arm_sim(doc)
    assert arm["median"] == round(ARM_MEDIAN - 0.3, 4) and arm["bars"]["median_at_least_bar"] is False
    assert arm["bars"]["over_decoy_ok"] is True and arm["bars"]["unmet"] == ["median_at_least_bar"]


def test_a_median_too_close_to_decoy_2(score_module, bench, ffmpeg):
    lower = {k: round(v - 0.12, 2) for k, v in SCORES.items() if k.startswith("A9-fake-seed") and ".s16" in k}
    doc = measured(score_module, bench, **lower, **{"A9-fake-decoy-decoy2-preset-fake-": 0.44})
    arm = arm_sim(doc)
    assert doc["sim"]["checks"]["2-wrong-speaker"]["valid"] is True
    assert arm["median"] == 0.55 and arm["bars"]["median_at_least_bar"] is True
    assert arm["bars"]["over_decoy"] == 0.11 and arm["bars"]["over_decoy_ok"] is False
    assert "over_decoy_ok" in arm["bars"]["unmet"] and arm["bars"]["all_met"] is False


@pytest.mark.parametrize(
    "self_sim,decoy,valid",
    [
        (0.9, 0.5, (True, False)),  # decoy 2 at or over the bar
        (0.5, 0.40, (False, False)),  # decoy 1 under 0.60, and decoy 2 within 0.15 of it although under the bar
        (0.5, 0.30, (False, True)),
        (0.6, 0.45, (True, False)),  # boundaries: decoy 1 at 0.60 holds, decoy 2 at the bar does not
    ],
)
def test_decoys_on_the_wrong_side_invalidate_the_bars(score_module, bench, ffmpeg, self_sim, decoy, valid):
    doc = measured(score_module, bench, **{"reference.second": self_sim, "A9-fake-decoy-decoy2-preset-fake-": decoy})
    checks = doc["sim"]["checks"]
    assert (checks["1-reference-self-match"]["valid"], checks["2-wrong-speaker"]["valid"]) == valid
    bars = arm_sim(doc)["bars"]
    assert bars["decoy_checks_valid"] is (valid == (True, True))
    assert ("decoy_checks_valid" in bars["unmet"]) is (valid != (True, True)) and bars["all_met"] is False


def test_a_failed_decoy_1_leaves_the_bars_unusable(score_module, bench, ffmpeg):
    doc = measured(score_module, bench, **{"reference.second": None})
    check = doc["sim"]["checks"]["1-reference-self-match"]
    assert check["observed"] is None and check["valid"] is None and "decoy 1" in check["reason"]
    assert passes(doc)["seed1"]["sim"]["median"] == 0.7  # the scorer stayed up after the failure
    bars = arm_sim(doc)["bars"]
    assert bars["decoy_checks_valid"] is False and "decoy_checks_valid" in bars["unmet"]


def test_a_missing_decoy_2_counts_as_unmet(score_module, bench, ffmpeg):
    doc = measured(score_module, bench, **{"A9-fake-decoy-decoy2-preset-fake-": None})
    check = doc["sim"]["checks"]["2-wrong-speaker"]
    assert check["observed"] is None and check["passes"] == 0 and check["valid"] is None
    bars = arm_sim(doc)["bars"]
    assert bars["over_decoy"] is None and bars["over_decoy_ok"] is None
    assert {"decoy_checks_valid", "over_decoy_ok"} <= set(bars["unmet"]) and bars["all_met"] is False


def test_sim_is_not_measured_without_its_inputs(score_module, bench, ffmpeg, tmp_path):
    def status(*extra):
        doc = scored(score_module, bench, *extra)
        assert all(p["sim"]["status"] == "not_measured" for p in passes(doc).values())
        assert "checks" not in doc["sim"]
        return doc["sim"]

    python, reference, toml = bench["worker"](), str(bench["reference"]), bench["ready"][-1]
    assert "no --reference" in status("--sim-python", python)["reason"]
    assert "no SIM interpreter" in status(*bench["ready"])["reason"]
    other = formant_voice(150, 0.9, "aeiu", 20.0, 9).write(tmp_path / "other-reference.wav")
    assert "is not the window's voice.wav" in status("--reference", str(other), "--config", toml)["reason"]
    assert "sim.threads" in status(*bench["ready"], "--sim-python", python, "--sim-threads", "9")["reason"]
    unchecked = status("--reference", reference, "--sim-python", python)
    assert "no --config" in unchecked["reason"] and unchecked["refused"] == "consent_unchecked"


def test_the_reference_needs_current_consent(score_module, bench, ffmpeg):
    ws = bench["ws"]
    for consent in ws.consents:
        consent["revokedAt"] = "2026-10-26T00:00:00Z"
    ws.write("A line.\n")
    doc = scored(score_module, bench, *bench["ready"], "--sim-python", bench["worker"]())
    assert doc["sim"]["status"] == "not_measured" and doc["sim"]["refused"] == "consent_revoked"
    for consent in ws.consents:
        consent["revokedAt"] = None
    ws.voices[0]["refClipSha256"] = "0" * 64
    ws.write("A line.\n")
    doc = scored(score_module, bench, *bench["ready"], "--sim-python", bench["worker"]())
    assert doc["sim"]["refused"] == "voice_unknown"


def test_one_scorer_at_a_time(score_module, bench, capsys):
    with sim.scorer_lock() as held:
        assert held
        assert score_module.main([*bench["base"], *bench["ready"]]) == 2
    assert "one at a time" in capsys.readouterr().err
    assert not (bench["out"] / "scored.json").exists()


def test_decoys_4_and_5_rebuild_beside_sim_and_serialise(score_module, bench, ffmpeg):
    doc = scored(
        score_module,
        bench,
        *bench["ready"],
        "--sim-python",
        bench["worker"](),
        "--decoys",
        "--decoy-arm",
        "A9-fake",
    )
    names = [d["decoy"] for d in doc["decoys"]]
    assert names == ["4-half-silence", "4-reversed", "5-shuffled-transcript"]
    assert all(set(d["observed"]) >= {"audio_s", "catastrophic"} and "pcm" not in d["observed"] for d in doc["decoys"])
    assert doc["decoys"][0]["valid"] is True and doc["decoys"][1]["valid"] is None
    assert "Decoy 4-half-silence: expected catastrophic, valid True" in (bench["out"] / "scored.md").read_text()
