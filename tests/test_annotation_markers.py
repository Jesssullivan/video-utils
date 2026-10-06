"""Synthetic v2-store projections into generic markers; metadata only, no media."""
import csv
import hashlib
import io
import json
from pathlib import Path
import random
import sys
import tempfile
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import annotation_markers as projection  # noqa: E402
import annotation_v2  # noqa: E402
import markers  # noqa: E402

SOURCE = hashlib.sha256(b"synthetic-annot-corpus-source").hexdigest()
REFERENCE = hashlib.sha256(b"synthetic-reference").hexdigest()
NAMESPACE = uuid.UUID("5d0c1f7a-6b8e-4c2d-9a31-20261006a0c5")
ACTORS = {"operator_assertion": "operator", "operator_context": "operator",
          "detector_hypothesis": "detector", "reference_comparison": "agent"}
REAL_RUN = "artifacts/experiments/s1-demo-context-20261006T0627"
REAL_STORE_SHA = "17041cb31476f91409e3c48f6434fcde8874ecd175a221b0f3fe644614d40eca"
REAL_MANIFEST_SHA = "61c9b3930c36d050818901138eb1820d5dc940e3603d38f019bde793da750a5f"


def artifact_base(relative):
    """Repository root holding a gitignored artifact (the main checkout from a worktree)."""
    for base in (ROOT, *ROOT.parents[:4]):
        if (base / relative).is_file():
            return base
    return None


def spec(name, kind="rhythm_timing", basis="operator_assertion", status="accepted_observation",
         start=1.0, end=2.0, extent=True, quote="the second riff felt late"):
    return {"name": name, "kind": kind, "basis": basis, "status": status, "start": start,
            "end": end if extent else start, "extent": extent, "quote": quote}


def stored(item, manifest_sha):
    basis = item["basis"]
    assertion = basis == "operator_assertion"
    stamp = "2026-10-06T06:00:00.000000+00:00"
    receipt = {"manifest_sha256": manifest_sha, "candidate_artifact_sha256": None}
    return {"kind": item["kind"], "basis": basis, "status": item["status"],
            "source_span": {"start_seconds": item["start"], "end_seconds": item["end"],
                            "extent_known": item["extent"]},
            "reported_by": {"actor": ACTORS[basis], "via": "cli"},
            "operator_certainty": "uncertain" if assertion else None,
            "operator_quote": item["quote"] if assertion else None,
            "note": "Synthetic fixture note for " + item["name"] + "; no listening occurred.",
            "id": str(uuid.uuid5(NAMESPACE, item["name"])), "candidate_id": None,
            "reference_sha256": REFERENCE if basis == "reference_comparison" else None,
            "created_at": stamp, "updated_at": stamp, "created_with": receipt, "updated_with": receipt,
            "claim_label": annotation_v2.LABELS[basis], "musical_verdict": "not_established"}


def write_run(directory, items, *, source=SOURCE, audio_start=0.0, format_start=0.0, duration=60.0,
              public=False, extra_manifest=None):
    """Write manifest.json + review-annotations-v2.json; return (manifest_sha, store_sha)."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    manifest = {"source": {"sha256": source},
                "timeline": {"audio_start_seconds": audio_start, "format_start_seconds": format_start,
                             "axis": "original_source_stream_timestamps_seconds"},
                "pcm": {"duration_seconds": duration}, **(extra_manifest or {})}
    raw = (json.dumps(manifest, sort_keys=True) + "\n").encode()
    (directory / "manifest.json").write_bytes(raw)
    manifest_sha = hashlib.sha256(raw).hexdigest()
    records = [stored(item, manifest_sha) for item in items]
    store = {"schema_version": 2, "source_sha256": source, "manifest_sha256": manifest_sha,
             "revision": len(records), "annotations": records, "listening_acceptance": "not_established"}
    if not public:
        store["replay_receipts"] = [{"key": f"fixture-key-{index:04d}", "request_sha256": hashlib.sha256(
            str(index).encode()).hexdigest(), "annotation_id": record["id"], "committed_revision": index + 1}
            for index, record in enumerate(records)]
    data = (json.dumps(store, indent=2, ensure_ascii=False) + "\n").encode()
    (directory / "review-annotations-v2.json").write_bytes(data)
    return manifest_sha, hashlib.sha256(data).hexdigest()


class AnnotationMarkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.run = self.base / "run"

    def project(self, items, include_text=False, **kwargs):
        _, store_sha = write_run(self.run, items, **kwargs)
        return projection.project(self.run, expected_store_sha256=store_sha, include_text=include_text)

    def refuse(self, code, store_sha=None):
        with self.assertRaises(projection.ProjectionError) as caught:
            projection.project(self.run, expected_store_sha256=store_sha or hashlib.sha256(
                (self.run / "review-annotations-v2.json").read_bytes()).hexdigest())
        self.assertEqual(caught.exception.code, code)

    def test_csv_header_and_row_columns(self):
        payload, text = self.project([spec("a"), spec("b", basis="operator_context", quote=None, start=3, end=5)])
        reader = csv.reader(io.StringIO(text))
        header = next(reader)
        self.assertEqual(header, markers.COLUMNS + ["basis_label"])
        self.assertEqual(len(list(reader)), payload["counts"]["visible_count"])
        extras = {"basis_label", "display_label", "label_basis", "annotation_id", "kind", "basis",
                  "review_state", "extent_known", "musical_verdict", "performance_issue_confirmed"}
        for row in payload["markers"]:
            self.assertEqual(set(row), set(markers.COLUMNS) | extras)
            self.assertEqual(row["name"], row["kind"])
            self.assertEqual(row["status"], row["review_state"])
            self.assertEqual(row["musical_verdict"], "not_established")
            self.assertIs(row["performance_issue_confirmed"], False)
        self.assertEqual(payload["schema_id"], "video-utils.annotation-markers.s2")
        self.assertEqual(payload["timeline"]["axis"], "original_source_stream_timestamps_seconds")
        self.assertEqual((payload["picture_coverage"], payload["editor_import"], payload["listening_acceptance"]),
                         ("not_evaluated", "not_validated", "not_established"))

    def test_basis_label_confidence_and_display_per_basis(self):
        items = [spec(basis, basis=basis, start=index * 10.0, end=index * 10.0 + 1,
                      quote="literal words" if basis == "operator_assertion" else None)
                 for index, basis in enumerate(sorted(annotation_v2.BASES))]
        payload, _ = self.project(items)
        self.assertEqual(payload["counts"]["visible_count"], 4)
        for row in payload["markers"]:
            self.assertEqual(row["basis_label"], annotation_v2.LABELS[row["basis"]])
            self.assertEqual(row["display_label"], annotation_v2.LABELS[row["basis"]] + ": " + row["kind"])
            self.assertEqual(row["label_basis"], row["basis"])
            expected = ("not_applicable_human_annotation" if row["basis"] in ("operator_assertion", "operator_context")
                        else "unknown_uncalibrated")
            self.assertEqual(row["confidence"], expected)
            self.assertEqual(row["evidence"]["claim_label"], row["basis_label"])

    def test_stale_store_hash_refuses_and_cli_writes_nothing(self):
        write_run(self.run, [spec("a")])
        self.refuse("stale_annotation_store", store_sha="0" * 64)
        output = self.base / "out"
        code = projection.main([str(self.run), "--store-sha256", "0" * 64, "--output-dir", str(output)])
        self.assertEqual(code, 1)
        self.assertFalse(output.exists())

    def test_manifest_mismatch_and_timeline_refusals(self):
        write_run(self.run, [spec("a")])
        manifest = json.loads((self.run / "manifest.json").read_text())
        manifest["note"] = "changed after the store was written"
        (self.run / "manifest.json").write_text(json.dumps(manifest))
        self.refuse("annotation_manifest_mismatch")
        write_run(self.run, [spec("a")], source="f" * 64)
        manifest = json.loads((self.run / "manifest.json").read_text())
        manifest["source"]["sha256"] = SOURCE
        (self.run / "manifest.json").write_text(json.dumps(manifest))
        self.refuse("annotation_source_mismatch")
        write_run(self.run, [spec("a")])
        manifest = json.loads((self.run / "manifest.json").read_text())
        del manifest["timeline"]
        (self.run / "manifest.json").write_text(json.dumps(manifest))
        self.refuse("source_timeline_required")

    def test_dismissed_suppressed_and_count_identity(self):
        payload, _ = self.project([spec("kept"), spec("gone", status="dismissed_candidate", start=10, end=11)])
        counts = payload["counts"]
        self.assertEqual(counts, {"record_count": 2, "visible_count": 1, "suppressed_count": 1,
                                  "suppressed_by_reason": {"dismissed_candidate_state": 1}})
        self.assertEqual(payload["suppressed_markers"][0]["suppression_reason"], "dismissed_candidate_state")
        self.assertEqual(counts["visible_count"] + counts["suppressed_count"], counts["record_count"])

    def test_overlap_limit_never_hides_user_reports_behind_detectors(self):
        items = [spec(f"det-{i}", basis="detector_hypothesis", quote=None, start=0.0 + i * .1, end=8.0)
                 for i in range(3)]
        items += [spec("user-1", start=4.0, end=6.0), spec("user-2", start=5.0, end=7.0)]
        payload, _ = self.project(items)
        visible = {row["annotation_id"] for row in payload["markers"]}
        for name in ("user-1", "user-2"):
            self.assertIn(str(uuid.uuid5(NAMESPACE, name)), visible)
        self.assertEqual(payload["counts"]["suppressed_by_reason"], {"exceeds_two_visible_callouts": 3})

    def test_visibility_property_loop(self):
        rng = random.Random(20261006)
        bases = sorted(annotation_v2.BASES)
        for case in range(200):
            items = []
            for index in range(rng.randint(1, 9)):
                basis = rng.choice(bases)
                start = round(rng.uniform(0, 20), 2)
                extent = rng.random() < .7
                items.append({"name": f"c{case}-{index}", "kind": rng.choice(sorted(annotation_v2.KINDS)),
                              "basis": basis, "status": rng.choice(sorted(annotation_v2.STATES)),
                              "start": start, "end": round(start + rng.uniform(0, 6), 2) if extent else start,
                              "extent": extent, "quote": "literal"})
            records = [stored(item, "a" * 64) for item in items]
            visible, suppressed = projection.visibility(records)
            self.assertEqual(len(visible) + len(suppressed), len(records))
            intervals = [projection._interval(row) for row in visible]
            for probe in {low for low, _ in intervals}:
                self.assertLessEqual(sum(low <= probe < high for low, high in intervals), 2)
            for row, reason in suppressed:
                if reason == "exceeds_two_visible_callouts" and row["basis"] == "operator_assertion":
                    low, high = projection._interval(row)
                    blockers = [v for v in visible if v["basis"] == "operator_assertion"]
                    self.assertGreaterEqual(projection._max_active([projection._interval(v) for v in blockers],
                                                                   low, high), 2)

    def test_point_annotation_keeps_zero_extent(self):
        payload, text = self.project([spec("point", start=12.5, extent=False)])
        row = payload["markers"][0]
        self.assertEqual((row["source_time_seconds"], row["end_seconds"], row["extent_known"]), (12.5, 12.5, False))
        data = list(csv.DictReader(io.StringIO(text)))[0]
        self.assertEqual(float(data["source_time_seconds"]), float(data["end_seconds"]))

    def test_marked_video_consumes_rows_without_modification(self):
        renderer = ROOT / "scripts" / "marked_video.py"
        before = hashlib.sha256(renderer.read_bytes()).hexdigest()
        import marked_video
        items = [spec("a", start=1, end=3), spec("b", basis="operator_context", quote=None, start=2, end=4),
                 spec("c", basis="detector_hypothesis", quote=None, start=2.5, end=2.5, extent=False),
                 spec("d", basis="reference_comparison", quote=None, start=10, end=10, extent=False)]
        payload, _ = self.project(items)
        self.assertEqual(payload["counts"]["suppressed_by_reason"], {"exceeds_two_visible_callouts": 1})
        for mode in (False, True):
            selected, excluded = marked_video.select_markers(payload["markers"], "all-review", 0.0, 0.0, 60.0,
                                                             arrangement_labels=mode)
            self.assertEqual((len(selected), excluded), (3, []))
            callouts, coverage = marked_video.compose_callouts(selected, 0.0, arrangement_labels=mode)
            self.assertTrue(callouts)
            self.assertTrue(all(len(callout["visible_marker_ids"]) <= 2 for callout in callouts))
            self.assertEqual(set(coverage), {row["marker_id"] for row in selected})
        self.assertEqual(hashlib.sha256(renderer.read_bytes()).hexdigest(), before)

    def test_text_omitted_by_default_and_literal_with_flag(self):
        quote = "Phrase two — Mgła-style tremolo felt rushed; 音"
        payload, text = self.project([spec("q", quote=quote)])
        evidence = payload["markers"][0]["evidence"]
        self.assertNotIn("operator_quote", evidence)
        self.assertNotIn("note", evidence)
        self.assertNotIn("Mgła", text)
        self.assertIs(evidence["text_included"], False)
        payload, text = self.project([spec("q", quote=quote)], include_text=True)
        self.assertEqual(payload["markers"][0]["evidence"]["operator_quote"], quote)
        self.assertIn("Mgła", text)

    def test_public_projection_and_negative_origin_clock(self):
        payload, _ = self.project([spec("neg", start=-0.25, end=0.5)], public=True,
                                  audio_start=-0.25, format_start=-0.25)
        self.assertEqual(payload["store_form"], "public_projection")
        self.assertEqual(payload["timeline"]["source_min_seconds"], -0.25)
        self.assertEqual(payload["markers"][0]["source_time_seconds"], -0.25)

    def test_cli_refuses_output_inside_run_dir_and_writes_outside(self):
        _, store_sha = write_run(self.run, [spec("a")])
        inside = self.run / "projection"
        self.assertEqual(projection.main([str(self.run), "--store-sha256", store_sha, "--output-dir", str(inside)]), 1)
        self.assertFalse(inside.exists())
        outside = self.base / "out"
        self.assertEqual(projection.main([str(self.run), "--store-sha256", store_sha, "--output-dir", str(outside)]), 0)
        self.assertEqual(sorted(path.name for path in outside.iterdir()),
                         ["annotation-markers.csv", "annotation-markers.json"])

    def test_real_s1_context_store_projection(self):
        base = artifact_base(REAL_RUN + "/review-annotations-v2.json")
        if base is None:
            self.skipTest("S1 demo context store is not present on this host")
        run = base / REAL_RUN
        before = hashlib.sha256((run / "review-annotations-v2.json").read_bytes()).hexdigest()
        payload, text = projection.project(run, expected_store_sha256=REAL_STORE_SHA)
        self.assertEqual(before, REAL_STORE_SHA)
        self.assertEqual((payload["store_sha256"], payload["manifest_sha256"]), (REAL_STORE_SHA, REAL_MANIFEST_SHA))
        self.assertEqual(payload["counts"], {"record_count": 1, "visible_count": 1, "suppressed_count": 0,
                                             "suppressed_by_reason": {}})
        row = payload["markers"][0]
        self.assertEqual((row["basis_label"], row["source_time_seconds"], row["end_seconds"]), ("INTENT", 0.0, 5.0))
        self.assertNotIn("note", row["evidence"])
        self.assertNotIn("fan noise", text)


if __name__ == "__main__":
    unittest.main()
