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
