import json

import pytest
from conftest import BURST, SILENCES, fake_words

from condense import audio, transcribe
from condense.events import detect, words_from


def near(found, wanted):
    return len(found) == len(wanted) and all(
        a == pytest.approx(x, abs=0.06) and b == pytest.approx(y, abs=0.06)
        for (a, b), (x, y) in zip(found, wanted, strict=True)
    )


def test_silencedetect_finds_every_gap(talk):
    clip = talk.clips[0]
    assert near(audio.silences(talk.f(clip, "16k.wav"), clip["silence_db"], talk.rules["silence_s"]), SILENCES)


def test_rms_track_is_loud_in_bursts_and_quiet_between(talk):
    rms = audio.read_rms(talk.f("talk", "rms.txt"))
    assert rms[20] > -35 and rms[70] > -35 and rms[163] > -35  # 2.0 s, 7.0 s and the burst at 16.3 s
    assert rms[50] < -60 and rms[150] < -60  # 5.0 s and 15.0 s


def test_pauses_are_the_silences_and_fillers_are_the_um_and_the_burst(talk):
    ev = json.loads(talk.f("talk", "events.json").read_text())
    # silences joined with word gaps: the last word of a burst ends 0.1 s early, and no word covers the burst
    assert near(ev["pauses"], [(0.0, 1.2), (3.9, 6.5), (8.9, 9.8), (10.2, 11.1), (13.9, 18.6), (22.0, 24.0)])
    assert [why for _, _, why in ev["fillers"]] == ["filler+unworded", "unworded"]  # the um is also a lone burst
    assert near([f[:2] for f in ev["fillers"]], [(9.8, 10.3), BURST])


def burst_is_unworded(words, pass1=()):
    return [BURST[0], BURST[1], "unworded"] in detect(words, SILENCES, pass1)[0]


def test_a_burst_stays_worded_when_pass_one_heard_a_word_there():
    assert burst_is_unworded(fake_words())
    # pass-1 times sit seconds off, so a pass-1 word within 1.5 s that the DTW pass lacks is proof enough
    assert not burst_is_unworded(fake_words(), [dict(start=17.4, end=17.8, word="consumer")])
    # the DTW pass has "Thanks" within 3 s of the burst, so pass 1 hearing it too proves nothing
    assert burst_is_unworded(fake_words(), [dict(start=17.4, end=17.8, word="Thanks")])


def test_a_dtw_word_up_to_800_ms_early_covers_the_burst():
    def with_word(start, end):
        return sorted([*fake_words(), dict(start=start, end=end, word="is")], key=lambda w: w["start"])

    assert not burst_is_unworded(with_word(15.3, 15.5))  # ends 0.5 s before the burst
    assert burst_is_unworded(with_word(14.6, 15.0))  # ends 1.0 s before it


def test_word_gaps_over_700_ms_are_pauses_without_silencedetect():
    pauses = detect(fake_words(), [])[1]
    assert near(pauses, [(0.0, 1.2), (3.9, 6.5), (8.9, 9.8), (10.2, 11.1), (13.9, 18.6)])


def test_the_first_copy_of_a_repeated_run_is_a_false_start():
    words = [dict(start=i * 0.4, end=i * 0.4 + 0.3, word=w) for i, w in enumerate("so we so we very very go".split())]
    fillers, _ = detect(words, [], keep_repeats=["very"])
    assert fillers == [[0.0, 0.8, "repeat:so we"]]
    assert detect(words, [])[0][1] == [1.6, 2.0, "repeat:very"]


def test_the_phone_rules():
    said = [(1.0, "you"), (1.4, "know"), (1.8, "so"), (2.2, "we"), (6.6, "so"), (7.0, "we"), (7.4, "go")]
    said += [(8.2, "I"), (8.6, "I"), (9.0, "think"), (9.4, "it's"), (9.8, "5"), (10.2, "5"), (449.1, "now")]
    words = [dict(start=t, end=round(t + 0.2, 3), word=w) for t, w in said]
    words[-2]["end"] = 448.4  # "5" ends 0.70 s before "now", a float hair over 0.7
    room, phone = detect(words, []), detect(words, [], phone=True)
    # the room rules: a stall, repeats within 3 s only, digits count, a lead-in pause and every gap over 0.7 s
    assert [why for _, _, why in room[0]] == ["stall", "repeat:i", "repeat:5"]
    assert room[1][0] == [0.0, 1.0] and room[1][-1] == [448.4, 449.1]
    # the phone rules: no stall, a repeat at any distance speeds only its own words, digits are no repeat,
    # no lead-in pause, and gaps are read to 10 ms
    assert phone[0] == [[1.8, 2.4, "repeat:so we"], [8.2, 8.4, "repeat:i"]]
    assert [0.0, 1.0] not in phone[1] and [448.4, 449.1] not in phone[1]


def test_the_phone_rules_trust_the_dtw_onset_and_split_at_spaces():
    def token(text, at, dtw):
        return {"text": text, "offsets": {"from": at, "to": at + 100}, "t_dtw": dtw}

    seg = {"text": " it . random", "offsets": {"from": 1000, "to": 2000}}
    seg["tokens"] = [token(" it", 1000, 90), token(" .", 1100, 110), token("random", 1100, 110)]
    full = {"transcription": [seg]}
    assert [(w["start"], w["word"]) for w in words_from(full, True)] == [(1.0, "it.random")]
    assert [(w["start"], w["word"]) for w in words_from(full, True, phone=True)] == [(0.9, "it"), (1.1, ".random")]


def test_chunks_cut_in_the_longest_silence_near_each_target():
    sil = [(95.0, 96.0), (100.0, 104.0), (210.0, 211.0)]
    assert transcribe.cuts(sil, 300.0, 100) == [(0.0, 102.0), (102.0, 210.5), (210.5, 300.0)]
    assert transcribe.cuts([], 120.0, 100) == [(0.0, 120.0)]


def test_merged_chunks_share_the_clip_clock():
    def chunk():
        token = {"text": " hi", "offsets": {"from": 500, "to": 900}, "t_dtw": 60}
        return {"transcription": [{"text": " hi", "offsets": {"from": 0, "to": 1000}, "tokens": [token]}]}

    second = transcribe.merge([chunk(), chunk()], [0.0, 102.5])["transcription"][1]
    assert second["offsets"] == {"from": 102500, "to": 103500}
    assert second["tokens"][0]["offsets"]["from"] == 103000 and second["tokens"][0]["t_dtw"] == 10310
