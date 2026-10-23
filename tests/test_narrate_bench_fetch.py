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
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("narrate_bench_fetch", ROOT / "narrate" / "bench" / "fetch.py")
fetch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fetch)

REV = "0123456789abcdef0123456789abcdef01234567"
WEIGHTS = b"synthetic weights " * 1000
CONFIG = b'{"synthetic": true}\n'


def git_blob(data):
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


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
                # Every file is hash-bound before download: an LFS file by its declared sha256, a non-LFS file
                # (configs, tokenizer text, hyperparams.yaml) by the Hub's git blob sha1. Exactly one is declared.
                label = f"{source['id']}:{entry['path']}"
                if entry["sha256"] is None:
                    self.assertRegex(entry.get("git_blob_sha1") or "", r"^[0-9a-f]{40}$", label)
                else:
                    self.assertRegex(entry["sha256"], r"^[0-9a-f]{64}$", label)
                    self.assertNotIn("git_blob_sha1", entry, label)

    def test_three_arms_on_both_hosts_and_optional_tier_excluded_by_default(self):
        arms = {arm for source in fetch.select(self.doc) for arm in source.get("arms", [])}
        for arm in ("A1-gpu", "A2-gpu", "A3-gpu", "A1-mac", "A2-mac", "A3-mac", "scoring"):
            self.assertIn(arm, arms)
        self.assertFalse([s["id"] for s in fetch.select(self.doc) if s.get("optional")])
        self.assertIn("drama3", [s["id"] for s in fetch.select(self.doc, include_optional=True)])
        self.assertEqual([s["id"] for s in fetch.select(self.doc, only=["drama3"])], ["drama3"])
        mac = fetch.select(self.doc, arms=["A1-mac"])
        self.assertEqual(sorted(s["id"] for s in mac), ["Ming-3.0-tts", "ming3-0.5b-mlx", "mlx-audio"])

    def test_optional_arms_are_selected_by_name_and_excluded_ids_are_printed(self):
        # The rented arm's runtime is optional like its weights, so the default plan does not print its clone.
        self.assertNotIn("fish-speech", [s["id"] for s in fetch.select(self.doc)])
        self.assertEqual(sorted(s["id"] for s in fetch.select(self.doc, arms=["D3-rented"])), ["drama3", "fish-speech"])
        self.assertEqual(sorted(s["id"] for s in fetch.select(self.doc, arms=["D3-gpu-experimental"])),
                         ["audio.cpp", "drama3-gguf-q3"])
        # An optional source on a non-optional arm (WavLM on scoring) still needs --include-optional.
        self.assertNotIn("wavlm-base-plus-sv", [s["id"] for s in fetch.select(self.doc, arms=["scoring"])])
        with tempfile.TemporaryDirectory() as scratch:
            code, out, err = run(["--dest", str(Path(scratch) / "weights")])
        self.assertEqual(code, 0, err)
        result = json.loads(out)
        self.assertEqual(result["optional_excluded"],
                         sorted(["drama3", "drama3-gguf-q3", "fish-speech", "wavlm-base-plus-sv"]))
        self.assertNotIn("fish-speech", [g["id"] for g in result["git"]])

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
        self.assertIn("inside a checkout of the repository", err)

    @unittest.skipUnless(shutil.which("git"), "git not on PATH")
    def test_destination_inside_another_checkout_is_refused(self):
        with tempfile.TemporaryDirectory() as scratch:
            main, linked = Path(scratch) / "main", Path(scratch) / "linked"
            env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
            for command in (["git", "init", "-q", str(main)],
                            ["git", "-C", str(main), "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                             "-c", "commit.gpgsign=false", "commit", "-q", "--allow-empty", "-m", "init"],
                            ["git", "-C", str(main), "worktree", "add", "-q", str(linked)]):
                subprocess.run(command, check=True, capture_output=True, env=env)
            # From the linked worktree, the main checkout is refused, and the reverse.
            with self.assertRaisesRegex(fetch.FetchError, "inside a checkout"):
                fetch.resolve_dest(str(main / "weights"), root=linked.resolve())
            with self.assertRaisesRegex(fetch.FetchError, "inside a checkout"):
                fetch.resolve_dest(str(linked / "weights"), root=main.resolve())
            self.assertEqual(fetch.resolve_dest(str(Path(scratch) / "weights"), root=main.resolve()),
                             (Path(scratch) / "weights").resolve())

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

        self.local = self.dest / "hf" / "synthetic-tts"

    def tearDown(self):
        self.scratch.cleanup()

    def write_sources(self, weights_sha):
        doc = {"schema_version": 1, "recorded": "2026-10-22", "sources": [
            {"id": "synthetic-tts", "kind": "hf", "arms": ["A1-gpu"], "repo": "synthetic/tts", "revision": REV,
             "licence": "MIT", "optional": False,
             "files": [{"path": "model-q8.gguf", "bytes": len(WEIGHTS), "sha256": weights_sha},
                       {"path": "sub/config.json", "bytes": len(CONFIG), "sha256": None,
                        "git_blob_sha1": git_blob(CONFIG)}]},
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
        self.assertEqual((self.local / "model-q8.gguf").read_bytes(), WEIGHTS)
        self.assertEqual((self.local / "sub" / "config.json").read_bytes(), CONFIG)
        sums = (self.local / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
        self.assertEqual(sums, [f"{hashlib.sha256(WEIGHTS).hexdigest()}  model-q8.gguf",
                                f"{hashlib.sha256(CONFIG).hexdigest()}  sub/config.json"])
        receipt = json.loads((self.dest / "fetch-receipt.json").read_text(encoding="utf-8"))
        checks = {r["path"]: r["check"] for r in receipt["files"]}
        self.assertEqual(checks, {"model-q8.gguf": "matched_declared_sha256",
                                  "sub/config.json": "matched_declared_git_blob_sha1"})
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
                         {"model-q8.gguf": "matched_declared_sha256",
                          "sub/config.json": "matched_declared_git_blob_sha1"})
        # A same-size file whose bytes changed after it was recorded is refused, not re-recorded.
        (self.local / "sub" / "config.json").write_bytes(CONFIG.upper())
        code, _, err = self.apply()
        self.assertEqual(code, 2)
        self.assertIn("git blob sha1", err)

    def test_preplaced_files_are_verified_against_the_declared_hash(self):
        config = self.local / "sub" / "config.json"
        config.parent.mkdir(parents=True)
        # A same-size forgery of a non-LFS file is refused before anything is recorded.
        config.write_bytes(CONFIG.replace(b"true", b"TRUE"))
        code, _, err = self.apply()
        self.assertEqual(code, 2)
        self.assertIn("does not match the declared", err)
        self.assertNotIn(hashlib.sha256(config.read_bytes()).hexdigest(),
                         (self.local / "SHA256SUMS").read_text(encoding="utf-8"))
        self.assertFalse((self.dest / "fetch-receipt.json").exists())
        # A file of another size is refused as such, never overwritten or recorded.
        config.write_bytes(b"fake")
        code, _, err = self.apply()
        self.assertEqual(code, 2)
        self.assertIn("wrong size", err)
        self.assertEqual(config.read_bytes(), b"fake")
        # The genuine bytes placed by hand are accepted as already present, with the declared check named.
        config.write_bytes(CONFIG)
        code, _, err = self.apply()
        self.assertEqual(code, 0, err)
        receipt = json.loads((self.dest / "fetch-receipt.json").read_text(encoding="utf-8"))
        status = {r["path"]: (r["status"], r["check"]) for r in receipt["files"]}
        self.assertEqual(status["sub/config.json"], ("already_present", "matched_declared_git_blob_sha1"))
        # The weights fetched by the first, refused run were verified then and are re-verified now.
        self.assertEqual(status["model-q8.gguf"], ("already_present", "matched_declared_sha256"))

    def test_downloaded_non_lfs_file_must_match_its_git_blob(self):
        (self.mirror / "synthetic" / "tts" / "resolve" / REV / "sub" / "config.json").write_bytes(CONFIG.upper())
        code, _, err = self.apply()
        self.assertEqual(code, 2)
        self.assertIn("git blob sha1", err)
        self.assertFalse((self.local / "sub" / "config.json").exists())
        self.assertFalse(list(self.dest.rglob(".partial-*")))

    def test_symlinked_destination_is_refused(self):
        outside = Path(self.scratch.name) / "elsewhere.gguf"
        outside.write_bytes(WEIGHTS)
        self.local.mkdir(parents=True)
        (self.local / "model-q8.gguf").symlink_to(outside)
        code, _, err = self.apply()
        self.assertEqual(code, 2)
        self.assertIn("symlinked destination", err)

    def test_redirect_away_from_https_is_refused(self):
        class Response(io.BytesIO):
            def geturl(self):
                return "http://mirror.invalid/model-q8.gguf"

        entry = {"path": "model-q8.gguf", "bytes": len(WEIGHTS), "sha256": hashlib.sha256(WEIGHTS).hexdigest()}
        target = self.local / "model-q8.gguf"
        with mock.patch.object(fetch.urllib.request, "urlopen", return_value=Response(WEIGHTS)):
            with self.assertRaisesRegex(fetch.FetchError, "redirected away from https"):
                fetch.download("https://huggingface.co/synthetic/tts/resolve/x/model-q8.gguf", target, entry, 5)
        self.assertFalse(target.exists())
        self.assertFalse(list(self.dest.rglob(".partial-*")))

    def test_source_ids_cannot_collide_with_receipts_or_clones(self):
        doc = json.loads(self.sources.read_text(encoding="utf-8"))
        doc["sources"][0]["id"] = "receipts"
        self.sources.write_text(json.dumps(doc), encoding="utf-8")
        code, _, err = self.apply()
        self.assertEqual(code, 0, err)
        self.assertEqual(sorted(p.suffix for p in (self.dest / "receipts").iterdir()), [".json"])
        self.assertTrue((self.dest / "hf" / "receipts" / "SHA256SUMS").is_file())

    def test_declared_hash_mismatch_leaves_nothing_behind(self):
        self.write_sources("f" * 64)
        code, _, err = self.apply()
        self.assertEqual(code, 2)
        self.assertIn("does not match the declared", err)
        self.assertFalse((self.local / "model-q8.gguf").exists())
        self.assertFalse(list(self.dest.rglob(".partial-*")))

    def test_hashes_measured_before_a_failure_are_kept(self):
        (self.mirror / "synthetic" / "tts" / "resolve" / REV / "sub" / "config.json").unlink()
        self.write_sources(hashlib.sha256(WEIGHTS).hexdigest())
        code, _, _ = self.apply()
        self.assertEqual(code, 2)
        sums = (self.local / "SHA256SUMS").read_text(encoding="utf-8")
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
        cases = (
            (lambda d: d["sources"][0]["files"][0].update(path="../escape.gguf"), "unsafe file path"),
            (lambda d: d["sources"][0].update(revision="main"), "full revision"),
            (lambda d: d["sources"][0].update(revision=["0" * 40]), "full revision"),
            (lambda d: d["sources"][0].update(repo=7), "owner/name"),
            (lambda d: d["sources"][1].update(commit="abc123"), "full commit"),
            (lambda d: d["sources"][1].update(commit=12345), "full commit"),
            (lambda d: d["sources"].append("not-an-object"), "must be an object"),
            (lambda d: d["sources"][0]["files"].append("weights.gguf"), "file entry must be an object"),
            (lambda d: d["sources"][0]["files"][1].pop("sha256"), "sha256 key is required"),
            (lambda d: d["sources"][0]["files"][1].pop("git_blob_sha1"), "unhashed files are refused"),
            (lambda d: d["sources"][0]["files"][1].update(git_blob_sha1="F" * 40), "git_blob_sha1 must be"),
            (lambda d: d["sources"][0]["files"][1].update(path="SHA256SUMS"), "reserved file path"),
            (lambda d: d["sources"][0].update(optional="no"), "optional must be"),
        )
        for mutate, message in cases:
            changed = json.loads(json.dumps(doc))
            mutate(changed)
            self.sources.write_text(json.dumps(changed), encoding="utf-8")
            code, _, err = self.apply()
            self.assertEqual(code, 2)
            self.assertTrue(re.search(message, err), err)


if __name__ == "__main__":
    unittest.main()
