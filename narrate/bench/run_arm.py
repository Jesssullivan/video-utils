"""Run and score one engine-bench arm against a narrate speech endpoint.

Plan: docs/agent-notes/2026-10-22-narrate-bench-plan.md.

    run_arm.py chunks [--text T]                       the fixed chunk list and its sha256 (JSON on stdout)
    run_arm.py run --endpoint URL --model M --arm A --voice ID --clip WAV --transcript TXT --seed 1 --out DIR
    run_arm.py score --out DIR --whisper-model BIN     whisper round trip, WER, catastrophic chunks, summary

Chunking follows the plan: text-v1 is split at sentence boundaries (narrate.chunker.sentences) and greedily packed
to at most 300 codepoints, never across a section; a sentence longer than the limit splits as narrate's chunker
splits it. The text is sent as written: no lexical pass and no pronunciation table.

`run` sends one POST /v1/audio/speech per chunk and seed, in narrate's dialect (ref_audio as a WAV data URI, the
verified ref_text, seed, response_format wav, speed 1.0, lang_code en as mlx_audio.tts.generate defaults), writes
each take to <out>/<arm>/<voice>/seed<k>/<chunk>.wav and appends one line per take to <out>/takes.jsonl: wall
time, the server's synthesis and load seconds and memory headers when it sends them, the WAV's duration and
sha256. A take already recorded is skipped, so an interrupted run resumes. Reference clips and transcripts are
read from private paths and never written to the output; only their sha256 values are.

`score` reads every take with whisper-cli (16 kHz mono with 0.5 s of silence on each side, at most 4 threads),
computes WER with narrate.qa.wer (narrate's normaliser, not the Whisper English normaliser), finds silences over
2 s inside a take (50 ms frames under -50 dBFS), and writes <out>/scores.jsonl and <out>/summary.json: per arm,
voice and seed the RTF (synthesis seconds over audio seconds, load excluded), load seconds, peak memory, whole-text
WER (summed word errors over summed reference words), catastrophic chunks (WER over 30%, an inner silence over
2 s, or longer than twice its expected duration at 150 words a minute), and best-of-seeds per chunk.
"""

import argparse
import base64
import hashlib
import io
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import wave
from array import array
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from narrate.chunker import sentences, split_long  # noqa: E402
from narrate.qa import wer, words  # noqa: E402

TEXT = Path(__file__).resolve().parent / "text-v1.md"
LIMIT = 300
WPM = 150
CATASTROPHIC_WER = 0.30
SILENCE_S = 2.0
SILENCE_DBFS = -50.0
FRAME_S = 0.05
PAD_S = 0.5
MAX_THREADS = 4
NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sections(markdown):
    """[(section id, prose)] of a bench text: front matter, HTML comments and headings are not spoken."""
    text = markdown
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end < 0:
            raise ValueError("unterminated front matter")
        text = text[end + 5 :]
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    out, current, body = [], None, []
    for line in text.splitlines():
        heading = re.match(r"^##\s+(\S+)", line)
        if heading:
            if current is not None:
                out.append((current, " ".join(" ".join(body).split())))
            current, body = heading.group(1), []
        elif line.startswith("#"):
            continue
        elif current is not None:
            body.append(line)
    if current is not None:
        out.append((current, " ".join(" ".join(body).split())))
    ids = [sid for sid, _ in out]
    if len(set(ids)) != len(ids) or not all(prose for _, prose in out):
        raise ValueError("section ids must be unique and every section must have prose")
    return out


def chunk_list(markdown, limit=LIMIT):
    chunks = []
    for sid, prose in sections(markdown):
        packed, current = [], ""
        for sentence in sentences(prose):
            if len(sentence) > limit:
                if current:
                    packed.append(current)
                    current = ""
                packed += [piece for piece, _ in split_long(sentence, limit)]
            elif not current:
                current = sentence
            elif len(current) + 1 + len(sentence) <= limit:
                current += " " + sentence
            else:
                packed.append(current)
                current = sentence
        if current:
            packed.append(current)
        chunks += [{"id": f"{sid}.c{i:02d}", "section": sid, "text": t} for i, t in enumerate(packed, 1)]
    return chunks


def chunk_digest(chunks):
    canonical = json.dumps([[c["id"], c["text"]] for c in chunks], ensure_ascii=False, separators=(",", ":"))
    return sha256_bytes(canonical.encode("utf-8"))


def wav_info(data):
    """(rate, channels, sample width, frame count) of a WAV byte string."""
    with wave.open(io.BytesIO(data), "rb") as w:
        return w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()


def read_takes(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def post(endpoint, body, timeout):
    request = urllib.request.Request(
        endpoint.rstrip("/") + "/v1/audio/speech",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "audio/wav"},
        method="POST",
    )
    with NO_PROXY.open(request, timeout=timeout) as reply:
        return reply.read(), {k.lower(): v for k, v in reply.headers.items()}


def number(headers, key, kind=float):
    value = headers.get(key)
    try:
        return kind(value) if value is not None else None
    except ValueError:
        return None


def run(args):
    chunks = chunk_list(Path(args.text).read_text(encoding="utf-8"))
    if args.chunks:
        chunks = chunks[: args.chunks]
    clip = Path(args.clip).read_bytes()
    transcript_bytes = Path(args.transcript).read_bytes()
    transcript = transcript_bytes.decode("utf-8").strip()
    if clip[:4] != b"RIFF" or clip[8:12] != b"WAVE":
        raise SystemExit("--clip must be a WAV")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    ledger = out / "takes.jsonl"
    done = {(t["arm"], t["voice"], t["seed"], t["chunk"]) for t in read_takes(ledger) if t.get("ok")}
    ref_audio = "data:audio/wav;base64," + base64.b64encode(clip).decode("ascii")
    common = {
        "arm": args.arm,
        "model": args.model,
        "voice": args.voice,
        "clip_sha256": sha256_bytes(clip),
        "transcript_sha256": sha256_bytes(transcript_bytes),
        "chunks_sha256": chunk_digest(chunk_list(Path(args.text).read_text(encoding="utf-8"))),
        "text_sha256": sha256_bytes(Path(args.text).read_bytes()),
    }
    for seed in args.seed:
        folder = out / args.arm / args.voice / f"seed{seed}"
        folder.mkdir(parents=True, exist_ok=True)
        for chunk in chunks:
            key = (args.arm, args.voice, seed, chunk["id"])
            if key in done:
                continue
            body = {
                "model": args.model,
                "input": chunk["text"],
                "voice": args.voice,
                "response_format": "wav",
                "speed": 1.0,
                "seed": seed,
                "ref_audio": ref_audio,
                "ref_text": transcript,
                "lang_code": args.lang_code,
            }
            record = {**common, "seed": seed, "chunk": chunk["id"], "codepoints": len(chunk["text"])}
            start = time.perf_counter()
            try:
                data, headers = post(args.endpoint, body, args.timeout)
            except urllib.error.HTTPError as error:
                detail = error.read(2000).decode("utf-8", "replace")
                record.update(ok=False, error=f"HTTP {error.code}", detail=detail)
            except (urllib.error.URLError, OSError) as error:
                record.update(ok=False, error=type(getattr(error, "reason", error)).__name__)
            else:
                wall = time.perf_counter() - start
                rate, channels, width, frames = wav_info(data)
                path = folder / f"{chunk['id']}.wav"
                path.write_bytes(data)
                record.update(
                    ok=True,
                    wav=str(path.relative_to(out)),
                    wav_sha256=sha256_bytes(data),
                    rate=rate,
                    channels=channels,
                    sample_bits=8 * width,
                    audio_s=round(frames / rate, 4),
                    wall_s=round(wall, 4),
                    synth_s=number(headers, "x-synth-seconds"),
                    load_s=number(headers, "x-load-seconds"),
                    peak_bytes=number(headers, "x-mlx-peak-bytes", int),
                    max_rss_bytes=number(headers, "x-max-rss-bytes", int),
                    ref_audio_used=headers.get("x-ref-audio-used"),
                    ref_text_used=headers.get("x-ref-text-used"),
                    ref_mode=headers.get("x-ref-mode"),
                    seed_used=headers.get("x-seed-used"),
                )
            record["at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            with ledger.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
            status = f"{record.get('audio_s', '-')} s audio, {record.get('synth_s', '-')} s synth"
            print(
                f"{args.arm} {args.voice} seed{seed} {chunk['id']}: {'ok' if record['ok'] else record['error']} "
                f"{status}",
                file=sys.stderr,
                flush=True,
            )
            if not record["ok"] and args.stop_on_error:
                return 1
    return 0


def pcm_frames(path):
    """Mono float samples and rate of a 16- or 24-bit PCM WAV (channels averaged)."""
    with wave.open(str(path), "rb") as w:
        rate, channels, width, n = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
        raw = w.readframes(n)
    if width == 2:
        values = array("h")
        values.frombytes(raw)
        if sys.byteorder != "little":
            values.byteswap()
        scale = 32768.0
    elif width == 3:
        values = [int.from_bytes(raw[i : i + 3], "little", signed=True) for i in range(0, len(raw), 3)]
        scale = 8388608.0
    else:
        raise ValueError(f"{width * 8}-bit WAV is not read here")
    mono = [sum(values[i : i + channels]) / channels / scale for i in range(0, len(values), channels)]
    return mono, rate


def inner_silence_s(samples, rate):
    """The longest run of frames under SILENCE_DBFS that has sound on both sides."""
    size = max(1, int(FRAME_S * rate))
    loud = []
    for i in range(0, len(samples) - size + 1, size):
        frame = samples[i : i + size]
        rms = math.sqrt(sum(v * v for v in frame) / size)
        loud.append(rms > 0 and 20 * math.log10(rms) > SILENCE_DBFS)
    if True not in loud:
        return len(loud) * FRAME_S
    first, last = loud.index(True), len(loud) - 1 - loud[::-1].index(True)
    longest = run = 0
    for flag in loud[first : last + 1]:
        run = 0 if flag else run + 1
        longest = max(longest, run)
    return round(longest * FRAME_S, 3)


def transcribe(whisper, model, path, threads):
    with tempfile.TemporaryDirectory(prefix="narrate-bench-") as work:
        padded = Path(work) / "take16k.wav"
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-i",
                str(path),
                "-af",
                f"adelay={int(PAD_S * 1000)}:all=1,apad=pad_dur={PAD_S}",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                str(padded),
            ],
            check=True,
        )
        reply = subprocess.run(
            [whisper, "-m", str(model), "-f", str(padded), "-l", "en", "-t", str(threads), "-nt", "-np"],
            check=True,
            capture_output=True,
            text=True,
        )
    return " ".join(reply.stdout.split())


def score(args):
    out = Path(args.out)
    whisper = shutil.which("whisper-cli")
    if not whisper or not shutil.which("ffmpeg"):
        raise SystemExit("whisper-cli and ffmpeg must be on PATH (nix develop .#condense)")
    model = Path(args.whisper_model)
    model_sha = sha256_bytes(model.read_bytes())
    chunks = {c["id"]: c for c in chunk_list(Path(args.text).read_text(encoding="utf-8"))}
    scores_path = out / "scores.jsonl"
    scored = {s["wav_sha256"]: s for s in read_takes(scores_path)}
    takes = [t for t in read_takes(out / "takes.jsonl") if t.get("ok")]
    latest = {}
    for take in takes:  # the last ok take per key wins
        latest[(take["arm"], take["voice"], take["seed"], take["chunk"])] = take
    threads = min(MAX_THREADS, max(1, args.threads))
    for key, take in sorted(latest.items()):
        if take["wav_sha256"] in scored:
            continue
        path = out / take["wav"]
        hypothesis = transcribe(whisper, model, path, threads)
        reference = chunks[take["chunk"]]["text"]
        samples, rate = pcm_frames(path)
        expected = len(words(reference)) / WPM * 60
        row = {
            "wav_sha256": take["wav_sha256"],
            "arm": take["arm"],
            "voice": take["voice"],
            "seed": take["seed"],
            "chunk": take["chunk"],
            "hypothesis": hypothesis,
            "ref_words": len(words(reference)),
            "wer": wer(reference, hypothesis),
            "inner_silence_s": inner_silence_s(samples, rate),
            "expected_s": round(expected, 3),
            "audio_s": take["audio_s"],
            "whisper_model_sha256": model_sha,
        }
        row["catastrophic"] = [
            name
            for name, hit in (
                ("wer", row["wer"] > CATASTROPHIC_WER),
                ("silence", row["inner_silence_s"] > SILENCE_S),
                ("length", take["audio_s"] > 2 * expected),
            )
            if hit
        ]
        scored[take["wav_sha256"]] = row
        with scores_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
        print(f"{key}: wer {row['wer']:.3f} {row['catastrophic'] or ''}", file=sys.stderr, flush=True)
    summary = summarise(latest, scored, chunks)
    summary["whisper_model_sha256"] = model_sha
    (out / "summary.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=1))
    return 0


def summarise(latest, scored, chunks):
    groups = {}
    for (arm, voice, seed, chunk), take in latest.items():
        groups.setdefault((arm, voice), {}).setdefault(seed, {})[chunk] = (take, scored.get(take["wav_sha256"]))
    rows = []
    for (arm, voice), seeds in sorted(groups.items()):
        per_seed = {}
        for seed, items in sorted(seeds.items()):
            takes = [t for t, _ in items.values()]
            rows_s = [s for _, s in items.values() if s]
            synth = sum(t["synth_s"] if t.get("synth_s") is not None else t["wall_s"] for t in takes)
            audio = sum(t["audio_s"] for t in takes)
            first = min(takes, key=lambda t: t["at"])
            per_seed[seed] = {
                "chunks": len(items),
                "complete": len(items) == len(chunks),
                "audio_s": round(audio, 2),
                "synth_s": round(synth, 2),
                "rtf": round(synth / audio, 3) if audio else None,
                "chunk_rtf_max": round(
                    max((t["synth_s"] if t.get("synth_s") is not None else t["wall_s"]) / t["audio_s"] for t in takes),
                    3,
                ),
                "load_s_first_take": first.get("load_s"),
                "peak_bytes_max": max((t.get("peak_bytes") or 0) for t in takes) or None,
                "max_rss_bytes": max((t.get("max_rss_bytes") or 0) for t in takes) or None,
                "ref_text_used": sorted({str(t.get("ref_text_used")) for t in takes}),
                "rate": sorted({t["rate"] for t in takes}),
                "scored": len(rows_s),
                "wer_whole": round(
                    sum(s["wer"] * s["ref_words"] for s in rows_s) / sum(s["ref_words"] for s in rows_s), 4
                )
                if rows_s
                else None,
                "catastrophic": sorted(s["chunk"] for s in rows_s if s["catastrophic"]),
            }
        best = {}
        for items in seeds.values():
            for chunk, (_, s) in items.items():
                if s and (chunk not in best or s["wer"] < best[chunk]["wer"]):
                    best[chunk] = s
        rows.append(
            {
                "arm": arm,
                "voice": voice,
                "seeds": per_seed,
                "best_of_seeds": {
                    "chunks": len(best),
                    "wer_whole": round(
                        sum(s["wer"] * s["ref_words"] for s in best.values())
                        / sum(s["ref_words"] for s in best.values()),
                        4,
                    )
                    if best
                    else None,
                    "catastrophic": sorted(c for c, s in best.items() if s["catastrophic"]),
                },
            }
        )
    return {"chunk_count": len(chunks), "arms": rows}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("chunks", help="print the fixed chunk list and its sha256")
    c.add_argument("--text", default=str(TEXT))
    r = sub.add_parser("run", help="render one arm, voice and seed list")
    r.add_argument("--text", default=str(TEXT))
    r.add_argument("--endpoint", required=True, help="the speech server's base URL (loopback or a tunnel)")
    r.add_argument("--model", required=True)
    r.add_argument("--arm", required=True)
    r.add_argument("--voice", required=True, help="the voice id (recorded; the clip is what the engine hears)")
    r.add_argument("--clip", required=True, help="the reference WAV (private path, never recorded)")
    r.add_argument("--transcript", required=True, help="its verified transcript (private path, never recorded)")
    r.add_argument("--seed", type=int, action="append", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--lang-code", default="en")
    r.add_argument("--chunks", type=int, default=0, help="only the first N chunks (a smoke run)")
    r.add_argument("--timeout", type=float, default=900.0)
    r.add_argument("--stop-on-error", action="store_true")
    s = sub.add_parser("score", help="whisper round trip and the summary")
    s.add_argument("--text", default=str(TEXT))
    s.add_argument("--out", required=True)
    s.add_argument("--whisper-model", required=True)
    s.add_argument("--threads", type=int, default=MAX_THREADS)
    args = parser.parse_args(argv)
    if args.command == "chunks":
        chunks = chunk_list(Path(args.text).read_text(encoding="utf-8"))
        print(
            json.dumps(
                {"limit": LIMIT, "count": len(chunks), "sha256": chunk_digest(chunks), "chunks": chunks},
                ensure_ascii=False,
                indent=1,
            )
        )
        return 0
    return run(args) if args.command == "run" else score(args)


if __name__ == "__main__":
    sys.exit(main())
