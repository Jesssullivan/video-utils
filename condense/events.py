"""Words, fillers, pauses and unworded bursts for one clip.

Reads the whisper JSON. Writes <clip>.silence.log, <clip>.rms.txt, <clip>.words.json and <clip>.events.json.

Fillers are: the filler lexicon (um, uh, er, hmm ...), "you know" and "I mean" stalls, the first copy of an
immediately repeated run of 1 to 5 words, and unworded bursts.
An unworded burst is 0.15 to 1.5 s of sound between two silences that no transcribed word covers.
Pauses are the silencedetect intervals joined with every gap over 0.7 s between two words.
"""

import json
import re

from . import audio

FILL = {"um", "uh", "er", "erm", "ah", "hmm", "hm", "mm", "mhm", "umm", "uhm", "uh-huh"}
FILL_RE = re.compile(r"^(u+h*m+|u+h+|e+r+m*|a+h+|h+m+|m+h*m+)$")
STALLS = {("you", "know"), ("i", "mean")}
SOFT = {"so", "ok", "okay"}  # too common to prove that pass 1 heard a word the DTW pass lacks


def norm(word):
    return re.sub(r"[^a-z0-9'-]", "", word.lower())  # a lone "--" stays a word: it breaks a repeat


def is_filler(word):
    return norm(word) in FILL or bool(FILL_RE.match(norm(word)))


def words_from(full, use_dtw, phone=False):
    """[{start, end, word}] from whisper full JSON. Starts are DTW times when asked for and present.

    A start never sits before its segment's start, and a lone punctuation token joins the word before it.
    The phone rules trust the DTW onset alone and start a new word at every leading space.
    """
    out = []
    for seg in full["transcription"]:
        if seg["text"].strip().startswith("["):
            continue
        s0, s1 = seg["offsets"]["from"] / 1000, seg["offsets"]["to"] / 1000
        cur = None
        for t in seg["tokens"]:
            txt = t["text"]
            if txt.startswith("[_") or not txt:
                continue
            start = t["t_dtw"] / 100 if use_dtw and t.get("t_dtw", -1) >= 0 else t["offsets"]["from"] / 1000
            dur = (t["offsets"]["to"] - t["offsets"]["from"]) / 1000
            stray = cur and not norm(txt) and not txt.strip().isalnum() and not phone
            if (txt.startswith(" ") or cur is None) and not stray:
                cur = {"start": start if phone else max(start, s0), "word": txt.strip(), "dur": dur, "seg_end": s1}
                out.append(cur)
            else:  # a word piece, or punctuation that belongs to the word before it
                cur["word"] += txt.strip() if txt.startswith(" ") else txt
                cur["dur"] += dur
    out = [w for w in out if norm(w["word"])]
    for prev, w in zip(out, out[1:], strict=False):  # starts never run backwards
        w["start"] = max(w["start"], prev["start"])
    for i, w in enumerate(out):  # a word ends by the next start and by its segment's end
        nxt = out[i + 1]["start"] if i + 1 < len(out) else w["seg_end"]
        w["end"] = min(nxt, w["seg_end"], w["start"] + max(w["dur"], 0.12))
        if w["end"] <= w["start"]:
            w["end"] = w["start"] + 0.05
    return [{"start": round(w["start"], 3), "end": round(w["end"], 3), "word": w["word"]} for w in out]


def build_words(dtw, pass1, sil, add_fillers=False):
    """DTW words. With add_fillers, pass-1 fillers that no DTW word covers join them: whisper drops fillers per run."""
    words = list(dtw)
    if add_fillers:
        for a in pass1:
            if is_filler(a["word"]) and not any(w["start"] < a["end"] and a["start"] < w["end"] for w in dtw):
                words.append(dict(a))
    words.sort(key=lambda w: w["start"])
    for w in words:  # a word never runs into a detected silence; a filler lasts at most 1.2 s
        for a, _ in sil:
            if w["start"] + 0.1 < a < w["end"]:
                w["end"] = round(a, 3)
        if is_filler(w["word"]):
            w["end"] = min(w["end"], round(w["start"] + 1.2, 3))
    return words


def voiced_ends(words, rms, voiced_db):
    """End each word where its sound stops: the voiced run after its start, 200 ms dips allowed.

    For rooms too noisy for silencedetect, where nothing else caps a word's end.
    """
    for i, w in enumerate(words):
        nxt = max(words[i + 1]["start"] if i + 1 < len(words) else w["end"], w["start"] + 0.1)
        f = last = int(w["start"] * 10)
        quiet = 0
        while f / 10 < nxt and quiet <= 2:
            if rms.get(f, -99.0) > voiced_db:
                last, quiet = f, 0
            else:
                quiet += 1
            f += 1
        w["end"] = round(min(nxt, max(w["start"] + 0.1, (last + 1) / 10)), 3)


def detect(words, sil, pass1=(), keep_repeats=(), word_gap_s=0.7, phone=False):
    """Return (fillers [[start, end, why]], pauses [[start, end]]).

    phone: the rules the phone recording was cut with. No stalls. A repeat is 1 to 3 words, compared with its
    fillers in and its digits out, at any distance. Only the first copy's own words are sped. Gaps are read
    to 10 ms, and the silence before the first word is not a pause.
    """
    n = [norm(w["word"]) for w in words]
    fill = [(w["start"], w["end"], "filler") for w in words if is_filler(w["word"])]
    for i in range(len(n) - 1):
        if (n[i], n[i + 1]) in STALLS and not phone:
            fill.append((words[i]["start"], words[i + 1]["end"], "stall"))
    i = 0
    while i < len(n):  # a run of 1 to 5 words said twice in a row: the first copy is a false start
        hit = 0
        for k in range(3 if phone else 5, 0, -1):
            a, b = n[i : i + k], n[i + k : i + 2 * k]
            if phone:
                a, b = [re.sub("[^a-z']", "", x) for x in a], [re.sub("[^a-z']", "", x) for x in b]
                a = a if all(a) else []
            else:
                a, b = [x for x in a if x not in FILL], [x for x in b if x not in FILL]
            emphasis = k == 1 and a and a[0] in keep_repeats
            if len(n[i : i + 2 * k]) == 2 * k and a and a == b and not emphasis:
                if words[i + k]["start"] - words[i + k - 1]["end"] < 3 or phone:
                    end = words[i + k - 1]["end"] if phone else words[i + k]["start"]
                    fill.append((words[i]["start"], end, "repeat:" + " ".join(n[i : i + k])))
                    hit = k
                    break
        i += hit or 1

    def gap(a, b):
        return round(b["start"] - a["end"], 2) if phone else b["start"] - a["end"]

    gaps = [(a["end"], b["start"]) for a, b in zip(words, words[1:], strict=False) if gap(a, b) > word_gap_s]
    if words and words[0]["start"] > word_gap_s and not phone:
        gaps.insert(0, (0.0, words[0]["start"]))
    pauses = []
    for s, e in sorted(list(sil) + gaps):
        if pauses and s <= pauses[-1][1]:
            pauses[-1][1] = max(pauses[-1][1], e)
        else:
            pauses.append([s, e])

    # Unworded bursts. Two cross-checks keep real words out of them:
    #   DTW starts can run 0.6 s early, so a word that ends up to 0.8 s before the burst still covers it.
    #   The DTW pass drops words pass 1 heard. Pass-1 times can sit 3 s off, so the burst stays worded when
    #   pass 1 has a word within 1.5 s of it that the DTW pass lacks within 3 s.
    lex = [w for w in words if not is_filler(w["word"])]
    heard = [w for w in pass1 if not is_filler(w["word"]) and norm(w["word"]) not in SOFT]

    def pass1_word(b, c):
        near = {k for w, k in zip(words, n, strict=True) if b - 3 < w["start"] < c + 3}
        return any(norm(w["word"]) not in near for w in heard if b - 1.5 < w["start"] < c + 1.5)

    for (_, b), (c, _) in zip(sil, sil[1:], strict=False):
        covered = any(w["start"] < c and b - 0.8 < w["end"] for w in lex)
        if 0.15 <= c - b <= 1.5 and words and b > words[0]["start"] and not covered and not pass1_word(b, c):
            fill.append((b, c, "unworded"))

    merged = []
    for s, e, why in sorted(fill):
        if merged and s <= merged[-1][1] + 0.05:
            merged[-1][1] = max(merged[-1][1], e)
            merged[-1][2] += "+" + why
        else:
            merged.append([s, e, why])
    return [[round(s, 3), round(e, 3), why] for s, e, why in merged], [[round(s, 3), round(e, 3)] for s, e in pauses]


def run(cfg, clip):
    wav = cfg.f(clip, "16k.wav")
    sil = audio.silences(wav, clip["silence_db"], cfg.rules["silence_s"], cfg.f(clip, "silence.log"))
    audio.write_rms(wav, cfg.f(clip, "rms.txt"))
    p1 = cfg.f(clip, "pass1.json")
    pass1 = words_from(json.loads(p1.read_text()), False) if p1.exists() else []
    phone = clip["detect"] == "phone"
    dtw = words_from(json.loads(cfg.f(clip, "dtw.json").read_text()), True, phone)
    words = build_words(dtw, pass1, sil, clip["pass1_fillers"])
    if phone:
        voiced_ends(words, audio.read_rms(cfg.f(clip, "rms.txt")), clip["voiced_db"])
    fillers, pauses = detect(words, sil, pass1, clip["keep_repeats"], cfg.rules["word_gap_s"], phone)
    cfg.f(clip, "words.json").write_text(json.dumps(words, indent=0))
    cfg.f(clip, "events.json").write_text(json.dumps({"fillers": fillers, "pauses": pauses}, indent=1))
    kinds = {}
    for _, _, why in fillers:
        for k in why.split("+"):
            kinds[k.split(":")[0]] = kinds.get(k.split(":")[0], 0) + 1
    print(
        f"{clip['name']}: {len(words)} words, {len(sil)} silences, {len(pauses)} pauses, {len(fillers)} fillers {kinds}"
    )
