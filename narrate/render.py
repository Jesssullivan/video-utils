"""Render one narration job into a hash-bound run under artifacts/narrate/<run_id>/ (docs/spec/NARRATE.md).

input adapter -> script IR -> (rewrite check) -> policy -> lexical pass -> chunker -> spoken normalisation ->
engine, best of maxTakes per chunk -> pauses -> timing fit -> placement -> two-pass loudnorm -> outputs.

Every refusal happens before any audio is made. The run is staged, renamed into place and then checked by
verify.verify; a run it refuses is renamed .failed-<run_id> and the render raises.

Timing fit, per segment with a target duration: when its natural length runs over, the engine's speed knob is
tried first (at most fit.speed_max), then FFmpeg atempo within the job's fitMaxStretch. What still runs over is
flagged overrun with its excess: never truncated and never stretched further. A segment shorter than its target
is padded with silence. A segment whose target start has passed starts late and is flagged late_start.
"""

import json
import platform
import shutil
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

from . import adapters, audio, chunker, engine, lexical, policy, qa, verify
from .config import guard_out, run
from .ir import canonical, sha256_bytes, sha256_file, sha256_text
from .normalise import Normaliser

SCHEMA_VERSION = 1
MAPPING = "narration_v1"
VOLATILE = ("run_id", "run_dir", "created_utc", "content_sha256")
EPS = 0.001


# CLI / MCP job overrides: name -> (job path, low, high). Booleans only tighten: confidential sets true, no_hosted
# sets allowHosted false. The gates only tighten too (TIGHTEN): an override may lower maxChunkWer or fitMaxStretch
# and raise minSim, never the reverse, so a caller cannot pass a run the job would flag. loudness_lufs is the
# delivery target, not a gate; the loudness pass rule applies around whatever target is recorded. Every override
# applied is recorded in the manifest's job.overrides.
OVERRIDES = {
    "voice": (("voice",), None, None),
    "input_kind": (("input",), None, None),
    "confidential": (("confidential",), None, None),
    "no_hosted": (("allowHosted",), None, None),
    "max_chunk_wer": (("gates", "maxChunkWer"), 0.0, 1.0),
    "min_sim": (("gates", "minSim"), -1.0, 1.0),
    "max_takes": (("gates", "maxTakes"), 1, 3),
    "chunk_max_codepoints": (("chunkMaxCodepoints",), 40, 1000),
    "loudness_lufs": (("post", "loudnessLufs"), -30.0, -10.0),
    "fit_max_stretch": (("post", "fitMaxStretch"), 0.0, 0.08),
}


TIGHTEN = {"max_chunk_wer": "lower", "fit_max_stretch": "lower", "min_sim": "higher"}


def overrides_from(values):
    """{name: value} checked against OVERRIDES; raises RenderError("override_invalid") on a value out of range."""
    out = {}
    for name, value in values.items():
        if name not in OVERRIDES:
            raise RenderError("override_invalid", f"{name}: not a job override")
        _, low, high = OVERRIDES[name]
        if name in ("confidential", "no_hosted"):
            if value is not True:
                raise RenderError("override_invalid", f"{name} only tightens the job: true or absent")
        elif low is not None and not (isinstance(value, (int, float)) and low <= value <= high):
            raise RenderError("override_invalid", f"{name} = {value!r}: from {low} to {high}")
        elif low is None and not (isinstance(value, str) and value):
            raise RenderError("override_invalid", f"{name}: a non-empty id")
        out[name] = value
    return out


def apply_overrides(job, overrides):
    """The job with overrides applied. A gate override that would loosen the job's own gate raises RenderError."""
    job = json.loads(json.dumps(job))
    for name, value in overrides.items():
        path = OVERRIDES[name][0]
        node = job
        for key in path[:-1]:
            node = node[key]
        direction, current = TIGHTEN.get(name), node.get(path[-1])
        if direction and current is not None and (value > current if direction == "lower" else value < current):
            raise RenderError(
                "override_invalid", f"{name} = {value!r} loosens the job's {path[-1]} {current!r}; gates only tighten"
            )
        node[path[-1]] = False if name == "no_hosted" else value
    return job


def summary(final, manifest):
    """What the CLI's --json and the narrate_render tool return: where the run is and what it says of itself."""
    return {
        "run_id": manifest["run_id"],
        "run_dir": str(final),
        "manifest": str(final / "manifest.json"),
        "kind": manifest["kind"],
        "status": manifest["status"],
        "synthetic": manifest["synthetic"],
        "verified": True,
        "engine": manifest["engine"]["id"],
        "voices": sorted({v["voice"] for v in manifest["voices"]}),
        "segments": manifest["input"]["segments"],
        "chunks": manifest["input"]["chunks"],
        "sample_rate": manifest["timeline"]["sample_rate"],
        "seconds": round(manifest["timeline"]["total_samples"] / manifest["timeline"]["sample_rate"], 3),
        "loudness": {**manifest["loudness"]["measured"], "passed": manifest["loudness"]["passed"]},
        "qa": manifest["qa"]["chunks"],
        "overruns": manifest["overruns"],
        "overrides": manifest["job"].get("overrides", {}),
        "flags": manifest["flags"],
        "meets_acceptance_gate": not manifest["flags"],
        "content_sha256": manifest["content_sha256"],
    }


class RenderError(RuntimeError):
    def __init__(self, code, detail):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


def content_digest(manifest):
    return sha256_text(canonical({k: v for k, v in manifest.items() if k not in VOLATILE}))


def chunk_spoken(segment, limit, normaliser):
    """[(chunk, spoken text)]: written chunks, each normalised. A chunk whose spoken form runs past the limit is
    packed again, word by word, so that each piece's spoken form fits."""
    out = []
    for piece in chunker.chunk_segment(segment, limit):
        spoken = normaliser.say(piece.text, segment.id, record=False)
        parts = [(piece.text, piece.oversize)]
        if len(spoken) > limit:
            parts = chunker.pack_words(piece.text, lambda t: len(normaliser.say(t, segment.id, record=False)) <= limit)
        for k, (text, oversize) in enumerate(parts):
            suffix = chr(ord("a") + k) if len(parts) > 1 else ""
            sub = chunker.Chunk(
                id=f"{piece.id}{suffix}",
                segment=piece.segment,
                paragraph=piece.paragraph,
                text=text,
                last_in_paragraph=piece.last_in_paragraph and k == len(parts) - 1,
                oversize=oversize,
            )
            out.append((sub, normaliser.say(text, segment.id)))
    return out


class Renderer:
    def __init__(
        self, cfg, *, input_path=None, rewrite=None, engine_id=None, seed=None, transcriber=None, overrides=None
    ):
        self.cfg = cfg
        self.overrides = dict(overrides or {})
        self.job = apply_overrides(cfg.job(), self.overrides)
        self.registry = cfg.registry()
        self.input_path = Path(input_path).resolve() if input_path else cfg.input
        self.rewrite_path = Path(rewrite).resolve() if rewrite else None
        self.engine_id = engine_id
        self.seed = self.job["seed"] if seed is None else int(seed)
        self.transcriber = transcriber
        self.flags = []

    # -- before any audio ------------------------------------------------------------------------------
    def prepare(self):
        job = self.job
        if self.input_path is None or not self.input_path.is_file():
            raise RenderError("input_missing", "name the script (input in narrate.toml, or --input)")
        input_sha = sha256_file(self.input_path)
        # An empty inputSha256 leaves the input unpinned: recorded as input.pinned false and flagged input_unpinned.
        self.input_pinned = bool(job.get("inputSha256"))
        if self.input_pinned and job["inputSha256"] != input_sha:
            raise RenderError(
                "input_digest_mismatch", f"the input is {input_sha[:12]}, the job pins {job['inputSha256'][:12]}"
            )
        self.input_sha = input_sha
        self.script = adapters.load(job["input"], self.input_path, self.cfg.input_opts)
        self.rewrite = {"status": "none"}
        if self.rewrite_path is not None:
            rewritten = adapters.load(job["input"], self.rewrite_path, self.cfg.input_opts)
            if job["lexical"]["rewriteCheck"]:
                self.rewrite = lexical.check_rewrite(self.script, rewritten)
            else:
                self.rewrite = {"status": "accepted_unchecked", "reason": "the job's rewriteCheck is false"}
            self.rewrite["sha256"] = sha256_file(self.rewrite_path)
            self.script = rewritten
        self.index = policy.store_index(self.cfg.store)
        self.engine, self.voices, self.consents = policy.admit(
            job, self.script, self.registry, self.index, self.engine_id
        )
        self.release = lexical.Release(self.cfg.lexical, job["lexical"])
        table = self.registry["pronunciation"].get(job["pronunciation"])
        if table is None:
            raise RenderError("pronunciation_unknown", f"pronunciation table {job['pronunciation']!r}")
        self.normaliser = Normaliser(table)
        self.refs = {}
        for voice in {v["id"]: v for v in self.voices.values()}.values():
            self.refs[voice["id"]] = {
                "audio": self.index[voice["refClipSha256"]].read_bytes(),
                "text": self.index[voice["refTextSha256"]].read_text(encoding="utf-8").strip(),
            }
        limit = int(job["chunkMaxCodepoints"])
        self.plan = [(segment, chunk_spoken(segment, limit, self.normaliser)) for segment in self.script.segments]
        if not any(chunks for _, chunks in self.plan):
            raise RenderError("input_empty", "nothing to speak")

    # -- audio -------------------------------------------------------------------------------------------
    def measure(self, pcm, text, work):
        if self.transcriber is not None:
            heard = self.transcriber(pcm, text)
            wer = {"status": "measured", "value": qa.wer(text, heard), "heard": heard}
        elif self.whisper_ready[0]:
            heard = self.whisper.read(pcm)
            wer = {"status": "measured", "value": qa.wer(text, heard), "heard": heard}
        else:
            wer = qa.not_measured(self.whisper_ready[1])
        return {"wer": wer, "sim": qa.sim(self.cfg)}

    def synth_chunk(self, chunk, spoken, voice, speed, work):
        rate = self.engine.get("sampleRateHz")

        def synth(seed):
            data, facts = engine.synthesize(
                self.engine, spoken, voice, self.refs[voice["id"]], seed, speed, self.cfg.engine_opts
            )
            pcm, converted = audio.canonical(data, rate or self.rate, work)
            if self.rate is None:
                self.rate = pcm.rate
            return pcm, {**facts, "reply_sha256": sha256_bytes(data), "converted": converted}

        return qa.best_of(spoken, synth, lambda pcm, text: self.measure(pcm, text, work), self.job["gates"], self.seed)

    def assemble(self, segment, synthesized):
        """(segment pcm, [(chunk, start_s, end_s)]) with sentence, paragraph and direction pauses."""
        post = self.job["post"]
        pcm = audio.Pcm(self.rate)
        offsets = []
        pauses = {}
        for d in segment.directions:
            if d.kind == "pause":
                pauses[d.paragraph] = pauses.get(d.paragraph, 0) + (
                    d.pause_ms if d.pause_ms is not None else post["paragraphPauseMs"]
                )
        last_paragraph = None
        for chunk, _spoken, take, _record in synthesized:
            if last_paragraph is None:
                pcm.silence(pauses.get(chunk.paragraph, 0) / 1000)
            elif chunk.paragraph != last_paragraph:
                pcm.silence(max(post["paragraphPauseMs"], pauses.get(chunk.paragraph, 0)) / 1000)
            else:
                pcm.silence(post["sentencePauseMs"] / 1000)
            start = pcm.seconds
            pcm.extend(take)
            offsets.append((chunk, start, pcm.seconds))
            last_paragraph = chunk.paragraph
        end_pause = pauses.get(len(segment.paragraphs()), 0)
        pcm.silence(end_pause / 1000)
        return pcm, offsets

    def voice_for(self, segment):
        """policy.voice_map keys a named speaker only when the job maps speakers; every other segment is None."""
        return self.voices[segment.speaker if segment.speaker in self.voices else None]

    def segment_audio(self, segment, chunks, work, staging):
        voice = self.voice_for(segment)
        fit = {"natural_s": None, "speed": 1.0, "atempo": 1.0, "overrun_s": 0.0, "flags": []}

        def synthesize_all(speed):
            out = []
            for chunk, spoken in chunks:
                take, facts, record = self.synth_chunk(chunk, spoken, voice, speed, work)
                out.append((chunk, spoken, take, {**record, "speed": speed, "engine_facts": facts}))
            return out

        synthesized = synthesize_all(1.0)
        pcm, offsets = self.assemble(segment, synthesized)
        fit["natural_s"] = round(pcm.seconds, 4)
        target = segment.target_dur
        if target is not None and pcm.seconds > target + EPS:
            speed = min(pcm.seconds / target, float(self.cfg.fit["speed_max"]))
            if speed > 1 + 1e-4:
                synthesized = synthesize_all(round(speed, 4))
                pcm, offsets = self.assemble(segment, synthesized)
                fit["speed"] = round(speed, 4)
            if pcm.seconds > target + EPS:
                factor = min(pcm.seconds / target, 1 + float(self.job["post"]["fitMaxStretch"]))
                stretched = audio.atempo(pcm, factor, work)
                scale = stretched.seconds / pcm.seconds if pcm.seconds else 1.0
                offsets = [(c, a * scale, b * scale) for c, a, b in offsets]
                pcm = stretched
                fit["atempo"] = round(factor, 6)
            if pcm.seconds > target + EPS:
                fit["overrun_s"] = round(pcm.seconds - target, 4)
                fit["flags"].append("overrun")
        records = []
        for (chunk, spoken, take, record), (_, a, b) in zip(synthesized, offsets, strict=True):
            name = f"chunks/{chunk.id}.wav"
            take.write(staging / name)
            records.append(
                {
                    "id": chunk.id,
                    "segment": segment.id,
                    "paragraph": chunk.paragraph,
                    "written": chunk.text,
                    "spoken": spoken,
                    "codepoints": len(spoken),
                    "oversize": chunk.oversize or len(spoken) > int(self.job["chunkMaxCodepoints"]),
                    "file": name,
                    "seconds": round(take.seconds, 4),
                    "in_segment_s": [round(a, 4), round(b, 4)],
                    "qa": record,
                }
            )
        return pcm, records, fit, voice

    def run(self, root=None):
        self.prepare()
        cfg = self.cfg
        self.rate = self.engine.get("sampleRateHz")
        self.whisper = qa.Whisper(cfg)
        self.whisper_ready = (False, "a transcriber was injected") if self.transcriber else self.whisper.available()
        root = guard_out(Path(root or cfg.out))
        root.mkdir(parents=True, exist_ok=True)
        run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:12]
        final, staging = root / run_id, root / f".staging-{run_id}"
        (staging / "chunks").mkdir(parents=True)
        try:
            with tempfile.TemporaryDirectory() as work:
                record = self.build(staging, Path(work), run_id, final)
            staging.rename(final)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        receipt = verify.verify(final)
        if not receipt["ok"]:
            final.rename(root / f".failed-{run_id}")
            raise RenderError("verify_refused", f"{run_id} kept as .failed-{run_id}: {receipt['reason']}")
        self.manifest = record
        return final

    def build(self, staging, work, run_id, final):
        job, post = self.job, self.job["post"]
        out = None
        segments, chunk_records, cursor = [], [], 0.0
        for segment, chunks in self.plan:
            if not chunks:
                continue
            pcm, records, fit, voice = self.segment_audio(segment, chunks, work, staging)
            if out is None:
                out = audio.Pcm(self.rate)
            gap = post["paragraphPauseMs"] / 1000 if segments and segment.target_start is None else 0.0
            start = cursor + gap if segment.target_start is None else max(cursor, segment.target_start)
            late = round(start - segment.target_start, 4) if segment.target_start is not None else 0.0
            if late > EPS:
                fit["flags"].append("late_start")
            out.silence(start - out.seconds)
            start = out.seconds  # whole samples
            out.extend(pcm)
            end = out.seconds
            padded = 0.0
            if segment.target_dur is not None and end - start < segment.target_dur - EPS:
                padded = segment.target_dur - (end - start)
                out.silence(padded)
            cursor = out.seconds
            for r in records:
                a, b = r.pop("in_segment_s")
                r["out_start_s"], r["out_end_s"] = round(start + a, 4), round(start + b, 4)
            chunk_records += records
            segments.append(
                {
                    "id": segment.id,
                    "speaker": segment.speaker,
                    "voice": voice["id"],
                    "origin": segment.origin,
                    "out_start_s": round(start, 4),
                    "out_end_s": round(end, 4),
                    "target_start_s": segment.target_start,
                    "target_dur_s": segment.target_dur,
                    "natural_s": fit["natural_s"],
                    "delivered_s": round(end - start, 4),
                    "speed": fit["speed"],
                    "atempo": fit["atempo"],
                    "stretch_applied": fit["atempo"] != 1.0 or fit["speed"] != 1.0,
                    "late_start_s": late if late > EPS else 0.0,
                    "padded_s": round(padded, 4),
                    "overrun_s": fit["overrun_s"],
                    "flags": fit["flags"],
                    "chunks": [
                        {"id": r["id"], "out_start_s": r["out_start_s"], "out_end_s": r["out_end_s"]} for r in records
                    ],
                }
            )
        raw = out.write(work / "narration.raw.wav")
        delivered = staging / "narration.wav"
        loud = audio.loudnorm(raw, delivered, self.rate, post["loudnessLufs"], post["truePeakDbtp"])
        integrated, lra, peak = audio.ebur128(delivered)
        final_pcm = audio.read(delivered)
        passed, loud_flags = audio.loudness_verdict(integrated, peak, post, loud["normalization_type"])
        loudness = {
            "target_lufs": post["loudnessLufs"],
            "true_peak_target_dbtp": post["truePeakDbtp"],
            "tolerance_lu": post["loudnessToleranceLu"],
            "loudnorm": loud,
            "measured": {"integrated_lufs": integrated, "loudness_range_lu": lra, "true_peak_dbtp": peak},
            "deviation_lu": round(integrated - post["loudnessLufs"], 2),
            "peak_tolerance_db": audio.PEAK_TOLERANCE_DB,
            "passed": passed,
            "flags": loud_flags,
            "samples_before": len(out.samples),
            "samples_after": len(final_pcm.samples),
        }
        # Both forms of the same samples: the job's audio format names the one consumers take first.
        audio.flac(delivered, staging / "narration.flac")
        files = {"narration.wav": delivered, "narration.flac": staging / "narration.flac"}
        label = any(c["syntheticLabelRequired"] for c in self.consents.values())
        caption_files = write_captions(staging, chunk_records, job["captions"], label)
        files.update(caption_files)
        edl = {
            "schema_version": SCHEMA_VERSION,
            "kind": "narration_edl",
            "mapping": MAPPING,
            "sample_rate": self.rate,
            "total_samples": len(final_pcm.samples),
            "total_seconds": round(final_pcm.seconds, 4),
            "output_axis": "delivered sample index / sample_rate of narration.wav",
            "source_axis": "none: narration is a new track; no source media is time-stretched",
            "segments": segments,
        }
        (staging / "narration.edl.json").write_text(json.dumps(edl, indent=1) + "\n")
        files["narration.edl.json"] = staging / "narration.edl.json"
        ir = self.script.to_json()
        (staging / "ir.json").write_text(json.dumps(ir, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
        files["ir.json"] = staging / "ir.json"
        for r in chunk_records:
            files[r["file"]] = staging / r["file"]
        digests = {name: sha256_file(path) for name, path in sorted(files.items())}
        overruns = [{"segment": s["id"], "overrun_s": s["overrun_s"]} for s in segments if "overrun" in s["flags"]]
        # A chunk whose kept take was never measured is not a pass: wer_not_measured and sim_not_measured say so.
        unmeasured = {
            f"{metric}_not_measured"
            for r in chunk_records
            for metric in ("wer", "sim")
            if r["qa"][f"{metric}_status"] != "measured"
        }
        flags = sorted(
            {f for s in segments for f in s["flags"]}
            | {f for r in chunk_records for f in r["qa"]["flags"]}
            | set(loud_flags)
            | unmeasured
            | ({"oversize_chunk"} if any(r["oversize"] for r in chunk_records) else set())
            | ({"input_unpinned"} if not self.input_pinned else set())
        )
        statuses = [r["qa"]["status"] for r in chunk_records]
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "kind": "narration_render",
            "status": "rendered_unreviewed",
            "synthetic": True,
            "run_id": run_id,
            "run_dir": str(final.resolve()),
            "created_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "job": {
                k: job[k]
                for k in (
                    "id",
                    "scope",
                    "confidential",
                    "allowHosted",
                    "chunkMaxCodepoints",
                    "gates",
                    "post",
                    "audio",
                    "captions",
                    "narrationEdl",
                )
            }
            | {"seed": self.seed}
            | ({"overrides": self.overrides} if self.overrides else {}),
            "input": {
                "kind": self.script.kind,
                "sha256": self.input_sha,
                "pinned": self.input_pinned,
                "ir_file": "ir.json",
                "ir_sha256": sha256_text(canonical(ir)),
                "segments": len(segments),
                "chunks": len(chunk_records),
                "meta": self.script.meta,
                "rewrite": self.rewrite,
            },
            "lexical": {
                **self.release.record(),
                "findings": lexical.findings(self.release, self.script.segments),
                "vale": lexical.vale(self.release, self.script.segments),
            },
            "pronunciation": self.normaliser.record(),
            "engine": engine_record(self.engine, self.cfg),
            "voices": [
                voice_record(speaker, v, self.consents)
                for speaker, v in sorted(self.voices.items(), key=lambda kv: str(kv[0]))
            ],
            "chunks": chunk_records,
            "qa": {
                "wer": {
                    "available": self.whisper_ready[0] or self.transcriber is not None,
                    "how": "injected transcriber" if self.transcriber else self.whisper_ready[1],
                    "max_chunk_wer": job["gates"]["maxChunkWer"],
                    **({} if self.transcriber else self.whisper.identity()),
                },
                "sim": qa.sim(self.cfg),
                "calibrated": job["gates"]["calibrated"],
                "chunks": {s: statuses.count(s) for s in ("passed", "failed", "not_measured")},
            },
            "overruns": overruns,
            "loudness": loudness,
            "timeline": {
                "mapping": MAPPING,
                "no_time_stretch": False,
                "edl": {"file": "narration.edl.json", "sha256": digests["narration.edl.json"]},
                "sample_rate": self.rate,
                "total_samples": len(final_pcm.samples),
                "stretch_applied": any(s["stretch_applied"] for s in segments),
                "output_axis": edl["output_axis"],
                "source_axis": edl["source_axis"],
            },
            "captions": {"source": "script_timing", "files": sorted(caption_files), "synthetic_notice": label},
            "licence_notices": [self.engine["licenceNotice"]] if self.engine.get("licenceNotice") else [],
            "watermark": {"status": "not_applied", "note": "best effort when applied; codecs and resynthesis strip it"},
            "flags": flags,
            "output_sha256": digests,
            "tools": tools(),
        }
        manifest["content_sha256"] = content_digest(manifest)
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n")
        return manifest


def engine_record(eng, cfg):
    keep = (
        "id",
        "profile",
        "backend",
        "model",
        "hfRepo",
        "hfRevision",
        "files",
        "licence",
        "licenceNotice",
        "hosted",
        "estateControlled",
        "confidentialAllowed",
        "sampleRateHz",
    )
    return {
        **{k: eng.get(k) for k in keep},
        "may_run_confidential": policy.may_run_confidential(eng),
        "knobs": {
            "fit_speed_max": cfg.fit["speed_max"],
            "ref_audio": cfg.engine_opts["ref_audio"],
            "timeout_s": cfg.engine_opts["timeout_s"],
        },
    }


def voice_record(speaker, voice, consents):
    consent = consents[voice["consentId"]]
    return {
        "speaker": speaker,
        "voice": voice["id"],
        "ref_clip_sha256": voice["refClipSha256"],
        "ref_text_sha256": voice["refTextSha256"],
        "consent_id": consent["id"],
        "scope": voice["scope"],
        "fixture": voice["fixture"],
        "synthetic_label_required": consent["syntheticLabelRequired"],
        "hosted_allowed": consent["hostedAllowed"],
    }


def stamp(seconds, sep):
    ms = round(seconds * 1000)
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def write_captions(staging, chunks, formats, label):
    """SRT and/or WebVTT, one cue per chunk on the output clock, in the written (not the spoken) text."""
    cues = [(c["out_start_s"], c["out_end_s"], c["written"]) for c in chunks]
    if label and cues:
        a, b, text = cues[0]
        cues[0] = (a, b, "[Synthetic voice] " + text)
    files = {}
    if "Srt" in formats:
        body = "".join(f"{i}\n{stamp(a, ',')} --> {stamp(b, ',')}\n{t}\n\n" for i, (a, b, t) in enumerate(cues, 1))
        (staging / "narration.srt").write_text(body)
        files["narration.srt"] = staging / "narration.srt"
    if "Vtt" in formats:
        note = "NOTE This narration is a synthetic voice.\n\n" if label else ""
        body = "WEBVTT\n\n" + note + "".join(f"{stamp(a, '.')} --> {stamp(b, '.')}\n{t}\n\n" for a, b, t in cues)
        (staging / "narration.vtt").write_text(body)
        files["narration.vtt"] = staging / "narration.vtt"
    return files


def tools():
    version = run("ffmpeg", "-hide_banner", "-version").stdout.splitlines()[0]
    return {"ffmpeg": version, "python": platform.python_version(), "narrate_schema": SCHEMA_VERSION}


def render(cfg, **kwargs):
    root = kwargs.pop("root", None)
    renderer = Renderer(cfg, **kwargs)
    final = renderer.run(root)
    return final, renderer.manifest
