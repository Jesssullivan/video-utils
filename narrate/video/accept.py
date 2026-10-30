"""The operator's acceptance of a delivered cut: `accept JOB --gate G --decision ID` (docs/spec/NARRATED_VIDEO.md,
"Operator acceptance", Linear TIN-7788).

deliver_check leaves listening and lip sync pending_operator, and nothing in the graph closes them. accept is the
one write path that does. It records the operator's decision against the gate of the current deliver_check render,
and only when the decision is a Softproxy decision id (`sp:dec:<ulid>`, softproxy docs/spec/SOFTPROXY.md section 5.1:
the 26-character Crockford base32 ULID). Free text ("GO", "yes", "lgtm"), an empty value, a proposal id or any other
malformed id refuses. accept checks the id's form only: that Softproxy holds an Operator accept under that id is the
caller's check (Cade's decision poll), and the id is the receipt a reader resolves.

Gates:

- listening and lip_sync close by acceptance, each where the current deliver_check reports it pending_operator;
- vrm_badge_decision refuses vrm_badge_undecided until a ruling settles the badge (SPR-128, narrate/video/vrm.py);
- the machine gates (profile, loudness, flash, captions) never close here: gate_automated;
- bed_licence_pdf and bed_content_id close only through the private MusicBed record: gate_record_bound;
- any other name refuses gate_unknown.

One acceptance binds one render: the deliver_check stage key and content digest, the composed video's sha256 and the
job's digest. A new render (a new deliver_check) plans every operator gate open again until it has its own decision.
The record is acceptance.json in the job directory, beside job.json, and append-only. job.json stays the NarratedVideo
record as rendered, so no stage key or private-terms binding moves. The same gate and decision for the same render is
a no-op (exit 0, recorded false). One decision may close several gates of one render (a GO closes listening and lip
sync, SPR-258), never a second render, and a gate holds one decision per render. The recorded graph.json (plan
--record, run, status) lists the acceptances that bind its deliver_check and drops their gates from pending_operator.
"""

import fcntl
import os
import re
from contextlib import contextmanager

from . import keys
from .job import SHA256, JobError
from .store import load_store_json, utc_now, verify_stage_dir, write_atomic

ACCEPTANCE = "acceptance.json"
KIND = "nv_acceptance"
SCHEMA_VERSION = 1
# sp:dec:<ulid>: 10 time characters (48 bits, so the first is 0 to 7) and 16 random ones, Crockford base32 upper case
# (no I, L, O or U). softproxy src/lib/prompt/ids.ts writes exactly this form.
DECISION = re.compile(r"sp:dec:[0-7][0-9A-HJKMNP-TV-Z]{25}")
DECISION_PREFIX = "sp:dec:"
ACCEPTABLE = ("listening", "lip_sync")
UNRULED = {"vrm_badge_decision": "whether offline VRM video carries a burned-in badge is not ruled (SPR-128)"}
AUTOMATED = ("profile", "loudness", "flash", "captions")
RECORD_BOUND = ("bed_licence_pdf", "bed_content_id")
GATES = ACCEPTABLE + tuple(UNRULED) + AUTOMATED + RECORD_BOUND
# admit's pending_operator gate names (narrate/video/admit.py) and the deliver_check gate each one waits on
ADMIT_GATES = {
    "listening_acceptance": "listening",
    "lip_sync_acceptance": "lip_sync",
    "vrm_badge_decision": "vrm_badge_decision",
}


def check_decision(value):
    """The Softproxy decision id, or JobError: decision_missing for an empty value, decision_free_text for anything
    that is not an sp:dec id at all, decision_invalid for a malformed one. A refusal never echoes the value."""
    if not isinstance(value, str) or not value.strip():
        raise JobError("decision_missing", "--decision needs a Softproxy decision id (sp:dec:<ulid>)")
    if not value.startswith(DECISION_PREFIX):
        raise JobError(
            "decision_free_text",
            "--decision takes only a Softproxy decision id (sp:dec:<ulid>): a reply, a GO line or another record's id "
            "is not a decision",
        )
    if not DECISION.fullmatch(value):
        raise JobError(
            "decision_invalid",
            "a Softproxy decision id is sp:dec: and a 26-character upper-case Crockford base32 ULID",
        )
    return value


def check_gate(gate):
    """The gate, or JobError when accept may not close it."""
    if gate in ACCEPTABLE:
        return gate
    if gate in UNRULED:
        raise JobError("vrm_badge_undecided", UNRULED[gate])
    if gate in AUTOMATED:
        raise JobError(
            "gate_automated", f"{gate} is a machine gate: deliver_check measures it, and no decision closes it"
        )
    if gate in RECORD_BOUND:
        raise JobError("gate_record_bound", f"{gate} closes through the private MusicBed record, not by a decision")
    raise JobError("gate_unknown", "the operator gates accept closes are " + ", ".join(ACCEPTABLE))


def render_of(store):
    """The current deliver_check render: {deliver_check: {stage_key, content_sha256}, video_sha256} and its gates.
    Refuses when deliver_check has not run, fails re-hashing, or no longer reads the current compose."""
    entry = store.entry("deliver_check")
    if entry is None:
        raise JobError("deliver_check_missing", f"{store.job_id} has no deliver_check run to accept")
    if verify_stage_dir(store.dir / entry["dir"], entry["key"]):
        raise JobError("deliver_check_corrupt", "the current deliver_check fails re-hashing; run it again")
    manifest = store.manifest("deliver_check")
    compose = store.entry("compose")
    compose_manifest = store.manifest("compose")
    if compose is None or compose_manifest is None or verify_stage_dir(store.dir / compose["dir"], compose["key"]):
        raise JobError("deliver_check_stale", "the composed cut deliver_check read is not current")
    read = [i.get("digest") for i in manifest.get("inputs", []) if i.get("stage") == "compose"]
    if read != [compose["content_sha256"]]:
        raise JobError("deliver_check_stale", "deliver_check did not read the current compose; run it again")
    video = (compose_manifest.get("outputs") or {}).get("video.mp4")
    gates = (manifest.get("measurements") or {}).get("gates")
    if not isinstance(video, str) or not SHA256.fullmatch(video) or not isinstance(gates, dict):
        raise JobError("deliver_check_invalid", "deliver_check holds no gates or the compose no video.mp4")
    render = {
        "deliver_check": {"stage_key": entry["key"], "content_sha256": entry["content_sha256"]},
        "video_sha256": video,
    }
    return render, gates


def empty(job_id):
    return {"kind": KIND, "schema_version": SCHEMA_VERSION, "job_id": job_id, "acceptances": []}


ROW_FIELDS = {"gate", "decision", "accepted_utc", "job_sha256", "deliver_check", "video_sha256"}


def read(store):
    """The job's acceptance record (an empty one when there is none). store_invalid when it is malformed."""
    path = store.dir / ACCEPTANCE
    if path.is_symlink():
        raise JobError("stage_symlink", f"{ACCEPTANCE} is a symlink")
    if not path.is_file():
        return empty(store.job_id)
    value = load_store_json(path)
    rows = value.get("acceptances") if isinstance(value, dict) else None
    if (
        not isinstance(value, dict)
        or value.get("kind") != KIND
        or value.get("job_id") != store.job_id
        or not isinstance(rows, list)
        or not all(
            isinstance(r, dict) and set(r) == ROW_FIELDS and DECISION.fullmatch(str(r["decision"])) for r in rows
        )
    ):
        raise JobError("store_invalid", f"{ACCEPTANCE} is not this job's {KIND} record")
    return value


@contextmanager
def locked(store):
    """One accept at a time per job directory."""
    store.dir.mkdir(parents=True, exist_ok=True)
    fd = os.open(store.dir / ".acceptance.lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def same_render(row, render):
    return row["deliver_check"] == render["deliver_check"] and row["video_sha256"] == render["video_sha256"]


def accept(store, gate, decision, video_sha256=None, now=utc_now):
    """Record one acceptance. Returns {ok, job_id, gate, decision, accepted_utc, recorded, render,
    operator_states_open}; recorded is False when the same gate, decision and render were already recorded."""
    check_decision(decision)
    check_gate(gate)
    if video_sha256 is not None and not SHA256.fullmatch(video_sha256):
        raise JobError("video_sha256_invalid", "--video-sha256 is 64 lower-case hex characters")
    job = store.read_job()
    with locked(store):
        render, gates = render_of(store)
        if video_sha256 is not None and video_sha256 != render["video_sha256"]:
            raise JobError("video_mismatch", "the decision names another cut than the current composed video")
        state = gates.get(gate)
        if state != "pending_operator":
            raise JobError("gate_not_applicable", f"deliver_check reports {gate} as {state or 'absent'}, not pending")
        record = read(store)
        rows = record["acceptances"]
        for row in rows:
            if row["decision"] == decision and not same_render(row, render):
                raise JobError("decision_bound_elsewhere", "this decision already accepted another render")
        existing = next((r for r in rows if r["gate"] == gate and same_render(r, render)), None)
        recorded = existing is None
        if existing is not None and existing["decision"] != decision:
            raise JobError(
                "gate_already_accepted", f"{gate} of this render is already accepted by {existing['decision']}"
            )
        if existing is None:
            existing = {
                "gate": gate,
                "decision": decision,
                "accepted_utc": now(),
                "job_sha256": keys.digest(job),
            } | render
            rows.append(existing)
            write_atomic(store.dir / ACCEPTANCE, record)
            refresh_graph(store, record, render)
    closed = {r["gate"] for r in rows if same_render(r, render)}
    return {
        "ok": True,
        "job_id": store.job_id,
        "gate": gate,
        "decision": decision,
        "accepted_utc": existing["accepted_utc"],
        "recorded": recorded,
        "render": render,
        "operator_states_open": sorted(g for g, v in gates.items() if v == "pending_operator" and g not in closed),
    }


def binding(record, stage_key, content_sha256=None):
    """The acceptances that bind the deliver_check render with this key (and content digest, when known)."""
    return [
        row
        for row in record["acceptances"]
        if row["deliver_check"]["stage_key"] == stage_key
        and (content_sha256 is None or row["deliver_check"]["content_sha256"] == content_sha256)
    ]


def apply(document, rows):
    """A graph document with its acceptances: accepted lists them, pending_operator drops each gate they close."""
    closed = {row["gate"] for row in rows}
    document["accepted"] = [{k: row[k] for k in ("gate", "decision", "accepted_utc", "video_sha256")} for row in rows]
    document["pending_operator"] = [p for p in document["pending_operator"] if ADMIT_GATES.get(p["gate"]) not in closed]
    return document


def refresh_graph(store, record, render):
    """Fold the acceptance into the recorded graph.json when its deliver_check node is this render, so status shows
    it before the next plan. A graph recorded for another render is left for the next plan --record."""
    if not store.graph_file.is_file() or store.graph_file.is_symlink():
        return
    try:
        document = store.read_graph()
    except JobError:
        return
    row = next((n for n in document.get("nodes", []) if n.get("id") == "deliver_check"), None)
    key = render["deliver_check"]["stage_key"]
    if row is None or row.get("key") != key or row.get("state") not in ("fresh", "pending_operator"):
        return
    store.write_graph(apply(document, binding(record, key, render["deliver_check"]["content_sha256"])))


def for_plan(store, nodes):
    """The acceptances that bind the deliver_check node of a plan, when it is fresh: [] otherwise."""
    if store is None or not (store.dir / ACCEPTANCE).is_file():
        return []
    node = next((n for n in nodes if n["id"] == "deliver_check"), None)
    if node is None or node["state"] not in ("fresh", "pending_operator") or node.get("content_sha256") is None:
        return []
    return binding(read(store), node["key"], node["content_sha256"])
