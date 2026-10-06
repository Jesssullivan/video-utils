#!/usr/bin/env python3
"""Read existing matched-candidate hashes/headers/arrays; no media subprocesses."""
import array
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT = ROOT / 'artifacts/experiments/actual-matched-capture-render-20261006T0303'
RELEASE = ROOT / 'docs/agent-notes/2026-10-06-root-actual-nr8-nr10-render-release.json'
WORKER = '00a03ef9fad8543be4335cb5cbcd3c9d9580a6b40b8faeb826811b105fd5daa6'
FRAMES = 6657385


def require(value, reason):
    if not value:
        raise ValueError(reason)


def sha(path):
    path = Path(path)
    require(path.is_file() and not any(p.is_symlink() for p in (path, *path.parents)), 'Regular nonsymlink input required')
    require(path.stat().st_size <= 3 * 1024**3, 'Hash input exceeds bound')
    digest = hashlib.sha256()
    with path.open('rb') as file:
        for chunk in iter(lambda: file.read(1024**2), b''):
            digest.update(chunk)
    return digest.hexdigest()


def read(path):
    require(Path(path).stat().st_size <= 1024**2, 'JSON byte bound exceeded')
    return json.loads(Path(path).read_bytes())


def native(path, floating):
    require(Path(path).stat().st_size <= 128 * 1024**2, 'Actual native file exceeds audit bound')
    with Path(path).open('rb') as file:
        header = file.read(12)
        require(header[:4] == b'RIFF' and header[8:12] == b'WAVE', 'Native RIFF/WAVE required')
        fmt = None
        values = None
        data_size = None
        for _ in range(128):
            chunk = file.read(8)
            if not chunk:
                break
            require(len(chunk) == 8, 'Truncated WAV chunk')
            kind, size = struct.unpack('<4sI', chunk)
            require(size <= 128 * 1024**2, 'Native chunk exceeds bound')
            if kind == b'fmt ':
                require(fmt is None and size <= 256, 'Malformed/duplicate native format')
                fmt = file.read(size)
            elif kind == b'data':
                require(data_size is None, 'Duplicate native data')
                data_size = size
                if floating:
                    require(size == FRAMES * 4, 'Float native extent differs')
                    values = array.array('f')
                    values.fromfile(file, FRAMES)
                    if sys.byteorder != 'little':
                        values.byteswap()
                    require(all(math.isfinite(v) for v in values), 'Nonfinite native samples')
                else:
                    file.seek(size, 1)
            else:
                file.seek(size, 1)
            if size % 2:
                file.seek(1, 1)
    require(fmt is not None and data_size is not None, 'Missing native header/data')
    code, channels, rate, byte_rate, block, bits = struct.unpack_from('<HHIIHH', fmt)
    if code == 0xfffe:
        code = struct.unpack_from('<I', fmt, 24)[0]
    require((channels, rate) == (1, 44100) and block == bits // 8 and byte_rate == rate * block, 'Native channel/rate/block differs')
    require(data_size // block == FRAMES and data_size % block == 0, 'Native frame count differs')
    require((code, bits) == ((3, 32) if floating else (1, 24)), 'Native encoding differs')
    return {'sample_rate': rate, 'channels': channels, 'sample_count': data_size // block,
            'code': code, 'bits': bits}, values


def main(label):
    require(label in ('NR8', 'NR10'), 'Only the released matched labels are allowed')
    release = read(RELEASE)
    candidate = next(c for c in release['candidates'] if c['label'] == label)
    require(release['application_sha256'] == WORKER == sha(ROOT / 'scripts/apply_capture_profile.py'), 'Application source changed')
    require(sha(ROOT / 'scripts/capture_profile.py') == release['author_sha256']
            and sha(ROOT / 'scripts/media.py') == release['media_sha256'], 'Frozen producer changed')
    for file, expected in release['protected_sha256'].items():
        require(sha(file) == expected, 'Protected original/parent/master changed')
    summary_path = EXPERIMENT / (label + '-verified-summary.json')
    summary = read(summary_path)
    require(summary['label'] == label and summary['exit_code'] == 0 and 0 < summary['elapsed_seconds'] <= 610, 'Terminal result differs')
    result = summary['result']
    run = Path(result['run_dir'])
    require(run.parent == ROOT / 'artifacts/runs' and result['status'] == 'rendered_unreviewed', 'Candidate identity/state differs')
    for field in ('listening_accepted', 'master_adopted'):
        require(result[field] is False, 'Acceptance promoted')
    manifest = read(run / 'manifest.json')
    receipt = read(run / 'application-receipt.json')
    outcome = read(run / 'export/outcome.json')
    require(sha(run / 'manifest.json') == result['manifest_sha256']
            and sha(run / 'application-receipt.json') == result['receipt_sha256']
            and sha(run / 'export/outcome.json') == result['export']['outcome_sha256'], 'Candidate metadata hash differs')
    require(sha(candidate['input']) == candidate['source_sha256'] == result['source_sha256'] == receipt['source']['sha256'], 'Original binding differs')
    author_dir = Path(candidate['authoring_dir'])
    require(sha(author_dir / 'receipt.json') == candidate['authoring_receipt_sha256'] == result['authoring_receipt_sha256'], 'Authoring binding differs')
    require(sha(author_dir / 'profile.json') == sha(run / 'applied-profile.json') == candidate['profile_sha256'] == result['profile_sha256'], 'Profile binding differs')
    require(receipt['producer']['application_worker_sha256'] == WORKER, 'Application producer differs')
    require(sha(receipt['authoring']['review']['path']) == receipt['authoring']['review']['sha256'], 'Review changed')
    for context in receipt['authoring']['context'].values():
        require(sha(context['path']) == context['sha256'], 'Context changed')
    require(receipt['capture']['native_samples'] == [180810, 218295]
            and receipt['capture']['source_media_span_seconds'] == [4.1, 4.95]
            and receipt['capture']['noise_only_verified'] is False, 'Capture scope differs')
    require(manifest['timeline']['audio_start_seconds'] == 0 and manifest['timeline']['no_time_stretch'] is True, 'Native origin differs')
    latency = manifest['dsp_latency']['denoise']
    require(latency['status'] == 'measured_and_compensated' and latency['delay_samples'] == 1102
            and latency['remaining_bulk_delay_samples'] == 0 and latency['measured_impulse_offsets_samples'] == [1102] * 2, 'Calibrated native latency differs')
    require(manifest['dsp_latency']['physical_audio_video_sync_verified'] is False
            and manifest['dsp_latency']['post_denoise']['complete_acoustic_alignment_verified'] is False, 'Complete sync/alignment promoted')
    headers = {}
    arrays = {}
    for name in ('source.wav', 'denoised.wav', 'residue.wav', 'processed.wav', 'baseline.wav', 'cleaned.wav'):
        require(sha(run / name) == manifest['output_sha256'][name] == receipt['outputs']['audio_sha256'][name], 'Native output hash differs')
        headers[name], arrays[name] = native(run / name, name not in ('baseline.wav', 'cleaned.wav'))
    parent_source = Path(receipt['parent']['pcm_path'])
    require(sha(run / 'source.wav') == sha(parent_source) == receipt['parent']['pcm_sha256'], 'Repeated original decode changed bytes')
    error = first = last = 0.0
    for index, (source, denoised, residue) in enumerate(zip(arrays['source.wav'], arrays['denoised.wav'], arrays['residue.wav'])):
        residual = abs(source - denoised - residue)
        error = max(error, residual)
        if index < 2048:
            first = max(first, residual)
        if index >= FRAMES - 2048:
            last = max(last, residual)
    require(error <= 2**-22, 'Pure denoise residue arithmetic differs')
    require(manifest['profile']['reduction_db'] == (8 if label == 'NR8' else 10), 'Noise reduction strength differs')
    require(outcome['status'] == 'exported_unreviewed' and outcome['listening_accepted'] is False, 'Export state promoted')
    video = run / 'export/cleaned-video.mov'
    require(sha(video) == outcome['output_sha256']['cleaned-video.mov'] == receipt['outputs']['video_sha256']['cleaned-video.mov'], 'Exported bytes changed')
    verify = outcome['verification']
    for flag in ('source_hash_verified', 'video_frame_count_preserved', 'relative_audio_video_start_verified',
                 'dsp_latency_compensation_recorded', 'final_true_peak_within_target', 'video_packet_timeline_preserved',
                 'video_packet_payload_hashes_preserved'):
        require(verify[flag] is True, 'Required saved export verification missing')
    require(verify['physical_audio_video_sync_verified'] is False and verify['source_decoded_video_frames'] == verify['export_decoded_video_frames'] == 3621
            and verify['source_video_packets'] == verify['export_video_packets'] == 3631, 'Saved native video scope differs')
    require(verify['video_packet_max_pts_delta_seconds'] == verify['video_packet_max_dts_delta_seconds'] == verify['video_packet_max_duration_delta_seconds'] == 0, 'Saved packet clock verification differs')
    peak = float(outcome['final_audio_loudness']['input_tp'])
    require(math.isfinite(peak) and peak <= -1.75, 'Final saved AAC peak exceeds target')
    require(receipt['listening_accepted'] is False and receipt['master_adopted'] is False, 'Receipt acceptance promoted')
    for file, expected in release['protected_sha256'].items():
        require(sha(file) == expected, 'Protected inputs changed during audit')
    output = {'schema_version': 1, 'actor': '/root/release_review', 'authority': 'Root explicit saved-actual-artifact audit; R-HOOK-CONVERGENCE-20261004/R-N13',
              'status': 'independent_actual_candidate_artifact_audit_passed', 'label': label,
              'auditor_source_sha256': sha(__file__), 'root_release_sha256': sha(RELEASE),
              'verified_summary_sha256': sha(summary_path), 'candidate_run_dir': str(run),
              'manifest_sha256': result['manifest_sha256'], 'application_receipt_sha256': result['receipt_sha256'],
              'export_outcome_sha256': result['export']['outcome_sha256'], 'native_headers': headers,
              'original_decode_bytes_equal_parent': True, 'residue_max_abs_error': error,
              'first_boundary_error': first, 'last_boundary_error': last,
              'native_capture_samples': [180810, 218295], 'audio_origin_seconds': 0,
              'calibrated_delay_samples': 1102, 'remaining_bulk_delay_samples': 0,
              'protected_files_hash_verified': len(release['protected_sha256']), 'saved_export_verification': verify,
              'final_AAC_true_peak_dbtp': peak, 'final_AAC_integrated_lufs': float(outcome['final_audio_loudness']['input_i']),
              'actual_media_probes_repeated': False, 'generation_DSP_analysis_repeated': False,
              'native_array_operations': 'Read existing PCM and check source-minus-pure-denoised-minus-residue only; no output audio, spectral inference or restoration',
              'export_clock_proof_scope': 'Readback of hash-bound executed exporter proof; no independent actual-video packet/frame reprobe',
              'noise_only_verified': False, 'complete_acoustic_alignment_verified': False,
              'physical_audio_video_sync_verified': False, 'listening_accepted': False, 'master_adopted': False}
    destination = ROOT / ('docs/agent-notes/2026-10-06-actual-' + label.lower() + '-independent-artifact-audit.json')
    require(not destination.exists(), 'Audit receipt must be fresh')
    destination.write_text(json.dumps(output, sort_keys=True, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'label': label, 'status': output['status'], 'audit_sha256': sha(destination),
                      'residue_max_abs_error': error, 'final_AAC_true_peak_dbtp': peak}, sort_keys=True))


if __name__ == '__main__':
    require(len(sys.argv) == 2, 'Specify one completed NR8/NR10 label')
    main(sys.argv[1])
