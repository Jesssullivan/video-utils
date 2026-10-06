"""Source-clock, claim and transactional invariants for the separate v2 store."""
import copy
import fcntl
import hashlib
import http.client
import importlib.util
import json
import math
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import annotation_v2 as annotations
spec = importlib.util.spec_from_file_location("review_server_v2_tests", SCRIPTS / "review_server.py")
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


class AnnotationV2Tests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.manifest = {"source": {"sha256": "a" * 64, "path": "private.mov"},
                         "timeline": {"audio_start_seconds": -2, "format_start_seconds": -3},
                         "pcm": {"duration_seconds": 12}}
        self.manifest_path = self.root / "manifest.json"
        self.manifest_path.write_text(json.dumps(self.manifest))
        self.session = review.Session(self.root, open_media=False)
        self.addCleanup(self.session.close)
        self.store = annotations.AnnotationStore(self.session)

    def request(self, revision=0, key="test-request-0001", **fields):
        item = {"kind": "rhythm_timing", "basis": "operator_assertion", "status": "needs_review",
                "source_span": {"start_seconds": 3, "end_seconds": 3, "extent_known": False},
                "reported_by": {"actor": "operator", "via": "agent"}, "operator_certainty": "uncertain",
                "operator_quote": "Known rhythmic issue at 3 seconds?", "note": "Exact intended notes not supplied."}
        item.update(fields)
        return {"schema_version": 2, "expected_revision": revision, "idempotency_key": key,
                "source_sha256": self.session.source_hash, "manifest_sha256": self.session.manifest_hash,
                "annotation": item}

    def bytes(self):
        return self.store.path.read_bytes() if self.store.path.exists() else None

    def refuse_unchanged(self, request, code=None):
        before = self.bytes()
        with self.assertRaises(annotations.AnnotationError) as context:
            self.store.write(request)
        if code:
            self.assertEqual(context.exception.code, code)
        self.assertEqual(self.bytes(), before)
        self.assertEqual(list(self.root.glob(".review-v2-*.json")), [])

    def test_separate_store_v1_is_unchanged_and_no_migration(self):
        v1 = self.session.annotate({"expected_revision": 0, "annotation": {
            "source_start_seconds": 3, "source_end_seconds": 4, "category": "rhythm", "status": "needs_review", "note": "v1 note"}})
        original = self.session.annotations_path.read_bytes()
        self.assertEqual(self.store.read()["annotations"], [])
        saved = self.store.write(self.request())
        self.assertEqual(saved["revision"], 1)
        self.assertEqual(self.session.annotations_path.read_bytes(), original)
        self.assertEqual(self.session.read_annotations(), v1)
        self.assertEqual(self.session.data()["annotations"], v1)

    def test_source_bound_create_edit_and_public_projection(self):
        saved = self.store.write(self.request(operator_certainty="confirmed", status="accepted_observation"))
        item = saved["annotations"][0]
        self.assertEqual(item["claim_label"], "USER REPORTED")
        self.assertEqual(item["musical_verdict"], "not_established")
        self.assertEqual(saved["listening_acceptance"], "not_established")
        self.assertNotIn("replay_receipts", saved)
        self.assertEqual(saved["mutation"]["annotation_id"], item["id"])
        self.assertEqual(item["created_with"]["manifest_sha256"], self.session.manifest_hash)
        edited = self.store.write(self.request(1, "test-request-0002", id=item["id"], note="Review extent", status="dismissed_candidate"))
        new = edited["annotations"][0]
        self.assertEqual(new["created_at"], item["created_at"])
        self.assertEqual(new["id"], item["id"])
        self.assertEqual(edited["revision"], 2)
        public = annotations.AnnotationStore(review.Session(self.root, open_media=False)).read()
        annotations.validate_store(public, public=True, **self.store.bindings())
        self.assertEqual(public["annotations"], edited["annotations"])

    def test_idempotent_replay_after_other_edit_keeps_current_store_and_committed_id(self):
        request = self.request()
        first = self.store.write(request)
        second = self.store.write(self.request(1, "test-request-0002", note="Another observation"))
        before = self.bytes()
        replay = self.store.write(request)
        self.assertEqual(self.bytes(), before)
        self.assertEqual(replay["revision"], second["revision"])
        self.assertEqual(replay["mutation"], {"outcome": "replayed", "annotation_id": first["annotations"][0]["id"], "committed_revision": 1})
        self.assertEqual(len(replay["annotations"]), 2)
        changed = copy.deepcopy(request)
        changed["annotation"]["note"] = "Changed content under same key"
        self.refuse_unchanged(changed, "idempotency_key_conflict")
        changed = copy.deepcopy(request)
        changed["expected_revision"] = 2
        self.refuse_unchanged(changed, "idempotency_key_conflict")

    def test_stale_revision_and_unknown_edit_refuse_without_writes(self):
        self.store.write(self.request())
        self.refuse_unchanged(self.request(0, "different-request-0001"), "stale_annotation_revision")
        self.refuse_unchanged(self.request(1, "different-request-0002", id="11111111-1111-4111-8111-111111111111"), "annotation_not_found")
        request = self.request(1, "different-request-0003")
        request["expected_revision"] = True
        self.refuse_unchanged(request, "invalid_expected_revision")

    def test_cross_source_manifest_and_pinned_manifest_mutation_refuse(self):
        self.store.write(self.request())
        for field, code in (("source_sha256", "annotation_source_mismatch"), ("manifest_sha256", "annotation_manifest_mismatch")):
            request = self.request(1, "different-request-0002")
            request[field] = "b" * 64
            self.refuse_unchanged(request, code)
        self.manifest["profile"] = "changed"
        self.manifest_path.write_text(json.dumps(self.manifest))
        self.refuse_unchanged(self.request(1, "different-request-0003"), "session_manifest_changed_restart_review")
        with self.assertRaisesRegex(annotations.AnnotationError, "session_manifest_changed_restart_review"):
            self.store.read()
        fresh = review.Session(self.root, open_media=False)
        with self.assertRaisesRegex(annotations.AnnotationError, "annotation_manifest_mismatch"):
            annotations.AnnotationStore(fresh).read()

    def test_invalid_nonfinite_bool_reversed_and_out_of_bounds_spans(self):
        self.store.write(self.request())
        invalid = [float("nan"), float("inf"), float("-inf"), True, "3", None, 10**1000, -3.001, 10.001]
        for value in invalid:
            with self.subTest(value=repr(value)[:50]):
                self.refuse_unchanged(self.request(1, "different-request-0002", source_span={"start_seconds": value, "end_seconds": value, "extent_known": False}))
        for span in ({"start_seconds": 4, "end_seconds": 3, "extent_known": True},
                     {"start_seconds": 3, "end_seconds": 4, "extent_known": False},
                     {"start_seconds": 3, "end_seconds": 4, "extent_known": 1},
                     {"start_seconds": 3, "end_seconds": 4, "extent_known": True, "frames": 50}):
            self.refuse_unchanged(self.request(1, "different-request-0002", source_span=span))

    def test_negative_origin_points_and_audio_tail_are_legal_source_seconds(self):
        for index, value in enumerate((-3, -2, 0, 9.999, 10)):
            saved = self.store.write(self.request(index, f"point-request-{index:04d}", source_span={"start_seconds": value, "end_seconds": value, "extent_known": False}))
            found = next(item for item in saved["annotations"] if item["id"] == saved["mutation"]["annotation_id"])
            self.assertEqual(found["source_span"]["start_seconds"], value)
            self.assertFalse(found["source_span"]["extent_known"])

    def test_claim_basis_authorship_and_raw_text_roundtrip(self):
        literal = "<script>odd picking</script> {\\\\pos(0,0)} & ♭\nmy wording  "
        saved = self.store.write(self.request(operator_quote=literal, note=literal))
        self.assertEqual(saved["annotations"][0]["operator_quote"], literal)
        self.assertEqual(saved["annotations"][0]["note"], literal)
        detector = self.request(1, "detector-request-0002", basis="detector_hypothesis", operator_certainty=None,
                                operator_quote=None, reported_by={"actor": "detector", "via": "cli"}, status="accepted_observation")
        saved = self.store.write(detector)
        record = next(item for item in saved["annotations"] if item["id"] == saved["mutation"]["annotation_id"])
        self.assertEqual(record["claim_label"], "REVIEW")
        self.assertEqual(record["musical_verdict"], "not_established")
        for fields in ({"operator_certainty": "confident"}, {"reported_by": {"actor": "agent", "via": "agent"}},
                       {"operator_quote": None}, {"operator_quote": " "}, {"musical_verdict": "confirmed_mistake"},
                       {"status": "detector_confirmed"}, {"kind": "missed_note"}, {"note": "bad\x00text"}):
            self.refuse_unchanged(self.request(2, "invalid-report-0003", **fields))
        invalid = copy.deepcopy(detector)
        invalid["expected_revision"] = 2
        invalid["idempotency_key"] = "invalid-detector-0003"
        invalid["annotation"]["operator_certainty"] = "confirmed"
        self.refuse_unchanged(invalid, "nonoperator_assertion_cannot_claim_operator_certainty")

    def test_reference_and_operator_context_remain_unconfirmed(self):
        fields = {"basis": "reference_comparison", "operator_certainty": None, "operator_quote": None,
                  "reported_by": {"actor": "agent", "via": "agent"}}
        self.refuse_unchanged(self.request(**fields), "reference_comparison_requires_reference_hash")
        saved = self.store.write(self.request(reference_sha256="c" * 64, **fields))
        self.assertEqual(saved["annotations"][0]["claim_label"], "REFERENCE REVIEW")
        saved = self.store.write(self.request(1, "context-request-0002", basis="operator_context", operator_certainty=None, operator_quote=None))
        self.assertEqual(saved["annotations"][1]["musical_verdict"], "not_established")

    def test_closed_request_nested_schema_and_key_boundaries(self):
        bad = self.request()
        bad["extra"] = "ignored?"
        self.refuse_unchanged(bad, "invalid_annotation_request")
        for key in ("short", "a" * 129, "with space", "../path-key", None, 3):
            bad = self.request(key=key)
            self.refuse_unchanged(bad, "invalid_idempotency_key")
        for fields in ({"reported_by": {"actor": "operator", "via": "browser", "token": "x"}}, {"note": "x" * 4001}, {"id": "BAD-ID"}):
            self.refuse_unchanged(self.request(**fields))
        schema = annotations.request_schema()
        self.assertFalse(schema["additionalProperties"])
        self.assertFalse(schema["properties"]["annotation"]["additionalProperties"])
        self.assertEqual(set(schema["required"]), annotations.REQUEST_FIELDS)

    def test_symlink_store_and_foreign_store_are_refused(self):
        outside = self.root / "external.json"
        outside.write_text("{}")
        self.store.path.symlink_to(outside)
        with self.assertRaisesRegex(annotations.AnnotationError, "unsafe_annotation_store"):
            self.store.write(self.request())
        self.assertEqual(outside.read_text(), "{}")
        self.store.path.unlink()
        self.store.write(self.request())
        foreign = json.loads(self.bytes())
        foreign["source_sha256"] = "b" * 64
        self.store.path.write_text(json.dumps(foreign))
        self.refuse_unchanged(self.request(1, "different-request-0002"), "annotation_source_mismatch")

    def test_store_rejects_forged_verdict_provenance_and_replay(self):
        self.store.write(self.request())
        original = json.loads(self.bytes())
        mutations = [lambda x: x["annotations"][0].update(musical_verdict="confirmed"),
                     lambda x: x["annotations"][0].update(claim_label="DETECTOR CONFIRMED"),
                     lambda x: x["annotations"][0]["created_with"].update(manifest_sha256="b" * 64),
                     lambda x: x["replay_receipts"][0].update(annotation_id=[]),
                     lambda x: x.update(replay_receipts=[]),
                     lambda x: x.update(listening_acceptance="accepted"),
                     lambda x: x.update(extra="tampered")]
        for mutate in mutations:
            bad = copy.deepcopy(original)
            mutate(bad)
            self.store.path.write_text(json.dumps(bad))
            with self.assertRaises(annotations.AnnotationError):
                self.store.read()
            self.refuse_unchanged(self.request(1, "different-request-0002"))

    def test_candidate_links_and_changed_artifacts_refuse_stale_write(self):
        markers = self.root / "markers.json"
        markers.write_text(json.dumps({"source_sha256": "a" * 64, "markers": [{"source_time_seconds": 3, "end_seconds": 4, "name": "candidate"}]}))
        session = review.Session(self.root, open_media=False)
        self.addCleanup(session.close)
        store = annotations.AnnotationStore(session)
        request = self.request(candidate_id=session.markers[0]["id"])
        saved = store.write(request)
        self.assertEqual(saved["annotations"][0]["created_with"]["candidate_artifact_sha256"], session.candidate_hash)
        self.store = store
        self.refuse_unchanged(self.request(1, "bad-candidate-0002", candidate_id="b" * 64), "candidate_not_in_current_session")
        markers.write_text(json.dumps({"source_sha256": "a" * 64, "markers": []}))
        self.refuse_unchanged(self.request(1, "changed-candidate-0002"), "session_candidates_changed_restart_review")

    def test_generated_origin_translation_and_span_roundtrips(self):
        rng = random.Random(6182026)
        for index in range(100):
            start = rng.uniform(-3, 9)
            end = rng.uniform(start, 10)
            point = index % 3 == 0
            if point:
                end = start
            item = self.request(source_span={"start_seconds": start, "end_seconds": end, "extent_known": not point})["annotation"]
            annotations.validate_annotation(item, source_min_seconds=-3, source_max_seconds=10)
            offset = rng.uniform(-100, 100)
            shifted = copy.deepcopy(item)
            shifted["source_span"]["start_seconds"] += offset
            shifted["source_span"]["end_seconds"] += offset
            annotations.validate_annotation(shifted, source_min_seconds=-3 + offset, source_max_seconds=10 + offset)
            self.assertAlmostEqual(end - start, shifted["source_span"]["end_seconds"] - shifted["source_span"]["start_seconds"])
            self.assertEqual(json.loads(annotations.canonical(item)), item)

    def test_two_sessions_same_revision_have_one_commit(self):
        other = review.Session(self.root, open_media=False)
        self.addCleanup(other.close)
        stores = [self.store, annotations.AnnotationStore(other)]
        barrier = threading.Barrier(2)
        results = []
        def write(index):
            barrier.wait()
            try:
                results.append(stores[index].write(self.request(key=f"parallel-request-{index:04d}")))
            except annotations.AnnotationError as error:
                results.append(error.code)
        threads = [threading.Thread(target=write, args=(index,)) for index in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(3)
            self.assertFalse(thread.is_alive())
        self.assertEqual(sum(isinstance(result, dict) for result in results), 1)
        self.assertTrue(any(result in ("annotation_store_busy_retry", "stale_annotation_revision") for result in results if isinstance(result, str)))
        self.assertEqual(self.store.read()["revision"], 1)

    def test_busy_process_lock_refuses_and_preserves_store(self):
        fd = os.open(self.root / ".review-annotations-v2.lock", os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.refuse_unchanged(self.request(), "annotation_store_busy_retry")
        finally:
            os.close(fd)

    def test_atomic_prepublication_failure_preserves_store_and_removes_temp(self):
        self.store.write(self.request())
        before = self.bytes()
        with mock.patch.object(annotations.os, "replace", side_effect=OSError("fixture publication failure")):
            with self.assertRaises(OSError):
                self.store.write(self.request(1, "next-request-0002"))
        self.assertEqual(self.bytes(), before)
        self.assertEqual(list(self.root.glob(".review-v2-*.json")), [])

    def test_limits_do_not_evict_idempotency_or_records(self):
        with mock.patch.object(annotations, "MAX_ANNOTATIONS", 1):
            self.store.write(self.request())
            self.refuse_unchanged(self.request(1, "limited-request-0002"), "annotation_limit_reached")
        item_id = self.store.read()["annotations"][0]["id"]
        with mock.patch.object(annotations, "MAX_REPLAY_RECEIPTS", 1):
            self.refuse_unchanged(self.request(1, "limited-request-0002", id=item_id), "annotation_replay_limit_reached")
            before = self.bytes()
            self.store.write(self.request())
            self.assertEqual(self.bytes(), before)
        with mock.patch.object(annotations, "MAX_STORE_BYTES", len(self.bytes())):
            self.refuse_unchanged(self.request(1, "size-request-0002", id=item_id, note="x" * 4000), "annotation_store_size_limit")

    def test_bounded_utf8_duplicate_keys_and_invalid_json(self):
        self.refuse_unchanged(self.request(note="🎸" * 4000, operator_quote="🎸" * 4000), "annotation_request_too_large_or_empty")
        request = self.root / "request.json"
        request.write_text('{"schema_version":2,"schema_version":1}')
        with self.assertRaisesRegex(annotations.AnnotationError, "duplicate_json_key"):
            annotations.read_json(request, annotations.MAX_REQUEST_BYTES)
        request.write_text('{"time":NaN}')
        with self.assertRaisesRegex(annotations.AnnotationError, "nonfinite_json_number"):
            annotations.read_json(request, annotations.MAX_REQUEST_BYTES)
        request.write_bytes(b"x" * (annotations.MAX_REQUEST_BYTES + 1))
        with self.assertRaisesRegex(annotations.AnnotationError, "annotation_file_size_limit"):
            annotations.read_json(request, annotations.MAX_REQUEST_BYTES)

    def server(self):
        server = review.ReviewHTTPServer(self.session, 0)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
        thread.start()
        def close():
            server.shutdown()
            server.server_close()
            thread.join(2)
        self.addCleanup(close)
        return server

    def http(self, server, method, path, payload=None, extra=None):
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
        headers = {"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{server.server_port}", "X-Review-Token": self.session.token}
        headers.update(extra or {})
        try:
            connection.request(method, path, body=json.dumps(payload) if isinstance(payload, dict) else payload, headers=headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_actual_loopback_route_source_save_replay_read_and_auth_refusals(self):
        server = self.server()
        status, value = self.http(server, "GET", "/api/annotations-v2")
        self.assertEqual((status, value["revision"]), (200, 0))
        request = self.request()
        status, saved = self.http(server, "POST", "/api/annotations-v2", request)
        self.assertEqual((status, saved["revision"]), (200, 1))
        before = self.bytes()
        status, replay = self.http(server, "POST", "/api/annotations-v2", request)
        self.assertEqual((status, replay["mutation"]["outcome"]), (200, "replayed"))
        self.assertEqual(self.bytes(), before)
        status, read = self.http(server, "GET", "/api/annotations-v2")
        self.assertEqual(read["annotations"], saved["annotations"])
        for headers in ({"X-Review-Token": "wrong"}, {"Origin": "https://evil.example"}, {"Host": "evil.example"}):
            self.assertEqual(self.http(server, "POST", "/api/annotations-v2", self.request(1, "other-request-0002"), headers)[0], 403)
            self.assertEqual(self.bytes(), before)
        self.assertEqual(self.http(server, "POST", "/api/annotations-v2", self.request(key="stale-request-0002")), (409, {"error": "stale_annotation_revision"}))
        self.assertEqual(self.http(server, "POST", "/api/annotations-v2", '{"a":1,"a":2}'), (400, {"error": "duplicate_json_key"}))
        self.assertEqual(self.http(server, "POST", "/api/annotations-v2", '{"a":NaN}'), (400, {"error": "nonfinite_json_number"}))
        status, refusal = self.http(server, "POST", "/api/annotations-v2", "[" * 7000 + "0" + "]" * 7000)
        self.assertEqual(status, 400)
        self.assertIn(refusal["error"], ("invalid_json_request", "invalid_annotation_request"))
        self.assertEqual(self.bytes(), before)
        self.assertEqual(self.http(server, "GET", "/api/annotations")[1]["schema_version"], 1)

    def test_fifo_read_is_bounded_before_regular_file_validation(self):
        path = self.root / "request.fifo"
        os.mkfifo(path)
        command = [sys.executable, "-c", "import sys;sys.path.insert(0,sys.argv[1]);import annotation_v2;annotation_v2.read_json(sys.argv[2],20000)", str(SCRIPTS), str(path)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=2)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unsafe_annotation_file", result.stderr)
        self.store.path = path
        before = path.stat().st_mode
        with self.assertRaisesRegex(annotations.AnnotationError, "unsafe_annotation_file"):
            self.store.load()
        self.assertEqual(path.stat().st_mode, before)

    def test_changed_provenance_oversize_and_fifo_are_bounded_refusals(self):
        self.store.write(self.request())
        before = self.bytes()
        with mock.patch.object(annotations, "MAX_PROVENANCE_BYTES", 1):
            with self.assertRaisesRegex(annotations.AnnotationError, "unsafe_provenance_file"):
                self.store.write(self.request(1, "oversize-request-0002"))
        self.assertEqual(self.bytes(), before)
        self.manifest_path.unlink()
        os.mkfifo(self.manifest_path)
        with self.assertRaisesRegex(annotations.AnnotationError, "session_manifest_changed_restart_review"):
            self.store.read()
        self.assertEqual(self.bytes(), before)

    def test_v2_pre_session_oversize_metadata_and_fifo_reject_without_legacy_loader(self):
        for name in ("manifest.json", "analysis.json", "dag.json", "flags.json", "markers.json"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "manifest.json").write_text(json.dumps(self.manifest))
                path = root / name
                with path.open("wb") as stream:
                    stream.truncate(annotations.MAX_PROVENANCE_BYTES + 1)
                with mock.patch.object(review.report, "load_json", side_effect=AssertionError("legacy unbounded loader invoked")):
                    with self.assertRaisesRegex(annotations.AnnotationError, "session_hash_byte_limit"):
                        review.Session(root, open_media=False, bounded_metadata=True)
                path.unlink()
                os.mkfifo(path)
                with mock.patch.object(review.report, "load_json", side_effect=AssertionError("legacy unbounded loader invoked")):
                    with self.assertRaisesRegex(annotations.AnnotationError, "unsafe_session_artifact"):
                        review.Session(root, open_media=False, bounded_metadata=True)

    def test_bounded_dependency_injection_preserves_legacy_candidate_semantics(self):
        markers = self.root / "markers.json"
        markers.write_text(json.dumps({"source_sha256": "a" * 64, "markers": [{"source_time_seconds": 3, "end_seconds": 4, "name": "candidate"}]}))
        baseline = review.Session(self.root, open_media=False)
        bounded = review.Session(self.root, open_media=False, bounded_metadata=True)
        self.addCleanup(baseline.close)
        self.addCleanup(bounded.close)
        self.assertEqual(baseline.markers, bounded.markers)
        self.assertEqual(baseline.auxiliary_status, bounded.auxiliary_status)
        self.assertEqual(baseline.candidate_hash, bounded.candidate_hash)
        self.assertEqual(baseline.manifest_hash, bounded.manifest_hash)
        self.assertEqual(baseline.analysis_status, bounded.analysis_status)
        self.assertEqual(bounded.metadata_access.metadata_bytes, self.manifest_path.stat().st_size + markers.stat().st_size)
        before = bounded.manifest["source"]["sha256"]
        self.manifest_path.write_text(json.dumps({**self.manifest, "source": {"sha256": "b" * 64}}))
        self.assertEqual(bounded.manifest["source"]["sha256"], before)
        with self.assertRaisesRegex(annotations.AnnotationError, "session_manifest_changed_restart_review"):
            annotations.AnnotationStore(bounded).write(self.request())

    def test_large_raw_lineage_hash_has_separate_budget_and_changed_snapshot_refuses(self):
        raw = self.root / "cleaned.wav"
        with raw.open("wb") as stream:
            stream.truncate(annotations.MAX_PROVENANCE_BYTES + 1)
        raw_sha = annotations.hash_provenance(raw, max_bytes=annotations.MAX_SESSION_HASH_BYTES)
        self.manifest["output_sha256"] = {"cleaned.wav": raw_sha}
        self.manifest_path.write_text(json.dumps(self.manifest))
        (self.root / "analysis.json").write_text(json.dumps({"source": {"sha256": raw_sha}}))
        bounded = review.Session(self.root, open_media=False, bounded_metadata=True)
        self.addCleanup(bounded.close)
        self.assertEqual(bounded.analysis_status, "verified_run_derivative_hash_bound")
        self.assertGreater(bounded.metadata_access.hash_bytes, annotations.MAX_PROVENANCE_BYTES)
        self.assertLess(bounded.metadata_access.metadata_bytes, annotations.MAX_PROVENANCE_BYTES)
        request = self.request()
        request["manifest_sha256"] = bounded.manifest_hash
        store = annotations.AnnotationStore(bounded)
        store.write(request)
        before = store.path.read_bytes()
        with raw.open("r+b") as stream:
            stream.write(b"changed")
        request["expected_revision"] = 1
        request["idempotency_key"] = "changed-lineage-0002"
        with self.assertRaisesRegex(annotations.AnnotationError, "session_selected_artifact_changed_restart_review"):
            store.write(request)
        self.assertEqual(store.path.read_bytes(), before)

    def test_session_aggregate_metadata_hash_count_budgets_refuse(self):
        with mock.patch.object(annotations, "MAX_METADATA_TOTAL_BYTES", 10):
            with self.assertRaisesRegex(annotations.AnnotationError, "session_metadata_byte_limit"):
                review.Session(self.root, open_media=False, bounded_metadata=True)
        with mock.patch.object(annotations, "MAX_SESSION_HASH_BYTES", 10):
            with self.assertRaisesRegex(annotations.AnnotationError, "session_hash_byte_limit"):
                review.Session(self.root, open_media=False, bounded_metadata=True)
        (self.root / "analysis.json").write_text("{}")
        with mock.patch.object(annotations, "MAX_SESSION_FILES", 1):
            with self.assertRaisesRegex(annotations.AnnotationError, "session_artifact_count_limit"):
                review.Session(self.root, open_media=False, bounded_metadata=True)

    def test_corrupt_or_deep_json_store_is_stable_http_refusal(self):
        server = self.server()
        for body in (b"{", b"\xff", ("[" * 7000 + "0" + "]" * 7000).encode()):
            self.store.path.write_bytes(body)
            status, refusal = self.http(server, "GET", "/api/annotations-v2")
            self.assertEqual(status, 400)
            self.assertEqual(refusal, {"error": "invalid_annotation_store"})
            self.assertEqual(self.store.path.read_bytes(), body)

    def test_unknown_explicit_source_origins_refuse_all_v2_access_preserving_v1(self):
        original = copy.deepcopy(self.session.manifest)
        variants = [{key: value for key, value in original.items() if key != "timeline"},
                    {**original, "timeline": {"audio_start_seconds": -2}},
                    {**original, "timeline": {"format_start_seconds": -3}}]
        for field in ("audio_start_seconds", "format_start_seconds"):
            for value in (None, True, "0", float("nan"), float("inf")):
                altered = copy.deepcopy(original)
                altered["timeline"][field] = value
                variants.append(altered)
        for altered in variants:
            with self.subTest(timeline=altered.get("timeline")):
                self.session.manifest = altered
                with self.assertRaisesRegex(annotations.AnnotationError, "annotation_source_clock_unknown"):
                    annotations.AnnotationStore(self.session)
                with self.assertRaisesRegex(review.ReviewError, "annotation_source_clock_unknown"):
                    self.session.read_annotations_v2()
                with self.assertRaisesRegex(review.ReviewError, "annotation_source_clock_unknown"):
                    self.session.annotate_v2(self.request())
                self.assertFalse(self.store.path.exists())
        self.session.manifest = original
        legacy = {"source": {"sha256": "a" * 64}, "pcm": {"duration_seconds": 10}}
        self.manifest_path.write_text(json.dumps(legacy))
        session = review.Session(self.root, open_media=False)
        self.addCleanup(session.close)
        self.assertEqual(session.source_min, 0)
        self.assertEqual(session.read_annotations()["schema_version"], 1)
        with self.assertRaisesRegex(review.ReviewError, "annotation_source_clock_unknown"):
            session.read_annotations_v2()
        request = self.request()
        request["manifest_sha256"] = session.manifest_hash
        path = self.root / "unknown-clock-request.json"
        path.write_text(json.dumps(request))
        for arguments in (["read", str(self.root)], ["write", str(self.root), "--input", str(path)]):
            result = subprocess.run([sys.executable, str(SCRIPTS / "annotation_v2.py"), *arguments], capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(json.loads(result.stderr), {"error": "annotation_source_clock_unknown"})
            self.assertFalse(self.store.path.exists())
        server = review.ReviewHTTPServer(session, 0)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
        thread.start()
        try:
            self.assertEqual(self.http(server, "GET", "/api/annotations-v2"), (409, {"error": "annotation_source_clock_unknown"}))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)

    def test_duration_requires_finite_declared_or_positive_native_integer_ratio(self):
        original = copy.deepcopy(self.session.manifest)
        for pcm in ({}, {"duration_seconds": None}, {"duration_seconds": True}, {"duration_seconds": float("nan")},
                    {"sample_count": True, "sample_rate": 44100}, {"sample_count": 441000, "sample_rate": False},
                    {"sample_count": 0, "sample_rate": 44100}):
            self.session.manifest = {**original, "pcm": pcm}
            with self.assertRaisesRegex(annotations.AnnotationError, "annotation_source_clock_unknown"):
                annotations.AnnotationStore(self.session)
        self.session.manifest = {**original, "pcm": {"sample_count": 529200, "sample_rate": 44100}}
        store = annotations.AnnotationStore(self.session)
        self.assertEqual(store.read()["revision"], 0)
        self.session.manifest = original

    def test_actual_cli_save_replay_and_missing_input_refuse(self):
        payload = self.root / "request.json"
        payload.write_text(json.dumps(self.request()))
        command = [sys.executable, str(SCRIPTS / "annotation_v2.py")]
        saved = subprocess.run(command + ["write", str(self.root), "--input", str(payload)], capture_output=True, text=True, timeout=5)
        self.assertEqual(saved.returncode, 0, saved.stderr)
        self.assertEqual(json.loads(saved.stdout)["status"], "annotations_v2_saved")
        replay = subprocess.run(command + ["write", str(self.root), "--input", str(payload)], capture_output=True, text=True, timeout=5)
        self.assertEqual(json.loads(replay.stdout)["mutation"]["outcome"], "replayed")
        read = subprocess.run(command + ["read", str(self.root)], capture_output=True, text=True, timeout=5)
        self.assertEqual(json.loads(read.stdout)["count"], 1)
        invalid = subprocess.run(command + ["write", str(self.root)], capture_output=True, text=True, timeout=5)
        self.assertEqual(invalid.returncode, 2)


if __name__ == "__main__":
    unittest.main()
