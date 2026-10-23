"""Voice and engine listings, and adding a reference clip to the private store.

Listings never return a path or a clip: voices carry ids, consent state, scopes and allowed engines; engines carry
profile, backend, confidentiality eligibility and availability.

`voices add` copies a 10 to 30 s mono WAV clip and its human-verified transcript into the private store, each named
by its sha256, and prints the Voice record to add to the private Dhall registry. It records nothing in git and
needs a consent record (its evidence also in the store) before any job can use the voice.
"""

import shutil
import wave
from pathlib import Path

from . import engine, policy
from .ir import sha256_file

REF_CLIP_SECONDS = (10, 30)


def consent_state(consent, index):
    if consent is None:
        return "missing"
    if consent["revokedAt"] is not None:
        return "revoked"
    if index is not None and consent["evidenceSha256"] not in index:
        return "evidence_absent"
    return "active"


def voices(cfg):
    registry = cfg.registry()
    index = policy.store_index(cfg.store) if cfg.store else None
    out = []
    for voice in sorted(registry["voices"].values(), key=lambda v: v["id"]):
        consent = registry["consents"].get(voice["consentId"])
        entry = {
            "id": voice["id"],
            "consent_id": voice["consentId"],
            "consent_state": consent_state(consent, index),
            "scope": voice["scope"],
            "consent_scopes": consent["scopes"] if consent else [],
            "allowed_engines": voice["allowedEngines"],
            "fixture": voice["fixture"],
            "hosted_allowed": bool(consent and consent["hostedAllowed"]),
        }
        if index is not None:
            entry["ref_clip_stored"] = voice["refClipSha256"] in index
            entry["ref_text_stored"] = voice["refTextSha256"] in index
        out.append(entry)
    return out


def engines(cfg, profile=None):
    out = []
    for eng in sorted(cfg.registry()["engines"].values(), key=lambda e: e["id"]):
        if profile and eng["profile"] != profile:
            continue
        out.append(
            {
                "id": eng["id"],
                "profile": eng["profile"],
                "backend": eng["backend"],
                "model": eng["model"],
                "hosted": policy.is_hosted(eng),
                "consistent": policy.consistent(eng),
                "may_run_confidential": policy.may_run_confidential(eng),
                "licence": eng["licence"],
                "licence_notice": eng.get("licenceNotice"),
                **engine.probe(eng),
            }
        )
    return out


def add_voice(cfg, clip, transcript, voice_id, consent_id, scope="OwnContent", engines_allowed=()):
    """Store the clip and transcript by digest; return the Voice record to add to the private registry."""
    if cfg.store is None:
        raise ValueError("no private store: set store in narrate.toml or NARRATE_STORE")
    with wave.open(str(clip)) as w:
        rate, frames, channels = w.getframerate(), w.getnframes(), w.getnchannels()
    seconds = frames / rate
    low, high = REF_CLIP_SECONDS
    if not low <= seconds <= high:
        raise ValueError(f"the reference clip is {seconds:.2f} s; a reference clip is {low} to {high} s")
    text = Path(transcript).read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError("the transcript is empty; a reference clip needs its human-verified transcript")
    store = Path(cfg.store)
    store.mkdir(parents=True, exist_ok=True)
    clip_sha, text_sha = sha256_file(clip), sha256_file(transcript)
    shutil.copyfile(clip, store / f"{clip_sha}.wav")
    shutil.copyfile(transcript, store / f"{text_sha}.txt")
    return {
        "id": voice_id,
        "consentId": consent_id,
        "scope": scope,
        "allowedEngines": list(engines_allowed),
        "refClipSha256": clip_sha,
        "refTextSha256": text_sha,
        "refClipSeconds": round(seconds, 3),
        "refClipSampleRateHz": rate,
        "fixture": False,
        "channels": channels,
    }
