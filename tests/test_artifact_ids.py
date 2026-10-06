"""Artifact/source ID projection: confinement, refusal codes, re-hash staleness, idempotency.

Synthetic temporary run roots only: fixed byte contents, no randomness, no
FFmpeg, no decoding, no recording reads, no network.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import artifact_ids as ids  # noqa: E402

SOURCE_SHA = hashlib.sha256(b'fixture-source').hexdigest()
HOST_SENTINEL = '/Users/HOST-PATH-SENTINEL/Documents/take.mov'
WAV_BYTES = b'RIFF' + bytes(range(256)) * 16


def manifest_bytes(source_sha=SOURCE_SHA, path=HOST_SENTINEL):
    source = {'path': path, 'size_bytes': 14}
    if source_sha is not None:
        source['sha256'] = source_sha
    return json.dumps({'schema_version': 1, 'run_id': 'RUN-A', 'source': source}, sort_keys=True).encode()


def tree_state(base):
    """(relative path, sha256, size, mtime_ns) for every entry; symlinks are not followed."""
    rows = []
    for directory, names, files in os.walk(base, followlinks=False):
        for name in sorted(names + files):
            path = Path(directory) / name
            info = os.lstat(path)
            digest = None
            if stat.S_ISREG(info.st_mode):
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
            rows.append((str(path.relative_to(base)), digest, info.st_size, info.st_mtime_ns))
    return sorted(rows)


class Fixture:
    def __init__(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / 'repo'
        self.runs = self.root / 'artifacts' / 'runs'
        self.run = self.runs / 'RUN-A'
        (self.run / 'export').mkdir(parents=True)
        self.outside = self.base / 'outside'
        self.outside.mkdir()
        (self.outside / 'secret.json').write_bytes(b'{"secret": true}')
        self.write('manifest.json', manifest_bytes())
        self.write('result.json', b'{"status": "ok", "value": 1}')
        self.write('audio.wav', WAV_BYTES)
        self.write('export/outcome.json', b'{"outcome": "rendered"}')

    def write(self, relative, data, mode=0o644):
        path = self.run / relative
        path.write_bytes(data)
        os.chmod(path, mode)
        return path

    def index(self, **kwargs):
        return ids.ArtifactIndex(self.root, **kwargs)

    def close(self):
        self.temp.cleanup()


class ArtifactIdTests(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture()
        self.addCleanup(self.fx.close)

    def refused(self, code, func, *args):
        with self.assertRaises(ids.ArtifactIdError) as caught:
            func(*args)
        self.assertEqual(caught.exception.code, code, f'{args!r}: {caught.exception}')
        return caught.exception

    # 1
    def test_ids_are_opaque_deterministic_and_versioned(self):
        index = self.fx.index()
        record = index.project('RUN-A/result.json')
        content = hashlib.sha256((self.fx.run / 'result.json').read_bytes()).hexdigest()
        expected = 'art_' + hashlib.sha256(b'video-utils/artifact-id/v1\0RUN-A/result.json\0'
                                           + content.encode()).hexdigest()[:32]
        self.assertEqual(record['artifact_id'], expected)
        self.assertRegex(record['artifact_id'], r'^art_[0-9a-f]{32}$')
        self.assertEqual(record['sha256'], content)
        self.assertEqual(set(record), set(ids.PUBLIC_KEYS))
        self.assertEqual((record['id_version'], record['claim_class'], record['not_a_job_service']),
                         (1, 'hash_measurement', True))
        self.assertEqual(record['kind'], 'json')
        self.assertEqual(index.project('RUN-A/audio.wav')['kind'], 'wav')
        # Another index over the same bytes derives the same ID; ID omits selector and content.
        self.assertEqual(self.fx.index().project('RUN-A/result.json'), record)
        for leak in ('RUN-A', 'result', content[:12]):
            self.assertNotIn(leak, record['artifact_id'])
        # Same bytes under another selector is a different artifact.
        (self.fx.run / 'export' / 'result.json').write_bytes((self.fx.run / 'result.json').read_bytes())
        other = index.project('RUN-A/export/result.json')
        self.assertNotEqual(other['artifact_id'], record['artifact_id'])
        self.assertEqual(other['sha256'], record['sha256'])

    # 2
    def test_project_and_resolve_current_returns_private_path_public_omits_it(self):
        index = self.fx.index()
        record = index.project('RUN-A/export/outcome.json')
        resolution = index.resolve(record['artifact_id'])
        self.assertEqual(resolution.state, 'current')
        self.assertEqual(resolution.path, self.fx.run / 'export' / 'outcome.json')
        public = resolution.public()
        self.assertEqual(public, record)
        text = json.dumps(public)
        for leak in (str(self.fx.base), 'outcome.json', 'RUN-A', 'export'):
            self.assertNotIn(leak, text)

    # 3
    def test_changed_bytes_same_size_resolves_stale_without_path(self):
        index = self.fx.index()
        record = index.project('RUN-A/audio.wav')
        changed = bytearray(WAV_BYTES)
        changed[100] ^= 0xFF
        self.fx.write('audio.wav', bytes(changed))
        self.assertEqual((self.fx.run / 'audio.wav').stat().st_size, len(WAV_BYTES))
        resolution = index.resolve(record['artifact_id'])
        self.assertEqual(resolution.state, 'stale')
        self.assertIsNone(resolution.path)
        self.assertEqual(resolution.public()['sha256'], record['sha256'])
        self.assertNotEqual(resolution.observed_sha256, record['sha256'])
        self.fx.write('audio.wav', WAV_BYTES)  # restoring the bytes restores currency
        self.assertEqual(index.resolve(record['artifact_id']).state, 'current')

    # 4
    def test_changed_size_and_deleted_file_resolve_stale_and_missing(self):
        index = self.fx.index()
        record = index.project('RUN-A/result.json')
        self.fx.write('result.json', b'{"status": "ok", "value": 12}')
        self.assertEqual(index.resolve(record['artifact_id']).state, 'stale')
        (self.fx.run / 'result.json').unlink()
        missing = index.resolve(record['artifact_id'])
        self.assertEqual((missing.state, missing.path), ('missing', None))
        nested = index.project('RUN-A/export/outcome.json')
        for path in (self.fx.run / 'export').iterdir():
            path.unlink()
        (self.fx.run / 'export').rmdir()
        self.assertEqual(index.resolve(nested['artifact_id']).state, 'missing')
        # A directory now standing where the file was is not a regular file -> missing.
        (self.fx.run / 'result.json').mkdir()
        self.assertEqual(index.resolve(record['artifact_id']).state, 'missing')

    # 5
    def test_touch_without_byte_change_stays_current(self):
        index = self.fx.index()
        record = index.project('RUN-A/audio.wav')
        path = self.fx.run / 'audio.wav'
        info = path.stat()
        os.utime(path, ns=(info.st_atime_ns + 5_000_000_000, info.st_mtime_ns + 5_000_000_000))
        resolution = index.resolve(record['artifact_id'])
        self.assertEqual(resolution.state, 'current')
        self.assertEqual(resolution.public(), record)

    # 6
    def test_repeated_project_and_resolve_are_idempotent_and_write_nothing(self):
        index = self.fx.index()
        before = tree_state(self.fx.root)
        selectors = ['RUN-A/manifest.json', 'RUN-A/result.json', 'RUN-A/audio.wav', 'RUN-A/export/outcome.json']
        first = [index.project(selector) for selector in selectors]
        source = index.project_source('RUN-A')
        count, sources = len(index), index.source_count
        self.assertEqual(count, 4)
        for _ in range(3):
            self.assertEqual([index.project(selector) for selector in selectors], first)
            self.assertEqual(index.project_source('RUN-A'), source)
            self.assertEqual([index.resolve(r['artifact_id']).public() for r in first], first)
            self.assertEqual(index.resolve_source(source['source_id']).state, 'current')
            self.assertEqual((len(index), index.source_count), (count, sources))
        self.assertEqual(tree_state(self.fx.root), before)
        fresh = self.fx.index()
        for selector in reversed(selectors):
            fresh.project(selector)
        fresh.project_source('RUN-A')
        self.assertEqual(fresh.to_document(), index.to_document())  # order-independent, deterministic

    # 7
    def test_host_paths_and_repo_relative_forms_refused(self):
        index = self.fx.index()
        cases = {
            'host_path_refused': [str(self.fx.run / 'result.json'), '/etc/passwd', '~/RUN-A/result.json',
                                  '~jess/x/y.json', 'C:/RUN-A/result.json', 'file:///etc/passwd',
                                  'https://example.invalid/a.json', '//server/share/a.json',
                                  '\\\\server\\share\\a.json'],
            'outside_runs_root': ['artifacts/runs/RUN-A/result.json', 'artifacts/RUN-A/result.json'],
        }
        for code, selectors in cases.items():
            for selector in selectors:
                self.refused(code, index.project, selector)
        self.assertEqual(len(index), 0)

    # 8
    def test_traversal_and_escaping_symlinks_refused(self):
        index = self.fx.index()
        for selector in ('RUN-A/../RUN-A/result.json', '../outside/secret.json', 'RUN-A/export/../../x.json'):
            self.refused('outside_runs_root', index.project, selector)
        os.symlink(self.fx.outside, self.fx.runs / 'RUN-LINK')
        self.refused('symlink_component', index.project, 'RUN-LINK/secret.json')
        os.symlink(self.fx.outside / 'secret.json', self.fx.run / 'leak.json')
        self.refused('symlink_component', index.project, 'RUN-A/leak.json')
        os.symlink(self.fx.run / 'result.json', self.fx.run / 'alias.json')  # internal link
        self.refused('symlink_component', index.project, 'RUN-A/alias.json')
        os.symlink(self.fx.run / 'export', self.fx.run / 'export-link')
        self.refused('symlink_component', index.project, 'RUN-A/export-link/outcome.json')
        self.assertEqual(len(index), 0)
        # A symlinked runs root itself is refused at construction.
        with tempfile.TemporaryDirectory() as temp:
            other = Path(temp).resolve()
            (other / 'artifacts').mkdir()
            os.symlink(self.fx.runs, other / 'artifacts' / 'runs')
            self.refused('symlink_component', ids.ArtifactIndex, other)

    # 9
    def test_executables_refused(self):
        index = self.fx.index()
        self.fx.write('mode.json', b'{"x": 1}', mode=0o755)
        self.fx.write('group.json', b'{"x": 1}', mode=0o654)
        self.fx.write('shebang.json', b'#!/bin/sh\necho hi\n')
        self.fx.write('elf.bin', b'\x7fELF\x02\x01\x01' + bytes(32))
        self.fx.write('macho.bin', b'\xcf\xfa\xed\xfe' + bytes(32))
        self.fx.write('macho32.bin', b'\xfe\xed\xfa\xce' + bytes(32))
        self.fx.write('fat.bin', b'\xca\xfe\xba\xbe' + bytes(32))
        for name in ('mode.json', 'group.json', 'shebang.json', 'elf.bin', 'macho.bin', 'macho32.bin', 'fat.bin'):
            self.refused('executable_refused', index.project, f'RUN-A/{name}')
        self.assertEqual(len(index), 0)
        # A file that becomes executable after projection refuses on resolve (no path).
        record = index.project('RUN-A/result.json')
        os.chmod(self.fx.run / 'result.json', 0o744)
        self.refused('executable_refused', index.resolve, record['artifact_id'])

    # 10
    def test_filter_and_shell_strings_refused(self):
        index = self.fx.index()
        hostile = ['anull,volume=2', 'RUN-A/x;rm', 'RUN-A/a|b.json', 'RUN-A/$(id).json', 'RUN-A/`id`.json',
                   'RUN-A/a b.json', 'RUN-A/a\tb.json', 'RUN-A/a\nb.json', "RUN-A/'q'.json", 'RUN-A/"q".json',
                   'RUN-A/[0:a]', 'RUN-A/volume=2', 'RUN-A/a:b.json', 'RUN-A/a&b.json', 'RUN-A/a>b.json',
                   'RUN-A/*.json']
        for selector in hostile:
            self.refused('filter_string_refused', index.project, selector)
        self.assertGreaterEqual(len(hostile), 15)
        self.assertEqual(len(index), 0)

    # 11
    def test_hidden_partial_dir_fifo_refused(self):
        index = self.fx.index()
        self.fx.write('.video-frame-count-cache.json', b'{"frames": 1}')
        self.fx.write('render.partial.wav', WAV_BYTES)
        self.fx.write('render.wav.partial', WAV_BYTES)
        for selector in ('RUN-A/.video-frame-count-cache.json', 'RUN-A/render.partial.wav',
                         'RUN-A/render.wav.partial', 'RUN-A/-rf.json', 'RUN-A//result.json', 'RUN-A/./result.json',
                         'RUN-A', 'RUN-A/result.json/', 'RUN-A/a\\b.json', 'RUN-A/x\0.json',
                         'RUN-A/' + 'a' * 129, '/'.join(['d'] * 17), 'RUN-A/é.json', ''):
            self.refused('unsafe_component', index.project, selector)
        self.refused('unsafe_component', index.project, 'RUN-A/' + 'a/' * 600 + 'x')
        self.refused('not_regular_file', index.project, 'RUN-A/export')
        os.mkfifo(self.fx.run / 'pipe.json')
        self.refused('not_regular_file', index.project, 'RUN-A/pipe.json')
        self.refused('not_regular_file', index.project, 'RUN-A/absent.json')
        small = self.fx.index(max_bytes=64)
        self.refused('too_large', small.project, 'RUN-A/audio.wav')
        self.assertEqual((len(index), len(small)), (0, 0))

    # 12
    def test_source_id_from_manifest_hash_never_exposes_host_path(self):
        index = self.fx.index()
        source = index.project_source('RUN-A')
        expected = 'src_' + hashlib.sha256(b'video-utils/source-id/v1\0' + SOURCE_SHA.encode()).hexdigest()[:32]
        self.assertEqual(source['source_id'], expected)
        self.assertEqual((source['source_binding'], source['source_sha256'], source['run_id']),
                         ('bound', SOURCE_SHA, 'RUN-A'))
        record = index.project('RUN-A/audio.wav')
        self.assertEqual((record['source_id'], record['source_binding']), (expected, 'bound'))
        resolution = index.resolve_source(expected)
        self.assertEqual(resolution.state, 'current')
        outputs = [source, record, resolution.public(), index.resolve(record['artifact_id']).public(),
                   index.to_document()]
        for value in outputs:
            text = json.dumps(value)
            self.assertNotIn('HOST-PATH-SENTINEL', text)
            self.assertNotIn('/Users', text)
            self.assertNotIn(str(self.fx.base), text)
        # A different source.path with the same source hash yields the same source ID.
        self.fx.write('manifest.json', manifest_bytes(path='/elsewhere/other-name.mov'))
        self.assertEqual(self.fx.index().project_source('RUN-A')['source_id'], expected)

    # 13
    def test_missing_source_hash_is_unknown_not_guessed(self):
        for content in (manifest_bytes(source_sha=None), manifest_bytes(source_sha='ABC'),
                        manifest_bytes(source_sha=SOURCE_SHA.upper()), b'{"source": "x"}', b'[]',
                        b'{"source": {"sha256": "' + SOURCE_SHA.encode() + b'"}, "source": {}}',
                        b'{"x": NaN}', b'not json'):
            self.fx.write('manifest.json', content)
            index = self.fx.index()
            source = index.project_source('RUN-A')
            self.assertIsNone(source['source_id'], content)
            self.assertIsNone(source['source_sha256'])
            self.assertEqual(source['source_binding'], 'unknown')
            record = index.project('RUN-A/result.json')
            self.assertEqual((record['source_id'], record['source_binding']), (None, 'unknown'))
            self.assertEqual(index.source_count, 0)
        (self.fx.run / 'manifest.json').unlink()
        index = self.fx.index()
        self.assertEqual(index.project('RUN-A/result.json')['source_binding'], 'unknown')
        self.refused('not_regular_file', index.project_source, 'RUN-A')
        for run_id in ('../RUN-A', 'RUN-A/x', '.hidden', '-x', ''):
            self.refused('unsafe_component', index.project_source, run_id)

    # 14
    def test_manifest_change_marks_source_stale(self):
        index = self.fx.index()
        source = index.project_source('RUN-A')
        manifest_record = index.resolve(source['manifest_artifact_id'])
        self.assertEqual(manifest_record.state, 'current')
        self.fx.write('manifest.json', manifest_bytes() + b' ')
        self.assertEqual(index.resolve_source(source['source_id']).state, 'stale')
        self.assertIsNone(index.resolve_source(source['source_id']).path)
        self.assertEqual(index.resolve(source['manifest_artifact_id']).state, 'stale')
        (self.fx.run / 'manifest.json').unlink()
        self.assertEqual(index.resolve_source(source['source_id']).state, 'missing')

    # 15
    def test_symlink_swapped_after_projection_refuses_on_resolve(self):
        index = self.fx.index()
        record = index.project('RUN-A/result.json')
        nested = index.project('RUN-A/export/outcome.json')
        target = self.fx.run / 'result.json'
        target.unlink()
        os.symlink(self.fx.outside / 'secret.json', target)
        self.refused('symlink_component', index.resolve, record['artifact_id'])
        export = self.fx.run / 'export'
        os.rename(export, self.fx.base / 'moved-export')
        os.symlink(self.fx.base / 'moved-export', export)
        self.refused('symlink_component', index.resolve, nested['artifact_id'])
        self.fx.runs.joinpath('RUN-A').rename(self.fx.base / 'moved-run')
        os.symlink(self.fx.base / 'moved-run', self.fx.runs / 'RUN-A')
        self.refused('symlink_component', index.resolve, record['artifact_id'])

    # 16
    def test_dump_refuses_runs_root_and_existing_target_and_roundtrips(self):
        index = self.fx.index()
        records = [index.project(s) for s in ('RUN-A/result.json', 'RUN-A/audio.wav')]
        source = index.project_source('RUN-A')
        before = tree_state(self.fx.runs)
        self.refused('write_inside_runs', index.dump, self.fx.run / 'index.json')
        self.refused('write_inside_runs', index.dump, self.fx.runs / 'index.json')
        os.symlink(self.fx.run, self.fx.base / 'runlink')
        self.refused('write_inside_runs', index.dump, self.fx.base / 'runlink' / 'index.json')
        self.assertEqual(tree_state(self.fx.runs), before)
        target = self.fx.base / 'index.json'
        written = index.dump(target)
        self.assertEqual(written['artifacts'], 3)
        self.refused('target_exists', index.dump, target)
        text = target.read_text()
        self.assertEqual(text, json.dumps(json.loads(text), sort_keys=True, indent=2) + '\n')
        self.assertNotIn(str(self.fx.base), text)
        self.assertNotIn('HOST-PATH-SENTINEL', text)
        second = self.fx.base / 'index2.json'
        index.dump(second)
        self.assertEqual(second.read_bytes(), target.read_bytes())
        loaded = ids.ArtifactIndex.load(target, self.fx.root)
        self.assertEqual(loaded.to_document(), index.to_document())
        self.assertEqual([loaded.resolve(r['artifact_id']).public() for r in records], records)
        self.assertEqual(loaded.resolve_source(source['source_id']).state, 'current')
        self.assertEqual([p.name for p in self.fx.base.iterdir() if p.name.startswith('.artifact-index-')], [])
        # Tampered indexes are refused: forged ID, unsafe selector, extra key, duplicate key.
        doc = json.loads(text)
        tampered = [
            lambda d: d['artifacts'][0].__setitem__('selector', 'RUN-A/forged.json'),
            lambda d: d['artifacts'][0].__setitem__('selector', '/etc/passwd'),
            lambda d: d['artifacts'][0].__setitem__('path', '/etc/passwd'),
            lambda d: d.__setitem__('not_a_job_service', False),
            lambda d: d.__setitem__('schema_version', True),
            lambda d: d['sources'][0].__setitem__('source_sha256', '0' * 64),
        ]
        for number, mutate in enumerate(tampered):
            copy_doc = json.loads(text)
            mutate(copy_doc)
            path = self.fx.base / f'bad-{number}.json'
            path.write_text(json.dumps(copy_doc))
            self.refused('bad_index', ids.ArtifactIndex.load, path, self.fx.root)
        dup = self.fx.base / 'dup.json'
        dup.write_text(text.replace('"claim_class": "hash_measurement",',
                                    '"claim_class": "hash_measurement",\n  "claim_class": "hash_measurement",', 1))
        self.refused('bad_index', ids.ArtifactIndex.load, dup, self.fx.root)
        self.assertEqual(doc['not_a_job_service'], True)

    # 16b
    def test_dump_refuses_case_variant_runs_paths_by_filesystem_identity(self):
        upper = self.fx.root / 'ARTIFACTS' / 'RUNS'
        if not upper.exists() or not os.path.samefile(upper, self.fx.runs):
            self.skipTest('case-sensitive filesystem: case variants are distinct directories')
        index = self.fx.index()
        index.project('RUN-A/result.json')
        before = tree_state(self.fx.runs)
        variants = (self.fx.root / 'artifacts' / 'RUNS' / 'RUN-A' / 'index.json',
                    self.fx.root / 'Artifacts' / 'runs' / 'idx2.json',
                    self.fx.root / 'ARTIFACTS' / 'RUNS' / 'idx3.json',
                    self.fx.root / 'artifacts' / 'runs' / 'run-a' / 'export' / 'idx4.json')
        for target in variants:
            self.refused('write_inside_runs', index.dump, target)
        self.assertEqual(tree_state(self.fx.runs), before)
        script = str(ROOT / 'scripts' / 'artifact_ids.py')
        for target in variants[:2]:
            cli = subprocess.run([sys.executable, script, '--root', str(self.fx.root), '--write-index',
                                  str(target), 'project', 'RUN-A/audio.wav'],
                                 capture_output=True, text=True, timeout=60, check=False)
            self.assertEqual(cli.returncode, 1)
            self.assertEqual(json.loads(cli.stderr)['code'], 'write_inside_runs')
        self.assertEqual(tree_state(self.fx.runs), before)
        # A sibling outside the runs root is still writable under any casing.
        (self.fx.root / 'artifacts' / 'indexes').mkdir()
        written = index.dump(self.fx.root / 'ARTIFACTS' / 'Indexes' / 'index.json')
        self.assertEqual(written['artifacts'], 1)
        self.assertEqual(tree_state(self.fx.runs), before)

    # 17
    def test_malformed_unknown_and_colliding_ids_refused(self):
        index = self.fx.index()
        record = index.project('RUN-A/result.json')
        for value in ('', 'art_', 'art_' + 'g' * 32, 'ART_' + '0' * 32, 'art_' + '0' * 31, 'art_' + '0' * 33,
                      record['artifact_id'].upper(), None, 7, '../art_' + '0' * 32, 'RUN-A/result.json'):
            self.refused('malformed_id', index.resolve, value)
        self.refused('unknown_id', index.resolve, 'art_' + '0' * 32)
        self.refused('malformed_id', index.resolve_source, 'art_' + '0' * 32)
        self.refused('unknown_id', index.resolve_source, 'src_' + '0' * 32)
        # Force a collision: register a different (selector, sha) under an existing ID.
        entry = dict(index._artifacts[record['artifact_id']])
        entry['selector'] = 'RUN-A/audio.wav'
        self.refused('id_collision', index._register, entry)
        self.assertEqual(len(index), 1)

    # extra coverage
    def test_changed_during_hash_detected_for_cooperative_writer(self):
        fx = self.fx

        class Racing(ids.ArtifactIndex):
            writes = 0

            def _read_chunk(self, descriptor):
                chunk = super()._read_chunk(descriptor)
                if chunk and not self.writes:
                    self.writes += 1
                    with open(fx.run / 'audio.wav', 'r+b') as handle:  # same size, new mtime
                        handle.write(b'RIFX')
                    info = os.stat(fx.run / 'audio.wav')
                    os.utime(fx.run / 'audio.wav', ns=(info.st_atime_ns, info.st_mtime_ns + 1_000_000_000))
                return chunk

        racing = Racing(fx.root)
        self.refused('changed_during_hash', racing.project, 'RUN-A/audio.wav')
        self.assertEqual(len(racing), 0)

        class Growing(ids.ArtifactIndex):
            def _read_chunk(self, descriptor):
                chunk = super()._read_chunk(descriptor)
                if chunk:  # an unbounded appender is cut off at the pre-open size
                    with open(fx.run / 'result.json', 'ab') as handle:
                        handle.write(b' ')
                return chunk

        growing = Growing(fx.root)
        self.refused('changed_during_hash', growing.project, 'RUN-A/result.json')
        self.assertEqual(len(growing), 0)

    def test_runs_root_must_exist_and_cli_round_trip(self):
        with tempfile.TemporaryDirectory() as temp:
            self.refused('outside_runs_root', ids.ArtifactIndex, temp)
        script = str(ROOT / 'scripts' / 'artifact_ids.py')
        index_path = self.fx.base / 'cli-index.json'

        def run(*args):
            return subprocess.run([sys.executable, script, '--root', str(self.fx.root), *args],
                                  capture_output=True, text=True, timeout=60, check=False)

        first = run('--write-index', str(index_path), 'project', 'RUN-A/result.json', 'RUN-A/audio.wav',
                    'anull,volume=2', '/etc/passwd')
        self.assertEqual(first.returncode, 1)
        out = json.loads(first.stdout)
        self.assertEqual(len(out['records']), 2)
        self.assertEqual([(r['position'], r['code']) for r in out['refusals']],
                         [(2, 'filter_string_refused'), (3, 'host_path_refused')])
        self.assertNotIn(str(self.fx.base), first.stdout)
        repeat = run('project', 'RUN-A/result.json', 'RUN-A/audio.wav')
        self.assertEqual(repeat.returncode, 0)
        self.assertEqual(json.loads(repeat.stdout)['records'], out['records'])
        resolved = run('resolve', '--index', str(index_path), out['records'][0]['artifact_id'])
        self.assertEqual(resolved.returncode, 0, resolved.stderr)
        self.assertEqual(json.loads(resolved.stdout), out['records'][0])
        self.assertNotIn(str(self.fx.base), resolved.stdout)
        source = run('source', 'RUN-A')
        self.assertEqual(source.returncode, 0)
        self.assertNotIn('HOST-PATH-SENTINEL', source.stdout)
        error = run('resolve', '--index', str(index_path), 'art_bad')
        self.assertEqual(error.returncode, 1)
        self.assertEqual(json.loads(error.stderr)['code'], 'malformed_id')
        self.fx.write('result.json', b'{"status": "changed"}')
        stale = run('resolve', '--index', str(index_path), out['records'][0]['artifact_id'])
        self.assertEqual((stale.returncode, json.loads(stale.stdout)['state']), (1, 'stale'))
        inside = run('--write-index', str(self.fx.run / 'idx.json'), 'project', 'RUN-A/audio.wav')
        self.assertEqual(json.loads(inside.stderr)['code'], 'write_inside_runs')
        self.assertFalse((self.fx.run / 'idx.json').exists())
        self.assertTrue(re.fullmatch(r'art_[0-9a-f]{32}', out['records'][1]['artifact_id']))


if __name__ == '__main__':
    unittest.main()
