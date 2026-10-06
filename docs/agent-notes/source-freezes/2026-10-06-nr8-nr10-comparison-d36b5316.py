#!/usr/bin/env python3
"""Released, bounded NR8/NR10 artifact readback; never renders source audio."""
from __future__ import annotations
import argparse
import csv
from fractions import Fraction
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import signal
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
METHOD = Path(__file__).with_name('2026-10-05-nr10-restoration-comparison-method.md')
METHOD_SHA = '9c06f5094966f4b24d832e4b2034810fe9e77300e21ae364c4b9bb41f58d2d0a'
HELPER = Path(__file__).with_name('2026-10-05-captured-restoration-comparison.py')
HELPER_SHA = 'e62498f5e00325e37da2b7d6463ae813c98ae3ae0a27d5bfafd5c3d47cf5efef'
SEGMENT = Path(__file__).with_name('2026-10-05-captured-restoration-segments.py')
SEGMENT_SHA = 'c195d711d42b86585a6bdc9486c5189e459916930df8a8088562c188e7b39294'
APPLICATION = ROOT / 'scripts/apply_capture_profile.py'
APPLICATION_SHA = '790ac58f1924db2607087c6ab1cdae5d813ba24eda610af1f396d77e93d06584'
APPROVED_APPLICATION_PRODUCERS = {
    'nr8': '00a03ef9fad8543be4335cb5cbcd3c9d9580a6b40b8faeb826811b105fd5daa6',
    'nr10': APPLICATION_SHA,
}
HISTORICAL_APPLICATION = ROOT / 'docs/agent-notes/source-freezes/2026-10-06-apply-capture-profile-00a03ef9.py'
RESOURCE_QUALIFICATION = ROOT / 'docs/agent-notes/2026-10-06-capture-application-resource-qualification-result.json'
RESOURCE_QUALIFICATION_SHA = '3ad6a3c119c4e3196604f8818630ec74960028cb1df33e3f3e7c0e3abcb09603'
AUTHORING_SHA = '7d2820878826c87aabf2ab60b73c997b9d406b7f3ff8943d6012ed967444c355'
MEDIA_SHA = '91443154251888c9e74670790766b289a2618f85f3be806d60ca26882faa9d94'
SOURCE_SHA = 'a522115f4e72e19384fb341bc84369728eceefe49183b8c6367a1008a95176c6'
PCM_SHA = 'd68e49688293b1fb8c7c2566e2ecd6e31df9972af013dd23454e15864654bd2a'
EVENTS = ROOT / 'artifacts/runs/20261005T232741Z-2b5dc43fd009/events.csv'
EVENTS_SHA = 'ab640f6370f5eef2ff0f548f94826b3db631a140d058db1578397d3b48a025f1'
ACTIVE = [(10, 20), (40, 50), (90, 100), (130, 140)]
INTERVALS = [(0, 1), (4, 5), (4.1, 4.95), (149, 150), *ACTIVE, (140, 150)]
BANDS = [(20, 45), (45, 120), (55, 70), (190, 225), (250, 2000), (2000, 10000), (10000, 22050)]
ROLES = {'source', 'denoised', 'residue', 'processed', 'cleaned', 'baseline'}
WHOLE_SECONDS = 60
PROCESS_SECONDS = 55
EXPECTED_EQ = [{'frequency_hz': 300., 'gain_db': -1.5, 'q': .8},
               {'frequency_hz': 2200., 'gain_db': 1., 'q': .8}]
EXPECTED_COMP = {'threshold_db': -18., 'ratio': 2., 'attack_ms': 15., 'release_ms': 100., 'knee_db': 3.}


class ComparisonError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ComparisonError(message)


def regular(value):
    p = Path(value).expanduser().absolute()
    require(p.is_file() and not any(q.is_symlink() for q in [p, *p.parents]), 'regular nonsymlink input required')
    return p.resolve()


def sha(p, deadline=None):
    h = hashlib.sha256()
    with p.open('rb') as f:
        while block := f.read(1024 * 1024):
            if deadline:
                deadline.check()
            h.update(block)
    return h.hexdigest()


def pinned(p, expected, deadline):
    p = regular(p)
    require(isinstance(expected, str) and len(expected) == 64 and all(c in '0123456789abcdef' for c in expected), 'invalid SHA256')
    require(sha(p, deadline) == expected, f'input hash differs: {p.name}')
    return p


def strict_json(p):
    require(p.stat().st_size <= 1024 * 1024, 'JSON byte bound exceeded')
    def pairs(items):
        d = {}
        for k, v in items:
            require(k not in d, 'duplicate JSON key')
            d[k] = v
        return d
    def number(s):
        x = float(s)
        require(math.isfinite(x), 'nonfinite JSON number')
        return x
    return json.loads(p.read_text(), object_pairs_hook=pairs, parse_float=number,
                      parse_constant=lambda s: (_ for _ in ()).throw(ComparisonError('nonfinite JSON constant')))


def load_module(p, name):
    spec = importlib.util.spec_from_file_location(name, p)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def delivery(loudness, structural):
    values = [loudness.get(k) for k in ('integrated_lufs', 'true_peak_dbtp', 'loudness_range_lu')]
    require(all(isinstance(x, (float, int)) and not isinstance(x, bool) and math.isfinite(x) for x in values), 'finite meter input values required')
    checks = {'structural': structural is True,
              'aac_integrated_within_0_3_lu': abs(values[0] + 18) <= .3 + 1e-12,
              'aac_true_peak_within_ceiling': values[1] <= -1.75}
    return {'checks': checks, 'eligible_for_comparison_delivery': all(checks.values()),
            'musical_acceptance': False, 'master_adopted': False}


def attack_panels(rows):
    selected = []
    for start, end in ACTIVE:
        times = sorted(float(r['audio_relative_seconds']) for r in rows if r['kind'] == 'broadband_attack_candidate')
        subset = []
        for t in times:
            require(math.isfinite(t), 'nonfinite event timestamp')
            if start + .20 <= t <= end - .50 and (not subset or t - subset[-1] >= .30):
                subset.append(t)
                if len(subset) == 3:
                    break
        selected += subset
    return selected


def profile_controls(p, reduction):
    expected = {'reduction_db': reduction, 'noise_floor_db': -40, 'adaptivity': 0,
                'gain_smooth': 0, 'integrated_lufs': -18, 'true_peak_dbtp': -1.75,
                'preserve_low_fundamental_hz': 32, 'denoise': True,
                'noise_capture_authorized': True, 'noise_capture_source_sha256': SOURCE_SHA,
                'peaking_eq': EXPECTED_EQ, 'compressor': EXPECTED_COMP}
    for k, v in expected.items():
        require(p.get(k) == v and (not isinstance(p[k], bool) or isinstance(v, bool)), f'profile control differs: {k}')
    require(set(p) == set(expected) | {'schema_version', 'name', 'description', 'noise_capture_review', 'noise_capture_seconds'}
            and p['schema_version'] == 1, 'closed authored profile required')
    require([round(t * 44100) for t in p['noise_capture_seconds']] == [180810, 218295], 'capture bounds differ')


def validate_candidate(d, label, deadline):
    require(set(d) == {'label', 'manifest', 'application_receipt', 'export_outcome'}, 'candidate selector keys differ')
    require(d['label'] == label, 'candidate order must be nr8 then nr10')
    docs = {}
    for key in ('manifest', 'application_receipt', 'export_outcome'):
        require(set(d[key]) == {'path', 'sha256'}, 'document binding keys differ')
        p = pinned(d[key]['path'], d[key]['sha256'], deadline)
        docs[key] = strict_json(p)
        docs[key + '_path'] = p
    m, app, exp = (docs[k] for k in ('manifest', 'application_receipt', 'export_outcome'))
    run = docs['manifest_path'].parent
    require(str(run) == m['run_dir'] == app['run_dir'] == exp['run_dir'], 'run identities differ')
    require(run.is_relative_to(ROOT / 'artifacts/runs'), 'candidate outside private run root')
    require(docs['application_receipt_path'] == run / 'application-receipt.json'
            and docs['export_outcome_path'] == run / 'export/outcome.json', 'canonical receipt selectors required')
    require(m['source']['sha256'] == app['source']['sha256'] == exp['source_sha256'] == SOURCE_SHA, 'source binding differs')
    require(app['status'] == 'rendered_unreviewed' and app['listening_accepted'] is False
            and app['master_adopted'] is False and exp['listening_accepted'] is False, 'unreviewed application required')
    require(app['producer']['application_worker_sha256'] == APPROVED_APPLICATION_PRODUCERS[label]
            and app['producer']['authoring_worker_sha256'] == AUTHORING_SHA
            and app['producer']['media_worker_sha256'] == MEDIA_SHA, 'application producer differs')
    require(app['outputs']['manifest_sha256'] == d['manifest']['sha256']
            and app['outputs']['export_outcome_sha256'] == d['export_outcome']['sha256'], 'application output bindings differ')
    require(m['pcm']['sample_rate'] == 44100 and m['pcm']['channels'] == 1 and m['pcm']['sample_count'] == 6657385,
            'actual native extent differs')
    require(all(app['native_pcm'][k] == m['pcm'][k] for k in ('sample_rate','channels','sample_count')),
            'application native extent differs')
    require(m['timeline']['no_time_stretch'] is True and m['timeline']['audio_start_seconds'] == 0, 'native origin/mapping differs')
    profile_controls(m['profile'], 8 if label == 'nr8' else 10)
    cap = m['noise_capture']
    require(cap['selected_samples'] == [180810, 218295] and cap['applies_to_original_start'] is True
            and cap['source_axis_sample_count_preserved'] is True and cap['noise_only_verified_by_worker'] is False, 'capture support/uncertainty differs')
    latency = m['dsp_latency']['denoise']
    require(latency['status'] == 'measured_and_compensated' and latency['remaining_bulk_delay_samples'] == 0
            and latency['delay_samples'] == cap['filter_delay_samples_removed'], 'calibrated delay unavailable')
    v = exp['verification']
    for key in ('source_hash_verified', 'video_frame_count_preserved', 'relative_audio_video_start_verified',
                'dsp_latency_compensation_recorded', 'video_packet_timeline_preserved', 'video_packet_payload_hashes_preserved'):
        require(v.get(key) is True, f'export structural evidence absent: {key}')
    require(v['physical_audio_video_sync_verified'] is False, 'physical sync must stay unknown')
    require(v['source_video_packets'] == v['export_video_packets'] > 0
            and v['source_decoded_video_frames'] == v['export_decoded_video_frames'] > 0, 'video counts differ')
    tolerance = v['video_packet_clock_tolerance_seconds']
    source_tick = Fraction(m['source']['probe']['video']['time_base'])
    output_tick = Fraction(exp['video_probe']['video']['time_base'])
    require(source_tick > 0 and output_tick > 0, 'positive rational stream clocks required')
    expected_tolerance = float(max(source_tick, output_tick))
    require(isinstance(tolerance, (int, float)) and not isinstance(tolerance, bool)
            and math.isfinite(tolerance) and tolerance == expected_tolerance, 'packet-clock tolerance differs from recorded stream clocks')
    for key in ('video_packet_max_pts_delta_seconds', 'video_packet_max_dts_delta_seconds', 'video_packet_max_duration_delta_seconds'):
        require(isinstance(v[key], (int, float)) and math.isfinite(v[key]) and 0 <= v[key] <= tolerance, 'packet clock exceeds declared tolerance')
    require(abs(v['relative_audio_video_start_delta_seconds']) <= v['aac_timing_tolerance_seconds']
            and 0 < v['aac_timing_tolerance_seconds'] <= 1024 / 44100 + .003, 'AAC offset tolerance differs')
    require(isinstance(v['audio_duration_delta_seconds'], (int,float))
            and math.isfinite(v['audio_duration_delta_seconds'])
            and abs(v['audio_duration_delta_seconds']) <= v['aac_timing_tolerance_seconds'], 'AAC duration exceeds padding tolerance')
    require(set(m['outputs']) == ROLES and m['output_sha256'] == app['outputs']['audio_sha256'], 'audio artifact roles/bindings differ')
    files = {}
    for role, name in m['outputs'].items():
        require(name == role + '.wav', 'noncanonical audio output')
        files[role] = pinned(run / name, m['output_sha256'][name], deadline)
    require(m['output_sha256']['source.wav'] == PCM_SHA, 'shared source PCM differs')
    require(exp['video'] == str(run / 'export/cleaned-video.mov')
            and exp['audio_master'] == str(files['cleaned']), 'export media selectors differ')
    docs['video'] = pinned(exp['video'], exp['output_sha256']['cleaned-video.mov'], deadline)
    require(exp['output_sha256'] == app['outputs']['video_sha256'], 'video application binding differs')
    return {**docs, 'files': files, 'label': label}


def local_stats(helper, x, y, rate, start, end):
    from scipy.signal import welch, coherence
    np = helper.np
    a, b = round(start * rate), round(end * rate)
    x, y = x[a:b, 0], y[a:b, 0]
    require(len(x) == b - a and len(y) == b - a and len(x) >= 16384, 'local panel support unavailable')
    c = dict(fs=rate, nperseg=16384, noverlap=8192, window='hann', detrend=False)
    f, p = welch(x, scaling='density', **c)
    unused, q = welch(y, scaling='density', **c)
    unused, coh = coherence(x, y, **c)
    bands = {}
    for lo, hi in BANDS:
        mask = (f >= lo) & (f < hi)
        px, py = float(p[mask].sum() * (f[1] - f[0])), float(q[mask].sum() * (f[1] - f[0]))
        weighted = float(np.sum(coh[mask] * p[mask]) / np.sum(p[mask])) if px > 0 and np.isfinite(coh[mask]).all() else None
        bands[f'{lo}-{hi}'] = {'source_power_dbfs': helper.db(px), 'output_power_dbfs': helper.db(py),
                            'delta_db': helper.db(py) - helper.db(px), 'bin_count': int(mask.sum()),
                            'coherence_source_power_weighted': weighted}
    return {'seconds': [start, end], 'native_samples': [a, b], 'welch_segment_count': 1 + (b-a-16384)//8192,
            'frequency_bin_hz': float(f[1]-f[0]), 'bands': bands,
            'source_rms_dbfs': helper.db(np.mean(x*x)), 'output_rms_dbfs': helper.db(np.mean(y*y))}


def short_panels(helper, x, times, rate):
    np = helper.np
    rows = []
    for t in times:
        origin = round(t*rate)
        windows = []
        for a, b in [(-.02, 0), (0, .02), (.02, .05), (.05, .25)]:
            lo, hi = origin + round(a*rate), origin + round(b*rate)
            z = x[lo:hi]
            require(lo >= 0 and hi <= len(x) and len(z) == hi-lo, 'attack/tail support absent')
            windows.append({'offset_seconds': [a, b], 'native_samples': [lo, hi],
                            'rms_dbfs': helper.db(np.mean(z*z)), 'peak_dbfs': helper.db(np.max(z*z))})
        rows.append({'candidate_audio_relative_seconds': t, 'native_sample': origin, 'windows': windows})
    return rows


def meter(owned, executable, media_path, deadline, events):
    command = [str(executable), '-hide_banner', '-nostdin', '-loglevel', 'info', '-threads', '2',
               '-filter_threads', '2', '-filter_complex_threads', '2', '-i', str(media_path),
               '-map', '0:a:0', '-af', 'loudnorm=I=-18:TP=-1.75:LRA=50:print_format=json', '-f', 'null', '-']
    result = owned.run_owned(command, deadline=deadline, timeout=deadline.remaining(), events=events)
    data = json.loads(result.stderr[result.stderr.rfind('{'):result.stderr.rfind('}')+1])
    values = {'integrated_lufs': float(data['input_i']), 'true_peak_dbtp': float(data['input_tp']),
              'loudness_range_lu': float(data['input_lra'])}
    delivery(values, True)
    return {**values, 'command': command, 'scope': 'meter input; no media output or normalization applied'}


def run(release_path, release_sha, output_dir):
    started = time.monotonic()
    # Reserve up to five seconds for exceptional owned cleanup/reporting inside the nominal 60-second job.
    class Budget:
        ends = started + PROCESS_SECONDS
        def check(self):
            require(time.monotonic() < self.ends, 'comparison processing deadline exceeded')
        def remaining(self):
            self.check()
            return self.ends - time.monotonic()
    deadline = Budget()
    protected = []
    bindings = []
    output = None
    output_created = False
    result = {'schema_version': 1, 'status': 'incomplete', 'candidates': [], 'threads': 2,
              'whole_job_seconds_max': WHOLE_SECONDS, 'processing_seconds_max': PROCESS_SECONDS, 'owned_subprocesses': [],
              'listening_accepted': False, 'master_adopted': False, 'fan_only_gain': None, 'music_only_gain': None,
              'protected_after_verified': False, 'comparison_delivery_eligible': False}
    owned = None
    previous_handler = None
    previous_timer = None
    timer_owned = False
    def alarm(signum, frame):
        raise ComparisonError('comparison processing deadline exceeded')
    try:
        previous_handler, previous_timer = signal.getsignal(signal.SIGALRM), signal.getitimer(signal.ITIMER_REAL)
        require(previous_timer == (0., 0.), 'existing external alarm must not be displaced')
        signal.signal(signal.SIGALRM, alarm)
        timer_owned = True
        signal.setitimer(signal.ITIMER_REAL, deadline.remaining())
        p = pinned(release_path, release_sha, deadline)
        release = strict_json(p)
        required = {'schema_version', 'authority', 'driver_sha256', 'method_sha256', 'output_dir', 'ffmpeg', 'candidates', 'protected',
                    'approved_application_producers'}
        require(set(release) == required and release['schema_version'] == 1
                and release['authority'] == 'root_nr8_nr10_measurement_release', 'explicit root release schema required')
        require(release['approved_application_producers'] == APPROVED_APPLICATION_PRODUCERS,
                'closed root-approved application producer map differs')
        pinned(Path(__file__), release['driver_sha256'], deadline)
        require(release['method_sha256'] == METHOD_SHA, 'method pin differs')
        for file, digest in [(METHOD, METHOD_SHA), (HELPER, HELPER_SHA), (SEGMENT, SEGMENT_SHA),
                             (APPLICATION, APPLICATION_SHA), (ROOT/'scripts/capture_profile.py', AUTHORING_SHA),
                             (ROOT/'scripts/media.py', MEDIA_SHA), (EVENTS, EVENTS_SHA),
                             (HISTORICAL_APPLICATION, APPROVED_APPLICATION_PRODUCERS['nr8']),
                             (RESOURCE_QUALIFICATION, RESOURCE_QUALIFICATION_SHA)]:
            bindings.append((pinned(file, digest, deadline), digest))
        require(len(release['protected']) >= 7 and len(release['protected']) <= 24, 'seven to 24 protected identities required')
        for item in release['protected']:
            require(set(item) == {'path', 'sha256'}, 'protected selector keys differ')
            protected.append((pinned(item['path'], item['sha256'], deadline), item['sha256']))
        require(len({p for p, unused in protected}) == len(protected), 'duplicate protected selector')
        original = [p for p, h in protected if h == SOURCE_SHA]
        require(len(original) == 1 and any(h == PCM_SHA for p, h in protected), 'original/shared PCM must be protected')
        require(set(release['ffmpeg']) == {'path', 'sha256'}, 'FFmpeg binding keys differ')
        ffmpeg = pinned(release['ffmpeg']['path'], release['ffmpeg']['sha256'], deadline)
        bindings.append((ffmpeg, release['ffmpeg']['sha256']))
        require(isinstance(release['candidates'], list) and len(release['candidates']) == 2, 'exactly two candidates required')
        candidates = [validate_candidate(d, label, deadline) for d, label in zip(release['candidates'], ['nr8', 'nr10'])]
        require(candidates[0]['manifest_path'] != candidates[1]['manifest_path'], 'distinct candidates required')
        profiles = [{k: v for k, v in d['manifest']['profile'].items() if k not in {'name', 'description', 'reduction_db'}} for d in candidates]
        require(profiles[0] == profiles[1], 'one-knob profile control failed')
        for d in candidates:
            require(regular(d['manifest']['source']['path']) == original[0], 'protected original path differs')
            bindings += [(d[key+'_path'], release['candidates'][i][key]['sha256'])
                         for i in [0 if d['label'] == 'nr8' else 1] for key in ('manifest', 'application_receipt', 'export_outcome')]
            bindings += [(d['files'][role], d['manifest']['output_sha256'][role+'.wav']) for role in ROLES]
            bindings.append((d['video'], d['export_outcome']['output_sha256']['cleaned-video.mov']))
        output = Path(output_dir).expanduser().absolute()
        require(str(output) == release['output_dir'] and output.is_relative_to(ROOT/'artifacts/experiments')
                and output.resolve(strict=False) == output
                and not output.exists() and not any(q.is_symlink() for q in output.parents), 'new released private output directory required')
        output.mkdir(parents=True, exist_ok=False)
        output_created = True
        for variable in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMBA_NUM_THREADS'):
            os.environ[variable] = '2'
        helper = load_module(HELPER, '_nr_comparison_helper')
        owned = load_module(APPLICATION, '_nr_owned_runner')
        owned.CLI_ALARM_HANDLER = alarm
        for d in candidates:
            for role, file in d['files'].items():
                native = owned.capture.native_pcm(file, deadline)
                require(native['sample_rate'] == 44100 and native['channels'] == 1
                        and native['sample_count'] == 6657385, f'native header differs: {role}')
        with EVENTS.open(newline='') as f:
            panels = attack_panels(list(csv.DictReader(f)))
        rate, source = helper.load(candidates[0]['files']['source'])
        require(rate == 44100 and source.shape == (6657385, 1), 'decoded source extent differs')
        result.update({'release_path': str(p), 'release_sha256': release_sha, 'driver_sha256': release['driver_sha256'],
                       'method_sha256': METHOD_SHA, 'helper_sha256': HELPER_SHA, 'segment_method_sha256': SEGMENT_SHA,
                       'application_runner_sha256': APPLICATION_SHA, 'native': {'sample_rate': rate, 'channels': 1, 'sample_frames': len(source), 'origin_seconds': 0},
                       'approved_application_producers': APPROVED_APPLICATION_PRODUCERS.copy(),
                       'application_revision_comparison': {
                           'different_resource_runners': True,
                           'scope': 'root-qualified process-inspection repair; shared authoring/media workers and matched DSP settings verified separately',
                           'authoring_worker_sha256': AUTHORING_SHA, 'media_dsp_worker_sha256': MEDIA_SHA,
                           'resource_qualification_path': str(RESOURCE_QUALIFICATION),
                           'resource_qualification_sha256': RESOURCE_QUALIFICATION_SHA,
                           'historical_nr8_application_path': str(HISTORICAL_APPLICATION),
                           'historical_nr8_application_sha256': APPROVED_APPLICATION_PRODUCERS['nr8']},
                       'attack_panel_seconds': panels, 'attack_panel_source': 'historical NR8 denoised unvalidated broadband candidates',
                       'capture_context': 'operator reports minor guitar/amp activity and mechanical wind-up before5s; selected4.10-4.95s contamination uncertain, not noise-only',
                       'source_decoded_read_count': 1, 'source_description': helper.describe(rate, source),
                       'source_attack_tail_windows': short_panels(helper, source, panels, rate),
                       'protected_before': [{'path': str(p), 'sha256': h} for p, h in protected]})
        np = helper.np
        for d in candidates:
            deadline.check()
            arrays = {}
            descriptions = {}
            row = {'label': d['label'], 'run_id': d['manifest']['run_id'], 'manifest_sha256': sha(d['manifest_path'], deadline),
                   'application_producer_sha256': d['application_receipt']['producer']['application_worker_sha256'],
                   'artifacts': descriptions, 'measurement_complete': False,
                   'normalization_mode': d['manifest'].get('loudness', {}).get('cleaned', {}).get('render', {}).get('normalization_type'),
                   'timeline_verification': d['export_outcome']['verification']}
            result['candidates'].append(row)
            for role in ('denoised', 'residue', 'processed', 'cleaned'):
                rr, x = helper.load(d['files'][role])
                require(rr == rate and x.shape == source.shape, 'output native extent differs')
                require(float(helper.np.max(helper.np.abs(x))) < 1, 'output clipping/headroom check failed')
                arrays[role] = x
                descriptions[role] = helper.describe(rate, x)
                descriptions[role]['local_panels'] = []
                for a,b in INTERVALS:
                    descriptions[role]['local_panels'].append(local_stats(helper, source, x, rate, a, b))
                    deadline.check()
                descriptions[role]['attack_tail_windows'] = short_panels(helper, x, panels, rate)
                envelopes = []
                descriptions[role]['envelopes_20ms'] = envelopes
                for a, b in ACTIVE + [(140,150)]:
                    z = x[round(a*rate):round(b*rate), 0]
                    envelope = np.mean(z.reshape(-1, 882)**2, axis=1)
                    envelopes.append({'seconds': [a,b], 'window_samples': 882,
                                      'rms_dbfs': [helper.db(v) for v in envelope]})
                descriptions[role]['measurement_complete'] = True
                deadline.check()
            err = float(np.max(np.abs(source-arrays['denoised']-arrays['residue'])))
            require(err <= 1e-7, 'pure residue arithmetic exceeds float storage bound')
            row['pure_residue_max_error_full_scale'] = err
            row['measured_master_loudness'] = meter(owned, ffmpeg, d['files']['cleaned'], deadline, result['owned_subprocesses'])
            row['measured_aac_loudness'] = meter(owned, ffmpeg, d['video'], deadline, result['owned_subprocesses'])
            row['delivery'] = delivery(row['measured_aac_loudness'], True)
            row['measurement_complete'] = True
        for p, h in bindings + protected:
            require(sha(p, deadline) == h, f'protected/input identity changed: {p.name}')
        result['protected_after_verified'] = True
        # Explicit matched-stage deltas, without fitting gain/clock or interpreting components.
        a, b = result['candidates']
        delta = {}
        for role in ('denoised', 'processed', 'cleaned', 'residue'):
            x, y = a['artifacts'][role], b['artifacts'][role]
            delta[role] = {'rms_db': y['rms_dbfs']-x['rms_dbfs'],
                'whole_band_db': {k: y['band_power_dbfs'][k]-v for k, v in x['band_power_dbfs'].items()},
                'fixed_window_rms_db': {k: y['windows'][k]['rms_dbfs']-v['rms_dbfs'] for k,v in x['windows'].items()},
                'local_band_db': [{'seconds': q['seconds'], 'bands': {k:q['bands'][k]['output_power_dbfs']-p['bands'][k]['output_power_dbfs'] for k in p['bands']}}
                                  for p,q in zip(x['local_panels'],y['local_panels'])]}
        result['nr10_minus_nr8_same_stage'] = delta
        result['status'] = 'complete_comparison_unreviewed'
        result['comparison_delivery_eligible'] = all(d['delivery']['eligible_for_comparison_delivery'] for d in result['candidates'])
    except Exception as exc:
        result['error'] = {'type': type(exc).__name__, 'message': str(exc)[:2000]}
        result['comparison_delivery_eligible'] = False
    finally:
        if timer_owned:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous_handler)
        if owned and owned.CLI_ALARM_HANDLER is not None:
            owned.CLI_ALARM_HANDLER = None
        result['elapsed_seconds'] = time.monotonic()-started
        result['within_whole_job_budget'] = result['elapsed_seconds'] <= WHOLE_SECONDS
        if not result['within_whole_job_budget']:
            result['status'] = 'incomplete_budget_exceeded'
            result['comparison_delivery_eligible'] = False
        if output_created:
            with (output/'results.json').open('x') as f:
                json.dump(result, f, indent=2, sort_keys=True, allow_nan=False)
                f.write('\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release', required=True)
    parser.add_argument('--release-sha256', required=True)
    parser.add_argument('--output-dir', required=True)
    args = parser.parse_args()
    result = run(args.release, args.release_sha256, args.output_dir)
    print(json.dumps({'status': result['status'], 'elapsed_seconds': result['elapsed_seconds'],
                      'comparison_delivery_eligible': result['comparison_delivery_eligible'],
                      'error': result.get('error'), 'output_dir': args.output_dir if result.get('release_path') else None}))
    return 0 if result['status'] == 'complete_comparison_unreviewed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
