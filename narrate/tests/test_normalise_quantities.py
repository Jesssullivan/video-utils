"""Synthetic quantity-preservation fixtures; no private pronunciation table or media."""

import pytest

from narrate.normalise import NormaliseError, Normaliser


def table(written, spoken):
    return {
        "id": "quantity-fixture",
        "language": "en",
        "entries": [{"written": written, "spoken": spoken, "wholeWord": False, "caseSensitive": True}],
    }


@pytest.mark.parametrize(
    "before,after",
    [
        ("-16 LUFS", "16 LUFS"),
        ("16 LUFS", "-16 LUFS"),
        ("+16 LUFS", "16 LUFS"),
        ("−16 LUFS", "16 LUFS"),
        ("- 16 LUFS", "16 LUFS"),
        ("− 16 LUFS", "16 LUFS"),
        ("+\t16 LUFS", "16 LUFS"),
        ("1 ms", "1 s"),
        ("1ms", "1s"),
        ("1 millisecond", "1 second"),
        ("1 ms", "1"),
        ("1", "1 ms"),
        ("16 GiB", "16 GB"),
        ("24000 Hz", "24000 kHz"),
        ("8%", "8"),
        ("8 percent", "8 milliseconds"),
        ("-1.6 LUFS", "-1,6 LUFS"),
        (".5 s", "5 s"),
        ("1e-3 s", "1e3 s"),
        ("1.2.3", "1,2,3"),
        ("-16 LUFS then 16 LUFS", "16 LUFS then -16 LUFS"),
    ],
)
def test_sign_notation_and_recognized_unit_changes_are_refused(before, after):
    normaliser = Normaliser(table(before, after))
    with pytest.raises(NormaliseError, match="numeric literal or recognized unit"):
        normaliser.say(before, "s1")
    assert normaliser.record()["substitutions"] == []


@pytest.mark.parametrize(
    "before,after",
    [
        ("8%", "8 percent"),
        ("-16LUFS", "-16 loudness units relative to full scale"),
        ("-16 LUFS", "-16 loudness units relative to full scale"),
        ("+1.5 ms", "+1.5 milliseconds"),
        ("−1.5 ms", "−1.5 milliseconds"),
        ("1e-3 s", "1e-3 seconds"),
        ("16 GiB", "16 gibibytes"),
        ("24 kHz", "24 kilohertz"),
        ("8% and 16 LUFS", "8 percent and 16 loudness units relative to full scale"),
        ("ABC1201", "A B C 1201"),
        ("ABC8S", "A B C 8 S"),
        ("RKE2", "R K E 2"),
        ("k8s", "K 8 S"),
        ("CC0", "C C 0"),
    ],
)
def test_explicit_aliases_and_identifier_spellouts_are_accepted(before, after):
    normaliser = Normaliser(table(before, after))
    assert normaliser.say(before, "s1") == after
    assert normaliser.record()["substitutions"][0]["count"] == 1


def test_context_protects_a_unit_or_sign_rewritten_without_its_number():
    for before, after, text in [("ms", "s", "Wait 1 ms."), ("-", "", "At -16 LUFS.")]:
        with pytest.raises(NormaliseError, match="numeric literal or recognized unit"):
            Normaliser(table(before, after)).say(text, "s2")


def test_same_guard_applies_to_upstream_and_local_tables():
    with pytest.raises(NormaliseError, match="recognized unit"):
        Normaliser(table("noop", "unused"), upstream=table("ms", "s")).say("1 ms", "s1")
    with pytest.raises(NormaliseError, match="recognized unit"):
        Normaliser(table("milliseconds", "seconds"), upstream=table("ms", "milliseconds")).say("1 ms", "s1")


def test_check_only_call_keeps_record_empty():
    normaliser = Normaliser(table("8%", "8 percent"))
    assert normaliser.say("8%", "s1", record=False) == "8 percent"
    assert normaliser.record()["substitutions"] == []
