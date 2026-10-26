"""Spoken normalisation with the Dhall pronunciation table (narrate/dhall/Pronunciation.dhall, rendered JSON).

Each entry says a written form the engines misread and what to say instead. Longer written forms apply first.
An entry changes how a value is said, never the value: a substitution that changes the sequence of digits in
the text is refused. Every substitution is recorded with the segment it was made in.

With a pinned upstream table (the xoxd-lexical narration register), the upstream layer runs first and this
table is an overlay: a local entry whose written form matches an upstream entry's (ignoring case) replaces that
upstream entry, and the record names every upstream entry so replaced.
"""

import re

from .ir import canonical, sha256_text


class NormaliseError(ValueError):
    pass


def digits(text):
    return re.findall(r"\d+", text)


def pattern(entry):
    body = re.escape(entry["written"])
    if entry["wholeWord"]:
        body = rf"(?<!\w){body}(?!\w)"
    return re.compile(body, 0 if entry["caseSensitive"] else re.IGNORECASE)


def unsay_order(pairs):
    """(spoken, written) pairs of one layer, longest spoken form first, for mapping a transcript back."""
    return sorted(dict.fromkeys(pairs), key=lambda p: (-len(p[0]), p))


def recorded_aliases(record, segment):
    """The (spoken, written) pairs a manifest's pronunciation record applied in segment, in the order that maps a
    transcript back to the written text: the local layer first, then the upstream layer."""
    layers = [record, record.get("upstream") or {}]
    return [
        pair
        for layer in layers
        for pair in unsay_order(
            (s["spoken"], s["written"]) for s in layer.get("substitutions", []) if s["segment"] == segment
        )
    ]


class Normaliser:
    def __init__(self, table, upstream=None):
        self.table = table
        self.overridden = []
        if upstream is not None:
            local = {e["written"].casefold() for e in table["entries"]}
            kept = [e for e in upstream["entries"] if e["written"].casefold() not in local]
            self.overridden = sorted(e.get("id", e["written"]) for e in upstream["entries"] if e not in kept)
            self.upstream = Normaliser(upstream)
            self.upstream.compiled = [(e, r) for e, r in self.upstream.compiled if e in kept]
        else:
            self.upstream = None
        entries = sorted(table["entries"], key=lambda e: (-len(e["written"]), e["written"]))
        self.compiled = [(e, pattern(e)) for e in entries]
        self.made = []

    def aliases(self, text, segment=""):
        """The (spoken, written) pairs saying text applies, in the order that maps a transcript back to text."""
        fired = []
        self.say(text, segment, record=False, fired=fired)
        return fired

    def say(self, text, segment, record=True, fired=None):
        """The spoken form of text. With record, each substitution is recorded against segment."""
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
            if record:
                self.made.append(
                    {"segment": segment, "written": entry["written"], "spoken": entry["spoken"], "count": count}
                )
            local.append((entry["spoken"], entry["written"]))
            text = new
        if fired is not None:
            fired += unsay_order(local) + upstream
        return text

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
        return record
