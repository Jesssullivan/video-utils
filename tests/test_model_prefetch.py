import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import model_prefetch  # noqa: E402

WHISPER = "ggerganov-whisper-cpp-ggml-small.en"


class PrefetchTests(unittest.TestCase):
    def registry(self, root, **extra):
        entry = {"url": "https://example.invalid/model.bin", "sha256": "0" * 64, "max_bytes": 10, **extra}
        path = Path(root) / "models.json"
        path.write_text(json.dumps({"schema_version": 1, "models": {"m": entry}}))
        return path

    def test_whisper_model_is_registered_hash_bound_at_a_pinned_revision(self):
        entry = json.loads((ROOT / "program/models.json").read_text())["models"][WHISPER]
        self.assertEqual(entry["sha256"], "c6138d6d58ecc8322097e0f987c32f1be8bb0a18532a3f88f734d1bbf9c41e5d")
        self.assertEqual(entry["max_bytes"], 487614201)
        self.assertIn("/resolve/" + entry["source_commit"] + "/", entry["url"])
        self.assertEqual(entry["download_timeout_seconds"], 1800)

    def test_download_timeout_outside_bounds_is_refused_before_any_network(self):
        for bad in (0, 1801, True, "60", 1.5):
            with tempfile.TemporaryDirectory() as root, mock.patch.object(model_prefetch, "REGISTRY", self.registry(root, download_timeout_seconds=bad)), \
                    mock.patch.object(model_prefetch, "ROOT", Path(root)), mock.patch("urllib.request.urlopen") as urlopen:
                with self.assertRaisesRegex(ValueError, "download_timeout_seconds"):
                    model_prefetch.prefetch("m")
                urlopen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
