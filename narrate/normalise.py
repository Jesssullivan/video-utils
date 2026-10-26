"""Spoken normalisation with the Dhall pronunciation table (narrate/dhall/Pronunciation.dhall, rendered JSON).

Each entry says a written form the engines misread and what to say instead. Longer written forms apply first.
An entry changes how a value is said, never the value: a substitution that changes the sequence of digits in
the text is refused. Ordered numeric literals also retain signs and notation, and a bounded set of
recognized units permits only equivalent spoken aliases. This is not a general semantic parser.
Every substitution is recorded with the segment it was made in.

Before either table runs, each recognised numeric range and dollar amount is said in words (narrate/amounts.py):
"$12,400–$27,000" becomes "twelve thousand four hundred to twenty-seven thousand dollars". This is not a table
substitution and the digit guard does not refuse it: each expansion is read back from its words to the written
values, unit and connector, refused on any difference, and recorded with its written and spoken forms under
"expansions". The tables never see an expansion's words: each one is held out of the text while they run, so no
entry can change its value or unit after the read-back. A span that a table entry with digits in its written form
matches is not expanded; that entry is how a script keeps a range such as a year span for the table to say.

With a pinned upstream table (the xoxd-lexical narration register), the upstream layer runs first and this
table is an overlay: a local entry whose written form matches an upstream entry's (ignoring case) replaces that
upstream entry, and the record names every upstream entry so replaced.
"""

import json
import re

from . import amounts
from .ir import canonical, sha256_text
from .lexical import UNITS


class NormaliseError(ValueError):
    pass


def digits(text):
    return re.findall(r"\d+", text)


# Numeric spelling is deliberately preserved: no rounding, unit conversion or words-to-number
# inference. The original digits gate remains useful for identifiers such as v2 and ABC1201.
# A sign is a symbol or an explicit spoken alias: -16, −16, - 16, minus 16 and negative 16 are one literal.
_SIGNS = {"-": "-", "\N{MINUS SIGN}": "-", "minus": "-", "negative": "-", "+": "+", "plus": "+", "positive": "+"}
_NUMBER = re.compile(
    r"(?:(?P<sign>[+\-\N{MINUS SIGN}]|(?i:\b(?:minus|negative|plus|positive)\b))\s*)?"
    r"(?P<body>(?:\d+(?:[.,]\d+)*|\.\d+)(?:[eE][+\-\N{MINUS SIGN}]?\d+)?)"
)

# The recognised units and their explicit spoken aliases are lexical.UNITS, the table the RewriteCheck and
# the chunker protect.
_UNIT_IDS = {alias: unit for unit, aliases in UNITS.items() for alias in aliases}
_UNIT = re.compile(r"\s*(" + "|".join(re.escape(a) for a in sorted(_UNIT_IDS, key=len, reverse=True)) + r")(?!\w)")


def quantities(text):
    """Ordered (literal, recognized unit) pairs; unknown units are outside this guard.

    A number embedded in an identifier still retains its literal, but is never assigned a
    unit. This keeps acronym spell-outs valid (e.g. ABC8S -> A B C 8 S). Whitespace before
    a numeric suffix's unit does not make that suffix a standalone quantity.
    """
    result = []
    for number in _NUMBER.finditer(text):
        unit = None
        start = number.start()
        # An identifier prefix (or a previous digit when a literal has been split) is
        # not a standalone quantity. Numeric literals themselves are always protected.
        if start == 0 or not (text[start - 1].isalnum() or text[start - 1] == "_"):
            match = _UNIT.match(text, number.end())
            if match:
                unit = _UNIT_IDS[match.group(1)]
        sign = number.group("sign")
        result.append(((_SIGNS[sign.lower()] if sign else "") + number.group("body"), unit))
    return result


def pattern(entry):
    body = re.escape(entry["written"])
    if entry["wholeWord"]:
        body = rf"(?<!\w){body}(?!\w)"
    return re.compile(body, 0 if entry["caseSensitive"] else re.IGNORECASE)


# Private-use placeholders hold each expansion out of the text while the tables run.
_HOLD = 0xF0000


def _held(text):
    return any(0xF0000 <= ord(c) <= 0xFFFFD for c in text)


def unsay_order(pairs):
    """(spoken, written) pairs of one layer, longest spoken form first, for mapping a transcript back."""
    return sorted(dict.fromkeys(pairs), key=lambda p: (-len(p[0]), p))


def recorded_aliases(record, segment):
    """The (spoken, written) pairs a manifest's pronunciation record applied in segment, in the order that maps a
    transcript back to the written text: the local layer first, then the upstream layer, then the expansions."""
    layers = [record.get("substitutions", []), (record.get("upstream") or {}).get("substitutions", [])]
    layers.append(record.get("expansions", []))
    return [
        pair
        for layer in layers
        for pair in unsay_order((s["spoken"], s["written"]) for s in layer if s["segment"] == segment)
    ]


class Normaliser:
    def __init__(self, table, upstream=None, expand=True):
        self.table = table
        self.expand = expand
        self.overridden = []
        if upstream is not None:
            local = {e["written"].casefold() for e in table["entries"]}
            kept = [e for e in upstream["entries"] if e["written"].casefold() not in local]
            self.overridden = sorted(e.get("id", e["written"]) for e in upstream["entries"] if e not in kept)
            self.upstream = Normaliser(upstream, expand=False)
            self.upstream.compiled = [(e, r) for e, r in self.upstream.compiled if e in kept]
        else:
            self.upstream = None
        entries = sorted(table["entries"], key=lambda e: (-len(e["written"]), e["written"]))
        self.compiled = [(e, pattern(e)) for e in entries]
        self.made = []
        self.expanded = []

    def aliases(self, text, segment=""):
        """The (spoken, written) pairs saying text applies, in the order that maps a transcript back to text."""
        fired = []
        self.say(text, segment, record=False, fired=fired)
        return fired

    def say(self, text, segment, record=True, fired=None):
        """The spoken form of text. With record, each expansion and substitution is recorded against segment."""
        said, found = [], []
        if self.expand:
            if _held(text):
                raise NormaliseError(f"segment {segment} has a supplementary private-use character")
            try:
                found = amounts.find(text, keep=self.table_spans(text))
            except amounts.AmountError as error:
                raise NormaliseError(
                    f"a range or amount in segment {segment} does not read back to its written value: {error}"
                ) from error
            for i, e in reversed(list(enumerate(found))):
                text = text[: e.start] + chr(_HOLD + i) + text[e.end :]
            if record:
                self.expanded += [{"segment": segment, **e.record()} for e in found]
            said = unsay_order((e.spoken, e.written) for e in found)
        upstream = []
        if self.upstream is not None:
            text = self.upstream.say(text, segment, record=record, fired=upstream)
        local = []
        for entry, regex in self.compiled:
            new, count = regex.subn(lambda _m, e=entry: e["spoken"], text)
            if not count:
                continue
            if digits(new) != digits(text):
                raise NormaliseError(
                    f"pronunciation entry {entry['written']!r} -> {entry['spoken']!r} changes the "
                    f"digits in segment {segment}; a table changes how a value is said, never the "
                    "value"
                )
            if quantities(new) != quantities(text):
                raise NormaliseError(
                    f"pronunciation entry {entry['written']!r} -> {entry['spoken']!r} changes "
                    f"a numeric literal or recognized unit in segment {segment}"
                )
            if record:
                self.made.append(
                    {"segment": segment, "written": entry["written"], "spoken": entry["spoken"], "count": count}
                )
            local.append((entry["spoken"], entry["written"]))
            text = new
        if found:
            holds = [c for c in text if _held(c)]
            if holds != [chr(_HOLD + i) for i in range(len(found))]:
                raise NormaliseError(f"a pronunciation entry moved a range or amount in segment {segment}")
            for i, e in enumerate(found):
                text = text.replace(chr(_HOLD + i), e.spoken)
        if fired is not None:
            fired += unsay_order(local) + upstream + said
        return text

    def table_spans(self, text):
        """[(start, end)] that an entry with a digit in its written form matches, in either layer: such an entry
        says that span itself, so the range and money stage leaves it as written."""
        layers = [self.compiled] + ([self.upstream.compiled] if self.upstream is not None else [])
        return [
            m.span()
            for compiled in layers
            for entry, regex in compiled
            if re.search(r"\d", entry["written"])
            for m in regex.finditer(text)
        ]

    def record(self):
        merged = {}
        for item in self.made:
            key = (item["segment"], item["written"], item["spoken"])
            merged[key] = merged.get(key, 0) + item["count"]
        substitutions = [
            {"segment": s, "written": w, "spoken": p, "count": c} for (s, w, p), c in sorted(merged.items())
        ]
        record = {
            "table": self.table["id"],
            "language": self.table["language"],
            "sha256": sha256_text(canonical(self.table)),
            "substitutions": substitutions,
        }
        if self.upstream is not None:
            record["upstream"] = self.upstream.record() | {"overridden_by_local": self.overridden}
        if self.expand:
            counted = {}
            for item in self.expanded:
                key = json.dumps(item, sort_keys=True)
                counted[key] = counted.get(key, 0) + 1
            record["expansions"] = sorted(
                ({**json.loads(k), "count": c} for k, c in counted.items()),
                key=lambda e: (e["segment"], e["written"], e["spoken"]),
            )
        return record
