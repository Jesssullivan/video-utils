"""Synthetic phone and Photo Booth media fixtures (S2 robustness lane, TIN-5609).

Test support only, not a product tool. Contract: docs/spec/sprints/ROBUSTNESS_S2.md §4.
Every fixture is short (<= 10 s), deterministic (anoisesrc seed 5609, no other
randomness), built by bounded FFmpeg/ffprobe calls (explicit timeout <= 60 s,
-nostdin -n -threads 2) and never overwrites an existing path. Binaries come
from the FFMPEG/FFPROBE environment variables.

The audio content is a synthetic signal fact, not a musical or intended-note
reference: a 0.00-1.00 s pink-noise-only lead-in (amplitude 0.02, seed 5609)
that serves as the synthetic capture source, then the same noise plus distorted
C1 bursts 0.3*tanh(3*sin(2*pi*32.70*t)) gated 120 ms every 0.25 s and a 3.5 kHz
9 ms exponentially decaying click every 0.5 s.
"""
from __future__ import annotations

from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

SEED = 5609
MAX_SECONDS = 10.0
MAX_TIMEOUT = 60
PHOTO_BOOTH_TAIL_SECONDS = 0.069
PHONE_AUDIO_OFFSET_SECONDS = 0.25
CLICK_AMPLITUDE = 0.5
CLICK_DECAY_SECONDS = 0.002
KINDS = ('phone', 'photo_booth', 'photo_booth_preroll', 'phone_hevc')
UNKNOWN = {'real_take_equivalence': 'not_established', 'device_capture_equivalence': 'unknown',
           'rotation_applied_to_pixels': False, 'real_take_audio_tail_reconciled': False,
           'capture_interval_noise_only': 'by_construction_synthetic',
           'physical_audio_video_sync_verified': False, 'listening_accepted': False}
REAL_TAKE_REFERENCE = {
    'source': 'artifacts/runs/20261006T041633Z-990aa1bd6737/manifest.json (read at contract freeze, not computed)',
    'video': 'h264 1620x1080 time_base 1/600 avg_frame_rate 108930/4549',
    'audio': 'aac mono 44100 Hz start 0.0 header duration 150.954059 s',
    'video_header_duration_seconds': 150.905, 'header_duration_difference_ms': 49.059,
    'lane_instruction_tail_ms': 69, 'reconciled': False}


class FixtureError(RuntimeError):
    pass


def binary(name: str) -> str:
    selected = os.environ.get(name.upper(), name)
    found = shutil.which(selected)
    if not found:
        raise FixtureError(f'{name} not available; set {name.upper()}')
    return found


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def run(command: list[str], timeout: int, commands: list | None = None) -> str:
    if timeout > MAX_TIMEOUT:
        raise FixtureError('fixture subprocess timeout exceeds 60 s')
    if commands is not None:
        commands.append(command)
    try:
        result = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise FixtureError(f'{Path(command[0]).name} did not finish: {exc}') from exc
    if result.returncode:
        raise FixtureError(f'{Path(command[0]).name} failed ({result.returncode}): {result.stderr[-2000:]}')
    return result.stdout


def ffmpeg(arguments: list[str], timeout: int, commands: list) -> None:
    run([binary('ffmpeg'), '-hide_banner', '-nostdin', '-loglevel', 'error', '-n', *arguments,
         ], timeout, commands)


def ffprobe_json(arguments: list[str], timeout: int = 60) -> dict:
    # ffprobe has no -nostdin/-n (ffmpeg-only); stdin is DEVNULL and it never writes media.
    return json.loads(run([binary('ffprobe'), '-v', 'error', '-threads', '2', *arguments, '-of', 'json'], timeout))


def encoders(timeout: int = 30) -> str:
    return run([binary('ffmpeg'), '-hide_banner', '-nostdin', '-encoders'], timeout)


def has_encoder(name: str) -> bool:
    try:
        return any(line.split()[1:2] == [name] for line in encoders().splitlines() if line.strip())
    except FixtureError:
        return False


def audio_graph(seconds: float, rate: int, channels: int) -> str:
    """Deterministic lavfi graph; pink noise throughout, signal only from 1.00 s."""
    signal = (f"if(gte(t\\,1)\\,0.3*tanh(3*sin(2*PI*32.70*t))*lt(mod(t-1\\,0.25)\\,0.12)"
              f"+{CLICK_AMPLITUDE}*sin(2*PI*3500*t)*exp(-mod(t-1\\,0.5)/{CLICK_DECAY_SECONDS})"
              f"*lt(mod(t-1\\,0.5)\\,0.009)\\,0)")
    layout = 'stereo' if channels == 2 else 'mono'
    pan = 'pan=stereo|c0=1.0*c0|c1=0.7*c0' if channels == 2 else 'anull'
    return (f"anoisesrc=color=pink:amplitude=0.02:seed={SEED}:sample_rate={rate}:duration={seconds:.6f}[noise];"
            f"aevalsrc=exprs='{signal}':sample_rate={rate}:duration={seconds:.6f}:channel_layout=mono[signal];"
            f"[noise][signal]amix=inputs=2:normalize=0:duration=longest,{pan},"
            f"aformat=sample_rates={rate}:channel_layouts={layout}[out0]")


def video_frames(path: Path) -> tuple[str, list[dict]]:
    data = ffprobe_json(['-select_streams', 'v:0', '-show_streams', '-show_frames', '-show_entries',
                         'stream=time_base:frame=best_effort_timestamp,pts,duration', str(path)])
    return data['streams'][0]['time_base'], data['frames']


def video_packets(path: Path) -> list[dict]:
    return ffprobe_json(['-select_streams', 'v:0', '-show_packets', '-show_entries',
                         'packet=pts,dts,duration,flags', str(path)])['packets']


def decoded_audio_samples(path: Path) -> int:
    frames = ffprobe_json(['-select_streams', 'a:0', '-show_frames', '-show_entries', 'frame=nb_samples',
                           str(path)])['frames']
    return sum(int(frame['nb_samples']) for frame in frames)


def presented_video_end(path: Path) -> Fraction:
    time_base, frames = video_frames(path)
    last = frames[-1]
    return (int(last['best_effort_timestamp']) + int(last['duration'])) * Fraction(time_base)


def rotation(stream: dict):
    for side in stream.get('side_data_list', []) or []:
        if 'rotation' in side:
            return side['rotation']
    return None


def measure(path: Path) -> dict:
    data = ffprobe_json(['-show_format', '-show_streams', str(path)])
    video = next(s for s in data['streams'] if s['codec_type'] == 'video')
    audio = next(s for s in data['streams'] if s['codec_type'] == 'audio')
    time_base, frames = video_frames(path)
    tick = Fraction(time_base)
    durations = sorted({int(frame['duration']) for frame in frames if frame.get('duration') is not None})
    packets = video_packets(path)
    audio_start = float(audio.get('start_time', 0) or 0)
    audio_duration = float(audio['duration'])
    last = frames[-1]
    video_end = (int(last['best_effort_timestamp']) + int(last['duration'])) * tick
    first = int(frames[0]['best_effort_timestamp']) * tick
    return {'video_codec': video['codec_name'], 'video_codec_tag': video.get('codec_tag_string'),
            'width': video['width'], 'height': video['height'], 'video_time_base': time_base,
            'avg_frame_rate': video.get('avg_frame_rate'), 'rotation': rotation(video),
            'presented_frames': len(frames), 'frame_duration_ticks': durations,
            'first_presented_frame_seconds': float(first), 'presented_video_end_seconds': float(video_end),
            'coded_video_packets': len(packets),
            'decode_only_packets': sum('D' in packet.get('flags', '') for packet in packets),
            'audio_codec': audio['codec_name'], 'sample_rate': int(audio['sample_rate']),
            'channels': int(audio['channels']), 'audio_start_seconds': audio_start,
            'audio_duration_seconds': audio_duration, 'audio_end_seconds': audio_start + audio_duration,
            'decoded_audio_samples': decoded_audio_samples(path),
            'audio_stream_duration_ts': int(audio['duration_ts']) if audio.get('duration_ts') is not None else None,
            'audio_stream_time_base': audio.get('time_base'),
            'audio_end_minus_video_end_seconds': audio_start + audio_duration - float(video_end),
            'format_start_seconds': float(data['format'].get('start_time', 0) or 0)}


def binaries() -> dict:
    return {name: {'path': binary(name), 'sha256': sha256(Path(binary(name)))} for name in ('ffmpeg', 'ffprobe')}


def build_fixture(kind: str, directory, *, seconds: float = 6.0, timeout_seconds: int = 60) -> dict:
    """Build one fixture kind into ``directory``; return its receipt."""
    if kind not in KINDS:
        raise FixtureError(f'unknown fixture kind {kind!r}')
    if not isinstance(seconds, (int, float)) or isinstance(seconds, bool) or not 1.5 <= seconds <= MAX_SECONDS:
        raise FixtureError('fixture seconds must be between 1.5 and 10')
    if not isinstance(timeout_seconds, int) or not 1 <= timeout_seconds <= MAX_TIMEOUT:
        raise FixtureError('fixture timeout must be an integer of at most 60 s')
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    output = directory / f'{kind}.mov'
    if output.exists() or output.is_symlink():
        raise FixtureError(f'refusing to overwrite existing fixture {output}')
    commands: list = []
    staging = directory / f'.{kind}-intermediate'
    if staging.exists():
        raise FixtureError(f'refusing to reuse intermediate directory {staging}')
    staging.mkdir()
    threads = ['-threads', '2']
    try:
        if kind in ('phone', 'phone_hevc'):
            if kind == 'phone_hevc' and not has_encoder('libx265'):
                raise FixtureError('libx265 encoder absent')
            codec = (['-c:v', 'libx265', '-preset', 'ultrafast', '-x265-params', 'log-level=error:pools=2',
                      '-tag:v', 'hvc1'] if kind == 'phone_hevc' else
                     ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '28'])
            base = staging / 'unrotated.mov'
            ffmpeg(['-f', 'lavfi', '-i', f'testsrc2=size=360x640:rate=30000/1001:duration={seconds:.6f}',
                    '-itsoffset', str(PHONE_AUDIO_OFFSET_SECONDS),
                    '-f', 'lavfi', '-i', audio_graph(seconds, 48000, 2),
                    '-map', '0:v', '-map', '1:a',
                    # Drop every 7th source frame: >= 2 distinct presented frame durations (VFR).
                    '-vf', "select='not(eq(mod(n\\,7)\\,3))'", '-fps_mode', 'vfr', *codec,
                    '-g', '30', '-pix_fmt', 'yuv420p', '-video_track_timescale', '30000',
                    '-c:a', 'aac', '-b:a', '128k', '-ar', '48000', '-ac', '2', *threads, str(base)],
                   timeout_seconds, commands)
            ffmpeg(['-display_rotation:v:0', '90', '-i', str(base), '-map', '0', '-c', 'copy',
                    *threads, str(output)], timeout_seconds, commands)
            expected = {'video_codec': 'hevc' if kind == 'phone_hevc' else 'h264', 'width': 360, 'height': 640,
                        'rotation_requested_degrees_counter_clockwise': 90, 'sample_rate': 48000, 'channels': 2,
                        'audio_start_seconds': PHONE_AUDIO_OFFSET_SECONDS, 'nominal_frame_rate': '30000/1001',
                        'video_time_base': '1/30000', 'min_distinct_frame_durations': 2,
                        'audio_extends_past_video_end': True, 'stereo_gain': {'left': 1.0, 'right': 0.7}}
        else:
            source = directory / 'photo_booth.mov' if kind == 'photo_booth_preroll' else None
            if kind == 'photo_booth_preroll':
                if source is None or not source.is_file():
                    raise FixtureError('photo_booth_preroll needs an existing photo_booth.mov in the same directory')
                cut = 1.3  # Not a multiple of the 2.0 s (GOP 48) keyframe interval.
                ffmpeg(['-ss', str(cut), '-i', str(source), '-map', '0', '-c', 'copy', '-video_track_timescale', '600',
                        *threads, str(output)],
                       timeout_seconds, commands)
                expected = {'video_codec': 'h264', 'width': 1280, 'height': 720, 'sample_rate': 44100,
                            'channels': 1, 'video_time_base': '1/600', 'cut_seconds': cut,
                            'min_decode_only_packets': 1, 'source_fixture_sha256': sha256(source)}
            else:
                frames = round(seconds * 24 / 3) * 3
                video = staging / 'video.mov'
                # Exact 24/25/26-tick cycle at a 1/600 time base (mean 25 ticks -> 24 fps).
                cadence = "settb=1/600,setpts='75*floor(N/3)+24*gte(mod(N\\,3)\\,1)+25*gte(mod(N\\,3)\\,2)'"
                ffmpeg(['-f', 'lavfi', '-i', f'testsrc2=size=1280x720:rate=24',
                        '-frames:v', str(frames), '-vf', cadence, '-fps_mode', 'passthrough',
                        '-enc_time_base:v', '1/600', '-video_track_timescale', '600',
                        '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '30', '-g', '48', '-keyint_min', '48',
                        '-sc_threshold', '0', '-bf', '0', '-pix_fmt', 'yuv420p', *threads, str(video)],
                       timeout_seconds, commands)
                video_end = presented_video_end(video)
                audio_seconds = float(video_end) + PHOTO_BOOTH_TAIL_SECONDS
                ffmpeg(['-i', str(video), '-f', 'lavfi', '-i', audio_graph(audio_seconds, 44100, 1),
                        '-map', '0:v', '-map', '1:a', '-c:v', 'copy', '-video_track_timescale', '600',
                        '-c:a', 'aac', '-b:a', '96k', '-ar', '44100', '-ac', '1', *threads, str(output)],
                       timeout_seconds, commands)
                expected = {'video_codec': 'h264', 'width': 1280, 'height': 720, 'sample_rate': 44100,
                            'channels': 1, 'video_time_base': '1/600', 'frame_duration_ticks': [24, 25, 26],
                            'presented_frames': frames, 'gop': 48,
                            'audio_end_minus_video_end_seconds': PHOTO_BOOTH_TAIL_SECONDS,
                            'video_presented_end_seconds_measured_before_mux': float(video_end)}
        measured = measure(output)
    except BaseException:
        if output.exists():
            output.unlink()
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return {'schema_version': 1, 'kind': kind, 'path': str(output), 'sha256': sha256(output),
            'size_bytes': output.stat().st_size, 'seconds_requested': seconds, 'commands': commands,
            'binaries': binaries(), 'expected': expected, 'measured': measured,
            'signal': {'lead_in_noise_only_seconds': [0.0, 1.0], 'noise': f'pink amplitude 0.02 seed {SEED}',
                       'c1_burst': '0.3*tanh(3*sin(2*pi*32.70*t)) gated 120 ms every 0.25 s from 1.00 s',
                       'click': f'3.5 kHz {CLICK_AMPLITUDE} amplitude exp(-t/{CLICK_DECAY_SECONDS}) 9 ms every 0.5 s from 1.00 s',
                       'scope': 'synthetic signal facts; not a musical or intended-note reference'},
            'unknown': dict(UNKNOWN, hevc='run' if kind == 'phone_hevc' else 'not_applicable'),
            'real_take_reference': REAL_TAKE_REFERENCE}
