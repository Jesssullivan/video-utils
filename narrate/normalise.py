"""Spoken normalisation with the Dhall pronunciation table (narrate/dhall/Pronunciation.dhall, rendered JSON).

Each entry says a written form the engines misread and what to say instead. Longer written forms apply first.
An entry changes how a value is said, never the value: a substitution that changes the sequence of digits in
the text is refused. Every substitution is recorded with the segment it was made in.
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


class Normaliser:
    def __init__(self, table, upstream=None):
        self.upstream = Normaliser(upstream) if upstream is not None else None
        self.table = table
        entries = sorted(table["entries"], key=lambda e: (-len(e["written"]), e["written"]))
        self.compiled = [(e, pattern(e)) for e in entries]
        self.made = []

    def say(self, text, segment, record=True):
        """The spoken form of text. With record, each substitution is recorded against segment."""
        if self.upstream is not None:
            text = self.upstream.say(text, segment, record=record)
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
            text = new
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
            record["upstream"] = self.upstream.record()
        return record
