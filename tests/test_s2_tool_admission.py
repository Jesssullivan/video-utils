"""S2 admission: freeze the first 32 descriptors and exercise four new typed hooks.

Synthetic metadata only. Outputs go beneath a patched temporary artifacts/
boundary; no recording, accepted run or repository artifact is read or written.
"""
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import tool_api  # noqa: E402
from test_mcp import exchange, initialization, request  # noqa: E402

FROZEN_NAMES = (
    'probe', 'denoise', 'bpm', 'noise', 'tone', 'notes', 'rhythm', 'phrases', 'export', 'report',
    'pipeline', 'markers', 'clicks', 'phrase_compare', 'benchmark', 'review', 'pitch', 'meter', 'tonal',
    'corpus', 'pitch_evaluate', 'phrase_evaluate', 'marked_video', 'basic_pitch_compare',
    'capture_profile', 'editor_marker_plan', 'learned_pitch_evaluate', 'apply_capture_profile',
    'arrangement_reference', 'share_export', 'annotation_v2', 'corpus_split')
# sha256 of json.dumps(tools[:32], sort_keys=True, separators=(',', ':'), ensure_ascii=False)
# (tests/test_s1_tool_admission.py serializer) and with ensure_ascii=True
# (tests/test_sprint1_audit.py canonical()), both taken from base commit e0da4ca.
FROZEN_SHA256 = '932d3e2683c5175fc08f0a8b27169a351b6269ba3db4467811d37bbd698e8863'
FROZEN_ASCII_SHA256 = '358ce0aeba9214076d64fcc69ee9554cdd048d2001304dc897bf7f38b4d313bb'
NEW = {
    'editor_marker_export': ('editor-marker-export', False, False,
                             {'run_dir', 'selection', 'profile', 'format'}, 120),
    'annotation_markers': ('guitar-annotation-markers', True, True,
                           {'run_dir', 'store_sha256', 'output_dir'}, 900),
    'flags_triage': ('guitar-flags-triage', True, True, {'run_dir', 'output'}, 900),
    'corpus_eval_s2': ('guitar-corpus-eval', True, True,
                       {'manifest', 'proposals', 'proposals_sha256', 'output'}, 900),
}
SHA = 'a' * 64


class S2ToolAdmissionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='s2 admission 音 ')
        self.addCleanup(temporary.cleanup)
        self.base = pathlib.Path(temporary.name).resolve()
        self.artifacts = self.base / 'artifacts'
        self.artifacts.mkdir()
        boundary = patch.object(tool_api, 'S2_OUTPUT_ROOT', self.artifacts)
        boundary.start()
        self.addCleanup(boundary.stop)

    # ----- registry freeze and descriptors ---------------------------------
    def test_first_32_descriptors_frozen_and_four_appended(self):
        tools = tool_api.descriptors()
        self.assertEqual(len(tools), 36)
        self.assertEqual(tuple(tool['name'] for tool in tools[:32]), FROZEN_NAMES)
        for ascii_only, expected in ((False, FROZEN_SHA256), (True, FROZEN_ASCII_SHA256)):
            data = json.dumps(tools[:32], sort_keys=True, separators=(',', ':'), ensure_ascii=ascii_only)
            self.assertEqual(hashlib.sha256(data.encode()).hexdigest(), expected)
        self.assertEqual([tool['name'] for tool in tools[32:]], list(NEW))
        raw = (ROOT / 'program/tools.json').read_text(encoding='utf-8')
        self.assertEqual(json.dumps(json.loads(raw), indent=2) + '\n', raw)

    def test_new_descriptors_closed_bounded_and_skills_exist(self):
        draft = json.loads((ROOT / 'docs/agent-notes/sprints/20261006-s2/editor_export-tool-descriptor.json')
                           .read_text())
        self.assertEqual(tool_api.descriptor('editor_marker_export'), draft)
        for name, (prompt, read_only, idempotent, required, ceiling) in NEW.items():
            with self.subTest(name=name):
                info = tool_api.descriptor(name)
                schema = info['inputSchema']
                tool_api.validate_schema(schema)
                self.assertIs(schema['additionalProperties'], False)
                self.assertEqual(set(schema['required']), required)
                timeout = schema['properties']['timeout_seconds']
                self.assertEqual((timeout['type'], timeout['minimum'], timeout['maximum']),
                                 ('integer', 1, ceiling))
                self.assertEqual(info['implementation_status'], 'experimental')
                self.assertEqual(info['annotations'], {'readOnlyHint': read_only, 'destructiveHint': False,
                                                       'idempotentHint': idempotent, 'openWorldHint': False})
                self.assertEqual(info['skill'], f'.agents/skills/{prompt}/SKILL.md')
                text = (ROOT / info['skill']).read_text(encoding='utf-8')
                self.assertTrue(text.startswith(f'---\nname: {prompt}\ndescription: '))
                self.assertIn(f'Hook `{name}`' if name != 'editor_marker_export' else 'MCP tool `editor_marker_export`',
                              text)
                for key in ('identify', 'research', 'iterate', 'acceptance'):
                    self.assertTrue(info['agent_workflow'][key])
                with self.assertRaises(tool_api.ValidationError):
                    tool_api.validate({'unknown': True}, schema)

    # ----- refusal before any worker or file read ---------------------------
    def test_unknown_keys_escapes_and_bad_pins_refuse_before_worker(self):
        export = {'run_dir': 'artifacts/runs/x', 'selection': 'selection.json', 'profile': 'export.json',
                  'format': 'fcpxml'}
        markers = {'run_dir': '/unopened/run', 'store_sha256': SHA, 'output_dir': 'artifacts/out'}
        triage = {'run_dir': '/unopened/run', 'output': 'artifacts/triage.json'}
        evaluation = {'manifest': '/unopened/split.json', 'proposals': '/unopened/flags.json',
                      'proposals_sha256': SHA, 'output': 'artifacts/eval.json'}
        invalid = [
            ('editor_marker_export', dict(export, dtd='/tmp/fcpxml.dtd')),
            ('editor_marker_export', dict(export, output_dir='artifacts/elsewhere')),
            ('editor_marker_export', dict(export, format='edl')),
            ('editor_marker_export', dict(export, selection='../selection.json')),
            ('editor_marker_export', dict(export, profile='https://host.invalid/p.json')),
            ('editor_marker_export', dict(export, profile='selection.json')),
            ('editor_marker_export', dict(export, run_dir='artifacts/runs/../x')),
            ('editor_marker_export', dict(export, timeout_seconds=121)),
            ('editor_marker_export', {k: v for k, v in export.items() if k != 'format'}),
            ('annotation_markers', dict(markers, argv=['--include-text'])),
            ('annotation_markers', dict(markers, store_sha256='A' * 64)),
            ('annotation_markers', dict(markers, store_sha256='a' * 63)),
            ('annotation_markers', dict(markers, run_dir='/unopened/../run')),
            ('annotation_markers', dict(markers, output_dir='artifacts/../escape')),
            ('annotation_markers', dict(markers, output_dir='file:///tmp/out')),
            ('annotation_markers', dict(markers, include_text='yes')),
            ('annotation_markers', dict(markers, timeout_seconds=901)),
            ('flags_triage', dict(triage, priority_rule='v2')),
            ('flags_triage', dict(triage, output='artifacts/../../triage.json')),
            ('flags_triage', dict(triage, run_dir='C:\\run')),
            ('flags_triage', {'run_dir': '/unopened/run'}),
            ('corpus_eval_s2', dict(evaluation, coverage_threshold=0.1)),
            ('corpus_eval_s2', dict(evaluation, proposals_sha256='g' * 64)),
            ('corpus_eval_s2', dict(evaluation, manifest='../split.json')),
            ('corpus_eval_s2', dict(evaluation, local_root='/unopened/..')),
            ('corpus_eval_s2', dict(evaluation, proposals='/unopened/x\x00.json')),
            ('corpus_eval_s2', dict(evaluation, output='artifacts/../eval.json')),
        ]
        for name, arguments in invalid:
            with self.subTest(name=name, arguments=arguments), patch.object(tool_api, 'run_worker') as worker:
                with self.assertRaises(tool_api.ValidationError):
                    tool_api.execute(name, arguments)
                worker.assert_not_called()

    # ----- fixtures ----------------------------------------------------------
    def annotation_run(self):
        from test_annotation_markers import spec, write_run
        run = self.base / 'annotation run $(literal)'
        _, store_sha = write_run(run, [spec('late fill'), spec('setup', basis='operator_context', quote=None,
                                                                start=0, end=4)])
        return run, store_sha

    def triage_run(self):
        run = self.base / 'triage run'
        (run / 'clicks').mkdir(parents=True)
        source = hashlib.sha256(b's2-admission-source').hexdigest()
        (run / 'manifest.json').write_text(json.dumps({
            'source': {'sha256': source}, 'timeline': {'audio_start_seconds': 0.0, 'format_start_seconds': 0.0},
            'pcm': {'duration_seconds': 32.0}}))
        clicks = run / 'clicks' / 'clicks.json'
        clicks.write_text(json.dumps({'click_grid': {'period_seconds': 0.5, 'phase_seconds_audio_relative': 0.0,
                                                     'bpm': 120.0}}))
        flags = [{'kind': kind, 'source_time_seconds': start, 'end_seconds': start, 'status': 'needs_review',
                  'confidence': 'unvalidated_automatic_phrase_candidate', 'evidence': {'kind': kind},
                  'performance_issue_confirmed': False}
                 for kind, start in (('spectral_texture_region_candidate', 1.0),
                                     ('automatic_recurrence_review_candidate', 2.0),
                                     ('spectral_texture_region_candidate', 9.0))]
        (run / 'flags.json').write_text(json.dumps({
            'schema_version': 1, 'source_sha256': source,
            'evidence_artifacts': {'clicks': {'selector': 'clicks/clicks.json',
                                              'sha256': hashlib.sha256(clicks.read_bytes()).hexdigest()}},
            'timeline': {'audio_start_seconds': 0.0, 'axis': 'original_source_stream_timestamps_seconds'},
            'flags': flags}))
        return run

    def corpus_fixture(self):
        from test_annotation_markers import spec
        from test_corpus_eval_s2 import CorpusEvaluationTests, proposal
        helper = CorpusEvaluationTests()
        helper.root = self.base / 'corpus root'
        helper.proposal_dir = self.base / 'proposal run'
        helper.root.mkdir(); helper.proposal_dir.mkdir()
        items = [spec('ctx', basis='operator_context', quote=None, start=0, end=12), spec('late', start=2, end=3)]
        split = helper.corpus(items, duration=20.0)
        proposals, digest = helper.proposals([proposal('automatic_recurrence_review_candidate', 2.5)])
        return split, helper.root, proposals, digest

    # ----- fixed argv and confined outputs -----------------------------------
    def test_worker_commands_are_fixed_argv_with_confined_fresh_outputs(self):
        run, store_sha = self.annotation_run()
        out = self.artifacts / 'markers out'
        args = {'run_dir': str(run), 'store_sha256': store_sha, 'output_dir': str(out)}
        command = tool_api.worker_command('annotation_markers', args)
        self.assertEqual(command[1:], [str(ROOT / 'scripts/annotation_markers.py'), str(run),
                                       '--store-sha256', store_sha, '--output-dir', str(out)])
        self.assertEqual(tool_api.worker_command('annotation_markers', dict(args, include_text=True))[-1],
                         '--include-text')
        self.assertNotIn('--include-text', tool_api.worker_command('annotation_markers',
                                                                   dict(args, include_text=False)))
        triage = self.triage_run()
        target = self.artifacts / 'triage.json'
        self.assertEqual(tool_api.worker_command('flags_triage', {'run_dir': str(triage), 'output': str(target)})[1:],
                         [str(ROOT / 'scripts/flags_triage.py'), str(triage), '--output', str(target)])
        split, root, proposals, digest = self.corpus_fixture()
        evaluation = self.artifacts / 'eval.json'
        command = tool_api.worker_command('corpus_eval_s2', {
            'manifest': str(split), 'local_root': str(root), 'proposals': str(proposals),
            'proposals_sha256': digest, 'output': str(evaluation)})
        self.assertEqual(command[1:], [str(ROOT / 'scripts/corpus_eval_s2.py'), 'evaluate', str(split),
                                       '--root', str(root), '--proposals', str(proposals),
                                       '--proposals-sha256', digest, '--output', str(evaluation)])

    def test_output_and_input_path_refusals(self):
        run, store_sha = self.annotation_run()
        alias = self.base / 'alias'; alias.symlink_to(run, target_is_directory=True)
        outside = self.base / 'not-artifacts'; outside.mkdir()
        existing = self.artifacts / 'existing'; existing.mkdir()
        linked = self.artifacts / 'linked'; linked.symlink_to(outside, target_is_directory=True)
        nested_run = self.artifacts / 'nested-run'
        from test_annotation_markers import spec, write_run
        _, nested_sha = write_run(nested_run, [spec('x')])
        refusals = [
            ('annotation_markers', {'run_dir': str(alias), 'store_sha256': store_sha,
                                    'output_dir': str(self.artifacts / 'a')}, 'symlink'),
            ('annotation_markers', {'run_dir': str(run), 'store_sha256': store_sha,
                                    'output_dir': str(outside / 'a')}, 'artifacts'),
            ('annotation_markers', {'run_dir': str(run), 'store_sha256': store_sha,
                                    'output_dir': str(self.artifacts)}, 'child'),
            ('annotation_markers', {'run_dir': str(run), 'store_sha256': store_sha,
                                    'output_dir': str(existing)}, 'fresh'),
            ('annotation_markers', {'run_dir': str(run), 'store_sha256': store_sha,
                                    'output_dir': str(linked / 'a')}, 'symlink'),
            ('annotation_markers', {'run_dir': str(run), 'store_sha256': store_sha,
                                    'output_dir': str(self.artifacts / 'missing' / 'a')}, 'parent'),
            ('annotation_markers', {'run_dir': str(nested_run), 'store_sha256': nested_sha,
                                    'output_dir': str(nested_run / 'inside')}, 'outside'),
            ('annotation_markers', {'run_dir': str(self.base / 'absent'), 'store_sha256': store_sha,
                                    'output_dir': str(self.artifacts / 'a')}, 'existing directory'),
            ('flags_triage', {'run_dir': str(run), 'output': str(self.artifacts / 't.json')}, 'flags.json'),
            ('flags_triage', {'run_dir': str(self.triage_run()), 'output': str(self.artifacts / 't.csv')}, '.json'),
        ]
        split, root, proposals, digest = self.corpus_fixture()
        evaluation = {'manifest': str(split), 'local_root': str(root), 'proposals': str(proposals),
                      'proposals_sha256': digest, 'output': str(self.artifacts / 'eval.json')}
        proposal_alias = self.base / 'proposal alias'
        proposal_alias.symlink_to(proposals.parent, target_is_directory=True)
        beside = self.artifacts / 'proposal-beside'; beside.mkdir()
        (beside / 'flags.json').write_bytes(proposals.read_bytes())
        refusals += [
            ('corpus_eval_s2', dict(evaluation, proposals=str(proposal_alias / 'flags.json')), 'symlink'),
            ('corpus_eval_s2', dict(evaluation, proposals=str(beside / 'flags.json'),
                                    output=str(beside / 'eval.json')), 'outside'),
            ('corpus_eval_s2', dict(evaluation, output=str(outside / 'eval.json')), 'artifacts'),
            ('corpus_eval_s2', dict(evaluation, manifest=str(self.base / 'elsewhere.json')), 'local_root'),
        ]
        for name, arguments, message in refusals:
            with self.subTest(name=name, arguments=arguments), patch.object(tool_api, 'run_worker') as worker:
                with self.assertRaisesRegex(tool_api.ToolError, message):
                    tool_api.execute(name, arguments)
                worker.assert_not_called()

    def test_editor_marker_export_digest_named_run_local_output(self):
        from test_editor_marker_export import EditorMarkerExportTests, vfr_pts
        fake_root = self.base / 'repo'
        run = fake_root / 'artifacts' / 'runs' / 'uniform'
        run.mkdir(parents=True)
        EditorMarkerExportTests().disk_fixture(run)
        args = {'run_dir': str(run), 'selection': 'selection.json', 'profile': 'export-profile.json',
                'format': 'fcpxml'}
        digest = hashlib.sha256((run / 'export-profile.json').read_bytes()).hexdigest()
        output = run / ('editor-export-fcpxml-' + digest[:12])
        with patch.object(tool_api, 'ROOT', fake_root):
            command = tool_api.worker_command('editor_marker_export', args)
            self.assertEqual(command[1:], [str(fake_root / 'scripts/editor_marker_export.py'), str(run),
                                           'selection.json', 'export-profile.json', '--format', 'fcpxml',
                                           '--output-dir', str(output), '--summary'])
            self.assertNotIn('--dtd', command)
            with self.assertRaisesRegex(tool_api.ToolError, 'artifacts/runs'):
                tool_api.worker_command('editor_marker_export', dict(args, run_dir=str(self.base)))
        # The exact dispatcher argv is accepted by the real worker; only the
        # interpreter/script prefix is the repository's own.
        real = [sys.executable, str(ROOT / 'scripts/editor_marker_export.py')] + command[2:]
        completed = subprocess.run(real, cwd=ROOT, capture_output=True, text=True, timeout=120, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        summary = json.loads(completed.stdout)
        self.assertEqual(summary['native_export_status'], 'written_unverified')
        self.assertEqual((summary['dtd_validation'], summary['application_import']),
                         ('not_performed', 'not_performed'))
        self.assertEqual(summary['output_dir'], str(output))
        self.assertTrue((output / 'review.fcpxmld' / 'Info.fcpxml').is_file())
        with patch.object(tool_api, 'ROOT', fake_root), patch.object(tool_api, 'run_worker') as worker:
            with self.assertRaisesRegex(tool_api.ToolError, 'already exists'):
                tool_api.execute('editor_marker_export', args)
            worker.assert_not_called()
        # VFR cadence abstains and writes nothing at the digest-named path.
        vfr = fake_root / 'artifacts' / 'runs' / 'vfr'
        vfr.mkdir()
        EditorMarkerExportTests().disk_fixture(vfr, pts=vfr_pts())
        with patch.object(tool_api, 'ROOT', fake_root):
            command = tool_api.worker_command('editor_marker_export', dict(args, run_dir=str(vfr)))
        completed = subprocess.run([sys.executable, str(ROOT / 'scripts/editor_marker_export.py')] + command[2:],
                                   cwd=ROOT, capture_output=True, text=True, timeout=120, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        summary = json.loads(completed.stdout)
        self.assertEqual((summary['native_export_status'], summary['cadence']), ('calibration_required', 'variable'))
        self.assertIn('cadence_variable', summary['reasons'])
        self.assertEqual(summary['files_written'], 0)
        self.assertFalse(os.path.lexists(command[command.index('--output-dir') + 1]))

    # ----- real execution through the dispatcher --------------------------
    def test_execute_runs_lane_workers_without_touching_inputs(self):
        run, store_sha = self.annotation_run()
        before = {path.name: path.read_bytes() for path in run.iterdir()}
        result = tool_api.execute('annotation_markers', {'run_dir': str(run), 'store_sha256': store_sha,
                                                         'output_dir': str(self.artifacts / 'markers')})
        self.assertEqual(result['result']['status'], 'annotation_markers_projected')
        self.assertEqual(result['evidence_kind'], 'human_annotation_projection_not_verdict')
        projected = json.loads((self.artifacts / 'markers' / 'annotation-markers.json').read_text())
        self.assertNotIn('the second riff felt late', json.dumps(projected))
        self.assertEqual({path.name: path.read_bytes() for path in run.iterdir()}, before)
        with self.assertRaises(tool_api.ToolError):
            tool_api.execute('annotation_markers', {'run_dir': str(run), 'store_sha256': 'b' * 64,
                                                    'output_dir': str(self.artifacts / 'stale')})
        self.assertFalse((self.artifacts / 'stale').exists())

        triage = self.triage_run()
        result = tool_api.execute('flags_triage', {'run_dir': str(triage),
                                                   'output': str(self.artifacts / 'triage.json')})
        self.assertEqual(result['result']['status'], 'flags_triage_written')
        self.assertEqual(result['result']['total_flags'], 3)

        split, root, proposals, digest = self.corpus_fixture()
        result = tool_api.execute('corpus_eval_s2', {
            'manifest': str(split), 'local_root': str(root), 'proposals': str(proposals),
            'proposals_sha256': digest, 'output': str(self.artifacts / 'eval.json')})
        self.assertEqual(result['result']['status'], 'coverage_first_evaluation_recorded')
        evaluation = json.loads((self.artifacts / 'eval.json').read_text())
        self.assertEqual((evaluation['negatives_inferred'], evaluation['source_audio_read']), (0, False))
        self.assertIsNone(evaluation['records'][0]['metrics']['precision'])

    # ----- MCP prompt readback ------------------------------------------------
    def test_real_mcp_lists_tools_and_reads_back_each_new_skill_prompt(self):
        messages = [initialization(), {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
                    request(2, 'tools/list'), request(3, 'prompts/list')]
        messages += [request(10 + index, 'prompts/get', {'name': prompt})
                     for index, (prompt, *_rest) in enumerate(NEW.values())]
        replies, stderr = exchange(messages, timeout=30)
        self.assertEqual(stderr, '')
        tools = {row['name']: row for row in replies[1]['result']['tools']}
        self.assertEqual(len(tools), 36)
        prompts = {row['name'] for row in replies[2]['result']['prompts']}
        for offset, (name, (prompt, *_rest)) in enumerate(NEW.items()):
            with self.subTest(name=name):
                self.assertIs(tools[name]['inputSchema']['additionalProperties'], False)
                self.assertIn(prompt, prompts)
                text = replies[3 + offset]['result']['messages'][0]['content']['text']
                self.assertEqual(text, (ROOT / '.agents/skills' / prompt / 'SKILL.md').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
