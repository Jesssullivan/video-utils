"""python -m narrate video {init,plan,run,stage,status,explain,verify,pin-check,fixture}.

The commands are docs/spec/NARRATED_VIDEO.md, "Commands".

Every command prints JSON with --json (status and explain always do) or a short table, and a typed refusal
{"ok": false, "refused": code, "detail": ...} on stderr with exit 1. Paths come from flags or the environment:

  --root       NARRATED_VIDEO_ROOT        the stage store root (default artifacts/narrated)
  --records    NARRATED_VIDEO_RECORDS     dhall-to-json renders of narrate jobs, voices, consents and music beds
  --externals  NARRATED_VIDEO_EXTERNALS   the private kitpip pin record; KITPIP_BIN names the binary
  --store      NARRATE_STORE              the private store; plan checks source digests only when one is named, and
                                          run and stage read every source from it
  --lexical    NARRATE_LEXICAL_DIR        the pinned xoxd-lexical release the script and voice stages read

plan never runs a stage and never writes, except graph.json with --record. run and stage run the lane L4 and L5
stages (narrate/video/run.py) and record graph.json when they finish. pin-check checks the private kitpip pin
against its public registration in program/externals.json and KITPIP_BIN against the pin. fixture writes a
synthetic workspace (records, store and lexical release) for `just nv-fixture`.
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
from . import fixture, graph, kitpip, store
from . import run as runner
from .common import Env
from .job import CLIENT_DEFAULT_EDITION, EDITIONS, JobError, check_shape, init_job, load_records, read_json

RECORDS_ENV = "NARRATED_VIDEO_RECORDS"


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
    pin = kitpip.load_pin(a.externals or os.environ.get(kitpip.EXTERNALS_ENV))
    store_dir = a.store or os.environ.get("NARRATE_STORE")
    sources = set(policy.store_index(store_dir)) if store_dir else None
    return {"pin": pin, "kitpip": kitpip.resolve(pin), "ffmpeg": ffmpeg_identity(), "sources": sources}


def job_store(a, job_id):
    return store.JobStore(a.root or os.environ.get(store.ROOT_ENV) or store.DEFAULT_ROOT, job_id)


def records_for(a):
    return load_records(a.records or os.environ.get(RECORDS_ENV))


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
    records = records_for(a)
    defaults_flags = [
        f"--{n.replace('_', '-')}"
        for n in ("narrate_job", "script", "voice", "still", "card", "bed", "edition", "persona")
        if getattr(a, n) is not None
    ]
    switches = [f"--{n}" for n in ("avatar", "client") if getattr(a, n)]
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
            avatar=a.avatar,
            persona=a.persona,
            client=a.client,
        )
    s = job_store(a, a.job)
    ctx = context(a)
    g = graph.plan(job, records, None, ctx)
    if g["admit"]["verdict"] != "Admitted":
        first = g["admit"]["refusals"][0]
        return refusal(first["code"], first["detail"])
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
    g = graph.public(graph.plan(s.read_job(), records_for(a), s, context(a)))
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


def run_common(a, only=None):
    s = job_store(a, a.job)
    job, records = s.read_job(), records_for(a)
    env = run_env(a, records)
    ctx = context(a)
    rc = runner.RunContext(job, records, s, ctx, env)
    stages = [x for x in (a.stages or "").split(",") if x] if only is None else None
    forced = [x for x in (a.force or "").split(",") if x] if only is None else []
    result, g = runner.run(rc, stages=stages, until=None if only else a.until, forced=forced, only=only)
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


def cmd_run(a):
    return run_common(a)


def cmd_stage(a):
    return run_common(a, only=f"{a.stage}/{a.segment}" if a.segment else a.stage)


def cmd_fixture(a):
    out = Path(a.out)
    if out.exists() and any(out.iterdir()):
        return refusal("fixture_exists", "--out must be a new or empty directory")
    paths = fixture.write(out)
    emit({"ok": True, "narrate_job": fixture.NARRATE_JOB, "bed": fixture.BED} | {k: str(v) for k, v in paths.items()})
    return 0


def cmd_status(a):
    g = job_store(a, a.job).read_graph()
    if a.json:
        emit(g)
    else:
        print(table(g))
    return 0


def cmd_explain(a):
    s = job_store(a, a.job)
    node = f"{a.stage}/{a.segment}" if a.segment else a.stage
    emit(graph.explain(s.read_job(), records_for(a), s, context(a), node))
    return 0


def cmd_pin_check(a):
    pin = kitpip.load_pin(a.externals or os.environ.get(kitpip.EXTERNALS_ENV))
    result = kitpip.pin_check(pin)
    if result["ok"]:
        emit(result)
        return 0
    code = {"unregistered": "kitpip_pin_missing", "pending": "kitpip_pin_pending", "mismatch": "kitpip_pin_mismatch"}
    return refusal(code.get(result["state"], "kitpip_missing"), result["detail"])


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
    i.add_argument("--avatar", action="store_true", help="turn the kitpip avatar on (needs --persona)")
    i.add_argument("--persona", help="labels.persona")
    i.add_argument("--replace", action="store_true", help="replace a different job with the same id")

    n = sub.add_parser("plan", help="key every stage and print its state; read-only")
    common(n)
    n.add_argument("--record", action="store_true", help="also write graph.json for status")

    r = sub.add_parser("run", help="run the stale stages (lanes L4 and L5); stops at the first refusal")
    common(r)
    r.add_argument("--stages", help="comma-separated stages: run only these")
    r.add_argument("--until", choices=[st.id for st in graph.STAGES], help="run this stage and what it depends on")
    r.add_argument("--force", help="comma-separated stages to rerun although fresh (archived to history/)")

    g = sub.add_parser("stage", help="run one stage node when its inputs are fresh")
    common(g)
    g.add_argument("stage", choices=[st.id for st in graph.STAGES])
    g.add_argument("--segment", help="the segment of a fan-out stage")

    f = sub.add_parser("fixture", help="write a synthetic workspace: records, a private store and a lexical release")
    f.add_argument("--out", required=True, help="a new or empty directory outside git")

    s = sub.add_parser("status", help="print the recorded graph.json and its pending operator gates")
    common(s)

    e = sub.add_parser("explain", help="print a stage's key inputs and what changed since its last run")
    common(e)
    e.add_argument("stage", choices=[st.id for st in graph.STAGES])
    e.add_argument("--segment", help="the segment of a fan-out stage")

    v = sub.add_parser("verify", help="re-hash a stage directory or every current stage of a job")
    v.add_argument("dir")

    k = sub.add_parser("pin-check", help="check the kitpip pin against program/externals.json and KITPIP_BIN")
    k.add_argument("--externals", help="the kitpip pin record, instead of NARRATED_VIDEO_EXTERNALS")

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
        }
        return commands[a.command](a)
    except JobError as exc:
        return refusal(exc.code, exc.detail)
    except policy.Refused as exc:
        return refusal(exc.code, exc.detail)


if __name__ == "__main__":
    sys.exit(main())
