"""The http speech-to-text backend against an in-process fake service on synthetic media.

No real service is contacted: every URL is a loopback port this module opened. The canned replies are the
fake whisper JSON of conftest, so the http path and the whisper-cli path can be compared word for word.
"""

import io
import json
import shutil
import subprocess
import threading
import time
import urllib.parse
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from conftest import SPEECH, TOTAL, fake_whisper, fake_words

from condense import audio, config, events, transcribe
from condense.config import Config

TOKEN = "synthetic-test-token-0123"
HOST = "localhost"  # stt_url accepts it only while it resolves to loopback addresses
TOML = """
[whisper]
backend = "{backend}"
url = "{url}"
chunk_s = {chunk_s}
[[clip]]
name = "talk"
file = "talk.wav"
{extra}
"""


def canned(chunk=(0.0, TOTAL)):
    """Fake whisper JSON for one chunk (start, end): the words said inside it, on the chunk's own clock."""
    a, b = chunk
    return fake_whisper([dict(w, start=w["start"] - a, end=w["end"] - a) for w in fake_words() if a <= w["start"] < b])


class Fake:
    """A loopback STT service. `reply(query, body)` gives (status, headers, bytes); every request is recorded."""

    def __init__(self, reply):
        self.requests, self.reply = [], reply
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(self.path).query))
                fake.requests.append(dict(path=self.path, query=query, headers=dict(self.headers), body=body))
                status, headers, data = fake.reply(query, body)
                try:
                    self.send_response(status)
                    for k, v in headers.items():
                        self.send_header(k, v)
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                except OSError:  # the client gave up first
                    pass

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer((HOST, 0), Handler)
        self.server.daemon_threads = True
        self.url = f"http://{HOST}:{self.server.server_address[1]}/v1/transcribe"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def ok(doc):
    return 200, {"Content-Type": "application/json"}, json.dumps(doc).encode()


def chunk_reply(query, body):
    """Canned JSON for the chunk the posted wav holds."""
    return ok(canned(chunk_of(body)))


SPANS = []  # the chunks of the clip under test, as transcribe.cuts makes them


def seconds(wav_bytes):
    with wave.open(io.BytesIO(wav_bytes)) as w:
        return w.getnframes() / w.getframerate()


def chunk_of(body):
    """The chunk a posted wav holds, told apart by its length."""
    return min(SPANS, key=lambda s: abs(s[1] - s[0] - seconds(body))) if SPANS else (0.0, TOTAL)


@pytest.fixture
def service():
    fakes = []

    def start(reply=chunk_reply):
        fakes.append(Fake(reply))
        return fakes[-1]

    yield start
    for f in fakes:
        f.close()
    SPANS.clear()


@pytest.fixture(scope="module")
def media(tmp_path_factory):
    """A 24 s wav: noisy tone bursts where conftest's words are said, digital silence between."""
    base = tmp_path_factory.mktemp("media")
    gate = "+".join(f"between(t,{a},{b})" for a, b in SPEECH)
    sound = (
        f"sine=f=220:r=48000:d={TOTAL}[s];anoisesrc=c=pink:r=48000:a=0.5:d={TOTAL}:seed=1[n];"
        f"[s][n]amix=inputs=2,volume='if({gate},1,0)':eval=frame"
    )
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", sound, base / "talk.wav"], check=True)
    return base / "talk.wav"


def make(tmp_path, media, name, backend, url="", chunk_s=800, extra=""):
    base = tmp_path / name
    base.mkdir()
    shutil.copy(media, base / "talk.wav")
    (base / "talk.toml").write_text(TOML.format(backend=backend, url=url, chunk_s=chunk_s, extra=extra))
    return Config(base / "talk.toml")


def fake_cli(monkeypatch):
    """whisper-cli stood in for: it writes the same canned JSON the fake service sends."""
    real = transcribe.run

    def run(*args, **kwargs):
        if args[0] != "whisper-cli":
            return real(*args, **kwargs)
        a = list(map(str, args))
        wav = a[a.index("-f") + 1]
        with open(wav, "rb") as f:
            doc = canned(chunk_of(f.read()))
        with open(a[a.index("-of") + 1] + ".json", "w") as f:
            json.dump(doc, f)
        return subprocess.CompletedProcess(a, 0, "", "")

    monkeypatch.setattr(transcribe, "run", run)


def record_chunks(cfg):
    """The clip's chunks, so both fakes can answer each chunk with its own words."""
    clip = cfg.clips[0]
    wav = audio.extract(cfg, clip)
    sil = audio.silences(wav, clip["silence_db"], cfg.rules["silence_s"])
    SPANS[:] = transcribe.cuts(sil, audio.duration(wav), cfg.whisper["chunk_s"])
    return SPANS


@pytest.mark.parametrize("chunk_s", [800, 10])
def test_http_words_equal_cli_words_for_the_same_whisper_json(tmp_path, media, service, monkeypatch, chunk_s):
    monkeypatch.setenv(transcribe.TOKEN_ENV, TOKEN)
    fake = service()
    cli = make(tmp_path, media, "cli", "cli", chunk_s=chunk_s)
    web = make(tmp_path, media, "http", "http", fake.url, chunk_s=chunk_s)
    (tmp_path / "model.bin").write_bytes(b"not a model")
    cli.model = str(tmp_path / "model.bin")
    spans = list(record_chunks(cli))
    assert len(spans) == (1 if chunk_s == 800 else 2)

    transcribe.transcribe(web, web.clips[0])
    fake_cli(monkeypatch)
    transcribe.transcribe(cli, cli.clips[0])
    for cfg in (cli, web):
        events.run(cfg, cfg.clips[0])

    for ext in ("pass1.json", "dtw.json", "words.json", "events.json"):
        assert web.f("talk", ext).read_bytes() == cli.f("talk", ext).read_bytes(), ext
    words = json.loads(web.f("talk", "words.json").read_text())
    assert [w["word"] for w in words] == " ".join(SPEECH.values()).split()  # every word once, chunks joined

    # one pass-1 and one DTW request per chunk; only the DTW one asks for DTW, with the configured preset
    assert len(fake.requests) == 2 * len(spans)
    assert sorted(r["query"].get("dtw", "") for r in fake.requests) == [""] * len(spans) + ["small.en"] * len(spans)
    for r in fake.requests:
        assert r["headers"]["Authorization"] == f"Bearer {TOKEN}"
        assert r["headers"]["Content-Type"] == "audio/wav" and r["body"][:4] == b"RIFF"
        assert r["query"]["response_format"] == "whisper_full" and r["query"]["language"] == "en"
        assert r["query"]["prompt"] == config.WHISPER["prompt"]
    assert TOKEN not in "".join(p.read_text(errors="replace") for p in web.work.rglob("*.json"))
    # each run names the backend that produced its transcription; neither names the token
    stt = {cfg.whisper["backend"]: json.loads(cfg.f("talk", "stt.json").read_text()) for cfg in (cli, web)}
    assert stt["http"]["backend"] == "http" and stt["http"]["url"] == fake.url
    assert stt["cli"] == {"backend": "cli", "model": "model.bin"} | {
        k: v for k, v in stt["http"].items() if k in ("language", "dtw", "pass1", "chunk_s")
    }


def test_the_segments_shape_is_adapted_to_whisper_json(tmp_path, media, service):
    def word(t):
        return {"start": t["offsets"]["from"] / 1000, "end": t["offsets"]["to"] / 1000, "word": t["text"]}

    def seg(s):
        o = s["offsets"]
        return {
            "start": o["from"] / 1000,
            "end": o["to"] / 1000,
            "text": s["text"],
            "words": list(map(word, s["tokens"])),
        }

    fake = service(lambda q, b: ok({"segments": [seg(s) for s in canned()["transcription"]]}))
    cfg = make(tmp_path, media, "seg", "http", fake.url)
    transcribe.transcribe(cfg, cfg.clips[0])
    for ext in ("pass1.json", "dtw.json"):
        assert events.words_from(json.loads(cfg.f("talk", ext).read_text()), True) == events.words_from(canned(), True)


def test_read_joins_the_service_text_without_tags_and_without_dtw(tmp_path, media, service, monkeypatch):
    monkeypatch.delenv(transcribe.TOKEN_ENV, raising=False)
    doc = canned()
    doc["transcription"].insert(0, {"text": " [BLANK_AUDIO]", "offsets": {"from": 0, "to": 900}, "tokens": []})
    doc["transcription"][1]["text"] = " (wind) Hello"
    fake = service(lambda q, b: ok(doc))
    cfg = make(tmp_path, media, "read", "http", fake.url)
    text = transcribe.read(cfg, cfg.clips[0]["file"], 1.0, 4.5)
    assert text == " ".join(SPEECH.values())
    (r,) = fake.requests
    assert "dtw" not in r["query"] and "prompt" not in r["query"]
    assert "Authorization" not in r["headers"]  # no token in the environment, none sent
    assert abs(seconds(r["body"]) - 3.5) < 0.01


def inf_word():
    """A word whose start is Infinity: json.dumps writes it and json.loads accepts it; no time is infinite."""
    return {"start": float("inf"), "end": 1, "word": "a"}


def slow(query, body):
    time.sleep(2)
    return ok(canned())


@pytest.mark.parametrize(
    "reply, match",
    [
        (lambda q, b: (500, {}, b"model fell over"), "HTTP 500"),
        (lambda q, b: (401, {}, b""), "HTTP 401"),
        (lambda q, b: (200, {"Content-Type": "application/json"}, b"{not json"), "no JSON"),
        (lambda q, b: ok({"text": "only text"}), "not whisper's full"),
        (
            lambda q, b: ok({"transcription": [{"text": " a", "offsets": {"from": 0.5, "to": 9}, "tokens": []}]}),
            "not whisper's full",
        ),
        (lambda q, b: ok([1, 2]), "not whisper's full"),
        (lambda q, b: ok({"segments": [{"start": 0, "end": 1, "text": " a", "words": [inf_word()]}]}), "not whisper's"),
        (lambda q, b: ok({"transcription": []} | {"pad": "x" * 200}), "over 100 bytes"),
        (slow, "timed out"),
    ],
)
def test_service_errors_and_timeouts_fail_closed(tmp_path, media, service, monkeypatch, capsys, reply, match):
    monkeypatch.setenv(transcribe.TOKEN_ENV, TOKEN)
    monkeypatch.setattr(transcribe, "MAX_REPLY", 100 if match.startswith("over") else transcribe.MAX_REPLY)
    fake = service(reply)
    cfg = make(tmp_path, media, "err", "http", fake.url)
    cfg.whisper["http_timeout_s"] = 0.5
    cfg.work.mkdir(exist_ok=True)
    for ext in ("pass1.json", "dtw.json", "stt.json"):  # an earlier run's outputs must not outlive a failed one
        cfg.f("talk", ext).write_text(json.dumps(canned()))
    with pytest.raises(RuntimeError, match=match) as err:
        transcribe.transcribe(cfg, cfg.clips[0])
    assert not any(cfg.f("talk", ext).exists() for ext in ("pass1.json", "dtw.json", "stt.json"))
    out = capsys.readouterr()
    assert TOKEN not in str(err.value) + out.out + out.err


def test_no_dtw_times_from_the_service_fail_closed(tmp_path, media, service):
    doc = canned()
    for seg in doc["transcription"]:
        for t in seg["tokens"]:
            t["t_dtw"] = -1
    fake = service(lambda q, b: ok(doc))
    cfg = make(tmp_path, media, "nodtw", "http", fake.url)
    with pytest.raises(RuntimeError, match="no DTW times"):
        transcribe.transcribe(cfg, cfg.clips[0])
    assert len(fake.requests) == 2  # pass 1 succeeded; its JSON is still not written alone
    assert not any(cfg.f("talk", ext).exists() for ext in ("pass1.json", "dtw.json", "stt.json"))


def test_a_redirect_is_refused_and_not_followed(tmp_path, media, service, monkeypatch):
    monkeypatch.setenv(transcribe.TOKEN_ENV, TOKEN)
    target = service()
    fake = service(lambda q, b: (307, {"Location": target.url}, b""))
    cfg = make(tmp_path, media, "redirect", "http", fake.url)
    with pytest.raises(RuntimeError, match="HTTP 307"):
        transcribe.transcribe(cfg, cfg.clips[0])
    assert target.requests == []


def test_an_unreachable_service_fails_closed(tmp_path, media, service):
    fake = service()
    url = fake.url
    fake.close()
    cfg = make(tmp_path, media, "down", "http", url)
    with pytest.raises(RuntimeError, match="stt service failed"):
        transcribe.transcribe(cfg, cfg.clips[0])


@pytest.mark.parametrize(
    "backend, url, extra, match",
    [
        ("grpc", "", "", "whisper.backend"),
        ("http", "", "", "loopback"),
        ("http", "http://stt.example.invalid:8080/v1/transcribe", "", "loopback"),
        ("http", "http://192.0.2.10:8080/v1/transcribe", "", "loopback"),
        ("http", f"ftp://{HOST}/v1/transcribe", "", "loopback"),
        ("http", f"http://user:pw@{HOST}:9/v1/transcribe", "", "user info"),
        ("http", f"http://{HOST}:9/v1/transcribe", 'whisper_args = ["-bs", "8"]', "whisper-cli only"),
        ("http", f"http://{HOST}:9/v1/transcribe#part", "", "no fragment"),
        ("http", f"http://{HOST}:9/v1/transcribe#", "", "no fragment"),
        ("http", f"http://{HOST}:9/v1/transcribe;v=1", "", "no ;params"),
    ],
)
def test_bad_backend_settings_are_refused_before_any_work(tmp_path, media, backend, url, extra, match):
    cfg = make(tmp_path, media, "bad", backend, url, extra=extra)
    with pytest.raises(ValueError, match=match) as err:
        transcribe.transcribe(cfg, cfg.clips[0])
    assert "pw" not in str(err.value)
    assert not cfg.f("talk", "16k.wav").exists()


def test_the_defaults_keep_the_cli_backend():
    assert config.WHISPER["backend"] == "cli" and config.WHISPER["url"] == ""
    assert "token" not in json.dumps(config.WHISPER).lower()  # the token lives in the environment only


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan"), True, "60"])
def test_a_timeout_that_is_not_a_positive_number_is_refused(tmp_path, media, timeout):
    cfg = make(tmp_path, media, "timeout", "http", f"http://{HOST}:9/v1/transcribe")
    cfg.whisper["http_timeout_s"] = timeout
    with pytest.raises(ValueError, match="http_timeout_s"):
        transcribe.transcribe(cfg, cfg.clips[0])
    assert not cfg.f("talk", "16k.wav").exists()


@pytest.mark.parametrize("token", [TOKEN + "\n", TOKEN + "\r\n", "two words", TOKEN + "\u00e9"])
def test_a_token_that_is_no_header_value_is_refused_without_echoing_it(tmp_path, media, service, monkeypatch, token):
    monkeypatch.setenv(transcribe.TOKEN_ENV, token)
    fake = service()
    cfg = make(tmp_path, media, "token", "http", fake.url)
    clip = cfg.clips[0]
    for call in (lambda: transcribe.transcribe(cfg, clip), lambda: transcribe.read(cfg, clip["file"], 1, 2)):
        with pytest.raises(ValueError, match=transcribe.TOKEN_ENV) as err:
            call()
        assert token.strip() not in str(err.value)
    assert fake.requests == [] and not cfg.f("talk", "16k.wav").exists()


def test_a_header_the_client_refuses_fails_closed_without_the_token(tmp_path, media, service, monkeypatch):
    """Belt and braces: should a bad header value reach http.client, its ValueError leaves no token behind."""
    monkeypatch.setattr(transcribe, "bearer", lambda: f"Bearer {TOKEN}\n")
    fake = service()
    cfg = make(tmp_path, media, "header", "http", fake.url)
    with pytest.raises(RuntimeError, match="stt service failed") as err:
        transcribe.http_full(cfg, media)
    assert TOKEN not in str(err.value) and err.value.__cause__ is None and err.value.__suppress_context__
    assert fake.requests == []


def test_localhost_counts_only_while_it_resolves_to_loopback(monkeypatch):
    def resolve(addresses):
        return lambda host, port: [(None, None, None, "", (a, 0)) for a in addresses]

    monkeypatch.setattr(transcribe.socket, "getaddrinfo", resolve(["::1"]))
    assert transcribe.loopback("localhost")
    monkeypatch.setattr(transcribe.socket, "getaddrinfo", resolve(["::1", "192.0.2.10"]))
    assert not transcribe.loopback("localhost")
    monkeypatch.setattr(transcribe.socket, "getaddrinfo", resolve([]))
    assert not transcribe.loopback("localhost")


@pytest.mark.parametrize(
    "url, recorded",
    [
        (f"http://{HOST}:8080/v1/transcribe?model=large&key=k1", f"http://{HOST}:8080/v1/transcribe"),
        (f"http://{HOST}/v1/transcribe?x=1", f"http://{HOST}:80/v1/transcribe"),
        ("https://[::1]:9443/stt?", "https://[::1]:9443/stt"),
        (f"http://{HOST}:9", f"http://{HOST}:9"),
    ],
)
def test_provenance_records_scheme_host_port_and_path_only(tmp_path, media, url, recorded):
    cfg = make(tmp_path, media, "prov", "http", url)
    record = transcribe.provenance(cfg)
    assert record["url"] == recorded and "?" not in json.dumps(record) and "k1" not in json.dumps(record)


def test_stt_json_never_carries_the_url_query(tmp_path, media, service):
    fake = service()
    cfg = make(tmp_path, media, "query", "http", f"{fake.url}?model=large&key=k1")
    transcribe.transcribe(cfg, cfg.clips[0])
    assert all(r["query"]["model"] == "large" and r["query"]["key"] == "k1" for r in fake.requests)  # still sent
    text = cfg.f("talk", "stt.json").read_text()
    assert json.loads(text)["url"] == fake.url and "?" not in text and "k1" not in text
