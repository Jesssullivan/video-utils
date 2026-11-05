"""Numeric ranges and dollar amounts said in words: synthetic fixtures only, no client text, no engine."""

import random

import pytest

from narrate import amounts, chunker, lexical, qa
from narrate.ir import Segment
from narrate.normalise import NormaliseError, Normaliser, recorded_aliases
from narrate.render import chunk_spoken

EMPTY = {"id": "amounts-fixture", "language": "en", "entries": []}


def said(text):
    return amounts.expand(text)[0]


# -- what is said -------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "written,spoken",
    [
        ("$12,400–$27,000", "twelve thousand four hundred to twenty-seven thousand dollars"),
        ("17–19 Oak Lane", "seventeen to nineteen Oak Lane"),
        ("120–275 h", "one hundred twenty to two hundred seventy-five hours"),
        ("$2,346.08", "two thousand three hundred forty-six dollars and eight cents"),
        ("$700", "seven hundred dollars"),
        ("$1", "one dollar"),
        ("$1.00", "one dollar"),
        ("$1.01", "one dollar and one cent"),
        ("$0.99", "ninety-nine cents"),
        ("$0.01", "one cent"),
        ("$0", "zero dollars"),
        ("$1,000,000", "one million dollars"),
        ("$3,040,506.70", "three million forty thousand five hundred six dollars and seventy cents"),
        ("$4.75–$9.20", "four dollars and seventy-five cents to nine dollars and twenty cents"),
        ("$3.00–$6.00", "three to six dollars"),
        ("$15–40", "fifteen to forty dollars"),
        ("15–$40", "fifteen to forty dollars"),
        ("$600 to $850", "six hundred to eight hundred fifty dollars"),
        ("$600 through $850", "six hundred through eight hundred fifty dollars"),
        ("0–6 dB", "zero to six decibels"),
        ("1.5–2.25 s", "one point five to two point two five seconds"),
        ("0.50–0.75 s", "zero point five zero to zero point seven five seconds"),
        ("3 through 7 min", "three through seven minutes"),
        ("4 ms to 9 ms", "four to nine milliseconds"),
        ("5%–12%", "five to twelve percent"),
        ("5–12%", "five to twelve percent"),
        ("2–3x", "two to three times"),
        ("30–45 seconds", "thirty to forty-five seconds"),
        ("11–13", "eleven to thirteen"),
        ("1,200–1,450", "one thousand two hundred to one thousand four hundred fifty"),
    ],
)
def test_ranges_and_amounts_are_said_in_words(written, spoken):
    assert said(written) == spoken


def test_an_expansion_sits_in_its_sentence():
    assert said("Units 17–19 Oak Lane cost $12,400–$27,000 (about $700 a month).") == (
        "Units seventeen to nineteen Oak Lane cost twelve thousand four hundred to twenty-seven thousand dollars "
        "(about seven hundred dollars a month)."
    )
    assert said("It costs $9.") == "It costs nine dollars."
    assert said("A fee—$40—applies.") == "A fee—forty dollars—applies."


@pytest.mark.parametrize(
    "written",
    [
        # signs: negatives stay as written
        "-$500",
        "−$500",
        "$-500",
        "+$500",
        "-5–10 dB",
        "−5–10 dB",
        "5–-10",
        "5 to -10 dB",
        "-3-5 h",
        # identifiers, dates, times, versions, tickets and chains
        "x86-64",
        "A7_31/0/88",
        "lot 314-422",
        "2026-10-26",
        "2026–10–26",
        "10/26–10/28",
        "9:00–10:30",
        "1–2–3",
        "TIN-7087",
        "ABC-12–14",
        "#17–19",
        "@12–14",
        "v1.2–1.3",
        "1.2.3–4",
        "01–05",
        "1,2–3",
        "item12–14",
        "12–14b",
        # a hyphen-minus, to or through between bare numbers is not a range
        "17-19 Oak Lane",
        "3 to 5",
        "17 through 19 Oak Lane",
        # an em dash or a spaced hyphen-minus is punctuation
        "5—10",
        "5 - 10",
        # descending or equal, or a bare range with an ungrouped integer of four or more digits
        "10–5",
        "5–5",
        "$10–$5",
        "1990–1995",
        "call 555–1234",
        "ISO 9001–2015",
        "RFC 2616–7230",
        "12345–6789",
        # ambiguous unit symbols: a label, a dimension, a byte count
        "Apt 3-4 B",
        "Gates 10–12 B",
        "rooms 2-4 x 8",
        "rooms 2–4 x 8",
        "10-5 dB",
        "3-6 dB",
        # other currency signs and the section sign
        "€5–10",
        "£5–10",
        "¥1000–2000",
        "§5–7",
        "5–10 €",
        "5–10€",
        "50¢",
        "€5",
        "$5-year plan",
        "5–10-year",
        # money the recogniser does not say
        "$5k",
        "$2 million",
        "$1–2 billion",
        "$5 to $7 million",
        "$2.5",
        "$2.505",
        "$5/month",
        "US$5",
        # unit mismatches and pluralising letters against the digits
        "5%–10 dB",
        "5 ms–10 s",
        "$5–10 s",
        "1990–2000s",
        "10–20B",
        # out of range
        "1,000,000,000,000,000–2,000,000,000,000,000",
    ],
)
def test_signed_identifiers_and_ambiguous_forms_are_untouched(written):
    assert said(written) == written
    assert amounts.find(written) == []


def test_en_dash_is_a_range_and_hyphen_minus_needs_a_marker():
    assert said("17–19 Oak Lane") == "seventeen to nineteen Oak Lane"
    assert said("17-19 Oak Lane") == "17-19 Oak Lane"
    assert said("$5-$10") == said("$5–$10") == "five to ten dollars"
    assert said("$5-10") == "five to ten dollars"
    assert said("5-10%") == "five to ten percent"
    assert said("120-275 h") == "one hundred twenty to two hundred seventy-five hours"
    assert said("3–6 dB") == "three to six decibels"  # dB marks an en dash range, not a hyphen-minus one


def test_a_spaced_en_dash_is_a_range():
    assert said("$12,400 – $27,000") == "twelve thousand four hundred to twenty-seven thousand dollars"
    assert said("17 – 19 Oak Lane") == "seventeen to nineteen Oak Lane"
    assert said("17\N{NO-BREAK SPACE}–\N{NO-BREAK SPACE}19") == "seventeen to nineteen"
    assert said("17 –19") == "17 –19"  # one-sided spacing is not taken


def test_grouped_or_marked_four_digit_ranges_are_still_said():
    assert said("1,200–1,450") == "one thousand two hundred to one thousand four hundred fifty"
    assert said("$1000–$2000") == "one thousand to two thousand dollars"
    assert said("1000–2000 h") == "one thousand to two thousand hours"


def test_to_needs_a_dollar_sign_on_both_sides_of_a_money_range():
    assert said("$5 to $10") == "five to ten dollars"
    assert said("$5 to 3 people") == "five dollars to 3 people"


@pytest.mark.parametrize("unit", sorted(lexical.UNITS))
def test_every_shared_unit_after_a_range_reads_back(unit):
    symbol = lexical.UNITS[unit][0]
    # B is never a range's unit (said bytes when written out), and x is one only against the digits.
    written = {"B": "2–3 bytes", "x": "2–3x"}.get(unit, f"2–3 {symbol}")
    (expansion,) = amounts.find(written)
    assert expansion.spoken == f"two to three {amounts.PLURAL[unit]}"
    assert expansion.values == (("2", unit), ("3", unit))
    assert amounts.PLURAL[unit] in lexical.UNITS[unit] and amounts.PLURAL[unit] not in amounts._SYMBOLS


def test_a_written_out_unit_is_kept_and_kb_is_kilobytes():
    assert said("2–3 per cent") == "two to three per cent"
    assert said("2–3 KB") == "two to three kilobytes"
    assert said("2–3 kB") == "two to three kilobytes"


# -- the read-back ------------------------------------------------------------------------------------------------
def test_cardinal_and_parse_cardinal_round_trip():
    rng = random.Random(7087)
    for n in list(range(0, 2100)) + [rng.randrange(amounts.LIMIT) for _ in range(3000)]:
        assert amounts.parse_cardinal(amounts.cardinal(n).replace("-", " ").split()) == n


@pytest.mark.parametrize(
    "words",
    [
        "twenty twenty",
        "one two",
        "hundred",
        "thousand",
        "one thousand thousand",
        "ten hundred",
        "and",
        "one and",
        "seven eleven",
        "zero one",
        "twenty forty",
        "one hundred hundred",
        "fifteen six",
    ],
)
def test_parse_cardinal_refuses_what_cardinal_never_writes(words):
    with pytest.raises(amounts.AmountError):
        amounts.parse_cardinal(words.split())


def test_read_back_of_the_spoken_forms():
    assert amounts.read_back("twelve thousand four hundred to twenty-seven thousand dollars") == (
        "to",
        (("12400.00", "$"), ("27000.00", "$")),
    )
    assert amounts.read_back("two thousand three hundred forty-six dollars and eight cents") == (
        None,
        (("2346.08", "$"),),
    )
    assert amounts.read_back("five to ten loudness units relative to full scale") == (
        "to",
        (("5", "LUFS"), ("10", "LUFS")),
    )
    assert amounts.read_back("one point five through two point two five seconds") == (
        "through",
        (("1.5", "s"), ("2.25", "s")),
    )


@pytest.mark.parametrize(
    "written,wrong",
    [
        ("$12,400–$27,000", "twelve thousand four hundred to twenty-six thousand dollars"),
        ("$2,346.08", "two thousand three hundred forty-six dollars and eighty cents"),
        ("17–19", "seventeen through nineteen"),
        ("120–275 h", "one hundred twenty to two hundred seventy-five minutes"),
        ("1.50–2 s", "one point five to two seconds"),
        ("$700", "seven hundred"),
        ("$700", "seven hundred dollars and"),
    ],
)
def test_the_guard_refuses_a_spoken_form_that_changes_a_value(monkeypatch, written, wrong):
    (good,) = amounts.find(written)
    with pytest.raises(amounts.AmountError):
        amounts.verify(amounts.Expansion(**{**good.__dict__, "spoken": wrong}))
    bad = amounts.Expansion(**{**good.__dict__, "spoken": wrong})
    monkeypatch.setattr(amounts, "_expansion", lambda *_a, **_k: bad)
    with pytest.raises(NormaliseError, match="does not read back to its written value"):
        Normaliser(EMPTY).say(written, "s1")


def test_a_wrong_cardinal_is_caught_by_the_independent_reader(monkeypatch):
    monkeypatch.setattr(amounts, "_below_thousand", lambda n: "seven" if n == 7 else amounts.ONES[min(n, 19)])
    with pytest.raises(NormaliseError):
        Normaliser(EMPTY).say("It costs $27.", "s1")


# -- the normaliser and its manifest record ----------------------------------------------------------------------
def test_the_normaliser_says_and_records_each_expansion():
    normaliser = Normaliser(EMPTY)
    text = "Units 17–19 Oak Lane cost $12,400–$27,000. Units 17–19 Oak Lane again."
    spoken = normaliser.say(text, "s1")
    assert "seventeen to nineteen Oak Lane cost twelve thousand four hundred to twenty-seven thousand dollars" in spoken
    record = normaliser.record()
    assert record["substitutions"] == []
    assert record["expansions"] == [
        {
            "segment": "s1",
            "kind": "money_range",
            "written": "$12,400–$27,000",
            "spoken": "twelve thousand four hundred to twenty-seven thousand dollars",
            "connector": "to",
            "values": [{"value": "12400.00", "unit": "$"}, {"value": "27000.00", "unit": "$"}],
            "count": 1,
        },
        {
            "segment": "s1",
            "kind": "range",
            "written": "17–19",
            "spoken": "seventeen to nineteen",
            "connector": "to",
            "values": [{"value": "17", "unit": None}, {"value": "19", "unit": None}],
            "count": 2,
        },
    ]


def test_a_check_only_call_records_nothing_and_tables_still_run():
    table = {
        "id": "amounts-fixture",
        "language": "en",
        "entries": [{"written": "SSOT", "spoken": "S S O T", "wholeWord": True, "caseSensitive": True}],
    }
    normaliser = Normaliser(table, upstream=EMPTY | {"id": "upstream-fixture"})
    assert normaliser.say("The SSOT says $700.", "s1", record=False) == "The S S O T says seven hundred dollars."
    record = normaliser.record()
    assert record["expansions"] == [] and "expansions" not in record["upstream"]
    normaliser.say("The SSOT says $700.", "s1")
    assert [e["written"] for e in normaliser.record()["expansions"]] == ["$700"]
    assert normaliser.record()["upstream"]["substitutions"] == []


def _table(*pairs):
    return {
        "id": "amounts-fixture",
        "language": "en",
        "entries": [{"written": w, "spoken": p, "wholeWord": True, "caseSensitive": False} for w, p in pairs],
    }


@pytest.mark.parametrize("upstream", [False, True])
def test_a_table_entry_never_edits_the_words_of_an_expansion(upstream):
    table = _table(("eight", "nine"), ("dollars", "euros"), ("nineteen", "twenty"))
    normaliser = Normaliser(EMPTY, upstream=table) if upstream else Normaliser(table)
    text = "Pay $1.08 or $5 for units 17–19, eight dollars in all."
    spoken = normaliser.say(text, "s1")
    assert spoken == (
        "Pay one dollar and eight cents or five dollars for units seventeen to nineteen, nine euros in all."
    )
    record = normaliser.record()
    for expansion in record["expansions"]:
        assert expansion["spoken"] in spoken
        assert amounts.read_back(expansion["spoken"])[1] == tuple((v["value"], v["unit"]) for v in expansion["values"])


@pytest.mark.parametrize("upstream", [False, True])
def test_a_table_entry_keyed_on_the_digits_keeps_its_span_written(upstream):
    table = _table(("17–19", "17 through 19"), ("1990–1995", "1990 to 1995"))
    normaliser = Normaliser(EMPTY, upstream=table) if upstream else Normaliser(table)
    spoken = normaliser.say("Units 17–19 and 21–23, from 1990–1995.", "s1")
    assert spoken == "Units 17 through 19 and twenty-one to twenty-three, from 1990 to 1995."
    record = normaliser.record()
    assert [e["written"] for e in record["expansions"]] == ["21–23"]
    layer = record["upstream"] if upstream else record
    assert sorted(s["written"] for s in layer["substitutions"]) == ["17–19", "1990–1995"]


def test_a_private_use_placeholder_in_the_script_is_refused():
    with pytest.raises(NormaliseError, match="private-use"):
        Normaliser(EMPTY).say("Pay $5 \U000f0000.", "s1")


def test_a_table_entry_still_cannot_turn_a_hyphen_into_to():
    table = {
        "id": "amounts-fixture",
        "language": "en",
        "entries": [{"written": "3-5", "spoken": "3 to 5", "wholeWord": False, "caseSensitive": True}],
    }
    with pytest.raises(NormaliseError, match="numeric literal"):
        Normaliser(table).say("3-5", "s1")


def test_the_aliases_map_a_spoken_range_back_to_its_written_form():
    normaliser = Normaliser(EMPTY)
    assert ("seventeen to nineteen", "17–19") in normaliser.aliases("Units 17–19 Oak Lane.", "s1")
    normaliser.say("Units 17–19 Oak Lane.", "s1")
    assert recorded_aliases(normaliser.record(), "s1") == [("seventeen to nineteen", "17–19")]
    assert recorded_aliases(normaliser.record(), "s2") == []


# -- the chunker --------------------------------------------------------------------------------------------------
RANGES = ["$12,400 to $27,000", "$4.75–$9.20", "17–19", "120–275 h", "4 ms to 9 ms", "$600 through $850", "$2,346.08"]


@pytest.mark.parametrize("span", RANGES)
def test_the_chunker_never_splits_an_expanded_range(span):
    text = ("word " * 9) + span + (" word" * 20)
    for limit in range(20, 80, 3):
        out = chunker.chunk_segment(Segment(id="s", text=text), limit)
        assert sum(span in c.text for c in out) == 1, (limit, [c.text for c in out])
        pieces = chunker.pack_words(text, lambda t, n=limit: len(t) <= n)
        assert sum(span in p for p, _ in pieces) == 1, (limit, pieces)


def test_chunk_spoken_keeps_a_range_in_one_chunk_when_its_spoken_form_runs_long():
    span = "$3,040,506.70–$7,080,910.30"
    segment = Segment(id="s", text=f"The budget is {span} for the year, give or take.")
    pairs = chunk_spoken(segment, 60, Normaliser(EMPTY))
    assert sum(span in c.text for c, _ in pairs) == 1
    (chunk, spoken) = next((c, s) for c, s in pairs if span in c.text)
    assert "three million forty thousand five hundred six dollars and seventy cents to seven million" in spoken


# -- the RewriteCheck ---------------------------------------------------------------------------------------------
ORIGINAL = "Units 17–19 Oak Lane cost $12,400–$27,000, or $2,346.08 a month, over 120–275 h."


@pytest.mark.parametrize(
    "rewrite",
    [
        ORIGINAL,
        "Units seventeen to nineteen Oak Lane cost $12,400–$27,000, or $2,346.08 a month, over 120–275 h.",
        "Units seventeen to nineteen Oak Lane cost twelve thousand four hundred to twenty-seven thousand dollars, "
        "or two thousand three hundred forty-six dollars and eight cents a month, over one hundred twenty to two "
        "hundred seventy-five hours.",
        "Units Seventeen to Nineteen on Oak Lane cost $12,400–$27,000, or $2,346.08 monthly, over 120–275 h.",
        "Units 17–19 Oak Lane cost twelve thousand four hundred to twenty seven thousand dollars, or $2,346.08 a "
        "month, over 120–275 h.",
    ],
)
def test_the_rewrite_check_accepts_a_value_preserving_expansion(rewrite):
    assert lexical.rewrite_check(ORIGINAL, rewrite) == []


@pytest.mark.parametrize(
    "rewrite",
    [
        "Units eighteen to nineteen Oak Lane cost $12,400–$27,000, or $2,346.08 a month, over 120–275 h.",
        "Units 17–19 Oak Lane cost twelve thousand four hundred to twenty-six thousand dollars, or $2,346.08 a "
        "month, over 120–275 h.",
        "Units 17–19 Oak Lane cost $12,400–$27,000, or two thousand three hundred forty-six dollars a month, "
        "over 120–275 h.",
        "Units 17–19 Oak Lane cost $12,400–$27,000, or $2,346.08 a month, over one hundred twenty to two hundred "
        "seventy-five minutes.",
        "Units 17–19 Oak Lane cost $12400–$27000, or $2,346.08 a month, over 120–275 h.",
        "Units 17–19 Oak Lane cost $2,346.08 a month, or $12,400–$27,000, over 120–275 h.",
    ],
)
def test_the_rewrite_check_refuses_a_changed_value(rewrite):
    assert lexical.rewrite_check(ORIGINAL, rewrite)


@pytest.mark.parametrize(
    "before,after",
    [
        ("Pay $5–$10.", "Pay five to ten dollars and fifty cents."),
        ("Units 17–19.", "Units seventeen to nineteen hundred."),
        ("Pay $700.", "Pay seven hundred dollars and ninety-nine cents."),
        ("Pay $5.", "Pay minus five dollars."),
        ("Pay $5.", "Pay negative five dollars."),
        ("Pay $5.", "Pay -five dollars."),
        ("Pay $5.", "Pay plus five dollars."),
        ("Units 17–19.", "Units seventeen to nineteen percent."),
        ("Units 17–19.", "Units seventeen to nineteen point five."),
        ("Units 17–19.", "Units seventeen to nineteen thousand."),
        ("Pay $5.", "Pay five dollars fifty."),
        ("Pay $5.", "Pay one hundred five dollars."),
        ("Pay $5.", "Pay a thousand and five dollars."),
        ("Pay $7.", "Pay seven dollars and 5 cents."),
    ],
)
def test_the_rewrite_check_refuses_words_that_extend_or_sign_the_value(before, after):
    assert lexical.rewrite_check(before, after)


@pytest.mark.parametrize(
    "before,after",
    [
        ("It is $5 and more.", "It is five dollars and more."),
        ("Pay $700 per month.", "Pay seven hundred dollars per month."),
        ("Pay $5, then $7.", "Pay five dollars, then seven dollars."),
    ],
)
def test_the_rewrite_check_accepts_a_whole_phrase_followed_by_ordinary_words(before, after):
    assert lexical.rewrite_check(before, after) == []


def test_a_rewrite_that_spells_an_unrecognised_number_is_still_refused():
    assert lexical.rewrite_check("Pick 3 to 5 of them.", "Pick three to five of them.")
    assert lexical.rewrite_check("Lot 314-422 is here.", "Lot three hundred fourteen to four hundred twenty-two.")


# -- WER ----------------------------------------------------------------------------------------------------------
WRITTEN = "Units 17–19 Oak Lane cost $12,400–$27,000, or $2,346.08 a month."


@pytest.mark.parametrize(
    "heard",
    [
        "Units seventeen to nineteen Oak Lane cost twelve thousand four hundred to twenty-seven thousand dollars, "
        "or two thousand three hundred forty-six dollars and eight cents a month.",
        "Units 17 to 19 Oak Lane cost $12,400 to $27,000, or $2,346.08 a month.",
        "Units 17-19 Oak Lane cost $12,400-$27,000, or $2,346.08 a month.",
        "Units 17–19 Oak Lane cost $12,400–$27,000, or $2,346.08 a month.",
        "Units 17 to 19 Oak Lane cost 12,400 to 27,000 dollars, or 2,346 dollars and 8 cents a month.",
        "Units seventeen to nineteen Oak Lane cost $12,400 to $27,000, or $2,346.08 a month.",
    ],
)
def test_a_correct_reading_scores_zero_whether_whisper_writes_numerals_or_words(heard):
    normaliser = Normaliser(EMPTY)
    spoken = normaliser.say(WRITTEN, "s1")
    assert qa.chunk_wer(WRITTEN, spoken, heard, normaliser.aliases(WRITTEN, "s1")) == 0.0
    assert qa.chunk_wer(WRITTEN, spoken, heard, recorded_aliases(normaliser.record(), "s1")) == 0.0


@pytest.mark.parametrize(
    "heard",
    [
        "Units 17 to 18 Oak Lane cost $12,400 to $27,000, or $2,346.08 a month.",
        "Units seventeen to nineteen Oak Lane cost twelve thousand four hundred to twenty-six thousand dollars, "
        "or two thousand three hundred forty-six dollars and eight cents a month.",
        "Units 17 to 19 Oak Lane cost $12,400 to $27,000, or $2,346.80 a month.",
        "Units 17 Oak Lane cost $27,000, or $2,346.08 a month.",
    ],
)
def test_a_misread_value_still_fails_the_gate(heard):
    normaliser = Normaliser(EMPTY)
    spoken = normaliser.say(WRITTEN, "s1")
    assert qa.chunk_wer(WRITTEN, spoken, heard, normaliser.aliases(WRITTEN, "s1")) > 0.0


def test_say_for_a_transcript_takes_bare_hyphen_and_to_ranges():
    assert amounts.say("17-19 Oak Lane") == "seventeen to nineteen Oak Lane"
    assert amounts.say("$5 to 10") == "five to ten dollars"
    assert amounts.say("x86-64") == "x86-64"


# -- end to end with the fake engine ------------------------------------------------------------------------------
@pytest.mark.usefixtures("ffmpeg")
@pytest.mark.parametrize(
    "heard",
    [
        "Units 17 to 19 Oak Lane cost $12,400 to $27,000, or $2,346.08 a month.",
        "Units seventeen to nineteen Oak Lane cost twelve thousand four hundred to twenty-seven thousand dollars, "
        "or two thousand three hundred forty-six dollars and eight cents a month.",
    ],
)
def test_a_render_says_ranges_records_them_and_passes_a_correct_reading(workspace, heard):
    from narrate import render, verify
    from narrate.config import Config

    workspace.use_narration()
    workspace.job["gates"]["maxChunkWer"] = 0.0
    cfg = Config(workspace.write(WRITTEN + "\n", "PlainText"))
    final, manifest = render.render(cfg, transcriber=lambda pcm, text: heard)
    assert verify.verify(final)["ok"]
    (chunk,) = manifest["chunks"]
    assert chunk["written"] == WRITTEN
    assert chunk["spoken"] == (
        "Units seventeen to nineteen Oak Lane cost twelve thousand four hundred to twenty-seven thousand dollars, "
        "or two thousand three hundred forty-six dollars and eight cents a month."
    )
    assert chunk["qa"]["status"] == "passed" and "qa_failed" not in manifest["flags"]
    expansions = manifest["pronunciation"]["expansions"]
    assert [(e["written"], e["kind"], e["count"]) for e in expansions] == [
        ("$12,400–$27,000", "money_range", 1),
        ("$2,346.08", "money", 1),
        ("17–19", "range", 1),
    ]
    assert "17–19" in (final / "narration.srt").read_text()
    aliases = recorded_aliases(manifest["pronunciation"], chunk["segment"])
    assert qa.chunk_wer(chunk["written"], chunk["spoken"], heard, aliases) == 0.0


@pytest.mark.usefixtures("ffmpeg")
def test_a_render_accepts_a_rewrite_that_says_the_range_and_refuses_one_that_changes_it(workspace):
    from narrate import render
    from narrate.config import Config

    cfg = Config(workspace.write("Units 17–19 Oak Lane cost $700.\n", "PlainText"))
    bad = workspace.base / "bad.txt"
    bad.write_text("Units seventeen to eighteen Oak Lane cost $700.\n")
    with pytest.raises(lexical.LexicalError, match="rewrite_refused"):
        render.render(cfg, rewrite=bad)
    ok = workspace.base / "ok.txt"
    ok.write_text("Units seventeen to nineteen on Oak Lane cost seven hundred dollars.\n")
    _, manifest = render.render(cfg, rewrite=ok)
    assert manifest["input"]["rewrite"]["status"] == "accepted"
    assert manifest["chunks"][0]["spoken"] == "Units seventeen to nineteen on Oak Lane cost seven hundred dollars."
    assert manifest["pronunciation"]["expansions"] == []
