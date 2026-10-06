#!/usr/bin/env python3
"""Render a separate, hash-bound uncertain phrase-review video; copy its AAC audio."""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / 'scripts') not in sys.path:
    sys.path.insert(0, str(ROOT / 'scripts'))
import markers as marker_tool
import run_demo as workflow

MAX_JSON = 20_000_000
MAX_INPUT_JSON = 64_000_000
MAX_MEDIA_BYTES = 2_000_000_000
MAX_PROCESS_BYTES = 2 * 1024 * 1024
MAX_MARKERS = 5000
MAX_FRAMES = 120_000
MAX_DURATION = 600
SELECTIONS = ('phrase-review', 'recurrences', 'all-review')
LABELS = {'recurrence_relative_alignment_shift_review': 'Loop alignment differs',
          'recurrence_relative_rate_difference_review': 'Loop rate differs',
          'recurrence_motif_timing_difference_review': 'Riff timing differs',
          'recurrence_attack_density_difference_review': 'Attack pattern differs',
          'automatic_recurrence_review_candidate': 'Possible repeated phrase',
          'low_register_riff_or_breakdown_candidate': 'Possible low-register riff',
          'spectral_texture_region_candidate': 'Texture boundary candidate',
          'four_pulse_group_review_candidate': 'Four-pulse navigation proxy'}
COMPARISON_KINDS = set(LABELS) - {'automatic_recurrence_review_candidate', 'low_register_riff_or_breakdown_candidate',
                                'spectral_texture_region_candidate', 'four_pulse_group_review_candidate'}
DEFAULT_KINDS = COMPARISON_KINDS | {'automatic_recurrence_review_candidate', 'low_register_riff_or_breakdown_candidate'}


class PreviewError(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise PreviewError(reason)


def local_directory(value, fresh=False):
    path = Path(value).expanduser()
    require('..' not in path.parts and '\\' not in str(value), 'Path traversal prohibited')
    if not path.is_absolute():
        path = ROOT / path
    boundary = ROOT
    for part in ('artifacts','runs'):
        boundary /= part
        require(not boundary.is_symlink(), 'Symlink repository artifact boundary prohibited')
    allowed = boundary.resolve()
    require(path.is_relative_to(allowed) and path != allowed, 'Directory must be beneath artifacts/runs')
    current = allowed
    for part in path.relative_to(allowed).parts:
        current /= part
        require(not current.is_symlink(), 'Symlink directory prohibited')
    require(not path.exists() if fresh else path.is_dir(), 'Output directory must be fresh' if fresh else 'Run directory missing')
    return path


def read_json(path):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_JSON, 'JSON type or byte bound invalid')
    before = workflow.sha256(path)
    with path.open('rb') as handle:
        content=handle.read(MAX_JSON+1)
    require(len(content)<=MAX_JSON,'JSON grew beyond byte bound')
    payload = workflow.strict_json(content.decode('utf-8'))
    require(workflow.sha256(path) == before, 'JSON changed during read')
    return payload


def unchanged(identities):
    for path, expected in identities.items():
        require(path.is_file() and not path.is_symlink() and workflow.sha256(path) == expected,
                'Preview input changed: ' + str(path))


def prepare(run_dir, arrangement_markers=None):
    paths = {name: marker_tool.local_artifact(run_dir, name) for name in
             ('manifest.json', 'export/outcome.json', 'dag.json', 'flags.json', 'markers.json')}
    payloads = {name: read_json(path) for name, path in paths.items()}
    graph = payloads['dag.json']
    hashes = graph.get('artifact_hashes', {})
    require(isinstance(hashes, dict) and len(hashes) <= 5000, 'Invalid graph artifact bounds')
    total = sum(path.stat().st_size for path in paths.values())
    for name in hashes:
        path = marker_tool.local_artifact(run_dir, name)
        require(path.stat().st_size <= (MAX_JSON if path.suffix == '.json' else MAX_MEDIA_BYTES),
                'Upstream graph artifact exceeds byte bound')
        if path.suffix == '.json':
            total += path.stat().st_size
    require(total <= MAX_INPUT_JSON, 'Upstream graph exceeds aggregate byte bound')
    expected_markers, _ = marker_tool.build(run_dir)
    require(expected_markers == payloads['markers.json'], 'Existing markers differ from current verified evidence; export them again')
    flags = payloads['flags.json'].get('flags', [])
    require(len(expected_markers['markers']) <= MAX_MARKERS and len(flags) <= MAX_MARKERS, 'At most 5000 markers supported')
    require(all(row.get('status', 'needs_review') == 'needs_review' and row.get('performance_issue_confirmed') is not True
                for row in flags), 'Preview accepts only unconfirmed review flags')
    manifest, export = payloads['manifest.json'], payloads['export/outcome.json']
    original = Path(manifest['source']['path']).expanduser()
    require(original.is_file() and not original.is_symlink(), 'Original source missing or aliased')
    source_hash = manifest['source']['sha256']
    require(original.stat().st_size <= MAX_MEDIA_BYTES, 'Original source exceeds media byte bound')
    require(workflow.sha256(original) == source_hash == export.get('source_sha256'), 'Original/export source hash mismatch')
    video = marker_tool.local_artifact(run_dir, 'export/cleaned-video.mov')
    master = marker_tool.local_artifact(run_dir, 'cleaned.wav')
    require(Path(export['video']) == video and export['output_sha256'].get('cleaned-video.mov') == workflow.sha256(video),
            'Delivery video differs from its exact export receipt')
    require(Path(export['audio_master']) == master and manifest['output_sha256'].get('cleaned.wav') == workflow.sha256(master),
            'Master identity differs')
    verification = export.get('verification', {})
    require(all(verification.get(key) is True for key in ('source_hash_verified', 'video_frame_count_preserved',
                     'video_packet_timeline_preserved', 'final_true_peak_within_target')), 'Export verification must precede preview')
    identities = {path: workflow.sha256(path) for path in (*paths.values(), original, video, master)}
    marker_tool.checked_hashes(run_dir, hashes, identities)
    marker_tool.checked_hashes(ROOT, graph.get('external_context_hashes', {}), identities)
    for name, expected in manifest.get('output_sha256', {}).items():
        path = marker_tool.local_artifact(run_dir, name)
        require(workflow.sha256(path) == expected, 'Restoration output differs from manifest')
        identities[path] = expected
    for name in ('report.html', 'report.json', 'demo.json'):
        path = run_dir / name
        if path.exists() or path.is_symlink():
            path = marker_tool.local_artifact(run_dir, name)
            identities[path] = workflow.sha256(path)
    recorded_origin=manifest.get('timeline', {}).get('format_start_seconds')
    if recorded_origin is None:
        recorded_origin=manifest.get('source',{}).get('probe',{}).get('format',{}).get('start_time')
    require(recorded_origin is not None,'Original container start is unknown; cannot map source callouts')
    origin = float(recorded_origin)
    require(math.isfinite(origin), 'Source container origin must be finite')
    translation=verification.get('video_packet_expected_translation_seconds')
    require(translation is not None and math.isfinite(float(translation)) and abs(float(translation)+origin)<1e-9,
            'Export packet translation does not establish the source timestamp mapping')
    flag_links = {}
    for index, flag in enumerate(flags):
        marker = {'source_time_seconds':float(flag['source_time_seconds']), 'end_seconds':float(flag.get('end_seconds',flag['source_time_seconds'])),
                  'name':str(flag.get('kind','review_candidate'))[:256], 'confidence':flag.get('confidence','unknown'),
                  'status':flag.get('status','needs_review'), 'evidence':flag.get('evidence',{})}
        marker.update({key:flag[key] for key in ('selected_evidence_slot','selected_artifact','selected_artifact_sha256') if key in flag})
        key=json.dumps(marker,sort_keys=True,allow_nan=False)
        flag_id=f'flag-{index:04d}-'+hashlib.sha256(json.dumps(flag,sort_keys=True,allow_nan=False).encode()).hexdigest()[:12]
        flag_links.setdefault(key,[]).append({'flag_id':flag_id,'flag_index':index})
    context = {'video': video, 'manifest': manifest, 'export': export, 'markers': expected_markers['markers'],
               'flags': flags, 'flag_links':flag_links, 'identities': identities, 'source_container_start_seconds': origin}
    if arrangement_markers is not None:
        import arrangement_markers as arrangement_tool
        alternate, alternate_identities = arrangement_tool.load_validated(run_dir, arrangement_markers)
        for path, identity in alternate_identities.items():
            require(path not in identities or identities[path] == identity, 'Arrangement/canonical input identity conflict')
            identities[path] = identity
        context['markers'] = alternate['markers']
        context['arrangement_markers'] = alternate
        context['arrangement_marker_selector'] = arrangement_markers
        context['flag_links'] = {}
        for index, marker in enumerate(alternate['markers']):
            key = json.dumps(marker, sort_keys=True, allow_nan=False)
            context['flag_links'][key] = [{'flag_id': 'arrangement-' + hashlib.sha256(key.encode()).hexdigest()[:16],
                                          'flag_index': index, 'flag_origin': 'hash_bound_arrangement_assessment'}]
    return context


def timestamp(value):
    centiseconds = round(value * 100)
    require(centiseconds >= 0, 'Negative subtitle timestamp')
    hours, remain = divmod(centiseconds, 360000)
    minutes, remain = divmod(remain, 6000)
    seconds, cs = divmod(remain, 100)
    return f'{hours}:{minutes:02d}:{seconds:02d}.{cs:02d}'


def safe_text(value):
    # Neutralize ASS override syntax and line escapes before any rendering.
    return str(value).replace('\\', '/').replace('{', '(').replace('}', ')').replace('\n', ' ').replace('\r', ' ')[:200]


def arrangement_display(marker):
    # Display-only reduction; validated full wording/evidence remain in metadata.
    full = safe_text(marker['display_label'])
    phrase = full.split(': ', 1)[-1].replace(' (presumed repeat)', '').replace(' phrase ', ' · phrase ')
    user_length = '[USER: length?]' in phrase
    phrase = phrase.replace(' [USER: length?]', '')
    kind = marker['name']
    badge = ('Expected' if kind == 'arrangement_intended_unit' else
             'Expected boundary' if full.startswith('EXPECTED boundary window:') else 'Timing review')
    badges = [badge] + (['Check breakdown length (user)'] if user_length else [])
    return {'arrangement_phrase_label': phrase, 'arrangement_badges': badges,
            'full_display_label': full, 'label': phrase + ' | ' + ' · '.join(badges)}


def select_markers(markers, selection, origin, frame_start, frame_end, *, arrangement_labels=False):
    require(selection in SELECTIONS, 'Unknown marker selection')
    selected, excluded = [], []
    for index, marker in enumerate(markers):
        name = marker.get('name')
        take = selection == 'all-review' or name in (DEFAULT_KINDS if selection == 'phrase-review' else DEFAULT_KINDS - {'low_register_riff_or_breakdown_candidate'})
        marker_id = f'marker-{index:04d}-' + hashlib.sha256(json.dumps(marker, sort_keys=True, allow_nan=False).encode()).hexdigest()[:12]
        if not take:
            excluded.append({'marker_id': marker_id, 'name': name, 'reason': 'outside_explicit_selection'})
            continue
        start, end = float(marker['source_time_seconds']), float(marker['end_seconds'])
        require(math.isfinite(start) and math.isfinite(end) and end >= start, 'Invalid marker source interval')
        low, high = start - origin, end - origin
        if low == high:
            high = low + 1.0  # Presentation dwell only, never asserted phrase duration.
        low, high = max(low, frame_start), min(high, frame_end)
        if high <= low:
            excluded.append({'marker_id': marker_id, 'name': name, 'reason': 'outside_decoded_picture_coverage'})
            continue
        require(low >= 0, 'Negative exported video timestamps are not supported by ASS preview')
        selected.append({'marker_id': marker_id, 'marker_index': index, 'name': name,
                         'source_start_seconds': start, 'source_end_seconds': end,
                         'video_start_seconds': round(low*100)/100, 'video_end_seconds': round(high*100)/100,
                         'label': safe_text(marker['display_label']) if arrangement_labels else LABELS.get(name, 'Review candidate'), 'status': 'needs_review',
                         'evidence': marker.get('evidence', {}), 'confidence': marker.get('confidence', 'unknown'),
                         'presentation_dwell_extended': start == end,
                         **({'label_basis': marker['label_basis'], **arrangement_display(marker)} if arrangement_labels else {})})
    limit = MAX_MARKERS if selection == 'all-review' else 128
    require(len(selected) <= limit, 'Selected marker count exceeds explicit preview bound')
    return selected, excluded


def compose_callouts(selected, origin, *, arrangement_labels=False):
    edges = sorted({row[key] for row in selected for key in ('video_start_seconds', 'video_end_seconds')})
    callouts = []
    coverage = {row['marker_id']: {'visible_seconds': 0., 'suppressed_seconds': 0.} for row in selected}
    for low, high in zip(edges, edges[1:]):
        if high <= low:
            continue
        active = [row for row in selected if row['video_start_seconds'] <= low and row['video_end_seconds'] >= high]
        active.sort(key=lambda row: (row['name'] not in COMPARISON_KINDS, row['video_start_seconds'], row['marker_id']))
        if not active:
            continue
        visible, suppressed = active[:2], active[2:]
        for row in visible:
            coverage[row['marker_id']]['visible_seconds'] += high-low
        for row in suppressed:
            coverage[row['marker_id']]['suppressed_seconds'] += high-low
        labels = list(dict.fromkeys(row['label'] for row in visible))
        if arrangement_labels:
            grouped = {}
            for row in visible:
                badges = grouped.setdefault(row['arrangement_phrase_label'], [])
                for badge in row['arrangement_badges']:
                    if badge not in badges:
                        badges.append(badge)
            labels = [phrase + ' | ' + ' · '.join(badges) for phrase, badges in grouped.items()]
        callout = {'video_start_seconds': low, 'video_end_seconds': high,
                   'source_start_seconds': low+origin, 'source_end_seconds': high+origin,
                   'visible_marker_ids': [row['marker_id'] for row in visible],
                   'suppressed_marker_ids': [row['marker_id'] for row in suppressed],
                   'labels': labels}
        if (callouts and callouts[-1]['video_end_seconds'] == low and all(callouts[-1][key] == callout[key]
                for key in ('visible_marker_ids', 'suppressed_marker_ids', 'labels'))):
            callouts[-1]['video_end_seconds'] = high
            callouts[-1]['source_end_seconds'] = high+origin
        else:
            callouts.append(callout)
    require(len(callouts) <= MAX_MARKERS*2, 'Callout count exceeds bound')
    return callouts, coverage


def subtitles(callouts, width, height, font_family='Helvetica', reference_bpm=None):
    size = max(14, round(height*.025))
    header = f'''[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Review,{font_family},{size},&H0048C9FF,&H0048C9FF,&H00101010,&H80080808,0,0,0,0,100,100,0,0,3,8,0,2,{round(width*.035)},{round(width*.035)},{round(height*.045)},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    rows = []
    for row in callouts:
        low, high = row['video_start_seconds'], row['video_end_seconds']
        if round(high*100) <= round(low*100):
            continue
        source_range = f"{timestamp(row['source_start_seconds'])} - {timestamp(row['source_end_seconds'])}"
        details = safe_text(' / '.join(row['labels']))
        fade = '{\\fad(60,60)}' if high-low >= .3 else ''
        heading = ('REVIEW - uncertain | SOURCE ' + source_range if reference_bpm is None else
                   f'~{reference_bpm:g} BPM · expected arrangement')
        text = fade + safe_text(heading) + '\\N' + details
        rows.append(f'Dialogue: 0,{timestamp(low)},{timestamp(high)},Review,,0,0,0,,{text}')
    return header + '\n'.join(rows) + '\n'


def executable(name):
    value = os.environ.get(name.upper()) or shutil.which(name)
    require(value is not None and Path(value).is_file(), f'Executable unavailable: {name}; set {name.upper()} explicitly')
    return str(Path(value).resolve())


def installed_font(output):
    candidates=(('/System/Library/Fonts/Helvetica.ttc','Helvetica'),
                ('/System/Library/Fonts/Supplemental/Arial.ttf','Arial'),
                ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf','DejaVu Sans'))
    for name,family in candidates:
        source=Path(name)
        if source.is_file() and not source.is_symlink() and source.stat().st_size <= 10_000_000:
            identity=workflow.sha256(source)
            directory=output/'fonts'
            directory.mkdir(mode=0o700)
            destination=directory/('review-font'+source.suffix)
            shutil.copyfile(source,destination)
            require(workflow.sha256(source)==identity==workflow.sha256(destination),'Installed font changed during private snapshot')
            return {'family':family,'source':str(source),'sha256':identity,
                    'private_snapshot':destination.relative_to(output).as_posix(),
                    'scope':'Existing local font copied for this private render; no installation or host change'}
    raise PreviewError('No bounded supported installed font found; no font installation occurs')


def command_run(command, executions, timeout=120, cwd=None):
    receipt = {'command': command, 'timeout_seconds': timeout, 'max_output_bytes_per_stream': MAX_PROCESS_BYTES,
               'status': 'starting', 'math_threads': 2}
    executions.append(receipt)
    started = time.monotonic()
    environment = os.environ.copy()
    environment.update({name: '2' for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS')})
    process = subprocess.Popen(command, cwd=cwd or ROOT, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environment)
    # Direct ffmpeg/ffprobe workers retain the controller's process group. An
    # outer MCP group deadline therefore owns the complete process tree.
    receipt.update(pid=process.pid, new_session_requested=False, controller_pgid=os.getpgrp())
    buffers = {'stdout': bytearray(), 'stderr': bytearray()}
    try:
        with selectors.DefaultSelector() as selector:
            for name, pipe in (('stdout',process.stdout),('stderr',process.stderr)):
                os.set_blocking(pipe.fileno(),False)
                selector.register(pipe,selectors.EVENT_READ,name)
            while selector.get_map():
                remaining = timeout-(time.monotonic()-started)
                require(remaining > 0, 'Owned media worker hard deadline exceeded')
                for key,_ in selector.select(min(.1,remaining)):
                    chunk=os.read(key.fileobj.fileno(),65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    require(len(buffers[key.data])+len(chunk) <= MAX_PROCESS_BYTES,'Owned media worker output byte bound exceeded')
                    buffers[key.data].extend(chunk)
            process.wait(timeout=max(.001,timeout-(time.monotonic()-started)))
        require(process.returncode == 0, 'Media worker failed: '+buffers['stderr'][-2000:].decode(errors='replace'))
        receipt['status']='completed'
        return buffers['stdout'].decode('utf-8')
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        receipt.update(status='failed',error=str(exc))
        raise
    finally:
        if process.poll() is None:
            try:
                observed=os.getpgid(process.pid)
                process.kill()
                process.wait(timeout=5)
                receipt['process_escape_hatch']={'actor':'video-utils/marked_video',
                    'target_ownership':{'pid':process.pid,'observed_pgid':observed,'created_by_invocation':True,
                                        'new_session_requested':False},
                    'reason':'bounded direct media worker cleanup','ruling':'R-N11; '+workflow.AUTHORITY,
                    'prior_state':'own recorded child polled live and its process group inspected',
                    'result':{'signal_target':'owned_worker_only','worker_returncode':process.returncode}}
            except ProcessLookupError:
                process.wait(timeout=5)
        receipt.update(returncode=process.returncode,elapsed_seconds=time.monotonic()-started,
                       stdout_bytes=len(buffers['stdout']),stderr_bytes=len(buffers['stderr']),
                       stderr_tail=buffers['stderr'][-2000:].decode(errors='replace'))
        process.stdout.close()
        process.stderr.close()


def inspect_media(path, ffmpeg, ffprobe, executions):
    base=[ffprobe,'-v','error','-threads','2']
    probe=workflow.strict_json(command_run(base+['-show_streams','-show_format','-of','json',str(path)],executions))
    videos=[row for row in probe['streams'] if row['codec_type']=='video']
    audios=[row for row in probe['streams'] if row['codec_type']=='audio']
    require(len(videos)==len(audios)==1,'Preview requires exactly one picture stream and one audio stream')
    video,audio=videos[0],audios[0]
    require(audio['codec_name']=='aac','Verified AAC delivery required for packet-copy preview')
    duration=float(probe['format']['duration'])
    require(math.isfinite(duration) and 0 < duration <= MAX_DURATION,'Preview input duration exceeds 600 seconds')
    frames=workflow.strict_json(command_run(base+['-select_streams','v:0','-show_frames','-show_entries',
           'frame=best_effort_timestamp,duration','-of','json=compact=1',str(path)],executions,240))['frames']
    require(0 < len(frames) <= MAX_FRAMES,'Decoded frame count outside bounds')
    tick=Fraction(video['time_base'])
    pts=[int(row['best_effort_timestamp'])*tick for row in frames]
    require(all(a<=b for a,b in zip(pts,pts[1:])),'Decoded picture timestamps not monotonic')
    tail=int(frames[-1].get('duration',0))*tick
    require(tail>0,'Last decoded frame extent unknown')
    packets=workflow.strict_json(command_run(base+['-select_streams','a:0','-show_packets','-show_entries',
             'packet=pts,dts,duration,data_hash,side_data_list:packet_side_data=side_data_type,skip_samples,discard_padding',
             '-show_data_hash','sha256','-of','json=compact=1',str(path)],executions))['packets']
    require(0 < len(packets) <= 60000,'Audio packet count outside bound')
    pcm_hash=command_run([ffmpeg,'-hide_banner','-nostdin','-loglevel','error','-threads','2','-i',str(path),
                         '-map','0:a:0','-vn','-c:a','pcm_f32le','-f','hash','-hash','sha256','-'],executions).strip()
    require(pcm_hash.startswith('SHA256=') and len(pcm_hash)==71,'Decoded AAC PCM hash unavailable')
    return {'probe':probe,'video':video,'audio':audio,'frame_pts':pts,'frames':frames,'packets':packets,
            'frame_start':float(pts[0]),'frame_end':float(pts[-1]+tail),'pcm_hash':pcm_hash,'duration':duration}


def verify_render(before,after):
    require(before['frame_pts']==after['frame_pts'],'Reencoded preview changed decoded picture frame PTS or count')
    require(Fraction(str(before['frame_end']))==Fraction(str(after['frame_end'])),'Reencoded preview changed last decoded picture extent')
    require(all(before['video'].get(key)==after['video'].get(key) for key in ('width','height','sample_aspect_ratio')),
            'Reencoded preview changed picture geometry')
    for key in ('sample_rate','channels','codec_name'):
        require(before['audio'][key]==after['audio'][key],'Preview changed delivery audio format')
    require(before['pcm_hash']==after['pcm_hash'],'Preview changed decoded delivery audio')
    require(len(before['packets'])==len(after['packets']),'Preview changed AAC packet count')
    for old,new in zip(before['packets'],after['packets']):
        require(old.get('data_hash')==new.get('data_hash') and old.get('side_data_list')==new.get('side_data_list'),
                'Preview changed AAC packet payload or priming/discard metadata')
        for key in ('pts','dts','duration'):
            require(key in old and key in new and int(old[key])*Fraction(before['audio']['time_base']) == int(new[key])*Fraction(after['audio']['time_base']),
                    'Preview changed AAC packet timing')
    return {'decoded_video_frame_count':len(after['frame_pts']),'decoded_video_frame_pts_preserved':True,
            'decoded_video_last_extent_preserved':True,'aac_packet_payloads_timing_and_padding_preserved':True,
            'decoded_video_first_pts_seconds':before['frame_start'], 'decoded_video_last_extent_seconds':before['frame_end'],
            'picture_geometry_preserved':True,
            'decoded_video_variable_frame_intervals_observed':len({b-a for a,b in zip(before['frame_pts'],before['frame_pts'][1:])})>1,
            'decoded_video_frame_pts_sha256':hashlib.sha256(json.dumps([str(value) for value in before['frame_pts']]).encode()).hexdigest(),
            'decoded_audio_pcm_sha256_preserved':True,'decoded_audio_pcm_hash':after['pcm_hash'],
            'audio_sample_rate':int(after['audio']['sample_rate']),'audio_channels':after['audio']['channels'],
            'picture_reencoded':True,'physical_audio_video_sync_verified':False}


def render(run_dir, output, selection='phrase-review', arrangement_markers=None):
    run_dir=local_directory(run_dir)
    output=local_directory(output,fresh=True)
    require(not run_dir.is_relative_to(output),'Output cannot contain the input run')
    require(arrangement_markers is None or selection == 'all-review', 'Arrangement markers require explicit all-review selection')
    context=prepare(run_dir, arrangement_markers)
    ffmpeg,ffprobe=executable('ffmpeg'),executable('ffprobe')
    output.mkdir(parents=True,mode=0o700)
    outcome={'schema_version':1,'status':'running','run_dir':str(run_dir),'selection':selection,
             'source_sha256':context['manifest']['source']['sha256'],'worker_sha256':workflow.sha256(Path(__file__)),
             'executions':[],'input_sha256':{str(p):h for p,h in context['identities'].items()},
             'authority':workflow.AUTHORITY+'/R-N11/R-N13','listening_accepted':False,
             'limitations':['All callouts are uncertain review hypotheses, not confirmed musical mistakes.',
                            'Picture is reencoded; original and cleaned delivery remain separate.',
                            'Generic source timestamp spans are not validated Final Cut/Resolve import.',
                            'Physical capture A/V synchronization and Logic acceptance remain unverified.']}
    if arrangement_markers is not None:
        outcome['marker_mode'] = 'arrangement_reference_review'
        outcome['arrangement_marker_selector'] = arrangement_markers
        outcome['arrangement_marker_bindings'] = {key: context['arrangement_markers'][key]
            for key in ('source_sha256', 'analyzed_input_sha256', 'manifest_sha256', 'assessment', 'reference',
                        'producer_sha256', 'reference_validator_sha256', 'tempo')}
    workflow.atomic_json(output/'outcome.json',outcome)
    try:
        filters=command_run([ffmpeg,'-hide_banner','-filters'],outcome['executions'],30)
        require(any('ass' in line.split() for line in filters.splitlines()),'Installed FFmpeg ASS filter unavailable')
        outcome['ffmpeg_version']=command_run([ffmpeg,'-version'],outcome['executions'],30).splitlines()[0]
        outcome['font']=installed_font(output)
        before=inspect_media(context['video'],ffmpeg,ffprobe,outcome['executions'])
        selected,excluded=select_markers(context['markers'],selection,context['source_container_start_seconds'],before['frame_start'],before['frame_end'],
                                         arrangement_labels=arrangement_markers is not None)
        for row in selected:
            key=json.dumps(context['markers'][row['marker_index']],sort_keys=True,allow_nan=False)
            row['flags']=context['flag_links'].get(key,[])
            require(row['flags'],'Selected marker has no exact current flag binding')
        callouts,coverage=compose_callouts(selected,context['source_container_start_seconds'],
                                          arrangement_labels=arrangement_markers is not None)
        require(callouts,'No selected evidence intersects decoded picture coverage')
        selection_payload={'schema_version':1,'selection':selection,'source_sha256':outcome['source_sha256'],
            'source_container_start_seconds':context['source_container_start_seconds'],
            'source_mapping':'source seconds = preserved exported frame PTS + original container start',
            'subtitle_time_quantization_seconds':.01,'selected_markers':selected,'excluded_markers':excluded,
            'callouts':callouts,'marker_visibility':coverage,'visible_lines_maximum':2,
            'performance_issue_confirmed':False,'listening_accepted':False}
        if arrangement_markers is not None:
            selection_payload['marker_mode'] = 'arrangement_reference_review'
            selection_payload['arrangement_marker_bindings'] = outcome['arrangement_marker_bindings']
        workflow.atomic_json(output/'selection.json',selection_payload)
        (output/'callouts.ass').write_text(subtitles(callouts,before['video']['width'],before['video']['height'],outcome['font']['family'],
            context['arrangement_markers']['tempo']['bpm'] if arrangement_markers is not None else None))
        unchanged(context['identities'])
        destination=output/'marked-video.mov'
        tick=Fraction(before['video']['time_base'])
        require(tick.numerator==1,'Preview requires an exact reciprocal video stream timebase')
        command=[ffmpeg,'-hide_banner','-nostdin','-loglevel','warning','-threads','2','-filter_threads','2',
                 '-filter_complex_threads','2','-n','-copyts','-i',str(context['video']),'-map','0:v:0','-map','0:a:0',
                 '-map_metadata','0','-vf','ass=filename=callouts.ass:fontsdir=fonts','-c:v','libx264','-preset','veryfast','-crf','18',
                 '-threads','2','-fps_mode:v','passthrough','-enc_time_base:v','demux',
                 '-video_track_timescale',str(tick.denominator),'-c:a','copy','-avoid_negative_ts','disabled',
                 '-movflags','+faststart',str(destination)]
        command_run(command,outcome['executions'],600,output)
        after=inspect_media(destination,ffmpeg,ffprobe,outcome['executions'])
        verification=verify_render(before,after)
        unchanged(context['identities'])
        require(workflow.sha256(Path(outcome['font']['source']))==outcome['font']['sha256']
                ==workflow.sha256(output/outcome['font']['private_snapshot']), 'Render font identity changed')
        outcome.update(status='marked_review_preview_verified_unreviewed',verification=verification,
             selected_marker_count=len(selected),callout_count=len(callouts),
             audio_loudness=context['export'].get('final_audio_loudness'),
             audio_loudness_scope='Inherited from exact packet and decoded PCM identity; no normalization or separate listening acceptance',
             source_container_start_seconds=context['source_container_start_seconds'],input_hashes_preserved=True,
             video_probe=after['probe'],
             output_sha256={name:workflow.sha256(output/name) for name in ('marked-video.mov','callouts.ass','selection.json')})
        workflow.atomic_json(output/'outcome.json',outcome)
        return {'status':outcome['status'],'marked_video':str(destination),'outcome_json':str(output/'outcome.json'),
                'selection_json':str(output/'selection.json'),'subtitles_ass':str(output/'callouts.ass'),
                'selected_marker_count':len(selected),'callout_count':len(callouts),'listening_accepted':False}
    except (OSError,ValueError,KeyError,subprocess.TimeoutExpired) as exc:
        outcome.update(status='failed_preview_preserving_inputs',error=str(exc))
        workflow.atomic_json(output/'outcome.json',outcome)
        raise


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--selection',choices=SELECTIONS,default='phrase-review')
    parser.add_argument('--arrangement-markers', help='Validated same-run-relative arrangement marker JSON; requires all-review')
    args=parser.parse_args(argv)
    try:
        print(json.dumps(render(args.run_dir,args.output,args.selection,args.arrangement_markers),allow_nan=False))
        return 0
    except (OSError,ValueError,KeyError,subprocess.TimeoutExpired) as exc:
        print(json.dumps({'status':'error','error':str(exc)}),file=sys.stderr)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
