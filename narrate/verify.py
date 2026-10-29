"""Re-hash and re-check a narration run (`python -m narrate verify RUN_DIR`).

The receipt is JSON: ok, the run id, each check and the first failure as `reason`. Checks:
  manifest     kind narration_render, schema_version 1, synthetic true
  timeline     mapping narration_v1 and no_time_stretch false (TIMELINE_CONTRACT.md, narration amendment), and
               timeline.edl.sha256 equal to its output_sha256 entry
  outputs      every listed file exists inside the run and has its sha256; no file in the run is unlisted
  ir           ir.json's canonical digest equals input.ir_sha256
  edl          segments in order, never overlapping, inside the track; total samples equal narration.wav's
  content      content_sha256 equals the digest of the manifest without its volatile fields
  location     the run directory is not under artifacts/runs/ (the guitar runs)
The receipt also carries the manifest's content_sha256 when the content check holds (null otherwise).
`--result-line` prints one compact line {ok, run_id, content_sha256} instead (and reason when a check fails), for a
caller such as a workflow task that adopts the run with `narrate video stage JOB voice --from-run RUN_DIR`.
Exit 0 when every check holds, 1 when one fails, 2 when the run cannot be read.
"""

import json
import wave
from pathlib import Path

from .config import in_guitar_runs
from .ir import canonical, sha256_file, sha256_text

VOLATILE = ("run_id", "run_dir", "created_utc", "content_sha256")


def verify(run_dir):
    run_dir = Path(run_dir)
    checks, reason = {}, None

    def check(name, ok, why):
        nonlocal reason
        checks[name] = bool(ok)
        if not ok and reason is None:
            reason = f"{name}: {why}"

    try:
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return {"ok": False, "run_dir": str(run_dir), "checks": {}, "reason": f"manifest unreadable: {error}"}
    if not isinstance(manifest, dict):
        return {"ok": False, "run_dir": str(run_dir), "checks": {}, "reason": "manifest is not an object"}
    check(
        "manifest",
        manifest.get("kind") == "narration_render"
        and manifest.get("schema_version") == 1
        and manifest.get("synthetic") is True,
        "not a synthetic narration_render manifest of schema 1",
    )
    timeline = manifest.get("timeline") if isinstance(manifest.get("timeline"), dict) else {}
    digests = manifest.get("output_sha256") if isinstance(manifest.get("output_sha256"), dict) else {}
    edl_ref = timeline.get("edl") if isinstance(timeline.get("edl"), dict) else {}
    check(
        "timeline",
        timeline.get("mapping") == "narration_v1"
        and timeline.get("no_time_stretch") is False
        and edl_ref.get("file") in digests
        and edl_ref.get("sha256") == digests.get(edl_ref.get("file")),
        "mapping must be narration_v1 with no_time_stretch false and a listed EDL",
    )
    bad = []
    root = run_dir.resolve()
    for name, digest in sorted(digests.items()):
        path = (run_dir / name).resolve()
        if root not in path.parents or not path.is_file() or sha256_file(path) != digest:
            bad.append(name)
    present = {str(p.relative_to(run_dir)) for p in run_dir.rglob("*") if p.is_file()} - {"manifest.json"}
    unlisted = sorted(present - set(digests))
    check(
        "outputs",
        digests and not bad and not unlisted,
        f"changed or missing {bad[:3]}" if bad else f"unlisted files {unlisted[:3]}",
    )
    try:
        ir = json.loads((run_dir / "ir.json").read_text(encoding="utf-8"))
        ir_ok = sha256_text(canonical(ir)) == (manifest.get("input") or {}).get("ir_sha256")
    except (OSError, ValueError):
        ir_ok = False
    check("ir", ir_ok, "ir.json does not match input.ir_sha256")
    check("edl", *edl_ok(run_dir, edl_ref.get("file") or "narration.edl.json", timeline))
    expected = sha256_text(canonical({k: v for k, v in manifest.items() if k not in VOLATILE}))
    check("content", manifest.get("content_sha256") == expected, "content_sha256 differs from the manifest")
    check("location", not in_guitar_runs(run_dir), "a narration run under artifacts/runs/")
    return {
        "ok": reason is None,
        "run_id": manifest.get("run_id"),
        "run_dir": str(run_dir),
        "checks": checks,
        "reason": reason,
        "flags": manifest.get("flags", []),
        "content_sha256": manifest.get("content_sha256") if checks["content"] else None,
    }


def result_line(ok, run_id, content_sha256, reason=None):
    """One compact JSON line: what `render --result-line` and `verify --result-line` print on stdout."""
    value = {"ok": bool(ok), "run_id": run_id, "content_sha256": content_sha256 if ok else None}
    if not ok:
        value["reason"] = reason
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def edl_ok(run_dir, name, timeline):
    try:
        edl = json.loads((run_dir / name).read_text(encoding="utf-8"))
        with wave.open(str(run_dir / "narration.wav")) as w:
            samples, rate = w.getnframes(), w.getframerate()
    except (OSError, ValueError, wave.Error, EOFError) as error:
        return False, f"unreadable: {error}"
    if not isinstance(edl, dict):
        return False, "the EDL is not an object"
    if edl.get("kind") != "narration_edl" or edl.get("mapping") != "narration_v1":
        return False, "not a narration_v1 EDL"
    if (edl.get("total_samples"), edl.get("sample_rate")) != (samples, rate):
        return False, f"EDL says {edl.get('total_samples')} samples at {edl.get('sample_rate')} Hz, WAV has {samples}"
    if (timeline.get("total_samples"), timeline.get("sample_rate")) != (samples, rate):
        return False, "manifest timeline totals differ from narration.wav"
    end = 0.0
    segments = edl.get("segments", [])
    if not isinstance(segments, list):
        return False, "segments is not a list"
    for index, segment in enumerate(segments):
        try:
            a, b = float(segment["out_start_s"]), float(segment["out_end_s"])
            name = segment["id"]
        except (KeyError, TypeError, ValueError):
            return False, f"malformed segment {index}"
        if a < end - 1e-3 or b < a or b > samples / rate + 1e-3:
            return False, f"segment {name} [{a}, {b}] overlaps, reverses or overruns the track"
        end = b
    return True, ""


def main(run_dir, line=False):
    receipt = verify(run_dir)
    if line:
        print(result_line(receipt["ok"], receipt["run_id"], receipt["content_sha256"], receipt["reason"]))
    else:
        print(json.dumps(receipt, indent=1, sort_keys=True))
    return 0 if receipt["ok"] else 1
