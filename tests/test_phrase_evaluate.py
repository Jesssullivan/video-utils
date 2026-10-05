import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
import wave
import contextlib
import io
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import phrase_evaluate as evaluate
import phrase_compare as compare


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value))
    return evaluate.digest(path)


def make_bank(root):
    """Small actual WAV + independently specified metadata; no mocked CLI output."""
    bank=root/"artifacts/benchmarks/fixture"
    bank.mkdir(parents=True)
    registry=root/"program/instrument.json"
    write(registry,{"string_count":9,"lowest_hz":32})
    waveform=bank/"source.wav"
    with wave.open(str(waveform),"wb") as handle:
        handle.setnchannels(1);handle.setsampwidth(2);handle.setframerate(8000)
        handle.writeframes(b"\0\0"*32000)
    source_hash=evaluate.digest(waveform)
    truth={"schema_version":2,"kind":"synthetic_generated_signal_and_score_truth",
           "ground_truth_scope":"generator_only_not_musician",
           "instrument_registry_sha256":evaluate.digest(registry),
           "source":{"path":"source.wav","sha256":source_hash,"sample_rate":8000,"channels":1,
                     "sample_count":32000,"duration_seconds":4,"audio_start_seconds":0,"origin_evidence":"generator"},
           "phrase_spans_seconds":[[0,2],[2,4]],"boundaries_seconds":[0,2,4],"recurrence_pairs":[],
           "generated_score":{"events":[{"articulation":"picked_attack","onset_source_seconds":1}]}}
    truth_hash=write(bank/"truth.json",truth)
    index={"schema_version":2,"suite":"technical-v2","case_count":1,"total_duration_seconds":4,
           "instrument_registry_sha256":evaluate.digest(registry),
           "cases":[{"id":"example","duration_seconds":4,"truth":"truth.json","truth_sha256":truth_hash}]}
    index_hash=write(bank/"fixtures.json",index)
    run=bank/"pilot/run"
    phrases={"source":{"sha256":source_hash},"analysis":{"backend":"fixture"},
             "observations":{"segment_candidates":[{"start_seconds":0,"end_seconds":2.025},
                 {"start_seconds":2.025,"end_seconds":4}],"recurrence_candidates":[]}}
    analysis={"source":{"sha256":source_hash},"analysis":{"backend":"fixture"},
              "events":[{"kind":"broadband_attack","audio_relative_seconds":1.025}]}
    phrase_hash=write(run/"phrases.json",phrases)
    analysis_hash=write(run/"analysis.json",analysis)
    pilot={"schema_version":1,"bank_index_sha256":index_hash,"instrument_registry_sha256":evaluate.digest(registry),
           "cases":[{"id":"example","run_dir":"run","phrases":{"path":"run/phrases.json","sha256":phrase_hash},
                     "analysis":{"path":"run/analysis.json","sha256":analysis_hash},"comparisons":None}]}
    write(bank/"pilot/phrase-pilot-index.json",pilot)
    return bank/"fixtures.json",bank/"pilot/phrase-pilot-index.json"


class MetricTests(unittest.TestCase):
    def test_duplicate_predictions_one_to_one_oracle(self):
        result=evaluate.boundaries([1,2],[.98,1.02,2],3,.05)
        self.assertEqual((result["tp"],result["fp"],result["fn"]),(2,1,0))
        self.assertAlmostEqual(result["precision"],2/3)
        self.assertEqual(result["recall"],1)
        self.assertEqual(result["f1"],.8)

    def test_greedy_counterexample_and_minimum_displacement(self):
        result=evaluate.boundaries([.1,.13],[.12,.15],1,.021)
        self.assertEqual(result["tp"],2)
        result=evaluate.boundaries([1],[.99,1.04],3,.05)
        self.assertAlmostEqual(result["matches"][0]["estimate_seconds"],.99)

    def test_windows_endpoints_and_empty(self):
        self.assertEqual([evaluate.boundaries([1],[1.025],2,t)["tp"] for t in (.02,.05,.1)],[0,1,1])
        self.assertEqual([evaluate.boundaries([1],[1.101],2,t)["tp"] for t in (.02,.05,.1)],[0,0,0])
        self.assertIsNone(evaluate.boundaries([0,2],[0,2],2,.05)["f1"])
        missing=evaluate.boundaries([1],[],2,.05)
        self.assertEqual((missing["f1"],missing["fn"]),(0,1))
        false=evaluate.boundaries([],[1],2,.05)
        self.assertEqual((false["fp"],false["recall"]),(1,0))

    def test_span_iou_oracles_and_duplicate_credit(self):
        self.assertAlmostEqual(evaluate.iou([1,3],[2,4]),1/3)
        self.assertEqual(evaluate.span_metrics([[1,3]],[[2,4]],5,.5)["tp"],0)
        self.assertEqual(evaluate.span_metrics([[1,3]],[[1.2,3.2]],5,.75)["tp"],1)
        result=evaluate.span_metrics([[0,2],[2,4]],[[0,4]],4,.5)
        self.assertEqual((result["tp"],result["fn"]),(1,1))

    def test_ordered_recurrence_pair_does_not_swap_credit(self):
        ref={"first_span_seconds":[0,1],"second_span_seconds":[2,3]}
        swap={"first_span_seconds":[2,3],"second_span_seconds":[0,1]}
        self.assertEqual(evaluate.recurrence_metrics([ref],[swap],4,.5)["tp"],0)

    def alignment(self,mapping="affine",path=None):
        ref={"first_span_seconds":[0,2],"second_span_seconds":[3,5],"warp_reference":{
            "source_times_seconds":[0,.5,1,1.5,2],"target_times_seconds":[3.1,3.5,3.9,4.3,4.7],"mapping_kind":mapping}}
        prediction={"status":"aligned_hypothesis","spans":{"first_start_seconds":0,"first_end_seconds":2,
                    "second_start_seconds":3,"second_end_seconds":5},"median_relative_offset_seconds":-.1,
                    "interior_rate_median":.8,"path_audio_relative_seconds":path or [
                    {"first_seconds":x,"second_seconds":y} for x,y in zip(ref["warp_reference"]["source_times_seconds"],ref["warp_reference"]["target_times_seconds"])]}
        return ref,prediction

    def test_affine_oracle_raw_warped_rate_and_concealment(self):
        ref,pred=self.alignment()
        result=evaluate.alignment_metrics(ref,pred,6)
        self.assertAlmostEqual(result["reference_relative_shift_seconds"],.1)
        self.assertAlmostEqual(result["reference_affine_rate"],.8)
        self.assertLess(result["absolute_ratio_error"],1e-12)
        self.assertLess(result["warped_landmark_error"]["mean_absolute_seconds"],1e-12)
        self.assertTrue(result["dtw_absorbed_generated_timing_change"])
        self.assertEqual(len(result["raw_prewarp_landmark_offsets_seconds"]),5)

    def test_piecewise_and_uncovered_no_extrapolation(self):
        ref,pred=self.alignment("piecewise_linear",[{"first_seconds":.5,"second_seconds":3.5},{"first_seconds":1.5,"second_seconds":4.3}])
        result=evaluate.alignment_metrics(ref,pred,6)
        self.assertIsNone(result["reference_affine_rate"])
        self.assertEqual(result["covered_landmark_count"],3)
        self.assertEqual(result["landmark_coverage"],.6)
        self.assertIsNone(result["piecewise_interval_rates"][0]["estimated_rate"])
        pred["status"]="no_valid_constrained_path"
        result=evaluate.alignment_metrics(ref,pred,6)
        self.assertEqual(result["covered_landmark_count"],0)
        self.assertIsNone(result["warped_landmark_error"]["mean_absolute_seconds"])

    def test_uncovered_change_is_not_claimed_as_dtw_absorption(self):
        ref={"first_span_seconds":[0,2],"second_span_seconds":[3,5],"warp_reference":{
            "source_times_seconds":[0,1,2],"target_times_seconds":[3,4,4.8],"mapping_kind":"piecewise_linear"}}
        pred={"status":"aligned_hypothesis","spans":{"first_start_seconds":0,"first_end_seconds":2,
            "second_start_seconds":3,"second_end_seconds":5},"path_audio_relative_seconds":[
            {"first_seconds":0,"second_seconds":3},{"first_seconds":.5,"second_seconds":3.5}]}
        result=evaluate.alignment_metrics(ref,pred,6)
        self.assertEqual(result["landmark_coverage"],1/3)
        self.assertFalse(result["dtw_absorbed_generated_timing_change"])
        self.assertEqual(result["timing_change_coverage"]["covered_changed_landmark_count"],0)
        self.assertEqual(result["timing_change_coverage"]["status"],"unknown_generated_change_outside_path_support")

    def test_invalid_and_bounded_metric_inputs(self):
        with self.assertRaises(ValueError):evaluate.boundaries([math.nan],[],4,.05)
        with self.assertRaises(ValueError):evaluate.span_metrics([[2,1]],[],4,.5)
        with self.assertRaises(ValueError):evaluate.boundaries(list(range(513)),[],600,.05)
        ref,pred=self.alignment()
        pred["path_audio_relative_seconds"].reverse()
        with self.assertRaises(ValueError):evaluate.alignment_metrics(ref,pred,6)

    def test_portable_json_depth_and_overflow(self):
        for text in ('{"x":1e400}','{"x":NaN}','{"x":1,"x":2}','['*129+'0'+']'*129):
            with self.assertRaises(ValueError):evaluate.guarded_json(text)
        self.assertEqual(evaluate.guarded_json('{"x":"[[\\\"}]]"}'),{"x":'[["}]]'})

    def test_unsupported_claim_counter(self):
        self.assertEqual(evaluate.unsupported_claims({"flags":[{"performance_issue_confirmed":True}],"performance_grade":"perfect"}),2)
        self.assertEqual(evaluate.unsupported_claims({"performance_grade":"not_graded","flags":[{"performance_issue_confirmed":False}]}),0)


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name).resolve()
        self.patch=patch.object(evaluate,"ROOT",self.root)
        self.patch.start()
        self.index,self.pilot=make_bank(self.root)

    def tearDown(self):
        self.patch.stop();self.temp.cleanup()

    def update_truth(self,changes):
        truth_path=self.index.parent/"truth.json"
        data=json.loads(truth_path.read_text());changes(data)
        truth_hash=write(truth_path,data)
        index=json.loads(self.index.read_text());index["cases"][0]["truth_sha256"]=truth_hash
        index_hash=write(self.index,index)
        pilot=json.loads(self.pilot.read_text());pilot["bank_index_sha256"]=index_hash;write(self.pilot,pilot)

    def test_small_bank_full_validation_visible_baseline(self):
        result=evaluate.evaluate(self.index,self.pilot)
        self.assertTrue(result["source_read"])
        self.assertFalse(result["source_audio_decoded"])
        self.assertEqual(result["fixture_count"],1)
        self.assertEqual(result["fixtures"][0]["boundary_metrics"][0]["f1"],0)
        self.assertEqual(result["fixtures"][0]["boundary_metrics"][1]["f1"],1)
        self.assertTrue(result["hard_gates_passed"])

    def test_stale_artifact_and_settings_hash_reject(self):
        file=self.pilot.parent/"run/analysis.json"
        data=json.loads(file.read_text());data["events"]=[]
        file.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,"hash mismatch"):evaluate.evaluate(self.index,self.pilot)
        pilot=json.loads(self.pilot.read_text());pilot["cases"][0]["analysis"]["sha256"]=evaluate.digest(file)
        data["settings_sha256"]="0"*64
        write(file,data);pilot["cases"][0]["analysis"]["sha256"]=evaluate.digest(file);write(self.pilot,pilot)
        with self.assertRaisesRegex(ValueError,"settings hash"):evaluate.evaluate(self.index,self.pilot)

    def test_native_extent_source_identity_context_and_duplicate_keys(self):
        source=self.index.parent/"source.wav"
        source.write_bytes(source.read_bytes()+b"changed")
        with self.assertRaisesRegex(ValueError,"source hash"):evaluate.evaluate(self.index,self.pilot)
        self.pilot.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaisesRegex(ValueError,"Duplicate"):evaluate.evaluate(self.index,self.pilot)

    def test_path_escape_symlink_and_new_output(self):
        with self.assertRaises(ValueError):evaluate.local_path("../outside",self.index.parent)
        link=self.index.parent/"linked.json";link.symlink_to(self.index)
        with self.assertRaises(ValueError):evaluate.local_path(link)
        with self.assertRaises(ValueError):evaluate.local_path(self.index.parent,new=True)
        with self.assertRaises(ValueError):evaluate.local_path(self.root/"outside")

    def test_claims_visible_and_fail_hard_gate(self):
        path=self.pilot.parent/"run/phrases.json"
        data=json.loads(path.read_text());data["performance_issue_confirmed"]=True
        write(path,data)
        pilot=json.loads(self.pilot.read_text());pilot["cases"][0]["phrases"]["sha256"]=evaluate.digest(path);write(self.pilot,pilot)
        result=evaluate.evaluate(self.index,self.pilot)
        self.assertFalse(result["hard_gates_passed"])
        self.assertEqual(result["unsupported_confirmed_claim_count"],1)
        output=self.index.parent/"failed-evaluation"
        stdout=io.StringIO()
        stderr=io.StringIO()
        with patch.object(sys,"argv",["phrase_evaluate","--fixture-index",str(self.index),"--pilot-index",str(self.pilot),"--output",str(output),"--summary"]),contextlib.redirect_stdout(stdout),contextlib.redirect_stderr(stderr):
            self.assertEqual(evaluate.main(),1)
        summary=json.loads(stdout.getvalue())
        self.assertEqual(summary["status"],"generated_fixture_calibration_failed_hard_gates")
        self.assertTrue((output/"phrase-evaluation.json").is_file())
        self.assertIn("diagnostic receipt retained",stderr.getvalue())

    def test_native_extent_and_unmatched_bad_warp_reject(self):
        self.update_truth(lambda data:data["source"].update(sample_count=31999))
        with self.assertRaisesRegex(ValueError,"extent"):evaluate.evaluate(self.index,self.pilot)
        self.update_truth(lambda data:data["source"].update(sample_count=32000))
        self.update_truth(lambda data:data.update(recurrence_pairs=[{"first_span_seconds":[0,1],"second_span_seconds":[2,3],
            "warp_reference":{"source_times_seconds":[0,1],"target_times_seconds":[3,2],"mapping_kind":"affine"}}]))
        with self.assertRaisesRegex(ValueError,"monotonic"):evaluate.evaluate(self.index,self.pilot)

    def test_explicit_nonpicked_reference_keeps_false_positives(self):
        self.update_truth(lambda data:data["generated_score"].update(events=[{"articulation":"pitch_transition","onset_source_seconds":1}]))
        result=evaluate.evaluate(self.index,self.pilot)
        self.assertEqual(result["fixtures"][0]["attack_detection_metrics"][1]["fp"],1)
        self.assertEqual(result["attack_aggregate"][1]["fp"],1)

    def test_null_semantic_refs_excluded_not_false_zero(self):
        self.update_truth(lambda data:data.update(phrase_spans_seconds=None,boundaries_seconds=None))
        result=evaluate.evaluate(self.index,self.pilot)
        self.assertIsNone(result["fixtures"][0]["span_metrics"])
        self.assertIsNone(result["fixtures"][0]["boundary_metrics"])
        self.assertEqual(result["boundary_aggregate"][0]["excluded_fixture_count"],1)

    def test_count_duration_and_metadata_budgets_reject(self):
        index=json.loads(self.index.read_text());index["case_count"]=13
        index_hash=write(self.index,index)
        pilot=json.loads(self.pilot.read_text());pilot["bank_index_sha256"]=index_hash;write(self.pilot,pilot)
        with self.assertRaisesRegex(ValueError,"count"):evaluate.evaluate(self.index,self.pilot)
        index["case_count"]=1;index["total_duration_seconds"]=121
        index_hash=write(self.index,index);pilot["bank_index_sha256"]=index_hash;write(self.pilot,pilot)
        with self.assertRaisesRegex(ValueError,"duration"):evaluate.evaluate(self.index,self.pilot)
        with patch.dict(evaluate.LIMITS,json_bytes=1):
            with self.assertRaisesRegex(ValueError,"budget"):evaluate.evaluate(self.index,self.pilot)

    def test_complete_score_native_event_binding(self):
        self.update_truth(lambda data:data["generated_score"].update(status="complete_generated_score",
            events=[{"id":"picked1","articulation":"picked_attack","onset_native_sample":8000,"onset_source_seconds":1.01}]))
        with self.assertRaisesRegex(ValueError,"axes disagree"):evaluate.evaluate(self.index,self.pilot)

    def test_changed_opaque_discovery_input_rejects(self):
        alias=self.pilot.parent/"run/audio-01.wav"
        alias.write_bytes((self.index.parent/"source.wav").read_bytes()+b"changed")
        artifact=self.pilot.parent/"run/analysis.json"
        data=json.loads(artifact.read_text());data["source"]["path"]=str(alias)
        identity=write(artifact,data)
        pilot=json.loads(self.pilot.read_text());pilot["cases"][0]["analysis"]["sha256"]=identity;write(self.pilot,pilot)
        with self.assertRaisesRegex(ValueError,"audio input changed"):evaluate.evaluate(self.index,self.pilot)


class FeatureSmokeTests(unittest.TestCase):
    def smoke(self,rate=1,shift=0,legato=False,omit=False):
        from test_phrase_compare import fixture
        pair,times,vectors=fixture(rate=rate,shift=shift,omitted=omit,articulation_hint="legato" if legato else None)
        result=compare.compare_pair(pair,times,vectors,compare.validate_settings())
        return result

    def test_shift_and_rate_bounded_feature_smoke(self):
        shifted=self.smoke(shift=.1)
        self.assertAlmostEqual(shifted["median_relative_offset_seconds"],.1,delta=.03)
        compressed=self.smoke(rate=.8)
        self.assertAlmostEqual(compressed["interior_rate_median"],.8,delta=.08)

    def test_qualified_omit_vs_legato_abstention(self):
        qualified=self.smoke(omit=True)
        self.assertEqual(qualified["motif_comparison"]["status"],"attack_edit_review_hypotheses")
        legato=self.smoke(omit=True,legato=True)
        self.assertEqual(legato["motif_comparison"]["status"],"attack_edits_abstained")
        self.assertFalse(any(x["performance_issue_confirmed"] for x in legato["flags"]))


if __name__=="__main__":unittest.main()
