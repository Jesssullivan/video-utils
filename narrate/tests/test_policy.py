"""Consent and confidentiality refusals, dialog speaker mapping and parity with Engine.dhall's port in check.py."""

import itertools

import pytest
from conftest import dhall_check

from narrate import adapters, policy
from narrate.config import Config
from narrate.policy import Refused

PROFILES = ["GpuSwitch", "GpuDirect", "MacMlx", "RentedOpen", "Hosted", "Fake"]
BACKENDS = ["VulkanAudioCpp", "QwenTtsCpp", "LlamaTts", "MlxAudio", "RentedOpen", "Hosted", "Fake"]


def test_engine_predicates_match_the_dhall_port_on_the_whole_truth_table():
    check = dhall_check()
    for profile, backend, hosted, confidential, estate in itertools.product(
        PROFILES, BACKENDS, (False, True), (False, True), (False, True)
    ):
        engine = {
            "profile": profile,
            "backend": backend,
            "hosted": hosted,
            "confidentialAllowed": confidential,
            "estateControlled": estate,
        }
        for name in ("is_hosted", "is_rented", "consistent", "may_run_confidential"):
            assert getattr(policy, name)(engine) == getattr(check, name)(engine), (name, engine)


def admit(ws, script="Plain words.", kind="PlainText", engine_id=None):
    cfg = Config(ws.write(script, kind))
    parsed = adapters.load(kind, cfg.input)
    return policy.admit(cfg.job(), parsed, cfg.registry(), policy.store_index(cfg.store), engine_id)


def refused(ws, code, **kwargs):
    with pytest.raises(Refused) as caught:
        admit(ws, **kwargs)
    assert caught.value.code == code, caught.value
    return caught.value


def test_the_fixture_job_is_admitted(workspace):
    engine, voices, consents = admit(workspace)
    assert engine["id"] == "fake-sine"
    assert voices == {None: workspace.voices[0]}
    assert list(consents) == ["consent-fixture-sine"]


def test_consent_missing_record(workspace):
    workspace.voices[0]["consentId"] = "no-such-consent"
    refused(workspace, "consent_missing")


def test_consent_missing_evidence(workspace):
    (workspace.store / "consent.txt").write_text("another statement\n")
    refused(workspace, "consent_missing")


def test_consent_revoked(workspace):
    workspace.consents[0]["revokedAt"] = "2026-10-23"
    refused(workspace, "consent_revoked")


def test_consent_scope_of_the_job_and_of_the_voice(workspace):
    workspace.job["scope"] = "ClientDisclosed"
    refused(workspace, "consent_scope")


def test_voice_scope_differs_from_the_job(workspace):
    workspace.consents[0]["scopes"] = ["OwnContent", "ClientDisclosed"]
    workspace.voices[0]["scope"] = "ClientDisclosed"
    refused(workspace, "consent_scope")


def test_ref_clip_digest_must_match_a_stored_clip(workspace):
    (workspace.store / "sine.wav").write_bytes(b"RIFF not the fixture clip")
    refused(workspace, "ref_clip_missing")


def test_ref_text_digest_must_match_a_stored_transcript(workspace):
    (workspace.store / "ref.txt").write_text("a different transcript\n")
    refused(workspace, "ref_text_missing")


def test_engine_not_in_the_voices_allowed_engines(workspace):
    workspace.engines.append({**workspace.engines[0], "id": "fake-other"})
    workspace.job["engine"] = "fake-other"
    refused(workspace, "engine_not_allowed")


def hosted(workspace, **extra):
    engine = {
        **workspace.engines[0],
        "id": "probe-hosted",
        "profile": "Hosted",
        "backend": "Hosted",
        "hosted": True,
        "endpoint": "https://speech.example.invalid",
        "confidentialAllowed": False,
        **extra,
    }
    workspace.engines.append(engine)
    workspace.voices[0]["allowedEngines"].append(engine["id"])
    workspace.job["engine"] = engine["id"]


def test_confidential_job_refuses_a_hosted_engine(workspace):
    hosted(workspace)
    workspace.job["confidential"] = True
    workspace.job["allowHosted"] = True
    refused(workspace, "confidential_engine_refused")


def test_hosted_engine_needs_allow_hosted_then_consent(workspace):
    hosted(workspace)
    refused(workspace, "hosted_not_allowed")
    workspace.job["allowHosted"] = True
    error = refused(workspace, "hosted_not_allowed")
    assert "consent" in error.detail
    workspace.consents[0]["hostedAllowed"] = True
    assert admit(workspace)[0]["id"] == "probe-hosted"


@pytest.mark.parametrize(
    "probe",
    [
        {"profile": "RentedOpen", "backend": "RentedOpen", "estateControlled": False, "confidentialAllowed": True},
        {"profile": "MacMlx", "backend": "RentedOpen", "estateControlled": True, "confidentialAllowed": True},
        {"profile": "GpuDirect", "backend": "Hosted", "estateControlled": True, "confidentialAllowed": True},
        {"profile": "GpuDirect", "backend": "QwenTtsCpp", "estateControlled": True, "confidentialAllowed": False},
    ],
)
def test_confidential_job_refuses_every_ineligible_engine(workspace, probe):
    engine = {**workspace.engines[0], "id": "probe", "hosted": False, "endpoint": "http://127.0.0.1:9/", **probe}
    workspace.engines.append(engine)
    workspace.voices[0]["allowedEngines"].append("probe")
    workspace.job.update(engine="probe", confidential=True)
    with pytest.raises(Refused) as caught:
        admit(workspace)
    assert caught.value.code in ("confidential_engine_refused", "engine_inconsistent")


def test_confidential_job_runs_on_the_fake_engine(workspace):
    workspace.job["confidential"] = True
    assert admit(workspace)[0]["id"] == "fake-sine"


DIALOG = "ANA: Hello there.\nBEN: Hi, Ana.\n"


def test_dialog_refuses_an_unmapped_speaker(workspace):
    workspace.job["speakers"] = [{"speaker": "ANA", "voice": "voice-fixture-sine"}]
    error = refused(workspace, "speaker_unmapped", script=DIALOG, kind="Dialog")
    assert "BEN" in error.detail


def test_dialog_maps_each_speaker_to_its_voice(workspace):
    workspace.add_voice("voice-fixture-b")
    workspace.job["speakers"] = [
        {"speaker": "ANA", "voice": "voice-fixture-sine"},
        {"speaker": "BEN", "voice": "voice-fixture-b"},
    ]
    _, voices, _ = admit(workspace, script=DIALOG, kind="Dialog")
    assert {k: v["id"] for k, v in voices.items()} == {"ANA": "voice-fixture-sine", "BEN": "voice-fixture-b"}


def test_every_named_voice_is_checked_even_unused(workspace):
    workspace.job["speakers"] = [{"speaker": "ZED", "voice": "voice-without-consent"}]
    refused(workspace, "voice_unknown")


def test_unknown_or_inconsistent_engine(workspace):
    workspace.job["engine"] = "nope"
    refused(workspace, "engine_unknown")
    workspace.job["engine"] = "fake-sine"
    workspace.engines[0]["profile"] = "GpuDirect"
    refused(workspace, "engine_inconsistent")
