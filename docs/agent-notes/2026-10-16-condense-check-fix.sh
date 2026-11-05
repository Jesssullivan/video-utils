#!/bin/sh
# TIN-6545 review fixes: the check stage again on the same private v5 rebuild, then the sync measures on the
# upload copy and on two copies of the edit with the sound moved early (87 ms, the v2 bug, and 1 s, beyond the
# search window), then publish into the run dir's published/. Usage, from the repository root inside
# `nix develop .#condense`: sh docs/agent-notes/2026-10-16-condense-check-fix.sh RUN_DIR
# RUN_DIR is the one 2026-10-16-condense-check-real.sh used. Its first check.json is kept as work/check-v1.json.
# WHISPER_MODEL (the registered model) and VIDEO_UTILS_BIN must be set. Logs stay in RUN_DIR; the moved copies
# are deleted after they are measured.
set -e
R=$1
mkdir -p "$R/logs" "$R/published"
[ -e "$R/work/check-v1.json" ] || cp -p "$R/work/check.json" "$R/work/check-v1.json"
start=$(date +%s)
python3 -m condense check "$R/talk.toml" > "$R/logs/check-fix.log" 2>&1 || echo "check exit $?" >> "$R/logs/check-fix.log"
echo "check wall $(( $(date +%s) - start )) s" >> "$R/logs/check-fix.log"
python3 - "$R" > "$R/logs/check-fix-copies.log" 2>&1 <<'PY'
import copy, json, subprocess, sys
from pathlib import Path
from condense import avsync, check, publish
from condense.config import Config
from condense.edl import Timeline
r = Path(sys.argv[1])
cfg = Config(r / "talk.toml")
tl = Timeline.load(cfg)
edl = json.loads(cfg.f("edl", "json").read_text())
limit = cfg.check["sync_ms"]
for name, lead in (("upload", None), ("lead87", 0.087), ("lead1000", 1.0)):
    moved = copy.copy(cfg)
    if lead is None:
        moved.out = r / "out" / "talk.upload.mp4"
    else:
        moved.out = r / "work" / f"{name}.mp4"
        early = f"atrim=start={lead},asetpts=PTS-STARTPTS,apad"
        remux = ["-i", cfg.out, "-map", "0:v", "-map", "0:a", "-c:v", "copy", "-af", early, "-c:a", "aac"]
        subprocess.run(["ffmpeg", "-v", "error", "-y", *remux, "-shortest", moved.out], check=True)
    print(f"== {name}")
    out = {"delivery_sha256": publish.sha256(moved.out), "lead_s": lead,
           "sync_real": avsync.measure_real(moved, tl, edl, limit),
           "sync_joined": avsync.measure_joined(moved, edl, limit)}
    if lead is None:
        out["loud"] = check.measure_loud(moved, tl)
    else:
        moved.out.unlink()
    (r / "work" / f"check-fix-{name}.json").write_text(json.dumps(out, indent=2) + "\n")
PY
python3 -c "import sys; from condense import publish; from condense.config import Config; publish.publish(Config(sys.argv[1] + '/talk.toml'), sys.argv[1] + '/published')" "$R" > "$R/logs/publish-fix.log" 2>&1 || echo "publish exit $?" >> "$R/logs/publish-fix.log"
echo "done $(( $(date +%s) - start )) s" >> "$R/logs/check-fix.log"
