"""The face timeline a VRM overlay is drawn from: face.json, schema face.timeline/v1 (docs/spec/NARRATED_VIDEO.md,
"Face timeline").

face.json holds one frame per overlay frame on the narration_output clock: frame i shows the face at i * den / num
seconds into its segment's narration.wav. The renderer reads it and nothing else about the narration, so the VRM
external never needs the narration's audio.

  {schema: face.timeline/v1, clock: narration_output, fps: {num, den}, frames: N, source: S,
   narration: {run_id, content_sha256, narration_sha256},
   track: [{i, mouth: {viseme, weight}, blink: [left, right], mood: {preset: weight}, look: [yaw, pitch],
            head: [yaw, pitch, roll]}]}

Visemes are the VRM mouth presets sil, aa, ih, ou, ee and oh. Moods are the VRM presets happy, angry, sad, relaxed and
surprised. Weights are 0 to 1. Angles are degrees in the VRM lookAt convention: yaw positive to the model's left,
pitch positive down.

v1 has one source, loudness_envelope: the mouth opens with the narration's RMS per frame (aa, weight min(1, 4 rms))
and closes to sil below a floor, the eyes blink on a fixed, seeded schedule, and mood, look and head stay neutral. It
is a deterministic placeholder. Word timings from a forced aligner, phonemes inside word spans and an expression
track are later sources; until one lands, VRM lip sync can only follow loudness, and lip sync stays pending_operator.
"""

import math
from pathlib import Path

from .. import audio
from ..ir import sha256_file
from .job import JobError

SCHEMA = "face.timeline/v1"
CLOCK = "narration_output"
VISEMES = ("sil", "aa", "ih", "ou", "ee", "oh")
MOODS = ("happy", "angry", "sad", "relaxed", "surprised")
SOURCES = ("loudness_envelope",)
SILENCE_RMS = 0.01  # below this RMS (full scale 1.0) a frame's mouth is sil
MOUTH_GAIN = 4.0
BLINK_EVERY_S = 3.7  # a blink starts every 3.7 s of narration, first at 1.3 s
BLINK_FIRST_S = 1.3
BLINK_FRAMES = (0.6, 1.0, 0.6)  # closure per frame of one blink
MAX_FRAMES = 30 * 60 * 60  # one hour at 30 fps


def refuse(detail):
    raise JobError("face_timeline_invalid", detail)


def weight(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 1


def angle(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and -180 <= value <= 180


def neutral(i):
    return {
        "i": i,
        "mouth": {"viseme": "sil", "weight": 0},
        "blink": [0, 0],
        "mood": {m: 0 for m in MOODS},
        "look": [0, 0],
        "head": [0, 0, 0],
    }


def blink_closure(i, fps):
    """The eyelid closure of frame i from the fixed blink schedule (0 open, 1 shut)."""
    t = i * fps["den"] / fps["num"]
    if t < BLINK_FIRST_S:
        return 0
    period = round(BLINK_EVERY_S * fps["num"] / fps["den"])
    start = round(BLINK_FIRST_S * fps["num"] / fps["den"])
    phase = (i - start) % max(period, len(BLINK_FRAMES) + 1)
    return BLINK_FRAMES[phase] if phase < len(BLINK_FRAMES) else 0


def window(i, per_frame, num):
    """The first sample of frame i on the narration clock: floor(i * rate * den / num), in integers."""
    return i * per_frame // num


def from_narration(run_dir, manifest, fps):
    """The loudness_envelope face timeline of one narrate run at fps. run_dir holds narration.wav and the run's
    manifest; frames = floor(samples * num / (rate * den)), at least 1. Frame i reads the samples from
    floor(i * rate * den / num) up to frame i + 1's first sample, so each window starts at i * den / num s on the
    narration clock; any remainder shorter than one frame at the end is not drawn."""
    wav = Path(run_dir) / "narration.wav"
    try:
        pcm = audio.read(wav)
    except (OSError, ValueError):
        refuse("narration.wav is not mono 16-bit PCM WAV")
    samples = pcm.samples
    count = max(1, math.floor(len(samples) * fps["num"] / (pcm.rate * fps["den"])))
    if count > MAX_FRAMES:
        refuse(f"the narration is longer than {MAX_FRAMES} frames")
    per_frame = pcm.rate * fps["den"]  # samples per frame, times num
    track = []
    for i in range(count):
        chunk = samples[window(i, per_frame, fps["num"]) : window(i + 1, per_frame, fps["num"])] or (0,)
        rms = math.sqrt(sum(s * s for s in chunk) / len(chunk)) / 32768
        frame = neutral(i)
        if rms >= SILENCE_RMS:
            frame["mouth"] = {"viseme": "aa", "weight": round(min(1.0, MOUTH_GAIN * rms), 4)}
        closure = blink_closure(i, fps)
        frame["blink"] = [closure, closure]
        track.append(frame)
    return {
        "schema": SCHEMA,
        "clock": CLOCK,
        "fps": {"num": fps["num"], "den": fps["den"]},
        "frames": count,
        "source": "loudness_envelope",
        "narration": {
            "run_id": manifest.get("run_id"),
            "content_sha256": manifest.get("content_sha256"),
            "narration_sha256": sha256_file(wav),
        },
        "track": track,
    }


def validate(doc, fps=None, narration=None):
    """Refuse face_timeline_invalid unless doc is a face.timeline/v1 on the narration_output clock, at fps when
    given, bound to narration ({run_id, content_sha256}) when given, with one well-formed frame per index."""
    if not isinstance(doc, dict) or doc.get("schema") != SCHEMA:
        refuse(f"the face timeline is not {SCHEMA}")
    if doc.get("clock") != CLOCK:
        refuse(f"the face timeline is not on the {CLOCK} clock")
    rate = doc.get("fps")
    if not (isinstance(rate, dict) and isinstance(rate.get("num"), int) and isinstance(rate.get("den"), int)):
        refuse("fps is {num, den}")
    if rate["num"] < 1 or rate["den"] < 1:
        refuse("fps is positive")
    if fps is not None and (rate["num"], rate["den"]) != (fps["num"], fps["den"]):
        refuse(f"the face timeline is at {rate['num']}/{rate['den']}, not the base's {fps['num']}/{fps['den']}")
    if doc.get("source") not in SOURCES:
        refuse(f"source is one of {', '.join(SOURCES)}")
    bound = doc.get("narration") if isinstance(doc.get("narration"), dict) else {}
    if narration is not None and any(bound.get(k) != narration.get(k) for k in ("run_id", "content_sha256")):
        refuse("the face timeline is bound to another narration")
    track = doc.get("track")
    if not isinstance(track, list) or not 1 <= len(track) <= MAX_FRAMES or doc.get("frames") != len(track):
        refuse("frames is the length of a non-empty track")
    for i, frame in enumerate(track):
        where = f"frame {i}"
        if not isinstance(frame, dict) or frame.get("i") != i:
            refuse(f"{where}: frames are indexed 0 to frames - 1 in order")
        mouth = frame.get("mouth")
        if not (isinstance(mouth, dict) and mouth.get("viseme") in VISEMES and weight(mouth.get("weight"))):
            refuse(f"{where}: mouth is {{viseme, weight}} with a viseme of {', '.join(VISEMES)}")
        blink = frame.get("blink")
        if not (isinstance(blink, list) and len(blink) == 2 and all(weight(b) for b in blink)):
            refuse(f"{where}: blink is [left, right], each 0 to 1")
        mood = frame.get("mood")
        if not (isinstance(mood, dict) and set(mood) <= set(MOODS) and all(weight(w) for w in mood.values())):
            refuse(f"{where}: mood holds VRM presets {', '.join(MOODS)}, each 0 to 1")
        look, head = frame.get("look"), frame.get("head")
        if not (isinstance(look, list) and len(look) == 2 and all(angle(a) for a in look)):
            refuse(f"{where}: look is [yaw, pitch] in degrees")
        if not (isinstance(head, list) and len(head) == 3 and all(angle(a) for a in head)):
            refuse(f"{where}: head is [yaw, pitch, roll] in degrees")
    return doc
