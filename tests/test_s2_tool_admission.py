"""S2 admission: freeze the first 32, 36, 37, 38, 39 and 40 descriptors and exercise eight new typed hooks.

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
# Second freeze (root_admission_c): tools[:36] as merged at main 736f406, same two serializers.
FROZEN_36_SHA256 = '82bdb7478deb8dc5859c33e7c2ca017c582cc54fc4dfaf85d858a6b5a77073ba'
FROZEN_36_ASCII_SHA256 = '51dd154f28079f178979a6add85bf9d2d8fcf4cc2f8d0fefec7061ab16749d31'
# Rebase proof (S2R descriptor_rebase): tools[:37] measured at base 7d0e11e, same two serializers. Everything
# before phrase_timing (tools[37]) is byte-identical across the rebase.
FROZEN_37_SHA256 = '72ed9aadd9ce065e93b47d6d00b22782d2b3a3ba45bc36a0508921f59374a7c3'
FROZEN_37_ASCII_SHA256 = '71977d3cace1baa00044925fb9da3e973d5d0c53830302c9050dee2e66271d21'
# Third freeze (root_admission_d), REBASED by the 2026-10-07 operator ruling "phrase_timing descriptor: rebase
# the freeze and fix the wording" (docs/agent-notes/2026-10-07-s2-operator-rulings.md; S2 follow-up 7): only
# tools[37] description/intent/limitations changed. Superseded values (main 0cdca01):
# 4005da2b6960de2b973078b272b678e9b995a8bb755888960944cfc8e2e187c5 / f079cffc30d6c2b19a6dab746fe76915642fef8a77bf3d9add4899a78f3eac54
FROZEN_38_SHA256 = '14eca3d3bd6f802791a8f7a30f4fb27593eeb7426959210f8d6ae535ceb429e5'
FROZEN_38_ASCII_SHA256 = '3714eb7a4377889180ce95e3158151512a96ed92801b6e7e9ef12eefa46fb688'
# Fourth freeze (root_admission_e), REBASED by the same 2026-10-07 operator ruling. Superseded values (main ebaf72d):
# eada780f79f40516db8583bd13c0f9a8b9bf7386f1f94a3ff1147a165165436f / aa60371ab37c791ed3b27cd9d940948a555bdbb5a5a9b4560c4ac48b75737259
FROZEN_39_SHA256 = '031cb17c9f75354228f0d218ec4f5943172b80deb5005405c39ad3fa8fa46619'
FROZEN_39_ASCII_SHA256 = 'd87b5fb852d75f6d51eb4df6981d4c12a534574d61a5659c7f99511fa1dcb267'
# Fifth freeze (newly pinned by S2R descriptor_rebase under the 2026-10-07 operator ruling): tools[:40]. The
# pre-ruling value at base 7d0e11e, never pinned, was
# b77d5243ed0ee3b797a5c2869a012120a29e6377b343666751dfe27863ed89b4 / 38dfb867168d41cec9536bab2b44956c3110a26ba4124eceeee13ea8eec86245
FROZEN_40_SHA256 = 'da091862fd7d854e80a8950a0e9581cff07c481b1d25614a939666e4c215045d'
FROZEN_40_ASCII_SHA256 = '5dc30b2f7f86a755083b8cf7783960ac563c4ecfb425b4f0d3d10af0acf30845'
# tools[37] (phrase_timing) invariance anchors measured at base 7d0e11e (serializer with ensure_ascii=False).
PHRASE_TIMING_SCHEMA_SHA256 = 'ec6401f8ec660ab07fbe2dee11ff8d6a4f093f85bc3dcd7aaf9f440905ba272e'
PHRASE_TIMING_NON_TEXT_SHA256 = '93ac74d44468c9bc36c49173468cf9629e2a19f4b579bc45d173b07c4ff21945'
PHRASE_TIMING_TEXT_KEYS = ('description', 'intent', 'limitations')
PHRASE_TIMING_BASE_LIMITATIONS_0_2 = (
    'Offsets use broadband attack candidates, which can include click energy, handling noise or several merged '
    'attacks; they are not note identities.',
    'The click reference is fitted to unverified periodic high-frequency transients; a guitar attack can displace '
    'or mask a click. Physical capture latency is uncalibrated and detector-delay compensation uses synthetic-probe '
    'medians.',
    'Phrase spans are review candidates or reference-conditioned alignments, not detected musical boundaries. '
    'Phrases with fewer than 4 click-proximal onsets, no click grid or spans outside the analysis abstain.',
)
NEW = {
    'editor_marker_export': ('editor-marker-export', False, False,
                             {'run_dir', 'selection', 'profile', 'format'}, 120),
    'annotation_markers': ('guitar-annotation-markers', True, True,
                           {'run_dir', 'store_sha256', 'output_dir'}, 900),
    'flags_triage': ('guitar-flags-triage', True, True, {'run_dir', 'output'}, 900),
    'corpus_eval_s2': ('guitar-corpus-eval', True, True,
                       {'manifest', 'proposals', 'proposals_sha256', 'output'}, 900),
}
# Admitted by root_admission_c: (prompt, readOnlyHint, idempotentHint, required, timeout ceiling, hook text).
NEW_C = {
    'marked_compact': ('guitar-marked-compact', False, False, {'run_dir', 'picture_preview', 'arrangement_markers'},
                       600, 'MCP tool `marked_compact`'),
    'phrase_timing': ('guitar-phrase-timing', True, False, {'analysis', 'phrases', 'output_root'}, 300,
                      'Hook `phrase_timing`'),
}
# Admitted by root_admission_d (same tuple shape as NEW_C).
NEW_D = {
    'tone_ab': ('guitar-tone-ab', False, False, {'run_dir', 'common_region_start', 'common_region_end'}, 1800,
                'Hook `tone_ab`'),
}
# Admitted by root_admission_e (same tuple shape as NEW_C).
NEW_E = {
    'report_bundle': ('guitar-report-bundle', False, False, {'run_dir'}, 900, 'MCP tool `report_bundle`'),
}
# sha256 of the admitted skill text. Re-pinned by S2R descriptor_rebase under the 2026-10-07 operator ruling
# "report_bundle skill text: update the wording and re-pin" (S2 follow-up 8): the hook line now says
# "(admitted as tool 40)" instead of "(once admitted by root)"; no other byte changed. Superseded value (skill text
# verbatim from report_d6-handoff.json at lane commit 5c9115e):
# 33045f113109c0d4cdaa73908ee49871677eb4b3c7c47df1fbb112c78c919ea9
REPORT_BUNDLE_SKILL_SHA256 = 'a8261d31be2fb328570c10e000beeff5fb84b5732215660e628420802319e483'
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
        self.assertEqual(len(tools), 40)
        self.assertEqual(tuple(tool['name'] for tool in tools[:32]), FROZEN_NAMES)
        for count, ascii_only, expected in ((32, False, FROZEN_SHA256), (32, True, FROZEN_ASCII_SHA256),
                                            (36, False, FROZEN_36_SHA256), (36, True, FROZEN_36_ASCII_SHA256),
                                            (37, False, FROZEN_37_SHA256), (37, True, FROZEN_37_ASCII_SHA256),
                                            (38, False, FROZEN_38_SHA256), (38, True, FROZEN_38_ASCII_SHA256),
                                            (39, False, FROZEN_39_SHA256), (39, True, FROZEN_39_ASCII_SHA256),
                                            (40, False, FROZEN_40_SHA256), (40, True, FROZEN_40_ASCII_SHA256)):
            data = json.dumps(tools[:count], sort_keys=True, separators=(',', ':'), ensure_ascii=ascii_only)
            self.assertEqual(hashlib.sha256(data.encode()).hexdigest(), expected)
        self.assertEqual([tool['name'] for tool in tools[32:36]], list(NEW))
        self.assertEqual([tool['name'] for tool in tools[36:38]], list(NEW_C))
        self.assertEqual([tool['name'] for tool in tools[38:39]], list(NEW_D))
        self.assertEqual([tool['name'] for tool in tools[39:]], list(NEW_E))
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

    # ----- root_admission_c: marked_compact and phrase_timing ---------------
    def test_admission_c_descriptors_closed_bounded_and_skills_exist(self):
        for name, (prompt, read_only, idempotent, required, ceiling, hook) in NEW_C.items():
            with self.subTest(name=name):
                info = tool_api.descriptor(name)
                schema = info['inputSchema']
                tool_api.validate_schema(schema)
                self.assertIs(schema['additionalProperties'], False)
                self.assertEqual(set(schema['required']), required)
                timeout = schema['properties']['timeout_seconds']
                self.assertEqual((timeout['type'], timeout['minimum'], timeout['maximum']), ('integer', 1, ceiling))
                self.assertEqual(info['implementation_status'], 'experimental')
                self.assertEqual(info['annotations'], {'readOnlyHint': read_only, 'destructiveHint': False,
                                                       'idempotentHint': idempotent, 'openWorldHint': False})
                self.assertEqual(info['skill'], f'.agents/skills/{prompt}/SKILL.md')
                text = (ROOT / info['skill']).read_text(encoding='utf-8')
                self.assertTrue(text.startswith(f'---\nname: {prompt}\ndescription: '))
                self.assertIn(hook, text)
                for key in ('identify', 'research', 'iterate', 'acceptance'):
                    self.assertTrue(info['agent_workflow'][key])
                with self.assertRaises(tool_api.ValidationError):
                    tool_api.validate({'unknown': True}, schema)
        self.assertEqual(tool_api.descriptor('phrase_timing')['inputSchema']['properties']['run_kind']['enum'],
                         ['real_take', 'synthetic_fixture'])

    def test_admission_c_invalid_arguments_refuse_before_worker(self):
        compact = {'run_dir': 'artifacts/runs/audio', 'picture_preview': 'artifacts/runs/preview',
                   'arrangement_markers': 'arrangement/markers.json'}
        timing = {'analysis': '/unopened/analysis.json', 'phrases': '/unopened/markers.json',
                  'output_root': 'artifacts/phrase-timing'}
        invalid = [
            ('marked_compact', dict(compact, arrangement_markers='../markers.json')),
            ('marked_compact', dict(compact, arrangement_markers='/abs/markers.json')),
            ('marked_compact', dict(compact, arrangement_markers='markers.txt')),
            ('marked_compact', dict(compact, run_dir='artifacts/runs/../audio')),
            ('marked_compact', dict(compact, picture_preview='C:\\preview')),
            ('marked_compact', dict(compact, output='artifacts/../escape')),
            ('marked_compact', dict(compact, output='file:///tmp/out')),
            ('marked_compact', dict(compact, timeout_seconds=601)),
            ('marked_compact', dict(compact, codec='h264')),
            ('marked_compact', {k: v for k, v in compact.items() if k != 'arrangement_markers'}),
            ('phrase_timing', dict(timing, run_kind='graded')),
            ('phrase_timing', dict(timing, tendency_threshold_ms=2)),
            ('phrase_timing', dict(timing, analysis='/unopened/../analysis.json')),
            ('phrase_timing', dict(timing, phrases='https://host.invalid/m.json')),
            ('phrase_timing', dict(timing, output_root='artifacts/../out')),
            ('phrase_timing', dict(timing, analysis='/unopened/a\x00.json')),
            ('phrase_timing', dict(timing, timeout_seconds=301)),
            ('phrase_timing', {k: v for k, v in timing.items() if k != 'output_root'}),
        ]
        for name, arguments in invalid:
            with self.subTest(name=name, arguments=arguments), patch.object(tool_api, 'run_worker') as worker:
                with self.assertRaises(tool_api.ValidationError):
                    tool_api.execute(name, arguments)
                worker.assert_not_called()

    def phrase_timing_inputs(self, bound=None):
        from test_phrase_timing import SOURCE_SHA, logic_analysis
        inputs = self.base / 'timing inputs $(literal)'
        inputs.mkdir()
        clicks = [1.0 + 0.5 * k for k in range(40)]
        onsets = [t + 0.012 for t in clicks[2:10]]
        analysis = inputs / 'analysis.json'
        analysis.write_text(json.dumps(logic_analysis(onsets=onsets, clicks=clicks, duration=30.0)))
        markers = inputs / 'markers.json'
        markers.write_text(json.dumps({'format': 'video-utils-arrangement-markers-v1',
                                       'analyzed_input_sha256': bound or SOURCE_SHA,
                                       'markers': [{'name': 'arrangement_aligned_unit_review',
                                                    'source_time_seconds': 1.75, 'end_seconds': 5.75,
                                                    'display_label': 'ALIGNMENT CANDIDATE: phrase 1',
                                                    'label_basis': 'estimated'}]}))
        return analysis, markers

    def test_admission_c_worker_commands_fixed_argv_and_confined_outputs(self):
        analysis, markers = self.phrase_timing_inputs()
        root = self.artifacts / 'phrase timing'
        command = tool_api.worker_command('phrase_timing', {'analysis': str(analysis), 'phrases': str(markers),
                                                            'output_root': str(root)})
        self.assertEqual(command[1:], [str(ROOT / 'scripts/phrase_timing.py'), '--analysis', str(analysis),
                                       '--phrases', str(markers), '--output-root', str(root),
                                       '--run-kind', 'real_take'])
        self.assertEqual(tool_api.worker_command('phrase_timing', {
            'analysis': str(analysis), 'phrases': str(markers), 'output_root': str(root),
            'run_kind': 'synthetic_fixture'})[-1], 'synthetic_fixture')
        outside = self.base / 'not-artifacts'; outside.mkdir()
        alias = self.base / 'analysis-alias.json'; alias.symlink_to(analysis)
        text = self.base / 'analysis.txt'; text.write_text('{}')
        blocker = self.artifacts / 'a-file'; blocker.write_text('x')
        refusals = [
            {'output_root': str(outside / 'pt')}, {'output_root': str(self.artifacts)},
            {'output_root': str(self.artifacts / 'runs' / 'pt')}, {'output_root': str(blocker)},
            {'output_root': str(self.artifacts / 'missing' / 'pt')},
            {'analysis': str(alias)}, {'analysis': str(text)}, {'analysis': str(self.base / 'absent.json')}]
        for change in refusals:
            arguments = dict({'analysis': str(analysis), 'phrases': str(markers), 'output_root': str(root)}, **change)
            with self.subTest(change=change), patch.object(tool_api, 'run_worker') as worker:
                with self.assertRaises(tool_api.ToolError):
                    tool_api.execute('phrase_timing', arguments)
                worker.assert_not_called()
        # marked_compact: parents beneath artifacts/runs, fresh output beneath artifacts/ but not runs.
        runs = self.artifacts / 'runs'
        (runs / 'audio').mkdir(parents=True); (runs / 'preview').mkdir()
        args = {'run_dir': str(runs / 'audio'), 'picture_preview': str(runs / 'preview'),
                'arrangement_markers': 'arrangement/markers.json'}
        with patch.object(tool_api, 'ROOT', self.base):
            command = tool_api.worker_command('marked_compact', dict(args, output=str(self.artifacts / 'compact')))
            self.assertEqual(command[1:], [str(self.base / 'scripts/marked_compact.py'), str(runs / 'audio'),
                                           '--picture-preview', str(runs / 'preview'),
                                           '--arrangement-markers', 'arrangement/markers.json',
                                           '--timeout-seconds', '600', '--output', str(self.artifacts / 'compact')])
            self.assertNotIn('--output', tool_api.worker_command('marked_compact', dict(args, timeout_seconds=30)))
            for output, message in ((str(runs / 'compact'), 'artifacts/runs'), (str(outside / 'c'), 'artifacts/'),
                                    (str(blocker), 'fresh')):
                with self.subTest(output=output), patch.object(tool_api, 'run_worker') as worker:
                    with self.assertRaisesRegex(tool_api.ToolError, message):
                        tool_api.execute('marked_compact', dict(args, output=output))
                    worker.assert_not_called()
            with self.assertRaisesRegex(tool_api.ToolError, 'artifacts/runs'):
                tool_api.worker_command('marked_compact', dict(args, run_dir=str(outside)))
        # The exact dispatcher argv parses in the real worker, which refuses the unverified parents with a
        # typed reason and creates no output.
        completed = subprocess.run([sys.executable, str(ROOT / 'scripts/marked_compact.py')] + command[2:],
                                   cwd=ROOT, capture_output=True, text=True, timeout=120, check=False)
        self.assertEqual(completed.returncode, 1, completed.stderr)
        self.assertEqual(json.loads(completed.stderr)['status'], 'error')
        self.assertTrue(json.loads(completed.stderr)['reason'])
        self.assertFalse(os.path.lexists(self.artifacts / 'compact'))

    def test_admission_c_phrase_timing_executes_without_touching_inputs(self):
        analysis, markers = self.phrase_timing_inputs()
        before = {path: path.read_bytes() for path in (analysis, markers)}
        root = self.artifacts / 'timing'
        result = tool_api.execute('phrase_timing', {'analysis': str(analysis), 'phrases': str(markers),
                                                    'output_root': str(root), 'run_kind': 'synthetic_fixture'})
        self.assertEqual(result['evidence_kind'], 'descriptive_click_relative_timing_unvalidated')
        written = pathlib.Path(result['result']['phrase_timing_json'])
        self.assertEqual(written.parent.parent, root)
        receipt = json.loads(written.read_text())
        self.assertEqual((receipt['click_identity'], receipt['performance_grading'], receipt['expected_rhythm_reference']),
                         ('unverified', 'not_performed', None))
        self.assertEqual((receipt['summary']['phrase_count'], receipt['summary']['measured_count']), (1, 1))
        self.assertEqual(receipt['phrases'][0]['status'], 'measured')
        self.assertEqual({path: path.read_bytes() for path in (analysis, markers)}, before)
        stale = self.base / 'stale.json'
        stale.write_text(markers.read_text().replace(json.loads(markers.read_text())['analyzed_input_sha256'], '0' * 64))
        with self.assertRaises(tool_api.ToolError):
            tool_api.execute('phrase_timing', {'analysis': str(analysis), 'phrases': str(stale),
                                               'output_root': str(self.artifacts / 'stale-out')})
        self.assertFalse((self.artifacts / 'stale-out').exists())

    # ----- S2R descriptor_rebase: phrase_timing wording only (2026-10-07 ruling) ---
    def test_descriptor_rebase_phrase_timing_only_text_changed(self):
        info = tool_api.descriptors()[37]
        self.assertEqual(info['name'], 'phrase_timing')

        def digest(value):
            data = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
            return hashlib.sha256(data.encode()).hexdigest()

        self.assertEqual(digest(info['inputSchema']), PHRASE_TIMING_SCHEMA_SHA256)
        self.assertEqual(digest({k: v for k, v in info.items() if k not in PHRASE_TIMING_TEXT_KEYS}),
                         PHRASE_TIMING_NON_TEXT_SHA256)
        self.assertEqual(len(info['limitations']), 4)
        self.assertEqual(tuple(info['limitations'][:3]), PHRASE_TIMING_BASE_LIMITATIONS_0_2)
        for key in PHRASE_TIMING_TEXT_KEYS:
            self.assertTrue(json.dumps(info[key], ensure_ascii=False).isascii(), key)

    def test_descriptor_rebase_phrase_timing_argv_unchanged(self):
        analysis, markers = self.phrase_timing_inputs()
        root = self.artifacts / 'rebase timing'
        command = tool_api.worker_command('phrase_timing', {'analysis': str(analysis), 'phrases': str(markers),
                                                            'output_root': str(root)})
        self.assertEqual(command[1:], [str(ROOT / 'scripts/phrase_timing.py'), '--analysis', str(analysis),
                                       '--phrases', str(markers), '--output-root', str(root),
                                       '--run-kind', 'real_take'])
        run_kind = tool_api.descriptor('phrase_timing')['inputSchema']['properties']['run_kind']
        self.assertEqual(run_kind['default'], 'real_take')
        self.assertEqual(run_kind['enum'], ['real_take', 'synthetic_fixture'])

    def test_descriptor_rebase_phrase_timing_skill_consistency(self):
        info = tool_api.descriptor('phrase_timing')
        text = ' '.join([info['description'], info['intent']] + info['limitations'])
        for phrase in ('median', 'IQR', 'count', 'withheld on real takes', 'known-offset fixtures',
                       'operator calibration'):
            self.assertIn(phrase, text)
        lowered = text.lower()
        for forbidden in ('tends', 'tendency', 'rushing', 'dragging'):
            self.assertNotIn(forbidden, lowered)
        skill = (ROOT / info['skill']).read_text(encoding='utf-8')
        self.assertTrue(skill.startswith('---\nname: guitar-phrase-timing\ndescription: '))
        for token in ('withheld_uncalibrated', 'synthetic_known_offset_fixture', 'median', 'IQR',
                      'operator calibration'):
            self.assertIn(token, skill)

    # ----- root_admission_d: tone_ab -------------------------------------------
    def test_admission_d_tone_ab_descriptor_equals_lane_draft_and_skill_admitted(self):
        draft = json.loads((ROOT / 'docs/agent-notes/sprints/20261006-s2/tone_ab-tool-descriptor.json')
                           .read_text(encoding='utf-8'))
        self.assertEqual(tool_api.descriptor('tone_ab'), draft)
        described = subprocess.run([sys.executable, str(ROOT / 'scripts/tone_ab.py'), 'describe'], cwd=ROOT,
                                   capture_output=True, text=True, timeout=60, check=True)
        self.assertEqual(json.loads(described.stdout), draft)
        for name, (prompt, read_only, idempotent, required, ceiling, hook) in NEW_D.items():
            with self.subTest(name=name):
                info = tool_api.descriptor(name)
                schema = info['inputSchema']
                tool_api.validate_schema(schema)
                self.assertIs(schema['additionalProperties'], False)
                self.assertEqual(set(schema['required']), required)
                self.assertNotIn('output', ' '.join(schema['properties']))
                timeout = schema['properties']['timeout_seconds']
                self.assertEqual((timeout['type'], timeout['minimum'], timeout['maximum'], timeout['default']),
                                 ('integer', 1, ceiling, 1200))
                self.assertEqual(info['implementation_status'], 'experimental')
                self.assertEqual(info['annotations'], {'readOnlyHint': read_only, 'destructiveHint': False,
                                                       'idempotentHint': idempotent, 'openWorldHint': False})
                self.assertEqual(info['skill'], f'.agents/skills/{prompt}/SKILL.md')
                text = (ROOT / info['skill']).read_text(encoding='utf-8')
                self.assertTrue(text.startswith(f'---\nname: {prompt}\ndescription: '))
                self.assertIn(hook, text)
                self.assertNotIn('(draft)', text)
                self.assertNotIn('once root registers', text)
                for key in ('identify', 'research', 'iterate', 'acceptance'):
                    self.assertTrue(info['agent_workflow'][key])

    def test_admission_d_tone_ab_invalid_arguments_refuse_before_worker(self):
        base = {'run_dir': '/unopened/run', 'common_region_start': 5.0, 'common_region_end': 55.0}
        invalid = [
            dict(base, output_dir='artifacts/elsewhere'),
            dict(base, output='artifacts/x'),
            dict(base, shelf_gain_db=3.0),
            dict(base, common_region_start=4.9),
            dict(base, common_region_end=49.0),
            dict(base, common_region_start=10.0, common_region_end=54.9),
            dict(base, common_region_start=True),
            dict(base, timeout_seconds=0),
            dict(base, timeout_seconds=1801),
            dict(base, timeout_seconds=12.5),
            dict(base, run_dir='/unopened/../run'),
            dict(base, run_dir='file:///tmp/run'),
            dict(base, run_dir='C:\\run'),
            dict(base, run_dir='/unopened/r\x00un'),
            dict(base, candidate_run_dir='artifacts/runs/../x'),
            dict(base, candidate_run_dir=''),
            {k: v for k, v in base.items() if k != 'common_region_end'},
            {k: v for k, v in base.items() if k != 'run_dir'},
        ]
        for arguments in invalid:
            with self.subTest(arguments=arguments), patch.object(tool_api, 'run_worker') as worker:
                with self.assertRaises(tool_api.ValidationError):
                    tool_api.execute('tone_ab', arguments)
                worker.assert_not_called()

    def tone_ab_run(self, name, *, duration_seconds=30, source='ab' * 32):
        run = self.base / name
        run.mkdir()
        (run / 'manifest.json').write_text(json.dumps({
            'schema_version': 1, 'run_id': 'admission-d-' + name.replace(' ', '-'),
            'pcm': {'sample_rate': 1000, 'channels': 1, 'sample_count': 1000 * duration_seconds},
            'outputs': {'source': 'source.wav', 'denoised': 'denoised.wav', 'cleaned': 'cleaned.wav'},
            'output_sha256': {}, 'source': {'sha256': source}}))
        return run

    def test_admission_d_tone_ab_fixed_argv_and_path_refusals(self):
        run = self.tone_ab_run('tone run $(literal)')
        candidate = self.tone_ab_run('tone candidate')
        command = tool_api.worker_command('tone_ab', {'run_dir': str(run), 'common_region_start': 5,
                                                      'common_region_end': 50.5})
        self.assertEqual(command[1:], [str(ROOT / 'scripts/tone_ab.py'), 'run', '--run-dir', str(run),
                                       '--common-region-start', '5.0', '--common-region-end', '50.5',
                                       '--timeout-seconds', '1200'])
        command = tool_api.worker_command('tone_ab', {'run_dir': str(run), 'candidate_run_dir': str(candidate),
                                                      'common_region_start': 6.25, 'common_region_end': 60,
                                                      'timeout_seconds': 30})
        self.assertEqual(command[-4:], ['--timeout-seconds', '30', '--candidate-run-dir', str(candidate)])
        self.assertNotIn('--output-dir', command)
        alias = self.base / 'tone alias'; alias.symlink_to(run, target_is_directory=True)
        empty = self.base / 'no manifest'; empty.mkdir()
        linked = self.base / 'linked manifest'; linked.mkdir()
        (linked / 'manifest.json').symlink_to(run / 'manifest.json')
        refusals = [
            ({'run_dir': str(alias)}, 'symlink'),
            ({'run_dir': str(empty)}, 'manifest.json'),
            ({'run_dir': str(linked)}, 'manifest.json'),
            ({'run_dir': str(self.base / 'absent')}, 'existing directory'),
            ({'candidate_run_dir': str(alias)}, 'symlink'),
            ({'candidate_run_dir': str(run)}, 'differ'),
        ]
        for change, message in refusals:
            arguments = dict({'run_dir': str(run), 'common_region_start': 5.0, 'common_region_end': 55.0}, **change)
            with self.subTest(change=change), patch.object(tool_api, 'run_worker') as worker:
                with self.assertRaisesRegex(tool_api.ToolError, message):
                    tool_api.execute('tone_ab', arguments)
                worker.assert_not_called()

    def test_admission_d_tone_ab_real_worker_refuses_without_writes(self):
        # The exact dispatcher argv parses in the real worker, which refuses on its own identity and
        # extent gates (exit 2) before creating any output and without touching the inputs.
        run = self.tone_ab_run('tone short run')
        other = self.tone_ab_run('tone other source', source='cd' * 32)
        outputs = ROOT / 'artifacts' / 's2' / 'tone_ab'
        before_outputs = sorted(os.listdir(outputs)) if outputs.is_dir() else []
        before = {path: path.read_bytes() for path in (run / 'manifest.json', other / 'manifest.json')}
        for arguments, code in (
                ({'run_dir': str(run), 'common_region_start': 5.0, 'common_region_end': 55.0}, 'region_out_of_bounds'),
                ({'run_dir': str(self.tone_ab_run('tone long run', duration_seconds=60)),
                  'candidate_run_dir': str(other), 'common_region_start': 5.0, 'common_region_end': 55.0,
                  'timeout_seconds': 60}, 'candidate_source_mismatch')):
            with self.subTest(code=code):
                with self.assertRaisesRegex(tool_api.ToolError, 'worker failed \\(2\\).*' + code):
                    tool_api.execute('tone_ab', arguments)
        self.assertEqual({path: path.read_bytes() for path in before}, before)
        self.assertEqual(sorted(os.listdir(outputs)) if outputs.is_dir() else [], before_outputs)
        self.assertEqual(sorted(path.name for path in run.iterdir()), ['manifest.json'])

    # ----- root_admission_e: report_bundle -------------------------------------
    def test_admission_e_report_bundle_descriptor_equals_lane_draft_and_skill_exists(self):
        draft = json.loads((ROOT / 'docs/agent-notes/sprints/20261006-s2/report_d6-tool-descriptor.json')
                           .read_text(encoding='utf-8'))
        self.assertEqual(tool_api.descriptor('report_bundle'), draft)
        for name, (prompt, read_only, idempotent, required, ceiling, hook) in NEW_E.items():
            with self.subTest(name=name):
                info = tool_api.descriptor(name)
                schema = info['inputSchema']
                tool_api.validate_schema(schema)
                self.assertIs(schema['additionalProperties'], False)
                self.assertEqual(set(schema['required']), required)
                self.assertEqual(set(schema['properties']),
                                 {'run_dir', 'analysis_run_dir', 'annotation_store', 'timeout_seconds'})
                self.assertNotIn('output', ' '.join(schema['properties']))
                timeout = schema['properties']['timeout_seconds']
                self.assertEqual((timeout['type'], timeout['minimum'], timeout['maximum'], timeout['default']),
                                 ('integer', 1, ceiling, 600))
                self.assertEqual(info['implementation_status'], 'experimental')
                self.assertEqual(info['annotations'], {'readOnlyHint': read_only, 'destructiveHint': False,
                                                       'idempotentHint': idempotent, 'openWorldHint': False})
                self.assertEqual(info['skill'], f'.agents/skills/{prompt}/SKILL.md')
                data = (ROOT / info['skill']).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), REPORT_BUNDLE_SKILL_SHA256)
                text = data.decode('utf-8')
                self.assertTrue(text.startswith(f'---\nname: {prompt}\ndescription: '))
                self.assertIn(hook, text)
                self.assertNotIn('once admitted by root', text)
                self.assertIn('**Hook:** MCP tool `report_bundle` (admitted as tool 40).', text)
                self.assertIn('Never adopt a detector, profile or master default', text)
                for key in ('identify', 'research', 'iterate', 'acceptance'):
                    self.assertTrue(info['agent_workflow'][key])
                with self.assertRaises(tool_api.ValidationError):
                    tool_api.validate({'unknown': True}, schema)

    def test_admission_e_report_bundle_invalid_arguments_refuse_before_worker(self):
        base = {'run_dir': '/unopened/run'}
        invalid = [
            dict(base, output_dir='artifacts/elsewhere'),
            dict(base, output='artifacts/x'),
            dict(base, argv=['--output-dir', '/tmp/x']),
            dict(base, check_origin=True),
            dict(base, timeout_seconds=0),
            dict(base, timeout_seconds=901),
            dict(base, timeout_seconds=12.5),
            dict(base, timeout_seconds=True),
            dict(base, run_dir='/unopened/../run'),
            dict(base, run_dir='../run'),
            dict(base, run_dir='file:///tmp/run'),
            dict(base, run_dir='C:\\run'),
            dict(base, run_dir='/unopened/r\x00un'),
            dict(base, run_dir=''),
            dict(base, analysis_run_dir='artifacts/runs/../x'),
            dict(base, analysis_run_dir=''),
            dict(base, annotation_store='../review-annotations-v2.json'),
            dict(base, annotation_store='https://host.invalid/store.json'),
            {},
        ]
        for arguments in invalid:
            with self.subTest(arguments=arguments), patch.object(tool_api, 'run_report_bundle_worker') as worker:
                with self.assertRaises(tool_api.ValidationError):
                    tool_api.execute('report_bundle', arguments)
                worker.assert_not_called()

    def report_bundle_run(self, name, manifest=None):
        run = self.base / name
        run.mkdir()
        (run / 'manifest.json').write_text(json.dumps(manifest if manifest is not None else {
            'schema_version': 1, 'run_id': 'admission-e', 'source': {'sha256': 'ab' * 32}, 'output_sha256': {}}))
        return run

    def test_admission_e_report_bundle_fixed_argv_and_path_refusals(self):
        run = self.report_bundle_run('bundle run $(literal)')
        analysis = self.report_bundle_run('bundle analysis')
        store = self.base / 'review-annotations-v2.json'; store.write_text('{}')
        command = tool_api.worker_command('report_bundle', {'run_dir': str(run)})
        self.assertEqual(command[1:], [str(ROOT / 'scripts/report_bundle.py'), 'build', '--run-dir', str(run)])
        command = tool_api.worker_command('report_bundle', {'run_dir': str(run), 'analysis_run_dir': str(analysis),
                                                            'annotation_store': str(store), 'timeout_seconds': 30})
        self.assertEqual(command[1:], [str(ROOT / 'scripts/report_bundle.py'), 'build', '--run-dir', str(run),
                                       '--analysis-run-dir', str(analysis), '--annotation-store', str(store)])
        self.assertNotIn('--output-dir', command)
        self.assertNotIn('30', command)
        alias = self.base / 'bundle alias'; alias.symlink_to(run, target_is_directory=True)
        store_alias = self.base / 'store-alias.json'; store_alias.symlink_to(store)
        text = self.base / 'store.txt'; text.write_text('{}')
        empty = self.base / 'no manifest'; empty.mkdir()
        refusals = [
            ({'run_dir': str(alias)}, 'symlink'),
            ({'run_dir': str(empty)}, 'manifest.json'),
            ({'run_dir': str(self.base / 'absent')}, 'existing directory'),
            ({'analysis_run_dir': str(alias)}, 'symlink'),
            ({'analysis_run_dir': str(empty)}, 'manifest.json'),
            ({'annotation_store': str(store_alias)}, 'symlink'),
            ({'annotation_store': str(text)}, 'JSON'),
            ({'annotation_store': str(self.base / 'absent.json')}, 'existing bounded regular file'),
        ]
        for change, message in refusals:
            arguments = dict({'run_dir': str(run)}, **change)
            with self.subTest(change=change), patch.object(tool_api, 'run_report_bundle_worker') as worker:
                with self.assertRaisesRegex(tool_api.ToolError, message):
                    tool_api.execute('report_bundle', arguments)
                worker.assert_not_called()

    def test_admission_e_report_bundle_deadline_and_result_confinement(self):
        run = self.report_bundle_run('bundle deadline run')
        boundary = self.artifacts / 's2' / 'report_d6' / 'bundles'
        boundary.mkdir(parents=True)
        built = boundary / 'admission-e-20261006T000000Z'
        (built / 'tables').mkdir(parents=True)
        (built / 'bundle.json').write_text('{}')
        good = {'status': 'built', 'bundle_dir': str(built), 'bundle_sha256': 'c' * 64}
        with patch.object(tool_api, 'REPORT_BUNDLE_OUTPUT_ROOT', boundary):
            for arguments, deadline in (({'run_dir': str(run)}, 600), ({'run_dir': str(run), 'timeout_seconds': 900}, 900),
                                        ({'run_dir': str(run), 'timeout_seconds': 1}, 1)):
                with self.subTest(arguments=arguments), patch.object(tool_api, 'run_report_bundle_worker',
                                                                     return_value=dict(good)) as worker:
                    result = tool_api.execute('report_bundle', arguments)
                    self.assertEqual(result['result'], good)
                    self.assertEqual(result['evidence_kind'], 'hash_bound_metadata_bundle_with_quoted_receipt_figures')
                    worker.assert_called_once()
                    self.assertEqual(worker.call_args.args[1], deadline)
                    self.assertEqual(worker.call_args.kwargs, {})
            outside = self.base / 'outside-bundle'; outside.mkdir()
            nested = boundary / 'a' / 'b'; nested.mkdir(parents=True)
            linked = boundary / 'linked'; linked.symlink_to(outside, target_is_directory=True)
            media = boundary / 'with-media'; media.mkdir(); (media / 'stage.wav').write_bytes(b'RIFF')
            bad = [dict(good, status='refused'), dict(good, bundle_sha256='C' * 64), dict(good, bundle_dir='relative'),
                   dict(good, bundle_dir=str(outside)), dict(good, bundle_dir=str(nested)),
                   dict(good, bundle_dir=str(linked)), dict(good, bundle_dir=str(boundary / 'absent')),
                   dict(good, bundle_dir=str(media))]
            for result in bad:
                with self.subTest(result=result), self.assertRaises(tool_api.ToolError):
                    tool_api.classify_report_bundle_result(result)

    def test_admission_e_report_bundle_failure_codes_never_relay_tails(self):
        refused = tool_api.report_bundle_failure(2, b'{"reason": "stage_hash_mismatch", "status": "refused"}\n')
        self.assertEqual(str(refused), 'worker refused (2): report_bundle stage_hash_mismatch')
        self.assertEqual(refused.receipt, {'report_bundle': {'status': 'refused', 'reason': 'stage_hash_mismatch',
                                                             'published': False}})
        error = tool_api.report_bundle_failure(1, b'{"error": "PermissionError", "status": "error"}\n')
        self.assertEqual(str(error), 'worker failed (1): report_bundle error PermissionError')
        for code, data in ((2, b'{"status": "refused", "reason": "/srv/private/path"}'),
                           (1, b'Traceback: /private/take.mov'), (2, b''), (3, b'{"status": "refused", "reason": "x"}'),
                           (1, b'{"status": "error", "error": "a b"}')):
            with self.subTest(code=code, data=data):
                failure = tool_api.report_bundle_failure(code, data)
                self.assertEqual(str(failure), f'worker failed ({code}): report_bundle returned no typed diagnostic')
                self.assertIsNone(failure.receipt)

    def test_admission_e_report_bundle_runner_deadline_and_stdout_codes(self):
        script = self.base / 'fake worker.py'
        cases = (('import time; time.sleep(30)', None),
                 ('print(\'{"status": "refused", "reason": "bundle_too_large"}\'); raise SystemExit(2)',
                  'worker refused (2): report_bundle bundle_too_large'),
                 ('import sys; sys.stderr.write("/srv/private"); raise SystemExit(1)',
                  'worker failed (1): report_bundle returned no typed diagnostic'),
                 ('print(\'{"status": "built"}\')', None))
        for index, (body, message) in enumerate(cases):
            script.write_text(body)
            with self.subTest(body=body):
                if index == 0:
                    with self.assertRaisesRegex(tool_api.ToolError, 'deadline exceeded \\(1s\\)') as caught:
                        tool_api.run_report_bundle_worker([sys.executable, str(script)], 1)
                    self.assertEqual(caught.exception.receipt['result']['signal_target'], 'owned_process_group')
                elif message:
                    with self.assertRaises(tool_api.ToolError) as caught:
                        tool_api.run_report_bundle_worker([sys.executable, str(script)], 30)
                    self.assertEqual(str(caught.exception), message)
                else:
                    self.assertEqual(tool_api.run_report_bundle_worker([sys.executable, str(script)], 30),
                                     {'status': 'built'})

    def test_admission_e_report_bundle_real_worker_refusal_writes_nothing(self):
        # The exact dispatcher argv parses in the real worker, which refuses on manifest identity (exit 2)
        # before choosing an output directory, so nothing is written anywhere.
        run = self.report_bundle_run('bundle no source', manifest={'schema_version': 1, 'output_sha256': {}})
        outputs = ROOT / 'artifacts' / 's2' / 'report_d6' / 'bundles'
        before_outputs = sorted(os.listdir(outputs)) if outputs.is_dir() else []
        before = (run / 'manifest.json').read_bytes()
        with self.assertRaises(tool_api.ToolError) as caught:
            tool_api.execute('report_bundle', {'run_dir': str(run), 'timeout_seconds': 60})
        self.assertEqual(str(caught.exception), 'worker refused (2): report_bundle source_identity_missing')
        self.assertEqual(caught.exception.receipt['report_bundle']['reason'], 'source_identity_missing')
        self.assertEqual((run / 'manifest.json').read_bytes(), before)
        self.assertEqual(sorted(path.name for path in run.iterdir()), ['manifest.json'])
        self.assertEqual(sorted(os.listdir(outputs)) if outputs.is_dir() else [], before_outputs)

    # ----- MCP prompt readback ------------------------------------------------
    def test_real_mcp_lists_tools_and_reads_back_each_new_skill_prompt(self):
        messages = [initialization(), {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
                    request(2, 'tools/list'), request(3, 'prompts/list')]
        admitted = list(NEW.items()) + list(NEW_C.items()) + list(NEW_D.items()) + list(NEW_E.items())
        messages += [request(10 + index, 'prompts/get', {'name': prompt})
                     for index, (_name, (prompt, *_rest)) in enumerate(admitted)]
        replies, stderr = exchange(messages, timeout=30)
        self.assertEqual(stderr, '')
        tools = {row['name']: row for row in replies[1]['result']['tools']}
        self.assertEqual(len(tools), 40)
        prompts = {row['name'] for row in replies[2]['result']['prompts']}
        self.assertEqual(len(prompts), 40)
        for offset, (name, (prompt, *_rest)) in enumerate(admitted):
            with self.subTest(name=name):
                self.assertIs(tools[name]['inputSchema']['additionalProperties'], False)
                self.assertIn(prompt, prompts)
                text = replies[3 + offset]['result']['messages'][0]['content']['text']
                self.assertEqual(text, (ROOT / '.agents/skills' / prompt / 'SKILL.md').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
