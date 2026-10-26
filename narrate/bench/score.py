"""Score a narrate bench window's outputs off the GPU, on the dev host: `just narrate-bench-score SRC DEST`.

Reads DEST/<arm>/receipt.json (narrate/bench/host_run.py) and every chunk WAV it names, and writes DEST/scored.json
and DEST/scored.md. Per chunk: WER of whisper's read-back against the chunk text (narrate.qa: condense's whisper
path, the registered small.en model, numbers compared as digits on both sides), the longest silent run, and
the catastrophic flags of the bench plan (chunk WER over 30%, silence over 2 s, longer than twice the expected
duration at 150 words per minute, or a chunk missing). Per pass: whole-text WER over the joined read-backs, the
worst chunk WER, catastrophic count, RTF and load time from the receipt. Per arm: peak VRAM above the idle
baseline. With --decoys, decoys 4 and 5 are rebuilt from one chunk of --decoy-arm (half silence, time reversal,
shuffled transcript) and must land on their expected side.

SIM (narrate/sim.py, the registered ECAPA model) needs --reference (the clip the window conditioned on; its sha256
must equal the window's inputs-verified.json voice.wav when that file is present), --sim-model and an interpreter
with torch and speechbrain (--sim-python or NARRATE_SIM_PYTHON; on the shared CPU host, inside a 6G memory scope).
Per pass: each chunk against the reference, the median and minimum, and wSIM, the minimum over 10 s windows (5 s
hop) of the pass's chunks joined in order, skipping windows with too little voice. Two scorer checks of the bench
plan run in the same scoring pass: decoy 1, the reference's second half against its first half (expected at least
SIM_SELF_MIN), and decoy 2, the passes the window rendered with a preset voice and no reference (a different
speaker: expected median below SIM_BAR and at least SIM_DECOY_MARGIN below decoy 1). When both are valid, each
pass is read against the preregistered bars: median at least SIM_BAR and SIM_DECOY_MARGIN above decoy 2, wSIM
minimum at least WSIM_RATIO times the median. Without any input SIM is not_measured with the reason.

The destination must lie outside every git work tree (voice renders never enter git); --pull SRC copies a window's
run directory there first. A receipt whose chunks_sha256 is not the committed chunk list's is not scored, and a
chunk WAV whose sha256 differs from its receipt is flagged digest_mismatch instead of scored.

Without whisper-cli (nix develop .#condense) or the model, WER is not_measured and catastrophic counts cover
only silence, duration and missing chunks. Measurements only: the bars and the pick are read by a person against
the preregistration (docs/agent-notes/2026-10-22-narrate-bench-plan.md), and listening is a separate state.
"""

import argparse
import array
import hashlib
import json
import os
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from narrate import audio, qa  # noqa: E402
from narrate import sim as simlib  # noqa: E402
from narrate.config import SIM, WHISPER, WHISPER_ENVS  # noqa: E402

CHUNKS = Path(__file__).resolve().parent / "chunks-v1.json"
MAX_CHUNK_WER = 0.30
MAX_SILENCE_S = 2.0
MAX_DURATION_RATIO = 2.0
FRAME_S = 0.05
SILENCE_DBFS = -50.0
# SIM bars preregistered in the bench plan ("Bars": median chunk SIM at least 0.45 and 0.15 above the preset-voice
# decoy; wSIM minimum at least 0.8 times the median). SIM_SELF_MIN reads decoy 1's "well above the SIM bar" as the
# bar plus the decoy margin. Where measurements sit against them (docs/agent-notes/2026-10-26-narrate-sim.md): the
# synthetic formant voices of narrate/tests/test_tools_sim.py score 0.95 for the same tract and 0.60 and 0.40 for
# its two decoys, so the absolute bar alone does not reject a near voice; the real-voice controls (self-match,
# preset-voice decoy, the same speaker on another microphone) are private and recorded on the tracker.
SIM_BAR, SIM_DECOY_MARGIN, WSIM_RATIO = 0.45, 0.15, 0.8
SIM_SELF_MIN = SIM_BAR + SIM_DECOY_MARGIN


def config(whisper_model=None, sim_model=None, sim_python=None, sim_threads=None):
    model = whisper_model or next((os.environ[e] for e in WHISPER_ENVS if os.environ.get(e)), WHISPER["model"])
    model = Path(model) if Path(model).is_absolute() else ROOT / model
    sim = dict(SIM)
    if sim_model:
        sim["model"] = str(sim_model)
    if sim_python:
        sim["python"] = str(sim_python)
    if sim_threads is not None:
        sim["threads"] = sim_threads
    return SimpleNamespace(whisper=dict(WHISPER), whisper_model=model, sim=sim, base=Path.cwd())


def inside_git(path):
    """The work tree root above path (a .git file or directory), or None."""
    path = Path(path).resolve()
    for parent in (path, *path.parents):
        if (parent / ".git").exists():
            return parent
    return None


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_pcm(path, work):
    return audio.canonical(Path(path).read_bytes(), None, work)[0]


def longest_silence(pcm):
    """Seconds of the longest run of 50 ms frames below -50 dBFS, anywhere in the take."""
    frame = max(1, round(FRAME_S * pcm.rate))
    threshold = 32768 * 10 ** (SILENCE_DBFS / 20)
    longest = run = 0
    samples = pcm.samples
    for start in range(0, len(samples), frame):
        block = samples[start : start + frame]
        rms = (sum(v * v for v in block) / len(block)) ** 0.5 if block else 0
        run = run + 1 if rms < threshold else 0
        longest = max(longest, run)
    return round(longest * frame / pcm.rate, 2)


class Reader:
    def __init__(self, cfg):
        self.whisper = qa.Whisper(cfg)
        self.ok, self.why = self.whisper.available()

    def read(self, pcm):
        return self.whisper.read(pcm) if self.ok else None


class Sim:
    """narrate/sim.py's scorer against one reference clip, or the reason SIM is not measured."""

    def __init__(self, cfg, reference, work, expected_sha256=None):
        self.scorer, self.reference, self.why, self.binding = None, None, None, None
        if reference is None:
            self.why = "no --reference clip given"
            return
        if not Path(reference).is_file():
            self.why = f"the --reference clip {Path(reference).name} is absent"
            return
        digest = sha256_file(reference)
        if expected_sha256 is not None and digest != expected_sha256:
            self.why = f"--reference sha256 {digest[:12]} is not the window's voice.wav {expected_sha256[:12]}"
            return
        self.binding = {
            "ref_clip_sha256": digest,
            "window_voice_wav": "matched" if expected_sha256 else "no inputs-verified.json voice.wav to compare",
        }
        try:
            scorer = simlib.Scorer(cfg)
        except ValueError as error:
            self.why = str(error)
            return
        ok, why = scorer.available()
        if not ok:
            self.why = why
            return
        work = Path(work)
        self.reference = simlib.to16k(reference, work / "reference.16k.wav")
        ref = audio.read(self.reference)
        half = len(ref.samples) // 2
        self.halves = (
            audio.Pcm(ref.rate, ref.samples[:half]).write(work / "reference.first.wav"),
            audio.Pcm(ref.rate, ref.samples[half:]).write(work / "reference.second.wav"),
        )
        self.scorer = scorer

    def score(self, pairs):
        """{id: value} or None; pairs [(id, wav)] each scored against the reference."""
        if self.scorer is None or not pairs:
            return None
        try:
            rows = self.scorer.score([(i, a, self.reference) for i, a in pairs])
        except (RuntimeError, OSError, ValueError) as error:
            self.why = f"SIM scorer failed: {error}"
            self.scorer = None
            return None
        return {i: rows[i]["sim"] for i, _ in pairs}

    def self_match(self):
        """Decoy 1: the reference's second half against its first half, or None."""
        if self.scorer is None:
            return None
        try:
            rows = self.scorer.score([("self", self.halves[1], self.halves[0])])
        except (RuntimeError, OSError, ValueError) as error:
            self.why = f"SIM scorer failed: {error}"
            self.scorer = None
            return None
        return rows["self"]["sim"]

    def status(self):
        if self.scorer is None:
            return qa.not_measured(self.why)
        return {"status": "measured", **self.scorer.identity(), "reference": self.binding}


def pass_windows(pieces, work, name):
    """wSIM windows over a pass's chunk takes joined in order: [(id, wav)], and the count skipped as silent."""
    pieces = [p for p in pieces if p.seconds > 0]
    if not pieces or len({p.rate for p in pieces}) != 1:
        return [], 0
    track = audio.Pcm(pieces[0].rate)
    for piece in pieces:
        track.extend(piece)
    out, silent = [], 0
    for k, start in enumerate(simlib.window_starts(track.seconds)):
        if not simlib.wsim_voiced(track, start):
            silent += 1
            continue
        a = round(start * track.rate)
        b = min(len(track.samples), a + round(simlib.WINDOW_S * track.rate))
        wid = f"{name}/window-{k}"
        out.append((wid, audio.Pcm(track.rate, track.samples[a:b]).write(Path(work) / f"{name}-window-{k}.wav")))
    return out, silent


def score_chunk(path, text, expected_s, reader, work):
    pcm = load_pcm(path, work)
    s16 = Path(work) / f"{Path(path).parent.name}-{Path(path).stem}.s16.wav"  # pass directory: names stay unique
    pcm.write(s16)
    heard = reader.read(pcm)
    row = {"audio_s": round(pcm.seconds, 3), "longest_silence_s": longest_silence(pcm), "s16": s16, "pcm": pcm}
    row["wer"] = qa.wer(text, heard) if heard is not None else None
    row["heard"] = heard
    flags = []
    if row["wer"] is not None and row["wer"] > MAX_CHUNK_WER:
        flags.append("wer")
    if row["longest_silence_s"] > MAX_SILENCE_S:
        flags.append("silence")
    if expected_s and pcm.seconds > MAX_DURATION_RATIO * expected_s:
        flags.append("too_long")
    row["catastrophic"] = flags
    return row


def score_pass(arm_dir, record, chunks_by_id, reader, sim, work):
    rows, texts, heard = [], [], []
    for chunk_id in record["expected_chunks"]:
        chunk = chunks_by_id[chunk_id]
        done = next((c for c in record["chunks"] if c["chunk"] == chunk_id and "audio_s" in c), None)
        if done is None:
            rows.append({"chunk": chunk_id, "catastrophic": ["missing"]})
            continue
        path = arm_dir / record["name"] / done["file"]
        if not path.is_file() or sha256_file(path) != done.get("sha256"):
            rows.append({"chunk": chunk_id, "catastrophic": ["digest_mismatch"]})
            continue
        row = score_chunk(path, chunk["text"], chunk["expected_s"], reader, work)
        row["chunk"] = chunk_id
        rows.append(row)
        texts.append(chunk["text"])
        heard.append(row.pop("heard") or "")
    tag = f"{arm_dir.name}/{record['name']}"
    windows, silent = pass_windows([r["pcm"] for r in rows if "pcm" in r], work, tag.replace("/", "-"))
    sims = sim.score([(r["chunk"], r["s16"]) for r in rows if "s16" in r] + windows)
    for r in rows:
        r.pop("s16", None)
        r.pop("pcm", None)
        if sims is not None and r["chunk"] in sims:
            r["sim"] = sims[r["chunk"]]
    measured = [r["wer"] for r in rows if r.get("wer") is not None]
    out = {
        "pass": record["name"],
        "variant": record.get("variant"),
        "complete": record.get("complete"),
        "chunks_done": record.get("chunks_done"),
        "chunks_total": len(record["expected_chunks"]),
        "audio_s": record.get("audio_s"),
        "synth_wall_s": record.get("synth_wall_s"),
        "rtf": record.get("rtf"),
        "load_s": record.get("load_s"),
        "catastrophic": sum(1 for r in rows if r["catastrophic"]),
        "wer_whole": qa.wer(" ".join(texts), " ".join(heard)) if reader.ok and texts else None,
        "wer_max_chunk": max(measured) if measured else None,
        "chunks": rows,
    }
    values = [r["sim"] for r in rows if "sim" in r]
    if values:
        wsim = [sims[w] for w, _ in windows]
        out["sim"] = {
            "status": "measured",
            "median": round(statistics.median(values), 4),
            "min": min(values),
            "wsim": {
                "window_s": simlib.WINDOW_S,
                "hop_s": simlib.HOP_S,
                "windows": len(wsim),
                "skipped_silent": silent,
                "min": min(wsim) if wsim else None,
            },
        }
    elif sim.scorer is not None:
        out["sim"] = qa.not_measured("no chunk of this pass was scored")
    else:
        out["sim"] = sim.status()
    if record.get("decoy"):
        out["decoy"] = record["decoy"]
    return out


def sim_checks(doc, self_sim):
    """Decoys 1 and 2 of the bench plan, then each non-decoy pass read against the SIM bars (in place)."""
    passes = [p for arm in doc["arms"] for p in arm.get("passes", [])]
    wrong = [p["sim"]["median"] for p in passes if p.get("decoy") and p["sim"].get("status") == "measured"]
    checks = {
        "1-reference-self-match": {
            "observed": self_sim,
            "expected": f"at least {SIM_SELF_MIN:.2f}",
            "valid": None if self_sim is None else self_sim >= SIM_SELF_MIN,
        }
    }
    decoy = statistics.median(wrong) if wrong else None
    checks["2-wrong-speaker"] = {
        "observed": None if decoy is None else round(decoy, 4),
        "passes": len(wrong),
        "expected": f"median below {SIM_BAR:.2f} and at least {SIM_DECOY_MARGIN:.2f} below decoy 1",
        "valid": None
        if decoy is None or self_sim is None
        else decoy < SIM_BAR and decoy <= self_sim - SIM_DECOY_MARGIN,
    }
    usable = all(c["valid"] for c in checks.values())
    for p in passes:
        s = p["sim"]
        if p.get("decoy") or s.get("status") != "measured" or "wsim" not in s:
            continue
        wmin = s["wsim"]["min"]
        s["bars"] = {
            "decoy_checks_valid": usable,
            "median_at_least_bar": s["median"] >= SIM_BAR,
            "over_decoy": None if decoy is None else round(s["median"] - decoy, 4),
            "over_decoy_ok": None if decoy is None else s["median"] - decoy >= SIM_DECOY_MARGIN,
            "wsim_ratio": None if wmin is None or s["median"] <= 0 else round(wmin / s["median"], 4),
            "wsim_ok": None if wmin is None else wmin >= WSIM_RATIO * s["median"],
        }
    return checks


def decoys(arm_dir, receipt, chunks, reader, work):
    """Decoys 4 and 5 rebuilt from the first chunk of the arm's first complete full pass."""
    record = next((p for p in receipt["passes"] if p["name"].startswith("seed") and p["complete"]), None)
    if record is None or len(chunks) < 2:
        return [{"decoy": "4/5", "valid": None, "reason": "no complete full pass to build from"}]
    first, other = chunks[0], chunks[1]
    pcm = load_pcm(arm_dir / record["name"] / record["chunks"][0]["file"], work)
    half = len(pcm.samples) // 2
    silenced = audio.Pcm(pcm.rate, array.array("h", list(pcm.samples[:half]) + [0] * (len(pcm.samples) - half)))
    reversed_pcm = audio.Pcm(pcm.rate, array.array("h", reversed(pcm.samples)))
    out = []
    for name, take, text in (
        ("4-half-silence", silenced, first["text"]),
        ("4-reversed", reversed_pcm, first["text"]),
        ("5-shuffled-transcript", pcm, other["text"]),
    ):
        path = Path(work) / f"decoy-{name}.wav"
        take.write(path)
        row = score_chunk(path, text, first["expected_s"], reader, work)
        for key in ("s16", "pcm", "heard"):
            row.pop(key)
        flagged = bool(row["catastrophic"]) if name.startswith("4") else (row["wer"] or 0) > MAX_CHUNK_WER
        measurable = reader.ok or name == "4-half-silence"
        out.append(
            {
                "decoy": name,
                "source": f"{receipt['arm']} {record['name']} {first['id']}",
                "expected": "catastrophic" if name.startswith("4") else f"WER over {MAX_CHUNK_WER}",
                "observed": row,
                "valid": flagged if measurable else None,
            }
        )
    return out


def window_voice_sha256(out_dir):
    """The voice.wav sha256 the window verified (inputs-verified.json, else inputs.json), or None."""
    for name in ("inputs-verified.json", "inputs.json"):
        path = Path(out_dir) / name
        if path.is_file():
            entry = (json.loads(path.read_text(encoding="utf-8")).get("verified") or {}).get("voice.wav") or {}
            if entry.get("sha256"):
                return entry["sha256"]
    return None


def fmt(value, digits=3):
    return "" if value is None else (f"{value:.{digits}f}" if isinstance(value, float) else str(value))


def table(doc):
    lines = [
        "| arm | pass | variant | done | audio s | RTF | load s | WER whole | WER max | catastrophic | SIM median |"
        " SIM min | wSIM min | peak VRAM above idle GiB | stop |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for arm in doc["arms"]:
        if "error" in arm:
            lines.append(f"| {arm['arm']} | not scored: {arm['error']} |" + " |" * 13)
            continue
        peak = arm.get("peak_above_baseline_bytes")
        peak = f"{peak / 2**30:.2f}" if peak is not None else ""
        stop = (arm.get("stop") or {}).get("rule", "")
        for p in arm["passes"]:
            s = p["sim"]
            if s.get("status") == "measured":
                sim_text = [fmt(s["median"]), fmt(s["min"]), fmt(s["wsim"]["min"])]
            else:
                sim_text = ["not_measured", "", ""]
            lines.append(
                f"| {arm['arm']} | {p['pass']} | {p['variant'] or ''} | {p['chunks_done']}/{p['chunks_total']} | "
                f"{fmt(p['audio_s'], 1)} | {fmt(p['rtf'], 3)} | {fmt(p['load_s'], 1)} | {fmt(p['wer_whole'], 3)} | "
                f"{fmt(p['wer_max_chunk'], 3)} | {p['catastrophic']} | {' | '.join(sim_text)} | {peak} | {stop} |"
            )
    lines.append("")
    s = doc["sim"]
    lines.append(f"WER: {doc['wer']}.")
    if s.get("status") == "measured":
        model = f"{s['model_id']} (sha256 {s['model_sha256'][:12]})"
        lines.append(f"SIM: {model}, {s['threads']} threads, bars {s['bars']}.")
    else:
        lines.append(f"SIM: not_measured: {s.get('reason')}.")
    for name, check in (s.get("checks") or {}).items():
        observed = fmt(check["observed"])
        lines.append(f"SIM decoy {name}: observed {observed}, expected {check['expected']}, valid {check['valid']}")
    for d in doc.get("decoys", []):
        lines.append(f"Decoy {d['decoy']}: expected {d.get('expected')}, valid {d['valid']}")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out_dir", type=Path, help="a window's runs/<holder> directory, outside any git work tree")
    parser.add_argument("--pull", metavar="SRC", help="rsync SRC (host:dir or a directory) into out_dir first")
    parser.add_argument("--whisper-model", type=Path)
    parser.add_argument("--sim-model", type=Path, help="the registered ECAPA embedding_model.ckpt")
    parser.add_argument("--sim-python", type=Path, help="interpreter with torch and speechbrain (NARRATE_SIM_PYTHON)")
    parser.add_argument("--sim-threads", type=int, help="SIM worker CPU threads, 1 to 8 (default 4)")
    parser.add_argument("--reference", type=Path, help="the voice's reference clip, for SIM (private)")
    parser.add_argument("--arm", action="append", default=[], help="score only these arms")
    parser.add_argument("--decoys", action="store_true", help="rebuild and score decoys 4 and 5")
    parser.add_argument("--decoy-arm", default="A2-gpu-alt")
    args = parser.parse_args(argv)

    tree = inside_git(args.out_dir if args.out_dir.exists() else args.out_dir.parent)
    if tree is not None:
        print(
            f"score: refused: {args.out_dir} is inside a git work tree; score outside the repository", file=sys.stderr
        )
        return 2
    if args.pull:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(["rsync", "-a", args.pull.rstrip("/") + "/", str(args.out_dir) + "/"], check=True)
    chunk_doc = json.loads(CHUNKS.read_text(encoding="utf-8"))
    chunks_by_id = {c["id"]: c for c in chunk_doc["chunks"]}
    cfg = config(args.whisper_model, args.sim_model, args.sim_python, args.sim_threads)
    reader = Reader(cfg)
    receipts = sorted(args.out_dir.glob("*/receipt.json"))
    doc = {
        "schema": "narrate-bench-scored/1",
        "chunks_sha256": chunk_doc["chunks_sha256"],
        "wer": {"status": "measured", **reader.whisper.identity()} if reader.ok else qa.not_measured(reader.why),
        "sim": None,
        "rules": {
            "max_chunk_wer": MAX_CHUNK_WER,
            "max_silence_s": MAX_SILENCE_S,
            "silence_dbfs": SILENCE_DBFS,
            "max_duration_ratio": MAX_DURATION_RATIO,
        },
        "arms": [],
    }
    with tempfile.TemporaryDirectory() as work:
        sim = Sim(cfg, args.reference, work, window_voice_sha256(args.out_dir))
        for path in receipts:
            receipt = json.loads(path.read_text(encoding="utf-8"))
            if args.arm and receipt["arm"] not in args.arm:
                continue
            listed = (receipt.get("chunk_list") or {}).get("chunks_sha256")
            if listed != chunk_doc["chunks_sha256"]:
                doc["arms"].append(
                    {"arm": receipt["arm"], "error": f"chunks_sha256 {listed} is not the committed list"}
                )
                continue
            arm_dir = path.parent
            vram = receipt.get("vram", {})
            arm = {
                "arm": receipt["arm"],
                "variant": receipt.get("variant"),
                "stop": receipt.get("stop"),
                "peak_bytes": vram.get("peak_bytes"),
                "peak_above_baseline_bytes": vram.get("peak_above_baseline_bytes"),
                "passes": [],
            }
            for record in receipt["passes"]:
                record["expected_chunks"] = record.get("chunk_ids") or [c["chunk"] for c in record["chunks"]]
                arm["passes"].append(score_pass(arm_dir, record, chunks_by_id, reader, sim, work))
            doc["arms"].append(arm)
            if args.decoys and receipt["arm"] == args.decoy_arm:
                doc["decoys"] = decoys(arm_dir, receipt, chunk_doc["chunks"], reader, work)
        self_sim = sim.self_match()
        doc["sim"] = {
            **sim.status(),
            "bars": {"bar": SIM_BAR, "decoy_margin": SIM_DECOY_MARGIN, "wsim_ratio": WSIM_RATIO},
        }
        if sim.scorer is not None:
            doc["sim"]["checks"] = sim_checks(doc, self_sim)
    (args.out_dir / "scored.json").write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    text = table(doc)
    (args.out_dir / "scored.md").write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
