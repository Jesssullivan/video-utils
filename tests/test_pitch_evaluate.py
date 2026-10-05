import array
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave

SPEC = importlib.util.spec_from_file_location("pitch_evaluate", Path(__file__).resolve().parents[1] / "scripts/pitch_evaluate.py")
evaluate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evaluate)


def put_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, allow_nan=False))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frame(time, frequency=220, voiced=True, half=.032, complete=True):
    return {"audio_relative_seconds":time,"source_timeline_seconds":time,
            "window_start_seconds_audio_relative":time-half,"window_end_seconds_audio_relative":time+half,
            "window_start_seconds_source_timeline":time-half,"window_end_seconds_source_timeline":time+half,
            "frequency_hz":frequency,"voiced":voiced,"edge_context_complete":complete,"voicing_probability":.8}


def reference(start, end, frequencies=(220,), condition="clean", kind="region"):
    return {"start_seconds":start,"end_seconds":end,"start_native_sample":round(start*48000),
            "end_native_sample":round(end*48000),"frequencies":list(frequencies),"monophonic":len(frequencies)==1,
            "condition":condition,"kind":kind,"id":f"region-{start}"}


def rows_for(frequencies, expected=220):
    branch = {"name":"high_register","frame_samples":1024,"minimum_hz":200,"maximum_hz":2000}
    segment = reference(0,10,(expected,))
    rows = []
    for i,hz in enumerate(frequencies):
        f = frame(.5+i*.016,hz,hz is not None)
        rows.append({**evaluate.classify_frame(f,branch,[segment],48000),"voicing_probability":f["voicing_probability"]})
    return rows


def create_valid_fixture(directory):
    """Portable generated metadata smoke; deliberate all-abstaining fake estimates.

    WAVs are genuinely generated tones; this fixture never runs inference or
    claims pYIN accuracy. Pure metric tests below use independent manual oracles.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    native_rate = 48000
    registry_hash = digest(evaluate.ROOT/"program/instrument.json")
    durations = [("low32-sustain",8),("palm-muted-recurrence",8),("legato-recurrence",8),
                 ("c1-missing-fundamental",8),("tuning-ladder",8),("legato-transition",10),
                 ("sweep-and-polyphony",10),("rest-syncopation-tuplets",12),("variable-tempo",12),
                 ("click-overlap-abstention",12),("timing-reference",12),("timing-errors",12)]
    cases,jobs = [],[]
    for case_id,duration in durations:
        case_dir = directory/case_id
        case_dir.mkdir()
        if case_id not in evaluate.PILOT:
            cases.append({"id":case_id,"duration_seconds":duration,"truth":f"{case_id}/truth.json","truth_sha256":"0"*64})
            continue
        count = native_rate*duration
        frequency = 32.703195663 if case_id=="c1-missing-fundamental" else 220
        artifacts = {}
        for component in ("clean","mix"):
            values = array.array("h")
            for sample in range(count):
                t = sample/native_rate
                tone = .15*math.sin(2*math.pi*frequency*t)
                if case_id=="c1-missing-fundamental":
                    tone = .12*math.sin(4*math.pi*frequency*t)+.1*math.sin(6*math.pi*frequency*t)
                if component=="mix":
                    tone += .002*math.sin(2*math.pi*3500*t)
                values.append(round(tone*32768))
            if sys.byteorder!="little":values.byteswap()
            path = case_dir/f"{component}.wav"
            with wave.open(str(path),"wb") as wav:
                wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(native_rate);wav.writeframes(values.tobytes())
            artifacts[component] = {"path":str(path.relative_to(directory)),"sha256":digest(path),"bytes":path.stat().st_size}
        # Unread zero-signal component metadata is enough for this structural-only smoke.
        artifacts["click"]={**artifacts["clean"],"path":f"{case_id}/click.wav"}
        artifacts["noise"]={**artifacts["clean"],"path":f"{case_id}/noise.wav"}
        truth={"schema_version":2,"id":case_id,"kind":"synthetic_generated_signal_and_score_truth",
               "ground_truth_scope":"generator_only_not_musician",
               "source":{"path":artifacts["mix"]["path"],"sha256":artifacts["mix"]["sha256"],
                         "sample_rate":native_rate,"channels":1,"sample_count":count,"duration_seconds":duration,
                         "audio_start_seconds":0,"origin_evidence":"synthetic_generator_sample_zero"},
               "artifacts":artifacts,"pitch_regions":[{"start_seconds":0,"end_seconds":duration,
                   "start_native_sample":0,"end_native_sample":count,"frequencies_hz":[frequency],"midi_notes":[24 if frequency<40 else 57],
                   "monophonic":True,"condition":"generated_metadata_smoke","articulation":"steady",
                   "expected_abstention_reasons":[]}],"pitch_trajectories":[],"guitar_absent_intervals_seconds":[]}
        truth_path=case_dir/"truth.json";truth_hash=put_json(truth_path,truth)
        cases.append({"id":case_id,"duration_seconds":duration,"truth":str(truth_path.relative_to(directory)),"truth_sha256":truth_hash})
        component,budget=evaluate.PILOT[case_id]
        input_path=directory/"inputs"/f"audio-{len(jobs)}.wav";input_path.parent.mkdir(exist_ok=True)
        shutil.copyfile(directory/artifacts[component]["path"],input_path)
        branches=[]
        for name,(size,low,high) in evaluate.BRANCHES.items():
            frames=[]
            for index in range(math.ceil(budget/evaluate.HOP*evaluate.RATE)):
                center=index*evaluate.HOP/evaluate.RATE;half=size/(2*evaluate.RATE)
                f=frame(center,None,False,half,center>=half and center+half<=budget)
                f["window_start_seconds_audio_relative"]=f["window_start_seconds_source_timeline"]=max(0,center-half)
                f["window_end_seconds_audio_relative"]=f["window_end_seconds_source_timeline"]=min(budget,center+half)
                frames.append(f)
            branches.append({"name":name,"frame_samples":size,"minimum_hz":low,"maximum_hz":high,"frames":frames})
        spans=[{"start_seconds":0.0,"end_seconds":float(budget)}]
        versions={"librosa":"0.11.0","numpy":"2.5.3","python":"3.14.6"}
        worker_hash="1"*64
        pitch={"schema_version":1,"tool":"pitch","status":"experimental_candidate_analysis",
               "source":{"path":str(input_path),"sha256":artifacts[component]["sha256"],"audio_stream_start_seconds":0},
               "instrument_context":{"tuning_metadata_sha256":registry_hash},"provenance":{"worker_sha256":worker_hash,"python_version":versions["python"]},
               "interpretation":{"performance_grade":"not_graded","intended_notes":None},
               "analysis":{"sample_rate":16000,"channels":1,"hop_samples":256,"pyin_resolution_semitones":.2,
                   "pyin_threshold_count":50,"backend":"librosa_pyin","sampling":"explicit_contiguous_excerpt",
                   "duration_seconds":duration,"max_analysis_seconds":budget,"numerical_threads_maximum":2,"pyin_timeout_seconds":180,
                   "coverage_spans_audio_relative":spans,"coverage_seconds":budget},
               "observations":{"analyzed_excerpts":[{"start_seconds":0.0,"end_seconds":float(budget),
                   "versions":{k:versions[k] for k in ("librosa","numpy")},"branches":branches}]}}
        pitch_path=case_dir/"pitch.json";pitch_hash=put_json(pitch_path,pitch)
        jobs.append({"case_id":case_id,"component":component,"input_path":str(input_path),"input_sha256":artifacts[component]["sha256"],
                     "mixture_parent_path":str(directory/artifacts["mix"]["path"]),"mixture_parent_sha256":artifacts["mix"]["sha256"],
                     "truth_path":str(truth_path),"truth_sha256":truth_hash,"pitch_path":str(pitch_path),"pitch_sha256":pitch_hash,
                     "command":["python","scripts/pitch.py",str(input_path),"--max-analysis-seconds",str(budget),"--start-seconds","0"],
                     "worker_sha256":worker_hash,"versions":versions,"requested_start_seconds":0,"requested_budget_seconds":budget,
                     "observed_coverage_spans":spans,"wall_seconds":0,"status":"completed_measurements"})
    bank_path=directory/"fixtures.json"
    bank_hash=put_json(bank_path,{"schema_version":2,"suite":"technical-v2","case_count":12,"total_duration_seconds":120,
            "ground_truth_scope":"generator_only_not_musician","instrument_registry_sha256":registry_hash,"cases":cases})
    pilot_path=directory/"pitch-pilot.json"
    put_json(pilot_path,{"schema_version":1,"bank_index_sha256":bank_hash,"instrument_registry_sha256":registry_hash,"budget_seconds":30,"jobs":jobs})
    return bank_path,pilot_path


class MetricTests(unittest.TestCase):
    def test_pitch_chroma_octave_semitone_and_abstention_oracle(self):
        rows=rows_for([220,220*2**(1/12),440,110,None])
        metric=evaluate.summarize_frames(rows)
        values=metric["stable_monophonic_metrics"]
        self.assertEqual(values["raw_pitch_accuracy"]["value"],1/5)
        self.assertEqual(values["raw_chroma_accuracy"]["value"],3/5)
        self.assertEqual(values["octave_error_fraction"]["value"],2/5)
        self.assertEqual(values["non_octave_pitch_error_fraction"]["value"],1/5)
        self.assertEqual(values["voicing_recall"]["value"],4/5)
        self.assertEqual(values["signed_semitone_error_histogram"],{"1":1})
        self.assertEqual(metric["context_diagnostics"]["abstention"]["value"],1/5)

    def test_false_voicing_and_null_denominators(self):
        branch={"name":"high_register","frame_samples":1024,"minimum_hz":200,"maximum_hz":2000}
        absent=reference(0,2,(),kind="absent")
        rows=[evaluate.classify_frame(frame(.4),branch,[absent],48000),evaluate.classify_frame(frame(.6,None,False),branch,[absent],48000)]
        values=evaluate.summarize_frames(rows)["stable_monophonic_metrics"]
        self.assertEqual(values["voicing_false_alarm"]["value"],.5)
        self.assertIsNone(values["raw_pitch_accuracy"]["value"])
        self.assertEqual(values["raw_pitch_accuracy"]["reason"],"no_applicable_frames")

    def test_context_masks_polyphony_range_crossing_and_edges(self):
        branch={"name":"high_register","frame_samples":1024,"minimum_hz":200,"maximum_hz":2000}
        segments=[reference(0,1,(220,)),reference(1,2,(32.7,)),reference(2,3,(220,330))]
        self.assertEqual(evaluate.classify_frame(frame(.99),branch,segments,48000)["context"],"transition_crossing")
        self.assertEqual(evaluate.classify_frame(frame(1.5),branch,segments,48000)["context"],"out_of_range")
        self.assertEqual(evaluate.classify_frame(frame(2.5),branch,segments,48000)["context"],"polyphonic")
        self.assertEqual(evaluate.classify_frame(frame(.01,complete=False),branch,segments,48000)["context"],"excerpt_edge")

    def test_log_glide_uses_center_native_sample_and_source_translation(self):
        truth={"source":{"sample_rate":48000,"sample_count":96000},"pitch_regions":[],"guitar_absent_intervals_seconds":[],
               "pitch_trajectories":[{"start_seconds":0,"end_seconds":2,"start_native_sample":0,"end_native_sample":96000,
                   "start_frequency_hz":220,"end_frequency_hz":880,"formula":"log_frequency_linear_time","monophonic":True}]}
        segments=evaluate.reference_segments(truth)
        f=frame(1,440);f["source_timeline_seconds"]=8
        result=evaluate.classify_frame(f,{"minimum_hz":200,"maximum_hz":2000},segments,48000)
        self.assertEqual(result["native_reference_sample"],48000)
        self.assertAlmostEqual(result["signed_cents"],0)
        self.assertEqual(f["source_timeline_seconds"],8)

    def test_transition_scan_retains_negative_lookahead_and_resolution_censor(self):
        branch={"name":"high_register","frame_samples":1024,"minimum_hz":200,"maximum_hz":2000}
        segments=[reference(0,.5,(220,)),reference(.5,1,(440,))]
        frames=[frame(.4+i*.016,440 if i>=5 else 220) for i in range(35)]
        rows=evaluate.transition_rows(frames,branch,segments,48000)
        measured=next(r for r in rows if r["reference_seconds"]==.5)
        self.assertEqual(measured["status"],"measured")
        self.assertAlmostEqual(measured["signed_timing_bias_seconds"],-.02)
        short=[reference(.5,.54,(440,))]
        self.assertEqual(evaluate.transition_rows(frames,branch,short,48000)[0]["status"],"censored_window_resolution")
        low=[reference(.5,1,(32.7,))]
        self.assertEqual(evaluate.transition_rows(frames,branch,low,48000)[0]["status"],"out_of_range_target")

    def test_probability_histogram_is_not_note_confidence_and_small_n_p95_null(self):
        result=evaluate.summarize_frames(rows_for([220,None]))
        self.assertIn("not_note_correctness",result["context_diagnostics"]["probability_meaning"])
        self.assertIsNone(result["stable_monophonic_metrics"]["cents_error"]["absolute_p95"])
        self.assertEqual(evaluate.error_summary(list(range(20)))["absolute_p95"],18)


class MetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        evaluate.ALLOWED.mkdir(parents=True,exist_ok=True)
        cls.temporary=tempfile.TemporaryDirectory(prefix="pitch-eval-tests-",dir=evaluate.ALLOWED)
        cls.root=Path(cls.temporary.name)
        cls.bank,cls.pilot=create_valid_fixture(cls.root/"template")
    @classmethod
    def tearDownClass(cls):cls.temporary.cleanup()
    def setUp(self):
        self.local=self.root/self._testMethodName
        shutil.copytree(self.root/"template",self.local)
        # Rebind path aliases and fingerprints after copying the independently generated fixture.
        pilot=json.loads((self.local/"pitch-pilot.json").read_text())
        for job in pilot["jobs"]:
            for key in ("input_path","mixture_parent_path","truth_path","pitch_path"):
                job[key]=str(self.local/Path(job[key]).relative_to(self.root/"template"))
            pitch=json.loads(Path(job["pitch_path"]).read_text());pitch["source"]["path"]=job["input_path"]
            job["pitch_sha256"]=put_json(Path(job["pitch_path"]),pitch)
        put_json(self.local/"pitch-pilot.json",pilot)
        self.bank=self.local/"fixtures.json";self.pilot=self.local/"pitch-pilot.json"
    def change_pitch(self,change):
        pilot=json.loads(self.pilot.read_text());job=pilot["jobs"][0];path=Path(job["pitch_path"])
        payload=json.loads(path.read_text());change(payload)
        job["pitch_sha256"]=put_json(path,payload);put_json(self.pilot,pilot)
    def test_complete_generated_smoke_preserves_baseline_failure_visibility(self):
        result,rows,transitions=evaluate.evaluate(self.bank,self.pilot)
        self.assertEqual(result["case_count"],4);self.assertEqual(result["frame_count"],3750)
        self.assertEqual(result["pilot_coverage_seconds"],30)
        self.assertEqual(result["status"],"completed_with_regression_alerts")
        self.assertTrue(result["hard_gates_passed"])
        self.assertTrue(result["source_audio_bytes_read"])
        self.assertFalse(result["source_audio_decoded"]);self.assertFalse(result["inference_invoked"])
        self.assertFalse(result["real_performance_grading"])
        self.assertTrue(result["quality_alerts"])
    def test_stale_pitch_fingerprint_rejected(self):
        pilot=json.loads(self.pilot.read_text());Path(pilot["jobs"][0]["pitch_path"]).write_text('{}')
        with self.assertRaisesRegex(evaluate.EvaluationError,"sha256_mismatch"):
            evaluate.evaluate(self.bank,self.pilot)
    def test_tampered_input_alias_rejected(self):
        pilot=json.loads(self.pilot.read_text());Path(pilot["jobs"][0]["input_path"]).write_bytes(b'not WAV')
        with self.assertRaisesRegex(evaluate.EvaluationError,"sha256_mismatch"):
            evaluate.evaluate(self.bank,self.pilot)
    def test_false_edge_flags_rejected(self):
        self.change_pitch(lambda p:p["observations"]["analyzed_excerpts"][0]["branches"][0]["frames"][0].update(edge_context_complete=True))
        with self.assertRaisesRegex(evaluate.EvaluationError,"untrusted_edge_context_flag"):
            evaluate.evaluate(self.bank,self.pilot)
    def test_duplicate_frame_grid_rejected(self):
        def duplicate(payload):
            frames=payload["observations"]["analyzed_excerpts"][0]["branches"][0]["frames"]
            frames[1]=dict(frames[0])
        self.change_pitch(duplicate)
        with self.assertRaisesRegex(evaluate.EvaluationError,"frame_grid_mismatch"):
            evaluate.evaluate(self.bank,self.pilot)
    def test_nested_confirmed_claim_retains_valid_metrics_but_hard_fails(self):
        self.change_pitch(lambda p:p["observations"].update(nested={"items":[{"note_correctness_confirmed":True}]}))
        result,rows,_=evaluate.evaluate(self.bank,self.pilot)
        self.assertEqual(result["unsupported_claim_count"],1)
        self.assertEqual(result["status"],"generated_fixture_calibration_failed_hard_gates")
        self.assertFalse(result["hard_gates_passed"]);self.assertTrue(rows)
    def test_missing_job_rejected(self):
        pilot=json.loads(self.pilot.read_text());pilot["jobs"].pop();put_json(self.pilot,pilot)
        with self.assertRaisesRegex(evaluate.EvaluationError,"mandatory_pilot_jobs_required"):
            evaluate.evaluate(self.bank,self.pilot)
    def test_worker_revision_drift_rejected(self):
        pilot=json.loads(self.pilot.read_text());pilot["jobs"][0]["worker_sha256"]="2"*64;put_json(self.pilot,pilot)
        with self.assertRaisesRegex(evaluate.EvaluationError,"worker_revision_drift"):
            evaluate.evaluate(self.bank,self.pilot)
    def test_switched_component_and_registry_drift_rejected(self):
        pilot=json.loads(self.pilot.read_text());pilot["jobs"][0]["component"]="mix";put_json(self.pilot,pilot)
        with self.assertRaisesRegex(evaluate.EvaluationError,"fixed_pilot_job_mismatch"):
            evaluate.evaluate(self.bank,self.pilot)
        pilot["jobs"][0]["component"]="clean";put_json(self.pilot,pilot)
        self.change_pitch(lambda p:p["instrument_context"].update(tuning_metadata_sha256="3"*64))
        with self.assertRaisesRegex(evaluate.EvaluationError,"pitch_registry_mismatch"):
            evaluate.evaluate(self.bank,self.pilot)
    def test_nonfinite_duplicate_deep_json_and_symlink_rejected(self):
        for data,message in [(b'{"x":1e400}',"nonfinite_json_number"),(b'{"x":1,"x":2}',"duplicate_json_key"),
                             (b'{"x":'+b'['*129+b'0'+b']'*129+b'}',"json_depth_bound")]:
            path=self.local/"bad.json";path.write_bytes(data)
            with self.assertRaisesRegex(evaluate.EvaluationError,message):evaluate.read_json(path)
        path=self.local/"link.json";path.symlink_to(self.bank)
        with self.assertRaisesRegex(evaluate.EvaluationError,"symlink_path"):evaluate.read_json(path)
    def test_summary_actual_cli_and_hard_gate_exit(self):
        output=self.local/"output"
        command=[sys.executable,str(evaluate.ROOT/"scripts/pitch_evaluate.py"),"--fixture-index",str(self.bank),
                 "--pilot-index",str(self.pilot),"--output",str(output),"--summary"]
        completed=subprocess.run(command,capture_output=True,text=True,timeout=30)
        self.assertEqual(completed.returncode,0,completed.stderr)
        summary=json.loads(completed.stdout);self.assertLess(len(completed.stdout),10000)
        self.assertTrue(summary["hard_gates_passed"])
        self.assertTrue(Path(summary["frame_errors_csv"]).is_file())
        self.change_pitch(lambda p:p["observations"].update(musical_error_confirmed=True))
        command[command.index(str(output))]=str(self.local/"hard-gate-output")
        completed=subprocess.run(command,capture_output=True,text=True,timeout=30)
        self.assertEqual(completed.returncode,1)
        self.assertEqual(json.loads(completed.stdout)["status"],"generated_fixture_calibration_failed_hard_gates")
        self.assertIn("retained",completed.stderr)


if __name__ == "__main__":unittest.main()
