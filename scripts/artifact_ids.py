#!/usr/bin/env python3
"""Opaque, hash-derived artifact/source IDs confined to artifacts/runs (stdlib only).

This is the WEB-1 artifact-ID boundary prerequisite, not a job service: it
never renders, decodes, launches a subprocess, downloads anything or writes
under ``artifacts/runs``. An ID is derived from SHA-256 and is a provenance
identifier, not an authorization token. Every ``resolve`` re-hashes the bytes
before returning; only a ``current`` resolution carries the private path, and
public records never contain a host path or a selector.

Identity (version 1)::

    content_sha256 = sha256(file bytes)
    artifact_id    = "art_" + sha256("video-utils/artifact-id/v1\\0" + selector + "\\0" + content_sha256)[:32]
    source_id      = "src_" + sha256("video-utils/source-id/v1\\0" + manifest.source.sha256)[:32]
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import errno
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ID_VERSION = 1
INDEX_SCHEMA = 'video-utils/artifact-index'
ARTIFACT_DOMAIN = b'video-utils/artifact-id/v1\0'
SOURCE_DOMAIN = b'video-utils/source-id/v1\0'
DEFAULT_MAX_BYTES = 3 * 1024 ** 3
MAX_MANIFEST_BYTES = 20 * 1024 * 1024
MAX_INDEX_BYTES = 64 * 1024 * 1024
MAX_INDEX_ENTRIES = 100_000
MAX_JSON_NESTING = 128
CHUNK = 1024 * 1024
MAX_SELECTOR_CHARS = 1024
MIN_COMPONENTS, MAX_COMPONENTS = 2, 16

COMPONENT = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}')
ARTIFACT_ID = re.compile(r'art_[0-9a-f]{32}')
SOURCE_ID = re.compile(r'src_[0-9a-f]{32}')
SHA256 = re.compile(r'[0-9a-f]{64}')
URL_SCHEME = re.compile(r'[A-Za-z][A-Za-z0-9+.-]*:')
DRIVE = re.compile(r'[A-Za-z]:')
# Filter-graph / shell syntax. A selector names a file; it is never a command,
# filter string or option, so these characters are refused rather than escaped.
FILTER_CHARS = frozenset('=,;[]|$`\'":&<>(){}*?!#%^@+~')
EXEC_MAGICS = (b'#!', b'\x7fELF', b'\xfe\xed\xfa\xce', b'\xfe\xed\xfa\xcf', b'\xce\xfa\xed\xfe',
               b'\xcf\xfa\xed\xfe', b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca', b'MZ')
VIDEO_SUFFIXES = ('.mov', '.mp4', '.m4v', '.mkv', '.webm')
STATES = ('current', 'stale', 'missing')
CLAIM_CLASS = 'hash_measurement'
PUBLIC_KEYS = ('artifact_id', 'kind', 'sha256', 'size_bytes', 'state', 'source_id',
               'source_binding', 'claim_class', 'not_a_job_service', 'id_version')
INDEX_ARTIFACT_KEYS = ('artifact_id', 'selector', 'sha256', 'size_bytes', 'kind', 'source_id',
                       'source_binding')
INDEX_SOURCE_KEYS = ('source_id', 'run_id', 'source_sha256', 'manifest_artifact_id')
ERROR_CODES = ('host_path_refused', 'outside_runs_root', 'symlink_component', 'filter_string_refused',
               'unsafe_component', 'executable_refused', 'not_regular_file', 'too_large',
               'changed_during_hash', 'malformed_id', 'unknown_id', 'id_collision',
               'write_inside_runs', 'target_exists', 'bad_index')


class ArtifactIdError(ValueError):
    """Stable refusal; ``code`` is one of ERROR_CODES. Messages never echo host paths."""

    def __init__(self, code, message=''):
        if code not in ERROR_CODES:
            raise AssertionError(f'unregistered artifact-id error code: {code}')
        super().__init__(f'{code}: {message}' if message else code)
        self.code = code
        self.message = message or code


class _Missing(Exception):
    """Internal: the selector no longer names a regular file (resolve -> missing)."""


def _fail(code, message=''):
    raise ArtifactIdError(code, message)


def signature(info):
    """Identity used to detect cooperative concurrent change around a hash."""
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


# --------------------------------------------------------------------------- identity

def artifact_id_for(selector, content_sha256):
    digest = hashlib.sha256(ARTIFACT_DOMAIN + selector.encode('utf-8') + b'\0'
                            + content_sha256.encode('ascii')).hexdigest()
    return 'art_' + digest[:32]


def source_id_for(source_sha256):
    return 'src_' + hashlib.sha256(SOURCE_DOMAIN + source_sha256.encode('ascii')).hexdigest()[:32]


def kind_for(selector):
    lower = selector.lower()
    if lower.endswith('.json'):
        return 'json'
    if lower.endswith('.wav'):
        return 'wav'
    if lower.endswith(VIDEO_SUFFIXES):
        return 'video'
    return 'other'


# --------------------------------------------------------------------------- selectors

def check_selector(selector):
    """Lexical validation of a runs-relative selector; returns its components.

    Refusal precedence is fixed so each hostile form maps to one stable code.
    """
    if not isinstance(selector, str) or not selector:
        _fail('unsafe_component', 'selector must be a non-empty string')
    if '\0' in selector:
        _fail('unsafe_component', 'selector contains NUL')
    if len(selector) > MAX_SELECTOR_CHARS:
        _fail('unsafe_component', f'selector exceeds {MAX_SELECTOR_CHARS} characters')
    if (selector.startswith(('/', '~', '\\\\', '//')) or DRIVE.match(selector)
            or (URL_SCHEME.match(selector) and '/' in selector.split(':', 1)[1][:2])
            or selector.startswith('file:')):
        _fail('host_path_refused', 'selector must be runs-relative, not a host path or URL')
    parts = selector.split('/')
    if parts[0] == 'artifacts' or '..' in parts:
        _fail('outside_runs_root', 'selector must be relative to artifacts/runs without parent traversal')
    if '\\' in selector:
        _fail('unsafe_component', 'selector contains a backslash')
    if any(character in FILTER_CHARS or character.isspace() for character in selector):
        _fail('filter_string_refused', 'selector contains filter or shell syntax')
    if not MIN_COMPONENTS <= len(parts) <= MAX_COMPONENTS:
        _fail('unsafe_component', f'selector must have {MIN_COMPONENTS}..{MAX_COMPONENTS} components')
    for part in parts:
        if (not part or part.startswith(('.', '-')) or '.partial' in part
                or not COMPONENT.fullmatch(part)):
            _fail('unsafe_component', 'selector component is empty, hidden, partial, option-like or unsupported')
    return parts


def check_run_id(run_id):
    if not isinstance(run_id, str) or not COMPONENT.fullmatch(run_id) or '.partial' in run_id:
        _fail('unsafe_component', 'run id must be one safe component')
    return run_id


def _strict_json(data, where):
    """Strict finite JSON with duplicate keys refused (stricter than tool_api.strict_json)."""
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError:
        raise ValueError(f'{where} is not UTF-8') from None
    depth = quoted = escaped = 0
    for character in text:
        if quoted:
            if escaped:
                escaped = 0
            elif character == '\\':
                escaped = 1
            elif character == '"':
                quoted = 0
        elif character == '"':
            quoted = 1
        elif character in '[{':
            depth += 1
            if depth > MAX_JSON_NESTING:
                raise ValueError(f'{where} nesting exceeds {MAX_JSON_NESTING}')
        elif character in ']}':
            depth -= 1

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f'{where} repeats key {key!r}')
            result[key] = value
        return result

    def constant(value):
        raise ValueError(f'{where} has non-finite number {value}')

    def finite(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError(f'{where} has non-finite number')
        return parsed

    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=constant, parse_float=finite)
    except RecursionError:
        raise ValueError(f'{where} nesting exceeds parser limits') from None


# --------------------------------------------------------------------------- records

@dataclass(frozen=True)
class Resolution:
    """Outcome of a re-hashing resolve. ``path`` is private and set only when current."""

    artifact_id: str
    state: str
    record: dict
    path: Path | None = None
    observed_sha256: str | None = None

    def public(self):
        return {**self.record, 'state': self.state}


def _public(entry, state='current'):
    return {'artifact_id': entry['artifact_id'], 'kind': entry['kind'], 'sha256': entry['sha256'],
            'size_bytes': entry['size_bytes'], 'state': state, 'source_id': entry['source_id'],
            'source_binding': entry['source_binding'], 'claim_class': CLAIM_CLASS,
            'not_a_job_service': True, 'id_version': ID_VERSION}


class ArtifactIndex:
    """In-memory ``id -> record`` projection over ``<root>/artifacts/runs``.

    No global state and no background work. Reads never write; only ``dump``
    writes, and never under the runs root.
    """

    def __init__(self, root=None, max_bytes=DEFAULT_MAX_BYTES):
        base = Path(root if root is not None else ROOT)
        try:
            self.root = base.resolve(strict=True)
        except OSError:
            _fail('outside_runs_root', 'root does not exist')
        artifacts = self.root / 'artifacts'
        runs = artifacts / 'runs'
        for directory in (artifacts, runs):
            try:
                info = os.lstat(directory)
            except OSError:
                _fail('outside_runs_root', 'artifacts/runs does not exist under root')
            if stat.S_ISLNK(info.st_mode):
                _fail('symlink_component', 'artifacts/runs must not be a symbolic link')
            if not stat.S_ISDIR(info.st_mode):
                _fail('not_regular_file', 'artifacts/runs must be a directory')
        if not runs.resolve().is_relative_to(self.root):
            _fail('outside_runs_root', 'artifacts/runs resolves outside root')
        if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes <= 0:
            raise ValueError('max_bytes must be a positive integer')
        self.runs = runs
        self.max_bytes = max_bytes
        self._artifacts = {}
        self._sources = {}

    # ----------------------------------------------------------------- reading

    def __len__(self):
        return len(self._artifacts)

    @property
    def source_count(self):
        return len(self._sources)

    def _walk(self, parts):
        """Confined, symlink-free walk; returns the leaf path and its lstat."""
        candidate = self.runs
        for index, part in enumerate(parts):
            candidate = candidate / part
            try:
                info = os.lstat(candidate)
            except FileNotFoundError:
                raise _Missing() from None
            except OSError:
                raise _Missing() from None
            if stat.S_ISLNK(info.st_mode):
                _fail('symlink_component', 'selector contains a symbolic-link component')
            if index < len(parts) - 1 and not stat.S_ISDIR(info.st_mode):
                raise _Missing()
        if not candidate.resolve().is_relative_to(self.runs.resolve()):
            _fail('outside_runs_root', 'selector resolves outside artifacts/runs')
        if not stat.S_ISREG(info.st_mode):
            _fail('not_regular_file', 'selector does not name a regular file')
        return candidate, info

    def _read_chunk(self, descriptor):
        """Single read; isolated so tests can model cooperative concurrent writers."""
        return os.read(descriptor, CHUNK)

    def _measure(self, selector, keep_limit=0):
        """Hash one confined regular file. Returns (path, sha256, size, kept_bytes|None)."""
        parts = check_selector(selector)
        path, before = self._walk(parts)
        if before.st_mode & 0o111:
            _fail('executable_refused', 'file has an executable mode bit')
        if before.st_size > self.max_bytes:
            _fail('too_large', f'file exceeds {self.max_bytes} bytes')
        flags = (os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
                 | getattr(os, 'O_CLOEXEC', 0))
        try:
            descriptor = os.open(path, flags)
        except FileNotFoundError:
            raise _Missing() from None
        except OSError as error:
            if error.errno == errno.ELOOP:
                _fail('symlink_component', 'leaf became a symbolic link')
            _fail('not_regular_file', 'file could not be opened as a regular file')
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode):
                _fail('not_regular_file', 'opened object is not a regular file')
            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                _fail('changed_during_hash', 'file was replaced between check and open')
            digest = hashlib.sha256()
            kept = [] if keep_limit else None
            total = 0
            first = True
            while True:
                chunk = self._read_chunk(descriptor)
                if not chunk:
                    break
                if first:
                    if chunk.startswith(EXEC_MAGICS):
                        _fail('executable_refused', 'file starts with an executable signature')
                    first = False
                total += len(chunk)
                if total > opened.st_size:
                    _fail('changed_during_hash', 'file grew while hashing')
                if total > self.max_bytes:
                    _fail('too_large', f'file exceeds {self.max_bytes} bytes')
                if kept is not None:
                    if total > keep_limit:
                        _fail('too_large', f'file exceeds {keep_limit} bytes')
                    kept.append(chunk)
                digest.update(chunk)
            after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        try:
            relinked = os.lstat(path)
        except OSError:
            _fail('changed_during_hash', 'file disappeared while hashing')
        if not (signature(opened) == signature(after) == signature(relinked)) or total != after.st_size:
            _fail('changed_during_hash', 'file identity, size or mtime changed while hashing')
        return path, digest.hexdigest(), total, (b''.join(kept) if kept is not None else None)

    def _source_binding(self, run_id):
        """(source_id|None, binding, manifest_sha|None, manifest_artifact_id|None, source_sha|None)."""
        selector = f'{run_id}/manifest.json'
        try:
            _, manifest_sha, _, data = self._measure(selector, keep_limit=MAX_MANIFEST_BYTES)
        except (_Missing, ArtifactIdError):
            return None, 'unknown', None, None, None
        manifest_artifact_id = artifact_id_for(selector, manifest_sha)
        try:
            manifest = _strict_json(data, 'manifest')
        except ValueError:
            return None, 'unknown', manifest_sha, manifest_artifact_id, None
        source = manifest.get('source') if isinstance(manifest, dict) else None
        value = source.get('sha256') if isinstance(source, dict) else None
        if not isinstance(value, str) or not SHA256.fullmatch(value):
            return None, 'unknown', manifest_sha, manifest_artifact_id, None
        return source_id_for(value), 'bound', manifest_sha, manifest_artifact_id, value

    # ----------------------------------------------------------------- projection

    def _register(self, entry):
        existing = self._artifacts.get(entry['artifact_id'])
        if existing is not None:
            if (existing['selector'], existing['sha256']) != (entry['selector'], entry['sha256']):
                _fail('id_collision', 'artifact id already names different content')
            if (existing['source_id'], existing['source_binding']) != (entry['source_id'], entry['source_binding']):
                existing.update(source_id=entry['source_id'], source_binding=entry['source_binding'])
            return existing
        self._artifacts[entry['artifact_id']] = entry
        return entry

    def _register_source(self, source_id, run_id, source_sha, manifest_artifact_id):
        entry = {'source_id': source_id, 'run_id': run_id, 'source_sha256': source_sha,
                 'manifest_artifact_id': manifest_artifact_id}
        existing = self._sources.get(source_id)
        if existing is not None and existing['source_sha256'] != source_sha:
            _fail('id_collision', 'source id already names a different source hash')
        if existing is None or existing != entry:
            # The same original source may be bound by several runs; the most
            # recently projected run is the one re-checked on resolve_source.
            self._sources[source_id] = entry
        return self._sources[source_id]

    def project(self, selector):
        """Validate, hash and register one file; returns the public record."""
        try:
            _, sha, size, _ = self._measure(selector)
        except _Missing:
            _fail('not_regular_file', 'selector does not name an existing regular file')
        run_id = selector.split('/', 1)[0]
        source_id, binding, *_ = self._source_binding(run_id)
        entry = {'artifact_id': artifact_id_for(selector, sha), 'selector': selector, 'sha256': sha,
                 'size_bytes': size, 'kind': kind_for(selector), 'source_id': source_id,
                 'source_binding': binding}
        return _public(self._register(entry))

    def project_source(self, run_id):
        """Bind a run to its original source by manifest hash; never reads source.path."""
        check_run_id(run_id)
        selector = f'{run_id}/manifest.json'
        try:
            _, manifest_sha, size, _ = self._measure(selector, keep_limit=MAX_MANIFEST_BYTES)
        except _Missing:
            _fail('not_regular_file', 'run has no regular manifest.json')
        source_id, binding, bound_sha, manifest_artifact_id, source_sha = self._source_binding(run_id)
        if bound_sha != manifest_sha:
            _fail('changed_during_hash', 'manifest changed between reads')
        self._register({'artifact_id': manifest_artifact_id, 'selector': selector, 'sha256': manifest_sha,
                        'size_bytes': size, 'kind': 'json', 'source_id': source_id,
                        'source_binding': binding})
        if source_id is not None:
            self._register_source(source_id, run_id, source_sha, manifest_artifact_id)
        return {'source_id': source_id, 'source_sha256': source_sha, 'run_id': run_id,
                'manifest_artifact_id': manifest_artifact_id, 'source_binding': binding,
                'claim_class': CLAIM_CLASS, 'not_a_job_service': True, 'id_version': ID_VERSION}

    # ----------------------------------------------------------------- resolution

    def resolve(self, artifact_id):
        """Re-hash, then report current (with private path), stale or missing."""
        if not isinstance(artifact_id, str) or not ARTIFACT_ID.fullmatch(artifact_id):
            _fail('malformed_id', 'artifact id must be art_ followed by 32 lowercase hex digits')
        entry = self._artifacts.get(artifact_id)
        if entry is None:
            _fail('unknown_id', 'artifact id is not registered in this index')
        record = _public(entry)
        try:
            path, sha, _, _ = self._measure(entry['selector'])
        except _Missing:
            return Resolution(artifact_id, 'missing', record)
        except ArtifactIdError as error:
            if error.code == 'not_regular_file':
                return Resolution(artifact_id, 'missing', record)
            raise
        if sha != entry['sha256']:
            return Resolution(artifact_id, 'stale', record, observed_sha256=sha)
        return Resolution(artifact_id, 'current', record, path=path, observed_sha256=sha)

    def resolve_source(self, source_id):
        """Re-read and re-hash the bound manifest; changed bytes -> stale."""
        if not isinstance(source_id, str) or not SOURCE_ID.fullmatch(source_id):
            _fail('malformed_id', 'source id must be src_ followed by 32 lowercase hex digits')
        entry = self._sources.get(source_id)
        if entry is None:
            _fail('unknown_id', 'source id is not registered in this index')
        record = {'source_id': source_id, 'source_sha256': entry['source_sha256'],
                  'manifest_artifact_id': entry['manifest_artifact_id'], 'source_binding': 'bound',
                  'claim_class': CLAIM_CLASS, 'not_a_job_service': True, 'id_version': ID_VERSION}
        manifest = self._artifacts[entry['manifest_artifact_id']]
        try:
            path, sha, _, _ = self._measure(manifest['selector'])
        except _Missing:
            return Resolution(source_id, 'missing', record)
        except ArtifactIdError as error:
            if error.code == 'not_regular_file':
                return Resolution(source_id, 'missing', record)
            raise
        if sha != manifest['sha256']:
            return Resolution(source_id, 'stale', record, observed_sha256=sha)
        return Resolution(source_id, 'current', record, path=path, observed_sha256=sha)

    # ----------------------------------------------------------------- persistence

    def to_document(self):
        return {'schema': INDEX_SCHEMA, 'schema_version': 1, 'id_version': ID_VERSION,
                'not_a_job_service': True, 'claim_class': CLAIM_CLASS,
                'artifacts': [{field: self._artifacts[key][field] for field in INDEX_ARTIFACT_KEYS}
                              for key in sorted(self._artifacts)],
                'sources': [dict(self._sources[key]) for key in sorted(self._sources)]}

    def _inside_runs(self, directory):
        """Filesystem-identity containment: is ``directory`` the runs root or below it?

        Lexical comparison is not enough on case-insensitive APFS (realpath
        keeps the caller's casing), so every ancestor of the resolved directory
        is compared to the runs root by ``(st_dev, st_ino)``.
        """
        runs_stat = os.stat(self.runs)
        runs_key = (runs_stat.st_dev, runs_stat.st_ino)
        for candidate in (directory, *directory.parents):
            try:
                info = os.stat(candidate)
            except OSError:
                return True  # unverifiable ancestry is refused, never assumed safe
            if (info.st_dev, info.st_ino) == runs_key:
                return True
        return False

    def dump(self, target):
        """Write a deterministic index; refuses runs-root targets and existing files."""
        target = Path(target)
        if not target.is_absolute():
            target = Path.cwd() / target
        try:
            parent = target.parent.resolve(strict=True)
        except OSError:
            _fail('bad_index', 'index target directory does not exist')
        resolved = parent / target.name
        if self._inside_runs(parent):
            _fail('write_inside_runs', 'index may not be written under artifacts/runs')
        if os.path.lexists(resolved):
            _fail('target_exists', 'index target already exists')
        data = (json.dumps(self.to_document(), sort_keys=True, indent=2, ensure_ascii=True) + '\n').encode()
        descriptor, temp = tempfile.mkstemp(prefix='.artifact-index-', suffix='.tmp', dir=parent)
        try:
            with os.fdopen(descriptor, 'wb') as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temp, resolved)  # atomic, never clobbers
            except FileExistsError:
                _fail('target_exists', 'index target already exists')
        finally:
            try:
                os.unlink(temp)
            except FileNotFoundError:
                pass
        return {'artifacts': len(self._artifacts), 'sources': len(self._sources),
                'sha256': hashlib.sha256(data).hexdigest()}

    @classmethod
    def load(cls, path, root=None, max_bytes=DEFAULT_MAX_BYTES):
        """Load an index and re-derive every ID; stored paths are never trusted."""
        index = cls(root, max_bytes)
        try:
            descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
                                 | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_CLOEXEC', 0))
        except OSError:
            _fail('bad_index', 'index is not a readable non-symlink file')
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_INDEX_BYTES:
                _fail('bad_index', 'index must be a bounded regular file')
            data = b''
            while True:
                chunk = os.read(descriptor, CHUNK)
                if not chunk:
                    break
                data += chunk
                if len(data) > MAX_INDEX_BYTES:
                    _fail('bad_index', 'index grew beyond its bound')
        finally:
            os.close(descriptor)
        try:
            doc = _strict_json(data, 'index')
        except ValueError as error:
            _fail('bad_index', str(error))
        index._ingest(doc)
        return index

    def _ingest(self, doc):
        top = ('schema', 'schema_version', 'id_version', 'not_a_job_service', 'claim_class',
               'artifacts', 'sources')
        if not isinstance(doc, dict) or set(doc) != set(top):
            _fail('bad_index', 'index top-level keys are not the closed v1 set')
        header = (doc['schema'], doc['schema_version'], doc['id_version'], doc['not_a_job_service'],
                  doc['claim_class'])
        expected = (INDEX_SCHEMA, 1, ID_VERSION, True, CLAIM_CLASS)
        if any(type(value) is not type(want) or value != want for value, want in zip(header, expected)):
            _fail('bad_index', 'index header constants differ from v1')
        for name, keys in (('artifacts', INDEX_ARTIFACT_KEYS), ('sources', INDEX_SOURCE_KEYS)):
            if not isinstance(doc[name], list) or len(doc[name]) > MAX_INDEX_ENTRIES:
                _fail('bad_index', f'index {name} must be a bounded array')
            for item in doc[name]:
                if not isinstance(item, dict) or set(item) != set(keys):
                    _fail('bad_index', f'index {name} entry keys are not the closed v1 set')
        for item in doc['artifacts']:
            try:
                check_selector(item['selector'])
            except ArtifactIdError as error:
                _fail('bad_index', f'stored selector refused ({error.code})')
            sha, size = item['sha256'], item['size_bytes']
            if not isinstance(sha, str) or not SHA256.fullmatch(sha):
                _fail('bad_index', 'stored sha256 is malformed')
            if not isinstance(size, int) or isinstance(size, bool) or size < 0:
                _fail('bad_index', 'stored size is malformed')
            if item['artifact_id'] != artifact_id_for(item['selector'], sha):
                _fail('bad_index', 'stored artifact id does not re-derive from selector and hash')
            if item['kind'] != kind_for(item['selector']):
                _fail('bad_index', 'stored kind does not match selector')
            binding, source_id = item['source_binding'], item['source_id']
            if binding not in ('bound', 'unknown') or (binding == 'bound') != isinstance(source_id, str) \
                    or (source_id is not None and not SOURCE_ID.fullmatch(source_id)):
                _fail('bad_index', 'stored source binding is malformed')
            if item['artifact_id'] in self._artifacts:
                _fail('bad_index', 'index repeats an artifact id')
            self._artifacts[item['artifact_id']] = dict(item)
        for item in doc['sources']:
            sha = item['source_sha256']
            if not isinstance(sha, str) or not SHA256.fullmatch(sha) or item['source_id'] != source_id_for(sha):
                _fail('bad_index', 'stored source id does not re-derive from source hash')
            try:
                check_run_id(item['run_id'])
            except ArtifactIdError:
                _fail('bad_index', 'stored run id is unsafe')
            manifest = self._artifacts.get(item['manifest_artifact_id'])
            if manifest is None or manifest['selector'] != f'{item["run_id"]}/manifest.json':
                _fail('bad_index', 'stored source does not reference its run manifest artifact')
            if item['source_id'] in self._sources:
                _fail('bad_index', 'index repeats a source id')
            self._sources[item['source_id']] = dict(item)


# --------------------------------------------------------------------------- CLI

def _emit(stream, value):
    stream.write(json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + '\n')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--root', default=None, help='repository root (default: this checkout)')
    parser.add_argument('--write-index', default=None, help='write the index to a fresh file outside artifacts/runs')
    commands = parser.add_subparsers(dest='command', required=True)
    project_parser = commands.add_parser('project')
    project_parser.add_argument('selectors', nargs='+')
    source_parser = commands.add_parser('source')
    source_parser.add_argument('run_id')
    resolve_parser = commands.add_parser('resolve')
    resolve_parser.add_argument('--index', required=True)
    resolve_parser.add_argument('id')
    args = parser.parse_args(argv)
    status = 0
    try:
        if args.command == 'resolve':
            index = ArtifactIndex.load(args.index, args.root)
            resolution = (index.resolve_source(args.id) if args.id.startswith('src_')
                          else index.resolve(args.id))
            result = resolution.public()
            status = 0 if resolution.state == 'current' else 1
        else:
            index = ArtifactIndex(args.root)
            if args.command == 'source':
                result = index.project_source(args.run_id)
            else:
                records, refusals = [], []
                for position, selector in enumerate(args.selectors):
                    try:
                        records.append(index.project(selector))
                    except ArtifactIdError as error:
                        refusals.append({'position': position, 'code': error.code})
                result = {'records': records, 'refusals': refusals, 'claim_class': CLAIM_CLASS,
                          'not_a_job_service': True, 'id_version': ID_VERSION}
                status = 0 if not refusals else 1
        if args.write_index:
            result = {**result, 'index_written': index.dump(args.write_index)}
    except ArtifactIdError as error:
        _emit(sys.stderr, {'status': 'error', 'code': error.code, 'error': error.message})
        return 1
    _emit(sys.stdout, result)
    return status


if __name__ == '__main__':
    raise SystemExit(main())
