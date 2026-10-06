#!/usr/bin/env python3
"""Exact frame index <-> display timecode labels (NDF everywhere, DF at 29.97/59.94/119.88).

Pure standard-library arithmetic with no I/O and no float conversions. Labels are
display identifiers only: they never change media time, sample position or the
rational frame period. Contract: docs/spec/EDITOR_MARKER_EXPORT.md and
docs/spec/sprints/EDITOR_EXPORT_S2.md (Apple TN2310 drop-frame semantics).
"""
from __future__ import annotations

from fractions import Fraction
import re

REASONS = frozenset({
    "rate_invalid", "rate_unsupported", "drop_frame_rate_unsupported", "frame_out_of_range",
    "label_malformed", "label_field_out_of_range", "label_dropped_in_drop_frame",
    "separator_mode_mismatch",
})
MAX_NOMINAL = 1000
DROP_FRAME_RATES = (Fraction(30000, 1001), Fraction(60000, 1001), Fraction(120000, 1001))
SECONDS_PER_DAY = 86_400
_RATE_TEXT = re.compile(r"-?[0-9]{1,12}(?:/-?[0-9]{1,12})?")
# ASCII digits only ([0-9], never \d, which also matches other Unicode digits).
_LABEL = re.compile(r"([0-9]{2}):([0-9]{2}):([0-9]{2})([:;])([0-9]+)")


class TimecodeError(ValueError):
    """Typed refusal; ``reason`` is one member of ``REASONS``."""

    def __init__(self, reason, message):
        if reason not in REASONS:
            raise AssertionError(f"Unknown timecode reason: {reason}")
        super().__init__(f"{reason}: {message}")
        self.reason = reason


def parse_rate(value) -> Fraction:
    """Return the exact frame rate as a reduced Fraction or raise TimecodeError.

    Accepted values are integer rates N/1 with 1 <= N <= 1000 and NTSC-family
    rates k*1000/1001 with 1 <= k <= 1000 (e.g. 24000/1001, 30000/1001). The
    NTSC test is exact (rate * 1001 / 1000 is an integer), so a reduced spelling
    such as 1000/143 (= 7000/1001) is the same rate as 7000/1001. Floats, bools,
    zero, negative and non-numeric values are ``rate_invalid``; other positive
    rationals (108930/4549, 24/1001, 2997/100, 1001/1) are ``rate_unsupported``.
    """
    if isinstance(value, bool):
        raise TimecodeError("rate_invalid", "boolean is not a frame rate")
    if isinstance(value, int):
        rate = Fraction(value)
    elif isinstance(value, Fraction):
        rate = value
    elif isinstance(value, str):
        if not _RATE_TEXT.fullmatch(value):
            raise TimecodeError("rate_invalid", "expected an integer or N/D rational string")
        try:
            rate = Fraction(value)
        except (ValueError, ZeroDivisionError) as exc:
            raise TimecodeError("rate_invalid", "zero denominator") from exc
    else:
        raise TimecodeError("rate_invalid", "expected int, Fraction or N/D string; floats are refused")
    if rate <= 0:
        raise TimecodeError("rate_invalid", "rate must be positive")
    if rate.denominator == 1:
        if rate.numerator <= MAX_NOMINAL:
            return rate
        raise TimecodeError("rate_unsupported", f"integer rate above {MAX_NOMINAL}")
    ntsc = rate * 1001 / 1000
    if ntsc.denominator == 1 and 1 <= ntsc.numerator <= MAX_NOMINAL:
        return rate
    raise TimecodeError("rate_unsupported",
                        f"{rate.numerator}/{rate.denominator} is neither N/1 nor N*1000/1001")


class Clock:
    """Validated timecode clock for one exact rate and one DF/NDF mode.

    Construct once and reuse for bulk conversion; the module-level functions build
    a Clock per call. All attributes are integers or the exact rational rate.
    """

    __slots__ = ("rate", "drop_frame", "nominal", "drop", "per_minute", "per_ten_minutes",
                 "per_day", "digits")

    def __init__(self, rate, drop_frame=False):
        if type(drop_frame) is not bool:
            raise TimecodeError("label_malformed", "drop_frame must be a boolean")
        exact = parse_rate(rate)
        if drop_frame and exact not in DROP_FRAME_RATES:
            raise TimecodeError("drop_frame_rate_unsupported",
                                "drop-frame is defined only for 30000/1001, 60000/1001 and 120000/1001")
        nominal = exact.numerator if exact.denominator == 1 else exact.numerator * 1001 // (1000 * exact.denominator)
        self.rate = exact
        self.drop_frame = drop_frame
        self.nominal = nominal
        self.drop = nominal // 15 if drop_frame else 0
        self.per_minute = 60 * nominal - self.drop
        self.per_ten_minutes = 600 * nominal - 9 * self.drop
        self.per_day = 144 * self.per_ten_minutes
        self.digits = max(2, len(str(nominal - 1)))

    def fields(self, frame):
        """(hours, minutes, seconds, frames) for a frame index in [0, per_day)."""
        if type(frame) is not int:
            raise TimecodeError("frame_out_of_range", "frame index must be a Python int")
        if not 0 <= frame < self.per_day:
            raise TimecodeError("frame_out_of_range", "frame outside [0, frames_per_day); no 24 h wrap")
        drop = self.drop
        if drop:
            tens, remainder = divmod(frame, self.per_ten_minutes)
            frame += 9 * drop * tens
            if remainder >= drop:
                frame += drop * ((remainder - drop) // self.per_minute)
        seconds, frames = divmod(frame, self.nominal)
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        return hours, minutes, seconds, frames

    def label(self, frame):
        # Same arithmetic as fields(), inlined because exhaustive 24 h checks call it per frame.
        if type(frame) is not int:
            raise TimecodeError("frame_out_of_range", "frame index must be a Python int")
        if not 0 <= frame < self.per_day:
            raise TimecodeError("frame_out_of_range", "frame outside [0, frames_per_day); no 24 h wrap")
        drop = self.drop
        if drop:
            tens, remainder = divmod(frame, self.per_ten_minutes)
            frame += 9 * drop * tens
            if remainder >= drop:
                frame += drop * ((remainder - drop) // self.per_minute)
        seconds, frames = divmod(frame, self.nominal)
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}{';' if self.drop_frame else ':'}{frames:0{self.digits}d}"

    def frame(self, label):
        if not isinstance(label, str):
            raise TimecodeError("label_malformed", "label must be a string")
        match = _LABEL.fullmatch(label)
        if not match:
            raise TimecodeError("label_malformed", "expected HH:MM:SS:FF or HH:MM:SS;FF with ASCII digits")
        hh, mm, ss, separator, ff = match.groups()
        if len(ff) != self.digits:
            raise TimecodeError("label_malformed", f"field widths must be 2:2:2:{self.digits}")
        if separator != (";" if self.drop_frame else ":"):
            raise TimecodeError("separator_mode_mismatch", "';' marks drop-frame, ':' marks non-drop-frame")
        hours, minutes, seconds, frames = int(hh), int(mm), int(ss), int(ff)
        if hours > 23 or minutes > 59 or seconds > 59 or frames >= self.nominal:
            raise TimecodeError("label_field_out_of_range", "HH 00-23, MM/SS 00-59, FF below nominal rate")
        plain = (hours * 3600 + minutes * 60 + seconds) * self.nominal + frames
        drop = self.drop
        if not drop:
            return plain
        if seconds == 0 and frames < drop and minutes % 10 != 0:
            raise TimecodeError("label_dropped_in_drop_frame", "label skipped by drop-frame counting")
        total_minutes = hours * 60 + minutes
        return plain - drop * (total_minutes - total_minutes // 10)


def nominal_fps(rate) -> int:
    """N for N/1; k for k*1000/1001."""
    return Clock(rate).nominal


def drop_frame_allowed(rate) -> bool:
    return parse_rate(rate) in DROP_FRAME_RATES


def dropped_per_minute(rate) -> int:
    """Labels skipped per non-tenth minute: nominal/15 (2, 4, 8). Drop-frame rates only."""
    return Clock(rate, True).drop


def frame_digits(rate) -> int:
    """Width of the FF field: max(2, len(str(nominal - 1)))."""
    return Clock(rate).digits


def frames_per_day(rate, drop_frame=False) -> int:
    return Clock(rate, drop_frame).per_day


def frame_to_fields(frame, rate, drop_frame=False):
    return Clock(rate, drop_frame).fields(frame)


def frame_to_timecode(frame, rate, drop_frame=False) -> str:
    return Clock(rate, drop_frame).label(frame)


def timecode_to_frame(label, rate, drop_frame=False) -> int:
    return Clock(rate, drop_frame).frame(label)
