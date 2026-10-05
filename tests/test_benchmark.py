"""Independent synthetic truth and failure-mode checks for benchmark metrics."""
import importlib.util
import math
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("benchmark",ROOT/"scripts"/"benchmark.py")
benchmark=importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


class BenchmarkTests(unittest.TestCase):
    def temporary(self):
        (ROOT/".cache").mkdir(exist_ok=True)
        return tempfile.TemporaryDirectory(dir=ROOT/".cache")

    def test_uniform_gain_is_not_noise_reduction(self):
        rate=4000
        clean=[.2*math.sin(2*math.pi*32*i/rate) if i>=rate//4 else 0 for i in range(rate)]
        noisy=[x+.01*math.sin(2*math.pi*531*i/rate) for i,x in enumerate(clean)]
        truth={"fundamental_hz":32,"lf_measurement_interval_seconds":[.3,.9],"noise_only_intervals_seconds":[[0,.2]]}
        metrics=benchmark.signal_metrics(clean,noisy,[x*3 for x in noisy],rate,truth)
        self.assertAlmostEqual(metrics["quiet_regions"][0]["gain_adjusted_noise_change_db"],0,places=8)
        self.assertAlmostEqual(metrics["before"]["gain_adjusted_mse"],metrics["after"]["gain_adjusted_mse"],places=12)

    def test_low32_damage_is_detected_despite_retained_harmonic(self):
        rate=4000
        low=[.2*math.sin(2*math.pi*32*i/rate) for i in range(rate)]
        harmonic=[.1*math.sin(2*math.pi*96*i/rate) for i in range(rate)]
        original=[a+b for a,b in zip(low,harmonic)]
        damaged=[.1*a+b for a,b in zip(low,harmonic)]
        truth={"fundamental_hz":32,"lf_measurement_interval_seconds":[0,1],"noise_only_intervals_seconds":[]}
        result=benchmark.signal_metrics(original,original,damaged,rate,truth)
        self.assertAlmostEqual(result["coherent_fundamental_gain_db"],-20,places=6)
        with self.assertRaisesRegex(ValueError,"extent"):
            benchmark.signal_metrics(original,original,damaged[:-1],rate,truth)

    def test_event_matching_has_no_duplicate_credit_or_latency_correction(self):
        metrics=benchmark.event_metrics([1,2,3],[1.01,1.015,2.01,3.1],.02)
        self.assertEqual(metrics["matched_count"],2)
        self.assertEqual(metrics["false_positive_count"],2)
        self.assertEqual(metrics["missed_count"],1)
        self.assertAlmostEqual(metrics["signed_offsets_seconds"][0],.01)
        self.assertEqual(metrics["latency_calibration"],"none")

    def test_shifted_phrase_region_is_not_exact_recurrence(self):
        expected=[[1,2],[4,5]]
        correct={"first_start_seconds":1,"first_end_seconds":2,"second_start_seconds":4,"second_end_seconds":5}
        shifted=dict(correct,second_start_seconds=4.75,second_end_seconds=5.75)
        self.assertEqual(benchmark.recurrence_metrics(expected,[correct])["best_pair_overlap"],1)
        self.assertLess(benchmark.recurrence_metrics(expected,[shifted])["best_pair_overlap"],.2)

    def test_signal_components_and_repeat_truth(self):
        config=benchmark.configuration()
        for definition in config["fixtures"]:
            signals,truth=benchmark.fixture_signals(definition,config)
            self.assertEqual(len(signals["mix"]),384000)
            self.assertLess(max(abs(x) for x in signals["mix"]),1)
            for index in (0,14400,48000,96000,288000):
                self.assertAlmostEqual(signals["mix"][index],sum(signals[k][index] for k in ("clean","click","noise")))
            self.assertTrue(all(x==0 for x in signals["clean"][:12000]))
            if definition["kind"]=="sustain":
                self.assertAlmostEqual(benchmark.amplitude(signals["clean"],48000,32,[2,6]),.16,places=6)
            else:
                first,second=truth["repeated_regions_seconds"]
                for offset in (.025,.075,.2,.4,.8):
                    self.assertAlmostEqual(signals["clean"][round((first[0]+offset)*48000)],signals["clean"][round((second[0]+offset)*48000)],places=8)

    def test_hash_tamper_rejected_and_output_paths_bounded(self):
        with self.temporary() as temporary:
            path=Path(temporary)/"artifact.json"
            path.write_text('{"status":"original"}')
            original=benchmark.digest(path)
            path.write_text('{"status":"changed"}')
            with self.assertRaisesRegex(ValueError,"hash mismatch"):
                benchmark.audit_artifact(path,original)
            with self.assertRaisesRegex(ValueError,"beneath"):
                benchmark.destination(Path(temporary)/"outside")

    def test_owned_worker_timeout_is_stopped_with_receipt(self):
        with self.temporary() as temporary:
            receipt={}
            with self.assertRaisesRegex(ValueError,"deadline"):
                benchmark.invoke([sys.executable,"-c","import time; print('started', flush=True); time.sleep(30)"],Path(temporary),.1,4096,receipt)
            self.assertEqual(receipt["process_receipt"]["result"],"terminated")
            self.assertEqual(receipt["process_receipt"]["ruling"],"R-HOOK-CONVERGENCE-20261004/R-N11")
            with self.assertRaises(ProcessLookupError):
                os.kill(receipt["process_receipt"]["pid"],0)


if __name__=="__main__":
    unittest.main()
