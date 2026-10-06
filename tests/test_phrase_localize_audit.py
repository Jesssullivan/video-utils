"""Independent L1 source oracles: synthetic feature arrays, no audio or truth input.

This module deliberately needs only the Python standard library.  Expected
coordinates belong to tests; the worker sees feature arrays and raw proposals.
The noise counterexample documents the guard's limit, rather than asserting a
musical classification which L1 does not implement.
"""
import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("phrase_localize_independent", ROOT / "scripts/phrase_localize.py")
worker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(worker)
HOP = .016


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def npy(shape, values):
    """Write an independent NPY1.0 float64 payload without NumPy."""
    header = repr({"descr": "<f8", "fortran_order": False, "shape": shape})
    header += " " * ((16 - ((10 + len(header) + 1) % 16)) % 16) + "\n"
    return b"\x93NUMPY\x01\x00" + struct.pack("<H", len(header)) + header.encode("ascii") + struct.pack("<" + "d" * len(values), *values)


def write_cache(path, cache):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        features = cache["features"]
        archive.writestr("features.npy", npy((len(features), len(cache["times"])), [x for row in features for x in row]))
        for key in ("times", "centroid", "onsets"):
            archive.writestr(key + ".npy", npy((len(cache[key]),), cache[key]))


def motif(count=64):
    corners = ([1., 0.], [0., 1.], [-1., 0.], [0., -1.])
    return [list(corners[(i // 8) % 4]) for i in range(count)]


def padded():
    return ([[ -1., 0.]] * 10 + motif() + [[-1., 0.]] * 6,
            [[0., -1.]] * 10 + motif() + [[0., -1.]] * 6)


def direct(a, b, *, times_a=None, times_b=None, **kwargs):
    return worker.diagonal_support(times_a or [i * HOP for i in range(len(a))],
                                   times_b or [3.2 + i * HOP for i in range(len(b))], a, b, **kwargs)


def fixture(*, origin=7.25, centered=True, frame_indices=None, ids=(7, 2)):
    duration = 6.
    indices = frame_indices or list(range(376 if centered else 368))
    times = [i * HOP + (0. if centered else .128) for i in indices]
    a, b = padded()
    vectors = [[.1, -.1] for _ in indices]
    for raw_index, vector in enumerate(a):
        if raw_index in indices:
            vectors[indices.index(raw_index)] = vector
    for raw_index, vector in enumerate(b, 200):
        if raw_index in indices:
            vectors[indices.index(raw_index)] = vector
    cache = {"features": [[v[d] if d < 2 else 0. for v in vectors] for d in range(26)],
             "times": times, "centroid": [100.] * len(times), "onsets": []}
    source_sha = "1" * 64
    cache_sha = "2" * 64
    clock = {"schema_version": 1, "source_sha256": source_sha, "audio_start_seconds": origin,
             "duration_seconds": duration, "native_pcm": {"sample_rate": 48000, "channels": 1, "sample_count": 288000},
             "analysis_pcm": {"sample_rate": 16000, "sample_count": 96000},
             "feature_clock": {"hop_samples": 256, "fft_samples": 4096, "centered": centered,
                               "timestamp_convention": "frame_centers_audio_relative", "frame_indices": indices},
             "cache_sha256": cache_sha}
    raw = {"first_start_seconds": 0., "first_end_seconds": 1.28,
           "second_start_seconds": 3.2, "second_end_seconds": 4.48,
           "original_candidate_index": 0, "pulse_count": 2,
           "performance_issue_confirmed": False, "detector_confidence": None,
           "first_boundary_confidence": None, "second_boundary_confidence": None,
           "contrast_evidence": {"margin": .2}, "order_evidence": {"margin": .2}}
    universe = [dict(raw, original_candidate_index=i) for i in range(max(ids, default=0) + 1)]
    retained = [copy.deepcopy(universe[i]) for i in ids]
    proposals = {"schema_version": 1, "source_sha256": source_sha, "cache_sha256": cache_sha,
                 "duration_seconds": duration, "proposal_universe": universe,
                 "arms": {"Border": retained, "Bcontrol": copy.deepcopy(retained)}, "audit": [],
                 "settings_sha256": "3" * 64, "runner_sha256": "4" * 64}
    return cache, proposals, clock


def exhaustive_best(a, b):
    """Enumerate fixed-diagonal contiguous subintervals, independent of DP.

    Used only for a positive-support motif fixture with no unsupported stretch.
    All eligible paths are shorter than eighty frames; no production algorithm
    is reused to obtain its endpoint/reward oracle.
    """
    eligible = []
    for delta in range(-len(a) + 1, len(b)):
        diagonal = [(i, i + delta) for i in range(len(a)) if 0 <= i + delta < len(b)]
        rewards = []
        for i, j in diagonal:
            norm = math.sqrt(sum(x*x for x in a[i]) * sum(x*x for x in b[j]))
            rewards.append(sum(x*y for x, y in zip(a[i], b[j])) / norm - .8 if norm else -.8)
        for start in range(len(diagonal)):
            if rewards[start] <= 0:
                continue
            total = 0.
            unsupported = 0
            for end in range(start, len(diagonal)):
                total += rewards[end]
                unsupported = unsupported + 1 if rewards[end] <= 0 else 0
                if total <= 0 or unsupported * HOP > .128 + 1e-12:
                    break
                if rewards[end] > 0 and (end-start+1)*HOP >= .5:
                    eligible.append((total, diagonal[start], diagonal[end]))
    score = max(row[0] for row in eligible)
    return [row for row in eligible if abs(row[0]-score) <= 1e-12]


class IndependentLocalizationTests(unittest.TestCase):
    def test_padded_motif_matches_exhaustive_fixed_diagonal_oracle(self):
        a, b = padded()
        oracle = exhaustive_best(a, b)
        self.assertEqual(len(oracle), 1)
        self.assertEqual(oracle[0][1:], ((10, 10), (73, 73)))
        result = direct(a, b, duration=6., source_origin=7.25)
        self.assertEqual(result["status"], "localized_support_candidate")
        support = result["localized_support"]
        self.assertAlmostEqual(support["total_reward"], oracle[0][0], places=10)
        for axis, base in (("first", 0.), ("second", 3.2)):
            span = support[axis]
            self.assertAlmostEqual(span["first_center_audio_relative_seconds"], base+.160)
            self.assertAlmostEqual(span["last_center_audio_relative_seconds"], base+1.168)
            self.assertAlmostEqual(span["cell_start_audio_relative_seconds"], base+.152)
            self.assertAlmostEqual(span["cell_end_audio_relative_seconds"], base+1.176)
            self.assertAlmostEqual(span["source_start_seconds"], 7.25+base+.152)
            self.assertAlmostEqual(span["source_end_seconds"], 7.25+base+1.176)
            self.assertAlmostEqual(span["fft_support_start_audio_relative_seconds"], base+.032)
            self.assertAlmostEqual(span["fft_support_end_audio_relative_seconds"], base+1.296)
            self.assertAlmostEqual(support["support_duration_seconds"][axis], 1.024)
        self.assertIsNone(result["confidence"])

    def test_recording_edge_cell_is_clipped_but_fft_support_remains_distinct(self):
        result = direct(motif(), motif(), duration=5.)
        self.assertEqual(result["status"], "localized_support_candidate")
        first = result["localized_support"]["first"]
        self.assertEqual(first["cell_start_audio_relative_seconds"], 0.)
        self.assertEqual(first["fft_support_start_audio_relative_seconds"], 0.)
        self.assertAlmostEqual(first["cell_end_audio_relative_seconds"], 1.016)
        self.assertAlmostEqual(first["fft_support_end_audio_relative_seconds"], 1.136)
        self.assertAlmostEqual(result["localized_support"]["positive_support_duration_seconds"]["first"], 1.016)
        self.assertAlmostEqual(result["localized_support"]["positive_support_duration_seconds"]["second"], 1.024)

    def test_sustain_and_zero_norm_are_unknown_not_phrase_claims(self):
        for vector in ([1., 0.], [0., 0.]):
            result = direct([vector]*64, [vector]*64)
            self.assertEqual(result["status"], "localization_unknown")
            self.assertIsNone(result["localized_support"])
            self.assertIsNone(result["confidence"])

    def test_no_match_is_full_unknown(self):
        result = direct(motif(), [[-x, -y] for x, y in motif(24)])
        self.assertEqual(result["status"], "localization_unknown")
        self.assertIsNone(result["localized_support"])

    def test_tied_distinct_motif_extents_abstain(self):
        a = motif()
        b = motif() + [[.6, .8]]*20 + motif()
        result = direct(a, b, duration=7.)
        self.assertEqual(result["status"], "localization_unknown")
        self.assertIsNone(result["localized_support"])
        self.assertEqual(result["reason"], "nonunique_maximum_support")

    def test_gap_breaks_path_instead_of_compressing_missing_time_bins(self):
        vectors = motif(40)
        times_a = [i*HOP if i < 20 else (i+1)*HOP for i in range(40)]
        times_b = [3.2+t for t in times_a]
        result = direct(vectors, vectors, times_a=times_a, times_b=times_b)
        self.assertEqual(result["status"], "localization_unknown")
        self.assertIsNone(result["localized_support"])

    def test_internal_changes_are_required_separated_and_inside_guard(self):
        for changes, accepted in (((24,40), True), ((24,), False), ((24,28), False), ((4,60), False)):
            with self.subTest(changes=changes):
                vectors = []
                corners = ([1.,0.], [0.,1.], [-1.,0.])
                for i in range(64):
                    vectors.append(list(corners[sum(i >= boundary for boundary in changes)]))
                result = direct(vectors, vectors)
                self.assertEqual(result["status"], "localized_support_candidate" if accepted else "localization_unknown")
                if not accepted:
                    self.assertIsNone(result["localized_support"])

    def test_128ms_unsupported_run_is_allowed_but_longer_run_breaks_path(self):
        vectors = [[math.cos(i*i*.173),math.sin(i*i*.173)] for i in range(160)]
        rotation = math.acos(.79)
        def shifted(count):
            result = copy.deepcopy(vectors)
            for i in range(64,64+count):
                x,y = result[i]
                result[i] = [x*math.cos(rotation)-y*math.sin(rotation), x*math.sin(rotation)+y*math.cos(rotation)]
            return result
        allowed = direct(vectors, shifted(8), duration=7.)
        broken = direct(vectors, shifted(9), duration=7.)
        self.assertEqual(allowed["status"], "localized_support_candidate")
        self.assertEqual(broken["status"], "localized_support_candidate")
        first = allowed["localized_support"]["first"]
        self.assertEqual((first["first_frame_index"],first["last_frame_index"]), (0,159))
        self.assertAlmostEqual(allowed["localized_support"]["unsupported_duration_seconds"]["first"], .128)
        self.assertAlmostEqual(allowed["localized_support"]["unsupported_duration_seconds"]["second"], .128)
        shorter = broken["localized_support"]["first"]
        self.assertGreater(shorter["first_frame_index"], 64)

    def test_large_roi_tiles_are_bounded_and_cells_counted_without_full_matrix(self):
        # Distinct changing sequence prevents arbitrary equal-extent tie selection.
        vectors = [[math.cos(i*i*.173),math.sin(i*i*.173)] for i in range(300)]
        result = direct(vectors, vectors, times_b=[6.4+i*HOP for i in range(300)], duration=12.)
        self.assertEqual(result["status"], "localized_support_candidate")
        self.assertEqual(result["cells_visited"], 300*300)
        tiles = result["localized_support"]["tile_shapes"]
        self.assertEqual(sum(a*b for a,b in tiles), 300*300)
        self.assertTrue(all(0<a<=256 and 0<b<=256 for a,b in tiles))

    def test_preserves_supplied_frame_ids_not_roi_row_numbers(self):
        a, b = padded()
        result = direct(a, b, indices_a=list(range(900,980)), indices_b=list(range(1400,1480)))
        support = result["localized_support"]
        self.assertEqual(support["first"]["first_frame_index"], 910)
        self.assertEqual(support["first"]["last_frame_index"], 973)
        self.assertEqual(support["second"]["first_frame_index"], 1410)
        self.assertEqual(support["second"]["last_frame_index"], 1473)

    def test_changing_noise_can_pass_guard_without_guitar_classification(self):
        # Deliberately shared changing pseudo-noise: acoustic recurrence is real,
        # but the signal has no guitar identity or note/phrase correctness truth.
        vectors = [[math.cos(i*i*.173), math.sin(i*i*.173)] for i in range(64)]
        result = direct(vectors, vectors)
        self.assertEqual(result["status"], "localized_support_candidate")
        self.assertIsNone(result["confidence"])
        self.assertNotIn("performance_issue_confirmed", result)

    def test_legato_features_need_no_picked_attack_onsets(self):
        cache, proposals, clock = fixture(ids=(7,))
        self.assertEqual(cache["onsets"], [])
        result = worker.localize(cache, proposals, clock)
        self.assertEqual(result["localized_count"], 1)
        self.assertIsNone(result["candidates"][0]["confidence"])

    def test_ids_order_raw_rows_and_counts_are_preserved_exactly(self):
        cache, proposals, clock = fixture()
        untouched = copy.deepcopy(proposals)
        result = worker.localize(cache, proposals, clock)
        self.assertEqual(proposals, untouched)
        self.assertEqual(result["candidate_count_pre_selection"], 8)
        self.assertEqual(result["retained_raw_count"], 2)
        self.assertEqual([row["candidate_id"] for row in result["candidates"]], [7,2])
        for row, original in zip(result["candidates"], proposals["arms"]["Border"]):
            self.assertEqual(row["raw_candidate"], original)
            self.assertTrue(row["raw_fallback_available"])
            self.assertIsNone(row["confidence"])
            self.assertEqual(row["roi_audio_relative_seconds"]["first"], [0.,1.536])
            self.assertAlmostEqual(row["roi_audio_relative_seconds"]["second"][0], 2.944)
            self.assertAlmostEqual(row["roi_audio_relative_seconds"]["second"][1], 4.736)
        self.assertLessEqual(result["cells_visited"], 2000000)

    def test_frozen_constants_are_not_hidden_adaptive_knobs(self):
        expected = {"roi_margin_seconds":.256,"cosine_threshold":.8,
                    "minimum_support_seconds":.5,"maximum_nonpositive_gap_seconds":.128,
                    "different_extent_tie_epsilon":1e-12,"active_dimension_std_threshold":1e-5,
                    "z_clip":4.,"internal_change_rms_threshold":.25,"minimum_internal_changes":2,
                    "internal_change_spacing_seconds":.128,"endpoint_guard_seconds":.128,
                    "maximum_frames":512,"maximum_proposals":60,"maximum_retained":10,
                    "maximum_tile_rows":256,"maximum_tile_columns":256,"maximum_cells":2000000,
                    "warp_steps":False,"competitor_order_margin_preserved_not_recomputed":.10}
        for key,value in expected.items():
            self.assertEqual(worker.SETTINGS[key], value, key)

    def test_uncentered_clock_offset_is_added_once_and_source_origin_once(self):
        cache, proposals, clock = fixture(centered=False, ids=(7,))
        result = worker.localize(cache, proposals, clock)
        support = result["candidates"][0]["localized_support"]
        self.assertIsNotNone(support)
        self.assertAlmostEqual(support["first"]["first_center_audio_relative_seconds"], .160+.128)
        self.assertAlmostEqual(support["first"]["source_start_seconds"], 7.25+.152+.128)
        self.assertEqual(support["first"]["first_frame_index"], 10)

    def test_empty_retained_set_and_stationary_full_unknown_keep_raw_fallback(self):
        cache, proposals, clock = fixture(ids=(7,))
        cache["features"] = [[0.]*len(cache["times"]) for _ in range(26)]
        result = worker.localize(cache, proposals, clock)
        self.assertEqual(result["localized_count"], 0)
        self.assertEqual(result["abstained_count"], 1)
        self.assertEqual(result["cells_visited"], 0)
        self.assertEqual(result["candidates"][0]["raw_candidate"], proposals["arms"]["Border"][0])
        self.assertTrue(result["candidates"][0]["raw_fallback_available"])
        self.assertIsNone(result["candidates"][0]["localized_support"])
        proposals["arms"]["Border"] = []
        empty = worker.localize(cache, proposals, clock)
        self.assertEqual(empty["candidates"], [])
        self.assertEqual(empty["localized_count"], 0)
        self.assertEqual(empty["abstained_count"], 0)
        self.assertEqual(empty["cells_visited"], 0)

    def test_native_and_feature_clock_and_binding_reject_inconsistent_metadata(self):
        mutations = (
            lambda c,p,k: k.update(source_sha256="9"*64),
            lambda c,p,k: k.update(cache_sha256="9"*64),
            lambda c,p,k: k["native_pcm"].update(sample_count=288001),
            lambda c,p,k: k["analysis_pcm"].update(sample_count=96001),
            lambda c,p,k: k["feature_clock"].update(hop_samples=257),
            lambda c,p,k: c["times"].__setitem__(10,c["times"][10]+.128),
            lambda c,p,k: p["arms"]["Border"][0].update(first_start_seconds=1.5,first_end_seconds=1.),
            lambda c,p,k: p["arms"]["Border"][0].update(performance_issue_confirmed=True),
        )
        for index, mutation in enumerate(mutations):
            with self.subTest(index=index):
                cache, proposals, clock = fixture(ids=(7,))
                mutation(cache, proposals, clock)
                with self.assertRaises((ValueError, worker.__dict__.get("LocalizeError", ValueError))):
                    worker.localize(cache, proposals, clock)

    def test_cache_and_candidate_resource_limits_reject_before_search(self):
        cache, proposals, clock = fixture(ids=(7,))
        proposals["proposal_universe"] = [dict(proposals["proposal_universe"][0], original_candidate_index=i) for i in range(61)]
        with self.assertRaises(ValueError):
            worker.localize(cache, proposals, clock)
        cache, proposals, clock = fixture(ids=(7,))
        proposals["proposal_universe"] *= 2
        proposals["arms"]["Border"] = [dict(proposals["arms"]["Border"][0], original_candidate_index=i) for i in range(11)]
        with self.assertRaises(ValueError):
            worker.localize(cache, proposals, clock)
        cache, proposals, clock = fixture(frame_indices=list(range(513)), ids=(7,))
        with self.assertRaises(ValueError):
            worker.localize(cache, proposals, clock)

    def test_cli_hash_bound_npz_is_stdlib_readable_and_stale_hash_fails(self):
        (ROOT/"artifacts/experiments").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="phrase-localize-audit-", dir=ROOT/"artifacts/experiments") as directory:
            path = Path(directory)
            cache, proposals, clock = fixture(ids=(7,))
            cache_path = path / "cache.npz"
            write_cache(cache_path, cache)
            cache_sha = digest(cache_path)
            clock["cache_sha256"] = proposals["cache_sha256"] = cache_sha
            proposals_path, clock_path = path/"proposals.json", path/"clock.json"
            proposals_path.write_text(json.dumps(proposals))
            clock_path.write_text(json.dumps(clock))
            args = [sys.executable, "-S", str(ROOT/"scripts/phrase_localize.py"), "--cache", str(cache_path),
                    "--cache-sha256", cache_sha, "--proposals", str(proposals_path), "--proposals-sha256", digest(proposals_path),
                    "--clock", str(clock_path), "--clock-sha256", digest(clock_path), "--output", str(path/"out"), "--summary"]
            run = subprocess.run(args, capture_output=True, text=True, timeout=30)
            self.assertEqual(run.returncode, 0, run.stderr)
            summary = json.loads(run.stdout)
            self.assertEqual(summary["localized_count"], 1)
            args[args.index("--output")+1] = str(path/"stale")
            cache_path.write_bytes(cache_path.read_bytes()+b"changed")
            rejected = subprocess.run(args, capture_output=True, text=True, timeout=30)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertFalse((path/"stale").exists())

    def test_npz_rejects_unknown_members_and_expansion_bomb(self):
        (ROOT/"artifacts/experiments").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="phrase-localize-parser-audit-", dir=ROOT/"artifacts/experiments") as directory:
            path = Path(directory)/"cache.npz"
            cache,_,_ = fixture(ids=(7,))
            write_cache(path, cache)
            with zipfile.ZipFile(path, "a") as archive:
                archive.writestr("unexpected.npy", npy((1,),[0.]))
            with self.assertRaises(ValueError):
                worker.cache_receipt(path,digest(path))
            # Four exact required names but over the independent expansion cap.
            with zipfile.ZipFile(path,"w",compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("features.npy", b"\x00"*(1024**2+1))
                for key in ("times","centroid","onsets"):
                    archive.writestr(key+".npy",npy((0,),[]))
            with self.assertRaises(ValueError):
                worker.cache_receipt(path,digest(path))

    def test_npy_parser_rejects_objects_fortran_nonfinite_and_payload_mismatch(self):
        ordinary = npy((1,),[0.])
        malformed = (
            ordinary.replace(b"'<f8'", b"'|O8'"),
            ordinary.replace(b"False", b"True "),
            npy((1,),[float("nan")]),
            npy((1,),[float("inf")]),
            ordinary[:-1],
        )
        for index, payload in enumerate(malformed):
            with self.subTest(index=index), self.assertRaises(ValueError):
                worker.npy(payload)

    def test_json_duplicate_depth_and_overflow_fail_and_symlink_is_rejected(self):
        (ROOT/"artifacts/experiments").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="phrase-localize-json-audit-", dir=ROOT/"artifacts/experiments") as directory:
            path = Path(directory)/"receipt.json"
            for raw in (b'{"a":1,"a":2}', b'{"a":1e400}', b'{"a":NaN}', b'{"a":'+b'['*129+b'0'+b']'*129+b'}'):
                path.write_bytes(raw)
                with self.assertRaises(ValueError):
                    worker.json_receipt(path,digest(path))
            path.write_text('{"a":1}')
            alias = path.parent/"alias.json"
            alias.symlink_to(path)
            with self.assertRaises(ValueError):
                worker.json_receipt(alias,digest(path))


if __name__ == "__main__":
    unittest.main()
