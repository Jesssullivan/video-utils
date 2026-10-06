#!/usr/bin/env python3
"""Fixed FULLER_NR8 saved headers/hashes/residue readback; no media subprocess."""
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NOTES = ROOT / 'docs/agent-notes'
HELPER = NOTES / '2026-10-06-actual-nr10-resource-artifact-audit.py'
assert hashlib.sha256(HELPER.read_bytes()).hexdigest() == '7139058e83748d42d088036053ceb1ce181f3f057f0e8d66df991bce884196ac'
spec = importlib.util.spec_from_file_location('qualified_saved_native_helpers', HELPER)
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
sha, read, require, native = h.sha, h.read, h.require, h.native
RUN = ROOT / 'artifacts/runs/20261006T041633Z-990aa1bd6737'
WORK = ROOT / 'artifacts/experiments/fuller-v1-20261006T041415Z'
PINS = {'manifest.json': '61c9b3930c36d050818901138eb1820d5dc940e3603d38f019bde793da750a5f',
        'application-receipt.json': 'ab1f31dfaefff2d781f4d8b20ebeb9a8a3575f77b2b42926d98a96f9c5ae7e48',
        'export/outcome.json': 'fe1b1009d7d56b54fedd8589aced49270a8bb6c37957df52b1e38d688b35f13d'}


def main():
    plan_path = NOTES / '2026-10-06-fuller-v1-plan.json'
    require(sha(plan_path) == 'f62cce0d5bf9e83ba045bfb9bd22a20d341ccc8ff690413fbfcd85bc447be599', 'Root fuller plan changed')
    plan = read(plan_path)
    for path, expected in PINS.items():
        require(sha(RUN/path) == expected, 'Exact candidate metadata changed')
    manifest, application, outcome = (read(RUN/name) for name in PINS)
    protected_path = WORK/'protected-before.json'
    protected = json.loads(protected_path.read_bytes())
    protected_hash = sha(protected_path)
    for row in protected:
        require(sha(row['path']) == row['sha256'], 'Protected source/latest/master changed')
    require(application['status'] == 'rendered_unreviewed' and application['run_dir'] == str(RUN), 'Candidate state/selector differs')
    require(application['dsp_performed'] is True and application['listening_accepted'] is False and application['master_adopted'] is False, 'Acceptance promoted')
    for slot, filename in [('application_worker_sha256','apply_capture_profile.py'), ('authoring_worker_sha256','capture_profile.py'), ('media_worker_sha256','media.py')]:
        require(sha(ROOT/'scripts'/filename) == application['producer'][slot], 'Producer changed')
    require(application['producer']['application_worker_sha256'] == plan['application_worker_sha256'], 'Application source differs from plan')
    require(sha(plan['input']) == plan['source_sha256'] == application['source']['sha256'], 'Original differs')
    parent = Path(plan['parent_run'])
    require(sha(parent/'manifest.json') == application['parent']['manifest_sha256'], 'Parent manifest changed')
    require(sha(parent/'source.wav') == application['parent']['pcm_sha256'], 'Parent PCM changed')
    author = Path(application['authoring']['directory'])
    author_receipt = read(author/'receipt.json')
    require(author_receipt['status'] == 'authored_unrendered' and author_receipt['dsp_performed'] is False, 'Authoring state differs')
    require(sha(author/'receipt.json') == application['authoring']['receipt_sha256'], 'Authoring receipt changed')
    require(sha(author/'profile.json') == sha(RUN/'applied-profile.json') == application['authoring']['profile_sha256'], 'Applied profile changed')
    require(author_receipt['settings'] == plan['settings'], 'Applied controls differ from root plan')
    profile = read(RUN/'applied-profile.json')
    require(all(profile[key] == value for key,value in plan['settings'].items()), 'Profile controls differ')
    old = read(Path(plan['fixed_denoise_control_run'])/'applied-profile.json')
    differences = sorted(key for key in set(old)|set(profile) if old.get(key) != profile.get(key))
    require(differences == ['name','peaking_eq'], 'Change exceeds the named EQ package')
    require(profile['peaking_eq'] == [{'frequency_hz':160.,'gain_db':2.,'q':.7}, {'frequency_hz':300.,'gain_db':1.,'q':.8}], 'EQ package differs')
    require(profile['preserve_low_fundamental_hz'] == 32 and profile['reduction_db'] == 8, 'Instrument/denoise controls changed')
    for context in application['authoring']['context'].values():
        require(sha(context['path']) == context['sha256'], 'Registered context changed')
    review = application['authoring']['review']
    require(sha(review['path']) == review['sha256'] == plan['review_sha256'], 'Capture review changed')
    require(application['capture']['native_samples'] == plan['capture_samples'] == [180810,218295]
            and application['capture']['source_media_span_seconds'] == [4.1,4.95]
            and application['capture']['noise_only_verified'] is False, 'Capture mapping/uncertainty differs')
    require(manifest['timeline']['audio_start_seconds'] == 0 and manifest['timeline']['no_time_stretch'] is True, 'Source timing differs')
    latency = manifest['dsp_latency']['denoise']
    require(latency['status'] == 'measured_and_compensated' and latency['delay_samples'] == 1102
            and latency['measured_impulse_offsets_samples'] == [1102]*2 and latency['remaining_bulk_delay_samples'] == 0, 'Bulk delay differs')
    require(manifest['dsp_latency']['post_denoise']['complete_acoustic_alignment_verified'] is False, 'Acoustic acceptance promoted')
    require(manifest['restoration_stages'][1:-1] == author_receipt['planned_post_denoise_stages'], 'Rendered tone stages differ')
    require(manifest['restoration_stages'][-2]['fixed_parallel_wet_fraction'] == .25, 'Compression mix differs')
    headers, arrays = {}, {}
    for name in ('source.wav','denoised.wav','residue.wav','processed.wav','baseline.wav','cleaned.wav'):
        require(sha(RUN/name) == manifest['output_sha256'][name] == application['outputs']['audio_sha256'][name], 'Native stage hash differs')
        headers[name], arrays[name] = native(RUN/name, name not in ('baseline.wav','cleaned.wav'))
    require(sha(RUN/'source.wav') == application['parent']['pcm_sha256'], 'Original decode changed')
    for name, field in [('denoised.wav','expected_denoised_sha256'), ('residue.wav','expected_residue_sha256')]:
        require(sha(RUN/name) == sha(Path(plan['fixed_denoise_control_run'])/name) == plan[field], 'Pure NR8 stage differs')
    require(sha(RUN/'processed.wav') != sha(Path(plan['fixed_denoise_control_run'])/'processed.wav'), 'Changed EQ stage is unexpectedly identical')
    error = first = last = 0.
    for index,(source,denoised,residue) in enumerate(zip(arrays['source.wav'],arrays['denoised.wav'],arrays['residue.wav'])):
        value = abs(source-denoised-residue); error=max(error,value)
        if index<2048:first=max(first,value)
        if index>=h.FRAMES-2048:last=max(last,value)
    require(error<=2**-22, 'Pure residue arithmetic differs')
    require(outcome['status'] == 'exported_unreviewed' and outcome['listening_accepted'] is False, 'Export acceptance promoted')
    require(sha(RUN/'export/cleaned-video.mov') == outcome['output_sha256']['cleaned-video.mov'] == application['outputs']['video_sha256']['cleaned-video.mov'], 'Export bytes changed')
    verification = outcome['verification']
    for flag in ('source_hash_verified','video_frame_count_preserved','relative_audio_video_start_verified','dsp_latency_compensation_recorded','final_true_peak_within_target','video_packet_timeline_preserved','video_packet_payload_hashes_preserved'):
        require(verification[flag] is True,'Saved export verification missing')
    require(verification['physical_audio_video_sync_verified'] is False
            and verification['source_decoded_video_frames'] == verification['export_decoded_video_frames'] == 3621
            and verification['source_video_packets'] == verification['export_video_packets'] == 3631, 'Saved video scope differs')
    require(all(verification[field] == 0 for field in ('relative_audio_video_start_delta_seconds','video_packet_max_pts_delta_seconds','video_packet_max_dts_delta_seconds','video_packet_max_duration_delta_seconds')), 'Saved export clock delta differs')
    require(float(outcome['final_audio_loudness']['input_tp'])<=-1.75,'Saved delivery peak exceeds target')
    for row in protected:require(sha(row['path']) == row['sha256'],'Protected source/latest/master changed during audit')
    require(sha(protected_path)==protected_hash,'Protected evidence changed')
    for path,expected in PINS.items():require(sha(RUN/path)==expected,'Candidate metadata changed during audit')
    result = {'schema_version':1,'actor':'/root/release_review','authority':'Root explicit saved FULLER_NR8 artifact audit; R-HOOK-CONVERGENCE-20261004/R-N13',
              'status':'independent_fuller_nr8_artifact_audit_passed','auditor_source_sha256':sha(__file__),
              'plan_sha256':sha(plan_path),'candidate_run_dir':str(RUN),'metadata_sha256':PINS,
              'native_headers':headers,'pure_nr8_denoised_and_residue_bytes_equal':True,
              'profile_differing_fields_from_nr8':differences,'peaking_eq':profile['peaking_eq'],
              'compressor':profile['compressor'],'fixed_parallel_wet_fraction':.25,
              'residue_max_abs_error':error,'first_boundary_error':first,'last_boundary_error':last,
              'native_capture_samples':[180810,218295],'audio_origin_seconds':0,'calibrated_delay_samples':1102,
              'remaining_bulk_delay_samples':0,'protected_files_hash_verified':len(protected),
              'protected_before_sha256':protected_hash,'saved_export_verification':verification,
              'final_AAC_integrated_lufs':float(outcome['final_audio_loudness']['input_i']),
              'final_AAC_true_peak_dbtp':float(outcome['final_audio_loudness']['input_tp']),
              'media_probes_decode_DSP_inference_repeated':False,'export_proof_scope':'Readback of saved exporter hashes/clocks only; no independent actual video probe',
              'noise_only_verified':False,'physical_audio_video_sync_verified':False,'complete_acoustic_alignment_verified':False,
              'listening_accepted':False,'master_adopted':False}
    destination = NOTES/'2026-10-06-fuller-nr8-independent-artifact-audit.json'
    with destination.open('x') as f:json.dump(result,f,sort_keys=True,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps({'status':result['status'],'audit_sha256':sha(destination),'residue_max_abs_error':error,'final_AAC_true_peak_dbtp':result['final_AAC_true_peak_dbtp']}))


if __name__ == '__main__':main()
