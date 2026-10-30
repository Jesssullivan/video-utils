"""WER, the best-of-N loop with seeds, and the not_measured path."""

import pytest

from narrate import qa
from narrate.audio import Pcm

GATES = {"maxChunkWer": 0.1, "minSim": 0.0, "maxTakes": 3, "calibrated": False}


@pytest.mark.parametrize(
    "ref,hyp,value",
    [
        ("the cat sat", "the cat sat", 0.0),
        ("The cat, sat.", "the cat sat", 0.0),
        ("the cat sat", "the cat", 0.3333),
        ("the cat sat", "a cat sat down", 0.6667),
        ("", "", 0.0),
        ("", "noise", 1.0),
        ("version 2.5 now", "version 2.5 now", 0.0),
    ],
)
def test_wer(ref, hyp, value):
    assert qa.wer(ref, hyp) == pytest.approx(value, abs=1e-4)


def run(heard_by_seed, gates=GATES, measured=True):
    seeds = []

    def synth(seed):
        seeds.append(seed)
        return Pcm(16000, None), {"variant": "test"}

    def measure(pcm, text):
        if not measured:
            return {"wer": qa.not_measured("absent"), "sim": qa.not_measured("absent")}
        heard = heard_by_seed[seeds[-1]]
        return {"wer": {"status": "measured", "value": qa.wer(text, heard)}, "sim": qa.not_measured("absent")}

    _, _, record = qa.best_of("one two three four five", synth, measure, gates, 10)
    return seeds, record


def test_a_passing_first_take_stops():
    seeds, record = run({10: "one two three four five"})
    assert seeds == [10] and record["status"] == "passed" and record["kept_take"] == 1


def test_retries_with_the_next_seed_until_a_take_passes():
    seeds, record = run({10: "one", 11: "one two three", 12: "one two three four five"})
    assert seeds == [10, 11, 12]
    assert (record["status"], record["kept_take"], record["seed"]) == ("passed", 3, 12)
    assert [t["passed"] for t in record["takes"]] == [False, False, True]


def test_keeps_the_best_failing_take_and_flags_it():
    seeds, record = run({10: "one", 11: "one two three four", 12: "two"})
    assert seeds == [10, 11, 12]
    assert (record["status"], record["kept_take"], record["flags"]) == ("failed", 2, ["qa_failed"])


def test_max_takes_bounds_the_loop():
    seeds, record = run({10: "x", 11: "y"}, gates=GATES | {"maxTakes": 2})
    assert seeds == [10, 11] and record["status"] == "failed"


def test_not_measured_takes_once_and_never_claims_a_pass():
    seeds, record = run({}, measured=False)
    assert seeds == [10] and record["status"] == "not_measured" and record["takes"][0]["passed"] is None


# Synthetic respellings shaped like a pronunciation table's: the spoken projection is what the engine reads, a
# transcriber writes either form back. Neither correct reading may fail the WER gate.
RESPELL = [("ex oh ex dee", "xoxd"), ("S S O T", "SSOT"), ("M C P", "MCP"), ("koo ber net eez", "Kubernetes")]


@pytest.mark.parametrize(
    "written,spoken,heard",
    [
        ("xoxd-lexical is pinned", "ex oh ex dee-lexical is pinned", "xoxd-lexical is pinned"),
        ("xoxd-lexical is pinned", "ex oh ex dee-lexical is pinned", "ex oh ex dee-lexical is pinned"),
        ("the SSOT lives here", "the S S O T lives here", "the SSOT lives here"),
        ("the SSOT lives here", "the S S O T lives here", "The S S O T lives here."),
        ("MCP server", "M C P server", "MCP server"),
        (
            "the SSOT and MCP on Kubernetes",
            "the S S O T and M C P on koo ber net eez",
            "the SSOT and M C P on Kubernetes",
        ),
    ],
)
def test_a_correct_reading_passes_whichever_form_the_transcript_writes(written, spoken, heard):
    assert qa.chunk_wer(written, spoken, heard, RESPELL) == 0.0


def test_a_misread_respelled_term_still_fails():
    written, spoken = "the SSOT and MCP", "the S S O T and M C P"
    assert qa.chunk_wer(written, spoken, "the SSO and M C P", RESPELL) > GATES["maxChunkWer"]
    assert qa.chunk_wer(written, spoken, "the S S O and MCP", RESPELL) > GATES["maxChunkWer"]
    assert qa.chunk_wer(written, spoken, "the SSOT and MCP", ()) == 0.0
    assert qa.chunk_wer(written, spoken, "the SSOT and M C P", ()) > GATES["maxChunkWer"]


# narrate-wer-2: one normalisation for both sides. The fixture is synthetic: 32 reference words, read back word for
# word, scored 6 errors (0.1875) under narrate-wer-1 because "low-end" and "nine-string" stayed whole (2 errors
# each) and "Hz" did not match "hertz" (1 error each).
LOW_END = (
    "The low-end check reads 32 Hz on the nine-string guitar, and the fan floor sits near 120 Hz. "
    "A tuned take keeps every pick attack and the sustain of each note clear."
)
LOW_END_HEARD = (
    "the low end check reads 32 hertz on the nine string guitar and the fan floor sits near 120 hertz "
    "a tuned take keeps every pick attack and the sustain of each note clear"
)


def test_the_normalisation_version_is_named():
    assert qa.NORMALISATION == "narrate-wer-2"


def test_a_word_for_word_take_with_hyphens_and_hertz_passes():
    assert len(qa.words(LOW_END)) == 34  # the two hyphenated words now score as two words each
    assert qa.chunk_wer(LOW_END, LOW_END, LOW_END_HEARD) == 0.0


@pytest.mark.parametrize(
    "ref,hyp",
    [
        ("a tool-head swap", "a tool head swap"),
        ("a tool–head swap", "a tool head swap"),
        ("32 Hz", "32 hertz"),
        ("32Hz", "thirty two hertz"),
        ("a 2.5 kHz shelf", "a 2.5 kilohertz shelf"),
        ("the Hz axis", "the hertz axis"),
        ("a 10 mm gap", "a 10 millimeter gap"),
        ("a 10 mm gap", "a 10 millimetres gap"),
        ("at 5 V and 20 mA", "at 5 volts and 20 milliamperes"),
        ("at 1 V", "at 1 volt"),
        ("draws 40 µA", "draws 40 microamperes"),
        ("draws 40 uA", "draws 40 microamperes"),
        ("a 3 W amp", "a 3 watt amp"),
        ("a 6 dB cut", "a 6 decibel cut"),
        ("a 6 dB cut", "a 6 decibels cut"),
        ("in 5 ms", "in 5 milliseconds"),
        ("in 5 s", "in 5 seconds"),
        ("in 1 s", "in 1 second"),
        ("at 40 °C", "at 40 degrees celsius"),
        ("at 40°C", "at 40 degrees Celsius"),
        ("a grey cable", "a gray cable"),
        ("the colour and behaviour", "the color and behavior"),
        ("a millimetre off centre", "a millimeter off center"),
        ("normalise and analyse it", "normalize and analyze it"),
        ("the signal was normalised", "the signal was normalized"),
        ("a travelling labelled case", "a traveling labeled case"),
        ("the toolhead moves", "the tool head moves"),
        ("the tool head moves", "the toolhead moves"),
        ("a headboard", "a head board"),
        ("a head board", "a headboard"),
        ("into the room", "in to the room"),
    ],
)
def test_equivalent_forms_score_equal(ref, hyp):
    assert qa.wer(ref, hyp) == 0.0
    assert qa.wer(hyp, ref) == 0.0


@pytest.mark.parametrize(
    "ref,hyp",
    [
        ("Bazel builds the take", "basil builds the take"),  # a misheard name is a substitution
        ("a grey cable", "a green cable"),  # a wrong word
        ("32 Hz", "33 hertz"),  # a wrong number
        ("32 Hz", "32 kilohertz"),  # a wrong unit
        ("5 mA", "5 amperes"),
        ("in 5 ms", "in 5 seconds"),
        ("12 strings", "1 2 strings"),  # digits never join
        ("the MCP server", "the M C P server"),  # spelled letters join only through a pronunciation alias
        ("the toolhead moves", "the tool bed moves"),  # concatenation must match exactly
        ("a headboard", "a head"),
        ("the 1990s", "the 1990 seconds"),  # s written against the digits is not a unit
        ("Apt 3B", "Apt 3 bytes"),  # neither is B
    ],
)
def test_a_real_error_still_counts(ref, hyp):
    assert qa.wer(ref, hyp) > 0.0


def test_a_misheard_name_still_fails_the_gate():
    ref = "Bazel builds the take and Kubernetes runs it"
    heard = "basil builds the take and Kubernetes runs it"
    assert qa.chunk_wer(ref, ref, heard) > GATES["maxChunkWer"]
    assert qa.chunk_wer(ref, ref, "builds the take and Kubernetes runs it") > GATES["maxChunkWer"]


def test_numbers_and_names_are_still_scored():
    assert "32" in qa.words(LOW_END) and "120" in qa.words(LOW_END)
    assert qa.chunk_wer(LOW_END, LOW_END, LOW_END_HEARD.replace("120", "112")) > 0.0
    assert qa.words("Bazel and Kubernetes") == ["bazel", "and", "kubernetes"]


def test_the_gate_limit_is_unchanged():
    # one word wrong in eight is over the 0.1 limit, as it was under narrate-wer-1
    ref = "the low end check reads 32 hertz today"
    assert qa.wer(ref, "the low end check reads 33 hertz today") == 0.125 > GATES["maxChunkWer"]


def test_identifiers_with_digits_keep_their_hyphen():
    assert qa.words("x86-64 and TIN-7088") == ["x86-64", "and", "tin-7088"]
