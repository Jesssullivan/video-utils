"""Property tests for scripts/timecode.py (S2 editor_export lane, TIN-5606).

Exhaustive 24 h checks compare the closed-form conversion with an independent
label odometer that increments HH:MM:SS;FF and skips drop-frame labels. These
are arithmetic/serialization checks only; they say nothing about how a host
editor displays or conforms a clip.
"""
from fractions import Fraction
import importlib.util
from pathlib import Path
import random
import unittest

SPEC = importlib.util.spec_from_file_location(
    "timecode", Path(__file__).resolve().parents[1] / "scripts/timecode.py")
tc = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tc)

SEED = 20261006
# rate: (nominal labels per second, labels skipped per non-tenth minute, frames per 24 h)
DF_RATES = {"30000/1001": (30, 2, 2_589_408), "60000/1001": (60, 4, 5_178_816), "120000/1001": (120, 8, 10_357_632)}
NDF_EXHAUSTIVE = {"24/1": (24, 0, 2_073_600), "30000/1001": (30, 0, 2_592_000)}


def odometer_hours(nominal, skip, separator):
    """Yield each hour's displayed labels in order, built by counting HH:MM:SS(;|:)FF.

    Independent of timecode.Clock: it only increments label fields and omits the
    first ``skip`` frame labels at second 00 of every minute not divisible by 10.
    """
    digits = max(2, len(str(nominal - 1)))
    frame_text = [f"{f:0{digits}d}" for f in range(nominal)]
    for hours in range(24):
        labels = []
        for minutes in range(60):
            first = skip if (skip and minutes % 10 != 0) else 0
            for seconds in range(60):
                prefix = f"{hours:02d}:{minutes:02d}:{seconds:02d}{separator}"
                labels.extend([prefix + text for text in (frame_text[first:] if seconds == 0 else frame_text)])
        yield labels


class TimecodeTests(unittest.TestCase):
    def exhaustive(self, rate, drop_frame, nominal, skip, expected_count):
        """Closed form == odometer label, parse(label) == frame, strictly increasing and unique, per hour."""
        clock = tc.Clock(rate, drop_frame)
        self.assertEqual((clock.nominal, clock.drop, clock.per_day), (nominal, skip, expected_count))
        label, parse = clock.label, clock.frame
        frame, previous = 0, ""
        for hour, reference in enumerate(odometer_hours(nominal, skip, ";" if drop_frame else ":")):
            frames = range(frame, frame + len(reference))
            closed = list(map(label, frames))
            if closed != reference:
                index = next(i for i, (a, b) in enumerate(zip(closed, reference)) if a != b)
                self.fail(f"{rate} drop={drop_frame} frame {frame + index}: {closed[index]} != {reference[index]}")
            if list(map(parse, closed)) != list(frames):
                self.fail(f"{rate} drop={drop_frame}: label parse is not the inverse in hour {hour}")
            # Fixed-width labels: lexicographic order is (h, m, s, f) order.
            if not previous < closed[0] or closed != sorted(closed) or len(set(closed)) != len(closed):
                self.fail(f"{rate} drop={drop_frame}: labels not strictly increasing in hour {hour}")
            previous = closed[-1]
            frame += len(reference)
        self.assertEqual(frame, expected_count)
        for beyond in (expected_count, -1):
            with self.assertRaises(tc.TimecodeError) as caught:
                clock.label(beyond)
            self.assertEqual(caught.exception.reason, "frame_out_of_range")
        return frame

    def test_exhaustive_drop_frame_24h_bijective_monotonic(self):
        total = 0
        for rate, (nominal, skip, per_day) in DF_RATES.items():
            with self.subTest(rate=rate):
                total += self.exhaustive(rate, True, nominal, skip, per_day)
        self.assertEqual(total, 18_125_856)

    def test_exhaustive_non_drop_frame_24h(self):
        total = 0
        for rate, (nominal, skip, per_day) in NDF_EXHAUSTIVE.items():
            with self.subTest(rate=rate):
                total += self.exhaustive(rate, False, nominal, skip, per_day)
        self.assertEqual(total, 4_665_600)

    def test_drop_frame_skips_k_labels_except_tens_minutes(self):
        for rate, (_, k, _) in DF_RATES.items():
            clock = tc.Clock(rate, True)
            self.assertEqual(tc.dropped_per_minute(rate), k)
            skipped_minutes = tens_minutes = 0
            for minute_index in range(1440):
                hours, minutes = divmod(minute_index, 60)
                prefix = f"{hours:02d}:{minutes:02d}:00;"
                labels = [prefix + f"{f:0{clock.digits}d}" for f in range(k + 1)]
                first_label = labels[0] if minutes % 10 == 0 else labels[k]
                first = clock.frame(first_label)
                if minute_index + 1 < 1440:
                    nh, nm = divmod(minute_index + 1, 60)
                    next_label = f"{nh:02d}:{nm:02d}:00;" + f"{(0 if nm % 10 == 0 else k):0{clock.digits}d}"
                    length = clock.frame(next_label) - first
                else:
                    length = clock.per_day - first
                if minutes % 10 == 0:
                    tens_minutes += 1
                    self.assertEqual([clock.frame(text) for text in labels[:k]], list(range(first, first + k)))
                    self.assertEqual(length, 60 * clock.nominal)
                else:
                    skipped_minutes += 1
                    for text in labels[:k]:
                        with self.assertRaises(tc.TimecodeError) as caught:
                            clock.frame(text)
                        self.assertEqual(caught.exception.reason, "label_dropped_in_drop_frame")
                    self.assertEqual(length, 60 * clock.nominal - k)
                    # The previous frame is the last label of the prior minute.
                    self.assertTrue(clock.label(first - 1).endswith(f"59;{clock.nominal - 1:0{clock.digits}d}"))
            self.assertEqual((skipped_minutes, tens_minutes), (1296, 144))

    def test_tn2310_boundaries(self):
        cases = [("30000/1001", "00:00:59;29", "00:01:00;02", 1799),
                 ("30000/1001", "00:09:59;29", "00:10:00;00", 17981),
                 ("60000/1001", "00:00:59;59", "00:01:00;04", 3599),
                 ("120000/1001", "00:00:59;119", "00:01:00;008", 7199)]
        for rate, before, after, frame in cases:
            with self.subTest(rate=rate, before=before):
                self.assertEqual(tc.frame_to_timecode(frame, rate, True), before)
                self.assertEqual(tc.frame_to_timecode(frame + 1, rate, True), after)
                self.assertEqual(tc.timecode_to_frame(after, rate, True), frame + 1)

    def test_sampled_non_drop_frame_rates(self):
        rates = ["24000/1001", 25, 48, 50, 60, "60000/1001", 120, "120000/1001", 1, 1000]
        generator = random.Random(SEED)
        checked = 0
        for rate in rates:
            clock = tc.Clock(rate, False)
            n = clock.nominal
            self.assertEqual(clock.per_day, SECONDS_PER_DAY * n)
            frames = set()
            for minute in range(1440):
                base = minute * 60 * n
                frames.update(f for f in range(base - 2, base + 3) if 0 <= f < clock.per_day)
            sample = sorted(frames) + [generator.randrange(clock.per_day) for _ in range(10_000)]
            for frame in sample:
                seconds, ff = divmod(frame, n)
                expected = (f"{seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}:"
                            f"{ff:0{clock.digits}d}")
                self.assertEqual(clock.label(frame), expected)
                self.assertEqual(clock.frame(expected), frame)
            labels = [clock.label(f) for f in sorted(frames)]
            self.assertEqual(labels, sorted(labels))  # fixed-width labels sort with frame order
            checked += len(sample)
        self.assertGreaterEqual(checked, 10 * 10_000)

    def test_drop_frame_refused_at_non_drop_frame_rates(self):
        for rate in ("24/1", "24000/1001", 25, "30/1", "48000/1001", 50, "60/1", "120/1", "1000/1"):
            with self.subTest(rate=rate):
                self.assertFalse(tc.drop_frame_allowed(rate))
                for call in (lambda: tc.frame_to_timecode(0, rate, True),
                             lambda: tc.timecode_to_frame("00:00:00;00", rate, True),
                             lambda: tc.frames_per_day(rate, True)):
                    with self.assertRaises(tc.TimecodeError) as caught:
                        call()
                    self.assertEqual(caught.exception.reason, "drop_frame_rate_unsupported")
        for rate in DF_RATES:
            self.assertTrue(tc.drop_frame_allowed(rate))

    def test_rate_refusal_typed(self):
        cases = {"108930/4549": "rate_unsupported", "24/1001": "rate_unsupported", "2997/100": "rate_unsupported",
                 "1001/1": "rate_unsupported", 1001: "rate_unsupported", Fraction(108930, 4549): "rate_unsupported",
                 0: "rate_invalid", -24: "rate_invalid", "-24": "rate_invalid", True: "rate_invalid",
                 "nan": "rate_invalid", 23.976: "rate_invalid", float("nan"): "rate_invalid", "24/0": "rate_invalid",
                 " 24": "rate_invalid", None: "rate_invalid"}
        for value, reason in cases.items():
            with self.subTest(value=value):
                with self.assertRaises(tc.TimecodeError) as caught:
                    tc.parse_rate(value)
                self.assertEqual(caught.exception.reason, reason)
                self.assertIsInstance(caught.exception, ValueError)
        self.assertEqual(tc.parse_rate("1000/143"), Fraction(7000, 1001))
        self.assertEqual(tc.nominal_fps("1000/143"), 7)
        with self.assertRaises(AssertionError):
            tc.TimecodeError("not_a_reason", "closed set")

    def test_range_and_last_labels(self):
        for rate, drop, last in (("30000/1001", True, "23:59:59;29"), (24, False, "23:59:59:23"),
                                 ("120000/1001", True, "23:59:59;119"), (1000, False, "23:59:59:999")):
            per_day = tc.frames_per_day(rate, drop)
            self.assertEqual(tc.frame_to_timecode(per_day - 1, rate, drop), last)
            self.assertEqual(tc.timecode_to_frame(last, rate, drop), per_day - 1)
            for frame in (-1, per_day, True, 1.0):
                with self.subTest(rate=rate, frame=frame), self.assertRaises(tc.TimecodeError) as caught:
                    tc.frame_to_timecode(frame, rate, drop)
                self.assertEqual(caught.exception.reason, "frame_out_of_range")

    def test_strict_parse_typed_reasons(self):
        cases = [("00:01:00;00", "30000/1001", True, "label_dropped_in_drop_frame"),
                 ("00:01:00;01", "30000/1001", True, "label_dropped_in_drop_frame"),
                 ("00:01:00;003", "120000/1001", True, "label_dropped_in_drop_frame"),
                 ("00:00:01:00", "30000/1001", True, "separator_mode_mismatch"),
                 ("00:00:01;00", "30000/1001", False, "separator_mode_mismatch"),
                 ("24:00:00:00", 24, False, "label_field_out_of_range"),
                 ("00:60:00:00", 24, False, "label_field_out_of_range"),
                 ("00:00:60:00", 24, False, "label_field_out_of_range"),
                 ("00:00:00:24", 24, False, "label_field_out_of_range"),
                 ("00:00:00;30", "30000/1001", True, "label_field_out_of_range"),
                 ("00:00:00:0", 24, False, "label_malformed"),
                 ("00:00:00:000", 24, False, "label_malformed"),
                 ("00:00:00:00", 120, False, "label_malformed"),
                 ("0:00:00:00", 24, False, "label_malformed"),
                 (" 00:00:00:00", 24, False, "label_malformed"),
                 ("00:00:00:00\n", 24, False, "label_malformed"),
                 ("00:00:00:١٢", 24, False, "label_malformed"),
                 ("00:00:00.00", 24, False, "label_malformed"),
                 (b"00:00:00:00", 24, False, "label_malformed")]
        for label, rate, drop, reason in cases:
            with self.subTest(label=label), self.assertRaises(tc.TimecodeError) as caught:
                tc.timecode_to_frame(label, rate, drop)
            self.assertEqual(caught.exception.reason, reason)
        self.assertEqual(tc.timecode_to_frame("00:01:00;02", "30000/1001", True), 1800)
        self.assertEqual(tc.timecode_to_frame("00:00:01:000", 120, False), 120)

    def test_rational_period_kept_exact_without_float(self):
        ntsc, film = tc.Clock("24000/1001"), tc.Clock(24)
        self.assertEqual((ntsc.nominal, film.nominal), (24, 24))
        self.assertEqual(ntsc.label(86_400), film.label(86_400))  # same display label...
        self.assertNotEqual(86_400 / ntsc.rate, 86_400 / film.rate)  # ...distinct media time
        self.assertEqual(86_400 / ntsc.rate, Fraction("3603.6"))
        self.assertEqual(86_400 / film.rate, 3600)
        exact = Fraction(30000, 1001)
        self.assertIs(type(tc.parse_rate(exact)), Fraction)
        self.assertEqual(tc.parse_rate(exact), exact)
        self.assertEqual(tc.parse_rate("30000/1001"), exact)
        for value in tc.frame_to_fields(123_456, exact, True) + (tc.timecode_to_frame("01:00:00;00", exact, True),):
            self.assertIs(type(value), int)
        self.assertEqual(tc.timecode_to_frame("01:00:00;00", exact, True), 107_892)
        self.assertEqual(tc.timecode_to_frame("01:00:00:00", exact, False), 108_000)

    def test_counts_digits_and_module_functions_agree_with_clock(self):
        self.assertEqual([tc.frame_digits(r) for r in (1, 24, 100, 101, 1000, "120000/1001")], [2, 2, 2, 3, 3, 3])
        self.assertEqual(tc.nominal_fps("60000/1001"), 60)
        generator = random.Random(SEED)
        for rate, drop in (("30000/1001", True), ("60000/1001", False), (25, False)):
            clock = tc.Clock(rate, drop)
            for frame in (generator.randrange(clock.per_day) for _ in range(500)):
                text = tc.frame_to_timecode(frame, rate, drop)
                self.assertEqual(text, clock.label(frame))
                self.assertEqual(tc.frame_to_fields(frame, rate, drop), clock.fields(frame))
                self.assertEqual(tc.timecode_to_frame(text, rate, drop), frame)
        with self.assertRaises(tc.TimecodeError):
            tc.Clock(24, 1)
        with self.assertRaises(tc.TimecodeError) as caught:
            tc.dropped_per_minute(24)
        self.assertEqual(caught.exception.reason, "drop_frame_rate_unsupported")


SECONDS_PER_DAY = tc.SECONDS_PER_DAY

if __name__ == "__main__":
    unittest.main()
