import shutil
import subprocess

import pytest

from condense.recover import recover


def record(path, seconds, tone):
    src = [
        "-f",
        "lavfi",
        "-i",
        f"testsrc2=s=320x180:r=30:d={seconds}",
        "-f",
        "lavfi",
        "-i",
        f"sine=f={tone}:d={seconds}",
    ]
    codec = ["-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac"]
    subprocess.run(["ffmpeg", "-v", "error", "-y", *src, *codec, path], check=True)


@pytest.mark.skipif(not shutil.which("untrunc"), reason="untrunc is not packaged for this platform")
def test_a_truncated_recording_plays_again(tmp_path):
    ref, full, broken, fixed = (tmp_path / f"{n}.mov" for n in ("ref", "full", "broken", "fixed"))
    record(ref, 40, 300)
    record(full, 30, 500)
    broken.write_bytes(full.read_bytes()[: full.stat().st_size * 7 // 10])  # the moov atom at the end is lost
    probe = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0"]
    assert subprocess.run([*probe, broken], capture_output=True).returncode != 0
    recover(ref, broken, fixed)
    assert float(subprocess.run([*probe, fixed], capture_output=True, text=True).stdout) == pytest.approx(21, abs=1.5)
    with pytest.raises(SystemExit):
        recover(ref, tmp_path / "missing.mov", tmp_path / "none.mov")
