"""Stdlib smoke for `bazel test //condense:stdlib_test`, on the hermetic CPython with no pip packages.

Every condense module that reaches no numpy import imports (avsync.py and its importers are left to pytest), the
example talk.toml loads, and the pure EDL, time map, filler and caption helpers give their documented answers.
No FFmpeg, whisper or Rust binary runs here: the pytest suite covers those (`just condense-test`, or
//condense:pytest under --config=host-tools).
"""

import ast
import importlib
import shutil
import tempfile
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
# The modules the stages share and this smoke exercises: they must stay importable without numpy.
CORE = {"audio", "captions", "config", "edl", "events", "overlay", "publish", "recover", "render", "timeline"}


def numpy_closure():
    """Modules that import numpy, directly or through a sibling."""
    edges, direct = {}, set()
    for path in PACKAGE.glob("*.py"):
        edges[path.stem] = set()
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                direct.update(path.stem for a in node.names if a.name.split(".")[0] == "numpy")
            elif isinstance(node, ast.ImportFrom) and node.level == 1:
                edges[path.stem].update([node.module] if node.module else [a.name for a in node.names])
            elif isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "numpy":
                direct.add(path.stem)
    found = set(direct)
    while grown := {m for m, uses in edges.items() if uses & found} - found:
        found |= grown
    return found


class StdlibSmoke(unittest.TestCase):
    def test_every_stdlib_module_imports(self):
        skip = numpy_closure() | {"__init__", "__main__"}  # __main__ runs the CLI on import
        self.assertIn("avsync", skip)
        names = sorted(p.stem for p in PACKAGE.glob("*.py") if p.stem not in skip)
        self.assertEqual(CORE - set(names), set())
        for name in names:
            with self.subTest(module=name):
                importlib.import_module(f"condense.{name}")

    def test_the_example_config_loads(self):
        from condense.config import Config

        with tempfile.TemporaryDirectory() as work:
            shutil.copy(PACKAGE / "examples" / "talk.toml", Path(work) / "talk.toml")
            cfg = Config(Path(work) / "talk.toml")
            self.assertEqual([c["name"] for c in cfg.clips], ["intro", "demo"])
            self.assertEqual(cfg.rules["cut_over_s"], 1.0)
            self.assertEqual(cfg.encode["loudness"], -16.0)
            self.assertEqual(cfg.fps, 30)
            self.assertEqual(cfg.f("intro", "edl.json"), Path(work).resolve() / "work" / "intro.edl.json")

    def test_quantise_keeps_whole_frames_and_the_time_map_inverts(self):
        from condense import edl

        fps = 30
        segs = [
            {"kind": "speech", "inp": 0.0, "out": 1.01, "speed": 2.0},
            {"kind": "pause", "inp": 1.01, "out": 1.5, "speed": 4.0},
            {"kind": "filler", "inp": 1.5, "out": 1.53, "speed": 8.0},
            {"kind": "speech", "inp": 1.53, "out": 3.2, "speed": 2.0},
        ]
        ideal = sum(edl.seg_dur(s) for s in segs) * fps
        quantised = edl.quantise(segs, fps)
        self.assertEqual(sum(s["frames"] for s in quantised), round(ideal))
        self.assertTrue(all(s["frames"] > 0 for s in quantised))
        tl = edl.Timeline({"fps": fps, "clips": [{"name": "a", "shift": 0.0, "segments": quantised}]})
        self.assertEqual(tl.to_out("a", 0.0), 0.0)
        for t in (0.25, 1.2, 2.0, 3.1):
            src, _ = tl.to_src(tl.to_out("a", t))
            self.assertAlmostEqual(src, t, places=9)
        self.assertIsNone(tl.to_src(tl.total))

    def test_fillers_and_captions(self):
        from condense import captions, events

        self.assertTrue(events.is_filler("Um,"))
        self.assertTrue(events.is_filler("ummm"))
        self.assertFalse(events.is_filler("under"))
        cues = captions.cues([(0.0, 0.4, "Hello"), (0.5, 0.9, "there."), (3.0, 3.2, "Next")])
        self.assertEqual([c[2] for c in cues], [["Hello there."], ["Next"]])
        self.assertTrue(captions.srt(cues).startswith("1\n00:00:00,000 --> 00:00:01,000\nHello there.\n"))
        self.assertTrue(captions.vtt(cues).startswith("WEBVTT\n\n00:00:00.000 --> 00:00:01.000\n"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
