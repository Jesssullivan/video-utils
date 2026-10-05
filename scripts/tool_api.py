#!/usr/bin/env python3
"""Validated local tool registry and bounded allowlist dispatcher (stdlib only)."""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / 'program' / 'tools.json'
MAX_WORKER_OUTPUT = 2 * 1024 * 1024
MAX_JSON_NESTING = 128
PIPELINE_SELECTORS = ('clicks_artifact', 'pitch_artifact', 'meter_artifact',
                      'tonal_artifact', 'comparisons_artifact')
CALIBRATION_TOOLS = {'pitch_evaluate': 5_000_000, 'phrase_evaluate': 20_000_000}
SUPPORTED_SCHEMA_KEYS = {'type', 'properties', 'required', 'additionalProperties', 'enum',
                         'minimum', 'maximum', 'exclusiveMinimum', 'minLength', 'maxLength', 'description', 'default'}
OUTPUT_SCHEMA = {'type': 'object', 'properties': {
    'schema_version': {'type': 'integer', 'enum': [1]},
    'tool': {'type': 'string'}, 'status': {'type': 'string', 'enum': ['completed']},
    'evidence_kind': {'type': 'string'}, 'implementation_status': {'type': 'string'},
    'instrument_context': {'type': 'object'}, 'result': {'type': 'object'},
    'limitations': {'type': 'array', 'items': {'type': 'string'}}, 'skill': {'type': 'string'}},
    'required': ['schema_version', 'tool', 'status', 'evidence_kind', 'implementation_status',
                 'instrument_context', 'result', 'limitations', 'skill'],
    'additionalProperties': False}


class ToolError(RuntimeError):
    """Execution failure returned as MCP isError, not a protocol failure."""
    def __init__(self, message, receipt=None):
        super().__init__(message)
        self.receipt = receipt


class ValidationError(ValueError):
    """Invalid invocation returned as JSON-RPC invalid params."""


def strict_json(text):
    # CPython JSON recursion behavior differs across releases. Enforce a portable
    # nesting bound before parsing; punctuation inside quoted strings is data.
    depth = 0
    quoted = False
    escaped = False
    for character in text:
        if quoted:
            if escaped:
                escaped = False
            elif character == '\\':
                escaped = True
            elif character == '"':
                quoted = False
        elif character == '"':
            quoted = True
        elif character in '[{':
            depth += 1
            if depth > MAX_JSON_NESTING:
                raise ValueError(f'JSON nesting exceeds {MAX_JSON_NESTING} levels')
        elif character in ']}':
            depth -= 1
    def reject_constant(value):
        raise ValueError(f'non-finite JSON number: {value}')
    def finite_float(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError('JSON exponent produces a non-finite number')
        return parsed
    try:
        return json.loads(text, parse_constant=reject_constant, parse_float=finite_float)
    except RecursionError as error:
        raise ValueError('JSON nesting exceeds parser limits') from error


def validate_schema(schema):
    """Fail closed if future registry authors add unsupported validation keywords."""
    unknown = set(schema) - SUPPORTED_SCHEMA_KEYS
    if unknown:
        raise ValueError(f'unsupported input schema keys: {sorted(unknown)}')
    kind = schema.get('type')
    if kind not in {'object', 'string', 'number', 'integer', 'boolean'}:
        raise ValueError(f'unsupported input schema type: {kind}')
    if kind == 'object':
        if schema.get('additionalProperties') is not False:
            raise ValueError('input object schemas must reject additionalProperties')
        props = schema.get('properties', {})
        if not isinstance(props, dict) or not set(schema.get('required', [])) <= set(props):
            raise ValueError('invalid object schema properties/required')
        for child in props.values():
            validate_schema(child)


def load_registry():
    registry = strict_json(REGISTRY.read_text(encoding='utf-8'))
    if registry.get('schema_version') != 1:
        raise ValueError('unsupported tool registry version')
    names = []
    for descriptor in registry['tools']:
        validate_schema(descriptor['inputSchema'])
        names.append(descriptor['name'])
        skill = (ROOT / descriptor['skill']).resolve()
        if not skill.is_relative_to(ROOT / '.agents' / 'skills') or skill.name != 'SKILL.md':
            raise ValueError('tool skill must be a repository-local SKILL.md')
    if len(names) != len(set(names)):
        raise ValueError('duplicate tool names')
    return registry


def descriptors():
    return load_registry()['tools']


def descriptor(name):
    match = next((item for item in descriptors() if item['name'] == name), None)
    if match is None:
        raise ValidationError(f'unknown tool: {name}')
    return match



def finite_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def validate(value, schema, label='arguments'):
    kind = schema['type']
    checks = {'object': lambda x: isinstance(x, dict), 'string': lambda x: isinstance(x, str),
              'boolean': lambda x: isinstance(x, bool),
              'integer': lambda x: isinstance(x, int) and not isinstance(x, bool),
              'number': finite_number}
    if not checks[kind](value):
        raise ValidationError(f'{label} must be {kind}')
    if 'enum' in schema and value not in schema['enum']:
        raise ValidationError(f'{label} must be one of {schema["enum"]}')
    if kind == 'object':
        props = schema.get('properties', {})
        extra = set(value) - set(props)
        if extra:
            raise ValidationError(f'{label} contains unknown keys: {sorted(extra)}')
        missing = set(schema.get('required', [])) - set(value)
        if missing:
            raise ValidationError(f'{label} requires: {sorted(missing)}')
        for key, child in value.items():
            validate(child, props[key], f'{label}.{key}')
    elif kind == 'string':
        if '\0' in value:
            raise ValidationError(f'{label} contains NUL')
        for key, predicate in [('minLength', lambda x: len(value) >= x),
                               ('maxLength', lambda x: len(value) <= x)]:
            if key in schema and not predicate(schema[key]):
                raise ValidationError(f'{label} violates {key}')
    elif kind in {'number', 'integer'}:
        if 'minimum' in schema and value < schema['minimum']:
            raise ValidationError(f'{label} is below minimum')
        if 'exclusiveMinimum' in schema and value <= schema['exclusiveMinimum']:
            raise ValidationError(f'{label} must exceed exclusiveMinimum')
        if 'maximum' in schema and value > schema['maximum']:
            raise ValidationError(f'{label} is above maximum')


def local_path(value, must_exist=False, directory=False):
    path = Path(value).expanduser().resolve()
    if must_exist and not (path.is_dir() if directory else path.is_file()):
        raise ToolError(f'local {"directory" if directory else "file"} is unavailable: {path}')
    if directory and path.exists() and not path.is_dir():
        raise ToolError(f'run_dir is not a directory: {path}')
    return str(path)


def validate_evidence_selector(value):
    """An exact run-relative JSON identifier, never a URL or normalized path."""
    parts = value.split('/')
    if (value.startswith('/') or ':' in value or '\\' in value
            or any(not part or part.startswith('.') or '.partial' in part for part in parts)
            or not value.endswith('.json')):
        raise ValidationError('pipeline selectors require exact run-relative JSON paths without traversal or staging components')


def selected_evidence_path(directory, value):
    """Check every original component before resolution could hide a symlink."""
    path = Path(directory)
    for part in value.split('/'):
        path = path / part
        if path.is_symlink():
            raise ToolError('pipeline evidence selector cannot contain a symlink component')
    if not path.is_file():
        raise ToolError('pipeline selected evidence must be an existing run-local regular file')
    # Forward the exact relative string. The worker independently validates paths,
    # byte limits and provenance; no wrapper normalization may hide path identity.
    return value


def corpus_worker_paths(args):
    """Preserve unsafe components beneath an explicitly chosen metadata root."""
    original_root = Path(args.get('local_root', str(ROOT))).expanduser().absolute()
    if original_root.is_symlink() or not original_root.is_dir():
        raise ToolError('corpus local_root must be an existing directory, not a symlink')
    root = original_root.resolve()
    original_manifest = Path(args['manifest']).expanduser().absolute()
    try:
        relative = original_manifest.relative_to(original_root)
    except ValueError:
        try:
            relative = original_manifest.relative_to(root)
        except ValueError as error:
            raise ToolError('corpus manifest must remain inside local_root') from error
    path = root
    for part in relative.parts:
        if part == '..':
            raise ValidationError('corpus manifest cannot contain traversal components')
        path = path / part
        if path.is_symlink():
            raise ToolError('corpus manifest cannot contain a symlink component')
    if not path.is_file():
        raise ToolError('corpus manifest must be an existing regular metadata file')
    return str(path), str(root)


def calibration_path(value, *, output=False, max_bytes=None):
    """Exact safe local index/output paths under the repository benchmark root."""
    try:
        path = Path(value).expanduser().absolute()
    except (RuntimeError, OSError) as error:
        raise ToolError('calibration path cannot be expanded to a local path') from error
    boundary = ROOT / 'artifacts' / 'benchmarks'
    try:
        relative = path.relative_to(boundary)
    except ValueError as error:
        raise ToolError('calibration paths must remain beneath repository artifacts/benchmarks') from error
    if not relative.parts:
        raise ToolError('calibration path must name a child of artifacts/benchmarks')
    candidate = ROOT
    for part in path.relative_to(ROOT).parts:
        candidate = candidate / part
        if candidate.is_symlink():
            raise ToolError('calibration paths cannot contain a symlink component')
        if candidate != path and candidate.exists() and not candidate.is_dir():
            raise ToolError('calibration path parents must be directories')
    if output:
        if path.exists():
            raise ToolError('calibration output must be a new directory')
    elif not path.is_file():
        raise ToolError('calibration index must be an existing regular JSON file')
    elif max_bytes is not None:
        try:
            size = path.stat().st_size
        except OSError as error:
            raise ToolError('calibration index became unavailable before launch') from error
        if size > max_bytes:
            raise ToolError('calibration index exceeds worker metadata byte limit')
    return str(path)


def marked_video_directory(value, *, output=False):
    """Repository-relative preview paths; inspect original components first."""
    if '\\' in value or '..' in value.split('/'):
        raise ValidationError('marked video directories cannot contain traversal or backslash components')
    try:
        path = Path(value).expanduser()
    except (RuntimeError, OSError) as error:
        raise ToolError('marked video directory cannot be expanded') from error
    if not path.is_absolute():
        path = ROOT / path
    boundary = ROOT / 'artifacts' / 'runs'
    try:
        relative = path.relative_to(boundary)
    except ValueError as error:
        raise ToolError('marked video directories must remain beneath repository artifacts/runs') from error
    if not relative.parts:
        raise ToolError('marked video directory must name a child of artifacts/runs')
    candidate = ROOT
    for part in path.relative_to(ROOT).parts:
        candidate = candidate / part
        if candidate.is_symlink():
            raise ToolError('marked video directories cannot contain a symlink component')
        if candidate != path and candidate.exists() and not candidate.is_dir():
            raise ToolError('marked video directory parents must be directories')
    if output:
        if path.exists():
            raise ToolError('marked video output must be a fresh directory')
    elif not path.is_dir():
        raise ToolError('marked video run_dir must be an existing directory')
    return str(path)



def validate_tool_arguments(name, args):
    """Cross-field rules that are known before a worker or file read starts."""
    if name == 'review':
        operation = args.get('operation', 'read')
        if operation == 'read' and 'input' in args:
            raise ValidationError('review input is accepted only for operation write')
        if operation == 'write' and 'input' not in args:
            raise ValidationError('review operation write requires input request JSON file')
    if name == 'benchmark' and args.get('operation', 'run') == 'fixtures':
        if any(key in args for key in ('profile', 'phrase_backend')):
            raise ValidationError('benchmark profile/phrase_backend apply only to operation run')
    if name == 'pipeline':
        for field in PIPELINE_SELECTORS:
            if field in args:
                validate_evidence_selector(args[field])
    if name == 'corpus' and any(part == '..' for part in args['manifest'].split('/')):
        raise ValidationError('corpus manifest cannot contain traversal components')
    if name == 'marked_video':
        for field in ('run_dir', 'output'):
            if '\\' in args[field] or '..' in args[field].split('/'):
                raise ValidationError('marked video directories cannot contain traversal or backslash components')
    if name in CALIBRATION_TOOLS:
        for field in ('fixture_index', 'pilot_index', 'output'):
            value = args[field]
            parts = value.split('/')
            if value.startswith('/'):
                parts = parts[1:]
            if (':' in value or '\\' in value or any(not part or part.startswith('.') or '.partial' in part for part in parts)
                    or (field != 'output' and not value.endswith('.json'))):
                raise ValidationError('calibration paths require exact JSON indices and a fresh safe local output path')
    if name == 'clicks':
        supplied = ('template_start' in args, 'template_end' in args)
        if supplied[0] != supplied[1]:
            raise ValidationError('click template_start and template_end must be supplied together')
        if all(supplied):
            duration = args['template_end'] - args['template_start']
            if not .005 <= duration <= .120 + 1e-10:
                raise ValidationError('click template duration must be 5–120 ms')
        if args.get('attenuate') and (not all(supplied) or not args.get('template_click_only')):
            raise ValidationError('click attenuation requires a template and explicit click-only declaration')


def worker_command(name, args):
    """Only fixed scripts and individual validated arguments, never a shell."""
    interpreter = os.environ.get('VIDEO_UTILS_PYTHON', sys.executable)
    if (name in {'clicks', 'pitch'} or args.get('backend') == 'librosa'
            or args.get('phrase_backend') == 'librosa'):
        interpreter = os.environ.get('VIDEO_UTILS_ANALYSIS_PYTHON', interpreter)
    head = [interpreter]
    source = local_path(args['input'], must_exist=True) if 'input' in args else None
    if name == 'probe':
        return head + [str(ROOT / 'scripts/media.py'), 'probe', source]
    if name == 'corpus':
        manifest, root = corpus_worker_paths(args)
        return head + [str(ROOT / 'scripts/corpus.py'), 'validate', manifest,
                       '--root', root, '--summary']
    if name == 'marked_video':
        return head + [str(ROOT / 'scripts/marked_video.py'),
                       '--run-dir', marked_video_directory(args['run_dir']),
                       '--selection', args.get('selection', 'phrase-review'),
                       '--output', marked_video_directory(args['output'], output=True)]
    if name in CALIBRATION_TOOLS:
        return head + [str(ROOT / ('scripts/' + name + '.py')),
                       '--fixture-index', calibration_path(args['fixture_index'], max_bytes=CALIBRATION_TOOLS[name]),
                       '--pilot-index', calibration_path(args['pilot_index'], max_bytes=CALIBRATION_TOOLS[name]),
                       '--output', calibration_path(args['output'], output=True), '--summary']
    if name == 'denoise':
        return head + [str(ROOT / 'scripts/media.py'), 'clean', source, args.get('profile', 'conservative3')]
    if name == 'benchmark':
        operation = args.get('operation', 'run')
        output = local_path(args['output'], directory=True)
        command = head + [str(ROOT / 'scripts/benchmark.py'), operation, '--output', output]
        if 'suite' in args:
            command += ['--suite', args['suite']]
        if operation == 'run':
            command += ['--profile', args.get('profile', 'conservative3'),
                        '--phrase-backend', args.get('phrase_backend', 'stdlib')]
        return command
    if name == 'review':
        operation = args.get('operation', 'read')
        directory = local_path(args['run_dir'], must_exist=True, directory=True)
        command = head + [str(ROOT / 'scripts/review_server.py'),
                          'annotate' if operation == 'write' else 'annotations', directory]
        if operation == 'write':
            command += ['--input', source]
        return command
    if name == 'phrase_compare':
        directory = local_path(args['run_dir'], must_exist=True, directory=True)
        command = head + [str(ROOT / 'scripts/phrase_compare.py'), directory]
        for field in ('max_pairs', 'band_fraction', 'min_rate', 'max_rate'):
            if field in args:
                command += ['--' + field.replace('_', '-'), str(args[field])]
        return command
    if name == 'tonal':
        directory = local_path(args['run_dir'], must_exist=True, directory=True)
        command = head + [str(ROOT / 'scripts/tonal.py'), directory]
        for field in ('max_regions', 'max_recurrences'):
            if field in args:
                command += ['--' + field.replace('_', '-'), str(args[field])]
        return command
    if name == 'meter':
        directory = local_path(args['run_dir'], must_exist=True, directory=True)
        return head + [str(ROOT / 'scripts/meter.py'), '--run-dir', directory]
    if name == 'pitch':
        directory = local_path(args['run_dir'], directory=True)
        command = head + [str(ROOT / 'scripts/pitch.py'), source, '--run-dir', directory,
                          '--max-analysis-seconds', str(args.get('max_analysis_seconds', 20))]
        if 'start_seconds' in args:
            command += ['--start-seconds', str(args['start_seconds'])]
        return command
    if name == 'clicks':
        directory = local_path(args['run_dir'], directory=True)
        command = head + [str(ROOT / 'scripts/clicks.py'), source, '--run-dir', directory]
        for field in ('bpm', 'template_start', 'template_end', 'strength'):
            if field in args:
                command += ['--' + field.replace('_', '-'), str(args[field])]
        for field in ('attenuate', 'template_click_only'):
            if args.get(field):
                command += ['--' + field.replace('_', '-')]
        return command
    if name in {'export', 'report', 'pipeline', 'markers'}:
        directory = local_path(args['run_dir'], must_exist=True, directory=True)
        if name == 'export':
            return head + [str(ROOT / 'scripts/media.py'), 'export', directory]
        if name == 'pipeline':
            command = head + [str(ROOT / 'scripts/dag.py'), directory]
            if 'reference' in args:
                command += ['--reference', local_path(args['reference'], must_exist=True)]
            for field in PIPELINE_SELECTORS:
                if field in args:
                    command += ['--' + field.replace('_', '-'),
                                selected_evidence_path(directory, args[field])]
            return command
        if name == 'markers':
            return head + [str(ROOT / 'scripts/markers.py'), directory]
        return head + [str(ROOT / 'scripts/report.py'), directory]
    directory = local_path(args['run_dir'], directory=True)
    if name in {'bpm', 'rhythm'}:
        command = head + [str(ROOT / 'scripts/rhythm.py'), source, '--run-dir', directory,
                          '--backend', args.get('backend', 'stdlib')]
        if 'bpm' in args:
            command += ['--bpm', str(args['bpm'])]
        return command
    if name in {'noise', 'tone', 'notes', 'phrases'}:
        command = head + [str(ROOT / 'scripts/guitar_features.py'), name, source, '--run-dir', directory]
        if name == 'phrases':
            command += ['--backend', args.get('backend', 'stdlib')]
            if 'bpm' in args:
                command += ['--bpm', str(args['bpm'])]
        return command
    raise ToolError('tool has no allowlisted worker')


def run_worker(command, timeout):
    if not Path(command[1]).is_file():
        raise ToolError('implementation worker is unavailable; no analysis was performed')
    # File-backed output avoids allocating all worker logs in memory. Workers are fixed,
    # repository-controlled code; accepted result size is bounded below.
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        try:
            process = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.DEVNULL,
                                       stdout=stdout, stderr=stderr, start_new_session=True)
        except OSError as error:
            raise ToolError(f'worker could not start: {error}') from error
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired as error:
            # This new process group was created and recorded by this invocation.
            # Inspect actual pgid before signalling only our owned worker descendants.
            prior_group = None
            signal_target = 'already_exited'
            try:
                prior_group = os.getpgid(process.pid)
                if prior_group == process.pid:
                    os.killpg(process.pid, signal.SIGKILL)
                    signal_target = 'owned_process_group'
                else:
                    process.kill()
                    signal_target = 'owned_worker_only'
            except ProcessLookupError:
                pass
            process.wait()
            receipt = {'actor': 'video-utils/tool_api',
                       'target_ownership': {'pid': process.pid, 'observed_pgid': prior_group,
                                            'created_by_invocation': True,
                                            'new_session_requested': True},
                       'reason': f'worker hard deadline exceeded ({timeout}s)',
                       'ruling': 'R-N11; R-HOOK-CONVERGENCE-20261004; TIN-3692 98cf680c-7299-4949-bfb2-60079053ad43',
                       'prior_state': 'owned worker wait timed out; live pgid checked before signal',
                       'result': {'signal_target': signal_target, 'worker_returncode': process.returncode}}
            raise ToolError(f'worker deadline exceeded ({timeout}s); owned process group stopped', receipt) from error
        stdout.seek(0, os.SEEK_END)
        if stdout.tell() > MAX_WORKER_OUTPUT:
            raise ToolError('worker result exceeds 2 MiB result limit; inspect local artifacts')
        stderr.seek(0, os.SEEK_END)
        stderr_size = stderr.tell()
        stderr.seek(max(0, stderr_size - 2500))
        error_tail = stderr.read().decode('utf-8', errors='replace')
        if process.returncode:
            raise ToolError(f'worker failed ({process.returncode}): {error_tail}')
        stdout.seek(0)
        try:
            result = strict_json(stdout.read().decode('utf-8'))
        except (UnicodeError, ValueError) as error:
            raise ToolError('worker did not return a single finite JSON object') from error
        if not isinstance(result, dict):
            raise ToolError('worker result must be a JSON object')
        return result


def execute(name, arguments):
    info = descriptor(name)
    validate(arguments, info['inputSchema'])
    validate_tool_arguments(name, arguments)
    timeout = arguments.get('timeout_seconds',
                            info['inputSchema']['properties'].get('timeout_seconds', {}).get('default', 600))
    result = run_worker(worker_command(name, arguments), timeout)
    return {'schema_version': 1, 'tool': name, 'status': 'completed',
            'evidence_kind': info['evidence_kind'], 'implementation_status': info['implementation_status'],
            'instrument_context': load_registry()['instrument_context'], 'result': result,
            'limitations': info['limitations'], 'skill': info['skill']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('list')
    show = commands.add_parser('describe'); show.add_argument('name')
    invoke = commands.add_parser('run'); invoke.add_argument('name')
    invoke.add_argument('--arguments', required=True, help='JSON object matching program/tools.json')
    args = parser.parse_args(argv)
    try:
        if args.command == 'list':
            result = load_registry()
        elif args.command == 'describe':
            result = descriptor(args.name)
        else:
            result = execute(args.name, strict_json(args.arguments))
        print(json.dumps(result, allow_nan=False, indent=2))
    except (ToolError, ValueError, OSError) as error:
        print(json.dumps(dict({'status': 'error', 'error': str(error)}, **({'receipt': error.receipt} if isinstance(error, ToolError) and error.receipt else {})), allow_nan=False), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
