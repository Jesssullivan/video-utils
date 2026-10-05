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
SUPPORTED_SCHEMA_KEYS = {'type', 'properties', 'required', 'additionalProperties', 'enum',
                         'minimum', 'maximum', 'minLength', 'maxLength', 'description', 'default'}
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
        if 'maximum' in schema and value > schema['maximum']:
            raise ValidationError(f'{label} is above maximum')


def local_path(value, must_exist=False, directory=False):
    path = Path(value).expanduser().resolve()
    if must_exist and not (path.is_dir() if directory else path.is_file()):
        raise ToolError(f'local {"directory" if directory else "file"} is unavailable: {path}')
    if directory and path.exists() and not path.is_dir():
        raise ToolError(f'run_dir is not a directory: {path}')
    return str(path)


def worker_command(name, args):
    """Only fixed scripts and individual validated arguments, never a shell."""
    interpreter = os.environ.get('VIDEO_UTILS_PYTHON', sys.executable)
    if args.get('backend') == 'librosa':
        interpreter = os.environ.get('VIDEO_UTILS_ANALYSIS_PYTHON', interpreter)
    head = [interpreter]
    source = local_path(args['input'], must_exist=True) if 'input' in args else None
    if name == 'probe':
        return head + [str(ROOT / 'scripts/media.py'), 'probe', source]
    if name == 'denoise':
        return head + [str(ROOT / 'scripts/media.py'), 'clean', source, args.get('profile', 'conservative3')]
    if name in {'export', 'report', 'pipeline', 'markers'}:
        directory = local_path(args['run_dir'], must_exist=True, directory=True)
        if name == 'export':
            return head + [str(ROOT / 'scripts/media.py'), 'export', directory]
        if name == 'pipeline':
            command = head + [str(ROOT / 'scripts/dag.py'), directory]
            if 'reference' in args:
                command += ['--reference', local_path(args['reference'], must_exist=True)]
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
    timeout = arguments.get('timeout_seconds', 600)
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
