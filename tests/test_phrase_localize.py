"""Constructed feature/time oracles only; no waveform or discovery inference."""
import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import random
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('phrase_localizer',ROOT/'scripts/phrase_localize.py')
worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)


def npy(values,shape):
    header=repr({'descr':'<f8','fortran_order':False,'shape':shape}).encode()
    header+=b' '*((-(10+len(header)+1))%64)+b'\n'
    return b'\x93NUMPY\x01\x00'+struct.pack('<H',len(header))+header+struct.pack('<'+'d'*len(values),*values)


def write_cache(path,cache):
    with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,values in cache.items():
            shape=(len(values),len(values[0])) if name=='features' else (len(values),)
            flat=[v for row in values for v in row] if name=='features' else values
            archive.writestr(name+'.npy',npy(flat,shape))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def changing_motif(n=48):
    rng=random.Random(816)
    return [[math.cos(angle),math.sin(angle)] for angle in [rng.uniform(-math.pi,math.pi) for _ in range(n)]]


def fixture(origin=0.):
    times=[i*.016 for i in range(501)];rng=random.Random(5321)
    vectors=[[rng.uniform(-1,1),rng.uniform(-1,1)] for _ in times]
    motif=changing_motif(48)
    for start in (50,250):vectors[start:start+48]=copy.deepcopy(motif)
    cache={'features':[[v[d] for v in vectors] for d in range(2)]+[[0.]*len(times) for _ in range(24)],
           'times':times,'centroid':[500.]*len(times),'onsets':[]}
    raw={'first_start_seconds':.64,'first_end_seconds':1.728,'second_start_seconds':3.84,'second_end_seconds':4.928,
         'pulse_count':4,'original_candidate_index':0,'confidence':None,'performance_issue_confirmed':False,
         'contrast_evidence':{'contrast':.11},'order_evidence':{'margin':.12}}
    proposals={'schema_version':1,'source_sha256':'a'*64,'cache_sha256':'b'*64,'duration_seconds':8.,
        'proposal_universe':[copy.deepcopy(raw)],'arms':{'Border':[raw]}}
    clock={'schema_version':1,'source_sha256':'a'*64,'cache_sha256':'b'*64,'duration_seconds':8.,'audio_start_seconds':origin,
        'native_pcm':{'sample_rate':48000,'channels':1,'sample_count':384000},
        'analysis_pcm':{'sample_rate':16000,'sample_count':128000},
        'feature_clock':{'hop_samples':256,'fft_samples':4096,'centered':True,
            'timestamp_convention':'frame_centers_audio_relative','frame_indices':list(range(501))}}
    return cache,proposals,clock


class DiagonalTests(unittest.TestCase):
    def test_padded_motif_unique_extent_and_internal_changes(self):
        a=[[-1.,0.]]*10+changing_motif(48)+[[-1.,0.]]*10
        b=[[0.,-1.]]*10+changing_motif(48)+[[0.,-1.]]*10
        first=[i*.016 for i in range(len(a))];second=[3+i*.016 for i in range(len(b))]
        result=worker.diagonal_support(first,second,a,b,duration=8.)
        self.assertEqual(result['status'],'localized_support_candidate',result)
        span=result['localized_support']['first']
        self.assertEqual(span['first_frame_index'],10);self.assertEqual(span['last_frame_index'],57)
        self.assertAlmostEqual(span['cell_start_audio_relative_seconds'],.152)
        self.assertAlmostEqual(span['cell_end_audio_relative_seconds'],.920)
    def test_stationary_sustain_and_empty_active_dimensions_abstain(self):
        times=[i*.016 for i in range(60)];other=[3+t for t in times]
        for z in ([[1.,0.]]*60,[[] for _ in times]):
            result=worker.diagonal_support(times,other,z,z,duration=8.)
            self.assertEqual(result['status'],'localization_unknown')
            self.assertEqual(result['reason'],'stationary_or_insufficient_internal_change')
    def test_zero_vectors_are_not_matches(self):
        self.assertIsNone(worker.cosine([0.,0.],[0.,0.]))
        result=worker.diagonal_support([i*.016 for i in range(40)],[3+i*.016 for i in range(40)],[[0.,0.]]*40,[[0.,0.]]*40)
        self.assertIsNone(result['localized_support'])
    def test_equal_reward_different_extents_abstain(self):
        motif=changing_motif(40)
        a=motif; b=motif+[[0.,0.]]*20+motif
        result=worker.diagonal_support([i*.016 for i in range(40)],[3+i*.016 for i in range(100)],a,b,duration=8.)
        self.assertEqual(result['reason'],'nonunique_maximum_support')
    def test_missing_time_bins_never_compress_into_long_support(self):
        motif=changing_motif(40);times=[i*.016 if i<20 else (i+10)*.016 for i in range(40)]
        result=worker.diagonal_support(times,[3+t for t in times],motif,motif,duration=8.)
        self.assertEqual(result['reason'],'no_ordered_support_of_minimum_duration')
    def test_short_support_never_passes_minimum(self):
        z=changing_motif(20)
        result=worker.diagonal_support([i*.016 for i in range(20)],[3+i*.016 for i in range(20)],z,z)
        self.assertIsNone(result['localized_support'])
    def test_edge_clipped_cell_durations_do_not_overstate_support(self):
        z=changing_motif(64)
        result=worker.diagonal_support([i*.016 for i in range(64)],[3+i*.016 for i in range(64)],z,z,duration=8.)
        support=result['localized_support']
        self.assertAlmostEqual(support['positive_support_duration_seconds']['first'],1.016)
        self.assertAlmostEqual(support['positive_support_duration_seconds']['second'],1.024)
    def test_long_rois_use_bounded_tiles(self):
        z=changing_motif(300)
        result=worker.diagonal_support([i*.016 for i in range(300)],[6+i*.016 for i in range(300)],z,z,duration=12.)
        self.assertEqual(result['status'],'localized_support_candidate')
        self.assertEqual(result['cells_visited'],90_000)
        self.assertTrue(all(a<=256 and b<=256 for a,b in result['localized_support']['tile_shapes']))


class ContractTests(unittest.TestCase):
    def test_raw_ids_order_preserved_no_picked_attack_gate_nonzero_origin(self):
        cache,proposals,clock=fixture(7.25);before=copy.deepcopy(proposals)
        result=worker.localize(cache,proposals,clock)
        self.assertEqual(proposals,before);self.assertEqual(result['retained_raw_count'],1)
        row=result['candidates'][0];self.assertEqual(row['raw_candidate'],before['arms']['Border'][0])
        self.assertEqual(row['status'],'localized_support_candidate',row)
        first=row['localized_support']['first'];self.assertEqual(first['first_frame_index'],50)
        self.assertAlmostEqual(first['first_center_audio_relative_seconds'],.8)
        self.assertAlmostEqual(first['cell_start_audio_relative_seconds'],.792)
        self.assertAlmostEqual(first['source_start_seconds'],8.042)
        self.assertAlmostEqual(first['fft_support_start_audio_relative_seconds'],.672)
        self.assertFalse(result['physical_latency_calibrated']);self.assertIsNone(row['confidence'])
    def test_uncentered_clock_adds_window_offset_exactly_once(self):
        cache,proposals,clock=fixture();clock['feature_clock']['centered']=False
        keep=493
        cache={name:([row[:keep] for row in value] if name=='features' else [t+.128 for t in value[:keep]] if name=='times'
            else value[:keep] if name=='centroid' else value) for name,value in cache.items()}
        clock['feature_clock']['frame_indices']=list(range(keep))
        result=worker.localize(cache,proposals,clock)
        first=result['candidates'][0]['localized_support']['first']
        self.assertAlmostEqual(first['first_center_audio_relative_seconds'],.928)
        self.assertAlmostEqual(first['source_start_seconds'],.920)
    def test_native_resampling_clock_and_source_binding_reject_fabrications(self):
        cache,proposals,clock=fixture()
        for mutate,reason in [(lambda c:c['analysis_pcm'].update(sample_count=127999),'native_analysis_extent'),
            (lambda c:c.update(source_sha256='c'*64),'cache_source_binding'),
            (lambda c:c['feature_clock'].update(centered=False),'frame_center_clock')]:
            altered=copy.deepcopy(clock);mutate(altered)
            with self.assertRaisesRegex(worker.base.EvaluationError,reason):worker.localize(cache,proposals,altered)
    def test_invalid_order_candidate_id_or_hash_claim_rejected(self):
        cache,proposals,clock=fixture()
        for mutate,reason in [(lambda p:p['arms']['Border'][0].update(second_start_seconds=.7),'candidate_span_order'),
            (lambda p:p['arms']['Border'][0].update(original_candidate_index=5),'candidate_identity_bound'),
            (lambda p:p['arms']['Border'][0].update(first_start_seconds=.65),'candidate_raw_window')]:
            altered=copy.deepcopy(proposals);mutate(altered)
            with self.assertRaisesRegex(worker.base.EvaluationError,reason):worker.localize(cache,altered,clock)
    def test_no_proposals_is_explicit_full_raw_universe_count(self):
        cache,proposals,clock=fixture();proposals['arms']['Border']=[]
        result=worker.localize(cache,proposals,clock)
        self.assertEqual(result['candidate_count_pre_selection'],1);self.assertEqual(result['localized_count'],0)
        self.assertEqual(result['candidates'],[])
    def test_unsupported_confirmed_grade_is_never_propagated(self):
        cache,proposals,clock=fixture();proposals['arms']['Border'][0]['performance_issue_confirmed']=True
        with self.assertRaisesRegex(worker.base.EvaluationError,'unsupported_confirmed_claim'):
            worker.localize(cache,proposals,clock)
    def test_inactive_cache_abstains_before_visiting_dp_cells(self):
        cache,proposals,clock=fixture();cache['features']=[[1.]*501 for _ in range(26)]
        result=worker.localize(cache,proposals,clock)
        self.assertEqual(result['active_dimensions'],0);self.assertEqual(result['cells_visited'],0)
        self.assertEqual(result['candidates'][0]['cells_visited'],0)
        self.assertEqual(result['localized_count'],0)
    def test_cap_limits_and_finite_features(self):
        cache,proposals,clock=fixture();altered=copy.deepcopy(proposals);altered['proposal_universe']*=61
        with self.assertRaisesRegex(worker.base.EvaluationError,'proposal_count'):worker.localize(cache,altered,clock)
        cache['features'][0][0]=float('nan')
        with self.assertRaisesRegex(worker.base.EvaluationError,'finite_nonboolean'):worker.localize(cache,proposals,clock)
    def test_cli_npz_hash_guards_and_no_existing_output_replacement(self):
        parent=ROOT/'artifacts/benchmarks';parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='phrase-localize-tests-',dir=parent) as tmp:
            directory=Path(tmp);cache,proposals,clock=fixture()
            npz=directory/'cache.npz';sha=write_cache(npz,cache);proposals['cache_sha256']=clock['cache_sha256']=sha
            files=[('cache',npz,sha)]
            for name,value in [('proposals',proposals),('clock',clock)]:
                p=directory/(name+'.json');p.write_text(json.dumps(value));files.append((name,p,hashlib.sha256(p.read_bytes()).hexdigest()))
            argv=[sys.executable,str(ROOT/'scripts/phrase_localize.py')]
            for name,p,sha in files:argv.extend(['--'+name,str(p),'--'+name+'-sha256',sha])
            output=directory/'output';argv.extend(['--output',str(output),'--summary'])
            completed=subprocess.run(argv,capture_output=True,text=True,timeout=30)
            self.assertEqual(completed.returncode,0,completed.stderr)
            self.assertEqual(json.loads(completed.stdout)['localized_count'],1)
            result=json.loads((output/'phrase-localization.json').read_text())
            self.assertFalse(result['provenance']['source_waveform_bytes_read'])
            self.assertFalse(result['inference_invoked'])
            self.assertEqual(subprocess.run(argv,capture_output=True,timeout=30).returncode,1)
            npz.write_bytes(b'changed')
            with self.assertRaisesRegex(worker.base.EvaluationError,'sha256_mismatch'):worker.cache_receipt(npz,files[0][2])
    def test_npz_rejects_unsafe_members_and_expansion_bomb(self):
        parent=ROOT/'artifacts/benchmarks';parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='phrase-archive-tests-',dir=parent) as tmp:
            p=Path(tmp)/'bad.npz'
            with zipfile.ZipFile(p,'w') as z:z.writestr('../features.npy',b'bad')
            with self.assertRaisesRegex(worker.base.EvaluationError,'cache_members'):worker.cache_receipt(p,hashlib.sha256(p.read_bytes()).hexdigest())
            with zipfile.ZipFile(p,'w',compression=zipfile.ZIP_DEFLATED) as z:
                for name in ('features','times','centroid','onsets'):z.writestr(name+'.npy',b'\0'*(300_000))
            with self.assertRaisesRegex(worker.base.EvaluationError,'cache_expansion'):worker.cache_receipt(p,hashlib.sha256(p.read_bytes()).hexdigest())


if __name__=='__main__':unittest.main()
