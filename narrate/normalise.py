"""Spoken normalisation with the Dhall pronunciation table (narrate/dhall/Pronunciation.dhall, rendered JSON).

Each entry says a written form the engines misread and what to say instead. Longer written forms apply first.
An entry changes how a value is said, never the value: a substitution that changes the sequence of digits in
the text is refused. Ordered numeric literals also retain signs and notation, and a bounded set of
recognized units permits only equivalent spoken aliases. This is not a general semantic parser.
Every substitution is recorded with the segment it was made in.
"""

import re

from .ir import canonical, sha256_text


class NormaliseError(ValueError):
    pass


def digits(text):
    return re.findall(r"\d+", text)


# Numeric spelling is deliberately preserved: no rounding, unit conversion or words-to-number
# inference. The original digits gate remains useful for identifiers such as v2 and ABC1201.
_NUMBER = re.compile(r"(?:[+\-−]\s*)?(?:\d+(?:[.,]\d+)*|\.\d+)(?:[eE][+\-−]?\d+)?")

# Explicit aliases, not inferred dimensions: 1 ms is not interchangeable with 1 s, nor GiB
# with GB. Symbols are case sensitive; written-out aliases use their conventional lower case.
_UNIT_ALIASES = {
    "%": ("%", "percent", "per cent"),
    "ms": ("ms", "millisecond", "milliseconds"),
    "s": ("s", "second", "seconds"),
    "min": ("min", "minute", "minutes"),
    "h": ("h", "hour", "hours"),
    "Hz": ("Hz", "hertz"),
    "kHz": ("kHz", "kilohertz"),
    "MHz": ("MHz", "megahertz"),
    "GHz": ("GHz", "gigahertz"),
    "dB": ("dB", "decibel", "decibels"),
    "dBFS": ("dBFS", "decibels relative to full scale"),
    "dBTP": ("dBTP", "decibels true peak"),
    "LUFS": ("LUFS", "loudness units relative to full scale"),
    "fps": ("fps", "frames per second"),
    "bpm": ("bpm", "beats per minute"),
    "B": ("B", "byte", "bytes"),
    "kB": ("kB", "kilobyte", "kilobytes"),
    "MB": ("MB", "megabyte", "megabytes"),
    "GB": ("GB", "gigabyte", "gigabytes"),
    "TB": ("TB", "terabyte", "terabytes"),
    "KiB": ("KiB", "kibibyte", "kibibytes"),
    "MiB": ("MiB", "mebibyte", "mebibytes"),
    "GiB": ("GiB", "gibibyte", "gibibytes"),
    "TiB": ("TiB", "tebibyte", "tebibytes"),
}
_UNIT_IDS = {alias: unit for unit, aliases in _UNIT_ALIASES.items() for alias in aliases}
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
        result.append((number.group(), unit))
    return result


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
            if quantities(new) != quantities(text):
                raise NormaliseError(
                    f"pronunciation entry {entry['written']!r} -> {entry['spoken']!r} changes "
                    f"a numeric literal or recognized unit in segment {segment}"
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
