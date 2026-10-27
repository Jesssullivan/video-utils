"""The narrated-video types (docs/spec/NARRATED_VIDEO.md, TIN-7476): the edition rule at its three points, the
music-bed acquisition rule, the persona label and the Consent persona field (NV-1).

The rule is defined in narrate/dhall/Edition.dhall and asserted in narrate/dhall/narrated-video-test.dhall.
check.py ports it; these tests pin the port to that table and name the refusal each example mutation draws.
Every input is a committed fixture or a generated sine; no media is read.
"""

import copy
import itertools
import json

import pytest
from conftest import EXAMPLES, dhall_check

from narrate import policy

POINTS = ("Plan", "Place", "DeliverCheck")
CLEAN = {"syntheticVoice": False, "avatar": False, "pip": False, "bed": False, "bedCleared": False}


@pytest.fixture(scope="module")
def check():
    return dhall_check()


@pytest.fixture
def data(check):
    return check.load_examples()


def refusals(check, data):
    return check.run_checks(
        data, *(check.load_json(p) for p in (check.DRAFT_SCHEMA, check.DRAFT_ENTRIES, check.BENCH_SOURCES))
    )


@pytest.mark.parametrize("point", POINTS)
@pytest.mark.parametrize(
    ("leaf", "code"),
    [
        ({"syntheticVoice": True}, "VoiceRefused"),
        ({"avatar": True}, "PipRefused"),
        ({"pip": True}, "PipRefused"),
        ({"bed": True}, "BedRefused"),
    ],
)
def test_client_voice_only_refuses_each_leaf_alone_at_each_point(check, point, leaf, code):
    verdict = check.edition_check(point, "ClientVoiceOnly", {**CLEAN, **leaf})
    assert verdict == {"verdict": "Refused", "point": point, "codes": [code]}
    assert check.EDITION_REFUSALS[code].startswith("edition_")


@pytest.mark.parametrize("point", POINTS)
def test_a_cleared_bed_and_a_voice_only_job_pass_at_every_point(check, point):
    assert check.edition_check(point, "ClientVoiceOnly", CLEAN) == {"verdict": "Admitted"}
    cleared = {**CLEAN, "bed": True, "bedCleared": True}
    assert check.edition_check(point, "ClientVoiceOnly", cleared) == {"verdict": "Admitted"}


def test_internal_and_own_content_admit_every_leaf_combination(check):
    for edition, point, values in itertools.product(
        ("Internal", "OwnContent"), POINTS, itertools.product((False, True), repeat=5)
    ):
        leaves = dict(zip(check.LEAVES, values, strict=True))
        assert check.edition_check(point, edition, leaves) == {"verdict": "Admitted"}


def test_the_port_refuses_an_unknown_point_edition_or_leaf_set(check):
    for args in (("Render", "Internal", CLEAN), ("Plan", "Public", CLEAN), ("Plan", "Internal", {"bed": True})):
        with pytest.raises(ValueError):
            check.edition_check(*args)


def test_the_committed_examples_pass(check, data):
    assert refusals(check, data) == []
    editions = {nv["id"]: nv["edition"] for nv in data["narrated_videos"]}
    assert editions == {
        "nv-fixture-card": "Internal",
        "nv-fixture-avatar": "Internal",
        "nv-fixture-client-deck": "ClientVoiceOnly",
    }


def client(data):
    return next(nv for nv in data["narrated_videos"] if nv["id"] == "nv-fixture-client-deck")


def card(data):
    return next(nv for nv in data["narrated_videos"] if nv["id"] == "nv-fixture-card")


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("segments", "refused at Plan: edition_voice_refused"),
        ("avatar", "refused at Plan: edition_pip_refused"),
        ("music", "refused at Plan: edition_bed_refused"),
    ],
)
def test_each_client_refusal_names_its_code_at_plan(check, data, field, expected):
    source = next(nv for nv in data["narrated_videos"] if nv[field])
    client(data)[field] = copy.deepcopy(source[field])
    found = refusals(check, data)
    assert [line for line in found if "refused at Plan" in line] == [
        f"examples: narrated video nv-fixture-client-deck: {expected}"
    ]


def test_a_cleared_bed_needs_the_voice_only_listen_too(check, data):
    bed = data["music_beds"][0]
    bed["licence"].update(certifiedPdfSha256="f" * 64, contentIdCheck={"clear": "probe-receipt"})
    client(data)["music"] = copy.deepcopy(card(data)["music"])
    assert any("edition_bed_refused" in line for line in refusals(check, data))
    client(data)["delivery"]["voiceOnlyListen"] = "probe-listen-receipt"
    assert refusals(check, data) == []


def test_an_agent_acquired_bed_is_refused(check, data):
    data["music_beds"][0]["acquisition"]["acquiredBy"] = "Agent"
    assert any("bed_acquisition_agent" in line for line in refusals(check, data))


def test_tighten_is_refused_on_synthetic_narration(check, data):
    deck = client(data)
    deck.update(edition="Internal", segments=copy.deepcopy(card(data)["segments"]))
    deck["base"]["deck"]["tightenEditsSha256"] = "e" * 64
    assert any("tighten_on_synthetic" in line for line in refusals(check, data))


def test_a_consent_persona_must_reach_the_labels(check, data):
    data["consents"][0]["persona"] = "fixture-persona"
    found = refusals(check, data)
    # nv-fixture-avatar already carries the persona; the other job with a segment lacks it.
    assert [line for line in found if "persona_label_missing" in line] == [
        "examples: narrated video nv-fixture-card: persona_label_missing (a voice's consent names a persona the "
        "labels lack)"
    ]


def test_consent_persona_field_renders_and_narrate_policy_accepts_it():
    consents = json.loads((EXAMPLES / "consents.json").read_text())
    assert [c["persona"] for c in consents] == [None]
    voices = {v["id"]: v for v in json.loads((EXAMPLES / "voices.json").read_text())}
    for persona in (None, "fixture-persona"):
        registry = {"voices": voices, "consents": {c["id"]: {**c, "persona": persona} for c in consents}}
        voice, consent = policy.check_consent("voice-fixture-sine", registry, None, "OwnContent")
        assert consent["persona"] == persona
