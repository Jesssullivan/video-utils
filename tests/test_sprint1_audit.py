"""Independent S1 refusal, provenance and numerical accounting probes.

Owner modules are loaded without edits. During isolation, explicit source roots
may select a sibling owner's frozen files; after integration the defaults select
this checkout. No actual media, model inference or network request is required.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1]
CATALOG_ROOT = Path(os.environ.get("VIDEO_UTILS_S1_AUDIT_ROOT", ROOT)).resolve()
OLD_NAMES = (
    "probe", "denoise", "bpm", "noise", "tone", "notes", "rhythm", "phrases",
    "export", "report", "pipeline", "markers", "clicks", "phrase_compare",
    "benchmark", "review", "pitch", "meter", "tonal", "corpus", "pitch_evaluate",
    "phrase_evaluate", "marked_video", "basic_pitch_compare", "capture_profile",
    "editor_marker_plan", "learned_pitch_evaluate", "apply_capture_profile",
    "arrangement_reference", "share_export",
)
OLD_DESCRIPTOR_SHA256 = "c13b2f89011e9fe862728d0e105b18945652d2fac3de36286971ecf686ca64aa"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def load_owner(filename, environment, module_name):
    root = Path(os.environ.get(environment, ROOT)).resolve()
    path = root / "scripts" / filename
    specification = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(specification)
    # Dataclass introspection needs the independently named module registered.
    sys.modules[module_name] = module
    sys.path.insert(0, str(path.parent))
    try:
        specification.loader.exec_module(module)
    finally:
        sys.path.remove(str(path.parent))
    return module


class AdmissionCompatibilityAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = load_owner("tool_api.py", "VIDEO_UTILS_S1_AUDIT_ROOT", "s1_independent_tool_api")

    def test_original_thirty_descriptors_remain_exact(self):
        catalog = json.loads((CATALOG_ROOT / "program" / "tools.json").read_text())
        tools = catalog["tools"]
        self.assertGreaterEqual(len(tools), len(OLD_NAMES))
        self.assertEqual(tuple(tool["name"] for tool in tools[:30]), OLD_NAMES)
        self.assertEqual(hashlib.sha256(canonical(tools[:30])).hexdigest(),
                         OLD_DESCRIPTOR_SHA256)

    def test_new_tools_have_closed_schemas_and_cross_field_refusals(self):
        for name in ("annotation_v2", "corpus_split"):
            schema = self.api.descriptor(name)["inputSchema"]
            self.assertFalse(schema["additionalProperties"])
            with self.assertRaises(self.api.ValidationError):
                self.api.validate({"unknown": "unadvertised"}, schema)
        for arguments in ({"run_dir": "unused", "operation": "write"},
                          {"run_dir": "unused", "operation": "read", "input": "unused"}):
            with self.assertRaises(self.api.ValidationError):
                self.api.validate_tool_arguments("annotation_v2", arguments)

    def test_corpus_split_rejects_ancestor_alias_without_changing_legacy_preflight(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            actual = root / "actual" / "sub"
            actual.mkdir(parents=True)
            (actual / "split.json").write_bytes(b"{}")
            (root / "alias").symlink_to(root / "actual", target_is_directory=True)
            arguments = {"local_root": str(root / "alias/sub"),
                         "manifest": str(root / "alias/sub/split.json")}
            with self.assertRaises(self.api.ToolError):
                self.api.worker_command("corpus_split", arguments)
            legacy = self.api.worker_command("corpus", arguments)
            self.assertIn(str(actual / "split.json"), legacy)

    def test_annotation_request_paths_preserve_bounds_and_symlink_components(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            run = root / "run"
            run.mkdir()
            request = root / "request.json"
            request.write_bytes(b"{}")
            command = self.api.worker_command("annotation_v2", {
                "run_dir": str(run), "operation": "write", "input": str(request),
            })
            self.assertIn(str(request), command)
            with request.open("wb") as stream:
                stream.truncate(20001)
            with self.assertRaises(self.api.ToolError):
                self.api.worker_command("annotation_v2", {
                    "run_dir": str(run), "operation": "write", "input": str(request),
                })
            alias = root / "alias"
            alias.symlink_to(run, target_is_directory=True)
            with self.assertRaises(self.api.ToolError):
                self.api.worker_command("annotation_v2", {"run_dir": str(alias)})

    def test_new_skill_prompts_are_exact_after_initialized_stdio(self):
        names = ("guitar-annotation-v2", "guitar-corpus-split")
        messages = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-11-25", "capabilities": {},
            "clientInfo": {"name": "s1-independent-audit", "version": "1"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"}]
        messages.extend({"jsonrpc": "2.0", "id": index + 2, "method": "prompts/get",
                         "params": {"name": name}} for index, name in enumerate(names))
        with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as input_stream, \
             tempfile.TemporaryFile(mode="w+", encoding="utf-8") as output_stream, \
             tempfile.TemporaryFile(mode="w+", encoding="utf-8") as error_stream:
            input_stream.write("".join(json.dumps(message) + "\n" for message in messages))
            input_stream.seek(0)
            result = subprocess.run([sys.executable, str(CATALOG_ROOT / "scripts/mcp_server.py")],
                                    stdin=input_stream, stdout=output_stream, stderr=error_stream, timeout=10)
            output_stream.seek(0)
            replies = [json.loads(line) for line in output_stream]
            error_stream.seek(0)
            self.assertEqual(result.returncode, 0, error_stream.read())
        self.assertEqual(len(replies), 3)
        for name, reply in zip(names, replies[1:]):
            self.assertEqual(reply["result"]["messages"][0]["content"]["text"],
                             (CATALOG_ROOT / ".agents/skills" / name / "SKILL.md").read_text())


class AnnotationRefusalAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.worker = load_owner("annotation_v2.py", "VIDEO_UTILS_S1_ANNOTATION_ROOT",
                                "s1_independent_annotation")

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        manifest = self.root / "manifest.json"
        payload = {"source": {"sha256": "a" * 64},
                   "timeline": {"audio_start_seconds": 2, "format_start_seconds": 1},
                   "pcm": {"duration_seconds": 10}}
        manifest.write_bytes(canonical(payload) + b"\n")
        self.session = SimpleNamespace(
            root=self.root, manifest_path=manifest, manifest=payload, source_hash="a" * 64,
            manifest_hash=hashlib.sha256(manifest.read_bytes()).hexdigest(),
            source_min=1.0, source_max=12.0, duration=10.0, audio_start=2.0, format_start=1.0,
            lock=threading.Lock(),
            provenance_hashes={}, marker_ids=set(), candidate_hash=None,
        )
        self.store = self.worker.AnnotationStore(self.session)

    def request(self, revision=0, key="audit-request-0001"):
        return {
            "schema_version": 2, "expected_revision": revision,
            "idempotency_key": key, "source_sha256": self.session.source_hash,
            "manifest_sha256": self.session.manifest_hash,
            "annotation": {
                "kind": "rhythm_timing", "basis": "operator_assertion",
                "status": "needs_review", "source_span": {
                    "start_seconds": 3.0, "end_seconds": 3.0, "extent_known": False,
                }, "reported_by": {"actor": "operator", "via": "agent"},
                "operator_certainty": "uncertain", "operator_quote": "  I may rush here.  ",
                "note": "Timestamp is a user assertion; extent remains unknown.",
            },
        }

    def bytes_or_absent(self):
        return self.store.path.read_bytes() if self.store.path.exists() else None

    def refused_without_change(self, request):
        before = self.bytes_or_absent()
        with self.assertRaises(self.worker.AnnotationError):
            self.store.write(request)
        self.assertEqual(self.bytes_or_absent(), before)

    def test_source_clock_literal_claim_and_v1_bytes_preserved(self):
        legacy = self.root / "review-annotations.json"
        legacy_bytes = b'{"schema_version":1,"retained":"inert legacy bytes"}\n'
        legacy.write_bytes(legacy_bytes)
        saved = self.store.write(self.request())
        item = saved["annotations"][0]
        self.assertEqual(item["source_span"], self.request()["annotation"]["source_span"])
        self.assertEqual(item["operator_quote"], "  I may rush here.  ")
        self.assertEqual(item["claim_label"], "USER REPORTED")
        self.assertEqual(item["musical_verdict"], "not_established")
        self.assertEqual(saved["listening_acceptance"], "not_established")
        self.assertNotIn("replay_receipts", saved)
        self.assertEqual(self.store.read()["annotations"], saved["annotations"])
        self.assertEqual(legacy.read_bytes(), legacy_bytes)

    def test_refusal_matrix_preserves_populated_store(self):
        self.store.write(self.request())
        mutations = [
            lambda r: r.update(source_sha256="b" * 64),
            lambda r: r.update(manifest_sha256="b" * 64),
            lambda r: r.update(expected_revision=0),
            lambda r: r.update(expected_revision=True),
            lambda r: r.update(schema_version=True),
            lambda r: r.update(extra="unadvertised"),
            lambda r: r["annotation"].update(kind="wrong_note_confirmed"),
            lambda r: r["annotation"].update(status="master_accepted"),
            lambda r: r["annotation"].update(musical_verdict="confirmed_mistake"),
            lambda r: r["annotation"].update(candidate_id="c" * 64),
            lambda r: r["annotation"].update(id="11111111-2222-4333-8444-555555555555"),
            lambda r: r["annotation"]["reported_by"].update(actor="detector"),
        ]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                request = self.request(1, "audit-request-0002")
                mutate(request)
                self.refused_without_change(request)
        for start, end, known in (
            (float("nan"), 3, False), (float("inf"), 3, False),
            (True, 3, False), ("3", 3, False), (0, 0, False),
            (3, 13, True), (4, 3, True), (3, 4, False), (3, 3, 1),
        ):
            with self.subTest(span=(start, end, known)):
                request = self.request(1, "audit-request-0002")
                request["annotation"]["source_span"] = {
                    "start_seconds": start, "end_seconds": end, "extent_known": known,
                }
                self.refused_without_change(request)

    def test_invalid_first_write_does_not_create_store(self):
        request = self.request()
        request["annotation"]["basis"] = "detector_hypothesis"
        self.refused_without_change(request)
        self.assertFalse(self.store.path.exists())

    def test_replay_after_later_mutation_is_inert_and_conflicts_refuse(self):
        first = self.request()
        committed = self.store.write(first)
        second = self.request(1, "audit-request-0002")
        second["annotation"]["source_span"] = {
            "start_seconds": 5, "end_seconds": 6, "extent_known": True,
        }
        self.store.write(second)
        before = self.bytes_or_absent()
        replay = self.store.write(first)
        self.assertEqual(replay["revision"], 2)
        self.assertEqual(replay["mutation"]["outcome"], "replayed")
        self.assertEqual(replay["mutation"]["committed_revision"], 1)
        self.assertEqual(replay["mutation"]["annotation_id"], committed["annotations"][0]["id"])
        self.assertEqual(self.bytes_or_absent(), before)
        conflicting = copy.deepcopy(first)
        conflicting["annotation"]["note"] += " Altered replay."
        self.refused_without_change(conflicting)

    def test_detector_cannot_acquire_operator_certainty_or_musical_verdict(self):
        request = self.request()
        request["annotation"].update(basis="detector_hypothesis", operator_quote=None,
                                     operator_certainty=None, reported_by={"actor": "detector", "via": "cli"})
        saved = self.store.write(request)
        self.assertEqual(saved["annotations"][0]["claim_label"], "REVIEW")
        self.assertEqual(saved["annotations"][0]["musical_verdict"], "not_established")
        forged = self.request(1, "audit-request-0002")
        forged["annotation"].update(basis="detector_hypothesis", reported_by={"actor": "detector", "via": "cli"})
        self.refused_without_change(forged)

    def test_changed_manifest_and_candidates_refuse_without_rewrite(self):
        self.store.write(self.request())
        candidate = self.root / "markers.json"
        candidate.write_bytes(b"original candidate metadata")
        self.session.provenance_hashes[candidate] = hashlib.sha256(candidate.read_bytes()).hexdigest()
        candidate.write_bytes(b"changed candidate metadata")
        self.refused_without_change(self.request(1, "audit-request-0002"))
        self.session.provenance_hashes.clear()
        self.session.manifest_path.write_bytes(b"changed manifest")
        self.refused_without_change(self.request(1, "audit-request-0002"))

    @unittest.skipUnless(hasattr(os, "mkfifo"), "POSIX FIFO fixture required")
    def test_fifo_read_is_bounded_and_refused(self):
        fifo = self.root / "request.json"
        os.mkfifo(fifo)
        source = Path(self.worker.__file__)
        code = (
            "import importlib.util,sys; "
            "s=importlib.util.spec_from_file_location('s1_fifo_probe',sys.argv[1]); "
            "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
            "m.read_json(sys.argv[2],20000)"
        )
        result = subprocess.run([sys.executable, "-c", code, str(source), str(fifo)],
                                capture_output=True, text=True, timeout=2)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unsafe_annotation_file", result.stderr)
        self.assertFalse(self.store.path.exists())

    def test_cli_metadata_is_bounded_before_session_loading(self):
        manifest = {"source": {"sha256": self.session.source_hash},
                    "timeline": {"audio_start_seconds": 2, "format_start_seconds": 1},
                    "pcm": {"duration_seconds": 10}}
        original = canonical(manifest) + b"\n"
        for name in ("manifest.json", "analysis.json", "dag.json", "flags.json", "markers.json"):
            with self.subTest(metadata=name):
                self.session.manifest_path.write_bytes(original)
                path = self.root / name
                with path.open("wb") as stream:
                    stream.truncate(self.worker.MAX_PROVENANCE_BYTES + 1)
                result = subprocess.run([sys.executable, self.worker.__file__, "read", str(self.root)],
                                        capture_output=True, text=True, timeout=5)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertFalse(self.store.path.exists())
                path.unlink()

    def test_cli_unknown_source_clock_cannot_author_annotations(self):
        self.session.manifest_path.write_bytes(canonical({"source": {"sha256": self.session.source_hash},
                                                         "pcm": {"duration_seconds": 10}}))
        request = self.request()
        request["manifest_sha256"] = hashlib.sha256(self.session.manifest_path.read_bytes()).hexdigest()
        path = self.root / "request.json"
        path.write_bytes(canonical(request))
        result = subprocess.run([sys.executable, self.worker.__file__, "write", str(self.root),
                                 "--input", str(path)], capture_output=True, text=True, timeout=5)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertFalse(self.store.path.exists())


class PhraseMetricAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.worker = load_owner("phrase_proposal_s1.py", "VIDEO_UTILS_S1_PHRASES_ROOT",
                                "s1_independent_phrase_metrics")

    @staticmethod
    def pair(offset=0):
        return {"first_span_seconds": [1 + offset, 2 + offset],
                "second_span_seconds": [4 + offset, 5 + offset]}

    def test_two_references_cannot_reuse_one_prediction(self):
        result = self.worker.score_rows([self.pair(), self.pair(.1)], [self.pair()])
        for metric in result["pair_iou"]:
            self.assertEqual((metric["tp"], metric["fp"], metric["fn"]), (1, 0, 1))
            self.assertEqual(metric["endpoint_count"], 4)
        for metric in result["typed_endpoints"]:
            self.assertEqual((metric["tp"], metric["fp"], metric["fn"]), (4, 0, 4))
            self.assertEqual(metric["reference_count"], 8)

    def test_abstention_retains_reference_counts_and_empty_negative_is_not_perfect(self):
        abstention = self.worker.score_rows([self.pair()], [])
        empty = self.worker.score_rows([], [])
        for metric in abstention["pair_iou"]:
            self.assertEqual(metric["fn"], 1)
            self.assertEqual(metric["reference_count"], 1)
            self.assertEqual(metric["recall"], 0)
            self.assertIsNone(metric["matched_endpoint_mae_seconds"])
        for metric in empty["pair_iou"]:
            self.assertIsNone(metric["recall"])
            self.assertIsNone(metric["f1"])
            self.assertEqual(metric["endpoint_count"], 0)

    def test_full_pair_requires_both_axes_and_invalid_spans_refuse(self):
        partial = self.pair()
        partial["second_span_seconds"] = [6, 7]
        result = self.worker.score_rows([self.pair()], [partial])
        self.assertEqual(result["pair_iou"][0]["tp"], 0)
        self.assertEqual(result["typed_endpoints"][0]["tp"], 2)
        invalid = self.pair()
        invalid["first_span_seconds"] = [float("nan"), 2]
        with self.assertRaises(ValueError):
            self.worker.score_rows([self.pair()], [invalid])


class CorpusLeakageAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.worker = load_owner("corpus_split_s1.py", "VIDEO_UTILS_S1_CORPUS_ROOT",
                                "s1_independent_corpus_split")
        cls.annotation_worker = load_owner("annotation_v2.py", "VIDEO_UTILS_S1_ANNOTATION_ROOT",
                                           "s1_independent_corpus_annotation")
        previous = sys.modules.get("annotation_v2")
        sys.modules["annotation_v2"] = cls.annotation_worker
        def restore():
            if previous is None:
                sys.modules.pop("annotation_v2", None)
            else:
                sys.modules["annotation_v2"] = previous
        cls.addClassCleanup(restore)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.path = self.root / "splits.json"
        self.payload = {
            "schema_id": "video-utils.corpus-split.s1", "schema_version": 1,
            "corpus_id": "independent-fixtures", "revision": 1,
            "coverage": "sparse_or_unknown_no_negative_inference", "approval_state": "unreviewed",
            "records": [self.record("original", "take-a", "a" * 64, "train")],
            "context_refs": [],
        }

    @staticmethod
    def record(name, family, source, split):
        return {
            "id": name, "take_family_id": family, "split": split,
            "origin": "synthetic_fixture", "source_sha256": source,
            "artifact_sha256": hashlib.sha256(name.encode()).hexdigest(),
            "parent_ids": [], "augmentation_group_ids": [], "manifest": None,
            "annotation_refs": [],
        }

    def write(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = canonical(value) + b"\n"
        path.write_bytes(raw)
        return hashlib.sha256(raw).hexdigest()

    def evaluate(self, summary=False):
        self.write("splits.json", self.payload)
        before = {str(path.relative_to(self.root)): path.read_bytes()
                  for path in self.root.rglob("*.json")}
        try:
            return self.worker.validate_split(self.path, self.root, summary=summary)
        finally:
            self.assertEqual(before, {str(path.relative_to(self.root)): path.read_bytes()
                                      for path in self.root.rglob("*.json")})

    def test_source_alias_artifact_and_transitive_augmentation_leaks_refuse(self):
        for relation in ("source", "artifact", "augmentation"):
            with self.subTest(relation=relation):
                first = self.record("original", "take-a", "a" * 64, "train")
                other = self.record("forged-alias", "take-b", "b" * 64, "test")
                if relation == "source":
                    other["source_sha256"] = first["source_sha256"]
                elif relation == "artifact":
                    other["artifact_sha256"] = first["artifact_sha256"]
                else:
                    first["augmentation_group_ids"] = ["shared-transform"]
                    other["augmentation_group_ids"] = ["shared-transform"]
                self.payload["records"] = [first, other]
                with self.assertRaises(self.worker.corpus.CorpusError):
                    self.evaluate()

    def test_unknown_coverage_stays_zero_negative_denominator(self):
        first = self.payload["records"][0]
        first["split"] = "unassigned"
        result = self.evaluate(summary=True)
        self.assertEqual(result["absence_denominator"], 0)
        self.assertEqual(result["negative_examples_inferred"], 0)
        self.assertEqual(result["unlabelled_intervals"], "unknown_not_negative")
        self.assertIsNone(result["groups"][0]["assigned_split"])
        self.assertFalse(result["source_audio_read"])
        self.assertFalse(result["ground_truth_established"])
        first["split"] = "unknown"
        with self.assertRaises(self.worker.corpus.CorpusError):
            self.evaluate()

    def test_group_keys_are_order_and_partition_independent(self):
        child = self.record("child", "take-a", "a" * 64, "unassigned")
        child["parent_ids"] = ["original"]
        self.payload["records"].append(child)
        first = self.evaluate()["groups"][0]["group_sha256"]
        self.payload["records"].reverse()
        for record in self.payload["records"]:
            record["split"] = "validation"
        self.assertEqual(self.evaluate()["groups"][0]["group_sha256"], first)
        self.payload["records"][0]["artifact_sha256"] = "c" * 64
        self.assertNotEqual(self.evaluate()["groups"][0]["group_sha256"], first)

    def v2_fixture(self):
        row = self.payload["records"][0]
        manifest = {"source": {"sha256": row["source_sha256"]},
                    "timeline": {"audio_start_seconds": 2, "format_start_seconds": 1},
                    "pcm": {"duration_seconds": 10}}
        manifest_hash = self.write("run/manifest.json", manifest)
        marker = {"source_sha256": row["source_sha256"], "markers": [
            {"source_time_seconds": 3, "end_seconds": 4, "name": "phrase"}]}
        marker_hash = self.write("run/markers.json", marker)
        identity = {"source_sha256": row["source_sha256"], "kind": "phrase", "start": 3.0, "end": 4.0}
        candidate = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        run = self.root / "run"
        session = SimpleNamespace(root=run, manifest_path=run / "manifest.json", manifest=manifest,
                                  source_hash=row["source_sha256"], manifest_hash=manifest_hash,
                                  source_min=1.0, source_max=12.0, duration=10.0, audio_start=2.0,
                                  format_start=1.0, lock=threading.Lock(),
                                  provenance_hashes={run / "markers.json": marker_hash},
                                  marker_ids={candidate}, candidate_hash=marker_hash)
        store = self.annotation_worker.AnnotationStore(session)
        request = {
            "schema_version": 2, "expected_revision": 0, "idempotency_key": "corpus-audit-0001",
            "source_sha256": session.source_hash, "manifest_sha256": manifest_hash,
            "annotation": {
                "kind": "phrase_duration", "basis": "operator_assertion", "status": "needs_review",
                "source_span": {"start_seconds": 3, "end_seconds": 4, "extent_known": True},
                "reported_by": {"actor": "operator", "via": "agent"}, "operator_certainty": "uncertain",
                "operator_quote": "Uncertain phrase tail", "note": "Literal user fixture; not detector truth.",
                "candidate_id": candidate,
            },
        }
        saved = store.write(request)
        row["manifest"] = {"path": "run/manifest.json", "sha256": manifest_hash}
        row["annotation_refs"] = [{
            "store": {"path": "run/review-annotations-v2.json", "sha256": hashlib.sha256(store.path.read_bytes()).hexdigest()},
            "schema_version": 2, "revision": 1, "selected_ids": [saved["annotations"][0]["id"]],
        }]
        return saved

    def test_v2_assertion_semantics_survive_without_promotion(self):
        saved = self.v2_fixture()
        result = self.evaluate()
        item = result["records"][0]["validated_annotation_refs"][0]["selected_annotations"][0]
        self.assertEqual(item, saved["annotations"][0])
        self.assertEqual(item["claim_label"], "USER REPORTED")
        self.assertEqual(item["musical_verdict"], "not_established")
        summary = self.evaluate(summary=True)
        self.assertNotIn("Uncertain phrase tail", json.dumps(summary))
        self.assertEqual(summary["unique_selected_annotation_count"], 1)
        self.assertEqual(summary["absence_denominator"], 0)

    def test_v2_stale_candidate_receipt_refuses(self):
        self.v2_fixture()
        self.write("run/markers.json", {"source_sha256": "b" * 64, "markers": []})
        with self.assertRaises(self.worker.corpus.CorpusError):
            self.evaluate()


@unittest.skipUnless(shutil.which("node"), "Node required for independent shipped UI behavior")
class PracticeSourceClockAudit(unittest.TestCase):
    def javascript(self, code):
        owner = Path(os.environ.get("VIDEO_UTILS_S1_UI_ROOT", ROOT)).resolve()
        harness = r'''
const fs=require("fs"),vm=require("vm"),elements=new Map();
function element(id){if(!elements.has(id))elements.set(id,{value:"",checked:false,disabled:false,textContent:"",children:[],classList:{toggle(){}},setAttribute(){},append(...v){this.children.push(...v)},replaceChildren(){this.children=[]},addEventListener(){},focus(){}});return elements.get(id)}
const context={console,document:{getElementById:element,addEventListener(){},dispatchEvent(){}},CustomEvent:class{constructor(type,options){this.type=type;this.detail=options.detail}},setTimeout,URL,Blob};
vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[1],"utf8").replace(/\ninit\(\);\s*$/,"\n"),context);vm.runInContext(fs.readFileSync(process.argv[2],"utf8"),context);
function run(code){return vm.runInContext(code,context)}
function emit(value){console.log(JSON.stringify(value))}
run(`session={timeline:{source_min_seconds:1,source_max_seconds:12,audio_start_seconds:2,format_start_seconds:1},markers:[]};activeRole='original';players.set('original',{currentTime:0,duration:10,readyState:1,paused:true,pause(){}})`);
'''
        result = subprocess.run([shutil.which("node"), "-e", harness + code,
                                 str(owner / "review/app.js"), str(owner / "review/practice.js")],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_unreachable_audio_loop_is_refused_without_rewriting_span(self):
        value = self.javascript('element("note-start").value="1";element("note-end").value="1.5";element("loop-span").checked=true;emit({enabled:run("updateLoopStatus()"),armed:element("loop-span").checked,start:element("note-start").value,end:element("note-end").value,notice:element("loop-status").textContent});')
        self.assertFalse(value["enabled"])
        self.assertFalse(value["armed"])
        self.assertEqual((value["start"], value["end"]), ("1", "1.5"))
        self.assertIn("coverage", value["notice"])

    def test_role_switch_rechecks_loop_and_unknown_duration_abstains(self):
        value = self.javascript('run("players.set(\'video\',{currentTime:0,duration:10,readyState:1,paused:true,pause(){}});activeRole=\'video\'");element("note-start").value="1.1";element("note-end").value="1.5";element("loop-span").checked=true;const before=run("updateLoopStatus()");run("setRole(\'original\')");const switched=element("loop-span").checked;element("note-start").value="4";element("note-end").value="5";element("loop-span").checked=true;run("players.get(\'original\').duration=NaN");emit({before,switched,unknown:run("updateLoopStatus()"),notice:element("loop-status").textContent});')
        self.assertTrue(value["before"])
        self.assertFalse(value["switched"])
        self.assertFalse(value["unknown"])
        self.assertIn("known", value["notice"])

    def test_source_seek_uses_audio_origin_and_never_autoplays(self):
        value = self.javascript('run("seekSource(4.5)");emit({relative:run("players.get(\'original\').currentTime"),source:element("position").value,paused:run("players.get(\'original\').paused")});')
        self.assertEqual(value, {"relative": 2.5, "source": 4.5, "paused": True})

    def test_point_display_dwell_does_not_invent_extent_or_late_endpoint(self):
        value = self.javascript('emit(run("[activeReviewBadge(4,4,4,false),activeReviewBadge(4.749,4,4,false),activeReviewBadge(4.75,4,4,false),activeReviewBadge(4.5,4,4.5,true)]"));')
        self.assertEqual(value, [True, True, False, False])

    def test_claim_labels_remain_four_distinct_evidence_bases(self):
        value = self.javascript('emit(run("[\'operator_assertion\',\'operator_context\',\'detector_hypothesis\',\'reference_comparison\'].map(evidenceLabel)"));')
        self.assertEqual(value, ["USER REPORTED", "INTENT", "DETECTOR HYPOTHESIS", "REFERENCE COMPARISON"])


class LowRegisterAccountingAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import numpy as np
            import scipy
        except ImportError as error:
            raise unittest.SkipTest("Optional qualified numerical environment required") from error
        cls.np = np
        owner = Path(os.environ.get("VIDEO_UTILS_S1_LOW_REGISTER_ROOT", ROOT)).resolve()
        sys.path.insert(0, str(owner / "scripts"))
        cls.addClassCleanup(sys.path.remove, str(owner / "scripts"))
        cls.worker = load_owner("low_register_s1.py", "VIDEO_UTILS_S1_LOW_REGISTER_ROOT",
                                "s1_independent_low_register")

    def fixture(self):
        np = self.np
        rate = 1024
        frequency = 440 * 2 ** ((24 - 69) / 12)
        positions = np.arange(4096) / rate
        guitar = np.zeros((4096, 1))
        guitar[512:2048, 0] = .1 * np.sin(2 * np.pi * frequency * positions[512:2048])
        guitar[2800:4000, 0] = .08 * np.sin(2 * np.pi * frequency * positions[2800:4000])
        truth = {
            "case": {"sample_rate": rate, "alias": "independent-zero-response",
                     "kind": "synthetic_audit", "parameters": {"harmonics": [[1, 1]], "noise_rms": 0}},
            "events": [
                {"kind": "sustain", "start_sample": 512, "end_sample": 2048, "frequency_hz": frequency},
                {"kind": "palm_mute", "start_sample": 1500, "end_sample": 1800, "frequency_hz": None},
                {"kind": "connected_legato_no_internal_pick_attacks", "start_sample": 2800,
                 "end_sample": 4000, "frequency_hz": None},
            ], "non_identifiable": False, "fundamental_gain_applicable": True,
        }
        return guitar, np.zeros_like(guitar), truth

    def test_complete_attenuation_keeps_supported_denominators_and_fails(self):
        guitar, zero, truth = self.fixture()
        score = self.worker.score(guitar, zero, guitar, zero, zero, zero, zero, truth,
                                  "protected_mask")
        self.assertEqual(score["fundamental_eligible_channel_event_denominator"], 1)
        self.assertGreaterEqual(set(score["quality_alerts"]), {
            "fundamental_preservation", "attack_energy", "tail_energy", "legato_energy",
        })
        self.assertEqual(score["active_sample_frame_denominator"], 2736)
        self.assertEqual(score["sample_value_denominator"], 4096)
        self.assertEqual(score["guitar_response_active_energy"]["status"], "complete_attenuation")

    def test_collision_excludes_separation_gate_but_preserves_raw_evidence(self):
        guitar, zero, truth = self.fixture()
        truth["non_identifiable"] = True
        score = self.worker.score(guitar, zero, guitar, guitar, guitar, zero, guitar,
                                  truth, "captured_nr8")
        self.assertFalse(score["fundamental_gate_eligible"])
        self.assertEqual(score["fundamental_eligible_channel_event_denominator"], 0)
        self.assertEqual(score["fundamental_exclusion"], "collision_not_identifiable")
        self.assertEqual(len(score["fundamental_gain_rows"]), 1)
        self.assertEqual(score["metric_scope"], "paired_counterfactual_not_stems")
        self.assertFalse(score["noise_control_is_mixture_residual"])
        self.assertFalse(score["real_stem_recovered"])
        self.assertFalse(score["missing_f0_recovered"])

    def test_zero_reference_remains_unknown_and_clipping_counts_sample_values(self):
        _, zero, truth = self.fixture()
        truth["events"] = []
        truth["fundamental_gain_applicable"] = False
        output = zero.copy()
        output[0:3, 0] = [1, -1.2, .9999]
        score = self.worker.score(zero, zero, zero, output, zero, zero, zero, truth,
                                  "bypass")
        self.assertIsNone(score["guitar_response_energy"]["value_db"])
        self.assertEqual(score["guitar_response_energy"]["status"], "zero_reference")
        self.assertEqual(score["active_sample_frame_denominator"], 0)
        self.assertEqual(score["clipped_sample_values"], 2)
        self.assertEqual(score["sample_value_denominator"], 4096)


if __name__ == "__main__":
    unittest.main()
