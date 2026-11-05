#!/bin/sh
# TIN-6545 after the rebase onto the drop/preset/upload change (TIN-6544): the check stage on reflink copies of
# the round-3 inputs, then the sync and loudness measures on the [encode] upload copy, then publish into the
# new run dir's published/. Usage, from the repository root inside `nix develop .#condense`:
#   sh docs/agent-notes/2026-10-16-condense-check-rebase.sh SRC_RUN_DIR RUN_DIR
# SRC_RUN_DIR is the one 2026-10-16-condense-check-round3.sh used; it is only read. RUN_DIR must not exist.
# WHISPER_MODEL (the registered model) and VIDEO_UTILS_BIN must be set. Logs stay in RUN_DIR.
set -e
S=$1
R=$2
[ ! -e "$R" ] || { echo "$R exists" >&2; exit 2; }
mkdir -p "$R/logs" "$R/published" "$R/work"
cp --reflink=auto -a "$S/talk.toml" "$S/media" "$S/out" "$R/"
for f in "$S"/work/*; do
  case $(basename "$f") in check*.json) ;; *) cp --reflink=auto -a "$f" "$R/work/" ;; esac
done
start=$(date +%s)
python3 -m condense check "$R/talk.toml" > "$R/logs/check.log" 2>&1 || echo "check exit $?" >> "$R/logs/check.log"
echo "check wall $(( $(date +%s) - start )) s" >> "$R/logs/check.log"
python3 - "$R" > "$R/logs/check-upload.log" 2>&1 <<'PY'
import copy, json, sys
from pathlib import Path
from condense import avsync, check, publish
from condense.config import Config
from condense.edl import Timeline
r = Path(sys.argv[1])
cfg = Config(r / "talk.toml")
tl = Timeline.load(cfg)
edl = json.loads(cfg.f("edl", "json").read_text())
limit = cfg.check["sync_ms"]
moved = copy.copy(cfg)
moved.out = cfg.out.with_suffix(".upload.mp4")
out = {"delivery_sha256": publish.sha256(moved.out),
       "sync_real": avsync.measure_real(moved, tl, edl, limit),
       "sync_joined": avsync.measure_joined(moved, edl, limit),
       "loud": check.measure_loud(moved, tl)}
(r / "work" / "check-upload.json").write_text(json.dumps(out, indent=2) + "\n")
PY
python3 -c "import sys; from condense import publish; from condense.config import Config; publish.publish(Config(sys.argv[1] + '/talk.toml'), sys.argv[1] + '/published')" "$R" > "$R/logs/publish.log" 2>&1 || echo "publish exit $?" >> "$R/logs/publish.log"
echo "done $(( $(date +%s) - start )) s" >> "$R/logs/check.log"
