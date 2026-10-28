"""The narrated-video types (docs/spec/NARRATED_VIDEO.md, TIN-7476): the edition rule at its three points, the
music-bed acquisition rule, the persona label, the tighten knob and the Consent persona field (NV-1).

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


@pytest.mark.parametrize("point", POINTS)
@pytest.mark.parametrize(("leaf", "code"), [({"pip": True}, "PipRefused"), ({"bed": True}, "BedRefused")])
def test_client_narrated_refuses_camera_pip_and_an_uncleared_bed_alone_at_each_point(check, point, leaf, code):
    verdict = check.edition_check(point, "ClientNarrated", {**CLEAN, **leaf})
    assert verdict == {"verdict": "Refused", "point": point, "codes": [code]}


@pytest.mark.parametrize("point", POINTS)
def test_client_narrated_admits_the_synthetic_narrator_and_avatar(check, point):
    leaves = {**CLEAN, "syntheticVoice": True, "avatar": True, "bed": True, "bedCleared": True}
    assert check.edition_check(point, "ClientNarrated", leaves) == {"verdict": "Admitted"}


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
        "nv-fixture-client-narrated": "ClientNarrated",
    }


def client(data):
    return next(nv for nv in data["narrated_videos"] if nv["id"] == "nv-fixture-client-deck")


def narrated(data):
    return next(nv for nv in data["narrated_videos"] if nv["id"] == "nv-fixture-client-narrated")


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


def test_tighten_defaults_off_and_a_project_may_enable_it(check, data):
    assert card(data)["tighten"] == {"enabled": False}
    deck = narrated(data)
    assert deck["tighten"] == {"enabled": True} and deck["base"]["deck"]["tightenEditsSha256"]
    assert refusals(check, data) == []
    deck["tighten"]["enabled"] = False
    assert [line for line in refusals(check, data) if "tighten_on_synthetic" in line] == [
        "examples: narrated video nv-fixture-client-narrated: tighten_on_synthetic (tighten edits on narrate "
        "segments need tighten.enabled; it is off by default, NV-2)"
    ]


def test_tighten_edits_on_operator_takes_need_no_override(check, data):
    client(data)["base"]["deck"]["tightenEditsSha256"] = narrated(data)["base"]["deck"]["tightenEditsSha256"]
    assert refusals(check, data) == []


def test_client_narrated_gates_the_bed_like_every_client_edition(check, data):
    narrated(data)["music"] = copy.deepcopy(card(data)["music"])
    assert [line for line in refusals(check, data) if "refused at Plan" in line] == [
        "examples: narrated video nv-fixture-client-narrated: refused at Plan: edition_bed_refused"
    ]
    data["music_beds"][0]["licence"].update(certifiedPdfSha256="f" * 64, contentIdCheck={"clear": "probe-receipt"})
    narrated(data)["delivery"]["voiceOnlyListen"] = "probe-listen-receipt"
    assert refusals(check, data) == []


def test_no_visible_label_is_required(check, data):
    """KP-15 (TIN-7476 comment 4ab7fc27): captions and description.txt need no synthetic or persona label."""
    for nv in data["narrated_videos"]:
        assert nv["labels"]["personaCue"] is None and nv["labels"]["extraNotice"] is None
    assert refusals(check, data) == []


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


# NV-6 (TIN-7476 comment 92605219): ClientNarrated is the default edition of a client delivery --------------------
def test_the_client_default_is_client_narrated_in_the_types_the_port_and_init(check):
    from narrate.video import job

    assert check.CLIENT_DEFAULT_EDITION == job.CLIENT_DEFAULT_EDITION == "ClientNarrated"
    assert check.client_edition() == "ClientNarrated" and check.client_edition("ClientVoiceOnly") == "ClientVoiceOnly"
    with pytest.raises(ValueError):
        check.client_edition("Internal")
    narrator = {**CLEAN, "syntheticVoice": True, "avatar": True}
    assert all(check.edition_check(p, check.client_edition(), narrator) == {"verdict": "Admitted"} for p in POINTS)
    assert check.edition_check("Plan", "ClientVoiceOnly", narrator)["codes"] == ["VoiceRefused", "PipRefused"]
    digest = "a" * 64
    assert job.init_job("j", "n", digest, client=True)["edition"] == "ClientNarrated"
    for client in (True, False):
        with pytest.raises(job.JobError) as caught:
            job.init_job("j", "n", digest, client=client, edition="ClientVoiceOnly")
        assert caught.value.code == "edition_voice_refused" and "--from" in caught.value.detail
    assert job.init_job("j", "n", digest)["edition"] == "Internal"
    with pytest.raises(job.JobError) as caught:
        job.init_job("j", "n", digest, client=True, edition="OwnContent")
    assert caught.value.code == "edition_not_client"


def test_the_dhall_client_default_renders_client_narrated():
    import shutil
    import subprocess

    if not shutil.which("dhall-to-json"):
        pytest.skip("dhall-to-json is not on PATH (nix develop .#condense)")
    expression = f"({EXAMPLES.parent / 'NarratedVideo.dhall'}).defaults.clientEdition\n"
    done = subprocess.run(["dhall-to-json"], input=expression, capture_output=True, text=True, timeout=120, check=True)
    assert json.loads(done.stdout) == "ClientNarrated"
