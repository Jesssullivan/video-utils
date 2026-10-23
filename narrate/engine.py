"""Engine clients: the OpenAI-compatible speech route and the offline fake engine.

http(s) engines get one `POST /v1/audio/speech` per chunk:
  {model, input, voice, response_format: "wav", speed, seed, ref_audio, ref_text}
ref_audio is the reference clip sent by content (a base64 data URI of the stored WAV, found by its digest) and
ref_text its verified transcript. The bearer token, when an engine needs one, comes only from
NARRATE_ENGINE_TOKEN. Plain http is allowed only to a loopback host (condense.transcribe.loopback) unless no token
is sent; Hosted and RentedOpen engines always need https. No proxy sees a request and no redirect is followed.
Every failure raises EngineError with a typed code; nothing is retried here (qa.py owns retries). The endpoint is
never recorded: real endpoints are private and live outside git.

QwenTtsCpp engines (qwentts.cpp tts-server, narrate/serve/qwentts.sh) take no ref_audio on the speech route:
the server clones from a voice registered once by name. The client registers the reference clip and its verified
transcript with `POST /v1/audio/voices {name, ref_text, wav_b64}` under a name derived from the voice id and the
digest of the clip and transcript, re-registers when `GET /v1/audio/voices` no longer lists it (a restarted server
forgets its registry), then asks `POST /v1/audio/speech {model, input, voice: <name>, response_format: "wav",
seed}`. The server parses `speed` and ignores it, so the client sends none and records `speed_honoured: false`;
render.py then fits timing with atempo alone. With `[engine] ref_audio = "omit"` nothing is registered and the
request names no voice, which this runtime answers with its unconditioned default voice.

fake engines (backend Fake) need no weights, GPU or network:
  fake://sine    a deterministic tone per chunk: its pitch follows the seed and the text, its length the text
                 length over the speed, with a syllable-rate envelope;
  fake://espeak  espeak-ng when it is on PATH (its version is recorded), else the sine with the fallback
                 recorded.
"""

import array
import base64
import hashlib
import http.client
import io
import json
import math
import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import wave

from .config import run

TOKEN_ENV = "NARRATE_ENGINE_TOKEN"
FAKE_RATE_HZ = 24000
SECONDS_PER_CODEPOINT = 0.065


class EngineError(RuntimeError):
    def __init__(self, code, detail):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect)


def wav_bytes(samples, rate):
    """A mono 16-bit PCM WAV of int samples."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        values = array.array("h", samples)
        if sys.byteorder != "little":
            values.byteswap()
        out.writeframes(values.tobytes())
    return buffer.getvalue()


def sine(text, seed, speed, rate):
    """The fake engine's take: deterministic for (text, seed, speed, rate)."""
    digest = hashlib.sha256(f"{seed}\0{text}".encode()).digest()
    pitch = 140 + int.from_bytes(digest[:2], "big") % 160  # Hz
    seconds = max(0.4, SECONDS_PER_CODEPOINT * len(text)) / speed
    count = round(seconds * rate)
    step, syllable = 2 * math.pi * pitch / rate, math.pi * 4.0 / rate  # four syllables a second
    fade = max(1, round(0.01 * rate))
    samples = []
    for n in range(count):
        envelope = 0.25 + 0.75 * abs(math.sin(syllable * n))
        edge = min(1.0, n / fade, (count - 1 - n) / fade)
        samples.append(round(9000 * envelope * edge * math.sin(step * n)))
    return wav_bytes(samples, rate)


def espeak(text, speed):
    binary = shutil.which("espeak-ng")
    if not binary:
        return None, None
    version = run(binary, "--version").stdout.strip()
    with tempfile.TemporaryDirectory() as work:
        out = os.path.join(work, "take.wav")
        run(binary, "-v", "en", "-s", str(round(175 * speed)), "-w", out, "--stdin", input=text)
        with open(out, "rb") as f:
            return f.read(), version


def fake(engine, text, seed, speed):
    rate = engine.get("sampleRateHz") or FAKE_RATE_HZ
    variant = urllib.parse.urlsplit(engine["endpoint"]).netloc or "sine"
    if variant not in ("sine", "espeak"):
        raise EngineError("engine_endpoint_invalid", f"fake engine {engine['id']}: fake://sine or fake://espeak")
    if variant == "espeak":
        data, version = espeak(text, speed)
        if data is not None:
            return data, {
                "variant": "espeak-ng",
                "espeak_version": version,
                "ref_audio_used": False,
                "ref_text_used": False,
            }
        return sine(text, seed, speed, rate), {
            "variant": "sine",
            "fallback": "espeak-ng is not on PATH",
            "ref_audio_used": False,
            "ref_text_used": False,
        }
    return sine(text, seed, speed, rate), {"variant": "sine", "ref_audio_used": False, "ref_text_used": False}


def bearer():
    token = os.environ.get(TOKEN_ENV)
    if not token:
        return None
    if not all(0x21 <= ord(c) <= 0x7E for c in token):
        raise EngineError("engine_token_invalid", f"{TOKEN_ENV} must be visible ASCII without spaces")
    return f"Bearer {token}"


REMOTE_PROFILES = ("Hosted", "RentedOpen")


def transport_ok(engine, endpoint, with_token):
    """Raise engine_transport_insecure when a request would cross a network in cleartext with a credential, or
    reach a hosted or rented engine over http at all."""
    from condense.transcribe import loopback

    p = urllib.parse.urlsplit(endpoint)
    if p.scheme == "https":
        return
    remote = engine.get("profile") in REMOTE_PROFILES or bool(engine.get("hosted"))
    if remote:
        raise EngineError(
            "engine_transport_insecure", f"engine {engine['id']}: a {engine['profile']} engine needs https"
        )
    if with_token and not loopback(p.hostname):
        raise EngineError(
            "engine_transport_insecure",
            f"engine {engine['id']}: {TOKEN_ENV} goes over https unless the host is loopback",
        )


def speech_url(endpoint):
    return route(endpoint, "/v1/audio/speech")


def base_url(endpoint):
    p = urllib.parse.urlsplit(endpoint)
    if p.scheme not in ("http", "https") or not p.hostname or "@" in p.netloc or p.fragment:
        raise EngineError("engine_endpoint_invalid", "an http(s) endpoint without user info or fragment")
    path = p.path.rstrip("/")
    if path.endswith("/v1/audio/speech"):
        path = path[: -len("/v1/audio/speech")]
    return urllib.parse.urlunsplit((p.scheme, p.netloc, path, p.query, ""))


def route(endpoint, suffix):
    p = urllib.parse.urlsplit(base_url(endpoint))
    return urllib.parse.urlunsplit((p.scheme, p.netloc, p.path + suffix, p.query, ""))


def call(engine, url, body, options, accept):
    """(bytes, reply headers) of one request to the engine, POST when body is not None, else GET; the token,
    transport and failure rules of every engine route."""
    request = urllib.request.Request(
        url,
        data=None if body is None else json.dumps(body).encode("utf-8"),
        headers={"Accept": accept, **({} if body is None else {"Content-Type": "application/json"})},
        method="GET" if body is None else "POST",
    )
    token = bearer()
    transport_ok(engine, engine["endpoint"], token is not None)
    if token:
        request.add_header("Authorization", token)
    limit, timeout = int(options["max_reply_bytes"]), float(options["timeout_s"])
    try:
        with OPENER.open(request, timeout=timeout) as reply:
            if reply.status != 200:
                raise EngineError("engine_http", f"engine {engine['id']} answered HTTP {reply.status}")
            data = reply.read(limit + 1)
            headers = reply.headers
    except urllib.error.HTTPError as error:
        error.close()
        code = "engine_refused" if error.code in (400, 401, 403, 409, 422, 451) else "engine_http"
        raise EngineError(code, f"engine {engine['id']} answered HTTP {error.code}") from None
    except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError) as error:
        reason = getattr(error, "reason", error)
        timed_out = isinstance(reason, TimeoutError) or isinstance(error, TimeoutError)
        code = "engine_timeout" if timed_out else "engine_unreachable"
        raise EngineError(
            code, f"engine {engine['id']}: {type(reason).__name__} (wait bounded by {timeout:g} s)"
        ) from None
    if len(data) > limit:
        raise EngineError("engine_reply_invalid", f"engine {engine['id']} sent more than {limit} bytes")
    return data, headers


def wav_reply(engine, data):
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise EngineError("engine_reply_invalid", f"engine {engine['id']} did not answer a WAV")
    return data


def speech(engine, text, voice, ref, seed, speed, options):
    body = {
        "model": engine["model"],
        "input": text,
        "voice": voice["id"],
        "response_format": "wav",
        "speed": round(speed, 4),
        "seed": seed,
    }
    if options["ref_audio"] == "data_uri":
        body["ref_audio"] = "data:audio/wav;base64," + base64.b64encode(ref["audio"]).decode("ascii")
        body["ref_text"] = ref["text"]
    data, headers = call(engine, speech_url(engine["endpoint"]), body, options, "audio/wav")
    used = headers.get("X-Ref-Text-Used")
    record = {
        "variant": "http",
        "ref_audio_used": "unknown" if body.get("ref_audio") else False,
        "ref_text_used": {"true": True, "false": False}.get(str(used).lower(), "unknown")
        if body.get("ref_text")
        else False,
    }
    return wav_reply(engine, data), record


QWENTTS = "QwenTtsCpp"


def qwentts_voice_name(voice, ref):
    """The registry name of a voice's reference: its id and a digest of clip and transcript, so a changed clip or
    transcript registers under a new name and never reuses stale latents. qwentts.cpp lowercases names."""
    digest = hashlib.sha256(hashlib.sha256(ref["audio"]).digest() + ref["text"].encode("utf-8")).hexdigest()
    return f"narrate-{voice['id']}-{digest[:16]}".lower()


def qwentts_registered(engine, options):
    data, _ = call(engine, route(engine["endpoint"], "/v1/audio/voices"), None, options, "application/json")
    try:
        listed = json.loads(data)["voices"]
        return {v["name"] for v in listed if isinstance(v, dict) and v.get("kind") == "registered"}
    except (ValueError, KeyError, TypeError):
        raise EngineError("engine_reply_invalid", f"engine {engine['id']} sent an unreadable voice list") from None


def qwentts_register(engine, name, ref, options):
    """Register the reference unless the server already lists the name; True when this call registered it."""
    if name in qwentts_registered(engine, options):
        return False
    body = {"name": name, "ref_text": ref["text"], "wav_b64": base64.b64encode(ref["audio"]).decode("ascii")}
    data, _ = call(engine, route(engine["endpoint"], "/v1/audio/voices"), body, options, "application/json")
    try:
        status = json.loads(data).get("status")
    except (ValueError, AttributeError):
        status = None
    if status != "registered":
        raise EngineError("engine_reply_invalid", f"engine {engine['id']} did not confirm the voice registration")
    return True


def qwentts_speech(engine, text, voice, ref, seed, options):
    body = {"model": engine["model"], "input": text, "response_format": "wav", "seed": seed}
    record = {"variant": "qwentts_registered_voice", "speed_honoured": False}
    if options["ref_audio"] == "data_uri":
        name = qwentts_voice_name(voice, ref)
        registered_now = qwentts_register(engine, name, ref, options)
        body["voice"] = name
        # qwentts.cpp (pinned 5916bf7) synthesises a registered voice from its speaker embedding, and in ICL mode
        # from the reference codes and transcript whenever the registration carried a ref_text.
        record.update(
            {
                "ref_audio_used": True,
                "ref_text_used": bool(ref["text"]),
                "conditioning": "icl" if ref["text"] else "x_vector",
                "registered_now": registered_now,
            }
        )
    else:
        record.update({"ref_audio_used": False, "ref_text_used": False, "conditioning": "none"})
    data, _ = call(engine, speech_url(engine["endpoint"]), body, options, "audio/wav")
    return wav_reply(engine, data), record


def honours_speed(engine):
    """False for a runtime that ignores the speed knob; render.py then fits timing with atempo alone."""
    return engine["backend"] != QWENTTS


def synthesize(engine, text, voice, ref, seed, speed, options):
    """(WAV bytes, facts about the take) for one chunk."""
    if engine["backend"] == "Fake":
        if not engine["endpoint"].startswith("fake://"):
            raise EngineError("engine_endpoint_invalid", f"fake engine {engine['id']} needs a fake:// endpoint")
        return fake(engine, text, seed, speed)
    if engine["endpoint"].startswith("fake://"):
        raise EngineError("engine_endpoint_invalid", f"engine {engine['id']} is not Fake but has a fake:// endpoint")
    if engine["backend"] == QWENTTS:
        return qwentts_speech(engine, text, voice, ref, seed, options)
    return speech(engine, text, voice, ref, seed, speed, options)


def probe(engine):
    """Availability without synthesis: fake engines are always available; http engines are not probed."""
    if engine["backend"] == "Fake":
        variant = urllib.parse.urlsplit(engine["endpoint"]).netloc
        espeak_found = shutil.which("espeak-ng") is not None
        return {"available": True, "variant": "espeak-ng" if variant == "espeak" and espeak_found else "sine"}
    return {"available": "not_probed", "reason": "http engines are reached only by a render"}
