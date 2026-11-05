"""Every guitar consumer of `timeline.no_time_stretch` refuses a condense run and a narration run
(docs/spec/TIMELINE_CONTRACT.md, with its narration amendment).

Two manifests are fed to each consumer's narrowest entry point, first for condense, then (the Narration* classes)
for a narration render that applied no stretch at all:

- the condense manifest, shaped exactly as the contract writes it (`kind: condense_edit`, `sources`,
  `timeline.mapping: edl_v1`, `no_time_stretch: false`, no top-level `source` or `pcm`);
- a hybrid: a guitar take's manifest whose timeline is the condense timeline. Every other field the
  consumer reads first is valid, so the refusal comes from the no-time-stretch check itself.

The narration manifest is built from narrate/tests/fixtures/narration-timeline.json and narration-shape.json,
which narrate/tests/test_contract_shape.py checks against a real zero-stretch render of narrate/render.py: a
renamed key or a dropped no_time_stretch there fails that test, and this matrix reads the same fixtures.

The NarratedVideo* classes run the matrix a third time, once per narrated-video mapping (`narrated_video_v1`,
`avatar_overlay_v1` and `music_bed_v1`, TIMELINE_CONTRACT.md's narrated-video amendment), with an `nv_stage`
manifest whose timeline is narrate/tests/fixtures/narrated-video/<mapping>.json. The stages that write those
manifests land in later lanes; the fixtures fix the shape they must write.

Each case asserts a refusal (an exception, a `False` shape test, a rejected lineage or a rejected evidence
row) and that the run directory holds the same files afterwards. phrase_anchor records the mapping instead
of refusing; it must record `no_time_stretch_verified: false`.

Not exercised dynamically: apply_capture_profile.validate (line 140) runs only after a pinned, authored
capture-profile receipt chain (receipt, profile and parent hashes). Its check is pinned by source text here,
and the same module's verify_render check is exercised dynamically.
"""

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import apply_capture_profile  # noqa: E402
import arrangement_markers  # noqa: E402
import arrangement_reference  # noqa: E402
import basic_pitch_compare  # noqa: E402
import capture_profile  # noqa: E402
import dag  # noqa: E402
import guitar_features  # noqa: E402
import marked_compact  # noqa: E402
import meter  # noqa: E402
import phrase_anchor  # noqa: E402
import rhythm  # noqa: E402
import tonal  # noqa: E402
import web_jobs  # noqa: E402

NARRATE_FIXTURES = ROOT / "narrate" / "tests" / "fixtures"
NARRATION_TIMELINE = json.loads((NARRATE_FIXTURES / "narration-timeline.json").read_text())
NARRATION_SHAPE = json.loads((NARRATE_FIXTURES / "narration-shape.json").read_text())
NV_MAPPINGS = ("narrated_video_v1", "avatar_overlay_v1", "music_bed_v1")
NV_TIMELINES = {m: json.loads((NARRATE_FIXTURES / "narrated-video" / f"{m}.json").read_text()) for m in NV_MAPPINGS}
NV_STAGES = {"narrated_video_v1": "place", "avatar_overlay_v1": "avatar", "music_bed_v1": "music"}
PCM = {"sample_rate": 48000, "channels": 1, "sample_count": 48000, "codec": "pcm_s16le"}
EDL_SHA = "e" * 64


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha(path: Path) -> str:
    return sha(path.read_bytes())


def condense_timeline(**extra):
    return {"mapping": "edl_v1", "no_time_stretch": False, "edl": {"file": "edl.json", "sha256": EDL_SHA},
            "fps": 30, "total_frames": 49, "clips": [{"name": "talk", "shift_seconds": 0.1}], **extra}


def condense_manifest(run_dir: Path, outputs: dict) -> dict:
    """The contract's condense manifest."""
    return {"schema_version": 1, "kind": "condense_edit", "status": "rendered_unreviewed",
            "run_id": run_dir.name, "run_dir": str(run_dir),
            "sources": [{"clip": "talk", "path": str(run_dir / "talk.mov"), "sha256": "a" * 64}],
            "output_sha256": {"edl.json": EDL_SHA, **outputs}, "timeline": condense_timeline(),
            "delivery": {"file": "edl.json", "audio_sample_rate": 48000, "audio_channels": 1, "video_frames": 49}}


def narration_timeline(**extra):
    """A real render's timeline (narration-timeline.json) that stretched nothing: still no_time_stretch false."""
    timeline = json.loads(json.dumps(NARRATION_TIMELINE))
    timeline["edl"]["sha256"] = EDL_SHA
    return {**timeline, **extra}


def narration_manifest(run_dir: Path, outputs: dict) -> dict:
    """The narration amendment's manifest (narrate/render.py), with zero applied stretch."""
    return {"schema_version": 1, "kind": "narration_render", "status": "rendered_unreviewed", "synthetic": True,
            "run_id": run_dir.name, "run_dir": str(run_dir),
            "input": {"kind": "Markdown", "sha256": "a" * 64, "ir_file": "ir.json", "ir_sha256": "d" * 64},
            "output_sha256": {"narration.edl.json": EDL_SHA, **outputs}, "timeline": narration_timeline(),
            "flags": []}


def nv_timeline_for(mapping):
    """A narrated-video stage timeline (narrate/tests/fixtures/narrated-video/<mapping>.json)."""
    def timeline(**extra):
        return {**json.loads(json.dumps(NV_TIMELINES[mapping]).replace("0" * 64, EDL_SHA)), **extra}
    return timeline


def nv_manifest_for(mapping):
    """The narrated-video amendment's stage manifest: kind nv_stage, synthetic, no top-level source or pcm."""
    def manifest(run_dir: Path, outputs: dict) -> dict:
        return {"schema_version": 1, "kind": "nv_stage", "stage": NV_STAGES[mapping], "segment": None,
                "status": "rendered_unreviewed", "synthetic": True, "run_id": run_dir.name, "run_dir": str(run_dir),
                "output_sha256": {"stage.json": EDL_SHA, **outputs}, "timeline": nv_timeline_for(mapping)()}
    return manifest


def hybrid_manifest(run_dir: Path, source_sha: str, outputs: dict, timeline=condense_timeline, **extra) -> dict:
    """A guitar take's manifest carrying a foreign timeline (with the guitar origin fields kept)."""
    return {"schema_version": 1, "status": "rendered_unreviewed", "run_id": run_dir.name, "run_dir": str(run_dir),
            "source": {"path": str(run_dir / "take.mov"), "sha256": source_sha},
            "outputs": {"source": "source.wav"}, "output_sha256": outputs, "pcm": dict(PCM),
            "timeline": timeline(audio_start_seconds=0.0, format_start_seconds=0.0), **extra}


def write_json(path: Path, value) -> str:
    path.write_text(json.dumps(value))
    return file_sha(path)


def listing(directory: Path) -> dict:
    return {str(p.relative_to(directory)): p.read_bytes() for p in sorted(directory.rglob("*")) if p.is_file()}


class ContractCase(unittest.TestCase):
    # The foreign mapping every case feeds the guitar consumers: condense here, narration in the Narration*
    # subclasses below (TIMELINE_CONTRACT.md, narration amendment).
    foreign_manifest = staticmethod(condense_manifest)
    foreign_timeline = staticmethod(condense_timeline)

    def hybrid(self, run_dir, source_sha, outputs, **extra):
        return hybrid_manifest(run_dir, source_sha, outputs, timeline=self.foreign_timeline, **extra)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.run = self.root / "20261015T000000Z-condense"
        self.run.mkdir()
        self.denoised = self.run / "denoised.wav"
        self.denoised.write_bytes(b"fixture opaque derivative bytes")
        self.identity = file_sha(self.denoised)
        self.original = "b" * 64

    def tearDown(self):
        self.tmp.cleanup()

    def refuses(self, call, *errors, regex=None):
        """`call` raises one of `errors` (matching `regex`) and leaves the run directory unchanged."""
        before = listing(self.root)
        with self.assertRaises(errors or (Exception,)) as caught:
            call()
        if regex:
            self.assertRegex(str(caught.exception), regex)
        self.assertEqual(listing(self.root), before)
        return caught.exception


class RunDirConsumers(ContractCase):
    def test_rhythm_input_timeline(self):
        metadata = {"audio": {"start_time": "0.0", "sample_rate": "48000", "channels": 1}}
        write_json(self.run / "manifest.json", self.foreign_manifest(self.run, {"denoised.wav": self.identity}))
        self.refuses(lambda: rhythm.input_timeline(self.denoised, self.identity, metadata, self.run), ValueError)
        write_json(self.run / "manifest.json", self.hybrid(self.run, self.original, {"denoised.wav": self.identity}))
        self.refuses(lambda: rhythm.input_timeline(self.denoised, self.identity, metadata, self.run), ValueError,
                     regex="does not establish an unchanged time scale")

    def test_tonal_build(self):
        write_json(self.run / "analysis.json", {"source": {"sha256": self.identity}})
        write_json(self.run / "manifest.json", self.foreign_manifest(self.run, {"denoised.wav": self.identity}))
        self.refuses(lambda: tonal.build(self.run), ValueError)
        write_json(self.run / "manifest.json", self.hybrid(self.run, self.original, {"denoised.wav": self.identity}))
        self.refuses(lambda: tonal.build(self.run), ValueError, regex="requires manifest no_time_stretch")

    def meter_analysis(self, manifest_hash):
        return {"source": {"path": str(self.denoised), "sha256": self.identity},
                "timeline": {"audio_stream_start_seconds": 0.0},
                "source_lineage": {"status": "hash_bound_run_derivative", "manifest_sha256": manifest_hash,
                                   "original_source_sha256": self.original, "analyzed_input_sha256": self.identity,
                                   "original_audio_start_seconds": 0.0, "sample_mapping": {"no_time_stretch": True}}}

    def test_meter_analyze_run(self):
        digest = write_json(self.run / "manifest.json", self.foreign_manifest(self.run, {}))
        write_json(self.run / "analysis.json", self.meter_analysis(digest))
        self.refuses(lambda: meter.analyze_run(self.run), ValueError)
        digest = write_json(self.run / "manifest.json",
                            self.hybrid(self.run, self.original, {"denoised.wav": self.identity}))
        write_json(self.run / "analysis.json", self.meter_analysis(digest))
        self.refuses(lambda: meter.analyze_run(self.run), ValueError, regex="no-stretch provenance differs")

    def test_basic_pitch_compare_build(self):
        write_json(self.run / "manifest.json", self.foreign_manifest(self.run, {"denoised.wav": self.identity}))
        self.refuses(lambda: basic_pitch_compare.build(self.run, {}), ValueError)
        write_json(self.run / "manifest.json", self.hybrid(self.run, self.original, {"denoised.wav": self.identity}))
        self.refuses(lambda: basic_pitch_compare.build(self.run, {}), ValueError,
                     regex="no-time-stretch source mapping")

    def test_guitar_features_inherit_manifest_lineage(self):
        def lineage():
            result = {"source": {"sha256": self.identity, "audio_stream_start_seconds": 0.0, "sample_rate": 48000,
                                 "channels": 1}, "analysis": {"duration_seconds": 1.0}}
            guitar_features.inherit_manifest_lineage(result, self.run)
            return result["lineage"]

        write_json(self.run / "manifest.json", self.foreign_manifest(self.run, {"denoised.wav": self.identity}))
        self.assertEqual(lineage()["manifest_status"], "rejected")
        write_json(self.run / "manifest.json", self.hybrid(self.run, self.original, {"denoised.wav": self.identity}))
        got = lineage()
        self.assertEqual((got["status"], got["manifest_status"], got["manifest_rejection_reason"]),
                         ("input_stream_timeline", "rejected", "canonical_timeline_not_verified"))

    def test_dag_select_evidence(self):
        def selected(manifest):
            digest = write_json(self.run / "manifest.json", manifest)
            write_json(self.run / "clicks.json", {
                "schema_version": 1, "events": [], "identity_status": "unknown", "source": {"sha256": self.identity},
                "source_lineage": {"status": "hash_bound_run_derivative", "manifest_sha256": digest,
                                   "original_source_sha256": self.original, "analyzed_input_sha256": self.identity}})
            return lambda: dag.select_evidence(self.run, manifest, {"clicks": "clicks.json"})

        self.refuses(selected(self.foreign_manifest(self.run, {"denoised.wav": self.identity})), KeyError)
        hybrid = selected(self.hybrid(self.run, self.original, {"denoised.wav": self.identity}))
        before = listing(self.root)
        rows, verified, _, _ = hybrid()
        self.assertEqual(listing(self.root), before)
        self.assertEqual(rows["clicks"]["status"], "rejected_missing_source_time_mapping")
        self.assertNotIn("clicks", verified)

    def test_arrangement_markers_build(self):
        reference_path = ROOT / arrangement_markers.REFERENCE
        reference = json.loads(reference_path.read_text())
        original = reference["source_sha256"]

        def build_with(manifest):
            manifest_hash = write_json(self.run / "manifest.json", manifest)
            analysis_hash = write_json(self.run / "analysis.json", {"schema_version": 1})
            phrases_hash = write_json(self.run / "phrases.json", {"schema_version": 1})
            recorded = {"path": arrangement_markers.REFERENCE, "sha256": file_sha(reference_path)}
            write_json(self.run / "assessment.json", {
                "schema_version": 1, "tool": "arrangement_reference", "source_sha256": original,
                "analyzed_input_sha256": self.identity, "reference": recorded,
                "binding": {"analyzed_input_sha256": self.identity, "reference": recorded,
                            "input_hashes": {"manifest.json": manifest_hash, "analysis.json": analysis_hash,
                                             "phrases.json": phrases_hash, "denoised.wav": self.identity},
                            "manifest": {"path": str(self.run / "manifest.json"), "sha256": manifest_hash},
                            "analysis": {"path": str(self.run / "analysis.json"), "sha256": analysis_hash},
                            "phrases": {"path": str(self.run / "phrases.json"), "sha256": phrases_hash}}})
            return lambda: arrangement_markers.build(self.run, "assessment.json")

        self.refuses(build_with(self.foreign_manifest(self.run, {"denoised.wav": self.identity})), KeyError, ValueError)
        self.refuses(build_with(self.hybrid(self.run, original, {"denoised.wav": self.identity})), ValueError,
                     regex="Unchanged source time scale required")


class ManifestConsumers(ContractCase):
    def test_arrangement_reference_observations_from_run(self):
        analysis = {"source": {"sha256": self.identity}}
        condense = self.foreign_manifest(self.run, {"denoised.wav": self.identity})
        self.refuses(lambda: arrangement_reference.observations_from_run(condense, analysis, {}, "c" * 64),
                     KeyError, ValueError)
        hybrid = self.hybrid(self.run, self.original, {"denoised.wav": self.identity})
        self.refuses(lambda: arrangement_reference.observations_from_run(hybrid, analysis, {}, "c" * 64),
                     ValueError, regex="native no-stretch mapping required")

    def test_web_jobs_baseline_shape(self):
        hybrid = self.hybrid(self.run, self.original, {"source.wav": self.identity})
        self.assertFalse(web_jobs.WebJobs._baseline_shape(self.foreign_manifest(self.run, {})))
        self.assertFalse(web_jobs.WebJobs._baseline_shape(hybrid))
        hybrid["timeline"] = {"no_time_stretch": True, "audio_start_seconds": 0.0}
        self.assertTrue(web_jobs.WebJobs._baseline_shape(hybrid))

    def test_marked_compact_branch_gate(self):
        source = self.original
        export = {"source_sha256": source, "verification": {
            **{key: True for key in marked_compact.EXPORT_TRUE},
            "video_packet_expected_translation_seconds": 0, "physical_audio_video_sync_verified": False}}
        preview = {"status": "marked_review_preview_verified_unreviewed", "marker_mode": "arrangement_reference_review",
                   "source_sha256": source, "arrangement_marker_selector": "markers.json",
                   "arrangement_marker_bindings": {key: source for key in marked_compact.BINDING_KEYS},
                   "source_container_start_seconds": 0, "verification": {
                       **{key: True for key in marked_compact.PREVIEW_TRUE}, "physical_audio_video_sync_verified": False,
                       "decoded_video_frame_count": 30, "decoded_video_last_extent_seconds": 1.0,
                       "decoded_video_first_pts_seconds": 0}}
        hybrid = self.hybrid(self.run, source, {})
        condense = self.foreign_manifest(self.run, {})
        self.refuses(lambda: marked_compact.branch_gate(condense, export, preview, hybrid, "markers.json"),
                     marked_compact.CompactError)
        error = self.refuses(lambda: marked_compact.branch_gate(hybrid, export, preview, hybrid, "markers.json"),
                             marked_compact.CompactError, regex="audio branch lacks no-time-stretch mapping")
        self.assertEqual(error.code, "nonzero_origin_unsupported")

    def test_phrase_anchor_records_the_mapping_unverified(self):
        def grid(mapping):
            return phrase_anchor.parse_grid({
                "schema_version": 1, "source": {"sha256": self.identity},
                "click_grid": {"period_seconds": 0.5, "phase_seconds_audio_relative": 0.0, "observed_events": []},
                "timeline": {"audio_stream_start_seconds": 0.0}, "pcm": {"duration_seconds": 10.0},
                "source_lineage": {"analyzed_input_sha256": self.identity, "sample_mapping": mapping}})

        self.assertIs(grid({"no_time_stretch": False, "mapping": self.foreign_timeline()["mapping"]})
                      ["no_time_stretch_verified"], False)
        self.assertIs(grid({})["no_time_stretch_verified"], False)
        self.assertIs(grid({"no_time_stretch": True})["no_time_stretch_verified"], True)


class CaptureConsumers(ContractCase):
    def setUp(self):
        super().setUp()
        self.workspace = self.root / "workspace"
        self.runs = self.workspace / "artifacts" / "runs"
        self.take = self.runs / "20261015T000000Z-take"
        self.take.mkdir(parents=True)
        self.input = self.workspace / "take.mov"
        self.input.write_bytes(b"fixture take bytes")
        (self.take / "source.wav").write_bytes(b"fixture native pcm bytes")
        self.review = self.take / "review.json"
        self.review.write_text("{}")

    def take_manifest(self, timeline):
        return {"schema_version": 1, "status": "rendered_unreviewed", "run_id": self.take.name,
                "run_dir": str(self.take), "source": {"path": str(self.input), "sha256": file_sha(self.input)},
                "outputs": {"source": "source.wav"},
                "output_sha256": {"source.wav": file_sha(self.take / "source.wav")},
                "pcm": dict(PCM), "timeline": timeline, "profile": "fuller", "threads": 2}

    def test_capture_profile_author(self):
        settings = dict(capture_start_seconds=0.0, capture_end_seconds=1.0, reduction_db=6.0, noise_floor_db=-50.0,
                        adaptivity=0.5, gain_smooth=8, integrated_lufs=-18.0, true_peak_dbtp=-1.5)

        def author():
            return capture_profile.author(self.input, self.take, self.review, **settings)

        with mock.patch.object(capture_profile, "ROOT", self.workspace):
            write_json(self.take / "manifest.json", self.foreign_manifest(self.take, {}))
            self.refuses(author, capture_profile.CaptureError, regex="provenance object")
            write_json(self.take / "manifest.json",
                       self.take_manifest(self.foreign_timeline(audio_start_seconds=0.0)))
            self.refuses(author, capture_profile.CaptureError, regex="native source sample mapping is unavailable")

    def test_apply_capture_profile_verify_render(self):
        state = {"source": self.input, "receipt": {"source": {"sha256": file_sha(self.input)}}, "profile": "fuller",
                 "native": {key: PCM[key] for key in ("sample_rate", "channels", "sample_count")}, "origin": 0.0}
        deadline = capture_profile.Deadline(60)

        def verify(manifest):
            write_json(self.take / "manifest.json", manifest)
            return lambda: apply_capture_profile.verify_render(manifest, state, self.workspace, deadline)

        self.refuses(verify(self.foreign_manifest(self.take, {})), apply_capture_profile.ApplyError)
        self.refuses(verify(self.take_manifest(self.foreign_timeline(audio_start_seconds=0.0))),
                     apply_capture_profile.ApplyError, regex="render changed verified native time axis")

    def test_apply_capture_profile_validate_keeps_its_check(self):
        text = (ROOT / "scripts" / "apply_capture_profile.py").read_text()
        self.assertIn('fail(timeline.get("no_time_stretch") is not True, '
                      '"verified no-time-stretch native mapping is required")', text)



class NarrationRow:
    """The refusal-matrix row for a narration manifest with zero applied stretch: every case above, again."""

    foreign_manifest = staticmethod(narration_manifest)
    foreign_timeline = staticmethod(narration_timeline)


class NarrationRunDirConsumers(NarrationRow, RunDirConsumers):
    pass


class NarrationManifestConsumers(NarrationRow, ManifestConsumers):
    pass


class NarrationCaptureConsumers(NarrationRow, CaptureConsumers):
    pass


# One row per narrated-video mapping, over each consumer group: NarratedVideo_<mapping>_<group>.
for _mapping in NV_MAPPINGS:
    for _group in (RunDirConsumers, ManifestConsumers, CaptureConsumers):
        _name = f"NarratedVideo_{_mapping}_{_group.__name__}"
        globals()[_name] = type(_name, (_group,), {"foreign_manifest": staticmethod(nv_manifest_for(_mapping)),
                                                   "foreign_timeline": staticmethod(nv_timeline_for(_mapping))})
del _mapping, _group, _name


class NarratedVideoManifestShape(unittest.TestCase):
    def test_every_mapping_says_no_time_stretch_false_and_is_never_identity(self):
        for mapping in NV_MAPPINGS:
            manifest = nv_manifest_for(mapping)(Path("/run"), {})
            self.assertEqual(manifest["timeline"]["mapping"], mapping)
            self.assertIs(manifest["timeline"]["no_time_stretch"], False)
            self.assertIn("stretch_applied", manifest["timeline"])
            self.assertTrue(manifest["timeline"]["output_axis"] and manifest["timeline"]["source_axis"])
            self.assertEqual((manifest["kind"], manifest["synthetic"]), ("nv_stage", True))
            self.assertNotIn("source", manifest)
            self.assertNotIn("pcm", manifest)

    def test_the_mappings_are_new_names(self):
        self.assertEqual(len(set(NV_MAPPINGS)), 3)
        self.assertTrue(set(NV_MAPPINGS).isdisjoint({"identity", "edl_v1", "narration_v1"}))
        rows = [name for name in globals() if name.startswith("NarratedVideo_")]
        self.assertEqual(len(rows), 9)


class NarrationManifestShape(unittest.TestCase):
    def test_the_matrix_manifest_uses_the_rendered_shape(self):
        manifest = narration_manifest(Path("/run"), {})
        self.assertLessEqual(set(manifest), set(NARRATION_SHAPE["manifest_keys"]))
        self.assertEqual(sorted(manifest["timeline"]), NARRATION_SHAPE["timeline_keys"])
        self.assertEqual(manifest["timeline"]["edl"]["file"], "narration.edl.json")

    def test_a_render_with_no_stretch_still_says_no_time_stretch_false(self):
        manifest = narration_manifest(Path("/run"), {})
        self.assertIs(manifest["timeline"]["no_time_stretch"], False)
        self.assertIs(manifest["timeline"]["stretch_applied"], False)
        self.assertNotIn(manifest["timeline"]["mapping"], (None, "identity"))
        self.assertNotIn("source", manifest)
        self.assertNotIn("pcm", manifest)


if __name__ == "__main__":
    unittest.main()
