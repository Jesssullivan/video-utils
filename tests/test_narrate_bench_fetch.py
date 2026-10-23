"""narrate/bench/fetch.py: the pinned dry-run plan and the hash-recording apply path.

No network and no weights: the apply tests serve synthetic bytes from a local file:// mirror laid out like the
Hub's resolve URLs. The real sources file is checked for pins, sizes and selection only.
"""

import hashlib
import importlib.util
import io
import json
import os
import re
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("narrate_bench_fetch", ROOT / "narrate" / "bench" / "fetch.py")
fetch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fetch)

REV = "0123456789abcdef0123456789abcdef01234567"
WEIGHTS = b"synthetic weights " * 1000
CONFIG = b'{"synthetic": true}\n'


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = fetch.main(argv)
    return code, out.getvalue(), err.getvalue()


class RealSources(unittest.TestCase):
    def setUp(self):
        self.doc = fetch.load_sources()

    def test_every_source_is_pinned_and_licensed(self):
        kinds = {source["kind"] for source in self.doc["sources"]}
        self.assertEqual(kinds, {"git", "hf"})
        for source in self.doc["sources"]:
            pin = source.get("commit") or source.get("revision")
            self.assertRegex(pin, r"^[0-9a-f]{40}$", source["id"])
            self.assertTrue(source["licence"], source["id"])
            for entry in source.get("files", []):
                self.assertGreater(entry["bytes"], 0)
                # Every weight file the Hub stores in LFS carries its declared sha256; only small
                # non-LFS files (configs, tokenizer text, a 2 KB normaliser checkpoint) are hashed at download time.
                weights = entry["path"].endswith((".gguf", ".safetensors", ".pth", ".ckpt", ".bin"))
                if weights and entry["bytes"] > 1024 * 1024:
                    self.assertRegex(entry["sha256"] or "", r"^[0-9a-f]{64}$", f"{source['id']}:{entry['path']}")

    def test_three_arms_on_both_hosts_and_optional_tier_excluded_by_default(self):
        arms = {arm for source in fetch.select(self.doc) for arm in source.get("arms", [])}
        for arm in ("A1-gpu", "A2-gpu", "A3-gpu", "A1-mac", "A2-mac", "A3-mac", "scoring"):
            self.assertIn(arm, arms)
        self.assertFalse([s["id"] for s in fetch.select(self.doc) if s.get("optional")])
        self.assertIn("drama3", [s["id"] for s in fetch.select(self.doc, include_optional=True)])
        self.assertEqual([s["id"] for s in fetch.select(self.doc, only=["drama3"])], ["drama3"])
        mac = fetch.select(self.doc, arms=["A1-mac"])
        self.assertEqual(sorted(s["id"] for s in mac), ["Ming-3.0-tts", "ming3-0.5b-mlx", "mlx-audio"])

    def test_dry_run_prints_a_pinned_plan_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as scratch:
            dest = Path(scratch) / "weights"
            code, out, err = run(["--dest", str(dest), "--arm", "A2-gpu"])
            self.assertEqual(code, 0, err)
            self.assertFalse(dest.exists())
        result = json.loads(out)
        self.assertEqual(result["mode"], "dry-run")
        urls = [f["url"] for source in result["hf"] for f in source["files"]]
        self.assertTrue(urls)
        for url in urls:
            self.assertRegex(url, r"^https://huggingface\.co/[^/]+/[^/]+/resolve/[0-9a-f]{40}/")
        self.assertEqual({f["state"] for source in result["hf"] for f in source["files"]}, {"missing"})
        self.assertEqual(result["totals"]["bytes"], result["totals"]["bytes_missing"])
        commits = {g["id"]: g["commit"] for g in result["git"]}
        self.assertIn("llama.cpp", commits)
        self.assertTrue(all(any(c in cmd for cmd in g["commands"]) for g in result["git"] for c in [g["commit"]]))

    def test_destination_inside_the_repository_is_refused(self):
        code, _, err = run(["--dest", str(ROOT / "models" / "narrate")])
        self.assertEqual(code, 2)
        self.assertIn("inside the repository", err)

    def test_destination_falls_back_to_the_environment(self):
        with tempfile.TemporaryDirectory() as scratch:
            previous = os.environ.get(fetch.DEST_ENV)
            os.environ[fetch.DEST_ENV] = scratch
            try:
                self.assertEqual(fetch.resolve_dest(None), Path(scratch).resolve())
            finally:
                if previous is None:
                    os.environ.pop(fetch.DEST_ENV)
                else:
                    os.environ[fetch.DEST_ENV] = previous

    def test_unknown_source_is_refused(self):
        code, _, err = run(["--only", "no-such-source", "--dest", tempfile.gettempdir() + "/narrate-none"])
        self.assertEqual(code, 2)
        self.assertIn("unknown source ids", err)


class FileMirrorApply(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        base = Path(self.scratch.name)
        self.mirror, self.dest = base / "mirror", base / "weights"
        for name, body in (("model-q8.gguf", WEIGHTS), ("sub/config.json", CONFIG)):
            path = self.mirror / "synthetic" / "tts" / "resolve" / REV / name
            path.parent.mkdir(parents=True)
            path.write_bytes(body)
        self.sources = base / "sources.json"
        self.write_sources(hashlib.sha256(WEIGHTS).hexdigest())

    def tearDown(self):
        self.scratch.cleanup()

    def write_sources(self, weights_sha):
        doc = {"schema_version": 1, "recorded": "2026-10-22", "sources": [
            {"id": "synthetic-tts", "kind": "hf", "arms": ["A1-gpu"], "repo": "synthetic/tts", "revision": REV,
             "licence": "MIT", "optional": False,
             "files": [{"path": "model-q8.gguf", "bytes": len(WEIGHTS), "sha256": weights_sha},
                       {"path": "sub/config.json", "bytes": len(CONFIG), "sha256": None}]},
            {"id": "synthetic-src", "kind": "git", "arms": ["A1-gpu"], "url": "https://example.invalid/src",
             "commit": REV, "ref": "test", "licence": "MIT"}]}
        self.sources.write_text(json.dumps(doc), encoding="utf-8")

    def apply(self, *extra):
        return run(["--sources", str(self.sources), "--dest", str(self.dest), "--hub-base", self.mirror.as_uri(),
                    "--allow-file-hub", "--apply", *extra])

    def test_apply_downloads_verifies_and_records_hashes(self):
        code, out, err = self.apply()
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["downloaded"], 2)
        self.assertEqual((self.dest / "synthetic-tts" / "model-q8.gguf").read_bytes(), WEIGHTS)
        self.assertEqual((self.dest / "synthetic-tts" / "sub" / "config.json").read_bytes(), CONFIG)
        sums = (self.dest / "synthetic-tts" / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
        self.assertEqual(sums, [f"{hashlib.sha256(WEIGHTS).hexdigest()}  model-q8.gguf",
                                f"{hashlib.sha256(CONFIG).hexdigest()}  sub/config.json"])
        receipt = json.loads((self.dest / "fetch-receipt.json").read_text(encoding="utf-8"))
        checks = {r["path"]: r["check"] for r in receipt["files"]}
        self.assertEqual(checks, {"model-q8.gguf": "matched_declared", "sub/config.json": "recorded_at_download"})
        self.assertEqual(receipt["sources_sha256"], hashlib.sha256(self.sources.read_bytes()).hexdigest())
        self.assertEqual([g["id"] for g in receipt["git_not_cloned"]], ["synthetic-src"])
        self.assertFalse((self.dest / "src").exists())
        self.assertFalse(list(self.dest.rglob(".partial-*")))

    def test_second_apply_reuses_files_and_checks_recorded_hashes(self):
        self.assertEqual(self.apply()[0], 0)
        code, out, err = self.apply()
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["downloaded"], 0)
        receipt = json.loads((self.dest / "fetch-receipt.json").read_text(encoding="utf-8"))
        self.assertEqual({r["status"] for r in receipt["files"]}, {"already_present"})
        self.assertEqual(len(list((self.dest / "receipts").glob("*.json"))), 2)
        self.assertEqual({r["path"]: r["check"] for r in receipt["files"]},
                         {"model-q8.gguf": "matched_declared", "sub/config.json": "matched_recorded"})
        # A same-size file whose bytes changed after it was recorded is refused, not re-recorded.
        (self.dest / "synthetic-tts" / "sub" / "config.json").write_bytes(CONFIG.upper())
        code, _, err = self.apply()
        self.assertEqual(code, 2)
        self.assertIn("differs from", err)

    def test_declared_hash_mismatch_leaves_nothing_behind(self):
        self.write_sources("f" * 64)
        code, _, err = self.apply()
        self.assertEqual(code, 2)
        self.assertIn("does not match the declared", err)
        self.assertFalse((self.dest / "synthetic-tts" / "model-q8.gguf").exists())
        self.assertFalse(list(self.dest.rglob(".partial-*")))

    def test_hashes_measured_before_a_failure_are_kept(self):
        (self.mirror / "synthetic" / "tts" / "resolve" / REV / "sub" / "config.json").unlink()
        self.write_sources(hashlib.sha256(WEIGHTS).hexdigest())
        code, _, _ = self.apply()
        self.assertEqual(code, 2)
        sums = (self.dest / "synthetic-tts" / "SHA256SUMS").read_text(encoding="utf-8")
        self.assertEqual(sums, f"{hashlib.sha256(WEIGHTS).hexdigest()}  model-q8.gguf\n")

    def test_size_mismatch_is_refused(self):
        (self.mirror / "synthetic" / "tts" / "resolve" / REV / "model-q8.gguf").write_bytes(WEIGHTS + b"extra")
        code, _, err = self.apply()
        self.assertEqual(code, 2)
        self.assertIn("exceeds its declared", err)

    def test_file_hub_needs_the_explicit_flag(self):
        code, _, err = run(["--sources", str(self.sources), "--dest", str(self.dest), "--hub-base",
                            self.mirror.as_uri(), "--apply"])
        self.assertEqual(code, 2)
        self.assertIn("hub base must be https", err)
        self.assertFalse(self.dest.exists())

    def test_unsafe_paths_and_bad_pins_are_refused(self):
        doc = json.loads(self.sources.read_text(encoding="utf-8"))
        for mutate, message in ((lambda d: d["sources"][0]["files"][0].update(path="../escape.gguf"), "unsafe file path"),
                                (lambda d: d["sources"][0].update(revision="main"), "full revision"),
                                (lambda d: d["sources"][1].update(commit="abc123"), "full commit")):
            changed = json.loads(json.dumps(doc))
            mutate(changed)
            self.sources.write_text(json.dumps(changed), encoding="utf-8")
            code, _, err = self.apply()
            self.assertEqual(code, 2)
            self.assertTrue(re.search(message, err), err)


if __name__ == "__main__":
    unittest.main()
