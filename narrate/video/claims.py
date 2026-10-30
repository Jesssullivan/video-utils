"""The spoken-number claims gate of a demo bundle (docs/spec/NARRATED_VIDEO.md, "Demo bundle intake").

Every number a beat's voiced text speaks must match a claims.json entry that the beat cites and that carries a
receipt. extract() finds the numbers: digits ("17.877", "1,024", "42%", "3rd", "12ms") and spelled-out English
("seventeen point eight seven seven", "one hundred and five", "forty two percent", "twenty first"), each with the
unit that follows it ("milliseconds", "per cent", "frames per second"). It fails closed: a reading it cannot pin to
one value is a mention with `ambiguous` set, and an ambiguous mention never matches a claim.

Ambiguous readings (refused as number_ambiguous):
- adjacent number words that are not one well-formed number: "nineteen eighty four", "one two three";
- a fraction or a vague quantity: "one third", "two thirds", "a half", "a third", "an eighth", "quarter", "dozen",
  "couple", "twice", the plural scale words ("hundreds", "thousands", "millions", "tens of"), "-fold" words
  ("tenfold", "ten-fold"), "nil", "nought", "naught" and the decade words ("the nineties", "teens");
- a scale word with no count before it: "hundred files", "thousand users";
- "point" with digit words and no whole part before it ("point five");
- "second" where it could be the ordinal or the unit ("twenty second", "one hundred second");
- a Roman numeral of two or more of I, V and X in capitals ("World War II", "Phase IV");
- a dash other than a hyphen between number words (an en dash in "five-hundred");
- a digit token that is not one plain number: "1.2.3", "10:30", "1/2", "2026-10-29", "MP4", "1,23", "4K", "½",
  "5M", or a whole ten with an attached "s" ("the 90s", "1990s"), which may be a decade or seconds;
- a number followed by a scale abbreviation or a unit the gate does not read: a single letter ("17 K", "3 B"),
  "k", "bn", "mn", "lakh", "crore", "grand", a lower-case unit with no vowel ("kph", "kbps"), a binary prefix
  ("GiB"), a mixed-case unit such as "Mbps" or "kWh", a unit symbol in another case that is not all capitals
  ("mpa", "Kpa", "dba"), or "/" joining a unit to something that is not one.

A hyphen (U+002D, U+2010, U+2011 or a soft hyphen) joins words ("twenty-one"). A possessive or contraction of a
number word ("five's") reads as the number. Unit symbols are read in their exact case ("m" is metres, "M" is not a
unit, "MPa" is megapascals). Other unknown words after a number, acronyms such as "MCP" and "GPA" among them, leave
it a bare count.

Not extracted: once, single, both, none and "a" or "an" before anything but hundred, thousand, million, billion,
trillion or an ordinal. "one" is always the number 1, and "first" or "second" alone are the ordinals 1 and 2: a
script that uses them as words cites a claim or rewords. These rules are strict on purpose (TIN-7735): a demo must
not speak a number that no receipt backs.

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
    "quadruple", "hundreds", "thousands", "millions", "billions", "trillions", "tens", "nil", "nought", "naught",
    "teens", "twenties", "thirties", "forties", "fifties", "sixties", "seventies", "eighties", "nineties",
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
    "dBA": (
        ("decibel", "a", "weighted"),
        ("decibels", "a", "weighted"),
        ("a", "weighted", "decibel"),
        ("a", "weighted", "decibels"),
    ),
    "V": ("volt", "volts"),
    "mV": ("millivolt", "millivolts"),
    "A": ("amp", "amps", "ampere", "amperes"),
    "mA": ("milliamp", "milliamps", "milliampere", "milliamperes"),
    "W": ("watt", "watts"),
    "kW": ("kilowatt", "kilowatts"),
    "mW": ("milliwatt", "milliwatts"),
    "ohm": ("ohm", "ohms"),
    "N": ("newton", "newtons"),
    "kN": ("kilonewton", "kilonewtons"),
    "Nm": (("newton", "metre"), ("newton", "metres"), ("newton", "meter"), ("newton", "meters")),
    "Pa": ("pascal", "pascals"),
    "kPa": ("kilopascal", "kilopascals"),
    "MPa": ("megapascal", "megapascals"),
    "GPa": ("gigapascal", "gigapascals"),
    "K": ("kelvin", "kelvins"),
    "m": ("metre", "metres", "meter", "meters"),
    "cm": ("centimetre", "centimetres", "centimeter", "centimeters"),
    "mm": ("millimetre", "millimetres", "millimeter", "millimeters"),
    "um": ("micrometre", "micrometres", "micrometer", "micrometers", "micron", "microns"),
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
    "rpm": (("revolution", "per", "minute"), ("revolutions", "per", "minute")),
    "ppm": (("part", "per", "million"), ("parts", "per", "million")),
    "x": ("times",),
    "USD": ("dollar", "dollars"),
}
# Case matters: "m" is metres and "M" a scale, "mW" is milliwatts and "MW" megawatts, "MB" is bytes and "Mb" bits,
# "Pa" is pascals and "PA" an acronym. A symbol in any other case is not read as a unit. "K" is no symbol: "17 K"
# and "4K" may be thousands, so kelvin is read only as the word.
SYMBOL_UNITS = {
    "%": "percent", "s": "s", "sec": "s", "ms": "ms", "us": "us", "µs": "us", "μs": "us", "ns": "ns",
    "min": "min", "h": "h", "Hz": "Hz", "hz": "Hz", "kHz": "kHz", "khz": "kHz", "MHz": "MHz", "mhz": "MHz",
    "GHz": "GHz", "ghz": "GHz", "dB": "dB", "db": "dB", "dBFS": "dBFS", "dbfs": "dBFS", "LUFS": "LUFS",
    "lufs": "LUFS", "LU": "LU", "lu": "LU", "dBTP": "dBTP", "dbtp": "dBTP", "V": "V", "v": "V", "mV": "mV",
    "mv": "mV", "mA": "mA", "ma": "mA", "W": "W", "w": "W", "kW": "kW", "kw": "kW", "mW": "mW", "mw": "mW",
    "Ω": "ohm", "m": "m", "cm": "cm", "mm": "mm", "km": "km", "g": "g", "kg": "kg", "mg": "mg", "°C": "degC",
    "°c": "degC", "°F": "degF", "°f": "degF", "°": "deg", "KB": "KB", "kB": "KB", "MB": "MB", "GB": "GB",
    "TB": "TB", "fps": "fps", "px": "px", "x": "x", "dBA": "dBA", "N": "N", "kN": "kN", "N·m": "Nm",
    "N⋅m": "Nm", "Nm": "Nm", "Pa": "Pa", "kPa": "kPa", "MPa": "MPa", "GPa": "GPa", "µm": "um", "μm": "um",
    "rpm": "rpm", "RPM": "rpm", "ppm": "ppm", "PPM": "ppm",
}  # fmt: skip
# Lower case of every symbol: a word that is one of these in another case, not all capitals, is a miscased unit.
SYMBOL_LOWER = {s.lower() for s in SYMBOL_UNITS}
# After a number these may change its value or name a unit the gate does not read, so the number is ambiguous rather
# than a bare count. Compared in lower case; single letters, vowel-less lower-case units, binary prefixes and
# mixed-case units are caught by their shape in unknown_after.
SCALE_ABBREVIATIONS = {
    "k", "kk", "bn", "mn", "mln", "mio", "bil", "tn", "mil", "thou", "grand", "lakh", "lakhs", "lac", "crore",
    "crores",
}  # fmt: skip
UPPER_UNKNOWN = {"BN", "MN", "MW", "MV", "MA", "KM", "PB", "EB", "KPH", "MPH", "BPM", "KBPS", "MBPS"}
VOWELS = set("aeiouy")
IEC = re.compile(r"[KMGTPEkmgtpe]i[Bb](?:ps)?")
LETTER_WORDS = {"a", "A", "I"}  # single letters that may follow a number without changing it
# Two or more of I, V and X in capitals, read as a Roman numeral ("II", "IV", "XIV").
ROMAN = re.compile(r"(?=[IVX]{2,}$)X{0,3}(?:IX|IV|V?I{0,3})")
# A hyphen joins words. Another dash between two words is a break, and a number never runs across it silently.
JOINERS = {"-", "\u2010", "\u2011", "\u00ad"}
DASHES = set("\u2012\u2013\u2014\u2015\u2212\u2e3a\u2e3b\ufe58\ufe63\uff0d")
APOSTROPHES = re.compile("['\u2019]")
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
WORD = re.compile("[A-Za-z]+(?:['\u2019][A-Za-z]+)?")
LEAD = "([{\"'“‘"
TRAIL = ".,;:!?)]}\"'”’"
DIGITS = re.compile(
    r"(?P<sign>[-−+]?)(?P<int>[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.(?P<frac>[0-9]+))?(?P<suffix>%|[A-Za-zµμ°Ω·⋅]+)?"
)


class Token:
    """brk: punctuation follows. dash: that punctuation, inside one chunk, is a dash other than a hyphen. slash: it is
    a "/". low is the lower-case text, without the "'s" or other apostrophe ending of a number word ("five's")."""

    __slots__ = ("kind", "text", "low", "start", "end", "brk", "dash", "slash")

    def __init__(self, kind, text, start, end, brk=False):
        self.kind, self.text, self.low, self.start, self.end, self.brk = kind, text, text.lower(), start, end, brk
        self.dash = self.slash = False
        base = APOSTROPHES.split(self.low)[0]
        if base != self.low and (word_class(base) is not None or vague(base)):
            self.low, self.brk = base, True


def tokens(text):
    """Words and digit tokens with character offsets. brk is True when punctuation follows the token: a number never
    runs across it. A hyphen joins words ("twenty-one"); any other mark inside a word chunk breaks. A chunk with any
    numeric character ("12", "½", "²", "٣") is one digit token."""
    out = []

    def mark(between=""):
        if out:
            out[-1].brk = True
            out[-1].dash = out[-1].dash or any(c in DASHES for c in between)
            out[-1].slash = out[-1].slash or between == "/"

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
        if any(c.isnumeric() for c in core):
            out.append(Token("num", core, start, start + len(core), brk=trailing))
            continue
        if core in SYMBOL_UNITS and not WORD.fullmatch(core):
            # One token for a unit symbol with a mark the word pattern splits on: "%", "°C", "µs", "Ω", "N·m".
            out.append(Token("word", core, start, start + len(core), brk=trailing))
            continue
        words = list(WORD.finditer(core))
        if not words:
            mark(core)
            continue
        position = 0
        for k, word in enumerate(words):
            between = core[position : word.start()]
            if between and (k == 0 or between not in JOINERS):
                mark(between if k else "")
            out.append(Token("word", word.group(), start + word.start(), start + word.end()))
            position = word.end()
        out[-1].brk = out[-1].brk or trailing or position != len(core)
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


def vague(low):
    """A fraction or vague quantity word: "half", "thousands", "thirds", "tenfold"."""
    if low in VAGUE or low in PLURAL_ORDINALS:
        return True
    return low.endswith("fold") and (word_class(low[:-4]) is not None or low[:-4] in VAGUE)


def roman(tok):
    return tok.kind == "word" and ROMAN.fullmatch(tok.text) is not None


def numberish(tok):
    """True for a token that would start or continue a number: digits, a number word or a Roman numeral."""
    if tok.kind == "num":
        return True
    return word_class(tok.low) is not None or vague(tok.low) or roman(tok)


def fractional(tok):
    return word_class(tok.low) in ("OU", "OT", "OD", "OB") or vague(tok.low)


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


def span_end(toks, i):
    """The last index of toks[i] and the number-like tokens that run on after it."""
    after = follows(toks, i)
    return run_on(toks, i) if after is not None and numberish(after) else i


def spelled(toks, i):
    """The Reading of a spelled number starting at toks[i], or None when none starts there."""
    first, sign = i, 1
    low, nxt = toks[i].low, follows(toks, i)
    if low in ("minus", "negative"):
        if nxt is None or nxt.kind == "num" or not numberish(nxt):
            return None
        sign, i = -1, i + 1
        low, nxt = toks[i].low, follows(toks, i)
    if vague(low):
        return Reading(first, i, ambiguous="fraction_or_vague_quantity")
    if roman(toks[i]):
        return Reading(first, span_end(toks, i), ambiguous="roman_numeral")
    if word_class(low) in ("H", "S"):
        return Reading(first, span_end(toks, i), ambiguous="scale_without_count")
    if low == "point":
        if nxt is None or word_class(nxt.low) not in ("Z", "U"):
            return None
        end = i + 1
        while follows(toks, end) is not None and word_class(toks[end + 1].low) in ("Z", "U"):
            end += 1
        return Reading(first, end, ambiguous="point_without_whole_part")
    total, group, state, last_scale, last = 0, 0, "start", None, i - 1
    if low in ("a", "an"):
        if nxt is not None and word_class(nxt.low) in ("OU", "OT", "OD", "OB"):
            return Reading(first, i + 1, ambiguous="fraction_or_vague_quantity")  # "a third", "an eighth"
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


def unknown_after(tok):
    """True for a word after a number that may scale it or names a unit the gate does not read: a single letter
    ("17 K"), a scale abbreviation ("bn", "lakh"), a lower-case unit with no vowel ("kph"), a binary prefix ("GiB"),
    a mixed-case unit ("Mbps", "kWh") or a listed capital one ("MW", "RPM"). An acronym such as "MCP" is not."""
    text = tok.text
    if tok.kind != "word" or not text.isalpha():
        return False
    if len(text) == 1:
        return text not in LETTER_WORDS
    if tok.low in SCALE_ABBREVIATIONS or text in UPPER_UNKNOWN or IEC.fullmatch(text):
        return True
    if tok.low in SYMBOL_LOWER and not text.isupper():
        return True  # a unit symbol in the wrong case ("mpa", "Kpa", "dba")
    if text.islower():
        return len(text) <= 5 and not set(text) & VOWELS
    if text.isupper():
        return False
    plural_acronym = text[:-1].isupper() and text[-1] == "s"
    inner_capital = any(a.islower() and b.isupper() for a, b in zip(text, text[1:], strict=False))
    return not plural_acronym and (inner_capital or (len(text) <= 5 and not set(text.lower()) & VOWELS))


def symbol_at(toks, i):
    """The canonical unit of the symbol toks[i] in its exact case, or ""."""
    if i >= len(toks) or toks[i].kind != "word":
        return ""
    return SYMBOL_UNITS.get(toks[i].text, "")


def unit_after(toks, end, symbols):
    """(unit, last index, ambiguous) for the unit words right after toks[end], or ("", end, ambiguous). ambiguous is
    None, "unknown_scale_or_unit" (the next word may scale the number; last is end) or "unit_not_read" (a "/" joins
    the unit to something that is not one; last is that thing)."""
    i = end + 1
    if follows(toks, end) is None or toks[i].kind != "word":
        return "", end, None
    unit, last = "", end
    if toks[i].text == "%" or (symbols and symbol_at(toks, i)):
        unit, last = symbol_at(toks, i), i
    for size in range(min(LONGEST_UNIT, len(toks) - i), 0, -1):
        words = toks[i : i + size]
        if any(t.brk for t in words[:-1]) or any(t.kind != "word" for t in words):
            continue
        key = tuple(t.low for t in words)
        if key in WORD_UNITS:
            unit, last = WORD_UNITS[key], i + size - 1
            break
    if not unit:
        return "", end, ("unknown_scale_or_unit" if unknown_after(toks[i]) else None)
    if toks[last].slash:
        k = last + 1
        over = symbol_at(toks, k) or (WORD_UNITS.get((toks[k].low,), "") if k < len(toks) else "")
        if not over or "/" in over or over in ("percent", "x") or toks[k].slash:
            return unit, min(k, len(toks) - 1), "unit_not_read"
        return f"{unit}/{over}", k, None
    per = follows(toks, last)
    if per is not None and per.low == "per":
        over, over_last, _ = unit_after(toks, last + 1, symbols=False)
        if over and "/" not in over and over != "percent":
            return f"{unit}/{over}", over_last, None
    return unit, last, None


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
    suffix = found["suffix"] or ""
    end, unit, kind = i, "", "cardinal"
    if suffix.lower() in ORDINAL_SUFFIX:
        if found["frac"] or found["sign"] or sign < 0:
            return Reading(first, i, ambiguous="digits_not_one_number")
        unit, kind = ORDINAL, "ordinal"
    elif suffix == "s" and not found["frac"] and number >= 10 and number % 10 == 0:
        return Reading(first, i, ambiguous="decade_or_seconds")  # "the 90s", "1990s"
    elif suffix:
        if suffix not in SYMBOL_UNITS:
            return Reading(first, i, ambiguous="digits_not_one_number")
        unit = SYMBOL_UNITS[suffix]
    else:
        scale = follows(toks, i)
        if scale is not None and scale.low in SCALES:
            number, end = number * SCALES[scale.low], i + 1
        unit, end, unclear = unit_after(toks, end, symbols=True)
        if unclear:
            return Reading(first, end + 1 if unclear == "unknown_scale_or_unit" else end, ambiguous=unclear)
    after = follows(toks, end)
    if after is not None and numberish(after):
        return Reading(first, run_on(toks, end), ambiguous="adjacent_numbers")
    return Reading(first, end, number=sign * number, unit=unit, kind=kind)


def joined(toks, reading):
    """reading, or an ambiguous reading when a dash joins it to the next number (an en dash between "five" and
    "hundred") or "fold" follows it ("ten-fold", "10 fold")."""
    if reading.ambiguous:
        return reading
    last = reading.last
    if toks[last].dash and last + 1 < len(toks) and numberish(toks[last + 1]):
        return Reading(reading.first, last + 1, ambiguous="dash_between_numbers")
    after = follows(toks, last)
    if after is not None and after.low == "fold":
        return Reading(reading.first, last + 1, ambiguous="fraction_or_vague_quantity")
    return reading


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
                unit, end, unclear = unit_after(toks, reading.last, symbols=True)
                if unclear:
                    last = end + 1 if unclear == "unknown_scale_or_unit" else end
                    reading = Reading(reading.first, last, ambiguous=unclear)
                elif unit:
                    reading.unit, reading.last = unit, end
        reading = joined(toks, reading)
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
