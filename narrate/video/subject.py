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
deliver_check stage key and content digest, and the operator gates still pending. It holds digests and gate names
only, so the Cade worker can ask Jess about that cut, and `nv accept` later checks the same digest.
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
MAX_TEXTS = 4096
MAX_TEXT = 200_000
LABEL_FIELDS = (("personaCue", "caption"), ("extraNotice", "description"), ("persona", "label"))


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
        except (InputError, NormaliseError, UnicodeDecodeError, ValueError) as exc:
            raise JobError("input_invalid", str(exc)[:200]) from None


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
    if len(out) > MAX_TEXTS or any(len(t["text"]) > MAX_TEXT for t in out):
        raise JobError("subject_too_large", f"the guard reads at most {MAX_TEXTS} texts of {MAX_TEXT} characters")
    return out


def subject(job, records, env, store):
    """{ok, job_id, texts}. The worker adds the packet id from its run input; the packet record names the brand."""
    return {"ok": True, "job_id": job["id"], "texts": texts(job, records, env, store)}


def cut(store, job):
    """{ok, job_id, video_sha256, deliver_check, pending_operator, accepted}: the current cut, the gates still open
    and the gates an acceptance of this same render has closed (accept.same_render). An acceptance of an earlier cut
    closes nothing here."""
    render, gates = accept.render_of(store, job)
    closed = sorted({row["gate"] for row in accept.read(store)["acceptances"] if accept.same_render(row, render)})
    pending = sorted(g for g, state in gates.items() if state == "pending_operator" and g not in closed)
    return {"ok": True, "job_id": job["id"], **render, "pending_operator": pending, "accepted": closed}
