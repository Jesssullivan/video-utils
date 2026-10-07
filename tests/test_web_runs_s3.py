"""S3 routes_review lane tests (docs/spec/sprints/ROUTES_REVIEW_S3.md section 8).

Synthetic fixtures only: every case builds a repository-shaped TemporaryDirectory (stage WAVs are 1 s of a
32.7 Hz + 196 Hz sine at 8 kHz written by ``wave``; bundles, renders, sidecars and receipts are generated
in-test). The real take, the main checkout's artifacts/runs, /Users/jess/Documents and /Users/jess/Desktop are
never read. The read API is driven through a test-owned loopback handler that calls the same
``web_runs_api.match``/``serve`` entry points web_api will call once root applies the registration hunk.
Every subprocess has a timeout; every process started here is terminated in tearDown/tearDownClass.
"""
from __future__ import annotations

import datetime
import hashlib
import http.client
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import wave
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tests'))

import annotation_v2  # noqa: E402
import artifact_ids  # noqa: E402
import web_api  # noqa: E402
import web_jobs  # noqa: E402
import web_runs_api  # noqa: E402
from web_jobs import WebJobs, WebJobsError  # noqa: E402

WEB = ROOT / 'web'
SCHEMA_TS = WEB / 'src' / 'lib' / 'server' / 'runs' / 'schema.ts'
OUT_DIR = ROOT / 'artifacts' / 's2' / 'routes_review'
RECEIPT = ROOT / 'docs' / 'agent-notes' / 'sprints' / '20261007-s3' / 'routes_review-walkthrough.json'
TOKEN = 'routes-review-token-' + 'R' * 24  # synthetic; never a real control-API token
RUN = 'RUN-S3'
OTHER = 'RUN-OTHER'
SOURCE_SHA = hashlib.sha256(b'routes-review synthetic original source').hexdigest()
SENTINEL_SOURCE = '/private/sentinel/routes-review/original-take-never-served.mov'
SENTINEL_RUN_DIR = '/Users/sentinel/routes-review/artifacts/runs/RUN-S3'
SENTINEL_AUTHORING = '/tmp/sentinel/routes-review/capture-profiles/authoring'
FAKE_MOV = b'\x00\x00\x00\x14ftypqt  \x00\x00\x02\x00qt  ' + bytes(range(256)) * 16
STAGES = ('source', 'denoised', 'processed', 'cleaned', 'baseline', 'residue')
BANNED = ('rushed', 'dragged', 'late', 'early', 'mistake', 'wrong', 'missed', 'sloppy', 'tight')
RATE = 8000
INSTALL_TIMEOUT_S = 300
CHECK_TIMEOUT_S = 600
BUILD_TIMEOUT_S = 600
METRICS = {'responses': 0, 'leak_checked': 0, 'success_schema_checked': 0}
RESPONSES = []  # (route, status, body) for the NoHostPath sweep

# --------------------------------------------------------------------------- closed key sets (Python side)

RUN_SUMMARY_KEYS = {'run_id', 'run_status', 'source_id', 'source_sha256', 'manifest_sha256', 'manifest_readable',
                    'stage_count', 'state_basis'}
RUN_LIST_KEYS = {'schema_id', 'schema_version', 'runs', 'truncated'}
RUN_GRAPH_KEYS = {'schema_id', 'schema_version', 'run_id', 'run_status', 'manifest_sha256', 'source_sha256',
                  'source_id', 'admitted_sources', 'admitted_sources_lookup', 'pcm', 'timeline', 'stages', 'edges',
                  'processing', 'evidence', 'invalidation', 'listening_acceptance', 'claim_boundary',
                  'unknown_fields', 'discovery_truncated'}
RUN_LAYERS_KEYS = {'schema_id', 'schema_version', 'run_id', 'manifest_sha256', 'selected_evidence_id',
                   'selected_generated_utc', 'alternatives', 'layers', 'media', 'spectrogram', 'clock',
                   'source_extent', 'unknown_fields', 'claim_boundary', 'discovery_truncated'}
CAPABILITIES_KEYS = {'schema_id', 'schema_version', 'tool_count', 'pilot_tool_count', 'tools', 'areas', 'models',
                     'model_note', 'registry_sha256', 'unknown_fields'}
STAGE_KEYS = {'stage', 'file_role', 'role_basis', 'artifact_id', 'signal_version', 'state', 'size_bytes'}
EVIDENCE_KEYS = {'evidence_id', 'kind', 'state', 'reason', 'bound_signal_version', 'generated_utc', 'files'}
EVIDENCE_FILE_KEYS = {'name', 'role', 'artifact_id', 'sha256', 'size_bytes', 'import_verified'}
INVALIDATION_KEYS = {'evidence_id', 'reason', 'was_bound_to', 'now'}
ACCEPTANCE_KEYS = {'value', 'reason', 'scope', 'receipt_sha256', 'master_adopted', 'accepted_file_sha256'}
CLAIM_KEYS = {'listening_acceptance_scope', 'musical_verdict', 'missed_or_extra_notes', 'default_adopted',
              'master_changed'}
PROCESSING_KEYS = {'profile_name', 'denoise', 'tone', 'loudness_targets', 'high_pass_applied', 'hum_notches_applied',
                   'intentional_low_fundamental_hz', 'noise_capture', 'dsp_latency_status',
                   'manifest_listening_accepted_field'}
LAYER_NAMES = {'tone_ab', 'coverage', 'flags_triage', 'phrase_timing', 'spectrogram', 'bpm'}
ENVELOPE_KEYS = {'status', 'reason', 'document'}
BPM_KEYS = {'value', 'reason', 'basis', 'grid'}
SPECTROGRAM_KEYS = {'status', 'reason', 'evidence_id', 'signal_version', 'stage', 'shape', 'band_centre_hz',
                    'band_centre_hz_range', 'hop_seconds', 'window_seconds', 'first_frame_centre_seconds',
                    'axis_offset_seconds', 'matrices', 'reference_lines', 'claim', 'pcen_status'}
MEDIA_KEYS = {'evidence_id', 'sha256', 'frames', 'sample_rate', 'channels', 'role'}
CLOCK_KEYS = {'layer_axis', 'annotation_axis', 'alignment', 'reason'}
TOOL_KEYS = {'name', 'title', 'area', 'area_basis', 'implementation_status', 'evidence_kind', 'annotations', 'skill',
             'limitations_count', 'limitations', 'dependencies', 'input', 'capability', 'capability_reason'}
MODEL_KEYS = {'model_id', 'format', 'license', 'sha256', 'max_bytes', 'source_commit', 'url_host', 'registration',
              'local_presence', 'lane', 'gate', 'status', 'gate_state'}
S2_KEYS = web_runs_api.S2_UNKNOWN_KEYS
S3_KEYS = web_runs_api.S3_UNKNOWN_KEYS


# --------------------------------------------------------------------------- strict parsing

def strict_loads(data):
    """Strict finite JSON: NaN/Infinity and duplicate keys are refused."""
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f'duplicate key {key!r}')
            result[key] = value
        return result

    def constant(value):
        raise ValueError(f'non-finite constant {value}')

    text = data.decode('utf-8') if isinstance(data, (bytes, bytearray)) else data
    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def sha_file(path):
    return sha(Path(path).read_bytes())


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(value, indent=1, sort_keys=True) + '\n').encode()
    path.write_bytes(data)
    return sha(data)


def make_wav(path, *, seconds=1.0, rate=RATE, gain=0.3, phase=0.0):
    """Deterministic PCM16 mono WAV: 32.7 Hz (theoretical C1) + 196 Hz sines."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    count = int(round(seconds * rate))
    frames = bytearray()
    for index in range(count):
        t = index / rate
        value = gain * 0.5 * (math.sin(2 * math.pi * 32.7 * t + phase) + math.sin(2 * math.pi * 196.0 * t))
        frames += struct.pack('<h', int(max(-1.0, min(1.0, value)) * 32767))
    with wave.open(str(path), 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(bytes(frames))
    return sha_file(path)


def flip_byte(path, offset=-1):
    data = bytearray(Path(path).read_bytes())
    data[offset] ^= 0x01
    Path(path).write_bytes(bytes(data))


# --------------------------------------------------------------------------- fixture

class Fixture:
    """A repository-shaped temp root R (artifacts/runs + evidence roots), docs root D and outside dir O."""

    def __init__(self, base, *, bundle_times=('2026-10-07T12:00:00+00:00',), invalid_bundle=False,
                 timing_schema=2, run_kind='real_take', symlink_experiments=False, export=True, clip=False):
        self.base = Path(base)
        self.R = self.base / 'R'
        self.D = self.base / 'D'
        self.O = self.base / 'O'
        self.O.mkdir(parents=True)
        self.artifacts = self.R / 'artifacts'
        self.runs = self.artifacts / 'runs'
        self.run_dir = self.runs / RUN
        self.hashes = {}
        for index, stage in enumerate(STAGES):
            self.hashes[f'{stage}.wav'] = make_wav(self.run_dir / f'{stage}.wav', gain=0.2 + 0.05 * index,
                                                   phase=0.1 * index)
        if export:
            (self.run_dir / 'export').mkdir()
            (self.run_dir / 'export' / 'cleaned-video.mov').write_bytes(FAKE_MOV)
            write_json(self.run_dir / 'export' / 'outcome.json',
                       {'output_sha256': {'cleaned-video.mov': sha(FAKE_MOV)}, 'run_dir': SENTINEL_RUN_DIR})
        if clip:
            import test_web_jobs as wj
            wj.make_clip(self.run_dir / 'export' / 'clip.mov')
        self.manifest = self.manifest_doc()
        self.manifest_sha = write_json(self.run_dir / 'manifest.json', self.manifest)
        other = self.runs / OTHER
        self.other_wav = make_wav(other / 'cleaned.wav', gain=0.11)
        write_json(other / 'manifest.json', {'run_id': OTHER, 'status': 'rendered_unreviewed',
                                             'source': {'sha256': sha(b'other-source'), 'path': SENTINEL_SOURCE},
                                             'outputs': {'cleaned': 'cleaned.wav'},
                                             'output_sha256': {'cleaned.wav': self.other_wav}})
        self.bundles = []
        for stamp in bundle_times:
            self.bundles.append(self.write_bundle(f'bundle-{len(self.bundles)}', stamp, timing_schema=timing_schema,
                                                  run_kind=run_kind))
        if invalid_bundle:
            self.bundles.append(self.write_bundle('bundle-invalid', '2026-10-07T23:00:00+00:00',
                                                  manifest_sha='0' * 64))
        self.render = self.write_render()
        self.sidecar = self.write_sidecar()
        self.compact = self.write_compact(symlinked=symlink_experiments)
        self.receipt_rel = 'docs/agent-notes/routes-review-acceptance.json'
        receipt = {'run_id': RUN, 'manifest_sha256': self.manifest_sha, 'cleaned_wav_sha256': self.hashes['cleaned.wav'],
                   'export_video_sha256': sha(FAKE_MOV), 'listening_accepted': True, 'master_adopted': False,
                   'scope': 'Synthetic acceptance scope sentence for the exact fixture audio only.'}
        self.receipt_sha = write_json(self.D / self.receipt_rel, receipt)

    def manifest_doc(self):
        return {
            'run_id': RUN, 'status': 'rendered_unreviewed', 'schema_version': 1, 'run_dir': SENTINEL_RUN_DIR,
            'source': {'sha256': SOURCE_SHA, 'path': SENTINEL_SOURCE},
            'pcm': {'sample_rate': RATE, 'channels': 1, 'sample_count': RATE, 'duration_seconds': 1.0,
                    'codec': 'pcm_s16le'},
            'timeline': {'audio_start_seconds': 0.0, 'format_start_seconds': 0.0, 'no_time_stretch': True},
            'outputs': {stage: f'{stage}.wav' for stage in STAGES},
            'output_sha256': dict(self.hashes),
            'restoration_stages': [{'stage': 'afftdn', 'output': 'denoised.wav'}],
            'frequency_preservation': {'high_pass_applied': False, 'hum_notches_applied': False,
                                       'intentional_low_fundamental_hz': 32},
            'profile': {'name': 'synthetic-fuller', 'peaking_eq': [{'frequency_hz': 160.0, 'gain_db': 2.0, 'q': 0.7}],
                        'compressor': {'ratio': 2.0, 'threshold_db': -18.0}},
            'loudness': {'cleaned': {'target_integrated_lufs': -18.0, 'target_true_peak_dbtp': -1.75}},
            'capture_profile_application': {'authoring_dir': SENTINEL_AUTHORING, 'listening_accepted': False},
            'noise_capture': {'selected_seconds': [0.1, 0.3], 'review': 'synthetic fixture review text'},
            'dsp_latency': {'denoise': {'filter': 'afftdn', 'delay_samples': 100, 'status': 'measured_and_compensated'},
                            'physical_audio_video_sync_verified': False},
            'commands': [['/nix/store/sentinel-ffmpeg/bin/ffmpeg', '-i', SENTINEL_SOURCE]],
            'tools': {'ffmpeg': '/nix/store/sentinel-ffmpeg/bin/ffmpeg'},
        }

    def unknown_fields(self):
        return {key: {'value': value, 'reason': reason} for key, (value, reason) in web_runs_api.S2_DEFAULTS.items()}

    def write_bundle(self, name, generated, *, manifest_sha=None, timing_schema=2, run_kind='real_take'):
        directory = self.artifacts / 's2' / 'ui' / name
        media = {}
        for side in ('X', 'Y'):
            media_name = f'excerpt-1-{side}.wav'
            digest = make_wav(directory / 'media' / media_name, seconds=0.1, gain=0.25 if side == 'X' else 0.3)
            media[media_name] = {'file': f'media/{media_name}', 'sha256': digest, 'frames': 800, 'sample_rate': RATE,
                                 'channels': 1, 'role': f'tone_ab blind excerpt pair 1 {side}'}
        timing_row_measured = {'phrase_id': 'span-0', 'label': 'riff_region_1', 'label_basis': 'automatic_review_span',
                               'span_source_seconds': [0.1, 0.5], 'status': 'measured', 'median_offset_ms': -12.0,
                               'median_offset_ms_delay_compensated': -14.2, 'iqr_ms': [-16.0, -9.0],
                               'iqr_ms_delay_compensated': [-18.2, -11.2], 'click_proximal_onset_count': 6,
                               'abstain_reason': None}
        if run_kind == 'synthetic_fixture':
            timing_row_measured.update(direction='ahead_of_click', direction_status='synthetic_known_offset_fixture')
        else:
            timing_row_measured.update(direction=None, direction_status='withheld_uncalibrated')
        timing_row_abstained = {'phrase_id': 'span-1', 'label': None, 'label_basis': 'automatic_review_span',
                                'span_source_seconds': [0.5, 0.9], 'status': 'abstained', 'median_offset_ms': None,
                                'median_offset_ms_delay_compensated': None, 'iqr_ms': None,
                                'iqr_ms_delay_compensated': None, 'click_proximal_onset_count': 2,
                                'abstain_reason': 'fewer_than_4_click_proximal_onsets', 'direction': None,
                                'direction_status': None}
        timing_doc = {'tool': 'phrase_timing', 'schema_version': timing_schema, 'run_kind': run_kind,
                      'phrases': [timing_row_measured, timing_row_abstained], 'phrase_basis': 'automatic_review_span',
                      'real_take_status': 'unvalidated_until_operator_spot_check',
                      'detector_delay': {'status': 'synthetic_probe_medians_applied'},
                      'click_reference': {'basis': 'synthetic', 'identity': 'not_verified_metronome'},
                      'inputs': {'analyzed_input_sha256': self.hashes['denoised.wav'], 'path': '/Users/sentinel/x.wav'},
                      'summary': {'measured_count': 1, 'abstained_count': 1, 'phrase_count': 2}}
        flag = lambda index, kind, start, conf='unvalidated_automatic_phrase_candidate': {  # noqa: E731
            'confidence': conf, 'end_seconds': start + 0.2, 'kind': kind, 'performance_issue_confirmed': False,
            'source_time_seconds': start, 'status': 'needs_review'}
        bundle = {
            'schema_id': web_runs_api.PRACTICE_SCHEMA_ID, 'schema_version': 1, 'generated_utc': generated,
            'session_binding': {'run_id': RUN, 'manifest_sha256': manifest_sha or self.manifest_sha,
                                'original_source_sha256': SOURCE_SHA, 'source_extent_seconds': 1.0,
                                'audio_start_seconds': 0.0, 'format_start_seconds': 0.0, 'timeline_no_time_stretch': True},
            'layers': {
                'tone_ab': {
                    'status': 'available', 'file': 'tone-ab.json', 'sha256': sha(b'tone'), 'tool': 'tone_ab',
                    'schema_version': 1, 'tone_ab_status': 'completed',
                    'run': {'run_id': RUN, 'source_sha256': SOURCE_SHA, 'manifest_sha256': self.manifest_sha},
                    'region': {'start_seconds': 0.1, 'end_seconds': 0.9, 'excluded_setup_interval_seconds': [0.0, 0.1]},
                    'loudness_match': {'match_status': 'matched', 'match_lu_delta': 0.02, 'target_lufs': -21.0,
                                       'tolerance_lu': 0.3, 'meter': 'synthetic fixture value (not a measurement)',
                                       'per_arm': {'source': {'lufs_before': -20.0, 'gain_db': -1.0, 'lufs_after': -21.0,
                                                              'abs_delta_lu': 0.0},
                                                   'delivery_master': {'lufs_before': -18.0, 'gain_db': -3.0,
                                                                       'lufs_after': -21.02, 'abs_delta_lu': 0.02}}},
                    'excerpts': {'frames_per_file': 800, 'blind_key': [{'pair': 1, 'X': 'delivery_master', 'Y': 'source'}],
                                 'pairs': [{'pair': 1, 'start_sample': 800, 'end_sample_exclusive': 1600,
                                            'start_seconds': 0.1, 'files': {
                                                'X': {'file': 'excerpt-1-X.wav', 'sha256': media['excerpt-1-X.wav']['sha256']},
                                                'Y': {'file': 'excerpt-1-Y.wav', 'sha256': media['excerpt-1-Y.wav']['sha256']}}}]},
                    'pair_media': [{'pair': 1, 'X': 'excerpt-1-X.wav', 'Y': 'excerpt-1-Y.wav'}],
                    'trial': {'status': 'unavailable', 'reason': 'trial_excerpts_not_requested',
                              'filter': 'atrim=start_sample=a, volume=-3dB'},
                    'experiment': {'band_deltas_vs_delivery_master': {'20-45': {'raw_db': 1.4, 'matched_db': 1.3,
                                                                                 'share_db': 1.2}},
                                   'attack_deltas_vs_delivery_master': {'primary': {'energy_db_matched': 0.01,
                                                                                    'pairs': 12, 'centroid_hz': -3.0,
                                                                                    'centroid_pairs': 12}}},
                    'claims': {'measurements': ['synthetic fixture'], 'inferences': [], 'listening': []},
                    'limitations': ['Synthetic fixture excerpts; no listening review exists.'],
                    'operator_preference': None, 'listening_accepted': False, 'default_adopted': False,
                    'master_changed': False},
                'coverage': {
                    'status': 'available', 'source_min_seconds': 0.0, 'source_max_seconds': 1.0,
                    'overlap_is_not_agreement': 'Overlap between lanes is not agreement, accuracy or correctness.',
                    'intent': {'status': 'available', 'refused': [], 'files': [{
                        'file': 'spans-k3.json', 'k0': 3, 'anchor_status': 'review_candidate_not_confirmed_downbeat',
                        'anchor_adopted': False, 'breakdown1_execution': 'unknown_operator_reported_possible_rush_or_skip',
                        'units': [{'id': 'verse:1', 'kind': 'phrase', 'section_id': 'verse', 'section_unit_index': 1,
                                   'coverage': 'within_source', 'start_source_seconds': 0.1, 'end_source_seconds': 0.5},
                                  {'id': 'verse:2', 'kind': 'phrase', 'section_id': 'verse', 'section_unit_index': 2,
                                   'coverage': 'within_source', 'start_source_seconds': 0.5, 'end_source_seconds': 0.9}],
                        'boundaries': [{'id': 'boundary:0', 'source_seconds': 0.5, 'join_confidence': 'uncertain',
                                        'structural_status': ['breakdown_execution_uncertain']}]}]},
                    'detector': {'status': 'available', 'proposed_review_spans': [
                        {'kind': 'low_register_riff_or_breakdown_candidate', 'label': 'riff_region_1',
                         'source_start_seconds': 0.2, 'source_end_seconds': 0.6}]}},
                'flags_triage': {'status': 'available', 'file': 'flags-triage.json', 'sha256': sha(b'flags'), 'document': {
                    'schema_id': 'video-utils.flags-triage.s2', 'schema_version': 1, 'source_sha256': SOURCE_SHA,
                    'denominators': {'shown': 1, 'suppressed_lower_priority': 1, 'navigation_hidden': 1, 'total_flags': 3},
                    'shown': [{'flag_id': 'flag-1', 'flag': flag(1, 'automatic_recurrence_review_candidate', 0.3),
                               'window_id': 'grid_+00', 'tier': 'T2', 'tier_name': 'automatic_recurrence'}],
                    'suppressed': [{'flag_id': 'flag-2', 'flag': flag(2, 'spectral_texture_region_candidate', 0.35),
                                    'window_id': 'grid_+00', 'reason': 'lower_priority_in_window',
                                    'winner_flag_id': 'flag-1'}],
                    'hidden_navigation': [{'flag_id': 'flag-0', 'flag': flag(0, 'four_pulse_group_review_candidate', 0.1,
                                                                             'navigation_proxy_not_confirmed_bar'),
                                           'reason': 'navigation_proxy_hidden_by_default'}],
                    'window_basis': {'kind': 'click_grid_16_period_navigation_windows', 'period_seconds': 0.25,
                                     'phase_seconds_source': 0.0, 'window_seconds': 4.0},
                    'timeline': {'axis': 'original_source_stream_timestamps_seconds'}}},
                'phrase_timing': {'status': 'available', 'refused': [], 'files': [{
                    'status': 'available', 'file': 'layers/phrase-timing.json', 'sha256': sha(b'timing'),
                    'analyzed_input_sha256': self.hashes['denoised.wav'],
                    'source_binding': 'session manifest output denoised.wav', 'document': timing_doc}]},
            },
            'media': media,
            'claim_boundary': {'listening_acceptance': 'not_established', 'musical_verdict': 'not_established'},
            'unknown_fields': self.unknown_fields(),
            'inputs': [{'path': '/private/var/sentinel/layers/flags-triage.json', 'sha256_before': sha(b'x')}],
            'commands': [{'argv': ['/nix/store/sentinel-ffmpeg/bin/ffmpeg', '<out>']}],
            'evidence_kind': 'composed_existing_evidence_not_new_analysis',
        }
        digest = write_json(directory / 'bundle.json', bundle)
        rel = f's2/ui/{name}/bundle.json'
        return {'dir': directory, 'path': directory / 'bundle.json', 'rel': rel,
                'evidence_id': web_runs_api.evidence_id_for(rel, digest), 'media': media}

    def write_render(self):
        directory = self.artifacts / 's2' / 'lowreg' / 'render-a'
        directory.mkdir(parents=True)
        frames, bands = 4, 160
        files = {}
        for matrix, base in (('log_power_db', -80.0), ('pcen', 0.5)):
            values = [base + (row * bands + band) * 0.01 for row in range(frames) for band in range(bands)]
            raw = struct.pack(f'<{len(values)}d', *values)
            (directory / f'{matrix}.f64le').write_bytes(raw)
            files[matrix] = {'path': f'{matrix}.f64le', 'sha256': sha(raw), 'bytes': len(raw),
                             'dtype': 'float64_little_endian', 'layout': 'row_major_frames_by_bands',
                             'shape': [frames, bands]}
        resampled = sha(b'synthetic 8 kHz analysis copy of denoised.wav')
        render = {'schema': 'lowreg-render-v1', 'shape': {'frames': frames, 'bands': bands}, 'files': files,
                  'input': {'path': '/Users/sentinel/resampled.wav', 'sha256': resampled},
                  'resampler': {'command': '/nix/store/sentinel-ffmpeg/bin/ffmpeg -ar 8000', 'tool_version': 'x',
                                'output_sha256': resampled, 'source_sha256': self.hashes['denoised.wav']},
                  'band_centre_hz': [20 * 2 ** (k / 24) for k in range(bands)], 'hop_seconds': 0.02,
                  'temporal_support_seconds': 0.512, 'coverage': {'first_frame_centre_seconds': 0.256},
                  'pcen_status': 'experimental_fixed_knobs_not_tuned'}
        digest = write_json(directory / 'render.json', render)
        rel = 's2/lowreg/render-a/render.json'
        return {'dir': directory, 'rel': rel, 'evidence_id': web_runs_api.evidence_id_for(rel, digest)}

    def write_sidecar(self):
        directory = self.artifacts / 's3' / 'markers' / 'export-a'
        payload = b'<?xml version="1.0"?><fcpxml version="1.10"><!-- synthetic --></fcpxml>\n'
        (directory / 'review.fcpxmld').mkdir(parents=True)
        (directory / 'review.fcpxmld' / 'Info.fcpxml').write_bytes(payload)
        sidecar = {'format': 'editor_marker_export_sidecar', 'schema_version': 1, 'export_format': 'fcpxml',
                   'source_sha256': SOURCE_SHA, 'native_export_status': 'written_unverified',
                   'application_import': 'not_performed',
                   'payload_sha256': {'review.fcpxmld/Info.fcpxml': sha(payload)}}
        digest = write_json(directory / web_runs_api.SIDECAR_NAME, sidecar)
        rel = f's3/markers/export-a/{web_runs_api.SIDECAR_NAME}'
        return {'dir': directory, 'payload': directory / 'review.fcpxmld' / 'Info.fcpxml', 'rel': rel,
                'evidence_id': web_runs_api.evidence_id_for(rel, digest)}

    def write_compact(self, symlinked=False):
        target_root = self.O / 'experiments' if symlinked else self.artifacts / 'experiments'
        directory = target_root / 'compact-a'
        directory.mkdir(parents=True)
        movie = FAKE_MOV + b'marked-compact'
        (directory / 'marked-compact.mov').write_bytes(movie)
        receipt = {'tool': 'marked_compact', 'schema_version': 1, 'status': 'marked_compact_composition_verified',
                   'created_utc': '2026-10-07T01:00:00+00:00', 'output': '/Users/sentinel/out/marked-compact.mov',
                   'output_sha256': sha(movie), 'run_dir': SENTINEL_RUN_DIR,
                   'audio_branch': {'cleaned_sha256': self.hashes['cleaned.wav'], 'manifest_sha256': self.manifest_sha}}
        digest = write_json(directory / 'receipt.json', receipt)
        if symlinked:
            os.symlink(target_root, self.artifacts / 'experiments')
        rel = 'experiments/compact-a/receipt.json'
        return {'dir': directory, 'movie': directory / 'marked-compact.mov', 'rel': rel,
                'evidence_id': web_runs_api.evidence_id_for(rel, digest)}

    def api(self, pins=None, program_root=None):
        pins = ((self.receipt_rel, self.receipt_sha),) if pins is None else pins
        return web_runs_api.RunsAPI(self.R, acceptance_pins=pins, docs_root=self.D, program_root=program_root)

    def forbidden(self):
        values = {str(self.base), os.path.realpath(self.base), str(ROOT), '/Users/', '/private/', '/tmp/',
                  SENTINEL_RUN_DIR, SENTINEL_SOURCE, SENTINEL_AUTHORING, '/nix/store/'}
        return sorted(values)


# --------------------------------------------------------------------------- loopback handler (same entry points)

class RunsHandler(web_api.Handler):
    """web_api.Handler with a dispatcher that only knows the runs routes (match + serve)."""

    def _dispatch(self):
        self._consumed = False
        try:
            self._trusted()
            parts = urlsplit(self.path)
            route = web_runs_api.match(parts.path)
            if route is None:
                raise WebJobsError('route_not_found', 404, 'unknown route')
            web_runs_api.serve(self, route, parts.query)
        except WebJobsError as error:
            self._safe_drain()
            self._safe_json(error.status, error.body())
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass
        except Exception:  # pragma: no cover - mirrors web_api's generic refusal
            self._safe_drain()
            self._safe_json(500, {'status': 'error', 'code': 'internal_error', 'error': 'internal_error'})

    do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = _dispatch


class RunsServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, api):
        self.runs_api = api
        self.token = TOKEN
        self.shutting_down = False
        super().__init__(('127.0.0.1', 0), RunsHandler)

    @property
    def hosts(self):
        port = self.server_address[1]
        return {f'127.0.0.1:{port}', f'localhost:{port}'}


class Response:
    def __init__(self, status, headers, body, complete=True):
        self.status, self.headers, self.body, self.complete = status, headers, body, complete

    @property
    def json(self):
        return strict_loads(self.body)


class ApiCase(unittest.TestCase):
    """Per-test fixture root and loopback server."""

    fixture_options = {}

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix='routes-review-')
        self.addCleanup(self._tmp.cleanup)
        self.fx = Fixture(Path(self._tmp.name), **self.fixture_options)
        self.start(self.fx.api())

    def start(self, api):
        if getattr(self, 'server', None) is not None:
            self.stop()
        self.api = api
        self.server = RunsServer(api)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': 0.05}, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]
        self.addCleanup(self.stop)

    def stop(self):
        server = getattr(self, 'server', None)
        if server is not None:
            self.server = None
            server.shutdown()
            server.server_close()
            self.thread.join(timeout=10)

    def request(self, path, *, method='GET', token=TOKEN, host=None, raw=False):
        if raw:  # hand-written request line (non-ASCII bytes)
            sock = socket.create_connection(('127.0.0.1', self.port), timeout=30)
            try:
                head = (f'{method} '.encode() + path + b' HTTP/1.1\r\n' + f'Host: 127.0.0.1:{self.port}\r\n'.encode()
                        + f'Authorization: Bearer {token}\r\nConnection: close\r\n\r\n'.encode())
                sock.sendall(head)
                chunks = []
                while True:
                    chunk = sock.recv(65536)
                    if not chunk:
                        break
                    chunks.append(chunk)
            finally:
                sock.close()
            data = b''.join(chunks)
            top, _, body = data.partition(b'\r\n\r\n')
            status = int(top.split(b' ', 2)[1])
            response = Response(status, {}, body)
        else:
            conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=30)
            headers = {'Host': host or f'127.0.0.1:{self.port}'}
            if token:
                headers['Authorization'] = f'Bearer {token}'
            try:
                conn.request(method, path, headers=headers)
                reply = conn.getresponse()
                complete = True
                try:
                    body = reply.read()
                except http.client.IncompleteRead as error:
                    body, complete = error.partial, False
                response = Response(reply.status, {k.lower(): v for k, v in reply.getheaders()}, body, complete)
            finally:
                conn.close()
        RESPONSES.append((path if isinstance(path, str) else path.decode('latin-1'), response.status, response.body,
                          self.fx.forbidden()))
        METRICS['responses'] += 1
        # Every status class is checked, 5xx bodies included (registry_unreadable, layers_too_large).
        for needle in self.fx.forbidden():
            self.assertNotIn(needle.encode(), response.body, f'{path!r} leaked a host path or command string')
        METRICS['leak_checked'] += 1
        return response

    def get_json(self, path, status=200):
        response = self.request(path)
        self.assertEqual(response.status, status, response.body[:400])
        return response.json

    def graph(self):
        return self.get_json(f'/api/v1/runs/{RUN}')

    def layers(self, query=''):
        return self.get_json(f'/api/v1/runs/{RUN}/layers{query}')

    def assert_code(self, response, codes):
        self.assertNotEqual(response.status, 200)
        body = response.json
        self.assertEqual(body.get('status'), 'error')
        self.assertIn(body.get('code'), codes, body)
        return body['code']


# --------------------------------------------------------------------------- 1. Confinement

class Confinement(ApiCase):
    """16 adversarial cases, each refused with a typed code and never a 200."""

    CASES = []

    def record(self, name, response, codes):
        code = self.assert_code(response, codes)
        Confinement.CASES.append({'case': name, 'status': response.status, 'code': code})

    def test_run_id_forms_are_refused(self):
        for name, path in (('dotdot', '/api/v1/runs/..'), ('encoded_dotdot', '/api/v1/runs/%2e%2e'),
                           ('absolute_path', '/api/v1/runs//etc/passwd'), ('partial_suffix', f'/api/v1/runs/{RUN}.partial'),
                           ('id_129_chars', '/api/v1/runs/' + 'a' * 129), ('empty_segment', '/api/v1/runs/')):
            with self.subTest(case=name):
                self.record(name, self.request(path), {'malformed_id'})
        with self.subTest(case='slash_in_id'):
            self.record('slash_in_id', self.request('/api/v1/runs/a/b'), {'route_not_found', 'malformed_id', 'unknown_run'})
        with self.subTest(case='non_ascii'):
            self.record('non_ascii', self.request('/api/v1/runs/RéN'.encode('utf-8'), raw=True), {'malformed_id'})

    def test_symlinked_run_manifest_and_stage_are_refused(self):
        os.symlink(self.fx.run_dir, self.fx.runs / 'RUN-LINK')
        self.record('symlinked_run_dir', self.request('/api/v1/runs/RUN-LINK'), {'confinement_refused'})
        manifest_run = self.fx.runs / 'RUN-MLINK'
        manifest_run.mkdir()
        os.symlink(self.fx.run_dir / 'manifest.json', manifest_run / 'manifest.json')
        self.record('symlinked_manifest', self.request('/api/v1/runs/RUN-MLINK'), {'confinement_refused'})
        stage_run = self.fx.runs / 'RUN-SLINK'
        stage_run.mkdir()
        os.symlink(self.fx.run_dir / 'denoised.wav', stage_run / 'denoised.wav')
        write_json(stage_run / 'manifest.json', {'source': {'sha256': SOURCE_SHA}, 'outputs': {'denoised': 'denoised.wav'},
                                                 'output_sha256': {'denoised.wav': self.fx.hashes['denoised.wav']}})
        self.record('symlinked_stage', self.request('/api/v1/runs/RUN-SLINK'), {'confinement_refused'})
        self.record('symlinked_stage_artifact',
                    self.request(f'/api/v1/runs/RUN-SLINK/artifacts/{artifact_ids.artifact_id_for("RUN-SLINK/denoised.wav", self.fx.hashes["denoised.wav"])}'),
                    {'confinement_refused'})

    def test_evidence_through_symlinked_directory_is_not_discovered(self):
        outside = self.fx.O / 'linked-bundle'
        shutil.copytree(self.fx.bundles[0]['dir'], outside)
        os.symlink(outside, self.fx.artifacts / 's2' / 'linked')
        digest = sha_file(outside / 'bundle.json')
        evidence = web_runs_api.evidence_id_for('s2/linked/bundle.json', digest)
        graph = self.graph()
        self.assertNotIn(evidence, [item['evidence_id'] for item in graph['evidence']])
        self.record('evidence_via_symlinked_dir', self.request(f'/api/v1/runs/{RUN}/layers?evidence={evidence}'),
                    {'unknown_evidence'})

    def test_media_name_not_in_table_and_with_slash(self):
        evidence = self.fx.bundles[0]['evidence_id']
        self.record('media_not_in_table', self.request(f'/api/v1/runs/{RUN}/layers/media/{evidence}/nope.wav'),
                    {'unknown_media'})
        self.record('media_with_slash', self.request(f'/api/v1/runs/{RUN}/layers/media/{evidence}/media/excerpt-1-X.wav'),
                    {'unknown_media'})

    def test_artifact_of_another_run(self):
        other = artifact_ids.artifact_id_for(f'{OTHER}/cleaned.wav', self.fx.other_wav)
        self.assertEqual(self.request(f'/api/v1/runs/{OTHER}/artifacts/{other}').status, 200)
        self.record('artifact_of_other_run', self.request(f'/api/v1/runs/{RUN}/artifacts/{other}'), {'unknown_artifact'})

    @classmethod
    def tearDownClass(cls):
        METRICS['confinement'] = {'refused': len(cls.CASES), 'cases': sorted(cls.CASES, key=lambda item: item['case'])}


class ConfinementSymlinkRoot(ApiCase):
    """An evidence root (artifacts/experiments) that is a symlink out of artifacts/ is never entered."""

    fixture_options = {'symlink_experiments': True}

    def test_symlinked_evidence_root(self):
        graph = self.graph()
        self.assertNotIn(self.fx.compact['evidence_id'], [item['evidence_id'] for item in graph['evidence']])
        response = self.request(f'/api/v1/runs/{RUN}/layers?evidence={self.fx.compact["evidence_id"]}')
        code = self.assert_code(response, {'unknown_evidence'})
        Confinement.CASES.append({'case': 'symlinked_evidence_root', 'status': response.status, 'code': code})


# --------------------------------------------------------------------------- 3. HashBinding

class HashBinding(ApiCase):
    """9 mutation cases, each detected with the specified state or code."""

    CASES = []

    def stage(self, graph, name):
        return next(item for item in graph['stages'] if item['stage'] == name)

    def evidence(self, graph, evidence_id):
        return next(item for item in graph['evidence'] if item['evidence_id'] == evidence_id)

    def done(self, name):
        HashBinding.CASES.append(name)

    def test_stage_flip_is_stale(self):
        self.assertEqual(self.stage(self.graph(), 'processed.wav')['state'], 'current')
        flip_byte(self.fx.run_dir / 'processed.wav')
        self.assertEqual(self.stage(self.graph(), 'processed.wav')['state'], 'stale')
        self.done('stage_flip_stale')

    def test_deleted_stage_is_missing(self):
        (self.fx.run_dir / 'baseline.wav').unlink()
        node = self.stage(self.graph(), 'baseline.wav')
        self.assertEqual((node['state'], node['size_bytes']), ('missing', None))
        self.assertEqual(self.request(f'/api/v1/runs/{RUN}/artifacts/{node["artifact_id"]}').status, 410)
        self.done('stage_deleted_missing')

    def test_manifest_edit_invalidates_bundle(self):
        evidence = self.fx.bundles[0]['evidence_id']
        self.assertEqual(self.evidence(self.graph(), evidence)['state'], 'current')
        manifest = dict(self.fx.manifest, status='edited_after_bundle')
        write_json(self.fx.run_dir / 'manifest.json', manifest)
        graph = self.graph()
        item = self.evidence(graph, evidence)
        self.assertEqual((item['state'], item['reason']), ('invalidated', 'bound_manifest_changed'))
        self.assertIn(evidence, [row['evidence_id'] for row in graph['invalidation']])
        layers = self.layers()
        self.assertIsNone(layers['selected_evidence_id'])
        self.assertEqual(layers['layers']['coverage']['status'], 'unavailable')
        self.assert_code(self.request(f'/api/v1/runs/{RUN}/layers?evidence={evidence}'), {'evidence_invalidated'})
        self.done('manifest_edit_bound_manifest_changed')

    def test_bundle_media_flip_is_media_stale(self):
        bundle = self.fx.bundles[0]
        path = f'/api/v1/runs/{RUN}/layers/media/{bundle["evidence_id"]}/excerpt-1-X.wav'
        ok = self.request(path)
        self.assertEqual(ok.status, 200)
        self.assertEqual(sha(ok.body), ok.headers['x-artifact-sha256'])
        self.assertEqual(ok.headers.get('accept-ranges'), 'none')
        flip_byte(bundle['dir'] / 'media' / 'excerpt-1-X.wav')
        self.assert_code(self.request(path), {'media_stale'})
        (bundle['dir'] / 'media' / 'excerpt-1-Y.wav').unlink()
        self.assert_code(self.request(f'/api/v1/runs/{RUN}/layers/media/{bundle["evidence_id"]}/excerpt-1-Y.wav'),
                         {'media_missing'})
        self.done('bundle_media_flip_media_stale')

    def test_bundle_json_edit_rereads_and_rebinds(self):
        first = self.layers()
        self.assertEqual(first['selected_evidence_id'], self.fx.bundles[0]['evidence_id'])
        path = self.fx.bundles[0]['path']
        document = json.loads(path.read_text())
        document['generated_utc'] = '2026-10-07T13:30:00+00:00'
        document['layers']['flags_triage']['document']['window_basis']['period_seconds'] = 0.5
        new_sha = write_json(path, document)
        second = self.layers()
        self.assertEqual(second['selected_evidence_id'], web_runs_api.evidence_id_for(self.fx.bundles[0]['rel'], new_sha))
        self.assertNotEqual(second['selected_evidence_id'], first['selected_evidence_id'])
        self.assertEqual(second['selected_generated_utc'], '2026-10-07T13:30:00+00:00')
        self.assertEqual(second['layers']['bpm']['grid']['period_seconds'], 0.5)
        self.done('bundle_json_edit_rebinds')

    def test_render_parent_not_current(self):
        layers = self.layers()
        self.assertEqual(layers['spectrogram']['status'], 'available')
        self.assertEqual(layers['unknown_fields']['spectrogram_binding']['value'], 'bound')
        flip_byte(self.fx.run_dir / 'denoised.wav')
        graph = self.graph()
        item = self.evidence(graph, self.fx.render['evidence_id'])
        self.assertEqual((item['state'], item['reason']), ('invalidated', 'analyzed_input_not_current'))
        layers = self.layers()
        self.assertEqual(layers['spectrogram']['status'], 'unavailable')
        self.assertEqual(layers['unknown_fields']['spectrogram_binding']['value'], 'unavailable')
        self.assert_code(self.request(f'/api/v1/runs/{RUN}/layers/media/{self.fx.render["evidence_id"]}/log_power_db.f64le'),
                         {'media_stale'})
        self.done('render_parent_analyzed_input_not_current')

    def test_marker_file_flip(self):
        self.assertEqual(self.evidence(self.graph(), self.fx.sidecar['evidence_id'])['state'], 'current')
        flip_byte(self.fx.sidecar['payload'], 20)
        item = self.evidence(self.graph(), self.fx.sidecar['evidence_id'])
        self.assertEqual((item['state'], item['reason'], item['files']), ('invalidated', 'file_hash_mismatch', []))
        self.done('marker_flip_file_hash_mismatch')

    def test_artifact_changed_between_hash_and_send(self):
        node = self.stage(self.graph(), 'cleaned.wav')
        path = self.fx.run_dir / 'cleaned.wav'
        full = path.stat().st_size

        def truncate():
            with open(path, 'r+b') as handle:
                handle.truncate(full // 2)
        self.api.before_send = truncate
        response = self.request(f'/api/v1/runs/{RUN}/artifacts/{node["artifact_id"]}')
        self.api.before_send = None
        self.assertEqual(response.status, 200)
        self.assertFalse(response.complete)
        self.assertLess(len(response.body), full)
        self.done('artifact_short_body_closed_connection')

    def test_receipt_pin_mismatch(self):
        accepted = self.graph()['listening_acceptance']
        self.assertEqual(accepted['value'], 'accepted')
        self.assertEqual(accepted['scope'], 'Synthetic acceptance scope sentence for the exact fixture audio only.')
        self.assertIs(accepted['master_adopted'], False)
        self.start(self.fx.api(pins=((self.fx.receipt_rel, '0' * 64),)))
        refused = self.graph()['listening_acceptance']
        self.assertEqual((refused['value'], refused['scope'], refused['receipt_sha256']), ('not_established', None, None))
        self.done('receipt_pin_mismatch_not_established')

    @classmethod
    def tearDownClass(cls):
        METRICS['hash_binding'] = {'detected': len(cls.CASES), 'cases': sorted(cls.CASES)}


# --------------------------------------------------------------------------- 4. Schema

def ts_struct_keys(text, name):
    """Top-level keys of `export const <name> = Schema.Struct({ ... })` (one key per line)."""
    match = re.search(rf'export const {name} = Schema\.Struct\(\{{\n', text)
    if match is None:
        raise AssertionError(f'{name} not found in schema.ts')
    keys, depth = [], 0
    for line in text[match.end():].splitlines():
        if depth == 0:
            if line.startswith('})'):
                return set(keys)
            key = re.match(r"^\t'?([A-Za-z_][\w.]*)'?\s*:", line)
            if key:
                keys.append(key.group(1))
        stripped = re.sub(r"'[^']*'|\"[^\"]*\"|`[^`]*`", '', line)
        depth += sum(stripped.count(c) for c in '({[') - sum(stripped.count(c) for c in ')}]')
        if depth < 0:
            return set(keys)
    raise AssertionError(f'{name} struct did not close')


class Schema(ApiCase):
    fixture_options = {'bundle_times': ('2026-10-07T12:00:00+00:00',)}

    def check_unknowns(self, fields, where):
        self.assertEqual(set(fields), set(S2_KEYS) | set(S3_KEYS), where)
        present = 0
        for key in (*S2_KEYS, *S3_KEYS):
            entry = fields[key]
            self.assertIn('value', entry, f'{where}.{key}')
            self.assertIsInstance(entry.get('reason'), str, f'{where}.{key}')
            self.assertTrue(entry['reason'], f'{where}.{key}')
            present += 1
        return present

    def test_success_responses_are_closed_and_strict(self):
        runs = self.get_json('/api/v1/runs')
        self.assertEqual(set(runs), RUN_LIST_KEYS)
        self.assertEqual(runs['schema_id'], 'video-utils.web-runs.list')
        for row in runs['runs']:
            self.assertEqual(set(row), RUN_SUMMARY_KEYS)
            self.assertEqual(row['state_basis'], 'listing does not re-hash')
        self.assertEqual([row['run_id'] for row in runs['runs']], sorted([row['run_id'] for row in runs['runs']], reverse=True))
        graph = self.graph()
        self.assertEqual(set(graph), RUN_GRAPH_KEYS)
        self.assertEqual(set(graph['processing']), PROCESSING_KEYS)
        self.assertEqual(set(graph['listening_acceptance']), ACCEPTANCE_KEYS)
        self.assertEqual(set(graph['claim_boundary']), CLAIM_KEYS)
        for node in graph['stages']:
            self.assertEqual(set(node), STAGE_KEYS)
            self.assertIn(node['state'], ('current', 'stale', 'missing', 'unbound'))
        for item in graph['evidence']:
            self.assertEqual(set(item), EVIDENCE_KEYS)
            for file in item['files']:
                self.assertEqual(set(file), EVIDENCE_FILE_KEYS)
        for item in graph['invalidation']:
            self.assertEqual(set(item), INVALIDATION_KEYS)
        self.assertEqual([edge['from'] + '>' + edge['to'] for edge in graph['edges']],
                         ['source.wav>denoised.wav', 'denoised.wav>processed.wav', 'processed.wav>cleaned.wav',
                          'source.wav>baseline.wav', 'source.wav>residue.wav', 'denoised.wav>residue.wav'])
        self.assertIs(graph['processing']['high_pass_applied'], False)
        self.assertIs(graph['processing']['hum_notches_applied'], False)
        layers = self.layers()
        self.assertEqual(set(layers), RUN_LAYERS_KEYS)
        self.assertEqual(set(layers['layers']), LAYER_NAMES)
        for name in ('tone_ab', 'coverage', 'flags_triage', 'phrase_timing', 'spectrogram'):
            self.assertEqual(set(layers['layers'][name]), ENVELOPE_KEYS, name)
        self.assertEqual(set(layers['layers']['bpm']), BPM_KEYS)
        self.assertEqual(set(layers['spectrogram']), SPECTROGRAM_KEYS)
        self.assertEqual(set(layers['clock']), CLOCK_KEYS)
        self.assertEqual(layers['clock']['alignment'], 'unverified')
        for record in layers['media'].values():
            self.assertEqual(set(record), MEDIA_KEYS)
        caps = self.get_json('/api/v1/capabilities')
        self.assertEqual(set(caps), CAPABILITIES_KEYS)
        for tool in caps['tools']:
            self.assertEqual(set(tool), TOOL_KEYS)
        for model in caps['models']:
            self.assertEqual(set(model), MODEL_KEYS)
        METRICS['success_schema_checked'] += 4
        METRICS['unknown_keys_present'] = {'run_graph': self.check_unknowns(graph['unknown_fields'], 'graph'),
                                           'run_layers': self.check_unknowns(layers['unknown_fields'], 'layers'),
                                           'required_per_document': len(S2_KEYS) + len(S3_KEYS)}
        self.assertEqual(len(S2_KEYS) + len(S3_KEYS), 33)
        for key in ('clock_alignment', 'editor_import'):
            self.assertEqual(graph['unknown_fields'][key]['value'], 'unverified')
        self.assertEqual(graph['unknown_fields']['share_low_register_preservation']['value'], 'not_claimed')
        self.assertEqual(graph['unknown_fields']['stems']['value'], 'not_available')
        self.assertIs(graph['unknown_fields']['room_response_recovered']['value'], False)
        self.assertIs(graph['unknown_fields']['physical_av_sync']['value'], False)
        self.assertIsNone(graph['unknown_fields']['annotation_source']['value'])

    def test_strict_parser_refuses_nan_and_duplicates(self):
        with self.assertRaises(ValueError):
            strict_loads(b'{"a": NaN}')
        with self.assertRaises(ValueError):
            strict_loads(b'{"a": 1, "a": 2}')
        (self.fx.runs / 'RUN-NAN').mkdir()
        (self.fx.runs / 'RUN-NAN' / 'manifest.json').write_text('{"source": {"sha256": "x"}, "status": NaN}')
        self.assert_code(self.request('/api/v1/runs/RUN-NAN'), {'manifest_unreadable'})
        (self.fx.runs / 'RUN-DUP').mkdir()
        (self.fx.runs / 'RUN-DUP' / 'manifest.json').write_text('{"status": "a", "status": "b"}')
        self.assert_code(self.request('/api/v1/runs/RUN-DUP'), {'manifest_unreadable'})

    def test_typescript_key_sets_match(self):
        text = SCHEMA_TS.read_text()
        pairs = {'RunSummary': RUN_SUMMARY_KEYS, 'RunList': RUN_LIST_KEYS, 'RunGraph': RUN_GRAPH_KEYS,
                 'RunLayers': RUN_LAYERS_KEYS, 'Capabilities': CAPABILITIES_KEYS}
        identical = 0
        for name, expected in pairs.items():
            with self.subTest(schema=name):
                self.assertEqual(ts_struct_keys(text, name), expected)
                identical += 1
        METRICS['ts_python_key_parity'] = f'{identical}/{len(pairs)}'

    def test_method_query_and_size_policy(self):
        self.assert_code(self.request(f'/api/v1/runs/{RUN}', method='POST'), {'method_not_allowed'})
        self.assert_code(self.request('/api/v1/runs?limit=0'), {'bad_query'})
        self.assert_code(self.request('/api/v1/runs?limit=501'), {'bad_query'})
        self.assert_code(self.request('/api/v1/runs?other=1'), {'bad_query'})
        self.assert_code(self.request(f'/api/v1/runs/{RUN}?x=1'), {'bad_query'})
        self.assert_code(self.request(f'/api/v1/runs/{RUN}/layers?evidence=bad'), {'bad_query'})
        self.assert_code(self.request('/api/v1/runs/NOPE'), {'unknown_run'})
        self.assert_code(self.request(f'/api/v1/runs/{RUN}/artifacts/art_x'), {'malformed_id'})
        self.assert_code(self.request(f'/api/v1/runs/{RUN}', token=None), {'token_required'})
        self.assert_code(self.request(f'/api/v1/runs/{RUN}', host='evil.example:80'), {'host_refused'})
        original = web_runs_api.MAX_RESPONSE_BYTES
        web_runs_api.MAX_RESPONSE_BYTES = 256
        try:
            self.assert_code(self.request(f'/api/v1/runs/{RUN}/layers'), {'layers_too_large'})
        finally:
            web_runs_api.MAX_RESPONSE_BYTES = original

    def test_downloads_rehash_and_labels(self):
        graph = self.graph()
        export = next(node for node in graph['stages'] if node['stage'] == 'export/cleaned-video.mov')
        self.assertEqual(export['state'], 'current')
        response = self.request(f'/api/v1/runs/{RUN}/artifacts/{export["artifact_id"]}?disposition=inline')
        self.assertEqual((response.status, sha(response.body)), (200, sha(FAKE_MOV)))
        self.assertTrue(response.headers['content-disposition'].startswith('inline;'))
        self.assertEqual(response.headers['content-type'], 'video/quicktime')
        markers = next(item for item in graph['evidence'] if item['kind'] == 'editor_marker_export')
        fcpxml = next(file for file in markers['files'] if file['name'] == 'Info.fcpxml')
        self.assertIs(fcpxml['import_verified'], False)
        body = self.request(f'/api/v1/runs/{RUN}/artifacts/{fcpxml["artifact_id"]}')
        self.assertEqual((body.status, sha(body.body)), (200, sha_file(self.fx.sidecar['payload'])))
        compact = next(item for item in graph['evidence'] if item['kind'] == 'marked_compact')
        self.assertEqual(compact['state'], 'current')
        self.assertEqual(sorted(graph['listening_acceptance']['accepted_file_sha256']),
                         sorted([self.fx.hashes['cleaned.wav'], sha(FAKE_MOV)]))


# --------------------------------------------------------------------------- 5. Selection

class Selection(ApiCase):
    fixture_options = {'bundle_times': ('2026-10-07T10:00:00+00:00', '2026-10-07T12:00:00+00:00'), 'invalid_bundle': True}

    def test_newest_current_bundle_and_alternatives(self):
        older, newer, invalid = self.fx.bundles
        layers = self.layers()
        self.assertEqual(layers['selected_evidence_id'], newer['evidence_id'])
        self.assertEqual(layers['alternatives'], [older['evidence_id']])
        graph = self.graph()
        self.assertIn(invalid['evidence_id'], [row['evidence_id'] for row in graph['invalidation']])
        chosen = self.layers(f'?evidence={older["evidence_id"]}')
        self.assertEqual(chosen['selected_evidence_id'], older['evidence_id'])
        self.assertEqual(chosen['alternatives'], [newer['evidence_id']])
        self.assert_code(self.request(f'/api/v1/runs/{RUN}/layers?evidence={invalid["evidence_id"]}'), {'evidence_invalidated'})
        self.assert_code(self.request(f'/api/v1/runs/{RUN}/layers?evidence=evd_{"0" * 32}'), {'unknown_evidence'})
        METRICS['selection'] = {'current_bundles': 2, 'invalidated_bundles': 1, 'alternatives': len(layers['alternatives'])}

    def test_layer_content_policy(self):
        layers = self.layers()
        timing = layers['layers']['phrase_timing']
        self.assertEqual(timing['status'], 'available')
        rows = timing['document']['files'][0]['document']['phrases']
        measured = [row for row in rows if row['status'] == 'measured']
        self.assertTrue(all(row['direction'] is None and row['direction_status'] == 'withheld_uncalibrated' for row in measured))
        self.assertNotIn('inputs', timing['document']['files'][0]['document'])
        self.assertNotIn('filter', layers['layers']['tone_ab']['document']['trial'])
        self.assertIsNone(layers['layers']['bpm']['value'])
        self.assertEqual(layers['layers']['bpm']['grid']['period_seconds'], 0.25)
        self.assertEqual(layers['spectrogram']['reference_lines'][0]['label'], 'theoretical C1 (instrument.json)')
        self.assertAlmostEqual(layers['spectrogram']['reference_lines'][0]['hz'], 32.703195663, places=6)
        self.assertEqual(layers['spectrogram']['claim'], 'visualisation only; no pitch, note or stem claim')
        self.assertEqual(sorted(layers['media']), ['excerpt-1-X.wav', 'excerpt-1-Y.wav'])


class SelectionSchemaOne(ApiCase):
    """phrase_timing schema 1 is refused as layer_schema_superseded; schema-2 synthetic rows keep their class."""

    fixture_options = {'timing_schema': 1}

    def test_schema_one_superseded(self):
        timing = self.layers()['layers']['phrase_timing']
        self.assertEqual((timing['status'], timing['reason']), ('unavailable', 'layer_schema_superseded'))


# --------------------------------------------------------------------------- 6. Capabilities

class Capabilities(ApiCase):
    def test_registry_projection(self):
        registry = json.loads((ROOT / 'program' / 'tools.json').read_text())
        pilot = json.loads((ROOT / 'program' / 'capabilities.json').read_text())['pilot_tools']
        caps = self.get_json('/api/v1/capabilities')
        names = [tool['name'] for tool in caps['tools']]
        self.assertEqual(names, [tool['name'] for tool in registry['tools']])
        self.assertEqual(caps['tool_count'], 42)
        with_capability = [tool for tool in caps['tools'] if tool['capability'] is not None]
        without = [tool for tool in caps['tools'] if tool['capability'] is None]
        self.assertEqual(sorted(tool['name'] for tool in with_capability), sorted(pilot))
        self.assertEqual(len(with_capability), 8)
        self.assertEqual(len(without), 34)
        self.assertTrue(all(tool['capability_reason'] == 'capability pilot covers 8 tools' for tool in without))
        unmapped = [tool['name'] for tool in caps['tools'] if tool['area'] == 'unmapped']
        self.assertEqual(unmapped, [])
        for tool in with_capability:
            self.assertEqual(tool['area_basis'], 'program/capabilities.json domain')
            self.assertIn('network', tool['capability']['effects'])
            self.assertIn('timeout_seconds', tool['capability']['resources'])
        self.assertEqual(len(caps['models']), 1)
        model = caps['models'][0]
        self.assertEqual((model['local_presence'], model['url_host'], model['registration']),
                         ('not_checked', 'raw.githubusercontent.com', 'registered_hash_bound'))
        self.assertEqual(model['gate_state'], {'value': None, 'reason': 'not recorded in program/models.json'})
        self.assertNotIn('https://', json.dumps(caps))
        METRICS['capabilities'] = {'tools': f'{len(names)}/42', 'pilot_with_metadata': f'{len(with_capability)}/8',
                                   'null_reason': f'{len(without)}/34', 'unmapped': len(unmapped),
                                   'models': f'{len(caps["models"])}/1'}

    def test_extra_model_fields_pass_through(self):
        program = Path(self._tmp.name) / 'program'
        shutil.copytree(ROOT / 'program', program)
        models = json.loads((program / 'models.json').read_text())
        entry = next(iter(models['models'].values()))
        entry.update(gate_state='gate_pending_root_review', lane='model_lanes', gate='TIN-5721', status='registered')
        (program / 'models.json').write_text(json.dumps(models))
        self.start(self.fx.api(program_root=program))
        model = self.get_json('/api/v1/capabilities')['models'][0]
        self.assertEqual(model['gate_state'], {'value': 'gate_pending_root_review', 'reason': 'recorded in program/models.json'})
        self.assertEqual((model['lane'], model['gate'], model['status']), ('model_lanes', 'TIN-5721', 'registered'))
        (program / 'tools.json').write_text('{"tools": [}')
        self.assert_code(self.request('/api/v1/capabilities'), {'registry_unreadable'})


# --------------------------------------------------------------------------- 2. NoHostPath (runs after the API classes)

class NoHostPath(ApiCase):
    def test_every_recorded_response_is_path_free(self):
        # Exercise all six routes in this case too, so the sweep is not order-dependent.
        self.request('/api/v1/runs')
        graph = self.graph()
        self.layers()
        self.request('/api/v1/capabilities')
        self.request(f'/api/v1/runs/{RUN}/layers/media/{self.fx.bundles[0]["evidence_id"]}/excerpt-1-X.wav')
        cleaned = next(node for node in graph['stages'] if node['stage'] == 'cleaned.wav')
        self.request(f'/api/v1/runs/{RUN}/artifacts/{cleaned["artifact_id"]}')
        self.request('/api/v1/runs/NOPE')
        # Mid-module sweep (classes load alphabetically, so later classes are covered by the
        # request-time assertion and by the final sweep in tearDownModule).
        self.assertEqual(sweep_recorded_responses('sweep_at_no_host_path'), [])


# --------------------------------------------------------------------------- 7. Policy (static)

OWNED_WEB = [
    WEB / 'src' / 'routes' / '+layout.svelte',
    WEB / 'src' / 'routes' / '+page.svelte',
    *sorted((WEB / 'src' / 'routes' / 'runs').rglob('*.*')),
    *sorted((WEB / 'src' / 'routes' / 'compare').rglob('*.*')),
    *sorted((WEB / 'src' / 'routes' / 'review').rglob('*.*')),
    *sorted((WEB / 'src' / 'routes' / 'download').rglob('*.*')),
    WEB / 'src' / 'routes' / 'jobs' / '+page.svelte',
    WEB / 'src' / 'routes' / 'jobs' / '+page.server.ts',
    *sorted((WEB / 'src' / 'routes' / 'tools').rglob('*.*')),
    *sorted((WEB / 'src' / 'routes' / 'api' / 'runs').rglob('*.*')),
    *sorted((WEB / 'src' / 'routes' / 'api' / 'capabilities').rglob('*.*')),
    WEB / 'src' / 'params' / 'runid.ts',
    *sorted((WEB / 'src' / 'lib' / 'components' / 'review').rglob('*.*')),
    *sorted((WEB / 'src' / 'lib' / 'server' / 'runs').rglob('*.*')),
]
REVIEW = WEB / 'src' / 'lib' / 'components' / 'review'
TEXT_FILES = [REVIEW / name for name in ('review-logic.ts', 'TimingTable.svelte', 'FlagsList.svelte', 'TimelineTracks.svelte',
                                         'CompactOverlay.svelte', 'ReviewWorkspace.svelte')]


def is_client(path):
    rel = path.relative_to(WEB / 'src').parts
    return 'server' not in rel and not path.name.endswith(('.server.ts', '.server.js')) and path.name != '+server.ts'


class Policy(unittest.TestCase):
    def test_no_autoplay_or_play_call(self):
        hits = []
        for path in OWNED_WEB:
            text = path.read_text()
            if re.search(r'autoplay', text, re.I):
                hits.append(f'{path.name}: autoplay')
            if re.search(r'\.play\s*\(', text):
                hits.append(f'{path.name}: .play(')
        METRICS['owned_web_files'] = len(OWNED_WEB)
        self.assertEqual(hits, [])

    def test_no_banned_words_in_timing_flag_phrase_text(self):
        hits = []
        for path in TEXT_FILES:
            text = path.read_text()
            for word in BANNED:
                if re.search(rf'(?<![A-Za-z_]){word}(?![A-Za-z_])', text, re.I):
                    hits.append(f'{path.name}: {word}')
        self.assertEqual(hits, [])

    def test_keyboard_bindings_and_guards(self):
        text = (REVIEW / 'review-logic.ts').read_text()
        block = text[text.index('export const KEY_BINDINGS'):text.index('];', text.index('export const KEY_BINDINGS'))]
        bindings = re.findall(r"\{ key: '([^']+)', shift: (true|false), action: '([a-z_]+)'", block)
        self.assertEqual(len(bindings), 12)
        expected = {('ArrowLeft', 'false'), ('ArrowRight', 'false'), ('[', 'false'), (']', 'false'), ('l', 'false'),
                    ('b', 'false'), ('i', 'false'), ('n', 'false'), ('p', 'false'), ('n', 'true'), ('p', 'true'),
                    ('u', 'false')}
        self.assertEqual({(key, shift) for key, shift, _ in bindings}, expected)
        self.assertIn("input,select,textarea", text)
        self.assertRegex(text, r'event\.altKey \|\| event\.ctrlKey \|\| event\.metaKey')
        workspace = (REVIEW / 'ReviewWorkspace.svelte').read_text()
        self.assertIn('onkeydown={onkey}', workspace)
        self.assertNotIn('svelte:window onkeydown', workspace)  # keys never bind globally
        METRICS['keyboard_bindings'] = f'{len(bindings)}/12'

    def test_labels_and_shapes(self):
        compare = (REVIEW / 'ABCompare.svelte').read_text()
        self.assertIn('operator_preference: <strong>not recorded</strong>', compare)
        text = (REVIEW / 'review-logic.ts').read_text()
        block = text[text.index('export const BASIS_STYLE'):text.index('} as const;', text.index('export const BASIS_STYLE'))]
        rows = re.findall(r"(\w+): \{ label: '([^']+)', shape: '(\w+)', text: '([^']+)'", block)
        self.assertEqual({row[0] for row in rows}, set(annotation_v2.BASES))
        self.assertEqual({row[0]: row[1] for row in rows}, annotation_v2.LABELS)
        self.assertEqual(len({row[2] for row in rows}), 4)
        self.assertEqual(len({row[1] for row in rows}), 4)
        self.assertEqual(dict((row[0], row[3]) for row in rows)['operator_assertion'], 'User report')
        self.assertEqual(dict((row[0], row[3]) for row in rows)['detector_hypothesis'], 'Review candidate')
        METRICS['bases_distinct'] = f'{len(rows)}/4'
        deliver = (WEB / 'src' / 'routes' / 'runs' / '[id=runid]' / 'deliver' / '+page.svelte').read_text()
        self.assertIn("'import unverified (no editor application proof)'", deliver)
        self.assertIn('data-import-unverified', deliver)
        self.assertIn('not exported or calibration_required', deliver)
        self.assertIn('lossy sharing derivative; low-register preservation not claimed', deliver)
        self.assertIn("'direction withheld (uncalibrated)'", text)
        self.assertIn('synthetic known-offset fixture', text)

    def test_stubs_replaced_and_client_imports(self):
        replaced = 0
        for slug in ('compare', 'review', 'download'):
            route = WEB / 'src' / 'routes' / slug
            text = '\n'.join(path.read_text() for path in route.rglob('*.*'))
            self.assertNotIn('PrototypeNotice', text)
            self.assertIn('redirect(303', (route / '+page.server.ts').read_text())
            replaced += 1
        METRICS['stubs_replaced'] = f'{replaced}/3'
        offenders = [str(path.relative_to(WEB)) for path in OWNED_WEB if is_client(path) and '$lib/server' in path.read_text()]
        self.assertEqual(offenders, [])

    def test_timing_and_keys_behaviour_in_node(self):
        """Measured: run review-logic.ts under node type stripping on synthetic rows and key events."""
        node = shutil.which('node')
        if node is None:
            self.skipTest('node not on PATH; behavioural check skipped (static checks above still ran)')
        script = r"""
const m = await import(process.argv[1]);
const real = {run_kind: 'real_take', phrases: [
  {phrase_id: 'a', status: 'measured', median_offset_ms: -12, median_offset_ms_delay_compensated: -14.2, iqr_ms_delay_compensated: [-18, -11], click_proximal_onset_count: 6, direction: null, direction_status: 'withheld_uncalibrated', span_source_seconds: [0.1, 0.5]},
  {phrase_id: 'b', status: 'measured', median_offset_ms: 3, click_proximal_onset_count: 5, direction: null, direction_status: 'withheld_uncalibrated', span_source_seconds: [0.5, 0.9]},
  {phrase_id: 'c', status: 'abstained', median_offset_ms: null, click_proximal_onset_count: 2, abstain_reason: 'fewer_than_4_click_proximal_onsets', span_source_seconds: [0.9, 1.0]}]};
const synthetic = {run_kind: 'synthetic_fixture', phrases: [{phrase_id: 's', status: 'measured', median_offset_ms: -9, click_proximal_onset_count: 6, direction: 'ahead_of_click', direction_status: 'synthetic_known_offset_fixture', span_source_seconds: [0, 1]}]};
const rows = m.timingRows(real);
const input = {matches: (s) => s.includes('input')};
const plain = {matches: () => false};
const ev = (key, extra = {}) => ({key, shiftKey: false, altKey: false, ctrlKey: false, metaKey: false, target: plain, ...extra});
const keys = m.KEY_BINDINGS.map((b) => m.keyAction(ev(b.key, {shiftKey: b.shift})) === b.action);
const guarded = [m.keyAction(ev('b', {target: input})), m.keyAction(ev('b', {altKey: true})), m.keyAction(ev('b', {ctrlKey: true})), m.keyAction(ev('b', {metaKey: true}))];
const flagLayer = {file: 'flags-triage.json', document: {schema_id: 'video-utils.flags-triage.s2', denominators: {shown: 1, total_flags: 2},
  shown: [{flag_id: 'f1', flag: {kind: 'automatic_recurrence_review_candidate', source_time_seconds: 0.3, end_seconds: 0.5}, window_id: 'grid_+00'}],
  hidden_navigation: [{flag_id: 'f0', flag: {kind: 'four_pulse_group_review_candidate', source_time_seconds: 0.1}}], suppressed: [],
  window_basis: {kind: 'click_grid_16_period_navigation_windows'}}};
const groups = m.flagGroups(flagLayer);
const flags = [groups.shown.length, groups.navigation.length, groups.denominators.total_flags, groups.windowBasis.kind, groups.navigation[0].note];
console.log(JSON.stringify({flags, real: rows.map((r) => [r.direction, r.median, r.measured]), synthetic: m.timingRows(synthetic).map((r) => r.direction), keys, guarded}));
"""
        proc = subprocess.run([node, '--experimental-strip-types', '--no-warnings', '--input-type=module', '-e', script,
                               str(REVIEW / 'review-logic.ts')], capture_output=True, text=True, timeout=60)
        if proc.returncode != 0 and 'strip-types' in proc.stderr:
            self.skipTest('node lacks type stripping; behavioural check skipped')
        self.assertEqual(proc.returncode, 0, proc.stderr[-2000:])
        result = json.loads(proc.stdout.strip().splitlines()[-1])
        real = result['real']
        measured = [row for row in real if row[2]]
        self.assertEqual(len(measured), 2)
        self.assertTrue(all(row[0] == 'direction withheld (uncalibrated)' for row in measured))
        self.assertEqual(real[2][:2], ['—', '—'])
        self.assertEqual(result['synthetic'], ['ahead of modelled click · synthetic known-offset fixture'])
        self.assertEqual(result['keys'], [True] * 12)
        self.assertEqual(result['guarded'], [None, None, None, None])
        self.assertEqual(result['flags'], [1, 1, 2, 'click_grid_16_period_navigation_windows',
                                           'navigation proxy; not a confirmed bar'])
        METRICS['timing_real_take_rows'] = {'measured': len(measured), 'withheld': len(measured), 'directions_on_real_take': 0,
                                            'abstained_shown_as_dash': 1}
        METRICS['keyboard_behaviour'] = {'bindings_dispatched': f'{sum(result["keys"])}/12', 'guards_held': '4/4'}


# --------------------------------------------------------------------------- 8. Registration

class Registration(unittest.TestCase):
    def setUp(self):
        if 'web_runs_api' not in (ROOT / 'scripts' / 'web_api.py').read_text():
            self.skipTest('root registration hunk not applied')

    def test_web_api_dispatches_runs_routes(self):
        with tempfile.TemporaryDirectory(prefix='routes-review-reg-') as base:
            fx = Fixture(Path(base))
            jobs = WebJobs(fx.R, Path(base) / 'state')
            jobs.start()
            server = web_api.WebAPIServer(jobs, 0)
            server.runs_api = fx.api()
            thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.05}, daemon=True)
            thread.start()
            try:
                port = server.server_address[1]

                def call(method, path, token=server.token, host=None):
                    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=30)
                    headers = {'Host': host or f'127.0.0.1:{port}'}
                    if token:
                        headers['Authorization'] = f'Bearer {token}'
                    conn.request(method, path, headers=headers)
                    reply = conn.getresponse()
                    body = reply.read()
                    conn.close()
                    return reply.status, body
                self.assertEqual(call('GET', '/api/v1/runs')[0], 200)
                self.assertEqual(call('GET', f'/api/v1/runs/{RUN}')[0], 200)
                self.assertEqual(call('GET', '/api/v1/capabilities')[0], 200)
                self.assertEqual(call('GET', '/api/v1/runs', token=None)[0], 401)
                self.assertEqual(call('GET', '/api/v1/runs', host='evil.example:1')[0], 403)
                self.assertEqual(call('POST', '/api/v1/runs')[0], 405)
            finally:
                server.stop()
                thread.join(timeout=10)
                jobs.close()


# --------------------------------------------------------------------------- 9. WebBuild

def _web_toolchain():
    import test_web_stack as ws  # helpers only; its classes are not collected here
    return ws


class WebBuild(unittest.TestCase):
    STATE = {}

    @classmethod
    def ensure(cls, case):
        ws = _web_toolchain()
        missing = ws._toolchain_missing()
        if missing:
            case.skipTest(missing)
        if 'lock' not in cls.STATE:
            cls.STATE['lock'] = (sha_file(WEB / 'pnpm-lock.yaml'), sha_file(WEB / 'package.json'))
        status, detail = ws._offline_install()
        if status == 'skip':
            case.skipTest(detail)
        if status == 'fail':
            case.fail(f'pnpm install --frozen-lockfile --offline failed:\n{detail}')
        return ws

    @classmethod
    def build(cls, case):
        ws = cls.ensure(case)
        if 'build' not in cls.STATE:
            started = time.monotonic()
            proc = ws._run(['pnpm', 'run', 'build'], BUILD_TIMEOUT_S)
            cls.STATE['build'] = (proc.returncode, (proc.stdout + proc.stderr)[-4000:], round(time.monotonic() - started, 1))
        code, output, _ = cls.STATE['build']
        if code != 0:
            case.fail(f'pnpm run build failed:\n{output}')
        return ws

    def test_check(self):
        ws = self.ensure(self)
        started = time.monotonic()
        proc = ws._run(['pnpm', 'run', 'check'], CHECK_TIMEOUT_S)
        output = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 0, output[-4000:])
        summary = re.findall(r'COMPLETED (\d+) FILES (\d+) ERRORS (\d+) WARNINGS', output)
        METRICS['pnpm_check'] = {'returncode': proc.returncode, 'summary': summary[-1] if summary else None,
                                 'seconds': round(time.monotonic() - started, 1)}

    def test_build_and_lock_unchanged(self):
        self.build(self)
        self.assertTrue((WEB / 'build' / 'index.js').is_file())
        METRICS['pnpm_build'] = {'returncode': self.STATE['build'][0], 'seconds': self.STATE['build'][2]}
        before = self.STATE['lock']
        after = (sha_file(WEB / 'pnpm-lock.yaml'), sha_file(WEB / 'package.json'))
        self.assertEqual(before, after)
        hits = []
        for path in (WEB / 'build' / 'client').rglob('*'):
            if path.is_file():
                text = path.read_bytes().decode('utf-8', errors='replace')
                for needle in ('VIDEO_UTILS_CONTROL_API_TOKEN', 'VIDEO_UTILS_CONTROL_API_URL', TOKEN):
                    if needle in text:
                        hits.append(f'{path.name}: {needle}')
        self.assertEqual(hits, [])
        METRICS['lock_package_unchanged'] = True


# --------------------------------------------------------------------------- 10. Walkthrough

class HunkHandler(web_api.Handler):
    """web_api.Handler._dispatch with the section 11.1 registration hunk applied (test-local)."""

    def _dispatch(self):
        self._consumed = False
        try:
            self._trusted()
            if self.server.shutting_down or self.server.jobs.closed:
                raise WebJobsError('shutting_down', 503, 'server is shutting down')
            parts = urlsplit(self.path)
            runs_route = web_runs_api.match(parts.path)
            if runs_route is not None:
                web_runs_api.serve(self, runs_route, parts.query)
                return
            name, identifier, methods, flavour = self._route(parts.path)
            if name is None:
                raise WebJobsError('route_not_found', 404, 'unknown route')
            action = methods.get(self.command)
            if action is None:
                raise WebJobsError('method_not_allowed', 405, 'method not allowed for this route')
            if parts.query and action not in web_api.LIST_ACTIONS:
                raise WebJobsError('bad_query', 400, 'this route accepts no query string')
            self._act(action, identifier, flavour, parts.query)
        except WebJobsError as error:
            self._safe_drain()
            self._safe_json(error.status, error.body())
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass
        except Exception:
            self._safe_drain()
            self._safe_json(500, {'status': 'error', 'code': 'internal_error', 'error': 'internal_error'})

    do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = _dispatch


def _headless_browser():
    cache = Path.home() / 'Library' / 'Caches' / 'ms-playwright'
    for candidate in sorted(cache.glob('chromium_headless_shell-*/chrome-headless-shell-*/chrome-headless-shell'), reverse=True):
        if os.access(candidate, os.X_OK):
            return candidate
    chrome = Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
    return chrome if os.access(chrome, os.X_OK) else None


class Walkthrough(unittest.TestCase):
    """Synthetic end-to-end: web_api (+hunk) in-process, built BFF as a test-owned child, one share_export job."""

    @classmethod
    def setUpClass(cls):
        import test_web_jobs as wj
        cls.skip_reason = None
        cls.app = cls.server = cls.jobs = cls._tmp = None
        if not wj.HAVE_FFMPEG:
            cls.skip_reason = wj.FFMPEG_SKIP
            return
        if shutil.which('node') is None or shutil.which('pnpm') is None:
            cls.skip_reason = 'node or pnpm not on PATH; walkthrough skipped (not a pass)'
            return
        cls._tmp = tempfile.TemporaryDirectory(prefix='routes-review-walk-')
        base = Path(cls._tmp.name).resolve()
        cls.fx = Fixture(base, clip=True)
        cls.jobs = WebJobs(cls.fx.R, base / 'T' / 'state')
        cls.jobs.start()
        cls.server = web_api.WebAPIServer(cls.jobs, 0)
        hunk = 'web_runs_api' in (ROOT / 'scripts' / 'web_api.py').read_text()
        if not hunk:
            cls.server.RequestHandlerClass = HunkHandler
        cls.registration = 'root_hunk' if hunk else 'test_local_subclass'
        cls.server.runs_api = cls.fx.api()
        cls.thread = threading.Thread(target=cls.server.serve_forever, kwargs={'poll_interval': 0.05}, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        try:
            if cls.app is not None:
                cls.app.close()
        finally:
            if cls.server is not None:
                cls.server.stop()
                cls.thread.join(timeout=10)
            if cls.jobs is not None:
                cls.jobs.close()
            if cls._tmp is not None:
                cls._tmp.cleanup()

    def control(self, method, path, body=None):
        port = self.server.server_address[1]
        conn = http.client.HTTPConnection('127.0.0.1', port, timeout=60)
        headers = {'Host': f'127.0.0.1:{port}', 'Authorization': f'Bearer {self.server.token}'}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers['Content-Type'] = 'application/json'
        conn.request(method, path, body=data, headers=headers)
        reply = conn.getresponse()
        payload = reply.read()
        conn.close()
        return reply.status, (json.loads(payload) if payload else None)

    def bff(self, method, path, body=None, timeout=90):
        conn = http.client.HTTPConnection('127.0.0.1', self.app.port, timeout=timeout)
        headers = {'accept': 'application/json, text/html'}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers.update({'content-type': 'application/json', 'origin': self.app.origin})
        try:
            conn.request(method, path, body=data, headers=headers)
            reply = conn.getresponse()
            payload = reply.read()
            out = {k.lower(): v for k, v in reply.getheaders()}
        finally:
            conn.close()
        for needle in self.fx.forbidden() + [self.server.token]:
            self.assertNotIn(needle.encode(), payload, f'{path} leaked {needle[:12]}…')
        return reply.status, out, payload

    def test_walkthrough(self):
        if self.skip_reason:
            self.skipTest(self.skip_reason)
        WebBuild.build(self)
        ws = _web_toolchain()
        steps, started = [], time.monotonic()
        # 1. admit the synthetic 2 s source (export/clip.mov of the run) and run one share_export job.
        status, source = self.control('POST', '/api/v1/sources', {'selector': f'{RUN}/export/clip.mov'})
        self.assertIn(status, (200, 201), source)
        source_id = source['source_artifact_id']
        status, job = self.control('POST', '/api/v1/jobs', {
            'tool': 'share_export', 'source_artifact_id': source_id, 'idempotency_key': 'routes-review-walk-0001',
            'parameters': {'height': 240, 'crf': 30, 'audio_kbps': 96, 'codec': 'h264', 'timeout_seconds': 120}})
        self.assertIn(status, (200, 201, 202), job)
        deadline = time.monotonic() + 120
        while True:
            status, job = self.control('GET', f'/api/v1/jobs/{job["job_id"]}')
            if job['state'] in web_jobs.TERMINAL:
                break
            self.assertLess(time.monotonic(), deadline, 'share_export job not terminal within 120 s')
            time.sleep(1.0)
        self.assertEqual(job['state'], 'succeeded', job.get('reason_code'))
        steps.append({'step': 'share_export_job', 'state': job['state'], 'wall_s': round(time.monotonic() - started, 1)})
        # 2. start the built BFF as a test-owned child.
        port = self.server.server_address[1]
        type(self).app = ws._App(f'http://127.0.0.1:{port}', token=self.server.token)
        # 3. fetch the routes.
        routes = [('/', 200, 'data-runs-entry'), ('/runs', 200, f'data-run-id="{RUN}"'),
                  (f'/runs/{RUN}', 200, 'data-run-graph'), (f'/runs/{RUN}/compare', 200, 'data-ab="true"'),
                  (f'/runs/{RUN}/review', 200, 'data-review-workspace'), (f'/runs/{RUN}/deliver', 200, 'data-deliverables'),
                  ('/jobs', 200, 'data-jobs-page'), ('/tools', 200, 'data-tools-page'),
                  ('/compare', (200, 303), f'/runs/{RUN}/compare'), ('/review', (200, 303), f'/runs/{RUN}/review'),
                  ('/download', (200, 303), f'/runs/{RUN}/deliver')]
        reached = []
        for path, expected, marker in routes:
            status, headers, payload = self.bff('GET', path)
            text = payload.decode('utf-8', errors='replace') + headers.get('location', '')
            ok = status in (expected if isinstance(expected, tuple) else (expected,)) and marker in text
            reached.append({'route': path, 'status': status, 'marker': marker, 'ok': ok})
            self.assertTrue(ok, f'{path}: {status} {marker!r} {text[:300]}')
        steps.append({'step': 'routes', 'reached': f'{sum(r["ok"] for r in reached)}/{len(routes)}', 'routes': reached})
        # With exactly one run the pickers redirect (303); remove the test-owned second run to exercise that path.
        shutil.rmtree(self.fx.runs / OTHER)
        redirects = []
        for path, target in (('/compare', 'compare'), ('/review', 'review'), ('/download', 'deliver')):
            status, headers, _ = self.bff('GET', path)
            redirects.append({'route': path, 'status': status, 'location': headers.get('location')})
            self.assertEqual((status, headers.get('location')), (303, f'/runs/{RUN}/{target}'))
        steps.append({'step': 'single_run_redirects', 'redirected': f'{len(redirects)}/3', 'routes': redirects})
        review_html = self.bff('GET', f'/runs/{RUN}/review')[2].decode()
        self.assertIn('Mark here', review_html)
        self.assertNotIn('data-mark-disabled', review_html)
        self.assertIn('shown 1 of 3 flags', review_html)
        self.assertIn('direction withheld (uncalibrated)', review_html)
        self.assertIn('phrase_duration', review_html)
        deliver_html = self.bff('GET', f'/runs/{RUN}/deliver')[2].decode()
        self.assertIn('import unverified (no editor application proof)', deliver_html)
        self.assertIn('data-deliverable="share-mp4"', deliver_html)
        # 4. one USER REPORTED Mark here write through the BFF, read back.
        status, _, payload = self.bff('GET', f'/api/sources/{source_id}/annotations')
        self.assertEqual(status, 200, payload[:300])
        read = json.loads(payload)
        revision = read['store']['revision']
        mark_time = round(read['clock']['source_start_seconds'] + 0.5, 3)
        request = {'schema_version': 2, 'expected_revision': revision, 'idempotency_key': 'browser-routes-review-0001',
                   'source_sha256': read['store']['source_sha256'], 'manifest_sha256': read['store']['manifest_sha256'],
                   'annotation': {'kind': 'phrase_duration', 'basis': 'operator_assertion', 'status': 'needs_review',
                                  'source_span': {'start_seconds': mark_time, 'end_seconds': mark_time, 'extent_known': False},
                                  'reported_by': {'actor': 'operator', 'via': 'browser'}, 'operator_certainty': 'uncertain',
                                  'operator_quote': 'synthetic walkthrough mark', 'note': 'Mark here (synthetic walkthrough)'}}
        status, _, payload = self.bff('POST', f'/api/sources/{source_id}/annotations', request)
        self.assertEqual(status, 200, payload[:300])
        written = json.loads(payload)
        status, _, payload = self.bff('GET', f'/api/sources/{source_id}/annotations')
        back = json.loads(payload)
        record = next(item for item in back['store']['annotations'] if item['id'] == written['mutation']['annotation_id'])
        self.assertEqual(record['claim_label'], 'USER REPORTED')
        self.assertEqual(back['store']['revision'], revision + 1)
        steps.append({'step': 'mark_here', 'claim_label': record['claim_label'], 'revision_delta': back['store']['revision'] - revision})
        # 5. downloads by ID, re-hashed.
        graph = json.loads(self.bff('GET', f'/api/runs/{RUN}')[2])
        cleaned = next(node for node in graph['stages'] if node['stage'] == 'cleaned.wav')
        status, headers, payload = self.bff('GET', f'/api/runs/{RUN}/artifacts/{cleaned["artifact_id"]}')
        self.assertEqual((status, sha(payload)), (200, self.fx.hashes['cleaned.wav']))
        self.assertEqual(headers['x-artifact-sha256'], sha(payload))
        layers = json.loads(self.bff('GET', f'/api/runs/{RUN}/layers')[2])
        media_name = 'excerpt-1-X.wav'
        media = layers['media'][media_name]
        status, headers, payload = self.bff('GET', f'/api/runs/{RUN}/layers/media/{media["evidence_id"]}/{media_name}')
        self.assertEqual((status, sha(payload)), (200, media['sha256']))
        self.assertEqual(headers['x-artifact-sha256'], media['sha256'])
        steps.append({'step': 'downloads', 'run_artifact_rehash': 'match', 'layer_media_rehash': 'match'})
        self.assertIn(source_id, [item['source_artifact_id'] for item in graph['admitted_sources']])
        self.assertTrue(next(item for item in graph['admitted_sources'] if item['source_artifact_id'] == source_id)['has_annotation_clock'])
        browser = self.browser_screens()
        receipt = {
            'schema': 'video-utils/routes-review-walkthrough', 'schema_version': 1, 'lane': 'routes_review',
            'sprint': '20261007-s3', 'tracker': 'TIN-5719',
            'ruling': 'R-HOOK-CONVERGENCE-20261004 (R-N11/R-N12/R-N13); TIN-3692 98cf680c-7299-4949-bfb2-60079053ad43',
            'recorded_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
            'fixture': 'synthetic: 1 s 32.7 Hz + 196 Hz PCM16 stage WAVs at 8 kHz; 2 s testsrc2 + 32.70 Hz sine clip; '
                       'in-test practice bundle, lowreg render, marker sidecar, marked-compact receipt',
            'real_take_touched': False, 'registration': self.registration,
            'claim_classes': {'M': 'measured on the synthetic fixture', 'B': 'browser check (muted, no listening)',
                              'U': 'not claimed'},
            'steps': steps, 'browser': browser,
            'not_claimed': ['listening acceptance', 'musical or note-level verdicts', 'default adoption',
                            'physical audio/video sync', 'FCPXML/Resolve import'],
            'wall_seconds': round(time.monotonic() - started, 1),
        }
        text = json.dumps(receipt, indent=2, sort_keys=True) + '\n'
        for needle in self.fx.forbidden():
            self.assertNotIn(needle, text)
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUT_DIR / 'walkthrough-latest.json').write_text(text)
        if os.environ.get('ROUTES_REVIEW_WRITE_RECEIPT') == '1':
            RECEIPT.parent.mkdir(parents=True, exist_ok=True)
            RECEIPT.write_text(text)
        METRICS['walkthrough'] = {'routes': steps[1]['reached'], 'mark_here': '1/1'}

    def browser_screens(self):
        browser = _headless_browser()
        if browser is None:
            return {'status': 'not_performed', 'reason': 'no local headless browser found'}
        shots = []
        for width, label in ((390, 'narrow-390'), (1280, 'desktop')):
            target = OUT_DIR / f'walkthrough-{label}.png'
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            profile = tempfile.mkdtemp(prefix='routes-review-chrome-')
            try:
                proc = subprocess.run([str(browser), '--headless=new', '--disable-gpu', '--no-first-run', '--mute-audio',
                                       f'--user-data-dir={profile}', f'--window-size={width},1800',
                                       f'--screenshot={target}', f'{self.app.origin}/runs/{RUN}/review'],
                                      capture_output=True, timeout=90, start_new_session=True)
                shots.append({'viewport': label, 'returncode': proc.returncode, 'written': target.is_file()})
            except subprocess.TimeoutExpired:
                shots.append({'viewport': label, 'returncode': None, 'written': False, 'reason': 'timeout'})
            finally:
                shutil.rmtree(profile, ignore_errors=True)
        return {'status': 'screenshots_only', 'screenshots': shots,
                'keys_and_players_paused': 'not_performed (no CDP automation in this lane); static keyboard checks only',
                'listening': 'not_performed'}


def sweep_recorded_responses(label):
    """Recheck every recorded response body, whatever its status, and record the tally by status class."""
    leaks, by_class = [], {}
    for path, status, body, forbidden in RESPONSES:
        key = f'{status // 100}xx'
        by_class[key] = by_class.get(key, 0) + 1
        for needle in forbidden:
            if needle.encode() in body:
                leaks.append((path, status, needle[:12]))
    METRICS[label] = {'responses': len(RESPONSES), 'checked': len(RESPONSES), 'excluded': 0,
                      'by_status_class': dict(sorted(by_class.items())), 'leaks': len(leaks)}
    METRICS['leaks'] = len(leaks)
    return leaks


def tearDownModule():
    leaks = sweep_recorded_responses('sweep_final')
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / 'test-metrics-latest.json').write_text(json.dumps(METRICS, indent=2, sort_keys=True, default=str) + '\n')
    if leaks:
        raise AssertionError(f'recorded responses leaked a host path or command string: {leaks[:5]}')


if __name__ == '__main__':
    unittest.main()
