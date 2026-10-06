#!/usr/bin/env python3
"""Compose a compact marked review movie by stream copy, with exact identity checks.

RUN_DIR is a verified restoration run (the audio branch). PREVIEW_DIR is a
verified arrangement-marker ``marked_video.py`` preview (the picture branch).
Both parents are read only. The coded picture packets of the preview and the
AAC packets of RUN_DIR's verified export are copied into a fresh MOV; no audio
DSP, normalization or picture encode occurs. Packet payloads, rational clocks,
AAC priming/padding, decoded AAC PCM and decoder configuration are verified to
be identical to their respective parents, and every parent file hash is
rechecked after composition.

Listening acceptance is never inferred. The operator's 2026-10-06 FULLER-v1
acceptance label is carried only when RUN_DIR is the identical accepted chain
with byte-identical audio; every other case records ``not_performed``.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import signal
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
import arrangement_markers  # noqa: E402  (same module object marked_video uses)

_spec = importlib.util.spec_from_file_location('_marked_compact_runner', SCRIPTS / 'apply_capture_profile.py')
runner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(runner)
media = runner.media

MAX_JSON = 20_000_000
MAX_PACKETS = 120_000
MAX_PROTECTED_FILES = 256
DEFAULT_TIMEOUT = 600
STATUS_OK = 'marked_compact_composition_verified'
STATUS_FAILED = 'marked_compact_failed_preserving_parents'
OUTPUT_NAME = 'marked-compact.mov'
AUTHORITY = 'R-HOOK-CONVERGENCE-20261004 / R-N11 / R-N13; S2 lane fuller_profile (TIN-5600)'
REASONS = ('run_dir_invalid', 'export_unverified', 'preview_unverified', 'arrangement_markers_mismatch',
           'source_mismatch', 'native_pcm_mismatch', 'nonzero_origin_unsupported',
           'audio_does_not_cover_picture', 'output_invalid', 'input_changed', 'packet_identity_failed',
           'pcm_identity_failed', 'format_identity_failed', 'deadline_exceeded', 'ffmpeg_failed',
           'internal_error')

# --- Accepted FULLER-v1 identity (docs/spec/sprints/FULLER_S2.md section 2) ---
ACCEPTED_LABEL = 'accepted_fuller_v1_by_operator_2026-10-06'
NOT_PERFORMED = 'not_performed'
ACCEPTED = {
    'run_id': '20261006T041633Z-990aa1bd6737',
    'source_sha256': 'a522115f4e72e19384fb341bc84369728eceefe49183b8c6367a1008a95176c6',
    'capture_samples': [180810, 218295],
    'pcm': {'sample_rate': 44100, 'channels': 1, 'sample_count': 6657385},
    'delay_samples': 1102,
    'ffmpeg_version': 'ffmpeg version 8.1.2 Copyright (c) 2000-2026 the FFmpeg developers',
    'cleaned_sha256': '9ed50aeca1345204959f1f72acc368a42045b568542150971a68119056cb2009',
    'export_video_sha256': '91b2f436abebf9dd8403791b18dd9b51410e25d25648c71febc27ed269a04a82',
    'loudnorm_command_count': 6,
    'acceptance_receipt': 'docs/agent-notes/2026-10-06-fuller-listening-acceptance.json',
    'acceptance_receipt_sha256': '0f8d3dbff43e8f8c2bdaed94856d697b94f3de9cf78cf5f72a0e6ee982578e92',
    'L': 'afftdn=nr=8.0:nf=-40.0:tn=0:gs=0:ad=0',
    'C': ("[0:a]asplit=2[noise][body];[noise]atrim=start_sample=180810:end_sample=218295,"
          "asetpts=N/SR/TB,apad=pad_len=4410[training];[body]asetpts=N/SR/TB[take];"
          "[training][take]concat=n=2:v=0:a=1,apad=pad_len=1102,"
          "asendcmd=c='0 afftdn sn start;0.85 afftdn sn stop',afftdn=nr=8.0:nf=-40.0:tn=0:gs=0:ad=0,"
          "atrim=start_sample=42997:end_sample=6700382,asetpts=N/SR/TB[out]"),
    'P': ("equalizer=f=160:t=q:w=0.7:g=2:b=0:r=f64,equalizer=f=300:t=q:w=0.8:g=1:b=0:r=f64,"
          "acompressor=threshold=0.125892541179:ratio=2:attack=15:release=100:knee=1.41253754462:"
          "makeup=1:level_in=1:mode=downward:link=maximum:detection=rms:mix=0.25"),
    'N': 'loudnorm=I=-18.0:TP=-1.75:LRA=50',
}

EXPORT_TRUE = ('source_hash_verified', 'video_frame_count_preserved', 'relative_audio_video_start_verified',
               'dsp_latency_compensation_recorded', 'final_true_peak_within_target')
PREVIEW_TRUE = ('decoded_video_frame_pts_preserved', 'decoded_video_last_extent_preserved',
                'picture_geometry_preserved', 'aac_packet_payloads_timing_and_padding_preserved',
                'decoded_audio_pcm_sha256_preserved')
PICTURE_FORMAT_KEYS = ('width', 'height', 'sample_aspect_ratio', 'display_aspect_ratio', 'codec_name',
                       'codec_tag_string', 'extradata_size', 'profile', 'level', 'pix_fmt', 'field_order',
                       'color_range', 'color_space', 'color_transfer', 'color_primaries',
                       'chroma_location', 'side_data_list')
AUDIO_FORMAT_KEYS = ('codec_name', 'profile', 'sample_rate', 'channels', 'channel_layout', 'extradata_size')
BINDING_KEYS = ('source_sha256', 'analyzed_input_sha256', 'manifest_sha256', 'assessment', 'reference',
                'producer_sha256', 'reference_validator_sha256', 'tempo')


class CompactError(ValueError):
    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


def require(condition, message, code):
    if not condition:
        raise CompactError(message, code)


def sha256(path, deadline=None):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for index, chunk in enumerate(iter(lambda: handle.read(1024 * 1024), b'')):
            digest.update(chunk)
            if deadline is not None and index % 256 == 255:
                deadline.check()
    return digest.hexdigest()


def is_sha256(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def no_symlink(path):
    path = Path(path)
    return not any(part.is_symlink() for part in (path, *path.parents))


def read_json(path, code):
    """Bounded, duplicate-key and non-finite rejecting JSON object reader."""
    path = Path(path)
    require(path.is_file() and no_symlink(path), f'JSON missing or aliased: {path}', code)
    require(path.stat().st_size <= MAX_JSON, f'JSON exceeds byte bound: {path}', code)
    raw = path.read_bytes()
    require(len(raw) <= MAX_JSON, f'JSON grew beyond byte bound: {path}', code)

    def pairs(rows):
        result = {}
        for key, value in rows:
            require(key not in result, f'Duplicate JSON key in {path}', code)
            result[key] = value
        return result

    def reject(value):
        raise CompactError(f'Non-finite JSON in {path}', code)

    try:
        payload = json.loads(raw, object_pairs_hook=pairs, parse_constant=reject)
    except (ValueError, RecursionError) as exc:
        if isinstance(exc, CompactError):
            raise
        raise CompactError(f'Invalid JSON {path}: {exc}', code) from exc
    require(isinstance(payload, dict), f'Expected JSON object: {path}', code)
    return payload, hashlib.sha256(raw).hexdigest()


def write_json(path, value):
    raw = json.dumps(value, sort_keys=True, indent=2, allow_nan=False, default=str) + '\n'
    with Path(path).open('x') as handle:
        handle.write(raw)


# --- FULLER-v1 chain identity -------------------------------------------------

def capture_template(start, end, sample_count, rate, delay, latency_filter=ACCEPTED['L']):
    """T(s, e, n, r, d): the accepted capture graph C with only the binding substituted.

    Guard g = ceil(r/10), stop (e-s)/r formatted .12g and the final trim
    [(e-s)+g+d, (e-s)+g+d+n) follow FULLER_S2.md section 2.
    """
    for name, value in (('start', start), ('end', end), ('sample_count', sample_count),
                        ('rate', rate), ('delay', delay)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f'{name} must be an integer')
    if not (0 <= start < end and sample_count > 0 and rate > 0 and delay >= 0):
        raise ValueError('capture template binding out of range')
    training = end - start
    guard = math.ceil(rate / 10)
    prefix = training + guard
    stop = training / rate
    return (f"[0:a]asplit=2[noise][body];[noise]atrim=start_sample={start}:end_sample={end},"
            f"asetpts=N/SR/TB,apad=pad_len={guard}[training];[body]asetpts=N/SR/TB[take];"
            f"[training][take]concat=n=2:v=0:a=1,apad=pad_len={delay},"
            f"asendcmd=c='0 afftdn sn start;{stop:.12g} afftdn sn stop',{latency_filter},"
            f"atrim=start_sample={prefix + delay}:end_sample={prefix + delay + sample_count},"
            f"asetpts=N/SR/TB[out]")


def loudnorm_prefix(value):
    return ':'.join(value.split(':')[:3])


def extract_chain(manifest):
    """Read L, C, P and the N prefixes from a media.py manifest command record."""
    commands = manifest.get('commands') if isinstance(manifest, dict) else None
    simple, complex_graphs = [], []
    for command in commands if isinstance(commands, list) else []:
        if not isinstance(command, list):
            continue
        for index, argument in enumerate(command[:-1]):
            value = command[index + 1]
            if argument == '-af' and isinstance(value, str):
                simple.append(value)
            elif argument == '-filter_complex' and isinstance(value, str):
                complex_graphs.append(value)
    latency = [value for value in simple if value.startswith('afftdn=')]
    capture = [value for value in complex_graphs if value.startswith('[0:a]asplit=2[noise][body];')]
    post = [value for value in simple if value.startswith(('equalizer=', 'acompressor='))]
    loudnorm = [value for value in simple if value.startswith('loudnorm=')]
    return {'L': latency[0] if len(latency) == 1 else None, 'L_count': len(latency),
            'C': capture[0] if len(capture) == 1 else None, 'C_count': len(capture),
            'P': post[0] if len(post) == 1 else None, 'P_count': len(post),
            'N_prefixes': sorted(set(loudnorm_prefix(value) for value in loudnorm)),
            'N_count': len(loudnorm)}


def _int(value):
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def chain_identity(manifest, cleaned_sha256=None, export_video_sha256=None):
    """Classify the audio branch and derive the only permitted listening label."""
    chain = extract_chain(manifest)
    capture = manifest.get('noise_capture') if isinstance(manifest.get('noise_capture'), dict) else {}
    pcm = manifest.get('pcm') if isinstance(manifest.get('pcm'), dict) else {}
    samples = capture.get('selected_samples')
    native = {key: pcm.get(key) for key in ('sample_rate', 'channels', 'sample_count')}
    delay = _int(capture.get('filter_delay_samples_removed'))
    tools = manifest.get('tools') if isinstance(manifest.get('tools'), dict) else {}
    source = (manifest.get('source') or {}).get('sha256') if isinstance(manifest.get('source'), dict) else None
    checks = {'L_equal': chain['L'] == ACCEPTED['L'],
              'P_equal': chain['P'] == ACCEPTED['P'],
              'N_prefix_equal': chain['N_count'] > 0 and chain['N_prefixes'] == [ACCEPTED['N']],
              'N_command_count_equal': chain['N_count'] == ACCEPTED['loudnorm_command_count'],
              'C_equal': chain['C'] == ACCEPTED['C'],
              'source_equal': source == ACCEPTED['source_sha256'],
              'capture_samples_equal': samples == ACCEPTED['capture_samples'],
              'native_pcm_equal': native == ACCEPTED['pcm'],
              'ffmpeg_version_equal': tools.get('ffmpeg') == ACCEPTED['ffmpeg_version']}
    template = None
    if (isinstance(samples, list) and len(samples) == 2 and all(_int(x) is not None for x in samples)
            and _int(native['sample_count']) and _int(native['sample_rate']) and delay is not None):
        try:
            template = capture_template(samples[0], samples[1], native['sample_count'],
                                        native['sample_rate'], delay)
        except ValueError:
            template = None
    checks['C_matches_template_at_binding'] = template is not None and chain['C'] == template
    common = checks['L_equal'] and checks['P_equal'] and checks['N_prefix_equal']
    if common and all(checks[key] for key in ('N_command_count_equal', 'C_equal', 'source_equal',
                                               'capture_samples_equal', 'native_pcm_equal',
                                               'ffmpeg_version_equal')):
        chain_class = 'identical_accepted_fuller_v1'
    elif common and checks['C_matches_template_at_binding']:
        chain_class = 'fuller_v1_template_other_binding'
    else:
        chain_class = 'not_fuller_v1'
    label, audio, export = NOT_PERFORMED, 'not_compared', 'not_compared'
    if chain_class == 'identical_accepted_fuller_v1':
        if cleaned_sha256 is None:
            reason = 'accepted_audio_bytes_not_compared'
        elif cleaned_sha256 != ACCEPTED['cleaned_sha256']:
            audio, reason = 'differs', 'chain_identical_audio_differs'
        else:
            audio = 'byte_identical'
            if export_video_sha256 is not None:
                export = 'byte_identical' if export_video_sha256 == ACCEPTED['export_video_sha256'] else 'differs'
            if export == 'differs':
                reason = 'chain_identical_export_differs'
            else:
                label, reason = ACCEPTED_LABEL, 'identical_chain_and_byte_identical_audio'
    elif chain_class == 'fuller_v1_template_other_binding':
        reason = 'fuller_template_other_take_or_interval_not_listened'
    else:
        reason = 'not_fuller_v1_chain'
    return {'chain_class': chain_class, 'listening_acceptance': label,
            'listening_acceptance_reason': reason, 'accepted_audio_identity': audio,
            'accepted_export_identity': export, 'checks': checks,
            'observed': {'capture_samples': samples, 'native_pcm': native, 'delay_samples': delay,
                         'ffmpeg_version': tools.get('ffmpeg'), 'source_sha256': source,
                         'loudnorm_command_count': chain['N_count'],
                         'cleaned_sha256': cleaned_sha256, 'export_video_sha256': export_video_sha256},
            'acceptance_receipt': ACCEPTED['acceptance_receipt'],
            'acceptance_scope': 'Operator QuickTime feedback on the exact accepted FULLER audio only; '
                                'no sync, analysis accuracy, master adoption or other-take claim.'}


# --- Section 5 explicit unknown/abstain fields -------------------------------

def claim_fields(markers_analysis=None, identity=None):
    fields = {'capture_noise_only_verified': False, 'capture_music_status': 'unknown',
              'capture_click_status': 'unknown', 'physical_audio_video_sync_verified': False,
              'fundamental_32hz_restoration_claimed': False, 'per_passage_level_matched': False,
              'composite_visual_review_performed': False, 'composite_listening_review': NOT_PERFORMED,
              'markers_are_analysis_of_audio_branch': markers_analysis,
              'performance_issue_confirmed': False, 'note_correctness_assessed': False,
              'master_adopted': False, 'latest_promoted': False, 'default_profile_changed_by_lane': False,
              'native_editor_import_verified': False,
              'listening_acceptance': identity['listening_acceptance'] if identity else NOT_PERFORMED,
              'accepted_audio_identity': identity['accepted_audio_identity'] if identity else 'not_compared',
              'tone_suitability_other_takes': 'unknown'}
    if markers_analysis is None:
        fields['markers_are_analysis_of_audio_branch_reason'] = 'not_evaluated_before_failure'
    if identity is None:
        fields['listening_acceptance_reason'] = 'chain_identity_not_evaluated_before_failure'
    return fields


# --- Packet identity ----------------------------------------------------------

def exact_packets(before, after, before_time_base, after_time_base, *, audio=False):
    """Zero-tolerance ordered payload, rational clock and (AAC) side-data identity."""
    require(isinstance(before, list) and isinstance(after, list) and len(before) == len(after) and before,
            f'copied packet count differs: {len(before or [])} -> {len(after or [])}', 'packet_identity_failed')
    old_tick, new_tick = Fraction(before_time_base), Fraction(after_time_base)
    for index, (old, new) in enumerate(zip(before, after)):
        require(old.get('data_hash') is not None and old.get('data_hash') == new.get('data_hash'),
                f'packet {index} payload differs', 'packet_identity_failed')
        if audio:
            require(old.get('side_data_list') == new.get('side_data_list'),
                    f'AAC packet {index} priming/padding side data differs', 'packet_identity_failed')
        for key in ('pts', 'dts', 'duration'):
            require(_int_like(old.get(key)) and _int_like(new.get(key))
                    and int(old[key]) * old_tick == int(new[key]) * new_tick,
                    f'packet {index} rational {key} differs', 'packet_identity_failed')
    return len(before)


def _number_text(value):
    try:
        return isinstance(value, str) and math.isfinite(float(value))
    except ValueError:
        return False


def _int_like(value):
    if isinstance(value, bool) or value is None:
        return False
    try:
        int(value)
    except (TypeError, ValueError):
        return False
    return True


# --- Branch gate (pure; file identity checked separately) ---------------------

def _zero(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return False
    try:
        return Fraction(str(value)) == 0
    except (ValueError, ZeroDivisionError):
        return False


def _native(manifest):
    pcm = manifest.get('pcm') if isinstance(manifest.get('pcm'), dict) else {}
    return {key: pcm.get(key) for key in ('sample_rate', 'channels', 'sample_count')}


def branch_gate(run_manifest, export, preview, preview_manifest, selector):
    """Generalized compact assembly gate; nothing about the accepted take is hard-coded."""
    verification = export.get('verification') if isinstance(export.get('verification'), dict) else {}
    for key in EXPORT_TRUE:
        require(verification.get(key) is True, f'audio export proof missing: {key}', 'export_unverified')
    translation = verification.get('video_packet_expected_translation_seconds')
    require(_zero(translation) and not isinstance(translation, str),
            'audio export packet translation must be exactly 0', 'export_unverified')
    require(verification.get('physical_audio_video_sync_verified') is False,
            'audio export sync scope differs', 'export_unverified')
    require(preview.get('status') == 'marked_review_preview_verified_unreviewed',
            'picture preview is not a verified terminal preview', 'preview_unverified')
    require(preview.get('marker_mode') == 'arrangement_reference_review',
            'picture preview is not an arrangement-reference branch', 'preview_unverified')
    proof = preview.get('verification') if isinstance(preview.get('verification'), dict) else {}
    for key in PREVIEW_TRUE:
        require(proof.get(key) is True, f'picture preview proof missing: {key}', 'preview_unverified')
    require(proof.get('physical_audio_video_sync_verified') is False, 'preview sync scope differs', 'preview_unverified')
    frames = proof.get('decoded_video_frame_count')
    extent = proof.get('decoded_video_last_extent_seconds')
    require(_int(frames) is not None and frames > 0 and isinstance(extent, (int, float))
            and not isinstance(extent, bool) and math.isfinite(extent) and extent > 0,
            'picture frame count or extent missing', 'preview_unverified')
    require(isinstance(selector, str) and preview.get('arrangement_marker_selector') == selector,
            'arrangement marker selector differs from the preview outcome', 'arrangement_markers_mismatch')
    bindings = preview.get('arrangement_marker_bindings')
    require(isinstance(bindings, dict) and all(key in bindings for key in BINDING_KEYS),
            'preview arrangement bindings missing', 'preview_unverified')
    shas = [(run_manifest.get('source') or {}).get('sha256'), export.get('source_sha256'),
            preview.get('source_sha256'), (preview_manifest.get('source') or {}).get('sha256'),
            bindings.get('source_sha256')]
    require(all(is_sha256(value) for value in shas) and len(set(shas)) == 1,
            'audio and picture branches do not share one original source SHA-256', 'source_mismatch')
    audio_native, picture_native = _native(run_manifest), _native(preview_manifest)
    require(all(_int(value) and value > 0 for value in audio_native.values()) and audio_native == picture_native,
            f'native PCM differs: {audio_native} vs {picture_native}', 'native_pcm_mismatch')
    for name, manifest in (('audio', run_manifest), ('picture', preview_manifest)):
        timeline = manifest.get('timeline') if isinstance(manifest.get('timeline'), dict) else {}
        require(_zero(timeline.get('audio_start_seconds')) and _zero(timeline.get('format_start_seconds')),
                f'{name} branch source origin is not 0 (v1 supports origin 0 only)', 'nonzero_origin_unsupported')
        require(timeline.get('no_time_stretch') is True, f'{name} branch lacks no-time-stretch mapping',
                'nonzero_origin_unsupported')
    require(_zero(preview.get('source_container_start_seconds')) and _zero(proof.get('decoded_video_first_pts_seconds')),
            'picture origin is not 0', 'nonzero_origin_unsupported')
    return {'source_sha256': shas[0], 'native_pcm': audio_native, 'picture_frame_count': frames,
            'picture_extent': Fraction(str(extent))}


# --- Output path --------------------------------------------------------------

def default_output():
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    return ROOT / 'artifacts' / 'experiments' / f'marked-compact-{stamp}-{uuid.uuid4().hex[:12]}'


def output_directory(value, parents):
    """Fresh directory beneath ROOT/artifacts, not artifacts/runs, not inside a parent."""
    raw = str(value)
    require(raw and '\0' not in raw and '..' not in Path(raw).parts, 'output path traversal prohibited', 'output_invalid')
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    base = ROOT / 'artifacts'
    require(path.is_relative_to(base) and path != base, 'output must be beneath repository artifacts/', 'output_invalid')
    require(not path.is_relative_to(base / 'runs'), 'output must not be beneath artifacts/runs', 'output_invalid')
    current = ROOT
    for part in path.relative_to(ROOT).parts:
        current = current / part
        require(not current.is_symlink(), f'symlink output component prohibited: {current}', 'output_invalid')
    require(not path.exists(), 'output directory must be fresh', 'output_invalid')
    resolved = path.resolve()
    for parent in parents:
        parent = Path(parent).absolute()
        for candidate in {parent, parent.resolve()}:
            require(not resolved.is_relative_to(candidate) and not candidate.is_relative_to(resolved),
                    'output must not be inside (or contain) a parent branch', 'output_invalid')
    return path


# --- Owned media subprocesses -------------------------------------------------

class Session:
    def __init__(self, deadline):
        self.deadline = deadline
        self.events = []

    def run(self, command, timeout=120):
        return runner.run_owned(command, deadline=self.deadline,
                                timeout=min(timeout, self.deadline.remaining()), events=self.events)

    def json(self, command, timeout=120):
        try:
            return json.loads(self.run(command, timeout).stdout)
        except json.JSONDecodeError as exc:
            raise CompactError(f'ffprobe returned invalid JSON: {exc}', 'ffmpeg_failed') from exc


def probe(session, path):
    data = session.json([media.executable('ffprobe'), '-v', 'error', '-threads', '2', '-show_format',
                         '-show_streams', '-show_data_hash', 'sha256', '-of', 'json', str(path)], 60)
    streams = data.get('streams', [])
    videos = [row for row in streams if row.get('codec_type') == 'video'
              and not (row.get('disposition') or {}).get('attached_pic')]
    audios = [row for row in streams if row.get('codec_type') == 'audio']
    require(videos and audios, f'{Path(path).name} lacks a picture or audio stream', 'format_identity_failed')
    return {'probe': data, 'video': videos[0], 'audio': audios[0], 'video_count': len(videos),
            'audio_count': len(audios)}


def audio_packets(session, path, index):
    fields = ('packet=pts,dts,duration,data_hash,side_data_list:'
              'packet_side_data=side_data_type,skip_samples,discard_padding')
    rows = session.json([media.executable('ffprobe'), '-v', 'error', '-threads', '2', '-select_streams',
                         str(index), '-show_packets', '-show_entries', fields, '-show_data_hash', 'sha256',
                         '-of', 'json', str(path)]).get('packets')
    require(isinstance(rows, list) and 0 < len(rows) <= MAX_PACKETS, 'AAC packet table outside bounds',
            'packet_identity_failed')
    return rows


def decoded_pcm_hash(session, path):
    value = session.run([media.executable('ffmpeg'), '-hide_banner', '-nostdin', '-loglevel', 'error',
                         '-threads', '2', '-i', str(path), '-map', '0:a:0', '-vn', '-c:a', 'pcm_f32le',
                         '-f', 'hash', '-hash', 'sha256', '-'], 300).stdout.strip()
    require(value.startswith('SHA256=') and len(value) == 71, 'decoded AAC PCM hash unavailable', 'pcm_identity_failed')
    return value


# --- File identity ------------------------------------------------------------

def _top_level_files(directory):
    directory = Path(directory)
    if not directory.is_dir():
        return []
    files = sorted(path for path in directory.iterdir() if path.is_file() and not path.is_symlink())
    require(len(files) <= MAX_PROTECTED_FILES, 'too many parent files to protect', 'run_dir_invalid')
    return files


def verify_identities(identities, deadline, code='input_changed'):
    for name, expected in identities.items():
        path = Path(name)
        require(path.is_file() and no_symlink(path), f'protected input missing or aliased: {name}', code)
        require(sha256(path, deadline) == expected, f'protected input changed: {name}', code)


def parent_identities(run_dir, preview_dir, preview, marker_identities, deadline):
    """Hash every parent file the composition depends on; verify recorded hashes."""
    identities = {}
    for path in [*_top_level_files(run_dir), *_top_level_files(run_dir / 'export')]:
        identities[str(path)] = sha256(path, deadline)
    recorded = preview.get('output_sha256') if isinstance(preview.get('output_sha256'), dict) else {}
    for name in ('marked-video.mov', 'selection.json', 'callouts.ass'):
        path = preview_dir / name
        require(path.is_file() and no_symlink(path) and is_sha256(recorded.get(name))
                and sha256(path, deadline) == recorded[name],
                f'picture preview output differs from its outcome: {name}', 'preview_unverified')
        identities[str(path)] = recorded[name]
    identities[str(preview_dir / 'outcome.json')] = sha256(preview_dir / 'outcome.json', deadline)
    inputs = preview.get('input_sha256')
    require(isinstance(inputs, dict) and inputs, 'picture preview input identities missing', 'preview_unverified')
    for name, expected in inputs.items():
        path = Path(name)
        require(is_sha256(expected) and path.is_file() and no_symlink(path)
                and sha256(path, deadline) == expected,
                f'picture preview input changed since render: {name}', 'preview_unverified')
        identities[str(path)] = expected
    for path, expected in marker_identities.items():
        identities.setdefault(str(path), expected)
    latest = ROOT / 'artifacts' / 'latest.json'
    if latest.is_file() and not latest.is_symlink():
        identities[str(latest)] = sha256(latest, deadline)
    return identities


# --- Composition --------------------------------------------------------------

def _validated_markers(preview_run, selector, bindings):
    try:
        saved, tracked = arrangement_markers.load_validated(preview_run, selector)
    except (ValueError, KeyError, TypeError, OSError, RecursionError) as exc:
        raise CompactError(f'arrangement markers failed revalidation: {exc}', 'arrangement_markers_mismatch') from exc
    rebuilt = {key: saved.get(key) for key in BINDING_KEYS}
    require(rebuilt == {key: bindings.get(key) for key in BINDING_KEYS},
            'revalidated arrangement markers differ from the preview bindings', 'arrangement_markers_mismatch')
    return {Path(path): value for path, value in tracked.items()}


def compose(run_dir, preview_dir, selector, output=None, timeout_seconds=DEFAULT_TIMEOUT):
    started = time.monotonic()
    deadline = runner.Deadline(timeout_seconds)
    run_dir, preview_dir = Path(run_dir).absolute(), Path(preview_dir).absolute()
    output = output_directory(output if output is not None else default_output(), (run_dir, preview_dir))
    output.mkdir(parents=True, mode=0o700)
    os.chmod(output, 0o700)
    session = Session(deadline)
    state = {'schema_version': 1, 'tool': 'marked_compact', 'status': 'running', 'authority': AUTHORITY,
             'created_utc': datetime.now(timezone.utc).isoformat(), 'run_dir': str(run_dir),
             'picture_preview': str(preview_dir), 'arrangement_marker_selector': selector,
             'output_dir': str(output), 'timeout_seconds': timeout_seconds, 'threads': 2,
             'controller_sha256': sha256(Path(__file__)), 'runner_sha256': sha256(SCRIPTS / 'apply_capture_profile.py'),
             'media_sha256': sha256(SCRIPTS / 'media.py'), 'new_audio_dsp': False, 'picture_reencoded': False,
             'normalization_applied': False, 'retries': 0}
    write_json(output / 'start.json', state)
    identities = {}
    markers_analysis, identity = None, None
    try:
        require(run_dir.is_dir() and no_symlink(run_dir), 'RUN_DIR missing or aliased', 'run_dir_invalid')
        run_manifest, run_manifest_sha = read_json(run_dir / 'manifest.json', 'run_dir_invalid')
        export, export_sha = read_json(run_dir / 'export' / 'outcome.json', 'run_dir_invalid')
        require(preview_dir.is_dir() and no_symlink(preview_dir), 'PREVIEW_DIR missing or aliased', 'preview_unverified')
        preview, preview_sha = read_json(preview_dir / 'outcome.json', 'preview_unverified')
        preview_run = Path(str(preview.get('run_dir', ''))).absolute()
        require(preview_run.is_dir() and no_symlink(preview_run), 'preview run directory missing', 'preview_unverified')
        preview_manifest, preview_manifest_sha = read_json(preview_run / 'manifest.json', 'preview_unverified')
        gate = branch_gate(run_manifest, export, preview, preview_manifest, selector)
        marker_identities = _validated_markers(preview_run, selector, preview['arrangement_marker_bindings'])
        audio = run_dir / 'export' / 'cleaned-video.mov'
        recorded_audio = (export.get('output_sha256') or {}).get('cleaned-video.mov')
        require(Path(str(export.get('video', ''))) == audio and is_sha256(recorded_audio),
                'audio export receipt does not name RUN_DIR/export/cleaned-video.mov', 'export_unverified')
        require(audio.is_file() and no_symlink(audio) and sha256(audio, deadline) == recorded_audio,
                'audio export video differs from its outcome receipt', 'export_unverified')
        cleaned = run_dir / 'cleaned.wav'
        recorded_cleaned = (run_manifest.get('output_sha256') or {}).get('cleaned.wav')
        require(cleaned.is_file() and is_sha256(recorded_cleaned) and sha256(cleaned, deadline) == recorded_cleaned,
                'RUN_DIR cleaned.wav differs from its manifest', 'run_dir_invalid')
        identities = parent_identities(run_dir, preview_dir, preview, marker_identities, deadline)
        identities[str(run_dir / 'manifest.json')] = run_manifest_sha
        identities[str(run_dir / 'export' / 'outcome.json')] = export_sha
        identities[str(preview_dir / 'outcome.json')] = preview_sha
        identities[str(preview_run / 'manifest.json')] = preview_manifest_sha
        analyzed = preview['arrangement_marker_bindings'].get('analyzed_input_sha256')
        denoised = (run_manifest.get('output_sha256') or {}).get('denoised.wav')
        markers_analysis = bool(is_sha256(analyzed) and analyzed == denoised)
        identity = chain_identity(run_manifest, recorded_cleaned, recorded_audio)
        picture = preview_dir / 'marked-video.mov'
        destination = output / OUTPUT_NAME
        state.update(input_sha256=identities, chain_identity=identity, branch_gate={
            'source_sha256': gate['source_sha256'], 'native_pcm': gate['native_pcm'],
            'picture_frame_count': gate['picture_frame_count'],
            'picture_extent_seconds': str(gate['picture_extent'])})
        with runner.private_media(media.ROOT, deadline, session.events):
            ffmpeg_version = session.run([media.executable('ffmpeg'), '-version'], 30).stdout.splitlines()[0]
            before_picture, before_audio = probe(session, picture), probe(session, audio)
            pv, pa = before_picture['video'], before_audio['audio']
            require(pa.get('codec_name') == 'aac', 'audio branch delivery is not AAC', 'format_identity_failed')
            require(int(pa.get('sample_rate', 0)) == gate['native_pcm']['sample_rate']
                    and int(pa.get('channels', 0)) == gate['native_pcm']['channels'],
                    'AAC rate/channels differ from native PCM', 'native_pcm_mismatch')
            for row in (pv, pa, before_picture['probe'].get('format', {}), before_audio['probe'].get('format', {})):
                require(_zero(row.get('start_time')), 'parent stream/container origin is not 0', 'nonzero_origin_unsupported')
            picture_end = gate['picture_extent']
            require(_number_text(pa.get('duration')),
                    'AAC header duration unavailable', 'audio_does_not_cover_picture')
            audio_end = Fraction(str(pa.get('duration')))
            require(audio_end >= picture_end, f'audio header extent {audio_end} < picture extent {picture_end}',
                    'audio_does_not_cover_picture')
            tick = Fraction(pv['time_base'])
            require(tick.numerator == 1, 'reciprocal picture stream clock required', 'format_identity_failed')
            parent_video = media.video_packets(picture, pv['index'])
            parent_audio = audio_packets(session, audio, pa['index'])
            require(len(parent_video) <= MAX_PACKETS, 'picture packet table outside bounds', 'packet_identity_failed')
            parent_pcm = decoded_pcm_hash(session, audio)
            write_json(output / 'parent-video-packets.json', {'time_base': pv['time_base'], 'packets': parent_video})
            write_json(output / 'parent-audio-packets.json', {'time_base': pa['time_base'], 'packets': parent_audio})
            command = [media.executable('ffmpeg'), '-hide_banner', '-nostdin', '-loglevel', 'warning',
                       '-threads', '2', '-n', '-copyts', '-i', str(picture), '-i', str(audio), '-map', '0:v:0',
                       '-map', '1:a:0', '-map_metadata', '0', '-map_chapters', '-1', '-c:v', 'copy', '-c:a', 'copy',
                       '-video_track_timescale', str(tick.denominator), '-avoid_negative_ts', 'disabled',
                       '-movflags', '+faststart', str(destination)]
            state['command'] = command
            session.run(command, 300)
            after = probe(session, destination)
            nv, na = after['video'], after['audio']
            require(after['video_count'] == 1 and after['audio_count'] == 1
                    and len(after['probe'].get('streams', [])) == 2,
                    'composed movie must hold exactly one picture and one AAC stream', 'format_identity_failed')
            output_video = media.video_packets(destination, nv['index'])
            output_audio = audio_packets(session, destination, na['index'])
            try:
                video_proof = media.compare_video_packets(parent_video, output_video, pv['time_base'],
                                                          nv['time_base'], Fraction(0))
            except media.MediaError as exc:
                raise CompactError(str(exc), 'packet_identity_failed') from exc
            video_count = exact_packets(parent_video, output_video, pv['time_base'], nv['time_base'])
            audio_count = exact_packets(parent_audio, output_audio, pa['time_base'], na['time_base'], audio=True)
            output_pcm = decoded_pcm_hash(session, destination)
            require(output_pcm == parent_pcm, 'decoded AAC PCM changed', 'pcm_identity_failed')
            for key in PICTURE_FORMAT_KEYS:
                require(pv.get(key) == nv.get(key), f'picture format differs: {key}', 'format_identity_failed')
            for key in AUDIO_FORMAT_KEYS:
                require(pa.get(key) == na.get(key), f'AAC format differs: {key}', 'format_identity_failed')
            for name, old, new in (('picture', pv, nv), ('AAC', pa, na)):
                require(old.get('extradata_hash') is not None and old.get('extradata_hash') == new.get('extradata_hash'),
                        f'{name} decoder configuration differs', 'format_identity_failed')
            require(_zero(nv.get('start_time')) and _zero(na.get('start_time')), 'composed origins differ',
                    'format_identity_failed')
            require(Fraction(str(na.get('duration'))) == audio_end, 'AAC header extent changed', 'format_identity_failed')
        verify_identities(identities, deadline)
        require(sha256(Path(__file__)) == state['controller_sha256'], 'controller source changed', 'input_changed')
        deadline.check()
        write_json(output / 'output-video-packets.json', {'time_base': nv['time_base'], 'packets': output_video})
        write_json(output / 'output-audio-packets.json', {'time_base': na['time_base'], 'packets': output_audio})
        state.update(
            status=STATUS_OK, ffmpeg_version=ffmpeg_version, elapsed_seconds=time.monotonic() - started,
            output=str(destination), output_sha256=sha256(destination), output_bytes=destination.stat().st_size,
            input_hashes_preserved=True, owned_subprocesses=session.events,
            video_packet_verification=video_proof, video_packets_identical=f'{video_count}/{len(parent_video)}',
            aac_packets_identical=f'{audio_count}/{len(parent_audio)}', video_packet_count=video_count,
            aac_packet_count=audio_count,
            exact_video_packet_payload_and_rational_clock_identity=True,
            exact_aac_packet_payload_clock_padding_identity=True,
            picture_and_aac_decoder_configuration_identity=True,
            decoded_aac_pcm_sha256=parent_pcm, decoded_aac_identity_preserved=True,
            clock_overlap={'decoded_picture_start_seconds': '0', 'decoded_picture_end_seconds': str(picture_end),
                           'aac_stream_start_seconds': '0', 'aac_stream_end_seconds': str(audio_end),
                           'complete_picture_clock_covered': True,
                           'native_pcm_extent_samples': gate['native_pcm']['sample_count'],
                           'aac_padding_is_separate_from_native_pcm_extent': True},
            inherited_picture_frame_proof=preview.get('verification'),
            frame_proof_scope='Transitive: parent verified decoded frame table plus exact coded packet/clock/'
                              'geometry identity; no new full picture decode',
            inherited_audio_loudness=export.get('final_audio_loudness'),
            audio_loudness_scope='Parent export measurement transferred by exact AAC packet and decoded PCM '
                                 'identity; no fresh normalization',
            picture_branch={'outcome_sha256': preview_sha, 'run_dir': str(preview_run),
                            'selection_sha256': (preview.get('output_sha256') or {}).get('selection.json'),
                            'arrangement_marker_bindings': preview['arrangement_marker_bindings']},
            audio_branch={'manifest_sha256': run_manifest_sha, 'export_outcome_sha256': export_sha,
                          'export_video_sha256': recorded_audio, 'cleaned_sha256': recorded_cleaned,
                          'denoised_sha256': denoised},
            composed_probe=after['probe'],
            **claim_fields(markers_analysis, identity))
        write_json(output / 'receipt.json', state)
        return state
    except BaseException as exc:
        code = error_code(exc)
        state.update(status=STATUS_FAILED, reason=code, error=str(exc)[:2000],
                     owned_subprocesses=session.events, elapsed_seconds=time.monotonic() - started,
                     input_hashes_preserved=None, unverified_partial_output=(output / OUTPUT_NAME).exists(),
                     **claim_fields(markers_analysis, identity))
        if identities:
            try:
                verify_identities(identities, None)
                state['input_hashes_preserved'] = True
            except (CompactError, OSError):
                state['input_hashes_preserved'] = False
        try:
            write_json(output / 'failure.json', state)
        except OSError:
            pass
        if not isinstance(exc, CompactError) and isinstance(exc, Exception):
            raise CompactError(str(exc), code) from exc
        raise


def error_code(exc):
    if isinstance(exc, CompactError):
        return exc.code
    if isinstance(exc, runner.ApplyError):
        return 'deadline_exceeded' if exc.code == 'deadline_exceeded' else 'ffmpeg_failed'
    if isinstance(exc, media.MediaError):
        return 'ffmpeg_failed'
    return 'internal_error'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('run_dir', help='Verified restoration run (audio branch); read only')
    parser.add_argument('--picture-preview', required=True, help='Verified arrangement marked_video output (picture branch)')
    parser.add_argument('--arrangement-markers', required=True, help='Preview-run-relative arrangement marker selector')
    parser.add_argument('--output', help='Fresh directory beneath artifacts/ (not artifacts/runs)')
    parser.add_argument('--timeout-seconds', type=int, default=DEFAULT_TIMEOUT)
    args = parser.parse_args(argv)
    old_handler, timer_owned = None, False
    try:
        require(1 <= args.timeout_seconds <= 600, 'timeout_seconds must be 1-600', 'output_invalid')
        require(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), 'another interval timer is active', 'internal_error')
        old_handler = signal.getsignal(signal.SIGALRM)

        def expired(signum, frame):
            raise runner.ApplyError('marked-compact deadline exceeded', 'deadline_exceeded')

        signal.signal(signal.SIGALRM, expired)
        runner.CLI_ALARM_HANDLER = expired
        signal.setitimer(signal.ITIMER_REAL, args.timeout_seconds)
        timer_owned = True
        result = compose(args.run_dir, args.picture_preview, args.arrangement_markers, args.output,
                         args.timeout_seconds)
        signal.setitimer(signal.ITIMER_REAL, 0)
        print(json.dumps({key: result.get(key) for key in (
            'status', 'output', 'output_sha256', 'video_packets_identical', 'aac_packets_identical',
            'listening_acceptance', 'accepted_audio_identity', 'markers_are_analysis_of_audio_branch',
            'elapsed_seconds')} | {'chain_class': result['chain_identity']['chain_class']}, allow_nan=False))
        return 0
    except (CompactError, runner.ApplyError, media.MediaError, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'status': 'error', 'reason': error_code(exc), 'error': str(exc)[:2000]}), file=sys.stderr)
        return 1
    finally:
        if timer_owned:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old_handler)
        runner.CLI_ALARM_HANDLER = None


if __name__ == '__main__':
    raise SystemExit(main())
