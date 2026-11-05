"""What the lane L4 stages share: the typed stage refusal, the run environment, FFmpeg calls and loudness meters.

A stage refusal is a verdict or a failure, as kitpip.KitpipRefused is. A verdict repeats for the same stage key (a
loudness drift, an edition refusal, a placement overlap); the store records it and the node stays refused until its
key changes. A failure says nothing about the key (a source missing from the private store, no lexical release, an
FFmpeg crash, an engine that does not answer): nothing is recorded and calling run again retries it.
"""

import json
import tempfile
from contextlib import contextmanager
from pathlib import Path

from .. import audio, policy
from ..config import FF, run
from .job import JobError

RATE_HZ = 48000  # every stem on the base clock: voice.wav, clips.wav, bed.wav, mix.wav
LIMITER_HEADROOM_DB = 0.5  # the one limiter sits this far under the delivery's true-peak ceiling (-2.0 for -1.5)


class StageRefused(JobError):
    """A stage refused. verdict is True when the same key would refuse again (the store records it) and False for a
    failure a retry may clear."""

    def __init__(self, code, detail, verdict=True):
        super().__init__(code, detail)
        self.verdict = verdict


class Env:
    """What a run reads besides the job: the records directory and its tables, the private store and its index
    ({sha256: path}) and the pinned xoxd-lexical release directory, if any."""

    def __init__(self, records_dir, records, store_dir, lexical=None):
        self.records_dir = Path(records_dir).resolve()
        self.records = records
        self.store_dir = Path(store_dir).resolve()
        self.index = policy.store_index(self.store_dir)
        self.lexical = Path(lexical).resolve() if lexical else None

    def source(self, digest, what):
        path = self.index.get(digest)
        if path is None:
            raise StageRefused("source_missing", f"{what} is not in the private store", verdict=False)
        return Path(path)

    def record_file(self, name):
        path = self.records_dir / name
        if path.is_symlink() or not path.is_file():
            raise StageRefused("records_missing", f"the records directory has no {name}", verdict=False)
        return path


def ffmpeg(*args, timeout=None):
    """One FFmpeg call with bit-exact output flags left to the caller. A crash is a failure, not a verdict."""
    try:
        return run(*FF, "-v", "error", *args, timeout=timeout)
    except RuntimeError as exc:
        raise StageRefused("ffmpeg_failed", str(exc).splitlines()[0][:200], verdict=False) from None


def ffprobe(path):
    """ffprobe's JSON for a media file's streams and format."""
    try:
        done = run(
            "ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path), timeout=120
        )
        return json.loads(done.stdout)
    except (RuntimeError, ValueError) as exc:
        raise StageRefused("ffprobe_failed", str(exc).splitlines()[0][:200], verdict=False) from None


BITEXACT = ("-fflags", "+bitexact", "-flags:a", "+bitexact")


def to_mono(source, target, rate=RATE_HZ, chain=None):
    """source as mono 16-bit PCM at rate into target, through an optional filter chain. Returns target. No tag or
    chapter of the source passes: without -map_metadata -1 the WAV muxer writes a source's title and comment into a
    LIST/INFO chunk, and base's clips.wav reaches the handoff layers (TIN-7788)."""
    filters = ["-af", chain] if chain else []
    ffmpeg("-i", str(source), *filters, "-ac", "1", "-ar", str(rate), "-c:a", "pcm_s16le",
           "-map_metadata", "-1", "-map_chapters", "-1", *BITEXACT, str(target))  # fmt: skip
    return target


def loudness(path):
    """{integrated_lufs, loudness_range_lu, true_peak_dbtp} of a file's sound (EBU R128, FFmpeg ebur128)."""
    try:
        integrated, lra, peak = audio.ebur128(path)
    except (RuntimeError, ValueError) as exc:
        raise StageRefused("ffmpeg_failed", str(exc).splitlines()[0][:200], verdict=False) from None
    return {"integrated_lufs": integrated, "loudness_range_lu": lra, "true_peak_dbtp": peak}


@contextmanager
def work_dir(store):
    """A scratch directory inside the job directory, outside every stage directory, removed afterwards."""
    store.dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=store.dir, prefix=".work-") as work:
        yield Path(work)


def upstream(store, node_id):
    """(manifest, directory) of a fresh upstream node."""
    entry = store.entry(node_id)
    manifest = store.manifest(node_id)
    if entry is None or manifest is None:
        raise StageRefused("stage_input_stale", f"{node_id} has no current run", verdict=False)
    return manifest, store.dir / entry["dir"]


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
