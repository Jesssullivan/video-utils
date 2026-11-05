"""The narration manifest the guitar contract tests consume is the one render.py writes.

tests/test_timeline_contract.py (the refusal matrix) and tests/cli.rs (verify-run) build their narration manifests
from two committed fixtures, so they cannot drift from render.py silently:

- fixtures/narration-timeline.json   a real zero-stretch render's `timeline`, with the EDL digest zeroed;
- fixtures/narration-shape.json      the key sets of a real render's manifest, timeline, EDL and EDL segment.

This test renders that run with the fake engine and asserts both fixtures still describe it. After an intended
change to the manifest, regenerate them with NARRATE_REGEN_SHAPE=1 and review the diff.
"""

import json
import os

import pytest
from conftest import SLIDE

from narrate import render, verify
from narrate.config import Config

FIXTURES = __import__("pathlib").Path(__file__).resolve().parent / "fixtures"
TIMELINE, SHAPE = FIXTURES / "narration-timeline.json", FIXTURES / "narration-shape.json"
ZERO = "0" * 64

pytestmark = pytest.mark.usefixtures("ffmpeg")


def shape_of(manifest, edl):
    return {
        "manifest_keys": sorted(manifest),
        "timeline_keys": sorted(manifest["timeline"]),
        "edl_keys": sorted(edl),
        "edl_segment_keys": sorted(edl["segments"][0]),
    }


def zero_stretch_render(workspace):
    final, manifest = render.render(Config(workspace.write(SLIDE)))
    edl = json.loads((final / "narration.edl.json").read_text())
    timeline = json.loads(json.dumps(manifest["timeline"]))
    timeline["edl"]["sha256"] = ZERO
    return final, manifest, edl, timeline


def test_the_contract_fixtures_describe_a_real_zero_stretch_render(workspace):
    final, manifest, edl, timeline = zero_stretch_render(workspace)
    assert verify.verify(final)["ok"]
    assert timeline["stretch_applied"] is False and timeline["no_time_stretch"] is False
    if os.environ.get("NARRATE_REGEN_SHAPE") == "1":
        TIMELINE.write_text(json.dumps(timeline, indent=1, sort_keys=True) + "\n")
        SHAPE.write_text(json.dumps(shape_of(manifest, edl), indent=1) + "\n")
    assert json.loads(SHAPE.read_text()) == shape_of(manifest, edl)
    committed = json.loads(TIMELINE.read_text())
    assert sorted(committed) == sorted(timeline) and sorted(committed["edl"]) == sorted(timeline["edl"])
    for key in ("mapping", "no_time_stretch", "stretch_applied", "sample_rate", "output_axis", "source_axis"):
        assert committed[key] == timeline[key], key
    assert committed["edl"]["file"] == timeline["edl"]["file"] and committed["edl"]["sha256"] == ZERO
