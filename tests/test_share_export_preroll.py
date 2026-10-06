"""Edit-list pre-roll regression: decode-only packets are not presented frames.

The accepted run export `cleaned-video.mov` carries an MOV edit list whose
leading packets are flagged decode-only ('D'). A re-encode correctly emits no
frame for them, so share_export must compare presented packets, while copy
must keep every coded packet and its decode-only state.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch


REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("share_export_preroll_worker", REPO / "scripts/share_export.py")
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
QUALIFIED_BIN = Path("/nix/store/mv3x2v2pr6pwvwj7cdyh8nci2q1wpnjq-ffmpeg-headless-8.1.2-bin/bin")
QUALIFIED_SHA = {
    "ffmpeg": "3a315207e67de78e48c3bbb6b3346663f6a27c02e034d65ac72a12fee74c534a",
    "ffprobe": "5fb21f955aad27bc59615906801ce4b5b9f1466e99450b714b6d989f836c8850",
}


def record(pts, duration, flags="___", tag="source"):
    return {"pts": pts, "dts": pts - 80, "duration": duration, "flags": flags,
            "data_hash": "SHA256:" + hashlib.sha256(f"{tag}:{pts}".encode()).hexdigest()}


def preroll_source():
    # Two decode-only pre-roll packets (negative PTS, 'D'), then VFR pictures.
    lead = [record(-80, 40, "KD_"), record(-40, 40, "_D_")]
    shown = [record(0, 40, "K__"), record(40, 80), record(120, 40), record(160, 80)]
    return lead + shown


def reencoded_output():
    return [record(0, 40, "K__", "encoded"), record(40, 80, tag="encoded"),
            record(120, 40, tag="encoded"), record(160, 80, tag="encoded")]


class PresentedPacketComparison(unittest.TestCase):
    def test_reencode_excludes_decode_only_preroll_and_keeps_vfr_timeline(self):
        source, output = preroll_source(), list(reversed(reencoded_output()))
        proof = worker.verify_packets(source, output, "1/1000", "1/1000", copy=False)
        self.assertEqual(proof["comparison_scope"], "presented_packets_excluding_edit_list_discard")
        self.assertEqual((proof["source_packet_count_total"], proof["source_decode_only_packets"]), (6, 2))
        self.assertEqual((proof["packet_count"], proof["output_decode_only_packets"]), (4, 0))
        self.assertEqual(proof["maximum_pts_delta_seconds"], 0.0)
        self.assertEqual(proof["tail_extent_delta_seconds"], 0.0)
        self.assertEqual((proof["source_start_seconds"], proof["source_end_seconds"]), (0.0, 0.24))

    def test_dropped_or_duplicated_presented_picture_is_still_refused_with_counts(self):
        dropped = reencoded_output()[:-1]
        duplicated = reencoded_output() + [record(240, 40, tag="encoded")]
        for name, output in (("dropped", dropped), ("duplicated", duplicated)):
            with self.subTest(case=name), self.assertRaises(worker.ShareError) as caught:
                worker.verify_packets(preroll_source(), output, "1/1000", "1/1000", copy=False)
            message = str(caught.exception)
            self.assertEqual(caught.exception.code, "validation_failed")
            self.assertIn("video packet count changed (presented re-encode)", message)
            self.assertIn("source 4 presented + 2 decode-only", message)
            self.assertIn("do not bypass this check", message)

    def test_presented_picture_shift_is_still_refused(self):
        output = reencoded_output()
        output[2]["pts"] += 20  # beyond the one-tick mux tolerance
        with self.assertRaisesRegex(worker.ShareError, "timestamp or tail extent changed"):
            worker.verify_packets(preroll_source(), output, "1/1000", "1/1000", copy=False)

    def test_output_decode_only_packets_are_not_counted_as_presented_pictures(self):
        output = [record(-40, 40, "KD_", "encoded")] + reencoded_output()
        proof = worker.verify_packets(preroll_source(), output, "1/1000", "1/1000", copy=False)
        self.assertEqual((proof["packet_count"], proof["output_decode_only_packets"]), (4, 1))
        output = [dict(row, flags="_D_") for row in reencoded_output()]
        with self.assertRaisesRegex(worker.ShareError, "output 0 presented"):
            worker.verify_packets(preroll_source(), output, "1/1000", "1/1000", copy=False)

    def test_copy_requires_every_coded_packet_and_identical_decode_only_state(self):
        source = preroll_source()
        proof = worker.verify_packets(source, preroll_source(), "1/1000", "1/1000", copy=True)
        self.assertEqual(proof["comparison_scope"], "all_coded_packets")
        self.assertEqual((proof["packet_count"], proof["source_decode_only_packets"]), (6, 2))
        self.assertEqual(proof["source_start_seconds"], 0.0)
        lost_preroll = preroll_source()[2:]
        with self.assertRaisesRegex(worker.ShareError, r"\(coded copy\)"):
            worker.verify_packets(source, lost_preroll, "1/1000", "1/1000", copy=True)
        moved_flag = preroll_source()
        moved_flag[1]["flags"], moved_flag[2]["flags"] = "___", "_D_"
        with self.assertRaisesRegex(worker.ShareError, "decode-only"):
            worker.verify_packets(source, moved_flag, "1/1000", "1/1000", copy=True)

    def test_malformed_flags_or_all_decode_only_source_cannot_prove_timing(self):
        for invalid in (1, True, ["D"], "D" * 17):
            output = reencoded_output()
            output[0]["flags"] = invalid
            with self.subTest(flags=repr(invalid)), self.assertRaises(worker.ShareError):
                worker.verify_packets(preroll_source(), output, "1/1000", "1/1000", copy=False)
        hidden = [dict(row, flags="_D_") for row in preroll_source()]
        with self.assertRaises(worker.ShareError):
            worker.verify_packets(hidden, reencoded_output(), "1/1000", "1/1000", copy=False)
        with self.assertRaises(worker.ShareError):
            worker.verify_packets(hidden, hidden, "1/1000", "1/1000", copy=True)


class SyntheticEditListPreroll(unittest.TestCase):
    """Generated 3 s 320x240 VFR H.264 MOV cut by stream copy at 0.6 s."""

    @classmethod
    def setUpClass(cls):
        for name, digest in QUALIFIED_SHA.items():
            path = QUALIFIED_BIN / name
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise unittest.SkipTest(f"qualified {name} binary unavailable or changed")
        parent = REPO / "artifacts/experiments"
        parent.mkdir(parents=True, exist_ok=True)
        cls.root = Path(tempfile.mkdtemp(prefix="share-preroll-test-", dir=parent)).resolve()
        cls.preserve = False
        base, cls.source = cls.root / "vfr-base.mov", cls.root / "vfr-preroll.mov"
        ffmpeg = [str(QUALIFIED_BIN / "ffmpeg"), "-nostdin", "-hide_banner", "-loglevel", "error", "-n"]
        commands = [
            ffmpeg + ["-f", "lavfi", "-i", "testsrc2=size=320x240:rate=24:duration=3",
                      "-f", "lavfi", "-i", "sine=frequency=1000:sample_rate=44100:duration=3",
                      "-vf", "select=not(eq(mod(n\\,7)\\,3))", "-fps_mode", "vfr",
                      "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-g", "24", "-threads", "2",
                      "-c:a", "aac", "-ac", "2", "-b:a", "96k", str(base)],
            # Copy cut between keyframes: the MOV muxer writes an edit list and
            # the demuxer flags the leading GOP packets decode-only.
            ffmpeg + ["-ss", "0.6", "-i", str(base), "-c", "copy", str(cls.source)],
        ]
        try:
            for command in commands:
                subprocess.run(command, check=True, capture_output=True, timeout=60)
        except BaseException:
            shutil.rmtree(cls.root)
            raise

    @classmethod
    def tearDownClass(cls):
        if not cls.preserve:
            shutil.rmtree(cls.root)

    def probe(self, path):
        command = [str(QUALIFIED_BIN / "ffprobe"), "-v", "error", "-select_streams", "v:0", "-show_streams",
                   "-show_packets", "-show_entries", "packet=pts,dts,duration,flags,data_hash:stream=time_base",
                   "-show_data_hash", "sha256", "-of", "json", str(path)]
        data = json.loads(subprocess.run(command, check=True, capture_output=True, text=True, timeout=30).stdout)
        return data["packets"], data["streams"][0]["time_base"]

    def decoded_frames(self, path):
        command = [str(QUALIFIED_BIN / "ffprobe"), "-v", "error", "-select_streams", "v:0", "-count_frames",
                   "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(path)]
        return int(subprocess.run(command, check=True, capture_output=True, text=True, timeout=30).stdout.strip())

    def export(self, codec):
        output = self.root / f"shared-{codec}.mp4"
        environment = {"FFMPEG": str(QUALIFIED_BIN / "ffmpeg"), "FFPROBE": str(QUALIFIED_BIN / "ffprobe")}
        try:
            with patch.dict(os.environ, environment):
                return output, worker.share_export(str(self.source), str(output), codec=codec, timeout_seconds=120)
        except BaseException as exc:
            type(self).preserve = True
            exc.add_note(f"Retained synthetic pre-roll fixture and stage evidence: {self.root}")
            raise

    def test_fixture_reproduces_decode_only_preroll_condition(self):
        packets, _ = self.probe(self.source)
        decode_only = [row for row in packets if "D" in row["flags"]]
        self.assertGreater(len(decode_only), 0)
        self.assertTrue(all(row["pts"] < 0 for row in decode_only))
        self.assertEqual(self.decoded_frames(self.source), len(packets) - len(decode_only))

    def test_default_h264_reencode_keeps_every_presented_vfr_picture(self):
        source_packets, source_tb = self.probe(self.source)
        output, result = self.export("h264")
        output_packets, output_tb = self.probe(output)
        presented = [row for row in source_packets if "D" not in row["flags"]]
        # The pre-fix total-count comparison is exactly what refused this input.
        self.assertNotEqual(len(source_packets), len(output_packets))
        self.assertEqual(len(output_packets), len(presented))
        self.assertFalse(any("D" in row["flags"] for row in output_packets))
        self.assertEqual(self.decoded_frames(output), len(presented))
        proof = result["video_proof"]
        self.assertEqual(proof["comparison_scope"], "presented_packets_excluding_edit_list_discard")
        self.assertEqual(proof["packet_count"], len(presented))
        self.assertEqual(proof["source_decode_only_packets"], len(source_packets) - len(presented))
        self.assertEqual(proof["maximum_pts_delta_seconds"], 0.0)
        self.assertEqual(proof["tail_extent_delta_seconds"], 0.0)
        self.assertEqual(proof["source_start_seconds"], 0.0)
        independent = worker.verify_packets(source_packets, output_packets, source_tb, output_tb, copy=False)
        self.assertEqual(independent["packet_count"], len(presented))

    def test_copy_keeps_coded_preroll_and_its_decode_only_state(self):
        source_packets, _ = self.probe(self.source)
        output, result = self.export("copy")
        output_packets, _ = self.probe(output)
        self.assertEqual(len(output_packets), len(source_packets))
        self.assertEqual(sorted((r["pts"], r["flags"], r["data_hash"]) for r in output_packets),
                         sorted((r["pts"], r["flags"], r["data_hash"]) for r in source_packets))
        self.assertEqual(result["video_proof"]["comparison_scope"], "all_coded_packets")
        self.assertTrue(result["video_proof"]["copied_payload_verified"])
        self.assertEqual(self.decoded_frames(output), self.decoded_frames(self.source))


if __name__ == "__main__":
    unittest.main()
