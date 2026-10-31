"""The guard subject and the current cut of a narrated-video job (docs/spec/NARRATED_VIDEO.md, "Guard subject and
cut", Linear TIN-7788, SPR-220).

The Cade narrate worker runs the BS-21 guard (xoxd-ai/cade src/bs21-guard.ts) before any task that voices, shows or
renders a text. That guard needs the texts themselves, and Hatchet carries job ids only, so the worker reads them
here, inside its own process, and never hands them to Hatchet, a log or a receipt.

texts(job, records, env, store) lists every text that the job's own records hold and that the job voices or shows,
in a fixed order:

  narration    each segment's voiced text, read as the script stage reads it (narrate.spoken.lines of its script
               through its narrate job's input adapter). The voice speaks it and the captions show it
  title        the job id, then each segment id, then each slide page id. description.txt and chapters.json show them
  caption      labels.personaCue, which compose puts above the first cue
  description  labels.extraNotice, the last line of description.txt
  label        labels.persona, which every stage manifest from place on carries

The text an asset shows on screen (a slide, a plot, a clip) is not in this list: the intake's private-terms guard
reads it from each asset's text source (narrate/video/private_terms.py, visible_text.py), and deliver_check's
visible_text gate stays open until a guarded intake has read all of it.

cut(store, job) is the current deliver_check render as accept.render_of binds it: the composed video's sha256, the
deliver_check stage key and content digest, the machine gate states, deliver_check's internal-review flag and the
operator gates still pending. It holds digests and gate names only, so the Cade worker can ask Jess about that cut,
and `nv accept` later checks the same digest. deliver_check records a failed machine gate as a state, not a refusal
(narrate/video/deliver.py delivery_gate), so cut refuses machine_gates_failed for it: a cut that failed flash,
loudness, profile or captions never reaches Jess as an ordinary request for a decision.
"""

from types import SimpleNamespace

from .. import adapters, spoken
from ..adapters import InputError
from ..normalise import NormaliseError
from . import accept
from .common import StageRefused, work_dir
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


def voiced(records, env, segment, store):
    """One segment's voiced text, read as the script stage reads it (narrate/video/speech.py run_script)."""
    narrate_job = records["jobs"].get(segment["narrateJob"])
    if narrate_job is None:
        raise JobError("records_invalid", f"segment {segment['id']} names no narrate job in the records")
    with work_dir(store) as work:
        try:
            path = script_copy(SimpleNamespace(env=env), segment, narrate_job["input"], work)
            return spoken.lines(adapters.load(narrate_job["input"], path))
        except StageRefused as exc:
            raise JobError(exc.code, exc.detail) from None
        except (InputError, NormaliseError, UnicodeDecodeError, ValueError):
            # A parser error can quote a line of the script, and a refusal goes to stderr: name the segment only.
            raise JobError("input_invalid", f"segment {segment['id']}'s script does not load") from None


def texts(job, records, env, store):
    """[{field, text}] for every text the job's records hold that it voices or shows, in the module's order."""
    out = [{"field": "narration", "text": voiced(records, env, s, store)} for s in job["segments"]]
    pages = (job.get("slides") or {}).get("pages") or []
    titles = [job["id"], *(s["id"] for s in job["segments"]), *(p["id"] for p in pages)]
    out += [{"field": "title", "text": t} for t in titles]
    for key, field in LABEL_FIELDS:
        value = job["labels"][key]
        if isinstance(value, str) and value:
            out.append({"field": field, "text": value})
    if len(out) > MAX_TEXTS or any(utf16_units(t["text"]) > MAX_TEXT for t in out):
        raise JobError("subject_too_large", f"the guard reads at most {MAX_TEXTS} texts of {MAX_TEXT} UTF-16 units")
    return out


def subject(job, records, env, store):
    """{ok, job_id, texts}. The worker adds the packet id from its run input; the packet record names the brand."""
    return {"ok": True, "job_id": job["id"], "texts": texts(job, records, env, store)}


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
