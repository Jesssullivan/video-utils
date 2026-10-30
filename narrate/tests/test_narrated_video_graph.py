"""The narrated-video graph core (lane L3, docs/spec/NARRATED_VIDEO.md): stage keys, the content-addressed store, the
admit gate, the plan states, every invalidation row of the spec's table, freshness, the CLI and the kitpip stub stage.

Stages other than avatar are run here by a fake runner that writes one small JSON output per node, so the planner is
exercised without FFmpeg. The avatar test renders a narrate run with the fake engine and runs the kitpip stub on it.
Every input is a committed synthetic fixture: the Dhall example records, generated sine loops and the stub.
"""

import copy
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from conftest import EXAMPLES, SLIDE

from narrate import render
from narrate.config import ROOT, Config
from narrate.video import admit, cli, graph, keys, kitpip, store
from narrate.video.job import DEFAULTS, JobError, check_shape, init_job, load_records

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "narrated-video"
STUB = FIXTURES / "kitpip_stub.py"
EXTERNALS = FIXTURES / "kitpip-externals.json"
DAG = ROOT / "program" / "dags" / "narrated-video.json"
FFMPEG_ID = "f" * 64
FPS = {"num": 30, "den": 1}


# Helpers -------------------------------------------------------------------------------------------------------
def examples():
    return {j["id"]: j for j in json.loads((EXAMPLES / "narrated-videos.json").read_text())}


def example(job_id):
    return copy.deepcopy(examples()[job_id])


def records():
    return copy.deepcopy(load_records(EXAMPLES))


def stub_ctx(binary=STUB):
    pin = kitpip.load_pin(EXTERNALS)
    return {
        "pin": pin,
        "kitpip": kitpip.resolve(pin, {kitpip.BIN_ENV: str(binary)}),
        "ffmpeg": FFMPEG_ID,
        "sources": None,
    }


def plain_ctx():
    return {"pin": None, "kitpip": None, "ffmpeg": FFMPEG_ID, "sources": None}


def new_store(tmp_path, job):
    s = store.JobStore(tmp_path / "narrated", job["id"])
    s.write_job(job)
    return s


def two_segment_avatar_job(recs):
    """nv-fixture-avatar with a second segment voiced by a second fixture narrate job."""
    job = example("nv-fixture-avatar")
    second = copy.deepcopy(recs["jobs"]["job-fixture-fake"])
    second["id"] = "job-fixture-fake-2"
    second["inputSha256"] = hashlib.sha256(b"second synthetic segment\n").hexdigest()
    recs["jobs"][second["id"]] = second
    job["segments"].append(
        {
            "id": "seg-2",
            "narrateJob": second["id"],
            "scriptSha256": second["inputSha256"],
            "anchor": {"atSeconds": 12.5},
            "avatar": True,
        }
    )
    return job


def run_all(job, recs, s, ctx):
    """Run every runnable node with a fake runner until none is left. Returns the node ids that ran, in order."""
    ran = []
    for _ in range(30):
        g = graph.plan(job, recs, s, ctx)
        if not g["runnable"]:
            return ran, g
        for node_id in g["runnable"]:
            document = g["_documents"][node_id]
            key = keys.stage_key(document)
            partial = s.begin(node_id, key)
            (partial / "out.json").write_text(json.dumps({"node": node_id, "key": key}))
            fields = {"measurements": {"fps": FPS}} if node_id == "base" else {}
            s.commit(node_id, key, document, fields)
            ran.append(node_id)
    raise AssertionError("the graph did not settle")


def states(g):
    return {n["id"]: n["state"] for n in g["nodes"]}


def selected(g):
    return {n["id"] for n in g["nodes"] if n["state"] != "not_selected" and n["stage"] != "admit"}


def tree(path):
    return sorted(str(p.relative_to(path)) for p in Path(path).rglob("*"))


# The graph table -----------------------------------------------------------------------------------------------
def test_the_published_dag_equals_the_graph_table():
    dag = json.loads(DAG.read_text())
    assert dag["spec"] == "docs/spec/NARRATED_VIDEO.md" and dag["parallel"]["max_stages"] == 2
    rows = [
        (
            s["id"],
            s["fan_out"] == "segment",
            [(d["stage"], d["how"]) for d in s["depends_on"]],
            s["optional"],
            s["mapping"],
            s["intent"],
        )
        for s in dag["stages"]
    ]
    want = [(s.id, s.fan_out, [list(d) for d in s.depends_on], s.optional, s.mapping, s.intent) for s in graph.STAGES]
    assert [(r[0], r[1], [list(d) for d in r[2]], r[3], r[4], r[5]) for r in rows] == want
    assert len(graph.STAGES) == 13 and graph.ORDER[0] == "admit"


def test_the_avatar_stage_tools_are_neutral_and_keyed_by_avatar_external():
    """TIN-7788: avatar_overlay and avatar_verify name the stages whatever external draws the overlay, so the DAG
    keeps its tool names when a job moves from kitpip to vrm."""
    dag = {s["id"]: s for s in json.loads(DAG.read_text())["stages"]}
    for stage, tool in graph.AVATAR_TOOLS.items():
        assert dag[stage]["tool"] == tool
        assert dag[stage]["dispatch"] == {
            "by": graph.AVATAR_DISPATCH,
            "default": DEFAULTS["avatar"]["external"],
            "externals": list(admit.AVATAR_EXTERNALS),
        }
    assert set(graph.AVATAR_TOOLS) == set(graph.AVATAR_STAGES)
    # no stage tool names an implementation; every other stage has no dispatch
    assert not [s["tool"] for s in dag.values() if s["tool"].startswith(("kitpip", "vrm"))]
    assert [s for s in dag if "dispatch" in dag[s]] == list(graph.AVATAR_TOOLS)
    drafts = json.loads((ROOT / "program" / "tool-drafts" / "narrated_video.json").read_text())
    names = [t["name"] for t in drafts["tools"]]
    assert set(graph.AVATAR_TOOLS.values()) <= set(names)
    assert not [n for n in names if n.startswith(("kitpip", "vrm"))]
    for tool in graph.AVATAR_TOOLS.values():
        draft = next(t for t in drafts["tools"] if t["name"] == tool)
        assert (ROOT / draft["skill"]).is_file() and "avatar.external" in draft["description"]


def test_a_looping_or_dangling_graph_refuses():
    loop = (
        graph.Stage("a", False, (("b", "all"),), False, None, ""),
        graph.Stage("b", False, (("a", "all"),), False, None, ""),
    )
    with pytest.raises(JobError) as caught:
        graph.toposort(loop)
    assert caught.value.code == "graph_cycle"
    with pytest.raises(JobError):
        graph.toposort((graph.Stage("a", False, (("ghost", "all"),), False, None, ""),))


# Keys ----------------------------------------------------------------------------------------------------------
def test_canonical_json_is_order_free_and_writes_integral_doubles_as_integers():
    assert keys.canonical({"b": 1, "a": -16.0}) == keys.canonical({"a": -16, "b": 1}) == '{"a":-16,"b":1}'
    assert keys.canonical({"w": 0.22, "t": True, "n": None}) == '{"n":null,"t":true,"w":"0.22"}'
    for bad in (float("nan"), float("inf"), {1: "x"}, {1, 2}):
        with pytest.raises(keys.KeyDocumentError):
            keys.canonical(bad)


def test_input_order_never_changes_a_key():
    rows = [{"slot": "a", "stage": "source", "digest": "1" * 64}, {"slot": "b", "stage": "voice", "digest": "2" * 64}]
    tool = {"name": "t", "version": "1", "binary_sha256": None}
    one = keys.key_document("mix", None, 1, tool, None, {}, "Internal", rows)
    two = keys.key_document("mix", None, 1, tool, None, {}, "Internal", list(reversed(rows)))
    assert keys.stage_key(one) == keys.stage_key(two)


SCRIPT_SHA256 = "93f7f4183b4b6ccec0c3ef2c83cca16dcb0ec4a929d55941193ab84f4f355d3a"
PINNED = {
    "script": (
        "script",
        "seg-1",
        {"narrate_job": "job-fixture-fake", "input_kind": "Markdown"},
        [{"slot": "script", "stage": "source", "digest": SCRIPT_SHA256}],
        None,
    ),
    "mix": (
        "mix",
        None,
        {
            "music": {"bedBelowVoiceLu": 20.0, "duckDb": 7, "attackMs": 50},
            "delivery": {"targetLufs": -16.0, "truePeakDbtp": -1.5, "driftLu": 0.5, "channels": "Mono"},
        },
        [
            {"slot": "place", "stage": "place", "digest": "a" * 64},
            {"slot": "music", "stage": "music", "digest": "b" * 64},
        ],
        FFMPEG_ID,
    ),
    "avatar": (
        "avatar",
        "seg-2",
        {"rig": "kitpip-stub-rig", "renderSize": 512},
        [
            {"slot": "voice:seg-2", "stage": "voice", "digest": "c" * 64},
            {"slot": "base.fps", "stage": "base", "value": {"num": 30, "den": 1}},
        ],
        None,
    ),
}
PINNED_KEYS = {
    "script": "c2c0f5fd306ec7868bc0ecd900371797e7a4f9ad3cb97d528882e739bfa0f805",
    "mix": "bbac534e3485777a3770611d40d6c0d0ef1290a8b7a8e6af1bd4b7a65ed2e02b",
    "avatar": "f076d8cbcbfa47a4a73bb3e43c8f9c785b873af810bbf5bac5a28af9df5b4809",
}


@pytest.mark.parametrize("name", sorted(PINNED))
def test_three_stage_keys_are_pinned(name):
    stage, segment, knobs, inputs, ffmpeg = PINNED[name]
    tool = {"name": f"narrate.video.{stage}", "version": "1", "binary_sha256": None}
    document = keys.key_document(stage, segment, 1, tool, ffmpeg, knobs, "Internal", inputs)
    assert keys.stage_key(document) == PINNED_KEYS[name]


def test_the_commit_and_run_dir_stay_out_of_the_content_digest():
    manifest = {
        "kind": "nv_stage",
        "stage_key": "k",
        "outputs": {},
        "commit": "1" * 40,
        "run_dir": "a",
        "created_utc": "2026-10-27T00:00:00Z",
    }
    moved = manifest | {"commit": "2" * 40, "run_dir": "b", "created_utc": "2026-10-28T00:00:00Z"}
    assert keys.content_digest(manifest) == keys.content_digest(moved)
    assert "commit" not in keys.key_document("mix", None, 1, {"name": "t", "version": "1"}, None, {}, "Internal", [])


# Plan ----------------------------------------------------------------------------------------------------------
def test_plan_keys_the_ready_stages_and_writes_nothing(tmp_path):
    job = example("nv-fixture-card")
    s = new_store(tmp_path, job)
    before = tree(s.dir)
    g = graph.plan(job, records(), s, plain_ctx())
    assert tree(s.dir) == before
    st = states(g)
    assert st["admit"] == "fresh"
    assert {k for k, v in st.items() if v == "not_selected"} == {"avatar/seg-1", "avatar_check/seg-1", "handoff"}
    assert set(g["runnable"]) == {"script/seg-1", "base", "music"}
    assert all(n["key"] is None for n in g["nodes"] if n["reason"] == "upstream_stale")
    assert g["pending_operator"] == [
        {
            "gate": "listening_acceptance",
            "stage": "voice_qa",
            "segment": "seg-1",
            "detail": g["pending_operator"][0]["detail"],
        }
    ]
    assert "_documents" not in graph.public(g)


def test_a_full_fake_run_leaves_every_selected_node_fresh(tmp_path):
    recs = records()
    job = two_segment_avatar_job(recs)
    s = new_store(tmp_path, job)
    ran, g = run_all(job, recs, s, stub_ctx())
    assert set(ran) == selected(g) and len(ran) == len(set(ran)) == 16
    assert all(states(g)[n] == "fresh" for n in selected(g))
    assert s.verify() == {n: [] for n in ran}
    order = {n: i for i, n in enumerate(ran)}
    for node in g["nodes"]:
        for upstream in node["depends_on"]:
            assert order[upstream] < order[node["id"]]
    again, _ = run_all(job, recs, s, stub_ctx())
    assert again == []


def test_no_ffmpeg_blocks_the_render_stages_and_no_kitpip_blocks_the_avatar(tmp_path):
    job = example("nv-fixture-avatar")
    ctx = plain_ctx() | {"ffmpeg": None}
    st = states(graph.plan(job, records(), new_store(tmp_path, job), ctx))
    for node in ("base", "music"):
        assert st[node] == "blocked"
    assert st["avatar/seg-1"] == "blocked" and st["compose"] == "blocked"
    assert st["script/seg-1"] == "stale"


def test_a_source_missing_from_the_private_store_blocks_its_stage(tmp_path):
    job = example("nv-fixture-card")
    ctx = plain_ctx() | {"sources": {job["segments"][0]["scriptSha256"]}}
    g = graph.plan(job, records(), new_store(tmp_path, job), ctx)
    node = next(n for n in g["nodes"] if n["id"] == "music")
    assert (node["state"], node["reason"]) == ("blocked", "source_missing")
    assert states(g)["script/seg-1"] == "stale"


# Invalidation: each row of the spec's table asserts the exact rerun set ------------------------------------------
def bed_level(job, recs, ctx):
    job["music"]["bedBelowVoiceLu"] = 18


def second_script(job, recs, ctx):
    digest = hashlib.sha256(b"second synthetic segment, revised\n").hexdigest()
    recs["jobs"]["job-fixture-fake-2"]["inputSha256"] = digest
    job["segments"][1]["scriptSha256"] = digest


def overlay_width(job, recs, ctx):
    job["avatar"]["width"] = 0.18


def kitpip_rig(job, recs, ctx):
    job["avatar"]["rig"] = "kitpip-other-rig"


def kitpip_pin(job, recs, ctx):
    ctx["kitpip"]["tool"]["version"] = "0.0.1-stub"


def content_id(job, recs, ctx):
    recs["music_beds"]["bed-fixture-emaj"]["licence"]["contentIdCheck"] = {"clear": "fixture-check-1"}


def handoff_on(job, recs, ctx):
    job["delivery"]["handoff"] = True


def pronunciation_entry(job, recs, ctx):
    table = recs["pronunciation"]["narrate-en-example"]
    table["entries"].append(
        {"caseSensitive": False, "note": None, "spoken": "fix sure", "wholeWord": True, "written": "fixture"}
    )


def engine_model(job, recs, ctx):
    recs["engines"]["fake-sine"]["model"] = "fake-sine-v2"


def engine_files(job, recs, ctx):
    recs["engines"]["fake-sine"]["files"] = [{"path": "private/model.bin", "sha256": "d" * 64}]


def persona(job, recs, ctx):
    job["labels"]["persona"] = "fixture-persona-b"


AVATARS = {"avatar/seg-1", "avatar/seg-2", "avatar_check/seg-1", "avatar_check/seg-2"}
# Both fixture narrate jobs name the same engine and pronunciation table, so an edit to either reruns both voices.
VOICES = {"voice/seg-1", "voice/seg-2", "voice_qa/seg-1", "voice_qa/seg-2"}
ROWS = {
    "bed level": (bed_level, {"mix", "compose", "deliver_check"}),
    "one segment's script": (
        second_script,
        {
            "script/seg-2",
            "voice/seg-2",
            "voice_qa/seg-2",
            "avatar/seg-2",
            "avatar_check/seg-2",
            "place",
            "mix",
            "compose",
            "deliver_check",
        },
    ),
    "overlay width": (overlay_width, {"compose", "deliver_check"}),
    "kitpip rig": (kitpip_rig, AVATARS | {"compose", "deliver_check"}),
    "kitpip pin": (kitpip_pin, AVATARS | {"compose", "deliver_check"}),
    "content id recorded": (content_id, {"deliver_check"}),
    "handoff turned on": (handoff_on, {"handoff"}),
    "pronunciation entry": (pronunciation_entry, VOICES | AVATARS | {"place", "mix", "compose", "deliver_check"}),
    "engine model": (engine_model, VOICES | AVATARS | {"place", "mix", "compose", "deliver_check"}),
    "engine files": (engine_files, VOICES | AVATARS | {"place", "mix", "compose", "deliver_check"}),
    # The persona joins at place and at avatar (its overlay manifest carries labels.persona, so the persona is an
    # avatar knob, lane L5); no voice reruns.
    "persona": (persona, AVATARS | {"place", "mix", "compose", "deliver_check"}),
}


@pytest.mark.parametrize("row", sorted(ROWS))
def test_invalidation_reruns_exactly_the_rows_stages(tmp_path, row):
    change, want = ROWS[row]
    recs = records()
    job = two_segment_avatar_job(recs)
    ctx = stub_ctx()
    s = new_store(tmp_path, job)
    run_all(job, recs, s, ctx)
    change(job, recs, ctx)
    s.write_job(job, replace=True)
    g = graph.plan(job, recs, s, ctx)
    assert {n for n, state in states(g).items() if state in ("stale", "corrupt")} == want
    ran, _ = run_all(job, recs, s, ctx)
    assert set(ran) == want and len(ran) == len(want)


def test_a_voice_rendered_before_kp15_plans_stale(tmp_path, monkeypatch):
    """KP-15 changed narrate render's captions for the same inputs, so voice is at impl 2 and an impl-1 voice reruns."""
    assert graph.IMPL["voice"] == 2 and graph.IMPL["compose"] == 2 and graph.IMPL["handoff"] == 2
    assert all(impl == 1 for stage, impl in graph.IMPL.items() if stage not in ("voice", "compose", "handoff"))
    recs = records()
    job = two_segment_avatar_job(recs)
    ctx = stub_ctx()
    s = new_store(tmp_path, job)
    with monkeypatch.context() as m:
        m.setitem(graph.IMPL, "voice", 1)
        run_all(job, recs, s, ctx)
    g = graph.plan(job, recs, s, ctx)
    stale = {n for n, state in states(g).items() if state in ("stale", "corrupt")}
    assert stale == VOICES | AVATARS | {"place", "mix", "compose", "deliver_check"}
    voices = {n["id"]: n["reason"] for n in g["nodes"] if n["stage"] == "voice"}
    assert voices == {"voice/seg-1": "key_changed", "voice/seg-2": "key_changed"}


def test_the_voice_key_holds_the_engine_by_digest_and_the_pronunciation_table_and_no_private_path():
    recs = records()
    recs["engines"]["fake-sine"] |= {
        "endpoint": "http://private-host.invalid:9000",
        "files": [{"path": "/private/b.bin", "sha256": "b" * 64}, {"path": "/private/a.bin", "sha256": "a" * 64}],
    }
    job = example("nv-fixture-card")
    segment = job["segments"][0]
    knobs = graph.knobs_for("voice", segment, job, recs, None)
    assert knobs["engine"]["files"] == ["a" * 64, "b" * 64] and "endpoint" not in knobs["engine"]
    assert knobs["engine"]["model"] == "fake-sine-v1"
    table = recs["pronunciation"]["narrate-en-example"]
    assert knobs["pronunciation"] == {"id": "narrate-en-example", "sha256": keys.digest(table)}
    assert "/private" not in keys.canonical(knobs) and "private-host" not in keys.canonical(knobs)
    tool = graph.tool_for("voice", plain_ctx(), segment, recs)
    assert tool["binary_sha256"] == keys.digest(["a" * 64, "b" * 64])
    del recs["engines"]["fake-sine"]
    assert graph.knobs_for("voice", segment, job, recs, None)["engine"] is None


def test_deck_reassembly_with_the_same_takes_keeps_voice_and_avatar(tmp_path):
    recs = records()
    job = example("nv-fixture-client-narrated")
    ctx = stub_ctx()
    s = new_store(tmp_path, job)
    run_all(job, recs, s, ctx)
    job["base"]["deck"]["videoSha256"] = hashlib.sha256(b"re-assembled fixture deck video").hexdigest()
    s.write_job(job, replace=True)
    ran, _ = run_all(job, recs, s, ctx)
    assert set(ran) == {"base", "place", "mix", "compose", "deliver_check"}


def test_a_rerun_with_identical_content_stops_the_cascade(tmp_path):
    """A downstream key holds the upstream content digest, which leaves out run_dir, created_utc and the commit."""
    job = example("nv-fixture-card")
    recs = records()
    s = new_store(tmp_path, job)
    run_all(job, recs, s, plain_ctx())
    entry = s.entry("mix")
    (s.dir / entry["dir"] / "out.json").write_text("tampered")
    g = graph.plan(job, recs, s, plain_ctx())
    assert states(g)["mix"] == "corrupt" and states(g)["compose"] == "stale"
    ran, g = run_all(job, recs, s, plain_ctx())
    assert ran == ["mix"]
    assert len(list(s.history.iterdir())) == 1
    assert states(g)["compose"] == "fresh"


# Freshness and the store ---------------------------------------------------------------------------------------
@pytest.fixture
def settled(tmp_path):
    job = example("nv-fixture-card")
    recs = records()
    s = new_store(tmp_path, job)
    run_all(job, recs, s, plain_ctx())
    return job, recs, s


def plan_state(settled, node):
    job, recs, s = settled
    row = next(n for n in graph.plan(job, recs, s, plain_ctx())["nodes"] if n["id"] == node)
    return row["state"], row["reason"]


def test_a_tampered_output_is_corrupt_and_never_trusted_by_mtime(settled):
    _, _, s = settled
    path = s.dir / s.entry("base")["dir"] / "out.json"
    stat = path.stat()
    path.write_text(path.read_text().replace("base", "BASE"))
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    assert plan_state(settled, "base") == ("corrupt", "output_digest_mismatch: out.json")
    assert plan_state(settled, "place")[0] == "stale"


@pytest.mark.parametrize("damage", ["extra file", "missing output", "manifest edit", "renamed dir", "symlink"])
def test_every_kind_of_damage_makes_a_stage_corrupt(settled, damage):
    _, _, s = settled
    directory = s.dir / s.entry("music")["dir"]
    if damage == "extra file":
        (directory / "stray.txt").write_text("x")
    elif damage == "missing output":
        (directory / "out.json").unlink()
    elif damage == "manifest edit":
        manifest = json.loads((directory / "manifest.json").read_text())
        manifest["knobs"]["rateHz"] = 44100
        (directory / "manifest.json").write_text(json.dumps(manifest))
    elif damage == "renamed dir":
        s_current = s.current()
        moved = directory.with_name("0" * 16)
        directory.rename(moved)
        s_current["stages"]["music"]["dir"] = moved.relative_to(s.dir).as_posix()
        store.write_atomic(s.current_file, s_current)
    else:
        (directory / "link.json").symlink_to(directory / "out.json")
    assert plan_state(settled, "music")[0] == "corrupt"


def test_archive_moves_a_stage_to_history_and_it_becomes_stale(settled):
    _, _, s = settled
    target = s.archive("compose")
    assert target.parent == s.history and (target / "manifest.json").is_file()
    assert plan_state(settled, "compose") == ("stale", "no_run")
    assert plan_state(settled, "deliver_check") == ("stale", "upstream_stale")


def test_a_leftover_partial_directory_is_ignored(settled):
    job, recs, s = settled
    before = states(graph.plan(job, recs, s, plain_ctx()))
    key = s.entry("compose")["key"]
    partial = s.partial_dir("compose", key)
    partial.mkdir()
    (partial / "half.json").write_text("{")
    assert states(graph.plan(job, recs, s, plain_ctx())) == before
    assert all(problems == [] for problems in s.verify().values())
    assert s.begin("compose", key) == partial and list(partial.iterdir()) == []


def test_a_refusal_holds_for_its_key_only(settled):
    job, recs, s = settled
    s.archive("mix")
    key = next(n["key"] for n in graph.plan(job, recs, s, plain_ctx())["nodes"] if n["id"] == "mix")
    s.record_refusal("mix", key, "loudness_drift", "fixture")
    assert plan_state(settled, "mix") == ("refused", "loudness_drift")
    assert plan_state(settled, "compose") == ("blocked", "upstream_blocked")
    job["music"]["duckDb"] = 6
    s.write_job(job, replace=True)
    assert plan_state(settled, "mix") == ("stale", "no_run")


def test_the_store_refuses_guitar_runs_narrate_runs_and_symlinks(tmp_path):
    for root, code in (
        (ROOT / "artifacts" / "runs" / "x", "store_in_guitar_runs"),
        (ROOT / "artifacts" / "narrate", "store_in_narrate_runs"),
    ):
        with pytest.raises(store.StoreError) as caught:
            store.JobStore(root, "nv-a")
        assert caught.value.code == code
    (tmp_path / "real").mkdir()
    (tmp_path / "narrated").mkdir()
    (tmp_path / "narrated" / "nv-a").symlink_to(tmp_path / "real")
    with pytest.raises(store.StoreError) as caught:
        store.JobStore(tmp_path / "narrated", "nv-a")
    assert caught.value.code == "stage_symlink"
    for bad in ("../x", "A", "", "voice/seg/x"):
        with pytest.raises(store.StoreError):
            store.node_parts(bad) if "/" in bad else store.JobStore(tmp_path, bad)


def test_a_stage_dir_records_its_key_inputs_and_repo_relative_run_dir(settled):
    _, _, s = settled
    manifest = s.manifest("mix")
    assert manifest["kind"] == "nv_stage" and manifest["stage"] == "mix" and manifest["segment"] is None
    assert keys.stage_key(manifest["key_document"]) == manifest["stage_key"]
    assert {i["slot"] for i in manifest["inputs"]} == {"place", "music"}
    assert manifest["content_sha256"] == keys.content_digest(manifest)
    assert manifest["run_dir"] is None  # the test store is outside the checkout


# Admit ---------------------------------------------------------------------------------------------------------
def consent_gone(job, recs):
    recs["consents"].clear()


def consent_revoked(job, recs):
    recs["consents"]["consent-fixture-sine"]["revokedAt"] = "2026-10-27"


def consent_persona(job, recs):
    recs["consents"]["consent-fixture-sine"]["persona"] = "fixture-persona"


def avatar_without_persona(job, recs):
    job["avatar"] = copy.deepcopy(DEFAULTS["avatar"])


def bed_unknown(job, recs):
    job["music"]["bed"] = "bed-unknown"


def bed_by_agent(job, recs):
    recs["music_beds"]["bed-fixture-emaj"]["acquisition"]["acquiredBy"] = "Agent"


def bed_one_layer(job, recs):
    recs["music_beds"]["bed-fixture-emaj"]["layers"] = recs["music_beds"]["bed-fixture-emaj"]["layers"][:1]


def script_mismatch(job, recs):
    job["segments"][0]["scriptSha256"] = "0" * 64


def narrate_job_unknown(job, recs):
    job["segments"][0]["narrateJob"] = "job-unknown"


def client_voice_only(job, recs):
    job["edition"] = "ClientVoiceOnly"
    job["music"] = None


def client_bed_not_cleared(job, recs):
    job["edition"] = "ClientNarrated"


def tighten_off_with_edits(job, recs):
    job["base"] = {"deck": copy.deepcopy(examples()["nv-fixture-client-narrated"]["base"]["deck"])}


def width_out(job, recs):
    job["avatar"] = copy.deepcopy(DEFAULTS["avatar"]) | {"width": 0.4}
    job["labels"]["persona"] = "fixture-persona"


def duck_zero(job, recs):
    job["music"]["duckDb"] = 0


def drift_wide(job, recs):
    job["delivery"]["driftLu"] = 0.6


def peak_hot(job, recs):
    job["delivery"]["truePeakDbtp"] = -1.0


def tempo_fast(job, recs):
    recs["music_beds"]["bed-fixture-emaj"]["layers"][1]["tempoFactor"] = 2.5


def tempo_slow(job, recs):
    recs["music_beds"]["bed-fixture-emaj"]["layers"][0]["tempoFactor"] = 0.25


ADMIT = {
    "consent_missing": consent_gone,
    "consent_revoked": consent_revoked,
    "persona_label_missing": consent_persona,
    "persona_label_missing (avatar)": avatar_without_persona,
    "bed_record_missing": bed_unknown,
    "bed_acquisition_agent": bed_by_agent,
    "bed_layers_invalid": bed_one_layer,
    "script_digest_mismatch": script_mismatch,
    "narrate_job_missing": narrate_job_unknown,
    "edition_voice_refused": client_voice_only,
    "edition_bed_refused": client_bed_not_cleared,
    "tighten_on_synthetic": tighten_off_with_edits,
    "knob_out_of_bounds (width)": width_out,
    "knob_out_of_bounds (duck)": duck_zero,
    "knob_out_of_bounds (drift)": drift_wide,
    "knob_out_of_bounds (peak)": peak_hot,
    "knob_out_of_bounds (tempo above 2)": tempo_fast,
    "knob_out_of_bounds (tempo below 0.5)": tempo_slow,
}


@pytest.mark.parametrize("name", sorted(ADMIT))
def test_admit_refuses_before_any_stage_and_blocks_the_rest(tmp_path, name):
    job, recs = example("nv-fixture-card"), records()
    ADMIT[name](job, recs)
    g = graph.plan(job, recs, None, plain_ctx())
    assert g["admit"]["verdict"] == "Refused"
    assert name.split(" ")[0] in {r["code"] for r in g["admit"]["refusals"]}
    assert states(g)["admit"] == "refused"
    assert all(n["state"] in ("blocked", "not_selected") for n in g["nodes"] if n["stage"] != "admit")
    assert g["runnable"] == []


def test_client_voice_only_refuses_the_avatar_at_plan():
    job = example("nv-fixture-client-deck")
    job["avatar"] = copy.deepcopy(DEFAULTS["avatar"])
    result = admit.admit(job, records())
    assert {r["code"] for r in result["refusals"]} == {"edition_pip_refused"}
    assert result["edition"] == {"verdict": "Refused", "point": "Plan", "codes": ["PipRefused"]}


def test_a_kitpip_binary_off_its_pin_refuses_at_admit(tmp_path):
    tampered = tmp_path / "kitpip"
    tampered.write_bytes(STUB.read_bytes() + b"# changed\n")
    ctx = stub_ctx(tampered)
    assert ctx["kitpip"]["state"] == "mismatch"
    g = graph.plan(example("nv-fixture-avatar"), records(), None, ctx)
    assert [r["code"] for r in g["admit"]["refusals"]] == ["kitpip_pin_mismatch"]


def test_admit_carries_the_labels_and_the_open_operator_gates(tmp_path):
    job = example("nv-fixture-avatar")
    job["delivery"]["upload"] = True
    recs = records()
    result = admit.admit(job, recs)
    assert result["verdict"] == "Admitted"
    assert result["labels"] == {
        "synthetic": True,
        "consent_ids": ["consent-fixture-sine"],
        "voice_ids": ["voice-fixture-sine"],
        "persona": "fixture-persona",
    }
    gates = {(p["gate"], p["stage"]) for p in result["pending_operator"]}
    assert gates == {
        ("listening_acceptance", "voice_qa"),
        ("lip_sync_acceptance", "avatar_check"),
        ("bed_licence_incomplete", "deliver_check"),
        ("bed_content_id_unchecked", "deliver_check"),
    }
    s = new_store(tmp_path, job)
    _, g = run_all(job, recs, s, stub_ctx())
    assert states(g)["deliver_check"] == "pending_operator"
    bed = recs["music_beds"]["bed-fixture-emaj"]["licence"]
    bed["certifiedPdfSha256"] = "e" * 64
    bed["contentIdCheck"] = {"clear": "fixture-check-1"}
    ran, g = run_all(job, recs, s, stub_ctx())
    assert ran == ["deliver_check"] and states(g)["deliver_check"] == "fresh"


# Jobs ----------------------------------------------------------------------------------------------------------
def test_init_from_the_defaults_is_the_simple_card_example():
    script = (EXAMPLES / "script.md").read_bytes()
    digest = hashlib.sha256(script).hexdigest()
    job = init_job("nv-fixture-card", "job-fixture-fake", digest, bed="bed-fixture-emaj", avatar=False)
    assert job == examples()["nv-fixture-card"]
    # NV-8: the avatar is on by default where the edition allows one, with the persona the caller gives.
    on = init_job("nv-fixture-avatar", "job-fixture-fake", digest, bed="bed-fixture-emaj", persona="fixture-persona")
    assert on == examples()["nv-fixture-avatar"]
    assert init_job("nv-n", "job-fixture-fake", digest, edition="ClientNarrated")["avatar"] == DEFAULTS["avatar"]
    still = init_job("nv-still", "job-fixture-fake", "1" * 64, still="2" * 64, avatar=False)
    assert still["base"] == {"still": {"sha256": "2" * 64, "size": {"w": 1920, "h": 1080}, "fps": FPS, "tailS": 1}}
    assert still["music"] is None and still["avatar"] is None and still["tighten"] == {"enabled": False}
    for bad in ({"still": "/a/path.png"}, {"colour": "red"}):
        with pytest.raises(JobError):
            init_job("nv-x", "job-fixture-fake", "1" * 64, **bad)


@pytest.mark.parametrize(
    "edit",
    [
        lambda j: j.pop("labels"),
        lambda j: j.update(id="Bad Id"),
        lambda j: j.update(edition="Public"),
        lambda j: j.update(base={"slides": {}}),
        lambda j: j["segments"].append(copy.deepcopy(j["segments"][0])),
        lambda j: j.update(tighten={}),
        lambda j: j["segments"][0].pop("avatar"),
        lambda j: j["segments"][0].pop("anchor"),
        lambda j: j["segments"][0].update(anchor={"atSeconds": "soon"}),
        lambda j: j["segments"][0].update(scriptSha256="/a/script.md"),
        lambda j: j["delivery"].pop("voiceOnlyListen"),
        lambda j: j["delivery"].update(channels="Surround"),
        lambda j: j["music"].pop("duckDb"),
        lambda j: j["music"].update(attackMs=-1),
        lambda j: j["labels"].update(badge="AI"),
        lambda j: j["captions"].update(burn="no"),
        lambda j: j["base"]["card"].pop("fps"),
        lambda j: j["base"]["card"].update(colour="red"),
        lambda j: j.update(avatar={"external": "kitpip"}),
        lambda j: j.update(avatar=dict(DEFAULTS["avatar"], corner="Middle")),
        lambda j: j.update(base={"deck": {"producer": "x", "videoSha256": "1" * 64}}),
    ],
)
def test_a_misshapen_job_refuses(edit):
    job = example("nv-fixture-card")
    edit(job)
    with pytest.raises(JobError) as caught:
        check_shape(job)
    assert caught.value.code == "job_invalid"


# CLI -----------------------------------------------------------------------------------------------------------
@pytest.fixture
def cli_env(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "ffmpeg_identity", lambda: FFMPEG_ID)
    for name in (store.ROOT_ENV, cli.RECORDS_ENV, kitpip.EXTERNALS_ENV, kitpip.BIN_ENV):
        monkeypatch.delenv(name, raising=False)
    return ["--root", str(tmp_path / "narrated"), "--records", str(EXAMPLES)]


def call(capsys, argv):
    code = cli.main(argv)
    out, err = capsys.readouterr()
    return code, out, err


def test_cli_init_plan_status_and_explain(tmp_path, capsys, cli_env):
    code, out, _ = call(
        capsys,
        [
            "init",
            *cli_env,
            "--job",
            "nv-fixture-card",
            "--narrate-job",
            "job-fixture-fake",
            "--script",
            str(EXAMPLES / "script.md"),
            "--bed",
            "bed-fixture-emaj",
            "--no-avatar",
            "--json",
        ],
    )
    assert code == 0 and json.loads(out)["counts"]["stale"] == 9
    s = store.JobStore(tmp_path / "narrated", "nv-fixture-card")
    assert s.read_job() == examples()["nv-fixture-card"]
    code, out, _ = call(capsys, ["status", "nv-fixture-card", *cli_env, "--json"])
    assert code == 0 and json.loads(out)["kind"] == "nv_graph"
    code, out, _ = call(capsys, ["plan", "nv-fixture-card", *cli_env])
    assert code == 0 and "script/seg-1" in out and "pending_operator listening_acceptance" in out
    run_all(s.read_job(), records(), s, plain_ctx())
    job = s.read_job()
    job["music"]["bedBelowVoiceLu"] = 18
    s.write_job(job, replace=True)
    code, out, _ = call(capsys, ["explain", "nv-fixture-card", "mix", *cli_env])
    explained = json.loads(out)
    assert code == 0 and (explained["state"], explained["reason"]) == ("stale", "key_changed")
    assert explained["changed"] == [{"field": "knobs.music.bedBelowVoiceLu", "was": 20, "now": 18}]
    code, out, _ = call(capsys, ["explain", "nv-fixture-card", "voice", "--segment", "seg-1", *cli_env])
    assert json.loads(out)["state"] == "fresh" and json.loads(out)["changed"] == []
    code, out, _ = call(capsys, ["verify", str(s.dir)])
    assert code == 0 and json.loads(out)["ok"] is True
    (s.dir / s.entry("base")["dir"] / "out.json").write_text("x")
    code, out, _ = call(capsys, ["verify", str(s.dir)])
    assert code == 1 and json.loads(out)["problems"]["base"] == ["output_digest_mismatch: out.json"]


def test_cli_refusals_use_the_narrate_stderr_shape(tmp_path, capsys, cli_env):
    records_dir = tmp_path / "records"
    shutil.copytree(EXAMPLES, records_dir)
    (records_dir / "consents.json").write_text("[]")
    argv = [
        "init",
        "--root",
        str(tmp_path / "narrated"),
        "--records",
        str(records_dir),
        "--job",
        "nv-a",
        "--narrate-job",
        "job-fixture-fake",
        "--script",
        str(EXAMPLES / "script.md"),
    ]
    code, out, err = call(capsys, argv)
    detail = "segment seg-1: voice voice-fixture-sine has no consent record"
    assert code == 1 and out == "" and json.loads(err) == {"ok": False, "refused": "consent_missing", "detail": detail}
    assert not (tmp_path / "narrated" / "nv-a").exists()
    code, _, err = call(
        capsys,
        [
            "init",
            *cli_env,
            "--job",
            "nv-b",
            "--narrate-job",
            "job-fixture-fake",
            "--script",
            str(EXAMPLES / "script.md"),
            "--voice",
            "voice-other",
        ],
    )
    assert code == 1 and json.loads(err)["refused"] == "voice_mismatch"
    # NV-8: the avatar is on by default, so init without a persona refuses and names both ways out.
    argv = [
        "init",
        *cli_env,
        "--job",
        "nv-c",
        "--narrate-job",
        "job-fixture-fake",
        "--script",
        str(EXAMPLES / "script.md"),
    ]
    code, _, err = call(capsys, argv)
    refused = json.loads(err)
    assert code == 1 and refused["refused"] == "persona_label_missing"
    assert "--persona P, or --no-avatar" in refused["detail"] and not (tmp_path / "narrated" / "nv-c").exists()
    code, _, _ = call(capsys, argv + ["--persona", "fixture-persona"])
    assert code == 0 and store.JobStore(tmp_path / "narrated", "nv-c").read_job()["avatar"] == DEFAULTS["avatar"]
    with pytest.raises(SystemExit):
        cli.main(argv + ["--avatar", "--no-avatar"])
    capsys.readouterr()
    code, _, err = call(capsys, ["status", "nv-none", *cli_env])
    assert code == 1 and json.loads(err)["refused"] == "graph_missing"
    code, _, err = call(capsys, ["plan", "nv-none", *cli_env])
    assert code == 1 and json.loads(err)["refused"] == "job_missing"


def test_cli_init_client_voice_only_refuses_and_points_to_a_render(tmp_path, capsys, cli_env):
    """NV-6: init voices a synthetic segment, so ClientVoiceOnly comes only through --from (the deck example)."""
    defaults = ["init", *cli_env, "--narrate-job", "job-fixture-fake", "--script", str(EXAMPLES / "script.md")]
    for flags in (["--client", "--edition", "ClientVoiceOnly"], ["--edition", "ClientVoiceOnly"]):
        code, out, err = call(capsys, [*defaults, "--job", "nv-voice-only", *flags, "--json"])
        refused = json.loads(err)
        assert code == 1 and out == "" and refused["refused"] == "edition_voice_refused"
        assert "--from" in refused["detail"]
        assert not (tmp_path / "narrated" / "nv-voice-only").exists()
    # --client turns the avatar on (NV-8), so the job needs a persona label.
    code, out, _ = call(capsys, [*defaults, "--job", "nv-client", "--client", "--persona", "fixture-persona", "--json"])
    assert code == 0 and json.loads(out)["ok"] is True
    assert store.JobStore(tmp_path / "narrated", "nv-client").read_job()["edition"] == "ClientNarrated"
    code, out, _ = call(
        capsys,
        [
            "init",
            *cli_env,
            "--job",
            "nv-fixture-client-deck",
            "--from",
            str(EXAMPLES / "narrated-videos.json"),
            "--json",
        ],
    )
    assert code == 0 and json.loads(out)["ok"] is True
    deck = store.JobStore(tmp_path / "narrated", "nv-fixture-client-deck").read_job()
    assert deck["edition"] == "ClientVoiceOnly"


def test_cli_init_from_a_render_and_a_refused_plan(tmp_path, capsys, cli_env):
    code, _, _ = call(
        capsys, ["init", *cli_env, "--job", "nv-fixture-avatar", "--from", str(EXAMPLES / "narrated-videos.json")]
    )
    assert code == 0
    code, _, err = call(
        capsys,
        [
            "init",
            *cli_env,
            "--job",
            "nv-fixture-avatar",
            "--from",
            str(EXAMPLES / "narrated-videos.json"),
            "--edition",
            "ClientVoiceOnly",
        ],
    )
    assert code == 1 and json.loads(err)["refused"] == "usage"
    code, _, err = call(
        capsys, ["init", *cli_env, "--job", "nv-none", "--from", str(EXAMPLES / "narrated-videos.json")]
    )
    assert code == 1 and json.loads(err)["refused"] == "job_invalid"
    s = store.JobStore(tmp_path / "narrated", "nv-fixture-avatar")
    job = s.read_job()
    job["edition"] = "ClientVoiceOnly"
    s.write_job(job, replace=True)
    code, out, _ = call(capsys, ["plan", "nv-fixture-avatar", *cli_env, "--json"])
    graph_doc = json.loads(out)
    assert code == 1 and graph_doc["admit"]["edition"]["codes"] == ["VoiceRefused", "PipRefused", "BedRefused"]


def test_cli_init_from_a_misshapen_record_refuses_and_writes_nothing(tmp_path, capsys, cli_env):
    for name, edit in (
        ("segment", lambda j: j["segments"][0].pop("avatar")),
        ("delivery", lambda j: j["delivery"].pop("voiceOnlyListen")),
    ):
        job = example("nv-fixture-card")
        edit(job)
        record = tmp_path / f"{name}.json"
        record.write_text(json.dumps(job))
        code, out, err = call(capsys, ["init", *cli_env, "--job", "nv-fixture-card", "--from", str(record)])
        assert code == 1 and out == "" and json.loads(err)["refused"] == "job_invalid"
        assert not (tmp_path / "narrated" / "nv-fixture-card").exists()


@pytest.mark.parametrize("damage", ["{", "[]", '{"stages": {"base": 1}}', '{"refusals": {"mix": {}}}', "\udcff"])
def test_a_damaged_current_or_graph_file_refuses_store_invalid(tmp_path, capsys, cli_env, damage):
    code, _, _ = call(
        capsys, ["init", *cli_env, "--job", "nv-fixture-card", "--from", str(EXAMPLES / "narrated-videos.json")]
    )
    assert code == 0
    s = store.JobStore(tmp_path / "narrated", "nv-fixture-card")
    raw = damage.encode("utf-8", "surrogateescape")
    s.current_file.write_bytes(raw)
    for argv in (["plan", "nv-fixture-card"], ["explain", "nv-fixture-card", "mix"]):
        code, out, err = call(capsys, [*argv, *cli_env])
        assert code == 1 and out == "" and json.loads(err)["refused"] == "store_invalid"
    s.current_file.unlink()
    s.graph_file.write_bytes(raw)
    code, out, err = call(capsys, ["status", "nv-fixture-card", *cli_env])
    assert code == 1 and out == "" and json.loads(err)["refused"] == "store_invalid"


# kitpip --------------------------------------------------------------------------------------------------------
def test_the_avatar_keys_the_default_rig_revision_only_for_the_default_rig():
    pin = kitpip.load_pin(EXTERNALS)
    recs = records()
    job = example("nv-fixture-avatar")
    segment = job["segments"][0]
    default = pin["default_rig"]
    for rig, revision, want in (
        (None, None, (default["id"], default["sha256"])),
        (default["id"], None, (default["id"], default["sha256"])),
        ("some-other-rig", None, ("some-other-rig", None)),
        ("some-other-rig", "d" * 64, ("some-other-rig", "d" * 64)),
        (None, "d" * 64, (default["id"], "d" * 64)),
    ):
        job["avatar"].update(rig=rig, rigRevisionSha256=revision)
        knobs = graph.knobs_for("avatar", segment, job, recs, pin)
        assert (knobs["rig"], knobs["rigRevisionSha256"]) == want


def test_the_fixture_pin_is_the_stub_and_never_a_release():
    pin = kitpip.load_pin(EXTERNALS)
    want = pin["binaries"]["kitpip"]["any"]
    assert (want["sha256"], want["bytes"]) == (hashlib.sha256(STUB.read_bytes()).hexdigest(), STUB.stat().st_size)
    assert pin["visibility"] == "test_fixture" and pin["source_commit"] == "0" * 40
    assert pin["default_rig"] == {
        "id": "kitpip-stub-rig",
        "revision": 0,
        "sha256": hashlib.sha256(b"kitpip-stub-rig").hexdigest(),
    }
    assert os.access(STUB, os.X_OK)
    text = EXTERNALS.read_text()
    assert "http" not in text and "/" not in json.dumps(pin["binaries"])


def test_resolve_states(tmp_path):
    pin = kitpip.load_pin(EXTERNALS)
    assert kitpip.resolve(None)["state"] == "unregistered"
    assert kitpip.resolve(pin, {})["state"] == "missing"
    assert kitpip.resolve(pin, {kitpip.BIN_ENV: str(tmp_path / "none")})["state"] == "missing"
    assert kitpip.resolve(pin, {kitpip.BIN_ENV: str(STUB)})["state"] == "resolved"
    real = {**pin, "visibility": "private"}
    assert kitpip.resolve(real, {kitpip.BIN_ENV: str(STUB)})["state"] == "missing"  # 'any' serves fixtures only
    for bad in ([], {"schema_version": 1}, {"schema_version": 1, "externals": {"kitpip": {"version": "1"}}}):
        path = tmp_path / "bad.json"
        path.write_text(json.dumps(bad))
        with pytest.raises(JobError) as caught:
            kitpip.load_pin(path)
        assert caught.value.code == "externals_invalid"


def pinned_script(tmp_path, body):
    """A script binary and a test-fixture externals record that pins it."""
    binary = tmp_path / "kitpip-wrapper"
    binary.write_text(body)
    binary.chmod(0o755)
    record = json.loads(EXTERNALS.read_text())
    record["externals"]["kitpip"]["binaries"]["kitpip"]["any"] = {
        "sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "bytes": binary.stat().st_size,
    }
    externals = tmp_path / "externals.json"
    externals.write_text(json.dumps(record))
    pin = kitpip.load_pin(externals)
    return binary, pin, kitpip.resolve(pin, {kitpip.BIN_ENV: str(binary)})


def test_a_binary_changed_after_resolve_refuses_before_spawn(tmp_path):
    sentinel = tmp_path / "spawned"
    binary, pin, resolution = pinned_script(tmp_path, f"#!/bin/sh\ntouch {sentinel}\n")
    assert resolution["state"] == "resolved"
    binary.write_text(binary.read_text() + "# changed\n")
    with pytest.raises(kitpip.KitpipRefused) as caught:
        kitpip.call(resolution, pin, ["--version"])
    assert caught.value.code == "kitpip_pin_mismatch" and not sentinel.exists()
    with pytest.raises(kitpip.KitpipRefused) as caught:
        kitpip.call(resolution, pin, ["render", "x", "--allow-unlabelled-test"])
    assert caught.value.code == "contract_invalid" and not sentinel.exists()


@pytest.mark.parametrize("code", ["no_consent", "not_synthetic", "digest_mismatch", "unknown_rig"])
def test_kitpip_refusals_are_relayed_with_their_code(tmp_path, code):
    _, pin, resolution = pinned_script(tmp_path, f'#!/bin/sh\nKITPIP_STUB_REFUSE={code} exec python3 "{STUB}" "$@"\n')
    with pytest.raises(kitpip.KitpipRefused) as caught:
        kitpip.call(resolution, pin, ["verify", str(tmp_path)])
    assert caught.value.code == code
    ctx = stub_ctx()
    assert kitpip.call(ctx["kitpip"], ctx["pin"], ["--version"]) == {"commit": "0" * 40, "version": "0.0.0-stub"}


def narrate_run(tmp_path, workspace):
    final, manifest = render.render(Config(workspace.write(SLIDE)))
    return final, manifest


def avatar_document(narration_manifest, ctx):
    knobs = {"rig": "kitpip-stub-rig", "rigRevisionSha256": ctx["pin"]["default_rig"]["sha256"], "renderSize": 64}
    inputs = [
        {"slot": "voice:seg-1", "stage": "voice", "digest": narration_manifest["content_sha256"]},
        {"slot": "base.fps", "stage": "base", "value": FPS},
    ]
    return keys.key_document(
        "avatar", "seg-1", graph.IMPL["avatar"], ctx["kitpip"]["tool"], None, knobs, "Internal", inputs
    )


def pixel_alpha(overlay, x, y, size):
    raw = subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-loglevel",
            "error",
            "-i",
            str(overlay),
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgba",
            "-",
        ],
        capture_output=True,
        check=True,
    ).stdout
    assert len(raw) == size * size * 4
    return raw[(y * size + x) * 4 + 3]


def test_the_kitpip_stub_stage_renders_a_labelled_alpha_overlay_into_the_store(tmp_path, workspace, ffmpeg):
    run_dir, narration = narrate_run(tmp_path, workspace)
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in run_dir.iterdir() if p.is_file()}
    ctx = stub_ctx()
    job = example("nv-fixture-avatar")
    s = new_store(tmp_path, job)
    document = avatar_document(narration, ctx)
    key = keys.stage_key(document)
    manifest = kitpip.run_avatar(
        s,
        "avatar/seg-1",
        key,
        document,
        run_dir,
        FPS,
        "kitpip-stub-rig",
        64,
        "fixture-persona",
        ctx["kitpip"],
        ctx["pin"],
        rig_sha256=ctx["pin"]["default_rig"]["sha256"],
    )
    directory = s.final_dir("avatar/seg-1", key)
    assert store.verify_stage_dir(directory, key) == []
    assert s.entry("avatar/seg-1")["key"] == key
    assert manifest["timeline"]["mapping"] == "avatar_overlay_v1" and manifest["timeline"]["no_time_stretch"] is False
    assert manifest["synthetic"] is True and manifest["labels"]["consent_ids"] == ["consent-fixture-sine"]
    assert manifest["labels"]["persona"] == "fixture-persona"
    assert manifest["labels"]["voice_ids"] == [v["voice"] for v in narration["voices"]]
    assert manifest["measurements"]["rig"] == {"id": "kitpip-stub-rig", "sha256": ctx["pin"]["default_rig"]["sha256"]}
    assert manifest["states"] == {"source_checks": "passed", "render": "stub", "lip_sync": "pending_operator"}
    assert manifest["timeline"]["narration"]["content_sha256"] == narration["content_sha256"]
    overlay = directory / "overlay" / "overlay.mov"
    assert pixel_alpha(overlay, 0, 0, 64) == 0 and pixel_alpha(overlay, 63, 63, 64) == 0
    assert pixel_alpha(overlay, 32, 32, 64) == 255
    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in run_dir.iterdir() if p.is_file()}
    assert after == before and not (run_dir / "analyze").exists()


def test_the_kitpip_stage_refuses_a_store_inside_the_narrate_run_and_records_refusals(tmp_path, workspace, ffmpeg):
    run_dir, narration = narrate_run(tmp_path, workspace)
    ctx = stub_ctx()
    document = avatar_document(narration, ctx)
    key = keys.stage_key(document)
    inside = store.JobStore(run_dir / "narrated", "nv-fixture-avatar")
    with pytest.raises(kitpip.KitpipRefused) as caught:
        kitpip.run_avatar(
            inside,
            "avatar/seg-1",
            key,
            document,
            run_dir,
            FPS,
            "kitpip-stub-rig",
            64,
            "fixture-persona",
            ctx["kitpip"],
            ctx["pin"],
        )
    assert caught.value.code == "avatar_outside_store" and not (run_dir / "narrated").exists()
    s = new_store(tmp_path, example("nv-fixture-avatar"))
    with pytest.raises(kitpip.KitpipRefused) as caught:
        kitpip.run_avatar(
            s,
            "avatar/seg-1",
            key,
            document,
            run_dir,
            FPS,
            "no-such-rig",
            64,
            "fixture-persona",
            ctx["kitpip"],
            ctx["pin"],
        )
    assert caught.value.code == "unknown_rig"
    assert s.current()["refusals"]["avatar/seg-1"]["code"] == "unknown_rig"
    assert not s.partial_dir("avatar/seg-1", key).exists() and s.entry("avatar/seg-1") is None


def run_stub_avatar(tmp_path, run_dir, narration, binary_body, timeout_s=kitpip.TIMEOUT_S):
    """run_avatar through a pinned wrapper script; (store, key, the KitpipRefused it raised)."""
    _, pin, resolution = pinned_script(tmp_path, binary_body)
    ctx = {"pin": pin, "kitpip": resolution}
    document = avatar_document(narration, ctx)
    key = keys.stage_key(document)
    s = new_store(tmp_path, example("nv-fixture-avatar"))
    with pytest.raises(kitpip.KitpipRefused) as caught:
        kitpip.run_avatar(
            s,
            "avatar/seg-1",
            key,
            document,
            run_dir,
            FPS,
            "kitpip-stub-rig",
            64,
            "fixture-persona",
            resolution,
            pin,
            timeout_s,
            rig_sha256=pin["default_rig"]["sha256"],
        )
    return s, key, caught.value


@pytest.mark.parametrize(
    "body, code",
    [
        ("#!/bin/sh\nexec sleep 5\n", "kitpip_timeout"),
        ('#!/bin/sh\necho \'{"error": "out of memory"}\'\nexit 2\n', "kitpip_error"),
        ("#!/bin/sh\necho not-json\n", "kitpip_error"),
    ],
)
def test_a_wrapper_failure_is_not_recorded_and_the_avatar_stays_runnable(tmp_path, workspace, body, code):
    run_dir, narration = narrate_run(tmp_path, workspace)
    s, key, refused = run_stub_avatar(tmp_path, run_dir, narration, body, timeout_s=1)
    assert refused.code == code and refused.verdict is False
    assert s.current()["refusals"] == {} and s.freshness("avatar/seg-1", key) == ("stale", "no_run")
    assert not s.partial_dir("avatar/seg-1", key).exists()


def test_a_binary_that_fails_its_pin_at_spawn_is_not_recorded(tmp_path, workspace):
    run_dir, narration = narrate_run(tmp_path, workspace)
    binary, pin, resolution = pinned_script(tmp_path, f'#!/bin/sh\nexec python3 "{STUB}" "$@"\n')
    binary.write_text(binary.read_text() + "# changed\n")
    ctx = {"pin": pin, "kitpip": resolution}
    document = avatar_document(narration, ctx)
    key = keys.stage_key(document)
    s = new_store(tmp_path, example("nv-fixture-avatar"))
    with pytest.raises(kitpip.KitpipRefused) as caught:
        kitpip.run_avatar(s, "avatar/seg-1", key, document, run_dir, FPS, "kitpip-stub-rig", 64, "p", resolution, pin)
    assert caught.value.code == "kitpip_pin_mismatch" and caught.value.verdict is False
    assert s.current()["refusals"] == {} and s.freshness("avatar/seg-1", key) == ("stale", "no_run")


def mutating_stub(mutation):
    """A wrapper that runs the stub and then applies mutation (Python on manifest m) after a passing verify."""
    return f"""#!/usr/bin/env python3
import json, subprocess, sys
from pathlib import Path
done = subprocess.run([sys.executable, {str(STUB)!r}, *sys.argv[1:]], capture_output=True, text=True)
if sys.argv[1] == "verify" and done.returncode == 0:
    path = Path(sys.argv[2]) / "manifest.json"
    m = json.loads(path.read_text())
    {mutation}
    path.write_text(json.dumps(m))
sys.stdout.write(done.stdout)
sys.exit(done.returncode)
"""


@pytest.mark.parametrize(
    "mutation, code",
    [
        ('m["voice_ids"] = []', "label_chain_broken"),
        ('m["voice_ids"] = ["voice-other"]', "label_chain_broken"),
        ('m["consent_ids"] = []', "label_chain_broken"),
        ('m["synthetic"] = False', "label_chain_broken"),
        ('m["rig"]["sha256"] = "0" * 64', "kitpip_pin_mismatch"),
    ],
)
def test_an_overlay_that_alters_a_label_or_the_rig_revision_refuses_and_is_recorded(
    tmp_path, workspace, ffmpeg, mutation, code
):
    run_dir, narration = narrate_run(tmp_path, workspace)
    s, key, refused = run_stub_avatar(tmp_path, run_dir, narration, mutating_stub(mutation))
    assert refused.code == code and refused.verdict is True
    assert s.freshness("avatar/seg-1", key) == ("refused", code)
    assert not s.partial_dir("avatar/seg-1", key).exists() and s.entry("avatar/seg-1") is None
    assert s.clear_refusal("avatar/seg-1")["code"] == code
    assert s.freshness("avatar/seg-1", key) == ("stale", "no_run") and s.clear_refusal("avatar/seg-1") is None
