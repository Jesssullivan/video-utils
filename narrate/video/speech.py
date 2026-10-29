"""The speech stages of lane L4: script, voice and voice_qa (docs/spec/NARRATED_VIDEO.md, "Stages").

- script reads one segment's script from the private store through its narrate job's input adapter, records the
  spoken-text digest and the pinned xoxd-lexical release's findings. Findings are advisory (R-N12): they never refuse.
- voice renders the segment with narrate (`narrate.render`, tool 58) into its stage directory. The narrate run keeps
  its own manifest, mapping narration_v1 and verification; the stage manifest adds the labels. `stage JOB voice
  --from-run RUN_DIR` adopts a run narrate already rendered instead (an AudioCppBatch engine's
  `narrate render --prerendered`): the run is copied in, re-verified and bound to the voice key, never voiced again.
- voice_qa re-verifies that run and scores it with `narrate.evaluate` (tool 61) against the narrate job's gates. A
  measured gate that fails refuses voice_qa_failed. A metric the host cannot measure stays not_measured, and the
  operator's listening receipt stays pending_operator: voice_qa never marks listening passed.

voice and voice_qa carry only the labels a narrate run yields (synthetic, consent ids, voice ids) and no persona. The
persona joins the chain at place, whose key holds labels.persona, so a persona change reruns place and what follows it
and never re-synthesises a voice.

The script is copied to a fixed name before narrate reads it, so the run's IR and content digest depend on the
script's bytes and never on its name in the store.
"""

import json
import shutil
from pathlib import Path

from .. import adapters, evaluate, lexical, render, spoken, verify
from ..adapters import InputError
from ..config import Config, ConfigError, in_guitar_runs
from ..engine import EngineError
from ..ir import canonical, sha256_text
from ..lexical import LexicalError
from ..normalise import NormaliseError
from ..policy import Refused
from ..registry import RegistryError
from . import graph, labels
from .common import StageRefused, upstream, work_dir, write_json
from .keys import normalise
from .store import StoreError, files_under

SUFFIX = {"Markdown": ".md", "PlainText": ".txt", "Srt": ".srt", "Vtt": ".vtt", "Dialog": ".txt"}
RUN = "narration"  # the narrate run directory inside a voice stage directory
NARRATE_ERRORS = (Refused, LexicalError, EngineError, render.RenderError, RegistryError, ConfigError)


def segment_of(rc, row):
    return next(s for s in rc.job["segments"] if s["id"] == row["segment"])


def script_copy(rc, segment, kind, work):
    """The segment's script from the private store, copied into work under a fixed name."""
    if kind not in SUFFIX:
        raise StageRefused("input_kind_unsupported", f"a narrated-video segment reads {', '.join(SUFFIX)}")
    target = work / f"script{SUFFIX[kind]}"
    shutil.copyfile(rc.env.source(segment["scriptSha256"], f"segment {segment['id']}'s script"), target)
    return target


def narrate_config(rc, narrate_job_id, script, out, work):
    """A narrate.toml in work naming the records, the private store, the lexical release and out."""
    env = rc.env
    values = {
        "input": str(script),
        "job": str(env.record_file("jobs.json")),
        "job_id": narrate_job_id,
        "engines": str(env.record_file("engines.json")),
        "voices": str(env.record_file("voices.json")),
        "consents": str(env.record_file("consents.json")),
        "pronunciation": str(env.record_file("pronunciation.json")),
        "store": str(env.store_dir),
        "lexical": str(env.lexical or ""),
        "out": str(out),
    }
    toml = work / "narrate.toml"
    toml.write_text("".join(f"{k} = {json.dumps(v)}\n" for k, v in values.items()), encoding="utf-8")
    try:
        return Config(toml)
    except (ConfigError, ValueError, KeyError) as exc:
        raise StageRefused("config_invalid", str(exc)[:200], verdict=False) from None


# script ---------------------------------------------------------------------------------------------------------
def run_script(rc, row, partial):
    segment = segment_of(rc, row)
    narrate_job = rc.records["jobs"][segment["narrateJob"]]
    kind = narrate_job["input"]
    with work_dir(rc.store) as work:
        path = script_copy(rc, segment, kind, work)
        try:
            script = adapters.load(kind, path)
        except (InputError, NormaliseError, UnicodeDecodeError, ValueError) as exc:
            raise StageRefused("input_invalid", str(exc)[:200]) from None
        voiced = spoken.lines(script)
        try:
            release = lexical.Release(rc.env.lexical, narrate_job["lexical"])
        except LexicalError as exc:
            raise StageRefused(exc.code, exc.detail, verdict=False) from None
        findings = lexical.findings(release, script.segments)
        vale = lexical.vale(release, script.segments)
    write_json(
        partial / "lexical.json",
        {"release": release.record(), "findings": findings, "vale": vale, "advisory": True, "rule": "R-N12"},
    )
    measured = {
        "input_kind": kind,
        "segments": len(script.segments),
        "spoken_sha256": sha256_text(voiced),
        "spoken_codepoints": len(voiced),
        "lexical_findings": len(findings["findings"]),
        "vale": vale["status"],
    }
    write_json(partial / "script.json", measured | {"script_sha256": segment["scriptSha256"]})
    return {"measurements": measured, "states": {"lexical": "advisory"}}


# voice ----------------------------------------------------------------------------------------------------------
def run_voice(rc, row, partial):
    if getattr(rc, "from_run", None) is not None:
        return adopt_voice(rc, row, partial)
    segment = segment_of(rc, row)
    narrate_job = rc.records["jobs"][segment["narrateJob"]]
    out = partial / ".narrate"
    with work_dir(rc.store) as work:
        script = script_copy(rc, segment, narrate_job["input"], work)
        cfg = narrate_config(rc, segment["narrateJob"], script, out, work)
        try:
            final, manifest = render.render(cfg, root=out)
        except NARRATE_ERRORS as exc:
            raise StageRefused(exc.code, exc.detail, verdict=False) from None
        except (InputError, NormaliseError) as exc:
            raise StageRefused("input_invalid", str(exc)[:200]) from None
    final.rename(partial / RUN)
    shutil.rmtree(out)
    return voice_fields(manifest, {"source_checks": "passed", "render": "local", "listening": "pending_operator"})


def voice_fields(manifest, states, adopted=None):
    """The voice stage manifest's parts for a narrate run's manifest, rendered here or adopted."""
    consent_ids = sorted({v["consent_id"] for v in manifest["voices"]})
    voice_ids = sorted({v["voice"] for v in manifest["voices"]})
    rate = manifest["timeline"]["sample_rate"]
    measured = {
        "narrate_run": RUN,
        "narrate_content_sha256": manifest["content_sha256"],
        "narration_sha256": manifest["output_sha256"]["narration.wav"],
        "sample_rate": rate,
        "total_samples": manifest["timeline"]["total_samples"],
        "seconds": round(manifest["timeline"]["total_samples"] / rate, 6),
        "integrated_lufs": manifest["loudness"]["measured"]["integrated_lufs"],
        "engine": manifest["engine"]["id"],
        "chunks": manifest["input"]["chunks"],
        "flags": manifest["flags"],
    }
    if adopted is not None:
        measured["adopted"] = adopted
    return {
        "synthetic": True,
        "measurements": measured,
        "volatile_outputs": [f"{RUN}/manifest.json"],
        "labels": {
            "synthetic": True,
            "consent_ids": consent_ids,
            "voice_ids": voice_ids,
            "persona": None,
        },
        "timeline": {
            "mapping": manifest["timeline"]["mapping"],
            "no_time_stretch": False,
            "stretch_applied": manifest["timeline"]["stretch_applied"],
            "sample_rate": rate,
            "total_samples": manifest["timeline"]["total_samples"],
            "narration": {"dir": RUN, "content_sha256": manifest["content_sha256"]},
            "output_axis": manifest["timeline"]["output_axis"],
            "source_axis": manifest["timeline"]["source_axis"],
        },
        "states": states,
    }


# voice --from-run -----------------------------------------------------------------------------------------------
# The narrate job fields a run's manifest copies (render.py, manifest["job"]) that the voice key holds. gates is not
# one: the voice key leaves it to voice_qa, which scores the adopted run against the job's own gates.
JOB_FIELDS = (
    "id",
    "scope",
    "confidential",
    "allowHosted",
    "chunkMaxCodepoints",
    "post",
    "audio",
    "captions",
    "narrationEdl",
    "seed",
)
LEXICAL_FIELDS = {
    "release": "release",
    "commit": "commit",
    "register": "valeRegister",
    "lexicon_sha256": "lexiconSha256",
    "prompt_digest_sha256": "promptDigestSha256",
    "vale_register_sha256": "valeRegisterSha256",
    "rewrite_check": "rewriteCheck",
}
CHUNK_STATUSES = ("passed", "failed", "not_measured")


def adopt_refused(code, detail):
    """An adoption refusal says nothing about the voice key (another run may adopt), so it is never recorded."""
    return StageRefused(code, detail, verdict=False)


def adopted_copy(source, target):
    """Copy a narrate run directory into target. Refuses a missing run, a run without a manifest, a run under
    artifacts/runs/ and a symlink anywhere in the run, before a byte is copied."""
    source = Path(source)
    if source.is_symlink() or not source.is_dir():
        raise adopt_refused("voice_run_missing", "--from-run is not a narrate run directory")
    manifest = source / "manifest.json"
    if manifest.is_symlink() or not manifest.is_file():
        raise adopt_refused("voice_run_manifest_missing", "the run has no manifest.json")
    if in_guitar_runs(source):
        raise adopt_refused("voice_run_in_guitar_runs", "a narration run never lives under artifacts/runs/")
    try:
        files_under(source)
    except StoreError as exc:
        raise adopt_refused("voice_run_invalid", exc.detail) from None
    shutil.copytree(source, target, symlinks=True)
    return target


def chunk_gate_problem(manifest):
    """Why the run's chunk gates do not hold, or None: every chunk has its file and a known QA status, the counts
    agree with the chunks, and no chunk failed its measured gate (qa_failed)."""
    chunks = manifest.get("chunks")
    qa_block = manifest.get("qa") if isinstance(manifest.get("qa"), dict) else {}
    counts = qa_block.get("chunks") if isinstance(qa_block.get("chunks"), dict) else None
    digests = manifest.get("output_sha256") or {}
    if not isinstance(chunks, list) or not chunks or counts is None:
        return "the manifest lists no chunks or no chunk QA counts"
    if (manifest.get("input") or {}).get("chunks") != len(chunks):
        return "input.chunks differs from the chunk records"
    statuses = []
    for index, chunk in enumerate(chunks):
        qa_record = chunk.get("qa") if isinstance(chunk, dict) else None
        status = qa_record.get("status") if isinstance(qa_record, dict) else None
        if status not in CHUNK_STATUSES or chunk.get("file") not in digests:
            return f"chunk {index} has no listed take or QA status"
        statuses.append(status)
    if {s: statuses.count(s) for s in CHUNK_STATUSES} != {s: counts.get(s) for s in CHUNK_STATUSES}:
        return "qa.chunks differs from the chunk records"
    failed = [c.get("id", index) for index, c in enumerate(chunks) if c["qa"]["status"] == "failed"]
    if failed:
        return f"chunks {failed[:3]} failed their measured gate"
    return None


def binding_problem(rc, segment, manifest):
    """The first field where the run differs from what the voice key holds, or None: the narrate job, the script,
    the voices and their consents, the engine, the lexical release and the pronunciation table."""
    records, narrate_job = rc.records, rc.records["jobs"][segment["narrateJob"]]
    job = manifest.get("job") if isinstance(manifest.get("job"), dict) else {}
    if job.get("overrides"):
        return "job.overrides: an adopted run renders the job record as it is"
    for field in JOB_FIELDS:
        if normalise(job.get(field)) != normalise(narrate_job.get(field)):
            return f"job.{field}"
    run_input = manifest.get("input") if isinstance(manifest.get("input"), dict) else {}
    if run_input.get("sha256") != segment["scriptSha256"]:
        return "input.sha256: the run voiced another script"
    if run_input.get("kind") != narrate_job["input"]:
        return "input.kind"
    rewrite = run_input.get("rewrite")
    if not isinstance(rewrite, dict) or rewrite.get("status") != "none":
        return "input.rewrite: an adopted run voices the script itself"
    engine = manifest.get("engine") if isinstance(manifest.get("engine"), dict) else {}
    want_engine = graph.engine_identity(records, narrate_job)
    if want_engine is None or engine.get("id") != narrate_job["engine"]:
        return "engine.id"
    files = engine.get("files") if isinstance(engine.get("files"), list) else []
    if sorted(str(f.get("sha256")) for f in files if isinstance(f, dict)) != want_engine["files"]:
        return "engine.files"
    wanted = {v: records["voices"][v] for v in {narrate_job["voice"]} | {s["voice"] for s in narrate_job["speakers"]}}
    voices = manifest.get("voices") if isinstance(manifest.get("voices"), list) else []
    if not all(isinstance(v, dict) for v in voices) or sorted({v.get("voice") for v in voices}) != sorted(wanted):
        return "voices"
    for v in voices:
        record = wanted[v["voice"]]
        if (v.get("ref_clip_sha256"), v.get("consent_id"), v.get("scope")) != (
            record["refClipSha256"],
            record["consentId"],
            record["scope"],
        ):
            return f"voices.{v['voice']}"
    run_lexical = manifest.get("lexical") if isinstance(manifest.get("lexical"), dict) else {}
    for got, want in LEXICAL_FIELDS.items():
        if normalise(run_lexical.get(got)) != normalise(narrate_job["lexical"].get(want)):
            return f"lexical.{got}"
    table = (records.get("pronunciation") or {}).get(narrate_job.get("pronunciation"))
    pron = manifest.get("pronunciation") if isinstance(manifest.get("pronunciation"), dict) else {}
    if table is None or pron.get("table") != table["id"] or pron.get("sha256") != sha256_text(canonical(table)):
        return "pronunciation"
    return None


def adopt_voice(rc, row, partial):
    """voice --from-run: copy an already rendered narrate run into the stage directory, re-verify the copy (never
    the source, which could change after the check) and bind it to this node's key. Refusals: voice_run_missing,
    voice_run_manifest_missing, voice_run_in_guitar_runs, voice_run_invalid, voice_run_unverified (narrate verify:
    digests, synthetic, narration_v1, no_time_stretch false, content_sha256), voice_run_test_mode,
    voice_chunk_gate_failed and voice_run_mismatch."""
    segment = segment_of(rc, row)
    copied = adopted_copy(rc.from_run, partial / RUN)
    receipt = verify.verify(copied)
    if not receipt["ok"]:
        raise adopt_refused("voice_run_unverified", f"the narrate run does not verify: {receipt['reason']}")
    manifest = json.loads((copied / "manifest.json").read_text(encoding="utf-8"))
    synthesis = (manifest.get("engine") or {}).get("synthesis") or {}
    if "prerendered_test_mode" in manifest.get("flags", []) or synthesis.get("test_mode"):
        raise adopt_refused("voice_run_test_mode", "the batch ran in test mode (prerendered_test_mode)")
    problem = chunk_gate_problem(manifest)
    if problem:
        raise adopt_refused("voice_chunk_gate_failed", problem)
    problem = binding_problem(rc, segment, manifest)
    if problem:
        raise adopt_refused("voice_run_mismatch", f"the run differs from voice/{segment['id']}'s key at {problem}")
    adopted = {"run_id": manifest.get("run_id"), "content_sha256": manifest["content_sha256"]}
    states = {"source_checks": "passed", "render": "adopted", "listening": "pending_operator"}
    try:
        return voice_fields(manifest, states, adopted)
    except (KeyError, TypeError, ZeroDivisionError, AttributeError) as exc:
        raise adopt_refused("voice_run_invalid", f"the manifest lacks a field the voice stage records: {exc}") from None


# voice_qa -------------------------------------------------------------------------------------------------------
def measured_failures(metrics):
    """The metrics a gate measured and failed. not_measured never fails a gate; it stays a recorded state."""
    return sorted(name for name, value in metrics.items() if isinstance(value, dict) and value.get("passed") is False)


def run_voice_qa(rc, row, partial):
    segment = segment_of(rc, row)
    voice_manifest, voice_dir = upstream(rc.store, f"voice/{segment['id']}")
    run_dir = voice_dir / RUN
    receipt = verify.verify(run_dir)
    if not receipt["ok"]:
        raise StageRefused("voice_unverified", f"the narrate run does not verify: {receipt['reason']}")
    narrate_job = rc.records["jobs"][segment["narrateJob"]]
    with work_dir(rc.store) as work:
        script = script_copy(rc, segment, narrate_job["input"], work)
        cfg = narrate_config(rc, segment["narrateJob"], script, work / "unused", work)
        result = evaluate.evaluate(run_dir, evaluate.METRICS, cfg)
    if not result.get("ok"):
        raise StageRefused("voice_unverified", str(result.get("reason"))[:200])
    metrics = result["metrics"]
    failed = measured_failures(metrics)
    write_json(
        partial / "qa.json",
        {
            "verify": {k: receipt[k] for k in ("ok", "checks", "reason", "flags")},
            "metrics": metrics,
            "gates": narrate_job["gates"],
            "failed": failed,
        },
    )
    if failed:
        raise StageRefused("voice_qa_failed", f"measured gates failed: {', '.join(failed)}")
    status = {
        name: ("passed" if value.get("passed") else value.get("status", "measured"))
        for name, value in metrics.items()
        if isinstance(value, dict)
    }
    loud = metrics["loudness"]
    measured = {
        "verified": True,
        "integrated_lufs": loud["integrated_lufs"],
        "true_peak_dbtp": loud["true_peak_dbtp"],
        "overruns": len(metrics["overruns"]),
        "metrics": status,
        "narrate_flags": receipt["flags"],
    }
    return {
        "synthetic": True,
        "measurements": measured,
        "labels": labels.grow([voice_manifest], None),
        "states": {"source_checks": "passed", "listening": "pending_operator"},
    }


def narration_wav(voice_dir):
    return Path(voice_dir) / RUN / "narration.wav"
