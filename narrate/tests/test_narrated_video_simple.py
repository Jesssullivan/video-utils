"""The narrated-video simple path (lane L4, docs/spec/NARRATED_VIDEO.md): script, voice, voice_qa, base, place, music
and mix run for real on synthetic fixtures, end to end and stage by stage.

Every input is generated or a committed synthetic fixture: the fake engine's sine voice, the two generated E-major bed
loops, colour cards, an FFmpeg test pattern with a quiet tone and AM noise bursts as a speech-like signal. Nothing
here is a recording. Whisper is pointed at a model that does not exist, so WER stays not_measured on every host.
"""

import array
import copy
import hashlib
import json
import math
import random
import shutil
import subprocess
from pathlib import Path

import pytest

from narrate import audio
from narrate.video import cli, fixture, graph, labels, mix, music, place, run, speech, store
from narrate.video.common import RATE_HZ, Env, StageRefused
from narrate.video.job import init_job, load_records

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "narrated-video"
L4 = ("script/seg-1", "base", "music", "voice/seg-1", "voice_qa/seg-1", "place", "mix")


@pytest.fixture(autouse=True)
def no_whisper(monkeypatch, tmp_path):
    monkeypatch.setenv("NARRATE_WHISPER_MODEL", str(tmp_path / "no-whisper-model.bin"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Workspace:
    """A fixture workspace (records, store, lexical) and a job store under one directory."""

    def __init__(self, base):
        self.base = Path(base)
        self.paths = fixture.write(self.base / "ws")
        self.reload()

    def reload(self):
        self.records = load_records(self.paths["records"])
        self.env = Env(self.paths["records"], self.records, self.paths["store"], self.paths["lexical"])

    def edit_records(self, name, edit):
        path = self.paths["records"] / name
        rows = json.loads(path.read_text())
        edit(rows)
        path.write_text(json.dumps(rows, indent=1))
        self.reload()

    def add_source(self, path):
        target = self.paths["store"] / Path(path).name
        if Path(path) != target:
            shutil.copyfile(path, target)
        self.reload()
        return sha(target)

    def job(self, job_id="nv-simple", bed=fixture.BED, **edits):
        job = init_job(job_id, fixture.NARRATE_JOB, sha(self.paths["script"]), bed=bed)
        for path, value in edits.items():
            node = job
            *parents, last = path.split(".")
            for part in parents:
                node = node[part]
            node[last] = value
        return job

    def store(self, job, replace=False):
        s = store.JobStore(self.base / "narrated", job["id"])
        s.write_job(job, replace=replace)
        return s

    def ctx(self):
        return {"pin": None, "kitpip": None, "ffmpeg": cli.ffmpeg_identity(), "sources": set(self.env.index)}

    def run(self, job, replace=False, **kwargs):
        s = self.store(job, replace=replace)
        rc = run.RunContext(job, self.records, s, self.ctx(), self.env)
        result, g = run.run(rc, **kwargs)
        return s, result, g


def node_dir(s, node):
    return s.dir / s.entry(node)["dir"]


def wav(path):
    return audio.read(path)


def rms_db(samples):
    if not samples:
        return -math.inf
    return 10 * math.log10(math.sumprod(samples, samples) / len(samples) / 32768.0**2)


@pytest.fixture(scope="module")
def settled(tmp_path_factory, ffmpeg):
    """One simple job (card, the fixture bed, defaults) run end to end once; tests copy it before changing it."""
    with pytest.MonkeyPatch.context() as mp:
        base = tmp_path_factory.mktemp("settled")
        for name in ("WHISPER_MODEL", "NARRATE_STORE", "NARRATE_LEXICAL_DIR", "NARRATE_SIM_MODEL"):
            mp.delenv(name, raising=False)
        mp.delenv("NARRATE_SIM_PYTHON", raising=False)
        mp.setenv("NARRATE_SCORER_LOCK", str(base / "scorer.lock"))
        mp.setenv("NARRATE_WHISPER_MODEL", str(base / "no-whisper-model.bin"))
        ws = Workspace(base)
        job = ws.job()
        s, result, g = ws.run(job)
    return {"base": base, "job": job, "result": result}


@pytest.fixture
def copied(settled, tmp_path):
    """A private copy of the settled workspace and store."""
    shutil.copytree(settled["base"], tmp_path / "copy")
    ws = Workspace.__new__(Workspace)
    ws.base = tmp_path / "copy"
    ws.paths = {
        "records": ws.base / "ws" / "records",
        "store": ws.base / "ws" / "store",
        "lexical": ws.base / "ws" / "lexical",
        "script": ws.base / "ws" / "store" / "script.md",
    }
    ws.reload()
    job = copy.deepcopy(settled["job"])
    return ws, job


def ran(result):
    return [r["node"] for r in result["ran"]]


# End to end ------------------------------------------------------------------------------------------------------
def test_a_simple_job_runs_script_to_mix_and_yields_a_labelled_mixed_stem(settled):
    result = settled["result"]
    assert result["ok"] is True and "refused" not in result
    assert sorted(ran(result)) == sorted(L4)
    assert {n: result["states"][n] for n in L4} == {n: "fresh" for n in L4}
    assert result["waiting_on_lane"] == {"compose": "L6", "deliver_check": "L6"}
    assert result["states"]["avatar/seg-1"] == "not_selected" and result["states"]["handoff"] == "not_selected"
    s = store.JobStore(settled["base"] / "narrated", "nv-simple")
    assert all(problems == [] for problems in s.verify().values())
    mixed = s.manifest("mix")
    m = mixed["measurements"]
    assert abs(m["integrated_lufs"] - (-16)) <= 0.5 and abs(m["drift_lu"]) <= 0.5
    assert m["true_peak_dbtp"] <= -1.5
    assert 6 <= m["duck_depth_db"] <= 8 and m["gates"] == {"duck_min_3db": "passed"} and m["flags"] == []
    assert m["bed_below_voice_lu"] == 20 and m["duck_mode"] == "Sidechain" and m["channels"] == "Mono"
    assert mixed["labels"] == {
        "synthetic": True,
        "consent_ids": ["consent-fixture-sine"],
        "voice_ids": ["voice-fixture-sine"],
        "persona": None,
    }
    assert mixed["synthetic"] is True and mixed["states"]["listening"] == "pending_operator"
    out = node_dir(s, "mix")
    assert sorted(mixed["outputs"]) == ["bed-ducked.wav", "mix.json", "mix.wav"]
    channels, width, rate, frames = audio.wav_format(out / "mix.wav")
    assert (channels, width, rate, frames) == (1, 2, RATE_HZ, m["total_samples"])
    # The program runs to the narration's end plus the music tail, a whole number of frames at 30/1.
    placed = s.manifest("place")["measurements"]
    assert m["total_samples"] % (RATE_HZ // 30) == 0
    assert m["length_s"] >= placed["voice_end_s"] + 5 > m["length_s"] - 1 / 30


def test_a_second_run_runs_nothing_and_every_stage_dir_holds_no_private_path(settled):
    s = store.JobStore(settled["base"] / "narrated", "nv-simple")
    ws_root = str(settled["base"])
    for node in L4:
        directory = node_dir(s, node)
        for path in directory.rglob("*.json"):
            if path.parent.name == speech.RUN:
                continue  # narrate's own run manifest keeps its run_dir, as every narrate run does
            assert ws_root not in path.read_text(), f"{node}: {path.name} names a private path"


def test_rerunning_is_idempotent_and_a_forced_music_rerun_stops_the_cascade(copied):
    ws, job = copied
    s, result, _ = ws.run(job)
    assert ran(result) == [] and result["ok"]
    before = s.entry("mix")
    s, result, _ = ws.run(job, forced=["music"])
    assert ran(result) == ["music"]
    assert s.entry("mix") == before and list(s.history.iterdir())


def test_a_forced_voice_rerun_that_renders_the_same_narration_keeps_every_later_stage(copied):
    ws, job = copied
    before = ws.store(job).entry("voice/seg-1")
    s, result, _ = ws.run(job, forced=["voice"])
    assert ran(result) == ["voice/seg-1"]
    assert s.entry("voice/seg-1")["content_sha256"] == before["content_sha256"]


def test_the_narrate_run_manifest_is_still_rehashed_and_tampering_makes_the_voice_corrupt(copied):
    ws, job = copied
    s = ws.store(job)
    manifest = node_dir(s, "voice/seg-1") / speech.RUN / "manifest.json"
    manifest.write_text(manifest.read_text().replace('"rendered_unreviewed"', '"accepted"'))
    g = graph.plan(job, ws.records, s, ws.ctx())
    row = next(n for n in g["nodes"] if n["id"] == "voice/seg-1")
    assert row["state"] == "corrupt" and row["reason"].startswith("output_digest_mismatch")


def test_a_pronunciation_edit_and_an_engine_edit_each_rerun_the_voice_and_what_follows(copied):
    ws, job = copied
    narration = ws.store(job).manifest("voice/seg-1")["measurements"]["narration_sha256"]

    def respell(table):
        table["entries"].append(
            {"caseSensitive": False, "note": None, "spoken": "fix sure", "wholeWord": True, "written": "fixture"}
        )

    ws.edit_records("pronunciation.json", respell)
    s, result, _ = ws.run(job)
    assert ran(result) == ["voice/seg-1", "voice_qa/seg-1", "place", "mix"] and result["ok"]
    assert s.manifest("voice/seg-1")["measurements"]["narration_sha256"] != narration

    def repin(rows):
        rows[0]["model"] = "fake-sine-v2"

    ws.edit_records("engines.json", repin)
    s, result, _ = ws.run(job)
    assert ran(result)[:2] == ["voice/seg-1", "voice_qa/seg-1"] and result["ok"]
    assert ws.run(job)[1]["ran"] == []


def test_a_persona_change_reruns_place_and_mix_only_and_the_chain_holds(copied):
    ws, job = copied
    keep = {n: ws.store(job).entry(n) for n in ("script/seg-1", "voice/seg-1", "voice_qa/seg-1", "base", "music")}
    for persona in ("persona-probe-a", "persona-probe-b"):
        job["labels"]["persona"] = persona
        s, result, _ = ws.run(job, replace=True)
        assert ran(result) == ["place", "mix"] and result["ok"] and "refused" not in result
        assert {n: s.entry(n) for n in keep} == keep
        assert s.manifest("place")["labels"]["persona"] == persona == s.manifest("mix")["labels"]["persona"]
        assert s.manifest("voice/seg-1")["labels"]["persona"] is None
    job["base"]["card"]["tailS"] += 1
    s, result, _ = ws.run(job, replace=True)
    assert ran(result) == ["place", "mix"] and result["ok"] and s.current()["refusals"] == {}


def test_a_bed_level_change_reruns_only_mix(copied):
    ws, job = copied
    keep = {n: ws.store(job).entry(n) for n in L4 if n != "mix"}
    job["music"]["bedBelowVoiceLu"] = 24
    s, result, _ = ws.run(job, replace=True)
    assert ran(result) == ["mix"]
    assert {n: s.entry(n) for n in keep} == keep
    m = s.manifest("mix")["measurements"]
    assert m["bed_below_voice_lu"] == 24


def test_stereo_delivery_keeps_the_integrated_loudness(copied):
    ws, job = copied
    job["delivery"]["channels"] = "Stereo"
    s, result, _ = ws.run(job, replace=True)
    assert ran(result) == ["mix"] and result["ok"]
    m = s.manifest("mix")["measurements"]
    assert audio.wav_format(node_dir(s, "mix") / "mix.wav")[0] == 2
    assert abs(m["drift_lu"]) <= 0.5 and m["true_peak_dbtp"] <= -1.5


# Mix levels, measured on the audio ---------------------------------------------------------------------------------
def test_the_bed_sits_20_lu_under_the_voice_and_ducks_7_db_under_the_placed_voice(tmp_path, ffmpeg):
    ws = Workspace(tmp_path)
    job = ws.job("nv-duck")
    job["segments"][0]["anchor"] = {"atSeconds": 4.0}
    job["music"]["duckMode"] = "EdlEnvelope"
    s, result, _ = ws.run(job)
    assert result["ok"], result
    m = s.manifest("mix")["measurements"]
    bed = wav(node_dir(s, "music") / "bed.wav").samples
    ducked = wav(node_dir(s, "mix") / "bed-ducked.wav").samples
    total = m["total_samples"]
    gain = 10 ** (m["bed_gain_db"] / 20)
    reference = array.array("h", (round(v * gain) for v in (bed * (total // len(bed) + 1))[:total]))
    # Un-ducked, the bed's integrated loudness sits bedBelowVoiceLu under the measured voice.
    ref_path = tmp_path / "reference.wav"
    audio.Pcm(RATE_HZ, reference).write(ref_path)
    integrated, _, _ = audio.ebur128(ref_path)
    assert abs((m["voice_integrated_lufs"] - integrated) - 20) <= 0.5
    # Before the voice (after the 3 s fade-in) the bed is untouched; under the voice it sits 7 dB down.
    a, b = round(3.2 * RATE_HZ), round(3.9 * RATE_HZ)
    assert abs(rms_db(ducked[a:b]) - rms_db(reference[a:b])) <= 0.3
    a, b = round(4.5 * RATE_HZ), round(8.5 * RATE_HZ)
    depth = rms_db(reference[a:b]) - rms_db(ducked[a:b])
    assert 6 <= depth <= 8 and abs(depth - 7) <= 0.3
    # The 5 s fade-out ends the program at silence.
    assert rms_db(ducked[-480:]) < rms_db(reference[-480:]) - 30


def test_the_level_gates_refuse_drift_over_half_a_lu_and_a_hot_true_peak():
    delivery = {"targetLufs": -16, "driftLu": 0.5, "truePeakDbtp": -1.5}
    assert mix.gates(-16.4, -16.4, -1.5, delivery) == []
    assert [c for c, _ in mix.gates(None, -15.4, -3, delivery)] == ["loudness_drift"]
    assert [c for c, _ in mix.gates(None, -16.6, -3, delivery)] == ["loudness_drift"]
    assert [c for c, _ in mix.gates(None, -16.0, -1.4, delivery)] == ["true_peak_exceeded"]
    assert [c for c, _ in mix.gates(-16.6, None, None, delivery)] == ["foreground_not_normalised"]


def speech_like(seed, seconds):
    """AM noise bursts: syllables of 120 to 220 ms, short gaps inside words and 500 ms gaps between phrases."""
    rng = random.Random(seed)
    out, t = array.array("h"), 0
    while len(out) < seconds * RATE_HZ:
        for _ in range(rng.randint(3, 6)):
            n = round(rng.uniform(0.12, 0.22) * RATE_HZ)
            out.extend(round(8000 * math.sin(math.pi * k / n) * rng.uniform(-1, 1)) for k in range(n))
            out.extend([0] * round(rng.uniform(0.03, 0.08) * RATE_HZ))
        out.extend([0] * round(0.5 * RATE_HZ))
        t += 1
    return out[: seconds * RATE_HZ]


def test_the_sidechain_envelope_on_a_speech_like_signal_holds_the_depth_and_its_ramps():
    signal = speech_like(7, 6)
    keys = mix.sidechain_keys(mix.block_power(signal))
    env = mix.envelope(keys, 7, 50, 400)
    assert min(env) == -7 and max(env) == 0
    first = keys.index(True)
    assert env[first + 4] == pytest.approx(-7)  # 50 ms attack: 5 blocks of 10 ms
    assert env[first + 3] > -7
    # After the last syllable the gain comes back at 7 dB per 400 ms: 40 blocks to unity.
    last = len(keys) - 1 - keys[::-1].index(True)
    if last + 41 < len(env):
        assert env[last + 40] == 0 and env[last + 20] < 0
    assert 6 <= mix.duck_depth(env, keys) <= 8
    # Span keys cover exactly the blocks a span touches.
    assert mix.span_keys([(480, 961)], 4) == [False, True, True, False]
    assert mix.span_keys([(480, 960)], 4) == [False, True, False, False]
    # The 1 kHz envelope interpolates each block in dB and never exceeds unity gain.
    samples = mix.envelope_samples([0.0, -7.0, -7.0])
    assert len(samples) == 30 and samples[9] == 32767 and samples[19] == round(32767 * 10 ** (-7 / 20))


def test_a_voice_off_its_target_refuses_foreground_not_normalised_and_the_refusal_holds(tmp_path, ffmpeg):
    ws = Workspace(tmp_path)

    def quieter(rows):
        rows[0]["post"]["loudnessLufs"] = -20

    ws.edit_records("jobs.json", quieter)
    job = ws.job("nv-quiet")
    s, result, _ = ws.run(job)
    assert result["refused"] == "foreground_not_normalised" and result["node"] == "mix" and result["recorded"]
    assert not result["ok"] and s.current()["refusals"]["mix"]["code"] == "foreground_not_normalised"
    assert {n: result["states"][n] for n in L4 if n != "mix"} == {n: "fresh" for n in L4 if n != "mix"}
    assert result["states"]["mix"] == "refused" and not list((s.dir / "stages" / "mix").glob("*.partial"))
    s, again, _ = ws.run(job)
    assert ran(again) == [] and again["refused"] == "foreground_not_normalised"


# Place -----------------------------------------------------------------------------------------------------------
FPS = {"num": 30, "den": 1}


def test_placement_property_segments_start_on_their_anchor_never_overlap_and_end_inside_the_base():
    rng = random.Random(20261027)
    for _ in range(300):
        count = rng.randint(1, 5)
        segments, cursor = [], 0
        for k in range(count):
            samples = rng.randint(1, 10 * RATE_HZ)
            if rng.random() < 0.5:
                anchor = "Auto"
                start = cursor
            else:
                start = cursor + rng.randint(0, 3 * RATE_HZ)
                anchor = {"atSeconds": start / RATE_HZ}
            segments.append({"id": f"s{k}", "anchor": anchor, "samples": samples})
            cursor = start + samples
        extendable = rng.random() < 0.5
        base = {"extendable": True, "length_samples": None, "frames": None}
        if not extendable:
            frames = rng.randint(1, 40 * 30)
            base = {"extendable": False, "length_samples": place.samples_for(frames, FPS), "frames": frames}
        tail = rng.choice([0, 0.5, 1, 2.25])
        try:
            out = place.layout(segments, FPS, base, tail)
        except StageRefused as exc:
            assert exc.code == "base_too_short" and not extendable and cursor > base["length_samples"]
            continue
        for row, segment in zip(out["segments"], segments, strict=True):
            if segment["anchor"] != "Auto":
                want = round(segment["anchor"]["atSeconds"] * RATE_HZ)
                assert abs(row["start_sample"] - want) <= RATE_HZ // 30  # within one frame of the anchor
            assert row["end_sample"] - row["start_sample"] == segment["samples"]
            assert row["end_sample"] <= out["total_samples"]
        ordered = sorted(out["segments"], key=lambda r: r["start_sample"])
        assert all(a["end_sample"] <= b["start_sample"] for a, b in zip(ordered, ordered[1:], strict=False))
        if extendable:
            assert out["total_samples"] >= cursor + round(tail * RATE_HZ)
            assert out["total_samples"] == place.samples_for(out["frames"], FPS)
            assert out["total_samples"] - (cursor + round(tail * RATE_HZ)) < RATE_HZ // 30
        else:
            assert out["total_samples"] == base["length_samples"]


def test_a_frame_rate_is_read_from_the_first_positive_ffprobe_rate():
    assert place.parse_rate("0/0", "25/1") == {"num": 25, "den": 1}
    assert place.parse_rate("30000/1001") == {"num": 30000, "den": 1001}
    with pytest.raises(StageRefused) as caught:
        place.parse_rate("0/0", None, "x")
    assert caught.value.code == "base_invalid"


@pytest.mark.parametrize(
    ("segments", "code"),
    [
        ([{"id": "a", "anchor": {"atSeconds": 1.0}, "samples": RATE_HZ * 2},
          {"id": "b", "anchor": {"atSeconds": 2.0}, "samples": 10}], "placement_overlap"),
        ([{"id": "a", "anchor": {"atSeconds": -0.5}, "samples": 10}], "anchor_invalid"),
        ([{"id": "a", "anchor": {"page": "p1"}, "samples": 10}], "anchor_needs_deck"),
    ],
)  # fmt: skip
def test_placement_refusals(segments, code):
    with pytest.raises(StageRefused) as caught:
        place.layout(segments, FPS, {"extendable": True, "length_samples": None, "frames": None}, 1)
    assert caught.value.code == code and caught.value.verdict


def test_edition_check_at_place_reads_the_placed_stems_and_the_bed_gate(copied):
    ws, job = copied
    synthetic = [{"synthetic": True}]
    assert place.edition_at_place(job, ws.records, synthetic)["verdict"] == "Admitted"
    voice_only = copy.deepcopy(job) | {"edition": "ClientVoiceOnly", "segments": [], "music": None}
    with pytest.raises(StageRefused) as caught:
        place.edition_at_place(voice_only, ws.records, synthetic)
    assert caught.value.code == "edition_voice_refused"
    assert place.edition_at_place(voice_only, ws.records, [{"synthetic": False}])["verdict"] == "Admitted"
    narrated = copy.deepcopy(job) | {"edition": "ClientNarrated"}
    with pytest.raises(StageRefused) as caught:
        place.edition_at_place(narrated, ws.records, synthetic)
    assert caught.value.code == "edition_bed_refused"


def test_labels_only_grow_and_a_dropped_label_breaks_the_chain():
    voice = {"labels": {"synthetic": True, "consent_ids": ["c1"], "voice_ids": ["v1"], "persona": "p"}}
    other = {"labels": {"synthetic": True, "consent_ids": ["c2"], "voice_ids": ["v2"], "persona": "p"}}
    grown = labels.grow([voice, other, {"labels": {}}], "p")
    assert grown == {"synthetic": True, "consent_ids": ["c1", "c2"], "voice_ids": ["v1", "v2"], "persona": "p"}
    assert labels.check(grown, [voice, other], "p") == grown
    for broken in (
        grown | {"synthetic": False},
        grown | {"consent_ids": ["c1"]},
        grown | {"voice_ids": ["v2"]},
        grown | {"persona": "q"},
    ):
        with pytest.raises(StageRefused) as caught:
            labels.check(broken, [voice, other], "p" if broken["persona"] == "p" else "q")
        assert caught.value.code == "label_chain_broken" and caught.value.verdict


# Bases -----------------------------------------------------------------------------------------------------------
def make_media(path, *args):
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", *args, str(path)], check=True)
    return path


def test_a_still_is_conformed_to_the_job_size_and_a_card_to_its_colour(tmp_path, ffmpeg):
    ws = Workspace(tmp_path)
    still = make_media(tmp_path / "still.png", "-f", "lavfi", "-i", "testsrc2=s=640x360:d=1", "-frames:v", "1")
    digest = ws.add_source(still)
    job = init_job("nv-still", fixture.NARRATE_JOB, sha(ws.paths["script"]), still=digest)
    s, result, _ = ws.run(job, until="base")
    assert ran(result) == ["base"]
    probe = json.loads(
        subprocess.run(
            ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", str(node_dir(s, "base") / "base.png")],
            capture_output=True,
            check=True,
        ).stdout
    )["streams"][0]
    assert (probe["width"], probe["height"]) == (1920, 1080)
    m = s.manifest("base")["measurements"]
    assert m == {
        "fps": FPS,
        "size": {"w": 1920, "h": 1080},
        "frames": None,
        "length_s": None,
        "extendable": True,
        "clip_sound": False,
    }


def test_a_video_base_keeps_its_rate_and_its_quiet_clip_sound_ducks_the_bed_with_the_voice(tmp_path, ffmpeg):
    ws = Workspace(tmp_path)
    video = make_media(
        tmp_path / "base-video.mp4",
        "-f", "lavfi", "-i", "testsrc2=s=320x180:r=25:d=12",
        "-f", "lavfi", "-i", "sine=f=220:d=12:sample_rate=48000",
        "-af", "volume=-40dB", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest",
    )  # fmt: skip
    digest = ws.add_source(video)
    job = ws.job("nv-video")
    job["base"] = {"video": {"sha256": digest, "keepBaseAudio": True}}
    s, result, _ = ws.run(job)
    assert result["ok"], result
    base = s.manifest("base")["measurements"]
    assert base["fps"] == {"num": 25, "den": 1} and base["size"] == {"w": 320, "h": 180}
    assert base["frames"] == 300 and base["clip_sound"] is True and base["extendable"] is False
    placed = s.manifest("place")
    assert sorted(placed["outputs"]) == ["clips.wav", "placements.json", "voice.wav"]
    m = s.manifest("mix")["measurements"]
    assert m["total_samples"] == 12 * RATE_HZ and abs(m["drift_lu"]) <= 0.5


def test_a_video_shorter_than_the_narration_refuses_base_too_short(tmp_path, ffmpeg):
    ws = Workspace(tmp_path)
    video = make_media(
        tmp_path / "short.mp4", "-f", "lavfi", "-i", "testsrc2=s=160x90:r=30:d=2", "-c:v", "libx264", "-preset",
        "ultrafast",
    )  # fmt: skip
    job = ws.job("nv-short", bed=None)
    job["base"] = {"video": {"sha256": ws.add_source(video), "keepBaseAudio": False}}
    s, result, _ = ws.run(job)
    assert result["refused"] == "base_too_short" and result["node"] == "place" and result["recorded"]


def test_a_deck_base_waits_for_the_deck_seam_and_records_nothing(tmp_path, ffmpeg):
    ws = Workspace(tmp_path)
    store_files = fixture.port().fixtures()
    job = ws.job("nv-deck", bed=None)
    job["base"] = {
        "deck": {
            "producer": "fixture",
            "videoSha256": hashlib.sha256(store_files["deck-video.txt"]).hexdigest(),
            "timelineSha256": hashlib.sha256(store_files["deck-timeline.txt"]).hexdigest(),
            "stemsSha256": hashlib.sha256(store_files["deck-stems.txt"]).hexdigest(),
            "tightenEditsSha256": None,
        }
    }
    s, result, _ = ws.run(job, until="base")
    assert result["refused"] == "base_deck_pending" and result["recorded"] is False
    assert s.current()["refusals"] == {} and result["states"]["base"] == "stale"


# Music -----------------------------------------------------------------------------------------------------------
def test_the_bed_cycle_repeats_every_loop_whole_and_records_its_layers(copied):
    ws, job = copied
    s = ws.store(job)
    manifest = s.manifest("music")
    m = manifest["measurements"]
    assert m["cycle_samples"] == 6 * RATE_HZ and m["cycle_rule"] == "lcm" and m["headroom_gain_db"] == 0
    assert manifest["timeline"]["stretch_applied"] is False
    # The licence gates belong to deliver_check, whose key holds them; music records no licence state.
    assert manifest["states"] == {"source_checks": "passed", "render": "local"}
    bed = json.loads((node_dir(s, "music") / "bed.json").read_text())
    assert [layer["repeats"] for layer in bed["layers"]] == [3, 2]
    assert music.cycle_length([96000, 144000]) == (288000, "lcm")
    assert music.cycle_length([RATE_HZ * 7 + 1, RATE_HZ * 11 + 3]) == (RATE_HZ * 11 + 3, "longest")


def test_a_tempo_factor_stretches_a_layer_and_a_wrong_byte_count_refuses(copied):
    ws, job = copied

    def faster(rows):
        rows[0]["layers"][1]["tempoFactor"] = 1.25

    ws.edit_records("music-beds.json", faster)
    s, result, _ = ws.run(job, until="music")
    assert ran(result) == ["music"]
    manifest = s.manifest("music")
    assert manifest["timeline"]["stretch_applied"] is True
    assert [layer["tempo_factor"] for layer in manifest["timeline"]["layers"]] == [1, 1.25]

    def wrong_bytes(rows):
        rows[0]["layers"][0]["bytes"] += 2

    ws.edit_records("music-beds.json", wrong_bytes)
    s, result, _ = ws.run(job, until="music")
    assert result["refused"] == "bed_digest_mismatch" and result["recorded"]

    # A factor outside 0.5 to 2.0 refuses once at admit, before FFmpeg's atempo sees it.
    for factor in (2.5, 0.25):
        ws.edit_records("music-beds.json", lambda rows, f=factor: rows[0]["layers"][1].update(tempoFactor=f))
        s, result, _ = ws.run(job, until="music")
        assert (result["refused"], result["node"], ran(result)) == ("knob_out_of_bounds", "admit", [])


# Timeline contract -----------------------------------------------------------------------------------------------
def test_place_mix_and_music_write_the_timeline_shapes_of_their_contract_fixtures(settled):
    s = store.JobStore(settled["base"] / "narrated", "nv-simple")
    nv = json.loads((FIXTURES / "narrated_video_v1.json").read_text())
    bed = json.loads((FIXTURES / "music_bed_v1.json").read_text())
    for node in ("place", "mix"):
        timeline = s.manifest(node)["timeline"]
        assert set(timeline) == set(nv) and timeline["mapping"] == "narrated_video_v1"
        assert timeline["no_time_stretch"] is False and timeline["stretch_applied"] is False
        assert (timeline["clock"], timeline["sample_rate"], timeline["fps"]) == ("base", RATE_HZ, FPS)
        assert timeline["output_axis"] == nv["output_axis"] and timeline["source_axis"] == nv["source_axis"]
        assert timeline["placements"]["sha256"] == s.manifest("place")["outputs"]["placements.json"]
    timeline = s.manifest("music")["timeline"]
    assert set(timeline) == set(bed) and timeline["mapping"] == "music_bed_v1"
    assert timeline["no_time_stretch"] is False and timeline["sample_rate"] == RATE_HZ
    assert [set(layer) for layer in timeline["layers"]] == [set(layer) for layer in bed["layers"]]
    assert timeline["output_axis"] == bed["output_axis"] and timeline["source_axis"] == bed["source_axis"]
    voice = s.manifest("voice/seg-1")
    assert voice["timeline"]["mapping"] == "narration_v1" and voice["timeline"]["no_time_stretch"] is False


# CLI -------------------------------------------------------------------------------------------------------------
def call(capsys, argv):
    code = cli.main(argv)
    out, err = capsys.readouterr()
    return code, out, err


def test_cli_fixture_init_run_and_stage(tmp_path, capsys, ffmpeg):
    code, out, _ = call(capsys, ["fixture", "--out", str(tmp_path / "ws")])
    paths = json.loads(out)
    assert code == 0 and paths["narrate_job"] == fixture.NARRATE_JOB
    common = ["--root", str(tmp_path / "narrated"), "--records", paths["records"]]
    code, _, _ = call(
        capsys,
        ["init", "--job", "nv-cli", "--narrate-job", paths["narrate_job"], "--script", paths["script"]]
        + ["--bed", "bed-fixture-emaj"]
        + common,
    )
    assert code == 0
    run_args = common + ["--store", paths["store"], "--lexical", paths["lexical"], "--json"]
    code, out, _ = call(capsys, ["stage", "nv-cli", "mix"] + run_args)
    result = json.loads(out)
    assert code == 1 and result["refused"] == "stage_input_stale" and result["ran"] == []
    code, out, _ = call(capsys, ["run", "nv-cli", "--until", "place"] + run_args)
    result = json.loads(out)
    assert code == 0 and "mix" not in ran(result) and "music" not in ran(result)
    assert result["states"]["place"] == "fresh" and result["states"]["music"] == "stale"
    code, out, _ = call(capsys, ["stage", "nv-cli", "mix"] + run_args)
    assert code == 1 and json.loads(out)["refused"] == "stage_input_stale"
    code, out, _ = call(capsys, ["stage", "nv-cli", "music"] + run_args)
    assert code == 0 and ran(json.loads(out)) == ["music"]
    code, out, _ = call(capsys, ["stage", "nv-cli", "mix"] + run_args)
    assert code == 0 and ran(json.loads(out)) == ["mix"]
    code, out, _ = call(capsys, ["status", "nv-cli"] + common + ["--json"])
    assert code == 0 and {n["id"]: n["state"] for n in json.loads(out)["nodes"]}["mix"] == "fresh"
    code, _, err = call(capsys, ["run", "nv-cli"] + common)
    assert code == 1 and json.loads(err)["refused"] == "store_missing"
    code, _, err = call(capsys, ["fixture", "--out", str(tmp_path / "ws")])
    assert code == 1 and json.loads(err)["refused"] == "fixture_exists"


def test_the_runner_table_covers_lanes_l4_and_l5_and_names_the_lane_still_to_come():
    assert set(run.RUNNERS) | set(run.LANES) | {"admit"} == set(graph.BY_ID)
    lane_l4 = {"script", "voice", "voice_qa", "base", "place", "music", "mix"}
    assert set(run.RUNNERS) == lane_l4 | {"avatar", "avatar_check"}
    assert run.LANES == {"compose": "L6", "deliver_check": "L6", "handoff": "L6"}
    assert run.ancestors("mix") == {"mix", "place", "music", "base", "voice", "voice_qa", "script"}
    assert speech.measured_failures({"wer": {"passed": False}, "sim": {"status": "not_measured"}}) == ["wer"]
