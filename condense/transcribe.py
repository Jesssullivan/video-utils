"""whisper.cpp transcription with DTW word times.

Each clip is cut at long silences into chunks of about chunk_s seconds. The chunks run in parallel, twice:
  pass1: the default beam search. It hears the most words. Its token times can sit seconds off.
  dtw:   greedy, flash attention off, DTW on. Its word starts follow the audio. It drops some words.
Flash attention silently disables DTW (every t_dtw comes back -1), so the dtw pass always sets -nfa.
A single beam DTW run over 55 minutes looped. Greedy chunks of 14 minutes did not.
"""

import json
import os
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import audio
from .config import FF, run


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


def whisper(cfg, wav, out, threads, dtw, extra):
    """Run whisper-cli on one wav. Return its full JSON (segments, tokens, offsets in ms, t_dtw in 1/100 s)."""
    w = cfg.whisper
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
        text = run("whisper-cli", "-m", model(cfg), "-f", f.name, "-t", cfg.whisper["threads"], "-nt", "-np").stdout
    return " ".join(re.sub(r"\[[^]]*\]|\([^)]*\)", " ", text).split())


def transcribe(cfg, clip):
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
