"""S1 protocol/refusal and optional known-component arithmetic checks."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import low_register_s1 as module
AVAILABLE=importlib.util.find_spec('numpy') is not None and importlib.util.find_spec('scipy') is not None

class ProtocolTests(unittest.TestCase):
    def test_plan_has_four_frozen_arms_nine_cases_no_real_media(self):
        plan=module.declaration()
        self.assertEqual(plan['arms'],['bypass','captured_nr8','captured_nr10','protected_mask'])
        self.assertEqual(len(plan['cases']),9)
        self.assertEqual(sum(c['duration_seconds'] for c in plan['cases']),72)
        self.assertEqual(plan['afftdn']['noise_floor_db'],-40)
        self.assertEqual(plan['cases'][-1]['parameters']['fan_line_hz']-plan['cases'][-1]['parameters']['fundamental_hz'],.75)
        self.assertIn('generated_only',plan['truth_scope'])

    def test_output_existing_escape_and_symlink_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()
            with patch.object(module,'ARTIFACTS',root):
                with self.assertRaises(ValueError):module.artifact_path(root,fresh=True)
                with self.assertRaises(ValueError):module.artifact_path(root/'../outside')
                existing=root/'existing';existing.mkdir()
                with self.assertRaises(ValueError):module.artifact_path(existing,fresh=True)
                (root/'link').symlink_to(existing)
                with self.assertRaises(ValueError):module.artifact_path(root/'link'/'output')

    def test_mutated_or_duplicate_plan_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();p=root/'plan.json'
            with patch.object(module,'ARTIFACTS',root):
                plan=module.declaration();module.write_json(p,plan)
                self.assertEqual(module.read_plan(p)[0],plan)
                plan['afftdn']['noise_floor_db']=-35;p.write_text(json.dumps(plan))
                with self.assertRaises(ValueError):module.read_plan(p)
                p.write_text('{"arms":[],"arms":[]}')
                with self.assertRaisesRegex(ValueError,'Duplicate'):module.read_plan(p)

    def test_zero_ratio_explicit(self):
        self.assertEqual(module.ratio(0,0)['status'],'zero_reference')
        self.assertEqual(module.ratio(0,1)['status'],'complete_attenuation')
        self.assertAlmostEqual(module.ratio(.5,1)['value_db'],-3.01029995664)

@unittest.skipUnless(AVAILABLE,'Optional locked NumPy/SciPy environment required')
class NumericalTests(unittest.TestCase):
    def test_bypass_additive_native_metrics_and_clipping_denominator(self):
        np,_,fixtures,_=module.numeric()
        case=module.declaration()['cases'][5]
        arrays,truth=fixtures.components(case)
        clean,noise=(arrays[k].astype(np.float64) for k in ('clean','fan'))
        mix=clean+noise
        row=module.score(clean,noise,mix,mix,clean,noise,clean,truth,'bypass')
        self.assertLess(row['conditional_additivity_max_abs'],1e-15)
        self.assertAlmostEqual(row['guitar_response_energy']['value_db'],0)
        self.assertEqual(row['palm_event_denominator'],6)
        self.assertEqual(row['legato_event_denominator'],1)
        self.assertEqual(row['clipped_sample_values'],0)
        self.assertEqual(row['sample_value_denominator'],case['sample_frames']*2)
        self.assertTrue(row['noise_control_is_mixture_residual'])

    def test_missing_f0_and_collision_gate_exclusions(self):
        np,_,fixtures,_=module.numeric()
        for idx in (1,2,6,8):
            case=module.declaration()['cases'][idx]
            arrays,truth=fixtures.components(case)
            clean,noise=(arrays[k].astype(np.float64) for k in ('clean','fan'))
            row=module.score(clean,noise,clean+noise,clean+noise,clean,noise,clean,truth,'bypass')
            self.assertFalse(row['fundamental_gate_eligible'])
            self.assertEqual(row['fundamental_eligible_channel_event_denominator'],0)
            self.assertFalse(row['missing_f0_recovered'])
            self.assertFalse(row['real_stem_recovered'])

    def test_complete_attenuation_remains_in_denominator_and_fails_gates(self):
        np,_,fixtures,_=module.numeric()
        for idx in (0,5):
            case=module.declaration()['cases'][idx];arrays,truth=fixtures.components(case)
            clean=arrays['clean'].astype(np.float64);noise=arrays['fan'].astype(np.float64)
            zero=np.zeros_like(clean)
            row=module.score(clean,noise,clean+noise,noise,zero,noise,zero,truth,'protected_mask')
            self.assertEqual(row['guitar_response_energy']['status'],'complete_attenuation')
            self.assertGreater(row['active_sample_frame_denominator'],0)
            if idx==0:
                self.assertEqual(row['fundamental_eligible_channel_event_denominator'],2)
                self.assertIn('fundamental_preservation',row['quality_alerts'])
            else:
                self.assertIn('attack_energy',row['quality_alerts'])
                self.assertIn('tail_energy',row['quality_alerts'])
                self.assertIn('legato_energy',row['quality_alerts'])

    def test_non_linear_interaction_not_mislabeled_as_residual_stem(self):
        np,_,fixtures,_=module.numeric()
        case=module.declaration()['cases'][0];arrays,truth=fixtures.components(case)
        clean=arrays['clean'].astype(np.float64);noise=arrays['fan'].astype(np.float64)
        y=.5*clean;n=noise;s=.6*clean
        row=module.score(clean,noise,clean+noise,y,y-n,n,s,truth,'captured_nr8')
        self.assertEqual(row['metric_scope'],'paired_counterfactual_not_stems')
        self.assertFalse(row['noise_control_is_mixture_residual'])
        self.assertIsNone(row['conditional_additivity_max_abs'])
        self.assertIsNotNone(row['interaction_relative_energy']['value_db'])

if __name__=='__main__':unittest.main()
