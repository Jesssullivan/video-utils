"""Synthetic, stdlib-only tests for scripts/report_bundle.py (no FFmpeg, network or real media)."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import struct
import tempfile
import unittest
import wave

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("report_bundle", REPO / "scripts" / "report_bundle.py")
rb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rb)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_wave(path, value):
    with wave.open(str(path), "wb") as stream:
        stream.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
        stream.writeframes(struct.pack("<h", value) * 4000)
    return sha(path.read_bytes())


def dump(path, value):
    data = json.dumps(value, indent=1).encode("utf-8")
    path.write_bytes(data)
    return sha(data)


class BundleFixture(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.tmp = Path(os.path.realpath(self.directory.name))
        self.data = self.tmp / "data"
        runs = self.data / "artifacts" / "runs"
        self.parent = runs / "20261005T000000Z-parent"
        self.run = runs / "20261006T000000Z-fuller"
        self.other = runs / "20261006T010000Z-other"
        for path in (self.parent / "capture-profiles" / "p1", self.run, self.other):
            path.mkdir(parents=True)
        self.source_sha = sha(b"original take bytes")
        self.denoised_sha = write_wave(self.parent / "denoised.wav", 1000)
        shutil.copyfile(self.parent / "denoised.wav", self.run / "denoised.wav")
        self.source_wav_sha = write_wave(self.run / "source.wav", 2000)
        self.other_sha = write_wave(self.other / "denoised.wav", 3000)
        dump(self.parent / "manifest.json", {"run_id": self.parent.name, "source": {"sha256": self.source_sha},
                                             "output_sha256": {"denoised.wav": self.denoised_sha}})
        dump(self.other / "manifest.json", {"run_id": self.other.name, "source": {"sha256": self.source_sha},
                                            "output_sha256": {"denoised.wav": self.other_sha}})
        self.write_parent_payloads()
        self.manifest = {
            "run_id": self.run.name,
            "source": {"path": "/Users/jess/Documents/Movie take.mov", "sha256": self.source_sha},
            "output_sha256": {"source.wav": self.source_wav_sha, "denoised.wav": self.denoised_sha},
            "capture_profile_application": {"authoring_dir": str(self.parent / "capture-profiles" / "p1")},
            "pcm": {"duration_seconds": 150.0, "sample_rate": 44100},
        }
        self.manifest_sha = dump(self.run / "manifest.json", self.manifest)
        self.receipts = self.tmp / "receipts"
        self.receipts.mkdir()
        self.registry = self.write_receipts()
        self.store_path = self.data / rb.DEFAULT_STORE_REL
        self.store_path.parent.mkdir(parents=True)
        self.write_store()
        self.out_root = self.tmp / "out"
        self.counter = 0

    def write_parent_payloads(self, analyzed=None, dag_analysis_sha=None):
        analysis = {"source": {"sha256": analyzed or self.denoised_sha},
                    "source_lineage": {"original_source_sha256": self.source_sha},
                    "click_grid": {"bpm": 88.8}, "declared_tempo": {"bpm": 178.0},
                    "meter": {"status": "unknown", "time_signature": None},
                    "events": [{"kind": "broadband_attack_candidate", "audio_relative_seconds": 0.25},
                               {"kind": "periodic_high_frequency_candidate", "audio_relative_seconds": 0.5}]}
        self.analysis_sha = dump(self.parent / "analysis.json", analysis)
        flags = {"source_sha256": self.source_sha, "flags": [
            {"kind": "four_pulse_group_review_candidate", "source_time_seconds": 0.0, "end_seconds": 1.3,
             "confidence": "navigation_proxy_not_confirmed_bar", "status": "needs_review",
             "performance_issue_confirmed": False}]}
        flags_sha = dump(self.parent / "flags.json", flags)
        dump(self.parent / "markers.json", {"source_sha256": self.source_sha, "flags_sha256": flags_sha, "markers": []})
        dump(self.parent / "phrases.json", {"source": {"sha256": self.denoised_sha}, "observations": {}})
        dump(self.parent / "dag.json", {"source_sha256": self.source_sha, "flags_sha256": flags_sha,
                                        "artifact_hashes": {"analysis.json": dag_analysis_sha or self.analysis_sha,
                                                            "flags.json": flags_sha}})

    def write_receipts(self, extra=()):
        payloads = {
            "tone_ab": {"run": {"manifest_sha256": self.manifest_sha, "run_id": self.run.name,
                                "source_sha256": self.source_sha},
                        "claims": {"measurements": ["m"], "inferences": [], "listening": []},
                        "loudness_match": {"match_lu_delta": 0.01, "match_status": "matched"}},
            "rhythm_clicks": {"claim_class": "M-real", "R1_drift": {"drift_ppm": 1.67},
                              "source": {"analyzed_input_sha256": self.other_sha,
                                         "analyzed_input": str(self.other / "denoised.wav")}},
            "phrase_anchor_riff_spans": {"claim_class": "inference_intent_projection_not_detection",
                                         "inputs": {"original_source_sha256": self.source_sha,
                                                    "grid_analyzed_input_sha256": self.other_sha}},
            "phrase_anchor_riff_bench": {"bank_sha256": "b" * 64, "status": "generated_research_scored",
                                         "continuous_riff_accuracy_scope": "generated_only",
                                         "real_take_accuracy": "unknown", "suite": "synthetic-suite",
                                         "cases": [{"cohort": "tapping-run"}, {"cohort": "sweep-arpeggio"}],
                                         "scoring": {"reference_totals": {"positive_pairs": 2}}},
            "annot_corpus": {"measurements": {"claim_class_legend": {"M": "metadata"},
                                              "metric_2": {"inputs_sha256": {"manifest": self.manifest_sha}}}},
        }
        payloads.update(dict(extra))
        registry = []
        for key, value in payloads.items():
            name = f"{key}-receipt.json"
            if isinstance(value, bytes):
                (self.receipts / name).write_bytes(value)
            else:
                dump(self.receipts / name, value)
            registry.append((key, name))
        return tuple(registry)

    def write_store(self, source=None, manifest=None):
        store = {"schema_version": 2, "source_sha256": source or self.source_sha,
                 "manifest_sha256": manifest or self.manifest_sha, "revision": 1,
                 "annotations": [{"kind": "noise", "basis": "operator_context", "status": "needs_review",
                                  "source_span": {"start_seconds": 0, "end_seconds": 5, "extent_known": True},
                                  "reported_by": {"actor": "operator", "via": "agent"},
                                  "operator_certainty": None, "operator_quote": None,
                                  "note": "PRIVATE-FREE-TEXT fan and amp setup", "id": "e2add83c-0000",
                                  "claim_label": "INTENT", "musical_verdict": "not_established"}],
                 "listening_acceptance": "not_established", "replay_receipts": []}
        dump(self.store_path, store)

    def output(self):
        self.counter += 1
        return self.out_root / f"bundle-{self.counter}"

    def build(self, output=None, **kwargs):
        kwargs.setdefault("receipts_dir", self.receipts)
        kwargs.setdefault("registry", self.registry)
        kwargs.setdefault("repo_root", self.data)
        output = output or self.output()
        return rb.build(kwargs.pop("run_dir", self.run), kwargs.pop("analysis_run_dir", None),
                        kwargs.pop("annotation_store", None), output, **kwargs), output

    def refused(self, code, **kwargs):
        output = kwargs.pop("output", None) or self.output()
        with self.assertRaises(rb.Refusal) as caught:
            self.build(output, **kwargs)
        self.assertEqual(caught.exception.code, code)
        return output

    def index(self, output):
        return json.loads((output / "bundle.json").read_text())


class ReportBundleTests(BundleFixture):
    def test_build_hash_binds_every_member_and_bundle_sha(self):
        result, output = self.build()
        status, details = rb.verify(output, check_origin=True)
        self.assertEqual(status, "verified")
        index = self.index(output)
        recomputed = rb.digest(rb.canonical({key: index[key] for key in rb.HASH_SCOPE}))
        self.assertEqual(index["bundle_sha256"], recomputed)
        self.assertEqual(result["bundle_sha256"], recomputed)
        self.assertEqual(details["member_count"], len(index["members"]))
        for row in index["members"]:
            data = (output / row["bundle_path"]).read_bytes()
            self.assertEqual(rb.digest(data), row["bundle_sha256"])
            if row["derived_from"] is None and row["origin_path"]:
                self.assertEqual(row["origin_sha256"], row["bundle_sha256"])
        events = next(row for row in index["members"] if row["bundle_path"] == "tables/events.csv")
        self.assertEqual((events["derived_from"], events["origin_sha256"]), ("analysis.json", self.analysis_sha))
        self.assertEqual(index["run"]["stage_files_verified"], 2)
        self.assertEqual(index["run"]["readback"]["status"], "unchanged")
        self.assertNotIn("events.csv", {row["bundle_path"] for row in index["members"]})

    def test_refuses_missing_or_invalid_manifest(self):
        (self.run / "manifest.json").unlink()
        self.assertFalse(self.refused("manifest_missing").exists())
        (self.run / "manifest.json").write_text("{}")
        self.assertFalse(self.refused("manifest_invalid").exists())
        dump(self.run / "manifest.json", {"source": {"path": "x.mov"}, "output_sha256": {}})
        self.assertFalse(self.refused("source_identity_missing").exists())
        self.assertFalse(self.out_root.exists())

    def test_refuses_stage_hash_mismatch(self):
        data = bytearray((self.run / "denoised.wav").read_bytes())
        data[-1] ^= 0x01
        (self.run / "denoised.wav").write_bytes(bytes(data))
        output = self.refused("stage_hash_mismatch")
        self.assertFalse(output.exists())
        self.assertFalse(Path(f"{output}.failed").exists())

    def test_parent_analysis_derived_from_authoring_dir(self):
        result, output = self.build()
        analysis = self.index(output)["run"]["analysis"]
        self.assertEqual(analysis["basis"], "parent_run_from_capture_profile_authoring_dir")
        self.assertEqual(analysis["lineage"], "verified_run_derivative_hash_bound")
        self.assertEqual(analysis["analysis_run_id"], self.parent.name)
        self.assertTrue((output / "analysis.json").is_file())
        statuses = self.index(output)["run"]["auxiliary"]
        self.assertEqual({k: v["copied"] for k, v in statuses.items()},
                         {"dag": True, "flags": True, "markers": True, "phrases": True})
        _, explicit = self.build(analysis_run_dir=self.parent)
        self.assertEqual(self.index(explicit)["run"]["analysis"]["basis"], "explicit")

    def test_unbound_analysis_abstains_not_refuses(self):
        self.write_parent_payloads(analyzed="c" * 64)
        result, output = self.build()
        index = self.index(output)
        self.assertEqual(index["run"]["analysis"]["status"], "rejected_unrelated_or_modified_source")
        self.assertFalse((output / "analysis.json").exists())
        self.assertFalse((output / "flags.json").exists())
        self.assertFalse((output / "markers.json").exists())
        self.assertFalse((output / "tables" / "events.csv").exists())
        for name in ("dag", "flags", "markers"):
            self.assertEqual(index["run"]["auxiliary"][name]["status"], "rejected_stale_analysis_binding")
        self.assertEqual(len(index["unknowns"]), 21)
        self.assertEqual(rb.verify(output)[0], "verified")

    def test_analysis_run_source_mismatch_refused(self):
        dump(self.parent / "manifest.json", {"source": {"sha256": "d" * 64}, "output_sha256": {}})
        self.assertFalse(self.refused("analysis_run_source_mismatch").exists())

    def test_stale_dag_analysis_hash_excludes_aux(self):
        self.write_parent_payloads(dag_analysis_sha="e" * 64)
        # report.auxiliary_evidence rejects a dag whose artifact hash is stale; the bundle never copies it.
        _, output = self.build()
        index = self.index(output)
        self.assertTrue((output / "analysis.json").exists())
        for name in ("dag", "flags", "markers"):
            self.assertFalse((output / f"{name}.json").exists())
            self.assertTrue(index["run"]["auxiliary"][name]["status"].startswith("rejected"))
        # A dag that report.py accepts but that names another analysis hash is rejected by the bundle rule.
        original = rb.report.auxiliary_evidence

        def accepting(root, manifest, **kwargs):
            payloads, statuses = original(root, manifest, **kwargs)
            dag = json.loads((root / "dag.json").read_text())
            return ({"dag": dag, "flags": json.loads((root / "flags.json").read_text())},
                    {"dag": "source_hash_bound", "flags": "source_hash_bound", "markers": "unavailable"})
        rb.report.auxiliary_evidence = accepting
        self.addCleanup(setattr, rb.report, "auxiliary_evidence", original)
        _, output = self.build()
        auxiliary = self.index(output)["run"]["auxiliary"]
        self.assertEqual(auxiliary["dag"]["status"], "rejected_stale_analysis_binding")
        self.assertEqual(auxiliary["flags"]["status"], "rejected_stale_analysis_binding")
        self.assertFalse((output / "flags.json").exists())

    def test_verify_detects_tampered_member(self):
        _, output = self.build()
        (output / "analysis.json").write_text("{}")
        self.assertEqual(rb.verify(output)[0], "refused:member_hash_mismatch")
        _, second = self.build()
        (second / "extra.txt").write_text("x")
        self.assertEqual(rb.verify(second)[0], "refused:unexpected_member")
        _, third = self.build()
        index = self.index(third)
        index["unknowns"]["note_correctness"]["value"] = "correct"
        (third / "bundle.json").write_text(json.dumps(index))
        self.assertEqual(rb.verify(third)[0], "refused:bundle_hash_mismatch")
        _, fourth = self.build()
        (fourth / "tables" / "corpus.csv").unlink()
        self.assertEqual(rb.verify(fourth)[0], "refused:member_missing")
        with contextlib.redirect_stdout(io.StringIO()) as stream:
            code = rb.main(["verify", "--bundle-dir", str(output), "--status-only"])
        self.assertEqual((code, stream.getvalue()), (2, "refused:member_hash_mismatch\n"))

    def test_verify_check_origin_detects_changed_origin(self):
        _, output = self.build()
        self.assertEqual(rb.verify(output, check_origin=True)[0], "verified")
        manifest = dict(self.manifest, note="edited after build")
        dump(self.run / "manifest.json", manifest)
        self.assertEqual(rb.verify(output)[0], "verified")
        self.assertEqual(rb.verify(output, check_origin=True)[0], "refused:origin_changed")
        _, second = self.build()
        (self.receipts / "tone_ab-receipt.json").unlink()
        self.assertEqual(rb.verify(second, check_origin=True)[0], "refused:origin_missing")

    def test_no_audio_or_video_bytes_in_bundle(self):
        _, output = self.build()
        index = self.index(output)
        for path in output.rglob("*"):
            if path.is_file():
                self.assertFalse(rb.is_media_name(path.name), path.name)
                self.assertFalse(rb.has_media_magic(path.read_bytes()), path.name)
        self.assertLessEqual(index["total_member_bytes"], rb.MAX_TOTAL_BYTES)
        wav_bytes = (self.run / "denoised.wav").read_bytes()
        for path in output.rglob("*"):
            if path.is_file():
                self.assertNotIn(wav_bytes[44:400], path.read_bytes())
        shutil.copyfile(self.run / "denoised.wav", self.receipts / "bad.wav")
        self.refused("media_member_refused", registry=self.registry + (("bad", "bad.wav"),))
        (self.receipts / "riff.json").write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt ")
        self.refused("media_member_refused", registry=self.registry + (("riff", "riff.json"),))
        original = rb.MAX_TOTAL_BYTES
        rb.MAX_TOTAL_BYTES = 1024
        self.addCleanup(setattr, rb, "MAX_TOTAL_BYTES", original)
        self.refused("bundle_too_large")

    def test_receipt_missing_and_invalid_refused(self):
        self.refused("receipt_missing", registry=self.registry + (("absent", "absent.json"),))
        (self.receipts / "list.json").write_text("[1, 2]")
        self.refused("receipt_invalid", registry=self.registry + (("list", "list.json"),))
        (self.receipts / "broken.json").write_text("{not json")
        self.refused("receipt_invalid", registry=self.registry + (("broken", "broken.json"),))
        original = rb.MAX_RECEIPT_BYTES
        rb.MAX_RECEIPT_BYTES = 16
        self.addCleanup(setattr, rb, "MAX_RECEIPT_BYTES", original)
        self.refused("receipt_too_large")

    def test_receipt_binding_classes(self):
        dump(self.receipts / "context.json", {"note": "no identity", "status": "context"})
        result, output = self.build(registry=self.registry + (("context", "context.json"),))
        self.assertEqual(result["receipts"], {
            "tone_ab": "run_bound",
            "rhythm_clicks": "source_bound_different_analyzed_input",
            "phrase_anchor_riff_spans": "source_bound_different_analyzed_input",
            "phrase_anchor_riff_bench": "synthetic_bank_not_take",
            "annot_corpus": "metadata_bound",
            "context": "unbound_context_only"})
        receipts = {row["key"]: row for row in self.index(output)["receipts"]}
        self.assertEqual(receipts["rhythm_clicks"]["binding_basis"], "analyzed_input_run_manifest_chain")
        self.assertTrue((output / "receipts" / "rhythm_clicks.chain-manifest.json").is_file())
        same = {"inputs": {"original_source_sha256": self.source_sha,
                           "analyzed_input_sha256": self.denoised_sha}}
        dump(self.receipts / "same.json", same)
        dump(self.receipts / "foreign.json", {"inputs": {"original_source_sha256": "f" * 64}})
        result, _ = self.build(registry=self.registry + (("same", "same.json"), ("foreign", "foreign.json")))
        self.assertEqual(result["receipts"]["same"], "source_bound_same_analyzed_input")
        self.assertEqual(result["receipts"]["foreign"], "unbound_context_only")
        # File names and mtimes never confer binding.
        dump(self.receipts / f"tone_ab-{self.run.name}.json", {"status": "named like the run"})
        result, _ = self.build(registry=(("named", f"tone_ab-{self.run.name}.json"),))
        self.assertEqual(result["receipts"]["named"], "unbound_context_only")

    def test_output_dir_fresh_and_protected(self):
        existing = self.out_root / "existing"
        existing.mkdir(parents=True)
        self.refused("output_dir_exists", output=existing)
        self.refused("output_dir_protected", output=self.run / "bundle")
        self.refused("output_dir_protected", output=self.parent / "bundle")
        lookalike = self.tmp / "elsewhere" / "artifacts" / "runs" / "x" / "bundle"
        self.refused("output_dir_protected", output=lookalike)
        self.refused("output_dir_protected", output=self.tmp / ".local" / "sprint1" / "bundle")
        self.assertFalse(lookalike.exists())

        def explode():
            raise OSError("disk")
        output = self.output()
        with self.assertRaises(OSError):
            self.build(output, after_stage_hook=explode)
        self.assertFalse(output.exists())
        siblings = sorted(path.name for path in output.parent.iterdir())
        self.assertEqual(siblings, sorted(["existing", f"{output.name}.failed"]))
        failed = Path(f"{output}.failed")
        self.assertEqual([path.name for path in failed.iterdir()], ["report-bundle.failed.json"])
        self.assertEqual(json.loads((failed / "report-bundle.failed.json").read_text())["reason"], "OSError")

    def test_protected_readback_and_change_during_build(self):
        before = {path: path.read_bytes() for path in list(self.run.iterdir()) + list(self.parent.iterdir())
                  if path.is_file()}
        _, output = self.build()
        readback = self.index(output)["run"]["readback"]
        self.assertEqual(readback["changed"], [])
        opened = {row["path"] for row in readback["files"]}
        self.assertIn(str(self.run / "denoised.wav"), opened)
        self.assertIn(str(self.parent / "analysis.json"), opened)
        self.assertIn(str(self.store_path), opened)
        for path, data in before.items():
            self.assertEqual(path.read_bytes(), data)
        self.assertEqual(sorted(p.name for p in self.run.iterdir()), sorted(p.name for p in before if p.parent == self.run))

        def mutate():
            with (self.parent / "analysis.json").open("ab") as stream:
                stream.write(b" ")
        output = self.output()
        with self.assertRaises(rb.Refusal) as caught:
            self.build(output, after_stage_hook=mutate)
        self.assertEqual(caught.exception.code, "input_changed_during_build")
        self.assertFalse(output.exists())
        self.assertEqual(list(output.parent.glob(f"{output.name}.staging-*")), [])
        reason = json.loads((Path(f"{output}.failed") / "report-bundle.failed.json").read_text())["reason"]
        self.assertEqual(reason, "input_changed_during_build")

    def test_corpus_coverage_operator_vs_generated(self):
        _, output = self.build()
        index = self.index(output)
        operator = index["corpus"]["operator_labelled"]
        self.assertTrue(operator["store_bound"])
        self.assertEqual((operator["annotation_count"], operator["covered_seconds"], operator["duration_seconds"]),
                         (1, 5.0, 150.0))
        self.assertAlmostEqual(operator["coverage_fraction"], 5.0 / 150.0, places=6)
        self.assertEqual((operator["musical_phrase_labels"], operator["note_labels"]), (0, 0))
        self.assertEqual(operator["by_kind"], {"noise": 1})
        self.assertFalse(operator["approved_expected_rhythm_reference"])
        self.assertEqual(operator["statement"], "small labelled corpus: 1 operator annotation covering 5.0 of "
                                                "150.00 s; 0 musical phrase or note labels")
        banks = index["corpus"]["generated_banks"]
        self.assertEqual(len(banks), 1)
        self.assertEqual((banks[0]["origin"], banks[0]["case_count"], banks[0]["real_take_accuracy"]),
                         ("synthetic_generated_bank", 2, "unknown"))
        self.assertFalse(index["corpus"]["pools_summed"])
        for path in output.rglob("*"):
            if path.is_file():
                self.assertNotIn(b"PRIVATE-FREE-TEXT", path.read_bytes())
        self.write_store(manifest="9" * 64)
        _, unbound = self.build()
        operator = self.index(unbound)["corpus"]["operator_labelled"]
        self.assertIsNone(operator["covered_seconds"])
        self.assertEqual(operator["reason"], "annotation_store_unbound")
        self.assertFalse((unbound / "annotations.json").exists())
        self.store_path.unlink()
        _, absent = self.build()
        self.assertEqual(self.index(absent)["corpus"]["operator_labelled"]["reason"], "annotation_store_absent")

    def test_unknown_fields_complete_with_reasons(self):
        _, output = self.build()
        unknowns = self.index(output)["unknowns"]
        expected = {
            "listening_accepted": False, "listening_acceptance": "not_established", "operator_preference": None,
            "perceived_fullness": None, "nasal_quality": None, "expected_rhythm_reference_approved": None,
            "note_correctness": None, "missed_or_extra_notes": None, "performance_grade": "not_performed",
            "click_identity": "unverified", "physical_capture_latency": "uncalibrated", "meter": None,
            "tonic": None, "mode": None, "fundamental_32hz_presence": None, "room_response_recovered": False,
            "stems": "not_produced", "editor_import_proven": False, "default_adopted": False,
            "master_changed": False, "quarto_render_status": "not_attempted"}
        self.assertEqual({key: row["value"] for key, row in unknowns.items()}, expected)
        self.assertTrue(all(isinstance(row["reason"], str) and row["reason"] for row in unknowns.values()))
        self.assertIn("candidate only", unknowns["meter"]["candidate"])

    def test_listening_review_template_all_null(self):
        template = json.loads((REPO / "docs" / "spec" / "examples" / "listening-review.json").read_text())
        leaves = []

        def walk(value, path):
            if isinstance(value, dict):
                for key, item in value.items():
                    walk(item, path + (key,))
            else:
                leaves.append((path, value))
        walk(template, ())
        schema = {("schema_id",), ("schema_version",)}
        self.assertTrue(schema <= {path for path, _ in leaves})
        others = [(path, value) for path, value in leaves if path not in schema]
        self.assertGreaterEqual(len(others), 10)
        self.assertEqual([path for path, value in others if value is not None], [])

    def test_quarto_sources_contract_and_html_fallback_intact(self):
        qmd = (REPO / "reports" / "demo.qmd").read_text()
        plots = (REPO / "reports" / "plots.R").read_text()
        config = (REPO / "reports" / "_quarto.yml").read_text()
        self.assertIn("params$run_dir", qmd)
        self.assertIn("report_bundle.py", qmd)
        self.assertIn("--status-only", qmd)
        for text in (qmd, plots, config):
            self.assertNotIn("jsonlite", text)
            self.assertNotIn("http://", text)
            self.assertNotIn("https://", text)
        self.assertNotIn("source$path", qmd)
        self.assertIn("embed-resources: true", config)
        self.assertIn("output-dir: _render", config)
        self.assertIn("events.csv", plots)
        self.assertIn("not a Quarto-rendered report", (REPO / "scripts" / "report.py").read_text())

    def test_cli_describe_and_build_refusal_exit_codes(self):
        with contextlib.redirect_stdout(io.StringIO()) as stream:
            self.assertEqual(rb.main(["describe"]), 0)
        described = json.loads(stream.getvalue())
        self.assertEqual(len(described["unknown_fields"]), 21)
        self.assertIn("synthetic_bank_not_take", described["binding_classes"])
        (self.run / "manifest.json").unlink()
        with contextlib.redirect_stdout(io.StringIO()) as stream:
            code = rb.main(["build", "--run-dir", str(self.run), "--output-dir", str(self.output())])
        self.assertEqual((code, json.loads(stream.getvalue())), (2, {"status": "refused", "reason": "manifest_missing"}))
        with contextlib.redirect_stdout(io.StringIO()) as stream:
            code = rb.main(["verify", "--bundle-dir", str(self.tmp / "nope"), "--status-only"])
        self.assertEqual((code, stream.getvalue().strip()), (2, "refused:bundle_missing"))


if __name__ == "__main__":
    unittest.main()
