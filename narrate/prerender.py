"""Two-phase rendering for an engine that runs out of process as a batch (backend AudioCppBatch).

audio.cpp's `audiocpp_cli` has no server at the pinned commit: it loads the model once per `--request-sequence`
file and writes one WAV per request. Such an engine cannot answer a render chunk by chunk, so a render runs in
three phases (docs/spec/NARRATE.md, "Out-of-process batch engines"):

  A, CPU host   `narrate plan CONFIG --out DIR` runs the whole text pipeline of a render (adapters, lexical pass,
                chunker, normaliser with ranges and amounts) and writes the request batch, every chunk times the
                takes the job may keep, each take with its seed:
                  DIR/plan.json               chunk -> request ids, batch and reference digests
                  DIR/requests/<voice>.json   {"requests": [...]}, audiocpp_cli's request-sequence format
                  DIR/refs/<sha256>.wav       the reference clip each request names, copied from the store
  B, GPU host   narrate/serve/audiocpp_batch.py runs audiocpp_cli once per requests file, inside the window's
                bounds, and writes DIR/wav/<id>.wav and DIR/receipts/<voice>.json (binary, weights, requests and
                reference digests, and each output's sha256).
  C, CPU host   `narrate render CONFIG --prerendered DIR` runs the render with this module standing in for the
                engine: each take is looked up by the id of the request the render would have sent, and QA,
                best of maxTakes, timing fit, loudness, captions, EDL, manifest and verify run as for any engine.

A request id is a digest of the request's content (text, seed, reference digests and transcript), so a WAV named
by an id answers exactly that request, batches of many runs merge without collisions, and a render whose text,
seed or reference changed after its plan finds no take and is refused before any audio is made. A receipt is
trusted only when its requests file has the digest it names, every request in it carries its own content's id,
its binary and weights are among the engine record's pinned files, and each output has the sha256 it lists.

VoxCPM2 (family voxcpm2 at audio.cpp 47c2756e) clones in one of two ways, `[engine] audiocpp_clone`:
  ultimate    voice_ref and audio both name the reference and reference_text is its transcript plus one space
              (the pin joins prompt and target text with no separator); the model card's "ultimate" clone.
  reference   voice_ref alone; the transcript is not used.
Its AudioVAE encoder takes at most 240000 samples at 16 kHz after padding to a multiple of 2560 (14.88 s), so a
longer reference is refused when the plan is made (ref_clip_misfit), as is one under 5 s.
"""

import hashlib
import io
import json
import math
import re
import urllib.parse
import wave
from pathlib import Path

from .ir import canonical, sha256_bytes, sha256_file

BACKEND = "AudioCppBatch"
PLAN_SCHEMA = "narrate-prerender-plan/1"
RECEIPT_SCHEMA = "narrate-audiocpp-batch-receipt/1"
CLONES = ("ultimate", "reference")
FAMILIES = {
    # audio.cpp 47c2756e: voxcpm2.audiovae_encoder_sample_capacity at audio_vae_config.sample_rate, padded to
    # patch_size x prod(encoder_rates) = 4 x 640; the 5 s floor is the VoxCPM2 usage guide's practical range.
    "voxcpm2": {"task": "clon", "encoder_rate": 16000, "capacity": 240000, "pad": 2560, "min_s": 5.0},
}
ID_LENGTH = 32
SHA256 = re.compile(r"^[0-9a-f]{64}$")
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
MAX_JSON_BYTES = 64 << 20


class PrerenderError(RuntimeError):
    """A plan or a prerendered take narrate refuses. code is the typed refusal."""

    def __init__(self, code, detail):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


def is_batch(engine):
    return engine.get("backend") == BACKEND


def family(engine):
    """The audio.cpp model family an AudioCppBatch engine names in its endpoint, audiocpp://<family>."""
    p = urllib.parse.urlsplit(engine.get("endpoint") or "")
    name = p.netloc
    if p.scheme != "audiocpp" or name not in FAMILIES or p.path not in ("", "/") or p.query or p.fragment:
        raise PrerenderError(
            "engine_endpoint_invalid",
            f"engine {engine['id']}: an AudioCppBatch endpoint is audiocpp://<family>, one of {sorted(FAMILIES)}",
        )
    return name


def clone_mode(options):
    mode = options.get("audiocpp_clone", "ultimate")
    if mode not in CLONES:
        raise PrerenderError("config_invalid", f"engine.audiocpp_clone = {mode!r}: one of {', '.join(CLONES)}")
    return mode


def check_engine(engine, options):
    """Refuse an AudioCppBatch record narrate cannot bind a take to: a bad endpoint, no pinned files, a clone mode
    it does not know, or a reference sent by any route other than the request (ref_audio omit)."""
    family(engine)
    clone_mode(options)
    files = engine.get("files") or []
    if not files or any(not SHA256.match(str(f.get("sha256", ""))) for f in files):
        raise PrerenderError(
            "engine_unpinned",
            f"engine {engine['id']}: an AudioCppBatch record lists the audiocpp_cli binary and the weights with "
            "their sha256 in files",
        )
    if options.get("ref_audio") != "data_uri":
        raise PrerenderError("config_invalid", "an AudioCppBatch engine clones from the reference: ref_audio data_uri")


def reference_fit(engine, voice_id, audio):
    """{seconds, sample_rate, encoder_samples} of a reference clip, or PrerenderError ref_clip_misfit when the
    family's encoder cannot take it."""
    spec = FAMILIES[family(engine)]
    try:
        with wave.open(io.BytesIO(audio)) as w:
            rate, frames = w.getframerate(), w.getnframes()
    except (wave.Error, EOFError) as error:
        raise PrerenderError("ref_clip_misfit", f"voice {voice_id}: the reference is not a WAV ({error})") from None
    seconds = frames / rate if rate else 0.0
    resampled = math.ceil(frames * spec["encoder_rate"] / rate) if rate else 0
    padded = math.ceil(resampled / spec["pad"]) * spec["pad"]
    if padded > spec["capacity"] or seconds < spec["min_s"]:
        most = (spec["capacity"] // spec["pad"]) * spec["pad"] / spec["encoder_rate"]
        raise PrerenderError(
            "ref_clip_misfit",
            f"voice {voice_id}: the reference is {seconds:.2f} s; {family(engine)} takes {spec['min_s']:g} to "
            f"{most:.2f} s (cut it with narrate/bench/ref_cut.py and register the cut)",
        )
    return {"seconds": round(seconds, 3), "sample_rate": rate, "encoder_samples": padded}


def ref_file(sha):
    return f"refs/{sha}.wav"


def request(engine, options, voice, ref, text, seed):
    """The audiocpp_cli request for one take, its id included."""
    clip = ref_file(voice["refClipSha256"])
    body = {"text": text, "seed": int(seed), "voice_ref": clip}
    if clone_mode(options) == "ultimate":
        body["audio"] = clip  # the continuation prompt the reference_text transcribes
        body["reference_text"] = ref["text"] + " "  # the pin joins prompt and target text with no separator
    return {"id": request_id(body), **body}


def request_id(body):
    """The digest of a request's content without its id: narrate/serve/audiocpp_batch.py computes the same."""
    content = {k: v for k, v in body.items() if k != "id"}
    return hashlib.sha256(canonical(content).encode("utf-8")).hexdigest()[:ID_LENGTH]


def batch_bytes(requests):
    return (json.dumps({"requests": requests}, indent=1, ensure_ascii=False) + "\n").encode("utf-8")


def read_json(path, what):
    path = Path(path)
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_JSON_BYTES:
            raise OSError("not a regular file of at most 64 MiB")
        data = path.read_bytes()
        return json.loads(data), sha256_bytes(data)
    except (OSError, ValueError) as error:
        raise PrerenderError("prerendered_invalid", f"{what} {path.name}: {error}") from None


def inside(root, relative):
    """root/relative when relative is a plain path inside root, else None."""
    if not isinstance(relative, str) or not relative or relative.startswith("/") or "\\" in relative:
        return None
    parts = relative.split("/")
    if any(p in ("", ".", "..") for p in parts):
        return None
    return root.joinpath(*parts)


class NoTake(LookupError):
    """The pool holds no output for this request (it was not planned, or the batch stopped before it)."""

    def __init__(self, request_id):
        super().__init__(request_id)
        self.request_id = request_id


class Pool:
    """The takes a prerendered directory holds, each bound to its request, its receipt and the engine's pins."""

    def __init__(self, root, engine, options):
        self.root = Path(root).resolve()
        self.engine, self.family, self.clone = engine, family(engine), clone_mode(options)
        if not self.root.is_dir():
            raise PrerenderError("prerendered_missing", "--prerendered names no directory")
        pins = {f["sha256"] for f in engine.get("files") or []}
        self.takes, self.batches = {}, []
        receipts = sorted((self.root / "receipts").glob("*.json")) if (self.root / "receipts").is_dir() else []
        if not receipts:
            raise PrerenderError("prerendered_missing", "the directory holds no receipts/*.json from a batch run")
        for path in receipts:
            self.load(path, pins)

    def load(self, path, pins):
        receipt, receipt_sha = read_json(path, "receipt")
        name = path.name

        def refuse(code, why):
            raise PrerenderError(code, f"receipt {name}: {why}")

        if not isinstance(receipt, dict) or receipt.get("schema") != RECEIPT_SCHEMA:
            refuse("prerendered_invalid", f"schema is not {RECEIPT_SCHEMA}")
        for key in ("binary_sha256", "model_sha256"):
            if receipt.get(key) not in pins:
                refuse("prerendered_engine_mismatch", f"{key} is not a file the engine {self.engine['id']} pins")
        if receipt.get("family") != self.family or receipt.get("task") != FAMILIES[self.family]["task"]:
            refuse("prerendered_engine_mismatch", f"family or task differ from {self.family}")
        requests_path = inside(self.root, receipt.get("requests_file"))
        if requests_path is None:
            refuse("prerendered_invalid", "requests_file is not a path inside the directory")
        batch, batch_sha = read_json(requests_path, "requests file")
        if batch_sha != receipt.get("requests_sha256"):
            refuse("prerendered_batch_mismatch", "the requests file's sha256 differs from requests_sha256")
        refs = receipt.get("refs") if isinstance(receipt.get("refs"), dict) else {}
        for rel, sha in refs.items():
            if rel != ref_file(sha) or not SHA256.match(str(sha)):
                refuse("prerendered_invalid", f"reference {rel} is not named by its sha256")
        outputs = receipt.get("outputs") if isinstance(receipt.get("outputs"), dict) else {}
        requests = batch.get("requests") if isinstance(batch, dict) else None
        if not isinstance(requests, list):
            refuse("prerendered_invalid", "the requests file holds no requests list")
        listed = set()
        for body in requests:
            if not isinstance(body, dict) or body.get("id") != request_id(body):
                refuse("prerendered_batch_mismatch", "a request's id is not the digest of its content")
            for key in ("voice_ref", "audio"):
                if key in body and body[key] not in refs:
                    refuse("prerendered_invalid", f"request {body['id']} names a reference the receipt did not check")
            listed.add(body["id"])
            out = outputs.get(body["id"])
            if out is None:
                continue
            if (
                not isinstance(out, dict)
                or out.get("file") != f"wav/{body['id']}.wav"
                or not SHA256.match(str(out.get("sha256")))
            ):
                refuse("prerendered_invalid", f"output {body['id']} is not wav/<id>.wav with a sha256")
            self.takes.setdefault(body["id"], (out, len(self.batches)))
        if set(outputs) - listed:
            refuse("prerendered_invalid", "it lists an output for a request its requests file does not hold")
        self.batches.append(
            {
                "receipt": name,
                "receipt_sha256": receipt_sha,
                "requests_file": receipt["requests_file"],
                "requests_sha256": batch_sha,
                "requests": len(requests),
                "outputs": len(outputs),
                "runtime": receipt.get("runtime"),
                "audiocpp_commit": receipt.get("audiocpp_commit"),
                "binary_sha256": receipt["binary_sha256"],
                "model_sha256": receipt["model_sha256"],
                "exit_code": receipt.get("exit_code"),
                "stop_rule": receipt.get("stop_rule"),
                "test_mode": receipt.get("test_mode") is True,
                "used": 0,
            }
        )

    def has(self, request_id):
        return request_id in self.takes

    def take(self, body):
        """(WAV bytes, facts) for one request, or NoTake. A file whose sha256 differs from its receipt is refused."""
        rid = body["id"]
        if rid not in self.takes:
            raise NoTake(rid)
        out, index = self.takes[rid]
        path = self.root / out["file"]
        if path.is_symlink() or not path.is_file() or sha256_file(path) != out["sha256"]:
            raise PrerenderError("prerendered_take_mismatch", f"wav/{rid}.wav differs from its receipt")
        batch = self.batches[index]
        batch["used"] += 1
        facts = {
            "variant": "audiocpp_prerendered",
            "request_id": rid,
            "requests_sha256": batch["requests_sha256"],
            "receipt_sha256": batch["receipt_sha256"],
            "out_of_process": True,
            "speed_honoured": False,
            "conditioning": self.clone,
            "ref_audio_used": True,
            "ref_text_used": self.clone == "ultimate",
        }
        return path.read_bytes(), facts

    def record(self):
        """What the manifest says of the synthesis: out of process, by which runtime, binary, weights and batches."""
        used = [b for b in self.batches if b["used"]]
        return {
            "mode": "out_of_process_batch",
            "runtime": "audio.cpp audiocpp_cli --request-sequence",
            "family": self.family,
            "clone": self.clone,
            "audiocpp_commits": sorted({str(b["audiocpp_commit"]) for b in used}),
            "binary_sha256": sorted({b["binary_sha256"] for b in used}),
            "model_sha256": sorted({b["model_sha256"] for b in used}),
            "batches": [dict(b) for b in used],
            "test_mode": any(b["test_mode"] for b in used),
        }


def write_plan(out, plan, batches, refs):
    """Write a plan directory: refs/, requests/ and plan.json. out must not exist yet."""
    out = Path(out)
    try:
        out.mkdir(parents=True)
    except FileExistsError:
        raise PrerenderError("plan_exists", f"{out.name} exists; every plan gets a new directory") from None
    out.chmod(0o700)
    (out / "refs").mkdir()
    (out / "requests").mkdir()
    for sha, data in refs.items():
        (out / ref_file(sha)).write_bytes(data)
    for name, data in batches.items():
        (out / "requests" / f"{name}.json").write_bytes(data)
    (out / "plan.json").write_text(json.dumps(plan, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return out / "plan.json"


def batch_name(voice_id):
    """A requests file name for a voice: its id when that is a plain file name, else a digest of it."""
    return voice_id if NAME.match(voice_id) else "voice-" + sha256_bytes(voice_id.encode("utf-8"))[:16]
