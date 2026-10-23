"""Stdlib smoke for `bazel test //narrate:stdlib_test`, on the hermetic CPython with no pip packages.

Every narrate module imports, the example narrate.toml loads, and the pure parts give their documented answers:
the adapters, chunker, normaliser, the engine predicates against narrate/dhall/check.py, the fixture lexicon and
RewriteCheck, the fake engine and WER. No FFmpeg, whisper or engine runs here: the pytest suite covers those
(`just narrate-test`, or //narrate:pytest under --config=host-tools).
"""

import importlib
import importlib.util
import itertools
import json
import tempfile
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
MODULES = (
    "adapters",
    "audio",
    "chunker",
    "config",
    "engine",
    "evaluate",
    "ir",
    "lexical",
    "normalise",
    "policy",
    "qa",
    "registry",
    "render",
    "sim",
    "sim_worker",
    "verify",
)


class StdlibSmoke(unittest.TestCase):
    def test_every_module_imports(self):
        names = sorted(p.stem for p in PACKAGE.glob("*.py") if p.stem not in ("__init__", "__main__"))
        self.assertEqual(sorted(MODULES), names)
        for name in names:
            with self.subTest(module=name):
                importlib.import_module(f"narrate.{name}")

    def test_the_example_config_loads(self):
        from narrate.config import Config

        cfg = Config(PACKAGE / "examples" / "narrate.toml")
        job = cfg.job()
        self.assertEqual((job["id"], job["engine"], job["input"]), ("job-fixture-fake", "fake-sine", "Markdown"))
        self.assertEqual(sorted(cfg.registry()), ["consents", "engines", "pronunciation", "voices"])
        self.assertEqual(cfg.fit["speed_max"], 1.15)

    def test_the_example_script_becomes_one_timed_slide(self):
        from narrate import adapters, chunker
        from narrate.normalise import Normaliser

        script = adapters.load("Markdown", PACKAGE / "dhall" / "examples" / "script.md")
        (segment,) = script.segments
        self.assertEqual((segment.id, segment.target_dur), ("slide-fixture", 6.0))
        self.assertEqual([d.kind for d in segment.directions], ["pause"])
        table = json.loads((PACKAGE / "dhall" / "examples" / "pronunciation.json").read_text())
        normaliser = Normaliser(table)
        spoken = [normaliser.say(c.text, segment.id) for c in chunker.chunk_segment(segment, 300)]
        self.assertIn("8 percent", spoken[0])

    def test_engine_predicates_match_the_dhall_port(self):
        from narrate import policy

        spec = importlib.util.spec_from_file_location("check", PACKAGE / "dhall" / "check.py")
        check = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(check)
        profiles = list(policy.PROFILE_BACKENDS)
        backends = sorted(set().union(*policy.PROFILE_BACKENDS.values()))
        for profile, backend, hosted, conf, estate in itertools.product(profiles, backends, *[(False, True)] * 3):
            engine = {
                "profile": profile,
                "backend": backend,
                "hosted": hosted,
                "confidentialAllowed": conf,
                "estateControlled": estate,
            }
            self.assertEqual(policy.may_run_confidential(engine), check.may_run_confidential(engine))
            self.assertEqual(policy.consistent(engine), check.consistent(engine))

    def test_fixture_lexicon_and_rewrite_check(self):
        from narrate import lexical

        directory = PACKAGE / "tests" / "fixtures" / "lexical"
        pin = {
            "release": "xoxd-lexical@0.0.0-fixture",
            "commit": "0" * 40,
            "valeRegister": "slides",
            "rewriteCheck": True,
        }
        pin["lexiconSha256"] = lexical.sha256_file(directory / "estate-lexicon.json")
        pin["promptDigestSha256"] = lexical.sha256_file(directory / "prompt-digest.txt")
        pin["valeRegisterSha256"] = lexical.sha256_file(directory / "vale" / "registers" / "slides.ini")
        self.assertEqual(lexical.Release(directory, pin).register, "slides")
        self.assertEqual(lexical.rewrite_check("We ship 3 tools.", "We will ship 3 tools."), [])
        self.assertTrue(lexical.rewrite_check("We ship 3 tools.", "We ship 4 tools."))

    def test_fake_engine_and_wer(self):
        from narrate import audio, engine, qa

        fake = {"id": "fake-sine", "backend": "Fake", "endpoint": "fake://sine", "sampleRateHz": 24000}
        data, _ = engine.synthesize(fake, "Hello there.", {"id": "v"}, {}, 0, 1.0, {})
        again, _ = engine.synthesize(fake, "Hello there.", {"id": "v"}, {}, 0, 1.0, {})
        self.assertEqual(data, again)
        self.assertEqual(audio.parse(data).rate, 24000)
        self.assertAlmostEqual(qa.wer("the cat sat", "the cat"), 0.3333, places=4)
        with tempfile.TemporaryDirectory() as work:
            path = audio.parse(data).write(Path(work) / "take.wav")
            self.assertEqual(audio.read(path).samples, audio.parse(data).samples)


if __name__ == "__main__":
    unittest.main(verbosity=2)
