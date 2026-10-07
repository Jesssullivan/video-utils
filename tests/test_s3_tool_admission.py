"""S3 admission (root_integration_f): freeze the first 40 descriptors and admit two experimental model-lane hooks.

Tools 41 and 42 are ``beat_this_compare`` and ``guitar_noul_decide`` (MODEL_LANES_S3 sections 3 and 4). No model is
registered or downloaded here: ``program/models.json`` must not carry the Beat This entry until root's explicit
hash-bound fetch, and the comparator must refuse with a typed reason meanwhile. No gateway is contacted.

Synthetic metadata only; no recording, accepted run or repository artifact is read or written.
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

# Sixth freeze (root_integration_f, base f44f962): tools[:40], measured with the two serializers used by
# tests/test_s1_tool_admission.py (ensure_ascii=False) and tests/test_sprint1_audit.py canonical() (ensure_ascii=True):
#   sha256(json.dumps(tools[:40], sort_keys=True, separators=(',', ':'), ensure_ascii=<flag>))
# These equal FROZEN_40_* in tests/test_s2_tool_admission.py. The first-38, first-39 and first-40 hashes were REBASED
# on 2026-10-07 by the operator descriptor ruling ("phrase_timing descriptor: rebase the freeze and fix the wording",
# docs/agent-notes/2026-10-07-s2-operator-rulings.md; docs/spec/sprints/DESCRIPTOR_REBASE_S2R.md): only tools[37]
# description/intent/limitations changed. S3 admission appends after index 39 and changes none of the 40.
FROZEN_40_SHA256 = 'da091862fd7d854e80a8950a0e9581cff07c481b1d25614a939666e4c215045d'
FROZEN_40_ASCII_SHA256 = '5dc30b2f7f86a755083b8cf7783960ac563c4ecfb425b4f0d3d10af0acf30845'
# tools[:42] as admitted by root_integration_f, same two serializers (recorded for the next freeze).
ADMITTED_42_SHA256 = '92aa3d3e82f2ff62211b063ddc9d4e37e96140fc1776308a51d2d11f7d4c1f83'
ADMITTED_42_ASCII_SHA256 = '61604b1af6c8791a42dfee924e5ef7a13d1e084c6de5693978fc68c00ddc06a7'

BEAT_THIS_MODEL_ID = 'cpjku-beat-this-final0'
BEAT_THIS_REFUSALS = ('model_not_registered', 'model_hash_not_registered', 'model_registry_entry_invalid',
                      'model_file_missing', 'model_hash_mismatch', 'runtime_not_qualified', 'platform_unsupported',
                      'input_rejected')
# name -> (skill prompt, annotations, required, (timeout min, max, default or None), evidence_kind, hook line)
NEW_F = {
    'beat_this_compare': (
        'guitar-beat-this',
        {'readOnlyHint': False, 'destructiveHint': False, 'idempotentHint': False, 'openWorldHint': False},
        {'run_dir'}, (1, 900, 660), 'uncalibrated_learned_beat_downbeat_hypotheses',
        '**Hook:** MCP tool `beat_this_compare` (admitted as tool 41, experimental).'),
    'guitar_noul_decide': (
        'guitar-noul',
        {'readOnlyHint': True, 'destructiveHint': False, 'idempotentHint': False, 'openWorldHint': True},
        {'run_dir', 'windows', 'timeout_seconds'}, (1, 120, None), 'external_detector_window_hypotheses',
        '**Hook:** MCP tool `guitar_noul_decide` (admitted as tool 42, experimental).'),
}
WINDOW = {'source_start_s': 1.0, 'source_end_s': 2.0}


def digest(tools, count, ascii_only):
    data = json.dumps(tools[:count], sort_keys=True, separators=(',', ':'), ensure_ascii=ascii_only)
    return hashlib.sha256(data.encode()).hexdigest()


class S3ToolAdmissionTests(unittest.TestCase):
    # ----- registry freeze ----------------------------------------------------
    def test_first_40_descriptors_frozen_and_two_appended(self):
        tools = tool_api.descriptors()
        self.assertEqual(len(tools), 42)
        self.assertEqual(digest(tools, 40, False), FROZEN_40_SHA256)
        self.assertEqual(digest(tools, 40, True), FROZEN_40_ASCII_SHA256)
        self.assertEqual(digest(tools, 42, False), ADMITTED_42_SHA256)
        self.assertEqual(digest(tools, 42, True), ADMITTED_42_ASCII_SHA256)
        self.assertEqual([tool['name'] for tool in tools[40:]], list(NEW_F))
        self.assertEqual(len({tool['name'] for tool in tools}), 42)
        raw = (ROOT / 'program/tools.json').read_text(encoding='utf-8')
        self.assertEqual(json.dumps(json.loads(raw), indent=2) + '\n', raw)

    def test_freeze_hashes_match_the_s2_pins(self):
        import test_s2_tool_admission as s2
        self.assertEqual((s2.FROZEN_40_SHA256, s2.FROZEN_40_ASCII_SHA256), (FROZEN_40_SHA256, FROZEN_40_ASCII_SHA256))

    # ----- descriptors and skills --------------------------------------------
    def test_new_descriptors_closed_bounded_experimental_and_skills_admitted(self):
        for name, (prompt, annotations, required, (low, high, default), evidence, hook) in NEW_F.items():
            with self.subTest(name=name):
                info = tool_api.descriptor(name)
                schema = info['inputSchema']
                tool_api.validate_schema(schema)
                self.assertIs(schema['additionalProperties'], False)
                self.assertEqual(set(schema['required']), required)
                run_dir = schema['properties']['run_dir']
                self.assertEqual((run_dir['type'], run_dir['minLength'], run_dir['maxLength']), ('string', 1, 4096))
                timeout = schema['properties']['timeout_seconds']
                self.assertEqual((timeout['type'], timeout['minimum'], timeout['maximum'], timeout.get('default')),
                                 ('integer', low, high, default))
                self.assertEqual(info['implementation_status'], 'experimental')
                self.assertEqual(info['evidence_kind'], evidence)
                self.assertEqual(info['annotations'], annotations)
                self.assertFalse(info['dependencies']['enforced'])
                self.assertEqual(info['skill'], f'.agents/skills/{prompt}/SKILL.md')
                text = (ROOT / info['skill']).read_text(encoding='utf-8')
                self.assertTrue(text.startswith(f'---\nname: {prompt}\ndescription: '))
                self.assertIn(hook, text)
                self.assertNotIn('DRAFT', text)
                self.assertNotIn('Root still has to admit', text)
                for key in ('identify', 'research', 'iterate', 'acceptance'):
                    self.assertTrue(info['agent_workflow'][key])
                with self.assertRaises(tool_api.ValidationError):
                    tool_api.validate({'run_dir': 'artifacts/runs/x', 'unknown': True}, schema)
        # No model, runtime, gateway, credential or output knob is exposed to a caller.
        self.assertEqual(set(tool_api.descriptor('beat_this_compare')['inputSchema']['properties']),
                         {'run_dir', 'timeout_seconds'})
        noul = tool_api.descriptor('guitar_noul_decide')['inputSchema']['properties']
        self.assertEqual(set(noul), {'run_dir', 'windows', 'timeout_seconds'})
        windows = noul['windows']
        self.assertEqual((windows['type'], windows['minItems'], windows['maxItems']), ('array', 1, 64))
        self.assertIs(windows['items']['additionalProperties'], False)
        self.assertEqual(set(windows['items']['required']), {'source_start_s', 'source_end_s'})
        self.assertEqual(set(windows['items']['properties']), {'source_start_s', 'source_end_s'})

    def test_descriptors_carry_the_evidence_boundaries(self):
        beat = ' '.join(tool_api.descriptor('beat_this_compare')['limitations'])
        for phrase in ('model hypotheses', 'does not establish meter', 'not an identification of intended tempo',
                       'never a default detector', 'approximately 32 Hz'):
            self.assertIn(phrase, beat)
        for code in BEAT_THIS_REFUSALS:
            self.assertIn(code, beat)
        noul = ' '.join(tool_api.descriptor('guitar_noul_decide')['limitations'])
        for phrase in ('detector_hypothesis', 'user_reported false', 'never mapped to annotations',
                       'note_correctness and performance_issue are always null', 'gateway_not_configured',
                       'real_take_not_permitted', 'approximately 32 Hz'):
            self.assertIn(phrase, noul)

    # ----- argument refusals before any worker --------------------------------
    def test_invalid_arguments_refuse_before_worker(self):
        cases = [
            ('beat_this_compare', {}),
            ('beat_this_compare', {'run_dir': ''}),
            ('beat_this_compare', {'run_dir': 'artifacts/runs/x', 'timeout_seconds': 0}),
            ('beat_this_compare', {'run_dir': 'artifacts/runs/x', 'timeout_seconds': 901}),
            ('beat_this_compare', {'run_dir': 'artifacts/runs/x', 'timeout_seconds': 1.5}),
            ('beat_this_compare', {'run_dir': 'artifacts/runs/x', 'model_id': 'other'}),
            ('beat_this_compare', {'run_dir': 'artifacts/runs/x', 'checkpoint': '/tmp/final0.ckpt'}),
            ('beat_this_compare', {'run_dir': 'artifacts/runs/../runs/x'}),
            ('beat_this_compare', {'run_dir': 'artifacts\\runs\\x'}),
            ('guitar_noul_decide', {'run_dir': 'artifacts/runs/x', 'windows': [WINDOW]}),
            ('guitar_noul_decide', {'run_dir': 'artifacts/runs/x', 'windows': [], 'timeout_seconds': 5}),
            ('guitar_noul_decide', {'run_dir': 'artifacts/runs/x', 'windows': [WINDOW] * 65, 'timeout_seconds': 5}),
            ('guitar_noul_decide', {'run_dir': 'artifacts/runs/x', 'windows': [WINDOW], 'timeout_seconds': 121}),
            ('guitar_noul_decide', {'run_dir': 'artifacts/runs/x', 'windows': [dict(WINDOW, label='x')],
                                    'timeout_seconds': 5}),
            ('guitar_noul_decide', {'run_dir': 'artifacts/runs/x', 'windows': [{'source_start_s': 1.0}],
                                    'timeout_seconds': 5}),
            ('guitar_noul_decide', {'run_dir': 'artifacts/runs/x', 'windows': [dict(WINDOW, source_start_s=-1)],
                                    'timeout_seconds': 5}),
            ('guitar_noul_decide', {'run_dir': 'artifacts/runs/x', 'windows': [WINDOW], 'timeout_seconds': 5,
                                    'gateway': 'https://models.xoxd.ai/x'}),
            ('guitar_noul_decide', {'run_dir': 'artifacts/runs/x', 'windows': [WINDOW], 'timeout_seconds': 5,
                                    'allow_real_take': 'v6-private-operator-lab-host'}),
            ('guitar_noul_decide', {'run_dir': 'artifacts/runs/../x', 'windows': [WINDOW], 'timeout_seconds': 5}),
        ]
        with patch.object(tool_api, 'run_typed_refusal_worker') as run, patch.object(tool_api, 'run_worker') as generic, \
                patch.object(tool_api, 'worker_command') as command:
            for name, arguments in cases:
                with self.subTest(name=name, arguments=arguments):
                    with self.assertRaises(tool_api.ValidationError):
                        tool_api.execute(name, arguments)
            run.assert_not_called()
            generic.assert_not_called()
            command.assert_not_called()

    # ----- fixed argv ----------------------------------------------------------
    def test_worker_commands_are_fixed_argv_without_model_or_gateway_arguments(self):
        with tempfile.TemporaryDirectory(prefix='s3 admission ') as base:
            run = pathlib.Path(base).resolve() / 'run'
            run.mkdir()
            with patch.object(tool_api, 'basic_pitch_directory', return_value=str(run)) as bound:
                command = tool_api.worker_command('beat_this_compare', {'run_dir': 'artifacts/runs/one'})
            bound.assert_called_once_with('artifacts/runs/one')
            self.assertEqual(command[1:], [str(ROOT / 'scripts/beat_this_compare.py'), 'compare', '--run-dir', str(run)])
        arguments = {'run_dir': 'artifacts/runs/one; rm -rf $HOME', 'windows': [WINDOW, {'source_start_s': 3, 'source_end_s': 4}],
                     'timeout_seconds': 7}
        command = tool_api.worker_command('guitar_noul_decide', arguments)
        self.assertEqual(command[1:3], [str(ROOT / 'scripts/guitar_noul_client.py'), '--request-json'])
        self.assertEqual(len(command), 4)
        self.assertEqual(json.loads(command[3]), arguments)  # one literal argv element, never a shell string
        self.assertNotIn('--out', command)
        for name in NEW_F:
            self.assertIn(name, tool_api.TRAVERSAL_GUARDED_RUN_TOOLS)
            self.assertIn(name, tool_api.TYPED_REFUSAL_TOOLS)

    def test_execute_uses_typed_refusal_relay_and_outer_deadline(self):
        with patch.object(tool_api, 'worker_command', return_value=['python', 'worker']), \
                patch.object(tool_api, 'run_typed_refusal_worker', return_value={'status': 'completed'}) as run, \
                patch.object(tool_api, 'run_worker') as generic:
            tool_api.execute('beat_this_compare', {'run_dir': 'artifacts/runs/one'})
            self.assertEqual(run.call_args.args[1:], (660, 'beat_this_compare'))
            tool_api.execute('guitar_noul_decide', {'run_dir': 'artifacts/runs/one', 'windows': [WINDOW],
                                                    'timeout_seconds': 30})
            self.assertEqual(run.call_args.args[1:], (40, 'guitar_noul_decide'))
            generic.assert_not_called()

    # ----- model registry and typed refusal -----------------------------------
    def test_beat_this_model_is_not_registered_and_no_checkpoint_is_present(self):
        registry = json.loads((ROOT / 'program/models.json').read_text(encoding='utf-8'))
        self.assertNotIn(BEAT_THIS_MODEL_ID, registry['models'])
        self.assertNotIn('TO_BE_FILLED_BY_ROOT_HASH_BOUND_FETCH', json.dumps(registry))
        self.assertFalse((ROOT / 'models' / f'{BEAT_THIS_MODEL_ID}.bin').exists())

    def test_real_comparator_refuses_typed_while_hash_unregistered(self):
        process = subprocess.run(
            [sys.executable, str(ROOT / 'scripts/beat_this_compare.py'), 'compare', '--run-dir', 'artifacts/runs/absent-s3-admission'],
            cwd=ROOT, capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
        self.assertEqual(process.returncode, 2)
        refused = json.loads(process.stdout)
        self.assertEqual((refused['status'], refused['refusal_code'], refused['model_id']),
                         ('refused', 'model_not_registered', BEAT_THIS_MODEL_ID))
        self.assertEqual((refused['network_used'], refused['model_acquired'], refused['default_adoption']),
                         (False, False, False))

    def test_tool_api_relays_the_typed_refusal_from_the_real_worker(self):
        with tempfile.TemporaryDirectory(prefix='s3 admission ') as base:
            run = pathlib.Path(base).resolve() / 'run'
            run.mkdir()
            before = sorted(os.listdir(run))
            with patch.object(tool_api, 'basic_pitch_directory', return_value=str(run)):
                with self.assertRaises(tool_api.ToolError) as caught:
                    tool_api.execute('beat_this_compare', {'run_dir': 'artifacts/runs/one', 'timeout_seconds': 60})
            self.assertEqual(sorted(os.listdir(run)), before)
        self.assertNotIsInstance(caught.exception, tool_api.ValidationError)
        self.assertEqual(str(caught.exception), 'beat_this_compare refused: model_not_registered')
        receipt = caught.exception.receipt
        self.assertEqual((receipt['status'], receipt['tool'], receipt['refusal_code'], receipt['worker_returncode']),
                         ('refused', 'beat_this_compare', 'model_not_registered', 2))

    def test_guitar_noul_refuses_typed_without_gateway_or_transport(self):
        environment = {key: value for key, value in os.environ.items() if not key.startswith('VIDEO_UTILS_GUITAR_NOUL_')}
        with patch.dict(os.environ, environment, clear=True):
            with self.assertRaises(tool_api.ToolError) as caught:
                tool_api.execute('guitar_noul_decide', {'run_dir': 'artifacts/runs/absent-s3-admission',
                                                        'windows': [WINDOW], 'timeout_seconds': 5})
        receipt = caught.exception.receipt
        self.assertEqual((receipt['status'], receipt['tool']), ('refused', 'guitar_noul_decide'))
        self.assertIn(receipt['refusal_code'], ('input_schema_invalid', 'gateway_not_configured'))
        self.assertEqual(str(caught.exception), f'guitar_noul_decide refused: {receipt["refusal_code"]}')

    def test_generic_run_worker_source_pin_is_untouched(self):
        import inspect
        # Same pin as tests/test_share_export_tool.py: typed refusals use a dedicated runner instead.
        self.assertEqual(hashlib.sha256(inspect.getsource(tool_api.run_worker).encode()).hexdigest(),
                         'acd72926a70c33cc92bd056f055fb83f348ad2e7c9a3576e7bfcd6d20e9bd3af')

    def test_refusal_relay_ignores_untyped_or_malformed_worker_output(self):
        with tempfile.TemporaryDirectory(prefix='s3 admission ') as base:
            worker = pathlib.Path(base) / 'worker.py'
            for body, expected in (
                    ({'status': 'refused', 'refusal_code': 'model_hash_not_registered', 'message': 'm' * 5000},
                     'beat_this_compare refused: model_hash_not_registered'),
                    ({'status': 'refused', 'refusal_code': 'Bad Code; rm'}, 'worker failed (2)'),
                    ({'status': 'completed', 'refusal_code': 'model_not_registered'}, 'worker failed (2)'),
                    ('not json', 'worker failed (2)')):
                with self.subTest(body=body):
                    text = body if isinstance(body, str) else json.dumps(body)
                    worker.write_text(f'import sys\nsys.stdout.write({text!r})\nsys.exit(2)\n')
                    with self.assertRaises(tool_api.ToolError) as caught:
                        tool_api.run_typed_refusal_worker([sys.executable, str(worker)], 30, 'beat_this_compare')
                    self.assertTrue(str(caught.exception).startswith(expected), str(caught.exception))
                    if expected.endswith('model_hash_not_registered'):
                        self.assertEqual(len(caught.exception.receipt['message']), 1000)
                    else:
                        self.assertIsNone(caught.exception.receipt)

    # ----- MCP readback --------------------------------------------------------
    def test_real_mcp_lists_42_tools_and_reads_back_both_skill_prompts(self):
        messages = [initialization(), {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
                    request(2, 'tools/list'), request(3, 'prompts/list')]
        messages += [request(10 + index, 'prompts/get', {'name': prompt})
                     for index, (prompt, *_rest) in enumerate(NEW_F.values())]
        messages.append(request(20, 'tools/call', {'name': 'beat_this_compare',
                                                   'arguments': {'run_dir': 'artifacts/runs/x', 'model_id': 'other'}}))
        replies, stderr = exchange(messages, timeout=30)
        self.assertEqual(stderr, '')
        tools = {row['name']: row for row in replies[1]['result']['tools']}
        self.assertEqual(len(tools), 42)
        prompts = {row['name'] for row in replies[2]['result']['prompts']}
        self.assertEqual(len(prompts), 42)
        for offset, (name, (prompt, annotations, *_rest)) in enumerate(NEW_F.items()):
            with self.subTest(name=name):
                self.assertIs(tools[name]['inputSchema']['additionalProperties'], False)
                self.assertEqual(tools[name]['annotations'], annotations)
                self.assertEqual(tools[name]['_meta']['video-utils']['implementationStatus'], 'experimental')
                self.assertIn(prompt, prompts)
                text = replies[3 + offset]['result']['messages'][0]['content']['text']
                self.assertEqual(text, (ROOT / '.agents/skills' / prompt / 'SKILL.md').read_text(encoding='utf-8'))
        self.assertEqual(replies[5]['error']['code'], -32602)


if __name__ == '__main__':
    unittest.main()
