"""Compare condense captions with the v5 SRT, cue for cue and word for word.

usage: compare_srt.py <v5.srt> <run dir with talk.toml> <worktree>
Cue for cue: same index, same text (whitespace folded), start and end within 1 frame.
Word level: the v5 text and the run's caption words aligned by difflib; for aligned words, the v5 cue start
against the run's output time of that word (only cue-initial words carry a v5 time).
"""

import difflib
import json
import re
import sys
from pathlib import Path

FRAME = 1 / 30
v5_path, run, tree = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
sys.path.insert(0, str(tree))
from condense import captions  # noqa: E402
from condense.config import Config  # noqa: E402
from condense.edl import Timeline  # noqa: E402


def parse(text):
    out = []
    for block in text.strip().split("\n\n"):
        lines = block.strip().split("\n")
        a, b = (
            sum(float(x) * m for x, m in zip(re.split("[:]", t.replace(",", ".")), (3600, 60, 1), strict=True))
            for t in lines[1].split(" --> ")
        )
        out.append((a, b, " ".join(" ".join(lines[2:]).split())))
    return out


v5 = parse(v5_path.read_text())
new = parse((run / "out/talk.srt").read_text())
same = sum(
    1
    for x, y in zip(v5, new, strict=False)
    if x[2] == y[2] and abs(x[0] - y[0]) <= FRAME + 1e-3 and abs(x[1] - y[1]) <= FRAME + 1e-3
)
same_text = sum(1 for x, y in zip(v5, new, strict=False) if x[2] == y[2])
v5_text = {x[2] for x in v5}
text_anywhere = sum(1 for y in new if y[2] in v5_text)


def norm(w):
    return re.sub(r"[^a-z0-9']", "", w.lower())


vw = [(norm(w), a if k == 0 else None) for a, _, t in v5 if not t.startswith("[") for k, w in enumerate(t.split())]
vw = [x for x in vw if x[0]]
cfg = Config(run / "talk.toml")
nw = [(norm(w), a) for a, _, w in captions.output_words(cfg, Timeline.load(cfg))]
nw = [x for x in nw if x[0]]
sm = difflib.SequenceMatcher(a=[w for w, _ in vw], b=[w for w, _ in nw], autojunk=False)
aligned, timed, within = 0, 0, 0
worst = 0.0
for blk in sm.get_matching_blocks():
    for k in range(blk.size):
        aligned += 1
        t5, tn = vw[blk.a + k][1], nw[blk.b + k][1]
        if t5 is not None:
            timed += 1
            d = abs(t5 - tn)
            within += d <= FRAME + 1e-3
            worst = max(worst, d)
print(
    json.dumps(
        dict(
            v5_cues=len(v5),
            new_cues=len(new),
            cue_for_cue_within_1_frame=same,
            same_text_same_index=same_text,
            new_cues_whose_text_is_a_v5_cue=text_anywhere,
            v5_words=len(vw),
            new_words=len(nw),
            aligned_words=aligned,
            word_ratio=round(sm.ratio(), 4),
            v5_cue_starts_aligned=timed,
            cue_starts_within_1_frame=within,
            worst_cue_start_s=round(worst, 3),
        ),
        indent=1,
    )
)
