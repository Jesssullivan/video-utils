"""The machine verdict of a Campaign job: `narrate video campaign-verdict JOB --evidence FILE`
(docs/spec/NARRATED_VIDEO.md, "Campaign verdict", Linear TIN-7788, rulings TIN-7125 52ca88bf, 0690fe88).

The operator's signed campaign rule lets Cade or an agent publish inside a named campaign with no per-video decision, on
the condition that every automated check passes. For a Campaign job this verdict stands where a client or internal
job has `accept` and the operator outbox. It is the one place public_upload_allowed can read true, and only for the
Campaign edition. Every other edition gets false with campaign_edition_required, whatever its gates and evidence say,
and keeps listening and lip sync open.

The verdict reads three things:

- the job root: the current deliver_check render and its gates, the campaign binding in rerun.json, the look each
  overlay used and the consent row in the records. A page no frame gate read fails here, because under this rule nobody
  else reads it. So does a shown asset whose text no guard read, an operator state still open, and upload off;
- the evidence file the caller writes, bound to this job.json and this cut by digest: {kind, schema_version, campaign,
  record_sha256, consent_record, look: {anchors}, job_sha256, video_sha256, checks: {name: state}}. CHECKS holds the
  required checks of the signed rule. A check with no result fails;
- nothing else. It runs no stage, moves no key and asks nobody.

The caller verifies the campaign record's signature and writes its digest here: this repository holds no signing key,
so resolution reads caller_checked, as accept's form_only says how far a decision id was checked. Cade binds what it
verified (src/hatchet-client-video.ts).

A verdict holds ids, digests and gate names, never a text or a path. The last one for a job root is
campaign-verdict.json beside job.json, outside every stage directory. render_stage.job_findings reads its rows while it
still names the current job.json and cut, so a failed check reaches a fix the way a failed machine gate does. A check
whose fix is a reviewed record, not an edit to the job, gives a stop row the loop controller does not route. So does a
failed confidentiality check, because the signed record never covers disclosure-hold, client or health content and a
fix author must not rewrite past it, and any check the caller marks stopped.

The verdict reads admit again on the current records. A voice's consent withdrawn or a client consent recorded after the
cut refuses here, because no stage runs between the cut and this read.
public_upload_allowed true on the manifest is what a publish step reads. Nothing here publishes."""

from . import accept, admit, keys, look, rerun
from . import findings as typed
from .deliver import MACHINE_GATES, campaign_rows
from .job import CAMPAIGN_EDITION, ID, JobError
from .store import load_store_json, write_atomic

KIND = "nv_campaign_verdict"
EVIDENCE_KIND = "nv_campaign_evidence"
SCHEMA_VERSION = 1
FILE = "campaign-verdict.json"
RESOLUTION = "caller_checked"
GRANT_SCOPE = "CampaignStandingRule"
GRANTOR = "Operator"
EVIDENCE_FIELDS = {
    "kind", "schema_version", "campaign", "record_sha256", "consent_record", "look", "job_sha256", "video_sha256",
    "checks",
}  # fmt: skip
PASSED = "passed"
GATE = "campaign"
# The required checks of the signed rule, each with the stage a fix enters. Cade's src/campaign-checks.ts holds the same
# names. The brand's public gate opens by a reviewed record, and the manifest is bound by what prints it, so no edit to
# the job repairs either. Confidentiality takes no fix: the signed record excludes that content outright, and a rewrite
# that got past the check would still be that content. Each has no stage and its own code, and each gives a stop row.
CHECKS = {
    "canon_b8_identity": "avatar",
    "claims_allowlist": "script",
    "brand_public_gate": None,
    "confidentiality": None,
    "ai_disclosure": "compose",
    "synthetic_metadata": "compose",
    "manifest": None,
}
STOP_CHECKS = {
    "brand_public_gate": "campaign_brand_gate_closed",
    "confidentiality": "campaign_confidentiality_refused",
    "manifest": "campaign_manifest_refused",
}
# A check state saying no machine may iterate past this failure, such as a failed adult read of canon_b8_identity. The
# caller knows which of a check's refusals stop, and one state per check is all the evidence carries.
STOPPED = "stopped"
CHECK_STOPPED = "campaign_check_stopped"
ADMIT_REFUSED = "campaign_admit_refused"
# A gate that must have read something. flash, avatar_box and slide_match read not_applicable with nothing to read.
MUST_PASS = ("profile", "loudness", "captions")
LIFTED = ("listening", "lip_sync")
# The refusals deliver_check's typed rows already name (deliver.typed_findings).
CUT_ROWS = ("campaign_gate_failed", typed.FRAME_UNREAD, typed.VISIBLE_TEXT_UNREAD)


def refused(code, detail=None, **rest):
    return {"code": code, "detail": detail} | rest


def check_evidence(value):
    """The evidence, or JobError campaign_evidence_invalid. The states are not judged here, only the shape."""
    look_named = value.get("look") if isinstance(value, dict) else None
    if (
        not isinstance(value, dict)
        or set(value) != EVIDENCE_FIELDS
        or value["kind"] != EVIDENCE_KIND
        or value["schema_version"] != SCHEMA_VERSION
        or not isinstance(value["campaign"], str)
        or ID.fullmatch(value["campaign"]) is None
        or not accept.sha256(value["record_sha256"])
        or not isinstance(value["consent_record"], str)
        or not value["consent_record"]
        or not accept.sha256(value["job_sha256"])
        or not accept.sha256(value["video_sha256"])
        or not isinstance(look_named, dict)
        or set(look_named) != {"anchors"}
        or not isinstance(look_named["anchors"], list)
        or not all(accept.sha256(a) for a in look_named["anchors"])
        or not isinstance(value["checks"], dict)
        or not set(value["checks"]) <= set(CHECKS)
        or not all(isinstance(v, str) for v in value["checks"].values())
    ):
        raise JobError("campaign_evidence_invalid", "the evidence is not one nv_campaign_evidence record")
    return value


def evidence_refusals(evidence, binding, job_sha256, video_sha256):
    """What the caller's evidence leaves open. A missing check fails, and no state but passed passes."""
    out = []
    if binding is None:
        out.append(refused("campaign_unbound", "campaign-bind wrote no campaign on this job root"))
    elif evidence["campaign"] != binding:
        out.append(refused("campaign_record_mismatch", "the evidence names another campaign than the root is bound to"))
    if evidence["job_sha256"] != job_sha256 or evidence["video_sha256"] != video_sha256:
        out.append(refused("campaign_evidence_stale", "the evidence read another job.json or cut"))
    for name in CHECKS:
        state = evidence["checks"].get(name)
        if state is None:
            out.append(refused("campaign_check_missing", gate=name))
        elif state == STOPPED:
            out.append(refused(STOP_CHECKS.get(name, CHECK_STOPPED), gate=name))
        elif state != PASSED:
            out.append(refused(STOP_CHECKS.get(name, "campaign_check_failed"), gate=name))
    return out


def consent_refusals(consent_record, records):
    """The signed grant the evidence names must be a row of consents.json: the campaign scope, the operator as grantor,
    an evidence digest and no revocation. Use stops on withdrawal, so a revoked row refuses every later cut."""
    row = (records.get("consents") or {}).get(consent_record)
    scopes = (row or {}).get("scopes")
    if (
        not isinstance(row, dict)
        or not isinstance(scopes, list)
        or GRANT_SCOPE not in scopes
        or row.get("grantedBy") != GRANTOR
        or not accept.sha256(row.get("evidenceSha256"))
    ):
        return [
            refused(
                "campaign_consent_missing", f"no {GRANT_SCOPE} grant by the {GRANTOR} under the id the evidence names"
            )
        ]
    if row.get("revokedAt") is not None:
        return [refused("campaign_consent_revoked", "the signed grant is revoked")]
    return []


def admit_refusals(job, records):
    """What admit refuses on the records as they stand now, by code only. look_refusals reports the look's own gates."""
    return [
        refused(ADMIT_REFUSED, gate=row["code"])
        for row in admit.admit(job, records)["refusals"]
        if not row["code"].startswith("look_")
    ]


def look_refusals(store, job, records, evidence):
    """Every overlay of the cut must be the look the campaign record names. A consent names a look per campaign, so an
    overlay another external drew, or another look, refuses. A job with no overlay shows no look."""
    out = []
    check = admit.port()
    if check.avatar_on(job):
        out += [refused(code, detail) for code, detail in look.gates(job, records)]
    want = keys.digest(sorted(evidence["look"]["anchors"]))
    for segment in job["segments"]:
        if job["avatar"] is None or not segment["avatar"]:
            continue
        measured = (store.manifest(f"avatar/{segment['id']}") or {}).get("measurements") or {}
        if (measured.get("renderer") or {}).get("kind") != look.EXTERNAL or (measured.get("rig") or {}).get(
            "sha256"
        ) != want:
            out.append(
                refused(
                    "campaign_look_mismatch", "an overlay is not the look the campaign names", segment=segment["id"]
                )
            )
    return out


def cut_refusals(job, report, delivery):
    """What the deliver_check report leaves open for a cut nobody reviews. The typed rows for the frame and visible-text
    faults come from deliver.campaign_rows, which job_findings reads with the machine gates' rows."""
    gates = report["gates"]
    out = [
        refused("campaign_gate_failed", gate=g)
        for g in MACHINE_GATES
        if gates.get(g) != PASSED and not (g not in MUST_PASS and gates.get(g) == "not_applicable")
    ]
    if delivery.get("machine_gates_passed") is not True:
        out.append(refused("campaign_gate_failed", gate="machine_gates_passed"))
    if job["delivery"]["upload"] is not True:
        out.append(refused("campaign_upload_off", "delivery.upload is off"))
    elif delivery.get("upload_gates_closed") is not True:
        out.append(refused("campaign_upload_gates_open", "a bed gate or machine gate leaves upload closed"))
    open_states = delivery.get("operator_states_open")
    if not isinstance(open_states, list):
        out.append(refused("campaign_gate_failed", gate="operator_states_open"))
    else:
        out += [refused("campaign_operator_state_open", gate=g) for g in open_states if g != "visible_text"]
    out += [refused(row["code"], page=row["page"]) for row in campaign_rows(report, job)]
    if (report.get("labels") or {}).get("synthetic") is not True:
        out.append(refused("campaign_not_synthetic", "the cut's labels do not say synthetic"))
    if (report.get("edition") or {}).get("verdict") != "Admitted":
        out.append(refused("campaign_gate_failed", gate="edition"))
    return out


def rows_of(refusals):
    """The typed rows of a verdict's refusals, for job_findings. A failed check names where its fix enters. A failed
    machine gate and an unread page already have deliver_check's rows. Every other code here has no fix a job edit can
    make, so its row stops the loop."""
    rows = []
    for row in refusals:
        if row["code"] == "campaign_check_failed":
            rows.append(typed.finding(row["code"], gate=row["gate"], stage=CHECKS[row["gate"]]))
        elif row["code"] not in CUT_ROWS:
            rows.append(typed.finding(row["code"], gate=row.get("gate") or GATE))
    return rows


def manifest_of(campaign, consent_record, video_sha256):
    return {"synthetic": True, "campaign": campaign, "consent_record": consent_record, "video_sha256": video_sha256}


def manifest(store, campaign, consent_record):
    """The render manifest the signed rule's manifest check reads: synthetic, the campaign id and the record's id, on
    the current cut. It holds what this job root can vouch for, and it refuses a Campaign cut it cannot say that about,
    so the caller reads it before it runs the checks. A true verdict prints the same four fields. Refusals:
    campaign_edition_required, campaign_unbound, campaign_record_mismatch, deliver_check_*, campaign_not_synthetic."""
    job = store.read_job()
    if job["edition"] != CAMPAIGN_EDITION:
        raise JobError("campaign_edition_required", f"edition {job['edition']} keeps its decision")
    binding = (rerun.read(store).get("campaign") or {}).get("id")
    if binding is None:
        raise JobError("campaign_unbound", "campaign-bind wrote no campaign on this job root")
    if binding != campaign:
        raise JobError("campaign_record_mismatch", "this job root is bound to another campaign")
    if not isinstance(consent_record, str) or not consent_record:
        raise JobError("campaign_consent_missing", "the manifest names no signed record")
    render, _ = accept.render_of(store, job)
    report = load_store_json(store.dir / store.entry("deliver_check")["dir"] / "deliver_check.json")
    if (report.get("labels") or {}).get("synthetic") is not True:
        raise JobError("campaign_not_synthetic", "the cut's labels do not say synthetic")
    return {"ok": True, "job_id": store.job_id, "job_sha256": keys.digest(job)} | manifest_of(
        campaign, consent_record, render["video_sha256"]
    )


def verdict(store, records, evidence=None):
    """The machine verdict of the job's current cut. Prints public_upload_allowed and every refusal, and refuses by
    JobError only a job root or evidence that does not read. Writes campaign-verdict.json for a Campaign job."""
    job = store.read_job()
    job_sha256 = keys.digest(job)
    out = {
        "ok": True,
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "job_id": store.job_id,
        "edition": job["edition"],
        "job_sha256": job_sha256,
        "public_upload_allowed": False,
        "video_sha256": None,
        "deliver_check": None,
        "campaign": None,
        "record_sha256": None,
        "consent_record": None,
        "resolution": RESOLUTION,
        "lifted": [],
        "checks": {},
        "look": None,
        "manifest": None,
        "refusals": [],
    }
    if job["edition"] != CAMPAIGN_EDITION:
        return out | {
            "refusals": [refused("campaign_edition_required", f"edition {job['edition']} keeps its decision")]
        }
    if evidence is not None:
        check_evidence(evidence)
    ledger = rerun.read(store)
    binding = (ledger.get("campaign") or {}).get("id")
    refusals = []
    if ledger.get("parked") is not None:
        refusals.append(refused("campaign_parked", "this job root is parked"))
    render = None
    try:
        render, _ = accept.render_of(store, job)
    except JobError as exc:
        if exc.code not in (
            "deliver_check_missing",
            "deliver_check_stale",
            "deliver_check_corrupt",
            "deliver_check_invalid",
        ):
            raise
        refusals.append(refused(exc.code, "no current deliver_check render"))
    if render is not None:
        out |= {"video_sha256": render["video_sha256"], "deliver_check": render["deliver_check"]}
        entry = store.entry("deliver_check")
        report = load_store_json(store.dir / entry["dir"] / "deliver_check.json")
        delivery = (store.manifest("deliver_check").get("measurements") or {}).get("delivery_gate") or {}
        refusals += cut_refusals(job, report, delivery)
        if rerun.fix_of(ledger, render["video_sha256"]) is not None:
            refusals.append(refused("campaign_cut_sent_back", "a round or FIX sent this cut back"))
    refusals += admit_refusals(job, records)
    if evidence is None:
        refusals.append(refused("campaign_evidence_missing", "no signed record or check results were given"))
    else:
        out |= {
            "campaign": evidence["campaign"],
            "record_sha256": evidence["record_sha256"],
            "consent_record": evidence["consent_record"],
            "checks": {name: evidence["checks"].get(name) for name in CHECKS},
            "look": keys.digest(sorted(evidence["look"]["anchors"])),
        }
        refusals += evidence_refusals(evidence, binding, job_sha256, out["video_sha256"])
        refusals += consent_refusals(evidence["consent_record"], records)
        if render is not None:
            refusals += look_refusals(store, job, records, evidence)
    allowed = not refusals and render is not None and evidence is not None
    out |= {"public_upload_allowed": allowed, "refusals": refusals, "lifted": list(LIFTED)}
    if allowed:
        out["manifest"] = manifest_of(evidence["campaign"], evidence["consent_record"], render["video_sha256"])
    write_atomic(store.dir / FILE, out)
    return out


def held_rows(store, job_sha256, video_sha256):
    """The typed rows of the last verdict while it read this job.json and cut. One of an older cut says nothing."""
    path = store.dir / FILE
    if not path.is_file() or path.is_symlink():
        return []
    held = load_store_json(path)
    if not isinstance(held, dict) or held.get("kind") != KIND:
        raise JobError("store_invalid", f"{FILE} is not a campaign verdict")
    if held.get("job_sha256") != job_sha256 or video_sha256 is None or held.get("video_sha256") != video_sha256:
        return []
    return rows_of(held.get("refusals") or [])
