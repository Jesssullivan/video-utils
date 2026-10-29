"""The spoken-number claims gate of a demo bundle (docs/spec/NARRATED_VIDEO.md, "Demo bundle intake").

Every number a beat's voiced text speaks must match a claims.json entry that the beat cites and that carries a
receipt. extract() finds the numbers: digits ("17.877", "1,024", "42%", "3rd", "12ms") and spelled-out English
("seventeen point eight seven seven", "one hundred and five", "forty two percent", "twenty first"), each with the
unit that follows it ("milliseconds", "per cent", "frames per second"). It fails closed: a reading it cannot pin to
one value is a mention with `ambiguous` set, and an ambiguous mention never matches a claim.

Ambiguous readings (refused as number_ambiguous):
- adjacent number words that are not one well-formed number: "nineteen eighty four", "one two three";
- a fraction or a vague quantity: "one third", "two thirds", "a half", "quarter", "dozen", "couple", "twice";
- "point" with digit words and no whole part before it ("point five");
- "second" where it could be the ordinal or the unit ("twenty second", "one hundred second");
- a digit token that is not one plain number: "1.2.3", "10:30", "1/2", "2026-10-29", "MP4", "1,23", "4K".

Not extracted: once, single, both, none and "a" or "an" before anything but hundred, thousand, million, billion or
trillion. "one" is always the number 1, and "first" or "second" alone are the ordinals 1 and 2: a script that uses
them as words cites a claim or rewords. These rules are strict on purpose (TIN-7735): a demo must not speak a
number that no receipt backs.

Standard library only. Numbers are decimal.Decimal, so 17.877 compares exactly.
"""

import re
from decimal import Decimal, InvalidOperation

SMALL = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
}  # fmt: skip
TEENS = {
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19,
}  # fmt: skip
TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
SCALES = {"thousand": 10**3, "million": 10**6, "billion": 10**9, "trillion": 10**12}
ORD_SMALL = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9,
}  # fmt: skip
ORD_TEENS = {
    "tenth": 10, "eleventh": 11, "twelfth": 12, "thirteenth": 13, "fourteenth": 14, "fifteenth": 15,
    "sixteenth": 16, "seventeenth": 17, "eighteenth": 18, "nineteenth": 19,
}  # fmt: skip
ORD_TENS = {
    "twentieth": 20, "thirtieth": 30, "fortieth": 40, "fiftieth": 50, "sixtieth": 60, "seventieth": 70,
    "eightieth": 80, "ninetieth": 90,
}  # fmt: skip
ORD_BIG = {"hundredth": 100, "thousandth": 10**3, "millionth": 10**6, "billionth": 10**9, "trillionth": 10**12}
VAGUE = {
    "half", "halves", "quarter", "quarters", "dozen", "dozens", "couple", "twice", "thrice", "double", "triple",
    "quadruple",
}  # fmt: skip
# A plural ordinal is a fraction ("two thirds"); "seconds" is the unit, never a fraction.
PLURAL_ORDINALS = {w + "s" for w in (*ORD_SMALL, *ORD_TEENS, *ORD_TENS, *ORD_BIG) if w != "second"}

# Canonical units and how they are said. WORD_UNITS follow any number; SYMBOL_UNITS only follow digits, attached
# ("12ms") or as the next word ("12 ms"). Keys are lower case; a multi-word unit is a tuple of words.
UNITS = {
    "percent": ("percent", ("per", "cent")),
    "pp": (("percentage", "point"), ("percentage", "points")),
    "s": ("second", "seconds"),
    "ms": ("millisecond", "milliseconds"),
    "us": ("microsecond", "microseconds"),
    "ns": ("nanosecond", "nanoseconds"),
    "min": ("minute", "minutes"),
    "h": ("hour", "hours"),
    "day": ("day", "days"),
    "week": ("week", "weeks"),
    "month": ("month", "months"),
    "year": ("year", "years"),
    "Hz": ("hertz",),
    "kHz": ("kilohertz",),
    "MHz": ("megahertz",),
    "GHz": ("gigahertz",),
    "dB": ("decibel", "decibels"),
    "dBFS": (("decibels", "full", "scale"), ("decibel", "full", "scale")),
    "LUFS": ("lufs",),
    "LU": ("lu",),
    "dBTP": ("dbtp",),
    "V": ("volt", "volts"),
    "mV": ("millivolt", "millivolts"),
    "A": ("amp", "amps", "ampere", "amperes"),
    "mA": ("milliamp", "milliamps", "milliampere", "milliamperes"),
    "W": ("watt", "watts"),
    "kW": ("kilowatt", "kilowatts"),
    "mW": ("milliwatt", "milliwatts"),
    "ohm": ("ohm", "ohms"),
    "m": ("metre", "metres", "meter", "meters"),
    "cm": ("centimetre", "centimetres", "centimeter", "centimeters"),
    "mm": ("millimetre", "millimetres", "millimeter", "millimeters"),
    "km": ("kilometre", "kilometres", "kilometer", "kilometers"),
    "in": ("inch", "inches"),
    "ft": ("foot", "feet"),
    "g": ("gram", "grams"),
    "kg": ("kilogram", "kilograms"),
    "mg": ("milligram", "milligrams"),
    "degC": (("degree", "celsius"), ("degrees", "celsius")),
    "degF": (("degree", "fahrenheit"), ("degrees", "fahrenheit")),
    "deg": ("degree", "degrees"),
    "B": ("byte", "bytes"),
    "KB": ("kilobyte", "kilobytes"),
    "MB": ("megabyte", "megabytes"),
    "GB": ("gigabyte", "gigabytes"),
    "TB": ("terabyte", "terabytes"),
    "bit": ("bit", "bits"),
    "fps": (("frames", "per", "second"), ("frame", "per", "second")),
    "px": ("pixel", "pixels"),
    "x": ("times",),
    "USD": ("dollar", "dollars"),
}
SYMBOL_UNITS = {
    "%": "percent", "s": "s", "sec": "s", "ms": "ms", "us": "us", "µs": "us", "ns": "ns", "min": "min", "h": "h",
    "hz": "Hz", "khz": "kHz", "mhz": "MHz", "ghz": "GHz", "db": "dB", "dbfs": "dBFS", "lufs": "LUFS", "lu": "LU",
    "dbtp": "dBTP", "v": "V", "mv": "mV", "ma": "mA", "w": "W", "kw": "kW", "mw": "mW", "ω": "ohm", "m": "m",
    "cm": "cm", "mm": "mm", "km": "km", "g": "g", "kg": "kg", "mg": "mg", "°c": "degC", "°f": "degF", "°": "deg",
    "kb": "KB", "gb": "GB", "tb": "TB", "fps": "fps", "px": "px", "x": "x",
}  # fmt: skip
ORDINAL_SUFFIX = {"st", "nd", "rd", "th"}
ORDINAL = "ordinal"  # the unit an ordinal mention carries ("third", "21st")
WORD_UNITS = {}
for _unit, _forms in UNITS.items():
    for _form in _forms:
        WORD_UNITS[_form if isinstance(_form, tuple) else (_form,)] = _unit
LONGEST_UNIT = max(len(k) for k in WORD_UNITS)


def unit_valid(unit):
    """A claim's unit: "" (a bare count), "ordinal", a canonical unit, or two joined by "/" ("m/s")."""
    if unit in ("", ORDINAL) or unit in UNITS:
        return True
    parts = unit.split("/")
    return len(parts) == 2 and all(p in UNITS for p in parts)


# Tokens ---------------------------------------------------------------------------------------------------------
CHUNK = re.compile(r"\S+")
WORD = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
LEAD = "([{\"'“‘"
TRAIL = ".,;:!?)]}\"'”’"
DIGITS = re.compile(r"(?P<sign>[-−+]?)(?P<int>\d{1,3}(?:,\d{3})+|\d+)(?:\.(?P<frac>\d+))?(?P<suffix>%|[A-Za-zµ°Ω]+)?")


class Token:
    __slots__ = ("kind", "text", "low", "start", "end", "brk")

    def __init__(self, kind, text, start, end, brk=False):
        self.kind, self.text, self.low, self.start, self.end, self.brk = kind, text, text.lower(), start, end, brk


def tokens(text):
    """Words and digit tokens with character offsets. brk is True when punctuation follows the token: a number never
    runs across it. A hyphen joins words ("twenty-one"); any other mark inside a word chunk breaks."""
    out = []

    def mark():
        if out:
            out[-1].brk = True

    for chunk in CHUNK.finditer(text):
        raw = chunk.group()
        core = raw.lstrip(LEAD)
        if len(core) != len(raw):
            mark()
        start = chunk.start() + len(raw) - len(core)
        stripped = core.rstrip(TRAIL)
        trailing = len(stripped) != len(core)
        core = stripped
        if not core:
            mark()
            continue
        if any(c.isdigit() for c in core):
            out.append(Token("num", core, start, start + len(core), brk=trailing))
            continue
        if core == "%":
            out.append(Token("word", "%", start, start + 1, brk=trailing))
            continue
        words = list(WORD.finditer(core))
        if not words:
            mark()
            continue
        position = 0
        for k, word in enumerate(words):
            between = core[position : word.start()]
            if between and (k == 0 or between != "-"):
                mark()
            out.append(Token("word", word.group(), start + word.start(), start + word.end()))
            position = word.end()
        out[-1].brk = trailing or position != len(core)
    return out


# Mentions -------------------------------------------------------------------------------------------------------
def word_class(low):
    for cls, table in (
        ("U", SMALL), ("T", TEENS), ("D", TENS), ("S", SCALES), ("OU", ORD_SMALL), ("OT", ORD_TEENS),
        ("OD", ORD_TENS), ("OB", ORD_BIG),
    ):  # fmt: skip
        if low in table:
            return "Z" if low == "zero" else cls
    return "H" if low == "hundred" else None


def word_value(low):
    for table in (SMALL, TEENS, TENS, SCALES, ORD_SMALL, ORD_TEENS, ORD_TENS, ORD_BIG):
        if low in table:
            return table[low]
    return 100 if low == "hundred" else None


def numberish(tok):
    """True for a token that would start or continue a number: digits or a number word."""
    if tok.kind == "num":
        return True
    return word_class(tok.low) is not None or tok.low in VAGUE or tok.low in PLURAL_ORDINALS


def fractional(tok):
    return word_class(tok.low) in ("OU", "OT", "OD", "OB") or tok.low in VAGUE or tok.low in PLURAL_ORDINALS


# After each state: the word classes that continue the number, and the state they lead to. An ordinal class ends the
# number as an ordinal. "and" is read inside a number only after hundred or a scale word, and only before a word that
# continues it.
NEXT = {
    "start": {"Z": "zero", "U": "small", "T": "small", "D": "tens", "OU": "ord", "OT": "ord", "OD": "ord", "OB": "ord"},
    "zero": {},
    "small": {"H": "hundred", "S": "scale"},
    "tens": {"U": "tens_units", "S": "scale", "OU": "ord"},
    "tens_units": {"H": "hundred", "S": "scale"},
    "hundred": {"U": "hundred_small", "T": "hundred_small", "D": "hundred_tens", "S": "scale", "OU": "ord",
                "OT": "ord", "OD": "ord", "AND": "hundred_and"},
    "hundred_and": {"U": "hundred_small", "T": "hundred_small", "D": "hundred_tens", "OU": "ord", "OT": "ord",
                    "OD": "ord"},
    "hundred_tens": {"U": "hundred_small", "S": "scale", "OU": "ord"},
    "hundred_small": {"S": "scale"},
    "scale": {"U": "small", "T": "small", "D": "tens", "OU": "ord", "OT": "ord", "OD": "ord", "AND": "scale_and"},
    "scale_and": {"U": "small", "T": "small", "D": "tens", "OU": "ord", "OT": "ord", "OD": "ord"},
}  # fmt: skip
# States where an ordinal word would combine: "second" there is the ordinal or the unit, so it is ambiguous.
ORDINAL_STATES = {state for state, moves in NEXT.items() if "OU" in moves and state != "start"}
# States whose whole part is complete with no scale word yet: "point" and digit words may follow.
POINT_STATES = {"zero", "small", "tens", "tens_units", "hundred", "hundred_tens", "hundred_small"}


class Reading:
    """One number's tokens first..last, its value, unit and kind, or the reason it is ambiguous."""

    def __init__(self, first, last, number=None, unit="", kind="cardinal", ambiguous=None):
        self.first, self.last, self.number, self.unit = first, last, number, unit
        self.kind, self.ambiguous = ("ambiguous" if ambiguous else kind), ambiguous


def run_on(toks, end):
    """The last index of the number-like tokens that run on, unbroken, after toks[end]."""
    stop = end + 1
    while stop + 1 < len(toks) and not toks[stop].brk and numberish(toks[stop + 1]):
        stop += 1
    return stop


def follows(toks, end):
    """The token right after toks[end] when no punctuation separates them, else None."""
    if end + 1 < len(toks) and not toks[end].brk:
        return toks[end + 1]
    return None


def spelled(toks, i):
    """The Reading of a spelled number starting at toks[i], or None when none starts there."""
    first, sign = i, 1
    low, nxt = toks[i].low, follows(toks, i)
    if low in ("minus", "negative"):
        if nxt is None or nxt.kind == "num" or not numberish(nxt):
            return None
        sign, i = -1, i + 1
        low, nxt = toks[i].low, follows(toks, i)
    if low in VAGUE or low in PLURAL_ORDINALS:
        return Reading(first, i, ambiguous="fraction_or_vague_quantity")
    if low == "point":
        if nxt is None or word_class(nxt.low) not in ("Z", "U"):
            return None
        end = i + 1
        while follows(toks, end) is not None and word_class(toks[end + 1].low) in ("Z", "U"):
            end += 1
        return Reading(first, end, ambiguous="point_without_whole_part")
    total, group, state, last_scale, last = 0, 0, "start", None, i - 1
    if low in ("a", "an"):
        if nxt is None or nxt.low not in ("hundred", *SCALES):
            return None
        group, state, last, i = 1, "small", i, i + 1
    while i < len(toks):
        tok = toks[i]
        if i > first and toks[i - 1].brk:
            break
        cls = "AND" if tok.low == "and" else word_class(tok.low)
        if state != "start" and tok.low == "second":
            if state in ORDINAL_STATES:
                return Reading(first, i, ambiguous="second_ordinal_or_unit")
            break  # the unit, read after the number
        if cls is None or cls not in NEXT[state]:
            break
        if cls == "AND":
            ahead = follows(toks, i)
            if ahead is None or word_class(ahead.low) not in NEXT[NEXT[state]["AND"]]:
                break
            state, i = NEXT[state]["AND"], i + 1
            continue
        value, target = word_value(tok.low), NEXT[state][cls]
        if cls == "S":
            if last_scale is not None and value >= last_scale:
                break
            total, group, last_scale = total + group * value, 0, value
        elif cls == "H":
            group *= 100
        else:
            group += value
        state, last, i = target, i, i + 1
        if target == "ord":
            return Reading(first, last, number=Decimal(sign * (total + group)), unit=ORDINAL, kind="ordinal")
    if last < first or toks[last].low in ("minus", "negative"):
        return None
    number, end = Decimal(total + group), last
    after = follows(toks, end)
    if after is not None and after.low == "point" and state in POINT_STATES and last_scale is None:
        k, digits = end + 2, []
        while k < len(toks) and not toks[k - 1].brk and word_class(toks[k].low) in ("Z", "U"):
            digits.append(str(SMALL[toks[k].low]))
            k += 1
        if digits:
            number, end = Decimal(f"{number}.{''.join(digits)}"), k - 1
            scale = follows(toks, end)
            if scale is not None and scale.low in SCALES:
                number, end = number * SCALES[scale.low], end + 1
    after = follows(toks, end)
    if after is not None and numberish(after) and after.low != "second":
        reason = "fraction_or_vague_quantity" if fractional(after) else "adjacent_numbers"
        return Reading(first, run_on(toks, end), ambiguous=reason)
    return Reading(first, end, number=sign * number)


def unit_after(toks, end, symbols):
    """(unit, last index) of the unit words right after toks[end], or ("", end)."""
    i = end + 1
    if follows(toks, end) is None or toks[i].kind != "word":
        return "", end
    unit, last = "", end
    if toks[i].low == "%" or (symbols and toks[i].low in SYMBOL_UNITS):
        unit, last = SYMBOL_UNITS[toks[i].low], i
    for size in range(min(LONGEST_UNIT, len(toks) - i), 0, -1):
        words = toks[i : i + size]
        if any(t.brk for t in words[:-1]) or any(t.kind != "word" for t in words):
            continue
        key = tuple(t.low for t in words)
        if key in WORD_UNITS:
            unit, last = WORD_UNITS[key], i + size - 1
            break
    per = follows(toks, last)
    if unit and per is not None and per.low == "per":
        over, over_last = unit_after(toks, last + 1, symbols=False)
        if over and "/" not in over and over != "percent":
            return f"{unit}/{over}", over_last
    return unit, last


def digits(toks, i):
    """The Reading of the digit token toks[i], with a sign word before it and a scale or unit after it."""
    tok, first = toks[i], i
    found = DIGITS.fullmatch(tok.text)
    if not found:
        return Reading(i, i, ambiguous="digits_not_one_number")
    sign = -1 if found["sign"] in ("-", "−") else 1
    if i > 0 and toks[i - 1].low in ("minus", "negative") and not toks[i - 1].brk:
        if found["sign"]:
            return Reading(i - 1, i, ambiguous="digits_not_one_number")
        sign, first = -1, i - 1
    try:
        number = Decimal(found["int"].replace(",", "") + (f".{found['frac']}" if found["frac"] else ""))
    except InvalidOperation:
        return Reading(first, i, ambiguous="digits_not_one_number")
    suffix = (found["suffix"] or "").lower()
    end, unit, kind = i, "", "cardinal"
    if suffix in ORDINAL_SUFFIX:
        if found["frac"] or found["sign"] or sign < 0:
            return Reading(first, i, ambiguous="digits_not_one_number")
        unit, kind = ORDINAL, "ordinal"
    elif suffix:
        if suffix not in SYMBOL_UNITS:
            return Reading(first, i, ambiguous="digits_not_one_number")
        unit = SYMBOL_UNITS[suffix]
    else:
        scale = follows(toks, i)
        if scale is not None and scale.low in SCALES:
            number, end = number * SCALES[scale.low], i + 1
        unit, end = unit_after(toks, end, symbols=True)
    after = follows(toks, end)
    if after is not None and numberish(after):
        return Reading(first, run_on(toks, end), ambiguous="adjacent_numbers")
    return Reading(first, end, number=sign * number, unit=unit, kind=kind)


def extract(text):
    """Every number text speaks, in order: [{text, start, end, number (Decimal or None), unit, kind, ambiguous}].
    ambiguous is None or the reason the reading is not one value."""
    toks = tokens(text)
    out, i = [], 0
    while i < len(toks):
        if toks[i].kind == "num":
            reading = digits(toks, i)
        else:
            reading = spelled(toks, i)
            if reading is None:
                i += 1
                continue
            if reading.ambiguous is None and reading.kind == "cardinal":
                unit, end = unit_after(toks, reading.last, symbols=False)
                if unit:
                    reading.unit, reading.last = unit, end
        start, end = toks[reading.first].start, toks[reading.last].end
        out.append(
            {
                "text": text[start:end],
                "start": start,
                "end": end,
                "number": reading.number,
                "unit": reading.unit,
                "kind": reading.kind,
                "ambiguous": reading.ambiguous,
            }
        )
        i = reading.last + 1
    return out


def fmt(number):
    """A Decimal as plain text (17.877, 42, -3.5), never an exponent; None stays None."""
    return None if number is None else format(number.normalize(), "f")


# The gate -------------------------------------------------------------------------------------------------------
def check_segment(voiced, cited, claims):
    """One beat's claims result. cited: the claim ids the beat lists, in order. claims: {id: claim} where a claim is
    {id, value: {spoken, number (Decimal), unit}, receipt}. Every spoken number must match exactly one cited claim
    with the same number and unit and a non-empty receipt.

    {status: passed | refused, codes, mentions: [{text, number, unit, kind, status, code?, claim?, receipt?}],
     unused_claims}"""
    rows, codes, used = [], [], set()
    for found in extract(voiced):
        row = {
            "text": found["text"],
            "number": fmt(found["number"]),
            "unit": found["unit"],
            "kind": found["kind"],
        }
        if found["ambiguous"]:
            row |= {"status": "refused", "code": "number_ambiguous", "reason": found["ambiguous"]}
        else:
            same = [
                c for c in cited
                if c in claims and claims[c]["value"]["number"] == found["number"]
                and claims[c]["value"]["unit"] == found["unit"]
            ]  # fmt: skip
            backed = [c for c in same if (claims[c]["receipt"] or "").strip()]
            if len(backed) == 1:
                row |= {"status": "matched", "claim": backed[0], "receipt": claims[backed[0]]["receipt"]}
                used.add(backed[0])
            elif len(backed) > 1:
                row |= {"status": "refused", "code": "claim_ambiguous", "claims": backed}
            elif same:
                row |= {"status": "refused", "code": "claim_unreceipted", "claims": same}
            else:
                row |= {"status": "refused", "code": "number_unclaimed"}
        if row["status"] == "refused" and row["code"] not in codes:
            codes.append(row["code"])
        rows.append(row)
    return {
        "status": "refused" if codes else "passed",
        "codes": codes,
        "mentions": rows,
        "unused_claims": [c for c in cited if c not in used],
    }
