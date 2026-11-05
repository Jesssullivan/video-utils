#!/bin/sh
# TIN-6575: publish the v5 rebuild again with the upload copy carried, then verify-run it. Reflink copies of the
# TIN-6545 rebase run's inputs, outputs and work (its check.json included: it binds the same edit); nothing is
# rendered or checked again. Usage, from the repository root inside `nix develop .#condense`:
#   sh docs/agent-notes/2026-10-16-condense-upload-carry.sh SRC_RUN_DIR RUN_DIR
# SRC_RUN_DIR is the one 2026-10-16-condense-check-rebase.sh wrote; it is only read. RUN_DIR must not exist.
# VIDEO_UTILS_BIN must be this checkout's build. Logs and the numbers the receipt quotes stay in RUN_DIR.
set -e
S=$1
R=$2
[ ! -e "$R" ] || { echo "$R exists" >&2; exit 2; }
[ -x "$VIDEO_UTILS_BIN" ] || { echo "VIDEO_UTILS_BIN is not set" >&2; exit 2; }
mkdir -p "$R/logs" "$R/published"
cp --reflink=auto -a "$S/talk.toml" "$S/media" "$S/out" "$S/work" "$R/"
start=$(date +%s)
python3 -c "import sys; from condense import publish; from condense.config import Config; publish.publish(Config(sys.argv[1] + '/talk.toml'), sys.argv[1] + '/published')" "$R" > "$R/logs/publish.log" 2>&1 || echo "publish exit $?" >> "$R/logs/publish.log"
echo "publish wall $(( $(date +%s) - start )) s" >> "$R/logs/publish.log"
for run in "$R"/published/*; do
  "$VIDEO_UTILS_BIN" verify-run --require-source --timeline edl_v1 "$run" > "$R/logs/verify-run.json" 2> "$R/logs/verify-run.err" || echo "verify-run exit $?" >> "$R/logs/verify-run.err"
done
python3 - "$R" > "$R/logs/numbers.json" <<'PY'
import json, sys
from pathlib import Path
r = Path(sys.argv[1])
(run,) = [p for p in (r / "published").iterdir() if not p.name.startswith(".")]
m = json.loads((run / "manifest.json").read_text())
v = json.loads((r / "logs" / "verify-run.json").read_text())
keep = ("file", "of", "video_frames", "faststart", "moov_offset", "mdat_offset", "video_first_pts",
        "video_first_dts", "video_b_frames", "audio_packets_sha256", "audio_first_pts", "audio_start_pts",
        "audio_time_base")
print(json.dumps({
    "files": sorted(m["output_sha256"]),
    "output_sha256": m["output_sha256"],
    "total_frames": m["timeline"]["total_frames"],
    "check_status": m["check"]["status"],
    "uploads": [{k: u[k] for k in keep} for u in m["uploads"]],
    "verify": {k: v[k] for k in ("status", "reason", "manifest_sha256", "bytes_hashed")}
    | {"outputs_verified": v["outputs"]["verified"], "sources": v["sources"]["status"],
       "uploads": [(u["file"], u["status"], u["moov_offset"], u["mdat_offset"]) for u in v["uploads"]]},
}, indent=2))
PY
echo "done $(( $(date +%s) - start )) s" >> "$R/logs/publish.log"
