"""Reruns of one job root: the render ledger, the compose-only proof and the FIX counter (docs/spec/RENDER_STAGE.md,
"Reruns", Linear TIN-7788, ruling TIN-7125 3672cb05).

A job keeps one job root. A rerun is a new event with a new run id on that root, so every stage whose key held stays
fresh and only what changed runs again. rerun.json, beside job.json, records each render and each FIX round:

- result records one row per event, with the stage keys and the store's commit counter (current.json seq). The next
  result reads that row. `ran` is every node committed since, read from seq and never from a time, so a forced rerun
  of an unchanged key still shows. A compose-only request refuses unless `ran` holds a compose stage and nothing else.
- fix records the operator's FIX of the current cut by Softproxy decision id, as accept records a GO: the id's form is
  checked, not Softproxy (resolution form_only), and the decision must name the cut it saw. The fourth FIX on a root
  refuses fix_cap_reached with nothing recorded, so the caller stops and asks the operator.

The counter is per job root, not per packet: a fixed bundle arrives as a new packet on the same root, so the rounds
add up across packets. A FIX stores ids and digests, never its notes. rerun.json carries no signature, so a reader
that needs the count to survive a hand edit keeps its own ledger too, as Cade does.
"""

from . import accept, keys
from .job import JobError
from .store import load_store_json, utc_now, write_atomic

LEDGER = "rerun.json"
KIND = "nv_rerun"
SCHEMA_VERSION = 1
FIX_CAP = 3  # TIN-7125 3672cb05: stop after 3 FIX rounds and ask the operator
COMPOSE_STAGES = ("compose", "deliver_check", "handoff")
SCOPES = ("any", "compose_only")
RENDER_FIELDS = {
    "run_id",
    "packet_id",
    "request_sha256",
    "job_sha256",
    "video_sha256",
    "deliver_check",
    "seq",
    "keys",
    "fix_round",
    "recorded_utc",
}
FIX_FIELDS = {"round", "decision", "resolution", "video_sha256", "job_sha256", "deliver_check", "recorded_utc"}


def empty(job_id):
    return {"kind": KIND, "schema_version": SCHEMA_VERSION, "job_id": job_id, "renders": [], "fixes": []}


def valid_render(row):
    return (
        isinstance(row, dict)
        and set(row) == RENDER_FIELDS
        and isinstance(row["run_id"], str)
        and isinstance(row["packet_id"], str)
        and accept.sha256(row["request_sha256"])
        and accept.sha256(row["job_sha256"])
        and accept.sha256(row["video_sha256"])
        and isinstance(row["deliver_check"], dict)
        and set(row["deliver_check"]) == accept.RENDER_FIELDS
        and isinstance(row["seq"], int)
        and not isinstance(row["seq"], bool)
        and isinstance(row["keys"], dict)
        and (row["fix_round"] is None or row["fix_round"] in range(1, FIX_CAP + 1))
    )


def valid_fix(row, position):
    return (
        isinstance(row, dict)
        and set(row) == FIX_FIELDS
        and row["round"] == position
        and accept.DECISION.fullmatch(str(row["decision"])) is not None
        and row["resolution"] == accept.RESOLUTION
        and accept.sha256(row["video_sha256"])
        and accept.sha256(row["job_sha256"])
        and isinstance(row["deliver_check"], dict)
        and set(row["deliver_check"]) == accept.RENDER_FIELDS
    )


def read(store):
    """The job root's ledger, an empty one when there is none. store_invalid when it is malformed, holds a row this
    module would not write or holds more FIX rounds than the cap."""
    path = store.dir / LEDGER
    if path.is_symlink():
        raise JobError("stage_symlink", f"{LEDGER} is a symlink")
    if not path.exists():
        return empty(store.job_id)
    if not path.is_file():
        raise JobError("store_invalid", f"{store.job_id}/{LEDGER} is not a regular file")
    value = load_store_json(path)
    renders = value.get("renders") if isinstance(value, dict) else None
    fixes = value.get("fixes") if isinstance(value, dict) else None
    if (
        not isinstance(value, dict)
        or value.get("kind") != KIND
        or value.get("schema_version") != SCHEMA_VERSION
        or value.get("job_id") != store.job_id
        or not isinstance(renders, list)
        or not isinstance(fixes, list)
        or len(fixes) > FIX_CAP
        or not all(valid_render(r) for r in renders)
        or not all(valid_fix(r, i) for i, r in enumerate(fixes, 1))
    ):
        raise JobError("store_invalid", f"{store.job_id}/{LEDGER} is not that job's {KIND} record")
    return value


def fix_summary(ledger, answers=None):
    used = len(ledger["fixes"])
    return {"rounds": used, "cap": FIX_CAP, "left": FIX_CAP - used, "answers_round": answers}


def fix_of(ledger, video):
    """The FIX round recorded against this cut, or None."""
    return next((r for r in ledger["fixes"] if r["video_sha256"] == video), None)


def previous_seq(previous):
    return previous["seq"] if previous is not None else 0


def proof(previous, stages):
    """What ran since the previous render, from the store's stages table. ran: nodes committed since, in commit order.
    changed_keys: nodes whose key moved. repeated: nodes that ran with the key they already held, which only a forced
    rerun does. compose_only: something ran, and every node of it is a compose stage."""
    since = previous_seq(previous)
    ran = [n for n, r in sorted(stages.items(), key=lambda kv: kv[1].get("seq", 0)) if r.get("seq", 0) > since]
    before = previous["keys"] if previous is not None else {}
    now = {n: r["key"] for n, r in stages.items()}
    changed = sorted(n for n in set(before) | set(now) if before.get(n) != now.get(n))
    return {
        "previous": None if previous is None else {k: previous[k] for k in ("run_id", "video_sha256")},
        "ran": ran,
        "changed_keys": changed if previous is not None else [],
        "repeated": sorted(set(ran) - set(changed)) if previous is not None else [],
        "unchanged_nodes": len(set(now) - set(ran)),
        "compose_only": bool(ran) and all(n.partition("/")[0] in COMPOSE_STAGES for n in ran),
    }


def check_scope(scope, previous, shown):
    """Refuse a compose-only request that has no render to compare, ran nothing or ran more than a compose stage."""
    if scope != "compose_only":
        return
    if previous is None:
        raise JobError("rerun_no_previous", "a compose-only rerun needs an earlier render on this job root")
    if not shown["ran"]:
        raise JobError("rerun_no_change", "the rerun ran no stage, so it proves nothing")
    if not shown["compose_only"]:
        others = [n for n in shown["ran"] if n.partition("/")[0] not in COMPOSE_STAGES]
        raise JobError("rerun_not_compose_only", f"{len(others)} other nodes ran, first {others[0]}")


def record_render(store, job, request, render, stages, seq, now=utc_now):
    """Refuse or record this event's render and return its proof for the result. The same event with the same render
    is a no-op that returns the same proof, so a retried collect writes nothing. The same event with another render
    refuses rerun_event_reused, because a resume takes a new event. A rerun of a cut the operator sent back refuses
    fix_unchanged_cut when it made that same cut again."""
    video = render["video_sha256"]
    with accept.locked(store):
        ledger = read(store)
        rows = ledger["renders"]
        at = next((i for i, r in enumerate(rows) if r["run_id"] == request["run_id"]), None)
        if at is not None:
            row = rows[at]
            if row["video_sha256"] != video or row["deliver_check"] != render["deliver_check"]:
                raise JobError(
                    "rerun_event_reused", "this event already recorded another render; a resume is a new event"
                )
            previous = rows[at - 1] if at else None
            return proof(previous, stages) | {"event": row["run_id"], "fix": fix_summary(ledger, row["fix_round"])}
        previous = rows[-1] if rows else None
        shown = proof(previous, stages)
        check_scope((request.get("rerun") or {}).get("scope"), previous, shown)
        sent_back = fix_of(ledger, previous["video_sha256"]) if previous is not None else None
        if sent_back is not None and video == sent_back["video_sha256"]:
            raise JobError("fix_unchanged_cut", "the rerun made the cut the operator sent back")
        answers = sent_back["round"] if sent_back is not None else None
        rows.append(
            {
                "run_id": request["run_id"],
                "packet_id": request["packet_id"],
                "request_sha256": keys.digest(request),
                "job_sha256": keys.digest(job),
                "video_sha256": video,
                "deliver_check": render["deliver_check"],
                "seq": seq,
                "keys": {n: r["key"] for n, r in stages.items()},
                "fix_round": answers,
                "recorded_utc": now(),
            }
        )
        write_atomic(store.dir / LEDGER, ledger)
    return shown | {"event": request["run_id"], "fix": fix_summary(ledger, answers)}


def fix(store, decision, video_sha256, now=utc_now):
    """Record the operator's FIX of the cut whose sha256 is video_sha256. Returns {ok, job_id, round, recorded, fix}.
    recorded is False when this decision already holds this cut's round. Refusals: the decision and video forms
    accept refuses, video_mismatch, fix_already_recorded (this cut holds another decision), decision_bound_elsewhere,
    cut_accepted and fix_cap_reached. Nothing is written on a refusal."""
    accept.check_decision(decision)
    accept.check_video(video_sha256)
    job = store.read_job()
    with accept.locked(store):
        render, _ = accept.render_of(store, job)
        if video_sha256 != render["video_sha256"]:
            raise JobError("video_mismatch", "the decision names another cut than the current composed video")
        ledger = read(store)
        existing = fix_of(ledger, video_sha256)
        if existing is not None and existing["decision"] != decision:
            raise JobError("fix_already_recorded", f"this cut's round is already held by {existing['decision']}")
        if existing is None:
            rows = accept.read(store)["acceptances"]
            if any(r["decision"] == decision for r in ledger["fixes"] + rows) or accept.bound_elsewhere(
                store, decision, render
            ):
                raise JobError("decision_bound_elsewhere", "this decision already answered another cut or gate")
            if any(r["video_sha256"] == video_sha256 for r in rows):
                raise JobError("cut_accepted", "the operator already accepted a gate of this cut")
            if len(ledger["fixes"]) >= FIX_CAP:
                raise JobError(
                    "fix_cap_reached", f"this job root used its {FIX_CAP} FIX rounds: stop and ask the operator"
                )
            existing = {
                "round": len(ledger["fixes"]) + 1,
                "decision": decision,
                "resolution": accept.RESOLUTION,
                "video_sha256": video_sha256,
                "job_sha256": keys.digest(job),
                "deliver_check": render["deliver_check"],
                "recorded_utc": now(),
            }
            ledger["fixes"].append(existing)
            write_atomic(store.dir / LEDGER, ledger)
            recorded = True
        else:
            recorded = False
    return {
        "ok": True,
        "job_id": store.job_id,
        "round": existing["round"],
        "decision": decision,
        "resolution": existing["resolution"],
        "recorded": recorded,
        "fix": fix_summary(ledger),
    }
