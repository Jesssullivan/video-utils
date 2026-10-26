"""Speaker similarity (SIM) for `narrate evaluate` (docs/spec/NARRATE.md, "Per-chunk QA" and "Evaluation").

The scorer is speechbrain/spkrec-ecapa-voxceleb's ECAPA-TDNN embedding (Apache-2.0), registered in
program/models.json as SIM_MODEL_ID and bound by the sha256 of embedding_model.ckpt. It runs on the CPU in a
separate interpreter that has torch and speechbrain (`nix develop .#ml`), because the condense shell the narrate
recipes use has neither: narrate.sim_worker reads one JSON request and prints one reply.

Settings, first found wins: `[sim] model` / NARRATE_SIM_MODEL (the embedding_model.ckpt path), `[sim] python` /
NARRATE_SIM_PYTHON (the worker interpreter), `[sim] threads` (1 to 8; default 4). With no model named,
models/<SIM_MODEL_ID>.bin is used when `just narrate-sim-model` has fetched it. The interpreter has no default:
torch inference starts only when someone names it. On the shared CPU host a scorer runs one at a time inside a
6G memory scope (systemd-run --user --scope -p MemoryMax=6G -p MemorySwapMax=0, nice 19, ionice -c3); no TTS
model runs there. Every embedded file is at most MAX_SECONDS long, because the worker's memory grows with the
length it embeds (a probe that embedded two 222 s and 266 s tracks peaked at 4.7 GB resident). Without a model
file, with a file whose sha256 is not the registered one, without an interpreter, or when the worker cannot run
or answers out of protocol, SIM is not_measured with the reason, never a number.

Consent: an ECAPA embedding is a voiceprint. Every reference voice (the speaking voices the manifest names, or
--reference-voice) passes policy.check_consent against the current registry before any clip is read: a revoked,
unregistered, evidence-less or out-of-scope consent gives not_measured with the typed refusal code.

The worker's front end is hardcoded to the hyperparams.yaml of the pinned revision; program/models.json records
that file's sha256, but only embedding_model.ckpt is fetched and checked. The real model path runs only in the
opt-in test (NARRATE_SIM_TEST_MODEL, NARRATE_SIM_TEST_PYTHON); CI covers the import smoke and the fake worker.

What a number means: cosine similarity of two utterance embeddings, -1 to 1. It measures how alike two recordings
sound to a speaker-verification model trained on VoxCeleb celebrity interviews; the channel (microphone, room,
codec) moves it as well as the voice does. It is evidence for a gate the bench calibrates against a decoy, not a
judgement that a listener hears the same person. Listening acceptance is a separate state.
"""

import json
import math
import os
import statistics
import subprocess
import tempfile
from pathlib import Path

from . import audio, policy, qa
from .config import FF, ROOT, SIM_MAX_THREADS, run

SIM_MODEL_ID = "speechbrain-spkrec-ecapa-voxceleb-embedding"
WORKER = Path(__file__).resolve().parent / "sim_worker.py"
MAX_THREADS = SIM_MAX_THREADS
WORKER_TIMEOUT_S = float(os.environ.get("NARRATE_SIM_TIMEOUT_S", 600))
WINDOW_S, HOP_S = 10.0, 5.0  # wSIM over the delivered track (bench plan): the minimum shows drift on long text
SHORT_S = 1.0  # a chunk shorter than this still scores, and is marked short: its embedding is noisy
MAX_SECONDS = 60.0  # the longest file the worker embeds (sim_worker.MAX_SECONDS); wSIM windows keep tracks short
DEFAULT_MODEL = ROOT / "models" / f"{SIM_MODEL_ID}.bin"  # where `just narrate-sim-model` puts it
# A wSIM window scores only when it holds MIN_VOICED_S of frames above VOICED_DBFS: padding to cue times can leave
# windows of silence, whose embedding measures nothing about voice drift.
FRAME_S, VOICED_DBFS, MIN_VOICED_S = 0.02, -45.0, 3.0


class Scorer:
    def __init__(self, cfg=None):
        sim = cfg.sim if cfg is not None else {}
        model = sim.get("model") or os.environ.get("NARRATE_SIM_MODEL", "")
        base = cfg.base if cfg is not None else Path.cwd()
        self.model = (Path(model) if Path(model).is_absolute() else base / model) if model else None
        if self.model is None and DEFAULT_MODEL.is_file():
            self.model = DEFAULT_MODEL
        self.python = sim.get("python") or os.environ.get("NARRATE_SIM_PYTHON") or None
        self.threads = check_threads(sim.get("threads", 4))
        self.model_sha256, self.model_id, self.runtime = None, None, {}

    def available(self):
        if self.python is None:
            return False, (
                "no SIM interpreter ([sim] python or NARRATE_SIM_PYTHON): torch starts only when one is named "
                "(on the shared CPU host, inside a 6G memory scope)"
            )
        if self.model is None:
            return False, "no speaker-verification model ([sim] model or NARRATE_SIM_MODEL)"
        if not self.model.is_file():
            return False, "the [sim] model file is absent (just narrate-sim-model)"
        digest = qa.model_digest(self.model)
        model_id = qa.registered(digest)
        if model_id != SIM_MODEL_ID:
            return False, f"SIM model sha256 {digest[:12]} is not the registered {SIM_MODEL_ID}"
        self.model_sha256, self.model_id = digest, model_id
        return True, f"{SIM_MODEL_ID} on the CPU"

    def identity(self):
        return {
            "model_id": self.model_id,
            "model_sha256": self.model_sha256,
            "embedding": "ECAPA-TDNN 192-d, Fbank 80 at 16 kHz, sentence mean norm",
            "score": "cosine similarity, -1 to 1",
            "threads": self.threads,
            **self.runtime,
        }

    def score(self, pairs, timeout=WORKER_TIMEOUT_S):
        """{id: sim} for [(id, wav a, wav b)] (16-bit mono WAV paths). Raises RuntimeError with the reason."""
        request = {
            "model": str(self.model),
            "threads": self.threads,
            "pairs": [{"id": i, "a": str(a), "b": str(b)} for i, a, b in pairs],
        }
        env = dict(os.environ, OMP_NUM_THREADS=str(self.threads), MKL_NUM_THREADS=str(self.threads))
        try:
            p = subprocess.run(
                [self.python, "-I", str(WORKER)],
                input=json.dumps(request),
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"the SIM worker ran over {timeout:g} s") from None
        except OSError as error:
            raise RuntimeError(f"the SIM worker could not start: {error}") from None
        try:
            reply = json.loads(p.stdout)
        except ValueError:
            tail = p.stderr.strip().splitlines()[-1:] or ["no output"]
            raise RuntimeError(f"the SIM worker failed ({p.returncode}): {tail[0][:300]}") from None
        if not reply.get("ok"):
            raise RuntimeError(f"the SIM worker refused: {reply.get('reason')}")
        rows = reply.get("scores")
        if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
            raise RuntimeError("the SIM worker reply has no score list")
        found = {r.get("id"): r for r in rows}
        wanted = {i for i, _, _ in pairs}
        if set(found) != wanted or len(rows) != len(wanted):
            raise RuntimeError(f"the SIM worker scored {len(found)} ids, not the {len(wanted)} requested")
        for row in rows:
            value = row.get("sim")
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not -1.0001 <= value <= 1.0001:
                raise RuntimeError(f"the SIM worker gave {row['id']} a score that is not a cosine: {value!r}")
        self.runtime = {"torch": reply.get("torch"), "speechbrain": reply.get("speechbrain")}
        return found


def check_threads(value):
    """[sim] threads: an integer from 1 to MAX_THREADS (narrate.config refuses anything else before a run)."""
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_THREADS:
        raise ValueError(f"sim.threads = {value!r}: an integer from 1 to {MAX_THREADS}")
    return value


def voiced_seconds(pcm, start_s, end_s):
    """Seconds of FRAME_S frames in pcm[start_s:end_s] whose RMS is above VOICED_DBFS (full scale 32768)."""
    frame = max(1, round(FRAME_S * pcm.rate))
    a, b = round(start_s * pcm.rate), min(len(pcm.samples), round(end_s * pcm.rate))
    floor = frame * (32768.0 * 10 ** (VOICED_DBFS / 20)) ** 2
    voiced = 0
    for k in range(a, b - frame + 1, frame):
        piece = pcm.samples[k : k + frame]
        if math.sumprod(piece, piece) > floor:
            voiced += 1
    return voiced * frame / pcm.rate


def window_starts(total_s):
    """wSIM window starts over a total_s track: every HOP_S, plus one that ends with the track."""
    if total_s <= WINDOW_S:
        return [0.0]
    starts = [k * HOP_S for k in range(int((total_s - WINDOW_S) // HOP_S) + 1)]
    if starts[-1] < total_s - WINDOW_S - 0.5:
        starts.append(round(total_s - WINDOW_S, 3))  # the last window ends with the track
    return starts


def wsim_voiced(pcm, start_s):
    """True when the window at start_s holds enough voiced frames to score (MIN_VOICED_S, or half a short track)."""
    return voiced_seconds(pcm, start_s, start_s + WINDOW_S) >= min(MIN_VOICED_S, pcm.seconds / 2)


def to16k(src, dst):
    """A 16 kHz mono 16-bit copy of any audio file FFmpeg reads (the store may hold a 24-bit or 44.1 kHz clip)."""
    run(*FF, "-loglevel", "error", "-i", src, "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", dst)
    return dst


def evaluate(run_dir, manifest, cfg, reference_voice=None, scorer=None):
    """The sim metric of `narrate evaluate`: each chunk of narration.wav (out_start_s..out_end_s) against the
    reference clip of the voice that spoke it, or of reference_voice for every chunk; plus wSIM, the minimum over
    10 s windows with a 5 s hop, when one reference serves the whole track."""
    if cfg is None:
        return qa.not_measured("no narrate.toml given (--config): the reference clip is found through its store")
    registry = cfg.registry()
    index = policy.store_index(cfg.store)
    by_speaker = {str(v["speaker"]): v for v in manifest["voices"]}
    edl = json.loads((Path(run_dir) / manifest["timeline"]["edl"]["file"]).read_text(encoding="utf-8"))
    chunk_voice = {c["id"]: s["voice"] for s in edl["segments"] for c in s["chunks"]}
    voice_ref = {v["voice"]: v["ref_clip_sha256"] for v in by_speaker.values()}
    if reference_voice is not None and reference_voice not in registry["voices"]:
        return qa.not_measured(f"reference voice {reference_voice!r} is not in the voice registry")
    # consent is read now, not from the manifest: a consent revoked after the render stops SIM too
    for voice_id in sorted({reference_voice} if reference_voice is not None else set(voice_ref)):
        try:
            policy.check_consent(voice_id, registry, index, manifest["job"]["scope"])
        except policy.Refused as refusal:
            return {**qa.not_measured(f"voice {voice_id}: {refusal.detail}"), "refused": refusal.code}
    scorer = scorer or Scorer(cfg)
    ready = scorer.available()
    if not ready[0]:
        return qa.not_measured(ready[1])
    if reference_voice is not None:
        record = registry["voices"][reference_voice]
        refs = {c["id"]: (reference_voice, record["refClipSha256"]) for c in manifest["chunks"]}
    else:
        refs = {c["id"]: (chunk_voice[c["id"]], voice_ref[chunk_voice[c["id"]]]) for c in manifest["chunks"]}
    missing = sorted({digest for _, digest in refs.values() if digest not in index})
    if missing:
        return qa.not_measured(f"reference clip {missing[0][:12]} is not in the private store")
    delivered = audio.read(Path(run_dir) / "narration.wav")
    with tempfile.TemporaryDirectory() as work:
        work = Path(work)
        ref_paths = {d: to16k(index[d], work / f"ref-{d[:16]}.wav") for d in {d for _, d in refs.values()}}
        pairs, seconds = [], {}
        for chunk in manifest["chunks"]:
            a, b = round(chunk["out_start_s"] * delivered.rate), round(chunk["out_end_s"] * delivered.rate)
            piece = audio.Pcm(delivered.rate, delivered.samples[a:b])
            seconds[chunk["id"]] = round(piece.seconds, 3)
            path = to16k(piece.write(work / f"chunk-{chunk['id']}.raw.wav"), work / f"chunk-{chunk['id']}.wav")
            pairs.append((chunk["id"], path, ref_paths[refs[chunk["id"]][1]]))
        single = len(set(ref_paths)) == 1
        windows, silent = [], 0
        if single:
            whole = to16k(Path(run_dir) / "narration.wav", work / "track.wav")
            total = delivered.seconds
            for k, start in enumerate(window_starts(total)):
                if not wsim_voiced(delivered, start):
                    silent += 1
                    continue
                wid = f"window-{k}"
                path = work / f"{wid}.wav"
                run(*FF, "-loglevel", "error", "-i", whole, "-ss", f"{start:.3f}", "-t", f"{WINDOW_S:.3f}", path)
                windows.append((wid, path, next(iter(ref_paths.values())), start))
        try:
            rows = scorer.score(pairs + [(w, p, r) for w, p, r, _ in windows])
        except RuntimeError as error:
            return qa.not_measured(str(error))
    chunks = [
        {
            "chunk": cid,
            "voice": refs[cid][0],
            "sim": rows[cid]["sim"],
            "seconds": seconds[cid],
            **({"short": True} if seconds[cid] < SHORT_S else {}),
        }
        for cid, _, _ in pairs
    ]
    values = [c["sim"] for c in chunks]
    gates = manifest["job"]["gates"]
    out = {
        "status": "measured",
        **scorer.identity(),
        "scored": "narration.wav, cut per chunk at out_start_s..out_end_s, against the voice's reference clip",
        "reference": {
            "override": reference_voice,
            "ref_clip_sha256": sorted({d for _, d in refs.values()}),
        },
        "chunks": chunks,
        "median": round(statistics.median(values), 4) if values else None,
        "min": min(values) if values else None,
        "min_sim": gates["minSim"],
        "calibrated": gates["calibrated"],
        "passed": all(v >= gates["minSim"] for v in values),
    }
    if single:
        wsim = [rows[w]["sim"] for w, _, _, _ in windows]
        out["wsim"] = {
            "window_s": WINDOW_S,
            "hop_s": HOP_S,
            "windows": len(wsim),
            "skipped_silent": silent,
            "min_voiced_s": MIN_VOICED_S,
            "min": min(wsim) if wsim else None,
        }
    if not gates["calibrated"]:
        out["note"] = "minSim is uncalibrated: the bench sets it against a decoy; passed is not acceptance"
    return out
