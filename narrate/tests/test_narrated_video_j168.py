"""The shipped private-terms defaults under J168 and SPR-339 (TIN-7125, docs/spec/NARRATED_VIDEO.md, "Private terms").

test_narrated_video_private_terms.py keeps the rules J168 stops, for the November 30, 2026 audit. This module does not
use its audit_rules fixture, so it reads what a release does. Every bundle and denylist here is synthetic.
"""

import pytest
from test_narrated_video_private_terms import ENTRIES, NAME, declare, no_whisper, refused, write_denylist, ws  # noqa: F401

from narrate.video import bundle, private_terms

NAME_ROW = {"id": "name-a", "class": "name", "literal": NAME}
GEOMETRY = {"id": "g", "class": "geometry", "regex": r"chamfer\s+angle"}


def test_the_shipped_defaults_are_the_j168_defaults():
    assert private_terms.MATCHED == ("name",) and private_terms.SCRIPT_MATCHES is False
    assert private_terms.NEEDS == {"never_name": {"name"}}


def test_an_ip_private_bundle_needs_no_denylist(ws):  # noqa: F811
    declare(ws["bundle"], None, ip_private=True, never_name=False)
    report = bundle.claims_only(ws["bundle"])["private_terms"]
    assert report["status"] == "not_declared" and report["ip_private"] is True


def test_an_ip_private_bundle_needs_no_number_or_geometry_entry(ws):  # noqa: F811
    declare(ws["bundle"], write_denylist(ws["denylist"], [NAME_ROW]), ip_private=True, never_name=False)
    assert bundle.claims_only(ws["bundle"], ws["denylist"])["private_terms"]["status"] == "passed"


@pytest.mark.parametrize(
    "text", ["it is 3.1416 wide", "three point one four one six", "the chamfer angle", "hеllo", "Zօrblax"]
)
def test_a_number_geometry_or_script_text_no_longer_matches(ws, text):  # noqa: F811
    entries = private_terms.parse(write_denylist_bytes(ws))
    assert private_terms.scan(entries, [("beat#1", "voiced", text)]) == []


def test_a_name_still_matches(ws):  # noqa: F811
    entries = private_terms.parse(write_denylist_bytes(ws))
    assert [m["class"] for m in private_terms.scan(entries, [("beat#1", "voiced", f"from {NAME}")])] == ["name"]


def test_never_name_still_needs_its_denylist_and_a_name_entry(ws):  # noqa: F811
    declare(ws["bundle"], None, ip_private=False, never_name=True)
    refused("denylist_missing", bundle.claims_only, ws["bundle"])
    declare(ws["bundle"], write_denylist(ws["denylist"], [GEOMETRY]), ip_private=False, never_name=True)
    refused("denylist_invalid", bundle.claims_only, ws["bundle"], ws["denylist"])


def write_denylist_bytes(ws):  # noqa: F811
    write_denylist(ws["denylist"], ENTRIES)
    return ws["denylist"].read_bytes()
