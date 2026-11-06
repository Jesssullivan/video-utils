"""narrate's Mac engine: an MLX speech server on loopback that speaks narrate's /v1/audio/speech dialect.

Runs on the Mac host inside a virtual environment with mlx-audio installed at the commit pinned in
narrate/bench/sources.json (docs/spec/NARRATE.md, profile `mac-mlx`, backend `MlxAudio`). Python 3.10 or later
there; this file also imports on 3.9 so the CPU host's tests can drive it with a fake backend.

Why a wrapper and not `mlx_audio.server`: at the pinned commit the upstream server reads `ref_audio` as a path on
the server's disk (a data URI is refused), has no `seed` field and reports no memory figure. narrate sends the
reference clip by content and records a seed per take, and the bench needs peak memory per take. This server:

- binds 127.0.0.1 only; reach it from another host through an SSH local forward;
- loads only the models named on the command line (`--model NAME=DIR`, a local snapshot fetched and hash-checked
  by narrate/bench/fetch.py), one resident at a time, with the Hub forced offline;
- accepts `ref_audio` only as a `data:audio/wav;base64,` URI (never a server path), writes it to a private
  temporary file for the duration of one request and passes it the way `mlx_audio.tts.generate` does;
- seeds MLX, NumPy and `random` with the request's `seed` before every take;
- answers a mono 16-bit WAV at the model's native rate, one request at a time.

Reply headers (facts about the take, never the request's text):
  X-Ref-Audio-Used   true when a reference clip reached the model
  X-Ref-Text-Used    true when the transcript reached a code path that reads it (see REF_TEXT_IGNORED); false
                     when it was sent but cannot be used; absent when none was sent
  X-Ref-Mode         ref (ref_audio + ref_text) or combined (VoxCPM2: also prompt_audio + prompt_text)
  X-Seed-Used        true when the request's seed seeded the generators
  X-Speed-Param      named when the model's generate() names `speed`, else absent (the knob is not applied)
  X-Load-Seconds     model load time paid by this request (0 when it was resident)
  X-Synth-Seconds    wall time of generation, after load
  X-Mlx-Peak-Bytes   MLX peak memory during this take (reset before it)
  X-Max-Rss-Bytes    the process's maximum resident size so far
  X-Sample-Rate      the WAV's rate

GET /health answers the allowed model names, the resident model and the pinned mlx-audio version.
"""

import argparse
import base64
import binascii
import contextlib
import gc
import inspect
import io
import json
import os
import random
import re
import resource
import sys
import tempfile
import time
import wave
from http.server import BaseHTTPRequestHandler, HTTPServer

HOST = "127.0.0.1"
DEFAULT_PORT = 18765
MAX_BODY = 32 * 1024 * 1024
MAX_INPUT = 2000
DATA_URI = re.compile(r"data:audio/(?:wav|x-wav|wave);base64,", re.IGNORECASE)
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,120}")

# Model types whose generate() names ref_text but whose reference-only mode does not read it (mlx-audio at the
# pinned commit: VoxCPM2's mode 3 tokenises only the target text). The combined mode passes the transcript as
# prompt_text with the same clip as prompt_audio, which that model does read.
REF_TEXT_IGNORED = {"voxcpm2"}
COMBINED_CAPABLE = {"voxcpm2"}


class Refusal(Exception):
    def __init__(self, status, code, detail):
        super().__init__(detail)
        self.status, self.code, self.detail = status, code, detail


class MlxBackend:
    """The real backend: mlx-audio on Apple silicon. Imported lazily so tests can run without MLX."""

    def __init__(self):
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        import mlx.core as mx
        import numpy as np

        self.mx, self.np = mx, np

    def version(self):
        try:
            from importlib.metadata import version

            return {"mlx_audio": version("mlx-audio"), "mlx": version("mlx")}
        except Exception:  # noqa: BLE001 - informational only
            return {}

    def load(self, path):
        from mlx_audio.tts.utils import load_model

        return load_model(path)

    def unload(self):
        gc.collect()
        self.mx.clear_cache()

    def reference(self, model, path):
        """The clip as `mlx_audio.tts.generate` would pass it: the path for models that read paths themselves,
        else audio loaded at the model's rate."""
        from mlx_audio.tts import generate as cli

        preserve = getattr(cli, "_model_preserves_ref_audio_paths", None)
        if preserve is not None and preserve(model):
            return path
        from mlx_audio.utils import load_audio

        return load_audio(path, sample_rate=model.sample_rate)

    def seed(self, value):
        self.mx.random.seed(value)
        self.np.random.seed(value)
        random.seed(value)

    def reset_peak(self):
        self.mx.reset_peak_memory()

    def peak(self):
        return int(self.mx.get_peak_memory())

    def pcm16(self, parts):
        """Little-endian 16-bit frames of the concatenated float parts, clipped to [-1, 1]."""
        np = self.np
        audio = np.concatenate([np.asarray(p, dtype=np.float32).reshape(-1) for p in parts])
        return (np.clip(audio, -1.0, 1.0) * 32767).round().astype("<i2").tobytes()


def pcm16(parts):
    """The standard-library form of MlxBackend.pcm16, for backends without NumPy."""
    frames = bytearray()
    for part in parts:
        for value in part:
            v = max(-1.0, min(1.0, float(value)))
            frames += int(round(v * 32767)).to_bytes(2, "little", signed=True)
    return bytes(frames)


def wav(frames, rate):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(int(rate))
        out.writeframes(frames)
    return buffer.getvalue()


def max_rss_bytes():
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(rss if sys.platform == "darwin" else rss * 1024)  # macOS reports bytes, Linux KiB


class Engine:
    """Model registry, residency and one take. Not thread-safe: the HTTP server is single-threaded."""

    def __init__(self, models, backend, modes=None):
        self.models, self.backend = dict(models), backend
        self.modes = dict(modes or {})
        self.resident_name, self.resident = None, None

    def model(self, name):
        if name not in self.models:
            raise Refusal(404, "model_not_allowed", f"model {name!r} is not one this server was started with")
        if self.resident_name == name:
            return self.resident, 0.0
        self.resident_name, self.resident = None, None
        self.backend.unload()
        start = time.perf_counter()
        model = self.backend.load(self.models[name])
        took = time.perf_counter() - start
        self.resident_name, self.resident = name, model
        return model, took

    def take(self, request):
        name = request.get("model")
        text = request.get("input")
        if not isinstance(name, str) or not NAME.fullmatch(name):
            raise Refusal(400, "model_invalid", "model must be a name this server was started with")
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_INPUT:
            raise Refusal(400, "input_invalid", f"input must be 1 to {MAX_INPUT} codepoints")
        if request.get("response_format", "wav") != "wav":
            raise Refusal(400, "format_unsupported", "response_format must be wav")
        speed = request.get("speed", 1.0)
        if not isinstance(speed, (int, float)) or isinstance(speed, bool) or not 0.5 <= speed <= 2.0:
            raise Refusal(400, "speed_invalid", "speed must be a number from 0.5 to 2.0")
        seed = request.get("seed")
        if seed is not None and (not isinstance(seed, int) or isinstance(seed, bool) or not 0 <= seed < 2**32):
            raise Refusal(400, "seed_invalid", "seed must be an integer from 0 to 2**32 - 1")
        ref_audio, ref_text = request.get("ref_audio"), request.get("ref_text")
        if ref_text is not None and (not isinstance(ref_text, str) or len(ref_text) > 4 * MAX_INPUT):
            raise Refusal(400, "ref_text_invalid", "ref_text must be text")
        if ref_audio is not None:
            if not isinstance(ref_audio, str) or not DATA_URI.match(ref_audio):
                raise Refusal(400, "ref_audio_invalid", "ref_audio must be a data:audio/wav;base64, URI")
            try:
                clip = base64.b64decode(ref_audio[DATA_URI.match(ref_audio).end() :], validate=True)
            except (binascii.Error, ValueError):
                raise Refusal(400, "ref_audio_invalid", "ref_audio is not valid base64") from None
            if clip[:4] != b"RIFF" or clip[8:12] != b"WAVE":
                raise Refusal(400, "ref_audio_invalid", "ref_audio is not a WAV")
        else:
            clip = None

        model, load_s = self.model(name)
        params = inspect.signature(model.generate).parameters
        model_type = getattr(model, "model_type", "")
        mode = self.modes.get(name, "ref")
        facts = {"load_s": load_s, "mode": mode if clip is not None else None}
        kwargs = {}
        if "speed" in params:
            kwargs["speed"] = float(speed)
        facts["speed_param"] = "speed" in params
        for key in ("lang_code", "max_tokens"):
            if request.get(key) is not None and key in params:
                kwargs[key] = request[key]

        with contextlib.ExitStack() as stack:
            if clip is not None:
                work = stack.enter_context(tempfile.TemporaryDirectory(prefix="narrate-ref-"))
                path = os.path.join(work, "ref.wav")
                with open(path, "wb") as f:
                    f.write(clip)
                kwargs["ref_audio"] = self.backend.reference(model, path)
                facts["ref_audio_used"] = True
                if ref_text:
                    if mode == "combined":
                        kwargs["prompt_audio"] = path
                        kwargs["prompt_text"] = ref_text
                        facts["ref_text_used"] = True
                    elif "ref_text" in params:
                        kwargs["ref_text"] = ref_text
                        facts["ref_text_used"] = model_type not in REF_TEXT_IGNORED
                    else:
                        facts["ref_text_used"] = False
            else:
                facts["ref_audio_used"] = False
                if request.get("voice") and "voice" in params:
                    kwargs["voice"] = request["voice"]
                if ref_text:
                    facts["ref_text_used"] = False
            if seed is not None:
                self.backend.seed(seed)
            facts["seed_used"] = seed is not None
            self.backend.reset_peak()
            start = time.perf_counter()
            parts, rate = [], None
            for result in model.generate(text, **kwargs):
                parts.append(result.audio)
                rate = rate or result.sample_rate
            frames = getattr(self.backend, "pcm16", pcm16)(parts) if parts else b""
            facts["synth_s"] = time.perf_counter() - start
            facts["peak_bytes"] = self.backend.peak()
        if not frames or not rate:
            raise Refusal(502, "engine_empty", "the model produced no audio")
        facts["rate"] = int(rate)
        facts["max_rss_bytes"] = max_rss_bytes()
        return wav(frames, rate), facts


def headers_for(facts):
    out = {
        "X-Ref-Audio-Used": "true" if facts["ref_audio_used"] else "false",
        "X-Seed-Used": "true" if facts["seed_used"] else "false",
        "X-Load-Seconds": f"{facts['load_s']:.3f}",
        "X-Synth-Seconds": f"{facts['synth_s']:.3f}",
        "X-Mlx-Peak-Bytes": str(facts["peak_bytes"]),
        "X-Max-Rss-Bytes": str(facts["max_rss_bytes"]),
        "X-Sample-Rate": str(facts["rate"]),
    }
    if "ref_text_used" in facts:
        out["X-Ref-Text-Used"] = "true" if facts["ref_text_used"] else "false"
    if facts.get("mode"):
        out["X-Ref-Mode"] = facts["mode"]
    if facts["speed_param"]:
        out["X-Speed-Param"] = "named"
    return out


def handler_for(engine, version):
    class Handler(BaseHTTPRequestHandler):
        server_version = "narrate-mlx-speech"
        sys_version = ""

        def log_message(self, fmt, *args):  # one line per request, never a body
            sys.stderr.write(f"{time.strftime('%H:%M:%S')} {fmt % args}\n")

        def reply(self, status, body, ctype, extra=None):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def refuse(self, refusal):
            body = json.dumps({"error": refusal.code, "detail": refusal.detail}).encode()
            self.reply(refusal.status, body, "application/json")

        def do_GET(self):
            if self.path.rstrip("/") != "/health":
                return self.refuse(Refusal(404, "not_found", "GET /health only"))
            body = {"models": sorted(engine.models), "resident": engine.resident_name, "versions": version}
            self.reply(200, json.dumps(body).encode(), "application/json")

        def do_POST(self):
            try:
                if self.path.split("?")[0].rstrip("/") != "/v1/audio/speech":
                    raise Refusal(404, "not_found", "POST /v1/audio/speech only")
                if "json" not in (self.headers.get("Content-Type") or ""):
                    raise Refusal(415, "content_type", "send application/json")
                length = int(self.headers.get("Content-Length") or 0)
                if length <= 0 or length > MAX_BODY:
                    raise Refusal(413, "body_size", f"body must be 1 to {MAX_BODY} bytes")
                try:
                    request = json.loads(self.rfile.read(length))
                except ValueError:
                    raise Refusal(400, "json_invalid", "body is not JSON") from None
                if not isinstance(request, dict):
                    raise Refusal(400, "json_invalid", "body must be a JSON object")
                data, facts = engine.take(request)
            except Refusal as refusal:
                return self.refuse(refusal)
            except Exception as error:  # noqa: BLE001 - a model failure is a 500 with its type, never a traceback
                sys.stderr.write(f"take failed: {type(error).__name__}: {error}\n")
                return self.refuse(Refusal(500, "engine_failed", type(error).__name__))
            self.reply(200, data, "audio/wav", headers_for(facts))

    return Handler


def parse_models(values):
    models = {}
    for value in values:
        name, sep, path = value.partition("=")
        if not sep or not NAME.fullmatch(name) or not path:
            raise SystemExit(f"--model {value!r}: NAME=DIR")
        if not os.path.isdir(path) or not os.path.isfile(os.path.join(path, "config.json")):
            raise SystemExit(f"--model {name}: {path} is not a model snapshot with a config.json")
        models[name] = os.path.abspath(path)
    if not models:
        raise SystemExit("at least one --model NAME=DIR")
    return models


def parse_modes(values, models):
    modes = {}
    for value in values:
        name, sep, mode = value.partition("=")
        if not sep or name not in models or mode not in ("ref", "combined"):
            raise SystemExit(f"--ref-mode {value!r}: NAME=ref|combined for a --model NAME")
        modes[name] = mode
    return modes


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--model", action="append", default=[], help="NAME=DIR, a local hash-checked snapshot")
    parser.add_argument("--ref-mode", action="append", default=[], help="NAME=ref|combined (default ref)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"loopback port (default {DEFAULT_PORT})")
    args = parser.parse_args(argv)
    models = parse_models(args.model)
    modes = parse_modes(args.ref_mode, models)
    backend = MlxBackend()
    engine = Engine(models, backend, modes)
    server = HTTPServer((HOST, args.port), handler_for(engine, backend.version()))
    sys.stderr.write(f"narrate mlx speech on http://{HOST}:{args.port} models={sorted(models)}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
