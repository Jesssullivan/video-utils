"""Consent, hosted and rented refusals, dialog speaker mapping and parity with Engine.dhall's port in check.py."""

import itertools

import pytest
from conftest import dhall_check

from narrate import adapters, policy
from narrate.config import Config
from narrate.policy import Refused

PROFILES = ["GpuSwitch", "GpuDirect", "MacMlx", "RentedOpen", "Hosted", "Fake"]
BACKENDS = [
    "VulkanAudioCpp",
    "AudioCppBatch",
    "RentedAudioCppBatch",
    "QwenTtsCpp",
    "LlamaTts",
    "MlxAudio",
    "RentedOpen",
    "Hosted",
    "Fake",
]


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
        for name in ("is_hosted", "is_rented", "is_offsite", "consistent", "may_run_confidential"):
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


def test_a_likeness_consent_never_grants_a_voice(workspace):
    workspace.consents[0]["scopes"] = ["OwnContent", "Likeness"]
    workspace.voices[0]["scope"] = workspace.job["scope"] = "Likeness"
    caught = refused(workspace, "consent_scope")
    assert "Likeness" in caught.detail


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


def test_a_confidential_client_job_runs_on_a_hosted_engine_once_job_and_consent_allow_it(workspace):
    hosted(workspace)
    workspace.consents[0]["scopes"] = ["ClientDisclosed"]
    workspace.voices[0]["scope"] = workspace.job["scope"] = "ClientDisclosed"
    workspace.job.update(confidential=True, allowHosted=True)
    refused(workspace, "hosted_not_allowed")
    workspace.consents[0]["hostedAllowed"] = True
    assert admit(workspace)[0]["id"] == "probe-hosted"


def test_hosted_engine_needs_allow_hosted_then_consent(workspace):
    hosted(workspace)
    refused(workspace, "hosted_not_allowed")
    workspace.job["allowHosted"] = True
    error = refused(workspace, "hosted_not_allowed")
    assert "consent" in error.detail
    workspace.consents[0]["hostedAllowed"] = True
    assert admit(workspace)[0]["id"] == "probe-hosted"


def probe(workspace, **fields):
    engine = {
        **workspace.engines[0],
        "id": "probe",
        "hosted": False,
        "endpoint": "https://gpu.example.invalid",
        **fields,
    }
    workspace.engines.append(engine)
    workspace.voices[0]["allowedEngines"].append("probe")
    workspace.job["engine"] = "probe"


@pytest.mark.parametrize("backend", ["RentedOpen", "RentedAudioCppBatch"])
@pytest.mark.parametrize("estate", [False, True])
@pytest.mark.parametrize("confidential", [False, True])
def test_a_rented_engine_must_pass_the_consent_check(workspace, backend, estate, confidential):
    probe(workspace, profile="RentedOpen", backend=backend, estateControlled=estate, confidentialAllowed=confidential)
    workspace.job["confidential"] = confidential
    error = refused(workspace, "hosted_not_allowed")
    assert "consent" in error.detail
    workspace.consents[0]["hostedAllowed"] = True
    assert admit(workspace)[0]["id"] == "probe"


def test_a_confidential_client_job_may_render_on_a_rented_engine(workspace):
    probe(workspace, profile="RentedOpen", backend="RentedOpen", estateControlled=False, confidentialAllowed=False)
    workspace.consents[0].update(scopes=["ClientDisclosed"], hostedAllowed=True)
    workspace.voices[0]["scope"] = workspace.job["scope"] = "ClientDisclosed"
    workspace.job["confidential"] = True
    assert admit(workspace)[0]["id"] == "probe"


def test_every_named_voice_passes_the_rented_consent_check(workspace):
    probe(workspace, profile="RentedOpen", backend="RentedOpen")
    workspace.consents[0]["hostedAllowed"] = True
    workspace.add_voice("voice-fixture-b")
    workspace.consents.append({**workspace.consents[0], "id": "consent-without-hosted", "hostedAllowed": False})
    workspace.voices[-1]["consentId"] = "consent-without-hosted"
    workspace.job["speakers"] = [{"speaker": "BEN", "voice": "voice-fixture-b"}]
    error = refused(workspace, "hosted_not_allowed", script="BEN: Hi.\n", kind="Dialog")
    assert "consent-without-hosted" in error.detail


@pytest.mark.parametrize("value", ["false", "true", 1, None])
def test_only_the_boolean_true_grants_hosted_allowed(workspace, value):
    probe(workspace, profile="RentedOpen", backend="RentedOpen")
    workspace.consents[0]["hostedAllowed"] = value
    refused(workspace, "hosted_not_allowed")


def test_the_rented_consent_check_holds_when_the_cli_names_the_engine(workspace):
    probe(workspace, profile="RentedOpen", backend="RentedOpen")
    workspace.job["engine"] = "fake-sine"
    refused(workspace, "hosted_not_allowed", engine_id="probe")


def test_the_dhall_port_refuses_a_rented_engine_without_hosted_allowed():
    check = dhall_check()
    data = {
        "voices": [{"id": "v", "consentId": "c", "scope": "OwnContent", "allowedEngines": ["r"]}],
        "consents": [{"id": "c", "scopes": ["OwnContent"], "revokedAt": None, "hostedAllowed": False}],
    }
    job = {"id": "j", "engine": "r", "scope": "OwnContent"}
    engine = {"id": "r", "profile": "RentedOpen", "backend": "RentedOpen", "hosted": False}
    errors = []
    check.check_voice_for_job(job, "v", data, engine, errors)
    assert [e for e in errors if "hostedAllowed" in e]
    data["consents"][0]["hostedAllowed"] = True
    errors = []
    check.check_voice_for_job(job, "v", data, engine, errors)
    assert errors == []


def test_an_inconsistent_engine_stays_refused_on_every_job(workspace):
    probe(workspace, profile="GpuDirect", backend="Hosted")
    refused(workspace, "engine_inconsistent")


def test_one_wrong_field_never_makes_a_rented_batch_look_local():
    rented = {"profile": "RentedOpen", "backend": "RentedAudioCppBatch", "hosted": False}
    assert policy.consistent(rented) and policy.is_rented(rented) and policy.is_offsite(rented)
    direct = {"profile": "GpuDirect", "backend": "AudioCppBatch", "hosted": False}
    assert policy.consistent(direct) and not policy.is_offsite(direct)
    wrong_profile = {**rented, "profile": "GpuDirect"}
    assert not policy.consistent(wrong_profile) and policy.is_offsite(wrong_profile)
    wrong_backend = {**rented, "backend": "AudioCppBatch"}
    assert not policy.consistent(wrong_backend) and policy.is_offsite(wrong_backend)
    assert not policy.consistent({"profile": "GpuSwitch", "backend": "AudioCppBatch", "hosted": False})


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
