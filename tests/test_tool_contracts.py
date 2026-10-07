"""Cross-tool contract checks independent of proposed extension implementation."""
import json
import hashlib
import os
import shutil
import uuid
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import tool_api
import mcp_server


def basic_pitch_missing_test_artifacts():
    """Availability only; present but corrupt qualified artifacts must fail inference."""
    import basic_pitch_compare as comparator
    cached = comparator.ROOT / 'models' / (comparator.MODEL_ID + '.bin')
    selected = cached if cached.exists() else comparator.LOCAL_MODEL
    return [label for label, path in (('local model', selected), ('isolated runtime', comparator.RUNTIME),
                                     ('runtime wheel manifest', comparator.WHEEL_MANIFEST)) if not path.is_file()]


class ToolContractTests(unittest.TestCase):
    def learned_evaluator_fixture(self):
        from test_learned_pitch_evaluate import create_fixture
        root = ROOT / 'artifacts/benchmarks' / ('contract-learned-evaluate-' + uuid.uuid4().hex)
        root.mkdir(parents=True); self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        bank, pyin, learned = create_fixture(root / 'bank')
        return root, {'fixture_index': str(bank), 'pyin_pilot_index': str(pyin),
                      'learned_pilot_index': str(learned), 'output': str(root / 'result')}

    def learned_evaluator_call(self, arguments):
        from test_mcp import exchange, initialization, request
        with patch.dict(os.environ, {'FFMPEG': '/nonexistent/ffmpeg', 'FFPROBE': '/nonexistent/ffprobe',
                                     'VIDEO_UTILS_ANALYSIS_PYTHON': '/nonexistent/analysis-python'}):
            replies, stderr = exchange([initialization(), {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
                request(2, 'tools/call', {'name': 'learned_pitch_evaluate', 'arguments': arguments})], timeout=120)
        self.assertEqual(stderr, '')
        return replies[1]['result']

    def test_learned_evaluator_schema_rejects_runtime_truth_and_unsafe_paths(self):
        valid = {'fixture_index': 'artifacts/benchmarks/bank.json', 'pyin_pilot_index': 'artifacts/benchmarks/pyin.json',
                 'learned_pilot_index': 'artifacts/benchmarks/learned.json', 'output': 'artifacts/benchmarks/new'}
        invalid = [dict(valid, timeout_seconds=True), dict(valid, timeout_seconds=121), dict(valid, timeout_seconds=0),
                   dict(valid, timeout_seconds=float('inf')), dict(valid, runtime_python='/bin/python'),
                   dict(valid, model_path='weights.onnx'), dict(valid, install_model=True), dict(valid, threshold=.2),
                   dict(valid, clock='best_by_truth'), dict(valid, learned_pilot_index='x' * 4097),
                   dict(valid, pyin_pilot_index=['index.json']), dict(valid, fixture_index='source.wav')]
        for field in tool_api.LEARNED_EVALUATION_FIELDS:
            invalid.extend(dict(valid, **{field: path}) for path in ('../bad.json', 'https://host/index.json',
                          'artifacts//benchmarks/index.json', 'artifacts/benchmarks/.stage/index.json',
                          'artifacts/benchmarks/run.partial/index.json', 'bad\\index.json'))
        for arguments in invalid:
            with self.subTest(arguments=arguments), patch.object(tool_api, 'run_worker') as worker:
                with self.assertRaises(tool_api.ValidationError): tool_api.execute('learned_pitch_evaluate', arguments)
                worker.assert_not_called()

    def test_learned_evaluator_fixed_command_deadline_and_preflight(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(); bank = root / 'artifacts/benchmarks'; bank.mkdir(parents=True)
            args = {'output': str(bank / 'new')}
            for field in tool_api.LEARNED_EVALUATION_FIELDS[:-1]:
                path = bank / (field + ' $(literal);.json'); path.write_text('{}'); args[field] = str(path)
            with patch.object(tool_api, 'ROOT', root):
                command = tool_api.worker_command('learned_pitch_evaluate', args)
                expected = [str(root / 'scripts/learned_pitch_evaluate.py')]
                for field in tool_api.LEARNED_EVALUATION_FIELDS:
                    expected += ['--' + field.replace('_', '-'), args[field]]
                self.assertEqual(command[1:], expected + ['--summary'])
                with patch.object(tool_api, 'run_worker', return_value={'status': 'test'}) as worker:
                    tool_api.execute('learned_pitch_evaluate', args); self.assertEqual(worker.call_args.args[1], 120)
                    tool_api.execute('learned_pitch_evaluate', dict(args, timeout_seconds=7))
                    self.assertEqual(worker.call_args.args[1], 7); self.assertEqual(worker.call_args.kwargs, {})
                linked = bank / 'linked.json'; linked.symlink_to(Path(args['fixture_index']))
                oversized = bank / 'large.json'
                with oversized.open('wb') as handle: handle.truncate(5_000_001)
                for changes in ({'fixture_index': str(linked)}, {'learned_pilot_index': str(oversized)},
                                {'pyin_pilot_index': str(bank / 'missing.json')}, {'output': str(bank)},
                                {'output': str(root / 'outside')}, {'output': args['fixture_index']}):
                    with self.subTest(changes=changes), patch.object(tool_api, 'run_worker') as worker:
                        with self.assertRaises(tool_api.ToolError): tool_api.execute('learned_pitch_evaluate', dict(args, **changes))
                        worker.assert_not_called()

    def test_real_learned_evaluator_mcp_preserves_octave_failure_and_inputs(self):
        root, args = self.learned_evaluator_fixture()
        before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in (root / 'bank').rglob('*') if path.is_file()}
        response = self.learned_evaluator_call(args); self.assertFalse(response['isError'], response)
        result = response['structuredContent']['result']
        self.assertEqual((result['case_count'], result['coverage_seconds'], result['model_windows']), (4, 30, 19))
        self.assertTrue(result['hard_gates_passed']); self.assertTrue(result['quality_alerts'])
        self.assertTrue(result['source_audio_bytes_read']); self.assertTrue(result['raw_array_bytes_read'])
        self.assertFalse(result['source_audio_decoded']); self.assertFalse(result['inference_invoked'])
        self.assertFalse(result['real_performance_grading']); self.assertFalse(result['listening_accepted'])
        self.assertEqual(result['ground_truth_scope'], 'generator_only_not_musician')
        self.assertNotIn('cases', result); self.assertLess(len(json.dumps(result)), 20_000)
        evidence = json.loads(Path(result['evaluation_json']).read_text())
        metrics = evidence['cases'][0]['native_model_input_context']['stable_monophonic_metrics']
        self.assertEqual(metrics['raw_pitch_accuracy']['value'], 0.)
        self.assertEqual(metrics['raw_chroma_accuracy']['value'], 1.)
        self.assertEqual(metrics['octave_error_fraction']['value'], 1.)
        self.assertTrue(Path(result['frame_errors_csv']).is_file()); self.assertTrue(Path(result['event_errors_csv']).is_file())
        for path, digest in before.items(): self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
        reused = self.learned_evaluator_call(args); self.assertTrue(reused['isError'])
        self.assertIn('new directory', reused['content'][0]['text'])

    def test_real_learned_evaluator_stale_raw_retains_structural_receipt(self):
        root, args = self.learned_evaluator_fixture()
        index = json.loads(Path(args['learned_pilot_index']).read_text())
        Path(index['jobs'][0]['activations_path']).write_bytes(b'changed archive')
        response = self.learned_evaluator_call(args); self.assertTrue(response['isError'])
        diagnostic = response['content'][0]['text']; self.assertIn('sha256_mismatch', diagnostic)
        self.assertIn('retained', diagnostic)
        evidence = json.loads((Path(args['output']) / 'learned-pitch-calibration.json').read_text())
        self.assertEqual(evidence['status'], 'failed_structural'); self.assertFalse(evidence['hard_gates_passed'])
        self.assertNotIn('cases', evidence); self.assertFalse(evidence['inference_invoked'])

    def test_real_learned_evaluator_unsupported_claim_keeps_metrics_and_fails(self):
        from test_pitch_evaluate import put_json
        root, args = self.learned_evaluator_fixture()
        index_path = Path(args['learned_pilot_index']); index = json.loads(index_path.read_text())
        job = index['jobs'][0]; receipt_path = Path(job['comparison_path']); receipt = json.loads(receipt_path.read_text())
        receipt['extra'] = {'note_correctness_confirmed': True}
        job['comparison_sha256'] = put_json(receipt_path, receipt); put_json(index_path, index)
        response = self.learned_evaluator_call(args); self.assertTrue(response['isError'])
        self.assertIn('unsupported_confirmed_claims', response['content'][0]['text'])
        evidence = json.loads((Path(args['output']) / 'learned-pitch-calibration.json').read_text())
        self.assertFalse(evidence['hard_gates_passed']); self.assertEqual(evidence['unsupported_claim_count'], 1)
        self.assertEqual(evidence['case_count'], 4); self.assertTrue(evidence['cases'])
        self.assertFalse(evidence['real_performance_grading']); self.assertFalse(evidence['listening_accepted'])

    def test_learned_evaluator_prompt_exact_readback(self):
        from test_mcp import exchange, initialization, request
        replies, stderr = exchange([initialization(), {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
            request(2, 'tools/list'), request(3, 'prompts/get', {'name': 'guitar-learned-pitch-evaluate'})])
        self.assertEqual(stderr, ''); self.assertEqual(len(replies[1]['result']['tools']), len(tool_api.descriptors()))
        self.assertEqual(replies[2]['result']['messages'][0]['content']['text'],
                         (ROOT / '.agents/skills/guitar-learned-pitch-evaluate/SKILL.md').read_text())

    def editor_marker_fixture(self):
        from test_editor_marker_plan import EditorMarkerPlanTests
        run = ROOT / 'artifacts/runs' / ('contract-editor-plan-' + uuid.uuid4().hex)
        run.mkdir(parents=True); self.addCleanup(shutil.rmtree, run, ignore_errors=True)
        EditorMarkerPlanTests().disk_fixture(run)
        return run, {'run_dir': str(run), 'selection': 'selection.json', 'profile': 'profile.json'}

    def test_editor_marker_schema_paths_and_no_host_controls(self):
        args = {'run_dir': 'artifacts/runs/existing', 'selection': 'selection.json', 'profile': 'profile.json'}
        invalid = [dict(args, selection='../selection.json'), dict(args, profile='/absolute/profile.json'),
                   dict(args, profile='https://editor.invalid/profile.json'), dict(args, selection='hidden/.partial.json'),
                   dict(args, profile='profile.py'), dict(args, profile='a//profile.json'),
                   dict(args, selection='profile.json'), dict(args, profile='manifest.json'),
                   dict(args, selection='x' * 1025), dict(args, timeout_seconds=True), dict(args, timeout_seconds=121),
                   dict(args, run_dir='x' * 4097), dict(args, output='import.fcpxml'), dict(args, editor_api='AddMarker'),
                   dict(args, apply=True), dict(args, profile_json={'target': 'davinci_resolve'}),
                   {'run_dir': args['run_dir'], 'profile': args['profile']}]
        for arguments in invalid:
            with self.subTest(arguments=arguments), patch.object(tool_api, 'run_worker') as worker:
                with self.assertRaises(tool_api.ValidationError):
                    tool_api.execute('editor_marker_plan', arguments)
                worker.assert_not_called()

    def test_editor_marker_dispatch_fixed_summary_and_bounded_metadata(self):
        run, args = self.editor_marker_fixture()
        command = tool_api.worker_command('editor_marker_plan', args)
        self.assertEqual(command[1:], [str(ROOT / 'scripts/editor_marker_plan.py'), str(run),
            'selection.json', 'profile.json', '--summary'])
        with patch.object(tool_api, 'run_worker', return_value={'executable': False}) as worker:
            tool_api.execute('editor_marker_plan', args)
            self.assertEqual(worker.call_args.args[1], 120)
            self.assertEqual(worker.call_args.kwargs, {})
        (run / 'linked.json').symlink_to(run / 'profile.json')
        with self.assertRaisesRegex(tool_api.ToolError, 'symlink'):
            tool_api.worker_command('editor_marker_plan', dict(args, profile='linked.json'))
        with (run / 'oversized.json').open('wb') as handle: handle.truncate(20000001)
        with self.assertRaisesRegex(tool_api.ToolError, 'bounded'):
            tool_api.worker_command('editor_marker_plan', dict(args, profile='oversized.json'))
        with self.assertRaises(tool_api.ToolError):
            tool_api.worker_command('editor_marker_plan', dict(args, profile='missing.json'))

    def test_real_editor_marker_mcp_metadata_summary_is_readonly_and_unverified(self):
        from test_mcp import exchange, initialization, request
        run, args = self.editor_marker_fixture()
        profile_path = run / 'profile.json'; profile = json.loads(profile_path.read_text())
        complete, complete_stderr = exchange([initialization(), {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
            request(2, 'tools/call', {'name': 'editor_marker_plan', 'arguments': args})], timeout=15)
        self.assertEqual(complete_stderr, '')
        self.assertFalse(complete[1]['result']['isError'], complete[1])
        fixture_summary = complete[1]['result']['structuredContent']['result']
        self.assertGreater(fixture_summary['action_count'], 0)
        self.assertFalse(fixture_summary['executable'])
        self.assertEqual(fixture_summary['native_contract_status'], 'native_contract_unverified')
        profile.pop('pts_artifact'); profile['input_sha256'].pop('pts.json'); profile.pop('fixture_grid')
        profile_path.write_text(json.dumps(profile))
        before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in run.iterdir()}
        with patch.dict(os.environ, {'FFMPEG': '/nonexistent/ffmpeg', 'FFPROBE': '/nonexistent/ffprobe'}):
            replies, stderr = exchange([initialization(), {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
                request(2, 'tools/call', {'name': 'editor_marker_plan', 'arguments': args})], timeout=15)
        self.assertEqual(stderr, '')
        response = replies[1]['result']; self.assertFalse(response['isError'], response)
        result = response['structuredContent']['result']
        self.assertEqual(result['format'], 'editor_marker_dry_run_summary')
        self.assertEqual(result['native_contract_status'], 'native_contract_unverified')
        self.assertFalse(result['executable']); self.assertEqual(result['action_count'], 0)
        self.assertEqual((result['marker_count'], result['selected_count'], result['excluded_count']), (1, 1, 0))
        self.assertEqual(result['plan_status'], 'calibration_required')
        self.assertEqual(result['disposition_counts'], {'video_coverage_unverified': 1})
        self.assertNotIn('markers', result); self.assertNotIn('actions', result)
        self.assertEqual(result['scope'], 'source_metadata_only_no_editor_invocation')
        self.assertEqual(set(before), set(run.iterdir()))
        for path, digest in before.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)

    def test_real_editor_marker_mcp_rejects_closed_profile_stale_and_nonfinite_data(self):
        from test_mcp import exchange, initialization, request
        run, args = self.editor_marker_fixture()
        path = run / 'profile.json'; good = json.loads(path.read_text())
        for profile in (dict(good, executable=True), dict(good, schema_version=True),
                        dict(good, fixture_grid=dict(good['fixture_grid'], script='AddMarker')),
                        dict(good, existing_markers=[{'fixture_frame_id': 1, 'command': 'AddMarker'}]),
                        dict(good, input_sha256=dict(good['input_sha256'], **{'manifest.json': 'b' * 64})),
                        dict(good, source_origin=float('nan'))):
            path.write_text(json.dumps(profile))
            replies, stderr = exchange([initialization(), {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
                request(2, 'tools/call', {'name': 'editor_marker_plan', 'arguments': args})], timeout=15)
            self.assertEqual(stderr, '')
            self.assertTrue(replies[1]['result']['isError'])
            self.assertIn('editor-marker-plan:', json.loads(replies[1]['result']['content'][0]['text'])['error'])
        self.assertEqual(set(p.name for p in run.iterdir()), {'manifest.json', 'flags.json', 'markers.json',
                                                               'selection.json', 'profile.json', 'pts.json'})

    def test_real_editor_marker_mcp_summary_fits_pipe_after_large_full_plan(self):
        import editor_marker_plan as planner
        from test_mcp import exchange, initialization, request
        run, args = self.editor_marker_fixture()
        flags = {'source_sha256': 'a' * 64, 'flags': [{'source_time_seconds': 1 + index / 10000,
            'end_seconds': 1 + index / 10000, 'kind': 'review_candidate', 'status': 'needs_review',
            'evidence': {'detail': 'x' * 2000}} for index in range(1200)]}
        (run / 'flags.json').write_text(json.dumps(flags))
        generic, _ = planner.markers.build(run)
        (run / 'markers.json').write_text(json.dumps(generic))
        selection = {'source_sha256': 'a' * 64, 'selected_markers': [
            {'marker_index': index, 'marker_id': planner.marker_id(index, row)}
            for index, row in enumerate(generic['markers'])]}
        (run / 'selection.json').write_text(json.dumps(selection))
        profile = {'target': 'davinci_resolve', 'source_sha256': 'a' * 64,
                   'input_sha256': {name: hashlib.sha256((run / name).read_bytes()).hexdigest()
                                    for name in ('markers.json', 'manifest.json', 'selection.json')}}
        (run / 'profile.json').write_text(json.dumps(profile))
        full = planner.build(run, 'selection.json', 'profile.json')
        self.assertGreater(len(json.dumps(full).encode()), tool_api.MAX_WORKER_OUTPUT)
        replies, stderr = exchange([initialization(), {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
            request(2, 'tools/call', {'name': 'editor_marker_plan', 'arguments': args})], timeout=30)
        self.assertEqual(stderr, '')
        response = replies[1]['result']; self.assertFalse(response['isError'], response)
        summary = response['structuredContent']['result']
        self.assertEqual((summary['marker_count'], summary['selected_count'], summary['excluded_count']), (1200, 1200, 0))
        self.assertEqual(summary['action_count'], 0); self.assertFalse(summary['executable'])
        self.assertLess(len(json.dumps(summary).encode()), 65536)

    def test_editor_marker_prompt_exact_readback(self):
        from test_mcp import exchange, initialization, request
        replies, stderr = exchange([initialization(), {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
            request(2, 'prompts/get', {'name': 'editor-marker-plan'})])
        self.assertEqual(stderr, '')
        self.assertEqual(replies[1]['result']['messages'][0]['content']['text'],
                         (ROOT / '.agents/skills/editor-marker-plan/SKILL.md').read_text())

    def capture_profile_fixture(self):
        import math, struct, wave
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        source = Path(temp.name).resolve() / 'original $(literal); source.wav'
        with wave.open(str(source), 'wb') as audio:
            audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(16000)
            audio.writeframes(b''.join(struct.pack('<h', round(1500 * math.sin(2 * math.pi * 32 * i / 16000)
                + 200 * math.sin(2 * math.pi * 103 * i / 16000))) for i in range(32000)))
        run = ROOT / 'artifacts/runs' / ('contract-capture-' + uuid.uuid4().hex)
        run.mkdir(parents=True); self.addCleanup(shutil.rmtree, run, ignore_errors=True)
        pcm = run / 'source.wav'; shutil.copyfile(source, pcm)
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        manifest = {'schema_version': 1, 'source': {'path': str(source), 'sha256': digest},
                    'pcm': {'sample_rate': 16000, 'channels': 1, 'sample_count': 32000},
                    'outputs': {'source': 'source.wav'}, 'output_sha256': {'source.wav': digest},
                    'timeline': {'audio_start_seconds': 7.125, 'no_time_stretch': True}}
        manifest_path = run / 'manifest.json'; manifest_path.write_text(json.dumps(manifest))
        review = {'schema_version': 1, 'source_sha256': digest,
                  'source_run_manifest_sha256': hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                  'source_pcm_sha256': digest, 'start_seconds': .125, 'end_seconds': .625,
                  'time_axis': 'decoded_source_audio_samples', 'selected_by': 'fixture selector',
                  'reviewed_by': 'fixture reviewer', 'review_status': 'reviewed_possible_contamination',
                  'authorization_scope': 'experimental_capture_render',
                  'authorization_reference': 'Fixture supplied assertion for metadata test, no audio rendering.',
                  'music_status': 'suspected', 'click_status': 'unknown', 'ambient_music_status': 'not_reported',
                  'note': 'Generated 32 Hz musical content is present; this interval is not a clean-noise truth.'}
        review_path = run / 'review.json'; review_path.write_text(json.dumps(review))
        arguments = {'input': str(source), 'run_dir': str(run), 'review': str(review_path),
                     'capture_start_seconds': .125, 'capture_end_seconds': .625, 'reduction_db': 8,
                     'noise_floor_db': -40, 'adaptivity': 0, 'gain_smooth': 0,
                     'integrated_lufs': -18, 'true_peak_dbtp': -1.5}
        return source, run, review_path, review, arguments

    def test_capture_profile_schema_extension_is_bounded_and_closed(self):
        args = {'input': 'source.wav', 'run_dir': 'artifacts/runs/existing', 'review': 'review.json',
                'capture_start_seconds': .125, 'capture_end_seconds': .625, 'reduction_db': 8,
                'noise_floor_db': -40, 'adaptivity': 0, 'gain_smooth': 0, 'integrated_lufs': -18,
                'true_peak_dbtp': -1.5}
        band = {'frequency_hz': 300, 'gain_db': -1.5, 'q': .8}
        bad = [dict(args, peaking_eq=[band] * 4), dict(args, peaking_eq={'frequency_hz': 300}),
               dict(args, peaking_eq=[dict(band, filter='arbitrary')]), dict(args, peaking_eq=[{'frequency_hz': 300}]),
               dict(args, peaking_eq=[dict(band, gain_db=True)]), dict(args, peaking_eq=[dict(band, q=float('nan'))]),
               dict(args, compressor={'ratio': 2}), dict(args, capture_end_seconds=.15),
               dict(args, capture_end_seconds=11), dict(args, reduction_db=10 ** 1000),
               dict(args, gain_smooth=.5), dict(args, timeout_seconds=61), dict(args, input='../source.wav'),
               dict(args, review='https://example.invalid/review.json'), dict(args, model='noise-model'),
               dict(args, filter='afftdn'), dict(args, profile_authorized=True)]
        for arguments in bad:
            with self.subTest(arguments=arguments), patch.object(tool_api, 'run_worker') as worker:
                with self.assertRaises(tool_api.ValidationError):
                    tool_api.execute('capture_profile', arguments)
                worker.assert_not_called()
        for schema in ({'type': 'array', 'items': {'type': 'number'}},
                       {'type': 'number', 'maxItems': 3},
                       {'type': 'array', 'items': {'type': 'number'}, 'maxItems': True},
                       {'type': 'array', 'items': {'type': 'number'}, 'maxItems': 129},
                       {'type': 'array', 'items': {'type': 'number'}, 'maxItems': 3, 'contains': {}}):
            with self.assertRaises(ValueError): tool_api.validate_schema(schema)
        schema = tool_api.descriptor('capture_profile')['inputSchema']
        tool_api.validate(dict(args, peaking_eq=[]), schema)
        tool_api.validate(dict(args, peaking_eq=[band]), schema)

    def test_capture_profile_paths_fixed_argv_and_deadline(self):
        source, run, review_path, review, args = self.capture_profile_fixture()
        args['peaking_eq'] = [{'frequency_hz': 300, 'gain_db': -1.5, 'q': .8}]
        args['compressor'] = {'threshold_db': -18, 'ratio': 2, 'attack_ms': 15, 'release_ms': 100, 'knee_db': 3}
        command = tool_api.worker_command('capture_profile', args)
        self.assertEqual(command[1:7], [str(ROOT / 'scripts/capture_profile.py'), str(source),
            '--run-dir', str(run), '--review', str(review_path)])
        self.assertEqual(command[command.index('--eq'):command.index('--eq') + 4], ['--eq', '300', '-1.5', '0.8'])
        self.assertEqual(command[command.index('--timeout-seconds') + 1], '60')
        self.assertEqual(command[command.index('--compressor-threshold-db') + 1], '-18')
        with patch.object(tool_api, 'run_worker', return_value={'status': 'fixture'}) as worker:
            tool_api.execute('capture_profile', args)
            self.assertEqual(worker.call_args.args[1], 60)
            self.assertEqual(worker.call_args.kwargs, {'error_json_tool': 'capture_profile'})
        other = source.parent / 'outside-review.json'; other.write_bytes(review_path.read_bytes())
        with self.assertRaisesRegex(tool_api.ToolError, 'beneath'):
            tool_api.worker_command('capture_profile', dict(args, review=str(other)))
        alias = run / 'alias.json'; alias.symlink_to(review_path)
        with self.assertRaisesRegex(tool_api.ToolError, 'symlink'):
            tool_api.worker_command('capture_profile', dict(args, review=str(alias)))
        oversized = run / 'oversized.json'; oversized.write_bytes(b'x' * (16384 + 1))
        with self.assertRaisesRegex(tool_api.ToolError, 'byte bound'):
            tool_api.worker_command('capture_profile', dict(args, review=str(oversized)))

    def test_real_capture_profile_mcp_statuses_preserve_scope_and_native_source(self):
        from test_mcp import exchange, initialization, request
        source, run, review_path, review, args = self.capture_profile_fixture()
        args['peaking_eq'] = [{'frequency_hz': 300, 'gain_db': -1.5, 'q': .8}]
        args['compressor'] = {'threshold_db': -18, 'ratio': 2, 'attack_ms': 15, 'release_ms': 100, 'knee_db': 3}
        before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in (source, run / 'source.wav', run / 'manifest.json')}
        def invoke():
            replies, stderr = exchange([initialization(), {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
                request(2, 'tools/call', {'name': 'capture_profile', 'arguments': args})], timeout=10)
            self.assertEqual(stderr, '')
            self.assertFalse(replies[1]['result']['isError'], replies[1])
            return replies[1]['result']['structuredContent']['result']
        with patch.dict(os.environ, {'FFMPEG': '/nonexistent/ffmpeg', 'FFPROBE': '/nonexistent/ffprobe'}):
            first = invoke()
            self.assertEqual(first['status'], 'authored_unrendered')
            self.assertFalse(first['dsp_performed']); self.assertFalse(first['listening_accepted'])
            self.assertEqual(first['capture']['native_samples'], [2000, 10000])
            self.assertEqual(first['capture']['source_media_span_seconds'], [7.25, 7.75])
            profile = json.loads(Path(first['profile_path']).read_text())
            self.assertTrue(profile['noise_capture_authorized'])
            self.assertEqual(profile['noise_capture_source_sha256'], before[source])
            self.assertEqual(profile['peaking_eq'], args['peaking_eq'])
            self.assertEqual(profile['compressor'], args['compressor'])
            receipt = json.loads(Path(first['receipt_path']).read_text())
            self.assertFalse(receipt['review']['identity_authenticated'])
            self.assertFalse(receipt['learned_band_shape']); self.assertFalse(receipt['audio_decoded'])
            review['authorization_scope'] = 'profile_authoring'; review_path.write_text(json.dumps(review))
            draft = invoke(); self.assertEqual(draft['status'], 'draft_authorization_incomplete')
            self.assertIsNone(draft['profile_path']); self.assertIsNone(draft['profile_sha256'])
            self.assertFalse(json.loads(Path(draft['proposal_path']).read_text())['noise_capture_authorized'])
            review['music_status'] = 'reviewed_present'; review_path.write_text(json.dumps(review))
            rejected = invoke(); self.assertEqual(rejected['status'], 'needs_reselection')
            self.assertIsNone(rejected['profile_path']); self.assertIsNone(rejected['proposal_path'])
        self.assertEqual(len({first['output_dir'], draft['output_dir'], rejected['output_dir']}), 3)
        self.assertEqual(hashlib.sha256(Path(first['profile_path']).read_bytes()).hexdigest(), first['profile_sha256'])
        for path, digest in before.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
        self.assertEqual(list(run.rglob('*.wav')), [run / 'source.wav'])

    def test_real_capture_profile_mcp_bad_review_and_hash_errors_retain_diagnostics(self):
        from test_mcp import exchange, initialization, request
        source, run, review_path, review, args = self.capture_profile_fixture()
        def invoke():
            replies, stderr = exchange([initialization(), {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
                request(2, 'tools/call', {'name': 'capture_profile', 'arguments': args})], timeout=10)
            self.assertEqual(stderr, '')
            result = replies[1]['result']; self.assertTrue(result['isError'])
            error_text = json.loads(result['content'][0]['text'])['error']
            self.assertIn('"dsp_performed": false', error_text)
            return error_text
        review_path.write_text('{bad json')
        self.assertIn('valid bounded JSON', invoke())
        review['authorization_scope'] = 'invented_unscoped'; review_path.write_text(json.dumps(review))
        self.assertIn('authorization_scope', invoke())
        review['authorization_scope'] = 'experimental_capture_render'; review['source_sha256'] = 'a' * 64
        review_path.write_text(json.dumps(review)); self.assertIn('source_sha256', invoke())
        review['source_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
        review_path.write_text(json.dumps(review))
        with source.open('ab') as handle: handle.write(b'changed original')
        self.assertIn('does not bind this original source and PCM', invoke())
        self.assertFalse((run / 'capture-profiles').exists())

    def test_capture_profile_skill_prompt_exact_readback(self):
        from test_mcp import exchange, initialization, request
        replies, stderr = exchange([initialization(), {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
            request(2, 'prompts/get', {'name': 'guitar-capture-profile'})])
        self.assertEqual(stderr, '')
        self.assertEqual(replies[1]['result']['messages'][0]['content']['text'],
                         (ROOT / '.agents/skills/guitar-capture-profile/SKILL.md').read_text())

    def test_real_capture_profile_decimal_minimum_interval_retains_native_bounds(self):
        import media
        from test_mcp import exchange, initialization, request
        source, run, review_path, review, args = self.capture_profile_fixture()
        args.update(capture_start_seconds=.2, capture_end_seconds=.3, reduction_db=.01)
        review.update(start_seconds=.2, end_seconds=.3)
        review_path.write_text(json.dumps(review))
        replies, stderr = exchange([initialization(), {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
            request(2, 'tools/call', {'name': 'capture_profile', 'arguments': args})], timeout=10)
        self.assertEqual(stderr, '')
        self.assertFalse(replies[1]['result']['isError'], replies[1])
        result = replies[1]['result']['structuredContent']['result']
        self.assertEqual(result['status'], 'authored_unrendered')
        self.assertEqual(result['capture']['native_samples'], [3200, 4800])
        profile = media.load_profile(result['profile_path'])
        self.assertEqual(profile['reduction_db'], .01)
        self.assertEqual([round(value * 16000) for value in profile['noise_capture_seconds']], [3200, 4800])
        self.assertFalse(result['dsp_performed'])

    def basic_pitch_fixture(self, run):
        import math, struct, wave
        run.mkdir(parents=True)
        source = run / 'denoised.wav'
        rate = 44100; count = rate * 2
        with wave.open(str(source), 'wb') as audio:
            audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(rate)
            audio.writeframes(b''.join(struct.pack('<h', round(8000 * math.sin(2 * math.pi * 440 * index / rate)))
                                       for index in range(count)))
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        manifest = {'source': {'sha256': digest}, 'output_sha256': {'denoised.wav': digest},
                    'timeline': {'no_time_stretch': True, 'audio_start_seconds': 3.},
                    'pcm': {'sample_rate': rate, 'channels': 1, 'sample_count': count}}
        (run / 'manifest.json').write_text(json.dumps(manifest))
        return source

    def test_basic_pitch_schema_rejects_unqualified_knobs_and_resource_requests(self):
        valid = {'run_dir': 'artifacts/runs/existing'}
        bad = [dict(valid, max_analysis_seconds=value) for value in (0, 31, True, float('inf'))]
        bad += [dict(valid, onset_threshold=.01), dict(valid, frame_threshold=.96),
                dict(valid, start_seconds=-1), dict(valid, start_seconds=float('nan')),
                dict(valid, timeout_seconds=901), dict(valid, run_dir='../existing'),
                dict(valid, model_id='other'), dict(valid, model_path='evil.onnx'),
                dict(valid, runtime_python='/bin/python'), dict(valid, decoder={'melodia': True}),
                dict(valid, minimum_note_length_ms=1), dict(valid, install_runtime=True)]
        for arguments in bad:
            with self.subTest(arguments=arguments), patch.object(tool_api, 'run_worker') as worker:
                with self.assertRaises(tool_api.ValidationError):
                    tool_api.execute('basic_pitch_compare', arguments)
                worker.assert_not_called()

    def test_basic_pitch_dispatch_preserves_fixed_runtime_and_artifact_byte_bounds(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(); run = root / 'artifacts/runs/test'
            run.mkdir(parents=True)
            (run / 'manifest.json').write_text('{}'); (run / 'denoised.wav').write_bytes(b'fixture')
            with patch.object(tool_api, 'ROOT', root), patch.dict(os.environ, {'VIDEO_UTILS_ANALYSIS_PYTHON': '/unqualified/analysis'}):
                args = {'run_dir': str(run), 'max_analysis_seconds': 2, 'start_seconds': .25,
                        'onset_threshold': .6, 'frame_threshold': .4}
                command = tool_api.worker_command('basic_pitch_compare', args)
                self.assertNotEqual(command[0], '/unqualified/analysis')
                self.assertEqual(command[1:], [str(root / 'scripts/basic_pitch_compare.py'), str(run),
                    '--max-analysis-seconds', '2', '--onset-threshold', '0.6', '--frame-threshold', '0.4',
                    '--start-seconds', '0.25'])
                self.assertNotIn('--runtime-python', command)
                with patch.object(tool_api, 'run_worker', return_value={'status': 'fixture'}) as worker:
                    tool_api.execute('basic_pitch_compare', args)
                    self.assertEqual(worker.call_args.args[1], 600)
                for name, ceiling in (('manifest.json', 1048576), ('denoised.wav', 1073741824)):
                    path = run / name; before = path.read_bytes()
                    with path.open('wb') as handle: handle.truncate(ceiling + 1)
                    with self.assertRaisesRegex(tool_api.ToolError, 'byte bound'):
                        tool_api.basic_pitch_directory(str(run))
                    path.write_bytes(before)
                target = run / 'real.wav'; (run / 'denoised.wav').rename(target)
                (run / 'denoised.wav').symlink_to(target)
                with self.assertRaisesRegex(tool_api.ToolError, 'non-symlink'):
                    tool_api.basic_pitch_directory(str(run))
                alias = run.parent / 'alias'; alias.symlink_to(run, target_is_directory=True)
                with self.assertRaises(tool_api.ToolError):
                    tool_api.basic_pitch_directory(str(alias))

    def test_basic_pitch_absent_or_changed_qualification_fails_before_decode(self):
        import basic_pitch_compare as comparator
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(); run = root / 'artifacts/runs/test'
            self.basic_pitch_fixture(run)
            (root / 'program').mkdir()
            shutil.copyfile(ROOT / 'program/models.json', root / 'program/models.json')
            model = root / 'wrong.onnx'; model.write_bytes(b'wrong model bytes')
            with patch.object(comparator, 'ROOT', root), patch.object(comparator, 'LOCAL_MODEL', model), \
                    patch.object(comparator.subprocess, 'run') as decoder:
                with self.assertRaisesRegex(ValueError, 'prequalified model'):
                    comparator.build(run, comparator.settings(2))
                decoder.assert_not_called()
                model.unlink()
                with self.assertRaisesRegex(ValueError, 'Qualified Basic Pitch model missing'):
                    comparator.build(run, comparator.settings(2))
                decoder.assert_not_called()
            absent = root / 'absent-runtime'
            # A deliberately mocked model preflight isolates launcher rejection;
            # this fixture is not qualified weights and requires no download.
            model.write_bytes(b'\0' * 230444)
            original_sha = comparator.sha256
            def fixture_sha(path):
                return comparator.MODEL_HASH if Path(path) == model else original_sha(path)
            with patch.object(comparator, 'ROOT', root), patch.object(comparator, 'LOCAL_MODEL', model), \
                    patch.object(comparator, 'RUNTIME', absent), patch.object(comparator, 'sha256', side_effect=fixture_sha), \
                    patch.object(comparator.subprocess, 'run') as decoder:
                with self.assertRaisesRegex(ValueError, 'qualified isolated venv launcher'):
                    comparator.build(run, comparator.settings(2), runtime_python=absent)
                decoder.assert_not_called()
            self.assertFalse((run / 'learned-pitch').exists())

    def test_basic_pitch_runtime_gate_reports_missing_offline_artifacts_without_acquisition(self):
        import basic_pitch_compare as comparator
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            paths = {'LOCAL_MODEL': root / 'missing.onnx', 'RUNTIME': root / 'missing-python',
                     'WHEEL_MANIFEST': root / 'missing-runtime.json'}
            with patch.object(comparator, 'ROOT', root), patch.multiple(comparator, **paths), \
                    patch.object(comparator.subprocess, 'run') as process:
                self.assertEqual(basic_pitch_missing_test_artifacts(),
                                 ['local model', 'isolated runtime', 'runtime wheel manifest'])
                for path in paths.values():
                    path.write_bytes(b'intentionally unqualified fixture')
                # Availability does not bless bad bytes: the real worker remains
                # responsible for rejecting present corrupted artifacts.
                self.assertEqual(basic_pitch_missing_test_artifacts(), [])
                process.assert_not_called()

    def test_real_basic_pitch_mcp_qualified_two_second_comparison_and_stale_input(self):
        missing = basic_pitch_missing_test_artifacts()
        if missing:
            self.skipTest('Optional qualified Basic Pitch inference unavailable: ' + ', '.join(missing)
                          + '; no model/runtime acquisition in tests')
        from test_mcp import exchange, initialization, request
        root = ROOT / 'artifacts/runs' / ('contract-basic-pitch-' + uuid.uuid4().hex)
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        run = root / 'run'; source = self.basic_pitch_fixture(run)
        before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in (source, run / 'manifest.json')}
        def invoke(arguments):
            replies, stderr = exchange([initialization(), {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
                request(2, 'tools/call', {'name': 'basic_pitch_compare', 'arguments': arguments})], timeout=120)
            self.assertEqual(stderr, '')
            return replies[1]['result']
        args = {'run_dir': str(run), 'max_analysis_seconds': 2, 'timeout_seconds': 90}
        reply = invoke(args)
        self.assertFalse(reply['isError'], reply)
        summary = reply['structuredContent']['result']
        self.assertEqual(summary['status'], 'experimental_official_model_project_decoder')
        self.assertEqual(summary['coverage_seconds'], 2.)
        self.assertEqual(summary['model_windows'], 2)
        self.assertEqual(summary['performance_grade'], 'not_graded')
        path = Path(summary['comparison_json'])
        self.assertTrue(path.is_relative_to(run / 'learned-pitch'))
        result = json.loads(path.read_text())
        self.assertEqual(result['providers'], ['CPUExecutionProvider'])
        self.assertFalse(result['upstream_decoder_parity'])
        self.assertEqual(result['analysis_input_sha256'], before[source])
        self.assertEqual(result['model_sha256'], '2c3c1d144bfa61ad236e92e169c13535c880469a12a047d4e73451f2c059a0ec')
        self.assertLessEqual(result['peak_rss_bytes'], 1024 ** 3)
        self.assertLessEqual(result['raw_array_bytes'], 20 * 1024 ** 2)
        self.assertEqual(set(summary['event_counts_by_minimum_ms']), {'127.7', '25.0'})
        for excerpt in result['excerpts']:
            for variant in excerpt['variants']:
                for event in variant['events']:
                    self.assertIsNone(event['identified_string'])
                    self.assertIsNone(event['intended_note'])
                    self.assertIsNone(event['performance_issue'])
                    self.assertEqual(event['confidence_kind'], 'uncalibrated_model_activation')
        for original, digest in before.items():
            self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(), digest)
        self.assertTrue(invoke(dict(args, start_seconds=2))['isError'])
        with source.open('ab') as handle: handle.write(b'changed source')
        stale = invoke(args)
        self.assertTrue(stale['isError'])
        self.assertIn('verified denoised derivative', stale['content'][0]['text'])

    def test_basic_pitch_skill_prompt_exact_readback(self):
        from test_mcp import exchange, initialization, request
        replies, stderr = exchange([initialization(), {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
            request(2, 'prompts/get', {'name': 'guitar-basic-pitch'})])
        self.assertEqual(stderr, '')
        self.assertEqual(replies[1]['result']['messages'][0]['content']['text'],
                         (ROOT / '.agents/skills/guitar-basic-pitch/SKILL.md').read_text())

    def test_captured_profile_enum_is_denoise_only_and_literal(self):
        captured = ('captured8', 'captured12', 'captured8-clarity')
        denoise = tool_api.descriptor('denoise')['inputSchema']
        benchmark = tool_api.descriptor('benchmark')['inputSchema']
        self.assertEqual(benchmark['properties']['profile']['enum'], ['bypass', 'conservative3', 'mild6'])
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'different $(literal); recording.wav'; source.write_bytes(b'not the captured source')
            for name in captured:
                arguments = {'input': str(source), 'profile': name}
                tool_api.validate(arguments, denoise)
                self.assertEqual(tool_api.worker_command('denoise', arguments)[1:],
                    [str(ROOT / 'scripts/media.py'), 'clean', str(source.resolve()), name])
                with patch.object(tool_api, 'run_worker') as worker:
                    with self.assertRaises(tool_api.ValidationError):
                        tool_api.execute('benchmark', {'output': 'artifacts/benchmarks/new', 'profile': name})
                    worker.assert_not_called()
            with patch.object(tool_api, 'run_worker') as worker:
                with self.assertRaises(tool_api.ValidationError):
                    tool_api.execute('denoise', {'input': str(source), 'profile': 'captured8', 'peaking_eq': []})
                worker.assert_not_called()

    def test_real_captured_profile_wrong_source_rejects_before_media_or_run_creation(self):
        from test_mcp import exchange, initialization, request
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'different recording.wav'
            source.write_bytes(b'Wrong source; deliberately not decodable audio')
            original = hashlib.sha256(source.read_bytes()).hexdigest()
            import media
            with patch.object(media, 'ROOT', Path(temporary)), patch.object(media, 'probe') as probe:
                for profile in ('captured8', 'captured12', 'captured8-clarity'):
                    with self.assertRaisesRegex(media.MediaError, 'noise capture source SHA-256 differs'):
                        media.clean(source, ROOT / 'profiles' / (profile + '.json'))
                probe.assert_not_called()
                self.assertFalse((Path(temporary) / 'artifacts').exists())
            messages = [initialization(), {'jsonrpc': '2.0', 'method': 'notifications/initialized'}]
            for index, profile in enumerate(('captured8', 'captured12', 'captured8-clarity'), 2):
                messages.append(request(index, 'tools/call', {'name': 'denoise', 'arguments': {
                    'input': str(source), 'profile': profile, 'timeout_seconds': 5}}))
            with patch.dict(os.environ, {'FFMPEG': '/nonexistent/ffmpeg', 'FFPROBE': '/nonexistent/ffprobe'}):
                replies, stderr = exchange(messages, timeout=15)
            self.assertEqual(stderr, '')
            for reply in replies[1:]:
                self.assertTrue(reply['result']['isError'])
                self.assertIn('noise capture source SHA-256 differs from this recording', reply['result']['content'][0]['text'])
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), original)

    def test_marked_video_paths_fixed_dispatch_and_default_deadline(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            runs = root / 'artifacts/runs'; runs.mkdir(parents=True)
            run = runs / 'existing $(literal); run'; run.mkdir()
            with patch.object(tool_api, 'ROOT', root):
                output = runs / 'new preview'
                args = {'run_dir': str(run), 'output': str(output)}
                command = tool_api.worker_command('marked_video', args)
                self.assertEqual(command[1:], [str(root / 'scripts/marked_video.py'),
                    '--run-dir', str(run), '--selection', 'phrase-review', '--output', str(output)])
                self.assertEqual(tool_api.marked_video_directory('artifacts/runs/' + run.name), str(run))
                with patch.object(tool_api, 'run_worker', return_value={'status': 'fixture'}) as worker:
                    tool_api.execute('marked_video', args)
                    self.assertEqual(worker.call_args.args[1], 600)
                alias = runs / 'alias'; alias.symlink_to(run, target_is_directory=True)
                for value in (str(alias), str(runs), str(root / 'outside'), str(run / '..' / 'other')):
                    with self.subTest(value=value), self.assertRaises((tool_api.ToolError, tool_api.ValidationError)):
                        tool_api.marked_video_directory(value)
                with self.assertRaises(tool_api.ToolError):
                    tool_api.marked_video_directory(str(run), output=True)
                file = runs / 'file'; file.write_text('regular')
                with self.assertRaises(tool_api.ToolError):
                    tool_api.marked_video_directory(str(file / 'new'), output=True)
                moved = root / 'moved-runs'; runs.rename(moved); runs.symlink_to(moved, target_is_directory=True)
                with self.assertRaises(tool_api.ToolError):
                    tool_api.marked_video_directory('artifacts/runs/' + run.name)

    def test_marked_video_schema_rejects_unknown_and_unsafe_knobs(self):
        valid = {'run_dir': 'artifacts/runs/existing', 'output': 'artifacts/runs/new'}
        cases = [dict(valid, selection='confirmed-errors'), dict(valid, output='../new'),
                 dict(valid, run_dir='artifacts\\runs\\old'), dict(valid, timeout_seconds=True),
                 dict(valid, timeout_seconds=901), dict(valid, timeout_seconds=float('nan')),
                 dict(valid, input='take.mov'), dict(valid, title='MISTAKE'), dict(valid, install_font=True),
                 dict(valid, output='x' * 4097), {'run_dir': valid['run_dir']}]
        for args in cases:
            with self.subTest(arguments=args), patch.object(tool_api, 'run_worker') as worker:
                with self.assertRaises(tool_api.ValidationError):
                    tool_api.execute('marked_video', args)
                worker.assert_not_called()

    def test_real_marked_video_mcp_preserves_vfr_audio_and_rejects_stale_evidence(self):
        from test_marked_video import create_verified_fixture
        from test_mcp import exchange, initialization, request
        ffmpeg = os.environ.get('FFMPEG') or shutil.which('ffmpeg')
        ffprobe = os.environ.get('FFPROBE') or shutil.which('ffprobe')
        if not ffmpeg or not ffprobe:
            self.skipTest('Explicit FFmpeg/FFprobe required for real preview proof')
        root = ROOT / 'artifacts/runs' / ('contract-marked-' + uuid.uuid4().hex)
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        run = root / 'run'
        create_verified_fixture(run, ffmpeg, ffprobe, origin=2., vfr=True)
        before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in run.rglob('*') if path.is_file()}
        output = root / 'preview'
        def invoke(destination):
            replies, stderr = exchange([initialization(), {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
                request(2, 'tools/call', {'name': 'marked_video', 'arguments': {
                    'run_dir': str(run), 'output': str(destination), 'timeout_seconds': 60}})], timeout=90)
            self.assertEqual(stderr, '')
            return replies[1]['result']
        reply = invoke(output)
        self.assertFalse(reply['isError'])
        result = reply['structuredContent']['result']
        self.assertEqual(result['status'], 'marked_review_preview_verified_unreviewed')
        self.assertFalse(result['listening_accepted'])
        self.assertEqual(result['selected_marker_count'], 1)
        receipt = json.loads(Path(result['outcome_json']).read_text())
        for key in ('decoded_video_frame_pts_preserved', 'aac_packet_payloads_timing_and_padding_preserved',
                    'decoded_audio_pcm_sha256_preserved', 'decoded_video_variable_frame_intervals_observed'):
            self.assertTrue(receipt['verification'][key])
        self.assertEqual(receipt['verification']['decoded_video_frame_count'], 21)
        self.assertTrue(receipt['input_hashes_preserved'])
        for path, digest in before.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
        selection = json.loads(Path(result['selection_json']).read_text())
        self.assertEqual(selection['selected_markers'][0]['source_start_seconds'], 2.25)
        self.assertEqual(selection['selected_markers'][0]['video_start_seconds'], .25)
        self.assertFalse(selection['performance_issue_confirmed'])
        self.assertTrue(invoke(output)['isError'])
        marker_path = run / 'markers.json'; markers = json.loads(marker_path.read_text())
        markers['markers'][0]['source_time_seconds'] = 9
        marker_path.write_text(json.dumps(markers))
        stale = root / 'stale-preview'
        reply = invoke(stale)
        self.assertTrue(reply['isError'])
        self.assertIn('markers differ', reply['content'][0]['text'])
        self.assertFalse(stale.exists())

    def test_marked_video_prompt_exact_readback(self):
        from test_mcp import exchange, initialization, request
        replies, stderr = exchange([initialization(), {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
            request(2, 'prompts/get', {'name': 'guitar-marked-video'})])
        self.assertEqual(stderr, '')
        body = replies[1]['result']['messages'][0]['content']['text']
        self.assertEqual(body, (ROOT / '.agents/skills/guitar-marked-video/SKILL.md').read_text())


    def test_benchmark_suite_schema_and_dispatch_preserve_v1_default(self):
        with tempfile.TemporaryDirectory() as temporary:
            arguments = {'output': str(Path(temporary) / 'new-output'), 'operation': 'fixtures'}
            default = tool_api.worker_command('benchmark', arguments)
            self.assertNotIn('--suite', default)
            schema = tool_api.descriptor('benchmark')['inputSchema']
            self.assertEqual(schema['properties']['suite']['default'], 'technical-v1')
            command = tool_api.worker_command('benchmark', dict(arguments, suite='technical-v2'))
            self.assertEqual(command[-2:], ['--suite', 'technical-v2'])
            with patch.object(tool_api, 'run_worker') as worker:
                with self.assertRaises(tool_api.ValidationError):
                    tool_api.execute('benchmark', dict(arguments, suite='private-recordings'))
                worker.assert_not_called()
                with self.assertRaises(tool_api.ValidationError):
                    tool_api.execute('benchmark', dict(arguments, suite='technical-v2', case='low-C1'))
                worker.assert_not_called()

    def test_real_benchmark_v2_hook_generates_bounded_synthetic_bank(self):
        from test_mcp import exchange, initialization, request
        output = ROOT / 'artifacts' / 'benchmarks' / ('contract-v2-bank-' + uuid.uuid4().hex)
        self.addCleanup(shutil.rmtree, output, ignore_errors=True)
        replies, stderr = exchange([initialization(), {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
            request(2, 'tools/call', {'name': 'benchmark', 'arguments': {
                'operation': 'fixtures', 'suite': 'technical-v2', 'output': str(output),
                'timeout_seconds': 90}})], timeout=120)
        self.assertEqual(stderr, '')
        self.assertFalse(replies[1]['result']['isError'])
        result = replies[1]['result']['structuredContent']['result']
        self.assertEqual(result['status'], 'fixtures_created')
        self.assertEqual(result['case_count'], 12)
        index = json.loads(Path(result['result']).read_text())
        self.assertEqual(index['suite'], 'technical-v2')
        self.assertEqual(index['case_count'], 12)
        self.assertEqual(index['total_duration_seconds'], 120)
        self.assertEqual(len(list(output.rglob('*.wav'))), 48)
        for case in index['cases']:
            self.assertLessEqual(case['duration_seconds'], 12)
            truth_path = output / case['truth']
            self.assertEqual(hashlib.sha256(truth_path.read_bytes()).hexdigest(), case['truth_sha256'])
            truth = json.loads(truth_path.read_text())
            self.assertEqual(truth['ground_truth_scope'], 'generator_only_not_musician')

    def test_calibration_paths_keep_original_components_and_fresh_output(self):
        with patch.object(Path, 'expanduser', side_effect=RuntimeError('unknown local user')):
            with self.assertRaises(tool_api.ToolError):
                tool_api.calibration_path('~unknown/fixture.json')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            bank = root / 'artifacts' / 'benchmarks'; bank.mkdir(parents=True)
            index = bank / 'fixture $(literal);.json'; index.write_text('{}')
            with patch.object(tool_api, 'ROOT', root):
                self.assertEqual(tool_api.calibration_path(str(index), max_bytes=100), str(index))
                self.assertEqual(tool_api.calibration_path(str(bank / 'new'), output=True), str(bank / 'new'))
                for path in (root / 'outside.json', bank / 'missing.json'):
                    with self.subTest(path=path), self.assertRaises(tool_api.ToolError):
                        tool_api.calibration_path(str(path), max_bytes=100)
                with self.assertRaises(tool_api.ToolError):
                    tool_api.calibration_path(str(bank), output=True)
                with self.assertRaises(tool_api.ToolError):
                    tool_api.calibration_path(str(index), output=True)
                with self.assertRaises(tool_api.ToolError):
                    tool_api.calibration_path(str(index), max_bytes=1)
                with self.assertRaises(tool_api.ToolError):
                    tool_api.calibration_path(str(index / 'child.json'), max_bytes=100)
                (bank / 'linked.json').symlink_to(index)
                (bank / 'linked-dir').symlink_to(bank, target_is_directory=True)
                for path in (bank / 'linked.json', bank / 'linked-dir' / index.name):
                    with self.subTest(path=path), self.assertRaises(tool_api.ToolError):
                        tool_api.calibration_path(str(path), max_bytes=100)

    def test_calibration_dispatch_uses_fixed_workers_and_summary(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            bank = root / 'artifacts' / 'benchmarks'; bank.mkdir(parents=True)
            index = bank / 'fixture $(literal);.json'; index.write_text('{}')
            pilot = bank / 'pilot with spaces.json'; pilot.write_text('{}')
            with patch.object(tool_api, 'ROOT', root):
                for name in tool_api.CALIBRATION_TOOLS:
                    output = bank / (name + '-new')
                    arguments = {'fixture_index': str(index), 'pilot_index': str(pilot), 'output': str(output)}
                    command = tool_api.worker_command(name, arguments)
                    self.assertEqual(command[1:], [str(root / ('scripts/' + name + '.py')),
                        '--fixture-index', str(index), '--pilot-index', str(pilot),
                        '--output', str(output), '--summary'])

    def test_evaluator_schema_and_default_deadline_are_enforced(self):
        valid = {'fixture_index': 'artifacts/benchmarks/fixture.json',
                 'pilot_index': 'artifacts/benchmarks/pilot.json', 'output': 'artifacts/benchmarks/new'}
        bad = [dict(valid, timeout_seconds=True), dict(valid, timeout_seconds=901),
               dict(valid, timeout_seconds=float('nan')), dict(valid, fixture_index='../fixture.json'),
               dict(valid, fixture_index='a//fixture.json'), dict(valid, fixture_index='a.partial/fixture.json'),
               dict(valid, fixture_index='a/.hidden/fixture.json'), dict(valid, fixture_index='file:fixture.json'),
               dict(valid, fixture_index='a\\fixture.json'), dict(valid, fixture_index='source.wav'),
               dict(valid, pilot_index=['pilot.json']), dict(valid, output='x' * 4097),
               dict(valid, bpm=178), dict(valid, intended_notes=['C1']), dict(valid, install_model=True)]
        for name in tool_api.CALIBRATION_TOOLS:
            for arguments in bad:
                with self.subTest(tool=name, arguments=arguments), patch.object(tool_api, 'run_worker') as worker:
                    with self.assertRaises(tool_api.ValidationError):
                        tool_api.execute(name, arguments)
                    worker.assert_not_called()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            bank = root / 'artifacts' / 'benchmarks'; bank.mkdir(parents=True)
            index = bank / 'fixture.json'; index.write_text('{}')
            pilot = bank / 'pilot.json'; pilot.write_text('{}')
            with patch.object(tool_api, 'ROOT', root):
                for name in tool_api.CALIBRATION_TOOLS:
                    with patch.object(tool_api, 'run_worker', return_value={'status': 'fixture'}) as worker:
                        tool_api.execute(name, {'fixture_index': str(index), 'pilot_index': str(pilot),
                                                'output': str(bank / name)})
                        self.assertEqual(worker.call_args.args[1], 120)

    def test_real_phrase_evaluator_summary_stale_proof_and_failed_hard_gate(self):
        from test_phrase_evaluate import make_bank, write
        from test_mcp import exchange, initialization, request
        root = ROOT / 'artifacts' / 'benchmarks' / ('contract-phrase-evaluate-' + uuid.uuid4().hex)
        root.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, root)
        index, pilot = make_bank(root)
        registry_hash = hashlib.sha256((ROOT / 'program/instrument.json').read_bytes()).hexdigest()
        bank = json.loads(index.read_text()); bank['instrument_registry_sha256'] = registry_hash
        for case in bank['cases']:
            truth_path = index.parent / case['truth']
            truth = json.loads(truth_path.read_text()); truth['instrument_registry_sha256'] = registry_hash
            case['truth_sha256'] = write(truth_path, truth)
        write(index, bank)
        jobs = json.loads(pilot.read_text())
        jobs['instrument_registry_sha256'] = registry_hash
        jobs['bank_index_sha256'] = hashlib.sha256(index.read_bytes()).hexdigest()
        write(pilot, jobs)
        arguments = {'fixture_index': str(index), 'pilot_index': str(pilot), 'output': str(root / 'new-result')}
        conversation = [initialization(), {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
            request(2, 'tools/call', {'name': 'phrase_evaluate', 'arguments': arguments})]
        before = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
                  for path in root.rglob('*') if path.is_file()}
        replies, stderr = exchange(conversation)
        self.assertEqual(stderr, '')
        self.assertFalse(replies[1]['result']['isError'])
        result = replies[1]['result']['structuredContent']['result']
        self.assertEqual(result['fixture_count'], 1)
        self.assertEqual(result['unsupported_confirmed_claim_count'], 0)
        self.assertTrue(result['hard_gates_passed'])
        self.assertTrue(result['source_read'])
        self.assertFalse(result['source_audio_decoded'])
        self.assertFalse(result['inference_invoked'])
        self.assertEqual(result['ground_truth_scope'], 'generator_only_not_musician')
        self.assertFalse(result['listening_acceptance'])
        self.assertNotIn('fixtures', result, 'full calibration rows must stay in local artifact')
        evidence = json.loads(Path(result['evaluation_json']).read_text())
        self.assertEqual(evidence['fixtures'][0]['boundary_metrics'][0]['f1'], 0)
        self.assertEqual(evidence['fixtures'][0]['boundary_metrics'][1]['f1'], 1)
        for relative, digest in before.items():
            self.assertEqual(hashlib.sha256((root / relative).read_bytes()).hexdigest(), digest)
        artifact = pilot.parent / 'run' / 'analysis.json'
        payload = json.loads(artifact.read_text()); payload['contract_test_changed'] = True
        write(artifact, payload)
        arguments['output'] = str(root / 'stale-result')
        replies, _ = exchange(conversation)
        self.assertTrue(replies[1]['result']['isError'])
        self.assertIn('hash mismatch', replies[1]['result']['content'][0]['text'])
        self.assertTrue(Path(result['evaluation_json']).is_file())
        jobs['cases'][0]['analysis']['sha256'] = hashlib.sha256(artifact.read_bytes()).hexdigest()
        phrases_path = pilot.parent / 'run' / 'phrases.json'
        phrases = json.loads(phrases_path.read_text()); phrases['performance_issue_confirmed'] = True
        write(phrases_path, phrases)
        jobs['cases'][0]['phrases']['sha256'] = hashlib.sha256(phrases_path.read_bytes()).hexdigest()
        write(pilot, jobs)
        arguments['output'] = str(root / 'unsupported-claim-result')
        replies, _ = exchange(conversation)
        self.assertTrue(replies[1]['result']['isError'])
        failed = json.loads((root / 'unsupported-claim-result' / 'phrase-evaluation.json').read_text())
        self.assertFalse(failed['hard_gates_passed'])
        self.assertEqual(failed['unsupported_confirmed_claim_count'], 1)
        self.assertEqual(failed['status'], 'generated_fixture_calibration_failed_hard_gates')

    def test_real_pitch_evaluator_summary_keeps_abstentions_and_structural_failure(self):
        from test_pitch_evaluate import create_valid_fixture
        from test_mcp import exchange, initialization, request
        root = ROOT / 'artifacts' / 'benchmarks' / ('contract-pitch-evaluate-' + uuid.uuid4().hex)
        root.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, root)
        index, pilot = create_valid_fixture(root / 'bank')
        before = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
                  for path in root.rglob('*') if path.is_file()}
        arguments = {'fixture_index': str(index), 'pilot_index': str(pilot), 'output': str(root / 'new-result')}
        conversation = [initialization(), {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
            request(2, 'tools/call', {'name': 'pitch_evaluate', 'arguments': arguments})]
        replies, stderr = exchange(conversation)
        self.assertEqual(stderr, '')
        self.assertFalse(replies[1]['result']['isError'])
        result = replies[1]['result']['structuredContent']['result']
        self.assertEqual(result['case_count'], 4)
        self.assertEqual(result['pilot_coverage_seconds'], 30)
        self.assertEqual(result['hard_failure_count'], 0)
        self.assertEqual(result['frame_count'], 3750)
        self.assertTrue(result['hard_gates_passed'])
        self.assertTrue(result['source_audio_bytes_read'])
        self.assertFalse(result['source_audio_decoded'])
        self.assertFalse(result['inference_invoked'])
        self.assertEqual(result['ground_truth_scope'], 'generator_only_not_musician')
        self.assertFalse(result['listening_accepted'])
        self.assertFalse(result['real_performance_grading'])
        self.assertTrue(result['quality_alerts'], 'all-abstaining oracle metadata must not become a quality pass')
        self.assertNotIn('cases', result, 'full case/frame evidence must stay local')
        self.assertLess(len(json.dumps(result)), 20_000)
        evidence = json.loads(Path(result['evaluation_json']).read_text())
        self.assertEqual(evidence['case_count'], 4)
        for branch in evidence['aggregate_branches']:
            self.assertEqual(branch['counts']['covered_frames'], branch['counts']['abstained_frames'])
            cents = branch['stable_monophonic_metrics']['cents_error']
            self.assertEqual(cents['n'], 0)
            self.assertIsNone(cents['median_absolute'])
        self.assertTrue(Path(result['frame_errors_csv']).is_file())
        for relative, digest in before.items():
            self.assertEqual(hashlib.sha256((root / relative).read_bytes()).hexdigest(), digest)
        jobs = json.loads(pilot.read_text())
        pitch_path = Path(jobs['jobs'][0]['pitch_path'])
        payload = json.loads(pitch_path.read_text()); payload['contract_test_changed'] = True
        pitch_path.write_text(json.dumps(payload))
        arguments['output'] = str(root / 'stale-result')
        replies, _ = exchange(conversation)
        self.assertTrue(replies[1]['result']['isError'])
        self.assertIn('retained', replies[1]['result']['content'][0]['text'])
        failed = json.loads((root / 'stale-result' / 'pitch-calibration.json').read_text())
        self.assertEqual(failed['status'], 'failed_structural')
        self.assertEqual(failed['hard_failure_count'], 1)
        self.assertFalse(failed['real_performance_grading'])
        self.assertTrue(Path(result['evaluation_json']).is_file())

    def test_corpus_schema_errors_do_not_launch(self):
        for arguments in ({}, {'manifest': True}, {'manifest': 'x', 'local_root': []},
                          {'manifest': 'x', 'operation': 'train'}, {'manifest': 'x', 'decode_audio': True},
                          {'manifest': '../corpus.json'}, {'manifest': 'a/../corpus.json'},
                          {'manifest': 'x' * 4097}, {'manifest': 'x', 'timeout_seconds': 901}):
            with self.subTest(arguments=arguments), patch.object(tool_api, 'run_worker') as worker:
                with self.assertRaises(tool_api.ValidationError):
                    tool_api.execute('corpus', arguments)
                worker.assert_not_called()

    def test_corpus_dispatch_is_read_only_summary_and_literal_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            manifest = root / 'corpus $(literal); data.json'; manifest.write_text('{}')
            command = tool_api.worker_command('corpus', {'manifest': str(manifest), 'local_root': str(root)})
            self.assertEqual(command[1:], [str(ROOT / 'scripts/corpus.py'), 'validate', str(manifest),
                                           '--root', str(root), '--summary'])
            self.assertNotIn('--audio', command)

    def test_corpus_unsafe_or_missing_manifest_never_launches(self):
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as outside:
            root = Path(temporary).resolve()
            other = Path(outside).resolve()
            external = other / 'corpus.json'; external.write_text('{}')
            (root / 'linked.json').symlink_to(external)
            (root / 'linked-dir').symlink_to(other, target_is_directory=True)
            linked_root = other / 'linked-root'; linked_root.symlink_to(root, target_is_directory=True)
            (root / 'folder.json').mkdir()
            cases = [{'manifest': str(root / name), 'local_root': str(root)}
                     for name in ('missing.json', 'linked.json', 'linked-dir/corpus.json', 'folder.json')]
            cases += [{'manifest': str(external), 'local_root': str(root)},
                      {'manifest': str(linked_root / 'corpus.json'), 'local_root': str(linked_root)}]
            for arguments in cases:
                with self.subTest(arguments=arguments), patch.object(tool_api, 'run_worker') as worker:
                    with self.assertRaises(tool_api.ToolError):
                        tool_api.execute('corpus', arguments)
                    worker.assert_not_called()

    def test_real_corpus_hook_summary_stale_receipts_and_unsafe_metadata(self):
        from test_corpus import CorpusTests
        from test_mcp import exchange, initialization, request
        fixture = CorpusTests('test_sparse_ambiguous_nonzero_timeline_never_establishes_ground_truth')
        fixture.setUp(); self.addCleanup(fixture.doCleanups)
        fixture.write('corpus.json', fixture.data)
        arguments = {'manifest': str(fixture.root / 'corpus.json'), 'local_root': str(fixture.root)}
        conversation = [initialization(), {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
            request(2, 'tools/call', {'name': 'corpus', 'arguments': arguments})]
        before = {str(path.relative_to(fixture.root)): path.read_bytes()
                  for path in fixture.root.rglob('*') if path.is_file()}
        replies, stderr = exchange(conversation)
        self.assertEqual(stderr, '')
        self.assertFalse(replies[1]['result']['isError'])
        envelope = replies[1]['result']['structuredContent']
        result = envelope['result']
        self.assertEqual(result['result_mode'], 'metadata_summary')
        self.assertEqual(result['source_origin_counts'], {'real_recording': 0, 'synthetic_fixture': 1})
        self.assertEqual(result['source_origin_label_counts'], {'real_recording': 0, 'synthetic_fixture': 1})
        self.assertEqual(result['reviewer_count'], 1)
        self.assertEqual(result['source_count'], 1)
        self.assertEqual(result['label_count'], 1)
        self.assertFalse(result['source_audio_read'])
        self.assertFalse(result['ground_truth_established'])
        self.assertEqual(result['unlabelled_intervals'], 'unknown_not_negative')
        self.assertEqual(result['listening_acceptance'], 'not_established')
        self.assertEqual(result['sources'][0]['source_bounds_seconds'], [1, 10])
        self.assertNotIn('selected_labels', result['sources'][0])
        self.assertNotIn('manifest', result['sources'][0])
        self.assertNotIn('reviewers', result)
        self.assertEqual(envelope['evidence_kind'], 'supplied_review_metadata_consistency')
        self.assertEqual(before, {str(path.relative_to(fixture.root)): path.read_bytes()
                                  for path in fixture.root.rglob('*') if path.is_file()})
        fixture.store['revision'] = 2
        fixture.refresh_store(); fixture.write('corpus.json', fixture.data)
        stale_bytes = (fixture.run / 'review-annotations.json').read_bytes()
        replies, _ = exchange(conversation)
        self.assertTrue(replies[1]['result']['isError'])
        self.assertIn('stale_annotation_revision', replies[1]['result']['content'][0]['text'])
        self.assertEqual((fixture.run / 'review-annotations.json').read_bytes(), stale_bytes)
        fixture.entry['manifest']['path'] = '../outside/manifest.json'
        fixture.write('corpus.json', fixture.data)
        replies, _ = exchange(conversation)
        self.assertTrue(replies[1]['result']['isError'])
        self.assertIn('unsafe_metadata_path', replies[1]['result']['content'][0]['text'])

    def test_pipeline_selector_syntax_is_rejected_before_launch(self):
        bad = ['', '/tmp/evidence.json', '../pitch.json', 'a/../pitch.json',
               './pitch.json', 'a//pitch.json', 'a/pitch.json/', 'file:artifact.json',
               'a\\pitch.json', '.hidden/pitch.json', 'a.partial/pitch.json',
               'a/pitch.partial.json', 'pitch.wav', 'x' * 1025, True, ['pitch.json']]
        for field in tool_api.PIPELINE_SELECTORS:
            for value in bad:
                with self.subTest(field=field, value=value), patch.object(tool_api, 'run_worker') as worker:
                    with self.assertRaises(tool_api.ValidationError):
                        tool_api.execute('pipeline', {'run_dir': '/unopened/run', field: value})
                    worker.assert_not_called()

    def test_pipeline_selector_dispatch_preserves_exact_relative_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve()
            arguments = {'run_dir': str(directory)}
            for field in tool_api.PIPELINE_SELECTORS:
                relative = 'evidence ' + field + '/take $(data);.json'
                path = directory / relative
                path.parent.mkdir()
                path.write_text('{}')
                arguments[field] = relative
            command = tool_api.worker_command('pipeline', arguments)
            self.assertEqual(command[1:3], [str(ROOT / 'scripts/dag.py'), str(directory)])
            expected = [item for field in tool_api.PIPELINE_SELECTORS
                        for item in ('--' + field.replace('_', '-'), arguments[field])]
            self.assertEqual(command[3:], expected)
            self.assertEqual(len(tool_api.descriptors()), 46)

    def test_pipeline_missing_or_symlink_selector_does_not_launch(self):
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as outside:
            directory = Path(temporary)
            external = Path(outside) / 'pitch.json'; external.write_text('{}')
            (directory / 'linked.json').symlink_to(external)
            (directory / 'linked-dir').symlink_to(Path(outside), target_is_directory=True)
            (directory / 'broken.json').symlink_to(Path(outside) / 'absent.json')
            (directory / 'folder.json').mkdir()
            for relative in ('missing.json', 'linked.json', 'linked-dir/pitch.json', 'broken.json', 'folder.json'):
                with self.subTest(relative=relative), patch.object(tool_api, 'run_worker') as worker:
                    with self.assertRaises(tool_api.ToolError):
                        tool_api.execute('pipeline', {'run_dir': temporary, 'pitch_artifact': relative})
                    worker.assert_not_called()

    def test_pipeline_selected_receipts_keep_rejections_nulls_and_sparse_coverage(self):
        result = {'dag_json': 'dag.json', 'flags_json': 'flags.json', 'status': 'automatic_phrase_review_candidates',
                  'selected_evidence': {'pitch': {'status': 'verified', 'selector': 'pitch.json',
                     'metadata': {'coverage_fraction': .13248, 'intended_notes': None}},
                    'tonal': {'status': 'rejected_stale_upstream', 'metadata': {'tonic': None, 'mode': None}}}}
        with tempfile.TemporaryDirectory() as temporary, patch.object(tool_api, 'run_worker', return_value=result):
            (Path(temporary) / 'pitch.json').write_text('{}')
            envelope = tool_api.execute('pipeline', {'run_dir': temporary, 'pitch_artifact': 'pitch.json'})
        self.assertEqual(envelope['result'], result)
        self.assertEqual(envelope['status'], 'completed')
        self.assertNotEqual(envelope['result']['selected_evidence']['tonal']['status'], 'verified')

    def test_pipeline_prompt_exact_readback_and_twenty_seven_tool_catalog(self):
        from test_mcp import exchange, initialization, request
        replies, stderr = exchange([initialization(), {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
            request(2, 'tools/list'), request(3, 'prompts/get', {'name': 'guitar-pipeline'})])
        self.assertEqual(stderr, '')
        self.assertEqual(len(replies[1]['result']['tools']), len(tool_api.descriptors()))
        pipeline = next(tool for tool in replies[1]['result']['tools'] if tool['name'] == 'pipeline')
        self.assertTrue(set(tool_api.PIPELINE_SELECTORS) <= set(pipeline['inputSchema']['properties']))
        self.assertEqual(replies[2]['result']['messages'][0]['content']['text'],
                         (ROOT / '.agents/skills/guitar-pipeline/SKILL.md').read_text())

    def test_real_pipeline_selector_verifies_meter_and_retains_stale_rejection(self):
        from test_meter import MeterTests
        from test_mcp import exchange, initialization, request
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve()
            source, analysis = MeterTests().make_run(temporary)
            source_before = source.read_bytes()
            meter = tool_api.execute('meter', {'run_dir': temporary})['result']
            selected = Path(meter['output']).relative_to(directory).as_posix()
            artifact_before = (directory / selected).read_bytes()
            arguments = {'run_dir': temporary, 'meter_artifact': selected}
            conversation = [initialization(), {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
                request(2, 'tools/call', {'name': 'pipeline', 'arguments': arguments})]
            replies, stderr = exchange(conversation)
            self.assertEqual(stderr, '')
            self.assertFalse(replies[1]['result']['isError'])
            graph = json.loads((directory / 'dag.json').read_text())
            receipt = graph['selected_evidence']['meter']
            self.assertEqual(receipt['status'], 'verified')
            self.assertEqual(receipt['selector'], selected)
            self.assertIsNone(receipt['metadata']['time_signature'])
            self.assertEqual(graph['artifact_hashes'][selected], hashlib.sha256(artifact_before).hexdigest())
            self.assertEqual(graph['selected_evidence']['pitch']['status'], 'not_selected')
            self.assertEqual(receipt['timing_status'], 'dsp_delay_uncalibrated')
            original_graph = (directory / 'dag.json').read_bytes()
            analysis['contract_test_changed'] = True
            (directory / 'analysis.json').write_text(json.dumps(analysis))
            replies, stderr = exchange(conversation)
            self.assertEqual(stderr, '')
            self.assertFalse(replies[1]['result']['isError'])
            graph = json.loads((directory / 'dag.json').read_text())
            self.assertTrue(graph['selected_evidence']['meter']['status'].startswith('rejected_'))
            self.assertEqual((directory / selected).read_bytes(), artifact_before)
            self.assertEqual(source.read_bytes(), source_before)
            self.assertIn(original_graph, [path.read_bytes() for path in directory.rglob('dag.json')])

    def test_schema_errors_never_launch_a_worker(self):
        for descriptor in tool_api.descriptors():
            name = descriptor['name']
            for arguments in [None, [], True, {'shell': 'anything'}, {'timeout_seconds': True}]:
                with self.subTest(tool=name, arguments=arguments), patch.object(tool_api, 'run_worker') as worker:
                    with self.assertRaises(tool_api.ValidationError):
                        tool_api.execute(name, arguments)
                    worker.assert_not_called()


    def test_extreme_integer_number_is_rejected_without_crashing_server(self):
        with patch.object(tool_api, 'run_worker') as worker:
            with self.assertRaises(tool_api.ValidationError):
                tool_api.execute('rhythm', {'input': '/nonexistent.wav', 'run_dir': '/tmp/no-write', 'bpm': 10**400})
            worker.assert_not_called()
        server = mcp_server.Server()
        server.initialized = server.ready = True
        reply = server.handle({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call',
                               'params': {'name': 'rhythm', 'arguments': {
                                   'input': '/nonexistent.wav', 'run_dir': '/tmp/no-write', 'bpm': 10**400}}})
        self.assertEqual(reply['error']['code'], -32602)

    def test_unknown_tools_never_launch_a_worker(self):
        for name in ['not_registered', '../scripts/media.py', 'run_shell', 'download_model']:
            with self.subTest(name=name), patch.object(tool_api, 'run_worker') as worker:
                with self.assertRaises(tool_api.ValidationError):
                    tool_api.execute(name, {})
                worker.assert_not_called()

    def test_nonfinite_or_double_worker_json_is_a_tool_failure(self):
        for output in ['{"confidence": NaN}', '{"offset": Infinity}', '{"offset": -Infinity}', '{"overflow": 1e400}', '{}\n{}']:
            with self.subTest(output=output), tempfile.TemporaryDirectory() as temporary:
                script = Path(temporary) / 'fixture_worker.py'
                script.write_text('import sys\nsys.stdout.write(' + repr(output) + ')\n')
                with self.assertRaises(tool_api.ToolError):
                    tool_api.run_worker([sys.executable, str(script)], 2)


    def test_excessive_json_nesting_is_a_parse_error_not_a_server_crash(self):
        import subprocess
        payload = '[' * 10000 + '0' + ']' * 10000
        with self.assertRaises(ValueError):
            tool_api.strict_json(payload)
        child = subprocess.run([sys.executable, str(ROOT / 'scripts/mcp_server.py')],
                               input=payload + '\n', capture_output=True, text=True, timeout=5)
        self.assertEqual(child.returncode, 0)
        self.assertEqual(json.loads(child.stdout)['error']['code'], -32700)


    def test_json_nesting_limit_is_explicit_and_ignores_quoted_punctuation(self):
        limit = tool_api.MAX_JSON_NESTING
        accepted = '[' * limit + '0' + ']' * limit
        rejected = '[' * (limit + 1) + '0' + ']' * (limit + 1)
        self.assertIsInstance(tool_api.strict_json(accepted), list)
        with self.assertRaisesRegex(ValueError, 'nesting'):
            tool_api.strict_json(rejected)
        value = {'note': '[{' * 10000 + 'quoted \" braces } ] and literal backslash \\',
                 'nested': [{'quoted_key{': 'escaped \" quote and more [{ punctuation'}]}
        self.assertEqual(tool_api.strict_json(json.dumps(value)), value)

    def test_timeout_cleans_only_recorded_descendants_and_returns_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            late_output = directory / 'escaped-worker-output.txt'
            child = directory / 'child.py'
            child.write_text('import time\nfrom pathlib import Path\ntime.sleep(.5)\nPath(' +
                             repr(str(late_output)) + ').write_text("escaped")\n')
            parent = directory / 'parent.py'
            parent.write_text('import subprocess, sys, time\nsubprocess.Popen([sys.executable, ' +
                              repr(str(child)) + '])\ntime.sleep(20)\n')
            with self.assertRaises(tool_api.ToolError) as caught:
                tool_api.run_worker([sys.executable, str(parent)], .15)
            receipt = caught.exception.receipt
            self.assertEqual(receipt['actor'], 'video-utils/tool_api')
            target = receipt['target_ownership']
            self.assertTrue(target['created_by_invocation'])
            self.assertEqual(target['observed_pgid'], target['pid'])
            self.assertEqual(receipt['result']['signal_target'], 'owned_process_group')
            self.assertIn('R-N11', receipt['ruling'])
            time.sleep(.6)
            self.assertFalse(late_output.exists(), 'worker descendant outlived its owned process-group deadline')

    def test_nested_evidence_and_unknowns_survive_the_tool_wrapper(self):
        result = {'source': {'sha256': 'a' * 64, 'kind': 'processed_input'},
                  'lineage': {'original_source_sha256': 'b' * 64, 'status': 'hash_verified'},
                  'timeline': {'audio_start_seconds': 3.25},
                  'interpretation': {'tonic': None, 'mode': None, 'performance_issue': None},
                  'confidence': {'kind': 'heuristic_not_probability', 'score': .42},
                  'flags': [{'source_start_seconds': 4, 'source_end_seconds': 5,
                             'status': 'needs_review', 'performance_issue_confirmed': False}]}
        with tempfile.NamedTemporaryFile() as source, patch.object(tool_api, 'run_worker', return_value=result):
            envelope = tool_api.execute('probe', {'input': source.name})
        self.assertEqual(envelope['result'], result)
        self.assertIsNone(envelope['result']['interpretation']['tonic'])
        self.assertFalse(envelope['result']['flags'][0]['performance_issue_confirmed'])
        self.assertNotEqual(envelope['status'], 'accepted')
        self.assertEqual(json.loads(json.dumps(envelope, allow_nan=False))['result'], result)

    def test_mcp_validation_failure_and_worker_failure_are_distinct(self):
        server = mcp_server.Server()
        server.handle({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                       'params': {'protocolVersion': '2025-11-25', 'capabilities': {},
                                  'clientInfo': {'name': 'contract-test', 'version': '1'}}})
        server.handle({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        invalid = server.handle({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call',
                                 'params': {'name': 'probe', 'arguments': {'input': 3}}})
        self.assertEqual(invalid['error']['code'], -32602)
        failed = server.handle({'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call',
                                'params': {'name': 'probe', 'arguments': {'input': '/nonexistent/private-take.wav'}}})
        self.assertNotIn('error', failed)
        self.assertTrue(failed['result']['isError'])


    def test_extension_knob_errors_do_not_launch_workers(self):
        bad = [
            ('clicks', {'input': 'x', 'run_dir': 'x', 'attenuate': True}),
            ('clicks', {'input': 'x', 'run_dir': 'x', 'template_start': 0}),
            ('clicks', {'input': 'x', 'run_dir': 'x', 'template_start': 0, 'template_end': .5}),
            ('clicks', {'input': 'x', 'run_dir': 'x', 'template_start': 0, 'template_end': .01,
                        'attenuate': True, 'template_click_only': False}),
            ('clicks', {'input': 'x', 'run_dir': 'x', 'strength': .51}),
            ('pitch', {'input': 'x', 'run_dir': 'x', 'max_analysis_seconds': 31}),
            ('pitch', {'input': 'x', 'run_dir': 'x', 'start_seconds': -1}),
            ('pitch', {'input': 'x', 'run_dir': 'x', 'backend': 'install-a-model'}),
            ('meter', {'run_dir': 'x', 'time_signature': '4/4'}),
            ('tonal', {'run_dir': 'x', 'max_regions': 257}),
            ('tonal', {'run_dir': 'x', 'max_recurrences': True}),
            ('tonal', {'run_dir': 'x', 'tonic': 'C'}),
            ('phrase_compare', {'run_dir': 'x', 'band_fraction': 0}),
            ('phrase_compare', {'run_dir': 'x', 'band_fraction': float('inf')}),
            ('phrase_compare', {'run_dir': 'x', 'max_pairs': True}),
            ('benchmark', {'operation': 'fixtures', 'output': 'x', 'profile': 'bypass'}),
            ('benchmark', {'output': 'x', 'phrase_backend': 'install-anything'}),
            ('review', {'run_dir': 'x', 'operation': 'write'}),
            ('review', {'run_dir': 'x', 'operation': 'read', 'input': 'x'}),
            ('review', {'run_dir': 'x', 'operation': 'serve'}),
        ]
        for name, arguments in bad:
            with self.subTest(name=name, arguments=arguments), patch.object(tool_api, 'run_worker') as worker:
                with self.assertRaises(tool_api.ValidationError):
                    tool_api.execute(name, arguments)
                worker.assert_not_called()

    def test_click_worker_uses_only_explicit_analysis_python_and_literal_args(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve()
            source = directory / 'take $(shell); with spaces.wav'
            source.write_bytes(b'fixture')
            arguments = {'input': str(source), 'run_dir': str(directory), 'bpm': 178,
                         'template_start': .1, 'template_end': .11, 'attenuate': True,
                         'template_click_only': True, 'strength': .25}
            with patch.dict(os.environ, {'VIDEO_UTILS_ANALYSIS_PYTHON': '/explicit/analysis/python'}):
                command = tool_api.worker_command('clicks', arguments)
            self.assertEqual(command[0], '/explicit/analysis/python')
            self.assertEqual(command[1:3], [str(ROOT / 'scripts/clicks.py'), str(source)])
            self.assertIn('--attenuate', command)
            self.assertIn('--template-click-only', command)
            self.assertIn('178', command)
            self.assertNotIn('serve', tool_api.worker_command('review', {'run_dir': str(directory)}))


    def test_pitch_dispatch_keeps_budget_and_explicit_interpreter(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve()
            source = directory / 'C1 fixture.wav'; source.write_bytes(b'fixture')
            with patch.dict(os.environ, {'VIDEO_UTILS_ANALYSIS_PYTHON': '/explicit/analysis/python'}):
                command = tool_api.worker_command('pitch', {'input': str(source), 'run_dir': str(directory),
                                                           'max_analysis_seconds': 1, 'start_seconds': 2.5})
            self.assertEqual(command[0], '/explicit/analysis/python')
            self.assertEqual(command[1:3], [str(ROOT / 'scripts/pitch.py'), str(source)])
            self.assertEqual(command[-4:], ['--max-analysis-seconds', '1', '--start-seconds', '2.5'])
            self.assertNotIn('--backend', command)


    def test_real_meter_hook_keeps_notation_unknown_and_rejects_stale_input(self):
        from test_meter import MeterTests
        from test_mcp import exchange, initialization, request
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source, _ = MeterTests().make_run(temporary)
            replies, stderr = exchange([initialization(), {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
                request(2, 'tools/call', {'name': 'meter', 'arguments': {'run_dir': temporary}})])
            self.assertEqual(stderr, '')
            self.assertFalse(replies[1]['result']['isError'])
            result = replies[1]['result']['structuredContent']['result']
            artifact = Path(result['output'])
            self.assertTrue(artifact.is_relative_to(directory.resolve()))
            self.assertEqual(hashlib.sha256(artifact.read_bytes()).hexdigest(), result['sha256'])
            meter = json.loads(artifact.read_text())
            self.assertIsNone(meter['time_signature'])
            self.assertTrue(meter['provenance']['no_media_changes'])
            source.write_bytes(b'changed provenance fixture')
            with self.assertRaisesRegex(tool_api.ToolError, 'Analyzed media hash differs'):
                tool_api.execute('meter', {'run_dir': temporary})
            self.assertEqual(len(list((directory / 'meter').glob('*/meter.json'))), 1)


    def test_pitch_real_c1_mcp_summary_and_sparse_coverage(self):
        import importlib.util
        import math
        import statistics
        import struct
        import wave
        from test_mcp import exchange, initialization, request
        interpreter = os.environ.get('VIDEO_UTILS_ANALYSIS_PYTHON')
        if not interpreter:
            if not (importlib.util.find_spec('numpy') and importlib.util.find_spec('librosa')):
                self.skipTest('explicit installed librosa analysis environment is required')
            interpreter = sys.executable
        if not (shutil.which(os.environ.get('FFMPEG', 'ffmpeg')) and
                shutil.which(os.environ.get('FFPROBE', 'ffprobe'))):
            self.skipTest('FFmpeg/FFprobe are required for the optional actual pitch hook')
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source = directory / 'known-C1.wav'
            rate, frequency = 16000, 440 * 2 ** ((24 - 69) / 12)
            values = [round(.4 * 32767 * math.tanh(3 * math.sin(2 * math.pi * frequency * i / rate)))
                      for i in range(rate * 2)]
            with wave.open(str(source), 'wb') as stream:
                stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(rate)
                stream.writeframes(struct.pack('<' + 'h' * len(values), *values))
            with patch.dict(os.environ, {'VIDEO_UTILS_ANALYSIS_PYTHON': interpreter}):
                replies, stderr = exchange([initialization(), {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
                    request(2, 'tools/call', {'name': 'pitch', 'arguments': {
                        'input': str(source), 'run_dir': str(directory), 'max_analysis_seconds': 1,
                        'start_seconds': .25, 'timeout_seconds': 90}})], timeout=120)
            self.assertEqual(stderr, '')
            self.assertFalse(replies[1]['result']['isError'])
            summary = replies[1]['result']['structuredContent']['result']
            self.assertLess(len(json.dumps(summary)), 50000)
            self.assertNotIn('observations', summary)
            self.assertAlmostEqual(summary['analysis']['coverage_fraction'], .5)
            self.assertEqual(summary['analysis']['sampling'], 'explicit_contiguous_excerpt')
            artifact = json.loads(Path(summary['pitch_json']).read_text())
            self.assertIsNone(artifact['interpretation']['intended_notes'])
            self.assertEqual(artifact['interpretation']['performance_grade'], 'not_graded')
            branches = artifact['observations']['analyzed_excerpts'][0]['branches']
            low = next(branch for branch in branches if branch['minimum_hz'] == 28)
            candidates = [frame['frequency_hz'] for frame in low['frames'] if frame['frequency_hz'] is not None]
            self.assertTrue(candidates)
            self.assertAlmostEqual(statistics.median(candidates), frequency, delta=1)
            self.assertTrue(all(frame['note_mapping']['identified_string'] is None
                                for frame in low['frames'] if frame['frequency_hz'] is not None))


    def test_real_tonal_hook_preserves_null_tonic_mode_and_provenance(self):
        from test_tonal import fixture
        from test_mcp import exchange, initialization, request
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            fixture(directory)
            source = directory / 'denoised.wav'
            original = source.read_bytes()
            replies, stderr = exchange([initialization(), {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
                request(2, 'tools/call', {'name': 'tonal', 'arguments': {
                    'run_dir': temporary, 'max_regions': 1, 'max_recurrences': 1}})])
            self.assertEqual(stderr, '')
            self.assertFalse(replies[1]['result']['isError'])
            summary = replies[1]['result']['structuredContent']['result']
            self.assertIsNone(summary['tonic'])
            self.assertIsNone(summary['mode'])
            artifact = Path(summary['tonal_json'])
            self.assertTrue(artifact.is_relative_to(directory.resolve() / 'tonal'))
            tonal = json.loads(artifact.read_text())
            self.assertEqual(tonal['performance_grade'], 'not_graded')
            self.assertFalse(tonal['requires_expected_score'])
            self.assertFalse(tonal['instrument_context']['used_as_tonic_prior'])
            for comparison in tonal['recurrence_context_comparisons']:
                self.assertIsNone(comparison['tonal_change'])
                self.assertIsNone(comparison['performance_issue'])
            self.assertEqual(source.read_bytes(), original)
            source.write_bytes(b'mismatched derivative')
            with self.assertRaises(tool_api.ToolError):
                tool_api.execute('tonal', {'run_dir': temporary})
            self.assertEqual(len(list((directory / 'tonal').glob('*/tonal.json'))), 1)

    def test_real_review_read_write_revision_and_source_binding(self):
        from test_mcp import exchange, initialization, request
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            manifest_path = directory / 'manifest.json'
            manifest = {'source': {'sha256': 'a' * 64},
                        'timeline': {'audio_start_seconds': 2.5},
                        'pcm': {'duration_seconds': 10}}
            manifest_path.write_text(json.dumps(manifest))
            write = directory / 'annotation.json'
            write.write_text(json.dumps({'expected_revision': 0, 'annotation': {
                'source_start_seconds': 3, 'source_end_seconds': 4, 'category': 'phrase',
                'status': 'needs_review', 'note': 'Synthetic review candidate; acceptance remains unknown.'}}))
            messages = [initialization(), {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
                request(2, 'tools/call', {'name': 'review', 'arguments': {'run_dir': temporary}}),
                request(3, 'tools/call', {'name': 'review', 'arguments': {
                    'run_dir': temporary, 'operation': 'write', 'input': str(write)}}),
                request(4, 'tools/call', {'name': 'review', 'arguments': {
                    'run_dir': temporary, 'operation': 'write', 'input': str(write)}})]
            replies, stderr = exchange(messages)
            self.assertEqual(stderr, '')
            self.assertEqual(replies[1]['result']['structuredContent']['result']['revision'], 0)
            saved = replies[2]['result']['structuredContent']['result']
            self.assertEqual(saved['revision'], 1)
            self.assertEqual(saved['listening_acceptance'], 'not_established')
            self.assertEqual(saved['annotations'][0]['source_start_seconds'], 3)
            self.assertTrue(replies[3]['result']['isError'])
            self.assertIn('stale_annotation_revision', replies[3]['result']['content'][0]['text'])
            stored = directory / 'review-annotations.json'
            prior = hashlib.sha256(stored.read_bytes()).hexdigest()
            manifest['source']['sha256'] = 'b' * 64
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(tool_api.ToolError, 'annotation_source_mismatch'):
                tool_api.execute('review', {'run_dir': temporary})
            self.assertEqual(hashlib.sha256(stored.read_bytes()).hexdigest(), prior)

    def test_real_phrase_compare_keeps_missing_features_unknown_and_rejects_lineage(self):
        from test_mcp import exchange, initialization, request
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / 'manifest.json').write_text(json.dumps({'source': {'sha256': 'a' * 64}}))
            (directory / 'analysis.json').write_text(json.dumps({'source': {'sha256': 'a' * 64}}))
            phrases = {'source': {'sha256': 'a' * 64}, 'observations': {'recurrence_candidates': []}}
            phrases_path = directory / 'phrases.json'; phrases_path.write_text(json.dumps(phrases))
            replies, stderr = exchange([initialization(), {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
                request(2, 'tools/call', {'name': 'phrase_compare', 'arguments': {'run_dir': temporary}})])
            self.assertEqual(stderr, '')
            self.assertFalse(replies[1]['result']['isError'])
            self.assertEqual(replies[1]['result']['structuredContent']['result']['status'], 'feature_alignment_unavailable')
            artifact = directory / 'phrase-comparisons.json'
            result = json.loads(artifact.read_text())
            self.assertFalse(result['requires_expected_intent'])
            self.assertEqual(result['flags'], [])
            prior = hashlib.sha256(artifact.read_bytes()).hexdigest()
            phrases['source']['sha256'] = 'b' * 64; phrases_path.write_text(json.dumps(phrases))
            with self.assertRaisesRegex(tool_api.ToolError, 'matching analysis-input identity'):
                tool_api.execute('phrase_compare', {'run_dir': temporary})
            self.assertEqual(hashlib.sha256(artifact.read_bytes()).hexdigest(), prior)

    def test_real_benchmark_fixtures_and_output_root_rejection(self):
        from test_mcp import exchange, initialization, request
        output = ROOT / 'artifacts/benchmarks' / ('contract-' + uuid.uuid4().hex)
        try:
            replies, stderr = exchange([initialization(), {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
                request(2, 'tools/call', {'name': 'benchmark', 'arguments': {
                    'operation': 'fixtures', 'output': str(output), 'timeout_seconds': 90}})], timeout=120)
            self.assertEqual(stderr, '')
            self.assertFalse(replies[1]['result']['isError'])
            result = replies[1]['result']['structuredContent']['result']
            self.assertEqual(result['status'], 'fixtures_created')
            self.assertEqual(result['case_count'], 3)
            self.assertTrue((output / 'fixtures.json').is_file())
            with self.assertRaisesRegex(tool_api.ToolError, 'must not already exist'):
                tool_api.execute('benchmark', {'operation': 'fixtures', 'output': str(output)})
        finally:
            if output.exists():
                shutil.rmtree(output)  # Only this unique test-owned ignored artifact tree.
        with tempfile.TemporaryDirectory() as temporary:
            outside = Path(temporary) / 'must-not-create'
            with self.assertRaisesRegex(tool_api.ToolError, 'beneath artifacts/benchmarks'):
                tool_api.execute('benchmark', {'operation': 'fixtures', 'output': str(outside)})
            self.assertFalse(outside.exists())


if __name__ == '__main__':
    unittest.main()
