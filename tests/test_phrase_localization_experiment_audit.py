"""Independent fresh-bank source oracles; no native WAVs, decoder or inference.

Only metadata, tiny512Hz component-algebra arrays and fabricated evaluation
coordinates are used.  They are not native construction/accuracy evidence.
"""
import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location("localization_pilot_independent",ROOT/"scripts/phrase_localization_pilot.py")
pilot=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pilot)
COHORTS=("low32-sustain","missing-f0-sustain","ordered-click-noise-only","fan-envelope-only","palm-recurrence","legato-recurrence")


def reference():
    return {"id":"toy-motif","first_span_seconds":[1.,2.],"second_span_seconds":[4.,5.]}


def estimate(first=(1.,2.),second=(4.,5.)):
    return {"first_start_seconds":first[0],"first_end_seconds":first[1],
            "second_start_seconds":second[0],"second_end_seconds":second[1],
            "performance_issue_confirmed":False}


def arms(border,localized=None,raw=None):
    return {"Araw":copy.deepcopy(border if raw is None else raw),
            "Border":copy.deepcopy(border),"L1":copy.deepcopy(border if localized is None else localized)}


def solve_joint_basis(values,rate,frequencies,start=2.,end=6.):
    """Independent small Gaussian-elimination least squares, no FFT/NumPy."""
    samples=list(range(round(start*rate),round(end*rate)))
    basis=[[1.]+[function(2*math.pi*hz*i/rate) for hz in frequencies for function in (math.sin,math.cos)] for i in samples]
    columns=len(basis[0])
    matrix=[[math.fsum(row[a]*row[b] for row in basis) for b in range(columns)]+
            [math.fsum(row[a]*values[i] for row,i in zip(basis,samples))] for a in range(columns)]
    for pivot in range(columns):
        best=max(range(pivot,columns),key=lambda row:abs(matrix[row][pivot]))
        matrix[pivot],matrix[best]=matrix[best],matrix[pivot]
        denominator=matrix[pivot][pivot]
        if abs(denominator)<1e-12:
            raise AssertionError("independent basis singular")
        matrix[pivot]=[v/denominator for v in matrix[pivot]]
        for row in range(columns):
            if row==pivot:continue
            factor=matrix[row][pivot]
            matrix[row]=[v-factor*q for v,q in zip(matrix[row],matrix[pivot])]
    return [row[-1] for row in matrix]


class FreshLocalizationIndependentTests(unittest.TestCase):
    def sealed_fixture(self,directory):
        directory=Path(directory)
        bank_dir=directory/"bank";bank_dir.mkdir()
        output=directory/"predictions";output.mkdir()
        bank={"cases":[]};rows=[]
        def save(path,value):
            path.write_text(json.dumps(value))
            return hashlib.sha256(path.read_bytes()).hexdigest()
        for index,(seed,cohort) in enumerate(((s,c) for s in (617,719) for c in COHORTS)):
            identity=f"seed{seed}-{cohort}"
            source={"sha256":str(index%10)*64}
            refs=pilot.expected_reference(seed,cohort)
            truth={"suite":pilot.SUITE,"seed":seed,"cohort":cohort,"ground_truth_scope":"generator_only_not_musician",
                   "source":source,"recurrence_pairs":refs,"performance_issue_confirmed":False}
            truth_name=f"truth-{index:02d}.json"
            truth_sha=save(bank_dir/truth_name,truth)
            candidates=[dict(row,original_candidate_index=i) for i,row in enumerate(refs)]
            prediction={"source_sha256":source["sha256"],"arms":arms(candidates),"status":"synthetic_metadata_only",
                        "localized_count":len(refs),"abstained_count":0,"candidate_failures":[],"performance_issue_confirmed":False}
            prediction_name=f"prediction-{index:02d}.json"
            prediction_sha=save(output/prediction_name,prediction)
            bank["cases"].append({"id":identity,"seed":seed,"cohort":cohort,"source":source,
                                    "truth":{"path":truth_name,"sha256":truth_sha}})
            rows.append({"id":identity,"prediction_path":prediction_name,"prediction_sha256":prediction_sha})
        bank_path=bank_dir/"fixtures.json";bank_sha=save(bank_path,bank)
        seal={"status":"all_twelve_predictions_frozen_truth_unopened","case_count":12,"bank_sha256":bank_sha,
              "case_prediction_sha256":[row["prediction_sha256"] for row in rows],
              "artifact_sha256":{row["prediction_path"]:row["prediction_sha256"] for row in rows}}
        sealed_path=output/"predictions-frozen.json";sealed_sha=save(sealed_path,seal)
        return bank,bank_path,output,rows,sealed_path,sealed_sha

    def test_fixed_metadata_is_preregistered_and_native_extent_is_exact(self):
        metadata=pilot.metadata()
        published=json.loads((ROOT/"docs/agent-notes/2026-10-06-phrase-localization-fresh-preregistration.json").read_text())
        self.assertEqual(metadata,published)
        self.assertEqual(metadata["seeds"],[617,719])
        self.assertEqual(tuple(metadata["cohorts"]),COHORTS)
        self.assertEqual(metadata["case_count"],12)
        self.assertEqual(metadata["total_audio_seconds"],96)
        self.assertEqual(metadata["native_pcm"],{"sample_rate":48000,"channels":1,"sample_width_bytes":2,"sample_count_per_case":384000})
        self.assertEqual(metadata["signal"]["component_sum_pcm_error_bound"],2/32768)
        self.assertFalse(metadata["signal"]["missing_f0_nonlinearity_after_synthesis"])

    def test_geometry_is_independently_rounded_not_pulse_or_frame_snapped(self):
        for parameter in pilot.metadata()["parameters"]:
            motif=parameter["motif"]
            for key in ("first_start","second_start","duration"):
                item=motif[key]
                self.assertEqual(item["native_sample"],round(item["requested_seconds"]*48000))
                self.assertEqual(item["seconds"],item["native_sample"]/48000)
                self.assertLessEqual(abs(item["seconds"]-item["requested_seconds"]),.5/48000+1e-12)
                self.assertNotEqual(item["native_sample"]%768,0)
            first,second,length=[motif[k]["seconds"] for k in ("first_start","second_start","duration")]
            self.assertLess(first+length,second)
            self.assertLess(second+length,8.)
            pulse=parameter["nuisance"]["pulse_period_seconds"]
            phase=parameter["nuisance"]["pulse_phase_seconds"]
            self.assertGreater(abs((first-phase)/pulse-round((first-phase)/pulse)),1e-4)

    def test_independent_knob_hash_namespace_and_ordered_nuisance_pattern(self):
        metadata=pilot.metadata()
        for row in metadata["parameters"]:
            seed=row["seed"]
            h=hashlib.sha256(f'{metadata["suite"]}:{seed}:motif:first'.encode()).digest()
            u=int.from_bytes(h[:8],"big")/2**64
            self.assertAlmostEqual(row["motif"]["first_start"]["requested_seconds"],.853+(1.107-.853)*u)
            events=[event for event in row["nuisance"]["clicks"] if event["type"]=="ordered_texture"]
            self.assertEqual(len(events),16)
            first,second=events[:8],events[8:]
            for a,b in zip(first,second):
                self.assertEqual((a["hz"],a["amplitude"]),(b["hz"],b["amplitude"]))
                self.assertAlmostEqual(b["seconds"]-a["seconds"],row["nuisance"]["ordered_starts_seconds"][1]-row["nuisance"]["ordered_starts_seconds"][0])
            self.assertNotEqual(row["nuisance"]["ordered_starts_seconds"][0],row["motif"]["first_start"]["seconds"])

    def test_tiny_algebra_components_share_nuisance_with_explicit_fan_exception(self):
        for seed in (617,719):
            baseline=None
            for cohort in COHORTS:
                result=pilot.construct_components(seed,cohort,rate=512)
                self.assertEqual({len(result[k]) for k in ("clean","fan","noise","click","mix")},{4096})
                self.assertEqual(result["truth"]["construction_scope"],"tiny_low_rate_algebra_fixture_only")
                if baseline is None:baseline=result
                self.assertEqual(result["fan"],baseline["fan"])
                self.assertEqual(result["noise"],baseline["noise"])
                if cohort=="fan-envelope-only":
                    self.assertFalse(any(result["click"]))
                else:
                    self.assertEqual(result["click"],baseline["click"])
                for components in zip(*(result[k] for k in ("clean","fan","noise","click","mix"))):
                    *parts,mix=components
                    self.assertAlmostEqual(math.fsum(parts),mix,places=14)
                    self.assertLess(abs(mix),.5)
                    integer_difference=round(mix*32768)-sum(round(v*32768) for v in parts)
                    self.assertLessEqual(abs(integer_difference),2)

    def test_tiny_missing_fundamental_joint_fit_is_linear_not_projection_leakage(self):
        result=pilot.construct_components(617,"missing-f0-sustain",rate=512)
        f0=pilot.metadata()["signal"]["c1_frequency_hz"]
        harmonics=[1,2,3,4,5,7]
        quantized=[round(v*32768)/32768 for v in result["clean"]]
        coefficients=solve_joint_basis(quantized,512,[f0*k for k in harmonics])
        self.assertLess(math.hypot(coefficients[1],coefficients[2]),5e-5)
        for index,amplitude in ((2,.1),(3,.065),(4,.035),(5,.02),(7,.012)):
            column=1+2*harmonics.index(index)
            self.assertAlmostEqual(coefficients[column],amplitude,delta=5e-5)
        self.assertFalse(result["truth"]["missing_fundamental"]["nonlinearity_after_synthesis"])

    def test_tiny_low32_and_full_repeated_motif_geometry(self):
        low=pilot.construct_components(719,"low32-sustain",rate=512)
        coefficients=solve_joint_basis(low["clean"],512,[32.])
        self.assertAlmostEqual(math.hypot(coefficients[1],coefficients[2]),.17,places=12)
        for cohort in COHORTS[4:]:
            result=pilot.construct_components(617,cohort,rate=512)
            parameters=result["truth"]["motif_parameters"]
            starts=[round(parameters[key]["seconds"]*512) for key in ("first_start","second_start")]
            length=round(parameters["duration"]["seconds"]*512)
            clean=result["clean"]
            self.assertEqual(clean[starts[0]:starts[0]+length],clean[starts[1]:starts[1]+length])
            self.assertEqual(len(result["truth"]["recurrence_pairs"]),1)
            self.assertFalse(result["truth"]["physical_articulation_accepted"])
            self.assertFalse(result["truth"]["performance_issue_confirmed"])

    def test_known_negative_no_reference_keeps_false_positives_and_null_recall(self):
        score=pilot.score_case([],arms([estimate()]))
        for arm in ("Araw","Border","L1"):
            metric=score["scores"][arm]["iou"][0]
            self.assertEqual((metric["tp"],metric["fp"],metric["fn"]),(0,1,0))
            self.assertEqual(metric["precision"],0.)
            self.assertIsNone(metric["recall"])
        self.assertEqual(score["common_reference_endpoints"][0]["endpoint_count"],0)
        self.assertIsNone(score["common_reference_endpoints"][0]["mean_absolute_error_seconds"]["L1"])

    def test_abstention_is_full_reference_miss_and_raw_fallback_is_not_estimate(self):
        score=pilot.score_case([reference()],arms([estimate()],localized=[]))
        baseline=score["scores"]["Border"]["iou"][0]
        localized=score["scores"]["L1"]["iou"][0]
        self.assertEqual((baseline["tp"],baseline["fp"],baseline["fn"]),(1,0,0))
        self.assertEqual((localized["tp"],localized["fp"],localized["fn"]),(0,0,1))
        self.assertEqual(localized["recall"],0.)
        self.assertFalse(score["raw_fallback_credited_L1"])
        common=score["common_reference_endpoints"][0]
        self.assertEqual(common["lost_reference_ids"],["toy-motif"])
        self.assertEqual(common["endpoint_count"],0)
        self.assertIsNone(common["mean_absolute_error_seconds"]["L1"])

    def test_minimum_axis_iou_retains_exact_frozen_primary_definition(self):
        score=pilot.score_case([reference()],arms([estimate(second=(4.,6.))]))
        strict=score["scores"]["Border"]["iou"][1]
        self.assertEqual((strict["tp"],strict["fp"],strict["fn"]),(0,1,1))

    def test_eligible_pair_assignment_prefers_maximum_mean_iou_not_first_prediction(self):
        candidates=[estimate((.8,2.2),(3.8,5.2)),estimate()]
        score=pilot.score_case([reference()],arms(candidates))
        match=score["scores"]["Border"]["iou"][0]["matches"][0]
        self.assertEqual(match["estimate_index"],1)
        self.assertEqual(match["signed_endpoint_offsets_seconds"],[0.,0.,0.,0.])

    def test_boundary_precision_counts_individual_endpoints_not_joint_pair_success(self):
        score=pilot.score_case([reference()],arms([estimate(second=(4.,5.06))]))
        medium=score["scores"]["L1"]["boundary"][1]
        self.assertEqual((medium["tp"],medium["fp"],medium["fn"]),(3,1,1))
        broad=score["scores"]["L1"]["boundary"][2]
        self.assertEqual((broad["tp"],broad["fp"],broad["fn"]),(4,0,0))

    def test_common_reference_offsets_and_nulls_are_per_iou_threshold(self):
        broad=estimate((.8,2.2),(3.8,5.2))
        score=pilot.score_case([reference()],arms([broad],localized=[estimate()]))
        primary,strict=score["common_reference_endpoints"]
        self.assertEqual(primary["common_reference_ids"],["toy-motif"])
        self.assertEqual(primary["endpoint_count"],4)
        self.assertAlmostEqual(primary["mean_absolute_error_seconds"]["Border"],.2)
        self.assertEqual(primary["mean_absolute_error_seconds"]["L1"],0.)
        self.assertEqual(strict["common_reference_ids"],[])
        self.assertEqual(strict["gained_reference_ids"],["toy-motif"])
        self.assertIsNone(strict["mean_absolute_error_seconds"]["L1"])

    def test_matching_is_maximum_cardinality_not_greedy_nearest(self):
        # Independent two-reference counterexample: a greedy first match loses
        # the second reference, but augmenting paths can reassign it.
        matches=pilot.maximum_matching([0.,.03],[.02,.05],lambda a,b:abs(a-b)<=.021)
        self.assertEqual(matches,[(0,0),(1,1)])

    def test_duplicate_predictions_cannot_double_credit_one_reference(self):
        score=pilot.score_case([reference()],arms([estimate(),estimate()]))
        metric=score["scores"]["Border"]["iou"][0]
        self.assertEqual((metric["tp"],metric["fp"],metric["fn"]),(1,1,0))

    def test_confirmed_claims_invalid_axes_and_over_cap_are_rejected(self):
        for bad in (estimate((2.,1.)),dict(estimate(),performance_issue_confirmed=True)):
            with self.assertRaises(ValueError):pilot.score_case([reference()],arms([bad]))
        with self.assertRaises(ValueError):pilot.score_case([reference()],arms([estimate()]*11))

    def test_micro_counts_and_per_seed_negatives_use_full_same_references(self):
        rows=[]
        for seed,cohort,refs,predictions in (
            (617,"legato-recurrence",[reference()],arms([estimate()],localized=[])),
            (617,"ordered-click-noise-only",[],arms([estimate(),estimate()],localized=[estimate()])),
            (719,"palm-recurrence",[reference()],arms([estimate()])),
            (719,"fan-envelope-only",[],arms([],localized=[])),
        ):
            rows.append({"seed":seed,"cohort":cohort,**pilot.score_case(refs,predictions)})
        aggregate=pilot.aggregate_cases(rows)
        self.assertEqual((aggregate["all"]["L1"]["iou"][0]["tp"],aggregate["all"]["L1"]["iou"][0]["fp"],aggregate["all"]["L1"]["iou"][0]["fn"]),(1,1,1))
        self.assertEqual(aggregate["seed617"]["L1"]["negative_false_candidates_by_cohort"]["ordered-click-noise-only"],1)
        self.assertEqual(aggregate["seed719"]["L1"]["negative_false_candidates_by_cohort"]["fan-envelope-only"],0)
        common=aggregate["all"]["common_reference_endpoints"][0]
        self.assertEqual(common["endpoint_count"],4)
        self.assertEqual(common["lost_reference_ids"],["toy-motif"])
        self.assertEqual(common["reference_pair_count"],2)

    def test_localized_estimates_exclude_unknown_raw_fallback_and_preserve_ids(self):
        raw=dict(estimate(),original_candidate_index=7)
        proposal={"arms":{"Border":[raw]}}
        row={"candidate_id":7,"raw_candidate":copy.deepcopy(raw),"status":"localization_unknown","localized_support":None}
        self.assertEqual(pilot.treatment_estimates({"candidates":[row]},proposal),[])
        row["status"]="localized_support_candidate"
        row["localized_support"]={"first":{"cell_start_audio_relative_seconds":1.1,"cell_end_audio_relative_seconds":1.9},
                                  "second":{"cell_start_audio_relative_seconds":4.1,"cell_end_audio_relative_seconds":4.9}}
        estimates=pilot.treatment_estimates({"candidates":[row]},proposal)
        self.assertEqual(estimates[0]["original_candidate_index"],7)
        self.assertEqual(estimates[0]["first_span_seconds"],[1.1,1.9])
        self.assertEqual(raw,proposal["arms"]["Border"][0])
        row["candidate_id"]=2
        with self.assertRaises(ValueError):pilot.treatment_estimates({"candidates":[row]},proposal)

    def test_sealed_scoring_opens_truth_only_after_all_predictions_are_bound(self):
        pilot.AREA.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="independent-seal-",dir=pilot.AREA) as directory:
            values=self.sealed_fixture(directory)
            bank,bank_path,output,rows,sealed,sealed_sha=values
            opened=[]
            def on_open():
                self.assertEqual(hashlib.sha256(sealed.read_bytes()).hexdigest(),sealed_sha)
                for row in rows:
                    self.assertEqual(hashlib.sha256((output/row["prediction_path"]).read_bytes()).hexdigest(),row["prediction_sha256"])
                opened.append(True)
            result=pilot.score_sealed(*values,on_truth_open=on_open)
            self.assertEqual(len(opened),12)
            self.assertEqual(len(result["cases"]),12)
            self.assertEqual(result["aggregate"]["all"]["L1"]["iou"][0]["reference_pair_count"],4)
            self.assertEqual(result["aggregate"]["all"]["L1"]["iou"][0]["tp"],4)
            self.assertFalse(result["canonical_defaults_activated"])

    def test_stale_last_prediction_is_rejected_before_any_truth_open(self):
        pilot.AREA.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="independent-stale-",dir=pilot.AREA) as directory:
            values=self.sealed_fixture(directory)
            bank,bank_path,output,rows,sealed,sealed_sha=values
            changed=output/rows[-1]["prediction_path"]
            changed.write_text(changed.read_text()+"\n")
            opened=[]
            with self.assertRaises(ValueError):pilot.score_sealed(*values,on_truth_open=lambda:opened.append(True))
            self.assertEqual(opened,[])

    def test_incomplete_seal_or_truncated_bank_cannot_hide_reference_denominator(self):
        pilot.AREA.mkdir(parents=True,exist_ok=True)
        for truncated in (False,True):
            with self.subTest(truncated=truncated),tempfile.TemporaryDirectory(prefix="independent-incomplete-",dir=pilot.AREA) as directory:
                values=self.sealed_fixture(directory)
                bank,bank_path,output,rows,sealed,sealed_sha=values
                if truncated:
                    bank["cases"].pop()
                else:
                    seal=json.loads(sealed.read_text());seal["case_count"]=11
                    sealed.write_text(json.dumps(seal));sealed_sha=hashlib.sha256(sealed.read_bytes()).hexdigest()
                    values=bank,bank_path,output,rows,sealed,sealed_sha
                opened=[]
                with self.assertRaises(ValueError):pilot.score_sealed(*values,on_truth_open=lambda:opened.append(True))
                self.assertEqual(opened,[])

    def test_runner_wrong_exact_bank_release_fails_before_bank_or_decoder_access(self):
        plan=pilot.metadata()
        with mock.patch.object(pilot,"authorized",return_value=(plan,{"bank_sha256":"1"*64})),mock.patch.object(pilot,"validate_bank") as bank:
            with self.assertRaisesRegex(ValueError,"exact_released_bank_hash_required"):
                pilot.runner(None,None,None,None,None,"2"*64,None)
            bank.assert_not_called()

    def test_pcm_and_two_lsb_construction_guard_are_source_algebra_only(self):
        encoded={key:pilot.pcm16([0.,.03125,-.03125]) for key in ("clean","fan","noise","click")}
        encoded["mix"]=pilot.pcm16([0.,.125,-.125])
        proof=pilot.component_sum_proof(encoded)
        self.assertEqual(proof["maximum_integer_sample_residual"],0)
        encoded["mix"]=pilot.pcm16([3/32768,.125,-.125])
        with self.assertRaises(ValueError):pilot.component_sum_proof(encoded)
        for value in (.5,float("nan"),float("inf")):
            with self.assertRaises(ValueError):pilot.pcm16([value])

    def test_internal_child_admission_precedes_numeric_import_and_feature_loading(self):
        # No child, waveform or root receipt is created. Only call ordering is
        # exercised, with the admission guard deliberately rejecting.
        run=pilot.AREA/"fabricated-owned-layout"
        target=run/"discovery/job-01"
        task={"source":str(run/"inputs/audio-01.wav"),"source_sha256":"1"*64,
              "target":str(target),"sources":str(run/"sources"),
              "controller_sha256":hashlib.sha256(Path(pilot.__file__).read_bytes()).hexdigest(),
              "release_sha256":"2"*64,"admission_sha256":"3"*64}
        helper=mock.Mock()
        helper.read.return_value=task
        with mock.patch.object(pilot,"old_helper",return_value=helper),mock.patch.object(pilot,"artifact_path",side_effect=lambda p,*args:Path(p)),\
             mock.patch.object(pilot,"validate_child_admission",side_effect=ValueError("admission_rejected")),mock.patch.object(pilot,"load_module") as loader:
            with self.assertRaisesRegex(ValueError,"admission_rejected"):
                pilot.child(target/"task.json","4"*64)
            loader.assert_not_called()

    def test_owned_group_readback_excludes_zombies_and_other_groups(self):
        report=mock.Mock(stdout="81234 81234 S\n81235 81234 Z\n91346 91346 S\n")
        with mock.patch.object(pilot.subprocess,"run",return_value=report) as command:
            self.assertEqual(pilot.live_owned_group(81234),[{"pid":81234,"pgid":81234,"state":"S"}])
            self.assertEqual(command.call_args.kwargs["timeout"],2)

    def test_simulated_cleanup_targets_recorded_group_and_retains_rn11_receipt(self):
        # Signals are mocked; no host process or other session is touched.
        process=mock.Mock(pid=81234)
        process.poll.return_value=0
        receipts=[]
        with mock.patch.object(pilot,"live_owned_group",side_effect=[[{"pid":81235,"pgid":81234,"state":"S"}],[],[],[]]),\
             mock.patch.object(pilot.os,"killpg") as signal:
            pilot.cleanup_owned_group(process,receipts,"source_fixture_only")
            signal.assert_called_once_with(81234,pilot.signal.SIGTERM)
        self.assertEqual(receipts[0]["target_pgid"],81234)
        self.assertEqual(receipts[0]["ruling"],"R-N11")
        self.assertEqual(receipts[0]["prior_state"]["live_group_members"][0]["pid"],81235)
        self.assertEqual(receipts[0]["result"],"owned_group_signalled_leader_reaped_no_live_members")


if __name__=="__main__":unittest.main()
