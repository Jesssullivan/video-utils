"""Speaker similarity (SIM) for `narrate evaluate` (docs/spec/NARRATE.md, "Per-chunk QA" and "Evaluation").

The scorer is speechbrain/spkrec-ecapa-voxceleb's ECAPA-TDNN embedding (Apache-2.0), registered in
program/models.json as SIM_MODEL_ID and bound by the sha256 of embedding_model.ckpt. It runs on the CPU in a
separate interpreter that has torch and speechbrain (`nix develop .#ml`), because the condense shell the narrate
recipes use has neither: narrate.sim_worker reads one JSON request and prints one reply.

Settings, first found wins: `[sim] model` / NARRATE_SIM_MODEL (the embedding_model.ckpt path), `[sim] python` /
NARRATE_SIM_PYTHON (the worker interpreter; default this one), `[sim] threads` (at most 8; default 4). With no
model named, models/<SIM_MODEL_ID>.bin is used when `just narrate-sim-model` has fetched it. Without a
model file, with a file whose sha256 is not the registered one, or when the worker cannot run, SIM is
not_measured with the reason, never a number.

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
import sys
import tempfile
from pathlib import Path

from . import audio, policy, qa
from .config import FF, ROOT, run

SIM_MODEL_ID = "speechbrain-spkrec-ecapa-voxceleb-embedding"
WORKER = Path(__file__).resolve().parent / "sim_worker.py"
MAX_THREADS = 8
WORKER_TIMEOUT_S = float(os.environ.get("NARRATE_SIM_TIMEOUT_S", 600))
WINDOW_S, HOP_S = 10.0, 5.0  # wSIM over the delivered track (bench plan): the minimum shows drift on long text
SHORT_S = 1.0  # a chunk shorter than this still scores, and is marked short: its embedding is noisy


class Scorer:
    def __init__(self, cfg=None):
        sim = cfg.sim if cfg is not None else {}
        model = sim.get("model") or os.environ.get("NARRATE_SIM_MODEL", "")
        base = cfg.base if cfg is not None else Path.cwd()
        default = ROOT / "models" / f"{SIM_MODEL_ID}.bin"  # where `just narrate-sim-model` puts it
        self.model = (Path(model) if Path(model).is_absolute() else base / model) if model else None
        if self.model is None and default.is_file():
            self.model = default
        self.python = sim.get("python") or os.environ.get("NARRATE_SIM_PYTHON") or sys.executable
        self.threads = max(1, min(MAX_THREADS, int(sim.get("threads", 4))))
        self.model_sha256, self.model_id, self.runtime = None, None, {}

    def available(self):
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
        self.runtime = {}
        expected = [i for i, _, _ in pairs]
        if not expected or any(type(i) is not str or not i for i in expected) or len(set(expected)) != len(expected):
            raise RuntimeError("the SIM request needs unique nonempty string IDs")
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
        if p.returncode != 0:
            raise RuntimeError(f"the SIM worker failed (exit {p.returncode})")
        try:
            reply = json.loads(p.stdout)
            if type(reply) is not dict or type(reply.get("ok")) is not bool:
                raise ValueError("expected an object with boolean ok")
            if reply["ok"] is not True:
                raise ValueError("worker refused")
            scores = reply["scores"]
            if type(scores) is not list or len(scores) != len(expected):
                raise ValueError("scores must match every requested ID exactly once")
            rows = {}
            for row in scores:
                if type(row) is not dict or type(row.get("id")) is not str:
                    raise ValueError("each score needs a string ID")
                ident = row["id"]
                if ident not in expected or ident in rows:
                    raise ValueError("unexpected or duplicate score ID")
                for key in ("sim", "a_seconds", "b_seconds"):
                    value = row[key]
                    if type(value) not in (int, float) or not math.isfinite(value):
                        raise ValueError(f"{key} must be a finite number")
                    if key == "sim" and not -1 <= value <= 1:
                        raise ValueError("cosine must lie in [-1, 1]")
                    if key != "sim" and value <= 0:
                        raise ValueError("scored audio duration must be positive")
                rows[ident] = row
            for key in ("torch", "speechbrain"):
                if type(reply[key]) is not str or not reply[key]:
                    raise ValueError(f"{key} version must be a nonempty string")
            if "threads" in reply and (type(reply["threads"]) is not int or reply["threads"] != self.threads):
                raise ValueError("worker threads differ from the request")
        except (ValueError, KeyError, TypeError, OverflowError) as error:
            raise RuntimeError(f"invalid SIM worker response: {error}") from None
        self.runtime = {"torch": reply["torch"], "speechbrain": reply["speechbrain"]}
        return rows


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
    scorer = scorer or Scorer(cfg)
    ready = scorer.available()
    if not ready[0]:
        return qa.not_measured(ready[1])
    by_speaker = {str(v["speaker"]): v for v in manifest["voices"]}
    edl = json.loads((Path(run_dir) / manifest["timeline"]["edl"]["file"]).read_text(encoding="utf-8"))
    chunk_voice = {c["id"]: s["voice"] for s in edl["segments"] for c in s["chunks"]}
    voice_ref = {v["voice"]: v["ref_clip_sha256"] for v in by_speaker.values()}
    registry = cfg.registry()
    if reference_voice is not None:
        record = registry["voices"].get(reference_voice)
        if record is None:
            return qa.not_measured(f"reference voice {reference_voice!r} is not in the voice registry")
        refs = {c["id"]: (reference_voice, record["refClipSha256"]) for c in manifest["chunks"]}
    else:
        refs = {c["id"]: (chunk_voice[c["id"]], voice_ref[chunk_voice[c["id"]]]) for c in manifest["chunks"]}
    # A historical render is not current permission to use its reference, including a decoy override.
    # Metadata checks precede even store hashing; digest-bound evidence precedes audio decoding/embedding.
    try:
        for voice_id, digest in set(refs.values()):
            voice = registry["voices"].get(voice_id)
            if voice is None:
                raise policy.Refused("voice_unknown", "reference voice is not currently registered")
            consent = registry["consents"].get(voice["consentId"])
            if consent is None:
                raise policy.Refused("consent_missing", "reference consent is not currently registered")
            if consent["revokedAt"] is not None:
                raise policy.Refused("consent_revoked", "reference consent has been revoked")
            scope = manifest["job"]["scope"]
            if (
                type(scope) is not str
                or scope not in ("OwnContent", "ClientDisclosed")
                or type(voice["scope"]) is not str
                or type(consent["scopes"]) is not list
                or any(type(s) is not str for s in consent["scopes"])
                or type(consent["evidenceSha256"]) is not str
                or not consent["evidenceSha256"]
            ):
                raise policy.Refused("consent_invalid", "reference consent metadata has invalid types")
            if voice["scope"] != scope or scope not in consent["scopes"]:
                raise policy.Refused("consent_scope", "reference consent does not grant the job and voice scope")
            if voice["refClipSha256"] != digest:
                raise policy.Refused("ref_clip_changed", "reference clip differs from the current voice record")
        index = policy.store_index(cfg.store)
        for voice_id, _ in set(refs.values()):
            consent = registry["consents"][registry["voices"][voice_id]["consentId"]]
            if consent["evidenceSha256"] not in index:
                raise policy.Refused(
                    "consent_missing", "reference consent evidence is not in the private store (digest-bound lookup)"
                )
    except (policy.Refused, KeyError, TypeError, ValueError) as error:
        return qa.not_measured(f"reference consent refused: {error}")
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
        windows = []
        if single:
            whole = to16k(Path(run_dir) / "narration.wav", work / "track.wav")
            total = delivered.seconds
            starts = [0.0] if total <= WINDOW_S else [k * HOP_S for k in range(int((total - WINDOW_S) // HOP_S) + 1)]
            if total > WINDOW_S and starts[-1] < total - WINDOW_S - 0.5:
                starts.append(round(total - WINDOW_S, 3))  # the last window ends with the track
            for k, start in enumerate(starts):
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
    if windows:
        wsim = [rows[w]["sim"] for w, _, _, _ in windows]
        out["wsim"] = {"window_s": WINDOW_S, "hop_s": HOP_S, "windows": len(wsim), "min": min(wsim)}
    if not gates["calibrated"]:
        out["note"] = "minSim is uncalibrated: the bench sets it against a decoy; passed is not acceptance"
    return out
