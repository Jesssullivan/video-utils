"""The fake engine's determinism, and the /v1/audio/speech client against a loopback test server: the request it
sends, and every refusal path (HTTP refusal, a reply that is not WAV, timeout, redirect)."""

import base64
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from narrate import audio, engine
from narrate.config import ENGINE
from narrate.engine import EngineError

FAKE = {
    "id": "fake-sine",
    "backend": "Fake",
    "profile": "Fake",
    "endpoint": "fake://sine",
    "sampleRateHz": 24000,
    "model": "fake-sine-v1",
}
VOICE = {"id": "voice-fixture-sine"}
REF = {"audio": b"RIFF....WAVEfixture", "text": "Synthetic sine fixture."}


def test_fake_sine_is_deterministic_and_follows_text_seed_and_speed():
    a, facts = engine.synthesize(FAKE, "Hello there.", VOICE, REF, 0, 1.0, ENGINE)
    b, _ = engine.synthesize(FAKE, "Hello there.", VOICE, REF, 0, 1.0, ENGINE)
    c, _ = engine.synthesize(FAKE, "Hello there.", VOICE, REF, 1, 1.0, ENGINE)
    fast, _ = engine.synthesize(FAKE, "Hello there.", VOICE, REF, 0, 1.25, ENGINE)
    assert a == b and a != c
    assert facts["variant"] == "sine" and facts["ref_text_used"] is False
    pa, pf = audio.parse(a), audio.parse(fast)
    assert pa.rate == 24000 and pa.seconds == pytest.approx(max(0.4, 0.065 * 12), abs=1e-3)
    assert pf.seconds == pytest.approx(pa.seconds / 1.25, abs=1e-3)


def test_fake_espeak_falls_back_to_the_sine_without_espeak(monkeypatch):
    monkeypatch.setattr(engine.shutil, "which", lambda name: None)
    data, facts = engine.synthesize({**FAKE, "endpoint": "fake://espeak"}, "Hi.", VOICE, REF, 0, 1.0, ENGINE)
    assert facts == {
        "variant": "sine",
        "fallback": "espeak-ng is not on PATH",
        "ref_audio_used": False,
        "ref_text_used": False,
    }
    assert audio.parse(data).rate == 24000


def test_endpoint_and_backend_must_agree():
    with pytest.raises(EngineError, match="engine_endpoint_invalid"):
        engine.synthesize({**FAKE, "endpoint": "http://127.0.0.1:9"}, "x", VOICE, REF, 0, 1.0, ENGINE)
    with pytest.raises(EngineError, match="engine_endpoint_invalid"):
        engine.synthesize({**FAKE, "backend": "MlxAudio"}, "x", VOICE, REF, 0, 1.0, ENGINE)
    with pytest.raises(EngineError, match="engine_endpoint_invalid"):
        engine.synthesize({**FAKE, "endpoint": "fake://other"}, "x", VOICE, REF, 0, 1.0, ENGINE)


class Server:
    """A loopback speech server whose behaviour each test sets."""

    def __init__(self):
        self.requests, self.mode = [], "ok"
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.requests.append({"path": self.path, "body": body, "auth": self.headers.get("Authorization")})
                if outer.mode == "slow":
                    time.sleep(2)
                if outer.mode == "redirect":
                    self.send_response(307)
                    self.send_header("Location", "http://127.0.0.1:9/elsewhere")
                    self.end_headers()
                    return
                if outer.mode == "refuse":
                    self.send_response(422)
                    self.end_headers()
                    return
                data = b"not audio" if outer.mode == "text" else engine.sine(body["input"], body["seed"], 1.0, 22050)
                self.send_response(200)
                self.send_header("Content-Type", "audio/wav")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("X-Ref-Text-Used", "true")
                self.end_headers()
                self.wfile.write(data)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.httpd.server_port}"

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def server():
    s = Server()
    yield s
    s.close()


def http_engine(url):
    return {
        "id": "mlx-probe",
        "backend": "MlxAudio",
        "profile": "MacMlx",
        "endpoint": url,
        "model": "probe-model",
        "sampleRateHz": None,
    }


def test_speech_request_carries_ref_audio_ref_text_seed_and_speed(server, monkeypatch):
    monkeypatch.setenv(engine.TOKEN_ENV, "fixture-token")
    data, facts = engine.synthesize(http_engine(server.url), "Read this.", VOICE, REF, 7, 1.1, ENGINE)
    (request,) = server.requests
    assert request["path"] == "/v1/audio/speech"
    body = request["body"]
    assert {k: body[k] for k in ("model", "input", "voice", "response_format", "speed", "seed")} == {
        "model": "probe-model",
        "input": "Read this.",
        "voice": "voice-fixture-sine",
        "response_format": "wav",
        "speed": 1.1,
        "seed": 7,
    }
    assert base64.b64decode(body["ref_audio"].split(",", 1)[1]) == REF["audio"]
    assert body["ref_text"] == REF["text"]
    assert request["auth"] == "Bearer fixture-token"
    assert facts["ref_text_used"] is True and audio.parse(data).rate == 22050


def test_ref_fields_can_be_omitted(server, monkeypatch):
    monkeypatch.delenv(engine.TOKEN_ENV, raising=False)
    engine.synthesize(
        http_engine(server.url + "/v1/audio/speech"), "x", VOICE, REF, 0, 1.0, ENGINE | {"ref_audio": "omit"}
    )
    (request,) = server.requests
    assert "ref_audio" not in request["body"] and "ref_text" not in request["body"] and request["auth"] is None


@pytest.mark.parametrize(
    "mode,code", [("refuse", "engine_refused"), ("text", "engine_reply_invalid"), ("redirect", "engine_http")]
)
def test_refusal_paths(server, mode, code):
    server.mode = mode
    with pytest.raises(EngineError) as caught:
        engine.synthesize(http_engine(server.url), "x", VOICE, REF, 0, 1.0, ENGINE)
    assert caught.value.code == code
    assert len(server.requests) == 1  # never retried here, never followed


def test_timeout(server):
    server.mode = "slow"
    with pytest.raises(EngineError) as caught:
        engine.synthesize(http_engine(server.url), "x", VOICE, REF, 0, 1.0, ENGINE | {"timeout_s": 0.3})
    assert caught.value.code == "engine_timeout"


def test_unreachable_and_bad_endpoints():
    with pytest.raises(EngineError, match="engine_unreachable"):
        engine.synthesize(http_engine("http://127.0.0.1:9"), "x", VOICE, REF, 0, 1.0, ENGINE | {"timeout_s": 2})
    for bad in ("ftp://host/x", "http://user@127.0.0.1/", "http://127.0.0.1/#frag"):
        with pytest.raises(EngineError, match="engine_endpoint_invalid"):
            engine.synthesize(http_engine(bad), "x", VOICE, REF, 0, 1.0, ENGINE)


def test_token_must_be_visible_ascii(server, monkeypatch):
    monkeypatch.setenv(engine.TOKEN_ENV, "two words\n")
    with pytest.raises(EngineError, match="engine_token_invalid"):
        engine.synthesize(http_engine(server.url), "x", VOICE, REF, 0, 1.0, ENGINE)
