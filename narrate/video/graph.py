"""The narrated-video stage graph and its planner (docs/spec/NARRATED_VIDEO.md, "Stages").

STAGES is the graph; program/dags/narrated-video.json publishes the same table and a test keeps them equal. Each
stage reads three kinds of input into its key:

- knobs: the job fields (and record fields) the stage's output depends on, projected by KNOBS[stage]. A field
  that only a later stage reads is that stage's knob, so changing it reruns only that stage and what follows it;
- sources: SHA-256 digests of private-store blobs (script, still, video, deck files, bed loops);
- upstream inputs: an upstream node's manifest content_sha256, or one measured value from its manifest (a
  projection). avatar reads only the base's measured fps, so re-assembling a deck with the same rate keeps
  every overlay fresh.

admit is a gate, not a data input: it runs at every plan, and a refusal blocks every other stage. Plan is read-only:
it keys each node in topological order from the store's current.json and reports one state per node:

  fresh            the current directory has this key and re-hashes
  stale            no run, a changed key, or an upstream node that is not fresh (key unknown until it runs)
  corrupt          the current directory has this key but fails re-hashing (run moves it to history/)
  blocked          admit refused, a tool or source is missing, or an upstream node is blocked or refused
  refused          the stage refused for this exact key; it stays refused until the key changes
  not_selected     an optional stage the job turns off
  pending_operator deliver_check is fresh but an operator gate (listening, lip sync, licence PDF, Content ID, unread
                   on-screen text) is open

The graph also lists the operator's acceptances (`accept`, narrate/video/accept.py) that bind the fresh deliver_check
render under accepted, and drops the gates they close (listening and lip sync) from pending_operator. Every other
operator gate, visible_text_unread among them, stays listed.
"""

from collections import namedtuple
from datetime import UTC, datetime

from . import accept as acceptance
from . import admit as admit_stage
from . import keys, vrm
from .job import JobError

Stage = namedtuple("Stage", "id fan_out depends_on optional mapping intent")

# depends_on: (upstream stage, how) with how one of "segment" (the same segment's node), "all" (every selected
# node of that stage) or "measure:<field>" (one value from the upstream manifest's measurements, not its digest).
STAGES = (
    Stage(
        "admit",
        False,
        (),
        False,
        None,
        "Resolve the job and refuse before any render: consent, persona, bed "
        "acquisition, tighten, bounds, kitpip pin and the edition at Plan",
    ),
    Stage("script", True, (), False, None, "Lexical findings (advisory, R-N12) and the spoken-text digest"),
    Stage("voice", True, (("script", "segment"),), False, "narration_v1", "One narrate run per segment"),
    Stage("voice_qa", True, (("voice", "segment"),), False, None, "narrate verify and evaluate receipt"),
    Stage("base", False, (), False, None, "Conformed base picture and base.json (fps, size, length)"),
    Stage(
        "place",
        False,
        (("base", "all"), ("voice", "all"), ("voice_qa", "all")),
        False,
        "narrated_video_v1",
        "placements.json, voice.wav and clips.wav on the base clock; the base extended to narration plus tail",
    ),
    Stage(
        "avatar",
        True,
        (("voice", "segment"), ("base", "measure:fps")),
        True,
        "avatar_overlay_v1",
        "overlay.mov (ProRes 4444) per segment, drawn by the job's avatar external",
    ),
    Stage(
        "avatar_check",
        True,
        (("avatar", "segment"), ("voice", "segment")),
        True,
        None,
        "the avatar external's verify and the label chain",
    ),
    Stage("music", False, (), True, "music_bed_v1", "bed.wav (48 kHz) arranged from the record's loops"),
    Stage(
        "mix",
        False,
        (("place", "all"), ("music", "all")),
        False,
        "narrated_video_v1",
        "mix.wav: bed level, sidechain duck, fades, one limiter; measured loudness, true peak and duck depth",
    ),
    Stage(
        "compose",
        False,
        (("base", "all"), ("place", "all"), ("mix", "all"), ("avatar", "all"), ("avatar_check", "all")),
        False,
        "narrated_video_v1",
        "video.mp4, upload copy, captions, description.txt and chapters",
    ),
    Stage(
        "deliver_check",
        False,
        (("compose", "all"),),
        False,
        None,
        "deliver_check.json: per-gate states and delivery_gate",
    ),
    Stage(
        "handoff",
        False,
        (("base", "all"), ("place", "all"), ("mix", "all"), ("avatar", "all"), ("compose", "all")),
        True,
        "narrated_video_v1",
        "pre-VFX layers and edit.json",
    ),
)
BY_ID = {s.id: s for s in STAGES}
# Bump a stage's impl by hand when its output changes for the same inputs. voice is 2: KP-15 (TIN-7476 comment
# 4ab7fc27) dropped the "[Synthetic voice] " caption prefix and the VTT NOTE from narrate render. compose and handoff
# are 2: they drop chapters and record the metadata check, and handoff writes each slide layer stripped (TIN-7788).
# base is 2: its clips.wav drops the source's tags. deliver_check is 2: it reports the intake's visible_text state as
# an operator gate (TIN-7788). music and place also call to_mono, but they re-encode its samples, so their bytes stay.
IMPL = {s.id: 1 for s in STAGES} | {"voice": 2, "base": 2, "compose": 2, "handoff": 2, "deliver_check": 2}
TOOLS = {
    "admit": ("narrate.video.admit", "1"),
    "script": ("narrate.lexical", "1"),
    "voice": ("narrate.render", "1"),
    "voice_qa": ("narrate.evaluate", "1"),
    "base": ("narrate.video.base", "1"),
    "place": ("narrate.video.place", "1"),
    "music": ("narrate.video.music", "1"),
    "mix": ("narrate.video.mix", "1"),
    "compose": ("narrate.video.compose", "1"),
    "deliver_check": ("narrate.video.deliver_check", "1"),
    "handoff": ("narrate.video.handoff", "1"),
}
KITPIP_STAGES = ("avatar", "avatar_check")
AVATAR_STAGES = KITPIP_STAGES  # run by the job's avatar external: kitpip or vrm (narrate/video/avatar.py)
# The neutral tool name of each avatar stage. program/dags/narrated-video.json publishes them with dispatch.by
# avatar.external, so a job that moves from kitpip to vrm keeps the same stage tools (TIN-7788).
AVATAR_TOOLS = {"avatar": "avatar_overlay", "avatar_check": "avatar_verify"}
AVATAR_DISPATCH = "avatar.external"
# ctx keys of each external's pin and resolution, and the plan reasons for avatar stages it cannot run.
AVATAR_CTX = {"kitpip": ("pin", "kitpip"), "vrm": ("vrm_pin", "vrm")}
AVATAR_BLOCKED = {
    "kitpip": {"pending": "kitpip_pin_pending", None: "kitpip_missing"},
    "vrm": {"pending": "vrm_pin_pending", None: "vrm_renderer_missing"},
}
RENDER_STAGES = ("base", "place", "music", "mix", "compose", "handoff")
STATES = ("fresh", "stale", "corrupt", "blocked", "refused", "not_selected", "pending_operator")
MUSIC_RATE_HZ = 48000


def toposort(stages):
    """Stage ids in dependency order; JobError graph_cycle when the edges loop or name an unknown stage."""
    ids = {s.id for s in stages}
    edges = {s.id: {up for up, _ in s.depends_on} for s in stages}
    for stage, ups in edges.items():
        if ups - ids:
            raise JobError("graph_cycle", f"{stage} depends on unknown {sorted(ups - ids)}")
    order, done = [], set()
    while len(order) < len(stages):
        ready = [s.id for s in stages if s.id not in done and edges[s.id] <= done]
        if not ready:
            raise JobError("graph_cycle", f"the stage graph loops among {sorted(ids - done)}")
        order.extend(ready)
        done.update(ready)
    return order


ORDER = toposort(STAGES)


def avatar_external(job):
    """The job's avatar.external (kitpip or vrm), or None without an avatar block."""
    return (job.get("avatar") or {}).get("external")


def avatar_pin(job, ctx):
    """The pin of the job's avatar external from the plan context, or None."""
    keys_ = AVATAR_CTX.get(avatar_external(job))
    return ctx.get(keys_[0]) if keys_ else None


def avatar_resolution(job, ctx):
    """The resolution ({state, binary, tool, detail}) of the job's avatar external, or None."""
    keys_ = AVATAR_CTX.get(avatar_external(job))
    return ctx.get(keys_[1]) if keys_ else None


def avatar_blocked(job, state):
    table = AVATAR_BLOCKED.get(avatar_external(job), AVATAR_BLOCKED["kitpip"])
    return table.get(state, table[None])


# Knobs ---------------------------------------------------------------------------------------------------------
def base_kind(job):
    kind, body = next(iter(job["base"].items()))
    return kind, body


def engine_identity(records, narrate_job):
    """The engine record narrate renders with, as the voice key holds it: every field but the endpoint (a serving
    path, private and not part of the output), with its files named by digest only (their paths are private).
    None when the records hold no such engine; narrate then refuses at render."""
    engine = (records.get("engines") or {}).get(narrate_job["engine"])
    if engine is None:
        return None
    out = {k: v for k, v in engine.items() if k not in ("endpoint", "files")}
    out["files"] = sorted(f["sha256"] for f in engine.get("files") or [])
    return out


def pronunciation_identity(records, narrate_job):
    """{id, sha256} of the pronunciation table narrate's normaliser reads, or None when the records lack it."""
    table = (records.get("pronunciation") or {}).get(narrate_job.get("pronunciation"))
    if table is None:
        return None
    return {"id": table["id"], "sha256": keys.digest(table)}


def engine_binary_sha256(records, narrate_job):
    """The voice tool's binary digest: the SHA-256 of the canonical sorted list of the engine's pinned file digests
    (binary and weights), or None for an engine that pins no file (the in-process fake)."""
    engine = (records.get("engines") or {}).get(narrate_job["engine"]) if narrate_job else None
    files = sorted(f["sha256"] for f in (engine or {}).get("files") or [])
    return keys.digest(files) if files else None


def knobs_for(stage, segment, job, records, pin):
    """The job and record fields one node's output depends on. Each field belongs to the first stage that uses it."""
    narrate_job = records["jobs"].get(segment["narrateJob"]) if segment else None
    kind, body = base_kind(job)
    if stage == "script":
        return {
            "narrate_job": segment["narrateJob"],
            "input_kind": narrate_job["input"],
            "lexical": narrate_job["lexical"],
        }
    if stage == "voice":
        voices = [narrate_job["voice"]] + [s["voice"] for s in narrate_job["speakers"]]
        return {
            "narrate_job": {k: v for k, v in narrate_job.items() if k != "gates"},
            "voices": [records["voices"][v] for v in sorted(set(voices))],
            "engine": engine_identity(records, narrate_job),
            "pronunciation": pronunciation_identity(records, narrate_job),
        }
    if stage == "voice_qa":
        return {"gates": narrate_job["gates"]}
    if stage == "base":
        return {
            "kind": kind,
            "base": {k: v for k, v in body.items() if k != "tailS"},
            "profile": job["delivery"]["profile"],
        }
    if stage == "place":
        return {
            "segments": [{"id": s["id"], "anchor": s["anchor"]} for s in job["segments"]],
            "tailS": body.get("tailS"),
            "keepBaseAudio": body.get("keepBaseAudio"),
            "tighten": job["tighten"],
            "persona": job["labels"]["persona"],
        }
    if stage == "avatar" and avatar_external(job) == "vrm":
        return vrm.knobs(job, records, pin)
    if stage == "avatar":
        # The pin's default-rig revision belongs only to the default rig. Another rig with no revision in the job
        # keys None; its stage manifest records the revision kitpip reports (measurements.rig).
        avatar, default = job["avatar"], pin["default_rig"]
        rig = avatar["rig"] or default["id"]
        revision = avatar["rigRevisionSha256"]
        if revision is None and rig == default["id"]:
            revision = default.get("sha256")
        # The overlay's manifest carries labels.persona, so the persona is an avatar knob: a persona change
        # reruns the overlay rather than leaving a stage whose labels no longer match its key.
        return {
            "rig": rig,
            "rigRevisionSha256": revision,
            "renderSize": avatar["renderSize"],
            "persona": job["labels"]["persona"],
        }
    if stage == "avatar_check" and avatar_external(job) == "vrm":
        return {"external": "vrm", "persona": job["labels"]["persona"]}
    if stage == "avatar_check":
        return {"persona": job["labels"]["persona"]}
    if stage == "music":
        bed = records["music_beds"][job["music"]["bed"]]
        layers = [
            {k: layer[k] for k in ("sha256", "bytes", "rateHz", "channels", "tempoFactor", "gainDb")}
            for layer in bed["layers"]
        ]
        return {"bed": bed["id"], "layers": layers, "rateHz": MUSIC_RATE_HZ}
    if stage == "mix":
        music = {k: v for k, v in job["music"].items() if k != "bed"} if job["music"] else None
        delivery = {k: job["delivery"][k] for k in ("targetLufs", "truePeakDbtp", "driftLu", "channels")}
        return {"music": music, "delivery": delivery}
    if stage == "compose":
        fields = ("corner", "width", "marginPx", "avatarOff", "fadeS")
        placement = {k: job["avatar"][k] for k in fields} if job["avatar"] else None
        return {
            "avatar": placement,
            "slides": job["slides"],
            "captions": job["captions"],
            "labels": job["labels"],
            "profile": job["delivery"]["profile"],
        }
    if stage == "deliver_check":
        bed = records["music_beds"].get(job["music"]["bed"]) if job["music"] else None
        gates = {k: bed["licence"][k] for k in ("certifiedPdfSha256", "contentIdCheck")} if bed else None
        delivery = {k: v for k, v in job["delivery"].items() if k != "handoff"}
        # The guarded intake's visible-text summary (job.load_records from the marker): a re-intake that reads
        # more slides changes it, so deliver_check reruns.
        visible = records.get("visible_text")
        # The job's digest too: accept pairs one deliver_check render with job.json (accept.render_of), so any edit
        # to job.json, delivery.handoff included, plans a new render rather than leaving an old one current.
        return {
            "delivery": delivery,
            "bed_gates": gates,
            "labels": job["labels"],
            "visible_text": visible,
            "job_sha256": keys.digest(job),
        }
    if stage == "handoff":
        return {}
    raise JobError("graph_cycle", f"no knobs for stage {stage}")


def sources_for(stage, segment, job, records):
    """[{slot, stage: "source", digest}] of the private-store blobs a node reads."""
    kind, body = base_kind(job)
    rows = []
    if stage == "script":
        rows.append(("script", segment["scriptSha256"]))
    elif stage == "base":
        if kind in ("still", "video"):
            rows.append((kind, body["sha256"]))
        elif kind == "deck":
            for field in ("videoSha256", "timelineSha256", "stemsSha256", "tightenEditsSha256"):
                if body[field] is not None:
                    rows.append((f"deck.{field}", body[field]))
    elif stage == "music":
        bed = records["music_beds"][job["music"]["bed"]]
        rows.extend((f"loop.{i}", layer["sha256"]) for i, layer in enumerate(bed["layers"]))
    elif stage in ("compose", "handoff"):
        rows.extend((f"slide.{page_id}", digest) for page_id, digest in slide_sources(job))
    return [{"slot": slot, "stage": "source", "digest": digest} for slot, digest in rows]


def slide_sources(job):
    """[(page id, SHA-256)] of every slide picture the job's pages show, in page order."""
    pages = (job["slides"] or {}).get("pages") or []
    return [(p["id"], p["show"]["slide"]["sha256"]) for p in pages if isinstance(p["show"], dict)]


# Nodes ---------------------------------------------------------------------------------------------------------
def selection(stage, segment, job):
    """(selected, reason) for one node."""
    if stage in AVATAR_STAGES:
        if job["avatar"] is None:
            return False, "no_avatar"
        if not segment["avatar"]:
            return False, "segment_avatar_off"
    if stage == "music" and job["music"] is None:
        return False, "no_music"
    if stage == "handoff" and not job["delivery"]["handoff"]:
        return False, "handoff_off"
    return True, None


def nodes_for(job):
    """[{id, stage, segment}] in topological order. Fan-out stages get one node per segment."""
    out = []
    for stage_id in ORDER:
        stage = BY_ID[stage_id]
        segments = job["segments"] if stage.fan_out else [None]
        for segment in segments:
            node_id = f"{stage_id}/{segment['id']}" if segment else stage_id
            out.append({"id": node_id, "stage": stage_id, "segment": segment})
    return out


def upstream(node, by_stage):
    """[(slot, upstream node, how)] for one node: how is 'digest' or a measurement field."""
    rows = []
    for up_stage, how in BY_ID[node["stage"]].depends_on:
        candidates = by_stage.get(up_stage, [])
        if how == "segment":
            candidates = [c for c in candidates if c["segment"] and c["segment"]["id"] == node["segment"]["id"]]
        for up in candidates:
            slot = up["id"].replace("/", ":")
            rows.append((slot, up, how.split(":", 1)[1] if how.startswith("measure:") else "digest"))
    return rows


def tool_for(stage, ctx, segment=None, records=None, job=None):
    if stage in AVATAR_STAGES:
        found = avatar_resolution(job, ctx) if job is not None else ctx.get("kitpip")
        return (found or {}).get("tool")
    name, version = TOOLS[stage]
    binary = None
    if stage == "voice" and segment is not None and records is not None:
        binary = engine_binary_sha256(records, records["jobs"].get(segment["narrateJob"]))
    return {"name": name, "version": version, "binary_sha256": binary}


# Planning ------------------------------------------------------------------------------------------------------
def plan(job, records, store, ctx):
    """The graph for a job: admit's verdict and one state, reason and key per node. Writes nothing.

    ctx: {"kitpip": kitpip.resolve() result or None, "pin": the kitpip pin or None, "vrm": vrm.resolve() result
    or None, "vrm_pin": the vrm pin or None, "ffmpeg": FFmpeg identity or None, "sources": set of SHA-256 digests
    in the private store, or None when no store is configured}. The avatar stages use the pin and resolution of
    the job's avatar.external.
    """
    avatar_state = (avatar_resolution(job, ctx) or {}).get("state")
    gate = admit_stage.admit(job, records, avatar_state if job["avatar"] is not None else None)
    nodes = nodes_for(job)
    by_stage = {}
    for node in nodes:
        selected, reason = selection(node["stage"], node["segment"], job)
        node.update(selected=selected, state=None, reason=reason, key=None, document=None, depends_on=[])
        if selected:
            by_stage.setdefault(node["stage"], []).append(node)
    current = store.current() if store is not None else {"stages": {}, "refusals": {}}
    sources = ctx.get("sources")
    for node in nodes:
        stage = node["stage"]
        if stage == "admit":
            node["state"], node["reason"] = (
                ("fresh", None)
                if gate["verdict"] == "Admitted"
                else ("refused", ",".join(r["code"] for r in gate["refusals"]))
            )
            continue
        if not node["selected"]:
            node["state"] = "not_selected"
            continue
        ups = upstream(node, by_stage)
        node["depends_on"] = [up["id"] for _, up, _ in ups]
        if gate["verdict"] != "Admitted":
            node["state"], node["reason"] = "blocked", "admit_refused"
            continue
        tool = tool_for(stage, ctx, node["segment"], records, job)
        if stage in AVATAR_STAGES and avatar_state != "resolved":
            node["state"], node["reason"] = "blocked", avatar_blocked(job, avatar_state)
            continue
        if stage in RENDER_STAGES and not ctx.get("ffmpeg"):
            node["state"], node["reason"] = "blocked", "ffmpeg_missing"
            continue
        node_sources = sources_for(stage, node["segment"], job, records)
        if sources is not None and any(row["digest"] not in sources for row in node_sources):
            node["state"], node["reason"] = "blocked", "source_missing"
            continue
        waiting = [up for _, up, _ in ups if up["state"] != "fresh"]
        if any(up["state"] in ("blocked", "refused") for up in waiting):
            node["state"], node["reason"] = "blocked", "upstream_blocked"
            continue
        if waiting:
            node["state"], node["reason"] = "stale", "upstream_stale"
            continue
        inputs = list(node_sources)
        for slot, up, how in ups:
            if how == "digest":
                inputs.append({"slot": slot, "stage": up["stage"], "digest": up["content_sha256"]})
            else:
                value = (up.get("measurements") or {}).get(how)
                inputs.append({"slot": f"{slot}.{how}", "stage": up["stage"], "value": value})
        pin = avatar_pin(job, ctx) if stage in AVATAR_STAGES else ctx.get("pin")
        knobs = knobs_for(stage, node["segment"], job, records, pin)
        document = keys.key_document(
            stage,
            node["segment"]["id"] if node["segment"] else None,
            IMPL[stage],
            tool,
            ctx.get("ffmpeg") if stage in RENDER_STAGES else None,
            knobs,
            job["edition"],
            inputs,
        )
        key = keys.stage_key(document)
        node["key"], node["document"] = key, document
        state, reason = store.freshness(node["id"], key) if store is not None else ("stale", "no_run")
        node["state"], node["reason"] = state, reason
        if state == "fresh":
            entry = current["stages"][node["id"]]
            manifest = store.manifest(node["id"])
            node["content_sha256"] = entry["content_sha256"]
            node["measurements"] = (manifest or {}).get("measurements", {})
            if stage == "deliver_check" and any(p["stage"] == "deliver_check" for p in gate["pending_operator"]):
                node["state"], node["reason"] = "pending_operator", "operator_gate_open"
    return acceptance.apply(graph_document(job, gate, nodes), acceptance.for_plan(store, nodes))


def graph_document(job, gate, nodes):
    rows = []
    for node in nodes:
        rows.append(
            {
                "id": node["id"],
                "stage": node["stage"],
                "segment": node["segment"]["id"] if node["segment"] else None,
                "state": node["state"],
                "reason": node["reason"],
                "key": node["key"],
                "key16": keys.key16(node["key"]) if node["key"] else None,
                "depends_on": node["depends_on"],
                "mapping": BY_ID[node["stage"]].mapping,
                "optional": BY_ID[node["stage"]].optional,
            }
        )
    fresh = {n["id"] for n in nodes if n["state"] in ("fresh", "pending_operator")}
    runnable = [
        n["id"]
        for n in nodes
        if n["state"] in ("stale", "corrupt") and n["key"] is not None and all(d in fresh for d in n["depends_on"])
    ]
    counts = {state: sum(1 for n in nodes if n["state"] == state) for state in STATES}
    return {
        "kind": "nv_graph",
        "schema_version": 1,
        "job_id": job["id"],
        "job_sha256": keys.digest(job),
        "edition": job["edition"],
        "planned_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "admit": gate,
        "nodes": rows,
        "counts": {k: v for k, v in counts.items() if v},
        "runnable": runnable,
        "pending_operator": gate["pending_operator"],
        "_documents": {n["id"]: n["document"] for n in nodes if n["document"] is not None},
    }


def public(graph):
    """The graph without key documents (what plan prints and graph.json holds)."""
    return {k: v for k, v in graph.items() if not k.startswith("_")}


# Explain -------------------------------------------------------------------------------------------------------
def diff(was, now, path=""):
    """[{field, was, now}] between two key documents. Inputs are matched by slot."""
    if isinstance(was, dict) and isinstance(now, dict):
        out = []
        for k in sorted(set(was) | set(now)):
            out.extend(diff(was.get(k), now.get(k), f"{path}.{k}" if path else k))
        return out
    if path == "inputs" and isinstance(was, list) and isinstance(now, list):
        return diff({i["slot"]: i for i in was}, {i["slot"]: i for i in now}, path)
    if keys.normalise(was) != keys.normalise(now):
        return [{"field": path, "was": was, "now": now}]
    return []


def explain(job, records, store, ctx, node_id):
    graph = plan(job, records, store, ctx)
    row = next((n for n in graph["nodes"] if n["id"] == node_id), None)
    if row is None:
        raise JobError(
            "node_unknown", f"{node_id} is not a node of {job['id']}: " + ", ".join(n["id"] for n in graph["nodes"])
        )
    document = graph["_documents"].get(node_id)
    last = store.manifest(node_id) if store is not None else None
    states = {n["id"]: n["state"] for n in graph["nodes"]}
    out = {
        "node": node_id,
        "state": row["state"],
        "reason": row["reason"],
        "key": row["key"],
        "key_document": document,
        "last": {"key": last["stage_key"], "dir": store.entry(node_id)["dir"]} if last else None,
        "waiting_on": [d for d in row["depends_on"] if states.get(d) not in ("fresh", "pending_operator")],
        "changed": None,
    }
    if document is not None and last is not None:
        out["changed"] = diff(last.get("key_document", {}), document)
    return out
