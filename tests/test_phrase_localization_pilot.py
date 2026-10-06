"""Source-only experiment tests: tiny pure arrays and inert orchestration, no native audio."""
from array import array
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('fresh_localization_pilot',ROOT/'scripts/phrase_localization_pilot.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)


def candidate(first=(1.,2.),second=(4.,5.)):
    return {'first_span_seconds':list(first),'second_span_seconds':list(second),'performance_issue_confirmed':False}


class SourceTests(unittest.TestCase):
    def test_fixed_metadata_matches_preregistration(self):
        receipt=json.loads((ROOT/'docs/agent-notes/2026-10-06-phrase-localization-fresh-preregistration.json').read_text())
        self.assertEqual(receipt,p.metadata());self.assertEqual(receipt['total_audio_seconds'],96)
        self.assertEqual(receipt['case_count'],12);self.assertEqual(receipt['seeds'],[617,719])

    def test_native_geometry_is_non_grid_and_before_any_array(self):
        for row in p.metadata()['parameters']:
            for field in ('first_start','second_start','duration'):
                geometry=row['motif'][field]
                self.assertEqual(geometry['native_sample'],round(geometry['requested_seconds']*48000))
                self.assertEqual(geometry['seconds'],geometry['native_sample']/48000)
                self.assertGreater(abs(geometry['seconds']/.016-round(geometry['seconds']/.016)),1e-3)
            self.assertNotAlmostEqual(row['motif']['first_start']['seconds'],row['nuisance']['pulse_phase_seconds'])

    def test_shared_components_tiny_algebra_and_fan_exception(self):
        for seed in (617,719):
            cases=[p.construct_components(seed,cohort,256) for cohort in p.COHORTS]
            for name in ('fan','noise'):
                self.assertTrue(all(row[name].tobytes()==cases[0][name].tobytes() for row in cases))
            for index in (0,1,2,4,5):self.assertEqual(cases[index]['click'].tobytes(),cases[0]['click'].tobytes())
            self.assertTrue(any(cases[0]['click']));self.assertFalse(any(cases[3]['click']))
            self.assertFalse(any(cases[2]['clean']));self.assertFalse(any(cases[3]['clean']))
            for row in cases:
                self.assertEqual(len(row['mix']),2048)
                self.assertLess(max(abs(v) for v in row['mix']),.5)
                self.assertEqual(row['truth']['construction_scope'],'tiny_low_rate_algebra_fixture_only')

    def test_exact_repeated_motif_despite_independent_nuisance(self):
        for cohort in p.COHORTS[4:]:
            row=p.construct_components(617,cohort,512);motif=row['truth']['motif_parameters']
            first=round(motif['first_start']['seconds']*512);second=round(motif['second_start']['seconds']*512)
            count=round(motif['duration']['seconds']*512)
            self.assertEqual(row['clean'][first:first+count],row['clean'][second:second+count])
            self.assertEqual(row['truth']['recurrence_pairs'],p.expected_reference(617,cohort))
            self.assertGreater(max(row['clean']),.01)

    def test_internal_rests_remain_in_full_truth(self):
        row=p.construct_components(719,'legato-recurrence',512);motif=row['truth']['motif_parameters']
        start=round(motif['first_start']['seconds']*512)
        native_length=motif['duration']['native_sample']
        for a,b in motif['internal_rest_fraction_spans']:
            left=round(a*native_length)/48000;right=round(b*native_length)/48000
            interior=[row['clean'][start+i] for i in range(round(motif['duration']['seconds']*512)) if left<=i/512<right]
            self.assertTrue(interior);self.assertFalse(any(interior))
        self.assertAlmostEqual(row['truth']['recurrence_pairs'][0]['first_span_seconds'][1]-row['truth']['recurrence_pairs'][0]['first_span_seconds'][0],motif['duration']['seconds'])

    def test_missing_f0_is_linear_absolute_clock_synthesis(self):
        rate=512;row=p.construct_components(617,'missing-f0-sustain',rate);signal=p.metadata()['signal']
        import math
        for i in (1024,1347,1823):
            expected=sum(a*math.sin(2*math.pi*k*signal['c1_frequency_hz']*i/rate) for k,a in signal['missing_f0_harmonics'])
            self.assertAlmostEqual(row['clean'][i],expected,places=14)
        self.assertFalse(row['truth']['missing_fundamental']['nonlinearity_after_synthesis'])
        self.assertEqual(row['truth']['recurrence_pairs'],[])

    def test_two_lsb_component_quantization_oracle(self):
        values={'clean':array('d',[.0002,.13,-.12]),'fan':array('d',[.00002,.01,.015]),
                'noise':array('d',[-.00003,.000005,.003]),'click':array('d',[.00006,.02,-.004])}
        values['mix']=array('d',(sum(v[i] for v in values.values()) for i in range(3)))
        encoded={key:p.pcm16(row) for key,row in values.items()}
        proof=p.component_sum_proof(encoded);self.assertLessEqual(proof['maximum_integer_sample_residual'],2)
        encoded['mix']=bytes(len(encoded['mix']))
        with self.assertRaisesRegex(ValueError,'two_lsb'):p.component_sum_proof(encoded)

    def test_rendered_low32_coefficient_oracle_in_memory_only(self):
        signal=p.construct_components(617,'low32-sustain',512)
        proof=p.verify_low32_render(p.pcm16(signal['clean']),512)
        self.assertAlmostEqual(proof['measured_amplitude'],.17,delta=5e-5)
        import math
        octave=array('d',(.17*math.sin(2*math.pi*64*i/512) for i in range(4096)))
        with self.assertRaisesRegex(ValueError,'low32_coefficient'):p.verify_low32_render(p.pcm16(octave),512)

    def test_primary_both_axis_iou_and_best_mean_assignment(self):
        reference=[candidate()];wide=candidate((.8,2.2),(3.8,5.2));exact=candidate()
        scores=p.pair_metrics(reference,[wide,exact],8.,'iou',.5)
        self.assertEqual(scores['matches'][0]['estimate_index'],1)
        asymmetric=candidate((1.,2.),(4.,6.))
        score=p.pair_metrics(reference,[asymmetric],8.,'iou',.75)
        self.assertEqual((score['tp'],score['fn']),(0,1))

    def test_typed_boundary_three_of_four_and_unknown_full_denominator(self):
        reference=[candidate()];predicted=candidate((1.01,2.01),(4.01,5.2))
        scores=p.score_case(reference,{'Araw':[predicted],'Border':[predicted],'L1':[]})
        measured=scores['scores']['Border']['boundary'][0]
        self.assertEqual((measured['tp'],measured['fp'],measured['fn']),(3,1,1))
        abstained=scores['scores']['L1']['boundary'][0]
        self.assertEqual((abstained['tp'],abstained['fp'],abstained['fn']),(0,0,4))
        self.assertEqual(scores['scores']['L1']['iou'][0]['fn'],1)
        self.assertIsNone(scores['common_reference_endpoints'][0]['mean_absolute_error_seconds']['L1'])

    def test_negative_counts_and_null_recall(self):
        scored=p.score_case([],{'Araw':[candidate()],'Border':[candidate()],'L1':[]})
        self.assertEqual(scored['scores']['Border']['iou'][0]['fp'],1)
        self.assertIsNone(scored['scores']['Border']['iou'][0]['recall'])
        self.assertEqual(scored['scores']['Border']['boundary'][0]['fp'],4)
        self.assertIsNone(scored['scores']['L1']['iou'][0]['precision'])

    def test_aggregate_sum_denominators_and_common_intersections(self):
        rows=[]
        for refs,arm,cohort in [([candidate()],{'Araw':[candidate()],'Border':[candidate()],'L1':[]},'palm-recurrence'),
                                ([],{'Araw':[candidate()],'Border':[],'L1':[]},'ordered-click-noise-only')]:
            measured=p.score_case(refs,arm);measured.update(seed=617,cohort=cohort);rows.append(measured)
        total=p.aggregate_cases(rows)['all']
        self.assertEqual((total['Araw']['iou'][0]['tp'],total['Araw']['iou'][0]['fp'],total['Araw']['iou'][0]['fn']),(1,1,0))
        self.assertEqual(total['Araw']['iou'][0]['precision'],.5)
        self.assertEqual(total['L1']['boundary'][0]['reference_endpoint_count'],4)
        self.assertIsNone(total['common_reference_endpoints'][0]['mean_absolute_error_seconds']['L1'])

    def test_no_raw_fallback_credit_and_identity_change_rejected(self):
        raw={'first_start_seconds':1.,'first_end_seconds':2.,'second_start_seconds':4.,'second_end_seconds':5.,'original_candidate_index':2}
        row={'candidate_id':2,'raw_candidate':raw,'status':'unknown','localized_support':None,'raw_fallback_available':True}
        self.assertEqual(p.treatment_estimates({'candidates':[row]},{'arms':{'Border':[raw]}}),[])
        changed=copy.deepcopy(row);changed['candidate_id']=1
        with self.assertRaisesRegex(ValueError,'identity'):p.treatment_estimates({'candidates':[changed]},{'arms':{'Border':[raw]}})

    def test_release_gate_and_mutated_plan_reject_without_construct(self):
        with patch.object(p,'construct_components',side_effect=AssertionError('must not construct')):
            with self.assertRaisesRegex(ValueError,'missing|Missing|Artifact'):
                p.generate(ROOT/'docs/agent-notes/no-release-plan.json','a'*64,ROOT/'docs/agent-notes/no-release.json','b'*64,p.AREA/'must-not-exist')
        self.assertFalse((p.AREA/'must-not-exist').exists())

    def test_caps_and_recursive_claim_and_nonfinite_guards(self):
        with self.assertRaisesRegex(ValueError,'confirmed'):p.score_case([],{'Araw':[{'evidence':{'performance_issue_confirmed':True}}],'Border':[],'L1':[]})
        with self.assertRaisesRegex(ValueError,'caps'):p.score_case([],{'Araw':[candidate()]*61,'Border':[],'L1':[]})
        with self.assertRaisesRegex(ValueError,'finite'):p.spans(candidate((float('nan'),2.)))
        with self.assertRaisesRegex(ValueError,'ordered'):p.spans(candidate((1.,4.5)))

    def test_time_budgets_cover_preparation_and_sealing(self):
        with patch.object(p.time,'monotonic',return_value=601.):
            for phase in ('preparation','predictions_frozen','evaluation_seal','final_receipt_seal'):
                with self.assertRaisesRegex(ValueError,'overall_deadline'):p.guard_deadline(0,phase)
        with patch.object(p.time,'monotonic',return_value=121.):
            with self.assertRaisesRegex(ValueError,'case_deadline'):p.guard_deadline(0,'case_seal',0)

    def test_real_pinned_rhythm_return_shape_and_measured_grid_phase(self):
        rhythm=p.load_module(ROOT/'scripts/rhythm.py','source_test_real_rhythm')
        samples=array('f',[0.])*80000
        for start in range(2000,80000,8000):
            for k in range(24):samples[start+k]=.3 if k%2 else -.3
        analysis=rhythm.analyze(samples,source_start=0.,bpm=None,backend='stdlib')
        self.assertIn('click_grid',analysis);self.assertIn('selected_periodicity',analysis)
        self.assertNotIn('observations',analysis)
        result=p.pulse_settings(analysis);self.assertIsNotNone(result)
        period,origin,provenance=result;grid=analysis['click_grid']
        self.assertAlmostEqual(period,60/grid['bpm'])
        self.assertAlmostEqual(origin,grid['phase_seconds_audio_relative']%period)
        self.assertEqual(provenance['phase_field'],'click_grid.phase_seconds_audio_relative')
        self.assertFalse(provenance['generator_bpm_supplied'])

    def test_pulse_null_fallback_and_schema_guard(self):
        self.assertIsNone(p.pulse_settings({'schema_version':1,'click_grid':None,'selected_periodicity':None}))
        period,origin,evidence=p.pulse_settings({'schema_version':1,'click_grid':None,'selected_periodicity':{'bpm':120.}})
        self.assertEqual((period,origin),(.5,0.));self.assertFalse(evidence['phase_available'])
        with self.assertRaisesRegex(ValueError,'return_schema'):p.pulse_settings({'observations':{}})
        with self.assertRaisesRegex(ValueError,'measured_bpm'):p.pulse_settings({'schema_version':1,'click_grid':{'bpm':float('inf')},'selected_periodicity':None})
        with self.assertRaisesRegex(ValueError,'measured_phase'):p.pulse_settings({'schema_version':1,'click_grid':{'bpm':120,'phase_seconds_audio_relative':True},'selected_periodicity':None})


class InertOrchestrationTests(unittest.TestCase):
    def setUp(self):
        p.AREA.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(prefix='source-only-test-',dir=p.AREA)
        self.directory=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()

    def fixture(self):
        source=self.directory/'opaque-placeholder';source.write_bytes(b'not audio; inert mocked workflow only')
        bank_path=self.directory/'bank.json';cases=[]
        for seed in (617,719):
            for cohort in p.COHORTS:
                identity=f'seed{seed}-{cohort}';source_row={'sha256':p.digest(source)}
                truth={'suite':p.SUITE,'seed':seed,'cohort':cohort,'ground_truth_scope':'generator_only_not_musician',
                       'source':source_row,'recurrence_pairs':p.expected_reference(seed,cohort),'performance_issue_confirmed':False}
                target=self.directory/(identity+'.json');p.write(target,truth,new=True)
                cases.append({'id':identity,'seed':seed,'cohort':cohort,'source':source_row,
                              'truth':{'path':target.name,'sha256':p.digest(target)}})
        bank={'cases':cases};p.write(bank_path,bank,new=True)
        return source,bank_path,bank

    def test_all_twelve_predictions_sealed_before_truth_open_in_inert_runner(self):
        source,bank_path,bank=self.fixture();output=self.directory/'run';helper=p.old_helper()
        authorization={'worker_sha256':p.digest(p.__file__),'sha256':'a'*64,'plan_sha256':'b'*64,'bank_sha256':p.digest(bank_path),
                       'path':'irrelevant-release','plan_path':'irrelevant-plan'}
        owner=self
        class Process:
            pid=99999999
            def __init__(self,argv,**kwargs):
                task=json.loads(Path(argv[argv.index('--child-task')+1]).read_text())
                owner.assertEqual(set(task),{'source','source_sha256','target','sources','controller_sha256','release_sha256','admission_sha256'})
                owner.assertNotIn('seed',json.dumps(task));owner.assertNotIn('cohort',json.dumps(task))
                target=Path(task['target']);prediction={'source_sha256':task['source_sha256'],'arms':{'Araw':[],'Border':[],'L1':[]},
                    'status':'upstream_pulse_unavailable_no_cache','discovery_reference_labels_supplied':False,
                    'localized_count':0,'abstained_count':0,'candidate_failures':[],'performance_issue_confirmed':False}
                p.write(target/'prediction.json',prediction,new=True)
            def wait(self,timeout):owner.assertLessEqual(timeout,112);return 0
        truth_opens=[]
        original_read=helper.read
        def reader(path,expected=None,opened=None):
            if opened is not None:
                owner.assertTrue((output/'predictions-frozen.json').is_file())
                seal=json.loads((output/'predictions-frozen.json').read_text());owner.assertEqual(len(seal['case_prediction_sha256']),12)
                truth_opens.append(str(path))
            return original_read(path,expected,opened)
        inert_plan=self.directory/'inert-plan.json';p.write(inert_plan,p.metadata(),new=True)
        with patch.object(p,'authorized',return_value=(p.metadata(),authorization)),\
             patch.object(p,'validate_bank',return_value=(bank_path,bank,[source]*12,[(source,p.digest(source))])),\
             patch.object(p,'old_helper',return_value=helper),patch.object(helper,'read',side_effect=reader),\
             patch.object(helper,'executable_preflight',return_value=({'inert':True},[])),\
             patch.object(p,'cleanup_owned_group'),patch.object(p,'recheck_bindings'),\
             patch.object(p.subprocess,'Popen',Process),patch('builtins.print'):
            self.assertEqual(p.runner(inert_plan,'b'*64,self.directory/'release','a'*64,bank_path,p.digest(bank_path),output),0)
        self.assertEqual(len(truth_opens),12)
        measured=json.loads((output/'evaluation.json').read_text())
        self.assertEqual(measured['aggregate']['all']['L1']['iou'][0]['fn'],4)
        self.assertEqual(measured['aggregate']['all']['L1']['boundary'][0]['fn'],16)
        self.assertEqual(measured['aggregate']['all']['L1']['iou'][0]['reference_pair_count'],4)

    def test_partial_seal_never_opens_truth(self):
        source,bank_path,bank=self.fixture();output=self.directory/'run';output.mkdir()
        seal=output/'predictions-frozen.json';p.write(seal,{'status':'partial','case_count':1,'case_prediction_sha256':[]})
        opened=[]
        with self.assertRaisesRegex(ValueError,'complete_prediction'):
            p.score_sealed(bank,bank_path,output,[],seal,p.digest(seal),on_truth_open=lambda:opened.append(True))
        self.assertEqual(opened,[])

    def test_symlink_and_traversal_output_rejected(self):
        link=self.directory/'link';link.symlink_to(self.directory)
        with self.assertRaisesRegex(ValueError,'Symlink'):p.artifact_path(link/'new')
        with self.assertRaisesRegex(ValueError,'Artifact'):p.artifact_path(self.directory/'..'/'outside')

    @unittest.skipUnless(os.name=='posix','owned process groups require POSIX')
    def test_owned_exited_leader_live_inert_child_cleanup(self):
        # Creates only a sleeping process: no audio, files, analysis or model work.
        script='import subprocess,sys; subprocess.Popen([sys.executable,"-c","import time;time.sleep(30)"]); print("spawned",flush=True)'
        process=subprocess.Popen([sys.executable,'-c',script],stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                 start_new_session=True,text=True)
        receipts=[]
        try:
            self.assertEqual(process.stdout.readline().strip(),'spawned');process.wait(timeout=5)
            self.assertTrue(p.live_owned_group(process.pid))
            p.cleanup_owned_group(process,receipts,'source_only_inert_owned_group_test')
            self.assertFalse(p.live_owned_group(process.pid))
            self.assertEqual(receipts[0]['ruling'],'R-N11')
            self.assertEqual(receipts[0]['result'],'owned_group_signalled_leader_reaped_no_live_members')
        finally:
            if p.live_owned_group(process.pid):p.cleanup_owned_group(process,receipts,'source_only_inert_finally')
            process.stdout.close();process.stderr.close()


if __name__=='__main__':unittest.main()
