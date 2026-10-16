"""Contract test for livecode, against stub ffmpeg, df and diskutil.

The script under test comes from LIVECODE_UNDER_TEST, never from this file's
location: the Bazel runner passes the source (`livecode/livecode.sh`) and the
Nix check passes the built package (`bin/livecode`). Every host probe is
stubbed through livecode's hooks (LIVECODE_FFMPEG, LIVECODE_DF,
LIVECODE_DISKUTIL, LIVECODE_SYSTEM_PROFILER, LIVECODE_QLMANAGE), not through
PATH, so a wrapper's PATH prefix cannot shadow a stub. Stubs start with the absolute bash found on PATH.

No camera, screen, microphone, FFmpeg or macOS is needed. The test pins:

* the filter graph is one scale per input plus one overlay, encoded with
  h264_videotoolbox; recordings default to MKV under LIVECODE_DIR/recordings;
* device names resolve by pattern and skip Continuity / Desk View cameras;
* audio follows the macOS system default input (system_profiler), with no
  audio knob, and an unmappable default input stops instead of picking a mic;
* `livecode preview` grabs one 960 px frame of the same composition into
  scratch, with no encoder, and hands it to Quick Look;
* LIVECODE_DIR is required for rec, stream and preview; an internal-disk target is refused unless
  LIVECODE_ALLOW_INTERNAL=1; LIVECODE_VOLUME_UUID, when set, must match; every
  refusal happens before anything is created;
* the stream URL is never in the script and is redacted from ffmpeg's output.
"""

import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

BASH = shutil.which("bash")

FFMPEG_STUB = r"""
for a in "$@"; do
  if [ "$a" = "-list_devices" ]; then
    cat >&2 <<'L'
[AVFoundation indev @ 0x1] AVFoundation video devices:
[AVFoundation indev @ 0x1] [0] FaceTime HD Camera
[AVFoundation indev @ 0x1] [1] Example iPhone Desk View Camera
[AVFoundation indev @ 0x1] [2] Capture screen 0
[AVFoundation indev @ 0x1] AVFoundation audio devices:
[AVFoundation indev @ 0x1] [0] Example Virtual Audio
[AVFoundation indev @ 0x1] [1] MacBook Pro Microphone
[AVFoundation indev @ 0x1] [2] Example AirPods Pro
L
    exit 251
  fi
done
printf '%s\n' "$@" > "$STUB_ARGV"
last="${*: -1}"
printf 'frame=1\rError opening output %s: refused\n' "$last" >&2
case "$last" in *.mkv|*.png) echo data > "$last" ;; esac
"""

CAPTURE_UUID = "00000000-0000-4000-8000-00000000CAFE"
OTHER_UUID = "11111111-1111-4111-8111-111111111111"

# df stub: every path reports the mount in $STUB_MOUNT with $STUB_AVAIL KiB free.
DF_STUB = """
printf 'Filesystem 1024-blocks Used Available Capacity Mounted on\\n'
printf '/dev/disk7s1 100 1 %s 1%% %s\\n' "${STUB_AVAIL:-999999999}" "$STUB_MOUNT"
"""

# diskutil stub: records each call, then prints the volume's Internal flag and UUID.
DISKUTIL_STUB = """
echo "$@" >> "$STUB_DISKUTIL_CALLS"
cat <<P
<plist><dict>
\t<key>Internal</key>
\t<${STUB_INTERNAL:-false}/>
\t<key>VolumeUUID</key>
\t<string>${STUB_UUID}</string>
</dict></plist>
P
"""

# system_profiler stub: the default input device is $STUB_DEFAULT_INPUT.
SYSTEM_PROFILER_STUB = """
cat <<J
{
  "SPAudioDataType" : [
    {
      "_items" : [
        {
          "_name" : "Example Virtual Audio",
          "coreaudio_device_input" : 2
        },
        {
          "_name" : "${STUB_DEFAULT_INPUT}",
          "coreaudio_default_audio_input_device" : "spaudio_yes",
          "coreaudio_device_input" : 1
        }
      ],
      "_name" : "coreaudio_device"
    }
  ]
}
J
"""

QLMANAGE_STUB = """
printf '%s\\n' "$@" > "$STUB_QL_ARGV"
"""


def under_test():
    value = os.environ.get("LIVECODE_UNDER_TEST", "")
    if not value:
        raise RuntimeError("LIVECODE_UNDER_TEST must name the livecode script or binary under test")
    return Path(value).absolute()


def code(text):
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


class Livecode(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(BASH, "bash must be on PATH")
        self.script = under_test()
        self.assertTrue(self.script.is_file(), self.script)
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.tmp = Path(scratch.name)
        self.stubs = self.tmp / "stubs"
        self.stubs.mkdir()
        for name, body in (("ffmpeg", FFMPEG_STUB), ("df", DF_STUB), ("diskutil", DISKUTIL_STUB),
                           ("system_profiler", SYSTEM_PROFILER_STUB), ("qlmanage", QLMANAGE_STUB)):
            (self.stubs / name).write_text(f"#!{BASH}\n{body}")
            (self.stubs / name).chmod(0o755)
        self.mount = self.tmp / "capture-volume"
        self.mount.mkdir()
        self.capture_dir = self.mount / "livecode"
        self.diskutil_calls = self.tmp / "diskutil-calls"

    def run_livecode(self, *args, **env):
        argv_file = self.tmp / "argv"
        if argv_file.exists():
            argv_file.unlink()
        full_env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(self.tmp),
            "LIVECODE_FFMPEG": str(self.stubs / "ffmpeg"),
            "LIVECODE_DF": str(self.stubs / "df"),
            "LIVECODE_DISKUTIL": str(self.stubs / "diskutil"),
            "LIVECODE_SYSTEM_PROFILER": str(self.stubs / "system_profiler"),
            "LIVECODE_QLMANAGE": str(self.stubs / "qlmanage"),
            "STUB_DEFAULT_INPUT": "MacBook Pro Microphone",
            "STUB_QL_ARGV": str(self.tmp / "ql-argv"),
            "LIVECODE_DIR": str(self.capture_dir),
            "LIVECODE_VOLUME_UUID": CAPTURE_UUID,
            "STUB_ARGV": str(argv_file),
            "STUB_DISKUTIL_CALLS": str(self.diskutil_calls),
            "STUB_MOUNT": str(self.mount),
            "STUB_UUID": CAPTURE_UUID,
        }
        full_env.update(env)
        full_env = {key: value for key, value in full_env.items() if value is not None}
        proc = subprocess.run([BASH, str(self.script), *args], env=full_env, capture_output=True, text=True,
                              timeout=30, stdin=subprocess.DEVNULL)
        return proc, argv_file.read_text().splitlines() if argv_file.exists() else []

    def assert_refused(self, proc, argv, needle="refusing"):
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn(needle, proc.stderr)
        self.assertEqual(argv, [], "ffmpeg must not run")
        self.assertFalse(self.capture_dir.exists(), "nothing may be created")

    def test_script_carries_no_stream_url_and_no_storage_default(self):
        source = self.script.read_text()
        script = code(source)
        self.assertIsNone(re.search(r"rtmps?://[A-Za-z0-9]", script))
        self.assertIn('LIVECODE_DIR="${LIVECODE_DIR:-}"', script)
        self.assertIn('VOLUME_UUID="${LIVECODE_VOLUME_UUID:-}"', script)
        self.assertIsNone(re.search(r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-", source), "no volume UUID literal")
        self.assertNotIn("HOME/Movies", script, "no fallback to ~/Movies")
        self.assertIn('export TMPDIR="$LIVECODE_DIR/scratch"', script)

    def test_version_help_and_devices_need_no_storage(self):
        proc, _ = self.run_livecode("--version", LIVECODE_DIR=None)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertRegex(proc.stdout, r"\Alivecode \d+\.\d+\.\d+\n\Z")
        proc, _ = self.run_livecode("-h", LIVECODE_DIR=None)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("LIVECODE_ALLOW_INTERNAL", proc.stdout)
        proc, _ = self.run_livecode("devices", LIVECODE_DIR=None)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("defaults: screen=2 camera=0 audio input=1 (MacBook Pro Microphone, macOS default input)",
                      proc.stdout)

    def test_unknown_verb_is_a_usage_error(self):
        proc, argv = self.run_livecode("upload")
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(argv, [])

    def test_record_pipeline_shape(self):
        proc, argv = self.run_livecode("rec")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        joined = " ".join(argv)
        self.assertIn("-i 2:1", joined, "screen plus the macOS default input, never the virtual device")
        self.assertIn("audio input: MacBook Pro Microphone (macOS default input)", proc.stderr)
        self.assertIn("-i 0:none", joined, "the built-in camera, never Desk View")
        graph = argv[argv.index("-filter_complex") + 1]
        self.assertEqual((graph.count("scale="), graph.count("overlay="), graph.count(";")), (2, 1, 3),
                         "screen, camera, overlay and the audio PTS reset only")
        # avfoundation stamps each device on its own clock: every stream is reset to t=0 before composing.
        self.assertIn("[0:v]setpts=PTS-STARTPTS,scale=1920:-2", graph)
        self.assertIn("[1:v]setpts=PTS-STARTPTS,scale=480:-2", graph)
        self.assertIn("[0:a]asetpts=PTS-STARTPTS[a]", graph)
        self.assertEqual(argv[argv.index("-map", argv.index("-map") + 1) + 1], "[a]")
        self.assertIn("scale=480:-2", graph)
        self.assertIn("overlay=x=W-w-24:y=H-h-24", graph)
        self.assertEqual(argv[argv.index("-c:v") + 1], "h264_videotoolbox")
        self.assertEqual(argv[argv.index("-b:v") + 1], "6M")
        out = argv[-1]
        self.assertRegex(out, re.escape(str(self.capture_dir)) + r"/recordings/livecode-\d{8}T\d{6}Z\.mkv$")
        self.assertIn("livecode: saved " + out, proc.stdout)
        self.assertTrue((self.capture_dir / "scratch").is_dir())

    def test_camera_none_drops_the_overlay(self):
        _, argv = self.run_livecode("rec", str(self.capture_dir / "x.mkv"), LIVECODE_CAMERA="none")
        graph = argv[argv.index("-filter_complex") + 1]
        self.assertEqual(graph, "[0:v]setpts=PTS-STARTPTS,scale=1920:-2:flags=bilinear[v];[0:a]asetpts=PTS-STARTPTS[a]")
        self.assertEqual(argv.count("-i"), 1)

    def test_camera_corner_and_fraction(self):
        _, argv = self.run_livecode("rec", str(self.capture_dir / "x.mkv"), LIVECODE_CAM="tl", LIVECODE_CAM_FRAC="5")
        graph = argv[argv.index("-filter_complex") + 1]
        self.assertIn("scale=384:-2", graph)
        self.assertIn("overlay=x=24:y=24", graph)

    def test_storage_dir_is_required(self):
        for env in ({"LIVECODE_DIR": None}, {"LIVECODE_DIR": "relative/dir"}):
            for verb in ("rec", "stream", "preview"):
                with self.subTest(env=env, verb=verb):
                    extra = ["rtmp://ingest.example.invalid/app/k"] if verb == "stream" else []
                    proc, argv = self.run_livecode(verb, *extra, **env)
                    self.assert_refused(proc, argv, "LIVECODE_DIR")

    def test_internal_disk_is_refused_by_default(self):
        for env in ({"STUB_MOUNT": "/"}, {"STUB_INTERNAL": "true"}, {"STUB_INTERNAL": "true", "LIVECODE_VOLUME_UUID": None}):
            with self.subTest(env=env):
                proc, argv = self.run_livecode("rec", **env)
                self.assert_refused(proc, argv)
                self.assertIn("internal disk", proc.stderr)

    def test_unidentified_volume_is_refused(self):
        stub = self.stubs / "diskutil"
        stub.write_text(f"#!{BASH}\nexit 1\n")
        proc, argv = self.run_livecode("rec", LIVECODE_VOLUME_UUID=None)
        self.assert_refused(proc, argv)
        self.assertIn("cannot identify", proc.stderr)

    def test_allow_internal_opts_out(self):
        proc, argv = self.run_livecode("rec", STUB_INTERNAL="true", LIVECODE_VOLUME_UUID=None, LIVECODE_ALLOW_INTERNAL="1")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(argv[-1].endswith(".mkv"))
        self.assertFalse(self.diskutil_calls.exists(), "nothing to ask diskutil without a UUID pin")

    def test_volume_uuid_set_must_match(self):
        proc, argv = self.run_livecode("rec", STUB_UUID=OTHER_UUID)
        self.assert_refused(proc, argv)
        self.assertIn(CAPTURE_UUID, proc.stderr)
        # The pin still applies when internal targets are allowed.
        proc, argv = self.run_livecode("rec", STUB_UUID=OTHER_UUID, STUB_INTERNAL="true", LIVECODE_ALLOW_INTERNAL="1")
        self.assert_refused(proc, argv)

    def test_volume_uuid_unset_accepts_any_external_volume(self):
        proc, argv = self.run_livecode("rec", STUB_UUID=OTHER_UUID, LIVECODE_VOLUME_UUID=None)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(argv[-1].endswith(".mkv"))

    def test_low_free_space_warns_at_the_configured_floor(self):
        proc, _ = self.run_livecode("rec", STUB_AVAIL=str(10 * 1024 * 1024))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("under 50 GiB", proc.stderr)
        proc, _ = self.run_livecode("rec", STUB_AVAIL=str(10 * 1024 * 1024), LIVECODE_MIN_FREE_GIB="5")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("GiB free", proc.stderr)

    def test_stream_redacts_url_and_key(self):
        fake = "live_" + "0123456789abcdef"
        url = f"rtmp://ingest.example.invalid/app/{fake}"
        proc, argv = self.run_livecode("stream", url)
        self.assertEqual(argv[-1], url)
        self.assertEqual(argv[argv.index("-f", argv.index("-c:v")) + 1], "flv")
        self.assertEqual(argv[argv.index("-b:v") + 1], "4500k")
        self.assertEqual(argv[argv.index("-force_key_frames") + 1], "expr:gte(t,n_forced*2)")
        self.assertNotIn(fake, proc.stdout + proc.stderr)
        self.assertIn("<rtmp-url>", proc.stderr)

    def test_stream_url_from_file_pointer(self):
        pointer = self.tmp / "url"
        pointer.write_text("rtmp://ingest.example.invalid/app/filekey12345\n")
        proc, argv = self.run_livecode("stream", LIVECODE_RTMP_URL_FILE=str(pointer))
        self.assertTrue(argv[-1].endswith("/filekey12345"))
        self.assertNotIn("filekey12345", proc.stdout + proc.stderr)

    def test_stream_refuses_a_non_rtmp_url(self):
        proc, argv = self.run_livecode("stream", "https://ingest.example.invalid/app/key12345")
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(argv, [])

    def test_audio_follows_the_macos_default_input(self):
        proc, argv = self.run_livecode("rec", STUB_DEFAULT_INPUT="Example AirPods Pro")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("-i 2:2", " ".join(argv))
        self.assertIn("audio input: Example AirPods Pro", proc.stderr)

    def test_unmappable_default_input_stops(self):
        proc, argv = self.run_livecode("rec", STUB_DEFAULT_INPUT="Some Headset")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("'Some Headset' has no avfoundation audio device", proc.stderr)
        self.assertEqual(argv, [])

    def test_no_audio_knob(self):
        script = code(self.script.read_text())
        self.assertNotIn("LIVECODE_MIC", script)
        self.assertIn("coreaudio_default_audio_input_device", script)

    def test_preview_is_one_frame_of_the_same_composition(self):
        proc, argv = self.run_livecode("preview")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        graph = argv[argv.index("-filter_complex") + 1]
        self.assertIn("scale=960:-2", graph)
        self.assertIn("scale=240:-2", graph)
        self.assertIn("overlay=x=W-w-12:y=H-h-12", graph)
        self.assertIn("[0:v]setpts=PTS-STARTPTS,", graph)
        self.assertIn("[1:v]setpts=PTS-STARTPTS,", graph)
        self.assertIn("select=gte(n\\,15)[v]", graph, "warm-up frames skipped in the graph")
        self.assertNotIn("asetpts", graph)
        self.assertEqual(argv[argv.index("-fps_mode") + 1], "passthrough")
        self.assertNotIn("-ss", argv, "-ss waits on raw device PTS")
        self.assertIn("-i 2:none", " ".join(argv), "preview captures no audio")
        self.assertEqual(argv[argv.index("-frames:v") + 1], "1")
        for encoder_flag in ("-c:v", "-b:v", "-c:a"):
            self.assertNotIn(encoder_flag, argv)
        png = self.capture_dir / "scratch" / "preview.png"
        self.assertTrue(png.is_file())
        self.assertEqual((self.tmp / "ql-argv").read_text().splitlines(), ["-p", str(png)])

    def test_preview_is_behind_the_storage_guard(self):
        proc, argv = self.run_livecode("preview", STUB_MOUNT="/")
        self.assert_refused(proc, argv)
        self.assertFalse((self.tmp / "ql-argv").exists())

    def test_help_says_operator_only(self):
        script = self.script.read_text()
        self.assertIn("Agents never start them", script)
        self.assertIn("Bluetooth headset profile", script)


if __name__ == "__main__":
    unittest.main()
