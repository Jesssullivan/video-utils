#!/usr/bin/env python3
"""Independent existing-artifact audit; generated-video metadata probes only."""
import array
from fractions import Fraction
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
TRIAL = ROOT / 'artifacts/experiments/capture-application-native-qualification/native-resource-20261006T0340'
WORKER = '790ac58f1924db2607087c6ab1cdae5d813ba24eda610af1f396d77e93d06584'
HARNESS = '7148945f6ec1dba19f388412f2cfca991cecd7b548d9592df5a5228d33c1324b'
PREREG = 'f6bec7567bc3e676d13f39c1f3f79671e307d4f75483ff1204a67bb33891d5c0'
RELEASE = '65662826f918c156b450f219ae8a60ed47256e3257d0a21d74919a0d606b07bc'


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(path):
    path = Path(path)
    require(path.is_file() and not any(p.is_symlink() for p in (path, *path.parents)), 'Regular nonsymlink input required')
    require(path.stat().st_size <= 3 * 1024**3, 'Hash input exceeds bound')
    result = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024**2), b''):
            result.update(chunk)
    return result.hexdigest()


def read(path):
    require(Path(path).stat().st_size <= 1024**2, 'JSON byte bound exceeded')
    return json.loads(Path(path).read_bytes())


def wav(path):
    require(Path(path).stat().st_size <= 4 * 1024**2, 'Generated WAV byte bound exceeded')
    raw = Path(path).read_bytes()
    require(raw[:4] == b'RIFF' and raw[8:12] == b'WAVE', 'Expected generated RIFF/WAVE')
    offset = 12
    chunks = {}
    for _ in range(128):
        if offset == len(raw):
            break
        require(offset + 8 <= len(raw), 'Truncated WAV chunk')
        kind, size = struct.unpack_from('<4sI', raw, offset)
        start = offset + 8
        require(start + size <= len(raw), 'WAV chunk exceeds file')
        if kind in (b'fmt ', b'data'):
            require(kind not in chunks, 'Duplicate essential WAV chunk')
            chunks[kind] = raw[start:start + size]
        offset = start + size + size % 2
    require(b'fmt ' in chunks and b'data' in chunks, 'Missing WAV audio/header')
    fmt = chunks[b'fmt ']
    code, channels, rate, byte_rate, block, bits = struct.unpack_from('<HHIIHH', fmt)
    if code == 0xfffe:
        code = struct.unpack_from('<I', fmt, 24)[0]
    data = chunks[b'data']
    require(channels == 2 and rate == 44100 and block == channels * bits // 8, 'Native WAV header differs')
    require(byte_rate == rate * block and len(data) % block == 0, 'WAV block extent differs')
    require(len(data) // block == 352800, 'Native WAV frame count differs')
    header = {'channels': channels, 'sample_rate': rate, 'sample_count': len(data) // block, 'bits': bits, 'code': code}
    if code == 3 and bits == 32:
        samples = array.array('f', data)
        if sys.byteorder != 'little':
            samples.byteswap()
        require(all(math.isfinite(v) for v in samples), 'Nonfinite native PCM')
    elif code == 1 and bits == 16:
        samples = array.array('h', data)
        if sys.byteorder != 'little':
            samples.byteswap()
    else:
        require(code == 1 and bits == 24, 'Unsupported generated PCM encoding')
        samples = None
    return header, samples


def main():
    prereg_path = ROOT / 'docs/agent-notes/2026-10-06-capture-application-resource-qualification-preregistration.json'
    release_path = ROOT / 'docs/agent-notes/2026-10-06-root-capture-application-resource-release.json'
    require(sha(prereg_path) == PREREG and sha(release_path) == RELEASE, 'Execution metadata changed')
    prereg, release = read(prereg_path), read(release_path)
    require(release['root_explicit_release'] is True and release['preregistration_sha256'] == PREREG
            and release['harness_sha256'] == HARNESS and release['worker_sha256'] == prereg['worker_sha256'], 'Closed release differs')
    require(sha(ROOT / 'scripts/apply_capture_profile.py') == WORKER, 'Application source changed')
    require(sha(ROOT / 'docs/agent-notes/2026-10-06-capture-application-resource-qualification.py') == HARNESS, 'Harness source changed')
    for slot, name in [('author', 'capture_profile.py'), ('media', 'media.py')]:
        require(sha(ROOT / 'scripts' / name) == prereg['worker_sha256'][slot], 'Worker source changed')
    receipt = read(TRIAL / 'receipt.json')
    receipt_hash = sha(TRIAL / 'receipt.json')
    require(receipt['status'] == 'native_generated_qualification_passed' and receipt['release_sha256'] == RELEASE
            and receipt['preregistration_sha256'] == PREREG and receipt['harness_sha256'] == HARNESS
            and receipt['worker_sha256'] == prereg['worker_sha256'], 'Saved qualification lineage differs')
    require(0 < receipt['elapsed_seconds'] < 600 and receipt['actual_recording_processed'] is False, 'Execution bounds/scope differ')
    require(receipt['listening_accepted'] is False and receipt['master_adopted'] is False
            and receipt['physical_audio_video_sync_verified'] is False, 'Acceptance was promoted')
    for mapping in (receipt['parent_sha256'], receipt['protected_sha256']):
        for name, expected in mapping.items():
            require(sha(name) == expected, 'Protected/parent bytes changed')
    summary = read(TRIAL / 'application-summary.json')
    run = Path(summary['run_dir'])
    require(run.parent == ROOT / 'artifacts/runs' and str(run) == receipt['candidate_run_dir'], 'Candidate selector differs')
    manifest = read(run / 'manifest.json')
    application = read(run / 'application-receipt.json')
    outcome = read(run / 'export/outcome.json')
    for name, expected in [('manifest.json', receipt['manifest_sha256']),
                           ('application-receipt.json', receipt['application_receipt_sha256']),
                           ('export/outcome.json', receipt['export_outcome_sha256'])]:
        require(sha(run / name) == expected, 'Candidate receipt hash differs')
    require(application['status'] == summary['status'] == 'rendered_unreviewed'
            and outcome['status'] == 'exported_unreviewed', 'Candidate state differs')
    require(application['listening_accepted'] is False and application['master_adopted'] is False
            and outcome['listening_accepted'] is False, 'Candidate acceptance was promoted')
    require(application['producer']['application_worker_sha256'] == WORKER
            and application['outputs']['manifest_sha256'] == receipt['manifest_sha256']
            and application['outputs']['export_outcome_sha256'] == receipt['export_outcome_sha256'], 'Application lineage differs')
    author_dir = Path(application['authoring']['directory'])
    author = read(author_dir / 'receipt.json')
    require(author['status'] == 'authored_unrendered' and author['dsp_performed'] is False, 'Authoring state differs')
    require(sha(author_dir / 'receipt.json') == application['authoring']['receipt_sha256'] == summary['authoring_receipt_sha256'], 'Authoring receipt binding differs')
    require(sha(author_dir / 'profile.json') == sha(run / 'applied-profile.json') == summary['profile_sha256'], 'Applied profile differs')
    require(sha(application['authoring']['review']['path']) == application['authoring']['review']['sha256'], 'Capture review changed')
    for context in application['authoring']['context'].values():
        require(sha(context['path']) == context['sha256'], 'Context changed')
    require(application['capture']['native_samples'] == [11025, 44100]
            and application['capture']['source_media_span_seconds'] == [1.75, 2.5]
            and application['capture']['noise_only_verified'] is False, 'Capture claim changed')
    require(manifest['timeline']['audio_start_seconds'] == 1.5 and manifest['timeline']['no_time_stretch'] is True, 'Native origin changed')
    latency = manifest['dsp_latency']['denoise']
    require(latency['status'] == 'measured_and_compensated' and latency['delay_samples'] == 1102
            and latency['remaining_bulk_delay_samples'] == 0 and latency['measured_impulse_offsets_samples'] == [1102] * 4, 'Calibration differs')
    headers = {}
    arrays = {}
    for name in ('source.wav', 'denoised.wav', 'residue.wav', 'baseline.wav', 'cleaned.wav'):
        require(sha(run / name) == manifest['output_sha256'][name] == application['outputs']['audio_sha256'][name], 'Native audio bytes differ')
        headers[name], arrays[name] = wav(run / name)
    reference_header, integers = wav(TRIAL / 'reference.wav')
    parent = Path(application['parent']['run_dir'])
    parent_header, parent_source = wav(parent / 'source.wav')
    golden = array.array('f', (value / 32768 for value in integers))
    require(golden == parent_source == arrays['source.wav'], 'Generated reference transport/channel values differ')
    errors = [abs(s - d - r) for s, d, r in zip(arrays['source.wav'], arrays['denoised.wav'], arrays['residue.wav'])]
    error = max(errors)
    require(error <= 2**-22 and error == receipt['native_checks']['residue_max_abs_error'], 'Residue algebra differs')
    require(max(errors[:2048]) == receipt['native_checks']['first_boundary_error']
            and max(errors[-2048:]) == receipt['native_checks']['last_boundary_error'], 'Boundary algebra differs')
    require(not (run / 'processed.wav').exists(), 'Unexpected tone stage')
    original = TRIAL / 'original.mov'
    video = run / 'export/cleaned-video.mov'
    require(sha(original) == receipt['original_sha256'] == application['source']['sha256'], 'Generated original changed')
    require(sha(video) == outcome['output_sha256']['cleaned-video.mov'] == application['outputs']['video_sha256']['cleaned-video.mov'], 'Delivery bytes changed')
    spec = importlib.util.spec_from_file_location('independent_native_application', ROOT / 'scripts/apply_capture_profile.py')
    app = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app)
    deadline = app.Deadline(120)
    events = []
    directory = TRIAL / 'independent-audit'
    require(not directory.exists() and not directory.is_symlink(), 'Audit output must be fresh')
    directory.mkdir(mode=0o700)
    ffprobe = prereg['binaries']['ffprobe']['path']
    require(sha(ffprobe) == prereg['binaries']['ffprobe']['sha256'], 'Pinned metadata binary changed')
    tables = {}
    commands = []
    for label, file in [('source', original), ('export', video)]:
        for kind in ('packets', 'frames'):
            command = [ffprobe, '-v', 'error', '-threads', '2', '-select_streams', 'v:0', '-show_' + kind]
            if kind == 'packets':
                command += ['-show_data_hash', 'sha256', '-show_entries', 'packet=pts,dts,duration,size,data_hash']
            else:
                command += ['-show_entries', 'frame=best_effort_timestamp,duration,pkt_duration']
            command += ['-of', 'json', str(file)]
            result = app.run_owned(command, deadline=deadline, timeout=30, events=events)
            raw = result.stdout.encode()
            require(len(raw) <= 4 * 1024**2, 'Metadata stdout exceeds bound')
            (directory / (label + '-' + kind + '.json')).write_bytes(raw)
            tables[label, kind] = json.loads(raw)[kind]
            require(len(tables[label, kind]) == 175, 'Video row count differs')
            commands.append(command)
    source_tick = Fraction(manifest['source']['probe']['video']['time_base'])
    export_tick = Fraction(outcome['video_probe']['video']['time_base'])
    saved_picture = read(TRIAL / 'source-picture.json')
    require(tables['source', 'frames'] == saved_picture['source_frames'], 'Retained decoded source table differs')
    for s, o in zip(tables['source', 'packets'], tables['export', 'packets']):
        require(s['data_hash'] == o['data_hash'] and s['size'] == o['size'], 'Ordered encoded packet payload differs')
        for coordinate in ('pts', 'dts'):
            require(int(s[coordinate]) * source_tick - 1 == int(o[coordinate]) * export_tick, 'Encoded packet clock translation differs')
        require(int(s['duration']) * source_tick == int(o['duration']) * export_tick, 'Encoded packet duration differs')
    expected_indices = [n for n in range(204) if n % 7 != 3]
    source_frames = tables['source', 'frames']
    export_frames = tables['export', 'frames']
    require([int(row['best_effort_timestamp']) * source_tick for row in source_frames]
            == [Fraction(1) + Fraction(n, 24) for n in expected_indices], 'Preregistered VFR source clock differs')
    def duration(row, tick):
        return int(row.get('duration', row.get('pkt_duration', 0))) * tick
    for s, o in zip(source_frames, export_frames):
        require(int(s['best_effort_timestamp']) * source_tick - 1 == int(o['best_effort_timestamp']) * export_tick
                and duration(s, source_tick) == duration(o, export_tick) > 0, 'Decoded frame clock/duration differs')
    require(int(export_frames[-1]['best_effort_timestamp']) * export_tick + duration(export_frames[-1], export_tick) == Fraction(17, 2), 'Last VFR extent differs')
    aac = read(TRIAL / 'delivery-audio-timing.json')
    tick = Fraction(aac['decoded_origin_gate']['time_base'])
    aac_origin = int(aac['frames'][0]['best_effort_timestamp']) * tick
    offset = aac_origin - int(export_frames[0]['best_effort_timestamp']) * export_tick
    tolerance = Fraction(1024, 44100) + Fraction(2, 1000)
    require(abs(offset - Fraction(1, 2)) <= tolerance, 'Independent AAC/video origin exceeds tolerance')
    require(str(offset) == aac['decoded_origin_gate']['relative_decoded_audio_video_seconds'], 'Retained AAC calculation differs')
    raw_count = sum(row['nb_samples'] for row in aac['frames'])
    require(raw_count == aac['raw_decoded_sample_count'] and raw_count != 352800, 'AAC raw padding extent was conflated')
    peak = float(outcome['final_audio_loudness']['input_tp'])
    require(math.isfinite(peak) and peak <= -1.5 and peak == float(receipt['final_audio_loudness']['input_tp']), 'Saved final AAC peak gate differs')
    require(outcome['verification']['physical_audio_video_sync_verified'] is False, 'Physical sync was promoted')
    for mapping in (receipt['parent_sha256'], receipt['protected_sha256']):
        for name, expected in mapping.items():
            require(sha(name) == expected, 'Protected/parent changed during independent audit')
    require(sha(TRIAL / 'receipt.json') == receipt_hash, 'Original qualification receipt changed')
    result = {'schema_version': 1, 'actor': '/root/release_review', 'authority': 'Root explicit generated-only metadata probe release; R-HOOK-CONVERGENCE-20261004/R-N13',
              'status': 'independent_generated_native_artifact_audit_passed', 'auditor_source_sha256': sha(__file__),
              'trial_receipt_sha256': receipt_hash, 'application_receipt_sha256': receipt['application_receipt_sha256'],
              'candidate_run_dir': str(run), 'preregistration_sha256': PREREG, 'release_sha256': RELEASE,
              'worker_sha256': WORKER, 'harness_sha256': HARNESS, 'reference_header': reference_header,
              'native_headers': headers, 'generated_reference_values_exact': True,
              'residue_max_abs_error': error, 'first_boundary_error': max(errors[:2048]), 'last_boundary_error': max(errors[-2048:]),
              'video_packets_and_frames': 175, 'video_packet_payloads_equal': True, 'video_clock_translation_seconds': -1,
              'export_last_picture_extent_seconds': '17/2', 'decoded_AAC_origin_seconds': str(aac_origin),
              'relative_AAC_video_origin_error_seconds': str(offset - Fraction(1, 2)), 'AAC_tolerance_seconds': str(tolerance),
              'raw_AAC_decoded_sample_count': raw_count, 'native_master_sample_count': 352800, 'final_AAC_true_peak_dbtp': peak,
              'parent_files_hash_verified': len(receipt['parent_sha256']), 'protected_files_hash_verified': len(receipt['protected_sha256']),
              'metadata_commands': commands, 'owned_subprocesses': events,
              'saved_table_sha256': {path.name: sha(path) for path in directory.glob('*.json')},
              'DSP_or_generation_repeated': False, 'actual_recording_processed': False, 'listening_accepted': False,
              'master_adopted': False, 'physical_audio_video_sync_verified': False}
    (directory / 'receipt.json').write_text(json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + '\n')
    durable = ROOT / 'docs/agent-notes/2026-10-06-capture-application-resource-artifact-audit.json'
    require(not durable.exists(), 'Durable audit receipt must be fresh')
    durable.write_text(json.dumps({key: value for key, value in result.items() if key not in ('metadata_commands', 'owned_subprocesses')}, sort_keys=True, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'status': result['status'], 'receipt_sha256': sha(directory / 'receipt.json'),
                      'durable_receipt_sha256': sha(durable), 'residue_max_abs_error': error,
                      'video_packets_and_frames': 175, 'protected_files_hash_verified': len(receipt['protected_sha256'])}, sort_keys=True))


if __name__ == '__main__':
    main()
