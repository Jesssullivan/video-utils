"""Numeric ranges and money amounts said in words (docs/spec/NARRATE.md, "Ranges and money").

The written script keeps its digits. Spoken normalisation says each recognised range or amount in words before the
pronunciation tables run, and records the written and spoken forms. Every expansion is read back from its spoken
words to its values; a read-back that differs from the written digits, unit or connector is refused. The generator
(cardinal) and the reader (parse_cardinal) are separate code paths, so the read-back checks one with the other.

Recognised, and nothing else:

- a dollar amount: $700, $2,346.08, $0.99 (cents exactly two digits);
- an ascending range of two unsigned amounts joined by an en dash (17–19, or 17 – 19 with one space on each side),
  by " to " or " through ", or by a hyphen-minus with no spaces. A hyphen-minus, to or through range needs a $ or a
  recognised unit (lexical.UNITS) to mark it: $5-$10 and 120-275 h are ranges, 314-422 and 3 to 5 stay as
  written; B, x and dB do not mark a hyphen-minus range. A unit may follow the second amount, and the first only
  when it is the same unit (5%–10%).

Left as written: a signed amount (-$5, -5–10 dB, 5–-10); an amount next to a letter, digit, underscore, slash,
backslash, dot, comma, colon, #, @, §, a currency sign other than a leading $, a sign or another dash (x86-64,
A7_31/0/88, 2026-10-26, 9:00–10:30, 1–2–3, #17–19, €5–10, TIN-7087); a money amount with a scale word or a
suffix ($2 million, $5k, $5-year); cents not in two digits ($1.5); an integer part with a leading zero (01–05); a
descending or equal range (10–5); a bare range with an ungrouped integer of four or more digits, such as a year,
phone number or standard (1990–1995, 555–1234); a range with B as its unit, x after a space, or a bare s or B
written against the digits (1990–2000s); an em dash or a spaced hyphen-minus; and any span a pronunciation table
entry with digits in its written form matches (the entry is the opt-out). This is a bounded recogniser, not a
parser of every way English writes a number.
"""

import re
from dataclasses import dataclass
from decimal import Decimal

from .lexical import UNITS

ONES = (
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
    "seventeen eighteen nineteen"
).split()
TENS = (None, None, *"twenty thirty forty fifty sixty seventy eighty ninety".split())
SCALES = ((10**12, "trillion"), (10**9, "billion"), (10**6, "million"), (10**3, "thousand"))
LIMIT = 10**15
CENT = Decimal("0.01")
CONNECTORS = {"–": "to", "-": "to", "to": "to", "through": "through"}

_ONE = {w: n for n, w in enumerate(ONES)}
_TEN = {w: 10 * n for n, w in enumerate(TENS) if w}
_SCALE = {name: size for size, name in SCALES}

# A range's unit is said by its plural spoken alias from the shared unit table; a written-out alias is kept.
_UNIT_IDS = {alias: unit for unit, aliases in UNITS.items() for alias in aliases}
PLURAL = {unit: ("percent" if unit == "%" else aliases[-1]) for unit, aliases in UNITS.items()}
_SYMBOLS = {aliases[0] for aliases in UNITS.values()} | {"KB"}
_TIGHT_REFUSED = {"s", "B"}  # 1990s and 20B: a bare s or B written against the digits is not taken as a unit
_NO_HYPHEN_MARK = {"B", "x", "dB"}  # Apt 3-4 B, rooms 2-4 x 8, 10-5 dB: too ambiguous to mark a hyphen-minus range
_UNGROUPED = re.compile(r"\d{4,}(?:\.\d+)?")  # 1990, 1234, 9001: a year, phone number or standard more often than not

_NUM = r"(?:[1-9]\d{0,2}(?:,\d{3})+|0|[1-9]\d*)(?:\.\d+)?"
_UNIT = "|".join(re.escape(a) for a in sorted(_UNIT_IDS, key=len, reverse=True))
# Other currency signs and the section sign: the recogniser says dollars only, so €5–10 and §5–7 stay as written.
_SIGNS = "€£¥₹₩₽¢₪₫₺₴₦₱฿¤§"
_SPACE = "[ \N{NO-BREAK SPACE}]"
_LEFT = r"(?<![\w.,:/\\$#@+\-\N{MINUS SIGN}–" + _SIGNS + "])"
_RIGHT = r"(?!\w|[.,:]\d|[/\\_#@]|[+\-\N{MINUS SIGN}–][\w$]|" + _SPACE + "?[$" + _SIGNS + "])"
_PATTERN = rf"""
    {_LEFT}
    (?P<a_cur>\$)?(?P<a>{_NUM})
    (?:
        (?:(?P<a_gap>{_SPACE}?)(?P<a_unit>{_UNIT})(?!\w))?
        (?:(?P<dash>{_SPACE}–{_SPACE}|[–-])|{_SPACE}+(?P<word>to|through){_SPACE}+)
        (?P<b_cur>\$)?(?P<b>{_NUM})
    )?
    (?:(?P<b_gap>{_SPACE}?)(?P<b_unit>{_UNIT})(?!\w))?
    {_RIGHT}
"""
_AMOUNT = re.compile(_PATTERN, re.VERBOSE)
_SCALED = re.compile(r"[ \N{NO-BREAK SPACE}]*(?:thousand|million|billion|trillion|bn)\b", re.IGNORECASE)


class AmountError(ValueError):
    """A spoken expansion does not read back to the written values."""


@dataclass(frozen=True)
class Expansion:
    start: int
    end: int
    written: str
    spoken: str
    kind: str  # money, money_range or range
    connector: str | None  # the spoken connector: to, through, or None for a single amount
    values: tuple  # ((value, unit or None), ...): value is the written digits without grouping commas

    def record(self):
        return {
            "kind": self.kind,
            "written": self.written,
            "spoken": self.spoken,
            "connector": self.connector,
            "values": [{"value": v, "unit": u} for v, u in self.values],
        }


# -- saying -------------------------------------------------------------------------------------------------------
def _below_thousand(n):
    words = []
    if n >= 100:
        words += [ONES[n // 100], "hundred"]
        n %= 100
    if n >= 20:
        words.append(TENS[n // 10] + (f"-{ONES[n % 10]}" if n % 10 else ""))
    elif n:
        words.append(ONES[n])
    return " ".join(words)


def cardinal(n):
    """n in words, US style: 2346 -> two thousand three hundred forty-six."""
    if not 0 <= n < LIMIT:
        raise ValueError(f"{n}: from 0 to {LIMIT - 1}")
    if n == 0:
        return "zero"
    parts = []
    for size, name in SCALES:
        if n >= size:
            parts += [_below_thousand(n // size), name]
            n %= size
    if n:
        parts.append(_below_thousand(n))
    return " ".join(parts)


def say_number(literal):
    """A written unsigned number in words; each digit after the point is said: 2.25 -> two point two five."""
    whole, _, fraction = literal.replace(",", "").partition(".")
    spoken = cardinal(int(whole))
    if fraction:
        spoken += " point " + " ".join(ONES[int(d)] for d in fraction)
    return spoken


def say_money(literal):
    """A dollar amount in words: 2,346.08 -> two thousand three hundred forty-six dollars and eight cents."""
    whole, _, fraction = literal.replace(",", "").partition(".")
    dollars, cents = int(whole), int(fraction or 0)
    cents_said = f"{cardinal(cents)} {'cent' if cents == 1 else 'cents'}"
    if dollars == 0 and cents:
        return cents_said
    said = f"{cardinal(dollars)} {'dollar' if dollars == 1 else 'dollars'}"
    return f"{said} and {cents_said}" if cents else said


# -- reading back ---------------------------------------------------------------------------------------------------
def parse_cardinal(words):
    """The integer words say, read by the grammar cardinal writes ("and" after hundred or a scale is also read).
    Raises AmountError for anything else."""
    if words == ["zero"]:
        return 0
    total, group, last, scale = 0, 0, None, None
    for i, w in enumerate(words):
        n = _ONE.get(w)
        if n is not None and w != "zero" and n < 10 and last in (None, "hundred", "scale", "and", "tens"):
            group, last = group + n, "unit"
        elif n is not None and n >= 10 and last in (None, "hundred", "scale", "and"):
            group, last = group + n, "teen"
        elif w in _TEN and last in (None, "hundred", "scale", "and"):
            group, last = group + _TEN[w], "tens"
        elif w == "hundred" and last == "unit" and group < 10:
            group, last = group * 100, "hundred"
        elif w in _SCALE and last in ("unit", "teen", "tens", "hundred") and (scale is None or _SCALE[w] < scale):
            total, group, last, scale = total + group * _SCALE[w], 0, "scale", _SCALE[w]
        elif w == "and" and last in ("hundred", "scale") and i + 1 < len(words):
            last = "and"
        else:
            raise AmountError(f"{' '.join(words)!r} is not a number in words")
    if last in (None, "and"):
        raise AmountError(f"{' '.join(words)!r} is not a number in words")
    return total + group


def parse_number(words):
    """The written digits words say: [two, point, two, five] -> "2.25"."""
    if "point" not in words:
        return str(parse_cardinal(words))
    i = words.index("point")
    fraction = words[i + 1 :]
    if not fraction or any(_ONE.get(w, 10) > 9 for w in fraction):
        raise AmountError(f"{' '.join(words)!r}: each digit after point is one word, zero to nine")
    return f"{parse_cardinal(words[:i])}." + "".join(str(_ONE[w]) for w in fraction)


def _endpoint(words):
    """(value, "$" or None) of one side of a spoken expansion."""
    for currency in ("dollar", "dollars"):
        if currency in words:
            i = words.index(currency)
            value = Decimal(parse_cardinal(words[:i]))
            rest = words[i + 1 :]
            if rest:
                if len(rest) < 3 or rest[0] != "and" or rest[-1] not in ("cent", "cents"):
                    raise AmountError(f"{' '.join(words)!r}: dollars and cents")
                cents = parse_cardinal(rest[1:-1])
                if not 1 <= cents <= 99:
                    raise AmountError(f"{' '.join(words)!r}: cents from one to ninety-nine")
                value += Decimal(cents) / 100
            return str(value.quantize(CENT)), "$"
    if words and words[-1] in ("cent", "cents"):
        cents = parse_cardinal(words[:-1])
        if not 1 <= cents <= 99:
            raise AmountError(f"{' '.join(words)!r}: cents from one to ninety-nine")
        return str((Decimal(cents) / 100).quantize(CENT)), "$"
    return parse_number(words), None


def read_back(spoken):
    """(connector, ((value, unit), ...)) that a spoken expansion says. A trailing unit, or the dollars of a range
    whose amounts have no cents, applies to both sides. Raises AmountError when the words do not parse."""
    tokens = spoken.replace("-", " ").split()
    unit = None
    for alias in sorted(_UNIT_IDS, key=lambda a: -len(a.split())):
        said = alias.split()
        if len(tokens) > len(said) and tokens[-len(said) :] == said:
            unit, tokens = _UNIT_IDS[alias], tokens[: -len(said)]
            break
    joins = [i for i, t in enumerate(tokens) if t in ("to", "through")]
    if len(joins) > 1:
        raise AmountError(f"{spoken!r}: one connector at most")
    connector = tokens[joins[0]] if joins else None
    sides = [tokens[: joins[0]], tokens[joins[0] + 1 :]] if joins else [tokens]
    values = [_endpoint(side) for side in sides]
    if unit is not None:
        if any(u for _, u in values):
            raise AmountError(f"{spoken!r}: a unit and a currency")
        values = [(v, unit) for v, _ in values]
    elif connector and values[0][1] is None and values[1][1] == "$":
        if "." in values[0][0]:
            raise AmountError(f"{spoken!r}: only whole dollars share a trailing dollars")
        values[0] = (str(Decimal(values[0][0]).quantize(CENT)), "$")
    if len({u for _, u in values}) > 1:
        raise AmountError(f"{spoken!r}: the two sides differ in unit")
    return connector, tuple(values)


def verify(expansion):
    """Raise AmountError unless the spoken form reads back to the written values, unit and connector."""
    got = read_back(expansion.spoken)
    want = (expansion.connector, expansion.values)
    if got != want:
        raise AmountError(f"{expansion.written!r} -> {expansion.spoken!r} reads back as {got}, not {want}")


# -- finding ------------------------------------------------------------------------------------------------------
def _cents_ok(literal):
    return "." not in literal or len(literal.partition(".")[2]) == 2


def _unit_said(alias):
    unit = _UNIT_IDS[alias]
    return PLURAL[unit] if alias in _SYMBOLS else alias


def _plain(literal):
    return literal.replace(",", "")


def _expansion(m, text, lenient):
    a, b = m.group("a"), m.group("b")
    a_unit, b_unit = m.group("a_unit"), m.group("b_unit")
    money = bool(m.group("a_cur") or m.group("b_cur"))
    if _too_large(m):
        return None
    for unit, gap in ((a_unit, m.group("a_gap")), (b_unit, m.group("b_gap"))):
        if unit in _TIGHT_REFUSED and not gap:
            return None
    if money and _SCALED.match(text, m.end()):
        return None  # $2 million, $1–2 billion: left as written
    if b is None:  # a single amount: only money is said in words
        if not money or a_unit or b_unit or not _cents_ok(a):
            return None
        value = str(Decimal(_plain(a)).quantize(CENT))
        return Expansion(m.start(), m.end(), m.group(0), say_money(a), "money", None, ((value, "$"),))
    dash = (m.group("dash") or "").strip()
    connector = CONNECTORS[dash or m.group("word")]
    if dash != "–" and not (money or b_unit) and not lenient:
        return None  # a hyphen-minus, to or through between bare numbers is not taken as a range
    if dash == "-" and not money and b_unit in _NO_HYPHEN_MARK:
        return None
    if a_unit and (not b_unit or _UNIT_IDS[a_unit] != _UNIT_IDS[b_unit]):
        return None
    if "B" in (a_unit, b_unit) or ("x" in (a_unit, b_unit) and (m.group("a_gap") or m.group("b_gap"))):
        return None  # Gates 10–12 B, rooms 2–4 x 8: a label or a dimension, not bytes or times
    if not Decimal(_plain(a)) < Decimal(_plain(b)):
        return None  # 10–5 and 5–5 are a score or a label more often than a range
    if not (money or b_unit) and any(_UNGROUPED.fullmatch(x) for x in (a, b)):
        return None  # 1990–1995, 555–1234, ISO 9001–2015
    if money:
        both = m.group("a_cur") and m.group("b_cur")
        if a_unit or b_unit or not (_cents_ok(a) and _cents_ok(b)) or (m.group("word") and not both and not lenient):
            return None  # "$5 to 3 people" is not a money range: to and through need a $ on both sides
        values = tuple((str(Decimal(_plain(x)).quantize(CENT)), "$") for x in (a, b))
        if all(Decimal(v) == int(Decimal(v)) for v, _ in values):
            spoken = f"{cardinal(int(Decimal(_plain(a))))} {connector} {cardinal(int(Decimal(_plain(b))))} dollars"
        else:
            spoken = f"{say_money(a)} {connector} {say_money(b)}"
        return Expansion(m.start(), m.end(), m.group(0), spoken, "money_range", connector, values)
    unit = _UNIT_IDS[b_unit] if b_unit else None
    spoken = f"{say_number(a)} {connector} {say_number(b)}" + (f" {_unit_said(b_unit)}" if b_unit else "")
    values = ((_plain(a), unit), (_plain(b), unit))
    return Expansion(m.start(), m.end(), m.group(0), spoken, "range", connector, values)


def _too_large(m):
    return any(int(_plain(x).partition(".")[0]) >= LIMIT for x in (m.group("a"), m.group("b")) if x)


def find(text, lenient=False, keep=()):
    """[Expansion] of text in reading order, each verified by its read-back. lenient (for a transcript) also takes a
    hyphen-minus, to or through between bare numbers, and a to range with one $, as a range. keep is [(start, end)]
    of spans to leave as written: an expansion that overlaps one is not taken."""
    out, pos = [], 0
    while True:
        m = _AMOUNT.search(text, pos)
        if m is None:
            return out
        found = _expansion(m, text, lenient)
        if found is None and m.group("word") and not _SCALED.match(text, m.end()):
            # "$5 to 3 people": the range is not taken, and the first amount alone may still be money.
            first = m.end("a_unit") if m.group("a_unit") else m.end("a")
            single = _AMOUNT.match(text[:first], m.start())
            found = _expansion(single, text, lenient) if single and single.end() == first else None
        if found is None:
            pos = m.start() + 1
            continue
        if any(start < found.end and found.start < end for start, end in keep):
            pos = found.end
            continue
        verify(found)
        out.append(found)
        pos = found.end


def expand(text, lenient=False, keep=()):
    """(spoken text, [Expansion]): text with each recognised range and amount said in words."""
    found = find(text, lenient, keep)
    for e in reversed(found):
        text = text[: e.start] + e.spoken + text[e.end :]
    return text, found


def say(text):
    """A transcript with any range or amount it wrote in digits said in words, for scoring WER."""
    try:
        return expand(text, lenient=True)[0]
    except AmountError:
        return text


# -- mapping a rewrite back -----------------------------------------------------------------------------------------
_TOKEN = re.compile(r"[A-Za-z]+|[^\sA-Za-z-]")  # a hyphen joins number words; it is not a token
_JOIN = re.compile(r"[ \t\n\N{NO-BREAK SPACE}-]*")


def _tokens(text):
    """[(token, start, end)] with each run of number words read as one token of its digits."""
    raw = [(m.group(0).lower(), m.start(), m.end()) for m in _TOKEN.finditer(text)]
    out, i = [], 0
    while i < len(raw):
        best = None
        if raw[i][0].isalpha():
            j = i
            while j < len(raw) and j - i < 24 and raw[j][0].isalpha():
                if j > i and not _JOIN.fullmatch(text, raw[j - 1][2], raw[j][1]):
                    break
                j += 1
                try:
                    best = (parse_number([t for t, _, _ in raw[i:j]]), j)
                except AmountError:
                    pass
        if best is None:
            out.append(raw[i])
            i += 1
        else:
            value, j = best
            out.append((value, raw[i][1], raw[j - 1][2]))
            i = j
    return out


_EXTENDS = {"hundred", "point", "cent", "cents", "dollar", "dollars", *_SCALE}
_SIGN_WORDS = {"minus", "negative", "plus", "positive"}
_UNIT_WORDS = sorted({tuple(a.lower().split()) for a in _UNIT_IDS}, key=len, reverse=True)


def _number(token):
    return token[:1].isdigit()


def _whole(text, tokens, i, j):
    """Whether tokens[i:j] is a whole number phrase: no sign before it, and no number, scale word, point, cents,
    currency or unit after it that would change the value it reads back to."""
    words = [t for t, _, _ in tokens]
    before = text[: tokens[i][1]].rstrip(" \t\n\N{NO-BREAK SPACE}")
    if before and before[-1] in "-+\N{MINUS SIGN}$" + _SIGNS:
        return False
    if i and (words[i - 1] in _SIGN_WORDS | _EXTENDS or _number(words[i - 1])):
        return False
    if i > 1 and words[i - 1] == "and" and (words[i - 2] in _EXTENDS or _number(words[i - 2])):
        return False
    rest = words[j:]
    if rest and (rest[0] in _EXTENDS or _number(rest[0])):
        return False
    if len(rest) > 1 and rest[0] == "and" and (_number(rest[1]) or rest[1] in _EXTENDS):
        return False
    return not any(tuple(rest[: len(u)]) == u for u in _UNIT_WORDS)


def restore(before, after):
    """after with each of before's expansions that after says in words put back as before's written form, in reading
    order. The words must read back to the same values; a changed value stays in words and fails the RewriteCheck."""
    try:
        found = find(before)
    except AmountError:
        return after
    tokens = _tokens(after)
    words = [t for t, _, _ in tokens]
    edits, cursor = [], 0
    for e in found:
        said = [t for t, _, _ in _tokens(e.spoken)]
        for k in range(cursor, len(words) - len(said) + 1):
            if words[k : k + len(said)] == said and _whole(after, tokens, k, k + len(said)):
                edits.append((tokens[k][1], tokens[k + len(said) - 1][2], e.written))
                cursor = k + len(said)
                break
    for start, end, written in reversed(edits):
        after = after[:start] + written + after[end:]
    return after
