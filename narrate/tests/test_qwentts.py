"""The QwenTtsCpp request mapping against a loopback fake of qwentts.cpp's tts-server (pinned 5916bf7): the speech
route takes no ref_audio, a voice is registered once by name from the reference WAV and its transcript, the
registry is lost when the server restarts, an unknown voice is refused with 400, and `speed` is ignored."""

import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from narrate import audio, engine, render
from narrate.config import ENGINE, Config
from narrate.engine import EngineError

VOICE = {"id": "Voice-Fixture-Sine"}
REF = {"audio": b"RIFF\x24\x00\x00\x00WAVEfixture", "text": "Synthetic sine fixture."}


class QwenTtsServer:
    """The tts-server routes narrate uses, with the pinned runtime's validation and error envelope."""

    def __init__(self):
        self.requests, self.voices, self.mode = [], {}, "ok"
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, status, data, kind):
                self.send_response(status)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def error(self, status, message):
                self.reply(status, json.dumps({"error": {"message": message}}).encode(), "application/json")

            def do_GET(self):
                outer.requests.append({"method": "GET", "path": self.path})
                if self.path != "/v1/audio/voices":
                    return self.error(404, "no route")
                if outer.mode == "garbled_list":
                    return self.reply(200, b"[not json", "application/json")
                listed = [{"name": n, "kind": "registered"} for n in outer.voices]
                self.reply(200, json.dumps({"voices": listed}).encode(), "application/json")

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.requests.append({"method": "POST", "path": self.path, "body": body})
                if self.path == "/v1/audio/voices":
                    if outer.mode == "refuse_register" or not body.get("wav_b64"):
                        return self.error(400, "cannot decode the WAV payload")
                    name = body["name"].lower()
                    outer.voices[name] = {"wav": base64.b64decode(body["wav_b64"]), "ref_text": body["ref_text"]}
                    return self.reply(
                        200, json.dumps({"name": name, "status": "registered"}).encode(), "application/json"
                    )
                if self.path != "/v1/audio/speech":
                    return self.error(404, "no route")
                voice = body.get("voice", "").lower()
                if voice and voice not in outer.voices:
                    return self.error(400, f"unknown voice '{voice}'")
                self.reply(200, engine.sine(body["input"], body.get("seed", 0), 1.0, 24000), "audio/wav")

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.httpd.server_port}"

    def restart(self):
        self.voices.clear()

    def calls(self):
        return [(r["method"], r["path"]) for r in self.requests]

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def qwentts():
    s = QwenTtsServer()
    yield s
    s.close()


def qwentts_engine(url):
    return {
        "id": "qwentts-probe",
        "backend": "QwenTtsCpp",
        "profile": "GpuDirect",
        "endpoint": url,
        "model": "qwen3-tts-1.7b-base",
        "sampleRateHz": 24000,
    }


def test_registers_the_reference_once_then_speaks_by_name(qwentts):
    eng = qwentts_engine(qwentts.url)
    data, facts = engine.synthesize(eng, "Read this.", VOICE, REF, 7, 1.1, ENGINE)
    name = engine.qwentts_voice_name(VOICE, REF)
    assert name == name.lower() and name.startswith("narrate-voice-fixture-sine-")
    assert qwentts.calls() == [
        ("GET", "/v1/audio/voices"),
        ("POST", "/v1/audio/voices"),
        ("POST", "/v1/audio/speech"),
    ]
    registration, speech = qwentts.requests[1]["body"], qwentts.requests[2]["body"]
    assert registration == {"name": name, "ref_text": REF["text"], "wav_b64": base64.b64encode(REF["audio"]).decode()}
    assert speech == {
        "model": "qwen3-tts-1.7b-base",
        "input": "Read this.",
        "response_format": "wav",
        "seed": 7,
        "voice": name,
    }
    assert facts == {
        "variant": "qwentts_registered_voice",
        "speed_honoured": False,
        "ref_audio_used": True,
        "ref_text_used": True,
        "conditioning": "icl",
        "registered_now": True,
    }
    assert audio.parse(data).rate == 24000

    _, again = engine.synthesize(eng, "And this.", VOICE, REF, 8, 1.0, ENGINE)
    assert again["registered_now"] is False
    assert qwentts.calls()[3:] == [("GET", "/v1/audio/voices"), ("POST", "/v1/audio/speech")]


def test_a_restarted_server_gets_the_voice_again(qwentts):
    eng = qwentts_engine(qwentts.url + "/v1/audio/speech")  # a speech-route endpoint maps to the same base
    engine.synthesize(eng, "One.", VOICE, REF, 1, 1.0, ENGINE)
    qwentts.restart()
    _, facts = engine.synthesize(eng, "Two.", VOICE, REF, 2, 1.0, ENGINE)
    assert facts["registered_now"] is True
    assert [c for c in qwentts.calls() if c == ("POST", "/v1/audio/voices")] == [("POST", "/v1/audio/voices")] * 2


def test_a_changed_clip_or_transcript_registers_under_a_new_name():
    base = engine.qwentts_voice_name(VOICE, REF)
    assert engine.qwentts_voice_name(VOICE, {**REF, "text": "Another transcript."}) != base
    assert engine.qwentts_voice_name(VOICE, {**REF, "audio": REF["audio"] + b"\x00"}) != base
    assert engine.qwentts_voice_name({"id": "other"}, REF) != base


def test_without_a_transcript_the_clone_is_x_vector_only(qwentts):
    _, facts = engine.synthesize(qwentts_engine(qwentts.url), "x", VOICE, {**REF, "text": ""}, 0, 1.0, ENGINE)
    assert facts["conditioning"] == "x_vector" and facts["ref_text_used"] is False


def test_omit_registers_nothing_and_names_no_voice(qwentts):
    _, facts = engine.synthesize(qwentts_engine(qwentts.url), "x", VOICE, REF, 0, 1.0, ENGINE | {"ref_audio": "omit"})
    assert qwentts.calls() == [("POST", "/v1/audio/speech")]
    assert "voice" not in qwentts.requests[0]["body"]
    assert facts["ref_audio_used"] is False and facts["conditioning"] == "none"


def test_a_refused_registration_never_reaches_the_speech_route(qwentts):
    qwentts.mode = "refuse_register"
    with pytest.raises(EngineError) as caught:
        engine.synthesize(qwentts_engine(qwentts.url), "x", VOICE, REF, 0, 1.0, ENGINE)
    assert caught.value.code == "engine_refused"
    assert ("POST", "/v1/audio/speech") not in qwentts.calls()


def test_an_unreadable_voice_list_is_refused(qwentts):
    qwentts.mode = "garbled_list"
    with pytest.raises(EngineError) as caught:
        engine.synthesize(qwentts_engine(qwentts.url), "x", VOICE, REF, 0, 1.0, ENGINE)
    assert caught.value.code == "engine_reply_invalid"


def test_the_token_and_transport_rules_cover_the_registry_routes(qwentts, monkeypatch):
    monkeypatch.setenv(engine.TOKEN_ENV, "fixture-token")
    remote = {**qwentts_engine("http://192.0.2.1:8080"), "id": "remote"}
    with pytest.raises(EngineError, match="engine_transport_insecure"):
        engine.synthesize(remote, "x", VOICE, REF, 0, 1.0, ENGINE)
    assert qwentts.requests == []


def test_honours_speed_is_false_only_for_qwentts():
    assert engine.honours_speed({"backend": "QwenTtsCpp"}) is False
    assert engine.honours_speed({"backend": "MlxAudio"}) is True and engine.honours_speed({"backend": "Fake"}) is True


SRT_LONG = """1
00:00:00,000 --> 00:00:02,000
This cue carries far more words than two seconds can hold, so the fit has work to do here.
"""


def test_render_fits_a_qwentts_engine_with_atempo_alone(workspace, qwentts):
    """The fit never asks a QwenTtsCpp engine for a faster take: its speed knob is ignored, so render goes straight
    to atempo, and the EDL records speed 1.0."""
    workspace.job["captions"] = ["Srt"]
    workspace.engines = [{**workspace.engines[0], **qwentts_engine(qwentts.url), "id": "fake-sine"}]
    final, manifest = render.render(Config(workspace.write(SRT_LONG, "Srt")))
    (segment,) = json.loads((final / "narration.edl.json").read_text())["segments"]
    assert segment["speed"] == 1.0 and segment["atempo"] == pytest.approx(1.08)
    speech = [r for r in qwentts.requests if r["path"] == "/v1/audio/speech"]
    assert len(speech) == 1 and "speed" not in speech[0]["body"]
    assert "overrun" in segment["flags"]
