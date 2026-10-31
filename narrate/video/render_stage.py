"""The render stage of a Cade demo DAG as one task body (docs/spec/RENDER_STAGE.md, Linear TIN-7788, demo DAG P9).

A Hatchet task on the Cade `render` worker hands this module a request that holds ids and digests only: the run,
the packet, the job, every input by sha256, how the voice is made and, for a GPU window, the Lease holder and its
TIN-5397 notice. The module never takes, reads or writes the GPU Lease. The estate lease helper does that, and the
GPU window runs outside this process (docs/spec/RENDER_STAGE.md, "Lease protocol").

    check REQUEST [--inputs DIR | --gpu-draft]
                                   validate the request and print its phase plan. With --inputs (verify_inputs, on
                                   the worker) also check the worker's commit and re-hash every input under
                                   DIR/<sha256>. --gpu-draft plans a gpu_window request, which v1 otherwise refuses;
                                   it never goes with --inputs. Writes nothing.
    result JOB --request REQUEST [--export DIR]
                                   the result of a job that ran to deliver_check: every output by digest and the
                                   deliver_check gates, after binding the request's inputs to the job's intake
                                   (JOB/intake/intake.json). With --export, copy the composed video and the
                                   deliver_check report into DIR under their sha256 names, then the result itself.

A request or a result holds no path, host, address or prose: every string is a single token, a digest or a fixed
word, so neither can carry a store path or a private term into a Hatchet payload or a log.
"""

import hashlib
import json
import os
import re
import shutil
from pathlib import Path

from ..ir import sha256_file
from . import accept, keys
from .job import ID, SHA256, JobError, check_shape
from .store import StoreError, verify_stage_dir
from .store import tree_sha256 as store_tree_sha256

REQUEST_KIND = "narrate_render_stage_request"
RESULT_KIND = "narrate_render_stage_result"
SCHEMA_VERSION = 1
WORKFLOW = "cade-hardware-handoff"
COMMIT_ENV = "VIDEO_UTILS_COMMIT"
TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
IMAGE = re.compile(r"^sha256:[0-9a-f]{64}$")
UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
# The one narrate holder form the GPU Lease guard admits (narrate/serve/finalize.py HOLDER; a test keeps them equal).
HOLDER = re.compile(r"^narrate-bench-[0-9]{8}-s[0-9]{6}$")
LEASE_NAME = "gpu-lease"  # the one GPU Lease; its cluster name stays outside this public repository
NOTICE_TICKET = "TIN-5397"
WINDOW_MAX_S = 1800  # docs/spec/NARRATE.md, "GPU use": attended or unattended windows of 30 minutes or less
EDITIONS_V1 = ("Internal",)  # T1 renders Internal demos only; a client edition needs its own tenant (T4)
UNTIL = ("deliver_check",)
VOICE_MODES = ("gpu_window", "from_run")
# inputs: name -> (required, how DIR/<sha256> is checked). "file" re-hashes a file, "tree" a directory's tree
# digest, "manifest" a bundle directory's manifest.json (intake then checks every asset against that manifest).
INPUTS = {
    "bundle_manifest_sha256": (True, "manifest"),
    "records_sha256": (True, "tree"),
    "engine_record_sha256": (True, "file"),
    "lexical_release_sha256": (True, "tree"),
    "kitpip_sha256": (False, "file"),
    "denylist_sha256": (False, "file"),
}
REQUEST_KEYS = {
    "kind",
    "schema_version",
    "workflow",
    "run_id",
    "packet_id",
    "job_id",
    "edition",
    "video_utils_commit",
    "worker_image",
    "inputs",
    "voice",
    "lease",
    "until",
}
LEASE_KEYS = {"lease", "holder", "max_seconds", "helper_sha256", "notice"}
# How far this module checks the Lease binding: form_only. It checks the shape of the notice comment id and of the
# helper digest. It never reads Linear or hashes a helper; Cade's voice_gpu does both before the window starts.
LEASE_RESOLUTION = "form_only"
LEASE_VERIFIED_BY_VOICE_GPU = ("notice_comment_on_ticket_names_holder", "helper_hashes_to_helper_sha256")
# The intake phase writes its --out here, under the job's store directory, and init --from reads it.
INTAKE_DIR = "intake"
INTAKE_KIND = "nv_bundle_intake"
# How each input reaches the job after verify_inputs re-hashed its mount. intake: intake.json records the digest it
# read. records_pin: the bound records pin the release file by file, and the script stage re-hashes those files.
# mount_only: only verify_inputs checked it; no later phase records reading it.
BOUND_BY = {
    "bundle_manifest_sha256": "intake",
    "records_sha256": "intake",
    "denylist_sha256": "intake",
    "lexical_release_sha256": "records_pin",
    "engine_record_sha256": "mount_only",
    "kitpip_sha256": "mount_only",
}


class RenderStageError(JobError):
    """A request, an input or a finished job the render stage refuses."""


def canonical_sha256(value):
    return keys.digest(value)


def tree_sha256(directory):
    """store.tree_sha256 with the render stage's codes: a symlink refuses input_symlink, and a FIFO, socket or device
    refuses input_irregular before any file is read."""
    try:
        return store_tree_sha256(directory)
    except StoreError as exc:
        code = "input_irregular" if exc.code == "tree_irregular" else "input_symlink"
        raise RenderStageError(code, exc.detail) from exc


def _sha(value):
    return isinstance(value, str) and SHA256.fullmatch(value) is not None


def _refuse(code, detail):
    raise RenderStageError(code, detail)


def check_request(request, gpu_draft=False):
    """The request, checked. Refuses the first problem with a typed code; returns the request unchanged. A
    gpu_window request refuses gpu_window_not_v1 unless gpu_draft (check --gpu-draft) asks for its plan only."""
    if not isinstance(request, dict):
        _refuse("request_invalid", "the request is not a JSON object")
    extra, missing = sorted(set(request) - REQUEST_KEYS), sorted(REQUEST_KEYS - set(request))
    if extra or missing:
        _refuse("request_keys", f"unknown keys {extra}, missing keys {missing}")
    if request["kind"] != REQUEST_KIND or request["schema_version"] != SCHEMA_VERSION:
        _refuse("request_kind", f"kind must be {REQUEST_KIND} at schema_version {SCHEMA_VERSION}")
    if request["workflow"] != WORKFLOW:
        _refuse("workflow_mismatch", f"the render stage serves {WORKFLOW} only")
    for name in ("run_id", "packet_id"):
        if not isinstance(request[name], str) or not TOKEN.fullmatch(request[name]):
            _refuse("token_invalid", f"{name} must be one token")
    if not isinstance(request["job_id"], str) or not ID.fullmatch(request["job_id"]):
        _refuse("token_invalid", "job_id must be a job id")
    if request["edition"] not in EDITIONS_V1:
        _refuse("edition_not_v1", f"v1 renders {', '.join(EDITIONS_V1)} only; a client edition needs its own tenant")
    if not isinstance(request["video_utils_commit"], str) or not COMMIT.fullmatch(request["video_utils_commit"]):
        _refuse("commit_invalid", "video_utils_commit must be a 40-hex commit")
    if not isinstance(request["worker_image"], str) or not IMAGE.fullmatch(request["worker_image"]):
        _refuse("image_invalid", "worker_image must be an OCI digest, sha256:<64 hex>")
    if request["until"] not in UNTIL:
        _refuse("until_invalid", f"the render stage stops at {', '.join(UNTIL)}; delivery is deliver_internal's")
    check_inputs(request["inputs"])
    check_voice(request["voice"], request["lease"])
    if request["voice"]["mode"] == "gpu_window" and not gpu_draft:
        _refuse(
            "gpu_window_not_v1",
            "v1 runs no GPU window: no TIN-5397 notice poster exists yet (R3) and no lease or batch receipt binds a"
            " voice; use from_run, or check --gpu-draft for the plan only",
        )
    return request


def check_inputs(inputs):
    if not isinstance(inputs, dict):
        _refuse("inputs_invalid", "inputs is not an object")
    extra = sorted(set(inputs) - set(INPUTS))
    if extra:
        _refuse("inputs_keys", f"unknown inputs {extra}")
    for name, (required, _) in INPUTS.items():
        value = inputs.get(name)
        if value is None and not required:
            continue
        if not _sha(value):
            _refuse("digest_invalid", f"inputs.{name} must be a sha256")


def check_voice(voice, lease):
    if not isinstance(voice, dict) or set(voice) != {"mode", "runs"}:
        _refuse("voice_invalid", "voice is {mode, runs}")
    if voice["mode"] not in VOICE_MODES:
        _refuse("voice_invalid", f"voice.mode is one of {', '.join(VOICE_MODES)}")
    runs = voice["runs"]
    if voice["mode"] == "from_run":
        if lease is not None:
            _refuse("lease_unneeded", "an adopted voice runs no GPU window, so the request names no Lease")
        if not isinstance(runs, dict) or not runs:
            _refuse("voice_runs_missing", "from_run names each segment's narrate run by content_sha256")
        for segment, digest in runs.items():
            if not isinstance(segment, str) or not ID.fullmatch(segment) or not _sha(digest):
                _refuse("voice_runs_invalid", "voice.runs maps a segment id to a narrate run content_sha256")
        return
    if runs is not None:
        _refuse("voice_runs_unexpected", "a GPU window renders the runs, so voice.runs is null")
    check_lease(lease)


def check_lease(lease):
    """The Lease binding's form (LEASE_RESOLUTION): the guard's holder form, the window cap, a sha256-shaped helper
    pin and a UUID-shaped notice comment id on TIN-5397. It does not prove the comment exists or names the holder,
    or that a helper hashes to the pin."""
    if not isinstance(lease, dict) or set(lease) != LEASE_KEYS:
        _refuse("lease_missing", f"a GPU window needs lease with {sorted(LEASE_KEYS)}")
    if lease["lease"] != LEASE_NAME:
        _refuse("lease_invalid", f"the one GPU Lease is {LEASE_NAME}")
    if not isinstance(lease["holder"], str) or not HOLDER.fullmatch(lease["holder"]):
        _refuse("lease_holder_form", "the holder must be narrate-bench-YYYYMMDD-sHHMMSS (just narrate-holder)")
    seconds = lease["max_seconds"]
    if isinstance(seconds, bool) or not isinstance(seconds, int) or not 0 < seconds <= WINDOW_MAX_S:
        _refuse("lease_window", f"max_seconds must be 1 to {WINDOW_MAX_S}")
    if not _sha(lease["helper_sha256"]):
        _refuse("lease_helper_unpinned", "helper_sha256 pins the lease helper the window runs under")
    notice = lease["notice"]
    if not isinstance(notice, dict) or set(notice) != {"ticket", "comment_id"}:
        _refuse("lease_notice_missing", f"the window needs its {NOTICE_TICKET} notice: {{ticket, comment_id}}")
    if (
        notice["ticket"] != NOTICE_TICKET
        or not isinstance(notice["comment_id"], str)
        or not UUID.fullmatch(notice["comment_id"])
    ):
        _refuse("lease_notice_missing", f"notice.ticket is {NOTICE_TICKET} and comment_id the posted comment's id")


def check_commit(request, env=None):
    """The worker's own video-utils commit must be the request's: the image bakes it into VIDEO_UTILS_COMMIT."""
    env = os.environ if env is None else env
    have = env.get(COMMIT_ENV)
    if not have:
        _refuse("commit_unknown", f"the worker does not know its video-utils commit ({COMMIT_ENV} is unset)")
    if have != request["video_utils_commit"]:
        _refuse("commit_mismatch", "the worker runs another video-utils commit than the request pins")


def check_input_dir(inputs, root):
    """Re-hash every named input at root/<sha256>. Returns {name: kind}. Refuses a missing or mismatched input."""
    root, seen = Path(root), {}
    for name, (_, how) in INPUTS.items():
        digest = inputs.get(name)
        if digest is None:
            continue
        path = root / digest
        if path.is_symlink():
            _refuse("input_symlink", f"inputs.{name} is a symlink")
        if how == "file":
            if not path.is_file():
                _refuse("input_missing", f"inputs.{name} is not a file under the inputs root")
            got = sha256_file(path)
        elif how == "manifest":
            manifest = path / "manifest.json"
            if not path.is_dir() or manifest.is_symlink() or not manifest.is_file():
                _refuse("input_missing", f"inputs.{name} is not a bundle directory with manifest.json")
            got = sha256_file(manifest)
        else:
            if not path.is_dir():
                _refuse("input_missing", f"inputs.{name} is not a directory under the inputs root")
            got = tree_sha256(path)
        if got != digest:
            _refuse("input_digest_mismatch", f"inputs.{name} does not hash to its name")
        seen[name] = how
    return seen


def phases(request):
    """The ordered phases of one render stage. Only voice_gpu holds the Lease, and it runs under the lease helper."""
    gpu = request["voice"]["mode"] == "gpu_window"
    rows = [
        {"id": "verify_inputs", "gpu": False, "runs": "render-stage check --inputs"},
        {"id": "intake", "gpu": False, "runs": "narrate video intake --out JOB/intake, then init --from"},
    ]
    if gpu:
        lease = request["lease"]
        rows += [
            {"id": "voice_plan", "gpu": False, "runs": "narrate plan"},
            {
                "id": "voice_gpu",
                "gpu": True,
                "runs": "lease helper run -- audiocpp_batch.py run",
                "lease": {
                    "lease": lease["lease"],
                    "holder": lease["holder"],
                    "max_seconds": lease["max_seconds"],
                    "resolution": LEASE_RESOLUTION,
                    "verify_before_run": list(LEASE_VERIFIED_BY_VOICE_GPU),
                },
            },
            {"id": "voice_render", "gpu": False, "runs": "narrate render --prerendered"},
        ]
    rows += [
        {"id": "voice_adopt", "gpu": False, "runs": "narrate video stage JOB voice --from-run"},
        {"id": "compose", "gpu": False, "runs": "narrate video run JOB --until deliver_check"},
        {"id": "collect", "gpu": False, "runs": "render-stage result"},
    ]
    return rows


def plan(request, gpu_draft=False):
    check_request(request, gpu_draft)
    gpu = request["voice"]["mode"] == "gpu_window"
    return {
        "ok": True,
        "kind": "narrate_render_stage_plan",
        "request_sha256": canonical_sha256(request),
        "run_id": request["run_id"],
        "job_id": request["job_id"],
        "gpu": gpu,
        "draft": gpu,
        "phases": phases(request),
    }


def check_worker(request, root, env=None):
    """verify_inputs on the worker: the request, the worker's commit, then every mounted input. Refuses before any
    phase writes or takes the Lease. Returns the plan with inputs_checked."""
    out = plan(request)
    check_commit(request, env)
    out["inputs_checked"] = check_input_dir(request["inputs"], root)
    return out


def _obj(value):
    return value if isinstance(value, dict) else {}


def _intake_file(directory, name):
    path = directory / name
    if path.is_symlink() or not path.is_file():
        _refuse("intake_missing", f"the job's intake holds no {name}; run intake with --out JOB/{INTAKE_DIR}")
    return path


def _intake_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RenderStageError("intake_invalid", f"{path.name} is not JSON") from exc


def intake_binding(request, store, job):
    """The sha256 of the job's intake.json, after binding the request to it. The intake at JOB/intake must have
    written the store's job.json and read the request's bundle manifest, records tree and denylist; any other
    intake refuses input_binding_mismatch."""
    directory = store.dir / INTAKE_DIR
    if directory.is_symlink():
        _refuse("intake_missing", f"JOB/{INTAKE_DIR} is a symlink")
    manifest_path = _intake_file(directory, "intake.json")
    record_path = _intake_file(directory, "narrated-video.json")
    intake = _intake_json(manifest_path)
    if not isinstance(intake, dict) or intake.get("kind") != INTAKE_KIND:
        _refuse("intake_invalid", f"intake.json is not {INTAKE_KIND}")
    if sha256_file(record_path) != _obj(intake.get("outputs")).get("narrated-video.json"):
        _refuse("input_binding_mismatch", "narrated-video.json does not hash to the digest intake.json holds")
    try:
        written = check_shape(_intake_json(record_path))
    except JobError as exc:
        raise RenderStageError("input_binding_mismatch", "the intake's narrated-video.json is not a job") from exc
    if written != job:
        _refuse("input_binding_mismatch", "the store's job.json is not the record this intake wrote")
    if intake.get("job_id") != request["job_id"] or intake.get("edition") != request["edition"]:
        _refuse("input_binding_mismatch", "the intake wrote another job id or edition than the request names")
    read = {
        "bundle_manifest_sha256": _obj(intake.get("bundle")).get("manifest_sha256"),
        "records_sha256": _obj(intake.get("inputs")).get("records_sha256"),
        "denylist_sha256": _obj(intake.get("private_terms")).get("denylist_sha256"),
    }
    for name, digest in read.items():
        if digest != request["inputs"].get(name):
            _refuse("input_binding_mismatch", f"the intake read another {name} than the request names")
    return sha256_file(manifest_path)


def machine_gates(gates, delivery_gate):
    """True when every machine gate (accept.AUTOMATED) passed or does not apply. A gate table missing one, or a
    delivery_gate whose machine_gates_passed disagrees, refuses deliver_check_invalid."""
    missing = [g for g in accept.AUTOMATED if g not in gates]
    if missing:
        _refuse("deliver_check_invalid", f"deliver_check holds no {', '.join(missing)} gate")
    passed = all(gates[g] in ("passed", "not_applicable") for g in accept.AUTOMATED)
    recorded = delivery_gate.get("machine_gates_passed") if isinstance(delivery_gate, dict) else None
    if recorded is not passed:
        _refuse("deliver_check_invalid", "delivery_gate.machine_gates_passed is missing or disagrees with the gates")
    return passed


def voice_runs(store, job):
    """{segment: narrate content_sha256} of every current voice node."""
    out = {}
    for segment in job["segments"]:
        manifest = store.manifest(f"voice/{segment['id']}")
        digest = ((manifest or {}).get("measurements") or {}).get("narrate_content_sha256")
        if not _sha(digest):
            _refuse("voice_missing", f"voice/{segment['id']} has no current narrate run")
        out[segment["id"]] = digest
    return out


def result(request, store, env=None):
    """The render stage's result for a job that ran to deliver_check. Refuses a stale or partial render."""
    check_request(request)
    check_commit(request, env)
    if store.job_id != request["job_id"]:
        _refuse("job_mismatch", "the store holds another job than the request names")
    job = store.read_job()
    if job.get("edition") != request["edition"]:
        _refuse("edition_mismatch", "the job's edition is not the request's")
    render, gates = accept.render_of(store, job)
    intake_sha256 = intake_binding(request, store, job)
    manifest = store.manifest("deliver_check")
    report = (manifest.get("outputs") or {}).get("deliver_check.json")
    if not _sha(report):
        _refuse("deliver_check_report_missing", "the deliver_check node holds no deliver_check.json")
    runs = voice_runs(store, job)
    if request["voice"]["mode"] == "from_run" and runs != request["voice"]["runs"]:
        _refuse("voice_run_mismatch", "the job's voice nodes hold other narrate runs than the request adopts")
    stages = {}
    for node_id, row in sorted(store.current()["stages"].items()):
        if verify_stage_dir(store.dir / row["dir"], row["key"]):
            _refuse("stage_corrupt", f"{node_id} fails re-hashing")
        stages[node_id] = row["content_sha256"]
    measurements = manifest.get("measurements") or {}
    machine_passed = machine_gates(gates, measurements.get("delivery_gate"))
    return {
        "kind": RESULT_KIND,
        "schema_version": SCHEMA_VERSION,
        "workflow": request["workflow"],
        "run_id": request["run_id"],
        "packet_id": request["packet_id"],
        "job_id": request["job_id"],
        "request_sha256": canonical_sha256(request),
        "video_utils_commit": request["video_utils_commit"],
        "worker_image": request["worker_image"],
        "job_sha256": keys.digest(job),
        "intake_sha256": intake_sha256,
        "inputs_bound_by": {name: BOUND_BY[name] for name in INPUTS if request["inputs"].get(name) is not None},
        "voice": {"mode": request["voice"]["mode"], "runs": runs},
        # v1 results are from_run only (check_request), so no Lease attests this voice. A gpu_window result would
        # need the helper's run receipt and the batch receipt by digest.
        "lease": None,
        "outputs": {
            "video_sha256": render["video_sha256"],
            "deliver_check": render["deliver_check"] | {"report_sha256": report},
            "stages": stages,
        },
        "deliver_check": {
            "gates": gates,
            "delivery_gate": measurements.get("delivery_gate"),
            "machine_passed": machine_passed,
            "pending_operator": sorted(g for g, v in gates.items() if v == "pending_operator"),
        },
    }


def _place(source, directory, digest, suffix):
    """Copy source into directory/<digest><suffix> unless it is there already; re-hash the copy."""
    target = directory / f"{digest}{suffix}"
    if target.is_symlink():
        _refuse("export_symlink", f"{target.name} is a symlink")
    if target.exists():
        if sha256_file(target) != digest:
            _refuse("export_conflict", f"{target.name} exists with other content")
        return target.name
    tmp = directory / f".{target.name}.partial"
    shutil.copyfile(source, tmp)
    if sha256_file(tmp) != digest:
        tmp.unlink()
        _refuse("export_digest_mismatch", f"the copy of {target.name} does not hash to its name")
    os.replace(tmp, target)
    return target.name


def export(store, value, directory):
    """Write the composed video, the deliver_check report and the result itself into directory by sha256.
    Returns {video, report, result}: file names only."""
    directory = Path(directory)
    if directory.is_symlink() or not directory.is_dir():
        _refuse("export_dir", "--export names an existing directory")
    compose = store.entry("compose")
    deliver = store.entry("deliver_check")
    names = {
        "video": _place(store.dir / compose["dir"] / "video.mp4", directory, value["outputs"]["video_sha256"], ".mp4"),
        "report": _place(
            store.dir / deliver["dir"] / "deliver_check.json",
            directory,
            value["outputs"]["deliver_check"]["report_sha256"],
            ".json",
        ),
    }
    body = (json.dumps(value, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    digest = hashlib.sha256(body).hexdigest()
    target = directory / f"{digest}.json"
    if target.is_symlink():
        _refuse("export_symlink", f"{target.name} is a symlink")
    if target.exists():
        if sha256_file(target) != digest:
            _refuse("export_conflict", f"{target.name} exists with other content")
    else:
        tmp = directory / f".{digest}.json.partial"
        tmp.write_bytes(body)
        os.replace(tmp, target)
    names["result"] = target.name
    return names
