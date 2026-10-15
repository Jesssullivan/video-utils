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
import math
import os
import re
import socket
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


def loopback(host):
    """True when host is a loopback address, or localhost resolving to loopback addresses only."""
    try:
        if host == "localhost":
            found = {a[4][0] for a in socket.getaddrinfo(host, None)}
            return bool(found) and all(ipaddress.ip_address(a).is_loopback for a in found)
        return ipaddress.ip_address(host or "").is_loopback
    except (OSError, ValueError):
        return False


def stt_url(cfg):
    """The http backend's endpoint: an http(s) URL on a loopback host, without user info, params or fragment.
    A fragment would swallow the query this module appends, so it is refused rather than dropped."""
    url = cfg.whisper["url"]
    p = urllib.parse.urlsplit(url)
    try:
        _ = p.port  # a malformed port raises ValueError
        local = loopback(p.hostname)
    except ValueError:
        local = False
    if p.scheme not in ("http", "https") or not local or "@" in p.netloc:
        raise ValueError("whisper.url must be an http(s) URL on a loopback host, without user info")
    if "#" in url or urllib.parse.urlparse(url).params:
        raise ValueError("whisper.url must carry no fragment and no ;params")
    return url


def http_timeout(cfg):
    """Seconds to wait on the service per socket operation: a finite number above zero."""
    t = cfg.whisper["http_timeout_s"]
    if isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t) or t <= 0:
        raise ValueError("whisper.http_timeout_s must be a finite number of seconds above 0")
    return float(t)


def bearer():
    """The Authorization header value from CONDENSE_STT_TOKEN, or None when it is unset or empty.
    A token that is not visible ASCII (a trailing newline from an env file, say) is refused without echoing it."""
    token = os.environ.get(TOKEN_ENV)
    if not token:
        return None
    if not re.fullmatch(r"[\x21-\x7e]+", token):
        raise ValueError(f"{TOKEN_ENV} must be visible ASCII without spaces or line breaks")
    return f"Bearer {token}"


def http_settings(cfg):
    """Check every http backend setting before any work. Return (url, timeout, authorization or None)."""
    return stt_url(cfg), http_timeout(cfg), bearer()


def provenance(cfg):
    """What produced the transcription, for work/<clip>.stt.json. Never the token."""
    w = cfg.whisper
    common = {"language": w["language"], "dtw": w["dtw"], "pass1": w["pass1"], "chunk_s": w["chunk_s"]}
    if backend(cfg) == "http":
        return {"backend": "http", "url": stt_url(cfg), "response_format": "whisper_full", **common}
    return {"backend": "cli", "model": Path(cfg.model).name, **common}


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
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
        raise RuntimeError("stt service sent JSON that is not whisper's full transcription") from None
    return doc


def http_full(cfg, wav, **query):
    """POST one wav to the STT service. Return whisper-cli full JSON. Every failure raises; none is retried.
    No error message carries the token."""
    url, timeout, auth = http_settings(cfg)
    params = urllib.parse.urlencode({"response_format": "whisper_full", "language": cfg.whisper["language"], **query})
    req = urllib.request.Request(
        f"{url}{'&' if urllib.parse.urlsplit(url).query else '?'}{params}",
        data=Path(wav).read_bytes(),
        headers={"Content-Type": "audio/wav", "Accept": "application/json"},
        method="POST",
    )
    if auth:
        req.add_header("Authorization", auth)
    try:
        with OPENER.open(req, timeout=timeout) as r:
            if r.status != 200:
                raise RuntimeError(f"stt service answered HTTP {r.status}")
            body = r.read(MAX_REPLY + 1)
    except urllib.error.HTTPError as e:
        e.close()
        raise RuntimeError(f"stt service answered HTTP {e.code}") from None
    except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError) as e:
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
    if backend(cfg) == "http":
        http_settings(cfg)
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
        http_settings(cfg)
        if clip["whisper_args"]:
            raise ValueError(f"{clip['name']}: whisper_args apply to whisper-cli only, not to backend = http")
    # A failed run leaves no pass JSON behind, not even an earlier run's: events must not read stale words.
    outputs = {tag: cfg.f(clip, f"{tag}.json") for tag in ("pass1", "dtw", "stt")}
    for path in outputs.values():
        path.unlink(missing_ok=True)
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
    done = {}
    for tag in ["pass1", "dtw"] if cfg.whisper["pass1"] else ["dtw"]:

        def one(part, tag=tag):
            return whisper(cfg, part, f"{part.with_suffix('')}.{tag}", threads, tag == "dtw", clip["whisper_args"])

        with ThreadPoolExecutor(jobs) as pool:
            full = merge(list(pool.map(one, parts)), [a for a, _ in spans])
        tokens = [t for seg in full["transcription"] for t in seg["tokens"]]
        if tag == "dtw" and tokens and all(t.get("t_dtw", -1) < 0 for t in tokens):
            raise RuntimeError("whisper returned no DTW times: flash attention was on, or the dtw preset is wrong")
        done[tag] = json.dumps(full)
        print(f"{clip['name']} {tag}: {len(spans)} chunks, {len(full['transcription'])} segments, {len(tokens)} tokens")
    for tag, text in done.items():
        outputs[tag].write_text(text)
    outputs["stt"].write_text(json.dumps(provenance(cfg), indent=1))
