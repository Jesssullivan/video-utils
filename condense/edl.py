"""The edit decision list: every span of every clip gets a kind and a speed.

Pacing rules (numbers are the defaults in config.RULES):
  speech       plays at the clip's speed, or a zone's. The welcome window plays at 1x and keeps its fillers.
  pause > 1 s  is cut: 5 frames before it and 4 after stay at 1x (0.3 s), joined by a hard video cut and a
               2-frame audio crossfade.
  pause <= 1 s plays at 4x.
  filler       plays at 8x. Fillers are never cut, so a wrong guess costs a blip and not a word.
Anything at 4x or faster is turned down to 0.4 gain.
A clip with `card` lines is one segment: the whole recording in `card_s` seconds, blurred, under the text.
A clip's `drop` spans of source are cut like long pauses, talk and all, after the pacing rules (drop()).

Events closer than 0.3 s merge into one span. A span is a pause when pauses cover half of it, else a filler.
Each span gives 0.15 s back to speech on both sides, and spans under 0.2 s stay speech.

Pause carving: word-gap pauses come from whisper word times, and whisper misses or mis-times words. So a
pause span is searched for sound: runs of 2+ RMS frames (100 ms each) over the clip's voiced_db. A run with
evidence stays speech, a run without evidence plays as a filler, and only true silence is cut. Evidence:
  energy  any run counts. For gated audio, where silence is digital silence.
  word    a transcribed word overlaps the run. Only the filler lexicon is no proof: a drawn-out "mmm" is a sound.
  asr     that, or whisper re-run on the pause span alone hears a word. For noisy rooms. Cached per clip and
          keyed by the speech-to-text that answered (pause_asr_key()).

Sync: every segment is a whole number of output frames ("frames"). quantise() rounds the running total, so
the rounding error never passes half a frame and never builds up. The render makes each segment's video and
audio exactly that long.

Clocks: EDL times are analysis times, counted from the first audio sample. Each clip carries a `shift`: the
audio stream's start after the video's, rounded up to whole frames. The render reads picture and sound at
analysis time + shift of the source.
"""

import bisect
import hashlib
import json
import re
from pathlib import Path
from types import SimpleNamespace

from . import audio, timeline, transcribe
from .events import FILL, norm


def merge(intervals, gap):
    """Union of (a, b, tag) intervals, joining those closer than gap. Returns [[a, b, members]]."""
    out = []
    for a, b, tag in sorted(intervals):
        if out and a - out[-1][1] < gap:
            out[-1][1] = max(out[-1][1], b)
            out[-1][2].append((a, b, tag))
        else:
            out.append([a, b, [(a, b, tag)]])
    return out


def classify(a, b, members):
    """'pause' if pause intervals cover at least half of [a, b], else 'filler'."""
    covered, cur = 0.0, a
    for x, y, _ in sorted(m for m in members if m[2] == "pause"):
        x, y = max(x, cur), min(y, b)
        if y > x:
            covered += y - x
            cur = y
    return "pause" if covered >= 0.5 * (b - a) else "filler"


def heard(c, a, b):
    """True or False when whisper has read [a, b] alone; None, and a note to read it, when it has not."""
    text = c.asr.get(f"{a:.3f}-{b:.3f}")
    if text is None:
        c.missing.add((a, b))
        return None
    text = re.sub(r"\[[^]]*\]|\([^)]*\)", " ", text.lower())  # [BLANK_AUDIO] and (noise) are not words
    return any(w not in FILL for w in re.findall(r"[a-z']+", text))


def voiced_runs(c, a, b, fillers):
    """Sounding runs in [a, b]: [(x, y, 'voiced' | 'filler')]. One quiet frame inside a run is allowed."""
    runs, cur, dips = [], None, 0
    for f in range(int(a * 10), int(b * 10) + 1):
        if c.rms.get(f, -99.0) > c.voiced_db:
            cur = [f, f] if cur is None else [cur[0], f]
            dips = 0
        elif cur is not None:
            dips += 1
            if dips > 1:
                runs.append(cur)
                cur, dips = None, 0
    if cur is not None:
        runs.append(cur)
    runs = [(f0 / 10, (f1 + 1) / 10) for f0, f1 in runs if f1 - f0 + 1 >= 2]

    def touches(spans, x, y):
        return any(p < y and x < q for p, q in spans)

    filler = [touches(fillers, x, y) for x, y in runs]
    if c.mode == "energy" or (c.mode == "asr" and not all(filler) and runs and heard(c, a, b)):
        proof = [True] * len(runs)
    else:
        proof = [touches(c.lex, x, y) for x, y in runs]
    # a run without evidence, or one that touches a filler, plays at filler speed
    return [(x, y, "voiced" if ok and not f else "filler") for (x, y), ok, f in zip(runs, proof, filler, strict=True)]


def carve(c, a, b, kind, fillers):
    """Split pause span [a, b] around its sounding runs, each widened by the margin, so a cut never drops a sound."""
    if kind != "pause":
        return [(a, b, kind)]
    pieces, t = [], a
    for x, y, k in voiced_runs(c, a, b, fillers):
        x, y = c.snap(max(a, x - c.r["margin_s"])), c.snap(min(b, y + c.r["margin_s"]))
        if x > t:
            pieces.append((t, x, "pause"))
        if y > max(x, t):
            if pieces and pieces[-1][2] == k and pieces[-1][1] >= max(x, t):
                pieces[-1] = (pieces[-1][0], y, k)
            else:
                pieces.append((max(x, t), y, k))
        t = max(t, y)
    if b > t:
        pieces.append((t, b, "pause"))
    # pause slivers shorter than the minimum play at speech speed
    return [(x, y, k if k != "pause" or y - x >= c.r["min_event_s"] else "voiced") for x, y, k in pieces]


def zone_at(zones, t):
    return next((z for z in zones if z[0] <= t < z[1]), zones[-1])


def event_segments(c, lo, hi, events, zones):
    """Split [lo, hi] into speech, fillers, short pauses and cuts.

    events: [(start, end, 'filler' | 'pause')].
    zones:  [(start, end, speech_speed, filler_speed or None)]; None keeps that zone's fillers as speech.
    """
    r, snap = c.r, c.snap
    margin, frame = r["margin_s"], 1 / c.fps
    events = [(a, b, k) for a, b, k in events if k != "filler" or zone_at(zones, a)[3] is not None]
    fillers = [(a, b) for a, b, k in events if k == "filler"]
    spans = []
    for a, b, members in merge([(max(a, lo), min(b, hi), k) for a, b, k in events if b > lo and a < hi], r["merge_s"]):
        a2, b2 = snap(a + margin), snap(b - margin)
        if b2 - a2 >= r["min_event_s"]:
            # voiced runs are left out, so the speech between spans covers them
            spans += [p for p in carve(c, a2, b2, classify(a, b, members), fillers) if p[2] != "voiced"]
    segs, t = [], snap(lo)

    def speech(a, b):
        for z0, z1, speed, _ in zones:
            x, y = max(a, snap(z0)), min(b, snap(z1))
            if y > x:
                segs.append(dict(src=c.name, inp=x, out=y, speed=speed, kind="speech"))

    for i, (a, b, kind) in enumerate(spans):
        if kind == "pause" and b - a + 2 * margin > r["cut_over_s"]:
            # keep the head before and the tail after the dropped silence at 1x; when a filler sits right
            # against the pause, those edges come out of the filler's margin
            x, y = snap(a - r["keep_head_frames"] * frame), snap(b + r["keep_tail_frames"] * frame)
            if x < t:
                if segs and segs[-1]["kind"] != "cut" and segs[-1]["inp"] < x - 1e-6:
                    segs[-1]["out"] = t = x
                else:
                    x = t
            if i + 1 < len(spans) and spans[i + 1][0] < y:
                n0, n1, nk = spans[i + 1]
                if n1 - y >= frame - 1e-6:
                    spans[i + 1] = (y, n1, nk)
                else:
                    y = n0
            y = min(y, snap(hi))
            assert a - x >= frame - 1e-6 and y - b >= frame - 1e-6, (c.name, a, b, x, y)
            speech(t, x)
            segs.append(dict(src=c.name, inp=x, out=y, speed=1.0, kind="cut", keep=[[x, a], [b, y]]))
            t = y
            continue
        speech(t, a)
        if kind == "pause":
            speed = r["short_pause_speed"]
        else:
            speed = zone_at(zones, a)[3] or zone_at(zones, b)[3]
            if speed is None:  # a sounding run inside a welcome pause is welcome speech
                speech(a, b)
                t = b
                continue
        segs.append(dict(src=c.name, inp=a, out=b, speed=speed, kind=kind))
        t = b
    speech(t, snap(hi))
    return segs


def drop(c, segs, spans):
    """Cut each [start, end] of source out of segs as one cut that keeps its head and tail frames at 1x.

    A drop is an editor's decision, such as a set-up stretch with talk in it: `[[clip]] drop` in talk.toml.
    The edges snap to the frame grid. An edge that lands inside a cut, or on its far edge, moves out to that
    cut's edge, so the pause joins the drop and no seam keeps two sets of frames; a later span that then
    starts inside or at the end of this drop's cut joins it too. The new cut keeps
    keep_head_frames after its start and keep_tail_frames before its end, so a pause cut whose kept edge was
    longer (a sound's margin pulled it out) loses those extra kept frames. Segments inside a span go, and a
    segment across an edge is trimmed to it. Runs before the max_s check, so a drop counts before the speed
    rises.
    """
    head, tail = c.r["keep_head_frames"] / c.fps, c.r["keep_tail_frames"] / c.fps
    for d0, d1 in spans:
        d0, d1 = c.snap(d0), c.snap(d1)
        for s in segs:
            if s["kind"] == "cut" and s["inp"] < d0 <= s["out"] + 1e-6:
                d0 = s["inp"]
            if s["kind"] == "cut" and s["inp"] - 1e-6 <= d1 < s["out"]:
                d1 = s["out"]
        out = []
        for s in segs:
            if s["out"] <= d0 + 1e-6 or s["inp"] >= d1 - 1e-6:
                out.append(s)
                continue
            if s["inp"] < d0 - 1e-6:
                out.append(dict(s, out=d0))
            if s["out"] > d1 + 1e-6:
                out.append(dict(s, inp=d1))
        cut = dict(
            src=c.name, inp=d0, out=d1, speed=1.0, kind="cut", keep=[[d0, c.snap(d0 + head)], [c.snap(d1 - tail), d1]]
        )
        at = next((i for i, s in enumerate(out) if s["inp"] >= d1 - 1e-6), len(out))
        segs = [*out[:at], cut, *out[at:]]
    return segs


def coalesce(segs):
    """Drop empty segments and join neighbours of one kind and speed."""
    out = []
    for s in segs:
        if s["out"] - s["inp"] < 1e-6:
            continue
        last = out[-1] if out else None
        same = last and s["kind"] != "cut" and (last["speed"], last["kind"]) == (s["speed"], s["kind"])
        if same and abs(last["out"] - s["inp"]) < 1e-6:
            last["out"] = s["out"]
        else:
            out.append(dict(s))
    return out


def seg_dur(s):
    """Output seconds of one segment."""
    if s["kind"] == "cut":
        return sum(b - a for a, b in s["keep"])
    return (s["out"] - s["inp"]) / s["speed"]


def quantise(segs, fps):
    """Give every segment a whole number of output frames, diffusing the rounding error.

    Segment k ends on frame round(ideal running total * fps). A segment that would get no frame joins a
    neighbour and plays at its speed: the one before it, or the one after when a cut sits before it.
    Between two cuts it keeps one frame. A cut always keeps its own frames, so the next segment pays that back.
    """
    segs = [dict(s) for s in segs]

    def free(o):
        return o is not None and o["kind"] != "cut"

    while True:
        total, done = 0.0, 0
        for s in segs:
            total += seg_dur(s) * fps
            own = round(seg_dur(s) * fps) if s["kind"] == "cut" else 1 if s.get("min1") else 0
            s["frames"] = own if s["kind"] == "cut" else max(round(total - 1e-9) - done, own)
            done += s["frames"]
        zero = next((i for i, s in enumerate(segs) if s["frames"] == 0), None)
        if zero is None:
            return [{k: v for k, v in s.items() if k != "min1"} for s in segs]
        z = segs[zero]
        prev = segs[zero - 1] if zero else None
        nxt = segs[zero + 1] if zero + 1 < len(segs) else None

        def same(o, z=z):
            return free(o) and o["speed"] == z["speed"]

        if free(prev) and abs(prev["out"] - z["inp"]) < 1e-6 and (same(prev) or not same(nxt)):
            prev["out"] = z["out"]
        elif free(nxt) and abs(nxt["inp"] - z["out"]) < 1e-6:
            nxt["inp"] = z["inp"]
        else:
            z["min1"] = True
            continue
        del segs[zero]
        segs = coalesce(segs)


def snap_welcome(welcome, pauses):
    """Move each welcome edge to a pause edge within 1 s, so the 1x window clips no syllable."""
    if not welcome:
        return None
    start, end = welcome
    ends = [e for _, e in pauses if abs(e - start) <= 1.0]
    starts = [(e - s, s) for s, e in pauses if abs(s - end) <= 1.0]
    return [min(ends, key=lambda e: abs(e - start)) if ends else start, max(starts)[1] if starts else end]


def zones_for(clip, total, speed, filler_speed, welcome):
    """[(start, end, speech_speed, filler_speed or None)] covering [0, total]: the welcome, the zones, the default."""
    marks = [x for z in clip["zones"] for x in z[:2]] + (welcome or [])
    edges = sorted({0.0, total, *(min(max(float(x), 0.0), total) for x in marks)})
    out = []
    for a, b in zip(edges, edges[1:], strict=False):
        if welcome and welcome[0] <= a < welcome[1]:
            out.append((a, b, 1.0, None))
        else:
            out.append((a, b, next((z[2] for z in clip["zones"] if z[0] <= a < z[1]), speed), filler_speed))
    return out


def pause_asr_key(cfg):
    """What decides transcribe.read()'s answers: the backend and its model (cli), or its endpoint, full URL and
    language (http). The full URL enters only as a sha256, so the key never stores a query."""
    if transcribe.backend(cfg) == "http":
        url = transcribe.stt_url(cfg)
        return {
            "backend": "http",
            "url": transcribe.endpoint(url),
            "url_sha256": hashlib.sha256(url.encode()).hexdigest(),
            "language": cfg.whisper["language"],
        }
    return {"backend": "cli", "model": Path(cfg.model).name}


def load_pause_asr(cfg, clip):
    """The clip's cached pause-span answers when the speech-to-text configured now wrote them, else {}.

    work/<clip>.pause_asr.json keeps the flat {"a-b": text} shape the retired tool wrote, so the parity check
    still compares it by sha256. work/<clip>.pause_asr.key names the STT that wrote it and the cache's sha256.
    A cache without a matching key (another backend or model, an older run, a hand-copied file) is read again."""
    cache, stamp = cfg.f(clip, "pause_asr.json"), cfg.f(clip, "pause_asr.key")
    if not cache.exists():
        return {}
    data = cache.read_bytes()
    try:
        found = json.loads(stamp.read_text()) if stamp.exists() else None
    except ValueError:
        found = None
    want = {"stt": pause_asr_key(cfg), "pause_asr_sha256": hashlib.sha256(data).hexdigest()}
    if found != want:
        print(f"{clip['name']}: the pause_asr cache is not keyed to this speech-to-text; its spans are read again")
        return {}
    return json.loads(data)


def save_pause_asr(cfg, clip, asr):
    """Write the cache, then its key. A key left from an earlier cache never matches the new cache's sha256."""
    cache = cfg.f(clip, "pause_asr.json")
    cache.write_text(json.dumps(asr, indent=0, sort_keys=True))
    key = {"stt": pause_asr_key(cfg), "pause_asr_sha256": hashlib.sha256(cache.read_bytes()).hexdigest()}
    cfg.f(clip, "pause_asr.key").write_text(json.dumps(key, indent=1, sort_keys=True))


def build_clip(cfg, clip):
    """Segments for one clip. Raises the speech speed by 0.05 up to speed_max while the clip runs over max_s."""
    fps, r = cfg.fps, cfg.rules
    if clip["card"]:  # the whole recording in card_s seconds
        total, frames = audio.duration(clip["file"]), round(clip["card_s"] * fps)
        speed = round(total * fps / frames, 4)
        card = dict(src=clip["name"], inp=0.0, out=total, speed=speed, kind="card", frames=frames)
        info = dict(duration=total, shift=0.0, speed=speed, welcome=None)
        return [card | dict(out_dur=frames / fps, gain=r["card_gain"])], info
    shift = audio.shift(clip["file"], fps)  # the clip ends with its shorter stream, on the frame grid
    total = int(min(audio.duration(cfg.f(clip, "16k.wav")), audio.duration(clip["file"], "v:0") - shift) * fps) / fps
    ev = json.loads(cfg.f(clip, "events.json").read_text())
    words = json.loads(cfg.f(clip, "words.json").read_text())
    events = [(a, b, "filler") for a, b, _ in ev["fillers"]] + [(a, b, "pause") for a, b in ev["pauses"]]
    welcome = snap_welcome(clip.get("welcome"), ev["pauses"])
    for span in clip["drop"]:
        if span[1] > total + 1e-6:
            raise ValueError(f"clip {clip['name']}: drop {span!r} ends after the clip's {total:.3f} s")
    c = SimpleNamespace(
        name=clip["name"],
        fps=fps,
        r=r,
        snap=lambda t: round(round(t * fps) / fps, 6),
        rms=audio.read_rms(cfg.f(clip, "rms.txt")),
        lex=[(w["start"], w["end"]) for w in words if norm(w["word"]) not in FILL],
        voiced_db=clip["voiced_db"],
        mode=clip["evidence"],
        asr=load_pause_asr(cfg, clip) if clip["evidence"] == "asr" else {},
        missing=set(),
    )
    speed, top = clip["speed"], clip.get("speed_max", clip["speed"])
    while True:
        zones = zones_for(clip, total, speed, r["filler_speed"], welcome)
        segs = coalesce(drop(c, event_segments(c, 0.0, total, events, zones), clip["drop"]))
        # a pause span inside a drop span goes whatever whisper hears in it, so it is never read
        c.missing -= {(a, b) for a, b in c.missing if any(c.snap(x) <= a and b <= c.snap(y) for x, y in clip["drop"])}
        if c.missing:  # whisper each pause span alone, then build again with the answers
            print(f"{c.name}: whisper on {len(c.missing)} pause spans")
            for a, b in sorted(c.missing):
                c.asr[f"{a:.3f}-{b:.3f}"] = transcribe.read(cfg, cfg.f(clip, "16k.wav"), a, b)
            save_pause_asr(cfg, clip, c.asr)
            c.missing.clear()
            continue
        if "max_s" not in clip or sum(map(seg_dur, segs)) <= clip["max_s"] or speed >= top - 1e-9:
            break
        speed = round(min(top, speed + 0.05), 2)
    segs = quantise(segs, fps)
    for s in segs:
        s["out_dur"] = round(s["frames"] / fps, 6)
        s["gain"] = r["loud_gain"] if s["speed"] >= r["loud_speed"] else 1.0
    return segs, dict(duration=total, shift=shift, speed=speed, welcome=welcome)


def build(cfg):
    clips = []
    for clip in cfg.clips:
        segs, info = build_clip(cfg, clip)
        kinds = {}
        for s in segs:
            kinds[s["kind"]] = round(kinds.get(s["kind"], 0) + s["out_dur"], 2)
        expected = round(sum(s["out_dur"] for s in segs), 3)
        clips.append(dict(name=clip["name"], **info, expected_s=expected, out_s_by_kind=kinds, segments=segs))
        took = f"{info['duration']:.1f} s -> {expected:.1f} s at {info['speed']}x"
        print(f"{clip['name']}: {took}, {len(segs)} segments, {kinds}")
    edl = dict(
        fps=cfg.fps, rules=cfg.rules, clips=clips, expected_total_s=round(sum(c["expected_s"] for c in clips), 3)
    )
    cfg.f("edl", "json").write_text(json.dumps(edl, indent=1))
    checked = timeline.validate(cfg.f("edl", "json"))
    print(f"total {edl['expected_total_s']} s, {checked['total_frames']} frames, validated by video-utils timeline")
    return edl


class Timeline:
    """Where every segment lands on the output clock, and the map between source and output times."""

    def __init__(self, edl):
        self.rows, self.by_clip, n, fps = [], {}, 0, edl["fps"]  # rows: (out_start, out_end, segment)
        for clip in edl["clips"]:
            first = len(self.rows)
            for s in clip["segments"]:
                self.rows.append((n / fps, (n + s["frames"]) / fps, s))
                n += s["frames"]
            self.by_clip[clip["name"]] = ([r[2]["inp"] for r in self.rows[first:]], self.rows[first:])
        self.total, self.starts = n / fps, [r[0] for r in self.rows]
        self.shift = {c["name"]: c["shift"] for c in edl["clips"]}

    @classmethod
    def load(cls, cfg):
        return cls(json.loads(cfg.f("edl", "json").read_text()))

    def row(self, clip, t):
        """The row whose segment holds source time t of a clip, or None."""
        inps, rows = self.by_clip[clip]
        i = bisect.bisect_right(inps, t) - 1
        return rows[i] if i >= 0 and t < rows[i][2]["out"] else None

    def to_out(self, clip, t, snap=False):
        """Output time of source time t. None inside a dropped span, unless snap moves it to the join."""
        row = self.row(clip, t)
        if row is None:
            return None
        t0, t1, s = row
        if s["kind"] != "cut":  # the segment's real speed is its source length over its whole frames
            return t0 + (t - s["inp"]) / (s["out"] - s["inp"]) * (t1 - t0)
        (a0, a1), (b0, _) = s["keep"]
        if a1 <= t < b0 and not snap:
            return None
        return t0 + (t - a0 if t < a1 else (a1 - a0) + max(0.0, t - b0))

    def to_src(self, t):
        """(source time, segment) under output time t, or None past the end."""
        i = bisect.bisect_right(self.starts, t) - 1
        if i < 0 or t >= self.rows[i][1]:
            return None
        t0, t1, s = self.rows[i]
        if s["kind"] != "cut":
            return s["inp"] + (t - t0) / (t1 - t0) * (s["out"] - s["inp"]), s
        (a0, a1), (b0, _) = s["keep"]
        return (a0 + t - t0 if t - t0 < a1 - a0 else b0 + t - t0 - (a1 - a0)), s
