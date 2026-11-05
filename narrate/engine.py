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
the server clones from a voice registered by name. A render opens one `session`: the first take of each voice
registers the reference clip and its verified transcript with `POST /v1/audio/voices {name, ref_text, wav_b64}`
under a name made of the voice id, a digest of clip and transcript and a random per-session nonce, and the
session's end deletes every name it registered (`DELETE /v1/audio/voices/{name}`), whether the render succeeded
or not. The client never trusts the server's voice list: it registers what it speaks with, so an entry another
client put there under a guessable name is never used. Each take asks `POST /v1/audio/speech {model, input,
voice: <name>, response_format: "wav", seed}`; a 400 there after an earlier registration (a restarted server
forgets its registry) registers the voice again and asks once more. The server parses `speed` and ignores it, so
the client sends none and records `speed_honoured: false`; render.py then fits timing with atempo alone. With
`[engine] ref_audio = "omit"` nothing is registered and the request names no voice, which this runtime answers
with its unconditioned default voice. synthesize() without a session registers, speaks and deletes in one call.

AudioCppBatch engines run out of process (narrate/prerender.py): narrate never calls them. synthesize() refuses
them with engine_out_of_process; a render takes their takes from a prerendered batch instead.

GpuSwitch engines reach the models switch's own `POST /v1/audio/speech` (xoxd-ai/fuzzy models_switch/tts.py,
TIN-7096), whatever runtime the switch's active tts entry runs. The switch takes the reference by content
(ref_audio, a base64 WAV data URI, with ref_text), registers it upstream under a content-addressed name and speaks
with that name, so the client never calls /v1/audio/voices there. Its flat contract bounds what is sent: input
up to 4096 characters, ref_text up to 2000, a decoded clip of 1 to 4 MiB, an integer seed (0 to 2**32 - 1 for
the audio.cpp engine) and no `speed` (audio.cpp refuses it, qwentts.cpp ignores it), so speed_honoured is false
and render.py fits timing with atempo alone. A request outside those bounds is refused here, before any upload.
The switch answers 409 while its active entry is not a tts entry (engine_switch_not_tts: the operator switches
first), 413 for a clip it will not decode (engine_ref_too_large) and 429 with Retry-After while its voice-clone
slots are taken; a 429 is asked again after the wait, at most SWITCH_ATTEMPTS times in all. The switch keeps a
registered voice until its upstream restarts and has no delete route: the take records that.

fake engines (backend Fake) need no weights, GPU or network:
  fake://sine    a deterministic tone per chunk: its pitch follows the seed and the text, its length the text
                 length over the speed, with a syllable-rate envelope;
  fake://espeak  espeak-ng when it is on PATH (its version is recorded), else the sine with the fallback
                 recorded.
"""

import array
import base64
import contextlib
import hashlib
import http.client
import io
import json
import math
import os
import secrets
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import wave

from .config import run

TOKEN_ENV = "NARRATE_ENGINE_TOKEN"
FAKE_RATE_HZ = 24000
SECONDS_PER_CODEPOINT = 0.065


class EngineError(RuntimeError):
    def __init__(self, code, detail, status=None, retry_after=None):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail, self.status, self.retry_after = code, detail, status, retry_after


def retry_after_s(headers):
    """A Retry-After of delta seconds as a float, else None (an HTTP date is not followed)."""
    value = headers.get("Retry-After") if headers is not None else None
    try:
        seconds = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return seconds if math.isfinite(seconds) and seconds >= 0 else None


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


def call(engine, url, body, options, accept, method=None):
    """(bytes, reply headers) of one request to the engine, POST when body is not None, else GET unless method
    says otherwise; the token, transport and failure rules of every engine route."""
    request = urllib.request.Request(
        url,
        data=None if body is None else json.dumps(body).encode("utf-8"),
        headers={"Accept": accept, **({} if body is None else {"Content-Type": "application/json"})},
        method=method or ("GET" if body is None else "POST"),
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
        wait = retry_after_s(error.headers)
        error.close()
        code = "engine_refused" if error.code in (400, 401, 403, 409, 422, 451) else "engine_http"
        raise EngineError(code, f"engine {engine['id']} answered HTTP {error.code}", error.code, wait) from None
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
    """The registry name stem of a voice's reference: its id and a digest of clip and transcript, so a changed clip
    or transcript registers under a new name and never reuses stale latents. qwentts.cpp lowercases names."""
    digest = hashlib.sha256(hashlib.sha256(ref["audio"]).digest() + ref["text"].encode("utf-8")).hexdigest()
    return f"narrate-{voice['id']}-{digest[:16]}".lower()


class Session:
    """The voices one render registered on a QwenTtsCpp server. Names carry a random nonce, so no other client
    can guess them, and close() deletes them all. For every other backend a session holds nothing."""

    def __init__(self, engine, options):
        self.engine, self.options = engine, options
        self.nonce = secrets.token_hex(8)
        self.names = {}  # stem -> registered name
        self.undeleted = []

    def name(self, voice, ref):
        return f"{qwentts_voice_name(voice, ref)}-{self.nonce}"

    def register(self, voice, ref):
        name = self.name(voice, ref)
        body = {"name": name, "ref_text": ref["text"], "wav_b64": base64.b64encode(ref["audio"]).decode("ascii")}
        url = route(self.engine["endpoint"], "/v1/audio/voices")
        self.names[qwentts_voice_name(voice, ref)] = name  # deleted at close even when the reply is unreadable
        data, _ = call(self.engine, url, body, self.options, "application/json")
        try:
            reply = json.loads(data)
        except ValueError:
            reply = None
        if not isinstance(reply, dict) or reply.get("status") != "registered" or reply.get("name") != name:
            raise EngineError(
                "engine_reply_invalid", f"engine {self.engine['id']} did not confirm the voice registration"
            )
        return name

    def registered(self, voice, ref):
        return self.names.get(qwentts_voice_name(voice, ref))

    def close(self):
        """Delete every name this session registered; a name the server no longer has is already gone."""
        for name in list(self.names.values()):
            url = route(self.engine["endpoint"], "/v1/audio/voices/" + urllib.parse.quote(name, safe=""))
            try:
                call(self.engine, url, None, self.options, "application/json", method="DELETE")
            except EngineError as error:
                if error.status != 404:
                    self.undeleted.append(name)
                    print(
                        f"narrate: engine {self.engine['id']} kept a registered voice ({error.code}); "
                        "restart the server to drop it",
                        file=sys.stderr,
                    )
        self.names.clear()


@contextlib.contextmanager
def session(engine, options):
    """A Session closed on every exit, the render's error paths included."""
    s = Session(engine, options)
    try:
        yield s
    finally:
        s.close()


def qwentts_speech(engine, text, voice, ref, seed, options, sess):
    if sess is None:
        with session(engine, options) as one:
            return qwentts_speech(engine, text, voice, ref, seed, options, one)
    body = {"model": engine["model"], "input": text, "response_format": "wav", "seed": seed}
    record = {"variant": "qwentts_registered_voice", "speed_honoured": False}
    if options["ref_audio"] != "data_uri":
        record.update({"ref_audio_used": False, "ref_text_used": False, "conditioning": "none"})
        data, _ = call(engine, speech_url(engine["endpoint"]), body, options, "audio/wav")
        return wav_reply(engine, data), record
    name = sess.registered(voice, ref)
    registered_now = name is None
    if registered_now:
        name = sess.register(voice, ref)
    try:
        data, _ = call(engine, speech_url(engine["endpoint"]), body | {"voice": name}, options, "audio/wav")
    except EngineError as error:
        if registered_now or error.status != 400:
            raise
        # The name was registered earlier in this session and is now unknown: the server restarted.
        name, registered_now = sess.register(voice, ref), True
        data, _ = call(engine, speech_url(engine["endpoint"]), body | {"voice": name}, options, "audio/wav")
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
    return wav_reply(engine, data), record


AUDIOCPP_BATCH = "AudioCppBatch"


SWITCH = "GpuSwitch"
SWITCH_MAX_INPUT_CHARS = 4096
SWITCH_MAX_REF_TEXT_CHARS = 2000
SWITCH_MAX_REF_AUDIO_BYTES = 4 * 1024 * 1024
SWITCH_SEED_RANGE = {"VulkanAudioCpp": (0, 2**32 - 1)}
SWITCH_ANY_SEED = (-(2**63), 2**63 - 1)
SWITCH_STATUS = {409: "engine_switch_not_tts", 413: "engine_ref_too_large", 429: "engine_busy"}
SWITCH_ATTEMPTS = 3
SWITCH_MAX_WAIT_S = 30.0


def switch_body(engine, text, ref, seed, options):
    """(request body, facts) for one take on the switch, refused with a typed code when the switch would refuse it."""
    if not text.strip() or len(text) > SWITCH_MAX_INPUT_CHARS:
        raise EngineError(
            "engine_input_invalid", f"engine {engine['id']}: a switch take is 1 to {SWITCH_MAX_INPUT_CHARS} characters"
        )
    low, high = SWITCH_SEED_RANGE.get(engine["backend"], SWITCH_ANY_SEED)
    if isinstance(seed, bool) or not isinstance(seed, int) or not low <= seed <= high:
        raise EngineError("engine_seed_range", f"engine {engine['id']}: the switch takes an integer seed {low}..{high}")
    body = {"model": engine["model"], "input": text, "response_format": "wav", "seed": seed}
    facts = {"variant": "switch", "speed_honoured": False}
    if options["ref_audio"] != "data_uri":
        return body, facts | {"ref_audio_used": False, "ref_text_used": False, "conditioning": "none"}
    if not 0 < len(ref["audio"]) <= SWITCH_MAX_REF_AUDIO_BYTES:
        raise EngineError(
            "engine_ref_too_large",
            f"engine {engine['id']}: the switch takes a reference clip of 1 to {SWITCH_MAX_REF_AUDIO_BYTES} bytes",
        )
    transcript = ref["text"] if ref["text"].strip() else ""
    if len(transcript) > SWITCH_MAX_REF_TEXT_CHARS:
        raise EngineError(
            "engine_ref_text_too_long",
            f"engine {engine['id']}: the switch takes a transcript of at most {SWITCH_MAX_REF_TEXT_CHARS} characters",
        )
    body["ref_audio"] = "data:audio/wav;base64," + base64.b64encode(ref["audio"]).decode("ascii")
    if transcript:
        body["ref_text"] = transcript
    return body, facts | {
        "ref_audio_used": True,
        "ref_text_used": bool(transcript),
        "conditioning": "reference_and_transcript" if transcript else "reference",
        "voice_kept_by_switch": True,
    }


SWITCH_DETAIL = {
    "engine_switch_not_tts": "the switch's active entry is not a tts entry; switch to one first",
    "engine_ref_too_large": "the switch would not take the reference clip",
    "engine_busy": f"the switch's voice-clone slots stayed taken over {SWITCH_ATTEMPTS} attempts",
}
SLEEP = time.sleep  # tests replace it


def switch_speech(engine, text, ref, seed, options):
    body, facts = switch_body(engine, text, ref, seed, options)
    attempt = 0
    while True:
        attempt += 1
        try:
            data, _ = call(engine, speech_url(engine["endpoint"]), body, options, "audio/wav")
            return wav_reply(engine, data), facts | {"attempts": attempt}
        except EngineError as error:
            code = SWITCH_STATUS.get(error.status)
            if code is None:
                raise
            if code == "engine_busy" and attempt < SWITCH_ATTEMPTS:
                SLEEP(min(5.0 if error.retry_after is None else error.retry_after, SWITCH_MAX_WAIT_S))
                continue
            detail = f"engine {engine['id']}: {SWITCH_DETAIL[code]} (HTTP {error.status})"
            raise EngineError(code, detail, error.status) from None


def honours_speed(engine):
    """False for a runtime that ignores the speed knob, a switch take (the switch sends none), or a batch rendered
    before the fit; render.py then fits timing with atempo alone."""
    return engine["backend"] not in (QWENTTS, AUDIOCPP_BATCH) and engine.get("profile") != SWITCH


def synthesize(engine, text, voice, ref, seed, speed, options, sess=None):
    """(WAV bytes, facts about the take) for one chunk. sess: the render's Session, for engines with a voice
    registry; without one a QwenTtsCpp take registers, speaks and deletes on its own."""
    if engine["backend"] == "Fake":
        if not engine["endpoint"].startswith("fake://"):
            raise EngineError("engine_endpoint_invalid", f"fake engine {engine['id']} needs a fake:// endpoint")
        return fake(engine, text, seed, speed)
    if engine["endpoint"].startswith("fake://"):
        raise EngineError("engine_endpoint_invalid", f"engine {engine['id']} is not Fake but has a fake:// endpoint")
    if engine["backend"] == AUDIOCPP_BATCH:
        raise EngineError(
            "engine_out_of_process",
            f"engine {engine['id']} runs as a batch on the GPU host: narrate plan, then render --prerendered",
        )
    if engine.get("profile") == SWITCH:
        return switch_speech(engine, text, ref, seed, options)
    if engine["backend"] == QWENTTS:
        return qwentts_speech(engine, text, voice, ref, seed, options, sess)
    return speech(engine, text, voice, ref, seed, speed, options)


def probe(engine):
    """Availability without synthesis: fake engines are always available; http engines are not probed."""
    if engine["backend"] == "Fake":
        variant = urllib.parse.urlsplit(engine["endpoint"]).netloc
        espeak_found = shutil.which("espeak-ng") is not None
        return {"available": True, "variant": "espeak-ng" if variant == "espeak" and espeak_found else "sine"}
    if engine["backend"] == AUDIOCPP_BATCH:
        return {"available": "out_of_process", "reason": "a batch run in a GPU window; narrate reads its takes"}
    return {"available": "not_probed", "reason": "http engines are reached only by a render"}
