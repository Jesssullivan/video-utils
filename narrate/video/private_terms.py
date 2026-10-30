"""The private-terms guard of a demo bundle (docs/spec/NARRATED_VIDEO.md, "Private terms", TIN-7735, SPR-220).

A bundle's manifest.json may declare `privacy: {ip_private, never_name, denylist_sha256}`. ip_private marks work
whose numbers and geometry stay private. never_name marks a bundle that must not name a party. When
either is true, the manifest names a denylist digest, the operator gives a denylist, or the operator pins its digest
(--denylist-sha256 or NARRATED_VIDEO_DENYLIST_SHA256), the claims gate needs the denylist: a JSON file kept outside
the bundle and outside any git work tree. A pin marks the lane private, so an undeclared bundle refuses
privacy_undeclared and the file must hash to the pin, whatever the manifest says. The guard refuses
denylist_missing, denylist_misplaced, denylist_digest_mismatch and denylist_invalid before it reads any text.

It then checks every text the job would speak or show or record: each beat's voiced text (the captions' text), its
spoken form after the pronunciation tables (intake only), each claim's spoken text, the persona label, and every
bundle text that reaches a record or report (the slug, the job id, beat, claim and asset ids, asset paths and claim
and asset receipts). A match refuses private_term. Record texts are checked first and reported by position (beat#2,
not the beat's id), so a report never carries a private id.

Matching fails closed, so it over-matches on purpose. Every text is folded: NFKD, combining marks stripped, case
folded, the confusable letters in CONFUSABLES mapped to Latin and every decimal digit mapped to ASCII. A literal
matches when its squeezed form (letters and digits only) occurs anywhere in the squeezed text, so "FixtureCorp",
"fixture-corp.com", "Fixture\\u00adCorp" and "Fixture Corps" all match "Fixture Corp". A word that mixes Latin and
Cyrillic letters refuses as class script. A regex entry uses the shared subset (REGEX_TOKEN, which cade
src/bs21-guard.ts reads alike); it runs on the NFKC text, on the spaced fold and, with its separators removed, on
the squeezed fold. A number entry matches its value in any unit: every mention the claims gate's extractor reads
as it, every digit run read as a whole, a decimal or its groups ("12,5", ".5", "12-5"), a vulgar fraction ("12½")
and its English spelling ("twelve point five", "twelve and a half"). Inflections, abbreviations and leetspeak
("Z0rblax") need entries of their own.

A report names the beat, the text's source and the entry id and class. Its detail names the entry by position only.
No report holds the matched text, a literal, a pattern or a number from the denylist, so a refusal can go to a log.
An entry id that any entry matches is refused as denylist_invalid, because reports carry ids. redact() withholds a
refusal detail from any earlier check that says a term.

Standard library only.
"""

import hashlib
import json
import os
import re
import unicodedata
from decimal import Decimal, InvalidOperation
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
# A random salt in the file, so that its digest cannot confirm a guessed short list (cade src/claims-gate.ts keeps
# no digest of its name list for that reason). Records carry the digest; the salt makes it unguessable. A salt
# of fewer than SALT_DISTINCT distinct hex digits ("00...", "0f0f...") is not random.
SALT = re.compile(r"^[0-9a-f]{32,128}$")
SALT_DISTINCT = 8
SOURCES = ("record", "voiced", "spoken", "claim", "label")
PIN_ENV = "NARRATED_VIDEO_DENYLIST_SHA256"

# Letters that look like Latin ones: Cyrillic, Greek and Latin extensions. UPPER_CONFUSABLES maps capitals before
# case folding (Greek Eta looks like H, its small form like n) and CONFUSABLES maps small letters after it. cade
# src/bs21-guard.ts holds the same pairs. The lists are a floor, not Unicode's whole confusables table.
UPPER_CONFUSABLES = str.maketrans(
    dict(
        zip(
            "\u0391\u0392\u0395\u0396\u0397\u0399\u039a\u039c\u039d\u039f\u03a1\u03a4\u03a5\u03a7"
            "\u0410\u0412\u0415\u041a\u041c\u041d\u041e\u0420\u0421\u0422\u0423\u0425\u0405\u0406\u0408",
            "ABEZHIKMNOPTYXABEKMHOPCTYXSIJ",
            strict=True,
        )
    )
)
CONFUSABLES = str.maketrans(
    dict(
        zip(
            "\u0430\u0432\u0435\u043a\u043c\u043d\u043e\u0440\u0441\u0442\u0443\u0445\u04bb\u0456\u0458\u0455\u0501"
            "\u051b\u051d\u04cf\u03b1\u03b2\u03b3\u03b5\u03b7\u03b9\u03ba\u03bd\u03bf\u03c1\u03c4\u03c5\u03c7\u03c9"
            "\u03f2\u03f3\u03c2\u0131\u0237\u0251\u0261\u0269",
            "abekmhopctyxhijsdqwlabyeniknoptuxwcj\u03c3ijagi",
            strict=True,
        )
    )
)
FRACTIONS = {
    "\u00bd": ".5", "\u00bc": ".25", "\u00be": ".75", "\u2155": ".2", "\u2156": ".4", "\u2157": ".6",
    "\u2158": ".8", "\u215b": ".125", "\u215c": ".375", "\u215d": ".625", "\u215e": ".875", "\u2152": ".1",
}  # fmt: skip
FRACTION = re.compile(r"(\d?)\s*([" + "".join(FRACTIONS) + "])")
DIGIT_RUN = re.compile(r"[0-9]+(?:[.,][0-9]+)*|[.,][0-9]+")
# The shared regex subset: ASCII letters, digits and spaces, the escapes \s \d \b \. \-, ".", groups "(" "(?:" ")",
# "|", character classes of those, and the quantifiers ? * + {n} {n,} {n,m}. Both repositories compile it
# case-insensitive with "." matching every character, and \s \d \b read ASCII only.
CLASS_ITEM = r"(?:[a-z0-9 ](?:-[a-z0-9])?|\\[sd.\-]|-(?=\]))"
REGEX_TOKEN = re.compile(
    r"\\[sdb.\-]|\[\^?" + CLASS_ITEM + r"+\]|\(\?:|[()|.]|[a-z0-9 ]|[?*+]|\{[0-9]{1,3}(?:,[0-9]{0,3})?\}", re.I
)
SEPARATORS = {" ", "-", "\\s", "\\.", "\\-"}
SMALL_WORDS = (
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen"
    " seventeen eighteen nineteen"
).split()
TENS_WORDS = "twenty thirty forty fifty sixty seventy eighty ninety".split()
SCALE_WORDS = ((10**12, "trillion"), (10**9, "billion"), (10**6, "million"), (10**3, "thousand"))
FRACTION_WORDS = {"5": ("and a half", "and one half"), "25": ("and a quarter", "and one quarter"),
                  "75": ("and three quarters",)}  # fmt: skip


class PrivateError(JobError):
    """A refused denylist or a private term. report is the guard's report when a term matched."""

    def __init__(self, code, detail, report=None):
        super().__init__(code, detail)
        self.report = report


# Folding ------------------------------------------------------------------------------------------------------
def is_word_char(ch):
    return unicodedata.category(ch)[0] in "LN"


def unmarked(text):
    return "".join(ch for ch in unicodedata.normalize("NFKD", text) if unicodedata.category(ch)[0] != "M")


def ascii_digits(text):
    return "".join(str(unicodedata.decimal(ch)) if unicodedata.category(ch) == "Nd" else ch for ch in text)


def skeleton(text):
    """NFKD with no marks, capital confusables mapped, case folded, NFKD with no marks again (folding can yield a
    character NFKD splits), small confusables mapped to Latin and every decimal digit made ASCII."""
    return ascii_digits(unmarked(unmarked(text).translate(UPPER_CONFUSABLES).casefold()).translate(CONFUSABLES))


def spaced(text):
    """The skeleton with every run of characters that are not letters or digits made one space, padded."""
    return " " + " ".join("".join(ch if is_word_char(ch) else " " for ch in skeleton(text)).split()) + " "


def squeezed(text):
    """The skeleton with only its letters and digits."""
    return "".join(ch for ch in skeleton(text) if is_word_char(ch))


def plain(text):
    """text for a regex match: NFKC with no format characters."""
    return "".join(ch for ch in unicodedata.normalize("NFKC", text) if unicodedata.category(ch) != "Cf")


def folded(text):
    """The spaced fold (kept for callers of the first guard)."""
    return spaced(text)


def mixed_script(text):
    """True when one word of text holds both Latin and Cyrillic letters."""
    for word in re.split(r"[^\w]|_|\d", unmarked(text)):
        scripts = {unicodedata.name(ch, "").split(" ")[0] for ch in word if unicodedata.category(ch)[0] == "L"}
        if {"LATIN", "CYRILLIC"} <= scripts:
            return True
    return False


def numeric_text(text):
    """text for number matching: vulgar fractions as decimals, NFKC, ASCII digits and no format characters."""
    text = FRACTION.sub(lambda m: (m[1] or "0") + FRACTIONS[m[2]], text)
    return ascii_digits(plain(text))


def run_values(run):
    """Every value a digit run may be read as. A run with one "." is that decimal. A run with a "," or two or more
    separators is ambiguous, so it is read whole, group by group, and as a decimal at its last separator."""
    seps = [ch for ch in run if ch in ".,"]
    groups = [g for g in re.split(r"[.,]", run) if g]
    if not seps:
        values = {run}
    elif run[0] in ".,":
        values = {"0." + "".join(groups)} | set(groups)
    elif seps == ["."]:
        values = {run}
    else:
        last = max(run.rfind("."), run.rfind(","))
        values = {"".join(groups), re.sub(r"[.,]", "", run[:last]) + "." + run[last + 1 :]} | set(groups)
    out = set()
    for v in values:
        try:
            out.add(abs(Decimal(v)))
        except InvalidOperation:
            pass
    return out


def int_words(n, with_and):
    if n < 20:
        return SMALL_WORDS[n]
    if n < 100:
        return TENS_WORDS[n // 10 - 2] + ("" if n % 10 == 0 else " " + SMALL_WORDS[n % 10])
    if n < 1000:
        rest = n % 100
        head = SMALL_WORDS[n // 100] + " hundred"
        return head if rest == 0 else head + (" and " if with_and else " ") + int_words(rest, with_and)
    for scale, word in SCALE_WORDS:
        if n >= scale:
            rest = n % scale
            head = int_words(n // scale, with_and) + " " + word
            return head if rest == 0 else head + " " + int_words(rest, with_and)
    raise ValueError(n)


def spelled_forms(value):
    """The English spellings of a number (its absolute value) that a text may say, spaced; [] when too long."""
    value = abs(value)
    text = format(value.normalize(), "f")
    whole, _, frac = text.partition(".")
    if len(whole) > 15 or len(frac) > 12:
        return []
    heads = {int_words(int(whole), True), int_words(int(whole), False)}
    if not frac:
        return sorted(heads)
    forms = set()
    for head in heads:
        forms.add(head + " point " + " ".join(SMALL_WORDS[int(d)] for d in frac))
        for tail in FRACTION_WORDS.get(frac, ()):
            forms.add(head + " " + tail)
    if whole == "0":
        forms.add("point " + " ".join(SMALL_WORDS[int(d)] for d in frac))
        if frac == "5":
            forms |= {"a half", "one half"}
    return sorted(forms)


# The shared regex subset ------------------------------------------------------------------------------------------
def regex_tokens(pattern):
    """The pattern's tokens in the shared subset, or None when it leaves the subset."""
    tokens, at, depth = [], 0, 0
    while at < len(pattern):
        m = REGEX_TOKEN.match(pattern, at)
        if m is None:
            return None
        tok, at = m[0], m.end()
        quantifier = tok in "?*+" or tok.startswith("{")
        if quantifier and (not tokens or tokens[-1] in ("(", "(?:", "|", "\\b") or is_quantifier(tokens[-1])):
            return None
        depth += tok in ("(", "(?:")
        depth -= tok == ")"
        if depth < 0:
            return None
        tokens.append(tok)
    return tokens if depth == 0 else None


def is_quantifier(tok):
    return tok in ("?", "*", "+") or tok.startswith("{")


def squeezed_regex(tokens):
    """The pattern for the squeezed fold: separators and \\b dropped, a separator class member removed, and "."
    made optional, so `chamfer\\s+angle` reads "chamferangle"."""
    out, i = [], 0
    while i < len(tokens):
        tok = tokens[i]
        quant = tokens[i + 1] if i + 1 < len(tokens) and is_quantifier(tokens[i + 1]) else None
        i += 2 if quant else 1
        if tok in SEPARATORS or tok == "\\b":
            continue
        if tok.startswith("[") and not tok.startswith("[^"):
            items = [x for x in re.findall(CLASS_ITEM, tok[1:-1], re.I) if x not in SEPARATORS]
            if not items:
                continue
            tok = "[" + "".join(items) + "]"
        if tok == ".":
            quant = loosened(quant)
        out.append(tok + (quant or ""))
    return "".join(out)


def loosened(quant):
    """A quantifier for "." with its lower bound made 0, because the squeezed fold drops what "." may have read."""
    if quant in (None, "?"):
        return "?"
    if quant in ("+", "*"):
        return "*"
    low, comma, high = quant[1:-1].partition(",")
    if comma and not high:
        return "*"
    return "{0," + (high or low) + "}"


def compile_regex(pattern):
    return re.compile(pattern, re.IGNORECASE | re.ASCII | re.DOTALL)


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
        raise PrivateError("bundle_invalid", f"{where}: missing {len(missing)} and holds {len(unknown)} unknown fields")
    for key in sorted(PRIVACY_FIELDS):
        if not isinstance(value[key], bool):
            raise PrivateError("bundle_invalid", f"{where}: {key} is not true or false")
    digest = value.get("denylist_sha256")
    if digest is not None and (not isinstance(digest, str) or not SHA256.match(digest)):
        raise PrivateError("bundle_invalid", f"{where}: denylist_sha256 is not 64 lowercase hex digits")
    return {"ip_private": value["ip_private"], "never_name": value["never_name"], "denylist_sha256": digest}


def required(declared, pin=None):
    return declared["ip_private"] or declared["never_name"] or declared["denylist_sha256"] is not None or bool(pin)


def operator_pin(pin=None):
    """The operator's pinned denylist digest: pin, else NARRATED_VIDEO_DENYLIST_SHA256, else None."""
    pin = pin or os.environ.get(PIN_ENV) or None
    if pin is not None and not SHA256.match(pin):
        raise PrivateError("denylist_pin_invalid", f"the denylist pin ({PIN_ENV}) is not 64 lowercase hex digits")
    return pin


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


def in_work_tree(path):
    """True when path lies inside a git work tree (a parent holds .git)."""
    return any((p / ".git").exists() for p in Path(path).resolve().parents)


def check_place(path, bundle=None):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise PrivateError("denylist_missing", "the --denylist file is missing or not a regular file")
    resolved = path.resolve()
    if bundle is not None and Path(bundle).resolve() in resolved.parents:
        raise PrivateError("denylist_misplaced", "the --denylist file lies inside the bundle")
    if in_work_tree(resolved):
        raise PrivateError("denylist_misplaced", "the --denylist file lies inside a git work tree")
    return path


def parse(data):
    """[entry] from denylist bytes, checked but bound to no declaration."""
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
    if not isinstance(value, dict) or set(value) != {"kind", "schema_version", "salt", "entries"}:
        bad("is not {kind, schema_version, salt, entries}")
    if value["kind"] != KIND or value["schema_version"] != SCHEMA_VERSION:
        bad(f"is not kind {KIND} schema_version {SCHEMA_VERSION}")
    salt = value["salt"]
    if not isinstance(salt, str) or not SALT.match(salt):
        bad("salt is not 32 to 128 lowercase hex digits")
    if len(set(salt)) < SALT_DISTINCT:
        bad(f"salt holds fewer than {SALT_DISTINCT} distinct hex digits, so it is not random")
    rows = value["entries"]
    if not isinstance(rows, list) or not rows or len(rows) > MAX_ENTRIES:
        bad(f"entries is not a list of 1 to {MAX_ENTRIES} entries")
    entries, ids = [], set()
    for n, row in enumerate(rows):
        entries.append(entry(row, n, ids))
    for other in entries:  # an id must not say a term: reports and logs carry ids
        if any(hits(other, e["id"]) for e in entries):
            bad(f"entry {other['index']} matches an entry id; an id must not say a term")
    return entries


def read_denylist(path, declared, pin=None, bundle=None):
    """([entry], sha256) of the denylist file at path, checked against the declaration and the operator's pin.
    Never echoes its content."""
    if path is None:
        raise PrivateError("denylist_missing", "the bundle declares private terms and no --denylist was given")
    path = check_place(path, bundle)
    if path.stat().st_size > MAX_BYTES:
        bad(f"is larger than {MAX_BYTES} bytes")
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if pin is not None:
        if not (declared["ip_private"] or declared["never_name"]):
            raise PrivateError("privacy_undeclared", "the lane is private (a denylist pin is set) and manifest.json"
                               " declares neither ip_private nor never_name")  # fmt: skip
        if declared["denylist_sha256"] is not None and declared["denylist_sha256"] != pin:
            raise PrivateError("denylist_digest_mismatch", "manifest.json binds another denylist than the pin")
        if digest != pin:
            raise PrivateError("denylist_digest_mismatch", "the --denylist file does not hash to the pin")
    elif declared["denylist_sha256"] is None and (declared["ip_private"] or declared["never_name"]):
        raise PrivateError("denylist_missing", "manifest.json declares private terms but names no denylist_sha256")
    elif declared["denylist_sha256"] is not None and digest != declared["denylist_sha256"]:
        raise PrivateError("denylist_digest_mismatch", "the --denylist file does not hash to the manifest's digest")
    entries = parse(data)
    for key, classes in NEEDS.items():
        if declared[key] and not any(e["class"] in classes for e in entries):
            bad(f"holds no {' or '.join(sorted(classes))} entry, which {key} needs")
    return entries, digest


def preload(path):
    """The denylist's entries for redact(), read before the manifest is: None when no file is given, False when
    the file is given but unreadable (redact then withholds every detail)."""
    if path is None:
        return None
    try:
        path = Path(path)
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
            return False
        return parse(path.read_bytes())
    except (PrivateError, OSError):
        return False


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
        if not isinstance(text, str) or len(text) > MAX_LITERAL or len(squeezed(text)) < 2:
            bad(f"{where}: literal is not text of 2 to {MAX_LITERAL} letters or digits")
        out["squeezed"] = squeezed(text)
    elif kind == "regex":
        pattern = row["regex"]
        if not isinstance(pattern, str) or not pattern or len(pattern) > MAX_REGEX:
            bad(f"{where}: regex is not text of 1 to {MAX_REGEX} characters")
        tokens = regex_tokens(pattern)
        if tokens is None:
            bad(f"{where}: regex leaves the shared subset (docs/spec/NARRATED_VIDEO.md, 'Private terms')")
        try:
            compiled, tight = compile_regex(pattern), compile_regex(squeezed_regex(tokens))
        except re.error:
            bad(f"{where}: regex does not compile")
        if compiled.search("") is not None or compiled.search(" ") is not None or tight.search("") is not None:
            bad(f"{where}: regex matches empty or blank text, so it would match everything")
        out |= {"regex": compiled, "tight": tight}
    else:
        if row["class"] == "name":
            bad(f"{where}: a name entry is a literal or a regex, not a number")
        if not isinstance(row["number"], Decimal):
            bad(f"{where}: number is not a JSON number")
        unit = row["unit"]
        if unit is not None and (not isinstance(unit, str) or not gate.unit_valid(unit)):
            bad(f"{where}: unit is not null or a unit the claims gate reads")
        value = abs(row["number"])
        forms = spelled_forms(value)
        out |= {
            "number": value,
            "unit": unit,
            "spelled": [" " + f + " " for f in forms],
            "spelled_tight": [f.replace(" ", "") for f in forms if " " in f],
        }
    return out


def number_hit(e, text):
    """True when text says e's number in any unit, as the claims gate reads it, as a digit run or spelled out."""
    numeric = numeric_text(text)
    want = e["number"]
    if any(m["number"] is not None and abs(m["number"]) == want for m in gate.extract(numeric)):
        return True
    if any(want in run_values(m[0]) for m in DIGIT_RUN.finditer(numeric)):
        return True
    words, tight = spaced(text), squeezed(text)
    return any(f in words for f in e["spelled"]) or any(f in tight for f in e["spelled_tight"])


def hits(e, text):
    """True when entry e matches text."""
    if e["kind"] == "literal":
        return e["squeezed"] in squeezed(text)
    if e["kind"] == "regex":
        return (
            e["regex"].search(plain(text)) is not None
            or e["regex"].search(spaced(text).strip()) is not None
            or e["tight"].search(squeezed(text)) is not None
        )
    return number_hit(e, text)


def redact(entries, code, detail):
    """detail, or a withheld detail when it says a term. entries False (an unreadable denylist) withholds all."""
    if entries is None:
        return detail
    if entries is False or mixed_script(detail) or any(hits(e, detail) for e in entries):
        return f"{code}: the detail is withheld because it may say a private term"
    return detail


# The guard ------------------------------------------------------------------------------------------------------
def scan(entries, texts):
    """[{segment, source, entry, class}] for every (segment, source, text) that an entry matches, in order. A word
    that mixes Latin and Cyrillic letters is a match of class script (entry null)."""
    out = []
    for segment, source, text in texts:
        if mixed_script(text):
            out.append({"segment": segment, "source": source, "entry": None, "class": "script"})
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

    def __init__(self, declared, denylist=None, pin=None, bundle=None):
        self.declared = declared
        self.pin = operator_pin(pin)
        self.entries, self.digest = None, None
        self.checked = dict.fromkeys(SOURCES, 0)  # texts checked so far, by source
        if required(declared, self.pin) or denylist is not None:
            self.entries, self.digest = read_denylist(denylist, declared, self.pin, bundle)

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
            index = next((e["index"] for e in self.entries if e["id"] == first["entry"]), None)
            said = "mixes Latin and Cyrillic letters" if index is None else f"matches denylist entry #{index}"
            raise PrivateError(
                "private_term",
                f"{len(found)} private-term matches; segment {first['segment']} {first['source']} text {said}"
                f" (class {first['class']})",
                report,
            )
        return report

    def redact(self, code, detail):
        return redact(self.entries, code, detail)

    def report(self, found=()):
        status = "not_declared" if self.entries is None else ("refused" if found else "passed")
        return {
            "status": status,
            "ip_private": self.declared["ip_private"],
            "never_name": self.declared["never_name"],
            "denylist_sha256": self.digest,
            "pinned": self.pin is not None,
            "entries": None if self.entries is None else len(self.entries),
            "checked": dict(self.checked) if self.entries is not None else None,
            "matches": list(found),
        }


# The records marker (intake writes it; job.load_records checks it) -------------------------------------------------
MARKER = "private-terms.json"
MARKER_KIND = "nv_private_terms"


def digest_of(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def marker(report, narrate_jobs, records):
    """The records marker of a guarded intake: the guard's status and digest and, per narrate job, the digests of
    the job record and of the pronunciation table it names. A later edit to either refuses at load."""
    jobs = {}
    for job in narrate_jobs:
        table = (records.get("pronunciation") or {}).get(job.get("pronunciation"))
        jobs[job["id"]] = {
            "job_sha256": digest_of(job),
            "pronunciation": job.get("pronunciation"),
            "pronunciation_sha256": None if table is None else digest_of(table),
        }
    return {
        "kind": MARKER_KIND,
        "schema_version": 1,
        "status": report["status"],
        "denylist_sha256": report["denylist_sha256"],
        "jobs": jobs,
    }


def check_marker(directory, records):
    """Refuse private_terms_stale when the records' marker no longer matches a narrate job or its pronunciation
    table. A records directory with no marker passes: only a guarded intake writes one."""
    path = Path(directory) / MARKER
    if not path.exists() and not path.is_symlink():
        return None
    if path.is_symlink() or not path.is_file():
        raise JobError("private_terms_stale", f"{MARKER} is not a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise JobError("private_terms_stale", f"{MARKER} is not JSON") from None
    if not isinstance(value, dict) or value.get("kind") != MARKER_KIND or not isinstance(value.get("jobs"), dict):
        raise JobError("private_terms_stale", f"{MARKER} is not a {MARKER_KIND} record")
    for n, (job_id, want) in enumerate(sorted(value["jobs"].items()), 1):
        job = records["jobs"].get(job_id)
        if job is None or not isinstance(want, dict) or digest_of(job) != want.get("job_sha256"):
            raise JobError("private_terms_stale", f"narrate job #{n} changed after the private-terms guard ran")
        table = (records.get("pronunciation") or {}).get(job.get("pronunciation"))
        if (None if table is None else digest_of(table)) != want.get("pronunciation_sha256"):
            raise JobError(
                "private_terms_stale",
                f"the pronunciation table of narrate job #{n} changed after the private-terms guard ran; run the"
                " intake again",
            )
    return value
