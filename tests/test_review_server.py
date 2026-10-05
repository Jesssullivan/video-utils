import fcntl
import http.client
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest


SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("review_server", SCRIPTS / "review_server.py")
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.media = b"synthetic-media-fixture-0123456789"
        (self.root / "baseline.wav").write_bytes(self.media)
        (self.root / "cleaned.wav").write_bytes(self.media)
        self.manifest = {"source": {"path": "/Users/jess/Documents/<take>.mov", "sha256": "a" * 64}, "timeline": {"audio_start_seconds": 2, "format_start_seconds": 1}, "pcm": {"duration_seconds": 10}, "outputs": {"baseline": "baseline.wav", "cleaned": "cleaned.wav"}, "output_sha256": {name: review.report.sha256(self.root / name) for name in ("baseline.wav", "cleaned.wav")}}
        self.write("manifest", self.manifest)
        self.write("markers", {"source_sha256": "a" * 64, "markers": [{"source_time_seconds": 3, "end_seconds": 4, "name": "phrase_<candidate>", "confidence": "heuristic_not_probability", "status": "needs_review"}]})

    def write(self, name, value):
        (self.root / f"{name}.json").write_text(json.dumps(value), encoding="utf-8")

    def session(self, media=False):
        session = review.Session(self.root, open_media=media)
        self.addCleanup(session.close)
        return session

    def request(self, revision=0, **fields):
        item = {"source_start_seconds": 3, "source_end_seconds": 4, "category": "phrase", "status": "needs_review", "note": "Review the tail and articulation."}
        item.update(fields)
        return {"expected_revision": revision, "annotation": item}

    def server(self):
        session = self.session(media=True)
        server = review.ReviewHTTPServer(session, 0)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
        thread.start()
        def close():
            server.shutdown()
            server.server_close()
            thread.join(2)
        self.addCleanup(close)
        return server, session

    def http(self, server, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_annotations_persist_and_update_with_source_receipts(self):
        session = self.session()
        saved = session.annotate(self.request(candidate_id=session.markers[0]["id"]))
        self.assertEqual(saved["revision"], 1)
        note = saved["annotations"][0]
        self.assertEqual(note["created_with"]["manifest_sha256"], session.manifest_hash)
        self.assertEqual(note["created_with"]["candidate_artifact_sha256"], session.candidate_hash)
        self.assertTrue(note["created_at"].endswith("+00:00"))
        self.assertEqual(self.session().read_annotations()["annotations"], saved["annotations"])
        update = session.annotate(self.request(1, id=note["id"], note="Observed an uncertain phrase boundary.", status="accepted_observation"))
        self.assertEqual(update["revision"], 2)
        self.assertEqual(update["annotations"][0]["created_at"], note["created_at"])
        self.assertEqual(update["annotations"][0]["id"], note["id"])
        self.assertEqual(update["listening_acceptance"], "not_established")
        self.assertEqual(list(self.root.glob(".review-*.json")), [])

    def test_stale_revisions_manifest_and_candidate_changes_reject(self):
        session = self.session()
        session.annotate(self.request())
        with self.assertRaisesRegex(review.ReviewError, "stale_annotation_revision"):
            session.annotate(self.request())
        self.write("markers", {"source_sha256": "a" * 64, "markers": []})
        with self.assertRaisesRegex(review.ReviewError, "session_candidates_changed"):
            session.annotate(self.request(1))
        fresh = self.session()
        self.manifest["profile"] = {"name": "changed"}
        self.write("manifest", self.manifest)
        with self.assertRaisesRegex(review.ReviewError, "session_manifest_changed"):
            fresh.annotate(self.request(1))

    def test_invalid_spans_types_and_foreign_store_rejected(self):
        session = self.session()
        for fields in ({"source_start_seconds": float("nan")}, {"source_start_seconds": True}, {"source_start_seconds": "3"}, {"source_end_seconds": 2}, {"source_end_seconds": 20}, {"status": "master_approved"}, {"note": " "}, {"note": "x" * 4001}, {"candidate_id": "unrelated"}):
            with self.subTest(fields=fields):
                with self.assertRaises(review.ReviewError):
                    session.annotate(self.request(**fields))
        with self.assertRaisesRegex(review.ReviewError, "stale_annotation_revision"):
            session.annotate(self.request(True))
        self.write("review-annotations", {"schema_version": 1, "source_sha256": "b" * 64, "revision": 0, "annotations": []})
        with self.assertRaisesRegex(review.ReviewError, "annotation_source_mismatch"):
            session.read_annotations()

    def test_cross_process_lock_refuses_busy_store(self):
        session = self.session()
        fd = review.os.open(self.root / ".review-annotations.lock", review.os.O_CREAT | review.os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(review.ReviewError, "annotation_store_busy_retry"):
                session.annotate(self.request())
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            review.os.close(fd)

    def test_foreign_markers_and_modified_media_are_omitted(self):
        self.write("markers", {"source_sha256": "b" * 64, "markers": [{"source_time_seconds": 3, "name": "foreign"}]})
        (self.root / "cleaned.wav").write_bytes(b"modified")
        session = self.session(media=True)
        self.assertEqual(session.markers, [])
        self.assertNotIn("clean", session.media)
        self.assertIn("original", session.media)
        serialized = json.dumps(session.data())
        self.assertNotIn("/Users/jess/Documents", serialized)
        self.assertNotIn(str(self.root), serialized)

    def test_media_ranges_head_and_traversal_routes(self):
        server, _ = self.server()
        self.assertEqual(server.server_address[0], "127.0.0.1")
        status, headers, body = self.http(server, "GET", "/media/original", headers={"Range": "bytes=3-8"})
        self.assertEqual(status, 206)
        self.assertEqual(body, self.media[3:9])
        self.assertEqual(headers["Content-Range"], f"bytes 3-8/{len(self.media)}")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        status, _, body = self.http(server, "GET", "/media/original", headers={"Range": "bytes=-4"})
        self.assertEqual(body, self.media[-4:])
        self.assertEqual(status, 206)
        status, headers, body = self.http(server, "HEAD", "/media/original")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"")
        self.assertEqual(int(headers["Content-Length"]), len(self.media))
        self.assertEqual(self.http(server, "GET", "/media/original", headers={"Range": "bytes=999-"})[0], 416)
        self.assertEqual(self.http(server, "GET", "/media/original", headers={"Range": "bytes=" + "9" * 100 + "-"})[0], 416)
        for path in ("/manifest.json", "/media/../manifest.json", "/%2e%2e/AGENTS.md", "/media/original%2f..%2fmanifest.json", "/Users/jess/Documents/take.mov"):
            self.assertEqual(self.http(server, "GET", path)[0], 404)

    def test_host_origin_token_and_request_size_checks(self):
        server, session = self.server()
        self.assertEqual(self.http(server, "GET", "/api/session", headers={"Host": "evil.example"})[0], 403)
        self.assertEqual(self.http(server, "GET", "/api/session", headers={"Origin": "https://evil.example"})[0], 403)
        body = json.dumps(self.request())
        origin = f"http://127.0.0.1:{server.server_port}"
        headers = {"Content-Type": "application/json", "Origin": origin, "X-Review-Token": session.token}
        missing = {"Content-Type": "application/json", "Origin": origin}
        self.assertEqual(self.http(server, "POST", "/api/annotations", body, missing)[0], 403)
        self.assertEqual(self.http(server, "POST", "/api/annotations", body, {**headers, "X-Review-Token": "ÿ"})[0], 403)
        self.assertEqual(self.http(server, "POST", "/api/annotations", body, {**headers, "Origin": "https://evil.example"})[0], 403)
        status, _, saved = self.http(server, "POST", "/api/annotations", body, headers)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(saved)["revision"], 1)
        self.assertEqual(self.http(server, "POST", "/api/annotations", body, headers)[0], 409)
        self.assertEqual(self.http(server, "POST", "/api/annotations", "x" * (review.MAX_BODY + 1), headers)[0], 413)
        self.assertEqual(self.http(server, "POST", "/api/annotations", "{", headers)[0], 400)

    def test_symlink_store_and_escaping_media_are_rejected(self):
        with tempfile.TemporaryDirectory() as outside:
            external = Path(outside) / "external.wav"
            external.write_bytes(self.media)
            (self.root / "baseline.wav").unlink()
            (self.root / "baseline.wav").symlink_to(external)
            session = self.session(media=True)
            self.assertNotIn("original", session.media)
            store = self.root / "review-annotations.json"
            store.symlink_to(Path(outside) / "annotations.json")
            with self.assertRaisesRegex(review.ReviewError, "unsafe_annotation_store"):
                session.annotate(self.request())

    def test_cli_reads_writes_and_preserves_manual_text(self):
        payload = self.root / "request.json"
        request = self.request(note="<script>local note</script> & uncertain")
        payload.write_text(json.dumps(request))
        command = [sys.executable, str(SCRIPTS / "review_server.py")]
        result = subprocess.run(command + ["annotate", str(self.root), "--input", str(payload)], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        saved = json.loads(result.stdout)
        self.assertEqual(saved["status"], "annotations_saved")
        self.assertEqual(saved["annotations"][0]["note"], request["annotation"]["note"])
        result = subprocess.run(command + ["annotations", str(self.root)], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["count"], 1)

    def test_browser_assets_use_text_nodes_and_no_remote_dependencies(self):
        javascript = (review.ASSETS / "app.js").read_text()
        markup = (review.ASSETS / "index.html").read_text()
        self.assertNotIn("innerHTML", javascript)
        self.assertNotIn(".play()", javascript)
        self.assertNotIn("autoplay", markup)
        self.assertNotIn("https://", javascript + markup)
        self.assertIn("textContent", javascript)

    def test_video_export_receipt_and_in_place_changes(self):
        export = self.root / "export"
        export.mkdir()
        video = export / "cleaned-video.mov"
        video.write_bytes(b"video-fixture")
        (export / "outcome.json").write_text(json.dumps({"source_sha256": "a" * 64, "video": str(video), "output_sha256": {video.name: review.report.sha256(video)}}))
        server, session = self.server()
        self.assertIn("video", session.media)
        status, headers, body = self.http(server, "GET", "/media/video", headers={"Range": "bytes=0-4"})
        self.assertEqual(status, 206)
        self.assertEqual(body, b"video")
        self.assertTrue(headers["Content-Type"].startswith("video/"))
        video.write_bytes(b"modified-video")
        self.assertEqual(self.http(server, "GET", "/media/video")[0], 409)

    def test_metadata_symlink_outside_run_rejected(self):
        with tempfile.TemporaryDirectory() as outside:
            external = Path(outside) / "markers.json"
            external.write_text(json.dumps({"source_sha256": "a" * 64, "markers": []}))
            (self.root / "markers.json").unlink()
            (self.root / "markers.json").symlink_to(external)
            with self.assertRaisesRegex(review.ReviewError, "metadata_outside_run_rejected"):
                self.session()


if __name__ == "__main__":
    unittest.main()
