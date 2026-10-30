"""Demo bundle intake (docs/spec/NARRATED_VIDEO.md, "Demo bundle intake", TIN-7735).

A demo bundle is a directory (docs/demo/<slug>/ in its producer's private repository) holding manifest.json,
script.md, claims.json and the PNG, MP4 and GIF assets the manifest lists. read() parses it strictly and refuses
with a typed code; claims_report() runs the spoken-number claims gate (claims.py); convert() turns a bundle into the
existing records: one NarratedVideo job and one narrate Job per beat, with no new schema (SPR-84). intake() checks
the result with job.check_shape and admit, checks that the template's pronunciation tables add no spoken number,
runs the private-terms guard (private_terms.py) on every text it would speak or show, and only then writes it:
every store file is checked, copied and hashed first, and the output directory is built as a temporary sibling and
renamed into place, so a refusal leaves no output and no new store file.

Everything here reads and writes local files only. Nothing renders, and nothing is published.
"""

import contextlib
import copy
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
from collections import Counter
from decimal import Decimal
from pathlib import Path, PurePosixPath

from .. import adapters, lexical
from ..adapters import InputError
from ..config import LEXICAL_ENV
from ..ir import canonical, sha256_file
from ..normalise import NormaliseError, Normaliser
from . import claims as gate
from . import private_terms
from .admit import admit, port
from .job import DEFAULTS, ID, RECORD_FILES, SHA256, JobError, check_shape, load_records

MANIFEST, SCRIPT, CLAIMS = "manifest.json", "script.md", "claims.json"
MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_SCRIPT_BYTES = 1024 * 1024
MAX_TARGET_S = Decimal(3600)
ASSET_KINDS = ("png", "mp4", "gif")
ASSET_FIELDS = {"id", "path", "sha256", "kind", "receipt"}
ASSET_OPTIONAL = {"size", "fps"}
MANIFEST_FIELDS = {"assets"}
MANIFEST_OPTIONAL = {"slug", "privacy"}
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
HEADING = re.compile(r"^## (?P<id>.*?)\s*$")
META = re.compile(r"^- (?P<key>[a-z_]+):(?P<value>.*)$")
META_KEYS = ("target_s", "asset_id", "claims")
TARGET = re.compile(r"^\d{1,4}(?:\.\d{1,3})?$")
FENCE = "```"
VOICED_FENCE = "```voiced"
# The fields of a narrate Job record (narrate/dhall/Job.dhall). A template narrate job must have exactly these.
NARRATE_JOB_FIELDS = {
    "id", "input", "inputSha256", "scope", "confidential", "allowHosted", "lexical", "pronunciation", "voice",
    "speakers", "engine", "seed", "chunkMaxCodepoints", "gates", "post", "audio", "captions", "narrationEdl",
}  # fmt: skip
EDITION = "Internal"  # every demo bundle job (TIN-7735); a client edition is a separate, later decision
SUFFIX = {"png": ".png", "mp4": ".mp4", "gif": ".gif", "md": ".md"}


class BundleError(JobError):
    """A bundle the intake refuses. code is the typed refusal; report is the claims report when the gate refused."""

    def __init__(self, code, detail, report=None):
        super().__init__(code, detail)
        self.report = report


# Reading --------------------------------------------------------------------------------------------------------
def regular_file(base, relative, what):
    """base/relative as a regular file inside base, with no symlink on the way."""
    path = Path(base)
    for part in PurePosixPath(relative).parts:
        path = path / part
        if path.is_symlink():
            raise BundleError("asset_missing", f"{what}: {relative} passes through a symlink")
    if not path.is_file():
        raise BundleError("asset_missing", f"{what}: {relative} is not a regular file in the bundle")
    return path


def reject_constant(name):
    raise ValueError(f"{name} is not a JSON number")


def no_duplicates(pairs):
    keys = [k for k, _ in pairs]
    if len(set(keys)) != len(keys):
        raise ValueError("a key repeats in one object")  # the key itself is never echoed: it may be private
    return dict(pairs)


def read_json(bundle, name):
    """A bundle JSON file: regular, at most MAX_JSON_BYTES, no repeated key, numbers as Decimal."""
    path = Path(bundle) / name
    if path.is_symlink() or not path.is_file():
        raise BundleError("bundle_invalid", f"{name} is missing or not a regular file")
    if path.stat().st_size > MAX_JSON_BYTES:
        raise BundleError("bundle_invalid", f"{name} is larger than {MAX_JSON_BYTES} bytes")
    data = path.read_bytes()
    try:
        value = json.loads(
            data.decode("utf-8"),
            parse_float=Decimal,
            parse_int=Decimal,
            parse_constant=reject_constant,
            object_pairs_hook=no_duplicates,
        )
    except (UnicodeDecodeError, ValueError) as exc:
        raise BundleError("bundle_invalid", f"{name}: {exc}") from None
    return value, hashlib.sha256(data).hexdigest()


def natural(value):
    return isinstance(value, Decimal) and value == value.to_integral_value() and value > 0


def fields(value, required, optional, where):
    if not isinstance(value, dict):
        raise BundleError("bundle_invalid", f"{where} is not an object")
    missing, unknown = sorted(required - set(value)), set(value) - required - optional
    if missing or unknown:  # the required names are this module's; an unknown key is counted, never echoed
        raise BundleError("bundle_invalid", f"{where}: missing {missing}, holds {len(unknown)} unknown fields")


def png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    if len(head) < 24 or head[12:16] != b"IHDR":
        return None
    return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")


def kind_problem(path, kind):
    """Why path's bytes are not a kind file, or None."""
    with open(path, "rb") as f:
        head = f.read(12)
    if kind == "png" and not head.startswith(PNG_MAGIC):
        return "is not a PNG"
    if kind == "mp4" and head[4:8] != b"ftyp":
        return "is not an MP4 (no ftyp box)"
    if kind == "gif" and head[:6] not in (b"GIF87a", b"GIF89a"):
        return "is not a GIF"
    return None


def read_manifest(bundle):
    """({asset id: asset}, manifest sha256). Every asset's file is re-hashed against its sha256."""
    manifest, digest = read_json(bundle, MANIFEST)
    fields(manifest, MANIFEST_FIELDS, MANIFEST_OPTIONAL, MANIFEST)
    if "slug" in manifest and manifest["slug"] != Path(bundle).resolve().name:
        raise BundleError("bundle_invalid", f"{MANIFEST}: slug is not the bundle directory's name")
    if not isinstance(manifest["assets"], list) or not manifest["assets"]:
        raise BundleError("bundle_invalid", f"{MANIFEST}: assets is not a non-empty list")
    assets = {}
    for n, asset in enumerate(manifest["assets"]):
        where = f"{MANIFEST} assets[{n}]"
        fields(asset, ASSET_FIELDS, ASSET_OPTIONAL, where)
        if not isinstance(asset["id"], str) or not ID.match(asset["id"]):
            raise BundleError("bundle_invalid", f"{where}: id is not 1 to 64 of a-z, 0-9, '.', '_' and '-'")
        where = f"asset {asset['id']}"
        if asset["id"] in assets:
            raise BundleError("bundle_invalid", f"{where}: the id repeats")
        if asset["kind"] not in ASSET_KINDS:
            raise BundleError("bundle_invalid", f"{where}: kind is not png, mp4 or gif")
        if not isinstance(asset["sha256"], str) or not SHA256.match(asset["sha256"]):
            raise BundleError("bundle_invalid", f"{where}: sha256 is not 64 lowercase hex digits")
        if not isinstance(asset["receipt"], str) or not asset["receipt"].strip():
            raise BundleError("asset_unreceipted", f"{where}: receipt is empty; every asset names its source receipt")
        path = asset["path"]
        parts = path.split("/") if isinstance(path, str) else [""]
        if "\\" in "".join(parts) or any(p in ("", ".", "..") for p in parts):
            raise BundleError("bundle_invalid", f"{where}: path is not a relative path inside the bundle")
        if not path.lower().endswith(SUFFIX[asset["kind"]]):
            raise BundleError("asset_kind_mismatch", f"{where}: path does not end in {SUFFIX[asset['kind']]}")
        for key, names in (("size", ("w", "h")), ("fps", ("num", "den"))):
            if key in asset:
                fields(asset[key], set(names), set(), f"{where} {key}")
                if not all(natural(asset[key][k]) for k in names):
                    raise BundleError("bundle_invalid", f"{where}: {key} values are not whole numbers above 0")
        file = regular_file(bundle, path, where)
        if sha256_file(file) != asset["sha256"]:
            raise BundleError("asset_digest_mismatch", f"{where}: {path} does not hash to its manifest sha256")
        problem = kind_problem(file, asset["kind"])
        if problem:
            raise BundleError("asset_kind_mismatch", f"{where}: {path} {problem}")
        if asset["kind"] == "png" and "size" in asset:
            size = png_size(file)
            if size != (int(asset["size"]["w"]), int(asset["size"]["h"])):
                raise BundleError("asset_kind_mismatch", f"{where}: the PNG is {size}, not its manifest size")
        assets[asset["id"]] = asset | {"file": file}
    return assets, digest


def read_script(bundle):
    """([beat], script sha256). A beat is {id, line, target_s (Decimal), asset_id, claims [ids], voiced}."""
    path = Path(bundle) / SCRIPT
    if path.is_symlink() or not path.is_file():
        raise BundleError("bundle_invalid", f"{SCRIPT} is missing or not a regular file")
    if path.stat().st_size > MAX_SCRIPT_BYTES:
        raise BundleError("bundle_invalid", f"{SCRIPT} is larger than {MAX_SCRIPT_BYTES} bytes")
    data = path.read_bytes()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BundleError("bundle_invalid", f"{SCRIPT}: {exc}") from None
    return parse_script(text), hashlib.sha256(data).hexdigest()


def parse_script(text):
    beats, beat, fence, titled = [], None, None, False

    def bad(number, why, code="script_invalid"):
        raise BundleError(code, f"{SCRIPT} line {number}: {why}")

    def close(b):
        if b is None:
            return
        where = f"beat {b['id']} (line {b['line']})"
        for key in META_KEYS:
            if key not in b["meta"]:
                raise BundleError("beat_invalid", f"{where}: no `- {key}:` line")
        if b["voiced"] is None or not b["voiced"].strip():
            raise BundleError("beat_voiced_missing", f"{where}: no ```voiced block with the words to speak")
        target = b["meta"]["target_s"]
        if not TARGET.match(target) or not 0 < Decimal(target) <= MAX_TARGET_S:
            raise BundleError("beat_invalid", f"{where}: target_s is not seconds above 0 and at most 3600")
        asset_id = b["meta"]["asset_id"]
        if not ID.match(asset_id):
            raise BundleError("beat_invalid", f"{where}: asset_id is not an asset id")
        cited = [c.strip() for c in b["meta"]["claims"].split(",")] if b["meta"]["claims"] else []
        if any(not ID.match(c) for c in cited) or len(set(cited)) != len(cited):
            raise BundleError("beat_invalid", f"{where}: claims is not a comma-separated list of distinct claim ids")
        beats.append(
            {
                "id": b["id"],
                "line": b["line"],
                "target_s": Decimal(target),
                "asset_id": asset_id,
                "claims": cited,
                "voiced": b["voiced"],
            }
        )

    for number, line in enumerate(text.splitlines(), 1):
        if fence is not None:
            if line.rstrip() == FENCE:
                beat["voiced"] = "\n".join(fence).strip("\n")
                fence = None
            else:
                fence.append(line)
            continue
        if not line.strip() or line.startswith(">"):
            continue
        heading = HEADING.match(line)
        if heading:
            close(beat)
            if not ID.match(heading["id"]):
                bad(number, "the beat id is not 1 to 64 of a-z, 0-9, '.', '_' and '-'", "beat_invalid")
            if any(b["id"] == heading["id"] for b in beats):
                bad(number, f"beat id {heading['id']} repeats", "beat_invalid")
            beat = {"id": heading["id"], "line": number, "meta": {}, "voiced": None}
            continue
        if beat is None:
            if line.startswith("# ") and not titled:
                titled = True
                continue
            bad(number, "before the first `## beat-id` heading only a `# title` line, notes (`>`) and blank lines")
        meta = META.match(line)
        if meta:
            key = meta["key"]
            if key not in META_KEYS:
                bad(number, f"`- {key}:` is not one of {', '.join(META_KEYS)}", "beat_invalid")
            if key in beat["meta"]:
                bad(number, f"`- {key}:` repeats in beat {beat['id']}", "beat_invalid")
            beat["meta"][key] = meta["value"].strip()
            continue
        if line.rstrip() == VOICED_FENCE:
            if beat["voiced"] is not None:
                bad(number, f"beat {beat['id']} has a second voiced block", "beat_invalid")
            fence = []
            continue
        bad(number, "a beat holds only its three `- key: value` lines, one ```voiced block, notes (`>`) and blanks")
    if fence is not None:
        raise BundleError("script_invalid", f"{SCRIPT}: the voiced block of beat {beat['id']} is never closed")
    close(beat)
    if not beats:
        raise BundleError("script_invalid", f"{SCRIPT} has no `## beat-id` beat")
    return beats


def read_claims(bundle):
    """({claim id: claim}, claims sha256). A claim is {id, value: {spoken, number (Decimal), unit}, receipt}."""
    rows, digest = read_json(bundle, CLAIMS)
    if not isinstance(rows, list):
        raise BundleError("bundle_invalid", f"{CLAIMS} is not a list")
    out = {}
    for n, claim in enumerate(rows):
        fields(claim, {"id", "value", "receipt"}, set(), f"{CLAIMS}[{n}]")
        if not isinstance(claim["id"], str) or not ID.match(claim["id"]) or claim["id"] in out:
            raise BundleError("claim_invalid", f"{CLAIMS}[{n}]: id is not a new claim id")
        where = f"claim {claim['id']}"
        fields(claim["value"], {"spoken", "number", "unit"}, set(), f"{where} value")
        value = claim["value"]
        if not isinstance(value["number"], Decimal):
            raise BundleError("claim_invalid", f"{where}: value.number is not a JSON number")
        if not isinstance(value["unit"], str) or not gate.unit_valid(value["unit"]):
            raise BundleError("claim_invalid", f"{where}: value.unit is not a unit the gate reads")
        if not isinstance(value["spoken"], str) or not value["spoken"].strip():
            raise BundleError("claim_invalid", f"{where}: value.spoken is empty")
        if claim["receipt"] is not None and not isinstance(claim["receipt"], str):
            raise BundleError("claim_invalid", f"{where}: receipt is not text or null")
        said = gate.extract(value["spoken"])
        if (
            len(said) != 1
            or said[0]["ambiguous"]
            or said[0]["number"] != value["number"]
            or said[0]["unit"] != value["unit"]
        ):
            reads = [(gate.fmt(m["number"]), m["unit"], m["ambiguous"]) for m in said]
            raise BundleError(
                "claim_invalid",
                f"{where}: value.spoken reads as {reads}, not one number {gate.fmt(value['number'])}"
                f" {value['unit'] or '(no unit)'}",
            )
        out[claim["id"]] = claim
    return out, digest


def cited_known(beats, claims):
    for beat in beats:
        unknown = [c for c in beat["claims"] if c not in claims]
        if unknown:
            raise BundleError("claim_unknown", f"beat {beat['id']} cites claims {unknown} that {CLAIMS} lacks")


def claims_report(beats, claims):
    """[{segment, status, codes, mentions, unused_claims}], one row per beat, in order."""
    return [{"segment": b["id"]} | gate.check_segment(b["voiced"], b["claims"], claims) for b in beats]


def gate_refusal(report):
    """A BundleError for the first refused segment of a claims report, or None when every segment passed."""
    refused = [r for r in report if r["status"] == "refused"]
    if not refused:
        return None
    first = refused[0]
    bad = next(m for m in first["mentions"] if m["status"] == "refused")
    detail = (
        f"{len(refused)} of {len(report)} segments refused; segment {first['segment']}: {bad['code']} for"
        f" {bad['text']!r}"
    )
    return BundleError(first["codes"][0], detail, report)


def read_privacy(bundle):
    """(declaration, manifest): the manifest's privacy declaration {ip_private, never_name, denylist_sha256}, read
    without an asset, and the parsed manifest."""
    manifest, _ = read_json(bundle, MANIFEST)
    fields(manifest, MANIFEST_FIELDS, MANIFEST_OPTIONAL, MANIFEST)
    try:
        return private_terms.declaration(manifest.get("privacy")), manifest
    except private_terms.PrivateError as exc:
        raise BundleError(exc.code, exc.detail) from None


def private_guard(declared, denylist, pin=None, bundle=None):
    """The bundle's private-terms guard: the denylist is read and checked when the manifest declares private terms,
    a denylist is given or the operator pins one."""
    try:
        return private_terms.Guard(declared, denylist, pin, bundle)
    except private_terms.PrivateError as exc:
        raise BundleError(exc.code, exc.detail) from None


def private_check(guard, texts):
    """The guard's report for texts; a match raises BundleError private_term carrying the report."""
    try:
        return guard.check(texts)
    except private_terms.PrivateError as exc:
        raise BundleError(exc.code, exc.detail, exc.report) from None


# The guard's own refusals name positions only, so they are never withheld.
GUARD_CODES = {
    "denylist_missing", "denylist_misplaced", "denylist_digest_mismatch", "denylist_invalid", "denylist_pin_invalid",
    "privacy_undeclared", "private_term",
}  # fmt: skip


@contextlib.contextmanager
def withheld(state):
    """Withhold the detail of any refusal raised inside that says a private term (F9). state["entries"] is the
    denylist's entries: preloaded before the manifest is read, then the bound guard's. A refusal of the guard's own
    passes as it is; any other refusal whose detail an entry matches, or every one while the denylist is given but
    unreadable or while the lane is private (state["pinned"]: a pin is set) and no denylist is bound yet, keeps its
    code and loses its detail and report."""
    try:
        yield
    except BundleError as exc:
        if exc.code in GUARD_CODES:
            raise
        entries = state.get("entries")
        if entries is None and state.get("pinned"):
            entries = False  # a pinned lane is private: with no denylist to test against, withhold every detail
        detail = private_terms.redact(entries, exc.code, exc.detail)
        if detail == exc.detail:
            raise
        raise BundleError(exc.code, detail) from None


def guarded_read(bundle, denylist, pin, state):
    """(beats, claims, digests, guard, private): the privacy declaration and the guard first, then script.md and
    claims.json, then the record, voiced and claim texts through the guard. Every refusal passes withheld()."""
    state.setdefault("entries", private_terms.preload(denylist))
    state.setdefault("pinned", private_terms.pinned(pin))
    with withheld(state):
        declared, manifest = read_privacy(bundle)
        guard = private_guard(declared, denylist, pin, bundle)
        if guard.entries is not None:
            state["entries"] = guard.entries
        beats, script_digest = read_script(bundle)
        claims, claims_digest = read_claims(bundle)
        cited_known(beats, claims)
        private_check(guard, private_terms.record_texts(manifest, beats, claims))
        private = private_check(guard, private_terms.written_texts(beats, claims))
    digests = {"script_sha256": script_digest, "claims_sha256": claims_digest}
    return beats, claims, digests, guard, private


def read_claims_only(bundle, denylist=None, pin=None, state=None):
    """The claims gate alone: script.md, claims.json and the manifest's privacy declaration, no asset. The
    private-terms guard is built first and runs on the record texts and then on every voiced text and claim text,
    and refuses before the number gate."""
    beats, claims, digests, guard, private = guarded_read(bundle, denylist, pin, {} if state is None else state)
    return beats, claims_report(beats, claims), digests, guard, private


def read(bundle, denylist=None, pin=None, state=None):
    """The parsed bundle: {slug, assets, beats, claims, report, digests}. Refuses structure, assets and references;
    the claims report is returned, not raised, so a caller can print it. The private-terms guard runs before any
    asset is read, and every refusal passes withheld()."""
    bundle = Path(bundle)
    if not bundle.is_dir():
        raise BundleError("bundle_invalid", "the bundle is not a directory")
    state = {} if state is None else state
    beats, report, digests, guard, private = read_claims_only(bundle, denylist, pin, state)
    with withheld(state):
        return read_assets(bundle, beats, report, digests, guard, private)


def read_assets(bundle, beats, report, digests, guard, private):
    assets, manifest_digest = read_manifest(bundle)
    videos = set()
    for beat in beats:
        asset = assets.get(beat["asset_id"])
        if asset is None:
            raise BundleError("asset_unknown", f"beat {beat['id']}: asset {beat['asset_id']} is not in {MANIFEST}")
        if asset["kind"] == "gif":
            raise BundleError(
                "asset_needs_conversion",
                f"beat {beat['id']}: asset {asset['id']} is a GIF. No narrated-video stage reads GIF (a slide is a"
                " still picture and the base is one video): convert it to a PNG still or an MP4 clip in the bundle,"
                " with its own sha256 and receipt, and cite that asset",
            )
        if asset["kind"] == "mp4":
            videos.add(asset["sha256"])
    if len(videos) > 1:
        raise BundleError(
            "asset_video_multiple",
            f"beats use {len(videos)} different MP4 assets; one MP4 becomes the base video and no stage joins clips",
        )
    return {
        "slug": bundle.resolve().name,
        "root": bundle,
        "assets": assets,
        "beats": beats,
        "report": report,
        "digests": {"manifest_sha256": manifest_digest} | digests,
        "guard": guard,
        "private": private,
    }


# Converting -----------------------------------------------------------------------------------------------------
def number(value):
    """A Decimal as the JSON number dhall-to-json writes: an integer when integral, else a float."""
    return int(value) if value == value.to_integral_value() else float(value)


def voiced_markdown(beat):
    """The narrate Markdown input of one beat: front matter (slide, target_seconds) and the voiced text."""
    return f"---\nslide: {beat['id']}\ntarget_seconds: {beat['target_s']}\n---\n\n{beat['voiced']}\n".encode()


def paragraphs(text):
    return [" ".join(p.split()) for p in re.split(r"\n\s*\n", text) if p.strip()]


def check_verbatim(beat, data):
    """The Markdown adapter must speak the voiced text as written: no markup, [direction], heading or Sources line."""
    try:
        script = adapters.markdown(data.decode(), name=beat["id"])
    except InputError as exc:
        raise BundleError("voiced_not_verbatim", f"beat {beat['id']}: {exc}") from None
    said = [" ".join(p.split()) for s in script.segments for p in s.paragraphs()]
    if said != paragraphs(beat["voiced"]):
        raise BundleError(
            "voiced_not_verbatim",
            f"beat {beat['id']}: narrate's Markdown adapter would not speak the voiced text as written (inline markup,"
            " a [bracketed] line, a heading or a Sources: line); write the words as plain text",
        )


def narrate_jobs(b, records, job_id, template, voice, engine):
    """{beat id: (narrate Job record, Markdown bytes)}."""
    check = port()
    base = records["jobs"].get(template)
    if base is None:
        raise BundleError("narrate_job_missing", f"template narrate job {template} is unknown")
    if set(base) != NARRATE_JOB_FIELDS:
        raise BundleError("records_invalid", f"template narrate job {template} is not a narrate Job record")
    engine_record = records["engines"].get(engine)
    if engine_record is None:
        raise BundleError("engine_unknown", f"engine {engine} has no record")
    if not check.may_run_confidential(engine_record):
        raise BundleError("confidential_engine_refused", f"engine {engine} may not run a confidential job")
    voice_record = records["voices"].get(voice)
    if voice_record is None:
        raise BundleError("voice_unknown", f"voice {voice} has no record")
    if engine not in voice_record.get("allowedEngines", []):
        raise BundleError("engine_not_allowed", f"voice {voice} does not allow engine {engine}")
    if voice_record.get("scope") != base["scope"]:
        raise BundleError("consent_scope", f"voice {voice}'s scope is not template {template}'s scope")
    out = {}
    for beat in b["beats"]:
        narrate_id = f"{job_id}-{beat['id']}"
        if not ID.match(narrate_id):
            raise BundleError("job_invalid", f"narrate job id {narrate_id} is longer than 64; pass a shorter --job")
        data = voiced_markdown(beat)
        check_verbatim(beat, data)
        record = copy.deepcopy(base) | {
            "id": narrate_id,
            "input": "Markdown",
            "inputSha256": hashlib.sha256(data).hexdigest(),
            "confidential": True,
            "allowHosted": False,
            "voice": voice,
            "speakers": [],
            "engine": engine,
        }
        out[beat["id"]] = (record, data)
    return out


def number_words(text):
    """The number-like tokens text speaks, as a multiset: each digit token's digit groups and each number word,
    vague quantity or Roman numeral. A unit a table spells out ("LUFS" said in words) is not a number word."""
    return Counter(
        tuple(re.findall(r"[0-9]+", t.text)) if t.kind == "num" else t.low
        for t in gate.tokens(text)
        if gate.numberish(t)
    )


def pronunciation_check(b, records, template):
    """The template's pronunciation tables must not make narrate say a number the voiced text does not: each beat's
    paragraphs go through Normaliser.say, as narrate's render does, and the spoken form may hold no number word or
    digit group that the written form lacks (number_words). With the narration register pinned, the upstream
    xoxd-lexical table runs too, from NARRATE_LEXICAL_DIR. Returns {table, upstream, said}: the table id, the pinned
    release or None, and each paragraph's spoken form as (beat id, "spoken", text) for the private-terms guard."""
    base = records["jobs"][template]
    table = records["pronunciation"].get(base["pronunciation"])
    if table is None:
        raise BundleError("pronunciation_unknown", f"template {template}'s pronunciation table has no record")
    pin, upstream = base["lexical"], None
    if pin.get("valeRegister") == "narration":
        directory = os.environ.get(LEXICAL_ENV)
        try:
            upstream = lexical.Release(Path(directory) if directory else None, pin).upstream_pronunciation
        except lexical.LexicalError as exc:
            raise BundleError(
                exc.code,
                f"template {template} pins the narration register, whose pronunciation table the intake reads to"
                f" check spoken numbers: {exc.detail}",
            ) from None
    normaliser = Normaliser(table, upstream=upstream)
    said_texts = []
    for beat in b["beats"]:
        for paragraph in paragraphs(beat["voiced"]):
            try:
                spoken = normaliser.say(paragraph, beat["id"], record=False)
            except NormaliseError as exc:
                raise BundleError("pronunciation_refused", f"beat {beat['id']}: {exc}") from None
            said_texts.append((beat["id"], "spoken", spoken))
            added = number_words(spoken) - number_words(paragraph)
            if added:
                said = sorted(" ".join(w) if isinstance(w, tuple) else w for w in added.elements())
                raise BundleError(
                    "pronunciation_adds_number",
                    f"beat {beat['id']}: the pronunciation tables make narrate say {', '.join(said)}, which the voiced"
                    " text does not; no claim backs a number a table adds",
                )
    return {
        "table": base["pronunciation"],
        "upstream": pin["release"] if upstream is not None else None,
        "said": said_texts,
    }


def convert(b, records, *, job_id, template, voice, engine, persona=None, tail_s=None):
    """(NarratedVideo record, {beat id: (narrate Job record, Markdown bytes)}).

    One segment per beat, anchored at the beat's start: beats run back to back from 0, each target_s long. A PNG beat
    shows its picture as a Full slide page over the beat's span; an MP4 beat shows the base, which is that MP4. With
    no MP4 the base is the default card. Edition Internal; the avatar is on with persona, off without it."""
    if not ID.match(job_id):
        raise BundleError("job_invalid", "the job id is not 1 to 64 of a-z, 0-9, '.', '_' and '-'")
    jobs = narrate_jobs(b, records, job_id, template, voice, engine)
    d = DEFAULTS
    segments, pages, start, video = [], [], Decimal(0), None
    for beat in b["beats"]:
        asset = b["assets"][beat["asset_id"]]
        end = start + beat["target_s"]
        record, data = jobs[beat["id"]]
        segments.append(
            {
                "id": beat["id"],
                "narrateJob": record["id"],
                "scriptSha256": record["inputSha256"],
                "anchor": {"atSeconds": number(start)},
                "avatar": True,
            }
        )
        show = {"slide": {"sha256": asset["sha256"]}} if asset["kind"] == "png" else "Base"
        pages.append({"id": beat["id"], "startS": number(start), "endS": number(end), "show": show})
        if asset["kind"] == "mp4":
            video = asset["sha256"]
        start = end
    if video is not None:
        base = {"video": {"sha256": video, "keepBaseAudio": False}}
    else:
        picture = {"size": copy.deepcopy(d["size"]), "fps": copy.deepcopy(d["fps"])}
        base = {"card": {"colour": d["colour"]} | picture | {"tailS": d["tailS"] if tail_s is None else tail_s}}
    slides = None
    if any(isinstance(p["show"], dict) for p in pages):
        slides = copy.deepcopy(d["slides"]) | {"pages": pages}
    job = {
        "id": job_id,
        "edition": EDITION,
        "base": base,
        "segments": segments,
        "avatar": copy.deepcopy(d["avatar"]) if persona else None,
        "slides": slides,
        "music": None,
        "tighten": copy.deepcopy(d["tighten"]),
        "captions": copy.deepcopy(d["captions"]),
        "labels": copy.deepcopy(d["labels"]) | {"persona": persona},
        "delivery": copy.deepcopy(d["delivery"]),
    }
    return check_shape(job), jobs


# Writing --------------------------------------------------------------------------------------------------------
def write_json(path, value):
    path.write_text(json.dumps(value, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def held(target, digest):
    """True when the store already holds target with digest; refuses store_conflict for anything else there."""
    if not target.is_symlink() and not target.exists():
        return False
    if target.is_symlink() or not target.is_file() or sha256_file(target) != digest:
        raise BundleError("store_conflict", f"the store holds a different file named {target.name}")
    return True


def open_asset(root, relative, where):
    """A read-only descriptor of root/relative, every component opened without following a symlink."""
    parts = PurePosixPath(relative).parts
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        asset = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
    except OSError:
        raise BundleError("asset_missing", f"{where}: {relative} is gone or passes through a symlink") from None
    finally:
        os.close(fd)
    if not stat.S_ISREG(os.fstat(asset).st_mode):
        os.close(asset)
        raise BundleError("asset_missing", f"{where}: {relative} is not a regular file in the bundle")
    return asset


def stage(directory, digest, data=None, source=None, where="a source"):
    """A new temporary file in directory holding data, or the bytes read from the descriptor source. It must hash to
    digest (the manifest sha256 for an asset): else it is removed and the intake refuses asset_digest_mismatch."""
    fd, name = tempfile.mkstemp(prefix=".intake-", suffix=".part", dir=directory)
    path, hasher = Path(name), hashlib.sha256()
    try:
        os.fchmod(fd, umask_mode(0o666))
        with os.fdopen(fd, "wb") as out:
            if data is not None:
                hasher.update(data)
                out.write(data)
            else:
                with os.fdopen(source, "rb") as f:
                    while chunk := f.read(1 << 20):
                        hasher.update(chunk)
                        out.write(chunk)
        if hasher.hexdigest() != digest:
            raise BundleError(
                "asset_digest_mismatch",
                f"{where} changed after it was read: its copy does not hash to its manifest sha256",
            )
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


def commit(part, target, digest):
    """Move a staged file to target without replacing anything. True when target is new."""
    try:
        os.link(part, target)
    except FileExistsError:
        held(target, digest)
        return False
    except OSError:
        if held(target, digest):
            return False
        os.rename(part, target)
        return True
    finally:
        part.unlink(missing_ok=True)
    return True


def umask_mode(mode):
    """mode under the process umask, as open() and mkdir() would create it: mkstemp and mkdtemp use 0600 and 0700."""
    current = os.umask(0)
    os.umask(current)
    return mode & ~current


def make_dirs(path):
    """Create path and its missing parents; the directories created, outermost first."""
    missing, p = [], Path(path)
    while not p.exists():
        missing.append(p)
        p = p.parent
    for d in reversed(missing):
        d.mkdir()
    return list(reversed(missing))


def merged_records(records_dir, new_jobs):
    """{file name: rows} for the output records directory: the input renders, with the new narrate jobs in jobs.json.
    A new id that the input already holds must be the same record."""
    tables = {}
    for name in RECORD_FILES.values():
        path = Path(records_dir) / name
        if path.is_file() and not path.is_symlink():
            tables[name] = json.loads(path.read_text(encoding="utf-8"))
    jobs = tables["jobs.json"]
    jobs = [jobs] if isinstance(jobs, dict) else list(jobs)
    held = {j["id"]: j for j in jobs}
    for record in new_jobs:
        if record["id"] in held:
            if held[record["id"]] != record:
                raise BundleError("narrate_job_exists", f"records hold a different narrate job {record['id']}")
            continue
        jobs.append(record)
    tables["jobs.json"] = jobs
    return tables


def intake(
    bundle, out, records_dir, *, job_id=None, template, voice, engine, persona=None, tail_s=None, store=None,
    denylist=None, pin=None,
):  # fmt: skip
    """Read, gate, convert, check and write one bundle. Returns the intake manifest written to out/intake.json.

    out must be new or empty. It receives narrated-video.json (the NarratedVideo record), records/ (the input
    renders with one narrate job per beat added to jobs.json) and intake.json; store (default out/store) receives
    each beat's Markdown and each used asset as <sha256><suffix>. denylist is the private denylist file that a
    manifest declaring ip_private or never_name binds by digest, and pin the operator's pinned digest of it. Nothing
    is written when any check refuses, and a refusal whose detail says a private term is withheld."""
    state = {"entries": private_terms.preload(denylist), "pinned": private_terms.pinned(pin)}
    with withheld(state):
        return guarded_intake(bundle, out, records_dir, state, job_id=job_id, template=template, voice=voice,
                              engine=engine, persona=persona, tail_s=tail_s, store=store, denylist=denylist,
                              pin=pin)  # fmt: skip


def guarded_intake(
    bundle, out, records_dir, state, *, job_id, template, voice, engine, persona, tail_s, store, denylist, pin
):  # fmt: skip
    out = Path(out)
    if out.is_symlink() or (out.exists() and (not out.is_dir() or any(out.iterdir()))):
        raise BundleError("out_exists", "--out must be a new or empty directory")
    store = Path(store) if store else out / "store"
    within = store.resolve() == out.resolve() or out.resolve() in store.resolve().parents
    if store.resolve() == out.resolve():
        raise BundleError("store_conflict", "--store must not be --out itself")
    b = read(bundle, denylist, pin, state)
    job_id = job_id or b["slug"]
    private_check(b["guard"], [("slug", "record", b["slug"]), ("job", "record", job_id)])  # the directory's name
    if persona is not None:
        private_check(b["guard"], [("labels", "label", persona)])
    refused = gate_refusal(b["report"])
    if refused:
        raise refused
    records = load_records(records_dir, marker_optional=True)
    job, jobs = convert(
        b, records, job_id=job_id, template=template, voice=voice, engine=engine, persona=persona, tail_s=tail_s
    )
    new_jobs = [record for record, _ in jobs.values()]
    tables = merged_records(records_dir, new_jobs)
    checked = copy.deepcopy(records)
    checked["jobs"] = {j["id"]: j for j in tables["jobs.json"]}
    verdict = admit(job, checked)
    if verdict["verdict"] != "Admitted":
        first = verdict["refusals"][0]
        raise BundleError(first["code"], f"admit: {first['detail']}")
    spoken = pronunciation_check(b, records, template)
    b["private"] = private_check(b["guard"], spoken["said"] + private_terms.joined(spoken["said"]))

    used = {beat["asset_id"] for beat in b["beats"]}
    sources = {}  # store file name: (digest, Markdown bytes or None, asset or None)
    for beat in b["beats"]:
        record, data = jobs[beat["id"]]
        sources[f"{record['inputSha256']}.md"] = (record["inputSha256"], data, None)
    for asset_id in sorted(used):
        asset = b["assets"][asset_id]
        sources[f"{asset['sha256']}{SUFFIX[asset['kind']]}"] = (asset["sha256"], None, asset)
    if not within:
        for name, (digest, _, _) in sources.items():
            held(store / name, digest)  # store_conflict before anything is written
    manifest = write_intake(out, store, within, sources, b, job, jobs, tables, verdict, template, voice, engine, spoken)
    return manifest


def write_intake(out, store, within, sources, b, job, jobs, tables, verdict, template, voice, engine, spoken):
    """Write the checked intake: stage every store file and the output tree, then commit them. On any failure every
    staged file, new store file and new directory is removed."""
    created, parts, new_store, staging = [], [], [], None
    try:
        created += make_dirs(out.parent)
        staging = Path(tempfile.mkdtemp(prefix=f".{out.name}.intake-", dir=out.parent))
        staging.chmod(umask_mode(0o777))
        if within:
            store_dir = staging / store.resolve().relative_to(out.resolve())
            store_dir.mkdir(parents=True)
        else:
            store_dir = store
            created += make_dirs(store)
        for name, (digest, data, asset) in sources.items():
            if not within and held(store / name, digest):
                continue
            where = "a beat script" if asset is None else f"asset {asset['id']}"
            source = None if asset is None else open_asset(b["root"], asset["path"], where)
            parts.append((stage(store_dir, digest, data, source, where), store_dir / name, digest))
        manifest = intake_manifest(staging, store_dir, sources, b, job, jobs, tables, verdict, template, voice,
                                   engine, spoken)  # fmt: skip
        for part, target, digest in parts:
            if commit(part, target, digest) and not within:
                new_store.append(target)
        parts = []
        try:
            os.rename(staging, out)
        except OSError:
            raise BundleError("out_exists", "--out appeared or filled while the intake ran") from None
        staging = None
        return manifest
    except BaseException:
        for part, _, _ in parts:
            part.unlink(missing_ok=True)
        for target in new_store:
            target.unlink(missing_ok=True)
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)
        for d in reversed(created):
            try:
                d.rmdir()
            except OSError:
                pass
        raise


def intake_manifest(staging, store_dir, sources, b, job, jobs, tables, verdict, template, voice, engine, spoken):
    """Write records/, narrated-video.json and intake.json into the staging directory; returns the manifest."""
    (staging / "records").mkdir()
    for name, rows in tables.items():
        write_json(staging / "records" / name, rows)
    write_json(staging / "narrated-video.json", job)
    if b["guard"].entries is not None:  # a later edit to a narrate job, its table or this job refuses (F8)
        written = load_records(staging / "records", marker_optional=True)  # digests as a later load reads them
        narrate_jobs = [written["jobs"][r["id"]] for r, _ in jobs.values()]
        read_back = check_shape(json.loads((staging / "narrated-video.json").read_text(encoding="utf-8")))
        marker = private_terms.marker(b["private"], narrate_jobs, written, read_back)  # as nv init --from reads it
        write_json(staging / "records" / private_terms.MARKER, marker)
    used = {beat["asset_id"] for beat in b["beats"]}
    report = {r["segment"]: r for r in b["report"]}
    start = Decimal(0)
    segments = []
    for beat in b["beats"]:
        asset = b["assets"][beat["asset_id"]]
        record, _ = jobs[beat["id"]]
        end = start + beat["target_s"]
        segments.append(
            {
                "segment": beat["id"],
                "narrate_job": record["id"],
                "script_sha256": record["inputSha256"],
                "start_s": number(start),
                "end_s": number(end),
                "asset": {"id": asset["id"], "kind": asset["kind"], "sha256": asset["sha256"],
                          "receipt": asset["receipt"]},
                "show": "slide" if asset["kind"] == "png" else "base",
                "claims": {k: v for k, v in report[beat["id"]].items() if k != "segment"},
            }
        )  # fmt: skip
        start = end
    written = [p for p in sorted(staging.rglob("*")) if p.is_file() and store_dir not in p.parents]
    outputs = {str(p.relative_to(staging)): sha256_file(p) for p in written}
    manifest = {
        "kind": "nv_bundle_intake",
        "schema_version": 1,
        "linear": "TIN-7735",
        "bundle": {"slug": b["slug"]} | b["digests"],
        "job_id": job["id"],
        "job_sha256": hashlib.sha256(canonical(job).encode()).hexdigest(),
        "edition": job["edition"],
        "narrate": {"template": template, "voice": voice, "engine": engine, "confidential": True,
                    "allowHosted": False, "input": "Markdown", "pronunciation": spoken["table"],
                    "pronunciation_upstream": spoken["upstream"]},
        "segments": segments,
        "unused_assets": sorted(set(b["assets"]) - used),
        "sources": sorted({digest for digest, _, _ in sources.values()}),
        "outputs": outputs,
        "admit": {"verdict": verdict["verdict"], "pending_operator": [p["gate"] for p in verdict["pending_operator"]]},
        "private_terms": b["private"],
        "states": {"source_checks": "passed", "claims": "passed", "pronunciation_numbers": "passed",
                   "private_terms": b["private"]["status"], "producer_review": "pending_operator", "render": "not_run",
                   "listening": "pending_operator"},
    }  # fmt: skip
    write_json(staging / "intake.json", manifest)
    return manifest


def claims_only(bundle, denylist=None, pin=None):
    """The claims gate on a bundle's script.md and claims.json, after the private-terms guard:
    {ok, bundle, segments, private_terms}. A private term raises BundleError private_term with the guard's report."""
    _, report, digests, _, private = read_claims_only(bundle, denylist, pin)
    return {"ok": gate_refusal(report) is None, "bundle": digests, "segments": report, "private_terms": private}
