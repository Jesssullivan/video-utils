"""Independent source-accounting, admission and negative oracle checks."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('low_register_fixture_test',ROOT/'scripts'/'low_register_fixtures.py')
bank=importlib.util.module_from_spec(spec);spec.loader.exec_module(bank)


class MetadataTests(unittest.TestCase):
    def test_declaration_has_bounded_native_coverage_and_unambiguous_sentinels(self):
        plan=bank.declaration();cases=plan['design']['cases']
        self.assertEqual(len(cases),8)
        self.assertEqual(sum(c['duration_seconds'] for c in cases),64)
        self.assertEqual({c['sample_rate'] for c in cases},{44100,48000})
        self.assertEqual({c['channels'] for c in cases},{1,2})
        self.assertEqual(cases[0]['parameters']['sentinel_hz'],32)
        self.assertAlmostEqual(cases[0]['parameters']['fundamental_hz'],32.70319566257483)
        self.assertNotEqual(cases[0]['parameters']['sentinel_hz'],cases[0]['parameters']['fundamental_hz'])
        self.assertFalse(plan['actual_recording_or_profile_used'])
        self.assertFalse(plan['attenuation_executed'])

    def test_plan_requires_identical_parameters_and_generator_before_any_output(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(bank,'ARTIFACTS',Path(tmp).resolve()):
            root=Path(tmp).resolve();path=root/'plan.json';bank.write_new(path,bank.declaration())
            self.assertEqual(bank.read_plan(path)[0],bank.declaration())
            changed=bank.declaration();changed['design']['cases'][0]['parameters']['gain']=.3
            path.write_text(json.dumps(changed))
            with self.assertRaisesRegex(ValueError,'Frozen'):
                bank.generate(path,root/'out')
            self.assertFalse((root/'out').exists())

    def test_plan_rejects_duplicate_nonfinite_and_outside_paths(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(bank,'ARTIFACTS',Path(tmp).resolve()):
            root=Path(tmp).resolve();path=root/'plan.json'
            for raw in ('{"a":1,"a":2}','{"a":NaN}'):
                path.write_text(raw)
                with self.assertRaises(ValueError):bank.read_plan(path)
            with self.assertRaises(ValueError):bank.local_path(root/'..'/'outside')
            with self.assertRaises(ValueError):bank.local_path(root)
            outside=root/'real';outside.mkdir();link=root/'link';link.symlink_to(outside)
            with self.assertRaises(ValueError):bank.local_path(link/'new')

    def test_declaration_write_never_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'plan.json';bank.write_new(path,{'value':1})
            with self.assertRaises(FileExistsError):bank.write_new(path,{'value':2})
            self.assertEqual(json.loads(path.read_text()),{'value':1})


class OracleTests(unittest.TestCase):
    def setUp(self):
        self.np,self.wavfile,_=bank.numeric()
        self.cases=bank.declaration()['design']['cases']

    def test_independent_rendered_additivity_and_capture_for_all_eight_cases(self):
        with tempfile.TemporaryDirectory() as tmp:
            for case in self.cases:
                arrays,truth=bank.components(case);bank.verify_oracles(arrays,case)
                self.assertEqual(truth['case']['sample_frames'],8*case['sample_rate'])
                for key in ('clean','fan','mixture'):
                    path=Path(tmp)/(key+'.wav');x=arrays[key]
                    self.wavfile.write(path,case['sample_rate'],x[:,0] if case['channels']==1 else x)
                    rr,y=self.wavfile.read(path)
                    y=y[:,None] if y.ndim==1 else y
                    self.assertEqual(rr,case['sample_rate']);self.assertTrue(self.np.array_equal(x,y))
                    self.assertLess(self.np.max(self.np.abs(y)),1)
                error=self.np.max(self.np.abs(arrays['clean'].astype(float)+arrays['fan'].astype(float)-arrays['mixture'].astype(float)))
                self.assertLessEqual(error,2e-7)
                self.assertTrue(self.np.all(arrays['clean'][:round(.8*case['sample_rate'])]==0))

    def test_missing_f0_joint_fit_is_absent_but_deliberate_injection_fails(self):
        case=self.cases[6];arrays,_=bank.components(case)
        check=bank.verify_oracles(arrays,case)
        self.assertLess(check['missing_f0_joint_fit_amplitude'],5e-5)
        for actual,(_,expected) in zip(check['joint_fit_harmonic_amplitudes'],case['parameters']['harmonics']):
            self.assertAlmostEqual(actual,expected,delta=5e-5)
        rate=case['sample_rate'];t=self.np.arange(case['sample_frames'])/rate
        injection=.002*self.np.sin(2*self.np.pi*case['parameters']['fundamental_hz']*t)
        injection[:rate]=0;injection[round(7.5*rate):]=0
        arrays['clean']=(arrays['clean']+injection[:,None]).astype('<f4')
        arrays['mixture']=(arrays['clean'].astype(float)+arrays['fan'].astype(float)).astype('<f4')
        with self.assertRaisesRegex(ValueError,'Missing F0'):bank.verify_oracles(arrays,case)

    def test_collision_has_distinct_components_with_exactly_same_mixture(self):
        case=self.cases[2];arrays,truth=bank.components(case)
        self.assertTrue(truth['non_identifiable']);self.assertFalse(truth['fundamental_gain_applicable'])
        rate=case['sample_rate'];t=self.np.arange(case['sample_frames'])/rate
        u=.02*self.np.sin(2*self.np.pi*bank.frequency(24)*t)
        u[:rate]=0;u[round(7.5*rate):]=0
        original=arrays['clean'].astype(float)+arrays['fan'].astype(float)
        alt=(arrays['clean'].astype(float)+u[:,None])+(arrays['fan'].astype(float)-u[:,None])
        self.assertGreater(self.np.max(self.np.abs(u)),.019)
        self.assertLess(self.np.max(self.np.abs(original-alt)),1e-10)
        self.assertFalse(self.np.array_equal(arrays['fan'][:,0],arrays['fan'][:,1]))

    def test_same_frozen_mask_additivity_and_broken_reference_negative_control(self):
        rng=self.np.random.default_rng(31)
        clean=rng.standard_normal((128,2))+1j*rng.standard_normal((128,2))
        fan=rng.standard_normal((128,2))+1j*rng.standard_normal((128,2))
        mask=rng.uniform(.2,1,(128,2))
        self.assertLess(bank.verify_same_mask(clean,fan,clean+fan,mask),1e-10)
        with self.assertRaisesRegex(ValueError,'accounting'):
            bank.verify_same_mask(clean,fan,clean+fan+.001,mask)
        with self.assertRaises(ValueError):bank.verify_same_mask(clean,fan,(clean+fan)[:-1],mask)

    def test_gain_envelope_and_pure_controls_have_correct_component_scope(self):
        clean,_=bank.components(self.cases[0]);self.assertFalse(self.np.any(clean['fan']))
        fan,_=bank.components(self.cases[1]);self.assertFalse(self.np.any(fan['clean']))
        arrays,_=bank.components(self.cases[7])
        for role in ('clean','fan'):
            self.assertLess(self.np.max(self.np.abs(arrays[role]-arrays['base_'+role].astype(float)*arrays['shared_gain'])),2e-7)
        self.assertLess(self.np.min(arrays['shared_gain']),.61)
        self.assertGreater(self.np.max(arrays['shared_gain']),1.19)

    def test_waveform_changes_extent_clipping_and_nonfinite_fail(self):
        case=self.cases[0];arrays,_=bank.components(case)
        for defect in ('extent','clip','nonfinite','mixture','capture'):
            bad={k:v.copy() for k,v in arrays.items()}
            if defect=='extent':bad['fan']=bad['fan'][:-1]
            elif defect=='clip':bad['mixture'][case['sample_rate']]=1.1
            elif defect=='nonfinite':bad['fan'][case['sample_rate']]=float('nan')
            elif defect=='mixture':bad['mixture'][case['sample_rate']]+=.001
            else:
                bad['clean'][0]=.001;bad['mixture'][0]=.001
            with self.assertRaises(ValueError):bank.verify_oracles(bad,case)


if __name__=='__main__':unittest.main()
