"""Independent structural checks; no model execution or audio decoding."""
import hashlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("learned_pitch_independent_audit", ROOT / "scripts/learned_pitch_evaluate.py")
learned = importlib.util.module_from_spec(spec)
spec.loader.exec_module(learned)


def one_second_receipt():
    """Construct constant A3 activation, independently projected sample clocks."""
    frames = 86
    arrays = {}
    for name, width in (("note", 88), ("onset", 88), ("contour", 264)):
        values = [.8 if name == "note" and k == 36 else .1
                  for _ in range(frames) for k in range(width)]
        arrays[name] = {"values": values, "bytes": len(values) * 8}
    correction = (172 * 256 - 43844) / 22050 + .0018
    clocks = {
        "nominal_times_seconds": [i * 256 / 22050 for i in range(frames)],
        "model_times_seconds": [i * 256 / 22050 - (i // 172) * correction for i in range(frames)],
        "input_window_projection_seconds": [((i // 142) * 36164 - 3840 + (i % 142 + 15) * 256) / 22050 for i in range(frames)],
        "window_index": [i // 142 for i in range(frames)],
        "window_frame_index": [i % 142 + 15 for i in range(frames)],
    }
    for name, values in clocks.items():
        arrays[name] = {"values": values, "bytes": len(values) * (4 if name.startswith("window_") else 8)}
    end = frames * 256 / 22050
    event = {
        "start_frame": 0, "end_frame_exclusive": frames, "midi_candidate": 57,
        "model_start_seconds": 0., "model_end_seconds": end,
        "nominal_start_seconds": 0., "nominal_end_seconds": end,
        "input_window_projection_start_seconds": 0., "input_window_projection_end_seconds": end,
        "audio_relative_start_seconds": 0., "audio_relative_end_seconds": min(1., end),
        "source_start_seconds": 0., "source_end_seconds": min(1., end),
        "mean_note_activation": .8, "maximum_onset_activation": .1,
        "touches_excerpt_boundary": True,
    }
    window = {"window_index": 0, "padded_start_sample": 0, "unpadded_start_sample": -3840,
              "leading_zero_samples": 3840, "trailing_zero_samples": 17954,
              "output_frames_before_crop": 172, "cropped_frames_each_side": 15, "retained_frames": 142,
              "input_context_start_seconds_in_excerpt": 0., "input_context_end_seconds_in_excerpt": 1.}
    index = {"model_sha256": "m", "adapter_sha256": "a", "runtime_manifest_sha256": "r", "instrument_registry_sha256": "t"}
    job = {"input_sha256": "i", "activations_sha256": "n"}
    receipt = {
        "schema_version": 1, "status": "experimental_official_model_project_decoder",
        "analysis_input_sha256": "i", "model_sha256": "m", "worker_sha256": "a",
        "wheel_manifest_sha256": "r", "tuning_registry_sha256": "t", "raw_activations_sha256": "n",
        "providers": ["CPUExecutionProvider"], "upstream_decoder_parity": False,
        "coverage_seconds": 1., "model_windows": 1, "peak_rss_bytes": 1, "elapsed_seconds": 0.,
        "raw_array_bytes": sum(a["bytes"] for a in arrays.values()),
        "settings": {"decoder": learned.DECODER, "minimum_note_length_ms_presets": [127.7, 25.],
                     "frame_threshold": .3, "onset_threshold": .5, "start_seconds": 0., "max_analysis_seconds": 1.},
        "excerpts": [{"start_seconds": 0., "end_seconds": 1., "sample_rate": 22050, "sample_count": 22050,
                      "retained_frames": frames, "model_input_windows": [window],
                      "variants": [{"minimum_note_length_ms": floor, "event_count": 1, "events": [dict(event)]}
                                   for floor in (127.7, 25.)]}],
    }
    return receipt, index, job, arrays


class IndependentAuditTests(unittest.TestCase):
    def test_valid_constant_activation_receipt(self):
        receipt, index, job, arrays = one_second_receipt()
        learned.validate_comparison(receipt, index, job, 1., arrays)

    def test_event_confidence_must_match_raw_activations(self):
        for field, false_value in (("mean_note_activation", .4), ("maximum_onset_activation", .9)):
            with self.subTest(field=field):
                receipt, index, job, arrays = one_second_receipt()
                receipt["excerpts"][0]["variants"][0]["events"][0][field] = false_value
                with self.assertRaisesRegex(learned.base.EvaluationError, "event_activation_array_mismatch"):
                    learned.validate_comparison(receipt, index, job, 1., arrays)

    def test_reserved_deflate_block_becomes_structural_error(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name in learned.NAMES:
                archive.writestr("excerpt_0_" + name + ".npy", b"placeholder")
        raw = bytearray(buffer.getvalue())
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            first = archive.infolist()[0]
            payload = first.header_offset + 30 + len(first.filename.encode()) + len(first.extra)
        raw[payload] = 0x07  # BFINAL=1, reserved DEFLATE BTYPE=3.
        learned.base.ALLOWED.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="learned-independent-audit-", dir=learned.base.ALLOWED) as directory:
            path = Path(directory) / "invalid-deflate.npz"
            path.write_bytes(raw)
            with self.assertRaisesRegex(learned.base.EvaluationError, "invalid_npz_archive"):
                learned.read_npz(path, hashlib.sha256(raw).hexdigest(), 1)

    def test_three_clock_seams_have_independent_sample_oracles(self):
        self.assertAlmostEqual(learned.model_time(142), 36352 / 22050, delta=1e-12)
        self.assertAlmostEqual(learned.projection_time(142), 36164 / 22050, delta=1e-12)
        self.assertAlmostEqual(learned.model_time(172), 43844 / 22050 - .0018, delta=1e-12)
        self.assertAlmostEqual(learned.projection_time(172), 43844 / 22050, delta=1e-12)

    def test_offset_residual_remains_signed_when_both_ends_observed(self):
        reference = [{"id": "observed", "start": 1., "end": 1.5, "frequency": 440., "boundary_truncated": False}]
        events = [{"model_start_seconds": 1.01, "model_end_seconds": 1.47, "midi_candidate": 69,
                   "touches_excerpt_boundary": False}]
        result = learned.event_metrics(reference, events, True)
        self.assertEqual((result["tp"], result["fp"], result["fn"]), (1, 0, 0))
        self.assertAlmostEqual(result["matches"][0]["offset_residual_seconds"], -.03)
        self.assertAlmostEqual(result["offset_residual_seconds"]["median_signed"], -.03)


if __name__ == "__main__":
    unittest.main()
