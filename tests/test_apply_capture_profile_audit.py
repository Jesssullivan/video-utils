"""Independent refusal checks; constructed provenance and mocked DSP only."""
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "application_owner_fixtures_for_audit", ROOT / "tests/test_apply_capture_profile.py")
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)


class ApplicationEvidenceAuditTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ApplyCaptureProfileTests()
        self.fixture.setUp()
        self.worker = fixtures.worker

    def tearDown(self):
        self.fixture.tearDown()

    def video_clean(self, *args):
        manifest = self.fixture.mock_clean(*args)
        manifest["source"]["probe"]["video"] = {"index": 0, "codec_name": "fixture"}
        fixtures.fixtures.dump(Path(manifest["run_dir"]) / "manifest.json", manifest)
        return manifest

    def video_export(self, directory):
        outcome = self.fixture.mock_export(directory)
        directory = Path(directory)
        video = directory / "export/cleaned-video.mov"
        video.write_bytes(b"inert constructed export identity; no media codec")
        outcome.update(video=str(video), output_sha256={"cleaned-video.mov": fixtures.fixtures.sha(video)},
            verification={"source_hash_verified": True, "video_frame_count_preserved": True,
                "relative_audio_video_start_verified": True, "dsp_latency_compensation_recorded": True,
                "final_true_peak_within_target": True, "physical_audio_video_sync_verified": False})
        return outcome

    def reject(self):
        with self.assertRaises(self.worker.ApplyError):
            self.fixture.apply()
        self.fixture.assert_no_new_run()
        self.fixture.assert_baseline_and_owner_preserved()

    def test_video_without_each_required_verification_abstains(self):
        self.fixture.clean.side_effect = self.video_clean
        for field in ("source_hash_verified", "video_frame_count_preserved",
                      "relative_audio_video_start_verified", "dsp_latency_compensation_recorded",
                      "final_true_peak_within_target"):
            def incomplete(directory, field=field):
                outcome = self.video_export(directory)
                outcome["verification"].pop(field)
                fixtures.fixtures.dump(Path(directory) / "export/outcome.json", outcome)
                return outcome
            with self.subTest(field=field):
                self.fixture.export.side_effect = incomplete
                self.reject()

    def test_changed_video_bytes_after_export_receipt_abstains(self):
        self.fixture.clean.side_effect = self.video_clean
        def changed(directory):
            outcome = self.video_export(directory)
            fixtures.fixtures.dump(Path(directory) / "export/outcome.json", outcome)
            Path(outcome["video"]).write_bytes(b"changed after verification")
            return outcome
        self.fixture.export.side_effect = changed
        self.reject()

    def test_invented_physical_sync_acceptance_abstains(self):
        self.fixture.clean.side_effect = self.video_clean
        def promoted(directory):
            outcome = self.video_export(directory)
            outcome["verification"]["physical_audio_video_sync_verified"] = True
            fixtures.fixtures.dump(Path(directory) / "export/outcome.json", outcome)
            return outcome
        self.fixture.export.side_effect = promoted
        self.reject()

    def test_uncalibrated_or_uncompensated_delay_abstains_before_export(self):
        for change in ({"status": "unknown"}, {"remaining_bulk_delay_samples": 1}):
            def drifted(*args, change=change):
                manifest = self.fixture.mock_clean(*args)
                manifest["dsp_latency"]["denoise"].update(change)
                fixtures.fixtures.dump(Path(manifest["run_dir"]) / "manifest.json", manifest)
                return manifest
            with self.subTest(change=change):
                self.fixture.clean.side_effect = drifted
                self.reject()
                self.fixture.export.assert_not_called()

    def test_new_decoder_origin_cannot_relabel_the_parent_clock(self):
        def shifted(*args):
            manifest = self.fixture.mock_clean(*args)
            manifest["timeline"]["audio_start_seconds"] += .001
            fixtures.fixtures.dump(Path(manifest["run_dir"]) / "manifest.json", manifest)
            return manifest
        self.fixture.clean.side_effect = shifted
        self.reject()
        self.fixture.export.assert_not_called()

    def test_inspection_and_group_signal_failure_still_reaps_direct_child(self):
        spawned = []
        events = []
        original_popen = self.worker.subprocess.Popen
        def recorded(*args, **kwargs):
            process = original_popen(*args, **kwargs)
            spawned.append(process)
            return process
        try:
            with patch.object(self.worker.subprocess, "Popen", side_effect=recorded), \
                 patch.object(self.worker, "live_group_members", side_effect=OSError("inert inspection failure")), \
                 patch.object(self.worker.os, "killpg", side_effect=PermissionError("inert group signal failure")):
                with self.assertRaises(self.worker.ApplyError) as caught:
                    self.worker.run_owned([sys.executable, "-c", "import time; time.sleep(5)"],
                        deadline=self.worker.Deadline(1), timeout=.05, events=events)
            self.assertEqual(caught.exception.code, "cleanup_failed")
            self.assertEqual(len(spawned), 1)
            self.assertIsNotNone(spawned[0].poll(), "owned direct child must be reaped")
            self.assertEqual(events[-1]["result"], "direct_child_reaped_descendant_absence_unverified")
            self.assertTrue(events[-1]["signal_errors"])
            self.assertIn("direct_child_kill_if_running", events[-1]["signals"])
            self.assert_no_media_launched()
        finally:
            # Only direct Popen children recorded by this fixture are owned here.
            for process in spawned:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=1)

    def assert_no_media_launched(self):
        self.fixture.clean.assert_not_called()
        self.fixture.export.assert_not_called()
        self.fixture.assert_no_new_run()
        self.fixture.assert_baseline_and_owner_preserved()

    def test_post_commit_fault_cannot_claim_no_candidate_was_published(self):
        original_publish = self.worker.publish_directory
        committed = []
        def publish_then_interrupt(staging, final):
            original_publish(staging, final)
            if Path(final).parent == self.fixture.f.root / "artifacts/runs":
                committed.append(Path(final))
                raise self.worker.ApplyError("inert fault immediately after atomic publication", "deadline_exceeded")
        with patch.object(self.worker, "publish_directory", side_effect=publish_then_interrupt):
            with self.assertRaises(self.worker.ApplyError) as caught:
                self.fixture.apply()
        self.assertEqual(len(committed), 1)
        final = committed[0]
        self.assertTrue((final / "manifest.json").is_file())
        self.assertTrue((final / "application-receipt.json").is_file())
        self.assertEqual(list(self.fixture.f.root.glob("artifacts/.capture-apply-*")), [])
        failure = json.loads(Path(caught.exception.failure_receipt_path).read_text())
        self.assertNotEqual(failure["status"], "failed_no_candidate_published",
                            "a committed candidate exists; failure evidence must report that fact")
        self.assertNotIn("no success candidate", failure.get("result", ""))
        self.assertEqual(failure["candidate_publication"], "committed_unreviewed")
        recovered = caught.exception.committed_candidate
        self.assertEqual(recovered["run_dir"], str(final))
        self.assertEqual(recovered["manifest_sha256"], fixtures.fixtures.sha(final / "manifest.json"))
        self.assertEqual(recovered["receipt_sha256"], fixtures.fixtures.sha(final / "application-receipt.json"))
        self.assertEqual(recovered["export"]["outcome_sha256"], fixtures.fixtures.sha(final / "export/outcome.json"))
        self.fixture.assert_baseline_and_owner_preserved()

    def test_cli_reporting_fault_retains_the_committed_candidate_path(self):
        if self.worker.signal.getitimer(self.worker.signal.ITIMER_REAL) != (0., 0.):
            self.skipTest("another owner has a process timer")
        writes = []
        def interrupted_print(value, *args, **kwargs):
            if not writes:
                self.assertEqual(self.worker.signal.getitimer(self.worker.signal.ITIMER_REAL), (0., 0.),
                                 "processing deadline must be disarmed before the first result report")
                writes.append(None)
                raise self.worker.ApplyError("inert console interruption after apply returned", "deadline_exceeded")
            writes.append(value)
        argv = [str(self.fixture.f.source), "--authoring-dir", str(self.fixture.authoring_dir),
                "--receipt-sha256", self.fixture.receipt_pin]
        with patch.object(self.worker, "print", side_effect=interrupted_print, create=True):
            returned = self.worker.main(argv)
        candidates = [p for p in (self.fixture.f.root / "artifacts/runs").iterdir()
                      if p.name not in (self.fixture.f.run.name, self.fixture.owner_run.name)]
        self.assertEqual(len(candidates), 1)
        self.assertTrue((candidates[0] / "application-receipt.json").is_file())
        self.assertEqual(returned, 2)
        self.assertTrue(writes[-1])
        self.assertIn(str(candidates[0]), writes[-1],
                      "post-commit CLI error must preserve the published candidate identity")
        report = json.loads(writes[-1])
        self.assertEqual(report["candidate_publication"], "committed_unreviewed")
        recovered = report["committed_candidate"]
        for slot, relative in (("manifest", "manifest.json"), ("receipt", "application-receipt.json"),
                               ("export_outcome", "export/outcome.json")):
            self.assertEqual(recovered[slot], {"relative_path": relative,
                                             "sha256": fixtures.fixtures.sha(candidates[0] / relative)})
        self.assertFalse(recovered["listening_accepted"])
        self.assertFalse(recovered["master_adopted"])
        self.assertEqual(self.worker.signal.getitimer(self.worker.signal.ITIMER_REAL), (0., 0.))
        self.fixture.assert_baseline_and_owner_preserved()

    def test_unobservable_post_rename_identity_cannot_assert_publication_absence(self):
        original_publish = self.worker.publish_directory
        original_stat = Path.stat
        moved = []
        def publish_then_hide_identity(staging, final):
            original_publish(staging, final)
            if Path(final).parent == self.fixture.f.root / "artifacts/runs":
                moved.append(Path(final))
        def inaccessible_candidate_stat(selected, *args, **kwargs):
            if moved and selected == moved[0]:
                raise OSError("inert observation failure after the owned directory moved")
            return original_stat(selected, *args, **kwargs)
        with patch.object(self.worker, "publish_directory", side_effect=publish_then_hide_identity), \
             patch.object(Path, "stat", inaccessible_candidate_stat):
            with self.assertRaises(self.worker.ApplyError) as caught:
                self.fixture.apply()
        self.assertEqual(len(moved), 1)
        final = moved[0]
        self.assertTrue((final / "manifest.json").is_file())
        self.assertTrue((final / "application-receipt.json").is_file())
        failure = json.loads(Path(caught.exception.failure_receipt_path).read_text())
        self.assertEqual(failure["status"], "publication_outcome_unknown",
                         "failed immediate observation cannot prove an atomic rename did not commit")
        self.assertEqual(failure["candidate_publication"], "unknown_after_publish_attempt")
        self.assertIsNone(failure["committed_candidate"])
        possible = failure["possible_candidate"]
        self.assertEqual(possible["run_dir"], str(final))
        for slot, relative in (("manifest", "manifest.json"), ("receipt", "application-receipt.json"),
                               ("export_outcome", "export/outcome.json")):
            self.assertEqual(possible[slot], {"relative_path": relative,
                                            "sha256": fixtures.fixtures.sha(final / relative)})
        self.assertFalse(possible["listening_accepted"])
        self.assertFalse(possible["master_adopted"])
        diagnostic = self.worker.error_diagnostic(caught.exception, None)
        self.assertEqual(diagnostic["candidate_publication"], "unknown_after_publish_attempt")
        self.assertEqual(diagnostic["possible_candidate"], possible)
        self.fixture.assert_baseline_and_owner_preserved()


if __name__ == "__main__":
    unittest.main()
