#!/bin/sh
# TIN-6545 receipt script: the check stage on a private v5 rebuild, then the upload copy (loudness, real and
# joined sync, captions), then publish into the run dir's published/. Usage, from the repository root inside
# `nix develop .#condense`: sh docs/agent-notes/2026-10-16-condense-check-real.sh RUN_DIR
# RUN_DIR holds talk.toml, media/, work/ (edl.json, words, mezzanines, lossless parts) and out/ (talk.mp4,
# talk.upload.mp4). WHISPER_MODEL (the registered model) and VIDEO_UTILS_BIN must be set. Logs stay in RUN_DIR.
set -e
R=$1
mkdir -p "$R/logs" "$R/published"
start=$(date +%s)
python3 -m condense check "$R/talk.toml" > "$R/logs/check.log" 2>&1 || echo "check exit $?" >> "$R/logs/check.log"
echo "check wall $(( $(date +%s) - start )) s" >> "$R/logs/check.log"
python3 - "$R" > "$R/logs/check-upload.log" 2>&1 <<'PY'
import copy, json, sys
from pathlib import Path
from condense import avsync, check
from condense.config import Config
from condense.edl import Timeline
r = Path(sys.argv[1])
cfg = Config(r / "talk.toml")
up = copy.copy(cfg)
up.out = r / "out" / "talk.upload.mp4"
tl = Timeline.load(cfg)
edl = json.loads(cfg.f("edl", "json").read_text())
limit = cfg.check["sync_ms"]
out = {"delivery_sha256": check.sha256(up.out), "loud": check.measure_loud(up, tl),
       "sync_real": avsync.measure_real(up, tl, edl, limit), "sync_joined": avsync.measure_joined(up, edl, limit),
       "captions": check.measure_captions(up, tl)}
(r / "work" / "check.upload.json").write_text(json.dumps(out, indent=2) + "\n")
PY
python3 -c "import sys; from condense import publish; from condense.config import Config; publish.publish(Config(sys.argv[1] + '/talk.toml'), sys.argv[1] + '/published')" "$R" > "$R/logs/publish.log" 2>&1 || echo "publish exit $?" >> "$R/logs/publish.log"
echo "done $(( $(date +%s) - start )) s" >> "$R/logs/check.log"
