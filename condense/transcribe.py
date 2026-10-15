"""whisper.cpp transcription with DTW word times.

Each clip is cut at long silences into chunks of about chunk_s seconds. The chunks run in parallel, twice:
  pass1: the default beam search. It hears the most words. Its token times can sit seconds off.
  dtw:   greedy, flash attention off, DTW on. Its word starts follow the audio. It drops some words.
Flash attention silently disables DTW (every t_dtw comes back -1), so the dtw pass always sets -nfa.
A single beam DTW run over 55 minutes looped. Greedy chunks of 14 minutes did not.

With [whisper] backend = "http" each chunk is POSTed to a loopback speech-to-text service instead. It must answer
whisper-cli's full JSON (or the segments/words shape whisper_json adapts), so events.words_from reads both alike.
"""

import http.client
import ipaddress
import json
import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import audio
from .config import FF, run

TOKEN_ENV = "CONDENSE_STT_TOKEN"  # the http backend's bearer token: only ever read from the environment
MAX_REPLY = 64 << 20  # bytes; a chunk's full JSON is a few MB


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect is an error: the token and the audio never follow it."""

    def redirect_request(self, *args, **kwargs):
        return None


# No proxy may see the token; no redirect is followed.
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect)


def cuts(sil, total, chunk_s):
    """[(start, end)] chunks. Each cut sits mid-way through the longest silence within a quarter chunk of its target."""
    edges, t = [0.0], chunk_s
    while t < total - chunk_s / 2:
        near = [(b - a, (a + b) / 2) for a, b in sil if abs((a + b) / 2 - t) < chunk_s / 4]
        edges.append(round(max(near)[1] if near else t, 2))
        t = edges[-1] + chunk_s
    return list(zip(edges, edges[1:] + [total], strict=True))


def model(cfg):
    if not Path(cfg.model).exists():
        raise FileNotFoundError(f"no whisper model at {cfg.model}: run `just condense-model` or set WHISPER_MODEL")
    return cfg.model


def backend(cfg):
    name = cfg.whisper["backend"]
    if name not in ("cli", "http"):
        raise ValueError(f"whisper.backend = {name!r}: use cli or http")
    return name


def stt_url(cfg):
    """The http backend's endpoint: an http(s) URL on a loopback host, without user info."""
    url = cfg.whisper["url"]
    p = urllib.parse.urlsplit(url)
    try:
        _ = p.port  # a malformed port raises ValueError
        local = p.hostname == "localhost" or ipaddress.ip_address(p.hostname or "").is_loopback
    except ValueError:
        local = False
    if p.scheme not in ("http", "https") or not local or "@" in p.netloc:
        raise ValueError("whisper.url must be an http(s) URL on a loopback host, without user info")
    return url


def whisper_json(doc):
    """whisper-cli full JSON from a service reply. Whisper's own shape passes as it is. The shape
    {"segments": [{start, end, text, words: [{start, end, word}]}]} in seconds is adapted: each word becomes one
    token, and its start stands in for the DTW time. Any other shape raises."""

    def ms(t):
        return round(float(t) * 1000)

    def whole(x):
        return isinstance(x, int) and not isinstance(x, bool)

    try:
        if "transcription" not in doc:
            doc = {
                "transcription": [
                    {
                        "text": s["text"],
                        "offsets": {"from": ms(s["start"]), "to": ms(s["end"])},
                        "tokens": [
                            {
                                "text": " " + w["word"].strip(),
                                "offsets": {"from": ms(w["start"]), "to": ms(w["end"])},
                                "t_dtw": round(float(w["start"]) * 100),
                            }
                            for w in s["words"]
                        ],
                    }
                    for s in doc["segments"]
                ]
            }
        for seg in doc["transcription"]:
            for part in [seg, *seg["tokens"]]:
                o = part["offsets"]
                if not (isinstance(part["text"], str) and whole(o["from"]) and whole(o["to"])):
                    raise TypeError
                if "t_dtw" in part and not whole(part["t_dtw"]):
                    raise TypeError
    except (KeyError, TypeError, ValueError, AttributeError):
        raise RuntimeError("stt service sent JSON that is not whisper's full transcription") from None
    return doc


def http_full(cfg, wav, **query):
    """POST one wav to the STT service. Return whisper-cli full JSON. Every failure raises; none is retried."""
    url = stt_url(cfg)
    params = urllib.parse.urlencode({"response_format": "whisper_full", "language": cfg.whisper["language"], **query})
    req = urllib.request.Request(
        f"{url}{'&' if urllib.parse.urlsplit(url).query else '?'}{params}",
        data=Path(wav).read_bytes(),
        headers={"Content-Type": "audio/wav", "Accept": "application/json"},
        method="POST",
    )
    token = os.environ.get(TOKEN_ENV)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    timeout = float(cfg.whisper["http_timeout_s"])
    try:
        with OPENER.open(req, timeout=timeout) as r:
            if r.status != 200:
                raise RuntimeError(f"stt service answered HTTP {r.status}")
            body = r.read(MAX_REPLY + 1)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"stt service answered HTTP {e.code}") from None
    except (urllib.error.URLError, http.client.HTTPException, OSError) as e:
        r = getattr(e, "reason", e)
        why = "timed out" if isinstance(r, TimeoutError) else type(r if isinstance(r, BaseException) else e).__name__
        raise RuntimeError(f"stt service failed ({why}; each wait is bounded by {timeout:g} s)") from None
    if len(body) > MAX_REPLY:
        raise RuntimeError(f"stt service reply is over {MAX_REPLY} bytes")
    try:
        doc = json.loads(body)
    except ValueError:
        raise RuntimeError("stt service sent no JSON") from None
    return whisper_json(doc if isinstance(doc, dict) else {})


def whisper(cfg, wav, out, threads, dtw, extra):
    """Run whisper-cli (or the http backend) on one wav. Return its full JSON (segments, tokens, offsets in ms,
    t_dtw in 1/100 s)."""
    w = cfg.whisper
    if backend(cfg) == "http":
        full = http_full(cfg, wav, prompt=w["prompt"], **({"dtw": w["dtw"]} if dtw else {}))
        Path(f"{out}.json").write_text(json.dumps(full))
        return full
    args = ["-m", model(cfg), "-f", wav, "-l", w["language"], "-t", threads, "--prompt", w["prompt"], "-ojf"]
    args += ["-of", out]
    if dtw:
        args += ["-bs", "1", "-bo", "1", "-nfa", "-dtw", w["dtw"]]
    run("whisper-cli", *args, *extra)
    return json.loads(Path(f"{out}.json").read_text(errors="replace"))


def merge(fulls, offsets):
    """Join per-chunk whisper JSON on the clip clock."""
    out = None
    for full, off in zip(fulls, offsets, strict=True):
        ms = round(off * 1000)
        for seg in full["transcription"]:
            for o in [seg["offsets"]] + [t["offsets"] for t in seg["tokens"]]:
                o["from"] += ms
                o["to"] += ms
            for t in seg["tokens"]:
                if t.get("t_dtw", -1) >= 0:
                    t["t_dtw"] += round(off * 100)
        if out is None:
            out = full
        else:
            out["transcription"] += full["transcription"]
    return out


def read(cfg, src, a, b):
    """Whisper's plain text for [a, b] seconds of any media file, without [noise] tags."""
    with tempfile.NamedTemporaryFile(suffix=".wav", dir=cfg.work) as f:
        cut = ("-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", src, "-vn", "-ac", "1", "-ar", "16000")
        run(*FF, "-v", "error", *cut, "-c:a", "pcm_s16le", f.name)
        if backend(cfg) == "http":
            text = "\n".join(seg["text"] for seg in http_full(cfg, f.name)["transcription"])
        else:
            text = run("whisper-cli", "-m", model(cfg), "-f", f.name, "-t", cfg.whisper["threads"], "-nt", "-np").stdout
    return " ".join(re.sub(r"\[[^]]*\]|\([^)]*\)", " ", text).split())


def transcribe(cfg, clip):
    if backend(cfg) == "http":
        stt_url(cfg)
        if clip["whisper_args"]:
            raise ValueError(f"{clip['name']}: whisper_args apply to whisper-cli only, not to backend = http")
    wav = audio.extract(cfg, clip)
    spans = cuts(
        audio.silences(wav, clip["silence_db"], cfg.rules["silence_s"]), audio.duration(wav), cfg.whisper["chunk_s"]
    )
    jobs = min(len(spans), cfg.encode["jobs"])
    threads = max(1, min(cfg.whisper["threads"], (os.cpu_count() or 1) // jobs))
    tmp = cfg.work / "chunks"
    tmp.mkdir(exist_ok=True)
    parts = [tmp / f"{clip['name']}.{i}.wav" for i in range(len(spans))]
    for part, (a, b) in zip(parts, spans, strict=True):
        run(*FF, "-v", "error", "-ss", a, "-to", b, "-i", wav, "-c:a", "pcm_s16le", part)
    for tag in ["pass1", "dtw"] if cfg.whisper["pass1"] else ["dtw"]:

        def one(part, tag=tag):
            return whisper(cfg, part, f"{part.with_suffix('')}.{tag}", threads, tag == "dtw", clip["whisper_args"])

        with ThreadPoolExecutor(jobs) as pool:
            full = merge(list(pool.map(one, parts)), [a for a, _ in spans])
        tokens = [t for seg in full["transcription"] for t in seg["tokens"]]
        if tag == "dtw" and tokens and all(t.get("t_dtw", -1) < 0 for t in tokens):
            raise RuntimeError("whisper returned no DTW times: flash attention was on, or the dtw preset is wrong")
        cfg.f(clip, f"{tag}.json").write_text(json.dumps(full))
        print(f"{clip['name']} {tag}: {len(spans)} chunks, {len(full['transcription'])} segments, {len(tokens)} tokens")
