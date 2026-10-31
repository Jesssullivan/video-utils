"""The Cade render stage's task body (docs/spec/RENDER_STAGE.md, narrate/video/render_stage.py, Linear TIN-7788).

Every stage runs through a fake runner, as in test_narrated_video_accept.py: one small output per node, a synthetic
video.mp4 for compose, a narrate run digest for each voice node and a deliver_check.json beside the gate table, so no
FFmpeg, model or GPU runs. Digests, run ids, holders and comment ids are made up; none names a real run or notice.
"""

import copy
import hashlib
import importlib.util
import json

import pytest
from test_narrated_video_accept import gates_for
from test_narrated_video_graph import FPS, example, new_store, plain_ctx, records

from narrate.config import ROOT
from narrate.video import cli, graph, keys, render_stage
from narrate.video.job import JobError

COMMIT = "a" * 40
RUN = "b" * 64
HOLDER = "narrate-bench-20261031-s010203"
NOTICE = "00000000-0000-4000-8000-000000000001"


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def request(**changes):
    value = {
        "kind": "narrate_render_stage_request",
        "schema_version": 1,
        "workflow": "cade-hardware-handoff",
        "run_id": "hatchet-run-01",
        "packet_id": "pkt-demo-01",
        "job_id": "nv-fixture-card",
        "edition": "Internal",
        "video_utils_commit": COMMIT,
        "worker_image": "sha256:" + "c" * 64,
        "inputs": {
            "bundle_manifest_sha256": sha("bundle"),
            "records_sha256": sha("records"),
            "engine_record_sha256": sha("engine"),
            "lexical_release_sha256": sha("lexical"),
            "kitpip_sha256": None,
            "denylist_sha256": None,
        },
        "voice": {"mode": "from_run", "runs": {"seg-1": RUN}},
        "lease": None,
        "until": "deliver_check",
    }
    value.update(changes)
    return value


def gpu_request(**lease_changes):
    lease = {
        "lease": "gpu-lease",
        "holder": HOLDER,
        "max_seconds": 1500,
        "helper_sha256": sha("helper"),
        "notice": {"ticket": "TIN-5397", "comment_id": NOTICE},
    }
    lease.update(lease_changes)
    return request(voice={"mode": "gpu_window", "runs": None}, lease=lease)


def refused(fn, *args, **kwargs):
    with pytest.raises(JobError) as caught:
        fn(*args, **kwargs)
    return caught.value.code


# The request -----------------------------------------------------------------------------------------------------
def test_a_from_run_request_plans_no_gpu_phase():
    out = render_stage.plan(request())
    assert out["gpu"] is False
    assert [p["id"] for p in out["phases"]] == ["verify_inputs", "intake", "voice_adopt", "compose", "collect"]
    assert out["request_sha256"] == keys.digest(request())


def test_a_gpu_request_puts_the_lease_on_voice_gpu_only():
    out = render_stage.plan(gpu_request())
    held = [p for p in out["phases"] if p["gpu"]]
    assert [p["id"] for p in held] == ["voice_gpu"]
    assert held[0]["lease"] == {"lease": "gpu-lease", "holder": HOLDER, "max_seconds": 1500}
    assert [p["id"] for p in out["phases"]].index("voice_plan") < [p["id"] for p in out["phases"]].index("voice_gpu")


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"workflow": "client-video-narrated-render"}, "workflow_mismatch"),
        ({"edition": "ClientNarrated"}, "edition_not_v1"),
        ({"run_id": "a/b"}, "token_invalid"),
        ({"packet_id": "host.example:/srv/packet"}, "token_invalid"),
        ({"job_id": "Not An Id"}, "token_invalid"),
        ({"video_utils_commit": "abc"}, "commit_invalid"),
        ({"worker_image": "ghcr.io/x/y:latest"}, "image_invalid"),
        ({"until": "handoff"}, "until_invalid"),
        ({"kind": "other"}, "request_kind"),
        ({"extra": 1}, "request_keys"),
    ],
)
def test_the_request_refuses_a_path_a_host_and_every_shape_v1_does_not_serve(change, code):
    assert refused(render_stage.check_request, request(**change)) == code


def test_inputs_are_digests_only():
    bad = request()
    bad["inputs"]["records_sha256"] = "/srv/records"
    assert refused(render_stage.check_request, bad) == "digest_invalid"
    missing = request()
    missing["inputs"]["engine_record_sha256"] = None
    assert refused(render_stage.check_request, missing) == "digest_invalid"
    extra = request()
    extra["inputs"]["store_path"] = sha("x")
    assert refused(render_stage.check_request, extra) == "inputs_keys"


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"holder": "cade-render-20261031"}, "lease_holder_form"),
        ({"lease": "other-gpu"}, "lease_invalid"),
        ({"max_seconds": 1801}, "lease_window"),
        ({"max_seconds": True}, "lease_window"),
        ({"helper_sha256": None}, "lease_helper_unpinned"),
        ({"notice": None}, "lease_notice_missing"),
        ({"notice": {"ticket": "TIN-7788", "comment_id": NOTICE}}, "lease_notice_missing"),
        ({"notice": {"ticket": "TIN-5397", "comment_id": "posted"}}, "lease_notice_missing"),
    ],
)
def test_a_gpu_window_needs_the_guard_holder_form_a_pinned_helper_and_its_notice(change, code):
    assert refused(render_stage.check_request, gpu_request(**change)) == code


def test_voice_modes_do_not_mix():
    no_lease = request(voice={"mode": "gpu_window", "runs": None})
    assert refused(render_stage.check_request, no_lease) == "lease_missing"
    adopted_with_lease = gpu_request()
    adopted_with_lease["voice"] = {"mode": "from_run", "runs": {"seg-1": RUN}}
    assert refused(render_stage.check_request, adopted_with_lease) == "lease_unneeded"
    assert refused(render_stage.check_request, request(voice={"mode": "from_run", "runs": {}})) == "voice_runs_missing"
    gpu_with_runs = gpu_request()
    gpu_with_runs["voice"]["runs"] = {"seg-1": RUN}
    assert refused(render_stage.check_request, gpu_with_runs) == "voice_runs_unexpected"


def test_the_holder_form_is_finalize_py_s():
    spec = importlib.util.spec_from_file_location("narrate_finalize", ROOT / "narrate" / "serve" / "finalize.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert render_stage.HOLDER.pattern == module.HOLDER.pattern


# Inputs by digest ------------------------------------------------------------------------------------------------
def write_inputs(root):
    (root / "bundle").mkdir(parents=True)
    (root / "bundle" / "manifest.json").write_text('{"bundle": 1}')
    (root / "records").mkdir()
    (root / "records" / "a.json").write_text("{}")
    (root / "lexical").mkdir()
    (root / "lexical" / "dist").mkdir()
    (root / "lexical" / "dist" / "x.json").write_text("[]")
    (root / "engine").write_text('{"engine": 1}')
    value = request()
    named = {
        "bundle_manifest_sha256": render_stage.sha256_file(root / "bundle" / "manifest.json"),
        "records_sha256": render_stage.tree_sha256(root / "records"),
        "lexical_release_sha256": render_stage.tree_sha256(root / "lexical"),
        "engine_record_sha256": render_stage.sha256_file(root / "engine"),
    }
    for name, digest in named.items():
        source = {
            "bundle_manifest_sha256": "bundle",
            "records_sha256": "records",
            "lexical_release_sha256": "lexical",
            "engine_record_sha256": "engine",
        }[name]
        (root / source).rename(root / digest)
        value["inputs"][name] = digest
    return value


def test_inputs_re_hash_under_their_names(tmp_path):
    value = write_inputs(tmp_path)
    assert render_stage.check_input_dir(value["inputs"], tmp_path) == {
        "bundle_manifest_sha256": "manifest",
        "records_sha256": "tree",
        "engine_record_sha256": "file",
        "lexical_release_sha256": "tree",
    }
    records_dir = tmp_path / value["inputs"]["records_sha256"]
    (records_dir / "a.json").write_text('{"changed": true}')
    assert refused(render_stage.check_input_dir, value["inputs"], tmp_path) == "input_digest_mismatch"


def test_a_symlinked_or_missing_input_refuses(tmp_path):
    value = write_inputs(tmp_path)
    lexical = tmp_path / value["inputs"]["lexical_release_sha256"]
    (lexical / "link").symlink_to(lexical / "dist" / "x.json")
    assert refused(render_stage.check_input_dir, value["inputs"], tmp_path) == "input_symlink"
    value["inputs"]["kitpip_sha256"] = sha("kitpip")
    (lexical / "link").unlink()
    assert refused(render_stage.check_input_dir, value["inputs"], tmp_path) == "input_missing"


# The result ------------------------------------------------------------------------------------------------------
def fields_for(node_id, partial, key, job):
    if node_id == "base":
        return {"measurements": {"fps": FPS}}
    if node_id.startswith("voice/"):
        return {"measurements": {"narrate_content_sha256": RUN}}
    if node_id == "compose":
        (partial / "video.mp4").write_bytes(b"synthetic cut " + key.encode())
    if node_id == "deliver_check":
        gates = gates_for(job)
        (partial / "deliver_check.json").write_text(json.dumps({"kind": "nv_deliver_check", "gates": gates}))
        return {"measurements": {"gates": gates, "delivery_gate": {"upload_gates_closed": False}}}
    return {}


def settle(job, recs, s, ctx):
    for _ in range(30):
        g = graph.plan(job, recs, s, ctx)
        if not g["runnable"]:
            return
        for node_id in g["runnable"]:
            document = g["_documents"][node_id]
            key = keys.stage_key(document)
            partial = s.begin(node_id, key)
            (partial / "out.json").write_text(json.dumps({"node": node_id, "key": key}))
            s.commit(node_id, key, document, fields_for(node_id, partial, key, job))
    raise AssertionError("the graph did not settle")


@pytest.fixture
def card(tmp_path):
    job, recs = example("nv-fixture-card"), records()
    s = new_store(tmp_path, job)
    settle(job, recs, s, plain_ctx())
    return job, s


def adopted_request(job):
    return request(voice={"mode": "from_run", "runs": {seg["id"]: RUN for seg in job["segments"]}})


ENV = {"VIDEO_UTILS_COMMIT": COMMIT}


def test_the_result_names_every_output_by_digest_and_returns_deliver_check(card):
    job, s = card
    value = render_stage.result(adopted_request(job), s, ENV)
    assert value["kind"] == "narrate_render_stage_result"
    assert value["outputs"]["video_sha256"] == s.manifest("compose")["outputs"]["video.mp4"]
    assert (
        value["outputs"]["deliver_check"]["report_sha256"]
        == s.manifest("deliver_check")["outputs"]["deliver_check.json"]
    )
    assert value["outputs"]["stages"] == {n: r["content_sha256"] for n, r in s.current()["stages"].items()}
    assert value["deliver_check"]["machine_passed"] is True
    assert "listening" in value["deliver_check"]["pending_operator"]
    assert value["job_sha256"] == keys.digest(job)
    text = json.dumps(value)
    assert str(s.dir) not in text and str(s.dir.parent) not in text
    # the only slashes are the stage[/segment] node ids that key outputs.stages
    assert all("/" not in n or n.split("/")[0] in graph.BY_ID for n in value["outputs"]["stages"])
    assert "/" not in json.dumps({k: v for k, v in value.items() if k != "outputs"})


def test_the_result_refuses_another_commit_job_or_voice(card):
    job, s = card
    value = adopted_request(job)
    assert refused(render_stage.result, value, s, {}) == "commit_unknown"
    assert refused(render_stage.result, value, s, {"VIDEO_UTILS_COMMIT": "d" * 40}) == "commit_mismatch"
    other = copy.deepcopy(value)
    other["voice"]["runs"] = {seg["id"]: "e" * 64 for seg in job["segments"]}
    assert refused(render_stage.result, other, s, ENV) == "voice_run_mismatch"
    assert refused(render_stage.result, request(job_id="nv-other"), s, ENV) == "job_mismatch"


def test_a_job_edit_after_deliver_check_refuses_the_result(card):
    job, s = card
    edited = copy.deepcopy(job)
    edited["labels"]["persona"] = "someone else"
    s.write_job(edited, replace=True)
    assert refused(render_stage.result, adopted_request(job), s, ENV) == "deliver_check_stale"


def test_export_writes_by_sha256_and_is_idempotent(card, tmp_path):
    job, s = card
    value = render_stage.result(adopted_request(job), s, ENV)
    out = tmp_path / "out"
    out.mkdir()
    first = render_stage.export(s, value, out)
    assert first["video"] == value["outputs"]["video_sha256"] + ".mp4"
    for name in first.values():
        assert render_stage.sha256_file(out / name) == name.split(".")[0]
    assert render_stage.export(s, value, out) == first
    (out / first["video"]).write_bytes(b"tampered")
    assert refused(render_stage.export, s, value, out) == "export_conflict"


def test_the_cli_checks_and_reports(card, tmp_path, capsys, monkeypatch):
    job, s = card
    path = tmp_path / "request.json"
    path.write_text(json.dumps(adopted_request(job)))
    assert cli.main(["render-stage", "check", "--request", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    monkeypatch.setenv("VIDEO_UTILS_COMMIT", COMMIT)
    root = str(s.dir.parent)
    assert cli.main(["render-stage", "result", job["id"], "--request", str(path), "--root", root]) == 0
    assert json.loads(capsys.readouterr().out)["outputs"]["video_sha256"]
    path.write_text(json.dumps(request(run_id="a b")))
    assert cli.main(["render-stage", "check", "--request", str(path)]) == 1
    assert json.loads(capsys.readouterr().err)["refused"] == "token_invalid"
