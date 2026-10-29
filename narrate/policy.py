"""Consent and confidentiality policy (docs/spec/NARRATE.md, "Consent and confidentiality policy").

The engine predicates are Engine.dhall's, ported as narrate/dhall/check.py ports them; tests assert the three
agree on the whole truth table. Every refusal raises Refused with a typed code before any audio is made:

  engine_unknown, engine_inconsistent, confidential_engine_refused, hosted_not_allowed,
  voice_unknown, engine_not_allowed, speaker_unmapped,
  consent_missing, consent_revoked, consent_scope, ref_clip_missing, ref_text_missing.

Reference clips, transcripts and consent evidence are found in the private store by sha256, never by a path the
job carries; a file whose digest differs is simply not found. Nothing here returns or records a path.
"""

from pathlib import Path

from .ir import sha256_file

PROFILE_BACKENDS = {
    "GpuSwitch": {"VulkanAudioCpp", "QwenTtsCpp", "LlamaTts"},
    "GpuDirect": {"VulkanAudioCpp", "QwenTtsCpp", "LlamaTts", "AudioCppBatch"},
    "MacMlx": {"MlxAudio"},
    "RentedOpen": {"RentedOpen"},
    "Hosted": {"Hosted"},
    "Fake": {"Fake"},
}
STORE_MAX_FILES = 4096
# Consent.Scope.Likeness (SP-R13) grants an avatar likeness to a VRM model record, never a voice.
LIKENESS_SCOPE = "Likeness"


class Refused(RuntimeError):
    def __init__(self, code, detail):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


def is_hosted(engine):
    return bool(engine["hosted"]) or engine["profile"] == "Hosted" or engine["backend"] == "Hosted"


def is_rented(engine):
    return engine["profile"] == "RentedOpen" or engine["backend"] == "RentedOpen"


def consistent(engine):
    fits = engine["backend"] in PROFILE_BACKENDS.get(engine["profile"], set())
    return fits and bool(engine["hosted"]) == (engine["profile"] == "Hosted")


def may_run_confidential(engine):
    return (
        consistent(engine)
        and not is_hosted(engine)
        and bool(engine["confidentialAllowed"])
        and (not is_rented(engine) or bool(engine["estateControlled"]))
    )


def store_index(store):
    """{sha256: path} of every regular file under the private store. Empty when there is no store."""
    if store is None or not Path(store).is_dir():
        return {}
    index = {}
    for count, path in enumerate(sorted(p for p in Path(store).rglob("*") if p.is_file() and not p.is_symlink())):
        if count >= STORE_MAX_FILES:
            raise Refused("store_too_large", f"the store holds more than {STORE_MAX_FILES} files")
        index.setdefault(sha256_file(path), path)
    return index


def voice_map(job, script):
    """{speaker or None: voice id} for every speaker the script uses. A Dialog script, or any script when the job
    has a speakers table, must map every named speaker; otherwise cue speakers read in the job's voice."""
    table = {s["speaker"]: s["voice"] for s in job["speakers"]}
    strict = script.kind == "Dialog" or bool(table)
    used = {}
    for segment in script.segments:
        if segment.speaker is None or not strict:
            used[segment.speaker if strict else None] = job["voice"]
        elif segment.speaker in table:
            used[segment.speaker] = table[segment.speaker]
        else:
            raise Refused(
                "speaker_unmapped",
                f"segment {segment.id} speaker {segment.speaker!r} is not in the "
                f"job's speakers table ({sorted(table)})",
            )
    return used


def check_engine(job, engine_id, engines):
    engine = engines.get(engine_id)
    if engine is None:
        raise Refused("engine_unknown", f"engine {engine_id!r} is not registered")
    if not consistent(engine):
        raise Refused(
            "engine_inconsistent",
            f"engine {engine_id}: profile {engine['profile']} and backend {engine['backend']} disagree",
        )
    if job["confidential"] and not may_run_confidential(engine):
        raise Refused(
            "confidential_engine_refused",
            f"job {job['id']} is confidential and engine {engine_id} may not run confidential jobs",
        )
    if is_hosted(engine) and not job["allowHosted"]:
        raise Refused("hosted_not_allowed", f"engine {engine_id} is hosted and job {job['id']} lacks allowHosted")
    return engine


def check_consent(voice_id, registry, index, job_scope):
    """The consent half of check_voice: the voice is registered, its consent is registered with stored evidence, not
    revoked, and grants both the voice's and the job's scope. Anything that uses a voice's reference clip (a render,
    or a SIM embedding, which is a voiceprint) passes this first. index None checks the registry metadata only, so
    a caller can refuse before hashing the store. Return (voice, consent) or raise Refused."""
    voice = registry["voices"].get(voice_id)
    if voice is None:
        raise Refused("voice_unknown", f"voice {voice_id!r} is not registered")
    cid = voice["consentId"]
    consent = registry["consents"].get(cid)
    if consent is None:
        raise Refused("consent_missing", f"voice {voice_id} names consent {cid!r}, which is not registered")
    scopes, evidence = consent["scopes"], consent["evidenceSha256"]
    if (
        type(job_scope) is not str
        or type(voice["scope"]) is not str
        or type(scopes) is not list
        or any(type(s) is not str for s in scopes)
        or type(evidence) is not str
        or not evidence
    ):
        raise Refused("consent_invalid", f"consent {cid} or voice {voice_id}: scope or evidence fields have bad types")
    if index is not None and evidence not in index:
        raise Refused("consent_missing", f"consent {cid}: no stored evidence has its sha256")
    if consent["revokedAt"] is not None:
        raise Refused("consent_revoked", f"consent {cid} was revoked {consent['revokedAt']}")
    if LIKENESS_SCOPE in (voice["scope"], job_scope):
        raise Refused("consent_scope", f"the {LIKENESS_SCOPE} scope (SP-R13) grants an avatar likeness, never a voice")
    for scope, whose in ((voice["scope"], "voice"), (job_scope, "job")):
        if scope not in scopes:
            raise Refused("consent_scope", f"consent {cid} does not grant the {whose} scope {scope}")
    if voice["scope"] != job_scope:
        raise Refused("consent_scope", f"voice {voice_id} scope {voice['scope']} differs from the job's {job_scope}")
    return voice, consent


def check_voice(job, voice_id, engine, registry, index):
    voice, consent = check_consent(voice_id, registry, index, job["scope"])
    if engine["id"] not in voice["allowedEngines"]:
        raise Refused("engine_not_allowed", f"engine {engine['id']} is not in voice {voice_id}'s allowedEngines")
    if is_hosted(engine) and not consent["hostedAllowed"]:
        raise Refused("hosted_not_allowed", f"consent {consent['id']} does not allow hosted engines")
    if voice["refClipSha256"] not in index:
        raise Refused("ref_clip_missing", f"voice {voice_id}: no stored clip has sha256 {voice['refClipSha256'][:12]}")
    if voice["refTextSha256"] not in index:
        raise Refused(
            "ref_text_missing", f"voice {voice_id}: no stored transcript has sha256 {voice['refTextSha256'][:12]}"
        )
    return voice, consent


def admit(job, script, registry, index, engine_id=None):
    """Check the whole job before any audio exists. Return (engine, {speaker: voice record}, consents) or raise."""
    engine = check_engine(job, engine_id or job["engine"], registry["engines"])
    used = voice_map(job, script)
    voices, consents = {}, {}
    # every voice the job names is checked, used or not: a job never carries an unconsented voice
    for voice_id in sorted({job["voice"], *(s["voice"] for s in job["speakers"])}):
        voice, consent = check_voice(job, voice_id, engine, registry, index)
        voices[voice_id], consents[consent["id"]] = voice, consent
    return engine, {speaker: voices[v] for speaker, v in used.items()}, consents
