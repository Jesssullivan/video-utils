"""Engineering units of the spoken-number claims gate (docs/spec/NARRATED_VIDEO.md, "Claims gate", TIN-7735).

Synthetic sentences only. Each unit must read the same from a symbol, an attached symbol and its spoken words, and
a claim must name the same canonical unit as the spoken text or the number is refused.
"""

import json
from decimal import Decimal

import pytest

from narrate.video import bundle, claims, fixture

# canonical unit: [(voiced text, number)]. Symbols, attached symbols, spelled numbers, singular and plural forms.
SAID = {
    "Pa": [("3 Pa", "3"), ("3Pa", "3"), ("one pascal", "1"), ("two pascals", "2")],
    "kPa": [("12 kPa", "12"), ("one kilopascal", "1"), ("twelve kilopascals", "12")],
    "MPa": [("17.5 MPa", "17.5"), ("17MPa", "17"), ("one megapascal", "1"), ("seventeen megapascals", "17")],
    "GPa": [("200 GPa", "200"), ("one gigapascal", "1"), ("two hundred gigapascals", "200")],
    "N": [("5 N", "5"), ("5N", "5"), ("one newton", "1"), ("five newtons", "5")],
    "kN": [("3 kN", "3"), ("one kilonewton", "1"), ("three kilonewtons", "3")],
    "Nm": [
        ("40 N·m", "40"), ("40 N⋅m", "40"), ("40N·m", "40"), ("40 Nm", "40"), ("one newton metre", "1"),
        ("forty newton metres", "40"), ("forty newton-meters", "40"), ("one newton meter", "1"),
    ],
    "dBA": [
        ("45 dBA", "45"), ("45dBA", "45"), ("forty five decibels A-weighted", "45"),
        ("one decibel A-weighted", "1"), ("45 A-weighted decibels", "45"),
    ],
    "um": [
        ("12 µm", "12"), ("12 μm", "12"), ("12µm", "12"), ("one micrometre", "1"), ("twelve micrometres", "12"),
        ("twelve micrometers", "12"), ("twelve microns", "12"),
    ],
    "us": [("5 µs", "5"), ("5µs", "5"), ("5 μs", "5"), ("five microseconds", "5")],
    "degC": [("20 °C", "20"), ("20°C", "20"), ("twenty degrees celsius", "20")],
    "ohm": [("12 Ω", "12"), ("twelve ohms", "12")],
    "K": [("one kelvin", "1"), ("three hundred kelvins", "300"), ("300 kelvin", "300")],
    "rpm": [
        ("3000 rpm", "3000"), ("3000 RPM", "3000"), ("one revolution per minute", "1"),
        ("three thousand revolutions per minute", "3000"),
    ],
    "ppm": [
        ("400 ppm", "400"), ("400 PPM", "400"), ("one part per million", "1"),
        ("four hundred parts per million", "400"),
    ],
}  # fmt: skip
CASES = [(unit, text, number) for unit, rows in SAID.items() for text, number in rows]


def claim(number, unit, receipt="fixture-receipt"):
    return {"id": "c", "value": {"spoken": "", "number": Decimal(number), "unit": unit}, "receipt": receipt}


@pytest.mark.parametrize(("unit", "text", "number"), CASES)
def test_each_unit_reads_from_its_symbol_and_its_words(unit, text, number):
    found = claims.extract(f"It held {text} in the run.")
    assert [(claims.fmt(m["number"]), m["unit"], m["ambiguous"]) for m in found] == [(number, unit, None)]


@pytest.mark.parametrize(("unit", "text", "number"), CASES)
def test_spoken_and_claimed_units_agree(unit, text, number):
    result = claims.check_segment(f"It held {text}.", ["c"], {"c": claim(number, unit)})
    assert result["status"] == "passed", result
    assert result["mentions"][0]["claim"] == "c"


@pytest.mark.parametrize(
    ("said", "claimed"),
    [
        ("17 MPa", "kPa"), ("17 MPa", "GPa"), ("17 MPa", "Pa"), ("17 kPa", "MPa"), ("17 megapascals", "kPa"),
        ("5 N", "kN"), ("5 kilonewtons", "N"), ("40 N·m", "N"), ("40 newtons", "Nm"), ("45 dBA", "dB"),
        ("45 decibels", "dBA"), ("12 µm", "mm"), ("12 millimetres", "um"), ("5 µs", "ms"), ("5 ms", "us"),
        ("300 kelvin", "degC"), ("20 °C", "K"), ("3000 rpm", ""), ("3000 rpm", "min"), ("400 ppm", "percent"),
        ("4 percent", "ppm"), ("5 kHz", "MHz"), ("5 mA", "A"), ("5 mV", "V"), ("5 mW", "W"), ("2 kg", "g"),
        ("17 MPa", ""), ("17", "MPa"),
    ],
)  # fmt: skip
def test_a_mismatched_unit_is_refused(said, claimed):
    number = claims.extract(said)[0]["number"]
    result = claims.check_segment(f"It held {said}.", ["c"], {"c": claim(number, claimed)})
    assert result["codes"] == ["number_unclaimed"], result


@pytest.mark.parametrize(
    ("singular", "plural", "unit"),
    [
        ("one pascal", "two pascals", "Pa"), ("one kilopascal", "two kilopascals", "kPa"),
        ("one megapascal", "two megapascals", "MPa"), ("one gigapascal", "two gigapascals", "GPa"),
        ("one newton", "two newtons", "N"), ("one kilonewton", "two kilonewtons", "kN"),
        ("one newton metre", "two newton metres", "Nm"), ("one decibel A-weighted", "two decibels A-weighted", "dBA"),
        ("one micrometre", "two micrometres", "um"), ("one micron", "two microns", "um"),
        ("one kelvin", "two kelvins", "K"), ("one revolution per minute", "two revolutions per minute", "rpm"),
        ("one part per million", "two parts per million", "ppm"),
    ],
)  # fmt: skip
def test_singular_and_plural_read_as_one_unit(singular, plural, unit):
    found = claims.extract(f"{singular}, then {plural}")
    assert [(claims.fmt(m["number"]), m["unit"]) for m in found] == [("1", unit), ("2", unit)]


@pytest.mark.parametrize(
    "said",
    ["12 mpa", "12 Mpa", "12 kpa", "12 Gpa", "12 pa", "12 dba", "12 DbA", "12 kn", "12 Kn", "12 Min", "300 K"],
)
def test_a_miscased_symbol_is_not_read(said):
    found = claims.extract(said)
    assert [m["ambiguous"] for m in found] == ["unknown_scale_or_unit"]
    result = claims.check_segment(said, ["c"], {"c": claim(12, "MPa")})
    assert result["codes"] == ["number_ambiguous"]


@pytest.mark.parametrize(("said", "number"), [("a 3.9 GPA", "3.9"), ("5 PA speakers", "5"), ("12 MPA", "12")])
def test_an_all_capital_acronym_stays_a_bare_count(said, number):
    assert [(claims.fmt(m["number"]), m["unit"]) for m in claims.extract(said)] == [(number, "")]


def test_the_new_units_are_canonical():
    new = ("Pa", "kPa", "MPa", "GPa", "N", "kN", "Nm", "dBA", "um", "K", "rpm", "ppm", "N/m", "MPa/s")
    assert all(claims.unit_valid(u) for u in new)
    # A claim names the canonical unit, never a symbol or a miscased form.
    assert not any(claims.unit_valid(u) for u in ("N·m", "µm", "mpa", "MPA", "kpa", "RPM", "°C", "dB(A)"))


def test_a_megapascal_claim_reads_in_a_bundle(tmp_path):
    # The reported case: a claims.json value in MPa was claim_invalid before the gate read pressure units.
    b = fixture.write_bundle(tmp_path / "bundles")
    rows = json.loads((b / "claims.json").read_text())
    rows[2]["value"] = {"spoken": "seventeen point five megapascals", "number": 17.5, "unit": "MPa"}
    (b / "claims.json").write_text(json.dumps(rows, indent=1))
    text = (b / "script.md").read_text()
    assert "four hundred generated files" in text
    (b / "script.md").write_text(text.replace("four hundred generated files", "17.5 MPa of generated files"))
    result = bundle.claims_only(b)
    assert result["ok"], result
    row = [m for m in result["segments"][1]["mentions"] if m["unit"] == "MPa"]
    assert [(m["number"], m["claim"]) for m in row] == [("17.5", "files")]
