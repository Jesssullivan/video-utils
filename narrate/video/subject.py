"""The guard subject and the current cut of a narrated-video job (docs/spec/NARRATED_VIDEO.md, "Guard subject and
cut", Linear TIN-7788, SPR-220).

The Cade narrate worker runs the BS-21 guard (xoxd-ai/cade src/bs21-guard.ts) before any task that voices, shows or
renders a text. That guard needs the texts themselves, and Hatchet carries job ids only, so the worker reads them
here, inside its own process, and never hands them to Hatchet, a log or a receipt.

texts(job, records, env, store) lists every text that the job's own records hold and that the job voices or labels,
in a fixed order:

  narration    each segment's written text, read as the script stage reads it (narrate.spoken.lines of its script
               through its narrate job's input adapter). The captions show it
  spoken       the same segment's text as the voice says it: render.chunk_spoken with the Normaliser render.py builds
               from the narrate job's pronunciation table and its pinned upstream table. A substitution can say what
               the written text does not, so the guard reads both forms
  title        the job id, then each segment id, then each slide page id. description.txt and chapters.json show them
  caption      labels.personaCue, which compose puts above the first cue
  description  labels.extraNotice, the last line of description.txt
  label        labels.persona, which every stage manifest from place on carries
  visible_text the strings each shown asset draws, one text per asset, from the source a guarded intake stored

The worker reads the visible_text rows like any other, so the BS-21 name list reads what a slide shows, and a name
need not be on the nv denylist for a slide to refuse it. Those rows come from the stored source, by the digest the
records marker binds (private_terms.VISIBLE_KIND, bundle.visible_source), never from a pixel.

subject fails closed. It refuses shown_text_unread when a job shows an asset and any of its text is unreadable: the
records carry no guarded intake's marker, a shown asset is unread or opaque, the marker binds no stored source, or
that source is missing from the store or malformed. This holds at any edition, and unlike deliver_check's
visible_text gate no operator acceptance closes it: only a re-intake does. A card base with no slide page shows no
asset.

cut(store, job) is the current deliver_check render as accept.render_of binds it: the composed video's sha256, the
deliver_check stage key and content digest, the machine gate states, deliver_check's internal-review flag and the
operator gates still pending. It holds digests and gate names only, so the Cade worker can ask Jess about that cut,
and `nv accept` later checks the same digest. deliver_check records a failed machine gate as a state, not a refusal
(narrate/video/deliver.py delivery_gate), so cut refuses machine_gates_failed for it: a cut that failed flash,
loudness, profile or captions never reaches Jess as an ordinary request for a decision.
"""

import json
from types import SimpleNamespace

from .. import adapters, lexical, render, spoken
from ..adapters import InputError
from ..normalise import NormaliseError, Normaliser
from . import accept, private_terms
from .common import StageRefused, work_dir
from .compose import page_kind
from .deliver import visible_gate
from .job import JobError
from .speech import script_copy

# xoxd-ai/cade src/bs21-guard.ts MAX_TEXTS and MAX_TEXT: the guard refuses a larger subject, so this refuses first.
# The guard measures a text with JavaScript's String.length, in UTF-16 code units, so MAX_TEXT counts those units.
MAX_TEXTS = 4096
MAX_TEXT = 200_000
LABEL_FIELDS = (("personaCue", "caption"), ("extraNotice", "description"), ("persona", "label"))
# deliver.py's machine gate states. A passed or not_applicable gate lets the cut go to internal review.
MACHINE_STATES = ("passed", "failed", "not_applicable")
MACHINE_OK = ("passed", "not_applicable")


def utf16_units(text):
    """The length of text as JavaScript's String.length reads it: one unit per BMP code point, two per astral one."""
    return len(text.encode("utf-16-le", "surrogatepass")) // 2


def said(records, env, segment, narrate_job, script):
    """What the voice says of one segment's script: render.py's normaliser and chunks, one chunk per line."""
    table = records["pronunciation"].get(narrate_job.get("pronunciation"))
    if table is None:
        raise JobError("pronunciation_unknown", f"segment {segment['id']}'s pronunciation table has no record")
    try:
        release = lexical.Release(env.lexical, narrate_job["lexical"])
    except lexical.LexicalError as exc:
        raise JobError(exc.code, exc.detail) from None
    normaliser = Normaliser(table, upstream=release.upstream_pronunciation)
    limit = int(narrate_job["chunkMaxCodepoints"])
    try:
        chunks = [text for part in script.segments for _, text in render.chunk_spoken(part, limit, normaliser)]
    except NormaliseError:
        # A pronunciation refusal quotes the entry and may quote a segment's text: name the segment only.
        raise JobError("pronunciation_refused", f"segment {segment['id']} has no spoken form") from None
    except ValueError:
        raise JobError("input_invalid", f"segment {segment['id']}'s script does not chunk") from None
    return "\n".join(chunks) + "\n"


def voiced(records, env, segment, store):
    """(narration, spoken): one segment's written text, read as the script stage reads it (narrate/video/speech.py
    run_script), and the same text as the voice says it."""
    narrate_job = records["jobs"].get(segment["narrateJob"])
    if narrate_job is None:
        raise JobError("records_invalid", f"segment {segment['id']} names no narrate job in the records")
    with work_dir(store) as work:
        try:
            path = script_copy(SimpleNamespace(env=env), segment, narrate_job["input"], work)
            script = adapters.load(narrate_job["input"], path)
            written = spoken.lines(script)
        except StageRefused as exc:
            raise JobError(exc.code, exc.detail) from None
        except (InputError, NormaliseError, UnicodeDecodeError, ValueError):
            # A parser error can quote a line of the script, and a refusal goes to stderr: name the segment only.
            raise JobError("input_invalid", f"segment {segment['id']}'s script does not load") from None
    return written, said(records, env, segment, narrate_job, script)


def texts(job, records, env, store, shown=()):
    """[{field, text}] for every text the job's records hold that it voices, labels or, through shown (the rows of
    shown_texts), shows, in the module's order."""
    read = [voiced(records, env, s, store) for s in job["segments"]]
    out = [{"field": "narration", "text": written} for written, _ in read]
    out += [{"field": "spoken", "text": text} for _, text in read]
    pages = (job.get("slides") or {}).get("pages") or []
    titles = [job["id"], *(s["id"] for s in job["segments"]), *(p["id"] for p in pages)]
    out += [{"field": "title", "text": t} for t in titles]
    for key, field in LABEL_FIELDS:
        value = job["labels"][key]
        if isinstance(value, str) and value:
            out.append({"field": field, "text": value})
    out += shown
    if len(out) > MAX_TEXTS or any(utf16_units(t["text"]) > MAX_TEXT for t in out):
        raise JobError("subject_too_large", f"the guard reads at most {MAX_TEXTS} texts of {MAX_TEXT} UTF-16 units")
    return out


def shown_assets(job):
    """The kinds of asset the job puts on screen, each of which can show text no subject field holds."""
    kinds = sorted(set(job["base"]) - {"card"})
    pages = (job.get("slides") or {}).get("pages") or []
    return kinds + (["slide"] if any(page_kind(p) == "slide" for p in pages) else [])


def stored_rows(digest, env):
    """The visible_text rows of the stored source with this digest. The store index hashes each file, so a changed
    file has no entry. Refuses shown_text_unread, naming no text from the source."""
    unread = JobError(
        "shown_text_unread", "the stored visible-text source is missing or malformed; run the intake again"
    )
    try:
        data = env.source(digest, "the stored visible text").read_bytes()
        document = json.loads(data.decode("utf-8"))
    except (StageRefused, OSError, UnicodeDecodeError, ValueError):
        raise unread from None
    rows = document.get("texts") if isinstance(document, dict) else None
    well_formed = (
        isinstance(rows, list)
        and document.get("kind") == private_terms.VISIBLE_KIND
        and document.get("schema_version") == private_terms.VISIBLE_VERSION
        and all(isinstance(r, dict) and isinstance(r.get("text"), str) for r in rows)
    )
    if not well_formed:
        raise unread
    return [{"field": "visible_text", "text": r["text"]} for r in rows]


def shown_texts(job, records, env):
    """The visible_text rows of a job: [] when it shows no asset. Refuses shown_text_unread when any shown text is
    unreadable, so the guard never passes a subject that leaves on-screen text out."""
    shown = shown_assets(job)
    if not shown:
        return []
    summary = records.get("visible_text")
    if visible_gate(summary)[0] == "not_applicable":
        raise JobError(
            "shown_text_unread",
            f"the job shows {', '.join(shown)} and its records carry no guarded intake's marker, so no check reads"
            " that text; run a guarded intake",
        )
    if summary["state"] != "passed":
        where = ", ".join(summary["unread"] + summary["opaque"]) or "assets the intake did not record"
        raise JobError("shown_text_unread", f"the intake read no text source it can vouch for at {where}")
    if "source_sha256" not in summary:
        raise JobError("shown_text_unread", "the guarded intake stored no visible text; run the intake again")
    return stored_rows(summary["source_sha256"], env)


def subject(job, records, env, store):
    """{ok, job_id, texts}. The worker adds the packet id from its run input; the packet record names the brand.
    Refuses shown_text_unread for a job that shows an asset whose text is unreadable (shown_texts)."""
    shown = shown_texts(job, records, env)
    return {"ok": True, "job_id": job["id"], "texts": texts(job, records, env, store, shown)}


def machine_gates(store, gates):
    """The machine gate states of the current deliver_check. Refuses deliver_check_invalid when a state or
    delivery_gate.internal_review_allowed is missing, and machine_gates_failed when a gate failed or the flag is not
    true. The refusal names the failed gates, never a measured value."""
    measurements = (store.manifest("deliver_check") or {}).get("measurements") or {}
    delivery = measurements.get("delivery_gate")
    states = {g: gates.get(g) for g in accept.AUTOMATED}
    allowed = delivery.get("internal_review_allowed") if isinstance(delivery, dict) else None
    if not isinstance(allowed, bool) or any(v not in MACHINE_STATES for v in states.values()):
        raise JobError("deliver_check_invalid", "deliver_check holds no machine gate states or no delivery_gate")
    failed = sorted(g for g, v in states.items() if v not in MACHINE_OK)
    if failed or not allowed:
        named = ", ".join(failed) if failed else "delivery_gate.internal_review_allowed"
        raise JobError("machine_gates_failed", f"deliver_check failed {named}; the cut is not for internal review")
    return states


def cut(store, job):
    """{ok, job_id, video_sha256, deliver_check, machine_gates, internal_review_allowed, pending_operator, accepted}:
    the current cut, its machine gate states, the operator gates still open and the gates an acceptance of this same
    render has closed (accept.same_render). An acceptance of an earlier cut closes nothing here. A cut whose machine
    gates failed refuses machine_gates_failed."""
    render, gates = accept.render_of(store, job)
    machine = machine_gates(store, gates)
    closed = sorted({row["gate"] for row in accept.read(store)["acceptances"] if accept.same_render(row, render)})
    pending = sorted(g for g, state in gates.items() if state == "pending_operator" and g not in closed)
    return {
        "ok": True,
        "job_id": job["id"],
        **render,
        "machine_gates": machine,
        "internal_review_allowed": True,
        "pending_operator": pending,
        "accepted": closed,
    }
