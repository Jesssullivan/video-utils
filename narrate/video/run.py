"""The executor: run the stale stages of a job, one at a time (docs/spec/NARRATED_VIDEO.md, "Run").

run plans the job, runs every runnable node whose stage has a runner, and plans again until nothing it may run is
left. A node runs only when every upstream node is fresh, so a key is always known before a stage starts. Each stage
writes into its <key16>.partial/ directory and is committed into the store with its manifest.

- The first refusal stops the run. Finished stages stay fresh. A verdict (StageRefused.verdict, or a kitpip verdict)
  is recorded for its key; a failure is not, so calling run again retries it.
- Lanes L4, L5 and L6 run every stage: script, voice, voice_qa, base, place, music, mix, avatar and avatar_check
  (kitpip or vrm, narrate/video/avatar.py), compose, deliver_check and handoff. No stage waits on a lane.
- --stages limits a run to those stages, --until to one stage and the stages it depends on, and --force reruns a
  stage whose current run is fresh by archiving it to history/ (its refusal, if any, is cleared too).
- v1 runs one stage at a time inside one process. `just nv-run` and `just nv-quick` wrap that process in
  narrate/bounded.sh, which holds the at-most-2 bound with room to spare.
"""

import time

from . import avatar, compose, deliver, graph, handoff, music, place, speech
from . import mix as mix_stage
from .common import StageRefused
from .job import JobError
from .kitpip import KitpipRefused

RUNNERS = {
    "script": speech.run_script,
    "voice": speech.run_voice,
    "voice_qa": speech.run_voice_qa,
    "base": place.run_base,
    "place": place.run_place,
    "music": music.run_music,
    "mix": mix_stage.run_mix,
    "avatar": avatar.run_avatar_stage,
    "avatar_check": avatar.run_avatar_check,
    "compose": compose.run_compose,
    "deliver_check": deliver.run_deliver_check,
    "handoff": handoff.run_handoff,
}
LANES = {}


class RunContext:
    """from_run: a narrate run directory the voice stage adopts instead of voicing (`stage JOB voice --from-run`)."""

    def __init__(self, job, records, store, ctx, env, from_run=None):
        self.job, self.records, self.store, self.ctx, self.env = job, records, store, ctx, env
        self.from_run = from_run


def ancestors(stage_id):
    """stage_id and every stage it depends on, transitively."""
    out, todo = set(), [stage_id]
    while todo:
        stage = todo.pop()
        if stage not in out:
            out.add(stage)
            todo.extend(up for up, _ in graph.BY_ID[stage].depends_on)
    return out


def allowed_stages(stages=None, until=None):
    allowed = set(RUNNERS)
    if stages:
        unknown = sorted(set(stages) - set(graph.BY_ID))
        if unknown:
            raise JobError("stage_unknown", f"{unknown} are not stages: " + ", ".join(graph.BY_ID))
        allowed &= set(stages)
    if until:
        if until not in graph.BY_ID:
            raise JobError("stage_unknown", f"{until} is not a stage")
        allowed &= ancestors(until)
    return allowed


def force(store, job, stage_ids):
    """Archive the current run of every node of these stages and clear their refusals, so they plan stale."""
    forced = []
    for node in graph.nodes_for(job):
        if node["stage"] in stage_ids:
            cleared = store.clear_refusal(node["id"])
            archived = store.archive(node["id"])
            if cleared or archived:
                forced.append(node["id"])
    return forced


def run_node(rc, row, document):
    """Run one node into its partial directory and commit it. Returns the stage manifest."""
    store, node_id, key = rc.store, row["id"], row["key"]
    partial = store.begin(node_id, key)
    try:
        fields = RUNNERS[row["stage"]](rc, row, partial)
        return store.commit(node_id, key, document, fields)
    except BaseException as exc:
        store.abort(node_id, key)
        if isinstance(exc, (StageRefused, KitpipRefused)) and exc.verdict:
            store.record_refusal(node_id, key, exc.code, exc.detail)
        raise


def summary(g, ran, refusal=None):
    rows = {n["id"]: n for n in g["nodes"]}
    waiting = sorted(n["id"] for n in g["nodes"] if n["stage"] in LANES and n["state"] not in ("not_selected", "fresh"))
    out = {
        "ok": refusal is None and g["admit"]["verdict"] == "Admitted",
        "job_id": g["job_id"],
        "edition": g["edition"],
        "ran": ran,
        "counts": g["counts"],
        "states": {n["id"]: n["state"] for n in g["nodes"]},
        "waiting_on_lane": {node: LANES[rows[node]["stage"]] for node in waiting},
        "pending_operator": g["pending_operator"],
    }
    if g["admit"]["verdict"] != "Admitted":
        first = g["admit"]["refusals"][0]
        out |= {"refused": first["code"], "node": "admit", "detail": first["detail"]}
    if refusal is not None:
        out |= refusal
    return out


def run(rc, stages=None, until=None, forced=(), only=None, clock=time.monotonic):
    """Run stale nodes until none the call may run is left. only: one node id (the `stage` command). Returns the
    summary and the last plan."""
    allowed = allowed_stages(stages, until)
    if forced:
        force(rc.store, rc.job, set(forced))
    ran = []
    rounds = len(graph.nodes_for(rc.job)) + 1  # each round runs one node, and no node runs twice
    for _ in range(rounds):
        g = graph.plan(rc.job, rc.records, rc.store, rc.ctx)
        if g["admit"]["verdict"] != "Admitted":
            return summary(g, ran), g
        rows = {n["id"]: n for n in g["nodes"]}
        if only is not None:
            row = rows.get(only)
            if row is None:
                raise JobError("node_unknown", f"{only} is not a node of {rc.job['id']}")
            if row["stage"] not in RUNNERS:
                raise JobError("stage_pending_lane", f"{row['stage']} runs in lane {LANES[row['stage']]}")
            if only in ran or row["state"] in ("fresh", "pending_operator", "not_selected"):
                return summary(g, ran), g
            if only not in g["runnable"]:
                waiting = [d for d in row["depends_on"] if rows[d]["state"] not in ("fresh", "pending_operator")]
                code = "stage_input_stale" if row["state"] in ("stale", "corrupt") else row["reason"] or row["state"]
                refusal = {"refused": code, "node": only, "detail": f"{only} is {row['state']}; waits on {waiting}"}
                return summary(g, ran, refusal), g
            todo = [only]
        else:
            todo = [n for n in g["runnable"] if rows[n]["stage"] in allowed]
        if not todo:
            blocked = [n for n in g["nodes"] if n["state"] in ("refused", "blocked") and n["stage"] in allowed]
            refusal = None
            if blocked:
                first = blocked[0]
                detail = f"{first['id']} is {first['state']}"
                refusal = {"refused": first["reason"], "node": first["id"], "detail": detail}
            return summary(g, ran, refusal), g
        node_id = todo[0]
        started = clock()
        try:
            run_node(rc, rows[node_id], g["_documents"][node_id])
        except JobError as exc:
            entry = {"node": node_id, "key16": rows[node_id]["key16"], "refused": exc.code}
            ran.append(entry)
            g = graph.plan(rc.job, rc.records, rc.store, rc.ctx)
            refusal = {
                "refused": exc.code,
                "node": node_id,
                "detail": exc.detail,
                "recorded": bool(getattr(exc, "verdict", False)),
            }
            return summary(g, ran, refusal), g
        ran.append({"node": node_id, "key16": rows[node_id]["key16"], "seconds": round(clock() - started, 3)})
    raise JobError("run_unsettled", f"the graph did not settle in {rounds} rounds")
