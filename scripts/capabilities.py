#!/usr/bin/env python3
"""Closed-schema capability metadata pilot beside program/tools.json (stdlib only).

The capability document never re-enters ranges, enums or defaults: those stay
in each descriptor's ``inputSchema``. This module only cross-checks key sets,
timeout bounds, default policy, ownership and static repository linkage
(capability -> worker -> skill -> tests). Nothing here executes a worker, a
test, FFmpeg or any DSP; every traversal result is a static repository check.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import sys

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
from tool_api import strict_json, validate_schema  # noqa: E402  (read-only library import)

ROOT = SCRIPTS.parent

# Root-admitted web_job adapters: tool -> evidence receipt. share_export: S2 root decision, 2026-10-06.
# denoise and capture_profile: S3 root integration, 2026-10-07, on their succeeded real-argv receipts.
# apply_capture_profile is NOT admitted and stays 'planned' in program/capabilities.json: its receipt
# (docs/agent-notes/sprints/20261007-s3/routes_processing-web-job-apply_capture_profile.json) records
# outcome not_run because tool_api refuses dot-prefixed path components and the lane worktree lived
# under .local/. Root must run the real-worker check from the main checkout before admitting it.
WEB_JOB_ADMISSIONS = {
    'share_export': 'docs/agent-notes/sprints/20261006-s2/web_reliability-real-web-job.json',
    'denoise': 'docs/agent-notes/sprints/20261007-s3/routes_processing-web-job-denoise.json',
    'capture_profile': 'docs/agent-notes/sprints/20261007-s3/routes_processing-web-job-capture_profile.json',
}
WEB_JOB_PENDING_REAL_WORKER = {
    'apply_capture_profile': 'docs/agent-notes/sprints/20261007-s3/routes_processing-web-job-apply_capture_profile.json',
}
CAPABILITIES = ROOT / 'program' / 'capabilities.json'
REGISTRY = ROOT / 'program' / 'tools.json'
MAX_CAPABILITY_BYTES = 1024 * 1024
MAX_REGISTRY_BYTES = 4 * 1024 * 1024
MAX_SOURCE_SCAN_BYTES = 8 * 1024 * 1024

PILOT_TOOLS = ('denoise', 'clicks', 'capture_profile', 'apply_capture_profile',
               'annotation_v2', 'corpus_split', 'editor_marker_plan', 'share_export')
# The only indirect allowlist linkage admitted by the S2 contract: tool_api.py
# imports this adapter module, and the adapter names the worker literally.
VIA_TOOLS = {'apply_capture_profile': 'scripts/capture_application_adapter.py'}

TOP_KEYS = ('schema_version', 'capability_contract_version', 'registry', 'status',
            'au_realtime_available', 'not_a_job_service', 'agent_may_change_defaults',
            'pilot_tools', 'capabilities')
TOP_CONSTS = {'schema_version': 1, 'capability_contract_version': 1,
              'registry': 'program/tools.json', 'status': 'pilot',
              'au_realtime_available': False, 'not_a_job_service': True,
              'agent_may_change_defaults': False}
CAP_KEYS = ('tool', 'domain', 'stage', 'implementation_status', 'evidence_kind', 'worker',
            'skill', 'tests', 'parameters', 'effects', 'resources', 'provenance_emitted',
            'dependencies', 'adapters', 'unknowns')
DOMAINS = ('restoration', 'analysis', 'review', 'corpus', 'delivery')
STAGES = ('render_candidate', 'event_analysis', 'profile_authoring', 'profile_application',
          'annotation_store', 'split_validation', 'editor_plan', 'share_derivative')
UNITS = ('s', 'ms', 'dB', 'LUFS', 'dBTP', 'Hz', 'Q', 'ratio', 'fraction_0_1', 'bpm', 'frames',
         'px', 'kbps', 'crf', 'count', 'local_path', 'run_relative_path', 'sha256_hex',
         'enum_token', 'boolean', 'json_object', 'json_array')
CLOCKS = ('input_audio_relative', 'decoded_source_audio_samples', 'original_source_seconds')
OWNERS = ('operator', 'root', 'none')
POLICIES = ('schema_default', 'explicit_required', 'omitted_means_off', 'omitted_means_none',
            'omitted_means_worker_default')
READS = ('original_source', 'run_manifest', 'run_pcm', 'run_json_evidence', 'capture_review',
         'profile_receipt', 'annotation_request', 'corpus_metadata', 'delivery_media')
WRITES = ('run_audio', 'run_json_evidence', 'capture_profile_metadata', 'applied_run',
          'annotation_store', 'delivery_media', 'delivery_receipt')
OUTPUT_ROOT_POLICIES = ('run_dir', 'artifacts_runs_child', 'explicit_fresh_file', 'none')
RESOURCE_CLASSES = ('metadata_light', 'analysis_cpu', 'media_render_ffmpeg')
PROVENANCE = ('original_source_sha256', 'analyzed_input_sha256', 'run_manifest_sha256',
              'settings', 'producer_script', 'output_sha256', 'capture_interval',
              'profile_receipt_sha256', 'annotation_revision', 'idempotency_key',
              'split_assignment', 'selection_sha256', 'editor_profile_sha256',
              'delivery_receipt', 'native_clock')
RUNTIMES = ('python_stdlib', 'analysis_python', 'ffmpeg', 'ffprobe')
UNKNOWN_FIELDS = ('memory_bytes', 'cpu_threads', 'output_bytes', 'musical_acceptance',
                  'listening_acceptance', 'web_admission', 'au_realtime')
UNKNOWN_REASON_CONSTS = {'musical_acceptance': 'not_established',
                         'listening_acceptance': 'not_established',
                         'web_admission': 'not_qualified', 'au_realtime': 'unsupported'}
UNIT_TYPES = {'boolean': {'boolean'}, 'json_object': {'object'}, 'json_array': {'array'}}
TOKEN = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}')
ENTRY = re.compile(r'[a-z][a-z0-9_]{0,31}')
ERROR_CODES = ('unknown_key', 'missing_key', 'bad_type', 'bad_enum', 'bad_const',
               'pilot_mismatch', 'unknown_tool', 'registry_drift', 'parameter_set_mismatch',
               'default_policy_conflict', 'timeout_mismatch', 'worker_missing',
               'worker_not_allowlisted', 'skill_missing', 'skill_mismatch', 'test_missing',
               'unsafe_path', 'readonly_conflict', 'duplicate')


class CapabilityError(ValueError):
    """Stable, machine-readable refusal; ``code`` is one of ERROR_CODES."""

    def __init__(self, code, message):
        if code not in ERROR_CODES:
            raise AssertionError(f'unregistered capability error code: {code}')
        super().__init__(f'{code}: {message}')
        self.code = code
        self.message = message


def _fail(code, message):
    raise CapabilityError(code, message)


# --------------------------------------------------------------------------- types

def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _closed(value, required, where, optional=()):
    if not isinstance(value, dict):
        _fail('bad_type', f'{where} must be an object')
    unknown = sorted(set(value) - set(required) - set(optional))
    if unknown:
        _fail('unknown_key', f'{where} has unknown keys {unknown}')
    missing = [key for key in required if key not in value]
    if missing:
        _fail('missing_key', f'{where} lacks keys {missing}')


def _const(value, expected, where):
    # Type-exact: False must not equal 0, and True must not equal 1.
    if type(value) is not type(expected) or value != expected:
        _fail('bad_const', f'{where} must be {json.dumps(expected)}')


def _enum(value, allowed, where):
    if not isinstance(value, str):
        _fail('bad_type', f'{where} must be a string')
    if value not in allowed:
        _fail('bad_enum', f'{where} has unsupported value {value!r}')


def _bool(value, where):
    if not isinstance(value, bool):
        _fail('bad_type', f'{where} must be a boolean')


def _unique_list(value, where, allowed=None, low=0, high=64, pattern=None):
    if not isinstance(value, list):
        _fail('bad_type', f'{where} must be an array')
    if not low <= len(value) <= high:
        _fail('bad_type', f'{where} must contain {low}..{high} items')
    for item in value:
        if allowed is not None:
            _enum(item, allowed, where)
        elif not isinstance(item, str) or (pattern is not None and not pattern.fullmatch(item)):
            _fail('bad_type', f'{where} items must be short tokens')
    if len(set(value)) != len(value):
        _fail('duplicate', f'{where} contains duplicate entries')


# --------------------------------------------------------------------------- paths

def _safe_relative(root, value, where, *, dot_head=None):
    """Lexically safe, symlink-free, root-confined repository path.

    ``dot_head`` admits one fixed dot-prefixed first component (``.agents`` for
    repository skills); every other hidden component is refused.
    """
    if not isinstance(value, str) or not 1 <= len(value) <= 512:
        _fail('unsafe_path', f'{where} must be a 1..512 character relative path')
    if value.startswith(('/', '~')) or ':' in value or '\\' in value or '\0' in value:
        _fail('unsafe_path', f'{where} must be a repository-relative POSIX path')
    parts = value.split('/')
    for index, part in enumerate(parts):
        if part in ('', '.', '..'):
            _fail('unsafe_path', f'{where} contains an empty, "." or ".." component')
        if part.startswith('.') and not (index == 0 and part == dot_head):
            _fail('unsafe_path', f'{where} contains a hidden component')
    base = Path(root).resolve()
    candidate = base
    for part in parts:
        candidate = candidate / part
        if candidate.is_symlink():
            _fail('unsafe_path', f'{where} contains a symbolic-link component')
    try:
        if not candidate.resolve().is_relative_to(base):
            _fail('unsafe_path', f'{where} resolves outside the repository root')
    except OSError as error:
        _fail('unsafe_path', f'{where} cannot be resolved: {error.__class__.__name__}')
    return candidate


def _regular(path):
    try:
        info = os.lstat(path)
    except OSError:
        return False
    return stat.S_ISREG(info.st_mode)


def _read_text(path, limit):
    """Bounded read of a regular non-symlink file; None when unavailable."""
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
                             | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_CLOEXEC', 0))
    except OSError:
        return None
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            return None
        chunks, total = [], 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                return None
            chunks.append(chunk)
        return b''.join(chunks).decode('utf-8', errors='replace')
    finally:
        os.close(descriptor)


def _load_json(path, limit, where):
    path = Path(path)
    if path.is_symlink() or not _regular(path):
        _fail('unsafe_path', f'{where} must be a regular non-symlink file')
    if path.stat().st_size > limit:
        _fail('bad_type', f'{where} exceeds {limit} bytes')
    text = _read_text(path, limit)
    if text is None:
        _fail('unsafe_path', f'{where} could not be read as a bounded regular file')
    try:
        value = strict_json(text)
    except ValueError as error:
        _fail('bad_type', f'{where} is not strict finite JSON: {error}')
    # tool_api.strict_json keeps the last duplicate key; a closed schema must not.
    def no_duplicates(pairs):
        keys = [key for key, _ in pairs]
        if len(set(keys)) != len(keys):
            _fail('duplicate', f'{where} repeats an object key')
        return dict(pairs)
    json.loads(text, object_pairs_hook=no_duplicates)
    return value


def load_registry(registry_path):
    registry = _load_json(registry_path, MAX_REGISTRY_BYTES, 'registry')
    if not isinstance(registry, dict) or not isinstance(registry.get('tools'), list):
        _fail('registry_drift', 'registry must be an object with a tools array')
    return registry


def load_capabilities(path=CAPABILITIES, registry_path=REGISTRY, root=ROOT):
    """Strictly load, then validate, the capability document; returns it."""
    doc = _load_json(path, MAX_CAPABILITY_BYTES, 'capabilities')
    validate(doc, load_registry(registry_path), root)
    return doc


# --------------------------------------------------------------------------- validation

def _descriptor_map(registry):
    tools = registry.get('tools') if isinstance(registry, dict) else None
    if not isinstance(tools, list):
        _fail('registry_drift', 'registry must contain a tools array')
    result = {}
    for item in tools:
        if not isinstance(item, dict) or not isinstance(item.get('name'), str):
            _fail('registry_drift', 'registry tool entries must be named objects')
        if item['name'] in result:
            _fail('duplicate', f'registry repeats tool {item["name"]}')
        result[item['name']] = item
    return result


def _check_descriptor(name, descriptor):
    try:
        validate_schema(descriptor['inputSchema'])
    except (KeyError, TypeError, ValueError) as error:
        _fail('registry_drift', f'{name} descriptor inputSchema is invalid: {error}')
    if not isinstance(descriptor.get('dependencies'), dict):
        _fail('registry_drift', f'{name} descriptor lacks dependencies')


def _worker_linkage(root, tool, worker):
    """Return 'direct' or 'via_adapter' when statically allowlisted, else None."""
    api = _read_text(Path(root) / 'scripts' / 'tool_api.py', MAX_SOURCE_SCAN_BYTES) or ''
    script, entry, via = worker['script'], worker['entry'], worker['via']
    if entry is not None and f"'{entry}'" not in api and f'"{entry}"' not in api:
        return None
    if script in api:
        return 'direct'
    if via is not None:
        adapter = _read_text(Path(root) / via, MAX_SOURCE_SCAN_BYTES) or ''
        stem = Path(via).stem
        imported = re.search(rf'^\s*(from\s+{re.escape(stem)}\s+import|import\s+{re.escape(stem)}\b)',
                             api, re.MULTILINE)
        if script in adapter and imported:
            return 'via_adapter'
    return None


def _validate_worker(root, tool, worker):
    _closed(worker, ('script', 'entry', 'via'), f'{tool}.worker')
    script, entry, via = worker['script'], worker['entry'], worker['via']
    if not isinstance(script, str) or not re.fullmatch(r'scripts/[a-z][a-z0-9_]{0,63}\.py', script):
        _fail('unsafe_path', f'{tool}.worker.script must be scripts/<file>.py')
    if entry is not None and (not isinstance(entry, str) or not ENTRY.fullmatch(entry)):
        _fail('bad_type', f'{tool}.worker.entry must be a fixed subcommand token or null')
    expected_via = VIA_TOOLS.get(tool)
    if via != expected_via:
        _fail('bad_const', f'{tool}.worker.via must be {json.dumps(expected_via)}')
    for label, value in (('script', script), ('via', via)):
        if value is None:
            continue
        path = _safe_relative(root, value, f'{tool}.worker.{label}')
        if not _regular(path):
            _fail('worker_missing', f'{tool}.worker.{label} {value} is not an existing regular file')
    if _worker_linkage(root, tool, worker) is None:
        _fail('worker_not_allowlisted', f'{tool} worker {script} is not literally allowlisted by scripts/tool_api.py')


def _validate_skill(root, tool, value, descriptor):
    if value != descriptor.get('skill'):
        _fail('skill_mismatch', f'{tool}.skill differs from the registry descriptor')
    if not isinstance(value, str) or not re.fullmatch(r'\.agents/skills/[a-z0-9][a-z0-9-]{0,63}/SKILL\.md', value):
        _fail('unsafe_path', f'{tool}.skill must be .agents/skills/<dir>/SKILL.md')
    path = _safe_relative(root, value, f'{tool}.skill', dot_head='.agents')
    if not _regular(path):
        _fail('skill_missing', f'{tool}.skill {value} is not an existing regular file')


def _validate_tests(root, tool, tests):
    if not isinstance(tests, list) or not 1 <= len(tests) <= 8:
        _fail('bad_type', f'{tool}.tests must list 1..8 test files')
    if len(set(map(str, tests))) != len(tests):
        _fail('duplicate', f'{tool}.tests contains duplicates')
    for value in tests:
        path = _safe_relative(root, value, f'{tool}.tests')
        if not re.fullmatch(r'tests/test_[a-z0-9_]{1,96}\.py', value):
            _fail('unsafe_path', f'{tool}.tests entries must be tests/test_*.py')
        if not _regular(path):
            _fail('test_missing', f'{tool}.tests {value} is not an existing regular file')


def _schema_type(schema):
    return schema.get('type') if isinstance(schema, dict) else None


def _nested_properties(schema):
    if _schema_type(schema) == 'object':
        return schema.get('properties', {})
    if _schema_type(schema) == 'array' and _schema_type(schema.get('items')) == 'object':
        return schema['items'].get('properties', {})
    return None


def _validate_unit_clock(entry, where, schema):
    _enum(entry['unit'], UNITS, f'{where}.unit')
    if entry['clock'] is not None:
        _enum(entry['clock'], CLOCKS, f'{where}.clock')
    allowed_types = UNIT_TYPES.get(entry['unit'])
    kind = _schema_type(schema)
    if allowed_types is not None and kind not in allowed_types:
        _fail('registry_drift', f'{where}.unit {entry["unit"]} disagrees with schema type {kind}')
    if allowed_types is None and kind in ('boolean', 'object', 'array'):
        _fail('registry_drift', f'{where}.unit {entry["unit"]} disagrees with schema type {kind}')


def _validate_parameters(tool, parameters, descriptor):
    if not isinstance(parameters, dict):
        _fail('bad_type', f'{tool}.parameters must be an object')
    schema = descriptor['inputSchema']
    properties = schema.get('properties', {})
    required = set(schema.get('required', []))
    if set(parameters) != set(properties):
        missing = sorted(set(properties) - set(parameters))
        extra = sorted(set(parameters) - set(properties))
        _fail('parameter_set_mismatch', f'{tool}.parameters missing {missing} extra {extra}')
    for name in properties:
        entry, child = parameters[name], properties[name]
        where = f'{tool}.parameters.{name}'
        nested = _nested_properties(child)
        _closed(entry, ('unit', 'clock', 'default_owner', 'default_policy'), where,
                optional=('fields',) if nested is not None else ())
        _validate_unit_clock(entry, where, child)
        _enum(entry['default_owner'], OWNERS, f'{where}.default_owner')
        _enum(entry['default_policy'], POLICIES, f'{where}.default_policy')
        has_default = 'default' in child
        policy, owner = entry['default_policy'], entry['default_owner']
        if (policy == 'schema_default') != has_default:
            _fail('default_policy_conflict', f'{where}: schema_default must match a descriptor default')
        if (policy == 'explicit_required') != (name in required):
            _fail('default_policy_conflict', f'{where}: explicit_required must match descriptor required')
        if (owner == 'none') == has_default:
            _fail('default_policy_conflict', f'{where}: default_owner none must match absence of a default')
        if nested is not None:
            if 'fields' not in entry:
                _fail('missing_key', f'{where} lacks nested fields metadata')
            fields = entry['fields']
            if not isinstance(fields, dict):
                _fail('bad_type', f'{where}.fields must be an object')
            if set(fields) != set(nested):
                _fail('parameter_set_mismatch', f'{where}.fields key set differs from nested properties')
            for field, metadata in fields.items():
                _closed(metadata, ('unit', 'clock'), f'{where}.fields.{field}')
                _validate_unit_clock(metadata, f'{where}.fields.{field}', nested[field])


def _validate_effects(tool, effects, descriptor):
    where = f'{tool}.effects'
    _closed(effects, ('reads', 'writes', 'renders_audio', 'renders_video', 'overwrites_input',
                      'network', 'model_acquisition', 'output_root_policy'), where)
    _unique_list(effects['reads'], f'{where}.reads', READS, low=1, high=len(READS))
    _unique_list(effects['writes'], f'{where}.writes', WRITES, low=0, high=len(WRITES))
    _bool(effects['renders_audio'], f'{where}.renders_audio')
    _bool(effects['renders_video'], f'{where}.renders_video')
    for key in ('overwrites_input', 'network', 'model_acquisition'):
        _const(effects[key], False, f'{where}.{key}')
    _enum(effects['output_root_policy'], OUTPUT_ROOT_POLICIES, f'{where}.output_root_policy')
    hints = descriptor.get('annotations', {})
    if isinstance(hints, dict) and hints.get('readOnlyHint') is True:
        if effects['writes'] or effects['renders_audio'] or effects['renders_video']:
            _fail('readonly_conflict', f'{tool} descriptor is readOnlyHint but effects write or render')
        if effects['output_root_policy'] != 'none':
            _fail('readonly_conflict', f'{tool} descriptor is readOnlyHint but declares an output root')


def _validate_resources(tool, resources, descriptor):
    where = f'{tool}.resources'
    _closed(resources, ('resource_class', 'heavy_numeric', 'timeout_seconds', 'source_bytes',
                        'memory_bytes'), where)
    _enum(resources['resource_class'], RESOURCE_CLASSES, f'{where}.resource_class')
    _bool(resources['heavy_numeric'], f'{where}.heavy_numeric')
    timeout = resources['timeout_seconds']
    _closed(timeout, ('min', 'max', 'default', 'status'), f'{where}.timeout_seconds')
    _const(timeout['status'], 'enforced', f'{where}.timeout_seconds.status')
    schema = descriptor['inputSchema'].get('properties', {}).get('timeout_seconds')
    if not isinstance(schema, dict):
        _fail('timeout_mismatch', f'{tool} descriptor has no timeout_seconds schema')
    for key, schema_key in (('min', 'minimum'), ('max', 'maximum'), ('default', 'default')):
        if not _is_int(timeout[key]) or timeout[key] != schema.get(schema_key):
            _fail('timeout_mismatch', f'{where}.timeout_seconds.{key} differs from registry {schema_key}')
    source = resources['source_bytes']
    _closed(source, ('max', 'status'), f'{where}.source_bytes')
    _enum(source['status'], ('enforced', 'unknown'), f'{where}.source_bytes.status')
    if source['status'] == 'enforced' and (not _is_int(source['max']) or source['max'] <= 0):
        _fail('bad_type', f'{where}.source_bytes.max must be a positive integer when enforced')
    if source['status'] == 'unknown' and source['max'] is not None:
        _fail('bad_const', f'{where}.source_bytes.max must be null when unknown')
    memory = resources['memory_bytes']
    _closed(memory, ('max', 'status'), f'{where}.memory_bytes')
    if memory['max'] is not None:
        _fail('bad_const', f'{where}.memory_bytes.max must be null in this pilot')
    _const(memory['status'], 'not_qualified', f'{where}.memory_bytes.status')


def _validate_dependencies(tool, dependencies, descriptor):
    where = f'{tool}.dependencies'
    _closed(dependencies, ('advisory_prior_tools', 'enforced', 'required_artifacts',
                           'external_runtime'), where)
    registered = descriptor['dependencies']
    prior = dependencies['advisory_prior_tools']
    if not isinstance(prior, list) or prior != registered.get('recommended_prior_tools'):
        _fail('registry_drift', f'{where}.advisory_prior_tools differs from registry')
    _bool(dependencies['enforced'], f'{where}.enforced')
    if dependencies['enforced'] is not registered.get('enforced'):
        _fail('registry_drift', f'{where}.enforced differs from registry')
    _unique_list(dependencies['required_artifacts'], f'{where}.required_artifacts', low=0, high=8,
                 pattern=TOKEN)
    _unique_list(dependencies['external_runtime'], f'{where}.external_runtime', RUNTIMES, low=1,
                 high=len(RUNTIMES))


def _validate_adapters(tool, adapters):
    where = f'{tool}.adapters'
    _closed(adapters, ('local_cli', 'mcp_stdio', 'web_job', 'au_render_parameter'), where)
    _const(adapters['local_cli'], 'available', f'{where}.local_cli')
    _const(adapters['mcp_stdio'], 'available', f'{where}.mcp_stdio')
    _enum(adapters['web_job'], ('planned', 'unsupported', 'admitted'), f'{where}.web_job')
    if adapters['web_job'] == 'admitted':
        evidence = WEB_JOB_ADMISSIONS.get(tool)
        if evidence is None:
            _fail('bad_enum', f'{where}.web_job admitted without a root admission record')
        if not (ROOT / evidence).is_file():
            _fail('missing_evidence', f'{where}.web_job admission evidence missing: {evidence}')
    _const(adapters['au_render_parameter'], 'unsupported', f'{where}.au_render_parameter')


def _validate_unknowns(tool, unknowns):
    where = f'{tool}.unknowns'
    keys = [key for field in UNKNOWN_FIELDS for key in (field, field + '_reason')]
    _closed(unknowns, keys, where)
    for field in UNKNOWN_FIELDS:
        if unknowns[field] is not None:
            _fail('bad_const', f'{where}.{field} must be null (unknown)')
        reason = unknowns[field + '_reason']
        if not isinstance(reason, str) or not 1 <= len(reason) <= 300:
            _fail('bad_type', f'{where}.{field}_reason must be a 1..300 character string')
        if field in UNKNOWN_REASON_CONSTS:
            _const(reason, UNKNOWN_REASON_CONSTS[field], f'{where}.{field}_reason')


def validate(doc, registry, root=ROOT):
    """Raise CapabilityError on the first violation; return None when valid."""
    _closed(doc, TOP_KEYS, 'capabilities document')
    for key, expected in TOP_CONSTS.items():
        _const(doc[key], expected, key)
    pilot = doc['pilot_tools']
    if not isinstance(pilot, list):
        _fail('bad_type', 'pilot_tools must be an array')
    if len(set(map(str, pilot))) != len(pilot):
        _fail('duplicate', 'pilot_tools contains duplicates')
    if pilot != list(PILOT_TOOLS):
        _fail('pilot_mismatch', f'pilot_tools must equal {list(PILOT_TOOLS)} in order')
    capabilities = doc['capabilities']
    if not isinstance(capabilities, list):
        _fail('bad_type', 'capabilities must be an array')
    names = [item.get('tool') if isinstance(item, dict) else None for item in capabilities]
    if len(set(map(str, names))) != len(names):
        _fail('duplicate', 'capabilities repeat a tool')
    if names != pilot:
        _fail('pilot_mismatch', 'capabilities must contain one entry per pilot tool in the same order')
    descriptors = _descriptor_map(registry)
    for tool, capability in zip(pilot, capabilities):
        if tool not in descriptors:
            _fail('unknown_tool', f'{tool} is not a registry descriptor')
        descriptor = descriptors[tool]
        _check_descriptor(tool, descriptor)
        _closed(capability, CAP_KEYS, f'capability {tool}')
        _enum(capability['domain'], DOMAINS, f'{tool}.domain')
        _enum(capability['stage'], STAGES, f'{tool}.stage')
        for key in ('implementation_status', 'evidence_kind'):
            if capability[key] != descriptor.get(key):
                _fail('registry_drift', f'{tool}.{key} differs from registry')
        _validate_worker(root, tool, capability['worker'])
        _validate_skill(root, tool, capability['skill'], descriptor)
        _validate_tests(root, tool, capability['tests'])
        _validate_parameters(tool, capability['parameters'], descriptor)
        _validate_effects(tool, capability['effects'], descriptor)
        _validate_resources(tool, capability['resources'], descriptor)
        _unique_list(capability['provenance_emitted'], f'{tool}.provenance_emitted', PROVENANCE,
                     low=1, high=16)
        _validate_dependencies(tool, capability['dependencies'], descriptor)
        _validate_adapters(tool, capability['adapters'])
        _validate_unknowns(tool, capability['unknowns'])


# --------------------------------------------------------------------------- traversal

def _edge_file(root, value, dot_head=None):
    try:
        return _regular(_safe_relative(root, value, 'edge', dot_head=dot_head))
    except CapabilityError:
        return False


def _traverse_one(capability, root):
    tool, worker = capability['tool'], capability['worker']
    worker_exists = _edge_file(root, worker['script']) and (
        worker['via'] is None or _edge_file(root, worker['via']))
    linkage = _worker_linkage(root, tool, worker) if worker_exists else None
    skill_exists = _edge_file(root, capability['skill'], dot_head='.agents')
    tests = [{'path': value, 'exists': _edge_file(root, value)} for value in capability['tests']]
    tests_exist = bool(tests) and all(item['exists'] for item in tests)
    stem = Path(worker['script']).stem
    mentions = False
    for item in tests:
        if item['exists']:
            text = _read_text(Path(root) / item['path'], MAX_SOURCE_SCAN_BYTES) or ''
            if stem in text:
                mentions = True
                break
    sources = [worker['script']] + ([worker['via']] if worker['via'] else [])
    corpus = ''.join(_read_text(Path(root) / value, MAX_SOURCE_SCAN_BYTES) or ''
                     for value in sources if _edge_file(root, value))
    provenance = {field: ('token_found_in_worker' if field in corpus else 'declared_unverified')
                  for field in capability['provenance_emitted']}
    edges = {'capability_present': True, 'worker_exists': worker_exists,
             'skill_exists': skill_exists, 'tests_exist': tests_exist}
    return {'tool': tool, **edges, 'worker_allowlisted': linkage is not None,
            'worker_linkage': linkage or 'none', 'worker': worker['script'],
            'worker_via': worker['via'], 'skill': capability['skill'], 'tests': tests,
            'test_mentions_worker': mentions, 'provenance': provenance,
            'edges_passed': sum(edges.values()), 'edges_total': len(edges)}


def traverse(doc, root=ROOT, tool=None):
    """Static capability -> worker -> skill -> tests walk; executes nothing."""
    capabilities = doc.get('capabilities', []) if isinstance(doc, dict) else []
    selected = [item for item in capabilities if isinstance(item, dict)
                and (tool is None or item.get('tool') == tool)]
    if tool is not None and not selected:
        _fail('unknown_tool', f'{tool} has no capability entry')
    rows = [_traverse_one(item, root) for item in selected]
    declared = sum(len(row['provenance']) for row in rows)
    found = sum(1 for row in rows for state in row['provenance'].values()
                if state == 'token_found_in_worker')
    return {'schema_version': 1, 'claim_class': 'static_repository_check',
            'tests_executed': False, 'au_realtime_available': False, 'not_a_job_service': True,
            'tools': rows,
            'summary': {'tools': len(rows),
                        'edges_passed': sum(row['edges_passed'] for row in rows),
                        'edges_total': sum(row['edges_total'] for row in rows),
                        'worker_allowlisted': sum(row['worker_allowlisted'] for row in rows),
                        'test_mentions_worker': sum(row['test_mentions_worker'] for row in rows),
                        'provenance_token_found': found, 'provenance_declared': declared,
                        'provenance_declared_unverified': declared - found}}


def describe(doc, registry, name, root=ROOT):
    """One capability with registry-owned bounds read (not copied) from inputSchema."""
    capability = next((item for item in doc['capabilities'] if item['tool'] == name), None)
    if capability is None:
        _fail('unknown_tool', f'{name} has no capability entry')
    descriptor = _descriptor_map(registry)[name]
    properties = descriptor['inputSchema'].get('properties', {})
    required = set(descriptor['inputSchema'].get('required', []))
    schema_view = {}
    for key, schema in properties.items():
        view = {field: schema[field] for field in ('type', 'minimum', 'maximum', 'exclusiveMinimum',
                                                   'minLength', 'maxLength', 'enum', 'default',
                                                   'minItems', 'maxItems') if field in schema}
        view['required'] = key in required
        schema_view[key] = view
    return {'schema_version': 1, 'tool': name, 'capability': capability,
            'registry_input_bounds': schema_view, 'registry_bounds_source': 'program/tools.json inputSchema',
            'traversal': traverse(doc, root, name)['tools'][0],
            'claim_class': 'static_repository_check', 'tests_executed': False,
            'au_realtime_available': False, 'not_a_job_service': True}


# --------------------------------------------------------------------------- CLI

def _emit(stream, value):
    stream.write(json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + '\n')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--root', default=str(ROOT))
    parser.add_argument('--capabilities', default=None)
    parser.add_argument('--registry', default=None)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('validate')
    traverse_parser = commands.add_parser('traverse')
    traverse_parser.add_argument('--tool')
    describe_parser = commands.add_parser('describe')
    describe_parser.add_argument('name')
    args = parser.parse_args(argv)
    root = Path(args.root)
    capabilities_path = Path(args.capabilities) if args.capabilities else root / 'program' / 'capabilities.json'
    registry_path = Path(args.registry) if args.registry else root / 'program' / 'tools.json'
    try:
        doc = load_capabilities(capabilities_path, registry_path, root)
        if args.command == 'validate':
            result = {'status': 'valid', 'schema_version': 1, 'pilot_tools': doc['pilot_tools'],
                      'tools': len(doc['capabilities']),
                      'parameters': sum(len(item['parameters']) for item in doc['capabilities']),
                      'nested_fields_groups': sum(1 for item in doc['capabilities']
                                                  for entry in item['parameters'].values() if 'fields' in entry),
                      'claim_class': 'static_repository_check', 'tests_executed': False,
                      'au_realtime_available': False, 'not_a_job_service': True,
                      'agent_may_change_defaults': False}
        elif args.command == 'traverse':
            result = traverse(doc, root, args.tool)
        else:
            result = describe(doc, load_registry(registry_path), args.name, root)
    except CapabilityError as error:
        _emit(sys.stderr, {'status': 'error', 'code': error.code, 'error': error.message})
        return 1
    _emit(sys.stdout, result)
    if args.command == 'traverse' and result['summary']['edges_passed'] != result['summary']['edges_total']:
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
