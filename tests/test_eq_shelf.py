"""S2R eq_shelf: bounded, boost-only, reversible low shelf below 160 Hz.

Contract: docs/spec/sprints/EQ_SHELF_S2R.md (frozen at f2627c8). Authority: operator
ruling 2026-10-07 ("capped, reversible low-shelf as an explicit profile option;
default FULLER unchanged; never a cut or notch near the ~32 Hz fundamental").

Claim classes: contract tests are code behaviour (C); the synthetic fixture arms
are measurements (M) on a generated harmonic series at the theoretical A4=440
C1 frequency, not a model of the instrument or a real-take result; the RBJ
analytic magnitudes are filter-theory inference (I). Listening (L) is never
performed here. FFmpeg arms are skipped (reported as skips) when FFmpeg does not
resolve through FFMPEG or PATH.

`python3 tests/test_eq_shelf.py --measure OUT.json` writes the fixture
measurements as JSON (used for the lane run receipt); otherwise unittest runs.
"""
from __future__ import annotations

import array
import cmath
import copy
import hashlib
import importlib.util
import json
import math
import operator
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("eq_shelf_media_worker", REPO / "scripts" / "media.py")
media = importlib.util.module_from_spec(spec)
spec.loader.exec_module(media)

FULLER = REPO / "profiles" / "fuller.json"
FULLER_SHELF = REPO / "profiles" / "fuller-shelf.json"
SKILL = REPO / ".agents" / "skills" / "guitar-denoise" / "SKILL.md"
TONE_AB_RECEIPT = REPO / "docs/agent-notes/sprints/20261006-s2/tone_ab-20261006T120702Z-actual-run.json"
FULLER_SHA256 = "33da74c7d1bda246b6349252e4374d3674e76356dd85d72a83b1389988d04a5c"
BASELINE_COMMIT = "7d0e11e"
EXISTING_PROFILES = ("bypass", "captured12", "captured8-clarity", "captured8", "conservative3",
                     "fuller", "mild6")
P = ("equalizer=f=160:t=q:w=0.7:g=2:b=0:r=f64,equalizer=f=300:t=q:w=0.8:g=1:b=0:r=f64,"
     "acompressor=threshold=0.125892541179:ratio=2:attack=15:release=100:knee=1.41253754462:"
     "makeup=1:level_in=1:mode=downward:link=maximum:detection=rms:mix=0.25")
SHELF_FILTER = "lowshelf=f=100:t=q:w=0.7:g=1.5:r=f64"
P_PRIME = SHELF_FILTER + "," + P
# Joined post-denoise text of every pre-existing profile at the frozen baseline
# 7d0e11e (static pin, so CI without history still checks identity).
BASELINE_POST = {
    "bypass": "", "captured12": "", "captured8": "", "conservative3": "", "mild6": "",
    "fuller": P,
    "captured8-clarity": ("equalizer=f=300:t=q:w=0.8:g=-1.5:b=0:r=f64,"
                          "equalizer=f=2200:t=q:w=0.8:g=1:b=0:r=f64,"
                          "acompressor=threshold=0.125892541179:ratio=2:attack=15:release=100:"
                          "knee=1.41253754462:makeup=1:level_in=1:mode=downward:link=maximum:"
                          "detection=rms:mix=0.25"),
}

# Preregistered fixture F1 and scoring (contract section 7).
RATE = 44100
DURATION_S = 8.0
C1_HZ = 32.703  # theoretical A4=440 equal-temperament C1 (program/instrument.json); not measured
HARMONICS = 9
FADE_S = 0.050
WINDOW_S = (2.0, 6.0)
NO_CUT_TOLERANCE_DB = -0.02
RBJ_AGREEMENT_DB = 0.15
RENDER_TIMEOUT_S = 120
SHELF = {"frequency_hz": 100.0, "gain_db": 1.5, "q": 0.7}


def fuller():
    return json.loads(FULLER.read_text())


def fuller_shelf():
    return json.loads(FULLER_SHELF.read_text())


def joined(profile, rate=RATE):
    return ",".join(stage["filter"] for stage in media.post_denoise_filters(profile, rate))


def ffmpeg_path():
    selected = os.environ.get("FFMPEG", "ffmpeg")
    return shutil.which(selected)


# ---------------------------------------------------------------- fixture and scoring

def fixture_f1():
    count = int(round(RATE * DURATION_S))
    fade = int(round(RATE * FADE_S))
    data = array.array("f", bytes(4 * count))
    step = 2 * math.pi * C1_HZ / RATE
    amplitudes = [0.25 / k for k in range(1, HARMONICS + 1)]
    peak = 0.0
    for n in range(count):
        theta = step * n
        value = 0.0
        for k, amplitude in enumerate(amplitudes, 1):
            value += amplitude * math.sin(k * theta)
        if n < fade:
            value *= 0.5 * (1 - math.cos(math.pi * n / fade))
        elif n >= count - fade:
            value *= 0.5 * (1 - math.cos(math.pi * (count - 1 - n) / fade))
        data[n] = value
        peak = max(peak, abs(value))
    return data, peak


_BASIS_CACHE = {}


def _basis():
    """Sin/cos columns at k*C1 over the scoring window plus their Gram matrix (cached)."""
    if "basis" in _BASIS_CACHE:
        return _BASIS_CACHE["basis"]
    start, stop = (int(round(RATE * seconds)) for seconds in WINDOW_S)
    columns = []
    for k in range(1, HARMONICS + 1):
        step = 2 * math.pi * k * C1_HZ / RATE
        columns.append(array.array("d", (math.sin(step * n) for n in range(start, stop))))
        columns.append(array.array("d", (math.cos(step * n) for n in range(start, stop))))
    gram = [[math.fsum(map(operator.mul, a, b)) for b in columns] for a in columns]
    _BASIS_CACHE["basis"] = (start, stop, columns, gram)
    return _BASIS_CACHE["basis"]


def _solve(matrix, vector):
    size = len(vector)
    rows = [list(matrix[i]) + [vector[i]] for i in range(size)]
    for col in range(size):
        pivot = max(range(col, size), key=lambda r: abs(rows[r][col]))
        rows[col], rows[pivot] = rows[pivot], rows[col]
        for r in range(size):
            if r != col:
                factor = rows[r][col] / rows[col][col]
                rows[r] = [x - factor * y for x, y in zip(rows[r], rows[col])]
    return [rows[i][size] / rows[i][i] for i in range(size)]


def amplitudes(signal):
    """Joint least-squares amplitude of each harmonic over the scoring window."""
    start, stop, columns, gram = _basis()
    window = array.array("d", signal[start:stop])
    rhs = [math.fsum(map(operator.mul, column, window)) for column in columns]
    solution = _solve(gram, rhs)
    return [math.hypot(solution[2 * i], solution[2 * i + 1]) for i in range(HARMONICS)]


def rbj_lowshelf_db(frequency_hz, gain_db, q, rate, at_hz):
    """RBJ cookbook low shelf (FFmpeg t=q: alpha = sin(w0)/(2Q)) magnitude in dB (inference)."""
    a = 10 ** (gain_db / 40)
    w0 = 2 * math.pi * frequency_hz / rate
    cos_w0, alpha, root = math.cos(w0), math.sin(w0) / (2 * q), math.sqrt(a)
    b0 = a * ((a + 1) - (a - 1) * cos_w0 + 2 * root * alpha)
    b1 = 2 * a * ((a - 1) - (a + 1) * cos_w0)
    b2 = a * ((a + 1) - (a - 1) * cos_w0 - 2 * root * alpha)
    a0 = (a + 1) + (a - 1) * cos_w0 + 2 * root * alpha
    a1 = -2 * ((a - 1) + (a + 1) * cos_w0)
    a2 = (a + 1) + (a - 1) * cos_w0 - 2 * root * alpha
    z = cmath.exp(-2j * math.pi * at_hz / rate)
    return 20 * math.log10(abs((b0 + b1 * z + b2 * z * z) / (a0 + a1 * z + a2 * z * z)))


def render(source: Path, output: Path, audio_filter: str):
    command = [ffmpeg_path(), "-hide_banner", "-nostdin", "-loglevel", "error", "-threads", "2",
               "-filter_threads", "2", "-f", "f32le", "-ar", str(RATE), "-ac", "1", "-i", str(source),
               "-af", audio_filter, "-f", "f32le", "-ar", str(RATE), "-ac", "1", "-c:a", "pcm_f32le",
               "-y", str(output)]
    media.run(command, timeout=RENDER_TIMEOUT_S)
    data = array.array("f")
    data.frombytes(output.read_bytes())
    return data, command


def deltas(arm, reference):
    return [20 * math.log10(a / r) for a, r in zip(amplitudes(arm), amplitudes(reference))]


def measure_fixture():
    """Run arms E0, E1 and E2 on F1; return measurements with denominators."""
    signal, peak = fixture_f1()
    if not peak < 1.0:
        raise AssertionError(f"fixture peak {peak} is not below 0 dBFS")
    with tempfile.TemporaryDirectory(prefix="eq_shelf-") as temporary:
        directory = Path(temporary)
        source = directory / "f1.f32"
        source.write_bytes(signal.tobytes())
        e0, e0_command = render(source, directory / "e0.f32", "anull")
        e1, e1_command = render(source, directory / "e1.f32", SHELF_FILTER)
        p_arm, p_command = render(source, directory / "p.f32", P)
        pp_arm, pp_command = render(source, directory / "pp.f32", P_PRIME)
    for arm in (e0, e1, p_arm, pp_arm):
        if len(arm) != len(signal):
            raise AssertionError("render changed the sample count")
    e1_delta = deltas(e1, e0)
    e2_delta = deltas(pp_arm, p_arm)
    analytic = [rbj_lowshelf_db(SHELF["frequency_hz"], SHELF["gain_db"], SHELF["q"], RATE, k * C1_HZ)
                for k in range(1, HARMONICS + 1)]
    components = [{"k": k, "frequency_hz": round(k * C1_HZ, 6),
                   "e1_shelf_only_delta_db": round(e1_delta[k - 1], 6),
                   "e2_full_post_chain_delta_db": round(e2_delta[k - 1], 6),
                   "rbj_analytic_db": round(analytic[k - 1], 6)} for k in range(1, HARMONICS + 1)]
    not_cut = sum(1 for value in e1_delta if value >= NO_CUT_TOLERANCE_DB)
    return {
        "fixture": {"id": "F1", "sample_rate": RATE, "channels": 1, "format": "float32",
                    "duration_s": DURATION_S, "c1_hz": C1_HZ, "c1_basis": "theoretical A4=440 ET; not measured",
                    "harmonics": HARMONICS, "amplitude_rule": "0.25/k, phase 0 (sin)",
                    "fade": "50 ms raised cosine in/out", "peak": round(peak, 6),
                    "scope": "synthetic harmonic series; not a model of the instrument or the take"},
        "scoring": {"window_s": list(WINDOW_S), "method": "joint least-squares sin/cos projection at k*C1",
                    "delta": "20*log10(A_arm/A_ref) per component", "denominator": f"{HARMONICS} components"},
        "arms": {"E0": {"filter": "anull", "role": "reference for E1"},
                 "E1": {"filter": SHELF_FILTER, "role": "shelf only vs E0"},
                 "E2": {"filter_reference": P, "filter_arm": P_PRIME,
                        "role": "full post chain P' vs P, report only; includes compressor; no loudnorm"}},
        "components": components,
        "c1_delta_db_e1": round(e1_delta[0], 3),
        "c1_delta_db_e1_pass_band": "(0, +2.0]",
        "c1_delta_e1_passes": 0 < e1_delta[0] <= 2.0,
        "components_not_cut_e1": f"{not_cut}/{HARMONICS}",
        "no_cut_tolerance_db": NO_CUT_TOLERANCE_DB,
        "c1_rbj_analytic_db": round(analytic[0], 3),
        "c1_measured_minus_analytic_db": round(e1_delta[0] - analytic[0], 3),
        "rbj_agreement_band_db": RBJ_AGREEMENT_DB,
        "c1_rbj_within_band": abs(e1_delta[0] - analytic[0]) <= RBJ_AGREEMENT_DB,
        "max_abs_measured_minus_analytic_db_e1": round(max(abs(m - a) for m, a in zip(e1_delta, analytic)), 4),
        "c1_delta_db_e2": round(e2_delta[0], 3),
        "commands": {"E0": e0_command[1:], "E1": e1_command[1:], "E2_P": p_command[1:],
                     "E2_P_prime": pp_command[1:]},
    }


_MEASUREMENT = {}


def measurement():
    if "result" not in _MEASUREMENT:
        _MEASUREMENT["result"] = measure_fixture()
    return _MEASUREMENT["result"]


# ---------------------------------------------------------------- contract tests

class ShelfRefusalTests(unittest.TestCase):
    """Metric 1: 18 refusals, each asserting the exact typed code."""

    def assertRefused(self, profile, code):
        with self.assertRaises(media.MediaError) as caught:
            media.validate_profile(profile)
        self.assertEqual(caught.exception.code, code, str(caught.exception))

    def shelf(self, **changes):
        profile = fuller_shelf()
        profile["low_shelf"] = dict(profile["low_shelf"], **changes)
        return profile

    def test_frequency_bounds(self):
        for value in (79, 161):
            with self.subTest(frequency_hz=value):
                self.assertRefused(self.shelf(frequency_hz=value), "low_shelf_frequency_out_of_bounds")

    def test_gain_above_cap(self):
        self.assertRefused(self.shelf(gain_db=2.1), "low_shelf_gain_out_of_bounds")

    def test_any_cut_refused_including_negative_zero(self):
        for value in (-0.1, -2.0, -0.0):
            with self.subTest(gain_db=value):
                self.assertRefused(self.shelf(gain_db=value), "low_shelf_cut_refused")

    def test_two_shelves_as_list(self):
        profile = fuller_shelf()
        profile["low_shelf"] = [dict(SHELF), dict(SHELF, frequency_hz=150.0)]
        self.assertRefused(profile, "low_shelf_multiple")

    def test_duplicated_key_in_profile_file(self):
        text = FULLER_SHELF.read_text()
        line = '  "low_shelf": {"frequency_hz": 100.0, "gain_db": 1.5, "q": 0.7},\n'
        self.assertIn(line, text)
        doubled = text.replace(line, line + line.replace("100.0", "150.0"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "doubled.json"
            path.write_text(doubled)
            with self.assertRaises(media.MediaError) as caught:
                media.load_profile(path)
        self.assertEqual(caught.exception.code, "low_shelf_multiple")

    def test_q_bounds(self):
        for value in (0.49, 0.71):
            with self.subTest(q=value):
                self.assertRefused(self.shelf(q=value), "low_shelf_q_out_of_bounds")

    def test_invalid_shapes_and_values(self):
        missing = fuller_shelf()
        del missing["low_shelf"]["q"]
        cases = {"boolean": self.shelf(gain_db=True), "nan": self.shelf(gain_db=float("nan")),
                 "inf": self.shelf(frequency_hz=float("inf")), "missing_key": missing,
                 "extra_key": self.shelf(type="lowshelf"), "string": self.shelf(q="0.7")}
        for name, profile in cases.items():
            with self.subTest(case=name):
                self.assertRefused(profile, "low_shelf_invalid")

    def test_status_required(self):
        profile = fuller_shelf()
        del profile["operator_review_status"], profile["listening_acceptance"]
        self.assertRefused(profile, "low_shelf_review_status_required")

    def test_status_cannot_claim_acceptance(self):
        profile = fuller_shelf()
        profile["listening_acceptance"] = "accepted"
        self.assertRefused(profile, "low_shelf_review_status_invalid")

    def test_extras_beyond_denominator(self):
        # Not counted in the 18: one missing status, non-string status, huge int, null shelf.
        one = fuller_shelf()
        del one["listening_acceptance"]
        self.assertRefused(one, "low_shelf_review_status_required")
        self.assertRefused(dict(fuller_shelf(), operator_review_status=["unreviewed_trial"]),
                           "low_shelf_review_status_invalid")
        self.assertRefused(self.shelf(frequency_hz=10 ** 400), "low_shelf_invalid")
        self.assertRefused(dict(fuller_shelf(), low_shelf=None), "low_shelf_invalid")
        self.assertRefused(dict(fuller_shelf(), low_shelf=[]), "low_shelf_multiple")

    def test_above_nyquist_at_render(self):
        with self.assertRaises(media.MediaError) as caught:
            media.post_denoise_filters(fuller_shelf(), 200)
        self.assertEqual(caught.exception.code, "low_shelf_above_nyquist")


class ShelfAcceptanceTests(unittest.TestCase):
    """Metric 2: six accepted edges; plus filter-theory evidence for the Q bound."""

    def test_accepted_edges(self):
        edges = [("frequency_hz", 80), ("frequency_hz", 160), ("gain_db", 0.0), ("gain_db", 2.0),
                 ("q", 0.5), ("q", 0.707)]
        for key, value in edges:
            with self.subTest(**{key: value}):
                profile = fuller_shelf()
                profile["low_shelf"][key] = value
                self.assertIs(media.validate_profile(profile), profile)
                stage = media.post_denoise_filters(profile, RATE)[0]
                self.assertEqual(stage["stage"], "low_shelf")
                self.assertTrue(stage["filter"].startswith("lowshelf=f="))

    def test_rbj_shelf_never_cuts_inside_bounds_inference(self):
        # Class I: at the bound corners the cookbook magnitude stays >= 0 dB on a
        # 1 Hz..20 kHz log grid; just above Q 1/sqrt(2) it dips below unity.
        grid = [10 ** (i / 100) for i in range(0, 431)]
        for frequency in (80.0, 100.0, 160.0):
            for gain in (0.5, 2.0):
                for q in (0.5, 0.707):
                    low = min(rbj_lowshelf_db(frequency, gain, q, RATE, x) for x in grid)
                    self.assertGreaterEqual(low, -1e-9, (frequency, gain, q))
        self.assertLess(min(rbj_lowshelf_db(160.0, 2.0, 1.0, RATE, x) for x in grid), -0.1)


class PeakingEqUnchangedTests(unittest.TestCase):
    """Metric 3: peaking EQ keeps 160..6000 Hz."""

    def band(self, frequency):
        profile = fuller()
        profile["peaking_eq"][0]["frequency_hz"] = frequency
        return profile

    def test_peaking_bounds(self):
        for frequency in (159, 6001):
            with self.subTest(frequency_hz=frequency), self.assertRaises(media.MediaError):
                media.validate_profile(self.band(frequency))
        for frequency in (160, 6000):
            with self.subTest(frequency_hz=frequency):
                media.validate_profile(self.band(frequency))

    def test_shelf_like_peaking_band_below_160_still_refused(self):
        with self.assertRaises(media.MediaError):
            media.validate_profile(self.band(100))
        profile = fuller()
        profile["peaking_eq"].append({"frequency_hz": 100.0, "gain_db": 1.5, "q": 0.7, "type": "lowshelf"})
        with self.assertRaises(media.MediaError):
            media.validate_profile(profile)


class FullerIdentityTests(unittest.TestCase):
    """Metric 4: FULLER file hash, default name and P byte equality."""

    def test_fuller_json_unchanged(self):
        self.assertEqual(hashlib.sha256(FULLER.read_bytes()).hexdigest(), FULLER_SHA256)

    def test_default_profile_is_fuller(self):
        self.assertEqual(media.DEFAULT_PROFILE, "fuller")

    def test_fuller_post_graph_is_p(self):
        profile = media.load_profile("fuller")
        self.assertEqual(joined(profile), P)
        self.assertNotIn("low_shelf", [stage["stage"] for stage in media.post_denoise_filters(profile, RATE)])
        self.assertNotIn("low_shelf", profile)


def baseline_media():
    """Frozen media.py at 7d0e11e loaded in-process, or None without git history."""
    git = shutil.which("git")
    if not git:
        return None
    try:
        source = subprocess.run([git, "-C", str(REPO), "show", f"{BASELINE_COMMIT}:scripts/media.py"],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=30, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "media_baseline.py"
        path.write_bytes(source)
        loader = importlib.util.spec_from_file_location("eq_shelf_media_baseline", path)
        module = importlib.util.module_from_spec(loader)
        loader.loader.exec_module(module)
    module.ROOT = REPO
    return module


class ExistingProfilesUnchangedTests(unittest.TestCase):
    """Metric 5: all seven pre-existing profiles load with byte-identical stage lists."""

    def test_static_pin(self):
        for name in EXISTING_PROFILES:
            with self.subTest(profile=name):
                self.assertEqual(joined(media.load_profile(name)), BASELINE_POST[name])

    def test_against_frozen_baseline_source(self):
        baseline = baseline_media()
        if baseline is None:
            self.skipTest("git history for 7d0e11e unavailable; static pin still checked")
        for name in EXISTING_PROFILES:
            with self.subTest(profile=name):
                current = media.load_profile(name)
                frozen = baseline.load_profile(REPO / "profiles" / f"{name}.json")
                self.assertEqual(current, frozen)
                self.assertEqual(media.post_denoise_filters(current, RATE),
                                 baseline.post_denoise_filters(frozen, RATE))


class FullerShelfProfileTests(unittest.TestCase):
    """Metric 6: P' equality and shelf filter == tone_ab trial filter."""

    def setUp(self):
        self.profile = media.load_profile("fuller-shelf")

    def test_p_prime(self):
        self.assertEqual(joined(self.profile), P_PRIME)
        self.assertEqual([stage["stage"] for stage in media.post_denoise_filters(self.profile, RATE)],
                         ["low_shelf", "peaking_eq_1", "peaking_eq_2", "rms_compressor"])

    def test_shelf_filter_matches_tone_ab_trial(self):
        receipt = json.loads(TONE_AB_RECEIPT.read_text())
        stage = media.post_denoise_filters(self.profile, RATE)[0]
        self.assertEqual(stage["filter"], receipt["experiment"]["filter"])
        self.assertEqual(stage["filter"], SHELF_FILTER)
        self.assertIs(stage["boost_only"], True)
        self.assertIs(stage["recreates_uncaptured_fundamental"], False)
        self.assertIn("re-render the unchanged source with profile fuller", stage["reversibility"])
        self.assertIs(stage["timing"]["acoustic_alignment_verified"], False)

    def test_status_and_controls_match_fuller(self):
        self.assertEqual(self.profile["operator_review_status"], "unreviewed_trial")
        self.assertEqual(self.profile["listening_acceptance"], "not_performed")
        self.assertEqual(self.profile["low_shelf"], SHELF)
        base = fuller()
        added = {"low_shelf", "operator_review_status", "listening_acceptance"}
        self.assertEqual(set(self.profile) - added, set(base))
        for key in set(base) - {"name", "description"}:
            with self.subTest(key=key):
                self.assertEqual(json.dumps(self.profile[key]), json.dumps(base[key]))
        self.assertEqual(self.profile["name"], "fuller-shelf")
        self.assertIs(self.profile["noise_capture_required"], True)
        self.assertLessEqual(len(self.profile["description"]), 2000)
        for phrase in ("never the default", "not covered by the FULLER listening acceptance",
                       "before the peaking EQ, compression and loudnorm", "matched level",
                       "No claim of 32 Hz restoration"):
            self.assertIn(phrase, self.profile["description"])

    def test_no_cut_or_notch_stage(self):
        graph = joined(self.profile).lower()
        for name in ("highpass", "lowpass", "bandreject", "bandpass", "notch", "highshelf", "treble="):
            self.assertNotIn(name, graph)
        self.assertEqual(graph.count("lowshelf"), 1)


class DefaultRefusalTests(unittest.TestCase):
    """Metric 7: capture_interval_required before hashing/decode for fuller and fuller-shelf."""

    def test_capture_interval_required(self):
        runs = media.ROOT / "artifacts" / "runs"
        before = sorted(p.name for p in runs.iterdir()) if runs.is_dir() else None
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "take.mov"
            fixture.write_bytes(b"not decoded")
            for name in ("fuller", "fuller-shelf"):
                with self.subTest(profile=name), patch.object(media, "sha256") as digest, \
                        patch.object(media, "probe") as probe:
                    with self.assertRaises(media.MediaError) as caught:
                        media.clean(fixture, name)
                    self.assertEqual(caught.exception.code, "capture_interval_required")
                    self.assertIn(f"profile {name} requires a reviewed per-take capture", str(caught.exception))
                    digest.assert_not_called()
                    probe.assert_not_called()
        after = sorted(p.name for p in runs.iterdir()) if runs.is_dir() else None
        self.assertEqual(before, after)

    def test_invalid_shelf_refused_before_hashing(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "take.mov"
            fixture.write_bytes(b"not decoded")
            profile = fuller_shelf()
            profile["low_shelf"]["gain_db"] = -1.0
            path = Path(directory) / "cut.json"
            path.write_text(json.dumps(profile))
            with patch.object(media, "sha256") as digest, patch.object(media, "probe") as probe:
                with self.assertRaises(media.MediaError) as caught:
                    media.clean(fixture, path, capture_interval=(0.2, 1.0), capture_review="synthetic")
            self.assertEqual(caught.exception.code, "low_shelf_cut_refused")
            digest.assert_not_called()
            probe.assert_not_called()


@unittest.skipUnless(ffmpeg_path(), "FFmpeg not available via FFMPEG or PATH")
class SyntheticC1FixtureTests(unittest.TestCase):
    """Metrics 8-11: measured on F1 (class M), RBJ analytic beside it (class I)."""

    def test_e1_c1_boost_bounded_and_no_component_cut(self):
        result = measurement()
        self.assertTrue(result["fixture"]["peak"] < 1.0)
        c1 = result["components"][0]["e1_shelf_only_delta_db"]
        self.assertGreater(c1, 0.0)
        self.assertLessEqual(c1, 2.0)
        for component in result["components"]:
            with self.subTest(k=component["k"]):
                self.assertGreaterEqual(component["e1_shelf_only_delta_db"], NO_CUT_TOLERANCE_DB)
        self.assertEqual(result["components_not_cut_e1"], f"{HARMONICS}/{HARMONICS}")

    def test_reported_rbj_and_full_chain_fields_present(self):
        # Metric 10 and 11 are report-only: recorded, never tuned on.
        result = measurement()
        self.assertTrue(math.isfinite(result["c1_measured_minus_analytic_db"]))
        self.assertIsInstance(result["c1_rbj_within_band"], bool)
        self.assertEqual(len(result["components"]), HARMONICS)
        self.assertTrue(all(math.isfinite(c["e2_full_post_chain_delta_db"]) for c in result["components"]))


class SkillTextTests(unittest.TestCase):
    """Metric 12: eight skill-text checks."""

    def test_skill_documents_knob(self):
        text = SKILL.read_text()
        for phrase in ("`low_shelf`", "80–160 Hz", "0 to +2 dB", "Q 0.5–0.707", "boost only",
                       "reversible", "listening", "`fuller` remains the default"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--measure":
        out = Path(sys.argv[2])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(measure_fixture(), indent=2) + "\n")
        print(out)
    else:
        unittest.main()
