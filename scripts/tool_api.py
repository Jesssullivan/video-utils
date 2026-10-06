#!/usr/bin/env python3
"""Validated local tool registry and bounded allowlist dispatcher (stdlib only)."""
from __future__ import annotations

import argparse
import hashlib
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
LEARNED_EVALUATION_FIELDS = ('fixture_index', 'pyin_pilot_index', 'learned_pilot_index', 'output')
# S2 metadata projections write only fresh outputs beneath this repository boundary.
S2_OUTPUT_ROOT = ROOT / 'artifacts'
S2_EXACT_PATH_FIELDS = {'annotation_markers': ('run_dir', 'output_dir'),
                        'flags_triage': ('run_dir', 'output'),
                        'corpus_eval_s2': ('manifest', 'local_root', 'proposals', 'output'),
                        'marked_compact': ('run_dir', 'picture_preview', 'output'),
                        'phrase_timing': ('analysis', 'phrases', 'output_root'),
                        'tone_ab': ('run_dir', 'candidate_run_dir'),
                        'report_bundle': ('run_dir', 'analysis_run_dir', 'annotation_store')}
PHRASE_TIMING_MAX_INPUT_BYTES = 64 * 1024 * 1024
# report_bundle: the worker always writes a fresh default directory here (no output field) and
# refuses with exit 2 and one stable reason code; exit 1 reports an exception class name only.
REPORT_BUNDLE_OUTPUT_ROOT = ROOT / 'artifacts' / 's2' / 'report_d6' / 'bundles'
REPORT_BUNDLE_MAX_STORE_BYTES = 64 * 1024 * 1024
REPORT_BUNDLE_MEDIA_SUFFIXES = frozenset({'.wav', '.flac', '.aiff', '.aif', '.mp3', '.aac', '.m4a', '.mov', '.mp4',
                                          '.m4v', '.mkv', '.webm', '.caf'})
S2_DIGEST_FIELDS = {'annotation_markers': 'store_sha256', 'corpus_eval_s2': 'proposals_sha256'}
SUPPORTED_SCHEMA_KEYS = {'type', 'properties', 'required', 'additionalProperties', 'enum',
                         'minimum', 'maximum', 'exclusiveMinimum', 'minLength', 'maxLength', 'description', 'default',
                         'items', 'minItems', 'maxItems'}
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
    if kind not in {'object', 'string', 'number', 'integer', 'boolean', 'array'}:
        raise ValueError(f'unsupported input schema type: {kind}')
    if kind != 'array' and set(schema) & {'items', 'minItems', 'maxItems'}:
        raise ValueError('array validation keywords require array type')
    if kind == 'object':
        if schema.get('additionalProperties') is not False:
            raise ValueError('input object schemas must reject additionalProperties')
        props = schema.get('properties', {})
        if not isinstance(props, dict) or not set(schema.get('required', [])) <= set(props):
            raise ValueError('invalid object schema properties/required')
        for child in props.values():
            validate_schema(child)
    elif kind == 'array':
        low, high = schema.get('minItems', 0), schema.get('maxItems')
        if (isinstance(low, bool) or isinstance(high, bool) or not isinstance(low, int)
                or not isinstance(high, int) or not 0 <= low <= high <= 128 or 'items' not in schema):
            raise ValueError('input arrays require bounded items and maxItems <=128')
        validate_schema(schema['items'])


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
              'array': lambda x: isinstance(x, list),
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
    elif kind == 'array':
        if not schema.get('minItems', 0) <= len(value) <= schema['maxItems']:
            raise ValidationError(f'{label} violates bounded array length')
        for index, child in enumerate(value):
            validate(child, schema['items'], f'{label}[{index}]')
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


def annotation_v2_paths(args):
    """Preserve exact components before opening source-bound metadata."""
    selected = {}
    for field in ('run_dir', 'input'):
        if field not in args:
            continue
        value = args[field]
        if ('\x00' in value or ':' in value or '\\' in value or '..' in value.split('/')):
            raise ValidationError('annotation paths require exact local components')
        try:
            original = Path(value).expanduser().absolute()
        except (OSError, RuntimeError) as error:
            raise ToolError('annotation path is unavailable') from error
        current = Path(original.anchor)
        for part in original.parts[1:]:
            current = current / part
            if current.is_symlink():
                raise ToolError('annotation paths cannot contain symlink components')
        if field == 'run_dir':
            if not original.is_dir():
                raise ToolError('annotation run_dir must be an existing directory')
        elif not original.is_file() or original.stat().st_size > 20000:
            raise ToolError('annotation request must be a regular JSON file<=20000bytes')
        selected[field] = str(original)
    return selected


def corpus_split_paths(args):
    """Check every supplied ancestor before legacy corpus normalization."""
    for value in (args['manifest'], args.get('local_root', str(ROOT))):
        if ('\x00' in value or ':' in value or '\\' in value or '..' in value.split('/')):
            raise ValidationError('corpus split paths require exact local components')
        original = Path(value).expanduser().absolute()
        current = Path(original.anchor)
        for part in original.parts[1:]:
            current = current / part
            if current.is_symlink():
                raise ToolError('corpus split paths cannot contain symlink components')
    return corpus_worker_paths(args)


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


def basic_pitch_directory(value):
    """Bound the current run before model work; the worker verifies hashes."""
    directory = Path(marked_video_directory(value))
    for name, ceiling in (('manifest.json', 1_048_576), ('denoised.wav', 1_073_741_824)):
        path = directory / name
        if path.is_symlink() or not path.is_file():
            raise ToolError('Basic Pitch requires regular non-symlink manifest.json and denoised.wav')
        if path.stat().st_size > ceiling:
            raise ToolError('Basic Pitch input artifact exceeds preflight byte bound')
    return str(directory)


def capture_profile_paths(args):
    """Keep the selected original and review component identity until checked."""
    directory = Path(marked_video_directory(args['run_dir']))
    paths = {}
    for field, ceiling in (('input', 3 * 1024**3), ('review', 16 * 1024)):
        try:
            path = Path(args[field]).expanduser()
        except (OSError, RuntimeError) as error:
            raise ToolError('capture profile path cannot be expanded') from error
        if not path.is_absolute():
            path = ROOT / path
        cursor = Path(path.anchor)
        for part in path.parts[1:]:
            cursor /= part
            if cursor.is_symlink():
                raise ToolError('capture profile paths cannot contain symlink components')
        if not path.is_file() or path.stat().st_size > ceiling:
            raise ToolError('capture profile input/review is missing or exceeds its byte bound')
        if field == 'review' and not path.is_relative_to(directory):
            raise ToolError('capture profile review must remain beneath the verified run')
        paths[field] = str(path)
    for name, ceiling in (('manifest.json', 1024**2), ('source.wav', 1024**3)):
        path = directory / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > ceiling:
            raise ToolError('capture profile requires bounded regular manifest.json and source.wav')
    return paths['input'], str(directory), paths['review']


def editor_marker_inputs(args):
    """Three explicit bounded metadata inputs; profile semantics belong to worker."""
    try:
        directory = Path(marked_video_directory(args['run_dir']))
    except ToolError as error:
        raise ToolError('editor marker run_dir: ' + str(error)) from error
    for value in (args['selection'], args['profile']):
        selected_evidence_path(directory, value)
    for name in ('manifest.json', 'flags.json', 'markers.json', args['selection'], args['profile']):
        path = directory / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 20_000_000:
            raise ToolError('editor marker inputs must be bounded regular run-local JSON files')
    return str(directory)


def capture_application_paths(args):
    """Explicit authoring artifact identity; semantic provenance stays in worker."""
    from capture_profile import safe_path, CaptureError
    try:
        source_path = Path(args['input']).expanduser()
        author_path = Path(args['authoring_dir']).expanduser()
        original = safe_path(source_path if source_path.is_absolute() else ROOT / source_path)
        authored = safe_path(author_path if author_path.is_absolute() else ROOT / author_path, directory=True)
        if original.stat().st_size > 3 * 1024**3:
            raise ToolError('capture application original exceeds3GiB')
        boundary = ROOT / 'artifacts/runs'
        if (not authored.is_relative_to(boundary) or authored.parent.name != 'capture-profiles'
                or authored.parent.parent == boundary):
            raise ToolError('capture application authoring_dir must name an explicit run/capture-profiles/ID')
        for name, bound in (('receipt.json',64*1024), ('profile.json',16*1024)):
            selected = safe_path(authored / name)
            if selected.stat().st_size > bound: raise ToolError('capture application authoring metadata exceeds byte bound')
    except (CaptureError, OSError, ValueError, RuntimeError) as error:
        raise ToolError('capture application requires bounded regular source/authoring artifacts: '+str(error)) from error
    return dict(args, input=str(original), authoring_dir=str(authored))


def arrangement_reference_paths(args):
    """Public assessment stays inside its explicit verified source run."""
    from capture_profile import safe_path
    directory = Path(marked_video_directory(args['run_dir']))
    try:
        reference = Path(args.get('reference','program/demo-arrangement.json')).expanduser()
        reference = safe_path(reference if reference.is_absolute() else ROOT / reference)
    except (ValueError,OSError,RuntimeError) as error: raise ToolError('bounded local arrangement reference required') from error
    if reference.stat().st_size > 64*1024: raise ToolError('arrangement reference exceeds64KiB')
    output = Path(marked_video_directory(args['output'],output=True))
    if not output.is_relative_to(directory) or output == directory:
        raise ToolError('arrangement output must be a fresh child inside the selected run')
    for name,bound in (('manifest.json',1024**2),('analysis.json',16*1024**2),('phrases.json',4*1024**2)):
        try: path = safe_path(directory / name)
        except (ValueError,OSError,RuntimeError) as error: raise ToolError('bounded current arrangement run metadata required') from error
        if path.stat().st_size > bound: raise ToolError('arrangement cached metadata exceeds byte bound')
    return str(reference),str(directory),str(output)


def share_export_paths(args):
    """Sharing candidates are fresh local MP4s; never normalize away symlinks."""
    from capture_profile import safe_path, CaptureError
    try:
        source = Path(args['source']).expanduser()
        source = safe_path(source if source.is_absolute() else ROOT / source)
        if source.stat().st_size > 3 * 1024**3:
            raise ToolError('share export source exceeds3GiB')
        output = Path(args['output']).expanduser()
        if not output.is_absolute(): output = ROOT / output
        parent = safe_path(output.parent, directory=True)
        output = parent / output.name
        receipt = output.with_name(output.name + '.receipt.json')
        if output.suffix.lower() != '.mp4':
            raise ToolError('share export output must name a fresh MP4')
        if output.exists() or output.is_symlink() or receipt.exists() or receipt.is_symlink():
            raise ToolError('share export output and adjacent receipt must both be fresh')
    except (CaptureError, OSError, ValueError, RuntimeError) as error:
        raise ToolError('share export requires bounded regular local source and fresh output: ' + str(error)) from error
    return str(source), str(output)


def s2_original_path(value):
    """Absolute original path (relative values anchor at ROOT) without resolving symlinks."""
    try:
        path = Path(value).expanduser()
    except (RuntimeError, OSError) as error:
        raise ToolError('S2 path cannot be expanded to a local path') from error
    return (path if path.is_absolute() else ROOT / path).absolute()


def s2_reject_symlink_components(path):
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        if current.is_symlink():
            raise ToolError('S2 paths cannot contain symlink components')


def s2_input_directory(value, required):
    """Existing run directory whose named metadata files are regular, non-symlink files."""
    directory = s2_original_path(value)
    s2_reject_symlink_components(directory)
    if not directory.is_dir():
        raise ToolError('S2 run_dir must be an existing directory')
    for name in required:
        path = directory / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 20_000_000:
            raise ToolError('S2 run_dir requires bounded regular ' + name)
    return directory


def s2_input_file(value, max_bytes):
    path = s2_original_path(value)
    s2_reject_symlink_components(path)
    if not path.is_file() or path.stat().st_size > max_bytes:
        raise ToolError('S2 input must be an existing bounded regular file')
    return path


def s2_fresh_output(value, *, suffix=None, outside=()):
    """Fresh path beneath repository artifacts/, existing parent, never inside an input."""
    path = s2_original_path(value)
    boundary = Path(S2_OUTPUT_ROOT)
    try:
        relative = path.relative_to(boundary)
    except ValueError as error:
        raise ToolError('S2 outputs must remain beneath repository artifacts/') from error
    if not relative.parts:
        raise ToolError('S2 output must name a child of repository artifacts/')
    s2_reject_symlink_components(path)
    if not path.parent.is_dir():
        raise ToolError('S2 output parent must be an existing directory')
    if os.path.lexists(path):
        raise ToolError('S2 output must be fresh; nothing is overwritten')
    if suffix is not None and path.suffix != suffix:
        raise ToolError('S2 output must name a fresh ' + suffix + ' file')
    for other in outside:
        other = Path(other)
        if path == other or path.is_relative_to(other) or path.resolve() == other.resolve() \
                or path.resolve().is_relative_to(other.resolve()):
            raise ToolError('S2 output must remain outside its inputs')
    return path


def s2_output_relative(value):
    """Original path beneath repository artifacts/ but never artifacts/runs; symlink components reject."""
    path = s2_original_path(value)
    try:
        relative = path.relative_to(Path(S2_OUTPUT_ROOT))
    except ValueError as error:
        raise ToolError('S2 outputs must remain beneath repository artifacts/') from error
    if not relative.parts:
        raise ToolError('S2 output must name a child of repository artifacts/')
    if relative.parts[0] == 'runs':
        raise ToolError('S2 outputs must not be written beneath artifacts/runs')
    s2_reject_symlink_components(path)
    return path


def marked_compact_output(value):
    """Fresh directory; the worker re-validates and also refuses a parent-branch overlap."""
    path = s2_output_relative(value)
    if os.path.lexists(path):
        raise ToolError('marked compact output must be fresh; nothing is overwritten')
    return path


def phrase_timing_paths(args):
    """Bounded regular JSON inputs and an output root that receives a fresh run-id child."""
    inputs = []
    for field in ('analysis', 'phrases'):
        path = s2_input_file(args[field], PHRASE_TIMING_MAX_INPUT_BYTES)
        if path.suffix != '.json':
            raise ToolError('phrase timing ' + field + ' must be an existing .json file')
        inputs.append(path)
    root = s2_output_relative(args['output_root'])
    if os.path.lexists(root) and not root.is_dir():
        raise ToolError('phrase timing output_root must be a directory')
    if not root.exists() and not root.parent.is_dir():
        raise ToolError('phrase timing output_root parent must be an existing directory')
    return inputs[0], inputs[1], root


def editor_marker_export_output(directory, args):
    """Run-local exclusive output named by the exact export-profile digest."""
    profile = Path(directory) / args['profile']
    try:
        digest = hashlib.sha256(profile.read_bytes()).hexdigest()
    except OSError as error:
        raise ToolError('editor marker export profile became unavailable before launch') from error
    output = Path(directory) / ('editor-export-' + args['format'] + '-' + digest[:12])
    if os.path.lexists(output):
        raise ToolError('editor marker export output already exists; nothing is overwritten')
    return str(output)


def validate_tool_arguments(name, args):
    """Cross-field rules that are known before a worker or file read starts."""
    if name == 'share_export':
        if args.get('height', 720) % 2:
            raise ValidationError('share export height must be even')
        for field in ('source', 'output'):
            value = args[field]
            if ('\x00' in value or ':' in value or '\\' in value or '..' in value.split('/')):
                raise ValidationError('share export paths must be exact local paths without traversal/NUL/URL')
    if name == 'apply_capture_profile':
        digest = args['receipt_sha256']
        if any(character not in '0123456789abcdef' for character in digest):
            raise ValidationError('capture application requires exact lowercase hexadecimal receipt_sha256')
        for field in ('input','authoring_dir'):
            value = args[field]
            if ('\x00' in value or '\\' in value or ':' in value
                    or any(part.startswith('.') or '.partial' in part for part in value.split('/') if part)):
                raise ValidationError('capture application requires exact local paths without traversal/NUL/URL')
    if name == 'arrangement_reference':
        for field in ('run_dir','output','reference'):
            if field not in args: continue
            value=args[field]
            if ('\x00' in value or '\\' in value or ':' in value
                    or any(part.startswith('.') or '.partial' in part for part in value.split('/') if part)):
                raise ValidationError('arrangement inputs require exact safe local paths')
    if name in {'review', 'annotation_v2'}:
        operation = args.get('operation', 'read')
        if operation == 'read' and 'input' in args:
            raise ValidationError('review input is accepted only for operation write')
        if operation == 'write' and 'input' not in args:
            raise ValidationError('review operation write requires input request JSON file')
    if name == 'benchmark' and args.get('operation', 'run') == 'fixtures':
        if any(key in args for key in ('profile', 'phrase_backend')):
            raise ValidationError('benchmark profile/phrase_backend apply only to operation run')
    if name == 'capture_profile':
        for field in ('input', 'run_dir', 'review'):
            if '..' in args[field].split('/') or '\\' in args[field] or '://' in args[field]:
                raise ValidationError('capture profile paths must be exact local paths without traversal')
        duration = args['capture_end_seconds'] - args['capture_start_seconds']
        if not .1 - 1e-10 <= duration <= 10 + 1e-10:
            raise ValidationError('capture profile interval must be 0.1–10 seconds')
    if name == 'pipeline':
        for field in PIPELINE_SELECTORS:
            if field in args:
                validate_evidence_selector(args[field])
    if name in S2_EXACT_PATH_FIELDS:
        for field in S2_EXACT_PATH_FIELDS[name]:
            if field not in args:
                continue
            value = args[field]
            if ('\x00' in value or ':' in value or '\\' in value or '..' in value.split('/')):
                raise ValidationError('S2 paths require exact local paths without traversal/NUL/URL')
    if name == 'tone_ab' and args['common_region_end'] - args['common_region_start'] < 45:
        raise ValidationError('tone_ab common region must be at least 45 seconds long')
    if name in S2_DIGEST_FIELDS:
        digest = args[S2_DIGEST_FIELDS[name]]
        if len(digest) != 64 or any(character not in '0123456789abcdef' for character in digest):
            raise ValidationError('S2 pins require an exact lowercase hexadecimal SHA-256')
    if name in {'editor_marker_plan', 'editor_marker_export'}:
        for field in ('selection', 'profile'):
            try:
                validate_evidence_selector(args[field])
            except ValidationError as error:
                raise ValidationError('editor marker selection/profile requires an exact safe run-relative JSON path') from error
        if (args['selection'] == args['profile'] or args['selection'] in {'markers.json', 'manifest.json'}
                or args['profile'] in {'markers.json', 'manifest.json'}):
            raise ValidationError('editor marker selection/profile input roles must be distinct')
        if '\\' in args['run_dir'] or '..' in args['run_dir'].split('/'):
            raise ValidationError('editor marker run_dir cannot contain traversal components')
    if name in {'corpus', 'corpus_split'} and any(part == '..' for part in args['manifest'].split('/')):
        raise ValidationError('corpus manifest cannot contain traversal components')
    if name in {'marked_video', 'basic_pitch_compare'}:
        for field in (('run_dir', 'output') if name == 'marked_video' else ('run_dir',)):
            if '\\' in args[field] or '..' in args[field].split('/'):
                raise ValidationError('marked video directories cannot contain traversal or backslash components')
        if name == 'marked_video' and 'arrangement_markers' in args:
            validate_evidence_selector(args['arrangement_markers'])
            if args.get('selection') != 'all-review':
                raise ValidationError('arrangement markers require explicit selection all-review')
    if name == 'marked_compact':
        validate_evidence_selector(args['arrangement_markers'])
        for field in ('run_dir', 'picture_preview', 'output'):
            if field in args and ('\\' in args[field] or '..' in args[field].split('/')):
                raise ValidationError('marked compact paths cannot contain traversal or backslash components')
    if name in CALIBRATION_TOOLS or name == 'learned_pitch_evaluate':
        fields = LEARNED_EVALUATION_FIELDS if name == 'learned_pitch_evaluate' else ('fixture_index', 'pilot_index', 'output')
        for field in fields:
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
    source = local_path(args['input'], must_exist=True) if 'input' in args and name not in {'capture_profile', 'annotation_v2'} else None
    if name == 'annotation_v2':
        selected = annotation_v2_paths(args)
        command = head + [str(ROOT / 'scripts/annotation_v2.py'), args.get('operation', 'read'), selected['run_dir']]
        if args.get('operation', 'read') == 'write':
            command += ['--input', selected['input']]
        return command
    if name == 'corpus_split':
        manifest, boundary = corpus_split_paths(args)
        return head + [str(ROOT / 'scripts/corpus_split_s1.py'), 'validate', manifest, '--root', boundary, '--summary']
    if name == 'annotation_markers':
        directory = s2_input_directory(args['run_dir'], ('manifest.json', 'review-annotations-v2.json'))
        output = s2_fresh_output(args['output_dir'], outside=(directory,))
        command = head + [str(ROOT / 'scripts/annotation_markers.py'), str(directory),
                          '--store-sha256', args['store_sha256'], '--output-dir', str(output)]
        return command + (['--include-text'] if args.get('include_text') is True else [])
    if name == 'flags_triage':
        directory = s2_input_directory(args['run_dir'], ('flags.json',))
        output = s2_fresh_output(args['output'], suffix='.json', outside=(directory,))
        return head + [str(ROOT / 'scripts/flags_triage.py'), str(directory), '--output', str(output)]
    if name == 'tone_ab':
        # No output field: the worker writes only a fresh ROOT/artifacts/s2/tone_ab/<run_id>-<UTC>/ and
        # refuses any output inside a run directory or artifacts/runs/*; inputs are read only.
        directory = s2_input_directory(args['run_dir'], ('manifest.json',))
        command = head + [str(ROOT / 'scripts/tone_ab.py'), 'run', '--run-dir', str(directory),
                          '--common-region-start', repr(float(args['common_region_start'])),
                          '--common-region-end', repr(float(args['common_region_end'])),
                          '--timeout-seconds', str(args.get('timeout_seconds', 1200))]
        if 'candidate_run_dir' in args:
            candidate = s2_input_directory(args['candidate_run_dir'], ('manifest.json',))
            if candidate == directory:
                raise ToolError('tone_ab candidate_run_dir must differ from run_dir')
            command += ['--candidate-run-dir', str(candidate)]
        return command
    if name == 'report_bundle':
        # Fixed argv only: no --output-dir passthrough, so the worker writes only a fresh
        # ROOT/artifacts/s2/report_d6/bundles/<run_id>-<UTC>/ and never writes the run directories.
        directory = s2_input_directory(args['run_dir'], ('manifest.json',))
        command = head + [str(ROOT / 'scripts/report_bundle.py'), 'build', '--run-dir', str(directory)]
        if 'analysis_run_dir' in args:
            analysis = s2_input_directory(args['analysis_run_dir'], ('manifest.json',))
            command += ['--analysis-run-dir', str(analysis)]
        if 'annotation_store' in args:
            store = s2_input_file(args['annotation_store'], REPORT_BUNDLE_MAX_STORE_BYTES)
            if store.suffix != '.json':
                raise ToolError('report_bundle annotation_store must be a JSON file')
            command += ['--annotation-store', str(store)]
        return command
    if name == 'corpus_eval_s2':
        manifest, boundary = corpus_split_paths(args)
        proposals = s2_input_file(args['proposals'], 20_000_000)
        output = s2_fresh_output(args['output'], suffix='.json', outside=(proposals, proposals.parent))
        return head + [str(ROOT / 'scripts/corpus_eval_s2.py'), 'evaluate', manifest, '--root', boundary,
                       '--proposals', str(proposals), '--proposals-sha256', args['proposals_sha256'],
                       '--output', str(output)]
    if name == 'editor_marker_export':
        directory = editor_marker_inputs(args)
        # No DTD, output path or argv passthrough: MCP exports always record
        # dtd_validation not_performed and write only the digest-named child.
        return head + [str(ROOT / 'scripts/editor_marker_export.py'), directory, args['selection'],
                       args['profile'], '--format', args['format'],
                       '--output-dir', editor_marker_export_output(directory, args), '--summary']
    if name == 'share_export':
        original, output = share_export_paths(args)
        command = head + [str(ROOT / 'scripts/share_export.py'), original, output]
        for field, default in (('height', 720), ('crf', 27), ('audio_kbps', 96),
                               ('codec', 'h264'), ('timeout_seconds', 900)):
            command += ['--' + field.replace('_', '-'), str(args.get(field, default))]
        # The worker derives D-10 internally. Pass public D once, unchanged.
        return command + ['--tool-envelope']
    if name == 'capture_profile':
        original, directory, review = capture_profile_paths(args)
        command = head + [str(ROOT / 'scripts/capture_profile.py'), original, '--run-dir', directory, '--review', review]
        for field, flag in (('capture_start_seconds', 'capture-start'), ('capture_end_seconds', 'capture-end'),
                            ('reduction_db', 'reduction-db'), ('noise_floor_db', 'noise-floor-db'),
                            ('adaptivity', 'adaptivity'), ('gain_smooth', 'gain-smooth'),
                            ('integrated_lufs', 'integrated-lufs'), ('true_peak_dbtp', 'true-peak-dbtp')):
            command += ['--' + flag, str(args[field])]
        command += ['--timeout-seconds', str(args.get('timeout_seconds', 60))]
        for band in args.get('peaking_eq', []):
            command += ['--eq', str(band['frequency_hz']), str(band['gain_db']), str(band['q'])]
        for field, value in args.get('compressor', {}).items():
            command += ['--compressor-' + field.replace('_', '-'), str(value)]
        return command
    if name == 'probe':
        return head + [str(ROOT / 'scripts/media.py'), 'probe', source]
    if name == 'corpus':
        manifest, root = corpus_worker_paths(args)
        return head + [str(ROOT / 'scripts/corpus.py'), 'validate', manifest,
                       '--root', root, '--summary']
    if name == 'marked_video':
        directory = marked_video_directory(args['run_dir'])
        command = head + [str(ROOT / 'scripts/marked_video.py'),
                       '--run-dir', directory,
                       '--selection', args.get('selection', 'phrase-review'),
                       '--output', marked_video_directory(args['output'], output=True)]
        if 'arrangement_markers' in args:
            relative = selected_evidence_path(directory,args['arrangement_markers'])
            if (Path(directory)/relative).stat().st_size > 4*1024**2: raise ToolError('arrangement marker JSON exceeds4MiB')
            command += ['--arrangement-markers',relative]
        return command
    if name == 'marked_compact':
        command = head + [str(ROOT / 'scripts/marked_compact.py'), marked_video_directory(args['run_dir']),
                          '--picture-preview', marked_video_directory(args['picture_preview']),
                          '--arrangement-markers', args['arrangement_markers'],
                          '--timeout-seconds', str(args.get('timeout_seconds', 600))]
        if 'output' in args:
            command += ['--output', str(marked_compact_output(args['output']))]
        return command
    if name == 'phrase_timing':
        analysis, phrases, output_root = phrase_timing_paths(args)
        return head + [str(ROOT / 'scripts/phrase_timing.py'), '--analysis', str(analysis), '--phrases', str(phrases),
                       '--output-root', str(output_root), '--run-kind', args.get('run_kind', 'real_take')]
    if name == 'arrangement_reference':
        reference,directory,output = arrangement_reference_paths(args)
        return head + [str(ROOT/'scripts/arrangement_reference.py'),reference,'--run-dir',directory,'--output',output]
    if name == 'basic_pitch_compare':
        command = head + [str(ROOT / 'scripts/basic_pitch_compare.py'),
                          basic_pitch_directory(args['run_dir']),
                          '--max-analysis-seconds', str(args.get('max_analysis_seconds', 20)),
                          '--onset-threshold', str(args.get('onset_threshold', .5)),
                          '--frame-threshold', str(args.get('frame_threshold', .3))]
        if 'start_seconds' in args:
            command += ['--start-seconds', str(args['start_seconds'])]
        # The worker owns its pinned isolated ONNX launcher. Neither an MCP
        # argument nor the analysis-interpreter environment selects that child.
        return command
    if name == 'editor_marker_plan':
        return head + [str(ROOT / 'scripts/editor_marker_plan.py'), editor_marker_inputs(args),
                       args['selection'], args['profile'], '--summary']
    if name == 'learned_pitch_evaluate':
        command = head + [str(ROOT / 'scripts/learned_pitch_evaluate.py')]
        for field in LEARNED_EVALUATION_FIELDS:
            command += ['--' + field.replace('_', '-'),
                        calibration_path(args[field], output=field == 'output', max_bytes=5_000_000)]
        return command + ['--summary']
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


def run_worker(command, timeout, error_json_tool=None):
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
            if error_json_tool == 'report_bundle':
                stdout.seek(0)
                raise report_bundle_failure(process.returncode, stdout.read(4096))
            if error_json_tool == 'capture_profile':
                stdout.seek(0)
                try:
                    diagnostic = strict_json(stdout.read().decode('utf-8'))
                except (UnicodeError, ValueError):
                    diagnostic = None
                if (isinstance(diagnostic, dict) and diagnostic.get('tool') == error_json_tool
                        and diagnostic.get('status') == 'error' and isinstance(diagnostic.get('error'), dict)):
                    message = json.dumps(diagnostic, allow_nan=False)
                    if len(message.encode('utf-8')) <= 16 * 1024:
                        raise ToolError(f'worker failed ({process.returncode}): {message}')
            raise ToolError(f'worker failed ({process.returncode}): {error_tail}')
        stdout.seek(0)
        try:
            result = strict_json(stdout.read().decode('utf-8'))
        except (UnicodeError, ValueError) as error:
            raise ToolError('worker did not return a single finite JSON object') from error
        if not isinstance(result, dict):
            raise ToolError('worker result must be a JSON object')
        return result


def report_bundle_failure(returncode, data):
    """Exit 2 is a typed refusal with one stable reason code; exit 1 names an exception class only."""
    try:
        diagnostic = strict_json(data.decode('utf-8'))
    except (UnicodeError, ValueError):
        diagnostic = None
    def token(value):
        return (isinstance(value, str) and 0 < len(value) <= 64
                and all(character.isalnum() or character == '_' for character in value))
    if (returncode == 2 and isinstance(diagnostic, dict) and diagnostic.get('status') == 'refused'
            and token(diagnostic.get('reason'))):
        reason = diagnostic['reason']
        return ToolError(f'worker refused (2): report_bundle {reason}',
                         receipt={'report_bundle': {'status': 'refused', 'reason': reason, 'published': False}})
    if (returncode == 1 and isinstance(diagnostic, dict) and diagnostic.get('status') == 'error'
            and token(diagnostic.get('error'))):
        return ToolError(f'worker failed (1): report_bundle error {diagnostic["error"]}')
    # Never relay an unparsed tail: worker text may carry private paths.
    return ToolError(f'worker failed ({returncode}): report_bundle returned no typed diagnostic')


def classify_report_bundle_result(result):
    """A built bundle must be a fresh directory beneath the confined root and contain no media."""
    digest = result.get('bundle_sha256')
    if (result.get('status') != 'built' or not isinstance(digest, str) or len(digest) != 64
            or any(character not in '0123456789abcdef' for character in digest)):
        raise ToolError('report_bundle worker returned an unknown or malformed status')
    bundle = result.get('bundle_dir')
    if not isinstance(bundle, str) or not Path(bundle).is_absolute():
        raise ToolError('report_bundle worker returned no absolute bundle_dir')
    bundle = Path(bundle)
    boundary = Path(REPORT_BUNDLE_OUTPUT_ROOT)
    if (bundle.parent != boundary or bundle.is_symlink() or not bundle.is_dir()
            or bundle.resolve().parent != boundary.resolve()):
        raise ToolError('report_bundle output escaped artifacts/s2/report_d6/bundles')
    for path in bundle.rglob('*'):
        if path.is_symlink() or path.suffix.lower() in REPORT_BUNDLE_MEDIA_SUFFIXES:
            raise ToolError('report_bundle output contains a link or media file; bundle must not be used')
    return result


def classify_share_export_result(result, arguments):
    """Transport success does not turn a sharing-domain failure into success."""
    try:
        size = len(json.dumps(result, allow_nan=False, separators=(',', ':')).encode('utf-8'))
    except (TypeError, ValueError, OverflowError, RecursionError) as error:
        raise ToolError('share export result must be bounded finite JSON') from error
    if size > 16 * 1024:
        raise ToolError('share export result exceeds16KiB; inspect explicit output/receipt')
    def digest(value):
        return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)
    requested = Path(arguments['output']).expanduser()
    if not requested.is_absolute(): requested = ROOT / requested
    requested = str(requested.resolve())
    status = result.get('status')
    failures = {'rejected', 'failed_no_export_published',
                'exported_unreviewed_reporting_interrupted', 'publication_outcome_unknown'}
    if not isinstance(status, str) or status not in failures | {'exported_unreviewed'}:
        raise ToolError('share export worker returned an unknown domain status')
    if status in failures:
        allowed = {'status', 'error', 'code', 'output', 'possible_output', 'staging_dir',
                   'failure_receipt_path', 'failure_receipt_sha256', 'stage_progress',
                   'master_adopted', 'listening_accepted', 'diagnostic_fields_omitted'}
        if (set(result) - allowed or not isinstance(result.get('error'), str)
                or len(result['error']) > 1000 or not isinstance(result.get('code'), str)
                or len(result['code']) > 128):
            raise ToolError('share export worker returned malformed domain failure')
        if status != 'rejected':
            omitted = result.get('diagnostic_fields_omitted', [])
            if (not isinstance(omitted, list) or len(omitted) > 4 or any(not isinstance(field, str) for field in omitted)
                    or len(omitted) != len(set(omitted)) or set(omitted) - {'stage_progress', 'output.receipt_path', 'possible_output.receipt_path', 'staging_dir'}):
                raise ToolError('share export diagnostic omission fields are malformed')
            required = allowed - {'status', 'error', 'code', 'diagnostic_fields_omitted'}
            if 'staging_dir' in omitted: required.remove('staging_dir')
            if not required <= set(result) or result['master_adopted'] is not False or result['listening_accepted'] is not False:
                raise ToolError('share export failure lacks bounded recovery or acceptance state')
            if (('staging_dir' in result and (not isinstance(result['staging_dir'], str) or len(result['staging_dir']) > 4096))
                    or not isinstance(result['stage_progress'], list) or len(result['stage_progress']) > 128):
                raise ToolError('share export failure has malformed recovery selectors')
            if 'stage_progress' in omitted and result['stage_progress'] != []:
                raise ToolError('share export omitted progress must remain explicitly empty')
            path, pinned = result['failure_receipt_path'], result['failure_receipt_sha256']
            if not ((path is None and pinned is None) or
                    (isinstance(path, str) and 1 <= len(path) <= 4096 and digest(pinned))):
                raise ToolError('share export failure receipt selector/hash is malformed')
            for field in ('output', 'possible_output'):
                recovery = result[field]
                if recovery is None: continue
                projected = field + '.receipt_path' in omitted
                receipt_key = 'receipt_name' if projected else 'receipt_path'
                expected = Path(requested + '.receipt.json').name if projected else requested + '.receipt.json'
                if (not isinstance(recovery, dict) or set(recovery) != {'path', 'sha256', 'bytes', receipt_key, 'receipt_sha256'}
                        or recovery['path'] != requested or recovery[receipt_key] != expected
                        or not digest(recovery['sha256']) or not digest(recovery['receipt_sha256'])
                        or type(recovery['bytes']) is not int or not 0 < recovery['bytes'] <= 3 * 1024**3):
                    raise ToolError('share export candidate recovery is malformed or differs from request')
            if ((status == 'failed_no_export_published' and (result['output'] is not None or result['possible_output'] is not None))
                    or (status == 'exported_unreviewed_reporting_interrupted' and (not isinstance(result['output'], dict) or result['possible_output'] is not None))
                    or (status == 'publication_outcome_unknown' and (result['output'] is not None or not isinstance(result['possible_output'], dict)))):
                raise ToolError('share export failure publication state is inconsistent')
        raise ToolError('share export ' + status + ': ' + result['error'],
                        receipt={'share_export': result})
    if result.get('master_adopted') is not False or result.get('listening_accepted') is not False:
        raise ToolError('sharing export cannot adopt or accept a master')
    for field in ('source', 'output'):
        value = result.get(field)
        if not isinstance(value, dict): raise ToolError('share export lacks source/output provenance')
        pinned = value.get('sha256')
        if not digest(pinned):
            raise ToolError('share export provenance SHA256 is malformed')
        if type(value.get('bytes')) is not int or not 0 < value['bytes'] <= 3 * 1024**3:
            raise ToolError('share export provenance byte extent is malformed')
    original = Path(arguments['source']).expanduser()
    if not original.is_absolute(): original = ROOT / original
    if result['source'].get('path') != str(original.resolve()):
        raise ToolError('share export source selector differs from explicit request')
    output = result['output']
    if not digest(output.get('receipt_sha256')):
        raise ToolError('share export lacks pinned output receipt')
    if output.get('path') != requested or output.get('receipt_path') != requested + '.receipt.json':
        raise ToolError('share export output selectors differ from explicit request')
    return result


def execute(name, arguments):
    info = descriptor(name)
    validate(arguments, info['inputSchema'])
    validate_tool_arguments(name, arguments)
    timeout = arguments.get('timeout_seconds',
                            info['inputSchema']['properties'].get('timeout_seconds', {}).get('default', 600))
    if name == 'apply_capture_profile':
        from capture_application_adapter import ApplicationAdapter, AdapterError
        try:
            result = ApplicationAdapter(ROOT).run(capture_application_paths(arguments))
        except AdapterError as error:
            receipt = {'application_supervision':error.receipt, 'worker_diagnostic':error.diagnostic,
                       'worker_diagnostic_omitted':False,
                       'publication_outcome':'inspect_exact_durable_receipts'}
            message = str(error)[:1000]
            if len(json.dumps({'error':message,'receipt':receipt},allow_nan=False).encode()) > 16*1024:
                receipt['worker_diagnostic'] = None; receipt['worker_diagnostic_omitted'] = True
            raise ToolError(message, receipt=receipt) from error
    elif name == 'capture_profile':
        result = run_worker(worker_command(name, arguments), timeout, error_json_tool=name)
    elif name == 'report_bundle':
        result = classify_report_bundle_result(run_worker(worker_command(name, arguments), timeout, error_json_tool=name))
    elif name == 'share_export':
        result = classify_share_export_result(run_worker(worker_command(name, arguments), timeout), arguments)
    else:
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
