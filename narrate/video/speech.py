"""The speech stages of lane L4: script, voice and voice_qa (docs/spec/NARRATED_VIDEO.md, "Stages").

- script reads one segment's script from the private store through its narrate job's input adapter, records the
  spoken-text digest and the pinned xoxd-lexical release's findings. Findings are advisory (R-N12): they never refuse.
- voice renders the segment with narrate (`narrate.render`, tool 58) into its stage directory. The narrate run keeps
  its own manifest, mapping narration_v1 and verification; the stage manifest adds the labels.
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
from ..config import Config, ConfigError
from ..engine import EngineError
from ..ir import sha256_text
from ..lexical import LexicalError
from ..normalise import NormaliseError
from ..policy import Refused
from ..registry import RegistryError
from . import labels
from .common import StageRefused, upstream, work_dir, write_json

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
        "states": {"source_checks": "passed", "render": "local", "listening": "pending_operator"},
    }


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
