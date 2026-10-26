"""A voice's tempo (Voice.dhall `tempo`): a pitch-preserving tempo change applied to every take right after the
engine returns it, before WER and SIM QA and before the timing fit.

The fit's own speed knob and atempo (within fitMaxStretch) work on top of the changed take, so a voice at 1.1 whose
segment still runs over its target is fitted from the faster take. None speaks at 1.0 and calls no FFmpeg. A value
outside audio.TEMPO_RANGE is refused before any audio exists (voice_tempo_invalid). Operator ruling 2026-10-26: a
persona voice may be spoken faster than the engine speaks it.
"""

from pathlib import Path

from . import audio
from .policy import Refused


def voice_tempo(voice):
    """The voice's tempo as a float, 1.0 when it has none. Raises Refused("voice_tempo_invalid") out of range."""
    value = voice.get("tempo")
    if value is None:
        return 1.0
    low, high = audio.TEMPO_RANGE
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
        raise Refused("voice_tempo_invalid", f"voice {voice['id']} tempo {value!r}: from {low} to {high}")
    return float(value)


def check_voices(voices):
    """Refuse, before any audio, a voice whose tempo is out of range."""
    for voice in voices:
        voice_tempo(voice)


def apply_tempo(pcm, voice, facts, work):
    """(take at the voice's tempo, facts with tempo and pre_tempo_seconds). A tempo of 1.0 returns pcm itself."""
    tempo = voice_tempo(voice)
    facts = {**facts, "tempo": tempo, "pre_tempo_seconds": round(pcm.seconds, 4)}
    if tempo == 1.0:
        return pcm, facts
    source, target = pcm.write(Path(work) / "tempo.in.wav"), Path(work) / "tempo.out.wav"
    audio.time_stretch(source, target, tempo)
    return audio.read(target), facts
