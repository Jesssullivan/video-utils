"""python -m narrate video {init,plan,run,stage,status,explain,verify,pin-check,fixture,intake,claims,accept,subject,
cut}.

The commands are docs/spec/NARRATED_VIDEO.md, "Commands".

Every command prints JSON with --json (status and explain always do) or a short table, and a typed refusal
{"ok": false, "refused": code, "detail": ...} on stderr with exit 1. Paths come from flags or the environment:

  --root       NARRATED_VIDEO_ROOT        the stage store root (default artifacts/narrated)
  --records    NARRATED_VIDEO_RECORDS     dhall-to-json renders of narrate jobs, voices, consents and music beds
  --externals  NARRATED_VIDEO_EXTERNALS   the private pin record of the avatar externals: KITPIP_BIN names the kitpip
                                          binary, VRM_RENDERER_BIN the VRM renderer
  --store      NARRATE_STORE              the private store; plan checks source digests only when one is named, and
                                          run and stage read every source from it
  --lexical    NARRATE_LEXICAL_DIR        the pinned xoxd-lexical release the script and voice stages read

plan never runs a stage and never writes, except graph.json with --record. run and stage run the lane L4, L5 and L6
stages (narrate/video/run.py) and record graph.json when they finish. `stage JOB voice --from-run RUN_DIR` adopts a
narrate run already rendered elsewhere (narrate render --prerendered) as the voice node instead of voicing it.
pin-check checks the private kitpip pin (or, with --external vrm, the VRM renderer pin) against its public
registration in program/externals.json and the binary against the pin. fixture writes a synthetic workspace (records,
store and lexical release) for `just nv-fixture`. init turns the kitpip avatar on by default for an edition that
allows one (NV-8), which needs --persona; --no-avatar turns it off.

accept records the operator's acceptance of one operator gate (listening or lip_sync) of the current deliver_check
render, and only with a Softproxy decision id (sp:dec:<ulid>) and the sha256 of the cut that decision saw: free text,
an empty value, a malformed id, a missing or other cut, a machine gate, the visible_text gate and an unknown gate
refuse (narrate/video/accept.py).

subject prints the guard subject of a job: every text its records hold that it voices or shows, which the Cade narrate
worker reads in its own process for the BS-21 guard and never logs. cut prints the current deliver_check render (the
composed video's sha256, the deliver_check key and digest), its machine gate states and the operator gates still
pending, digests and gate names only, and refuses machine_gates_failed when a machine gate failed
(narrate/video/subject.py).

intake and claims read a demo bundle (manifest.json, script.md, claims.json and its assets; docs/spec/NARRATED_VIDEO.md,
"Demo bundle intake"). claims runs the spoken-number claims gate alone. intake also checks every asset by digest,
writes one NarratedVideo record, one narrate job per beat and their sources, and refuses before writing anything when
a check fails. Both run the private-terms guard first: a manifest that declares ip_private or never_name needs
--denylist (or NARRATED_VIDEO_DENYLIST), the private denylist it binds by digest. --denylist-sha256 (or
NARRATED_VIDEO_DENYLIST_SHA256) pins that digest outside the bundle and marks the lane private. fixture --bundle
also writes a synthetic bundle.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .. import policy
from ..ir import sha256_file
from . import accept, bundle, fixture, graph, kitpip, private_terms, speech, store, subject, vrm
from . import run as runner
from .common import Env
from .job import CLIENT_DEFAULT_EDITION, EDITIONS, JobError, check_shape, init_job, load_records, read_json

RECORDS_ENV = "NARRATED_VIDEO_RECORDS"
DENYLIST_ENV = "NARRATED_VIDEO_DENYLIST"
PIN_HELP = (
    "the operator's pinned sha256 of the denylist, instead of NARRATED_VIDEO_DENYLIST_SHA256: the lane is private, so"
    " an undeclared bundle refuses and the file must hash to it, whatever the manifest says"
)
DENYLIST_HELP = (
    "the private denylist file (kind nv_denylist) that a manifest declaring ip_private or never_name binds by sha256,"
    " instead of NARRATED_VIDEO_DENYLIST; kept outside the bundle and outside git"
)


def emit(value):
    print(json.dumps(value, indent=1, sort_keys=True, ensure_ascii=False))


def refusal(code, detail):
    print(json.dumps({"ok": False, "refused": code, "detail": detail}, sort_keys=True), file=sys.stderr)
    return 1


def ffmpeg_identity():
    """sha256 of `ffmpeg -version`'s first line, or None when FFmpeg is absent. Render stages key on it."""
    binary = shutil.which(os.environ.get("FFMPEG", "ffmpeg"))
    if binary is None:
        return None
    try:
        done = subprocess.run([binary, "-version"], capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    first = done.stdout.splitlines()[0] if done.returncode == 0 and done.stdout else ""
    return hashlib.sha256(first.encode()).hexdigest() if first else None


def context(a):
    path = a.externals or os.environ.get(kitpip.EXTERNALS_ENV)
    pin, vrm_pin = kitpip.load_pin(path, required=False), vrm.load_pin(path)
    if path is not None and pin is None and vrm_pin is None:
        raise JobError("externals_invalid", "the externals record pins neither kitpip nor a vrm renderer")
    store_dir = a.store or os.environ.get("NARRATE_STORE")
    sources = set(policy.store_index(store_dir)) if store_dir else None
    return {
        "pin": pin,
        "kitpip": kitpip.resolve(pin),
        "vrm_pin": vrm_pin,
        "vrm": vrm.resolve(vrm_pin),
        "ffmpeg": ffmpeg_identity(),
        "sources": sources,
    }


def job_store(a, job_id):
    return store.JobStore(a.root or os.environ.get(store.ROOT_ENV) or store.DEFAULT_ROOT, job_id)


def records_for(a, job=None):
    """The records. When they come from a guarded intake (or the lane is private), job must be the NarratedVideo
    record that intake wrote (private_terms.check_job), so an edit to its persona label or segments refuses."""
    directory = a.records or os.environ.get(RECORDS_ENV)
    records = load_records(directory)
    private_terms.check_job(directory, job)
    return records


def table(g):
    lines = [f"{g['job_id']}  edition {g['edition']}  admit {g['admit']['verdict']}"]
    for r in g["admit"]["refusals"]:
        lines.append(f"  refused {r['code']}: {r['detail']}")
    width = max(len(n["id"]) for n in g["nodes"])
    for n in g["nodes"]:
        reason = f"  ({n['reason']})" if n["reason"] else ""
        lines.append(f"{n['id']:<{width}}  {n['state']:<16} {n['key16'] or '-':<16}{reason}")
    for p in g["pending_operator"]:
        lines.append(f"pending_operator {p['gate']} at {p['stage']}" + (f"/{p['segment']}" if p["segment"] else ""))
    return "\n".join(lines)


def cmd_init(a):
    records = load_records(a.records or os.environ.get(RECORDS_ENV))
    defaults_flags = [
        f"--{n.replace('_', '-')}"
        for n in ("narrate_job", "script", "voice", "still", "card", "bed", "edition", "persona")
        if getattr(a, n) is not None
    ]
    switches = [f"--{n.replace('_', '-')}" for n in ("avatar", "no_avatar", "client") if getattr(a, n)]
    if a.from_file and (defaults_flags or switches):
        return refusal(
            "usage",
            "--from takes the rendered record as it is; drop " + ", ".join(defaults_flags + switches),
        )
    if a.from_file:
        value = read_json(a.from_file, "job")
        if isinstance(value, list):
            value = next((v for v in value if isinstance(v, dict) and v.get("id") == a.job), None)
            if value is None:
                return refusal("job_invalid", f"{a.from_file} holds no record with id {a.job}")
        job = check_shape(value)
        if job["id"] != a.job:
            return refusal("job_invalid", "the record's id is not --job")
    else:
        if not (a.narrate_job and a.script):
            return refusal("usage", "init needs --from FILE, or --narrate-job and --script")
        narrate_job = records["jobs"].get(a.narrate_job)
        if narrate_job is None:
            return refusal("narrate_job_missing", f"narrate job {a.narrate_job} is unknown")
        if a.voice and a.voice != narrate_job["voice"]:
            return refusal("voice_mismatch", f"narrate job {a.narrate_job} reads in voice {narrate_job['voice']}")
        script = Path(a.script)
        if script.is_symlink() or not script.is_file():
            return refusal("input_invalid", "--script is not a regular file")
        job = init_job(
            a.job,
            a.narrate_job,
            sha256_file(script),
            still=a.still,
            colour=a.card,
            bed=a.bed,
            edition=a.edition,
            avatar=True if a.avatar else False if a.no_avatar else None,
            persona=a.persona,
            client=a.client,
        )
    records = records_for(a, job)
    s = job_store(a, a.job)
    ctx = context(a)
    g = graph.plan(job, records, None, ctx)
    if g["admit"]["verdict"] != "Admitted":
        first = g["admit"]["refusals"][0]
        detail = first["detail"]
        if first["code"] == "persona_label_missing" and not (a.from_file or a.avatar):
            detail += "; the avatar is on by default (NV-8): pass --persona P, or --no-avatar"
        return refusal(first["code"], detail)
    s.write_job(job, replace=a.replace)
    g = graph.public(graph.plan(job, records, s, ctx))
    s.write_graph(g)
    if a.json:
        emit(
            {
                "ok": True,
                "job_id": job["id"],
                "job_sha256": g["job_sha256"],
                "graph": "graph.json",
                "counts": g["counts"],
            }
        )
    else:
        print(table(g))
    return 0


def cmd_plan(a):
    s = job_store(a, a.job)
    job = s.read_job()
    g = graph.public(graph.plan(job, records_for(a, job), s, context(a)))
    if a.record:
        s.write_graph(g)
    if a.json:
        emit(g)
    else:
        print(table(g))
    return 0 if g["admit"]["verdict"] == "Admitted" else 1


def run_env(a, records):
    store_dir = a.store or os.environ.get("NARRATE_STORE")
    if not store_dir or not Path(store_dir).is_dir():
        raise JobError("store_missing", "run reads every source from the private store: pass --store or NARRATE_STORE")
    records_dir = a.records or os.environ.get(RECORDS_ENV)
    return Env(records_dir, records, store_dir, a.lexical or os.environ.get("NARRATE_LEXICAL_DIR"))


def run_common(a, only=None, from_run=None):
    s = job_store(a, a.job)
    job = s.read_job()
    records = records_for(a, job)
    env = run_env(a, records)
    ctx = context(a)
    rc = runner.RunContext(job, records, s, ctx, env, from_run=from_run)
    stages = [x for x in (a.stages or "").split(",") if x] if only is None else None
    forced = [x for x in (a.force or "").split(",") if x] if only is None else []
    if from_run is not None and getattr(a, "replace", False):
        # check RUN_DIR in place first: a run that would be refused never costs the node it would replace
        problem, _ = checked(rc, only, from_run)
        if problem is not None:
            return refusal(*problem)
        s.clear_refusal(only)
        s.archive(only)
    result, g = runner.run(rc, stages=stages, until=None if only else a.until, forced=forced, only=only)
    if from_run is not None and result["ok"]:
        problem = adoption(rc, only, from_run, result)
        if problem is not None:
            s.write_graph(graph.public(g))
            return refusal(*problem)
    s.write_graph(graph.public(g))
    if a.json:
        emit(result)
    else:
        print(table(graph.public(g)))
        for row in result["ran"]:
            print(f"ran {row['node']} {row['key16']}" + (f" refused {row['refused']}" if "refused" in row else ""))
        if "refused" in result:
            print(f"refused {result['refused']} at {result['node']}: {result['detail']}")
    return 0 if result["ok"] else 1


def checked(rc, node, from_run):
    """(problem, manifest): every adoption check run on RUN_DIR in place (speech.check_adoptable), problem a
    (code, detail) refusal or None."""
    try:
        return None, speech.check_adoptable(rc, node.partition("/")[2], from_run)
    except JobError as exc:
        return (exc.code, exc.detail), None


def adoption(rc, node, from_run, result):
    """After `stage JOB voice --from-run RUN_DIR`: record what the voice node now holds in result["adopted"], or
    (code, detail) when it was already fresh with another narrate run (pass --replace to adopt this one), or when
    RUN_DIR, the run it already holds, no longer passes the adoption checks."""
    s = rc.store
    manifest = s.manifest(node) or {}
    have = (manifest.get("measurements") or {}).get("narrate_content_sha256")
    adopted = (manifest.get("measurements") or {}).get("adopted")
    if not any(row["node"] == node for row in result["ran"]):
        try:
            want = json.loads((Path(from_run) / "manifest.json").read_text(encoding="utf-8")).get("content_sha256")
        except (OSError, UnicodeDecodeError, ValueError, AttributeError):
            return "voice_run_manifest_missing", "the run has no readable manifest.json"
        if have != want:
            return "voice_already_fresh", f"{node} is fresh with another narrate run; pass --replace to adopt this one"
        # the node is unharmed either way, but exit 0 says RUN_DIR itself passed the checks
        problem, _ = checked(rc, node, from_run)
        if problem is not None:
            return problem
    result["adopted"] = {
        "node": node,
        "run_id": (adopted or {}).get("run_id"),
        "content_sha256": have,
        "state": "adopted" if adopted else "rendered_here",
    }
    return None


def cmd_run(a):
    return run_common(a)


def cmd_stage(a):
    if a.from_run is None and a.replace:
        return refusal("usage", "--replace goes with --from-run")
    if a.from_run is not None:
        if a.stage != "voice":
            return refusal("usage", "--from-run adopts a narrate run as a voice node only")
        if a.segment is None:
            segments = job_store(a, a.job).read_job()["segments"]
            if len(segments) != 1:
                return refusal("usage", f"{a.job} has {len(segments)} segments: name one with --segment")
            a.segment = segments[0]["id"]
    node = f"{a.stage}/{a.segment}" if a.segment else a.stage
    return run_common(a, only=node, from_run=a.from_run)


def cmd_fixture(a):
    out = Path(a.out)
    if out.exists() and any(out.iterdir()):
        return refusal("fixture_exists", "--out must be a new or empty directory")
    paths = fixture.write(out)
    if a.bundle:
        paths["bundle"] = fixture.write_bundle(out / "bundle")
    emit({"ok": True, "narrate_job": fixture.NARRATE_JOB, "bed": fixture.BED} | {k: str(v) for k, v in paths.items()})
    return 0


def cmd_intake(a):
    records_dir = a.records or os.environ.get(RECORDS_ENV)
    if not records_dir:
        return refusal("records_missing", "no records directory: pass --records or set NARRATED_VIDEO_RECORDS")
    if not (a.persona or a.no_avatar):
        return refusal("persona_label_missing", "the avatar is on by default (NV-8): pass --persona P, or --no-avatar")
    if a.tail_s is not None and not 0 <= a.tail_s <= 60:
        return refusal("knob_out_of_bounds", "--tail-s is 0 to 60 seconds")
    manifest = bundle.intake(
        a.bundle,
        a.out,
        records_dir,
        job_id=a.job,
        template=a.narrate_template,
        voice=a.voice,
        engine=a.engine,
        persona=a.persona,
        tail_s=a.tail_s,
        store=a.store,
        denylist=denylist(a),
        pin=a.denylist_sha256,
    )
    summary = {
        "ok": True,
        "job_id": manifest["job_id"],
        "job_sha256": manifest["job_sha256"],
        "segments": [
            {"segment": s["segment"], "show": s["show"], "claims": s["claims"]["status"]} for s in manifest["segments"]
        ],
        "unused_assets": manifest["unused_assets"],
    }
    emit(manifest if a.json else summary)
    return 0


def denylist(a):
    """The private denylist file: --denylist, else NARRATED_VIDEO_DENYLIST, else None."""
    return a.denylist or os.environ.get(DENYLIST_ENV) or None


def cmd_claims(a):
    result = bundle.claims_only(a.bundle, denylist(a), a.denylist_sha256)
    emit(result)
    if result["ok"]:
        return 0
    refused = bundle.gate_refusal(result["segments"])
    return refusal(refused.code, refused.detail)


def cmd_status(a):
    s = job_store(a, a.job)
    g = accept.check_recorded(s, s.read_graph())
    if a.json:
        emit(g)
    else:
        print(table(g))
    return 0


def cmd_explain(a):
    s = job_store(a, a.job)
    node = f"{a.stage}/{a.segment}" if a.segment else a.stage
    job = s.read_job()
    emit(graph.explain(job, records_for(a, job), s, context(a), node))
    return 0


def cmd_accept(a):
    emit(accept.accept(job_store(a, a.job), a.gate, a.decision, a.video_sha256))
    return 0


def cmd_subject(a):
    s = job_store(a, a.job)
    job = s.read_job()
    records = records_for(a, job)
    emit(subject.subject(job, records, run_env(a, records), s))
    return 0


def cmd_cut(a):
    s = job_store(a, a.job)
    emit(subject.cut(s, s.read_job()))
    return 0


def cmd_pin_check(a):
    path = a.externals or os.environ.get(kitpip.EXTERNALS_ENV)
    if getattr(a, "external", "kitpip") == "vrm":
        result = vrm.pin_check(vrm.load_pin(path))
        prefix, missing = "vrm", "vrm_renderer_missing"
    else:
        result = kitpip.pin_check(kitpip.load_pin(path))
        prefix, missing = "kitpip", "kitpip_missing"
    if result["ok"]:
        emit(result)
        return 0
    code = {
        "unregistered": f"{prefix}_pin_missing",
        "pending": f"{prefix}_pin_pending",
        "mismatch": f"{prefix}_pin_mismatch",
    }
    return refusal(code.get(result["state"], missing), result["detail"])


def cmd_verify(a):
    path = Path(a.dir)
    if (path / store.MANIFEST).is_file():
        problems = {path.name: store.verify_stage_dir(path)}
    elif (path / "job.json").is_file():
        problems = store.JobStore(path.parent, path.name).verify()
    else:
        return refusal("verify_target_invalid", "DIR is neither a stage directory nor a job directory")
    ok = not any(problems.values())
    emit({"ok": ok, "problems": problems})
    return 0 if ok else 1


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="narrate video", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="command", required=True)

    def common(r, job=True):
        if job:
            r.add_argument("job", help="the job id (artifacts/narrated/<job_id>/)")
        r.add_argument("--root", help="the stage store root, instead of NARRATED_VIDEO_ROOT or artifacts/narrated")
        r.add_argument("--records", help="the records directory, instead of NARRATED_VIDEO_RECORDS")
        r.add_argument("--externals", help="the kitpip pin record, instead of NARRATED_VIDEO_EXTERNALS")
        r.add_argument("--store", help="the private store for source digests, instead of NARRATE_STORE")
        r.add_argument("--lexical", help="the pinned xoxd-lexical release, instead of NARRATE_LEXICAL_DIR")
        r.add_argument("--json", action="store_true", help="print JSON")

    i = sub.add_parser("init", help="write a job into the store from the defaults, or from a dhall-to-json render")
    common(i, job=False)
    i.add_argument("--job", required=True, help="the job id")
    i.add_argument("--from", dest="from_file", help="a NarratedVideo record (or a list of them) as JSON")
    i.add_argument("--narrate-job", help="the narrate job record id that voices the script")
    i.add_argument("--script", help="the script file; its SHA-256 must be the narrate job's inputSha256")
    i.add_argument("--voice", help="check that the narrate job reads in this voice")
    picture = i.add_mutually_exclusive_group()
    picture.add_argument("--still", help="the still's SHA-256 in the private store")
    picture.add_argument("--card", help="a #rrggbb colour card (default #101820)")
    i.add_argument("--bed", help="a music bed record id")
    i.add_argument("--edition", choices=EDITIONS, help="the edition (default Internal, NV-2)")
    i.add_argument(
        "--client",
        action="store_true",
        help=f"a client delivery: edition {CLIENT_DEFAULT_EDITION} (NV-6). ClientVoiceOnly comes only through --from",
    )
    switch = i.add_mutually_exclusive_group()
    switch.add_argument(
        "--avatar", action="store_true", help="turn the kitpip avatar on (the default where the edition allows one)"
    )
    switch.add_argument("--no-avatar", action="store_true", help="turn the kitpip avatar off")
    i.add_argument("--persona", help="labels.persona (required while the avatar is on)")
    i.add_argument("--replace", action="store_true", help="replace a different job with the same id")

    n = sub.add_parser("plan", help="key every stage and print its state; read-only")
    common(n)
    n.add_argument("--record", action="store_true", help="also write graph.json for status")

    r = sub.add_parser("run", help="run the stale stages (script to handoff); stops at the first refusal")
    common(r)
    r.add_argument("--stages", help="comma-separated stages: run only these")
    r.add_argument("--until", choices=[st.id for st in graph.STAGES], help="run this stage and what it depends on")
    r.add_argument("--force", help="comma-separated stages to rerun although fresh (archived to history/)")

    g = sub.add_parser("stage", help="run one stage node when its inputs are fresh")
    common(g)
    g.add_argument("stage", choices=[st.id for st in graph.STAGES])
    g.add_argument("--segment", help="the segment of a fan-out stage")
    g.add_argument(
        "--from-run",
        metavar="RUN_DIR",
        help="voice only: adopt this already rendered narrate run (narrate render --prerendered) instead of voicing; "
        "it is copied in, re-verified and bound to the voice key. The segment defaults to the job's only one",
    )
    g.add_argument(
        "--replace", action="store_true", help="with --from-run: archive a fresh voice node to history/ first"
    )

    f = sub.add_parser("fixture", help="write a synthetic workspace: records, a private store and a lexical release")
    f.add_argument("--out", required=True, help="a new or empty directory outside git")
    f.add_argument("--bundle", action="store_true", help="also write a synthetic demo bundle under OUT/bundle/")

    t = sub.add_parser("intake", help="a demo bundle to a NarratedVideo job and its narrate jobs, claims gated")
    t.add_argument("bundle", help="the bundle directory (manifest.json, script.md, claims.json, assets)")
    t.add_argument("--out", required=True, help="a new or empty directory: the job, records and intake.json")
    t.add_argument("--records", help="the records directory, instead of NARRATED_VIDEO_RECORDS")
    t.add_argument("--store", help="where the beat scripts and assets go by digest (default OUT/store)")
    t.add_argument("--job", help="the job id (default the bundle directory's name)")
    t.add_argument(
        "--narrate-template",
        required=True,
        help="a narrate job record whose lexical pin, pronunciation"
        " table, scope, gates and post settings every beat's narrate job copies",
    )
    t.add_argument("--voice", required=True, help="the voice record id every beat reads in")
    t.add_argument("--engine", required=True, help="the engine record id; it must allow a confidential job")
    avatar = t.add_mutually_exclusive_group()
    avatar.add_argument("--persona", help="turn the kitpip avatar on with this labels.persona")
    avatar.add_argument("--no-avatar", action="store_true", help="no kitpip avatar")
    t.add_argument("--tail-s", type=float, help="seconds a card base holds after the last narration (default 1)")
    t.add_argument("--json", action="store_true", help="print the whole intake manifest")
    t.add_argument("--denylist", help=DENYLIST_HELP)
    t.add_argument("--denylist-sha256", help=PIN_HELP)

    c = sub.add_parser("claims", help="the spoken-number claims gate of a demo bundle, alone")
    c.add_argument("bundle", help="the bundle directory (script.md, claims.json and the manifest's privacy are read)")
    c.add_argument("--denylist", help=DENYLIST_HELP)
    c.add_argument("--denylist-sha256", help=PIN_HELP)

    s = sub.add_parser("status", help="print the recorded graph.json and its pending operator gates")
    common(s)

    e = sub.add_parser("explain", help="print a stage's key inputs and what changed since its last run")
    common(e)
    e.add_argument("stage", choices=[st.id for st in graph.STAGES])
    e.add_argument("--segment", help="the segment of a fan-out stage")

    v = sub.add_parser("verify", help="re-hash a stage directory or every current stage of a job")
    v.add_argument("dir")

    acc = sub.add_parser(
        "accept",
        help="record the operator's acceptance of one operator gate of the current cut, by Softproxy decision id",
    )
    acc.add_argument("job", help="the job id (artifacts/narrated/<job_id>/)")
    acc.add_argument("--root", help="the stage store root, instead of NARRATED_VIDEO_ROOT or artifacts/narrated")
    acc.add_argument("--gate", help="the operator gate: " + " or ".join(accept.ACCEPTABLE))
    acc.add_argument("--decision", help="the Softproxy decision id of the operator's accept: sp:dec:<ulid>, only")
    acc.add_argument(
        "--video-sha256",
        help="the sha256 of the cut the decision saw (required: video_sha256_missing without it, video_mismatch when "
        "it is not the current composed video)",
    )
    acc.add_argument("--json", action="store_true", help="print JSON (accept always does)")

    sj = sub.add_parser(
        "subject", help="print every text the job voices or shows, for the BS-21 guard; the caller never logs it"
    )
    common(sj)
    cu = sub.add_parser("cut", help="print the current cut's digests and the operator gates still pending")
    cu.add_argument("job", help="the job id (artifacts/narrated/<job_id>/)")
    cu.add_argument("--root", help="the stage store root, instead of NARRATED_VIDEO_ROOT or artifacts/narrated")
    cu.add_argument("--json", action="store_true", help="print JSON (cut always does)")

    k = sub.add_parser("pin-check", help="check an avatar external's pin against program/externals.json and its binary")
    k.add_argument("--externals", help="the private pin record, instead of NARRATED_VIDEO_EXTERNALS")
    k.add_argument(
        "--external",
        choices=("kitpip", "vrm"),
        default="kitpip",
        help="which pin to check: kitpip (KITPIP_BIN, the default) or vrm (VRM_RENDERER_BIN)",
    )

    a = p.parse_args(argv)
    try:
        commands = {
            "init": cmd_init,
            "plan": cmd_plan,
            "run": cmd_run,
            "stage": cmd_stage,
            "fixture": cmd_fixture,
            "status": cmd_status,
            "explain": cmd_explain,
            "verify": cmd_verify,
            "pin-check": cmd_pin_check,
            "intake": cmd_intake,
            "claims": cmd_claims,
            "accept": cmd_accept,
            "subject": cmd_subject,
            "cut": cmd_cut,
        }
        return commands[a.command](a)
    except bundle.BundleError as exc:
        if isinstance(exc.report, dict):
            emit({"ok": False, "private_terms": exc.report})
        elif exc.report is not None:
            emit({"ok": False, "segments": exc.report})
        return refusal(exc.code, exc.detail)
    except JobError as exc:
        return refusal(exc.code, exc.detail)
    except policy.Refused as exc:
        return refusal(exc.code, exc.detail)


if __name__ == "__main__":
    sys.exit(main())
