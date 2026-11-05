"""Refusals and evidence added after the first review of the CLI lane: the guitar-runs location, the whisper model
binding, unmeasured-chunk flags, voices add, slide ids, the input pin, the whisper model precedence, the shared
loudness rule, the engine transport rule, numerals in WER, evaluate on the delivered audio and verify on a
malformed EDL."""

import json
import re
import wave

import pytest
from conftest import PACKAGE, SLIDE, dhall_check

from narrate import adapters, audio, config, engine, evaluate, qa, registry, render, verify
from narrate.__main__ import main
from narrate.config import Config, ConfigError

POST = {"loudnessLufs": -16.0, "loudnessToleranceLu": 0.5, "truePeakDbtp": -1.5}


# -- 1: never under artifacts/runs/ -------------------------------------------------------------------------------
def test_out_under_guitar_runs_is_refused(workspace, capsys):
    toml = workspace.write(SLIDE)
    for out in (config.GUITAR_RUNS, config.GUITAR_RUNS / "narration"):
        with pytest.raises(ConfigError) as caught:
            Config(toml, {"out": str(out)})
        assert caught.value.code == "out_in_guitar_runs"
        assert main(["render", str(toml), "--out", str(out)]) == 1
        assert json.loads(capsys.readouterr().err)["refused"] == "out_in_guitar_runs"
    assert not config.in_guitar_runs(config.ROOT / "artifacts" / "narrate")
    assert not config.in_guitar_runs(config.ROOT / "artifacts" / "runs-narration")


def test_render_root_under_guitar_runs_is_refused(workspace):
    renderer = render.Renderer(Config(workspace.write(SLIDE)))
    with pytest.raises(ConfigError):
        renderer.run(config.GUITAR_RUNS / "x")


def test_verify_refuses_a_run_under_guitar_runs(workspace, ffmpeg, monkeypatch):
    final, _ = render.render(Config(workspace.write(SLIDE)))
    assert verify.verify(final)["checks"]["location"] is True
    monkeypatch.setattr(config, "GUITAR_RUNS", final.parent)
    receipt = verify.verify(final)
    assert receipt["ok"] is False and receipt["reason"].startswith("location")


# -- 2: the whisper model is bound by digest --------------------------------------------------------------------
def whisper_for(workspace, model, monkeypatch, registry_file):
    cfg = Config(workspace.write(SLIDE))
    cfg.whisper_model = model
    monkeypatch.setattr(qa.shutil, "which", lambda name: "/fixture/" + name)
    monkeypatch.setattr(qa, "MODELS", registry_file)
    return qa.Whisper(cfg)


def test_an_unregistered_whisper_model_is_not_used(workspace, tmp_path, monkeypatch):
    model = tmp_path / "model.bin"
    model.write_bytes(b"not the registered model")
    registry_file = tmp_path / "models.json"
    registry_file.write_text(json.dumps({"schema_version": 1, "models": {"other": {"sha256": "0" * 64}}}))
    whisper = whisper_for(workspace, model, monkeypatch, registry_file)
    ready, reason = whisper.available()
    assert ready is False and "not registered" in reason
    assert whisper.identity()["model_sha256"] is None


def test_a_registered_whisper_model_records_its_digest(workspace, tmp_path, monkeypatch):
    model = tmp_path / "model.bin"
    model.write_bytes(b"a registered fixture model")
    digest = qa.model_digest(model)
    registry_file = tmp_path / "models.json"
    registry_file.write_text(json.dumps({"schema_version": 1, "models": {"fixture-whisper": {"sha256": digest}}}))
    whisper = whisper_for(workspace, model, monkeypatch, registry_file)
    assert whisper.available() == (True, "whisper-cli with fixture-whisper")
    assert whisper.identity() == {
        "backend": "cli",
        "model_sha256": digest,
        "model_id": "fixture-whisper",
        "endpoint": None,
    }


def test_the_registered_small_en_digest_is_found():
    entries = json.loads(qa.MODELS.read_text())["models"]
    digest = entries["ggerganov-whisper-cpp-ggml-small.en"]["sha256"]
    assert qa.registered(digest) == "ggerganov-whisper-cpp-ggml-small.en"
    assert qa.registered("f" * 64) is None


def test_the_http_backend_records_its_loopback_endpoint(workspace):
    cfg = Config(workspace.write(SLIDE))
    cfg.whisper = cfg.whisper | {"backend": "http", "url": "http://127.0.0.1:8178/inference"}
    whisper = qa.Whisper(cfg)
    assert whisper.available()[0] is True
    assert whisper.identity()["endpoint"] == "http://127.0.0.1:8178/inference"
    cfg.whisper = cfg.whisper | {"url": "http://192.0.2.1:8178/inference"}
    assert qa.Whisper(cfg).available()[0] is False


# -- 3: unmeasured chunks are flagged ---------------------------------------------------------------------------
def test_unmeasured_chunks_are_flagged_and_printed(workspace, ffmpeg, capsys):
    toml = workspace.write(SLIDE)
    assert main(["render", str(toml)]) == 0
    line = capsys.readouterr().out
    assert "wer_not_measured" in line and "sim_not_measured" in line
    _, manifest = render.render(Config(toml))
    assert {"wer_not_measured", "sim_not_measured"} <= set(manifest["flags"])
    assert all(c["qa"]["wer_status"] == "not_measured" for c in manifest["chunks"])


def test_a_measured_wer_is_not_flagged_unmeasured(workspace, ffmpeg):
    cfg = Config(workspace.write("One short line to read.\n", "PlainText"))
    _, manifest = render.render(cfg, transcriber=lambda pcm, text: text)
    assert "wer_not_measured" not in manifest["flags"] and "sim_not_measured" in manifest["flags"]


# -- 4: voices add ------------------------------------------------------------------------------------------------
def voice_fields():
    text = (PACKAGE / "dhall" / "Voice.dhall").read_text()
    body = text[text.index("let T =") : text.index("\nin ")]
    return set(re.findall(r"[{,]\s*(\w+)\s*:", body))


def wav_file(path, channels=1, width=2, seconds=12.0, rate=16000):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(bytes(channels * width * round(seconds * rate)))
    return path


def test_voices_add_record_is_exactly_the_dhall_voice(workspace, tmp_path):
    cfg = Config(workspace.write(SLIDE))
    text = tmp_path / "clip.txt"
    text.write_text("A transcript.\n")
    clip = tmp_path / "clip.wav"
    clip.write_bytes(dhall_check().sine_wav())
    record = registry.add_voice(cfg, clip, text, "voice-new", "consent-new", engines_allowed=["fake-sine"])
    assert set(record) == voice_fields()
    assert "channels" not in record


@pytest.mark.parametrize(
    "make,code",
    [
        (lambda p: wav_file(p, channels=2), "ref_clip_invalid"),
        (lambda p: wav_file(p, width=1), "ref_clip_invalid"),
        (lambda p: p.write_bytes(b"not a wav at all") and p, "ref_clip_invalid"),
        (lambda p: p.write_bytes(b"") or p, "ref_clip_invalid"),
    ],
)
def test_voices_add_refuses_bad_clips(workspace, tmp_path, make, code):
    cfg = Config(workspace.write(SLIDE))
    text = tmp_path / "clip.txt"
    text.write_text("A transcript.\n")
    clip = tmp_path / "clip.wav"
    make(clip)
    with pytest.raises(registry.RegistryError) as caught:
        registry.add_voice(cfg, clip, text, "v", "c", engines_allowed=["fake-sine"])
    assert caught.value.code == code
    assert sorted(p.name for p in workspace.store.iterdir()) == sorted(dhall_check().fixtures())


def test_voices_add_refuses_no_or_unknown_engines_through_the_cli(workspace, tmp_path, capsys):
    toml = workspace.write(SLIDE)
    clip, text = wav_file(tmp_path / "clip.wav"), tmp_path / "clip.txt"
    text.write_text("A transcript.\n")
    base = ["voices", str(toml), "add", "--clip", str(clip), "--transcript", str(text), "--id", "v", "--consent", "c"]
    assert main(base) == 1
    assert json.loads(capsys.readouterr().err)["refused"] == "voice_engines_empty"
    assert main([*base, "--allow-engine", "nope"]) == 1
    assert json.loads(capsys.readouterr().err)["refused"] == "engine_unknown"
    stereo = wav_file(tmp_path / "stereo.wav", channels=2)
    assert main([*base[:4], str(stereo), *base[5:], "--allow-engine", "fake-sine"]) == 1
    assert json.loads(capsys.readouterr().err)["refused"] == "ref_clip_invalid"
    assert main([*base, "--allow-engine", "fake-sine"]) == 0
    assert set(json.loads(capsys.readouterr().out)) == voice_fields()


# -- 5: slide ids -----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("slide", ["3/4", "../x", ".hidden", "a b", "x" * 65])
def test_a_slide_id_that_cannot_name_a_file_is_refused(slide):
    with pytest.raises(adapters.InputError, match="slide"):
        adapters.markdown(f"---\nslide: {slide}\n---\n\nSome narration.\n")


def test_a_slide_id_from_the_file_name_is_made_safe():
    script = adapters.markdown("Some narration.\n", name="my slide (draft)")
    assert script.segments[0].id == "slide-my-slide--draft-"


def test_a_slash_slide_id_is_a_typed_cli_refusal(workspace, capsys):
    toml = workspace.write(SLIDE.replace("slide: 3", "slide: 3/4"))
    assert main(["render", str(toml)]) == 1
    assert json.loads(capsys.readouterr().err)["refused"] == "input_invalid"
    assert workspace.runs() == []


# -- 7: the input pin -------------------------------------------------------------------------------------------
def test_an_empty_input_pin_is_recorded_and_flagged(workspace, ffmpeg):
    _, manifest = render.render(Config(workspace.write(SLIDE)))
    assert manifest["input"]["pinned"] is False and "input_unpinned" in manifest["flags"]
    path = workspace.base / "script.md"
    workspace.job["inputSha256"] = audio_sha(path)
    _, manifest = render.render(Config(workspace.write(SLIDE)))
    assert manifest["input"]["pinned"] is True and "input_unpinned" not in manifest["flags"]


def audio_sha(path):
    from narrate.ir import sha256_file

    return sha256_file(path)


# -- 8: the whisper model precedence ----------------------------------------------------------------------------
def test_an_explicit_toml_whisper_model_beats_the_environment(workspace, monkeypatch):
    toml = workspace.write(SLIDE)
    monkeypatch.setenv("WHISPER_MODEL", "/env/whisper.bin")
    monkeypatch.setenv("NARRATE_WHISPER_MODEL", "/env/narrate.bin")
    assert Config(toml).whisper_model == workspace.base / "no-such-model.bin"
    text = toml.read_text()
    toml.write_text(re.sub(r"\[whisper\]\nmodel = .*\n", "", text))
    assert Config(toml).whisper_model.as_posix() == "/env/narrate.bin"
    monkeypatch.delenv("NARRATE_WHISPER_MODEL")
    assert Config(toml).whisper_model.as_posix() == "/env/whisper.bin"
    monkeypatch.delenv("WHISPER_MODEL")
    assert Config(toml).whisper_model == config.ROOT / config.WHISPER["model"]


# -- 9: one loudness rule ---------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "integrated,peak,kind,flags",
    [
        (-16.0, -1.5, "linear", []),
        (-16.0, -1.41, "linear", []),
        (-16.0, -1.3, "linear", ["true_peak_over_ceiling"]),
        (-16.6, -2.0, "linear", ["loudness_out_of_tolerance"]),
        (-16.0, -2.0, "dynamic", ["loudnorm_dynamic"]),
        (-16.0, -2.0, None, []),
    ],
)
def test_loudness_verdict(integrated, peak, kind, flags):
    assert audio.loudness_verdict(integrated, peak, POST, kind) == (not flags, flags)


def test_evaluate_uses_the_same_loudness_rule_as_render(workspace, ffmpeg):
    final, manifest = render.render(Config(workspace.write(SLIDE)))
    result = evaluate.evaluate(final, ("loudness",))
    assert result["metrics"]["loudness"]["passed"] == manifest["loudness"]["passed"]
    assert result["metrics"]["loudness"]["flags"] == manifest["loudness"]["flags"]


# -- 10: the bearer token never crosses a network in cleartext --------------------------------------------------
REMOTE = {"id": "remote", "backend": "MlxAudio", "profile": "GpuDirect", "endpoint": "", "model": "m"}


@pytest.mark.parametrize(
    "profile,endpoint,token,refused",
    [
        ("GpuDirect", "http://127.0.0.1:9", True, False),
        ("GpuDirect", "http://localhost:9", True, False),
        ("GpuDirect", "http://192.0.2.10:9", False, False),
        ("GpuDirect", "http://192.0.2.10:9", True, True),
        ("GpuDirect", "https://192.0.2.10:9", True, False),
        ("Hosted", "http://127.0.0.1:9", False, True),
        ("RentedOpen", "http://192.0.2.10:9", False, True),
        ("RentedOpen", "https://192.0.2.10:9", True, False),
    ],
)
def test_transport_rule(profile, endpoint, token, refused):
    eng = REMOTE | {"profile": profile, "endpoint": endpoint}
    if refused:
        with pytest.raises(engine.EngineError) as caught:
            engine.transport_ok(eng, endpoint, token)
        assert caught.value.code == "engine_transport_insecure"
    else:
        engine.transport_ok(eng, endpoint, token)


def test_a_token_is_never_sent_over_cleartext_to_a_remote_host(monkeypatch):
    monkeypatch.setenv(engine.TOKEN_ENV, "fixture-token")
    sent = []
    monkeypatch.setattr(engine.OPENER, "open", lambda *a, **k: sent.append(a))
    eng = REMOTE | {"endpoint": "http://192.0.2.10:9"}
    with pytest.raises(engine.EngineError, match="engine_transport_insecure"):
        engine.speech(
            eng,
            "x",
            {"id": "v"},
            {"audio": b"", "text": ""},
            0,
            1.0,
            {"ref_audio": "omit", "max_reply_bytes": 10, "timeout_s": 1},
        )
    assert sent == []


# -- 11: numerals ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "ref,hyp",
    [
        ("we ship seven tools", "We ship 7 tools."),
        ("version two point five", "version 2.5"),
        ("twenty-one tests in two thousand twenty six", "21 tests in 2026"),
        ("eight percent", "8%"),
        ("one hundred and five", "105"),
        ("one thousand users", "1,000 users"),
    ],
)
def test_wer_compares_numbers_as_digits(ref, hyp):
    assert qa.wer(ref, hyp) == 0.0


def test_a_counting_run_stays_separate_words():
    assert qa.words("one two three") == ["1", "2", "3"]
    assert qa.wer("one two three", "123") == 1.0


# -- 12: evaluate scores the delivered audio --------------------------------------------------------------------
def test_evaluate_reads_each_chunk_from_the_delivered_narration(workspace, ffmpeg, monkeypatch):
    final, manifest = render.render(Config(workspace.write(SLIDE)))
    read = []

    class FakeWhisper:
        def __init__(self, cfg):
            pass

        def available(self):
            return True, "fixture"

        def identity(self):
            return {"backend": "fixture", "model_sha256": None, "model_id": None, "endpoint": None}

        def read(self, pcm):
            read.append(pcm)
            return ""

    monkeypatch.setattr(qa, "Whisper", FakeWhisper)
    result = evaluate.evaluate(final, ("wer",), Config(workspace.base / "narrate.toml"))
    wer = result["metrics"]["wer"]
    assert wer["scored"].startswith("narration.wav")
    delivered = audio.read(final / "narration.wav")
    for pcm, chunk in zip(read, manifest["chunks"], strict=True):
        a = round(chunk["out_start_s"] * delivered.rate)
        b = round(chunk["out_end_s"] * delivered.rate)
        assert pcm.samples == delivered.samples[a:b]


# -- 13: verify on a malformed EDL ------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "segments", [[{"out_end_s": 1.0, "id": "x"}], [{"out_start_s": 0.0, "out_end_s": 1.0}], ["x"], {}]
)
def test_verify_returns_a_receipt_for_a_malformed_edl(workspace, ffmpeg, segments):
    final, _ = render.render(Config(workspace.write(SLIDE)))
    path = final / "narration.edl.json"
    edl = json.loads(path.read_text())
    edl["segments"] = segments
    path.write_text(json.dumps(edl))
    ok, why = verify.edl_ok(final, "narration.edl.json", json.loads((final / "manifest.json").read_text())["timeline"])
    assert ok is False and ("malformed" in why or "not a list" in why)
    assert verify.verify(final)["ok"] is False
