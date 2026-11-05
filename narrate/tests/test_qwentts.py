"""The QwenTtsCpp request mapping against a loopback fake of qwentts.cpp's tts-server (pinned 5916bf7c,
tools/tts-server.cpp and src/tts-server.h): the speech route takes no ref_audio, a voice is registered by name from
the reference WAV and its transcript once per session under a nonce name and deleted when the session ends, the
registry is lost when the server restarts, an unknown voice is refused with 400, and `speed` is ignored. The fake
checks what the pinned server checks: a non-empty name and either `wav_b64` (a PCM16, PCM24 or float32 RIFF WAVE)
or both `spk_b64` and `rvq_b64`; a non-empty `input`; an integer `seed`; `response_format` pcm or wav; and it
answers a wav request with a 24 kHz mono 16-bit RIFF file and a failed synthesis with 502."""

import base64
import binascii
import json
import struct
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from narrate import audio, engine, render
from narrate.config import ENGINE, Config
from narrate.engine import EngineError

VOICE = {"id": "Voice-Fixture-Sine"}
REF = {"audio": engine.sine("Synthetic sine fixture.", 3, 1.0, 16000), "text": "Synthetic sine fixture."}


def decodable_wav(data):
    """What the pinned read_wav_buf accepts: RIFF WAVE with a fmt chunk of PCM16, PCM24 or float32, then data."""
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        return False
    pos, fmt = 12, None
    while pos + 8 <= len(data):
        chunk, size = data[pos : pos + 4], struct.unpack("<I", data[pos + 4 : pos + 8])[0]
        pos += 8
        if chunk == b"fmt " and size >= 16:
            tag, channels, _, _, _, bits = struct.unpack("<HHIIHH", data[pos : pos + 16])
            fmt = (tag, bits) if channels > 0 else None
        elif chunk == b"data":
            return fmt in ((1, 16), (1, 24), (3, 32))
        pos += size
    return False


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
                listed = [{"name": n, "kind": "registered"} for n in outer.voices]
                self.reply(200, json.dumps({"voices": listed}).encode(), "application/json")

            def do_DELETE(self):
                outer.requests.append({"method": "DELETE", "path": self.path})
                prefix = "/v1/audio/voices/"
                if outer.mode == "refuse_delete":
                    return self.error(500, "fixture failure")
                name = urllib.parse.unquote(self.path[len(prefix) :]).lower()
                if not self.path.startswith(prefix) or name not in outer.voices:
                    return self.error(404, "no registered voice with this name")
                del outer.voices[name]
                self.reply(200, b'{"status":"deleted"}', "application/json")

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.requests.append({"method": "POST", "path": self.path, "body": body})
                if self.path == "/v1/audio/voices":
                    name = body.get("name")
                    if not isinstance(name, str) or not name:
                        return self.error(400, "'name' must be a non-empty string")
                    has_wav, has_spk, has_rvq = (bool(body.get(k)) for k in ("wav_b64", "spk_b64", "rvq_b64"))
                    if has_spk != has_rvq or has_wav == (has_spk and has_rvq):
                        return self.error(400, "provide either 'wav_b64' or both 'spk_b64' and 'rvq_b64'")
                    try:
                        wav = base64.b64decode(body["wav_b64"], validate=True)
                    except (binascii.Error, ValueError):
                        return self.error(400, "invalid base64 payload")
                    if outer.mode == "refuse_register" or not decodable_wav(wav):
                        return self.error(400, "cannot decode the WAV payload")
                    name = name.lower()
                    ref_text = body.get("ref_text") if isinstance(body.get("ref_text"), str) else ""
                    outer.voices[name] = {"wav": wav, "ref_text": ref_text}
                    if outer.mode == "garbled_register":
                        return self.reply(200, b"[not json", "application/json")
                    return self.reply(
                        200, json.dumps({"name": name, "status": "registered"}).encode(), "application/json"
                    )
                if self.path != "/v1/audio/speech":
                    return self.error(404, "no route")
                if not isinstance(body.get("input"), str) or not body["input"]:
                    return self.error(400, "'input' must be a non-empty string")
                if "seed" in body and (isinstance(body["seed"], bool) or not isinstance(body["seed"], int)):
                    return self.error(400, "'seed' is out of domain")
                if body.get("response_format", "pcm") not in ("pcm", "wav"):
                    return self.error(400, "response_format must be 'pcm' or 'wav'")
                voice = body.get("voice", "").lower() if isinstance(body.get("voice"), str) else ""
                if outer.mode == "forget_on_speech":
                    outer.voices.clear()
                if voice and voice not in outer.voices:
                    return self.error(400, f"unknown voice '{voice}'")
                if outer.mode == "synthesis_fails":
                    return self.error(502, "generation failed")
                take = engine.sine(body["input"], body.get("seed", 0), 1.0, 24000)
                if body.get("response_format", "pcm") == "pcm":
                    return self.reply(200, take[44:], "audio/pcm")
                self.reply(200, take, "audio/wav")

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


def test_a_session_registers_once_speaks_by_a_nonce_name_and_deletes_at_the_end(qwentts):
    eng = qwentts_engine(qwentts.url)
    with engine.session(eng, ENGINE) as sess:
        data, facts = engine.synthesize(eng, "Read this.", VOICE, REF, 7, 1.1, ENGINE, sess)
        name = sess.name(VOICE, REF)
        assert name == name.lower() and name.startswith(engine.qwentts_voice_name(VOICE, REF) + "-")
        assert len(name) == len(engine.qwentts_voice_name(VOICE, REF)) + 17
        assert qwentts.calls() == [("POST", "/v1/audio/voices"), ("POST", "/v1/audio/speech")]
        registration, speech = qwentts.requests[0]["body"], qwentts.requests[1]["body"]
        assert registration == {
            "name": name,
            "ref_text": REF["text"],
            "wav_b64": base64.b64encode(REF["audio"]).decode(),
        }
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

        _, again = engine.synthesize(eng, "And this.", VOICE, REF, 8, 1.0, ENGINE, sess)
        assert again["registered_now"] is False
        assert qwentts.calls()[2:] == [("POST", "/v1/audio/speech")]
    assert qwentts.calls()[3:] == [("DELETE", "/v1/audio/voices/" + name)]
    assert qwentts.voices == {}
    assert ("GET", "/v1/audio/voices") not in qwentts.calls()


def test_two_sessions_never_share_a_name(qwentts):
    eng = qwentts_engine(qwentts.url)
    with engine.session(eng, ENGINE) as one, engine.session(eng, ENGINE) as two:
        assert one.name(VOICE, REF) != two.name(VOICE, REF)


def test_without_a_session_one_take_registers_speaks_and_deletes(qwentts):
    engine.synthesize(qwentts_engine(qwentts.url), "x", VOICE, REF, 0, 1.0, ENGINE)
    assert [m for m, _ in qwentts.calls()] == ["POST", "POST", "DELETE"]
    assert qwentts.voices == {}


def test_a_listed_foreign_entry_is_never_trusted(qwentts):
    """Another client registered something under the name stem: the client neither reads the list nor speaks with
    that entry; it registers its own nonce name and leaves the foreign entry alone."""
    stem = engine.qwentts_voice_name(VOICE, REF)
    qwentts.voices[stem] = {"wav": b"someone else", "ref_text": "not the operator"}
    eng = qwentts_engine(qwentts.url)
    with engine.session(eng, ENGINE) as sess:
        engine.synthesize(eng, "x", VOICE, REF, 0, 1.0, ENGINE, sess)
        spoken_with = qwentts.requests[-1]["body"]["voice"]
    assert spoken_with == sess.name(VOICE, REF) != stem
    assert list(qwentts.voices) == [stem]
    assert ("GET", "/v1/audio/voices") not in qwentts.calls()


def test_the_session_deletes_its_voices_when_the_render_fails(qwentts):
    eng = qwentts_engine(qwentts.url)
    with pytest.raises(RuntimeError, match="render failed"), engine.session(eng, ENGINE) as sess:
        engine.synthesize(eng, "x", VOICE, REF, 0, 1.0, ENGINE, sess)
        raise RuntimeError("render failed")
    assert qwentts.calls()[-1][0] == "DELETE" and qwentts.voices == {}


def test_a_restarted_server_gets_the_voice_again_and_the_take_is_asked_once_more(qwentts):
    eng = qwentts_engine(qwentts.url + "/v1/audio/speech")  # a speech-route endpoint maps to the same base
    with engine.session(eng, ENGINE) as sess:
        engine.synthesize(eng, "One.", VOICE, REF, 1, 1.0, ENGINE, sess)
        qwentts.restart()
        _, facts = engine.synthesize(eng, "Two.", VOICE, REF, 2, 1.0, ENGINE, sess)
    assert facts["registered_now"] is True
    assert qwentts.calls() == [
        ("POST", "/v1/audio/voices"),
        ("POST", "/v1/audio/speech"),
        ("POST", "/v1/audio/speech"),  # 400: unknown voice after the restart
        ("POST", "/v1/audio/voices"),
        ("POST", "/v1/audio/speech"),
        ("DELETE", "/v1/audio/voices/" + sess.name(VOICE, REF)),
    ]


def test_a_400_on_a_fresh_registration_is_not_asked_again(qwentts):
    eng = qwentts_engine(qwentts.url)
    qwentts.mode = "forget_on_speech"
    with pytest.raises(EngineError) as caught, engine.session(eng, ENGINE) as sess:
        engine.synthesize(eng, "x", VOICE, REF, 0, 1.0, ENGINE, sess)
    assert caught.value.code == "engine_refused" and caught.value.status == 400
    assert [c for c in qwentts.calls() if c == ("POST", "/v1/audio/speech")] == [("POST", "/v1/audio/speech")]


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


def test_a_failed_synthesis_is_an_http_error_and_is_not_asked_again(qwentts):
    """The pinned server maps a generation failure (status -3 and below) to 502; only a 400 after an earlier
    registration means the server forgot the voice."""
    eng = qwentts_engine(qwentts.url)
    with engine.session(eng, ENGINE) as sess:
        engine.synthesize(eng, "One.", VOICE, REF, 1, 1.0, ENGINE, sess)
        qwentts.mode = "synthesis_fails"
        with pytest.raises(EngineError) as caught:
            engine.synthesize(eng, "Two.", VOICE, REF, 2, 1.0, ENGINE, sess)
        qwentts.mode = "ok"
    assert caught.value.code == "engine_http" and caught.value.status == 502
    assert [c for c in qwentts.calls() if c == ("POST", "/v1/audio/voices")] == [("POST", "/v1/audio/voices")]


def test_a_reference_the_server_cannot_decode_is_refused_before_speech(qwentts):
    """The pinned server decodes the registration's WAV itself (PCM16, PCM24 or float32); anything else is 400."""
    with pytest.raises(EngineError) as caught:
        engine.synthesize(
            qwentts_engine(qwentts.url), "x", VOICE, {**REF, "audio": b"RIFF\x04\x00\x00\x00WAVE"}, 0, 1.0, ENGINE
        )
    assert caught.value.code == "engine_refused" and caught.value.status == 400
    assert ("POST", "/v1/audio/speech") not in qwentts.calls()


def test_a_refused_registration_never_reaches_the_speech_route(qwentts):
    qwentts.mode = "refuse_register"
    with pytest.raises(EngineError) as caught:
        engine.synthesize(qwentts_engine(qwentts.url), "x", VOICE, REF, 0, 1.0, ENGINE)
    assert caught.value.code == "engine_refused"
    assert ("POST", "/v1/audio/speech") not in qwentts.calls()


def test_an_unconfirmed_registration_is_refused_and_still_deleted(qwentts):
    qwentts.mode = "garbled_register"
    with pytest.raises(EngineError) as caught:
        engine.synthesize(qwentts_engine(qwentts.url), "x", VOICE, REF, 0, 1.0, ENGINE)
    assert caught.value.code == "engine_reply_invalid"
    assert ("POST", "/v1/audio/speech") not in qwentts.calls()
    assert qwentts.calls()[-1][0] == "DELETE" and qwentts.voices == {}


def test_a_failed_delete_is_reported_not_raised(qwentts, capsys):
    eng = qwentts_engine(qwentts.url)
    with engine.session(eng, ENGINE) as sess:
        engine.synthesize(eng, "x", VOICE, REF, 0, 1.0, ENGINE, sess)
        qwentts.mode = "refuse_delete"
    assert sess.undeleted == [sess.name(VOICE, REF)]
    assert "kept a registered voice" in capsys.readouterr().err


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
    assert [r["method"] for r in qwentts.requests if r["path"].startswith("/v1/audio/voices")] == ["POST", "DELETE"]
    assert qwentts.voices == {}
