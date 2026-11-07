"""The typed finding record of a narrated video's gates (docs/spec/NARRATED_VIDEO.md, "Findings", Linear TIN-7788,
ruling TIN-7125 0690fe88).

A gate stops on its first refusal, and that stop stays as it is: the same exit code and the same first code. A machine
that fixes a job needs the rest, so every gate also returns one record per code and page. A row is

  {gate, code, stage, blocking, page, segment, detail}

- gate names the check that found it, and code what it found. CODES holds every code a gate here writes. A code it
  does not hold, such as a refusal a stage or admit raises, takes the gate and stage its caller names;
- stage is where a fix enters the stage graph, so graph.reach gives what that fix may run. None means no stage bounds
  it: a bundle whose structure is wrong can hold any fix, so its reach is the whole graph;
- blocking is False only for what a gate records and never refuses, the advisory lexical findings (R-N12);
- page and segment name where it is, and either may be None;
- detail holds counts, measures and tokens. A record never holds a path or a text, because it leaves the private store
  in a machine's hands: plain drops any string or key that is not one short token. A token holds no slash, except a
  ratio such as a frame rate's 30000/1001.

Reading a report with check rebuilds each row from CODES, so a caller cannot move a known code's stage or blocking, and
refuses a code, gate or stage that is not one short token, because a round's ledger row holds the codes as written.
"""

import math
import re

from .job import JobError

KIND = "nv_findings"
SCHEMA_VERSION = 1
FIELDS = {"gate", "code", "stage", "blocking", "page", "segment", "detail"}
TOKEN = re.compile(r"[A-Za-z0-9._:+-]{0,64}|[0-9]{1,20}/[0-9]{1,20}")
WITHHELD = "withheld"
INTAKE = "intake"
LEXICAL = "lexical"
VOICE_QA = "voice_qa"
CLAIMS = "claims"
AVATAR_BOX = "avatar_box"
SLIDE_MATCH = "slide_match"
PROFILE = "profile"
LOUDNESS = "loudness"
FLASH = "flash"
CAPTIONS = "captions"
# Only a composed cut can show these, so a round on them names that cut. The frame gates also read before any voice.
CUT_GATES = (PROFILE, LOUDNESS, FLASH, CAPTIONS)
# The slide gate reads before any voice too, and these three of its codes only read a composed cut. So does a failed
# gate that left no row of its own (deliver.typed_findings).
GATE_FAILED = "gate_failed"
CUT_CODES = ("slide_layer_missing", "slide_layer_mismatch", "slide_not_shown", GATE_FAILED)
PROFILE_FIELDS = (
    "video_codec", "pix_fmt", "size", "fps", "frames", "audio_codec", "audio_rate_hz", "audio_channels",
    "subtitle_tracks",
)  # fmt: skip
ADVISORY = {"lexical_finding"}

# code: (gate, the stage a fix enters). A slide's digest is a source of compose and handoff only, so a slide fix
# enters at compose. A base under the avatar's box enters at base, which no voice reads. A voice that fails its gates
# may need its words changed, so that fix enters at script.
CODES = {
    "lexical_finding": (LEXICAL, "script"),
    "voice_qa_failed": (VOICE_QA, "script"),
    "voice_unverified": (VOICE_QA, "script"),
    "number_ambiguous": (CLAIMS, "script"),
    "number_unclaimed": (CLAIMS, "script"),
    "claim_ambiguous": (CLAIMS, "script"),
    "claim_unreceipted": (CLAIMS, "script"),
    "claims_not_passed": (CLAIMS, "script"),
    "card_in_avatar_box": (AVATAR_BOX, "compose"),
    "avatar_box_occupied": (AVATAR_BOX, "base"),
    "slide_digest_mismatch": (SLIDE_MATCH, "compose"),
    "slide_letterbox": (SLIDE_MATCH, "compose"),
    "slide_page_mismatch": (SLIDE_MATCH, "compose"),
    "slide_layer_missing": (SLIDE_MATCH, "compose"),
    "slide_layer_mismatch": (SLIDE_MATCH, "compose"),
    "slide_not_shown": (SLIDE_MATCH, "compose"),
    "loudness_drift": (LOUDNESS, "mix"),
    "loudness_true_peak": (LOUDNESS, "mix"),
    "flash_jump": (FLASH, "compose"),
    "captions_srt_missing": (CAPTIONS, "compose"),
    "captions_vtt_missing": (CAPTIONS, "compose"),
    "captions_soft_missing": (CAPTIONS, "compose"),
    "captions_persona_cue": (CAPTIONS, "compose"),
    "captions_extra_notice": (CAPTIONS, "compose"),
} | {f"profile_{name}": (PROFILE, "base") for name in PROFILE_FIELDS}
# A bundle intake refuses before a job exists. These reach the whole graph, because the fix may be anything.
INTAKE_CODES = (
    "asset_digest_mismatch", "asset_kind_mismatch", "asset_missing", "asset_needs_conversion", "asset_text_invalid",
    "asset_unknown", "asset_unreceipted", "asset_video_multiple", "beat_invalid", "beat_voiced_missing",
    "bundle_invalid", "claim_invalid", "claim_unknown", "consent_scope", "engine_inconsistent", "engine_not_allowed",
    "engine_unknown", "hosted_not_allowed", "job_invalid", "job_mismatch", "narrate_job_exists", "narrate_job_missing",
    "out_exists", "pronunciation_adds_number", "pronunciation_refused", "pronunciation_unknown", "records_invalid",
    "script_invalid", "store_conflict", "voice_unknown", "voiced_not_verbatim",
)  # fmt: skip
CODES |= {code: (INTAKE, None) for code in INTAKE_CODES}


def plain(value):
    """value with every string that is not one short token replaced. A number, a boolean and None stay."""
    if isinstance(value, str):
        return value if TOKEN.fullmatch(value) else WITHHELD
    if isinstance(value, dict):
        return {plain(str(k)): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return WITHHELD
    return value if value is None or isinstance(value, (bool, int, float)) else WITHHELD


def where(value):
    """A page or segment id, or None when it is not one short token."""
    return value if isinstance(value, str) and TOKEN.fullmatch(value) else None


def finding(code, gate=None, stage=None, page=None, segment=None, **detail):
    """One row. CODES decides the gate and stage of a code it holds, so gate and stage only name an unlisted one."""
    if code in CODES:
        gate, stage = CODES[code]
    return {
        "gate": gate or "unknown",
        "code": code,
        "stage": stage,
        "blocking": code not in ADVISORY,
        "page": where(page),
        "segment": where(segment),
        "detail": plain(detail),
    }


def reads_cut(row):
    """Only a composed cut can show this row. The avatar gate reads a picture before any voice and the frame after it,
    and its row says which."""
    return row["gate"] in CUT_GATES or row["code"] in CUT_CODES or row["detail"].get("source") == "frame"


def report(rows):
    """Every row, and what a machine reads first: ok is False when one blocks, and codes counts each code."""
    codes = {}
    for row in rows:
        codes[row["code"]] = codes.get(row["code"], 0) + 1
    blocking = sum(1 for row in rows if row["blocking"])
    return {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "ok": not blocking,
        "count": len(rows),
        "blocking": blocking,
        "codes": codes,
        "findings": list(rows),
    }


def token(value):
    """value is one short token that says something, as a code, gate or stage is."""
    return isinstance(value, str) and bool(value) and TOKEN.fullmatch(value) is not None


def check(value):
    """The report value holds, each row rebuilt by finding, or JobError findings_invalid."""
    rows = value.get("findings") if isinstance(value, dict) else None
    if (
        not isinstance(rows, list)
        or value.get("kind") != KIND
        or value.get("schema_version") != SCHEMA_VERSION
        or not all(isinstance(r, dict) and set(r) == FIELDS and token(r["code"]) for r in rows)
        or not all(isinstance(r["detail"], dict) and token(r["gate"]) for r in rows)
        or not all(r["stage"] is None or token(r["stage"]) for r in rows)
    ):
        raise JobError("findings_invalid", f"this is not a {KIND} report of schema version {SCHEMA_VERSION}")
    return report(
        [
            finding(row["code"], row["gate"], row["stage"], row["page"], row["segment"])
            | {"detail": plain(row["detail"])}
            for row in rows
        ]
    )
