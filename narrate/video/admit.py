"""The admit stage: the read-only gate at the Plan point (docs/spec/NARRATED_VIDEO.md, "Editions").

admit resolves what a job names and refuses before any stage runs: an unknown narrate job, a script digest that is
not the narrate job's pinned input, a voice without an active consent, a missing persona label, a bed record that is
missing or not acquired by the operator, tighten edits on synthetic narration with tighten off, a knob outside its
bound (a bed layer's tempo factor included), a kitpip binary whose digest differs from its pin, and Edition.check at
Plan.

The edition rule, the plan leaves and the bounds are narrate/dhall/check.py's port of Edition.dhall and
NarratedVideo.dhall, loaded here so the Plan point and `just narrate-dhall-check` run one rule. Place (L4) and
DeliverCheck (L6) call the same port with their own leaves.

admit writes nothing. Its result carries the labels the job will grow from (synthetic, consent ids, voice ids,
persona) and the operator gates still open (pending_operator).
"""

import importlib.util

from ..config import ROOT

CHECK = ROOT / "narrate" / "dhall" / "check.py"
_PORT = None


def port():
    """narrate/dhall/check.py as a module (it is a script, not a package member)."""
    global _PORT
    if _PORT is None:
        spec = importlib.util.spec_from_file_location("narrate_dhall_check", CHECK)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _PORT = module
    return _PORT


def refusal(code, detail):
    return {"code": code, "detail": detail}


def segment_labels(job, records, refusals):
    """Consent ids, voice ids and consent personas of every segment's voices; refusals for what is missing."""
    consent_ids, voice_ids, personas = set(), set(), set()
    for segment in job["segments"]:
        where = f"segment {segment['id']}"
        narrate_job = records["jobs"].get(segment["narrateJob"])
        if narrate_job is None:
            refusals.append(refusal("narrate_job_missing", f"{where}: narrate job {segment['narrateJob']} is unknown"))
            continue
        if segment["scriptSha256"] != narrate_job.get("inputSha256"):
            refusals.append(refusal("script_digest_mismatch", f"{where}: scriptSha256 is not its job's input"))
        for voice_id in [narrate_job["voice"]] + [s["voice"] for s in narrate_job.get("speakers", [])]:
            voice = records["voices"].get(voice_id)
            consent = records["consents"].get((voice or {}).get("consentId"))
            if voice is None or consent is None:
                refusals.append(refusal("consent_missing", f"{where}: voice {voice_id} has no consent record"))
                continue
            if consent.get("revokedAt") is not None:
                refusals.append(refusal("consent_revoked", f"{where}: the consent of voice {voice_id} is revoked"))
                continue
            voice_ids.add(voice_id)
            consent_ids.add(consent["id"])
            if consent.get("persona") is not None:
                personas.add(consent["persona"])
    return consent_ids, voice_ids, personas


def bounds(job, refusals):
    check = port()
    if job["avatar"] is not None:
        if job["avatar"]["external"] != "kitpip":
            refusals.append(refusal("avatar_external_unknown", "avatar.external is not kitpip"))
        if not check.within(job["avatar"]["width"], check.NV_BOUNDS["avatar.width"]):
            refusals.append(refusal("knob_out_of_bounds", "avatar.width is not 0.10 to 0.30"))
    music = job["music"]
    if music is not None:
        if not check.within(music["bedBelowVoiceLu"], check.NV_BOUNDS["music.bedBelowVoiceLu"]):
            refusals.append(refusal("knob_out_of_bounds", "music.bedBelowVoiceLu is not 10 to 30"))
        if not check.within(music["duckDb"], check.NV_BOUNDS["music.duckDb"]) or music["duckDb"] == 0:
            refusals.append(refusal("knob_out_of_bounds", "music.duckDb is not above 0 and at most 12"))
        if min(music["fadeInS"], music["fadeOutS"], music["tailS"]) < 0:
            refusals.append(refusal("knob_out_of_bounds", "music fades and tail are not negative"))
    delivery = job["delivery"]
    if not 0 < delivery["driftLu"] <= check.NV_DRIFT_MAX_LU:
        refusals.append(refusal("knob_out_of_bounds", "delivery.driftLu is not above 0 and at most 0.5"))
    if delivery["truePeakDbtp"] > check.NV_TRUE_PEAK_MAX_DBTP:
        refusals.append(refusal("knob_out_of_bounds", "delivery.truePeakDbtp is above -1.5"))


def bed_record(job, records, refusals):
    if job["music"] is None:
        return None
    bed = records["music_beds"].get(job["music"]["bed"])
    if bed is None:
        refusals.append(refusal("bed_record_missing", f"music bed {job['music']['bed']} has no record"))
        return None
    if bed["acquisition"]["acquiredBy"] != "Operator":
        refusals.append(refusal("bed_acquisition_agent", "only the operator acquires a bed (MusicBed.acquiredBy)"))
    layers = bed["layers"]
    if not 2 <= len(layers) <= 3 or len({layer["sha256"] for layer in layers}) != len(layers):
        refusals.append(refusal("bed_layers_invalid", "a bed arranges 2 or 3 distinct loops"))
    check = port()
    low, high = check.BED_TEMPO_RANGE
    for i, layer in enumerate(layers):
        if not check.within(layer.get("tempoFactor"), check.BED_TEMPO_RANGE):
            refusals.append(refusal("knob_out_of_bounds", f"bed layer {i}'s tempoFactor is not {low} to {high}"))
    return bed


def pending_operator(job, bed):
    """Gates only the operator closes. admit lists them; nothing here marks one passed."""
    items = [
        {
            "gate": "listening_acceptance",
            "stage": "voice_qa",
            "segment": s["id"],
            "detail": "a rendered voice is not accepted until the operator's listening receipt",
        }
        for s in job["segments"]
    ]
    if job["avatar"] is not None and any(s["avatar"] for s in job["segments"]):
        items.append(
            {
                "gate": "lip_sync_acceptance",
                "stage": "avatar_check",
                "segment": None,
                "detail": "kitpip lip sync is pending the operator's acceptance",
            }
        )
    if job["delivery"]["upload"] and bed is not None:
        if bed["licence"]["certifiedPdfSha256"] is None:
            items.append(
                {
                    "gate": "bed_licence_incomplete",
                    "stage": "deliver_check",
                    "segment": None,
                    "detail": "the bed record holds no certified licence PDF digest",
                }
            )
        content_id = bed["licence"]["contentIdCheck"]
        if not (isinstance(content_id, dict) and "clear" in content_id):
            items.append(
                {
                    "gate": "bed_content_id_unchecked",
                    "stage": "deliver_check",
                    "segment": None,
                    "detail": "the bed record holds no clear Content ID result",
                }
            )
    return items


def admit(job, records, kitpip_state=None):
    """{verdict, refusals, edition, labels, pending_operator}. kitpip_state is kitpip.resolve()'s state, or None
    when no avatar is on. Only a digest mismatch refuses here; a missing binary blocks the avatar stages."""
    check = port()
    refusals = []
    consent_ids, voice_ids, personas = segment_labels(job, records, refusals)
    if check.avatar_on(job) and job["labels"]["persona"] is None:
        refusals.append(refusal("persona_label_missing", "an avatar is on and labels.persona is empty"))
    for persona in sorted(personas):
        if job["labels"]["persona"] != persona:
            refusals.append(refusal("persona_label_missing", "a voice's consent names a persona the labels lack"))
    bed = bed_record(job, records, refusals)
    deck = job["base"].get("deck")
    edits = deck is not None and deck["tightenEditsSha256"] is not None
    if edits and job["segments"] and not job["tighten"]["enabled"]:
        refusals.append(refusal("tighten_on_synthetic", "tighten edits on narrate segments need tighten.enabled"))
    bounds(job, refusals)
    if kitpip_state == "mismatch":
        refusals.append(refusal("kitpip_pin_mismatch", "the kitpip binary's digest is not its pin's"))
    edition = check.edition_check("Plan", job["edition"], check.plan_leaves(job, bed))
    for code in edition.get("codes", []):
        refusals.append(refusal(check.EDITION_REFUSALS[code], f"edition {job['edition']} at Plan"))
    return {
        "verdict": "Refused" if refusals else "Admitted",
        "refusals": refusals,
        "edition": edition,
        "labels": {
            "synthetic": bool(job["segments"]),
            "consent_ids": sorted(consent_ids),
            "voice_ids": sorted(voice_ids),
            "persona": job["labels"]["persona"],
        },
        "pending_operator": pending_operator(job, bed),
    }
