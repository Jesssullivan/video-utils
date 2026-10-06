"""Application provenance and atomic-publication fixtures with mocked media DSP."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
import uuid
import wave

REPO = Path(__file__).resolve().parents[1]
fixture_spec = importlib.util.spec_from_file_location("apply_capture_fixtures", REPO / "tests/test_capture_profile.py")
fixtures = importlib.util.module_from_spec(fixture_spec)
fixture_spec.loader.exec_module(fixtures)
worker_spec = importlib.util.spec_from_file_location("apply_capture_worker", REPO / "scripts/apply_capture_profile.py")
worker = importlib.util.module_from_spec(worker_spec)
worker_spec.loader.exec_module(worker)


class ApplyCaptureProfileTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.CaptureProfileTests()
        self.fixture.setUp()
        self.f = self.fixture
        self.root_patch = patch.object(worker, "ROOT", self.f.root)
        self.root_patch.start()
        self.capture_root_patch = patch.object(worker.capture, "ROOT", self.f.root)
        self.capture_root_patch.start()
        self.authored = self.f.author()
        self.authoring_dir = Path(self.authored["output_dir"])
        self.receipt_path = Path(self.authored["receipt_path"])
        self.receipt_pin = self.authored["receipt_sha256"]
        self.source_sha = fixtures.sha(self.f.source)
        self.media_root_before = worker.media.ROOT
        self.owner_run = self.f.root / "artifacts/runs/existing-owner-render"
        self.owner_run.mkdir()
        self.owner_master = self.owner_run / "cleaned.wav"
        self.owner_master.write_bytes(b"existing owned master sentinel")
        self.clean_patch = patch.object(worker.media, "clean", side_effect=self.mock_clean)
        self.export_patch = patch.object(worker.media, "export", side_effect=self.mock_export)
        self.clean = self.clean_patch.start()
        self.export = self.export_patch.start()

    def tearDown(self):
        self.export_patch.stop()
        self.clean_patch.stop()
        self.root_patch.stop()
        self.capture_root_patch.stop()
        self.fixture.tearDown()

    def apply(self, **changes):
        args = {"input_value": str(self.f.source), "authoring_dir_value": str(self.authoring_dir),
                "receipt_sha256": self.receipt_pin}
        args.update(changes)
        return worker.apply(**args)

    def mock_clean(self, source, profile):
        source, profile = Path(source), Path(profile)
        # Processing must target an owned private workspace, never the shared
        # active run root before export and post-stage verification succeed.
        self.assertNotEqual(worker.media.ROOT, self.f.root)
        self.assertEqual(worker.media.THREADS, "2")
        run_id = "mock-render-" + uuid.uuid4().hex
        directory = worker.media.ROOT / "artifacts/runs" / run_id
        directory.mkdir(parents=True)
        outputs = {name: name + ".wav" for name in ("source", "denoised", "baseline", "cleaned", "residue")}
        parsed_profile = json.loads(profile.read_text())
        if worker.media.post_denoise_filters(parsed_profile, self.f.rate):
            outputs["processed"] = "processed.wav"
        for name in outputs.values():
            shutil.copyfile(self.f.pcm, directory / name)
        manifest = {"schema_version": 1, "status": "rendered_unreviewed", "run_id": run_id,
                    "run_dir": str(directory), "profile": parsed_profile,
                    "source": {"path": str(source), "sha256": fixtures.sha(source),
                               "probe": {"video": None,
                                         "audio": {"sample_rate": self.f.rate, "channels": 1,
                                                   "start_time": 7.125, "duration": self.f.count / self.f.rate},
                                         "format": {"start_time": 0, "duration": self.f.count / self.f.rate}}},
                    "pcm": dict(self.f.manifest["pcm"]),
                    "timeline": dict(self.f.manifest["timeline"]), "threads": 2,
                    "noise_capture": {"source_sha256": self.source_sha, "selected_samples": [2000, 10000],
                                      "applies_to_original_start": True, "source_axis_sample_count_preserved": True,
                                      "noise_only_verified_by_worker": False},
                    "outputs": outputs,
                    "output_sha256": {name: fixtures.sha(directory / name) for name in outputs.values()},
                    "dsp_latency": {"denoise": {"status": "measured_and_compensated", "delay_samples": 400,
                                                "remaining_bulk_delay_samples": 0}},
                    "commands": []}
        fixtures.dump(directory / "manifest.json", manifest)
        return manifest

    def mock_export(self, value):
        directory = Path(value)
        manifest = json.loads((directory / "manifest.json").read_text())
        export = directory / "export"
        export.mkdir()
        outcome = {"schema_version": 1, "status": "exported_unreviewed", "run_dir": str(directory),
                   "audio_master": str(directory / "cleaned.wav"), "video": None,
                   "source_sha256": manifest["source"]["sha256"], "listening_accepted": False,
                   "output_sha256": {}, "commands": []}
        fixtures.dump(export / "outcome.json", outcome)
        return outcome

    def assert_baseline_and_owner_preserved(self):
        self.assertEqual(self.owner_master.read_bytes(), b"existing owned master sentinel")
        self.assertEqual(fixtures.sha(self.f.source), self.source_sha)
        self.assertEqual(worker.media.ROOT, self.media_root_before)

    def assert_no_new_run(self):
        runs = self.f.root / "artifacts/runs"
        self.assertEqual({path.name for path in runs.iterdir()}, {self.f.run.name, self.owner_run.name})
        self.assertEqual(list(self.f.root.rglob(".apply-staging-*")), [])
        self.assertEqual(list(self.f.root.rglob(".capture-apply-*")), [])

    def rewrite_receipt(self, modify):
        data = json.loads(self.receipt_path.read_text())
        modify(data)
        fixtures.dump(self.receipt_path, data)
        self.receipt_pin = fixtures.sha(self.receipt_path)

    def test_success_is_fresh_and_rewrites_private_paths_after_verified_export(self):
        before = {path: fixtures.sha(path) for path in (self.f.source, self.f.pcm, self.receipt_path,
                                                       Path(self.authored["profile_path"]), self.f.manifest_path)}
        result = self.apply()
        self.clean.assert_called_once()
        self.export.assert_called_once()
        directory = Path(result["run_dir"])
        self.assertEqual(directory.parent, self.f.root / "artifacts/runs")
        self.assertNotEqual(directory, self.f.run)
        self.assertFalse(result["listening_accepted"])
        self.assertFalse(result["master_adopted"])
        receipt_path = Path(result["receipt_path"])
        self.assertEqual(fixtures.sha(receipt_path), result["receipt_sha256"])
        self.assertEqual(fixtures.sha(directory / "manifest.json"), result["manifest_sha256"])
        self.assertEqual(fixtures.sha(directory / "export/outcome.json"), result["export"]["outcome_sha256"])
        receipt = json.loads(receipt_path.read_text())
        self.assertEqual(receipt["authoring"]["receipt_sha256"], self.receipt_pin)
        self.assertEqual(receipt["authoring"]["profile_sha256"], self.authored["profile_sha256"])
        manifest = json.loads((directory / "manifest.json").read_text())
        outcome = json.loads((directory / "export/outcome.json").read_text())
        self.assertEqual(manifest["run_dir"], str(directory))
        self.assertEqual(outcome["run_dir"], str(directory))
        self.assertEqual(outcome["audio_master"], str(directory / "cleaned.wav"))
        self.assertEqual(manifest["pcm"], self.f.manifest["pcm"])
        for path, identity in before.items():
            self.assertEqual(fixtures.sha(path), identity)
        self.assert_baseline_and_owner_preserved()

    def test_stale_explicit_receipt_pin_rejects_before_any_media_launch(self):
        with self.assertRaises(worker.ApplyError):
            self.apply(receipt_sha256="f" * 64)
        self.clean.assert_not_called()
        self.export.assert_not_called()
        self.assert_no_new_run()

    def test_changed_source_pcm_review_manifest_or_context_rejects_before_launch(self):
        paths = [self.f.source, self.f.pcm, self.f.review_path, self.f.manifest_path,
                 self.f.root / "program/instrument.json", self.f.root / "program/capture-context.json"]
        for path in paths:
            original = path.read_bytes()
            with self.subTest(path=path.name):
                with path.open("ab") as handle:
                    handle.write(b"\nchanged after authoring")
                with self.assertRaises(worker.ApplyError):
                    self.apply()
                self.clean.assert_not_called()
                self.export.assert_not_called()
                self.assert_no_new_run()
            path.write_bytes(original)

    def test_changed_profile_controls_reject_even_with_valid_media_profile_shape(self):
        profile = Path(self.authored["profile_path"])
        data = json.loads(profile.read_text())
        data["reduction_db"] = 12
        fixtures.dump(profile, data)
        with self.assertRaises(worker.ApplyError):
            self.apply()
        self.clean.assert_not_called()
        self.assert_no_new_run()

    def test_receipt_repin_cannot_change_settings_without_matching_profile(self):
        def modify(data):
            data["settings"]["reduction_db"] = 12
            data["settings_sha256"] = hashlib.sha256(worker.capture.json_bytes(
                data["settings"], worker.capture.MAX_PROFILE_BYTES)).hexdigest()
        self.rewrite_receipt(modify)
        with self.assertRaises(worker.ApplyError):
            self.apply()
        self.clean.assert_not_called()
        self.assert_no_new_run()

    def test_repinned_receipt_with_stale_source_manifest_and_pcm_hashes_rejects(self):
        original = self.receipt_path.read_bytes()
        for section, field in (("source", "sha256"), ("baseline", "manifest_sha256"), ("baseline", "pcm_sha256")):
            with self.subTest(section=section, field=field):
                self.rewrite_receipt(lambda data: data[section].update(**{field: "f" * 64}))
                with self.assertRaises(worker.ApplyError):
                    self.apply()
                self.clean.assert_not_called()
                self.assert_no_new_run()
            self.receipt_path.write_bytes(original)
            self.receipt_pin = fixtures.sha(self.receipt_path)

    def test_identical_bytes_from_another_original_path_are_not_the_selected_source(self):
        other = self.f.root / "same bytes different take.wav"
        shutil.copyfile(self.f.source, other)
        with self.assertRaises(worker.ApplyError):
            self.apply(input_value=str(other))
        self.clean.assert_not_called()
        self.assert_no_new_run()

    def test_authoring_only_and_rejected_capture_never_launch_media(self):
        for changes in ({"authorization_scope": "profile_authoring"}, {"music_status": "reviewed_present"}):
            with self.subTest(changes=changes):
                self.f.reviewed(**changes)
                authored = self.f.author()
                with self.assertRaises(worker.ApplyError):
                    self.apply(authoring_dir_value=authored["output_dir"], receipt_sha256=authored["receipt_sha256"])
                self.clean.assert_not_called()
                self.export.assert_not_called()
                self.assert_no_new_run()

    def test_repeated_application_keeps_both_completed_runs(self):
        first = self.apply()
        first_dir = Path(first["run_dir"])
        original = (first_dir / "manifest.json").read_bytes()
        second = self.apply()
        self.assertNotEqual(first["run_dir"], second["run_dir"])
        self.assertEqual((first_dir / "manifest.json").read_bytes(), original)
        self.assert_baseline_and_owner_preserved()

    def test_optional_tone_stage_requires_separate_processed_artifact(self):
        authored = self.f.author(peaking_eq=[{"frequency_hz": 300, "gain_db": -2, "q": 0.7}])
        result = self.apply(authoring_dir_value=authored["output_dir"], receipt_sha256=authored["receipt_sha256"])
        directory = Path(result["run_dir"])
        manifest = json.loads((directory / "manifest.json").read_text())
        self.assertEqual(manifest["outputs"]["processed"], "processed.wav")
        self.assertTrue((directory / "denoised.wav").is_file())
        self.assertTrue((directory / "residue.wav").is_file())
        self.assertTrue((directory / "processed.wav").is_file())
        self.assert_baseline_and_owner_preserved()

    def test_relative_paths_select_same_bound_input_and_authoring(self):
        with contextlib.chdir(self.f.root):
            result = self.apply(input_value=self.f.source.name,
                                authoring_dir_value=str(self.authoring_dir.relative_to(self.f.root)))
        self.assertEqual(result["source_sha256"], self.source_sha)
        self.assert_baseline_and_owner_preserved()

    def test_path_traversal_is_rejected_before_media_launch(self):
        traversal = str(self.authoring_dir / ".." / self.authoring_dir.name)
        with self.assertRaises(worker.ApplyError):
            self.apply(authoring_dir_value=traversal)
        self.clean.assert_not_called()
        self.assert_no_new_run()

    def test_unknown_source_origin_rejects_before_export_or_processing(self):
        self.f.rebound_manifest(timeline={"audio_start_seconds": None, "no_time_stretch": True})
        authored = self.f.author()
        with self.assertRaises(worker.ApplyError):
            self.apply(authoring_dir_value=authored["output_dir"], receipt_sha256=authored["receipt_sha256"])
        self.clean.assert_not_called()
        self.export.assert_not_called()
        self.assert_no_new_run()

    def test_valid_authoring_above_application_duration_ceiling_never_launches_media(self):
        count = 301 * self.f.rate
        with wave.open(str(self.f.source), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(self.f.rate)
            handle.writeframes(b"\0" * (count * 2))
        shutil.copyfile(self.f.source, self.f.pcm)
        self.f.manifest["source"]["sha256"] = fixtures.sha(self.f.source)
        self.f.rebound_manifest(pcm={"sample_rate": self.f.rate, "channels": 1, "sample_count": count},
                                output_sha256={"source.wav": fixtures.sha(self.f.pcm)})
        self.f.reviewed(source_sha256=fixtures.sha(self.f.source), source_pcm_sha256=fixtures.sha(self.f.pcm),
                        note="Generated silent 301-second fixture verifies the narrower application duration ceiling.")
        authored = self.f.author()
        self.assertEqual(authored["status"], "authored_unrendered")
        with self.assertRaises(worker.ApplyError):
            self.apply(authoring_dir_value=authored["output_dir"], receipt_sha256=authored["receipt_sha256"])
        self.clean.assert_not_called()
        self.export.assert_not_called()
        self.assert_no_new_run()

    def test_source_mutation_by_clean_abstains_and_discards_owned_run(self):
        original_clean = self.mock_clean

        def mutate_then_clean(*args, **kwargs):
            result = original_clean(*args, **kwargs)
            with self.f.source.open("ab") as handle:
                handle.write(b"source changed while rendering")
            return result

        self.clean.side_effect = mutate_then_clean
        with self.assertRaises(worker.ApplyError):
            self.apply()
        self.assert_no_new_run()
        self.assertEqual(worker.media.ROOT, self.media_root_before)
        self.assertEqual(self.owner_master.read_bytes(), b"existing owned master sentinel")

    def test_failed_clean_and_failed_export_restore_root_and_publish_no_partial_run(self):
        for stage in ("clean", "export"):
            with self.subTest(stage=stage):
                self.clean.side_effect = self.mock_clean
                self.export.side_effect = self.mock_export
                complete_partial_stage = self.mock_clean if stage == "clean" else self.mock_export

                def fail_after_owned_files(*args, **kwargs):
                    complete_partial_stage(*args, **kwargs)
                    raise worker.media.MediaError("fixture " + stage + " failure after owned files")

                getattr(self, stage).side_effect = fail_after_owned_files
                with self.assertRaises(worker.ApplyError):
                    self.apply()
                self.assert_no_new_run()
                self.assert_baseline_and_owner_preserved()

    def test_clean_output_native_extent_mismatch_is_not_published(self):
        original_clean = self.mock_clean

        def mismatched(*args, **kwargs):
            manifest = original_clean(*args, **kwargs)
            manifest["pcm"]["sample_count"] += 1
            fixtures.dump(Path(manifest["run_dir"]) / "manifest.json", manifest)
            return manifest

        self.clean.side_effect = mismatched
        with self.assertRaises(worker.ApplyError):
            self.apply()
        self.assert_no_new_run()
        self.assert_baseline_and_owner_preserved()

    def test_exported_master_mutation_fails_post_stage_hash_verification(self):
        original_export = self.mock_export

        def mutate_after_export(directory):
            result = original_export(directory)
            with (Path(directory) / "cleaned.wav").open("ab") as handle:
                handle.write(b"changed during export")
            return result

        self.export.side_effect = mutate_after_export
        with self.assertRaises(worker.ApplyError):
            self.apply()
        self.assert_no_new_run()
        self.assert_baseline_and_owner_preserved()

    def test_context_mutation_during_export_rejects_publication(self):
        original_export = self.mock_export

        def mutate_after_export(directory):
            result = original_export(directory)
            with (self.f.root / "program/capture-context.json").open("ab") as handle:
                handle.write(b"\n ")
            return result

        self.export.side_effect = mutate_after_export
        with self.assertRaises(worker.ApplyError):
            self.apply()
        self.assert_no_new_run()
        self.assert_baseline_and_owner_preserved()

    def test_symlink_authoring_directory_and_receipt_profile_paths_reject(self):
        alias = self.f.run / "capture-profiles/alias"
        alias.symlink_to(self.authoring_dir, target_is_directory=True)
        with self.assertRaises(worker.ApplyError):
            self.apply(authoring_dir_value=str(alias))
        self.clean.assert_not_called()
        for target in ("profile_path",):
            self.rewrite_receipt(lambda data: data.update(**{target: str(self.f.root / "profiles/external.json")}))
            with self.assertRaises(worker.ApplyError):
                self.apply()
            self.clean.assert_not_called()
        self.assert_no_new_run()

    def test_timeout_and_receipt_pin_are_strictly_typed_before_launch(self):
        controls = [{"timeout_seconds": True}, {"timeout_seconds": 0}, {"timeout_seconds": 601},
                    {"receipt_sha256": "A" * 64}, {"receipt_sha256": ""}]
        for change in controls:
            with self.subTest(change=change), self.assertRaises(worker.ApplyError):
                self.apply(**change)
        self.clean.assert_not_called()
        self.assert_no_new_run()

    def test_deadline_expiry_rejects_before_media_launch(self):
        error = worker.ApplyError("fixture application deadline", "deadline_exceeded")
        with patch.object(worker.Deadline, "check", side_effect=error):
            with self.assertRaises(worker.ApplyError) as caught:
                self.apply()
        self.assertEqual(caught.exception.code, "deadline_exceeded")
        self.clean.assert_not_called()
        self.assert_no_new_run()
        self.assert_baseline_and_owner_preserved()

    def test_existing_final_run_rejects_publication_and_preserves_owner_master(self):
        original_clean = self.mock_clean

        def collide(*args, **kwargs):
            manifest = original_clean(*args, **kwargs)
            original = Path(manifest["run_dir"])
            directory = original.parent / self.owner_run.name
            original.rename(directory)
            manifest.update(run_id=directory.name, run_dir=str(directory))
            fixtures.dump(directory / "manifest.json", manifest)
            return manifest

        self.clean.side_effect = collide
        with self.assertRaises(worker.ApplyError):
            self.apply()
        self.assert_no_new_run()
        self.assert_baseline_and_owner_preserved()

    def test_cli_hard_deadline_interrupts_blocked_application_and_restores_signal_state(self):
        previous_timer = signal.getitimer(signal.ITIMER_REAL)
        previous_handler = signal.getsignal(signal.SIGALRM)
        if previous_timer != (0.0, 0.0):
            self.skipTest("another owner already has a process timer")

        def blocked(*args, **kwargs):
            time.sleep(3)
            return {}

        stdout = io.StringIO()
        started = time.monotonic()
        argv = [str(self.f.source), "--authoring-dir", str(self.authoring_dir),
                "--receipt-sha256", self.receipt_pin, "--timeout-seconds", "1"]
        with patch.object(worker, "apply", side_effect=blocked), contextlib.redirect_stdout(stdout):
            returned = worker.main(argv)
        elapsed = time.monotonic() - started
        result = json.loads(stdout.getvalue())
        self.assertEqual(returned, 2)
        self.assertEqual(result["error"]["code"], "deadline_exceeded", json.dumps(result))
        self.assertGreaterEqual(elapsed, 0.8)
        self.assertLess(elapsed, 2.5)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), previous_timer)
        self.assertEqual(signal.getsignal(signal.SIGALRM), previous_handler)
        self.assert_no_new_run()

    def test_cli_unknown_filter_control_exits_before_application(self):
        argv = [str(self.f.source), "--authoring-dir", str(self.authoring_dir),
                "--receipt-sha256", self.receipt_pin, "--filter", "highpass=80"]
        with patch.object(worker, "apply") as apply, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                worker.main(argv)
        self.assertEqual(caught.exception.code, 2)
        apply.assert_not_called()
        self.assert_no_new_run()

    def test_cli_failure_retains_hash_pinned_process_receipt_outside_audio_staging(self):
        def clean_with_inert_owned_command(*args, **kwargs):
            worker.media.run([sys.executable, "-c", "print('inert application receipt fixture')"], timeout=3)
            return self.mock_clean(*args, **kwargs)

        self.clean.side_effect = clean_with_inert_owned_command
        self.export.side_effect = worker.media.MediaError("fixture export failed after owned command")
        stdout = io.StringIO()
        argv = [str(self.f.source), "--authoring-dir", str(self.authoring_dir),
                "--receipt-sha256", self.receipt_pin, "--timeout-seconds", "10"]
        with contextlib.redirect_stdout(stdout):
            returned = worker.main(argv)
        result = json.loads(stdout.getvalue())
        self.assertEqual(returned, 2)
        receipt_path = Path(result["failure_receipt_path"])
        self.assertTrue(receipt_path.is_relative_to(self.f.root / "artifacts/application-failures"))
        self.assertLessEqual(receipt_path.stat().st_size, 64 * 1024)
        self.assertEqual(fixtures.sha(receipt_path), result["failure_receipt_sha256"])
        receipt = json.loads(receipt_path.read_text())
        self.assertEqual(receipt["status"], "failed_no_candidate_published")
        self.assertEqual(receipt["source"]["sha256"], self.source_sha)
        self.assertEqual(receipt["authoring_receipt_sha256"], self.receipt_pin)
        self.assertEqual(receipt["profile_sha256"], self.authored["profile_sha256"])
        self.assertEqual(len(receipt["owned_subprocesses"]), 1)
        self.assertEqual(receipt["owned_subprocesses"], result["owned_process_events"])
        self.assertEqual(receipt["owned_subprocesses"][0]["result"], "leader_reaped_no_runnable_same_session_group_members")
        self.assertFalse(receipt["listening_accepted"])
        self.assertFalse(receipt["master_adopted"])
        self.assert_no_new_run()
        self.assert_baseline_and_owner_preserved()

    def test_successful_cli_disarms_its_timer_before_first_print(self):
        previous_handler = signal.getsignal(signal.SIGALRM)
        printed = []

        def observe_print(value, *args, **kwargs):
            self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))
            printed.append(json.loads(value))

        argv = [str(self.f.source), "--authoring-dir", str(self.authoring_dir),
                "--receipt-sha256", self.receipt_pin, "--timeout-seconds", "10"]
        with patch("builtins.print", side_effect=observe_print):
            returned = worker.main(argv)
        self.assertEqual(returned, 0)
        self.assertEqual(len(printed), 1)
        self.assertEqual(printed[0]["status"], "rendered_unreviewed")
        self.assertEqual(signal.getsignal(signal.SIGALRM), previous_handler)
        self.assert_baseline_and_owner_preserved()

    def test_oversized_error_events_omit_tail_but_keep_exact_committed_recovery(self):
        committed = self.apply()
        error = worker.ApplyError("Synthetic oversized event-tail diagnostic." * 100)
        error.process_ownership = [{"reason": "Synthetic event payload " + "x" * 8192} for unused in range(8)]
        failure = self.f.root / "artifacts/application-failures/synthetic-diagnostic/receipt.json"
        failure.parent.mkdir(parents=True)
        fixtures.dump(failure, {"schema_version": 1, "evidence_kind": "synthetic_diagnostic_fixture"})
        error.failure_receipt_path = str(failure)
        error.failure_receipt_sha256 = fixtures.sha(failure)
        diagnostic = worker.error_diagnostic(error, committed)
        raw = worker.capture.json_bytes(diagnostic, 16 * 1024)
        self.assertLessEqual(len(raw), 16 * 1024)
        self.assertTrue(diagnostic["owned_process_events_omitted"])
        self.assertEqual(diagnostic["owned_process_events"], [])
        self.assertEqual(diagnostic["status"], "committed_unreviewed_reporting_interrupted")
        self.assertEqual(diagnostic["failure_receipt_path"], str(failure))
        self.assertEqual(diagnostic["failure_receipt_sha256"], fixtures.sha(failure))
        recovered = diagnostic["committed_candidate"]
        self.assertEqual(recovered["run_dir"], committed["run_dir"])
        self.assertEqual(json.dumps(recovered).count(committed["run_dir"]), 1)
        for selector, relative in (("manifest", "manifest.json"), ("receipt", "application-receipt.json"),
                                   ("export_outcome", "export/outcome.json")):
            self.assertEqual(recovered[selector]["relative_path"], relative)
            self.assertEqual(recovered[selector]["sha256"], fixtures.sha(Path(recovered["run_dir"]) / relative))
        self.assertEqual(recovered["source_sha256"], self.source_sha)
        self.assertEqual(recovered["profile_sha256"], self.authored["profile_sha256"])
        self.assertEqual(recovered["authoring_receipt_sha256"], self.receipt_pin)
        self.assertFalse(recovered["master_adopted"])
        self.assertFalse(recovered["listening_accepted"])

    def test_precommit_collision_cannot_report_a_previous_success_as_committed(self):
        first = self.apply()
        original_manifest = Path(first["manifest_path"]).read_bytes()
        original_clean = self.mock_clean

        def collide(*args, **kwargs):
            manifest = original_clean(*args, **kwargs)
            original = Path(manifest["run_dir"])
            directory = original.parent / self.owner_run.name
            original.rename(directory)
            manifest.update(run_id=directory.name, run_dir=str(directory))
            fixtures.dump(directory / "manifest.json", manifest)
            return manifest

        self.clean.side_effect = collide
        with self.assertRaises(worker.ApplyError) as caught:
            self.apply()
        diagnostic = worker.error_diagnostic(caught.exception, worker.LAST_COMMITTED)
        self.assertIsNone(diagnostic["committed_candidate"])
        self.assertEqual(diagnostic["candidate_publication"], "not_committed")
        self.assertEqual(diagnostic["status"], "error")
        self.assertIsNone(worker.LAST_COMMITTED)
        self.assertIsNone(worker.LAST_COMMIT_CONTEXT)
        self.assertEqual(Path(first["manifest_path"]).read_bytes(), original_manifest)
        self.assert_baseline_and_owner_preserved()

    def test_expired_cli_attempt_clears_previous_commit_globals(self):
        first = self.apply()
        worker.LAST_POSSIBLE_CANDIDATE = first
        previous_runs = {path.name for path in (self.f.root / "artifacts/runs").iterdir()}
        stdout = io.StringIO()
        argv = [str(self.f.source), "--authoring-dir", str(self.authoring_dir),
                "--receipt-sha256", self.receipt_pin, "--timeout-seconds", "10"]
        with patch.object(worker, "apply", side_effect=worker.ApplyError("fixture deadline expired", "deadline_exceeded")), \
                contextlib.redirect_stdout(stdout):
            returned = worker.main(argv)
        diagnostic = json.loads(stdout.getvalue())
        self.assertEqual(returned, 2)
        self.assertEqual(diagnostic["error"]["code"], "deadline_exceeded")
        self.assertIsNone(diagnostic["committed_candidate"])
        self.assertIsNone(diagnostic["possible_candidate"])
        self.assertEqual(diagnostic["candidate_publication"], "not_committed")
        self.assertIsNone(worker.LAST_COMMITTED)
        self.assertIsNone(worker.LAST_COMMIT_CONTEXT)
        self.assertIsNone(worker.LAST_POSSIBLE_CANDIDATE)
        self.assertTrue(Path(first["manifest_path"]).is_file())
        self.assertEqual({path.name for path in (self.f.root / "artifacts/runs").iterdir()}, previous_runs)
        self.assert_baseline_and_owner_preserved()

    def test_unknown_publication_diagnostic_retains_only_possible_recovery(self):
        # This is a diagnostic fixture; the independent audit owns actual
        # publication/readback failure injection. No uncertainty is inferred
        # from the successful fixture render itself.
        prepared = self.apply()
        error = worker.ApplyError("synthetic publication verification interrupted", "publication_failed")
        error.possible_candidate = prepared
        error.process_ownership = [{"reason": "synthetic oversized event " + "x" * 8192} for unused in range(8)]
        diagnostic = worker.error_diagnostic(error, None)
        self.assertLessEqual(len(worker.capture.json_bytes(diagnostic, 16 * 1024)), 16 * 1024)
        self.assertEqual(diagnostic["status"], "publication_outcome_unknown")
        self.assertEqual(diagnostic["candidate_publication"], "unknown_after_publish_attempt")
        self.assertIsNone(diagnostic["committed_candidate"])
        self.assertTrue(diagnostic["owned_process_events_omitted"])
        possible = diagnostic["possible_candidate"]
        self.assertEqual(possible["run_dir"], prepared["run_dir"])
        self.assertEqual(json.dumps(possible).count(prepared["run_dir"]), 1)
        for selector, key, relative in (("manifest", "manifest_sha256", "manifest.json"),
                                        ("receipt", "receipt_sha256", "application-receipt.json"),
                                        ("export_outcome", "outcome_sha256", "export/outcome.json")):
            expected = prepared["export"][key] if selector == "export_outcome" else prepared[key]
            self.assertEqual(possible[selector], {"relative_path": relative, "sha256": expected})
        self.assertEqual(possible["source_sha256"], self.source_sha)
        self.assertEqual(possible["profile_sha256"], self.authored["profile_sha256"])
        self.assertEqual(possible["authoring_receipt_sha256"], self.receipt_pin)
        self.assertFalse(possible["listening_accepted"])
        self.assertFalse(possible["master_adopted"])

    def test_validation_failure_clears_previous_possible_publication(self):
        previous = self.apply()
        worker.LAST_POSSIBLE_CANDIDATE = previous
        with self.assertRaises(worker.ApplyError) as caught:
            self.apply(receipt_sha256="0" * 64)
        diagnostic = worker.error_diagnostic(caught.exception, worker.LAST_COMMITTED)
        self.assertEqual(diagnostic["status"], "error")
        self.assertEqual(diagnostic["candidate_publication"], "not_committed")
        self.assertIsNone(diagnostic["committed_candidate"])
        self.assertIsNone(diagnostic["possible_candidate"])
        self.assertIsNone(worker.LAST_COMMITTED)
        self.assertIsNone(worker.LAST_COMMIT_CONTEXT)
        self.assertIsNone(worker.LAST_POSSIBLE_CANDIDATE)
        self.assertTrue(Path(previous["manifest_path"]).is_file())
        self.assert_baseline_and_owner_preserved()


class OwnedRunnerTests(unittest.TestCase):
    """Only launch/signal descendants created by these explicit fixtures."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name).resolve()
        self.leader_record = self.directory / "leader.json"
        self.child_record = self.directory / "child.json"

    def tearDown(self):
        self.cleanup_owned_fixture()
        self.temp.cleanup()

    def command(self, *, exit_leader):
        # Metadata is emitted by each process itself, before any sleep. Both
        # records therefore describe the worker-created process session rather
        # than guessed PID ownership from an unrelated tool/session.
        child = """# owned_capture_application_child
import json, os, pathlib, sys, time
target = pathlib.Path(sys.argv[1])
staging = target.with_suffix('.tmp')
staging.write_text(json.dumps({'pid': os.getpid(), 'pgid': os.getpgrp(), 'sid': os.getsid(0)}))
staging.replace(target)
time.sleep(30)
"""
        leader = """# owned_capture_application_leader
import json, os, pathlib, subprocess, sys, time
leader_path, child_path, exit_early, child_code = sys.argv[1:]
pathlib.Path(leader_path).write_text(json.dumps({'pid': os.getpid(), 'pgid': os.getpgrp(), 'sid': os.getsid(0)}))
subprocess.Popen([sys.executable, '-c', child_code, child_path], stdin=subprocess.DEVNULL)
for unused in range(60):
    if pathlib.Path(child_path).exists():
        break
    time.sleep(.05)
if not pathlib.Path(child_path).exists():
    raise SystemExit(3)
if exit_early == 'yes':
    print('leader completed; child still has captured output descriptors', flush=True)
else:
    time.sleep(30)
"""
        return [sys.executable, "-c", leader, str(self.leader_record), str(self.child_record),
                "yes" if exit_leader else "no", child]

    def process_state(self, pid):
        result = subprocess.run(["/bin/ps", "-o", "stat=", "-p", str(pid)],
                                capture_output=True, text=True, timeout=2, check=False)
        return result.stdout.strip().split()[0] if result.stdout.strip() else None

    @contextlib.contextmanager
    def ready_process(self, command, *, child=True):
        """Bound startup separately; only the main's own alarm is paused."""
        original = subprocess.Popen
        ready_path = self.child_record if child else self.leader_record

        def launch(argv, *args, **kwargs):
            if argv != command:
                return original(argv, *args, **kwargs)
            owned_alarm = (worker.CLI_ALARM_HANDLER is not None
                           and signal.getsignal(signal.SIGALRM) is worker.CLI_ALARM_HANDLER)
            timer = signal.getitimer(signal.ITIMER_REAL) if owned_alarm else (0.0, 0.0)
            if owned_alarm:
                signal.setitimer(signal.ITIMER_REAL, 0)
            process = None
            try:
                process = original(argv, *args, **kwargs)
                self.assertTrue(kwargs.get("start_new_session"))
                limit = time.monotonic() + 5
                while not ready_path.is_file() and time.monotonic() < limit:
                    if process.poll() is not None:
                        break
                    time.sleep(.01)
                self.assertTrue(ready_path.is_file(), "bounded fixture readiness handshake expired")
                return process
            except BaseException:
                if process is not None:
                    try:
                        if process.poll() is None:
                            try:
                                if os.getpgid(process.pid) == process.pid and os.getsid(process.pid) == process.pid:
                                    os.killpg(process.pid, signal.SIGKILL)
                            except ProcessLookupError:
                                pass
                    finally:
                        # The exact Popen direct child remains ours even if
                        # the live group lookup raced leader exit.
                        if process.poll() is None:
                            process.kill()
                        process.wait(timeout=2)
                raise
            finally:
                if owned_alarm and timer[0] > 0:
                    # The processing-alarm test begins after readiness. This
                    # fixture allowance is not a claim of one-second startup.
                    signal.setitimer(signal.ITIMER_REAL, 1, timer[1])

        with patch.object(subprocess, "Popen", side_effect=launch):
            yield

    def records(self):
        self.assertTrue(self.leader_record.is_file(), "worker-owned leader never recorded startup identity")
        self.assertTrue(self.child_record.is_file(), "worker-owned child never recorded startup identity")
        leader = json.loads(self.leader_record.read_text())
        child = json.loads(self.child_record.read_text())
        self.assertEqual(leader["pid"], leader["pgid"])
        self.assertEqual(leader["pid"], leader["sid"])
        self.assertEqual(child["pgid"], leader["pgid"])
        self.assertEqual(child["sid"], leader["sid"])
        return leader, child

    def assert_owned_processes_unrunnable(self):
        leader, child = self.records()
        deadline = time.monotonic() + 2
        remaining = []
        while time.monotonic() < deadline:
            remaining = []
            for record in (leader, child):
                state = self.process_state(record["pid"])
                if state is not None and not state.startswith("Z"):
                    remaining.append((record["pid"], state))
            if not remaining:
                break
            time.sleep(.05)
        self.assertEqual(remaining, [], "worker returned with a runnable owned process")

    def assert_cleanup_receipt(self, events, reason):
        leader, child = self.records()
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["leader_pid"], leader["pid"])
        self.assertEqual(event["pgid"], leader["pgid"])
        self.assertEqual(event["session_id"], leader["sid"])
        self.assertEqual(event["reason"], reason)
        self.assertIn("R-N11", event["ruling"])
        self.assertIn(child["pid"], event["prior_state"]["live_members"])
        self.assertIn("SIGTERM", event["signals"])
        self.assertEqual(event["result"], "leader_reaped_no_runnable_same_session_group_members")

    def cleanup_owned_fixture(self):
        """Failure-only fallback with live PID/session/command checks (R-N11)."""
        if not self.leader_record.is_file() or not self.child_record.is_file():
            return
        leader = json.loads(self.leader_record.read_text())
        child = json.loads(self.child_record.read_text())
        group = leader["pgid"]
        if not (group == leader["pid"] == leader["sid"] == child["pgid"] == child["sid"]):
            return
        for record in (child, leader):
            pid = record["pid"]
            state = self.process_state(pid)
            if state is None or state.startswith("Z"):
                continue
            try:
                if os.getpgid(pid) != group or os.getsid(pid) != group:
                    continue
                observed = subprocess.run(["/bin/ps", "-o", "command=", "-p", str(pid)],
                                          capture_output=True, text=True, timeout=2, check=False)
                if "owned_capture_application_" not in observed.stdout:
                    continue
                os.killpg(group, signal.SIGKILL)
                break
            except ProcessLookupError:
                continue

    def test_timeout_reaps_owned_leader_and_stops_child_session(self):
        started = time.monotonic()
        events = []
        command = self.command(exit_leader=False)
        with self.ready_process(command), self.assertRaises(worker.ApplyError):
            worker.run_owned(command, deadline=worker.Deadline(20), timeout=8, events=events)
        self.assertLess(time.monotonic() - started, 14)
        self.assert_owned_processes_unrunnable()
        self.assert_cleanup_receipt(events, "stage_deadline_exceeded")

    def test_repeated_inspections_and_fallback_share_absolute_cleanup_budget(self):
        # Model a persistent same-session member and costly inspections with
        # a deterministic clock. Signals are mocked: these PIDs are synthetic.
        clock = [100.0]
        inspection_timeouts = []
        wait_timeouts = []
        process = Mock(pid=4242)
        process.poll.return_value = 0
        process.wait.side_effect = lambda *, timeout: wait_timeouts.append(timeout) or 0

        def inspect(command, **kwargs):
            self.assertEqual(command, ["/bin/ps", "-ax", "-o", "pid=,pgid=,stat="])
            inspection_timeouts.append(kwargs["timeout"])
            clock[0] += min(.8, kwargs["timeout"])
            return subprocess.CompletedProcess(command, 0, "4243 4242 S\n", "")

        def advance(seconds):
            clock[0] += seconds

        events = []
        with patch.object(worker.time, "monotonic", side_effect=lambda: clock[0]), \
                patch.object(worker.time, "sleep", side_effect=advance), \
                patch.object(worker.subprocess, "run", side_effect=inspect), \
                patch.object(worker.os, "getpgid", return_value=4242), \
                patch.object(worker.os, "getsid", return_value=4242), \
                patch.object(worker.os, "killpg") as signal_group:
            with self.assertRaises(worker.ApplyError) as caught:
                worker.cleanup_owned_group(process, 4242, "synthetic_budget_fixture", events)
        self.assertEqual(caught.exception.code, "cleanup_failed")
        self.assertGreaterEqual(len(inspection_timeouts), 2)
        self.assertTrue(all(0 < value <= worker.MAX_INSPECTION_SECONDS for value in inspection_timeouts))
        self.assertLess(inspection_timeouts[-1], inspection_timeouts[0])
        self.assertLessEqual(clock[0] - 100.0, worker.MAX_CLEANUP_SECONDS)
        self.assertGreaterEqual(wait_timeouts[-1], 0.0)
        self.assertLessEqual(wait_timeouts[-1], .25, "fallback must use only the original reap reserve")
        self.assertLessEqual(clock[0] - 100.0 + wait_timeouts[-1], worker.MAX_CLEANUP_SECONDS)
        self.assertEqual(signal_group.call_args_list[0].args, (4242, signal.SIGTERM))
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["prior_state"]["live_members"], [4243])
        self.assertIn("SIGTERM", events[0]["signals"])
        self.assertEqual(events[-1]["result"], "direct_child_reaped_descendant_absence_unverified")
        process.kill.assert_not_called()

    def test_transient_inspection_timeout_recovers_within_shared_cleanup_budget(self):
        clock = [100.0]
        timeouts = []
        process = Mock(pid=4242)
        process.poll.return_value = 0
        process.wait.return_value = 0

        def inspect(command, **kwargs):
            timeouts.append(kwargs["timeout"])
            if len(timeouts) == 1:
                clock[0] += kwargs["timeout"]
                raise subprocess.TimeoutExpired(command, kwargs["timeout"])
            clock[0] += .1
            return subprocess.CompletedProcess(command, 0, "", "")

        events = []
        with patch.object(worker.time, "monotonic", side_effect=lambda: clock[0]), \
                patch.object(worker.subprocess, "run", side_effect=inspect), \
                patch.object(worker.os, "killpg") as signal_group:
            worker.cleanup_owned_group(process, 4242, "synthetic_transient_inspection", events)
        self.assertEqual(len(timeouts), 2)
        self.assertEqual(timeouts[0], worker.MAX_INSPECTION_SECONDS)
        self.assertLess(timeouts[1], timeouts[0])
        self.assertLessEqual(clock[0] - 100.0, worker.MAX_CLEANUP_SECONDS)
        self.assertEqual(len(events), 1)
        retries = events[0]["inspection_retries"]
        self.assertEqual(len(retries), 1)
        self.assertEqual(retries[0]["attempt"], 1)
        self.assertEqual(retries[0]["timeout_seconds"], timeouts[0])
        self.assertEqual(retries[0]["result"], "timeout_then_retry_observed")
        self.assertLessEqual(len(retries[0]["error"]), 500)
        self.assertEqual(events[0]["prior_state"]["live_members"], [])
        self.assertEqual(events[0]["result"], "leader_reaped_no_runnable_same_session_group_members")
        process.wait.assert_called_once()
        process.kill.assert_not_called()
        signal_group.assert_not_called()

    def test_persistent_inspection_timeouts_abstain_and_reap_without_new_budget(self):
        clock = [100.0]
        timeouts = []
        wait_timeouts = []
        process = Mock(pid=4242)
        process.poll.return_value = None
        process.kill.side_effect = lambda: setattr(process.poll, "return_value", -9)
        process.wait.side_effect = lambda *, timeout: wait_timeouts.append(timeout) or -9

        def inspect(command, **kwargs):
            timeouts.append(kwargs["timeout"])
            clock[0] += kwargs["timeout"]
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])

        events = []
        with patch.object(worker.time, "monotonic", side_effect=lambda: clock[0]), \
                patch.object(worker.subprocess, "run", side_effect=inspect), \
                patch.object(worker.os, "getpgid", return_value=4242), \
                patch.object(worker.os, "getsid", return_value=4242), \
                patch.object(worker.os, "killpg") as signal_group:
            with self.assertRaises(worker.ApplyError) as caught:
                worker.cleanup_owned_group(process, 4242, "synthetic_persistent_inspection", events)
        self.assertEqual(caught.exception.code, "cleanup_failed")
        self.assertEqual(len(timeouts), 2)
        self.assertEqual(timeouts[0], worker.MAX_INSPECTION_SECONDS)
        self.assertLess(timeouts[1], timeouts[0])
        self.assertEqual(sum(timeouts), worker.MAX_CLEANUP_SECONDS - .25)
        self.assertLessEqual(clock[0] - 100.0, worker.MAX_CLEANUP_SECONDS)
        self.assertEqual(wait_timeouts, [.25])
        self.assertEqual(sum(timeouts) + sum(wait_timeouts), worker.MAX_CLEANUP_SECONDS)
        self.assertEqual(len(events), 1)
        retries = events[0]["inspection_retries"]
        self.assertEqual([entry["attempt"] for entry in retries], [1, 2])
        self.assertEqual([entry["timeout_seconds"] for entry in retries], timeouts)
        self.assertTrue(all(entry["result"] == "observation_timed_out" for entry in retries))
        self.assertTrue(all(len(entry["error"]) <= 500 for entry in retries))
        self.assertEqual(events[0]["result"], "direct_child_reaped_descendant_absence_unverified")
        self.assertIsNone(events[0]["prior_state"]["live_members"])
        self.assertEqual(signal_group.call_args.args, (4242, signal.SIGKILL))
        process.kill.assert_called_once()
        process.wait.assert_called_once()

    def test_dead_leader_empty_group_reuses_scan_only_after_same_popen_wait(self):
        process = Mock(pid=4242)
        process.poll.return_value = 0
        process.wait.return_value = 0
        events = []
        with patch.object(worker, "live_group_members", return_value=[]) as inspect, \
                patch.object(worker.os, "killpg") as signal_group:
            worker.cleanup_owned_group(process, 4242, "synthetic_dead_leader_empty", events)
        inspect.assert_called_once()
        process.wait.assert_called_once()
        signal_group.assert_not_called()
        self.assertEqual(events[0]["prior_state"]["leader_returncode"], 0)
        self.assertEqual(events[0]["prior_state"]["live_members"], [])
        self.assertEqual(events[0]["result"], "leader_reaped_no_runnable_same_session_group_members")
        self.assertEqual(events[0]["verification_method"], "empty_group_after_leader_terminated_and_direct_wait")

    def test_live_leader_empty_initial_scan_still_requires_postwait_observation(self):
        process = Mock(pid=4242)
        process.poll.return_value = None

        def reaped(*, timeout):
            process.poll.return_value = 0
            return 0

        process.wait.side_effect = reaped
        events = []
        with patch.object(worker, "live_group_members", return_value=[]) as inspect, \
                patch.object(worker.os, "killpg") as signal_group:
            worker.cleanup_owned_group(process, 4242, "synthetic_live_leader_empty", events)
        self.assertEqual(inspect.call_count, 2)
        process.wait.assert_called_once()
        signal_group.assert_not_called()
        self.assertIsNone(events[0]["prior_state"]["leader_returncode"])
        self.assertEqual(events[0]["result"], "leader_reaped_no_runnable_same_session_group_members")
        self.assertEqual(events[0]["verification_method"], "post_wait_live_same_session_group_inspection")

    def test_leader_exit_during_initial_scan_still_requires_postwait_observation(self):
        process = Mock(pid=4242)
        process.poll.return_value = None
        process.wait.return_value = 0

        def inspect(*args, **kwargs):
            process.poll.return_value = 0
            return []

        events = []
        with patch.object(worker, "live_group_members", side_effect=inspect) as observe, \
                patch.object(worker.os, "killpg") as signal_group:
            worker.cleanup_owned_group(process, 4242, "synthetic_exit_during_scan", events)
        self.assertEqual(observe.call_count, 2, "leader must already be terminated before the reused observation")
        process.wait.assert_called_once()
        signal_group.assert_not_called()
        self.assertEqual(events[0]["prior_state"]["leader_returncode"], 0)
        self.assertEqual(events[0]["verification_method"], "post_wait_live_same_session_group_inspection")
        self.assertEqual(events[0]["result"], "leader_reaped_no_runnable_same_session_group_members")

    def test_exited_leader_does_not_leave_runnable_owned_child(self):
        started = time.monotonic()
        events = []
        command = self.command(exit_leader=True)
        with self.ready_process(command):
            result = worker.run_owned(command, deadline=worker.Deadline(20), timeout=10, events=events)
        self.assertEqual(result.returncode, 0)
        self.assertIn("leader completed", result.stdout)
        self.assertLess(time.monotonic() - started, 11)
        self.assert_owned_processes_unrunnable()
        self.assert_cleanup_receipt(events, "stage_finished")

    def test_outer_cli_alarm_interrupt_also_cleans_owned_process_session(self):
        previous_timer = signal.getitimer(signal.ITIMER_REAL)
        previous_handler = signal.getsignal(signal.SIGALRM)
        if previous_timer != (0.0, 0.0):
            self.skipTest("another owner already has a process timer")
        events = []
        command = self.command(exit_leader=False)

        def application_with_longer_child_deadline(*args, **kwargs):
            # Deliberately make the runner's own deadline later than the outer
            # alarm, exercising exception cleanup rather than normal timeout.
            worker.run_owned(command, deadline=worker.Deadline(20), timeout=10, events=events)
            return {}

        stdout = io.StringIO()
        started = time.monotonic()
        argv = ["unused-owned-fixture.wav", "--authoring-dir", "unused-authoring-fixture",
                "--receipt-sha256", "a" * 64, "--timeout-seconds", "1"]
        with self.ready_process(command), patch.object(worker, "apply", side_effect=application_with_longer_child_deadline), \
                contextlib.redirect_stdout(stdout):
            returned = worker.main(argv)
        result = json.loads(stdout.getvalue())
        self.assertEqual(returned, 2)
        self.assertEqual(result["error"]["code"], "deadline_exceeded", json.dumps(result))
        self.assertLess(time.monotonic() - started, 12)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), previous_timer)
        self.assertEqual(signal.getsignal(signal.SIGALRM), previous_handler)
        self.assert_owned_processes_unrunnable()
        self.assert_cleanup_receipt(events, "stage_interrupted")

    def test_inspection_failure_still_stops_and_reaps_owned_direct_child(self):
        code = """# owned_capture_application_inspection_fixture
import json, os, pathlib, sys, time
pathlib.Path(sys.argv[1]).write_text(json.dumps({'pid': os.getpid(), 'pgid': os.getpgrp(), 'sid': os.getsid(0)}))
time.sleep(30)
"""
        command = [sys.executable, "-c", code, str(self.leader_record)]
        events = []
        try:
            with self.ready_process(command, child=False), \
                    patch.object(worker, "live_group_members", side_effect=worker.ApplyError("fixture inspection unavailable")) as inspect:
                with self.assertRaises(worker.ApplyError) as caught:
                    worker.run_owned(command, deadline=worker.Deadline(20), timeout=8, events=events)
            self.assertEqual(caught.exception.code, "cleanup_failed")
            inspect.assert_called_once()
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["result"], "direct_child_reaped_descendant_absence_unverified")
            self.assertIsNone(events[0]["prior_state"]["live_members"])
            self.assertTrue(self.leader_record.is_file())
            leader = json.loads(self.leader_record.read_text())
            self.assertEqual(leader["pid"], leader["pgid"])
            self.assertEqual(leader["pid"], leader["sid"])
            self.assertIsNone(self.process_state(leader["pid"]), "direct owned child must be reaped even when group inspection fails")
        finally:
            # Failure-only direct-PID cleanup: inspect the actual fixture PID,
            # session and command; never infer ownership from existence alone.
            if self.leader_record.is_file():
                leader = json.loads(self.leader_record.read_text())
                pid = leader["pid"]
                state = self.process_state(pid)
                if state is not None:
                    try:
                        observed = subprocess.run(["/bin/ps", "-o", "command=", "-p", str(pid)],
                                                  capture_output=True, text=True, timeout=2, check=False)
                        if (os.getpgid(pid) == leader["pgid"] == pid and os.getsid(pid) == leader["sid"] == pid
                                and (state.startswith("Z") or "owned_capture_application_inspection_fixture" in observed.stdout)):
                            if not state.startswith("Z"):
                                os.kill(pid, signal.SIGKILL)
                            os.waitpid(pid, 0)
                    except (ProcessLookupError, ChildProcessError):
                        pass


if __name__ == "__main__":
    unittest.main()
