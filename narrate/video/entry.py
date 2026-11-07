"""The entry gates of a narrated-video job as a DAG runs them, before any spend (docs/spec/NARRATED_VIDEO.md, "Entry
gates", Linear TIN-7788, ruling TIN-7125 0690fe88).

Cade's task bodies hand this module a job id and nothing else, so a path never crosses Hatchet. The bundle a job comes
from is BUNDLES/<job>/ and its intake knobs BUNDLES/<job>.entry.json, under --bundles or NARRATED_VIDEO_BUNDLES. A job
with no knobs file has no bundle, as a client or card job has none, and claims and intake print entry none and write
nothing. A client edition with a knobs file refuses, because intake writes an Internal job and would replace it.

    claims JOB    the private-terms guard, the spoken-number gate and each number against its claim's source
    intake JOB    the same gates and every asset, then the job, its records and init on the job's own root
    preflight JOB the frame gates on the pictures the job will show, recorded where render-stage result reads them
    lexical JOB   every lexical Error of the job, and a refusal when the tool cannot run

A gate stops on its first code with exit 1, as every gate here does, and it records every finding for `findings` to read
and a machine round to start from. claims and intake record theirs in JOB/entry.json, because a refused bundle may leave
no job.json on the root. That file holds rows and digests only. While it holds a refusal, findings and round read the
bundle's tree digest in place of the job's, so a fix that changes the bundle starts the next round and a fix that
changes nothing reads the same round again. A passing claims or intake clears it.

The gates are read-only on stages: no stage key moves. A root with an entry report reads its own JOB/intake/records,
which hold each beat's narrate job, and the records the worker names are that intake's input (cli.records_dir).

Findings stay advisory in a person's `plan`, `run` and `narrate-lexical-check` (R-N12). These commands are the DAG's.
"""

import json
from pathlib import Path

from ..ir import sha256_file
from ..lexical import LexicalError
from . import bundle, graph, keys, render_stage, speech
from . import findings as typed
from .job import CLIENT_EDITIONS, ID, JobError, check_shape, load_records
from .store import StoreError, tree_sha256, write_atomic

KIND = "nv_entry"
SCHEMA_VERSION = 1
BUNDLES_ENV = "NARRATED_VIDEO_BUNDLES"
KNOBS_KIND = "nv_entry_knobs"
KNOB_FIELDS = {"kind", "schema_version", "narrate_template", "voice", "engine", "persona", "tail_s"}
KNOB_IDS = ("narrate_template", "voice", "engine")
LEXICAL_KIND = "nv_lexical_gate"


def refuse(code, detail):
    raise JobError(code, detail)


def bundle_of(store, bundles):
    """(bundle directory, knobs) of this job, or None when no knobs file names one. Refuses entry_client_job on a client
    edition that has one, and entry_invalid on a knobs file or a directory of another shape."""
    if not bundles:
        return None
    path = Path(bundles) / f"{store.job_id}.entry.json"
    if not path.is_file() or path.is_symlink():
        return None
    if store.exists() and store.read_job()["edition"] in CLIENT_EDITIONS:
        refuse("entry_client_job", "a client edition keeps its own job; intake would replace it with an Internal one")
    try:
        knobs = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        refuse("entry_invalid", "the knobs file is not JSON")
    if (
        not isinstance(knobs, dict)
        or set(knobs) != KNOB_FIELDS
        or knobs["kind"] != KNOBS_KIND
        or knobs["schema_version"] != SCHEMA_VERSION
        or not all(isinstance(knobs[k], str) and ID.fullmatch(knobs[k]) for k in KNOB_IDS)
        or not (knobs["persona"] is None or (isinstance(knobs["persona"], str) and ID.fullmatch(knobs["persona"])))
        or not (knobs["tail_s"] is None or (type(knobs["tail_s"]) in (int, float) and 0 <= knobs["tail_s"] <= 60))
    ):
        refuse("entry_invalid", f"the knobs file is not {KNOBS_KIND} version {SCHEMA_VERSION}")
    directory = Path(bundles) / store.job_id
    if directory.is_symlink() or not directory.is_dir():
        refuse("entry_invalid", "the knobs file names a job with no bundle directory")
    return directory, knobs


def bundle_digest(directory):
    try:
        return tree_sha256(directory)
    except StoreError as exc:
        raise JobError("entry_invalid", "the bundle holds a file the tree digest refuses") from exc


def record(store, digest, phase, rows):
    """What this phase read, in JOB/entry.json. It writes the directory, because a refused bundle may be the root's
    first write."""
    store.dir.mkdir(parents=True, exist_ok=True)
    report = typed.report(rows)
    write_atomic(
        store.entry_file,
        {
            "kind": KIND,
            "schema_version": SCHEMA_VERSION,
            "job_id": store.job_id,
            "phase": phase,
            "bundle_sha256": digest,
            "ok": not rows,
            "findings": report,
        },
    )
    return report


def none(store):
    return {"ok": True, "job_id": store.job_id, "entry": "none"}


def claims(store, bundles, denylist=None, pin=None):
    """The claims phase. Numbers must agree with their sources, and one with no source refuses claim_value_unread."""
    found = bundle_of(store, bundles)
    if found is None:
        return none(store)
    directory, _ = found
    digest = bundle_digest(directory)
    try:
        result = bundle.claims_only(directory, denylist, pin, require_values=True)
    except bundle.BundleError as exc:
        record(store, digest, "claims", exc.findings)
        raise
    refused = bundle.gate_refusal(result["segments"])
    report = record(store, digest, "claims", [] if refused is None else refused.findings)
    if refused is not None:
        raise refused
    return {"ok": True, "job_id": store.job_id, "entry": "claims", "bundle_sha256": digest, "findings": report}


def intake(store, bundles, records_dir, source_store, ctx, denylist=None, pin=None):
    """The intake phase: bundle.intake into JOB/intake, replacing an earlier one only once this one passed, then init on
    this root. ctx is the planner's context."""
    found = bundle_of(store, bundles)
    if found is None:
        return none(store)
    directory, knobs = found
    if not records_dir:
        refuse("records_missing", "intake reads the worker's records: pass --records or set NARRATED_VIDEO_RECORDS")
    if not source_store:
        refuse("store_missing", "intake writes the private store: pass --store or set NARRATE_STORE")
    digest = bundle_digest(directory)
    out = store.dir / render_stage.INTAKE_DIR
    store.dir.mkdir(parents=True, exist_ok=True)
    try:
        manifest = bundle.intake(
            directory,
            out,
            records_dir,
            job_id=store.job_id,
            template=knobs["narrate_template"],
            voice=knobs["voice"],
            engine=knobs["engine"],
            persona=knobs["persona"],
            tail_s=knobs["tail_s"],
            store=source_store,
            denylist=denylist,
            pin=pin,
            replace=bundle.earlier_intake(out),
            require_values=True,
        )
    except bundle.BundleError as exc:
        record(store, digest, "intake", exc.findings)
        raise
    job = check_shape(json.loads((out / "narrated-video.json").read_text(encoding="utf-8")))
    records = load_records(out / "records")
    planned = graph.plan(job, records, None, ctx)
    if planned["admit"]["verdict"] != "Admitted":
        first = planned["admit"]["refusals"][0]
        rows = [typed.finding(row["code"], gate=typed.INTAKE) for row in planned["admit"]["refusals"]]
        record(store, digest, "intake", rows)
        refuse(first["code"], first["detail"])
    store.write_job(job, replace=True)
    store.write_graph(graph.public(graph.plan(job, records, store, ctx)))
    record(store, digest, "intake", [])
    return {
        "ok": True,
        "job_id": store.job_id,
        "entry": "intake",
        "bundle_sha256": digest,
        "job_sha256": manifest["job_sha256"],
    }


def preflight(store, media):
    """The preflight phase, on the job this root holds. With an intake it also binds that intake and its claims state,
    so the render stage's result reads the same report."""
    job = store.read_job()
    path = store.dir / render_stage.INTAKE_DIR / "intake.json"
    intake_report = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    digest = sha256_file(path) if intake_report is not None else None
    report = render_stage.recorded_preflight(store, job, media, intake_report, digest)
    return {
        "ok": True,
        "job_id": store.job_id,
        "entry": "preflight",
        "job_sha256": report["job_sha256"],
        "preflight_sha256": report["preflight_sha256"],
    }


def lexical(store, rc, planned):
    """The lexical gate, after the script stage of this same job. Every script node must be fresh, or the findings it
    left say nothing of this job. Refuses lexical_unread then, lexical_tool_absent or lexical_tool_fault when the tool
    cannot run, and lexical_error with every finding recorded."""
    job_sha256 = keys.digest(rc.job)
    stale = [n["id"] for n in planned["nodes"] if n["id"].split("/")[0] == "script" and n["state"] != "fresh"]
    if stale:
        refuse("lexical_unread", f"{len(stale)} script nodes are not fresh for this job")
    try:
        rows = speech.lexical_gate(rc)
    except LexicalError as exc:
        raise JobError(exc.code, exc.detail) from None
    report = typed.report(rows)
    write_atomic(
        store.dir / render_stage.LEXICAL_GATE_FILE,
        {
            "kind": LEXICAL_KIND,
            "schema_version": SCHEMA_VERSION,
            "job_id": store.job_id,
            "job_sha256": job_sha256,
            "ok": not rows,
            "findings": report,
        },
    )
    if rows:
        refuse("lexical_error", f"{len(rows)} lexical Error findings; findings names each by rule")
    return {"ok": True, "job_id": store.job_id, "entry": "lexical", "job_sha256": job_sha256}
