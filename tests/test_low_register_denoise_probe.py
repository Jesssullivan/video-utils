"""Independent waveform/clock/accounting oracles for the optional prototype."""
import importlib.util
import math
from pathlib import Path
import sys
import unittest

AVAILABLE=importlib.util.find_spec('numpy') is not None and importlib.util.find_spec('scipy') is not None
if AVAILABLE:
    import numpy as np
    path=Path(__file__).resolve().parents[1]/'scripts'/'low_register_denoise_probe.py'
    spec=importlib.util.spec_from_file_location('low_register_probe',path)
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)


@unittest.skipUnless(AVAILABLE,'Optional locked NumPy/SciPy analysis environment required')
class LowRegisterProbeTests(unittest.TestCase):
    def source(self,rate=44100,channels=1,frames=61637):
        t=np.arange(frames)/rate
        x=.17*np.sin(2*np.pi*32*t)+.04*np.cos(2*np.pi*130.81*t)
        if channels==2:return np.column_stack((x,.11*np.sin(2*np.pi*32.70319566*t+.4)))
        return x[:,None]

    def all_one(self,pcm,config):
        frames=module.analyze_native(pcm,config=config)
        return module.FrozenGain(np.ones_like(frames.coefficients.real),len(pcm),pcm.shape[1],module.grid(config),config)

    def test_native_bypass_preserves_low_fundamental_edges_and_irregular_extent(self):
        for rate,channels,n in [(44100,1,61637),(48000,2,67333),(44100,1,1)]:
            with self.subTest(rate=rate,channels=channels,frames=n):
                x=self.source(rate,channels,n);x[0]=.31;x[-1]=-.27
                config=module.MaskConfig(rate);gain=self.all_one(x,config)
                y=module.apply_frozen_gain(x,gain,config=config)
                self.assertEqual(y.shape,x.shape)
                self.assertLess(float(np.max(np.abs(y-x))),1e-10)

    def test_density_has_units_and_channel_specific_native_capture_support(self):
        rate=48000;n=round(.8*rate);t=np.arange(n)/rate
        x=np.column_stack((.1*np.sin(2*np.pi*1500*t),.2*np.sin(2*np.pi*1500*t)))
        config=module.MaskConfig(rate)
        capture=module.fit_capture_density(x,config=config,source_sha256='a'*64,decoded_start_sample=17,decoded_end_sample=17+n)
        df=rate/config.frame_samples
        # Integrating a full-support bin-centered sine PSD yields A²/2.
        self.assertAlmostEqual(float(np.sum(capture.density[0])*df),.005,places=7)
        self.assertAlmostEqual(float(np.sum(capture.density[1])*df),.020,places=7)
        self.assertEqual(capture.full_frame_count,(n-8192)//2048+1)
        self.assertFalse(capture.density.flags.writeable)

    def test_capture_rejects_partial_support_bad_hash_and_indices(self):
        config=module.MaskConfig(44100)
        for x,start,end,sha in [(np.zeros((10000,1)),0,10000,'a'*64),(np.zeros((35000,1)),2,35000,'a'*64),(np.zeros((35000,1)),0,35000,'x'*64)]:
            with self.assertRaises(ValueError):module.fit_capture_density(x,config=config,source_sha256=sha,decoded_start_sample=start,decoded_end_sample=end)

    def test_four_settings_enforce_continuous_low_floor_without_frame_exceptions(self):
        for low in (0.,.5):
            for scale in (.5,1.):
                config=module.MaskConfig(44100,low_ceiling_db=low,noise_density_scale=scale)
                x=self.source();capture=module.fit_capture_density(x[:35280],config=config,source_sha256='a'*64,decoded_start_sample=0,decoded_end_sample=35280)
                gains=module.derive_gain(module.analyze_native(x,config=config),capture,config=config)
                f=np.fft.rfftfreq(8192,1/44100);floor=module.gain_floor(config)
                self.assertTrue(np.all(gains.gains>=floor))
                self.assertTrue(np.all(gains.gains<=1))
                self.assertTrue(np.allclose(floor[f<=80],10**(-low/20)))
                self.assertTrue(np.allclose(floor[f>=140],10**(-8/20)))
                self.assertTrue(np.all(np.diff(floor)<=1e-15))
                self.assertFalse(gains.gains.flags.writeable)

    def test_zero_capture_is_exact_gain_one_not_noise_reduction_credit(self):
        config=module.MaskConfig(44100);x=self.source()
        cap=module.fit_capture_density(np.zeros((35280,1)),config=config,source_sha256='b'*64,decoded_start_sample=0,decoded_end_sample=35280)
        gains=module.derive_gain(module.analyze_native(x,config=config),cap,config=config)
        self.assertTrue(np.array_equal(gains.gains,np.ones_like(gains.gains)))
        self.assertLess(float(np.max(np.abs(module.apply_frozen_gain(x,gains,config=config)-x))),1e-10)
        self.assertEqual(module.db_ratio(0,0)['status'],'zero_reference')
        self.assertEqual(module.db_ratio(0,1)['status'],'complete_attenuation')

    def test_same_frozen_mask_linear_accounting_even_for_exact_collision(self):
        config=module.MaskConfig(48000);s=self.source(48000,2,70001)
        t=np.arange(len(s))/48000;n=np.column_stack((.04*np.sin(2*np.pi*32*t),.03*np.sin(2*np.pi*32.70319566*t+.4)))
        capture=module.fit_capture_density(n[:38400],config=config,source_sha256='c'*64,decoded_start_sample=0,decoded_end_sample=38400)
        gain=module.derive_gain(module.analyze_native(s+n,config=config),capture,config=config)
        ys=module.apply_frozen_gain(s,gain,config=config);yn=module.apply_frozen_gain(n,gain,config=config)
        y=module.apply_frozen_gain(s+n,gain,config=config)
        self.assertLess(float(np.max(np.abs(ys+yn-y))),1e-10)
        u=.02*np.sin(2*np.pi*32*t)[:,None]
        self.assertLess(float(np.max(np.abs((s+u)+(n-u)-(s+n)))),1e-10)
        self.assertGreater(float(np.max(np.abs(u))),.01)

    def test_adaptive_increment_is_not_conditional_music_component(self):
        config=module.MaskConfig(44100);s=self.source();n=.2*self.source()
        cap=module.fit_capture_density(n[:35280],config=config,source_sha256='d'*64,decoded_start_sample=0,decoded_end_sample=35280)
        def operation(pcm):
            mask=module.derive_gain(module.analyze_native(pcm,config=config),cap,config=config)
            return module.apply_frozen_gain(pcm,mask,config=config),mask
        mixed,gain=operation(s+n);noise,_=operation(n)
        conditional=module.apply_frozen_gain(s,gain,config=config)
        self.assertGreater(float(np.max(np.abs((mixed-noise)-conditional))),1e-5)

    def test_rejects_frame_clock_channel_extent_and_nonfinite_changes(self):
        x=self.source();config=module.MaskConfig(44100);gain=self.all_one(x,config)
        for bad,cfg in [(x[:-1],config),(np.repeat(x,2,axis=1),config),(x,module.MaskConfig(48000)),(x*np.nan,config)]:
            with self.assertRaises(ValueError):module.apply_frozen_gain(bad,gain,config=cfg)

    def test_harmonic_fit_measures_damage_without_loudness_or_delay_fitting(self):
        rate=44100;x=self.source(frames=rate*2)
        y=x*10**(-.7/20)
        metrics=module.harmonic_gain(x,y,rate,1000,rate*2-1000,32,[1,4])
        f0=next(row for row in metrics['rows'] if row['harmonic']==1)
        self.assertAlmostEqual(f0['value_db'],-.7,places=8)
        missing=module.harmonic_gain(np.zeros_like(x),np.zeros_like(x),rate,0,len(x),32,[1])
        self.assertEqual(missing['rows'][0]['status'],'source_harmonic_below_fit_threshold')

    def test_attack_oracle_catches_shift_and_tail_loss(self):
        rate=44100;n=rate*2;onset=rate;age=(np.arange(n)-onset)/rate
        env=np.where(age>=0,np.minimum(np.maximum(age,0)/.005,1)*np.exp(-np.maximum(age,0)/.09),0)
        source=(np.exp(-((age-.006)/.001)**2)+.01*env*np.sin(2*np.pi*32.70319566*np.arange(n)/rate))[:,None]
        event={'start_sample':onset,'end_sample':onset+round(.4*rate)}
        shifted=np.roll(source,round(.005*rate))
        metrics=module.temporal_metrics(source,shifted,event,rate)
        self.assertGreater(abs(metrics['centroid_shift_ms']),2)
        attenuated=module.temporal_metrics(source,source*.5,event,rate)
        self.assertAlmostEqual(attenuated['tail_energy']['value_db'],20*math.log10(.5),places=8)


if __name__=='__main__':unittest.main()
