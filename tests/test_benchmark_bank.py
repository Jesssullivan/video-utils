"""Independent waveform hashes, analytic timing and rendered-reference checks."""
import copy
import hashlib
import importlib.util
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("benchmark_bank_test_runner",ROOT/"scripts"/"benchmark.py")
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)
bank = benchmark.bank_module()

# Recorded before the extension from the original published v1 PCM16 artifacts.
GOLDEN = {
    "low32-sustain": {"clean":"89293c7a8e1f72491e4dfcac0a308dd31d96258ff3858c75cf948d449bdb3d6a",
                      "click":"103ce28c0f25293ac511116df6b67922e1f37fa270040f4948bad6c739ff79ff",
                      "noise":"0a37a002e341cd36846ff102b560a493b0d100057730d4c6e9a8565e78356b32",
                      "mix":"35a7a9ea48fb0bbef4e05d7ec40e4c3b3b93cdddefab9200dd244fbe5c7645e7"},
    "palm-muted-recurrence": {"clean":"221ab8d8aafd5aca7d227a20bc0ac0be579391476fd299a8a439b04e3413289d",
                             "click":"103ce28c0f25293ac511116df6b67922e1f37fa270040f4948bad6c739ff79ff",
                             "noise":"6b2726907ae907794caf622a0e4c1595e30a3c494c142826c1d3bb6a72553ed9",
                             "mix":"499c3693fdfbff38d88439cb7ea802115236817e1013f0a7aaa3651d560897c0"},
    "legato-recurrence": {"clean":"1108d30063dee980c56cc9b0d0e45f75d778610a1c01f749f28b89d5390e2ba3",
                         "click":"103ce28c0f25293ac511116df6b67922e1f37fa270040f4948bad6c739ff79ff",
                         "noise":"2ad9de640121fec79bc6fa4f7b1baad300743f206d0ba179c1d89204a9c912bb",
                         "mix":"ea2329ea35fb199ac0e42afc28fa019401f0722ae3a7ed37a0e3528640edf424"}}


class BankTests(unittest.TestCase):
    def setUp(self):
        self.config=benchmark.configuration("technical-v2")

    def signals(self,identity):
        definition=next(row for row in self.config["fixtures"] if row["id"]==identity)
        return bank.generate(definition,self.config,benchmark.fixture_signals)

    def test_registered_bank_and_hard_resource_limits(self):
        self.assertEqual(len(self.config["fixtures"]),12)
        self.assertEqual(sum(row["duration_seconds"] for row in self.config["fixtures"]),120)
        for key,value in (("max_cases",13),("max_total_duration_seconds",121),("math_threads",3),("max_decoded_bytes",3000001)):
            modified=copy.deepcopy(self.config)
            modified["bounds"][key]=value
            with self.assertRaises(ValueError):
                bank.validate_configuration(modified)
        modified=copy.deepcopy(self.config)
        modified["fixtures"][4]["duration_seconds"]=9
        with self.assertRaises(ValueError):
            bank.validate_configuration(modified)

    def test_configuration_bytes_cannot_be_rebound_after_initial_parse(self):
        import json
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            changed=copy.deepcopy(self.config)
            changed["seed"]+=1
            config_path=root/"config.json"
            config_path.write_text(json.dumps(changed))
            with patch.object(bank,"CONFIG",config_path):
                with self.assertRaisesRegex(ValueError,"configuration changed after parsing"):
                    bank.create_fixtures(root,self.config,benchmark.fixture_signals,benchmark.pcm16,
                                         benchmark.read_pcm16,benchmark.digest,benchmark.write_json)
            self.assertEqual([path.name for path in root.iterdir()],["config.json"])

    def test_legacy_waveforms_match_prepublished_pcm_hashes_in_both_suites(self):
        with tempfile.TemporaryDirectory() as temporary:
            for definition in benchmark.configuration()["fixtures"]:
                v1,_=benchmark.fixture_signals(definition,benchmark.configuration())
                v2,_=self.signals(definition["id"])
                for component in ("clean","click","noise","mix"):
                    for samples in (v1[component],v2[component]):
                        path=Path(temporary)/"reference.wav"
                        benchmark.pcm16(path,samples,48000)
                        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),GOLDEN[definition["id"]][component])

    def test_rendered_missing_fundamental_is_absent_and_injected_f0_fails(self):
        signals,truth=self.signals("c1-missing-fundamental")
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/"clean.wav"
            benchmark.pcm16(path,signals["clean"],48000)
            samples,rate=benchmark.read_pcm16(path)
        receipt=bank.verify_missing_render(samples,rate,truth)
        self.assertLess(receipt["measured_amplitudes"][0],5e-5)
        for measured,expected in zip(receipt["measured_amplitudes"][1:],[.13,.08,.05,.04,.02]):
            self.assertAlmostEqual(measured,expected,delta=5e-5)
        contaminated=[value+.002*math.sin(2*math.pi*32.703195663*i/rate) for i,value in enumerate(samples)]
        with self.assertRaisesRegex(ValueError,"missing-F0"):
            bank.verify_missing_render(contaminated,rate,truth)
        self.assertIsNone(truth["lf_measurement_interval_seconds"])
        metrics=benchmark.signal_metrics(samples,samples,samples,rate,truth)
        self.assertIsNone(metrics["coherent_fundamental_gain_db"])

    def test_ladder_has_exact_nine_string_notes_and_pair_conditions(self):
        _,truth=self.signals("tuning-ladder")
        self.assertEqual([row["midi_notes"][0] for row in truth["pitch_regions"][::2]],[24,29,34,39,46,51,56,60,65])
        for clean,distorted in zip(truth["pitch_regions"][::2],truth["pitch_regions"][1::2]):
            self.assertEqual((clean["condition"],distorted["condition"]),("clean","tanh_distorted"))
            self.assertEqual(distorted["start_native_sample"]-clean["start_native_sample"],14400)
            self.assertEqual(distorted["end_native_sample"]-clean["start_native_sample"],28800)
        self.assertAlmostEqual(truth["pitch_regions"][8]["frequencies_hz"][0]/truth["pitch_regions"][6]["frequencies_hz"][0],2**(7/12))

    def test_analytic_ramp_integral_is_continuous_and_changes_local_period(self):
        self.assertAlmostEqual(bank.tempo_phase(1),178/60)
        self.assertAlmostEqual(bank.tempo_phase(11),(178+10*(178+210)/2)/60)
        for t in (0,.337,1,2.5,5,10.8,11,12):
            self.assertAlmostEqual(bank.tempo_time(bank.tempo_phase(t)),t,places=10)
        _,truth=self.signals("variable-tempo")
        times=truth["pulse_times_seconds"]
        self.assertGreater(times[1]-times[0],times[-1]-times[-2])
        self.assertIsNone(truth["bpm"])
        self.assertEqual(truth["warp_reference"]["mapping_kind"],"piecewise_linear")

    def test_generated_shifts_omission_and_addition_have_sample_exact_receipts(self):
        _,truth=self.signals("timing-errors")
        edits=truth["generated_score"]["events"]
        shifted=[row["injected_offset_seconds"] for row in edits if row["injected_edit"]=="injected_timing_shift"]
        for actual,expected in zip(shifted,[-.025,.025,-.06,.06]):
            self.assertAlmostEqual(actual,expected,delta=1/48000)
        omitted=next(row for row in edits if row["injected_edit"]=="omitted_attack")
        self.assertIsNone(omitted["onset_source_seconds"])
        self.assertIsNone(omitted["onset_native_sample"])
        self.assertEqual(sum(row["injected_edit"]=="extra_attack" for row in edits),1)
        self.assertTrue(any(row["articulation"]=="intentional_rest" for row in edits))

    def test_tuplets_legato_polyphony_and_click_overlap_keep_context(self):
        _,tuplets=self.signals("rest-syncopation-tuplets")
        denominators={row["beat_position"]["denominator"] for row in tuplets["generated_score"]["events"]}
        self.assertTrue({3,5,7}.issubset(denominators))
        _,legato=self.signals("legato-transition")
        self.assertTrue(legato["pitch_trajectories"])
        self.assertLess(len(legato["guitar_onsets_seconds"]),len(legato["generated_score"]["events"]))
        _,sweep=self.signals("sweep-and-polyphony")
        self.assertTrue(any(not row["monophonic"] for row in sweep["pitch_regions"]))
        signals,clicks=self.signals("click-overlap-abstention")
        self.assertTrue({"isolated","sustain_overlap","pick_overlap"}.issubset({row["overlap_class"] for row in clicks["click_events"]}))
        a,b=(round(t*48000) for t in clicks["click_only_template_seconds"])
        self.assertTrue(all(value==0 for component in ("clean","noise") for value in signals[component][a:b]))

    def test_maximum_matching_does_not_lose_feasible_events_or_hide_shifts(self):
        result=benchmark.event_metrics_v2([0,.030],[.020,.050],.021)
        self.assertEqual(result["matched_count"],2)
        self.assertEqual(result["f1"],1)
        self.assertEqual(benchmark.event_metrics_v2([1],[1.025],.02)["matched_count"],0)
        shifted=benchmark.event_metrics_v2([1],[.975,1.025],.05)
        self.assertEqual((shifted["matched_count"],shifted["false_positive_count"]),(1,1))
        self.assertAlmostEqual(abs(shifted["signed_offsets_seconds"][0]),.025)
        self.assertEqual(shifted["latency_calibration"],"none")
        self.assertIsNone(benchmark.event_metrics_v2([],[],.02)["f1"])


if __name__=="__main__":
    unittest.main()
