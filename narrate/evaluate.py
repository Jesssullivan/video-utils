"""Score a rendered narration run without changing it (`python -m narrate evaluate RUN_DIR`).

Metrics: loudness (EBU R128 of narration.wav against the job's target, with render's own pass rule), overruns
(from the EDL), wer and sim. WER scores the delivered audio: each chunk's out_start_s..out_end_s span is cut from
narration.wav (after timing fit and loudnorm, as consumers hear it) and read back through condense's whisper path
when it is available, else not_measured. SIM is not_measured until a speaker-verification model is registered.
Prints JSON; writes nothing.
"""

import json
from pathlib import Path

from . import audio, qa, verify

METRICS = ("loudness", "overruns", "wer", "sim")


def evaluate(run_dir, metrics=METRICS, cfg=None):
    run_dir = Path(run_dir)
    receipt = verify.verify(run_dir)
    if not receipt["ok"]:
        return {"ok": False, "reason": f"the run does not verify: {receipt['reason']}"}
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    post = manifest["job"]["post"]
    out = {"ok": True, "run_id": manifest["run_id"], "metrics": {}}
    if "loudness" in metrics:
        integrated, lra, peak = audio.ebur128(run_dir / "narration.wav")
        loudnorm_type = (manifest.get("loudness", {}).get("loudnorm") or {}).get("normalization_type")
        passed, flags = audio.loudness_verdict(integrated, peak, post, loudnorm_type)
        out["metrics"]["loudness"] = {
            "integrated_lufs": integrated,
            "true_peak_dbtp": peak,
            "loudness_range_lu": lra,
            "target_lufs": post["loudnessLufs"],
            "deviation_lu": round(integrated - post["loudnessLufs"], 2),
            "true_peak_target_dbtp": post["truePeakDbtp"],
            "peak_tolerance_db": audio.PEAK_TOLERANCE_DB,
            "passed": passed,
            "flags": flags,
        }
    if "overruns" in metrics:
        edl = json.loads((run_dir / manifest["timeline"]["edl"]["file"]).read_text(encoding="utf-8"))
        out["metrics"]["overruns"] = [
            {"segment": s["id"], "overrun_s": s["overrun_s"]} for s in edl["segments"] if "overrun" in s["flags"]
        ]
    if "wer" in metrics:
        whisper = qa.Whisper(cfg) if cfg is not None else None
        ready = whisper.available() if whisper else (False, "no narrate.toml given (--config)")
        if not ready[0]:
            out["metrics"]["wer"] = qa.not_measured(ready[1])
        else:
            rows = []
            delivered = audio.read(run_dir / "narration.wav")
            for chunk in manifest["chunks"]:
                a = round(chunk["out_start_s"] * delivered.rate)
                b = round(chunk["out_end_s"] * delivered.rate)
                heard = whisper.read(audio.Pcm(delivered.rate, delivered.samples[a:b]))
                rows.append({"chunk": chunk["id"], "wer": qa.wer(chunk["spoken"], heard)})
            gate = manifest["job"]["gates"]["maxChunkWer"]
            out["metrics"]["wer"] = {
                "status": "measured",
                "scored": "narration.wav, cut per chunk at out_start_s..out_end_s",
                **whisper.identity(),
                "chunks": rows,
                "max_chunk_wer": gate,
                "passed": all(r["wer"] <= gate for r in rows),
            }
    if "sim" in metrics:
        out["metrics"]["sim"] = qa.sim(cfg) if cfg is not None else qa.not_measured("no narrate.toml given")
    return out
