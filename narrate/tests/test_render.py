"""End to end with the fake engine and FFmpeg: render, verify, determinism, timing fit and overrun, dialog voices,
condense words, refusals that leave no run, best-of-3 through an injected transcriber, tamper and the CLI."""

import json
import subprocess
import sys

import pytest
from conftest import PACKAGE, SLIDE, dhall_check
from test_adapters import EDL, WORDS

from narrate import audio, evaluate, registry, render, verify
from narrate.__main__ import main
from narrate.config import Config
from narrate.lexical import LexicalError
from narrate.policy import Refused

pytestmark = pytest.mark.usefixtures("ffmpeg")


def manifest_of(run_dir):
    return json.loads((run_dir / "manifest.json").read_text())


def test_markdown_render_verifies_and_records_everything(workspace):
    cfg = Config(workspace.write(SLIDE))
    final, manifest = render.render(cfg)
    assert final.parent == workspace.base / "runs"
    assert verify.verify(final)["ok"]
    assert manifest["kind"] == "narration_render" and manifest["synthetic"] is True
    assert manifest["timeline"]["mapping"] == "narration_v1" and manifest["timeline"]["no_time_stretch"] is False
    assert manifest["voices"] == [
        {
            "speaker": None,
            "voice": "voice-fixture-sine",
            "ref_clip_sha256": workspace.voices[0]["refClipSha256"],
            "ref_text_sha256": workspace.voices[0]["refTextSha256"],
            "consent_id": "consent-fixture-sine",
            "scope": "OwnContent",
            "fixture": True,
            "synthetic_label_required": True,
            "hosted_allowed": False,
        }
    ]
    text = json.dumps(manifest)
    assert str(workspace.store) not in text  # digests and ids, never a store path
    spoken = " ".join(c["spoken"] for c in manifest["chunks"])
    assert "8 percent" in spoken and "M C P" in spoken
    assert {c["qa"]["status"] for c in manifest["chunks"]} == {"not_measured"}
    assert manifest["qa"]["wer"]["available"] is False
    loud = manifest["loudness"]
    assert loud["passed"] and abs(loud["measured"]["integrated_lufs"] + 16) <= 0.5
    assert loud["measured"]["true_peak_dbtp"] <= -1.0
    assert manifest["lexical"]["release"] == "xoxd-lexical@0.0.0-fixture"
    assert manifest["lexical"]["vale"]["status"] in ("not_run", "measured")
    files = set(manifest["output_sha256"])
    assert {
        "narration.wav",
        "narration.flac",
        "narration.srt",
        "narration.vtt",
        "narration.edl.json",
        "ir.json",
    } <= files
    assert all(c["file"] in files for c in manifest["chunks"])
    srt = (final / "narration.srt").read_text()
    assert srt.startswith("1\n00:00:00,") and "[Synthetic voice] Narrate reads" in srt and "8%" in srt
    assert (final / "narration.vtt").read_text().startswith("WEBVTT\n\nNOTE This narration is a synthetic voice.")
    edl = json.loads((final / "narration.edl.json").read_text())
    (segment,) = edl["segments"]
    assert segment["target_dur_s"] == 30.0 and segment["padded_s"] > 0 and segment["flags"] == []
    assert edl["total_seconds"] == pytest.approx(30.0, abs=0.01)
    wav = audio.read(final / "narration.wav")
    assert (wav.rate, len(wav.samples)) == (24000, edl["total_samples"])


def test_manifest_and_outputs_are_deterministic(workspace):
    cfg = Config(workspace.write(SLIDE))
    first, a = render.render(cfg)
    second, b = render.render(cfg)
    assert first != second
    assert a["content_sha256"] == b["content_sha256"]
    assert a["output_sha256"] == b["output_sha256"]
    assert {k: v for k, v in a.items() if k not in render.VOLATILE} == {
        k: v for k, v in b.items() if k not in render.VOLATILE
    }


SRT_FIT = """1
00:00:00,000 --> 00:00:03,000
Short line.

2
00:00:03,000 --> 00:00:05,000
This cue carries far too many words to be spoken inside its two seconds.

3
00:00:08,000 --> 00:00:09,500
Fits after a slight push.
"""


def test_srt_timing_fit_speed_then_atempo_then_overrun_never_truncated(workspace):
    workspace.job["captions"] = ["Srt"]
    cfg = Config(workspace.write(SRT_FIT, "Srt"))
    final, manifest = render.render(cfg)
    edl = json.loads((final / "narration.edl.json").read_text())
    short, long, pushed = edl["segments"]
    assert short["out_start_s"] == 0.0 and short["flags"] == [] and short["padded_s"] > 0
    assert long["natural_s"] > 2.0 * 1.15 * 1.08
    assert long["speed"] == pytest.approx(1.15) and long["atempo"] == pytest.approx(1.08)
    assert "overrun" in long["flags"]
    assert long["overrun_s"] == pytest.approx(long["delivered_s"] - 2.0, abs=1e-3)
    assert long["delivered_s"] > 2.0  # never truncated
    assert pushed["out_start_s"] >= long["out_end_s"] - 1e-3  # never overlapping
    assert pushed["out_start_s"] == pytest.approx(8.0, abs=1e-3) or "late_start" in pushed["flags"]
    assert pushed["natural_s"] > 1.5 and pushed["delivered_s"] <= 1.5 + 1e-3 and "overrun" not in pushed["flags"]
    assert manifest["overruns"] == [{"segment": "cue-0002", "overrun_s": long["overrun_s"]}]
    assert "overrun" in manifest["flags"] and manifest["timeline"]["stretch_applied"] is True
    assert not (final / "narration.vtt").exists()


def test_dialog_render_maps_each_speaker_to_its_voice(workspace):
    workspace.add_voice("voice-fixture-b")
    workspace.job["speakers"] = [
        {"speaker": "ANA", "voice": "voice-fixture-sine"},
        {"speaker": "BEN", "voice": "voice-fixture-b"},
    ]
    cfg = Config(workspace.write("ANA: Hello there.\nBEN: Hi, Ana.\nANA: Bye.\n", "Dialog"))
    final, manifest = render.render(cfg)
    edl = json.loads((final / "narration.edl.json").read_text())
    assert [(s["speaker"], s["voice"]) for s in edl["segments"]] == [
        ("ANA", "voice-fixture-sine"),
        ("BEN", "voice-fixture-b"),
        ("ANA", "voice-fixture-sine"),
    ]
    assert {v["speaker"]: v["voice"] for v in manifest["voices"]} == {
        "ANA": "voice-fixture-sine",
        "BEN": "voice-fixture-b",
    }


def test_condense_words_render_lands_on_the_edit_clock(workspace):
    (workspace.base / "edl.json").write_text(json.dumps(EDL))
    workspace.options = {"edl": "edl.json", "clip": "talk"}
    cfg = Config(workspace.write(WORDS, "CondenseWords"))
    final, manifest = render.render(cfg)
    edl = json.loads((final / "narration.edl.json").read_text())
    assert [s["target_start_s"] for s in edl["segments"]] == [0.2, pytest.approx(2.45, abs=1e-3)]
    assert edl["segments"][0]["out_start_s"] == pytest.approx(0.2, abs=1e-3)
    assert manifest["input"]["meta"]["mapping"] == "condense_edl"


@pytest.mark.parametrize(
    "edit,code",
    [
        (lambda ws: ws.consents[0].update(revokedAt="2026-10-23"), "consent_revoked"),
        (lambda ws: (ws.store / "consent.txt").write_text("other\n"), "consent_missing"),
        (
            lambda ws: (
                ws.job.update(confidential=True, engine="probe-hosted", allowHosted=True)
                or ws.engines.append(
                    {
                        **ws.engines[0],
                        "id": "probe-hosted",
                        "profile": "Hosted",
                        "backend": "Hosted",
                        "hosted": True,
                        "endpoint": "https://speech.example.invalid",
                        "confidentialAllowed": False,
                    }
                )
                or ws.voices[0]["allowedEngines"].append("probe-hosted")
            ),
            "confidential_engine_refused",
        ),
    ],
)
def test_refusals_happen_before_any_run_exists(workspace, edit, code):
    edit(workspace)
    cfg = Config(workspace.write(SLIDE))
    with pytest.raises(Refused) as caught:
        render.render(cfg)
    assert caught.value.code == code
    assert workspace.runs() == []


def test_input_digest_pin_is_enforced(workspace):
    workspace.job["inputSha256"] = "0" * 64
    cfg = Config(workspace.write(SLIDE))
    with pytest.raises(render.RenderError, match="input_digest_mismatch"):
        render.render(cfg)


def test_best_of_three_through_an_injected_transcriber(workspace):
    workspace.job["gates"]["maxChunkWer"] = 0.0
    cfg = Config(workspace.write("One short line to read.\n", "PlainText"))
    calls = []

    def transcriber(pcm, text):
        calls.append(len(pcm.samples))
        return text if len(calls) == 3 else "something else entirely"

    final, manifest = render.render(cfg, transcriber=transcriber)
    (chunk,) = manifest["chunks"]
    assert [t["seed"] for t in chunk["qa"]["takes"]] == [0, 1, 2]
    assert (chunk["qa"]["status"], chunk["qa"]["kept_take"]) == ("passed", 3)
    assert len(set(calls)) >= 1 and manifest["qa"]["chunks"]["passed"] == 1


def test_a_chunk_that_never_passes_is_flagged(workspace):
    workspace.job["gates"]["maxChunkWer"] = 0.0
    cfg = Config(workspace.write("One short line to read.\n", "PlainText"))
    _, manifest = render.render(cfg, transcriber=lambda pcm, text: "wrong words")
    assert manifest["chunks"][0]["qa"]["status"] == "failed" and "qa_failed" in manifest["flags"]


def test_rewrite_check_gates_an_agent_rewrite(workspace):
    cfg = Config(workspace.write("We ship 3 tools in 2026.\n", "PlainText"))
    bad = workspace.base / "bad.txt"
    bad.write_text("We ship 4 tools in 2026.\n")
    with pytest.raises(LexicalError, match="rewrite_refused"):
        render.render(cfg, rewrite=bad)
    ok = workspace.base / "ok.txt"
    ok.write_text("We will ship 3 tools in 2026.\n")
    _, manifest = render.render(cfg, rewrite=ok)
    assert manifest["input"]["rewrite"]["status"] == "accepted"
    assert manifest["chunks"][0]["written"] == "We will ship 3 tools in 2026."


def test_verify_catches_tamper(workspace):
    final, _ = render.render(Config(workspace.write(SLIDE)))
    chunk = next((final / "chunks").iterdir())
    data = bytearray(chunk.read_bytes())
    data[len(data) // 2] ^= 1
    chunk.write_bytes(bytes(data))
    receipt = verify.verify(final)
    assert not receipt["ok"] and receipt["reason"].startswith("outputs")
    (final / "stray.txt").write_text("x")
    chunk.unlink()
    assert not verify.verify(final)["ok"]


def test_verify_refuses_an_edited_manifest(workspace):
    final, manifest = render.render(Config(workspace.write(SLIDE)))
    manifest["timeline"]["mapping"] = "identity"
    (final / "manifest.json").write_text(json.dumps(manifest))
    assert verify.verify(final)["reason"].startswith("timeline")
    manifest["timeline"]["mapping"] = "narration_v1"
    manifest["loudness"]["passed"] = False
    (final / "manifest.json").write_text(json.dumps(manifest))
    assert verify.verify(final)["reason"].startswith("content")


def test_evaluate_scores_without_writing(workspace):
    cfg = Config(workspace.write(SLIDE))
    final, _ = render.render(cfg)
    before = sorted(p.name for p in final.rglob("*"))
    result = evaluate.evaluate(final, cfg=cfg)
    assert result["ok"] and result["metrics"]["loudness"]["passed"]
    assert result["metrics"]["wer"]["status"] == "not_measured" and result["metrics"]["overruns"] == []
    assert sorted(p.name for p in final.rglob("*")) == before


def test_cli_render_verify_voices_engines_and_refusal(workspace, capsys):
    config = workspace.write(SLIDE)
    assert main(["render", str(config)]) == 0
    run_dir = workspace.base / "runs" / workspace.runs()[0]
    assert main(["verify", str(run_dir)]) == 0
    assert json.loads(capsys.readouterr().out.split("\n", 1)[1])["ok"] is True
    assert main(["voices", str(config)]) == 0
    voices = json.loads(capsys.readouterr().out)
    assert voices[0]["consent_state"] == "active" and voices[0]["ref_clip_stored"] is True
    assert str(workspace.store) not in json.dumps(voices)
    assert main(["engines", str(config)]) == 0
    engines = json.loads(capsys.readouterr().out)
    assert engines[0]["may_run_confidential"] is True and engines[0]["available"] is True
    workspace.consents[0]["revokedAt"] = "2026-10-23"
    workspace.write(SLIDE)
    assert main(["render", str(config)]) == 1
    assert json.loads(capsys.readouterr().err)["refused"] == "consent_revoked"


def test_voices_add_stores_by_digest_and_bounds_the_clip(workspace, tmp_path):
    config = workspace.write(SLIDE)
    clip, text = tmp_path / "clip.wav", tmp_path / "clip.txt"
    clip.write_bytes(dhall_check().sine_wav())
    text.write_text("A transcript.\n")
    record = registry.add_voice(Config(config), clip, text, "voice-new", "consent-new", engines_allowed=["fake-sine"])
    assert (workspace.store / f"{record['refClipSha256']}.wav").is_file()
    assert record["refClipSeconds"] == 10.0 and record["fixture"] is False
    short = tmp_path / "short.wav"
    pcm = audio.Pcm(24000)
    pcm.silence(2.0)
    pcm.write(short)
    with pytest.raises(registry.RegistryError, match="10 to 30 s"):
        registry.add_voice(Config(config), short, text, "voice-short", "consent-new", engines_allowed=["fake-sine"])


def test_module_entry_point_runs():
    out = subprocess.run(
        [sys.executable, "-m", "narrate", "--help"], cwd=PACKAGE.parent, capture_output=True, text=True, check=True
    ).stdout
    for command in ("render", "evaluate", "voices", "engines", "verify"):
        assert command in out


def test_loudnorm_limits_peaks_that_one_linear_gain_would_push_over_the_ceiling(tmp_path):
    import math

    pcm = audio.Pcm(24000)
    for _ in range(6):  # a quiet tone with a loud 10 ms burst each second: a speech-like crest factor
        pcm.samples.extend(round(2000 * math.sin(2 * math.pi * 220 * n / 24000)) for n in range(23760))
        pcm.samples.extend(round(28000 * math.sin(2 * math.pi * 1000 * n / 24000)) for n in range(240))
    source = pcm.write(tmp_path / "peaky.wav")
    record = audio.loudnorm(source, tmp_path / "out.wav", 24000, -16, -1.5)
    assert record["limiter"] is not None and record["normalization_type"] in ("linear", "dynamic")
    integrated, _, peak = audio.ebur128(tmp_path / "out.wav")
    assert abs(integrated + 16) <= 0.5 and peak <= -1.0
    assert len(audio.read(tmp_path / "out.wav").samples) == len(pcm.samples)


def test_whisper_reads_a_padded_take(monkeypatch):
    from condense import transcribe
    from narrate import qa

    seen = {}

    def fake_read(cfg, src, a, b):
        seen["pcm"] = audio.read(src)
        return "heard"

    monkeypatch.setattr(transcribe, "read", fake_read)
    take = audio.Pcm(16000)
    take.samples.extend([1000] * 16000)
    whisper = qa.Whisper(Config(PACKAGE / "examples" / "narrate.toml"))
    assert whisper.read(take) == "heard"
    assert seen["pcm"].seconds == pytest.approx(1.0 + 2 * qa.PAD)
    assert seen["pcm"].samples[: int(qa.PAD * 16000)].count(0) == int(qa.PAD * 16000)
