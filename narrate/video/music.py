"""The music stage of lane L4: one arranged cycle of the bed (docs/spec/NARRATED_VIDEO.md, "Music bed").

The bed record names 2 or 3 loops by SHA-256. Each loop comes from the private store, must have the record's byte
count, and becomes 48 kHz mono with its gain (and its tempo factor through one FFmpeg atempo, only when it is not 1).
The layers are summed into one cycle: the least common multiple of their lengths when that is at most
MAX_CYCLE_S, so every layer repeats whole, else the longest layer's length (shorter layers repeat and the last
repeat is cut, recorded as cycle_rule "longest"). A sum that would clip is scaled down as a whole, recorded as
headroom_gain_db. bed.wav is that cycle; mix tiles it to the program's length, sets its level from the voice and
ducks it. The stage measures the cycle's integrated loudness, which mix needs.

The licence PDF and Content ID gates are not music's: its key holds no licence field, so a state recorded here would
go stale when the operator records one. admit lists them under pending_operator and deliver_check, whose key holds
them, decides them.

The record's acquisition is checked again here: only the operator acquires a bed. No loop is fetched, searched for
or bought, and no loop name, vendor id or path enters an output: layers are named by digest.
"""

import array
import math

from .. import audio
from .common import RATE_HZ, StageRefused, loudness, to_mono, work_dir, write_json

MAPPING = "music_bed_v1"
MAX_CYCLE_S = 120
OUTPUT_AXIS = "bed sample index / sample_rate; mix places sample 0 at the base clock's start"
SOURCE_AXIS = (
    "none: loops are arranged into a new bed; a layer's tempo_factor may change its tempo, and stretch_applied says "
    "whether any did"
)
PEAK = 32767


def cycle_length(lengths):
    """(samples, rule): the least common multiple when it fits MAX_CYCLE_S, else the longest layer."""
    lcm = 1
    for n in lengths:
        lcm = lcm * n // math.gcd(lcm, n)
    if lcm <= MAX_CYCLE_S * RATE_HZ:
        return lcm, "lcm"
    return max(lengths), "longest"


def arrange(layers, total):
    """Sum the layers (arrays of int16), each repeated to total samples. Returns (array('h'), headroom_gain_db)."""
    acc = array.array("i", bytes(4 * total))
    for samples in layers:
        n = len(samples)
        tiled = samples * (total // n) + samples[: total % n]
        acc = array.array("i", map(int.__add__, acc, tiled))
    peak = max((abs(v) for v in acc), default=0)
    if peak <= PEAK:
        return array.array("h", acc), 0.0
    scale = PEAK / peak
    return array.array("h", (round(v * scale) for v in acc)), round(20 * math.log10(scale), 4)


def run_music(rc, row, partial):
    bed = rc.records["music_beds"][rc.job["music"]["bed"]]
    if bed["acquisition"]["acquiredBy"] != "Operator":
        raise StageRefused("bed_acquisition_agent", "only the operator acquires a bed (MusicBed.acquiredBy)")
    rows, pcms = [], []
    with work_dir(rc.store) as work:
        for i, layer in enumerate(bed["layers"]):
            path = rc.env.source(layer["sha256"], f"bed layer {i}")
            if path.stat().st_size != layer["bytes"]:
                raise StageRefused("bed_digest_mismatch", f"bed layer {i} is not the record's {layer['bytes']} bytes")
            chain = []
            if layer["tempoFactor"] != 1:
                chain.append(f"atempo={layer['tempoFactor']:.6f}")
            if layer["gainDb"] != 0:
                chain.append(f"volume={layer['gainDb']}dB")
            pcm = audio.read(to_mono(path, work / f"layer-{i}.wav", chain=",".join(chain) or None))
            if not pcm.samples:
                raise StageRefused("bed_loop_empty", f"bed layer {i} holds no sound")
            pcms.append(pcm.samples)
            rows.append(
                {
                    "sha256": layer["sha256"],
                    "tempo_factor": layer["tempoFactor"],
                    "gain_db": layer["gainDb"],
                    "samples": len(pcm.samples),
                }
            )
        total, rule = cycle_length([r["samples"] for r in rows])
        samples, headroom = arrange(pcms, total)
    for r in rows:
        r["repeats"] = round(total / r["samples"], 6)
    audio.Pcm(RATE_HZ, samples).write(partial / "bed.wav")
    measured = loudness(partial / "bed.wav")
    if not math.isfinite(measured["integrated_lufs"]):
        raise StageRefused("bed_silent", "the arranged bed has no measurable loudness")
    stretched = any(r["tempo_factor"] != 1 for r in rows)
    write_json(
        partial / "bed.json",
        {
            "bed": bed["id"],
            "layers": rows,
            "cycle_samples": total,
            "cycle_rule": rule,
            "headroom_gain_db": headroom,
            "sample_rate": RATE_HZ,
        },
    )
    return {
        "measurements": {
            "cycle_samples": total,
            "cycle_s": round(total / RATE_HZ, 6),
            "cycle_rule": rule,
            "headroom_gain_db": headroom,
            "integrated_lufs": measured["integrated_lufs"],
            "true_peak_dbtp": measured["true_peak_dbtp"],
            "layers": len(rows),
            "sources": sorted({layer["source"] for layer in bed["layers"]}),
        },
        "timeline": {
            "mapping": MAPPING,
            "no_time_stretch": False,
            "stretch_applied": stretched,
            "sample_rate": RATE_HZ,
            "total_samples": total,
            "layers": [{"sha256": r["sha256"], "tempo_factor": r["tempo_factor"]} for r in rows],
            "output_axis": OUTPUT_AXIS,
            "source_axis": SOURCE_AXIS,
        },
        "states": {"source_checks": "passed", "render": "local"},
    }
