"""Capability metadata pilot: closed schema, registry cross-checks, static traversal.

Metadata-only. No FFmpeg, no audio decoding, no recording reads, no network;
every traversal assertion is a static repository check, never test execution.
"""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import capabilities as cap  # noqa: E402

CAPS = ROOT / 'program' / 'capabilities.json'
TOOLS = ROOT / 'program' / 'tools.json'
EIGHT = ['denoise', 'clicks', 'capture_profile', 'apply_capture_profile', 'annotation_v2',
         'corpus_split', 'editor_marker_plan', 'share_export']


def load_real():
    return cap.load_capabilities(CAPS, TOOLS, ROOT), cap.load_registry(TOOLS)


def entry(doc, tool):
    return next(item for item in doc['capabilities'] if item['tool'] == tool)


def descriptor(registry, tool):
    return next(item for item in registry['tools'] if item['name'] == tool)


def copy_repo_subset(doc, target):
    """Copy only the files the capability document references (plus tool_api.py)."""
    paths = {'program/tools.json', 'program/capabilities.json', 'scripts/tool_api.py'}
    for item in doc['capabilities']:
        paths.add(item['worker']['script'])
        if item['worker']['via']:
            paths.add(item['worker']['via'])
        paths.add(item['skill'])
        paths.update(item['tests'])
    for relative in paths:
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)
    return target


class CapabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc, cls.registry = load_real()

    def refused(self, code, doc, registry=None, root=ROOT):
        with self.assertRaises(cap.CapabilityError) as caught:
            cap.validate(doc, registry if registry is not None else self.registry, root)
        self.assertEqual(caught.exception.code, code, caught.exception.message)
        return caught.exception

    def mutated(self):
        return copy.deepcopy(self.doc)

    # 1
    def test_real_document_validates_and_has_eight_pilot_tools(self):
        self.assertEqual(self.doc['pilot_tools'], EIGHT)
        self.assertEqual([item['tool'] for item in self.doc['capabilities']], EIGHT)
        self.assertIsNone(cap.validate(self.doc, self.registry, ROOT))
        names = {item['name'] for item in self.registry['tools']}
        self.assertTrue(set(EIGHT) <= names)

    # 2
    def test_traversal_reaches_worker_skill_and_tests_for_all_eight(self):
        result = cap.traverse(self.doc, ROOT)
        summary = result['summary']
        self.assertEqual((summary['edges_passed'], summary['edges_total']), (32, 32))
        self.assertEqual(summary['tools'], 8)
        self.assertEqual(summary['worker_allowlisted'], 8)
        self.assertEqual(summary['test_mentions_worker'], 8)
        for row in result['tools']:
            self.assertTrue(row['capability_present'] and row['worker_exists']
                            and row['skill_exists'] and row['tests_exist'], row['tool'])
            self.assertIn(row['worker_linkage'], ('direct', 'via_adapter'))
            self.assertTrue((ROOT / row['worker']).is_file())
            self.assertTrue((ROOT / row['skill']).is_file())
        linkage = {row['tool']: row['worker_linkage'] for row in result['tools']}
        self.assertEqual(linkage['apply_capture_profile'], 'via_adapter')
        self.assertEqual(sum(value == 'direct' for value in linkage.values()), 7)
        self.assertEqual(result['claim_class'], 'static_repository_check')
        self.assertIs(result['tests_executed'], False)
        self.assertIs(result['au_realtime_available'], False)
        self.assertIs(result['not_a_job_service'], True)
        statuses = {state for row in result['tools'] for state in row['provenance'].values()}
        self.assertTrue(statuses <= {'token_found_in_worker', 'declared_unverified'})
        self.assertEqual(summary['provenance_token_found'] + summary['provenance_declared_unverified'],
                         summary['provenance_declared'])
        single = cap.traverse(self.doc, ROOT, 'denoise')
        self.assertEqual([row['tool'] for row in single['tools']], ['denoise'])
        with self.assertRaises(cap.CapabilityError) as caught:
            cap.traverse(self.doc, ROOT, 'not_a_tool')
        self.assertEqual(caught.exception.code, 'unknown_tool')

    # 3
    def test_invariants_au_false_job_service_true_agent_defaults_false(self):
        checks = [self.doc['au_realtime_available'] is False, self.doc['not_a_job_service'] is True,
                  self.doc['agent_may_change_defaults'] is False]
        for item in self.doc['capabilities']:
            checks += [item['adapters']['au_render_parameter'] == 'unsupported',
                       item['effects']['network'] is False,
                       item['effects']['model_acquisition'] is False,
                       item['effects']['overwrites_input'] is False]
            self.assertEqual(item['unknowns']['au_realtime_reason'], 'unsupported')
            self.assertNotIn('agent', {p['default_owner'] for p in item['parameters'].values()})
        self.assertEqual((sum(checks), len(checks)), (35, 35))

    # 4
    def test_parameter_keys_equal_input_schema_including_nested_fields(self):
        top = nested = 0
        for item in self.doc['capabilities']:
            schema = descriptor(self.registry, item['tool'])['inputSchema']
            self.assertEqual(set(item['parameters']), set(schema['properties']), item['tool'])
            for name, metadata in item['parameters'].items():
                top += 1
                self.assertIn(metadata['unit'], cap.UNITS)
                self.assertIn(metadata['default_owner'], cap.OWNERS)
                if 'fields' in metadata:
                    child = schema['properties'][name]
                    props = child['properties'] if child['type'] == 'object' else child['items']['properties']
                    self.assertEqual(set(metadata['fields']), set(props))
                    nested += len(metadata['fields'])
        self.assertEqual(top, 48)
        self.assertEqual(nested, 8)  # peaking_eq 3 + compressor 5
        fields = entry(self.doc, 'capture_profile')['parameters']
        self.assertEqual(sorted(fields['peaking_eq']['fields']), ['frequency_hz', 'gain_db', 'q'])
        self.assertEqual(len(fields['compressor']['fields']), 5)
        # Ranges/enums are never re-entered in capability metadata.
        text = CAPS.read_text()
        for forbidden in ('"minimum"', '"maximum"', '"enum"', '"conservative3"'):
            self.assertNotIn(forbidden, text)
        doc = self.mutated()
        entry(doc, 'capture_profile')['parameters']['compressor']['fields'].pop('knee_db')
        self.refused('parameter_set_mismatch', doc)
        doc = self.mutated()
        entry(doc, 'capture_profile')['parameters']['peaking_eq'].pop('fields')
        self.refused('missing_key', doc)
        doc = self.mutated()
        entry(doc, 'denoise')['parameters']['profile']['fields'] = {}
        self.refused('unknown_key', doc)

    # 5
    def test_timeout_bounds_match_registry(self):
        for item in self.doc['capabilities']:
            schema = descriptor(self.registry, item['tool'])['inputSchema']['properties']['timeout_seconds']
            bounds = item['resources']['timeout_seconds']
            self.assertEqual((bounds['min'], bounds['max'], bounds['default']),
                             (schema['minimum'], schema['maximum'], schema['default']), item['tool'])
            self.assertEqual(bounds['status'], 'enforced')
        for key, value in (('min', 0), ('max', 901), ('default', 599), ('default', 600.0), ('max', True)):
            doc = self.mutated()
            entry(doc, 'denoise')['resources']['timeout_seconds'][key] = value
            self.refused('timeout_mismatch', doc)

    # 6
    def test_unknown_and_missing_keys_refused(self):
        doc = self.mutated()
        doc['extra'] = 1
        self.refused('unknown_key', doc)
        doc = self.mutated()
        del doc['not_a_job_service']
        self.refused('missing_key', doc)
        doc = self.mutated()
        entry(doc, 'clicks')['owner_notes'] = 'x'
        self.refused('unknown_key', doc)
        doc = self.mutated()
        del entry(doc, 'clicks')['unknowns']
        self.refused('missing_key', doc)
        doc = self.mutated()
        entry(doc, 'clicks')['parameters']['strength']['range'] = [0, 1]
        self.refused('unknown_key', doc)
        doc = self.mutated()
        del entry(doc, 'clicks')['parameters']['strength']['default_owner']
        self.refused('missing_key', doc)
        doc = self.mutated()
        entry(doc, 'clicks')['unknowns']['memory_bytes'] = 1024
        self.refused('bad_const', doc)
        doc = self.mutated()
        del entry(doc, 'clicks')['unknowns']['cpu_threads_reason']
        self.refused('missing_key', doc)

    # 7
    def test_const_and_enum_violations_refused(self):
        cases = [
            (lambda d: d.__setitem__('au_realtime_available', True), 'bad_const'),
            (lambda d: d.__setitem__('not_a_job_service', False), 'bad_const'),
            (lambda d: d.__setitem__('agent_may_change_defaults', True), 'bad_const'),
            (lambda d: d.__setitem__('schema_version', True), 'bad_const'),
            (lambda d: entry(d, 'denoise')['parameters']['profile'].__setitem__('default_owner', 'agent'), 'bad_enum'),
            (lambda d: entry(d, 'denoise')['effects'].__setitem__('network', True), 'bad_const'),
            (lambda d: entry(d, 'denoise')['effects'].__setitem__('model_acquisition', True), 'bad_const'),
            (lambda d: entry(d, 'denoise')['effects'].__setitem__('overwrites_input', 0), 'bad_const'),
            (lambda d: entry(d, 'denoise')['adapters'].__setitem__('au_render_parameter', 'available'), 'bad_const'),
            (lambda d: entry(d, 'denoise')['adapters'].__setitem__('web_job', 'available'), 'bad_enum'),
            (lambda d: entry(d, 'denoise').__setitem__('domain', 'mastering'), 'bad_enum'),
            (lambda d: entry(d, 'denoise')['parameters']['profile'].__setitem__('unit', 'semitones'), 'bad_enum'),
            (lambda d: entry(d, 'denoise')['resources']['memory_bytes'].__setitem__('max', 1), 'bad_const'),
            (lambda d: entry(d, 'denoise')['unknowns'].__setitem__('listening_acceptance_reason', 'accepted'), 'bad_const'),
            (lambda d: entry(d, 'denoise')['provenance_emitted'].append('settings'), 'duplicate'),
            (lambda d: entry(d, 'denoise')['provenance_emitted'].append('note_correctness'), 'bad_enum'),
            (lambda d: d['pilot_tools'].reverse(), 'pilot_mismatch'),
            (lambda d: d['capabilities'].pop(), 'pilot_mismatch'),
        ]
        for mutate, code in cases:
            doc = self.mutated()
            mutate(doc)
            self.refused(code, doc)
        self.assertGreaterEqual(len(cases), 15)

    # 8
    def test_registry_drift_refused(self):
        drift = [
            (lambda r: descriptor(r, 'clicks').__setitem__('skill', '.agents/skills/other/SKILL.md'), 'skill_mismatch'),
            (lambda r: descriptor(r, 'clicks').__setitem__('evidence_kind', 'measured'), 'registry_drift'),
            (lambda r: descriptor(r, 'clicks').__setitem__('implementation_status', 'planned'), 'registry_drift'),
            (lambda r: descriptor(r, 'clicks')['dependencies'].__setitem__('recommended_prior_tools', ['probe']), 'registry_drift'),
            (lambda r: descriptor(r, 'clicks')['dependencies'].__setitem__('enforced', True), 'registry_drift'),
            (lambda r: descriptor(r, 'clicks')['inputSchema']['properties'].__setitem__('gain_db', {'type': 'number'}), 'parameter_set_mismatch'),
            (lambda r: descriptor(r, 'clicks')['inputSchema']['properties'].pop('strength'), 'parameter_set_mismatch'),
            (lambda r: descriptor(r, 'clicks')['inputSchema']['properties']['strength'].pop('default'), 'default_policy_conflict'),
            (lambda r: descriptor(r, 'clicks')['inputSchema']['properties']['timeout_seconds'].__setitem__('maximum', 60), 'timeout_mismatch'),
            (lambda r: descriptor(r, 'clicks')['inputSchema'].__setitem__('patternProperties', {}), 'registry_drift'),
            (lambda r: r['tools'].remove(descriptor(r, 'share_export')), 'unknown_tool'),
        ]
        for mutate, code in drift:
            registry = copy.deepcopy(self.registry)
            mutate(registry)
            self.refused(code, self.doc, registry)
        # Same drift through a temp copy of tools.json read by load_capabilities.
        with tempfile.TemporaryDirectory() as temp:
            registry = json.loads(TOOLS.read_text())
            descriptor(registry, 'denoise')['evidence_kind'] = 'measured'
            path = Path(temp) / 'tools.json'
            path.write_text(json.dumps(registry))
            with self.assertRaises(cap.CapabilityError) as caught:
                cap.load_capabilities(CAPS, path, ROOT)
            self.assertEqual(caught.exception.code, 'registry_drift')

    # 9
    def test_missing_worker_skill_test_and_unsafe_paths_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            base = copy_repo_subset(self.doc, Path(temp).resolve())
            self.assertIsNone(cap.validate(self.doc, self.registry, base))
            for relative, code in (('scripts/clicks.py', 'worker_missing'),
                                   ('.agents/skills/guitar-clicks/SKILL.md', 'skill_missing'),
                                   ('tests/test_share_export.py', 'test_missing')):
                path = base / relative
                if relative.startswith('.agents'):
                    path = base / entry(self.doc, 'clicks')['skill']
                held = path.read_bytes()
                path.unlink()
                self.refused(code, self.doc, root=base)
                traversal = cap.traverse(self.doc, base)
                self.assertLess(traversal['summary']['edges_passed'], 32)
                path.write_bytes(held)
            # Symlink component: replace a worker with a link to an identical copy.
            worker = base / 'scripts' / 'corpus.py'
            outside = Path(temp) / 'outside.py'
            shutil.copyfile(ROOT / 'scripts' / 'corpus_split_s1.py', outside)
            target = base / 'scripts' / 'corpus_split_s1.py'
            target.unlink()
            os.symlink(outside, target)
            self.refused('unsafe_path', self.doc, root=base)
            self.assertFalse(worker.exists())
        for value in ('../scripts/media.py', '/etc/passwd', 'tests/../tests/test_media.py',
                      'tests/.hidden/test_media.py', 'tests\\test_media.py', 'C:/tests/test_media.py',
                      'tests//test_media.py'):
            doc = self.mutated()
            entry(doc, 'denoise')['tests'] = [value]
            self.refused('unsafe_path', doc)
        doc = self.mutated()
        entry(doc, 'denoise')['worker']['script'] = 'scripts/../media.py'
        self.refused('unsafe_path', doc)
        doc = self.mutated()
        entry(doc, 'denoise')['skill'] = '.agents/skills/../skills/guitar-denoise/SKILL.md'
        self.refused('skill_mismatch', doc)

    # 10
    def test_readonly_hint_conflict_refused(self):
        readonly = [item['name'] for item in self.registry['tools'] if item['name'] in EIGHT
                    and item['annotations'].get('readOnlyHint') is True]
        self.assertEqual(sorted(readonly), ['corpus_split', 'editor_marker_plan'])
        for mutate in (lambda e: e['writes'].append('run_json_evidence'),
                       lambda e: e.__setitem__('renders_audio', True),
                       lambda e: e.__setitem__('renders_video', True),
                       lambda e: e.__setitem__('output_root_policy', 'run_dir')):
            for tool in readonly:
                doc = self.mutated()
                mutate(entry(doc, tool)['effects'])
                self.refused('readonly_conflict', doc)

    # 11
    def test_cli_validate_and_traverse_deterministic_json(self):
        script = str(ROOT / 'scripts' / 'capabilities.py')
        outputs = {}
        for command in (['validate'], ['traverse'], ['traverse', '--tool', 'share_export'],
                        ['describe', 'capture_profile']):
            runs = [subprocess.run([sys.executable, script, '--root', str(ROOT), *command],
                                   capture_output=True, text=True, timeout=60, check=False)
                    for _ in range(2)]
            self.assertEqual([run.returncode for run in runs], [0, 0], runs[0].stderr)
            self.assertEqual(runs[0].stdout, runs[1].stdout)
            parsed = json.loads(runs[0].stdout)
            self.assertEqual(runs[0].stdout, json.dumps(parsed, sort_keys=True, indent=2, ensure_ascii=False) + '\n')
            outputs[command[0] if len(command) == 1 else ' '.join(command)] = parsed
        self.assertEqual(outputs['validate']['status'], 'valid')
        self.assertEqual(outputs['validate']['parameters'], 48)
        self.assertEqual(outputs['traverse']['summary']['edges_passed'], 32)
        described = outputs['describe capture_profile']
        self.assertEqual(described['registry_input_bounds']['reduction_db']['maximum'], 12)
        self.assertEqual(described['registry_bounds_source'], 'program/tools.json inputSchema')
        with tempfile.TemporaryDirectory() as temp:
            bad = Path(temp) / 'capabilities.json'
            bad.write_text(CAPS.read_text().replace('"au_realtime_available": false',
                                                    '"au_realtime_available": true'))
            run = subprocess.run([sys.executable, script, '--root', str(ROOT), '--capabilities', str(bad),
                                  'validate'], capture_output=True, text=True, timeout=60, check=False)
            self.assertEqual(run.returncode, 1)
            self.assertEqual(run.stdout, '')
            error = json.loads(run.stderr)
            self.assertEqual((error['status'], error['code']), ('error', 'bad_const'))

    # extra coverage
    def test_default_policy_conflicts_refused(self):
        cases = [('clicks', 'strength', 'default_policy', 'omitted_means_off'),
                 ('clicks', 'bpm', 'default_policy', 'schema_default'),
                 ('clicks', 'strength', 'default_owner', 'none'),
                 ('clicks', 'bpm', 'default_owner', 'operator'),
                 ('denoise', 'input', 'default_policy', 'omitted_means_none'),
                 ('annotation_v2', 'input', 'default_policy', 'explicit_required')]
        for tool, name, key, value in cases:
            doc = self.mutated()
            entry(doc, tool)['parameters'][name][key] = value
            self.refused('default_policy_conflict', doc)
        doc = self.mutated()
        entry(doc, 'clicks')['parameters']['attenuate']['unit'] = 'dB'
        self.refused('registry_drift', doc)
        # Operator owns musical/processing defaults; root owns engineering bounds.
        self.assertEqual(entry(self.doc, 'denoise')['parameters']['profile']['default_owner'], 'operator')
        self.assertEqual(entry(self.doc, 'clicks')['parameters']['strength']['default_owner'], 'operator')
        for item in self.doc['capabilities']:
            self.assertEqual(item['parameters']['timeout_seconds']['default_owner'], 'root')

    def test_duplicate_keys_unsafe_file_and_worker_not_allowlisted_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            text = CAPS.read_text()
            duplicated = Path(temp) / 'dup.json'
            duplicated.write_text(text.replace('"status": "pilot",', '"status": "pilot",\n  "status": "pilot",', 1))
            with self.assertRaises(cap.CapabilityError) as caught:
                cap.load_capabilities(duplicated, TOOLS, ROOT)
            self.assertEqual(caught.exception.code, 'duplicate')
            nonfinite = Path(temp) / 'nan.json'
            nonfinite.write_text(text.replace('"schema_version": 1', '"schema_version": NaN', 1))
            with self.assertRaises(cap.CapabilityError) as caught:
                cap.load_capabilities(nonfinite, TOOLS, ROOT)
            self.assertEqual(caught.exception.code, 'bad_type')
            link = Path(temp) / 'link.json'
            os.symlink(CAPS, link)
            with self.assertRaises(cap.CapabilityError) as caught:
                cap.load_capabilities(link, TOOLS, ROOT)
            self.assertEqual(caught.exception.code, 'unsafe_path')
            subset = copy_repo_subset(self.doc, base / 'repo')
            api = subset / 'scripts' / 'tool_api.py'
            api.write_text(api.read_text().replace('scripts/corpus_split_s1.py', 'scripts/other.py'))
            self.refused('worker_not_allowlisted', self.doc, root=subset)
            api.write_text((ROOT / 'scripts' / 'tool_api.py').read_text()
                           .replace('from capture_application_adapter import', 'from other_adapter import'))
            self.refused('worker_not_allowlisted', self.doc, root=subset)
        doc = self.mutated()
        entry(doc, 'denoise')['worker']['via'] = 'scripts/capture_application_adapter.py'
        self.refused('bad_const', doc)
        doc = self.mutated()
        entry(doc, 'denoise')['worker']['entry'] = 'clean; rm'
        self.refused('bad_type', doc)

    def test_outputs_carry_unknowns_and_no_musical_or_listening_claims(self):
        for item in self.doc['capabilities']:
            unknowns = item['unknowns']
            for field in cap.UNKNOWN_FIELDS:
                self.assertIsNone(unknowns[field])
                self.assertTrue(unknowns[field + '_reason'])
            self.assertEqual(unknowns['musical_acceptance_reason'], 'not_established')
            self.assertEqual(unknowns['listening_acceptance_reason'], 'not_established')
            self.assertEqual(unknowns['web_admission_reason'], 'not_qualified')
            self.assertEqual(item['resources']['memory_bytes'], {'max': None, 'status': 'not_qualified'})
        lowered = CAPS.read_text().lower()
        for phrase in ('missed note', 'missed_note', 'note_correct', 'wrong note', 'sounds better',
                       'listening_accepted', 'improved'):
            self.assertNotIn(phrase, lowered)
        # Heavy numeric/media workers declare FFmpeg; lightweight metadata tools do not.
        for item in self.doc['capabilities']:
            if item['resources']['resource_class'] == 'media_render_ffmpeg':
                self.assertIn('ffmpeg', item['dependencies']['external_runtime'])
                self.assertTrue(item['resources']['heavy_numeric'])
            if item['resources']['resource_class'] == 'metadata_light':
                self.assertFalse(item['resources']['heavy_numeric'])
                self.assertNotIn('ffmpeg', item['dependencies']['external_runtime'])


if __name__ == '__main__':
    unittest.main()
