"""Line breaks and printed millisecond edges of two SRT files, cue for cue, and the shape of each file's cues.

usage: L11-captions-lines.py <v5.srt> <new.srt>
"""

import collections
import json
import re
import statistics
import sys

FILLER = re.compile(r"^(um+|uh+|er+|hmm+|mm+)[,.?!]*$", re.I)


def parse(path):
    out = []
    for block in open(path).read().strip().split("\n\n"):
        lines = block.strip().split("\n")
        a, b = (
            sum(float(x) * m for x, m in zip(t.replace(",", ".").split(":"), (3600, 60, 1), strict=True))
            for t in lines[1].split(" --> ")
        )
        out.append((a, b, lines[2:]))
    return out


def shape(cues):
    words = [len(" ".join(t).split()) for _, _, t in cues]
    secs = [b - a for a, b, _ in cues]
    chars = [len(" ".join(t)) for _, _, t in cues]
    return dict(
        cues=len(cues),
        words_per_cue_median_max=[statistics.median(words), max(words)],
        chars_per_cue_median_max=[statistics.median(chars), max(chars)],
        seconds_median_max=[round(statistics.median(secs), 3), round(max(secs), 3)],
        seconds_min=round(min(secs), 3),
        one_two_more_lines=[sum(len(t) == n for _, _, t in cues) for n in (1, 2)]
        + [sum(len(t) > 2 for _, _, t in cues)],
        end_at_sentence=sum(" ".join(t)[-1:] in ".?!" for _, _, t in cues),
        bracketed=sum(" ".join(t).startswith("[") for _, _, t in cues),
        star_words=sum(w.startswith("*") for _, _, t in cues for w in " ".join(t).split()),
        filler_words=sum(bool(FILLER.match(w)) for _, _, t in cues for w in " ".join(t).split()),
        gaps_between_cues_over_1s=sum(y[0] - x[1] > 1.0 for x, y in zip(cues, cues[1:], strict=False)),
    )


v5, new = parse(sys.argv[1]), parse(sys.argv[2])
ds = [max(abs(x[0] - y[0]), abs(x[1] - y[1])) for x, y in zip(v5, new, strict=False)]
print(
    json.dumps(
        dict(
            cues=[len(v5), len(new)],
            same_line_breaks=sum(x[2] == y[2] for x, y in zip(v5, new, strict=False)),
            edges_equal_to_the_ms=sum(d < 5e-4 for d in ds),
            printed_edge_ms_histogram=sorted(collections.Counter(round(d * 1000) for d in ds).items()),
            longest_line=max(len(line) for c in new for line in c[2]),
            two_line_cues=sum(len(c[2]) == 2 for c in new),
            shape_first=shape(v5),
            shape_second=shape(new),
        ),
        indent=1,
    )
)
