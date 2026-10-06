import hashlib
import importlib.util
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result
learned=module("learned_eval",ROOT/"scripts/learned_pitch_evaluate.py")
fixtures=module("pyin_eval_fixture",ROOT/"tests/test_pitch_evaluate.py")

def npy(values,shape,dtype="<f8"):
    header=repr({"descr":dtype,"fortran_order":False,"shape":shape}).encode("latin1")
    header+=b" "*((-(10+len(header)+1))%64)+b"\n"
    fmt={"<f8":"d","<f4":"f","<i4":"i"}[dtype]
    return b"\x93NUMPY\x01\x00"+struct.pack("<H",len(header))+header+struct.pack("<"+fmt*len(values),*values)

def put_npz(path,arrays):
    with zipfile.ZipFile(path,"w",compression=zipfile.ZIP_DEFLATED) as archive:
        for name,value in arrays.items():archive.writestr("excerpt_0_"+name+".npy",value)
    return fixtures.digest(path)

def create_fixture(directory):
    """Independent structural smoke: generated WAVs, constructed model arrays.

    Deliberately wrong C2 activation for missing-C1 truth must remain a visible
    octave failure; this is not execution of Basic Pitch or its accuracy score.
    """
    bank_path,pyin_path=fixtures.create_valid_fixture(directory)
    bank=json.loads(bank_path.read_text());pyin=json.loads(pyin_path.read_text())
    jobs=[]
    for job in pyin["jobs"]:
        truth_path=Path(job["truth_path"]);truth=json.loads(truth_path.read_text())
        hz=truth["pitch_regions"][0]["frequencies_hz"][0]
        truth["generated_score"]={"events":[{"id":"generated-sustain","onset_source_seconds":0.,"onset_native_sample":0,
            "duration_samples":truth["source"]["sample_count"],"frequencies_hz":[hz],"articulation":"sustain"}]}
        job["truth_sha256"]=fixtures.put_json(truth_path,truth)
        next(case for case in bank["cases"] if case["id"]==job["case_id"])["truth_sha256"]=job["truth_sha256"]
        duration=job["requested_budget_seconds"];n=math.floor(duration*86)
        midi=36 if job["case_id"]=="c1-missing-fundamental" else 57
        note=[.8 if k==midi-21 else .01 for i in range(n) for k in range(88)]
        onset=[.1]*(n*88);contour=[.1]*(n*264)
        arrays={"note":npy(note,(n,88)),"onset":npy(onset,(n,88)),"contour":npy(contour,(n,264)),
            "model_times_seconds":npy([learned.model_time(i) for i in range(n)],(n,)),
            "nominal_times_seconds":npy([i*256/22050 for i in range(n)],(n,)),
            "input_window_projection_seconds":npy([learned.projection_time(i) for i in range(n)],(n,)),
            "window_index":npy([i//142 for i in range(n)],(n,),"<i4"),
            "window_frame_index":npy([i%142+15 for i in range(n)],(n,),"<i4")}
        run=Path(job["pitch_path"]).parent/"learned";run.mkdir()
        raw=run/"activations.npz";raw_hash=put_npz(raw,arrays)
        count=round(duration*22050);windows=[]
        for w in range(math.ceil((count+3840)/36164)):
            first=w*36164-3840
            windows.append({"window_index":w,"padded_start_sample":w*36164,"unpadded_start_sample":first,
                "input_context_start_seconds_in_excerpt":max(0,first)/22050,
                "input_context_end_seconds_in_excerpt":min(count,first+43844)/22050,
                "leading_zero_samples":max(0,-first),"trailing_zero_samples":max(0,first+43844-count),
                "output_frames_before_crop":172,"cropped_frames_each_side":15,"retained_frames":142})
        event={"start_frame":0,"end_frame_exclusive":n,"midi_candidate":midi,"model_start_seconds":0.,
            "model_end_seconds":learned.model_time(n),"nominal_start_seconds":0.,"nominal_end_seconds":n*256/22050,
            "input_window_projection_start_seconds":0.,"input_window_projection_end_seconds":learned.projection_time(n-1)+256/22050,
            "audio_relative_start_seconds":0.,"audio_relative_end_seconds":min(duration,learned.model_time(n)),
            "source_start_seconds":0.,"source_end_seconds":min(duration,learned.model_time(n)),
            "mean_note_activation":.8,"maximum_onset_activation":.1,"touches_excerpt_boundary":True,
            "intended_note":None,"identified_string":None,"performance_issue":None}
        data={"schema_version":1,"status":"experimental_official_model_project_decoder","analysis_input_sha256":job["input_sha256"],
            "model_sha256":learned.MODEL,"worker_sha256":"4"*64,"wheel_manifest_sha256":"5"*64,
            "tuning_registry_sha256":bank["instrument_registry_sha256"],"raw_activations_sha256":raw_hash,
            "providers":["CPUExecutionProvider"],"upstream_decoder_parity":False,"peak_rss_bytes":200000000,"elapsed_seconds":1.,
            "coverage_seconds":duration,"raw_array_bytes":n*(88*8*2+264*8+3*8+2*4),"model_windows":len(windows),
            "settings":{"decoder":learned.DECODER,"minimum_note_length_ms_presets":[127.7,25.],"frame_threshold":.3,
                "onset_threshold":.5,"start_seconds":0,"max_analysis_seconds":duration},
            "excerpts":[{"start_seconds":0.,"end_seconds":duration,"sample_rate":22050,"sample_count":count,"retained_frames":n,
                "model_input_windows":windows,"variants":[{"minimum_note_length_ms":m,"events":[dict(event)],"event_count":1} for m in (127.7,25.)]}]}
        receipt=run/"comparison.json";receipt_hash=fixtures.put_json(receipt,data)
        jobs.append({"case_id":job["case_id"],"component":job["component"],"status":"completed_measurements",
            "input_path":job["input_path"],"input_sha256":job["input_sha256"],"truth_path":str(truth_path),"truth_sha256":job["truth_sha256"],
            "comparison_path":str(receipt),"comparison_sha256":receipt_hash,"activations_path":str(raw),"activations_sha256":raw_hash})
    bank_hash=fixtures.put_json(bank_path,bank);pyin["bank_index_sha256"]=bank_hash;fixtures.put_json(pyin_path,pyin)
    index=Path(directory)/"learned-pilot.json"
    fixtures.put_json(index,{"schema_version":1,"bank_index_sha256":bank_hash,"instrument_registry_sha256":bank["instrument_registry_sha256"],
        "model_sha256":learned.MODEL,"adapter_sha256":"4"*64,"runtime_manifest_sha256":"5"*64,"budget_seconds":30,"jobs":jobs})
    return bank_path,pyin_path,index


class OracleTests(unittest.TestCase):
    def test_matching_maximum_cardinality_over_greedy_nearest(self):
        edges={("a","x"):0.,("a","y"):2.,("b","x"):1.}
        self.assertEqual(sorted(learned.best_matching(["a","b"],["x","y"],lambda a,b:(a,b) in edges,lambda a,b:edges[a,b])),[(0,1),(1,0)])
    def test_octave_harmonic_is_not_fundamental_or_extra_correct_voice(self):
        a=learned.best_matching([32.703],[65.406,130.812],lambda a,b:abs(learned.base.cents(b,a))<=50,lambda a,b:abs(learned.base.cents(b,a)))
        self.assertEqual(a,[])
    def test_negative_event_residual_and_duplicate_prediction(self):
        reference=[{"id":"one","start":1.,"end":1.5,"frequency":440.,"boundary_truncated":False}]
        events=[{"model_start_seconds":.98,"model_end_seconds":1.5,"midi_candidate":69}]*2
        result=learned.event_metrics(reference,events)
        self.assertEqual((result["tp"],result["fp"],result["fn"]),(1,1,0))
        self.assertAlmostEqual(result["onset_residual_seconds"]["median_signed"],-.02)
    def test_npy_nonfinite_object_header_and_extent_rejected(self):
        for value,reason in [(npy([float("nan")],(1,)),"nonfinite_array"),(npy([1.],(2,)),"npy_payload_extent")]:
            with self.assertRaisesRegex(learned.base.EvaluationError,reason):learned.read_npy(value)
        value=npy([1.],(1,)).replace(b"'<f8'",b"'|O8'")
        with self.assertRaisesRegex(learned.base.EvaluationError,"npy_dtype_not_allowed"):learned.read_npy(value)
    def test_boundary_truncation_does_not_establish_offset_correctness(self):
        reference=[{"id":"cut","start":1.,"end":2.,"unclipped_end":3.,"frequency":440.,"boundary_truncated":True}]
        events=[{"model_start_seconds":1.,"model_end_seconds":2.,"midi_candidate":69,"touches_excerpt_boundary":True}]
        onset=learned.event_metrics(reference,events);offset=learned.event_metrics(reference,events,True)
        self.assertEqual(onset["tp"],1);self.assertEqual(offset["tp"],0)
        self.assertEqual(onset["offset_residual_seconds"]["n"],0)
        self.assertIsNone(onset["matches"][0]["offset_residual_seconds"])
        self.assertIsNone(offset["recall"]["value"])
        self.assertEqual(offset["offset_excluded_reference_count"],1)
        self.assertEqual(offset["offset_excluded_estimate_count"],1)


class ReceiptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        learned.base.ALLOWED.mkdir(parents=True,exist_ok=True)
        cls.temp=tempfile.TemporaryDirectory(prefix="learned-eval-tests-",dir=learned.base.ALLOWED)
        cls.root=Path(cls.temp.name);create_fixture(cls.root/"template")
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def setUp(self):
        self.local=self.root/self._testMethodName;shutil.copytree(self.root/"template",self.local)
        # Rebase opaque paths; receipt path-independent identities stay immutable.
        self.bank=self.local/"fixtures.json";self.pyin=self.local/"pitch-pilot.json";self.index=self.local/"learned-pilot.json"
        for path in (self.pyin,self.index):
            data=json.loads(path.read_text())
            for job in data["jobs"]:
                for key in list(job):
                    if key.endswith("_path"):job[key]=str(self.local/Path(job[key]).relative_to(self.root/"template"))
                if "pitch_path" in job:
                    payload=json.loads(Path(job["pitch_path"]).read_text());payload["source"]["path"]=job["input_path"]
                    job["pitch_sha256"]=fixtures.put_json(Path(job["pitch_path"]),payload)
            fixtures.put_json(path,data)
    def change_receipt(self,callback):
        index=json.loads(self.index.read_text());job=index["jobs"][0];path=Path(job["comparison_path"])
        receipt=json.loads(path.read_text());callback(receipt);job["comparison_sha256"]=fixtures.put_json(path,receipt);fixtures.put_json(self.index,index)
    def evaluate(self):return learned.evaluate(self.bank,self.pyin,self.index)
    def test_missing_f0_failure_and_padding_are_visible(self):
        result,rows=self.evaluate();case=result["cases"][0]
        metrics=case["native_model_input_context"]["stable_monophonic_metrics"]
        self.assertEqual(metrics["raw_pitch_accuracy"]["value"],0.)
        self.assertEqual(metrics["raw_chroma_accuracy"]["value"],1.)
        self.assertEqual(metrics["octave_error_fraction"]["value"],1.)
        self.assertEqual(metrics["raw_pitch_accuracy"]["denominator"],426)
        self.assertEqual(case["event_presets"][0]["onset_only"]["tp"],0)
        self.assertEqual(case["event_presets"][0]["onset_only"]["fp"],1)
        self.assertEqual(case["event_presets"][0]["onset_only"]["fn"],1)
        self.assertEqual(result["model_windows"],19);self.assertEqual(result["coverage_seconds"],30)
        self.assertTrue(result["hard_gates_passed"]);self.assertTrue(result["quality_alerts"])
        self.assertFalse(result["inference_invoked"]);self.assertFalse(result["source_audio_decoded"])
        self.assertIn("input_padding",case["native_model_input_context"]["counts"]["contexts"])
    def test_changed_raw_archive_rejected(self):
        index=json.loads(self.index.read_text());Path(index["jobs"][0]["activations_path"]).write_bytes(b'fake')
        with self.assertRaisesRegex(learned.base.EvaluationError,"sha256_mismatch"):self.evaluate()
    def test_unbound_truth_rejected(self):
        index=json.loads(self.index.read_text());index["jobs"][0]["truth_sha256"]="6"*64;fixtures.put_json(self.index,index)
        with self.assertRaisesRegex(learned.base.EvaluationError,"switched_learned_input_or_truth"):self.evaluate()
    def test_false_padding_context_rejected(self):
        self.change_receipt(lambda r:r["excerpts"][0]["model_input_windows"][0].update(leading_zero_samples=0))
        with self.assertRaisesRegex(learned.base.EvaluationError,"window_mapping_mismatch"):self.evaluate()
    def test_fabricated_decoder_event_rejected(self):
        self.change_receipt(lambda r:r["excerpts"][0]["variants"][0]["events"][0].update(midi_candidate=24))
        with self.assertRaisesRegex(learned.base.EvaluationError,"event_decoder_array_mismatch"):self.evaluate()
    def test_nested_confirmed_claim_retains_metrics_and_hard_fails(self):
        self.change_receipt(lambda r:r.update(extra={"note_correctness_confirmed":True}))
        result,rows=self.evaluate();self.assertFalse(result["hard_gates_passed"]);self.assertTrue(rows)
    def test_nonnull_intended_note_is_an_unsupported_claim(self):
        self.change_receipt(lambda r:r["excerpts"][0]["variants"][0]["events"][0].update(intended_note="C1"))
        result,rows=self.evaluate();self.assertFalse(result["hard_gates_passed"])
        self.assertEqual(result["unsupported_claim_count"],1);self.assertTrue(rows)
    def test_npz_unsafe_member_and_uncompressed_bomb_rejected(self):
        path=self.local/"evil.npz"
        with zipfile.ZipFile(path,"w") as archive:archive.writestr("../array.npy",b"bad")
        with self.assertRaisesRegex(learned.base.EvaluationError,"npz_members_required"):
            learned.read_npz(path,fixtures.digest(path),1)
        with zipfile.ZipFile(path,"w",compression=zipfile.ZIP_DEFLATED) as archive:
            for name in learned.NAMES:archive.writestr("excerpt_0_"+name+".npy",b'\0'*(learned.MAX_RAW if name=="note" else 8192))
        with self.assertRaisesRegex(learned.base.EvaluationError,"npz_uncompressed_bound"):
            learned.read_npz(path,fixtures.digest(path),1)
    def test_actual_cli_summary_and_no_overwrite(self):
        output=self.local/"output";command=[sys.executable,str(ROOT/"scripts/learned_pitch_evaluate.py"),"--fixture-index",str(self.bank),
            "--pyin-pilot-index",str(self.pyin),"--learned-pilot-index",str(self.index),"--output",str(output),"--summary"]
        completed=subprocess.run(command,capture_output=True,text=True,timeout=60)
        self.assertEqual(completed.returncode,0,completed.stderr);result=json.loads(completed.stdout)
        self.assertEqual(result["status"],"completed_with_regression_alerts");self.assertLess(len(completed.stdout),10000)
        self.assertTrue(Path(result["event_errors_csv"]).is_file())
        self.assertEqual(subprocess.run(command,capture_output=True,timeout=60).returncode,2)
    def test_relative_indices_and_artifact_references_equal_absolute_metrics(self):
        # Both indices contain genuine relative descendant paths, reproducing
        # the direct CLI failure rather than testing normalization in isolation.
        for path in (self.pyin,self.index):
            payload=json.loads(path.read_text())
            for job in payload['jobs']:
                for key in list(job):
                    if key.endswith('_path'):
                        job[key]=str(Path(job[key]).relative_to(path.parent))
            fixtures.put_json(path,payload)
        absolute,absolute_rows=learned.evaluate(self.bank,self.pyin,self.index)
        relative,relative_rows=learned.evaluate(*(str(path.relative_to(ROOT)) for path in (self.bank,self.pyin,self.index)))
        # Wall-clock creation time is receipt metadata, not a score difference.
        absolute.pop('created_at');relative.pop('created_at')
        self.assertEqual(relative,absolute)
        self.assertEqual(relative_rows,absolute_rows)
        output=self.local/'relative-cli-output'
        command=[sys.executable,str(ROOT/'scripts/learned_pitch_evaluate.py')]
        for flag,path in [('--fixture-index',self.bank),('--pyin-pilot-index',self.pyin),
                          ('--learned-pilot-index',self.index),('--output',output)]:
            command.extend([flag,str(path.relative_to(ROOT))])
        completed=subprocess.run(command+['--summary'],cwd=ROOT,capture_output=True,text=True,timeout=60)
        self.assertEqual(completed.returncode,0,completed.stderr)
        receipt=json.loads(Path(json.loads(completed.stdout)['evaluation_json']).read_text())
        self.assertEqual(receipt['aggregate_views'],absolute['aggregate_views'])
        self.assertEqual(receipt['cases'],absolute['cases'])
        self.assertFalse(receipt['inference_invoked'])


if __name__=="__main__":unittest.main()
