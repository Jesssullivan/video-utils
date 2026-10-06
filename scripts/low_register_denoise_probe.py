#!/usr/bin/env python3
"""Unregistered offline synthetic low-register fixed-mask comparison.

Discovery sees only mixture/capture data; every mask is sealed before oracle
components are loaded. No actual-take restoration or default-profile mutation.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import time
import uuid

# Set before NumPy/SciPy imports; this module is deliberately optional in CI.
for _key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMBA_NUM_THREADS'):
    os.environ[_key] = '2'
import numpy as np
from scipy.io import wavfile

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / 'artifacts' / 'benchmarks'
MAX_JSON = 1_000_000
THRESHOLDS = {
    'bypass_float64_max_abs': 1e-10, 'conditional_additivity_float64_max_abs': 1e-10,
    'serialized_input_additivity_max_abs': 2e-7, 'serialized_conditional_max_abs': 4e-7,
    'fundamental_loss_db': .5, 'fundamental_boost_db': .1,
    'attack_energy_loss_db': 1., 'attack_energy_boost_db': .5,
    'attack_centroid_shift_ms': 2., 'tail_energy_loss_db': 1., 'tail_energy_boost_db': .5,
    'preattack_relative_rms_db': -35., 'broadband_noise_reduction_db': 3.,
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def array_digest(array):
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def bounded_json(path):
    path = Path(path)
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_JSON:
        raise ValueError('Expected bounded regular JSON')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate JSON key')
            result[key] = value
        return result
    def reject(value):
        raise ValueError('Nonfinite JSON')
    value = json.loads(path.read_bytes(), object_pairs_hook=pairs, parse_constant=reject)
    canonical(value)  # rejects overflow-to-infinity values too
    return value


def write_json(path, value):
    raw = canonical(value) + b'\n'
    if len(raw) > MAX_JSON:
        raise ValueError('Result metadata bound exceeded')
    with Path(path).open('xb') as stream:
        stream.write(raw)


def checked_path(base, relative):
    p = Path(relative)
    if p.is_absolute() or '..' in p.parts:
        raise ValueError('Artifact path escapes input root')
    p = base / p
    if any(q.is_symlink() for q in (p, *p.parents)) or not p.is_file():
        raise ValueError('Expected nonsymlink regular artifact')
    return p


@dataclass(frozen=True)
class MaskConfig:
    sample_rate: int
    frame_samples: int = 8192
    hop_samples: int = 2048
    protected_end_hz: float = 80.
    taper_end_hz: float = 140.
    low_ceiling_db: float = .5
    broadband_ceiling_db: float = 8.
    noise_density_scale: float = 1.

    def validate(self):
        if (self.sample_rate not in (44100, 48000) or self.frame_samples != 8192
                or self.hop_samples != 2048 or self.protected_end_hz != 80
                or self.taper_end_hz != 140 or self.low_ceiling_db not in (0., .5)
                or self.broadband_ceiling_db != 8.
                or self.noise_density_scale not in (.5, 1.)):
            raise ValueError('Configuration outside frozen four-setting contract')


@dataclass(frozen=True)
class NativeFrames:
    coefficients: np.ndarray
    sample_frames: int
    channels: int
    left_padding: int
    right_padding: int
    native_starts: np.ndarray
    config_grid: tuple


@dataclass(frozen=True)
class CaptureDensity:
    density: np.ndarray
    full_frame_count: int
    source_sha256: str
    decoded_start_sample: int
    decoded_end_sample: int
    config_grid: tuple


@dataclass(frozen=True)
class FrozenGain:
    gains: np.ndarray
    sample_frames: int
    channels: int
    config_grid: tuple
    config: MaskConfig


def pcm_checked(pcm):
    data = np.asarray(pcm, dtype=np.float64)
    if data.ndim != 2 or not 1 <= data.shape[1] <= 2 or not len(data) or not np.isfinite(data).all():
        raise ValueError('Expected finite nonempty native [sample,channel] PCM')
    return np.ascontiguousarray(data)


def grid(config):
    config.validate()
    return (config.sample_rate, config.frame_samples, config.hop_samples)


def window(config):
    return .5 - .5 * np.cos(2 * np.pi * np.arange(config.frame_samples) / config.frame_samples)


def density(coefficients, config):
    weights = np.full(config.frame_samples // 2 + 1, 2.)
    weights[[0, -1]] = 1.
    return np.abs(coefficients) ** 2 * weights / (config.sample_rate * np.sum(window(config) ** 2))


def analyze_native(pcm, *, config):
    data = pcm_checked(pcm)
    g = grid(config)
    length, hop = config.frame_samples, config.hop_samples
    extra = (-(len(data) + length)) % hop
    padded = np.pad(data, ((length, length + extra), (0, 0)))
    starts = np.arange(0, len(padded) - length + 1, hop, dtype=np.int64)
    frames = np.stack([padded[i:i+length].T for i in starts])
    coefficients = np.fft.rfft(frames * window(config), n=length, axis=-1, norm='backward')
    return NativeFrames(coefficients, len(data), data.shape[1], length, length + extra, starts-length, g)


def fit_capture_density(capture_pcm, *, config, source_sha256, decoded_start_sample, decoded_end_sample):
    data = pcm_checked(capture_pcm)
    g = grid(config)
    if (not isinstance(decoded_start_sample, int) or not isinstance(decoded_end_sample, int)
            or decoded_start_sample < 0 or decoded_end_sample-decoded_start_sample != len(data)
            or len(source_sha256) != 64 or any(c not in '0123456789abcdef' for c in source_sha256)):
        raise ValueError('Capture native indices or identity invalid')
    starts = range(0, len(data)-config.frame_samples+1, config.hop_samples)
    frames = [data[i:i+config.frame_samples].T for i in starts]
    if len(frames) < 4:
        raise ValueError('At least four fully contained capture frames required')
    coefficients = np.fft.rfft(np.stack(frames) * window(config), axis=-1, norm='backward')
    estimate = np.mean(density(coefficients, config), axis=0)
    estimate.setflags(write=False)
    return CaptureDensity(estimate, len(frames), source_sha256, decoded_start_sample, decoded_end_sample, g)


def gain_floor(config):
    config.validate()
    f = np.fft.rfftfreq(config.frame_samples, 1/config.sample_rate)
    broad, low = 10**(-config.broadband_ceiling_db/20), 10**(-config.low_ceiling_db/20)
    blend = np.clip((f-config.protected_end_hz)/(config.taper_end_hz-config.protected_end_hz), 0, 1)
    return broad + (low-broad) * (1+np.cos(np.pi*blend))/2


def derive_gain(mixture_frames, capture, *, config):
    if mixture_frames.config_grid != grid(config) or capture.config_grid != grid(config):
        raise ValueError('Capture/mixture grid mismatch')
    if capture.density.shape != mixture_frames.coefficients.shape[1:]:
        raise ValueError('Capture channels or frequency bins mismatch')
    py = density(mixture_frames.coefficients, config)
    q = config.noise_density_scale * capture.density
    ps = np.maximum(py-q, 0)
    gains = ps/(ps+q+1e-24)
    gains = np.where(q == 0, 1., gains)
    gains = np.maximum(gains, gain_floor(config))
    if not np.isfinite(gains).all() or np.any(gains > 1) or np.any(gains < gain_floor(config)):
        raise ValueError('Invalid gains')
    gains.setflags(write=False)
    return FrozenGain(gains, mixture_frames.sample_frames, mixture_frames.channels, grid(config), config)


def apply_frozen_gain(pcm, gain, *, config):
    data = pcm_checked(pcm)
    frames = analyze_native(data, config=config)
    if (gain.config_grid != grid(config) or gain.sample_frames != len(data)
            or gain.channels != data.shape[1] or gain.gains.shape != frames.coefficients.shape
            or not np.isfinite(gain.gains).all() or np.any(gain.gains < 0) or np.any(gain.gains > 1)):
        raise ValueError('Frozen gain/native support mismatch')
    w = window(config)
    parts = np.fft.irfft(frames.coefficients*gain.gains, n=config.frame_samples, axis=-1, norm='backward')*w
    count = len(data) + frames.left_padding + frames.right_padding
    result = np.zeros((count, data.shape[1])); denominator = np.zeros(count)
    for part, native_start in zip(parts, frames.native_starts):
        start = int(native_start)+frames.left_padding
        result[start:start+config.frame_samples] += part.T
        denominator[start:start+config.frame_samples] += w*w
    a, b = frames.left_padding, frames.left_padding+len(data)
    if np.min(denominator[a:b]) <= 0:
        raise ValueError('NOLA failure on native support')
    result = result[a:b]/denominator[a:b,None]
    if not np.isfinite(result).all():
        raise ValueError('Nonfinite reconstructed output')
    return result


def read_pcm(path, rate, channels, count):
    if path.stat().st_size > 8_000_000:
        raise ValueError('Audio byte bound exceeded')
    actual_rate, data = wavfile.read(path)
    if data.dtype != np.float32:
        raise ValueError('Expected canonical float32 fixture PCM')
    data = data[:,None] if data.ndim == 1 else data
    data = pcm_checked(data)
    if actual_rate != rate or data.shape != (count, channels):
        raise ValueError('Fixture native header/extent mismatch')
    return data


def db_ratio(after, before, factor=10.):
    if before == 0:
        return {'value_db': None, 'status': 'zero_reference'}
    if after == 0:
        return {'value_db': None, 'status': 'complete_attenuation'}
    return {'value_db': factor*math.log10(after/before), 'status': 'measured'}


def band_power(data, rate, low, high):
    w = .5-.5*np.cos(2*np.pi*np.arange(len(data))/len(data))
    coeff = np.fft.rfft(data*w[:,None], axis=0)
    f = np.fft.rfftfreq(len(data), 1/rate)
    weights = np.full(len(f), 2.); weights[0] = 1.
    if len(data)%2 == 0:
        weights[-1] = 1.
    p = np.abs(coeff)**2*weights[:,None]/(rate*np.sum(w*w))
    return float(np.sum(p[(f>=low)&(f<high)])*rate/len(data))


def harmonic_gain(before, after, rate, start, end, frequency, harmonics):
    a, b = start, end
    t = np.arange(a,b)/rate
    hs = sorted(set([1]+list(harmonics)))
    basis = np.column_stack([fn(2*np.pi*h*frequency*t) for h in hs for fn in (np.sin,np.cos)]+[np.ones(len(t))])
    condition = float(np.linalg.cond(basis))
    if len(t) < rate or condition > 1e8:
        return {'status': 'unsupported_fit', 'sample_count': len(t), 'condition_number': condition}
    x = np.linalg.lstsq(basis,before[a:b],rcond=None)[0]
    y = np.linalg.lstsq(basis,after[a:b],rcond=None)[0]
    rows = []
    for i,h in enumerate(hs):
        xa,ya = np.hypot(x[2*i],x[2*i+1]),np.hypot(y[2*i],y[2*i+1])
        for ch in range(before.shape[1]):
            ratio = db_ratio(float(ya[ch]), float(xa[ch]),20) if xa[ch]>5e-5 else {'value_db':None,'status':'source_harmonic_below_fit_threshold'}
            rows.append({'harmonic':h,'channel':ch,'source_amplitude':float(xa[ch]),'output_amplitude':float(ya[ch]),**ratio})
    return {'status':'measured','sample_count':len(t),'condition_number':condition,'rows':rows}


def temporal_metrics(before, after, event, rate):
    onset = event['start_sample']; stop = event['end_sample']; n20 = round(.020*rate)
    attack_before = before[onset:onset+n20]; attack_after = after[onset:onset+n20]
    eb,ea = float(np.sum(attack_before**2)),float(np.sum(attack_after**2))
    ratio = db_ratio(ea,eb)
    positions=np.arange(len(attack_before))/rate
    cb=float(np.sum(positions*np.sum(attack_before**2,axis=1))/eb) if eb else None
    ca=float(np.sum(positions*np.sum(attack_after**2,axis=1))/ea) if ea else None
    ta,tb=onset+round(.05*rate),min(onset+round(.25*rate),stop)
    tail=db_ratio(float(np.mean(after[ta:tb]**2)),float(np.mean(before[ta:tb]**2))) if tb>ta else {'value_db':None,'status':'no_tail_support'}
    pre=after[max(0,onset-round(.1*rate)):onset]
    pre_ratio=db_ratio(float(np.mean(pre**2)),eb/attack_before.size) if len(pre) else {'value_db':None,'status':'no_preattack_support'}
    return {'start_sample':onset,'end_sample':stop,'attack_energy':ratio,
      'centroid_shift_ms':1000*(ca-cb) if ca is not None and cb is not None else None,
      'tail_energy':tail,'preattack_relative_rms':pre_ratio}


def evaluate_known_components(*, clean, noise, mixture, frozen_gain, truth, processed_mixture):
    config=frozen_gain.config;rate=config.sample_rate
    s=apply_frozen_gain(clean,frozen_gain,config=config)
    n=apply_frozen_gain(noise,frozen_gain,config=config)
    exact=apply_frozen_gain(clean+noise,frozen_gain,config=config)
    conditional=float(np.max(np.abs(s+n-exact)))
    rounded=float(np.max(np.abs(s+n-processed_mixture)))
    input_round=float(np.max(np.abs(clean+noise-mixture)))
    hard=[];quality=[]
    for name,value,limit in [('conditional_additivity',conditional,1e-10),('serialized_conditional',rounded,4e-7),('input_additivity',input_round,2e-7)]:
        if value>limit:hard.append(name)
    case=truth['case'];params=case['parameters'];gain_rows=[];temporal=[]
    for event in truth['events']:
        if event['frequency_hz'] is None:continue
        start=event['start_sample']+round(.10*rate);end=event['end_sample']-round(.10*rate)
        if end-start>=rate:
            hs=[int(h[0]) for h in params.get('harmonics',[[1,1],[2,.25],[3,.15],[4,.1]])]
            row=harmonic_gain(clean,s,rate,start,end,event['frequency_hz'],hs)
            row['event_start_sample']=event['start_sample'];gain_rows.append(row)
        if event['kind']=='palm_mute':temporal.append(temporal_metrics(clean,s,event,rate))
    if truth.get('fundamental_gain_applicable'):
        for row in gain_rows:
            for h in row.get('rows',[]):
                if h['harmonic']==1 and (h['status']=='complete_attenuation' or (h['value_db'] is not None and not -.5<=h['value_db']<=.1)):
                    quality.append('fundamental_gain')
    for row in temporal:
        for label,low,high in [('attack_energy',-1.,.5),('tail_energy',-1.,.5)]:
            r=row[label]
            if r['status']=='complete_attenuation' or (r['value_db'] is not None and not low<=r['value_db']<=high):quality.append(label)
        if row['centroid_shift_ms'] is not None and abs(row['centroid_shift_ms'])>2:quality.append('attack_centroid')
        r=row['preattack_relative_rms']
        if r['value_db'] is not None and r['value_db']>-35:quality.append('preattack_leakage')
    bands={}
    for low,high in [(20,45),(45,120),(140,8000)]:
        bands[f'{low}-{high}']=db_ratio(band_power(n,rate,low,high),band_power(noise,rate,low,high))
    # Tonal-only noise's Hann leakage is not an applicable broadband source.
    broadband_applicable=bool(params.get('noise_rms',0)>0)
    r=bands['140-8000']
    if broadband_applicable and r['value_db'] is not None and r['value_db']>-3:quality.append('broadband_noise_reduction')
    return {'conditional_additivity_max_abs':conditional,'serialized_conditional_max_abs':rounded,
      'input_rounding_max_abs':input_round,'hard_failures':hard,'quality_alerts':sorted(set(quality)),
      'non_identifiable':bool(truth['non_identifiable']),
      'recovered_real_stem':False,'fundamental_gain_applicable':bool(truth['fundamental_gain_applicable']),
      'harmonic_gains':gain_rows,'isolated_attack_metrics':temporal,'noise_band_power_change':bands,
      'broadband_noise_gate_applicable':broadband_applicable,
      'music_relative_error':db_ratio(float(np.sum((s-clean)**2)),float(np.sum(clean**2))),
      'source_components_scope':'synthetic conditional same-mask accounting only'}


def deadline_check(deadline):
    if time.monotonic()>deadline:raise TimeoutError('120-second comparison deadline exceeded')


def run(discovery_index, fixture_index, output):
    started=time.monotonic();deadline=started+120;worker_hash=digest(Path(__file__))
    discovery_index=Path(discovery_index).absolute();fixture_index=Path(fixture_index).absolute()
    dest=Path(output).absolute()
    if ('..' in dest.parts or not dest.is_relative_to(ARTIFACTS) or dest==ARTIFACTS
            or dest.exists() or any(p.is_symlink() for p in (dest,*dest.parents))):
        raise ValueError('Output must be new nonsymlink directory beneath artifacts/benchmarks')
    discovery=bounded_json(discovery_index);discovery_hash=digest(discovery_index)
    rows=discovery['cases']
    if len(rows)!=8 or len({r['alias'] for r in rows})!=8 or discovery.get('truth_supplied') is not False:
        raise ValueError('Expected eight opaque truth-free discovery inputs')
    if any(r['sample_frames']!=8*r['sample_rate'] or r['sample_rate'] not in (44100,48000) or r['channels'] not in (1,2) for r in rows):
        raise ValueError('Native fixture bank bounds exceeded')
    stage=dest.parent/('.'+dest.name+'-stage-'+uuid.uuid4().hex)
    stage.mkdir(parents=True,exist_ok=False);jobs=[];source_checks={}
    try:
        # Phase one: NO fixture-index/truth/component read occurs in this loop.
        for row in rows:
            deadline_check(deadline)
            alias=row['alias']
            if len(alias)!=4 or not alias.startswith('lr') or not alias[2:].isdigit():raise ValueError('Nonopaque alias')
            path=checked_path(discovery_index.parent,row['mixture']['path'])
            sha=digest(path)
            if sha!=row['mixture']['sha256']:raise ValueError('Mixture hash mismatch')
            source_checks[str(path)]=sha
            rate,channels,count=row['sample_rate'],row['channels'],row['sample_frames']
            pcm=read_pcm(path,rate,channels,count)
            capture_indices=row.get('capture_samples',[0,round(.8*rate)])
            if capture_indices!=[0,round(.8*rate)]:raise ValueError('Capture outside frozen native interval')
            for low in (0.,.5):
                for scale in (.5,1.):
                    deadline_check(deadline)
                    config=MaskConfig(rate,low_ceiling_db=low,noise_density_scale=scale)
                    frames=analyze_native(pcm,config=config)
                    capture=fit_capture_density(pcm[:round(.8*rate)],config=config,source_sha256=sha,decoded_start_sample=0,decoded_end_sample=round(.8*rate))
                    gain=derive_gain(frames,capture,config=config)
                    processed=apply_frozen_gain(pcm,gain,config=config)
                    bypass=FrozenGain(np.ones_like(gain.gains),count,channels,grid(config),config)
                    bypass_error=float(np.max(np.abs(apply_frozen_gain(pcm,bypass,config=config)-pcm)))
                    if bypass_error>1e-10:raise ValueError('Bypass reconstruction failed')
                    name=f'{alias}-p{low:g}-n{scale:g}';folder=stage/name;folder.mkdir()
                    for key,data in [('mask',gain.gains),('density',capture.density),('processed',processed),('residue',pcm-processed)]:
                        np.save(folder/(key+'.npy'),data,allow_pickle=False)
                    hashes={key:digest(folder/(key+'.npy')) for key in ('mask','density','processed','residue')}
                    job={'alias':alias,'variant':name,'config':asdict(config),'source_sha256':sha,
                         'capture_start_sample':0,'capture_end_sample':round(.8*rate),'capture_full_frame_count':capture.full_frame_count,
                         'density_unit':'full-scale-squared/Hz','bypass_error_max_abs':bypass_error,
                         'left_padding':frames.left_padding,'right_padding':frames.right_padding,
                         'frame_count':len(frames.native_starts),'hashes':hashes}
                    write_json(folder/'discovery.json',job);jobs.append(job)
        write_json(stage/'masks-sealed.json',{'schema_version':1,'discovery_index_sha256':discovery_hash,'jobs':jobs,
            'settings_frozen_before_truth':True,'truth_components_read':False,'thresholds':THRESHOLDS})
        sealed_hash=digest(stage/'masks-sealed.json')
        # Phase two begins ONLY after all 32 masks and outputs are saved/hash-bound.
        fixture_hash=digest(fixture_index);fixture=bounded_json(fixture_index)
        if fixture.get('suite')!='low-register-separability-v1' or fixture.get('case_count')!=8 or fixture.get('source_seconds')!=64 or fixture.get('discovery_sha256')!=discovery_hash or fixture.get('no_real_recording_used') is not True:
            raise ValueError('Canonical fixture/discovery binding mismatch')
        frows={r['alias']:r for r in fixture['cases']}
        if set(frows)!=set(r['alias'] for r in rows):raise ValueError('Fixture alias set differs')
        results=[]
        for row in rows:
            deadline_check(deadline);alias=row['alias'];frow=frows[alias]
            truth_path=checked_path(fixture_index.parent,frow['truth'])
            if digest(truth_path)!=frow['truth_sha256']:raise ValueError('Truth hash mismatch')
            truth=bounded_json(truth_path)
            if truth['components']!=frow['components'] or truth['case']['alias']!=alias:raise ValueError('Truth component binding mismatch')
            if (truth.get('truth_for_evaluation_only') is not True or truth.get('no_intended_score_or_real_notes') is not True
                    or any(truth['case'][key]!=row[key] for key in ('sample_rate','channels','sample_frames'))):
                raise ValueError('Truth native context or claim contract differs')
            component={}
            for key in ('clean','fan','mixture'):
                info=frow['components'][key];path=checked_path(fixture_index.parent,info['path']);sha=digest(path)
                if sha!=info['sha256']:raise ValueError('Component hash mismatch')
                source_checks[str(path)]=sha;component[key]=read_pcm(path,row['sample_rate'],row['channels'],row['sample_frames'])
            if frow['components']['mixture']!=row['mixture']:raise ValueError('Discovery mixture differs from oracle mixture')
            if np.any(component['clean'][:round(.8*row['sample_rate'])]):raise ValueError('Generated noise capture contains musical oracle component')
            for job in [j for j in jobs if j['alias']==alias]:
                deadline_check(deadline);folder=stage/job['variant'];config=MaskConfig(**job['config'])
                for key,sha in job['hashes'].items():
                    if digest(folder/(key+'.npy'))!=sha:raise ValueError('Sealed output changed')
                gains=np.load(folder/'mask.npy',allow_pickle=False);gains.setflags(write=False)
                frozen=FrozenGain(gains,row['sample_frames'],row['channels'],grid(config),config)
                output_pcm=np.load(folder/'processed.npy',allow_pickle=False)
                metric=evaluate_known_components(clean=component['clean'],noise=component['fan'],mixture=component['mixture'],frozen_gain=frozen,truth=truth,processed_mixture=output_pcm)
                write_json(folder/'evaluation.json',metric);results.append({'alias':alias,'variant':job['variant'],'metrics':metric})
        for path,sha in source_checks.items():
            if digest(path)!=sha:raise ValueError('Source changed during comparison')
        if digest(discovery_index)!=discovery_hash or digest(fixture_index)!=fixture_hash or digest(stage/'masks-sealed.json')!=sealed_hash or digest(Path(__file__))!=worker_hash:
            raise ValueError('Index/seal changed during comparison')
        deadline_check(deadline)
        hard=sum(len(r['metrics']['hard_failures']) for r in results)
        result={'schema_version':1,'status':'synthetic_measurements_complete' if not hard else 'hard_failure',
            'worker_sha256':worker_hash,'fixture_index_sha256':fixture_hash,'discovery_index_sha256':discovery_hash,
            'masks_sealed_sha256':sealed_hash,'case_count':8,'source_seconds':64,'variant_count':4,'mask_count':32,
            'math_threads':2,'deadline_seconds':120,'elapsed_seconds':time.monotonic()-started,
            'all_masks_saved_before_truth_read':True,'source_hashes_preserved':True,'thresholds':THRESHOLDS,
            'hard_failure_count':hard,'quality_alert_variant_count':sum(bool(r['metrics']['quality_alerts']) for r in results),
            'results':results,'numpy_version':np.__version__,'actual_audio_processed':False,
            'recovered_real_stems':False,'listening_accepted':False,'default_adoption':False}
        write_json(stage/'results.json',result);stage.rename(dest)
        return result
    except Exception as exc:
        # Preserve a failed receipt for review; incomplete DSP artifacts are not published.
        failure={'status':'failed','reason':str(exc),'completed_mask_count':len(jobs),'actual_audio_processed':False}
        write_json(stage/'failure.json',failure)
        raise RuntimeError(f'{exc}; failed stage retained at {stage}') from exc


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--discovery-index',required=True)
    parser.add_argument('--fixture-index',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    result=run(args.discovery_index,args.fixture_index,args.output)
    print(json.dumps({k:v for k,v in result.items() if k!='results'},sort_keys=True,allow_nan=False))
    return 1 if result['hard_failure_count'] else 0


if __name__=='__main__':
    raise SystemExit(main())
