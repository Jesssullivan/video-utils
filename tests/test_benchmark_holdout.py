"""Admission, independent recipe and one-case construction integrity checks."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("benchmark_holdout",ROOT/"scripts/benchmark_holdout.py")
holdout=importlib.util.module_from_spec(spec)
spec.loader.exec_module(holdout)


class HoldoutTests(unittest.TestCase):
    def setUp(self):
        holdout.ARTIFACTS.mkdir(parents=True,exist_ok=True)
        self.temporary=tempfile.TemporaryDirectory(prefix="holdout-tests-",dir=holdout.ARTIFACTS)
        self.folder=Path(self.temporary.name)
        self.plan_path=self.folder/"plan.json"
        self.plan=holdout.make_plan()
        holdout.write_new(self.plan_path,self.plan)

    def tearDown(self):
        self.temporary.cleanup()

    def test_known_digest_integer_and_parameter_arithmetic(self):
        self.assertEqual(holdout.knob_bytes(211,"timing-pair","phrase_phase").hex(),
                         "e5546e9f6f28e6d278f1ae93b0c53ec740f180af1312d9d0da41467341047951")
        self.assertEqual(holdout.parameters(211,"timing-errors")["first_motif_start_seconds"],
                         .6+.3*(3847515807/4294967296))
        self.assertEqual(holdout.parameters(307,"low32-sustain")["noise_stream_seed"],12802149519597717092)

    def test_exact_budget_both_held_out_and_paired_nuisance(self):
        cases=self.plan["design"]["cases"]
        self.assertEqual(len(cases),12)
        self.assertEqual(sum(row["duration_seconds"] for row in cases),120)
        self.assertEqual(self.plan["role"],"both_seeds_withheld_from_setting_selection")
        self.assertEqual(self.plan["design"]["seeds"],[211,307])
        for seed in (211,307):
            self.assertEqual(holdout.parameters(seed,"timing-reference"),holdout.parameters(seed,"timing-errors"))

    def test_known_admitted_byte_hash_and_validator_read_only(self):
        before=self.plan_path.read_bytes()
        _,digest=holdout.validate_plan(self.plan_path)
        self.assertEqual(digest,"495ad2f3f553b0bd7030ac797b6e8589f37748df657219c075d0fc4ce7491e74")
        self.assertEqual(before,self.plan_path.read_bytes())

    def test_parameter_budget_role_dependency_and_type_tampering_rejected(self):
        mutations=[lambda p:p["design"]["cases"][0]["parameters"].update(guitar_gain=.1),
                   lambda p:p.update(total_duration_seconds=121),lambda p:p.update(role="exploratory"),
                   lambda p:p["published_dependencies"].update({"scripts/benchmark.py":"0"*64}),
                   lambda p:p.update(schema_version=True),lambda p:p.update(case_count=12.0)]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                value=copy.deepcopy(self.plan);mutate(value)
                self.plan_path.write_bytes(holdout.canonical(value))
                with self.assertRaises(ValueError):
                    holdout.validate_plan(self.plan_path)

    def test_duplicate_nonfinite_and_oversized_json_rejected(self):
        for raw in (b'{"a":1,"a":2}',b'{"x":NaN}',b' '*1_000_001):
            self.plan_path.write_bytes(raw)
            with self.assertRaises(ValueError):
                holdout.validate_plan(self.plan_path)

    def test_unsafe_paths_and_overwrite_rejected(self):
        for path in (ROOT/"outside.json",self.folder/".."/"escape.json"):
            with self.assertRaises(ValueError):
                holdout.local_path(path)
        alias=self.folder/"alias";alias.symlink_to(self.plan_path)
        with self.assertRaises(ValueError):
            holdout.validate_plan(alias)
        with self.assertRaises(FileExistsError):
            holdout.write_new(self.plan_path,self.plan)

    def test_revision_nonadmitted_bytes_and_unregistered_proof_rejected(self):
        with patch.object(holdout,"dependency_receipts",return_value={}):
            with self.assertRaises(ValueError):
                holdout.validate_plan(self.plan_path)
        self.plan_path.write_text(json.dumps(self.plan,indent=2))
        with self.assertRaisesRegex(ValueError,"exact root-admitted"):
            holdout.proof(self.plan_path,"seed211-timing-errors",self.folder/"proof")
        self.plan_path.write_bytes(holdout.canonical(self.plan)+b"\n")
        with self.assertRaisesRegex(ValueError,"registered timing-errors"):
            holdout.proof(self.plan_path,"seed211-low32-sustain",self.folder/"proof")

    def test_deadline_and_timestamp_mismatch_rejected_without_waveforms(self):
        case=next(c for c in self.plan["design"]["cases"] if c["id"]=="seed211-timing-errors")
        with self.assertRaisesRegex(ValueError,"deadline"):
            holdout.render_timing_case(case,time.monotonic()-1)
        minimal={"sample_rate":48000,"sample_count":480000,"audio_start_seconds":0.0,
                 "generated_score":{"events":[{"id":"e","ideal_onset_native_sample":48000,"ideal_onset_seconds":1.0,
                    "onset_native_sample":48001,"onset_source_seconds":1.0,"injected_edit":None,"duration_samples":100}]},
                 "click_events":[],"phrase_spans_seconds":[]}
        with self.assertRaisesRegex(ValueError,"timestamp mismatch"):
            holdout.verify_timestamps(minimal)

    def test_one_generated_score_matches_rendered_pcm_and_truth_receipts(self):
        before=holdout.dependency_receipts()
        result=holdout.proof(self.plan_path,"seed211-timing-errors",self.folder/"proof")
        truth=json.loads((self.folder/"proof"/"truth.json").read_text())
        self.assertEqual(result["case_count"],1)
        self.assertFalse(result["inference_executed"])
        self.assertLessEqual(result["checks"]["max_mix_error_pcm16_lsb"],2)
        self.assertEqual(truth["ground_truth_scope"],"generator_only_not_musician")
        events=truth["generated_score"]["events"]
        shifts=[row["onset_native_sample"]-row["ideal_onset_native_sample"] for row in events if row["injected_edit"]=="injected_timing_shift"]
        self.assertEqual(shifts,[1200,-1200,2880,-2880])
        omitted=[row for row in events if row["injected_edit"]=="omitted_attack"]
        self.assertEqual(len(omitted),1);self.assertIsNone(omitted[0]["onset_source_seconds"])
        self.assertEqual(len([row for row in events if row["injected_edit"]=="extra_attack"]),1)
        for row in truth["pitch_regions"]:
            self.assertTrue(any(a<=row["start_seconds"]<row["end_seconds"]<=b for a,b in truth["phrase_spans_seconds"]))
        # Native samples prove the intentionally omitted attack is actually silent,
        # and the separately declared extra attack is physically rendered.
        import array,wave,sys
        with wave.open(str(self.folder/"proof"/"clean.wav"),"rb") as stream:
            samples=array.array("h");samples.frombytes(stream.readframes(480000))
        if sys.byteorder!="little": samples.byteswap()
        index=omitted[0]["ideal_onset_native_sample"]
        self.assertEqual(max(abs(x) for x in samples[index:index+400]),0)
        extra=next(row for row in events if row["injected_edit"]=="extra_attack")
        index=extra["onset_native_sample"]
        self.assertGreater(max(abs(x) for x in samples[index:index+400]),100)
        changed=copy.deepcopy(truth);changed["source"]["audio_start_seconds"]=.1
        with self.assertRaisesRegex(ValueError,"source receipt"):
            holdout.verify_components(self.folder/"proof",changed)
        target=self.folder/"proof"/"click.wav";raw=target.read_bytes();target.write_bytes(raw[:-2]+b"xx")
        with self.assertRaisesRegex(ValueError,"path/hash"):
            holdout.verify_components(self.folder/"proof",truth)
        self.assertEqual(before,holdout.dependency_receipts())

    def mock_case_rows(self):
        """Metadata-only receipts for aggregator tests, never synthetic audio."""
        rows=[]
        for definition in self.plan["design"]["cases"]:
            identity=definition["id"]
            components={name:{"path":f"{identity}/{name}.wav","sha256":"a"*64,"bytes":960044,
                              "sample_rate":48000,"channels":1,"sample_count":480000,"duration_seconds":10}
                        for name in ("clean","click","noise","mix")}
            rows.append({"id":identity,"seed":definition["seed"],"cohort":definition["cohort"],"duration_seconds":10,
                         "components":components,"source":dict(components["mix"],audio_start_seconds=0.0,
                           origin_evidence={"status":"known_generated_native_sample_zero","scope":"generated_file_only"}),
                         "truth":{"path":f"{identity}/truth.json","sha256":"b"*64}})
        return rows

    def test_full_budget_and_deadline_reject_before_creating_output(self):
        for bound in (0,-1,601,True,1.0):
            with self.subTest(bound=bound),self.assertRaises(ValueError):
                holdout.generate(self.plan_path,self.folder/"not-created",bound)
        self.assertFalse((self.folder/"not-created").exists())
        for mutate in (lambda p:p["design"]["cases"].pop(),lambda p:p["design"]["cases"][0].update(duration_seconds=11)):
            value=copy.deepcopy(self.plan);mutate(value)
            with self.assertRaises(ValueError): holdout.generation_budget(value,600)

    def test_metadata_only_aggregate_requires_complete_ordered_native_receipts(self):
        rows=self.mock_case_rows()
        index=holdout.aggregate_index(self.plan,holdout.ADMITTED_PLAN_SHA256,"c"*64,rows,.5)
        self.assertEqual(index["wave_component_count"],48)
        self.assertEqual(index["total_duration_seconds"],120)
        self.assertFalse(index["inference_executed"])
        self.assertEqual(index["max_wave_bytes"],46_082_112)
        mutations=[lambda r:r.pop(),lambda r:r.reverse(),lambda r:r[0]["components"].pop("noise"),
                   lambda r:r[0]["components"]["clean"].update(sample_count=480001),
                   lambda r:r[0]["components"]["clean"].update(path="../clean.wav"),
                   lambda r:r[0]["truth"].update(sha256="bad"),lambda r:r[0]["source"].update(audio_start_seconds=.1)]
        for mutate in mutations:
            changed=copy.deepcopy(rows);mutate(changed)
            with self.subTest(mutation=mutate),self.assertRaises(ValueError):
                holdout.aggregate_index(self.plan,holdout.ADMITTED_PLAN_SHA256,"c"*64,changed,.5)
        with self.assertRaises(ValueError):
            holdout.aggregate_index(self.plan,holdout.ADMITTED_PLAN_SHA256,"c"*64,rows,600.01)

    def test_mock_serial_generation_aggregation_never_renders_audio(self):
        rows=self.mock_case_rows()
        render_calls=[]
        def fake_render(case,deadline):
            render_calls.append(case["id"])
            return {},{}
        with patch.object(holdout,"render_case",side_effect=fake_render),patch.object(holdout,"save_case",side_effect=rows):
            result=holdout.generate(self.plan_path,self.folder/"mock-success")
        self.assertEqual(render_calls,[row["id"] for row in rows])
        self.assertEqual(result["case_count"],12)
        self.assertEqual(list((self.folder/"mock-success").iterdir()),[self.folder/"mock-success"/"fixtures.json"])
        self.assertEqual(holdout.sha((self.folder/"mock-success"/"fixtures.json").read_bytes()),result["fixtures_sha256"])

    def test_partial_generation_failure_receipt_never_claims_success(self):
        rows=self.mock_case_rows()
        with patch.object(holdout,"render_case",side_effect=[({},{}),ValueError("independent construction failure")]),patch.object(holdout,"save_case",return_value=rows[0]):
            with self.assertRaisesRegex(ValueError,"construction failure"):
                holdout.generate(self.plan_path,self.folder/"mock-failure")
        failure=json.loads((self.folder/"mock-failure"/"failure.json").read_bytes())
        self.assertEqual(failure["status"],"failed_structural_generation")
        self.assertEqual(failure["completed_case_count"],1)
        self.assertEqual(failure["completed_source_seconds"],10)
        self.assertFalse(failure["successful_aggregate_index"])
        self.assertFalse((self.folder/"mock-failure"/"fixtures.json").exists())

    def test_expired_generation_receipt_does_not_invoke_case_renderer(self):
        with patch.object(holdout,"generation_budget",return_value=time.monotonic()-1),patch.object(holdout,"render_case") as renderer:
            with self.assertRaisesRegex(ValueError,"deadline"):
                holdout.generate(self.plan_path,self.folder/"mock-deadline")
        renderer.assert_not_called()
        failure=json.loads((self.folder/"mock-deadline"/"failure.json").read_bytes())
        self.assertEqual(failure["completed_case_count"],0)


if __name__=="__main__":
    unittest.main()
