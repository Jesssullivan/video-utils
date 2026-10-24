"""Voice and engine listings, and adding a reference clip to the private store.

Listings never return a path or a clip: voices carry ids, consent state, scopes and allowed engines; engines carry
profile, backend, confidentiality eligibility and availability.

`voices add` copies a 10 to 30 s mono 16-bit PCM WAV clip and its human-verified transcript into the private store,
each named by its sha256, and prints the Voice record to add to the private Dhall registry: exactly the fields of
narrate/dhall/Voice.dhall. It refuses (RegistryError, a typed code) a clip that is not such a WAV, an unreadable
transcript, no allowed engine, or an engine id the registry does not hold. It records nothing in git and
needs a consent record (its evidence also in the store) before any job can use the voice.
"""

import shutil
import socket
import time
import urllib.parse
import wave
from pathlib import Path

from . import engine, policy
from .ir import sha256_file

REF_CLIP_SECONDS = (10, 30)


class RegistryError(RuntimeError):
    def __init__(self, code, detail):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


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


REACH_TIMEOUT_S = 2.0


def reach(eng, timeout=REACH_TIMEOUT_S):
    """Whether the engine's host accepts a TCP connection: no request, no token, no synthesis. Fake engines are
    in process. The endpoint itself is never returned."""
    if eng["backend"] == "Fake":
        return {"reachable": True, "how": "in process"}
    parts = urllib.parse.urlsplit(eng.get("endpoint") or "")
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return {"reachable": False, "how": "no http(s) endpoint"}
    port = parts.port or (443 if parts.scheme == "https" else 80)
    started = time.monotonic()
    try:
        with socket.create_connection((parts.hostname, port), timeout=timeout):
            pass
    except OSError as error:
        return {"reachable": False, "how": f"tcp connect: {type(error).__name__}"}
    return {"reachable": True, "how": "tcp connect", "connect_ms": round(1000 * (time.monotonic() - started), 1)}


def engines(cfg, profile=None, probe_reach=False):
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
                **({"reach": reach(eng)} if probe_reach else {}),
            }
        )
    return out


def add_voice(cfg, clip, transcript, voice_id, consent_id, scope="OwnContent", engines_allowed=()):
    """Store the clip and transcript by digest; return the Voice record to add to the private registry."""
    if cfg.store is None:
        raise RegistryError("store_missing", "no private store: set store in narrate.toml or NARRATE_STORE")
    engines_allowed = list(engines_allowed)
    if not engines_allowed:
        raise RegistryError("voice_engines_empty", "name at least one --allow-engine; a voice no engine may use")
    unknown = sorted(set(engines_allowed) - set(cfg.registry()["engines"]))
    if unknown:
        raise RegistryError("engine_unknown", f"--allow-engine {unknown}: not in the engine registry")
    try:
        with wave.open(str(clip)) as w:
            rate, frames = w.getframerate(), w.getnframes()
            channels, width, comptype = w.getnchannels(), w.getsampwidth(), w.getcomptype()
    except (OSError, wave.Error, EOFError) as error:
        raise RegistryError("ref_clip_invalid", f"the reference clip is not a readable WAV: {error}") from None
    if (channels, width, comptype) != (1, 2, "NONE") or not rate:
        raise RegistryError(
            "ref_clip_invalid", f"the reference clip is {channels} ch, {8 * width}-bit; it must be mono 16-bit PCM"
        )
    seconds = frames / rate
    low, high = REF_CLIP_SECONDS
    if not low <= seconds <= high:
        raise RegistryError(
            "ref_clip_length", f"the reference clip is {seconds:.2f} s; a reference clip is {low} to {high} s"
        )
    try:
        text = Path(transcript).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise RegistryError("ref_text_invalid", f"the transcript is unreadable: {type(error).__name__}") from None
    if not text.strip():
        raise RegistryError(
            "ref_text_invalid", "the transcript is empty; a reference clip needs its human-verified transcript"
        )
    store = Path(cfg.store)
    store.mkdir(parents=True, exist_ok=True)
    clip_sha, text_sha = sha256_file(clip), sha256_file(transcript)
    shutil.copyfile(clip, store / f"{clip_sha}.wav")
    shutil.copyfile(transcript, store / f"{text_sha}.txt")
    return {
        "id": voice_id,
        "consentId": consent_id,
        "scope": scope,
        "allowedEngines": engines_allowed,
        "refClipSha256": clip_sha,
        "refTextSha256": text_sha,
        "refClipSeconds": round(seconds, 3),
        "refClipSampleRateHz": rate,
        "fixture": False,
    }
