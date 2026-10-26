"""Score a narrate bench window's outputs off the GPU, on the dev host: `just narrate-bench-score SRC DEST`.

Reads DEST/<arm>/receipt.json (narrate/bench/host_run.py) and every chunk WAV it names, and writes DEST/scored.json
and DEST/scored.md. Per chunk: WER of whisper's read-back against the chunk text (narrate.qa: condense's whisper
path, the registered small.en model, numbers compared as digits on both sides), the longest silent run, and
the catastrophic flags of the bench plan (chunk WER over 30%, silence over 2 s, longer than twice the expected
duration at 150 words per minute, or a chunk missing). Per pass: whole-text WER over the joined read-backs, the
worst chunk WER, catastrophic count, RTF and load time from the receipt. Per arm: peak VRAM above the idle
baseline. With --decoys, decoys 4 and 5 are rebuilt from one chunk of --decoy-arm (half silence, time reversal,
shuffled transcript) and must land on their expected side.

SIM (narrate/sim.py, the registered ECAPA model) needs --reference (the voice's full consented clip: the one fixed
SIM reference for every arm, so an arm conditioned on a cut of it, receipt `reference`, is still scored against the
full clip; its sha256 must equal the window's inputs-verified.json voice.wav when that file names one), --config (a
narrate.toml whose registry holds a voice with that clip: an ECAPA embedding is a voiceprint, so
policy.check_consent passes for every such voice, against the current registry and store, before the clip is
decoded), --sim-model and an interpreter with torch and speechbrain (--sim-python or NARRATE_SIM_PYTHON; on the
shared CPU host, inside a 6G memory scope). The scorer holds the host's one-scorer lock (narrate.sim.scorer_lock)
for the whole run and refuses to start while another scorer holds it.

Per pass: each chunk against the reference, the median and minimum, and wSIM over 10 s windows (5 s hop) of the
pass's chunks joined in order, skipping windows with too little voice: its minimum, mean and every window. A chunk
longer than the worker's 60 s is skipped (sim_skipped too_long) and the rest of the pass is scored; a worker
failure leaves only that pass not_measured. Two scorer checks of the bench plan run in the same scoring pass:
decoy 1, the reference's second half against its first half (expected at least SIM_SELF_MIN), and decoy 2, the
passes rendered with the preset voice (decoy ids starting decoy2; a different speaker: expected median below
SIM_BAR and at least SIM_DECOY_MARGIN below decoy 1). Decoy 2 is bench-wide by the plan (rendered inside A1-gpu's
budget, the decoy the SIM bar is defined against), so every arm is read against the same one. Per arm, over the
chunks and wSIM windows of its seed passes (smoke passes repeat a seed-1 chunk and decoys are another speaker, so
neither counts): the preregistered bars, median at least SIM_BAR and SIM_DECOY_MARGIN above decoy 2, wSIM minimum
at least WSIM_RATIO times the arm's median, and all_met, which counts any bar that is not True (a missing value
included) as unmet, as is a decoy check that is not valid. Without any input SIM is not_measured with the reason.

Each arm records the conditioning reference its receipt names (label, wav and text sha256, and the voice clip it was
cut from), and the output's `conditioning` flags arms that cloned from different references, and a SIM reference
that is not the clip an arm's conditioning came from, so SIM and WER are never read as like for like across them.
`conditioning.groups` lists the arms that share one conditioning reference, with each arm's variant: within a group
the reference is like for like, and the variant shows whether an arm fell back to another conditioning path. A
window whose arms used different references (window 2: A3-gpu and the matched-cut controls on the max14s cut, A1-gpu
and A2-gpu-alt on the full clip) is still scored against the one full clip; `matched` sets each
matched-cut arm (receipt `matched_cut_of`) beside the arm it controls: variant, SIM median, wSIM, the bars, seed-1
WER, catastrophic chunks and RTF, and the cut-minus-full differences. When the window verified no voice.wav (only cut
arms ran), the SIM reference is bound to the one voice clip the receipts name instead. scored.json `window` names
the holder, the window's start and the voice clip by sha256 (never a voice id).

Several windows (window 2 takes one voice per window): score each window's directory on its own, with that window's
voice's full clip as --reference, then `score.py DEST --combine DIR_A --combine DIR_B` reads each DIR/scored.json and
writes DEST/combined.json and DEST/combined.md: one row per window and arm, the matched-cut rows of every window,
and per arm whether the bars were met in every window (an arm that errored in, or is absent from, a window counts
as not met there). Windows that share a voice clip, or that used different SIM models or bars, are flagged.
Combining reruns no model.

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

from narrate import audio, policy, qa  # noqa: E402
from narrate import sim as simlib  # noqa: E402
from narrate.config import SIM, WHISPER, WHISPER_ENVS  # noqa: E402
from narrate.config import Config as NarrateConfig  # noqa: E402

CHUNKS = Path(__file__).resolve().parent / "chunks-v1.json"
MAX_CHUNK_WER = 0.30
MAX_SILENCE_S = 2.0
MAX_DURATION_RATIO = 2.0
FRAME_S = 0.05
SILENCE_DBFS = -50.0
# SIM bars preregistered in the bench plan ("Bars": median chunk SIM at least 0.45 and 0.15 above the preset-voice
# decoy; wSIM minimum at least 0.8 times the arm's median chunk SIM). SIM_SELF_MIN is not preregistered: the plan
# says only that decoy 1 lands "well above the SIM bar", and this scorer reads that as the bar plus the decoy margin
# (an interpretation, recorded as such on TIN-7085). Where measurements sit against them
# (docs/agent-notes/2026-10-26-narrate-sim.md): the synthetic formant voices of narrate/tests/test_tools_sim.py score
# 0.95 for the same tract and 0.60 and 0.40 for its two decoys, so the absolute bar alone does not reject a near
# voice; the real-voice controls (self-match, preset-voice decoy, the same speaker on another microphone) are private
# and recorded on the tracker.
SIM_BAR, SIM_DECOY_MARGIN, WSIM_RATIO = 0.45, 0.15, 0.8
SIM_SELF_MIN = SIM_BAR + SIM_DECOY_MARGIN
DECOY2_PREFIX = "decoy2"  # host-job.json decoy ids: decoy 2 is the preset voice; other decoys never set its median
SIM_REFERENCE_ROLE = "the one fixed SIM reference for every arm: the voice's full consented clip"


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


def reference_consent(narrate_toml, digest):
    """policy.check_consent, now, for every registered voice whose reference clip has this sha256: a summary, or a
    (reason, refusal code) pair. The registry metadata is checked before the store is hashed."""
    if narrate_toml is None:
        reason = (
            "no --config narrate.toml: the reference clip's consent cannot be checked (an embedding is a voiceprint)"
        )
        return None, (reason, "consent_unchecked")
    try:
        ncfg = NarrateConfig(narrate_toml)
        registry, scope = ncfg.registry(), ncfg.job()["scope"]
    except (OSError, ValueError, KeyError, TypeError) as error:
        return None, (f"--config could not be read ({type(error).__name__})", "consent_unchecked")
    voices = sorted(v for v, record in registry["voices"].items() if record.get("refClipSha256") == digest)
    if not voices:
        return None, (f"no registered voice has the --reference clip {digest[:12]}", "voice_unknown")
    voice_id = None
    try:
        for voice_id in voices:
            policy.check_consent(voice_id, registry, None, scope)
        index = policy.store_index(ncfg.store)
        if digest not in index:
            return None, (f"the --reference clip {digest[:12]} is not in the private store", "ref_clip_missing")
        for voice_id in voices:
            policy.check_consent(voice_id, registry, index, scope)
    except policy.Refused as refusal:
        return None, (f"reference consent refused: voice {voice_id}: {refusal.detail}", refusal.code)
    except (KeyError, TypeError, ValueError) as error:
        return None, (
            f"reference consent refused: voice {voice_id}: invalid record ({type(error).__name__})",
            "consent_invalid",
        )
    return {"checked": "current registry and store", "voices": len(voices), "scope": scope}, None


class Sim:
    """narrate/sim.py's scorer against one reference clip, or the reason SIM is not measured. A worker failure is
    reported for the pass that met it; the scorer stays up for every other pass."""

    def __init__(self, cfg, reference, work, expected_sha256=None, narrate_toml=None):
        self.scorer, self.reference, self.why, self.refused, self.binding = None, None, None, None, None
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
        consent, refusal = reference_consent(narrate_toml, digest)
        if refusal is not None:
            self.why, self.refused = refusal
            return
        self.binding = {
            "ref_clip_sha256": digest,
            "window_voice_wav": "matched" if expected_sha256 else "no inputs-verified.json voice.wav to compare",
            "consent": consent,
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
        if ref.seconds > simlib.MAX_SECONDS:
            self.why = (
                f"the --reference clip is {ref.seconds:.1f} s, over the {simlib.MAX_SECONDS:.0f} s the worker embeds"
            )
            return
        half = len(ref.samples) // 2
        self.halves = (
            audio.Pcm(ref.rate, ref.samples[:half]).write(work / "reference.first.wav"),
            audio.Pcm(ref.rate, ref.samples[half:]).write(work / "reference.second.wav"),
        )
        self.scorer = scorer

    def score(self, pairs):
        """({id: value}, None), or (None, reason); pairs [(id, wav)] each scored against the reference."""
        if self.scorer is None:
            return None, self.why
        if not pairs:
            return None, "nothing to score"
        try:
            rows = self.scorer.score([(i, a, self.reference) for i, a in pairs])
        except (RuntimeError, OSError, ValueError) as error:
            return None, f"SIM scorer failed on this request: {error}"
        return {i: rows[i]["sim"] for i, _ in pairs}, None

    def self_match(self):
        """Decoy 1: (the reference's second half against its first half, None), or (None, reason)."""
        if self.scorer is None:
            return None, self.why
        try:
            rows = self.scorer.score([("self", self.halves[1], self.halves[0])])
        except (RuntimeError, OSError, ValueError) as error:
            return None, f"SIM scorer failed on decoy 1: {error}"
        return rows["self"]["sim"], None

    def status(self):
        if self.scorer is None:
            out = qa.not_measured(self.why)
            return {**out, "refused": self.refused} if self.refused else out
        return {"status": "measured", **self.scorer.identity(), "reference": self.binding}


def pass_windows(pieces, work, name):
    """wSIM windows over a pass's chunk takes joined in order: ([(id, wav, start_s)], skipped silent, reason)."""
    pieces = [p for p in pieces if p.seconds > 0]
    if not pieces:
        return [], 0, "no chunk audio"
    if len({p.rate for p in pieces}) != 1:
        return [], 0, "the pass's chunks differ in sample rate, so they are not joined"
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
        path = audio.Pcm(track.rate, track.samples[a:b]).write(Path(work) / f"{name}-window-{k}.wav")
        out.append((f"{name}/window-{k}", path, start))
    return out, silent, None if out else "every window has too little voice"


def score_chunk(path, text, expected_s, reader, work):
    pcm = load_pcm(path, work)
    # arm, pass and chunk: every arm has a seed1, so the arm keeps the scratch names unique
    s16 = Path(work) / f"{Path(path).parent.parent.name}-{Path(path).parent.name}-{Path(path).stem}.s16.wav"
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
    windows, silent, no_windows = pass_windows([r["pcm"] for r in rows if "pcm" in r], work, tag.replace("/", "-"))
    pairs = []
    for r in rows:
        if "s16" not in r:
            continue
        if r["pcm"].seconds > simlib.MAX_SECONDS:
            r["sim_skipped"] = "too_long"  # the worker refuses a request holding it; the rest of the pass scores
        else:
            pairs.append((r["chunk"], r["s16"]))
    sims, failed = sim.score(pairs + [(w, p) for w, p, _ in windows]) if sim.scorer is not None else (None, None)
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
        wsim = [{"start_s": start, "sim": sims[w]} for w, _, start in windows]
        out["sim"] = {
            "status": "measured",
            "median": round(statistics.median(values), 4),
            "min": min(values),
            "skipped_too_long": sum(1 for r in rows if "sim_skipped" in r),
            "wsim": wsim_summary(wsim, silent, no_windows),
        }
    elif sim.scorer is None:
        out["sim"] = sim.status()
    elif failed and pairs:
        out["sim"] = qa.not_measured(failed)
    elif any("sim_skipped" in r for r in rows):
        out["sim"] = qa.not_measured(f"every chunk of this pass is over the worker's {simlib.MAX_SECONDS:.0f} s")
    else:
        out["sim"] = qa.not_measured("no chunk of this pass was scored")
    if record.get("decoy"):
        out["decoy"] = record["decoy"]
    return out


def wsim_summary(values, silent, reason=None):
    """wSIM's minimum and mean (the bench plan reports both) over [{start_s, sim}], with every window kept."""
    sims = [v["sim"] for v in values]
    out = {
        "window_s": simlib.WINDOW_S,
        "hop_s": simlib.HOP_S,
        "windows": len(sims),
        "skipped_silent": silent,
        "min": min(sims) if sims else None,
        "mean": round(statistics.fmean(sims), 4) if sims else None,
        "values": values,
    }
    if not sims:
        out["reason"] = reason or "no window was scored"
    return out


def is_decoy2(p):
    return str(p.get("decoy") or "").startswith(DECOY2_PREFIX)


def is_seed(p):
    return not p.get("decoy") and p["pass"].startswith("seed") and p["pass"][4:].isdigit()


def sim_checks(doc, self_sim, self_why=None):
    """Decoys 1 and 2 of the bench plan, then each arm read against the SIM bars over its seed passes (in place)."""
    passes = [(arm["arm"], p) for arm in doc["arms"] for p in arm.get("passes", [])]
    wrong = [(a, p["sim"]["median"]) for a, p in passes if is_decoy2(p) and p["sim"].get("status") == "measured"]
    checks = {
        "1-reference-self-match": {
            "observed": self_sim,
            "expected": f"at least {SIM_SELF_MIN:.2f} (the bar plus the decoy margin: a reading of 'well above')",
            "valid": None if self_sim is None else self_sim >= SIM_SELF_MIN,
        }
    }
    if self_sim is None:
        checks["1-reference-self-match"]["reason"] = self_why
    decoy = statistics.median(v for _, v in wrong) if wrong else None
    checks["2-wrong-speaker"] = {
        "observed": None if decoy is None else round(decoy, 4),
        "passes": len(wrong),
        "arms": sorted({a for a, _ in wrong}),
        "expected": f"median below {SIM_BAR:.2f} and at least {SIM_DECOY_MARGIN:.2f} below decoy 1",
        "valid": None
        if decoy is None or self_sim is None
        else decoy < SIM_BAR and decoy <= self_sim - SIM_DECOY_MARGIN,
    }
    usable = all(c["valid"] is True for c in checks.values())
    for arm in doc["arms"]:
        if "passes" in arm:
            arm["sim"] = arm_sim(arm, decoy, usable)
    return checks


def arm_sim(arm, decoy, usable):
    """The arm's SIM over the chunks and wSIM windows of its seed passes, against the preregistered bars."""
    seeds = [p for p in arm["passes"] if is_seed(p) and p["sim"].get("status") == "measured"]
    values = [c["sim"] for p in seeds for c in p["chunks"] if "sim" in c]
    if not values:
        return qa.not_measured("no seed pass of this arm has a scored chunk")
    median = round(statistics.median(values), 4)
    windows = [w for p in seeds for w in p["sim"]["wsim"]["values"]]
    wsim = [w["sim"] for w in windows]
    wmin = min(wsim) if wsim else None
    bars = {
        "decoy_checks_valid": usable,
        "median_at_least_bar": median >= SIM_BAR,
        "over_decoy": None if decoy is None else round(median - decoy, 4),
        "over_decoy_ok": None if decoy is None else median - decoy >= SIM_DECOY_MARGIN,
        "wsim_ratio": None if wmin is None or median <= 0 else round(wmin / median, 4),
        "wsim_ok": None if wmin is None or median <= 0 else wmin >= WSIM_RATIO * median,
    }
    unmet = [
        k for k in ("decoy_checks_valid", "median_at_least_bar", "over_decoy_ok", "wsim_ok") if bars[k] is not True
    ]
    bars |= {"unmet": unmet, "all_met": not unmet}
    weakest = min(seeds, key=lambda p: p["sim"]["wsim"]["min"] if p["sim"]["wsim"]["min"] is not None else 2)
    return {
        "status": "measured",
        "basis": "chunks and wSIM windows of the arm's seed passes (smoke and decoy passes excluded)",
        "passes": [p["pass"] for p in seeds],
        "chunks": len(values),
        "median": median,
        "min": min(values),
        "wsim": {
            "windows": len(wsim),
            "min": wmin,
            "mean": round(statistics.fmean(wsim), 4) if wsim else None,
            "weakest_pass": weakest["pass"] if wsim else None,
        },
        "bars": bars,
    }


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


def window_voice_sha256(out_dir, receipts=()):
    """The voice.wav sha256 the window verified (inputs-verified.json, else inputs.json); else, when only cut arms
    ran, the one voice clip sha256 the receipts' conditioning names; else None."""
    for name in ("inputs-verified.json", "inputs.json"):
        path = Path(out_dir) / name
        if path.is_file():
            entry = (json.loads(path.read_text(encoding="utf-8")).get("verified") or {}).get("voice.wav") or {}
            if entry.get("sha256"):
                return entry["sha256"]
    clips = {(conditioning_of(r) or {}).get("voice_clip_sha256") for r in receipts} - {None}
    return clips.pop() if len(clips) == 1 else None


def window_identity(out_dir, voice_clip_sha256):
    """The window's holder and start (its receipt.json), and its voice clip by sha256."""
    receipt = {}
    path = Path(out_dir) / "receipt.json"
    if path.is_file():
        try:
            receipt = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            receipt = {}
    return {
        "holder": receipt.get("holder") or Path(out_dir).name,
        "started_utc": receipt.get("started_utc"),
        "voice_clip_sha256": voice_clip_sha256,
    }


def conditioning_of(receipt):
    """The conditioning reference a receipt names: {label, wav_sha256, text_sha256, voice_clip_sha256}, a bare
    label from an older receipt, or None (not recorded, or the arm clones no voice)."""
    ref = receipt.get("reference")
    if isinstance(ref, dict):
        return {k: ref.get(k) for k in ("label", "wav_sha256", "text_sha256", "voice_clip_sha256")}
    if isinstance(ref, str):
        return {"label": ref, "wav_sha256": None, "text_sha256": None, "voice_clip_sha256": None}
    return None


def compare_conditioning(arms, sim_reference_sha256):
    """Flags: arms conditioned on different (or unrecorded) references, and a SIM reference that is not the voice
    clip an arm's conditioning came from."""
    scored = [a for a in arms if "error" not in a]
    keys = {a["arm"]: (a.get("conditioning") or {}).get("wav_sha256") for a in scored}
    flags = []
    unknown = sorted(name for name, key in keys.items() if key is None)
    if unknown:
        flags.append("conditioning reference not recorded for " + ", ".join(unknown))
    distinct = sorted({key for key in keys.values() if key})
    if len(distinct) > 1:
        groups = []
        for key in distinct:
            names = sorted(n for n, k in keys.items() if k == key)
            label = next(a["conditioning"]["label"] for a in scored if keys[a["arm"]] == key)
            groups.append(f"{label} {key[:8]} ({', '.join(names)})")
        flags.append("unequal conditioning: " + "; ".join(groups) + "; SIM and WER are not like for like across these")
    if sim_reference_sha256:
        for a in scored:
            cond = a.get("conditioning") or {}
            clip = cond.get("voice_clip_sha256")
            if clip and clip != sim_reference_sha256:
                flags.append(f"{a['arm']}: the SIM reference is not the voice clip its conditioning came from")
            elif cond.get("wav_sha256") and cond["wav_sha256"] != sim_reference_sha256:
                flags.append(f"{a['arm']}: conditioned on {cond.get('label')}, SIM against the full clip")
    groups = [
        {
            "label": next(a["conditioning"]["label"] for a in scored if keys[a["arm"]] == key),
            "wav_sha256": key,
            "arms": sorted(n for n, k in keys.items() if k == key),
            # one reference is not one conditioning path: a fallback variant (no transcript) changes the path
            "variants": {
                a["arm"]: a.get("variant") for a in sorted(scored, key=lambda a: a["arm"]) if keys[a["arm"]] == key
            },
        }
        for key in distinct
    ]
    return {"equal": not unknown and len(distinct) <= 1, "flags": flags, "groups": groups}


def first_seed(arm):
    """The arm's lowest-numbered seed pass, or None."""
    seeds = [p for p in arm.get("passes", []) if is_seed(p)]
    return min(seeds, key=lambda p: int(p["pass"][4:])) if seeds else None


def arm_summary(arm):
    """What a matched-cut comparison sets side by side for one arm."""
    cond = arm.get("conditioning") or {}
    sim = arm.get("sim") or {}
    measured = sim.get("status") == "measured"
    seed = first_seed(arm) or {}
    return {
        "arm": arm["arm"],
        "conditioning": cond.get("label"),
        "conditioning_wav_sha256": cond.get("wav_sha256"),
        "variant": arm.get("variant"),
        "stop": (arm.get("stop") or {}).get("rule"),
        "sim_median": sim.get("median") if measured else None,
        "wsim_min": (sim.get("wsim") or {}).get("min") if measured else None,
        "wsim_mean": (sim.get("wsim") or {}).get("mean") if measured else None,
        "bars_all_met": (sim.get("bars") or {}).get("all_met") if measured else None,
        "bars_unmet": (sim.get("bars") or {}).get("unmet") if measured else None,
        "sim_status": sim.get("status") or "not_measured",
        "seed_pass": seed.get("pass"),
        "complete": seed.get("complete"),
        "wer_whole": seed.get("wer_whole"),
        "catastrophic": seed.get("catastrophic"),
        "rtf": seed.get("rtf"),
        "load_s": seed.get("load_s"),
    }


def difference(a, b):
    return None if a is None or b is None else round(a - b, 4)


def matched_comparisons(arms):
    """Each matched-cut arm beside the arm it controls (receipt matched_cut_of): the same engine, settings and
    variants, cloned from the cut instead of the full clip. Both are scored against the full clip."""
    by_name = {a["arm"]: a for a in arms if "error" not in a}
    rows = []
    for arm in by_name.values():
        native = arm.get("matched_cut_of")
        if not native:
            continue
        cut, full = arm_summary(arm), arm_summary(by_name[native]) if native in by_name else None
        row = {"native_arm": native, "cut_arm": arm["arm"], "full": full, "cut": cut}
        if full is None:
            row["note"] = f"{native} was not scored in this window"
        else:
            row["cut_minus_full"] = {
                k: difference(cut[k], full[k]) for k in ("sim_median", "wsim_min", "wsim_mean", "wer_whole", "rtf")
            }
            if cut["variant"] != full["variant"]:
                row["note"] = (
                    f"the smoke chose variant {cut['variant']} on the cut and {full['variant']} on the full clip, so "
                    "the conditioning path differs as well as the reference"
                )
        rows.append(row)
    return sorted(rows, key=lambda r: r["cut_arm"])


def fmt(value, digits=3):
    return "" if value is None else (f"{value:.{digits}f}" if isinstance(value, float) else str(value))


def matched_table(rows, window=None):
    """Markdown lines setting each matched-cut arm beside the arm it controls."""
    head = "| window " if window is not None else ""
    lead = f"| {window} " if window is not None else ""
    lines = [
        f"{head}| arm | reference | variant | SIM median | wSIM min | wSIM mean | SIM bars met | WER whole | "
        "catastrophic | RTF |",
        "|---" * (10 + (window is not None)) + "|",
    ]
    for row in rows:
        for side in ("full", "cut"):
            a = row[side]
            if a is None:
                continue
            cells = [
                a["arm"],
                f"{a['conditioning'] or 'not recorded'} {(a['conditioning_wav_sha256'] or '')[:8]}".strip(),
                a["variant"] or "",
                fmt(a["sim_median"]),
                fmt(a["wsim_min"]),
                fmt(a["wsim_mean"]),
                fmt(a["bars_all_met"]) if a["bars_all_met"] is not None else a["sim_status"],
                fmt(a["wer_whole"]),
                fmt(a["catastrophic"]),
                fmt(a["rtf"]),
            ]
            lines.append(lead + "| " + " | ".join(cells) + " |")
        diff = row.get("cut_minus_full")
        if diff:
            lines.append(
                f"{lead}| {row['cut_arm']} minus {row['native_arm']} | | | {fmt(diff['sim_median'])} | "
                f"{fmt(diff['wsim_min'])} | {fmt(diff['wsim_mean'])} | | {fmt(diff['wer_whole'])} | | "
                f"{fmt(diff['rtf'])} |"
            )
    notes = [f"Matched {r['cut_arm']}: {r['note']}." for r in rows if r.get("note")]
    return lines + notes


def table(doc):
    lines = [
        "| arm | conditioning | pass | variant | done | audio s | RTF | load s | WER whole | WER max | catastrophic |"
        " SIM median | SIM min | wSIM min | wSIM mean | peak VRAM above idle GiB | stop |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for arm in doc["arms"]:
        if "error" in arm:
            lines.append(f"| {arm['arm']} | not scored: {arm['error']} |" + " |" * 15)
            continue
        cond = arm.get("conditioning")
        cond_text = "not recorded" if cond is None else f"{cond['label']} {(cond.get('wav_sha256') or '')[:8]}".strip()
        peak = arm.get("peak_above_baseline_bytes")
        peak = f"{peak / 2**30:.2f}" if peak is not None else ""
        stop = (arm.get("stop") or {}).get("rule", "")
        for p in arm["passes"]:
            s = p["sim"]
            if s.get("status") == "measured":
                sim_text = [fmt(s["median"]), fmt(s["min"]), fmt(s["wsim"]["min"]), fmt(s["wsim"]["mean"])]
            else:
                sim_text = ["not_measured", "", "", ""]
            lines.append(
                f"| {arm['arm']} | {cond_text} | {p['pass']} | {p['variant'] or ''} | "
                f"{p['chunks_done']}/{p['chunks_total']} | "
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
    for arm in doc["arms"]:
        a = arm.get("sim")
        if a is None:
            continue
        if a.get("status") != "measured":
            lines.append(f"SIM arm {arm['arm']}: not_measured: {a.get('reason')}")
            continue
        b, w = a["bars"], a["wsim"]
        lines.append(
            f"SIM arm {arm['arm']} ({', '.join(a['passes'])}): median {fmt(a['median'])}, over decoy 2 "
            f"{fmt(b['over_decoy'])}, wSIM min {fmt(w['min'])} ({w['weakest_pass']}), mean {fmt(w['mean'])}, ratio "
            f"{fmt(b['wsim_ratio'])}; all bars met {b['all_met']}"
            + (f", unmet {', '.join(b['unmet'])}" if b["unmet"] else "")
        )
    ref = doc.get("sim_reference")
    if ref:
        lines.append(f"SIM reference: {ref['sha256'][:8]}, {ref['role']}.")
    for flag in doc["conditioning"]["flags"]:
        lines.append(f"Conditioning: {flag}.")
    for group in doc["conditioning"].get("groups", []):
        if len(group["arms"]) > 1:
            variants = group.get("variants") or {}
            names = [f"{n} ({variants[n] or 'no variant'})" if n in variants else n for n in group["arms"]]
            lines.append(
                f"Like for like on {group['label']} {group['wav_sha256'][:8]}: {', '.join(names)}"
                " (one conditioning reference; the variant in brackets is each arm's conditioning path)."
            )
    if doc.get("matched"):
        lines += ["", "Matched cut (each control beside the arm it controls; both scored against the full clip):", ""]
        lines += matched_table(doc["matched"])
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
    parser.add_argument(
        "--reference", type=Path, help="the voice's full consented clip: the one SIM reference for every arm (private)"
    )
    parser.add_argument("--config", type=Path, help="narrate.toml whose registry and store check the clip's consent")
    parser.add_argument("--arm", action="append", default=[], help="score only these arms")
    parser.add_argument("--decoys", action="store_true", help="rebuild and score decoys 4 and 5")
    parser.add_argument("--decoy-arm", default="A2-gpu-alt")
    parser.add_argument(
        "--combine",
        action="append",
        default=[],
        metavar="SCORED_DIR",
        type=Path,
        help="combine already-scored windows (each DIR/scored.json) into out_dir/combined.json and combined.md",
    )
    args = parser.parse_args(argv)

    tree = inside_git(args.out_dir if args.out_dir.exists() else args.out_dir.parent)
    if tree is not None:
        print(
            f"score: refused: {args.out_dir} is inside a git work tree; score outside the repository", file=sys.stderr
        )
        return 2
    if args.combine:
        if args.pull:
            print("score: refused: --combine reads scored windows; it pulls nothing", file=sys.stderr)
            return 2
        return combine(args.out_dir, args.combine)
    if args.pull:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(["rsync", "-a", args.pull.rstrip("/") + "/", str(args.out_dir) + "/"], check=True)
    with simlib.scorer_lock() as held:
        if not held:
            print(f"score: refused: {simlib.SCORER_BUSY}", file=sys.stderr)
            return 2
        return score(args)


def score(args):
    chunk_doc = json.loads(CHUNKS.read_text(encoding="utf-8"))
    chunks_by_id = {c["id"]: c for c in chunk_doc["chunks"]}
    cfg = config(args.whisper_model, args.sim_model, args.sim_python, args.sim_threads)
    reader = Reader(cfg)
    receipts = sorted(args.out_dir.glob("*/receipt.json"))
    receipt_docs = [json.loads(path.read_text(encoding="utf-8")) for path in receipts]
    voice_sha256 = window_voice_sha256(args.out_dir, receipt_docs)
    reference = Path(args.reference) if args.reference else None
    reference_sha256 = sha256_file(reference) if reference is not None and reference.is_file() else None
    doc = {
        "schema": "narrate-bench-scored/1",
        "chunks_sha256": chunk_doc["chunks_sha256"],
        "wer": {"status": "measured", **reader.whisper.identity()} if reader.ok else qa.not_measured(reader.why),
        "sim": None,
        "sim_reference": {"sha256": reference_sha256, "role": SIM_REFERENCE_ROLE} if reference_sha256 else None,
        "window": window_identity(args.out_dir, voice_sha256),
        "rules": {
            "max_chunk_wer": MAX_CHUNK_WER,
            "max_silence_s": MAX_SILENCE_S,
            "silence_dbfs": SILENCE_DBFS,
            "max_duration_ratio": MAX_DURATION_RATIO,
        },
        "arms": [],
    }
    with tempfile.TemporaryDirectory() as work:
        sim = Sim(cfg, args.reference, work, voice_sha256, args.config)
        for path, receipt in zip(receipts, receipt_docs, strict=True):
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
                "conditioning": conditioning_of(receipt),
                "matched_cut_of": receipt.get("matched_cut_of"),
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
        self_sim, self_why = sim.self_match()
        doc["sim"] = {
            **sim.status(),
            "bars": {"bar": SIM_BAR, "decoy_margin": SIM_DECOY_MARGIN, "wsim_ratio": WSIM_RATIO},
        }
        if sim.scorer is not None:
            doc["sim"]["checks"] = sim_checks(doc, self_sim, self_why)
    doc["conditioning"] = compare_conditioning(doc["arms"], reference_sha256)
    doc["matched"] = matched_comparisons(doc["arms"])
    (args.out_dir / "scored.json").write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    text = table(doc)
    (args.out_dir / "scored.md").write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


def combine(dest, dirs):
    """DEST/combined.json and combined.md from several windows' scored.json (one voice per window)."""
    windows, problems = [], []
    for d in dirs:
        path = Path(d) / "scored.json"
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            problems.append(f"{path}: {type(error).__name__}")
            continue
        if doc.get("schema") != "narrate-bench-scored/1":
            problems.append(f"{path}: not a narrate-bench-scored/1 file")
            continue
        windows.append((Path(d), doc))
    if not problems and len({doc.get("chunks_sha256") for _, doc in windows}) > 1:
        problems.append("the windows scored different chunk lists")
    if problems:
        print("score: refused: " + "; ".join(problems), file=sys.stderr)
        return 2
    rows, matched, flags, seen = [], [], [], {}
    for d, doc in windows:
        ident = doc.get("window") or {}
        name = ident.get("holder") or d.name
        voice = ident.get("voice_clip_sha256") or (doc.get("sim_reference") or {}).get("sha256")
        if voice and voice in seen:
            flags.append(f"windows {seen[voice]} and {name} share the voice clip {voice[:8]}")
        seen.setdefault(voice, name)
        if not voice:
            flags.append(f"window {name} names no voice clip (no --reference and no window voice.wav)")
        checks = (doc.get("sim") or {}).get("checks") or {}
        decoys_valid = all(c.get("valid") is True for c in checks.values()) if checks else None
        for arm in doc.get("arms", []):
            if "error" in arm:
                rows.append({"window": name, "voice_clip_sha256": voice, "arm": arm["arm"], "error": arm["error"]})
                continue
            row = {"window": name, "voice_clip_sha256": voice, "decoy_checks_valid": decoys_valid}
            rows.append({**row, **arm_summary(arm)})
        for row in doc.get("matched") or matched_comparisons(doc.get("arms", [])):
            matched.append({"window": name, **row})
    sims = {
        (s.get("model_sha256"), canonical_bars(s.get("bars")))
        for _, doc in windows
        if (s := doc.get("sim") or {}).get("status") == "measured"
    }
    if len(sims) > 1:
        flags.append("the windows used different SIM models or bars, so SIM is not comparable across them")
    per_arm = {}
    names = list(dict.fromkeys((doc.get("window") or {}).get("holder") or d.name for d, doc in windows))
    for row in rows:
        entry = per_arm.setdefault(
            row["arm"], {"windows": [], "bars_met_in": [], "bars_unmet_in": [], "not_scored_in": [], "absent_from": []}
        )
        if "error" in row:
            entry["not_scored_in"].append(row["window"])
            continue
        entry["windows"].append(row["window"])
        (entry["bars_met_in"] if row["bars_all_met"] is True else entry["bars_unmet_in"]).append(row["window"])
    for arm, entry in per_arm.items():
        present = {r["window"] for r in rows if r["arm"] == arm}
        entry["absent_from"] = [n for n in names if n not in present]
        # an arm that errored in, or never reached, a window has not met its bars there
        entry["bars_met_in_every_window"] = not (
            entry["bars_unmet_in"] or entry["not_scored_in"] or entry["absent_from"]
        )
    out = {
        "schema": "narrate-bench-combined/1",
        "chunks_sha256": windows[0][1].get("chunks_sha256") if windows else None,
        "windows": [
            {
                "window": (doc.get("window") or {}).get("holder") or d.name,
                "started_utc": (doc.get("window") or {}).get("started_utc"),
                "voice_clip_sha256": (doc.get("window") or {}).get("voice_clip_sha256")
                or (doc.get("sim_reference") or {}).get("sha256"),
                "sim": {k: (doc.get("sim") or {}).get(k) for k in ("status", "model_sha256", "bars", "reason")},
                "decoy_checks": {k: c.get("valid") for k, c in ((doc.get("sim") or {}).get("checks") or {}).items()},
                "conditioning_flags": (doc.get("conditioning") or {}).get("flags", []),
            }
            for d, doc in windows
        ],
        "arms": rows,
        "matched": matched,
        "per_arm": per_arm,
        "flags": flags,
        "note": "measurements only: the bars and the pick are read by a person against the preregistration and its "
        "addendum; SIM in each window is against that window's voice's full clip; listening is a separate state",
    }
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "combined.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    text = combined_table(out)
    (dest / "combined.md").write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


def canonical_bars(bars):
    return json.dumps(bars, sort_keys=True)


def combined_table(out):
    lines = [
        "| window | voice clip | arm | reference | variant | SIM median | wSIM min | wSIM mean | SIM bars met |"
        " decoy checks valid | WER whole | catastrophic | RTF | stop |",
        "|---" * 14 + "|",
    ]
    for r in out["arms"]:
        voice = (r.get("voice_clip_sha256") or "")[:8]
        if "error" in r:
            lines.append(f"| {r['window']} | {voice} | {r['arm']} | not scored: {r['error']} |" + " |" * 10)
            continue
        ref = f"{r['conditioning'] or 'not recorded'} {(r['conditioning_wav_sha256'] or '')[:8]}".strip()
        met = fmt(r["bars_all_met"]) if r["bars_all_met"] is not None else r["sim_status"]
        lines.append(
            f"| {r['window']} | {voice} | {r['arm']} | {ref} | {r['variant'] or ''} | {fmt(r['sim_median'])} | "
            f"{fmt(r['wsim_min'])} | {fmt(r['wsim_mean'])} | {met} | {fmt(r['decoy_checks_valid'])} | "
            f"{fmt(r['wer_whole'])} | {fmt(r['catastrophic'])} | {fmt(r['rtf'])} | {r['stop'] or ''} |"
        )
    if out["matched"]:
        lines += ["", "Matched cut, per window (both arms scored against that window's full clip):", ""]
        for window in dict.fromkeys(r["window"] for r in out["matched"]):
            lines += matched_table([r for r in out["matched"] if r["window"] == window], window)
    lines.append("")
    for arm, entry in sorted(out["per_arm"].items()):
        lines.append(
            f"Arm {arm}: in {len(entry['windows'])} window(s); SIM bars met in every window "
            f"{entry['bars_met_in_every_window']}"
            + (f" (unmet in {', '.join(entry['bars_unmet_in'])})" if entry["bars_unmet_in"] else "")
            + (f" (not scored in {', '.join(entry['not_scored_in'])})" if entry.get("not_scored_in") else "")
            + (f" (absent from {', '.join(entry['absent_from'])})" if entry.get("absent_from") else "")
        )
    for flag in out["flags"]:
        lines.append(f"Flag: {flag}.")
    lines.append(f"Note: {out['note']}.")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.exit(main())
