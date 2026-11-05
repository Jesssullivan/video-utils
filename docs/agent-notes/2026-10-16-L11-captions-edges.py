"""Unrounded cue edges of a run's captions on its own edl.json against the same style on the hand-run edit list.

usage: L11-captions-edges.py <run dir with talk.toml> <worktree> <edl.v5.json> <published v5.srt>
The SRT's millisecond stamps round both sides, so a difference of exactly 1 frame can print as 34 ms.
Here both cue lists come from condense's build() before rounding; only the Timeline differs.
"""

import collections
import json
import sys
from pathlib import Path

run, tree, v5edl, v5srt = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])
sys.path.insert(0, str(tree))
from condense import captions  # noqa: E402
from condense.config import Config  # noqa: E402
from condense.edl import Timeline  # noqa: E402

cfg = Config(run / "talk.toml")
mine = captions.build(cfg)
segs = {}
for part in json.loads(v5edl.read_text())["parts"]:  # the card row carries out_dur only
    segs.setdefault(part["edl"][0]["src"], []).extend(
        {"frames": round(g.get("out_dur", 0) * 30), **g} for g in part["edl"]
    )
hand = dict(fps=30, clips=[dict(name=c["name"], shift=0.0, segments=segs[c["name"]]) for c in cfg.clips])
Timeline.load = classmethod(lambda cls, cfg: cls(hand))
ref = captions.build(cfg)
ds = [max(abs(x[0] - y[0]), abs(x[1] - y[1])) * 30 for x, y in zip(mine, ref, strict=True)]
print(
    json.dumps(
        dict(
            cues=len(mine),
            same_lines=sum(x[2] == y[2] for x, y in zip(mine, ref, strict=True)),
            worst_edge_frames=round(max(ds), 4),
            over_1_frame=sum(d > 1 + 1e-6 for d in ds),
            edge_frames_histogram=sorted(collections.Counter(round(d, 2) for d in ds).items()),
            hand_edit_list_srt_bytes_equal_published=captions.srt(ref) == v5srt.read_text(),
        )
    )
)
