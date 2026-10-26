#!/usr/bin/env python3
"""Cut a bench arm's voice reference to fit its engine: a time-aligned sub-clip of the consented clip, cut at word
boundaries, with the verified transcript cut at the same words. Runs on the dev host, never on the GPU host, and
never runs a TTS model.

    ref_cut.py words CLIP --out WORDS.json [--model M] [--threads 4]
    ref_cut.py cut CLIP TEXT --words WORDS.json --max-s S [--min-s S] [--capacity-samples N --encoder-rate R
        --pad-samples P] --out-wav OUT.wav --out-text OUT.txt --record OUT.cut.json

`words` reads the clip's word timings with whisper-cli (DTW word onsets, -t 4 at most): ffmpeg makes a 16 kHz mono
analysis copy in a temporary directory, and condense.events.words_from turns whisper's full JSON into [{start, end,
word}]. It refuses a model whose sha256 is not program/models.json's ggerganov-whisper-cpp-ggml-small.en (the
model -dtw small.en assumes), and refuses to start outside a memory limit of at most 6 GiB on its own cgroup or an
ancestor, with swap off: run it one process at a time as
`systemd-run --user --scope -p MemoryMax=6G -p MemorySwapMax=0 nice -n 19 ionice -c3 ...`.

`cut` is standard library only. It aligns the verified transcript's words to whisper's (difflib on lowercased
alphanumerics), and considers a cut that starts before verified word i and ends after verified word j when both are
matched words whose outer neighbours are matched to the adjacent whisper words (so no untranscribed or unheard word
sits in the gap). Inside the cut, at least 85% of the verified words i..j must be matched (matched_ratio), and at
least 85% of the whisper words between the ones i and j map to must be matched too (heard_ratio), so speech whisper
heard that the transcript lacks counts against the cut. Each cut point is the quietest 10 ms frame (nearest the
gap's middle among equals) of the gap between the whisper word and its neighbour, and must lie within 12 dB of the
clip's 10th-percentile frame level, so a cut lands in a pause, not in a word. Among the cuts that last from --min-s
to --max-s seconds, whose words pass both ratios, and whose encoder input fits (--capacity-samples: the clip
resampled to --encoder-rate and padded up to a multiple of --pad-samples, as audio.cpp's VoxCPM2 AudioVAE encoder
does), it takes the one with the best boundaries, then the longest. A boundary scores 2 at a sentence end (. ! ?), 1
at a clause end (, ; : or a dash) and 0 between other words; cuts rank by the sum of both scores, then by the end's
score (the continuation prompt ends there). The cut copies the source PCM frames unchanged (same rate, channels,
sample format and fmt chunk; no fade, no resampling) and checks the copy byte for byte; the transcript cut is
verified words i..j, joined by single spaces. The WAV and transcript are written to temporary names beside their
targets, checked, then renamed, and the record is written last: a refused run leaves every output as it was.

Every output is private: the clip, the transcript, the word timings and the record all stay outside git (the
voice store). The record names files by basename and sha256 and holds times, word indices and counts, never the
transcript; nothing here prints transcript text.
"""

import argparse
import array
import difflib
import hashlib
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRAME_S = 0.010
QUIET_DB = 12.0  # a cut point is at most this far above the clip's 10th-percentile frame level
MIN_MATCHED = 0.85
EDGE_S = 0.02  # how far a cut window may reach into the words on either side of a gap
SENTENCE_END = (".", "!", "?")
CLAUSE_END = (",", ";", ":", "-", "\u2014", "\u2013")
SCORE = {"sentence": 2, "clause": 1, "word": 0}
WHISPER_MODEL = "models/ggerganov-whisper-cpp-ggml-small.en.bin"
WHISPER_MODEL_ID = "ggerganov-whisper-cpp-ggml-small.en"  # -dtw small.en is this model's alignment heads
MODELS = ROOT / "program" / "models.json"
MAX_THREADS = 4
MAX_SCOPE_BYTES = 6 << 30
CGROUP_ROOT = Path("/sys/fs/cgroup")
SCOPE_HINT = "systemd-run --user --scope -p MemoryMax=6G -p MemorySwapMax=0 nice -n 19 ionice -c3"


class CutError(ValueError):
    """No cut satisfies the policy, or an input is not what it should be. No output file was written or replaced."""


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


# --- WAV --------------------------------------------------------------------------------------------------------


def read_wav(path):
    """{"fmt", "tag", "channels", "rate", "bits", "block", "pcm"} of an integer PCM WAV (plain or extensible)."""
    data = Path(path).read_bytes()
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise CutError(f"{Path(path).name} is not a RIFF WAVE file")
    pos, fmt, pcm = 12, None, None
    while pos + 8 <= len(data):
        cid, size = data[pos : pos + 4], struct.unpack("<I", data[pos + 4 : pos + 8])[0]
        body = data[pos + 8 : pos + 8 + size]
        if cid == b"fmt ":
            fmt = body
        elif cid == b"data":
            pcm = body
            break
        pos += 8 + size + (size & 1)
    if fmt is None or pcm is None or len(fmt) < 16:
        raise CutError(f"{Path(path).name} has no fmt and data chunk")
    tag, channels, rate, _byte_rate, block, bits = struct.unpack("<HHIIHH", fmt[:16])
    if tag == 0xFFFE and len(fmt) >= 40:
        tag = struct.unpack("<H", fmt[24:26])[0]  # the extensible format's sub-format GUID starts with the tag
    if tag != 1 or bits not in (16, 24, 32) or not channels or block != channels * bits // 8:
        raise CutError(f"{Path(path).name}: integer PCM at 16, 24 or 32 bits only (tag {tag}, {bits} bits)")
    pcm = pcm[: len(pcm) - len(pcm) % block]
    return {"fmt": fmt, "channels": channels, "rate": rate, "bits": bits, "block": block, "pcm": pcm}


def wav_bytes(fmt, pcm):
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt + (b"\0" if len(fmt) & 1 else b"")
    body += b"data" + struct.pack("<I", len(pcm)) + pcm + (b"\0" if len(pcm) & 1 else b"")
    return b"RIFF" + struct.pack("<I", len(body)) + body


def frames_of(info):
    return len(info["pcm"]) // info["block"]


def mono_samples(info):
    """Channel-averaged samples as floats in [-1, 1)."""
    bits, channels, pcm = info["bits"], info["channels"], info["pcm"]
    if bits in (16, 32):
        raw = array.array("h" if bits == 16 else "i", pcm)
        if sys.byteorder != "little":
            raw.byteswap()
    else:
        n = len(pcm) // 3
        padded = bytearray(4 * n)  # each 24-bit sample into the top three bytes of an int32, then shifted back
        padded[1::4], padded[2::4], padded[3::4] = pcm[0::3], pcm[1::3], pcm[2::3]
        raw = array.array("i", bytes(padded))
        if sys.byteorder != "little":
            raw.byteswap()
        raw = array.array("i", (v >> 8 for v in raw))
    scale = float(1 << (bits - 1))
    if channels == 1:
        return [v / scale for v in raw]
    return [sum(raw[i : i + channels]) / channels / scale for i in range(0, len(raw), channels)]


def frame_levels(info, frame_s=FRAME_S):
    """dBFS of each frame_s frame (RMS), from the start of the clip."""
    samples = mono_samples(info)
    hop = max(1, round(frame_s * info["rate"]))
    out = []
    for start in range(0, len(samples), hop):
        part = samples[start : start + hop]
        power = sum(v * v for v in part) / len(part)
        out.append(10 * math.log10(power) if power > 1e-12 else -120.0)
    return out


# --- alignment and the cut --------------------------------------------------------------------------------------


def norm(word):
    return "".join(ch for ch in word.lower() if ch.isalnum())


def align(tokens, words):
    """[whisper index or None] for each verified token: the tokens difflib matches to whisper's words."""
    left = [norm(t) for t in tokens]
    right = [norm(w["word"]) for w in words]
    mapping = [None] * len(tokens)
    matcher = difflib.SequenceMatcher(None, left, right, autojunk=False)
    for a, b, size in matcher.get_matching_blocks():
        for k in range(size):
            if left[a + k]:
                mapping[a + k] = b + k
    return mapping


def quietest(levels, lo_s, hi_s, frame_s=FRAME_S):
    """(time, dBFS) at the centre of the quietest frame between lo_s and hi_s, or None."""
    lo, hi = max(0, int(lo_s / frame_s)), min(len(levels) - 1, int(math.ceil(hi_s / frame_s)))
    if hi < lo:
        return None
    middle = (lo + hi) / 2
    best = min(range(lo, hi + 1), key=lambda k: (levels[k], abs(k - middle), k))
    return (best + 0.5) * frame_s, levels[best]


def kind_after(tokens, j):
    """The boundary after verified token j: sentence, clause or word."""
    token = tokens[j].rstrip("\"')]\u201d\u2019")
    return "sentence" if token.endswith(SENTENCE_END) else "clause" if token.endswith(CLAUSE_END) else "word"


def kind_before(tokens, i):
    return "sentence" if i == 0 else kind_after(tokens, i - 1)


def encoder_fit(frames, rate, encoder):
    """The encoder's padded input length for a clip of frames at rate, and whether it fits; None without one."""
    if not encoder:
        return None
    resampled = math.ceil(frames * encoder["rate"] / rate)  # soxr ExactExpected: ceil(n * out / in)
    pad = int(encoder["pad_samples"])
    padded = -(-resampled // pad) * pad
    return {
        "rate": int(encoder["rate"]),
        "resampled_samples": resampled,
        "padded_samples": padded,
        "capacity_samples": int(encoder["capacity_samples"]),
        "fits": padded <= int(encoder["capacity_samples"]),
    }


def plan(info, tokens, words, max_s, min_s, encoder=None):
    """The chosen cut: frame range, word range, boundary kinds and levels, encoder fit."""
    if not tokens:
        raise CutError("the verified transcript is empty")
    if not words:
        raise CutError("no word timings")
    rate, total = info["rate"], frames_of(info)
    duration = total / rate
    levels = frame_levels(info)
    floor = sorted(levels)[len(levels) // 10]
    quiet_max = floor + QUIET_DB
    mapping = align(tokens, words)
    matched = [i for i, w in enumerate(mapping) if w is not None]
    if not matched:
        raise CutError("no verified word matches a whisper word")
    starts, ends = [], []
    last = len(tokens) - 1
    for i in matched:
        w = mapping[i]
        # a gap is trusted only between a matched word and its matched neighbour: an unmatched verified word, or
        # one whisper heard that the transcript lacks, may lie in it
        start_ok = i == 0 or mapping[i - 1] == w - 1
        end_ok = i == last or mapping[i + 1] == w + 1
        prev_end = words[w - 1]["end"] if w > 0 else 0.0
        point = quietest(levels, min(prev_end, words[w]["start"]) - EDGE_S, words[w]["start"] + EDGE_S)
        if start_ok and point and point[1] <= quiet_max:
            starts.append((i, point, kind_before(tokens, i)))
        next_start = words[w + 1]["start"] if w + 1 < len(words) else duration
        point = quietest(levels, words[w]["end"] - EDGE_S, max(next_start, words[w]["end"]) + EDGE_S)
        if end_ok and point and point[1] <= quiet_max:
            ends.append((i, point, kind_after(tokens, i)))
    prefix = [0]
    for w in mapping:
        prefix.append(prefix[-1] + (w is not None))
    heard = [False] * len(words)
    for w in matched:
        heard[mapping[w]] = True
    heard_prefix = [0]
    for h in heard:
        heard_prefix.append(heard_prefix[-1] + h)
    ranked = []
    for i, (t0, db0), k0 in starts:
        for j, (t1, db1), k1 in ends:
            if j < i:
                continue
            a, b = round(t0 * rate), min(total, round(t1 * rate))
            seconds = (b - a) / rate
            if b <= a or not min_s <= seconds <= max_s:
                continue
            ratio = (prefix[j + 1] - prefix[i]) / (j + 1 - i)
            if ratio < MIN_MATCHED:
                continue
            wi, wj = mapping[i], mapping[j]
            heard_ratio = (heard_prefix[wj + 1] - heard_prefix[wi]) / (wj + 1 - wi)
            if heard_ratio < MIN_MATCHED:
                continue  # whisper heard words inside the cut that its transcript lacks
            fit = encoder_fit(b - a, rate, encoder)
            if fit is not None and not fit["fits"]:
                continue
            rank = (SCORE[k0] + SCORE[k1], SCORE[k1])
            ranked.append((rank, seconds, -i, -j, (i, j, a, b, k0, k1, db0, db1, ratio, heard_ratio, fit)))
    if not ranked:
        raise CutError(
            f"no cut of {min_s}-{max_s} s at quiet word boundaries fits the policy "
            f"({len(starts)} start and {len(ends)} end candidates, clip {duration:.2f} s)"
        )
    i, j, a, b, k0, k1, db0, db1, ratio, heard_ratio, fit = max(ranked)[4]
    return {
        "start_frame": a,
        "end_frame": b,
        "start_s": round(a / rate, 4),
        "end_s": round(b / rate, 4),
        "seconds": round((b - a) / rate, 4),
        "word_range": [i, j],
        "words": j + 1 - i,
        "start_boundary": k0,
        "end_boundary": k1,
        "start_dbfs": round(db0, 1),
        "end_dbfs": round(db1, 1),
        "floor_dbfs": round(floor, 1),
        "matched_ratio": round(ratio, 3),
        "heard_ratio": round(heard_ratio, 3),
        "encoder": fit,
        "candidates": len(ranked),
    }


def load_words(path):
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    words = doc["words"] if isinstance(doc, dict) else doc
    for w in words:
        if not (isinstance(w, dict) and isinstance(w.get("word"), str) and w["end"] >= w["start"] >= 0):
            raise CutError(f"{Path(path).name}: every word needs start <= end and a word")
    return doc if isinstance(doc, dict) else {"words": words}, words


def cut(args):
    clip, text = Path(args.clip), Path(args.text)
    info = read_wav(clip)
    tokens = text.read_text(encoding="utf-8").split()
    words_doc, words = load_words(args.words)
    if words_doc.get("clip_sha256") and words_doc["clip_sha256"] != sha256_file(clip):
        raise CutError(f"{Path(args.words).name} was read from another clip (clip_sha256 differs)")
    encoder = None
    if args.capacity_samples:
        encoder = {
            "rate": args.encoder_rate,
            "pad_samples": args.pad_samples,
            "capacity_samples": args.capacity_samples,
        }
    chosen = plan(info, tokens, words, args.max_s, args.min_s, encoder)
    a, b = chosen["start_frame"] * info["block"], chosen["end_frame"] * info["block"]
    pcm = info["pcm"][a:b]
    out_wav, out_text, record_path = Path(args.out_wav), Path(args.out_text), Path(args.record)
    for path in (out_wav, out_text, record_path):
        if path.exists() and not args.force:
            raise CutError(f"{path.name} exists; pass --force to replace it")
    i, j = chosen["word_range"]
    temps = {path: path.with_name(f".{path.name}.{os.getpid()}.tmp") for path in (out_wav, out_text, record_path)}
    try:
        temps[out_wav].write_bytes(wav_bytes(info["fmt"], pcm))
        temps[out_text].write_text(" ".join(tokens[i : j + 1]) + "\n", encoding="utf-8")
        copy = read_wav(temps[out_wav])
        if copy["pcm"] != pcm or copy["fmt"] != info["fmt"]:
            raise CutError("the written cut is not the source frames")
        record = cut_record(args, clip, text, info, tokens, words_doc, encoder, chosen, temps, out_wav, out_text)
        temps[record_path].write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
        for path in (out_wav, out_text, record_path):  # the record last: it names outputs already in place
            os.replace(temps[path], path)
    finally:
        for temp in temps.values():
            temp.unlink(missing_ok=True)
    return record


def cut_record(args, clip, text, info, tokens, words_doc, encoder, chosen, temps, out_wav, out_text):
    return {
        "schema": "narrate-bench-ref-cut/1",
        "source": {
            "file": clip.name,
            "sha256": sha256_file(clip),
            "rate": info["rate"],
            "channels": info["channels"],
            "bits": info["bits"],
            "seconds": round(frames_of(info) / info["rate"], 4),
            "words": len(tokens),
        },
        "transcript": {"file": text.name, "sha256": sha256_file(text)},
        "word_timings": {
            "file": Path(args.words).name,
            "sha256": sha256_file(args.words),
            "whisper": words_doc.get("whisper"),
        },
        "policy": {"max_s": args.max_s, "min_s": args.min_s, "encoder": encoder},
        "cut": chosen,
        "pcm_copy": "byte-identical source frames; no fade, resampling or level change",
        "outputs": {
            "wav": {"file": out_wav.name, "sha256": sha256_file(temps[out_wav])},
            "text": {"file": out_text.name, "sha256": sha256_file(temps[out_text])},
        },
    }


# --- whisper word timings ---------------------------------------------------------------------------------------


def registered_sha256(model_id=WHISPER_MODEL_ID, models=None):
    """The sha256 program/models.json registers for model_id, or None."""
    try:
        entry = json.loads(Path(models or MODELS).read_text(encoding="utf-8"))["models"][model_id]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not isinstance(entry, dict):
        return None
    return str(entry.get("sha256") or "").lower() or None


def cgroup_limits(cgroup_root=None, proc_cgroup="/proc/self/cgroup"):
    """(tightest memory.max, tightest memory.swap.max) in bytes over this process's cgroup v2 path and its ancestors;
    None for a level with no limit ("max") or a missing file."""
    root = Path(cgroup_root or CGROUP_ROOT)
    try:
        line = next(x for x in Path(proc_cgroup).read_text().splitlines() if x.startswith("0::"))
    except (OSError, StopIteration):
        return None, None
    path = root / line[3:].strip().lstrip("/")
    limits = {"memory.max": None, "memory.swap.max": None}
    while True:
        for name in limits:
            try:
                value = (path / name).read_text().strip()
            except OSError:
                continue
            if value.isdigit() and (limits[name] is None or int(value) < limits[name]):
                limits[name] = int(value)
        if path == root or root not in path.parents:
            break
        path = path.parent
    return limits["memory.max"], limits["memory.swap.max"]


def check_scope():
    """Refuse to run whisper outside a memory limit of at most MAX_SCOPE_BYTES with swap off."""
    memory, swap = cgroup_limits()
    if memory is None or memory > MAX_SCOPE_BYTES or swap != 0:
        raise CutError(
            f"whisper needs a memory scope of at most 6 GiB with swap off (memory.max {memory}, memory.swap.max "
            f"{swap}); run one process at a time under: {SCOPE_HINT} ..."
        )
    return {"memory_max": memory, "memory_swap_max": swap}


def words(args):
    """Word timings of CLIP from whisper-cli; writes {"clip_sha256", "whisper", "words"} to --out."""
    sys.path.insert(0, str(ROOT))
    from condense.events import words_from

    clip = Path(args.clip)
    model = Path(args.model) if Path(args.model).is_absolute() else ROOT / args.model
    if not model.is_file():
        raise CutError(f"no whisper model {model.name}")
    expected = registered_sha256()
    model_sha256 = sha256_file(model)
    if expected is None or model_sha256 != expected:
        raise CutError(
            f"whisper model {model.name} sha256 {model_sha256[:12]} is not program/models.json's {WHISPER_MODEL_ID}"
        )
    out = Path(args.out)
    if out.exists() and not args.force:
        raise CutError(f"{out.name} exists; pass --force to replace it")
    scope = check_scope()
    for tool in ("ffmpeg", "whisper-cli"):
        if not shutil.which(tool):
            raise CutError(f"{tool} is not on PATH (nix develop .#condense)")
    threads = min(int(args.threads), MAX_THREADS)
    with tempfile.TemporaryDirectory(prefix="narrate-ref-words-") as work:
        work = Path(work)
        mono = work / "clip16k.wav"
        subprocess.run(
            ["ffmpeg", "-nostdin", "-v", "error", "-i", str(clip), "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
             str(mono)],
            check=True,
        )  # fmt: skip
        argv = ["whisper-cli", "-m", str(model), "-f", str(mono), "-l", "en", "-t", str(threads), "-ojf", "-np"]
        argv += ["-of", str(work / "words"), "-bs", "1", "-bo", "1", "-nfa", "-dtw", "small.en"]
        subprocess.run(argv, check=True, stdout=subprocess.DEVNULL)
        full = json.loads((work / "words.json").read_text(encoding="utf-8", errors="replace"))
    found = words_from(full, use_dtw=True)
    doc = {
        "schema": "narrate-bench-ref-words/1",
        "clip_sha256": sha256_file(clip),
        "whisper": {
            "model_id": WHISPER_MODEL_ID,
            "model_sha256": model_sha256,
            "threads": threads,
            "dtw": "small.en",
            "scope": scope,
        },
        "words": found,
    }
    out.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    return {"words": len(found), "out": out.name, "whisper_model_sha256": doc["whisper"]["model_sha256"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Cut a bench voice reference at word boundaries.")
    sub = parser.add_subparsers(dest="command", required=True)
    p_words = sub.add_parser("words", help="whisper word timings of a clip (private output)")
    p_words.add_argument("clip")
    p_words.add_argument("--out", required=True)
    p_words.add_argument("--model", default=os.environ.get("NARRATE_WHISPER_MODEL") or WHISPER_MODEL)
    p_words.add_argument("--threads", type=int, default=MAX_THREADS)
    p_words.add_argument("--force", action="store_true")
    p_cut = sub.add_parser("cut", help="cut the clip and its transcript at the same word boundaries")
    p_cut.add_argument("clip")
    p_cut.add_argument("text")
    p_cut.add_argument("--words", required=True)
    p_cut.add_argument("--max-s", type=float, required=True)
    p_cut.add_argument("--min-s", type=float, default=0.0)
    p_cut.add_argument("--capacity-samples", type=int, default=0)
    p_cut.add_argument("--encoder-rate", type=int, default=16000)
    p_cut.add_argument("--pad-samples", type=int, default=1)
    p_cut.add_argument("--out-wav", required=True)
    p_cut.add_argument("--out-text", required=True)
    p_cut.add_argument("--record", required=True)
    p_cut.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = words(args) if args.command == "words" else cut(args)
    except (CutError, OSError, subprocess.CalledProcessError, ValueError, KeyError) as error:
        print(f"ref_cut: refused: {error}", file=sys.stderr)
        return 2
    if args.command == "cut":
        result = {"cut": result["cut"], "outputs": result["outputs"]}
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
