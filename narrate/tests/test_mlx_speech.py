"""narrate/serve/mlx_speech.py with a fake backend (no MLX, no weights, no network beyond loopback): the request
dialect narrate sends, the reference handling, the facts it answers in headers, and every refusal. Then narrate's
own client against it, and narrate/bench/run_arm.py's chunk list, run ledger and scoring helpers."""

import base64
import importlib.util
import inspect
import io
import json
import math
import os
import threading
import urllib.error
import urllib.request
import wave
from http.server import HTTPServer
from pathlib import Path

import pytest

from narrate import audio, engine
from narrate.config import ENGINE

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mlx_speech = load("narrate_mlx_speech", "narrate/serve/mlx_speech.py")
run_arm = load("narrate_bench_run_arm", "narrate/bench/run_arm.py")


def ref_wav(seconds=0.2, rate=16000):
    return engine.wav_bytes([0] * int(seconds * rate), rate)


REF = {"audio": ref_wav(), "text": "Synthetic reference transcript."}
DATA_URI = "data:audio/wav;base64," + base64.b64encode(REF["audio"]).decode("ascii")


class Result:
    def __init__(self, audio, rate):
        self.audio, self.sample_rate = audio, rate


class ClonerModel:
    """A cloning model: names ref_audio, ref_text, voice and speed, like Qwen3-TTS and Ming at the pinned pin."""

    model_type = "qwen3_tts"
    sample_rate = 24000

    def __init__(self):
        self.calls = []

    def generate(self, text, voice=None, speed=1.0, lang_code="auto", ref_audio=None, ref_text=None, **kwargs):
        seen = {"text": text, "voice": voice, "speed": speed, "lang_code": lang_code, "ref_text": ref_text, **kwargs}
        if isinstance(ref_audio, str):
            seen["ref_audio_path_existed"] = os.path.exists(ref_audio)
            with open(ref_audio, "rb") as f:
                seen["ref_audio_bytes"] = f.read()
        else:
            seen["ref_audio"] = ref_audio
        self.calls.append(seen)
        n = int(0.05 * len(text) * self.sample_rate)
        yield Result([0.5 * math.sin(i / 7) for i in range(n // 2)], self.sample_rate)
        yield Result([2.0] * (n - n // 2), self.sample_rate)  # out of range: clipped, never wrapped


class VoxModel(ClonerModel):
    """Names ref_text but its reference-only path does not read it (VoxCPM2 at the pinned commit)."""

    model_type = "voxcpm2"
    sample_rate = 48000

    def generate(self, text, ref_text=None, ref_audio=None, prompt_text=None, prompt_audio=None, **kwargs):
        self.calls.append(
            {
                "text": text,
                "ref_text": ref_text,
                "prompt_text": prompt_text,
                "prompt_audio": prompt_audio,
                "ref_audio": ref_audio,
                **kwargs,
            }
        )
        yield Result([0.1] * 4800, self.sample_rate)


class Backend:
    def __init__(self, models):
        self.models, self.loads, self.unloads, self.seeds, self.preserve = models, [], 0, [], True

    def load(self, path):
        self.loads.append(path)
        return self.models[path]

    def unload(self):
        self.unloads += 1

    def reference(self, model, path):
        return path if self.preserve else ("loaded", path)

    def seed(self, value):
        self.seeds.append(value)

    def reset_peak(self):
        pass

    def peak(self):
        return 123456


class Server:
    def __init__(self, models, modes=None):
        self.models = models
        self.backend = Backend({f"/models/{k}": v for k, v in models.items()})
        self.engine = mlx_speech.Engine({k: f"/models/{k}" for k in models}, self.backend, modes)
        self.httpd = HTTPServer(("127.0.0.1", 0), mlx_speech.handler_for(self.engine, {"mlx_audio": "fixture"}))
        self.httpd.RequestHandlerClass.log_message = lambda *a: None
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.httpd.server_port}"

    def post(self, body, content_type="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        request = urllib.request.Request(
            self.url + "/v1/audio/speech", data=data, method="POST", headers={"Content-Type": content_type}
        )
        try:
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=10) as reply:
                return reply.status, reply.read(), dict(reply.headers)
        except urllib.error.HTTPError as error:
            return error.code, error.read(), dict(error.headers)

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def server():
    s = Server({"cloner": ClonerModel(), "vox": VoxModel(), "vox-combined": VoxModel()}, {"vox-combined": "combined"})
    yield s
    s.close()


def body(**extra):
    return {
        "model": "cloner",
        "input": "Read this sentence.",
        "voice": "voice-id",
        "response_format": "wav",
        "speed": 1.1,
        "seed": 7,
        "ref_audio": DATA_URI,
        "ref_text": REF["text"],
        **extra,
    }


def test_binds_loopback_only():
    assert mlx_speech.HOST == "127.0.0.1"
    assert "host" not in inspect.signature(mlx_speech.main).parameters
    assert "--host" not in Path(mlx_speech.__file__).read_text()


def test_clone_request_reaches_the_model_and_answers_a_clipped_wav_with_facts(server):
    status, data, headers = server.post(body(lang_code="en"))
    assert status == 200 and headers["Content-Type"] == "audio/wav"
    (call,) = server.models["cloner"].calls
    assert call["ref_audio_path_existed"] and call["ref_audio_bytes"] == REF["audio"]
    assert call["ref_text"] == REF["text"] and call["voice"] is None  # a preset voice never overrides the clone
    assert call["speed"] == 1.1 and call["lang_code"] == "en"
    assert server.backend.seeds == [7]
    with wave.open(io.BytesIO(data)) as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (24000, 1, 2)
        frames = w.readframes(w.getnframes())
    assert max(int.from_bytes(frames[i : i + 2], "little", signed=True) for i in range(0, len(frames), 2)) == 32767
    assert headers["X-Ref-Audio-Used"] == "true" and headers["X-Ref-Text-Used"] == "true"
    assert headers["X-Ref-Mode"] == "ref" and headers["X-Seed-Used"] == "true"
    assert headers["X-Speed-Param"] == "named" and headers["X-Sample-Rate"] == "24000"
    assert headers["X-Mlx-Peak-Bytes"] == "123456" and float(headers["X-Load-Seconds"]) >= 0
    assert int(headers["X-Max-Rss-Bytes"]) > 0


def test_the_temporary_reference_is_gone_after_the_take(server):
    server.post(body())
    (call,) = server.models["cloner"].calls
    assert call["ref_audio_path_existed"]
    seen = []
    original = server.models["cloner"].generate

    def spy(text, **kw):
        seen.append(kw["ref_audio"])
        yield from original(text, **kw)

    server.models["cloner"].generate = spy
    server.post(body())
    assert seen and not os.path.exists(seen[0])


def test_without_a_reference_the_preset_voice_is_passed(server):
    status, _, headers = server.post(body(ref_audio=None, ref_text=None, seed=None))
    assert status == 200
    (call,) = server.models["cloner"].calls
    assert call["voice"] == "voice-id"
    assert headers["X-Ref-Audio-Used"] == "false" and "X-Ref-Text-Used" not in headers
    assert headers["X-Seed-Used"] == "false" and server.backend.seeds == []


def test_a_model_whose_reference_mode_ignores_the_transcript_says_so(server):
    status, _, headers = server.post(body(model="vox"))
    assert status == 200 and headers["X-Ref-Text-Used"] == "false" and headers["X-Ref-Mode"] == "ref"
    assert "X-Speed-Param" not in headers  # VoxCPM2's generate() names no speed: the knob is not applied
    (call,) = server.models["vox"].calls
    assert call["prompt_text"] is None and "speed" not in call


def test_combined_mode_sends_the_transcript_as_a_continuation_prompt(server):
    status, _, headers = server.post(body(model="vox-combined"))
    assert status == 200 and headers["X-Ref-Text-Used"] == "true" and headers["X-Ref-Mode"] == "combined"
    (call,) = server.models["vox-combined"].calls
    assert call["prompt_text"] == REF["text"] and call["prompt_audio"] == call["ref_audio"]
    assert call["ref_text"] is None


def test_one_model_is_resident_and_switching_reloads(server):
    for model in ("cloner", "cloner", "vox", "cloner"):
        assert server.post(body(model=model))[0] == 200
    assert server.backend.loads == ["/models/cloner", "/models/vox", "/models/cloner"]
    assert server.backend.unloads == 3


@pytest.mark.parametrize(
    "change,status,code",
    [
        ({"model": "elsewhere"}, 404, "model_not_allowed"),
        ({"model": "../x"}, 400, "model_invalid"),
        ({"input": ""}, 400, "input_invalid"),
        ({"input": "x" * 2001}, 400, "input_invalid"),
        ({"response_format": "mp3"}, 400, "format_unsupported"),
        ({"speed": 3}, 400, "speed_invalid"),
        ({"speed": True}, 400, "speed_invalid"),
        ({"seed": True}, 400, "seed_invalid"),
        ({"seed": -1}, 400, "seed_invalid"),
        ({"ref_audio": "/etc/hosts"}, 400, "ref_audio_invalid"),
        ({"ref_audio": "data:audio/wav;base64,!!!"}, 400, "ref_audio_invalid"),
        ({"ref_audio": "data:audio/wav;base64," + base64.b64encode(b"not a wav").decode()}, 400, "ref_audio_invalid"),
        ({"ref_text": 5}, 400, "ref_text_invalid"),
    ],
)
def test_refusals(server, change, status, code):
    got, data, _ = server.post(body(**change))
    assert got == status and json.loads(data)["error"] == code
    assert server.models["cloner"].calls == []


def test_transport_refusals(server):
    assert server.post(b"{}", content_type="text/plain")[0] == 415
    assert json.loads(server.post(b"[1]")[1])["error"] == "json_invalid"
    assert json.loads(server.post(b"not json")[1])["error"] == "json_invalid"
    request = urllib.request.Request(
        server.url + "/v1/other", data=b"{}", method="POST", headers={"Content-Type": "application/json"}
    )
    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=5)
    assert caught.value.code == 404


def test_a_model_failure_is_a_500_with_its_type_only(server):
    def broken(text, **kw):
        raise ValueError("prompt exhausts the cache: secret detail")
        yield  # pragma: no cover

    server.models["cloner"].generate = broken
    status, data, _ = server.post(body())
    assert status == 500 and json.loads(data) == {"error": "engine_failed", "detail": "ValueError"}


def test_health_names_models_never_paths(server):
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(server.url + "/health") as reply:
        health = json.loads(reply.read())
    assert health["models"] == ["cloner", "vox", "vox-combined"] and "/models" not in json.dumps(health)


def test_narrate_client_against_the_server_records_what_it_said(server):
    record = {
        "id": "mac-mlx-fixture",
        "backend": "MlxAudio",
        "profile": "MacMlx",
        "endpoint": server.url,
        "model": "cloner",
        "sampleRateHz": None,
    }
    data, facts = engine.synthesize(record, "Read this.", {"id": "voice-id"}, REF, 3, 1.0, ENGINE)
    assert audio.parse(data).rate == 24000
    assert facts == {"variant": "http", "ref_audio_used": True, "ref_text_used": True, "seed_used": True}
    record["model"] = "vox"
    _, facts = engine.synthesize(record, "Read this.", {"id": "voice-id"}, REF, 3, 1.0, ENGINE)
    assert facts["ref_text_used"] is False
    _, facts = engine.synthesize(record, "x", {"id": "voice-id"}, REF, 3, 1.0, ENGINE | {"ref_audio": "omit"})
    assert facts["ref_audio_used"] is False and facts["ref_text_used"] is False


def test_parse_models_needs_a_snapshot(tmp_path):
    with pytest.raises(SystemExit):
        mlx_speech.parse_models([f"m={tmp_path}"])
    (tmp_path / "config.json").write_text("{}")
    assert mlx_speech.parse_models([f"m={tmp_path}"]) == {"m": str(tmp_path)}
    with pytest.raises(SystemExit):
        mlx_speech.parse_modes(["m=other"], {"m": str(tmp_path)})
    with pytest.raises(SystemExit):
        mlx_speech.parse_modes(["n=combined"], {"m": str(tmp_path)})


# narrate/bench/run_arm.py

TEXT = ROOT / "narrate" / "bench" / "text-v1.md"
CHUNKS_SHA256 = "d52ceaa754a42b90b3b268c63bb370b6c2bab40af2a52472c88b49a63c78c1bc"


def test_bench_chunk_list_is_fixed_and_follows_the_plan():
    markdown = TEXT.read_text(encoding="utf-8")
    chunks = run_arm.chunk_list(markdown)
    assert run_arm.chunk_digest(chunks) == CHUNKS_SHA256 and len(chunks) == 17
    assert all(len(c["text"]) <= run_arm.LIMIT for c in chunks)
    for sid, prose in run_arm.sections(markdown):
        mine = [c["text"] for c in chunks if c["section"] == sid]
        assert " ".join(mine) == prose  # nothing dropped, nothing crosses a section
    assert [sid for sid, _ in run_arm.sections(markdown)] == ["s1", "s2", "s3", "s4", "s5", "s6"]
    spoken = " ".join(c["text"] for c in chunks)
    assert "narrate-bench-text-v1" not in spoken and "Written fresh" not in spoken  # front matter, comments


def test_sections_refuse_a_malformed_text():
    with pytest.raises(ValueError):
        run_arm.sections("---\nid: x\n")
    with pytest.raises(ValueError):
        run_arm.sections("## s1 A\n\nText.\n\n## s1 B\n\nMore.\n")


def test_run_writes_a_resumable_ledger_without_private_paths(server, tmp_path, capsys):
    clip = tmp_path / "private-clip.wav"
    clip.write_bytes(REF["audio"])
    transcript = tmp_path / "private-transcript.txt"
    transcript.write_text(REF["text"] + "\n")
    out = tmp_path / "out"
    argv = [
        "run",
        "--endpoint",
        server.url,
        "--model",
        "cloner",
        "--arm",
        "A2-mac",
        "--voice",
        "v1",
        "--clip",
        str(clip),
        "--transcript",
        str(transcript),
        "--seed",
        "1",
        "--seed",
        "2",
        "--chunks",
        "2",
        "--out",
        str(out),
    ]
    assert run_arm.main(argv) == 0
    takes = run_arm.read_takes(out / "takes.jsonl")
    assert [(t["seed"], t["chunk"]) for t in takes] == [(1, "s1.c01"), (1, "s1.c02"), (2, "s1.c01"), (2, "s1.c02")]
    take = takes[0]
    assert take["ok"] and take["rate"] == 24000 and take["ref_text_used"] == "true" and take["seed_used"] == "true"
    assert take["peak_bytes"] == 123456 and take["synth_s"] is not None
    assert take["clip_sha256"] == run_arm.sha256_bytes(REF["audio"])
    assert take["transcript_sha256"] == run_arm.sha256_bytes(transcript.read_bytes())
    assert take["chunks_sha256"] == CHUNKS_SHA256
    ledger = (out / "takes.jsonl").read_text()
    assert str(tmp_path) not in ledger and REF["text"] not in ledger
    assert (out / take["wav"]).is_file()
    assert run_arm.main(argv) == 0  # resumes: nothing new
    assert len(run_arm.read_takes(out / "takes.jsonl")) == 4
    assert server.models["cloner"].calls[0]["lang_code"] == "en"


def test_run_records_a_refused_take_and_can_stop(server, tmp_path):
    clip = tmp_path / "clip.wav"
    clip.write_bytes(REF["audio"])
    transcript = tmp_path / "t.txt"
    transcript.write_text("t")
    argv = [
        "run",
        "--endpoint",
        server.url,
        "--model",
        "elsewhere",
        "--arm",
        "A",
        "--voice",
        "v",
        "--clip",
        str(clip),
        "--transcript",
        str(transcript),
        "--seed",
        "1",
        "--out",
        str(tmp_path / "o"),
        "--stop-on-error",
    ]
    assert run_arm.main(argv) == 1
    (take,) = run_arm.read_takes(tmp_path / "o" / "takes.jsonl")
    assert not take["ok"] and take["error"] == "HTTP 404" and "model_not_allowed" in take["detail"]


def write_wav(path, samples, rate=16000, width=2):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(width)
        w.setframerate(rate)
        scale = 32767 if width == 2 else 8388607
        w.writeframes(b"".join(int(v * scale).to_bytes(width, "little", signed=True) for v in samples))


def test_inner_silence_ignores_the_edges_and_reads_24_bit(tmp_path):
    rate = 8000
    tone = [0.3 * math.sin(i / 3) for i in range(rate)]
    hush = [0.0] * int(2.5 * rate)
    for width in (2, 3):
        path = tmp_path / f"t{width}.wav"
        write_wav(path, hush + tone + hush + tone + hush, rate, width)
        samples, got_rate = run_arm.pcm_frames(path)
        assert got_rate == rate
        assert run_arm.inner_silence_s(samples, got_rate) == pytest.approx(2.5, abs=0.06)
    assert run_arm.inner_silence_s([0.0] * rate, rate) == pytest.approx(1.0, abs=0.06)


def test_summary_counts_rtf_wer_and_best_of_seeds():
    chunks = {"s1.c01": {}, "s1.c02": {}}

    def take(seed, chunk, synth, audio_s):
        return {
            "arm": "A",
            "voice": "v",
            "seed": seed,
            "chunk": chunk,
            "wav_sha256": f"{seed}{chunk}",
            "synth_s": synth,
            "wall_s": synth + 1,
            "audio_s": audio_s,
            "at": f"t{seed}{chunk}",
            "load_s": 2.0,
            "peak_bytes": 10 * seed,
            "max_rss_bytes": 5,
            "ref_text_used": "true",
            "rate": 24000,
        }

    latest, scored = {}, {}
    for seed, wers in ((1, (0.5, 0.0)), (2, (0.0, 0.1))):
        for chunk, w in zip(chunks, wers, strict=True):
            t = take(seed, chunk, 3.0, 2.0)
            latest[("A", "v", seed, chunk)] = t
            scored[t["wav_sha256"]] = {
                "chunk": chunk,
                "wer": w,
                "ref_words": 10,
                "catastrophic": ["wer"] if w > 0.3 else [],
            }
    summary = run_arm.summarise(latest, scored, chunks)
    (row,) = summary["arms"]
    one = row["seeds"][1]
    assert one["rtf"] == 1.5 and one["complete"] and one["wer_whole"] == 0.25 and one["catastrophic"] == ["s1.c01"]
    assert one["peak_bytes_max"] == 10 and row["seeds"][2]["peak_bytes_max"] == 20
    assert row["best_of_seeds"] == {"chunks": 2, "wer_whole": 0.0, "catastrophic": []}
