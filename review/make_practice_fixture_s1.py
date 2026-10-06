#!/usr/bin/env python3
"""Create a fresh ignored synthetic source-clock UI fixture, never a real take."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import wave


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output",type=Path)
    parser.add_argument("--empty-markers",action="store_true")
    args=parser.parse_args()
    repo=Path(__file__).resolve().parents[1]
    output=args.output.resolve()
    if not output.is_relative_to(repo/"artifacts") or output.exists():
        parser.error("output must be a fresh directory under this worktree's ignored artifacts/")
    output.mkdir(parents=True)
    rate=44100
    samples=bytearray()
    for index in range(10*rate):
        time=index/rate
        samples.extend(struct.pack("<h",int(2800*math.sin(2*math.pi*32.703*time)+700*math.sin(2*math.pi*130.813*time))))
    for name in ["baseline.wav","cleaned.wav","residual.wav"]:
        with wave.open(str(output/name),"wb") as handle:
            handle.setnchannels(1);handle.setsampwidth(2);handle.setframerate(rate);handle.writeframes(samples)
    hashes={path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in output.glob("*.wav")}
    source_hash=hashes["baseline.wav"]
    manifest={"source":{"path":"synthetic-practice-s1.wav","sha256":source_hash},
      "timeline":{"audio_start_seconds":2,"format_start_seconds":1},
      "pcm":{"duration_seconds":10,"sample_rate":rate,"sample_count":10*rate},
      "outputs":{"baseline":"baseline.wav","cleaned":"cleaned.wav","residual":"residual.wav"},"output_sha256":hashes}
    markers=[] if args.empty_markers else [{"source_time_seconds":4,"end_seconds":4.8,"name":"phrase_recurrence_review","confidence":"heuristic_not_probability","status":"needs_review"},{"source_time_seconds":7,"end_seconds":7.5,"name":"rhythm_review","confidence":"unknown","status":"needs_review"}]
    for name,value in [("manifest",manifest),("markers",{"source_sha256":source_hash,"markers":markers})]:
        (output/(name+".json")).write_text(json.dumps(value,indent=2)+"\n")
    print(json.dumps({"run":str(output),"source_sha256":source_hash,"evidence":"generated_ui_fixture_not_a_recorded_guitar_performance"}))


if __name__=="__main__":main()
