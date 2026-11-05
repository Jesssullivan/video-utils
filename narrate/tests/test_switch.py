"""The GpuSwitch client against a loopback fake of the models switch's speech route (xoxd-ai/fuzzy
models/models_switch/tts.py and web.py at 22dd29f9, TIN-7096). The fake checks what the switch checks before it
reaches an upstream: a flat JSON object of at most 16 fields, a non-empty `input` of at most 4096 characters,
`response_format` wav, an integer `seed` (0 to 2**32 - 1 for the audio.cpp engine), no `speed` for audio.cpp,
`ref_text` only with `ref_audio`, a base64 WAV data URI of 1 to 4 MiB (413 above), 409 while the active entry is
not tts, and 429 with Retry-After while the voice-clone slots are taken. It has no /v1/audio/voices route."""

import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from narrate import audio, engine, render
from narrate.config import ENGINE, Config
from narrate.engine import EngineError

VOICE = {"id": "voice-fixture-sine"}
REF = {"audio": engine.sine("Synthetic sine fixture.", 3, 1.0, 16000), "text": "Synthetic sine fixture."}
DATA_URI = "data:audio/wav;base64,"


def flat(text):
    """The switch's structural scan: one object, no nested container, at most 16 fields (colons outside strings)."""
    quoted = escaped = False
    braces = fields = 0
    for char in text:
        if quoted:
            escaped, quoted = (False, quoted) if escaped else (char == "\\", char != '"')
            continue
        if char == '"':
            quoted = True
        elif char in "{}":
            braces += 1
        elif char in "[]":
            return False
        elif char == ":":
            fields += 1
    return braces == 2 and fields <= 16


class SwitchServer:
    def __init__(self, upstream="qwentts"):
        self.requests, self.mode, self.busy, self.upstream = [], "tts", 0, upstream
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, status, data, kind, headers=()):
                self.send_response(status)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(data)))
                for name, value in headers:
                    self.send_header(name, value)
                self.end_headers()
                self.wfile.write(data)

            def error(self, status, message, headers=()):
                body = json.dumps({"error": {"message": message, "type": "invalid_request_error"}}).encode()
                self.reply(status, body, "application/json", headers)

            def do_DELETE(self):
                outer.requests.append({"method": "DELETE", "path": self.path})
                self.error(404, "no route")

            def do_POST(self):
                text = self.rfile.read(int(self.headers["Content-Length"])).decode()
                outer.requests.append({"method": "POST", "path": self.path, "text": text})
                if self.path != "/v1/audio/speech":
                    return self.error(404, "no route")
                if outer.mode == "llm":
                    return self.error(409, "the active entry is not a tts entry")
                if outer.busy:
                    outer.busy -= 1
                    return self.error(429, "voice clone slots are busy", [("Retry-After", "5")])
                if not flat(text):
                    return self.error(400, "speech body must be a flat JSON object of at most 16 fields")
                body = json.loads(text)
                outer.requests[-1]["body"] = body
                if not isinstance(body.get("input"), str) or not body["input"].strip() or len(body["input"]) > 4096:
                    return self.error(400, "input must be a non-empty string")
                if body.get("response_format", "wav") != "wav":
                    return self.error(400, "response_format must be one of ['wav']")
                low, high = (0, 2**32 - 1) if outer.upstream == "audiocpp" else (-(2**63), 2**63 - 1)
                if "seed" in body and (type(body["seed"]) is not int or not low <= body["seed"] <= high):
                    return self.error(400, "seed is out of range")
                if outer.upstream == "audiocpp" and ("speed" in body or "instructions" in body):
                    return self.error(400, "speed is not supported by this model's engine (audiocpp)")
                ref_audio, ref_text = body.get("ref_audio"), body.get("ref_text")
                if ref_audio is None and ref_text is not None:
                    return self.error(400, "ref_text needs ref_audio")
                if ref_audio is not None:
                    if not isinstance(ref_audio, str) or not ref_audio.startswith(DATA_URI):
                        return self.error(400, "ref_audio must be a base64 WAV data URI")
                    clip = base64.b64decode(ref_audio[len(DATA_URI) :], validate=True)
                    if len(clip) > 4 * 1024 * 1024:
                        return self.error(413, "ref_audio is too large")
                    if outer.mode == "refuse_clip":
                        return self.error(413, "ref_audio is too large")
                self.reply(200, engine.sine(body["input"], body.get("seed", 0), 1.0, 24000), "audio/wav")

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.httpd.server_port}"

    def calls(self):
        return [(r["method"], r["path"]) for r in self.requests]

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def switch():
    s = SwitchServer()
    yield s
    s.close()


@pytest.fixture
def waits(monkeypatch):
    slept = []
    monkeypatch.setattr(engine, "SLEEP", slept.append)
    return slept


def switch_engine(url, backend="QwenTtsCpp"):
    return {
        "id": "switch-probe",
        "backend": backend,
        "profile": "GpuSwitch",
        "endpoint": url,
        "model": "tts-entry-fixture",
        "sampleRateHz": 24000,
    }


def test_a_switch_take_sends_the_reference_by_content_on_the_speech_route_alone(switch):
    data, facts = engine.synthesize(switch_engine(switch.url), "Read this.", VOICE, REF, 7, 1.2, ENGINE)
    assert switch.calls() == [("POST", "/v1/audio/speech")]
    assert switch.requests[0]["body"] == {
        "model": "tts-entry-fixture",
        "input": "Read this.",
        "response_format": "wav",
        "seed": 7,
        "ref_audio": DATA_URI + base64.b64encode(REF["audio"]).decode(),
        "ref_text": REF["text"],
    }
    assert facts == {
        "variant": "switch",
        "speed_honoured": False,
        "ref_audio_used": True,
        "ref_text_used": True,
        "conditioning": "reference_and_transcript",
        "voice_kept_by_switch": True,
        "attempts": 1,
    }
    assert audio.parse(data).rate == 24000


def test_a_qwentts_backend_behind_the_switch_never_opens_a_voice_registry(switch):
    """The switch registers the clip upstream itself; a render's session holds nothing and deletes nothing."""
    eng = switch_engine(switch.url)
    with engine.session(eng, ENGINE) as sess:
        engine.synthesize(eng, "One.", VOICE, REF, 1, 1.0, ENGINE, sess)
        engine.synthesize(eng, "Two.", VOICE, REF, 2, 1.0, ENGINE, sess)
    assert switch.calls() == [("POST", "/v1/audio/speech")] * 2
    assert sess.names == {} and sess.undeleted == []


def test_omit_sends_no_reference_and_names_no_voice(switch):
    _, facts = engine.synthesize(switch_engine(switch.url), "x", VOICE, REF, 0, 1.0, ENGINE | {"ref_audio": "omit"})
    body = switch.requests[0]["body"]
    assert not {"voice", "ref_audio", "ref_text", "speed"} & set(body)
    assert facts["conditioning"] == "none" and facts["ref_audio_used"] is False
    assert "voice_kept_by_switch" not in facts


def test_a_blank_transcript_sends_the_clip_alone(switch):
    _, facts = engine.synthesize(switch_engine(switch.url), "x", VOICE, {**REF, "text": "  "}, 0, 1.0, ENGINE)
    assert "ref_text" not in switch.requests[0]["body"]
    assert facts["conditioning"] == "reference" and facts["ref_text_used"] is False


def test_the_audiocpp_engine_takes_the_take_without_speed_and_with_a_32_bit_seed():
    s = SwitchServer("audiocpp")
    try:
        eng = switch_engine(s.url, "VulkanAudioCpp")
        engine.synthesize(eng, "x", VOICE, REF, 2**32 - 1, 1.3, ENGINE)
        assert "speed" not in s.requests[0]["body"]
        with pytest.raises(EngineError, match="engine_seed_range"):
            engine.synthesize(eng, "x", VOICE, REF, 2**32, 1.0, ENGINE)
        assert len(s.requests) == 1
    finally:
        s.close()


@pytest.mark.parametrize(
    ("text", "ref", "code"),
    [
        ("", REF, "engine_input_invalid"),
        ("x" * 4097, REF, "engine_input_invalid"),
        ("x", {**REF, "audio": b""}, "engine_ref_too_large"),
        ("x", {**REF, "audio": b"\0" * (4 * 1024 * 1024 + 1)}, "engine_ref_too_large"),
        ("x", {**REF, "text": "t" * 2001}, "engine_ref_text_too_long"),
    ],
)
def test_what_the_switch_would_refuse_is_refused_before_any_upload(switch, text, ref, code):
    with pytest.raises(EngineError) as caught:
        engine.synthesize(switch_engine(switch.url), text, VOICE, ref, 0, 1.0, ENGINE)
    assert caught.value.code == code
    assert switch.requests == []


def test_the_bounds_at_the_edge_are_taken(switch):
    ref = {"audio": b"\0" * (4 * 1024 * 1024), "text": "t" * 2000}
    engine.synthesize(switch_engine(switch.url), "x" * 4096, VOICE, ref, 0, 1.0, ENGINE)
    assert switch.requests[0]["body"]["input"] == "x" * 4096


def test_a_switch_on_a_text_entry_is_a_typed_refusal(switch, waits):
    switch.mode = "llm"
    with pytest.raises(EngineError) as caught:
        engine.synthesize(switch_engine(switch.url), "x", VOICE, REF, 0, 1.0, ENGINE)
    assert caught.value.code == "engine_switch_not_tts" and caught.value.status == 409
    assert "switch to one first" in str(caught.value)
    assert len(switch.requests) == 1 and waits == []


def test_a_clip_the_switch_will_not_take_is_engine_ref_too_large(switch):
    switch.mode = "refuse_clip"
    with pytest.raises(EngineError) as caught:
        engine.synthesize(switch_engine(switch.url), "x", VOICE, REF, 0, 1.0, ENGINE)
    assert caught.value.code == "engine_ref_too_large" and caught.value.status == 413


def test_busy_clone_slots_are_asked_again_after_retry_after(switch, waits):
    switch.busy = 2
    _, facts = engine.synthesize(switch_engine(switch.url), "x", VOICE, REF, 0, 1.0, ENGINE)
    assert facts["attempts"] == 3 and waits == [5.0, 5.0]
    assert len(switch.requests) == 3


def test_busy_slots_past_the_attempts_are_engine_busy(switch, waits):
    switch.busy = engine.SWITCH_ATTEMPTS
    with pytest.raises(EngineError) as caught:
        engine.synthesize(switch_engine(switch.url), "x", VOICE, REF, 0, 1.0, ENGINE)
    assert caught.value.code == "engine_busy" and caught.value.status == 429
    assert len(switch.requests) == engine.SWITCH_ATTEMPTS and len(waits) == engine.SWITCH_ATTEMPTS - 1


@pytest.mark.parametrize(("value", "seconds"), [("5", 5.0), ("0.5", 0.5), ("-1", None), ("nan", None), (None, None)])
def test_retry_after_reads_delta_seconds_only(value, seconds):
    assert engine.retry_after_s({} if value is None else {"Retry-After": value}) == seconds
    assert engine.retry_after_s({"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}) is None


def test_a_long_retry_after_is_capped(switch, monkeypatch, waits):
    monkeypatch.setattr(engine, "retry_after_s", lambda headers: 3600.0)
    switch.busy = 1
    engine.synthesize(switch_engine(switch.url), "x", VOICE, REF, 0, 1.0, ENGINE)
    assert waits == [engine.SWITCH_MAX_WAIT_S]


def test_other_failures_keep_their_codes_and_are_not_asked_again(switch):
    with pytest.raises(EngineError) as caught:
        engine.synthesize(switch_engine(switch.url + "/elsewhere"), "x", VOICE, REF, 0, 1.0, ENGINE)
    assert caught.value.code == "engine_http" and caught.value.status == 404
    assert len(switch.requests) == 1


def test_the_switch_never_honours_speed_whatever_the_backend():
    for backend in ("QwenTtsCpp", "VulkanAudioCpp", "LlamaTts"):
        assert engine.honours_speed({"backend": backend, "profile": "GpuSwitch"}) is False
    assert engine.honours_speed({"backend": "VulkanAudioCpp", "profile": "GpuDirect"}) is True


SRT_LONG = """1
00:00:00,000 --> 00:00:02,000
This cue carries far more words than two seconds can hold, so the fit has work to do here.
"""


def test_render_on_the_switch_fits_with_atempo_alone(workspace, switch):
    workspace.job["captions"] = ["Srt"]
    workspace.engines = [{**workspace.engines[0], **switch_engine(switch.url), "id": "fake-sine"}]
    final, manifest = render.render(Config(workspace.write(SRT_LONG, "Srt")))
    (segment,) = json.loads((final / "narration.edl.json").read_text())["segments"]
    assert segment["speed"] == 1.0 and segment["atempo"] == pytest.approx(1.08)
    assert switch.calls() == [("POST", "/v1/audio/speech")]
    assert "speed" not in switch.requests[0]["body"]
