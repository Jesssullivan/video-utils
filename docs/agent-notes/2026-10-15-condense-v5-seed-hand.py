"""Seed a condense work dir with the hand-run pipeline's analysis, then build the EDL without whisper.

usage: seed_hand.py <archive video-edit dir> <run dir with talk.toml and media/> <worktree>
Whisper is never called: a pause span missing from the archived pause_asr cache counts as unheard ("").
"""

import json
import os
import shutil
import sys
from pathlib import Path

arch, run, tree = map(Path, sys.argv[1:4])
sys.path.insert(0, str(tree))
from condense import edl, transcribe  # noqa: E402
from condense.config import Config  # noqa: E402

work = run / "work"
work.mkdir(parents=True, exist_ok=True)
for clip in ("intro", "iphone"):
    ev = json.loads((arch / f"{clip}.events.json").read_text())

    def pair(x):
        return (x["start"], x["end"]) if isinstance(x, dict) else (x[0], x[1])

    fillers = [[*pair(x), x.get("kind", "filler") if isinstance(x, dict) else "filler"] for x in ev["fillers"]]
    pauses = [list(pair(x)) for x in ev["pauses"]]
    (work / f"{clip}.events.json").write_text(json.dumps(dict(fillers=fillers, pauses=pauses)))
    w = json.loads((arch / f"{clip}.words.json").read_text())
    w = w.get("words", w) if isinstance(w, dict) else w
    words = [dict(start=x["start"], end=x["end"], word=(x.get("word") or x.get("w") or "").strip()) for x in w]
    (work / f"{clip}.words.json").write_text(json.dumps(words))
    shutil.copyfile(arch / f"{clip}.rms.txt", work / f"{clip}.rms.txt")
    if (arch / f"{clip}.pause_asr.json").exists():
        shutil.copyfile(arch / f"{clip}.pause_asr.json", work / f"{clip}.pause_asr.json")
    wav = work / f"{clip}.16k.wav"
    if not wav.exists():
        os.link(run.parent / "v5" / "work" / f"{clip}.16k.wav", wav)

missed = []


def no_whisper(cfg, wav, a, b):
    missed.append((a, b))
    return ""


transcribe.read = no_whisper
edl.transcribe.read = no_whisper
cfg = Config(run / "talk.toml")
if os.environ.get("FIXED_WELCOME"):  # the hand-run welcome window was fixed, not snapped to pause edges
    edl.snap_welcome = lambda welcome, pauses: list(welcome) if welcome else None
edl.build(cfg)
print(json.dumps(dict(pause_spans_not_in_archived_cache=len(missed))))
