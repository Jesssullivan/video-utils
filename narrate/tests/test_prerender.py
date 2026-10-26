"""Two-phase rendering for an AudioCppBatch engine (narrate/prerender.py) with a fake audiocpp_cli only.

plan writes the request batch from the render pipeline; narrate/serve/audiocpp_batch.py runs it through the fake
binary and writes the receipt; render --prerendered takes each take by request id, runs QA and best of maxTakes,
and records the out-of-process synthesis. Every binding is tampered with once: the WAV, the receipt's binary and
weights, the requests file, the text after the plan, a missing take, and a reference too long for the encoder.
"""

import importlib.util
import json
import shutil
import stat
import sys
import wave

import pytest
from conftest import PACKAGE, SLIDE

from narrate import engine, prerender, qa, render, verify
from narrate.__main__ import main
from narrate.config import Config

pytestmark = pytest.mark.usefixtures("ffmpeg")

RUNNER = PACKAGE / "serve" / "audiocpp_batch.py"
FAKE = PACKAGE / "tests" / "fake_audiocpp.py"
ENGINE_ID = "voxcpm2-batch-fixture"


def runner_module():
    spec = importlib.util.spec_from_file_location("audiocpp_batch", RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def kit(tmp_path, monkeypatch):
    """A fake audiocpp_cli and fake weights, each with its sha256, as the GPU host would hold them."""
    bindir = tmp_path / "gpu"
    bindir.mkdir()
    binary = bindir / "audiocpp_cli"
    binary.write_text(f"#!{sys.executable}\n" + FAKE.read_text())
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
    model = bindir / "voxcpm2-bf16.gguf"
    model.write_bytes(b"fake voxcpm2 weights; no model\n")
    monkeypatch.setenv("NARRATE_AUDIOCPP_BATCH_TEST_MODE", "1")
    monkeypatch.setenv("FAKE_AUDIOCPP_LOG", str(tmp_path / "argv.jsonl"))

    class Kit:
        pass

    k = Kit()
    k.binary, k.model, k.log = binary, model, tmp_path / "argv.jsonl"
    k.binary_sha, k.model_sha = prerender.sha256_file(binary), prerender.sha256_file(model)
    return k


def batch_engine(kit, **extra):
    return {
        "id": ENGINE_ID,
        "profile": "GpuDirect",
        "backend": "AudioCppBatch",
        "endpoint": "audiocpp://voxcpm2",
        "model": "voxcpm2-bf16",
        "hfRepo": None,
        "hfRevision": None,
        "files": [
            {"path": "audiocpp_cli", "sha256": kit.binary_sha},
            {"path": "voxcpm2-bf16.gguf", "sha256": kit.model_sha},
        ],
        "licence": "Apache-2.0 (fixture record)",
        "licenceNotice": None,
        "vramGiB": 8.0,
        "sampleRateHz": 48000,
        "hosted": False,
        "estateControlled": True,
        "confidentialAllowed": True,
        **extra,
    }


def use_batch(workspace, kit, **extra):
    workspace.engines = [*workspace.engines, batch_engine(kit, **extra)]
    workspace.job["engine"] = ENGINE_ID
    for voice in workspace.voices:
        voice["allowedEngines"] = [*voice["allowedEngines"], ENGINE_ID]


def run_batch(kit, plan_dir, name=None, *extra, env=None, monkeypatch=None):
    names = [name] if name else [p.stem for p in sorted((plan_dir / "requests").glob("*.json"))]
    codes = []
    for n in names:
        argv = [
            "run",
            str(plan_dir),
            "--requests",
            f"requests/{n}.json",
            "--binary",
            str(kit.binary),
            "--binary-sha256",
            kit.binary_sha,
            "--model",
            str(kit.model),
            "--model-sha256",
            kit.model_sha,
            "--audiocpp-commit",
            "47c2756e",
            *extra,
        ]
        codes.append(runner_module().main(argv))
    return codes


def test_plan_batch_render_end_to_end(workspace, kit, tmp_path):
    use_batch(workspace, kit)
    cfg = Config(workspace.write(SLIDE))
    path, plan = render.plan(cfg, tmp_path / "plan", takes=2)
    plan_dir = path.parent
    assert plan["schema"] == prerender.PLAN_SCHEMA and plan["takes"] == 2
    (batch,) = plan["batches"]
    assert batch["voice"] == "voice-fixture-sine" and batch["file"] == "requests/voice-fixture-sine.json"
    requests = json.loads((plan_dir / batch["file"]).read_text())["requests"]
    assert len(requests) == 2 * len(plan["chunks"]) == batch["requests"]
    assert prerender.sha256_file(plan_dir / batch["file"]) == batch["sha256"]
    first = requests[0]
    clip = workspace.voices[0]["refClipSha256"]
    assert first["voice_ref"] == first["audio"] == f"refs/{clip}.wav"
    assert first["reference_text"].endswith(" ") and first["seed"] == workspace.job["seed"]
    assert prerender.sha256_file(plan_dir / first["voice_ref"]) == clip
    assert {r["seed"] for r in requests} == {workspace.job["seed"], workspace.job["seed"] + 1}
    assert not workspace.runs()  # a plan makes no run and no audio

    assert run_batch(kit, plan_dir) == [0]
    (argv,) = [json.loads(line) for line in kit.log.read_text().splitlines()]
    assert argv[argv.index("--task") + 1] == "clon" and argv[argv.index("--family") + 1] == "voxcpm2"
    assert argv[argv.index("--out-format") + 1] == "pcm16" and "--request-sequence" in argv

    final, manifest = render.render(cfg, prerendered=plan_dir)
    assert verify.verify(final)["ok"]
    synthesis = manifest["engine"]["synthesis"]
    assert synthesis["mode"] == "out_of_process_batch" and synthesis["family"] == "voxcpm2"
    assert synthesis["clone"] == "ultimate" and synthesis["audiocpp_commits"] == ["47c2756e"]
    assert synthesis["binary_sha256"] == [kit.binary_sha] and synthesis["model_sha256"] == [kit.model_sha]
    (used,) = synthesis["batches"]
    assert used["requests_sha256"] == batch["sha256"] and used["used"] == len(plan["chunks"])
    assert manifest["engine"]["knobs"]["audiocpp_clone"] == "ultimate"
    assert "prerendered_test_mode" in manifest["flags"]
    assert manifest["timeline"]["sample_rate"] == 48000
    for chunk in manifest["chunks"]:
        (take,) = chunk["qa"]["takes"]  # no whisper: not measured, the first take is kept
        assert take["variant"] == "audiocpp_prerendered" and take["out_of_process"] is True
        assert take["request_id"] in {r["id"] for r in requests}
        assert take["reply_sha256"] == prerender.sha256_file(plan_dir / "wav" / f"{take['request_id']}.wav")
    assert str(plan_dir) not in json.dumps(manifest)


def test_best_of_chooses_among_the_prerendered_takes(workspace, kit, tmp_path):
    use_batch(workspace, kit)
    cfg = Config(workspace.write(SLIDE))
    path, plan = render.plan(cfg, tmp_path / "plan")
    assert plan["takes"] == 3
    run_batch(kit, path.parent)
    seen = []

    def transcriber(pcm, text):
        seen.append(text)
        return "wrong words" if len(seen) % 2 else text  # every chunk fails take 1 and passes take 2

    _, manifest = render.render(cfg, prerendered=path.parent, transcriber=transcriber)
    for chunk in manifest["chunks"]:
        assert chunk["qa"]["status"] == "passed" and chunk["qa"]["kept_take"] == 2
        assert [t["passed"] for t in chunk["qa"]["takes"]] == [False, True]


def test_a_chunk_without_an_acceptable_take_is_flagged(workspace, kit, tmp_path):
    use_batch(workspace, kit)
    cfg = Config(workspace.write(SLIDE))
    path, _ = render.plan(cfg, tmp_path / "plan", takes=1)
    run_batch(kit, path.parent)
    _, manifest = render.render(cfg, prerendered=path.parent, transcriber=lambda pcm, text: "wrong words")
    assert "qa_failed" in manifest["flags"]
    for chunk in manifest["chunks"]:
        assert chunk["qa"]["status"] == "failed" and len(chunk["qa"]["takes"]) == 1
        seed = workspace.job["seed"]
        assert chunk["qa"]["missing_seeds"] == [seed + 1, seed + 2]


def test_render_refuses_without_the_batch_or_with_another_engine(workspace, kit, tmp_path):
    use_batch(workspace, kit)
    cfg = Config(workspace.write(SLIDE))
    with pytest.raises(render.RenderError) as error:
        render.render(cfg)
    assert error.value.code == "prerendered_required"
    with pytest.raises(render.RenderError) as error:
        render.render(cfg, prerendered=tmp_path / "nothing")
    assert error.value.code == "prerendered_missing"
    with pytest.raises(render.RenderError) as error:
        render.render(cfg, engine_id="fake-sine", prerendered=tmp_path)
    assert error.value.code == "engine_not_batch"
    with pytest.raises(render.RenderError) as error:
        render.plan(cfg, tmp_path / "p", engine_id="fake-sine")
    assert error.value.code == "engine_not_batch"
    assert not workspace.runs()


def test_a_changed_script_finds_no_take(workspace, kit, tmp_path):
    use_batch(workspace, kit)
    cfg = Config(workspace.write(SLIDE))
    path, _ = render.plan(cfg, tmp_path / "plan", takes=1)
    run_batch(kit, path.parent)
    cfg = Config(workspace.write(SLIDE.replace("allows 8%", "allows 7%")))
    with pytest.raises(render.RenderError) as error:
        render.render(cfg, prerendered=path.parent)
    assert error.value.code == "prerendered_take_missing"
    assert not workspace.runs()


@pytest.mark.parametrize(
    ("tamper", "code"),
    [
        ("wav", "prerendered_take_mismatch"),
        ("binary", "prerendered_engine_mismatch"),
        ("model", "prerendered_engine_mismatch"),
        ("requests", "prerendered_batch_mismatch"),
        ("request_id", "prerendered_batch_mismatch"),
        ("family", "prerendered_engine_mismatch"),
    ],
)
def test_every_binding_is_checked(workspace, kit, tmp_path, tamper, code):
    use_batch(workspace, kit)
    cfg = Config(workspace.write(SLIDE))
    path, plan = render.plan(cfg, tmp_path / "plan", takes=1)
    root = path.parent
    run_batch(kit, root)
    (receipt_path,) = (root / "receipts").glob("*.json")
    receipt = json.loads(receipt_path.read_text())
    requests_path = root / receipt["requests_file"]
    if tamper == "wav":
        wav = sorted((root / "wav").glob("*.wav"))[0]
        wav.write_bytes(wav.read_bytes()[:-2] + b"\0\1")
    elif tamper in ("binary", "model"):
        receipt[f"{tamper}_sha256"] = "0" * 64
    elif tamper == "family":
        receipt["family"] = "ming3_tts"
    elif tamper == "requests":
        requests_path.write_text(requests_path.read_text() + " ")
    elif tamper == "request_id":
        batch = json.loads(requests_path.read_text())
        batch["requests"][0]["seed"] += 100  # the id no longer names this content
        requests_path.write_text(json.dumps(batch))
        receipt["requests_sha256"] = prerender.sha256_file(requests_path)
    receipt_path.write_text(json.dumps(receipt))
    with pytest.raises(render.RenderError) as error:
        render.render(cfg, prerendered=root)
    assert error.value.code == code
    assert not workspace.runs()


def test_the_runner_and_narrate_agree_on_request_ids():
    body = {"text": "Ünïcode and  spaces.", "seed": 7, "voice_ref": "refs/" + "a" * 64 + ".wav"}
    assert runner_module().request_id(body) == prerender.request_id(body)
    assert prerender.request_id(body) == prerender.request_id({"id": "ignored", **body})
    assert prerender.request_id(body) != prerender.request_id({**body, "seed": 8})


def test_reference_mode_sends_voice_ref_alone(workspace, kit, tmp_path):
    use_batch(workspace, kit)
    workspace.extra = '[engine]\naudiocpp_clone = "reference"\n'
    cfg = Config(workspace.write(SLIDE))
    path, plan = render.plan(cfg, tmp_path / "plan", takes=1)
    requests = json.loads((path.parent / plan["batches"][0]["file"]).read_text())["requests"]
    assert all(set(r) == {"id", "text", "seed", "voice_ref"} for r in requests)
    run_batch(kit, path.parent)
    _, manifest = render.render(cfg, prerendered=path.parent)
    assert manifest["engine"]["synthesis"]["clone"] == "reference"
    assert {t["ref_text_used"] for c in manifest["chunks"] for t in c["qa"]["takes"]} == {False}


def test_a_reference_the_encoder_cannot_take_is_refused_at_the_plan(workspace, kit, tmp_path):
    use_batch(workspace, kit)
    clip = workspace.store / next(p.name for p in workspace.store.iterdir() if p.suffix == ".wav")
    with wave.open(str(clip)) as w:
        params, frames = w.getparams(), w.readframes(w.getnframes())
    long = workspace.store / "long.wav"
    with wave.open(str(long), "wb") as w:
        w.setparams(params)
        w.writeframes(frames * 2)  # 20 s: past the 14.88 s encoder capacity
    workspace.voices[0]["refClipSha256"] = prerender.sha256_file(long)
    cfg = Config(workspace.write(SLIDE))
    with pytest.raises(render.RenderError) as error:
        render.plan(cfg, tmp_path / "plan")
    assert error.value.code == "ref_clip_misfit"
    assert not (tmp_path / "plan").exists()


def test_an_unpinned_or_misnamed_batch_engine_is_refused(workspace, kit, tmp_path):
    use_batch(workspace, kit, files=[])
    cfg = Config(workspace.write(SLIDE))
    with pytest.raises(render.RenderError) as error:
        render.plan(cfg, tmp_path / "plan")
    assert error.value.code == "engine_unpinned"
    workspace.engines[-1] = batch_engine(kit, endpoint="audiocpp://ming3_tts")
    cfg = Config(workspace.write(SLIDE))
    with pytest.raises(render.RenderError) as error:
        render.plan(cfg, tmp_path / "plan")
    assert error.value.code == "engine_endpoint_invalid"


def test_the_engine_client_never_runs_a_batch_engine(kit):
    eng = batch_engine(kit)
    with pytest.raises(engine.EngineError) as error:
        engine.synthesize(eng, "Hello.", {"id": "v"}, {}, 0, 1.0, {})
    assert error.value.code == "engine_out_of_process"
    assert engine.honours_speed(eng) is False
    assert engine.probe(eng)["available"] == "out_of_process"


def test_the_runner_refuses_a_wrong_pin_and_a_bad_request(workspace, kit, tmp_path, capsys):
    use_batch(workspace, kit)
    path, plan = render.plan(Config(workspace.write(SLIDE)), tmp_path / "plan", takes=1)
    root = path.parent
    name = plan["batches"][0]["file"].split("/")[1][:-5]
    module = runner_module()
    base = ["run", str(root), "--requests", f"requests/{name}.json", "--binary", str(kit.binary)]
    base += ["--model", str(kit.model), "--model-sha256", kit.model_sha]
    assert module.main([*base, "--binary-sha256", "f" * 64]) == 2
    assert "sha256" in capsys.readouterr().err
    ref = root / "refs" / f"{workspace.voices[0]['refClipSha256']}.wav"
    ref.write_bytes(ref.read_bytes() + b"\0\0")
    assert module.main([*base, "--binary-sha256", kit.binary_sha]) == 2
    assert "not the one its name says" in capsys.readouterr().err
    assert not (root / "receipts").exists() and not kit.log.exists()


def test_a_stopped_batch_keeps_its_finished_takes_and_the_next_run_finishes_it(workspace, kit, tmp_path, monkeypatch):
    use_batch(workspace, kit)
    cfg = Config(workspace.write(SLIDE))
    path, plan = render.plan(cfg, tmp_path / "plan", takes=2)
    root = path.parent
    monkeypatch.setenv("FAKE_AUDIOCPP_FAIL_AFTER", "1")
    assert run_batch(kit, root) == [1]
    (receipt_path,) = (root / "receipts").glob("*.json")
    receipt = json.loads(receipt_path.read_text())
    assert receipt["exit_code"] == 1 and len(receipt["outputs"]) == 1
    assert len(receipt["missing"]) == plan["totals"]["requests"] - 1
    monkeypatch.delenv("FAKE_AUDIOCPP_FAIL_AFTER")
    name = plan["batches"][0]["file"].split("/")[1][:-5]
    assert run_batch(kit, root, name, "--only-missing") == [0]
    assert (root / "receipts" / f"{name}.part1.json").is_file()
    _, manifest = render.render(cfg, prerendered=root)
    assert {b["receipt"] for b in manifest["engine"]["synthesis"]["batches"]} >= {f"{name}.part1.json"}


def test_a_batch_past_its_deadline_is_stopped(workspace, kit, tmp_path, monkeypatch):
    use_batch(workspace, kit)
    path, _ = render.plan(Config(workspace.write(SLIDE)), tmp_path / "plan", takes=1)
    monkeypatch.setenv("FAKE_AUDIOCPP_HANG_AFTER", "1")
    assert run_batch(kit, path.parent, None, "--deadline-s", "2") == [20]
    (receipt_path,) = (path.parent / "receipts").glob("*.json")
    receipt = json.loads(receipt_path.read_text())
    assert receipt["stop_rule"].startswith("deadline") and receipt["process_group_gone"] is True
    assert len(receipt["outputs"]) == 1  # the take the runtime reported finished


def test_the_cli_plans_and_renders(workspace, kit, tmp_path, capsys):
    use_batch(workspace, kit)
    config = workspace.write(SLIDE)
    assert main(["plan", str(config), "--out", str(tmp_path / "plan"), "--takes", "1", "--confidential"]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["ok"] and summary["totals"]["requests"] >= 1
    assert main(["plan", str(config), "--out", str(tmp_path / "plan")]) == 1
    assert json.loads(capsys.readouterr().err)["refused"] == "plan_exists"
    run_batch(kit, tmp_path / "plan")
    capsys.readouterr()
    assert main(["render", str(config), "--prerendered", str(tmp_path / "plan"), "--json", "--confidential"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["verified"] and out["engine"] == ENGINE_ID


def test_policy_admits_a_batch_engine_only_under_gpu_direct(kit):
    from narrate import policy

    eng = batch_engine(kit)
    assert policy.consistent(eng) and policy.may_run_confidential(eng)
    assert not policy.consistent({**eng, "profile": "GpuSwitch"})
    assert not policy.consistent({**eng, "profile": "MacMlx"})


def test_best_of_reraises_when_the_first_take_is_missing():
    def synth(seed):
        raise qa.NoTake("x")

    gates = {"maxTakes": 3, "maxChunkWer": 0.1, "minSim": 0}
    with pytest.raises(qa.NoTake):
        qa.best_of("text", synth, lambda pcm, text: {}, gates, 0)


def test_a_plan_directory_holds_no_store_path(workspace, kit, tmp_path):
    use_batch(workspace, kit)
    path, _ = render.plan(Config(workspace.write(SLIDE)), tmp_path / "plan")
    for file in path.parent.rglob("*.json"):
        assert str(workspace.store) not in file.read_text()
    shutil.rmtree(path.parent)
