"""The private-terms guard of a demo bundle (docs/spec/NARRATED_VIDEO.md, "Private terms", TIN-7735, SPR-220).

A bundle's manifest.json may declare `privacy: {ip_private, never_name, denylist_sha256}`. ip_private marks work
whose numbers and geometry stay private. never_name marks a bundle that must not name a party. When
either is true, or the manifest names a denylist digest, the claims gate needs the denylist: a JSON file kept outside
the bundle and outside git, passed as --denylist and bound by its sha256 in the manifest. The guard refuses
denylist_missing when the file is not given, absent or unbound, denylist_digest_mismatch when its bytes do not hash to
the manifest's digest, and denylist_invalid when it is malformed. It then checks every text the job would speak or
show or record: each beat's voiced text (the captions' text), its spoken form after the pronunciation tables
(intake only), each claim's spoken text, the persona label, and every bundle text that reaches a record or report
(the slug, the job id, beat, claim and asset ids, asset paths and claim and asset receipts). A match refuses
private_term. The record texts are checked first and reported by position (beat#2, not the beat's id), so a report
never carries a private id.

It fails closed. A literal entry matches after NFKC, removal of format characters (zero-width spaces, soft hyphens),
case folding and the collapse of every run of other non-letters and non-digits to one space, at word boundaries: so
"Fixture-Corp's" matches the literal "fixture corp". A number entry matches every mention the claims gate's own
extractor reads as that value, digits or spelled out, with any unit when its unit is null. A regex entry runs on the
NFKC text with format characters removed and again on the literal form, case-insensitive: so `chamfer\\s+angle`
also matches "chamfer-angle.png".

A report names the beat, the text's source and the entry id and class. It never holds the matched text, a literal,
a pattern or a number from the denylist, so a refusal can go to a log. A denylist_invalid detail names an entry by
its position, never by its id, and an entry id that a literal or regex entry matches is refused as denylist_invalid
for the same reason.

Standard library only.
"""

import hashlib
import json
import re
import unicodedata
from decimal import Decimal
from pathlib import Path

from . import claims as gate
from .job import ID, SHA256, JobError

KIND, SCHEMA_VERSION = "nv_denylist", 1
MAX_BYTES = 1024 * 1024
MAX_ENTRIES = 10_000
MAX_LITERAL = 256
MAX_REGEX = 512
CLASSES = ("number", "geometry", "name")
# The class a declaration needs at least one entry of: a never_name denylist that names nobody is malformed.
NEEDS = {"ip_private": {"number", "geometry"}, "never_name": {"name"}}
PRIVACY_FIELDS = {"ip_private", "never_name"}
PRIVACY_OPTIONAL = {"denylist_sha256"}
SOURCES = ("record", "voiced", "spoken", "claim", "label")


class PrivateError(JobError):
    """A refused denylist or a private term. report is the guard's report when a term matched."""

    def __init__(self, code, detail, report=None):
        super().__init__(code, detail)
        self.report = report


def folded(text):
    """text for a literal match: NFKC, no format characters, case-folded, other non-word runs as one space, padded."""
    text = "".join(ch for ch in unicodedata.normalize("NFKC", text) if unicodedata.category(ch) != "Cf")
    return " " + re.sub(r"[\W_]+", " ", text.casefold()).strip() + " "


def plain(text):
    """text for a regex match: NFKC with no format characters."""
    return "".join(ch for ch in unicodedata.normalize("NFKC", text) if unicodedata.category(ch) != "Cf")


# The manifest declaration ---------------------------------------------------------------------------------------
def declaration(value, where="manifest.json privacy"):
    """{ip_private, never_name, denylist_sha256 or None} from a manifest's privacy value (None when absent)."""
    if value is None:
        return {"ip_private": False, "never_name": False, "denylist_sha256": None}
    if not isinstance(value, dict):
        raise PrivateError("bundle_invalid", f"{where} is not an object")
    missing = sorted(PRIVACY_FIELDS - set(value))
    unknown = sorted(set(value) - PRIVACY_FIELDS - PRIVACY_OPTIONAL)
    if missing or unknown:
        raise PrivateError("bundle_invalid", f"{where}: missing {missing}, unknown {unknown}")
    for key in sorted(PRIVACY_FIELDS):
        if not isinstance(value[key], bool):
            raise PrivateError("bundle_invalid", f"{where}: {key} is not true or false")
    digest = value.get("denylist_sha256")
    if digest is not None and (not isinstance(digest, str) or not SHA256.match(digest)):
        raise PrivateError("bundle_invalid", f"{where}: denylist_sha256 is not 64 lowercase hex digits")
    return {"ip_private": value["ip_private"], "never_name": value["never_name"], "denylist_sha256": digest}


def required(declared):
    return declared["ip_private"] or declared["never_name"] or declared["denylist_sha256"] is not None


# The denylist ---------------------------------------------------------------------------------------------------
def reject_constant(name):
    raise ValueError(f"{name} is not a JSON number")


def no_duplicates(pairs):
    keys = [k for k, _ in pairs]
    if len(set(keys)) != len(keys):
        raise ValueError("a key repeats in one object")
    return dict(pairs)


def bad(detail):
    raise PrivateError("denylist_invalid", f"the denylist {detail}")


def read_denylist(path, declared):
    """([entry], sha256) of the denylist file at path, checked against the declaration. Never echoes its content."""
    if path is None:
        raise PrivateError("denylist_missing", "the bundle declares private terms and no --denylist was given")
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise PrivateError("denylist_missing", "the --denylist file is missing or not a regular file")
    if path.stat().st_size > MAX_BYTES:
        bad(f"is larger than {MAX_BYTES} bytes")
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if declared["denylist_sha256"] is None and (declared["ip_private"] or declared["never_name"]):
        raise PrivateError("denylist_missing", "manifest.json declares private terms but names no denylist_sha256")
    if declared["denylist_sha256"] is not None and digest != declared["denylist_sha256"]:
        raise PrivateError("denylist_digest_mismatch", "the --denylist file does not hash to the manifest's digest")
    try:
        value = json.loads(
            data.decode("utf-8"),
            parse_float=Decimal,
            parse_int=Decimal,
            parse_constant=reject_constant,
            object_pairs_hook=no_duplicates,
        )
    except (UnicodeDecodeError, ValueError):
        bad("is not UTF-8 JSON with distinct keys and finite numbers")
    if not isinstance(value, dict) or set(value) != {"kind", "schema_version", "entries"}:
        bad("is not {kind, schema_version, entries}")
    if value["kind"] != KIND or value["schema_version"] != SCHEMA_VERSION:
        bad(f"is not kind {KIND} schema_version {SCHEMA_VERSION}")
    rows = value["entries"]
    if not isinstance(rows, list) or not rows or len(rows) > MAX_ENTRIES:
        bad(f"entries is not a list of 1 to {MAX_ENTRIES} entries")
    entries, ids = [], set()
    for n, row in enumerate(rows):
        entries.append(entry(row, n, ids))
    for key, classes in NEEDS.items():
        if declared[key] and not any(e["class"] in classes for e in entries):
            bad(f"holds no {' or '.join(sorted(classes))} entry, which {key} needs")
    texts = [e["id"] for e in entries]  # an id must not say a term: reports and logs carry ids
    for other in entries:
        if other["kind"] != "number" and any(hits(other, text) for text in texts):
            bad(f"entry {other['index']} matches an entry id; an id must not say a term")
    return entries, digest


def entry(row, n, ids):
    where = f"entry {n}"
    if not isinstance(row, dict) or not {"id", "class"} <= set(row):
        bad(f"{where} has no id or class")
    if not isinstance(row["id"], str) or not ID.match(row["id"]) or row["id"] in ids:
        bad(f"{where}: id is not a new id of a-z, 0-9, '.', '_' and '-'")
    ids.add(row["id"])
    if row["class"] not in CLASSES:
        bad(f"{where}: class is not number, geometry or name")
    kinds = [k for k in ("literal", "regex", "number") if k in row]
    allowed = {"id", "class", *kinds} | ({"unit"} if kinds == ["number"] else set())
    if len(kinds) != 1 or set(row) != allowed:
        bad(f"{where} holds not exactly one of literal, regex or number (with unit)")
    kind = kinds[0]
    out = {"id": row["id"], "class": row["class"], "kind": kind, "index": n}
    if kind == "literal":
        text = row["literal"]
        if not isinstance(text, str) or len(text) > MAX_LITERAL or len(folded(text).strip()) < 2:
            bad(f"{where}: literal is not text of 2 to {MAX_LITERAL} letters or digits")
        out["folded"] = folded(text)
    elif kind == "regex":
        pattern = row["regex"]
        if not isinstance(pattern, str) or not pattern or len(pattern) > MAX_REGEX:
            bad(f"{where}: regex is not text of 1 to {MAX_REGEX} characters")
        try:
            compiled = re.compile(pattern, re.IGNORECASE)
        except re.error:
            bad(f"{where}: regex does not compile")
        if compiled.search("") is not None or compiled.search(" ") is not None:
            bad(f"{where}: regex matches empty or blank text, so it would match everything")
        out["regex"] = compiled
    else:
        if row["class"] == "name":
            bad(f"{where}: a name entry is a literal or a regex, not a number")
        if not isinstance(row["number"], Decimal):
            bad(f"{where}: number is not a JSON number")
        unit = row["unit"]
        if unit is not None and (not isinstance(unit, str) or not gate.unit_valid(unit)):
            bad(f"{where}: unit is not null or a unit the claims gate reads")
        out |= {"number": row["number"], "unit": unit}
    return out


def hits(e, text):
    """True when entry e matches text."""
    if e["kind"] == "literal":
        return e["folded"] in folded(text)
    if e["kind"] == "regex":
        return e["regex"].search(plain(text)) is not None or e["regex"].search(folded(text).strip()) is not None
    return any(
        m["number"] is not None and m["number"] == e["number"] and (e["unit"] is None or m["unit"] == e["unit"])
        for m in gate.extract(text)
    )


# The guard ------------------------------------------------------------------------------------------------------
def scan(entries, texts):
    """[{segment, source, entry, class}] for every (segment, source, text) that an entry matches, in order."""
    out = []
    for segment, source, text in texts:
        for e in entries:
            if hits(e, text):
                out.append({"segment": segment, "source": source, "entry": e["id"], "class": e["class"]})
    return out


def written_texts(beats, claims, persona=None):
    """(segment, source, text) for every text a bundle speaks or shows before the pronunciation tables run."""
    texts = [(b["id"], "voiced", b["voiced"]) for b in beats]
    texts += [(c["id"], "claim", c["value"]["spoken"]) for c in claims.values()]
    if persona is not None:
        texts.append(("labels", "label", persona))
    return texts


def record_texts(manifest, beats, claims):
    """(position, "record", text) for every bundle text that reaches a record or a report: the manifest's slug and
    each asset's id, path and receipt, each beat's id and asset id, and each claim's id and receipt. Positions, not
    ids, name them, so a refusal never echoes a private id. The manifest is read leniently: read() checks it."""
    texts = []
    manifest = manifest if isinstance(manifest, dict) else {}
    if isinstance(manifest.get("slug"), str):
        texts.append(("slug", "record", manifest["slug"]))
    assets = manifest.get("assets") if isinstance(manifest.get("assets"), list) else []
    for n, asset in enumerate(assets, 1):
        for key in ("id", "path", "receipt"):
            if isinstance(asset, dict) and isinstance(asset.get(key), str):
                texts.append((f"asset#{n}", "record", asset[key]))
    for n, b in enumerate(beats, 1):
        texts += [(f"beat#{n}", "record", b["id"]), (f"beat#{n}", "record", b["asset_id"])]
    for n, c in enumerate(claims.values(), 1):
        texts.append((f"claim#{n}", "record", c["id"]))
        if isinstance(c["receipt"], str):
            texts.append((f"claim#{n}", "record", c["receipt"]))
    return texts


class Guard:
    """The guard of one bundle: its declaration and, when one is needed or given, its checked denylist."""

    def __init__(self, declared, denylist=None):
        self.declared = declared
        self.entries, self.digest = None, None
        self.checked = dict.fromkeys(SOURCES, 0)  # texts checked so far, by source
        if required(declared) or denylist is not None:
            self.entries, self.digest = read_denylist(denylist, declared)

    def check(self, texts):
        """The guard's report on every text checked so far, after checking texts. Raised as private_term when an
        entry matches one of them."""
        texts = list(texts)
        found = [] if self.entries is None else scan(self.entries, texts)
        for _, source, _ in texts:
            self.checked[source] += 1
        report = self.report(found)
        if found:
            first = found[0]
            raise PrivateError(
                "private_term",
                f"{len(found)} private-term matches; segment {first['segment']} {first['source']} text matches"
                f" denylist entry {first['entry']} (class {first['class']})",
                report,
            )
        return report

    def report(self, found=()):
        status = "not_declared" if self.entries is None else ("refused" if found else "passed")
        return {
            "status": status,
            "ip_private": self.declared["ip_private"],
            "never_name": self.declared["never_name"],
            "denylist_sha256": self.digest,
            "entries": None if self.entries is None else len(self.entries),
            "checked": dict(self.checked) if self.entries is not None else None,
            "matches": list(found),
        }
