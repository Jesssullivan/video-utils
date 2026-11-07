"""Reruns of one job root: the render ledger, the compose-only proof and the FIX counter (docs/spec/RENDER_STAGE.md,
"Reruns", Linear TIN-7788, ruling TIN-7125 3672cb05).

A job keeps one job root. A rerun is a new event with a new run id on that root, so every stage whose key held stays
fresh and only what changed runs again. rerun.json, beside job.json, records each render and each FIX round:

- result records one row per event, with the stage keys and the store's commit counter (current.json seq). The next
  result reads that row. `ran` is every node committed since, read from seq and never from a time, so a forced rerun
  of an unchanged key still shows. A compose-only request refuses unless `ran` holds a compose stage and nothing else.
- fix records the operator's FIX of the current cut by Softproxy decision id, as accept records a GO: the id's form is
  checked, not Softproxy (resolution form_only), and the decision must name the cut it saw. The fourth FIX on a root
  refuses fix_cap_reached with nothing recorded, so the caller stops and asks the operator. The answer extends the
  root by one round per decision, each recorded (ruling TIN-7125 11296de3): with extend, that FIX takes a round past
  the cap and its row says extended.
- machine_round records a round a gate's findings started, with no Softproxy decision, on a job bound to a campaign
  (rulings TIN-7125 52ca88bf, 0690fe88). bind_campaign is the one write that binds it, and it refuses a client edition
  and a root that already holds an operator's decision, so every other job keeps its fix or accept. The row holds the
  findings by digest and code count, the stages their fix may run (graph.reach) and the store's commit counter, and the
  render that answers it refuses round_out_of_reach when anything else ran since, so a slide fix cannot re-voice. A
  report that names its job or cut binds them, so findings of another job or an older job.json start nothing, and
  findings of a cut name that cut. At the cap the root parks: a parked record and the result parked, which asks nobody.
  A later round on that root reads parked again. An entry gate's refusal (narrate/video/entry.py) can start one before
  the bundle has become a job: its bundle's digest stands in for the job, and the edition is the one intake writes,
  never a client's.

A decision binds one cut of one job, whether it was a GO or a FIX: accept.bound_elsewhere reads every job's rerun.json
under the store root, under the root lock. A round binds its cut for good: accept refuses that cut and a later result
refuses to record it, whichever round sent it back and whether or not a render row names it. A machine round on findings
read before any render binds no cut.

The counter is per job root, not per packet: a fixed bundle arrives as a new packet on the same root, so the rounds
add up across packets. A FIX stores ids and digests, never its notes. rerun.json carries no signature, so a reader
that needs the count to survive a hand edit keeps its own ledger too, as Cade does. The same holds for the campaign
binding: its id's form is checked here, and that a signed campaign record holds it is the caller's check.
"""

from . import accept, graph, keys
from . import findings as typed
from .job import CLIENT_EDITIONS, ID, JobError
from .store import load_store_json, utc_now, write_atomic

LEDGER = "rerun.json"
KIND = "nv_rerun"
SCHEMA_VERSION = 1
FIX_CAP = 3  # TIN-7125 3672cb05: stop after 3 FIX rounds. Each operator decision past it adds one (11296de3)
COMPOSE_STAGES = ("compose", "deliver_check", "handoff")
SCOPES = ("any", "compose_only")
INTAKE_EDITION = "Internal"  # the one edition bundle.convert writes
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
MACHINE = "machine"  # a machine round's resolution, where a FIX holds form_only
ROUND_FIELDS = FIX_FIELDS | {"campaign", "findings_sha256", "codes", "reach", "seq"}
CAMPAIGN_FIELDS = {"id", "resolution", "recorded_utc"}
PARKED_FIELDS = {"round", "findings_sha256", "codes", "video_sha256", "job_sha256", "recorded_utc"}


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
        and (row["fix_round"] is None or (type(row["fix_round"]) is int and row["fix_round"] >= 1))
    )


def valid_round(row, position):
    """A machine round's row. It holds no decision and never passes the cap, and only a cut it read names a render."""
    return (
        isinstance(row, dict)
        and set(row) == ROUND_FIELDS
        and row["round"] == position
        and position <= FIX_CAP
        and row["decision"] is None
        and row["resolution"] == MACHINE
        and isinstance(row["campaign"], str)
        and accept.sha256(row["findings_sha256"])
        and isinstance(row["codes"], dict)
        and isinstance(row["reach"], list)
        and type(row["seq"]) is int
        and accept.sha256(row["job_sha256"])
        and (row["video_sha256"] is None or accept.sha256(row["video_sha256"]))
        and (
            row["deliver_check"] is None
            or (isinstance(row["deliver_check"], dict) and set(row["deliver_check"]) == accept.RENDER_FIELDS)
        )
    )


def valid_fix(row, position):
    """An operator's FIX. A round past the cap says extended, and no other round may."""
    if isinstance(row, dict) and row.get("resolution") == MACHINE:
        return valid_round(row, position)
    if not isinstance(row, dict) or ("extended" in row) != (position > FIX_CAP):
        return False
    if row.get("extended", True) is not True:
        return False
    row = {k: v for k, v in row.items() if k != "extended"}
    return (
        set(row) == FIX_FIELDS
        and row["round"] == position
        and accept.DECISION.fullmatch(str(row["decision"])) is not None
        and row["resolution"] == accept.RESOLUTION
        and accept.sha256(row["video_sha256"])
        and accept.sha256(row["job_sha256"])
        and isinstance(row["deliver_check"], dict)
        and set(row["deliver_check"]) == accept.RENDER_FIELDS
    )


def valid_campaign(value):
    return (
        value is None
        or isinstance(value, dict)
        and set(value) == CAMPAIGN_FIELDS
        and isinstance(value["id"], str)
        and ID.fullmatch(value["id"]) is not None
        and value["resolution"] == accept.RESOLUTION
    )


def valid_parked(value):
    return (
        value is None
        or isinstance(value, dict)
        and set(value) == PARKED_FIELDS
        and accept.sha256(value["findings_sha256"])
        and accept.sha256(value["job_sha256"])
    )


def read_path(path, job_id):
    """The ledger at path for job_id, an empty one when there is none. store_invalid when it is malformed, holds a row
    this module would not write or holds a round past the cap that no operator's decision extended. A ledger written
    before campaigns holds neither campaign nor parked and reads as holding none."""
    if path.is_symlink():
        raise JobError("stage_symlink", f"{LEDGER} is a symlink")
    if not path.exists():
        return empty(job_id)
    if not path.is_file():
        raise JobError("store_invalid", f"{job_id}/{LEDGER} is not a regular file")
    value = load_store_json(path)
    renders = value.get("renders") if isinstance(value, dict) else None
    fixes = value.get("fixes") if isinstance(value, dict) else None
    if (
        not isinstance(value, dict)
        or value.get("kind") != KIND
        or value.get("schema_version") != SCHEMA_VERSION
        or value.get("job_id") != job_id
        or not isinstance(renders, list)
        or not isinstance(fixes, list)
        or not all(valid_render(r) for r in renders)
        or not all(valid_fix(r, i) for i, r in enumerate(fixes, 1))
        or not valid_campaign(value.get("campaign"))
        or not valid_parked(value.get("parked"))
    ):
        raise JobError("store_invalid", f"{job_id}/{LEDGER} is not that job's {KIND} record")
    return value


def read(store):
    """The job root's ledger, as read_path gives it."""
    return read_path(store.dir / LEDGER, store.job_id)


def fix_summary(ledger, answers=None):
    """rounds used of the cap. A round past FIX_CAP raised the cap by one, and that round is used, so left stays 0."""
    used = len(ledger["fixes"])
    cap = max(FIX_CAP, used)
    return {"rounds": used, "cap": cap, "left": cap - used, "answers_round": answers}


def fix_of(ledger, video):
    """The FIX round recorded against this cut, or None."""
    return next((r for r in ledger["fixes"] if r["video_sha256"] == video), None)


def unanswered(ledger):
    """The FIX round a new render answers: the last one, unless a render answered it. None with no such round."""
    last = ledger["fixes"][-1]["round"] if ledger["fixes"] else None
    return None if any(r["fix_round"] == last for r in ledger["renders"]) else last


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


def check_reach(ledger, answers, previous, stages):
    """Refuse a render that answers a machine round when a stage that round's fix may not run committed after the round.
    The row holds the store's commit counter, so what ran before it counts for nothing, and a cut with no render row is
    still checked. A round that named no cut, on a root with no render, has nothing to compare: what runs next is the
    whole job."""
    row = ledger["fixes"][answers - 1] if answers is not None else None
    if row is None or row["resolution"] != MACHINE or (previous is None and row["video_sha256"] is None):
        return
    since = sorted((n for n, r in stages.items() if r.get("seq", 0) > row["seq"]), key=lambda n: stages[n]["seq"])
    others = [n for n in since if n.partition("/")[0] not in row["reach"]]
    if others:
        raise JobError("round_out_of_reach", f"round {answers} reaches no {others[0]}; {len(others)} such nodes ran")


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
    """Refuse or record this event's render and return its proof for the result. The same event with the same request
    and render is a no-op that writes nothing and reads the proof against the same previous row, so a retried collect
    is safe. The same event with another request or render refuses rerun_event_reused, because a resume takes a new
    event. A render of a cut any FIX round sent back refuses fix_unchanged_cut, so it never records. A FIX needs no
    render row, because it binds the current composed video, so this holds on a root with no render recorded."""
    video, request_sha256 = render["video_sha256"], keys.digest(request)
    with accept.locked(store):
        ledger = read(store)
        rows = ledger["renders"]
        at = next((i for i, r in enumerate(rows) if r["run_id"] == request["run_id"]), None)
        if at is not None:
            row = rows[at]
            if (
                row["request_sha256"] != request_sha256
                or row["video_sha256"] != video
                or row["deliver_check"] != render["deliver_check"]
            ):
                raise JobError(
                    "rerun_event_reused", "this event already recorded another request or render; resume with a new one"
                )
            previous = rows[at - 1] if at else None
            return proof(previous, stages) | {"event": row["run_id"], "fix": fix_summary(ledger, row["fix_round"])}
        previous = rows[-1] if rows else None
        shown = proof(previous, stages)
        check_scope((request.get("rerun") or {}).get("scope"), previous, shown)
        if fix_of(ledger, video) is not None:
            raise JobError("fix_unchanged_cut", "the rerun made a cut a FIX round sent back")
        answers = unanswered(ledger)
        check_reach(ledger, answers, previous, stages)
        rows.append(
            {
                "run_id": request["run_id"],
                "packet_id": request["packet_id"],
                "request_sha256": request_sha256,
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


def fix(store, decision, video_sha256, now=utc_now, extend=False):
    """Record the operator's FIX of the cut whose sha256 is video_sha256. Returns {ok, job_id, round, recorded, fix}.
    recorded is False when this decision already holds this cut's round. Refusals: the decision and video forms
    accept refuses, video_mismatch, fix_already_recorded (this cut holds another decision), decision_bound_elsewhere,
    cut_accepted, fix_extend_unneeded (extend with rounds left) and fix_cap_reached (no rounds left and no extend).
    extend is the operator's answer at the cap: this decision adds the one round it takes. Nothing is written on a
    refusal."""
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
            if any(r["decision"] == decision for r in rows) or accept.bound_elsewhere(store, decision, render):
                raise JobError("decision_bound_elsewhere", "this decision already answered another cut or gate")
            if any(r["video_sha256"] == video_sha256 for r in rows):
                raise JobError("cut_accepted", "the operator already accepted a gate of this cut")
            at_cap = len(ledger["fixes"]) >= FIX_CAP
            if at_cap and not extend:
                raise JobError(
                    "fix_cap_reached", f"this job root used its {FIX_CAP} FIX rounds: stop and ask the operator"
                )
            if extend and not at_cap:
                raise JobError("fix_extend_unneeded", "this job root has FIX rounds left, so no decision extends it")
            existing = {
                "round": len(ledger["fixes"]) + 1,
                "decision": decision,
                "resolution": accept.RESOLUTION,
                "video_sha256": video_sha256,
                "job_sha256": keys.digest(job),
                "deliver_check": render["deliver_check"],
                "recorded_utc": now(),
            } | ({"extended": True} if at_cap else {})
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


def bind_campaign(store, campaign, now=utc_now, before_intake=False):
    """Bind this job root to a campaign, the one thing that lets a round start with no Softproxy decision. Returns {ok,
    job_id, campaign, recorded}. Refusals: campaign_id_invalid, campaign_client_job (a client edition), campaign_bound
    (another campaign holds the root) and campaign_after_decision (the root holds an operator's FIX or acceptance, so
    it stays on that path). before_intake takes a root with no job.json yet, so the first entry gate's refusal can start
    a round. machine_round reads the edition again once a job exists. Nothing is written on a refusal, and binding the
    same campaign again is a no-op."""
    if not isinstance(campaign, str) or ID.fullmatch(campaign) is None:
        raise JobError("campaign_id_invalid", "a campaign id is 1 to 64 of a-z, 0-9, '.', '_' and '-'")
    if store.exists() or not before_intake:
        job = store.read_job()
        if job["edition"] in CLIENT_EDITIONS:
            raise JobError("campaign_client_job", f"edition {job['edition']} keeps the operator's decision")
    store.dir.mkdir(parents=True, exist_ok=True)
    with accept.locked(store):
        ledger = read(store)
        held = (ledger.get("campaign") or {}).get("id")
        if held not in (None, campaign):
            raise JobError("campaign_bound", "another campaign already holds this job root")
        if held is None:
            decided = any(r["decision"] is not None for r in ledger["fixes"]) or accept.read(store)["acceptances"]
            if decided:
                raise JobError("campaign_after_decision", "this job root holds an operator's decision")
            ledger["campaign"] = {"id": campaign, "resolution": accept.RESOLUTION, "recorded_utc": now()}
            write_atomic(store.dir / LEDGER, ledger)
    return {"ok": True, "job_id": store.job_id, "campaign": campaign, "recorded": held is None}


def round_entry(ledger, findings_sha256, job_sha256, video_sha256):
    """The round this same reading already recorded, or None. fix_already_recorded when this cut holds another."""
    if video_sha256 is None:
        rows = [r for r in ledger["fixes"] if r["video_sha256"] is None and r["job_sha256"] == job_sha256]
    else:
        rows = [r for r in ledger["fixes"] if r["video_sha256"] == video_sha256]
    if not rows:
        return None
    if rows[-1].get("findings_sha256") != findings_sha256:
        raise JobError("fix_already_recorded", f"round {rows[-1]['round']} already holds this cut")
    return rows[-1]


def round_result(store, ledger, row, recorded):
    return {
        "ok": True,
        "result": "round",
        "job_id": store.job_id,
        "round": row["round"],
        "campaign": row["campaign"],
        "reach": row["reach"],
        "recorded": recorded,
        "fix": fix_summary(ledger),
    }


def named_video(report, video_sha256):
    """The cut a round names: the caller's, or the one its report read. Refuses video_mismatch when they differ, because
    a round that dropped the report's cut would bind none, and an unchanged cut could answer it."""
    named = report.get("video_sha256")
    if named is None:
        return video_sha256
    accept.check_video(named)
    if video_sha256 not in (None, named):
        raise JobError("video_mismatch", "the report read another cut than --video-sha256 names")
    return named


def machine_round(store, report, video_sha256=None, now=utc_now):
    """Record a round that report (narrate/video/findings.py) started, on a job bound to a campaign. video_sha256 names
    the cut those findings read, and a report only a cut can give must name one. Returns {ok, result, ...}: result is
    round with its number and reach, or parked at the cap with the rounds used. Refusals: findings_invalid,
    round_needs_decision (a client edition, or no campaign bound), round_no_findings (no blocking row), findings_stale
    (the report names another job or job.json), round_video_missing, the video forms, video_mismatch, cut_accepted and
    fix_already_recorded. Parking writes the parked record, a refusal writes nothing, and the same findings on the same
    cut again is a no-op."""
    shown = typed.check(report)
    rows = [row for row in shown["findings"] if row["blocking"]]
    held_entry = store.entry_refused()
    job = store.read_job() if held_entry is None or store.exists() else {"edition": INTAKE_EDITION}
    job_sha256 = keys.digest(job) if held_entry is None else held_entry["bundle_sha256"]
    findings_sha256 = keys.digest(shown["findings"])
    codes = {code: sum(1 for row in rows if row["code"] == code) for code in sorted({row["code"] for row in rows})}
    with accept.locked(store):
        ledger = read(store)
        campaign = (ledger.get("campaign") or {}).get("id")
        if job["edition"] in CLIENT_EDITIONS or campaign is None:
            raise JobError("round_needs_decision", "only a job bound to a campaign starts a round with no decision")
        if not rows:
            raise JobError("round_no_findings", "the report holds no blocking finding, so nothing starts a round")
        if report.get("job_id", store.job_id) != store.job_id or report.get("job_sha256", job_sha256) != job_sha256:
            raise JobError("findings_stale", "the report read another job or job.json than the root holds")
        video_sha256 = named_video(report, video_sha256)
        render = None
        if video_sha256 is not None:
            accept.check_video(video_sha256)
            render, _ = accept.render_of(store, job)
            if video_sha256 != render["video_sha256"]:
                raise JobError("video_mismatch", "the findings name another cut than the current composed video")
            if any(r["video_sha256"] == video_sha256 for r in accept.read(store)["acceptances"]):
                raise JobError("cut_accepted", "the operator already accepted a gate of this cut")
        elif any(typed.reads_cut(row) for row in rows):
            raise JobError("round_video_missing", "these findings read a composed cut, so the round names it")
        if ledger.get("parked") is not None:
            return parked_result(store, ledger, recorded=False)
        existing = round_entry(ledger, findings_sha256, job_sha256, video_sha256)
        if existing is not None:
            return round_result(store, ledger, existing, recorded=False)
        fixes = ledger["fixes"]
        if len(fixes) >= FIX_CAP:
            ledger["parked"] = {
                "round": len(fixes),
                "findings_sha256": findings_sha256,
                "codes": codes,
                "video_sha256": video_sha256,
                "job_sha256": job_sha256,
                "recorded_utc": now(),
            }
            write_atomic(store.dir / LEDGER, ledger)
            return parked_result(store, ledger, recorded=True)
        row = {
            "round": len(fixes) + 1,
            "decision": None,
            "resolution": MACHINE,
            "campaign": campaign,
            "findings_sha256": findings_sha256,
            "codes": codes,
            "reach": graph.reach({row["stage"] for row in rows}),
            "seq": store.current().get("seq", 0),
            "video_sha256": video_sha256,
            "job_sha256": job_sha256,
            "deliver_check": None if render is None else render["deliver_check"],
            "recorded_utc": now(),
        }
        fixes.append(row)
        write_atomic(store.dir / LEDGER, ledger)
    return round_result(store, ledger, row, recorded=True)


def parked_result(store, ledger, recorded):
    held = ledger["parked"]
    return {
        "ok": True,
        "result": "parked",
        "job_id": store.job_id,
        "campaign": ledger["campaign"]["id"],
        "codes": held["codes"],
        "findings_sha256": held["findings_sha256"],
        "recorded": recorded,
        "fix": fix_summary(ledger),
    }
