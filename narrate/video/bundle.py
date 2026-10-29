"""Demo bundle intake (docs/spec/NARRATED_VIDEO.md, "Demo bundle intake", TIN-7735).

A demo bundle is a directory (docs/demo/<slug>/ in its producer's private repository) holding manifest.json,
script.md, claims.json and the PNG, MP4 and GIF assets the manifest lists. read() parses it strictly and refuses
with a typed code; claims_report() runs the spoken-number claims gate (claims.py); convert() turns a bundle into the
existing records: one NarratedVideo job and one narrate Job per beat, with no new schema (SPR-84). intake() checks
the result with job.check_shape and admit, then writes it to a new directory.

Everything here reads and writes local files only. Nothing renders, and nothing is published.
"""

import copy
import hashlib
import json
import re
import shutil
from decimal import Decimal
from pathlib import Path, PurePosixPath

from .. import adapters
from ..adapters import InputError
from ..ir import canonical, sha256_file
from . import claims as gate
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
MANIFEST_OPTIONAL = {"slug"}
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
        raise ValueError(f"a key repeats in one object: {sorted(k for k in keys if keys.count(k) > 1)[0]}")
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
    missing, unknown = sorted(required - set(value)), sorted(set(value) - required - optional)
    if missing or unknown:
        raise BundleError("bundle_invalid", f"{where}: missing {missing}, unknown {unknown}")


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
            raise BundleError("bundle_invalid", f"{where}: kind {asset['kind']!r} is not png, mp4 or gif")
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
            raise BundleError("beat_invalid", f"{where}: target_s {target!r} is not seconds above 0 and at most 3600")
        asset_id = b["meta"]["asset_id"]
        if not ID.match(asset_id):
            raise BundleError("beat_invalid", f"{where}: asset_id {asset_id!r} is not an asset id")
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
                bad(number, f"beat id {heading['id']!r} is not 1 to 64 of a-z, 0-9, '.', '_' and '-'", "beat_invalid")
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
            raise BundleError("claim_invalid", f"{where}: value.unit {value['unit']!r} is not a unit the gate reads")
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


def read_claims_only(bundle):
    """The claims gate alone: script.md and claims.json, no manifest or asset."""
    beats, script_digest = read_script(bundle)
    claims, claims_digest = read_claims(bundle)
    cited_known(beats, claims)
    return beats, claims_report(beats, claims), {"script_sha256": script_digest, "claims_sha256": claims_digest}


def read(bundle):
    """The parsed bundle: {slug, assets, beats, claims, report, digests}. Refuses structure, assets and references;
    the claims report is returned, not raised, so a caller can print it."""
    bundle = Path(bundle)
    if not bundle.is_dir():
        raise BundleError("bundle_invalid", "the bundle is not a directory")
    assets, manifest_digest = read_manifest(bundle)
    beats, report, digests = read_claims_only(bundle)
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
        "assets": assets,
        "beats": beats,
        "report": report,
        "digests": {"manifest_sha256": manifest_digest} | digests,
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


def convert(b, records, *, job_id, template, voice, engine, persona=None, tail_s=None):
    """(NarratedVideo record, {beat id: (narrate Job record, Markdown bytes)}).

    One segment per beat, anchored at the beat's start: beats run back to back from 0, each target_s long. A PNG beat
    shows its picture as a Full slide page over the beat's span; an MP4 beat shows the base, which is that MP4. With
    no MP4 the base is the default card. Edition Internal; the avatar is on with persona, off without it."""
    if not ID.match(job_id):
        raise BundleError("job_invalid", f"job id {job_id!r} is not 1 to 64 of a-z, 0-9, '.', '_' and '-'")
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


def put(store, data_or_file, kind):
    """Write one source into the store as <sha256><suffix>; an existing file of that name must hash the same."""
    if isinstance(data_or_file, bytes):
        digest = hashlib.sha256(data_or_file).hexdigest()
    else:
        digest = sha256_file(data_or_file)
    target = store / f"{digest}{SUFFIX[kind]}"
    if target.is_symlink() or (target.exists() and (not target.is_file() or sha256_file(target) != digest)):
        raise BundleError("store_conflict", f"the store holds a different file named {target.name}")
    if not target.exists():
        if isinstance(data_or_file, bytes):
            target.write_bytes(data_or_file)
        else:
            shutil.copyfile(data_or_file, target)
    return digest


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


def intake(bundle, out, records_dir, *, job_id=None, template, voice, engine, persona=None, tail_s=None, store=None):
    """Read, gate, convert, check and write one bundle. Returns the intake manifest written to out/intake.json.

    out must be new or empty. It receives narrated-video.json (the NarratedVideo record), records/ (the input
    renders with one narrate job per beat added to jobs.json) and intake.json; store (default out/store) receives
    each beat's Markdown and each used asset as <sha256><suffix>. Nothing is written when any check refuses."""
    out = Path(out)
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise BundleError("out_exists", "--out must be a new or empty directory")
    b = read(bundle)
    refused = gate_refusal(b["report"])
    if refused:
        raise refused
    job_id = job_id or b["slug"]
    records = load_records(records_dir)
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

    out.mkdir(parents=True, exist_ok=True)
    store = Path(store) if store else out / "store"
    store.mkdir(parents=True, exist_ok=True)
    (out / "records").mkdir()
    for name, rows in tables.items():
        write_json(out / "records" / name, rows)
    write_json(out / "narrated-video.json", job)
    sources = []
    for beat in b["beats"]:
        _, data = jobs[beat["id"]]
        sources.append(put(store, data, "md"))
    used = {beat["asset_id"] for beat in b["beats"]}
    for asset_id in sorted(used):
        asset = b["assets"][asset_id]
        sources.append(put(store, asset["file"], asset["kind"]))
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
    written = [p for p in sorted(out.rglob("*")) if p.is_file() and store not in p.parents]
    outputs = {str(p.relative_to(out)): sha256_file(p) for p in written}
    manifest = {
        "kind": "nv_bundle_intake",
        "schema_version": 1,
        "linear": "TIN-7735",
        "bundle": {"slug": b["slug"]} | b["digests"],
        "job_id": job["id"],
        "job_sha256": hashlib.sha256(canonical(job).encode()).hexdigest(),
        "edition": job["edition"],
        "narrate": {"template": template, "voice": voice, "engine": engine, "confidential": True,
                    "allowHosted": False, "input": "Markdown"},
        "segments": segments,
        "unused_assets": sorted(set(b["assets"]) - used),
        "sources": sorted(set(sources)),
        "outputs": outputs,
        "admit": {"verdict": verdict["verdict"], "pending_operator": [p["gate"] for p in verdict["pending_operator"]]},
        "states": {"source_checks": "passed", "claims": "passed", "render": "not_run",
                   "listening": "pending_operator"},
    }  # fmt: skip
    write_json(out / "intake.json", manifest)
    return manifest


def claims_only(bundle):
    """The claims gate on a bundle's script.md and claims.json: {ok, digests, segments}."""
    _, report, digests = read_claims_only(bundle)
    return {"ok": gate_refusal(report) is None, "bundle": digests, "segments": report}
