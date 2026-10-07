"""S3 admission (root_admission_g): freeze the first 42 descriptors and admit four experimental tools.

Tools 43-46 are ``take_intake`` (TAKE_INTAKE_S3), ``timing_calibration_analyze`` and ``timing_calibration_apply``
(TIMING_CALIBRATION_S3) and ``stems_estimate`` (STEMS_S3). ``stems_estimate`` keeps refusing ``model_not_registered``:
no htdemucs_6s entry is added to program/models.json and nothing is fetched. The timing-calibration pair shares one
skill and therefore one MCP prompt. This module also carries the R6 regression cases (bazel_full root request): the
hidden/staging/traversal guards inspect only the components below the checkout, never the checkout's own location.

Synthetic metadata only; no recording, accepted run or repository artifact is read or written.
"""
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
import wave
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import tool_api  # noqa: E402
from test_mcp import exchange, initialization, request  # noqa: E402

# Seventh freeze (root_admission_g, base 62d5838): tools[:42] as admitted by root_integration_f, measured with the two
# serializers of tests/test_s1_tool_admission.py (ensure_ascii=False) and tests/test_sprint1_audit.py (ensure_ascii=True):
#   sha256(json.dumps(tools[:42], sort_keys=True, separators=(',', ':'), ensure_ascii=<flag>))
# They equal ADMITTED_42_* in tests/test_s3_tool_admission.py. This admission appends after index 41 and changes none.
ADMITTED_42_SHA256 = '92aa3d3e82f2ff62211b063ddc9d4e37e96140fc1776308a51d2d11f7d4c1f83'
ADMITTED_42_ASCII_SHA256 = '61604b1af6c8791a42dfee924e5ef7a13d1e084c6de5693978fc68c00ddc06a7'
# tools[:46] as admitted by root_admission_g, same two serializers (recorded for the next freeze).
ADMITTED_46_SHA256 = 'ed2494b5e259ffac5d98ab554ac8e0b55b21119c948f49829a31170a5c7e6a4b'
ADMITTED_46_ASCII_SHA256 = '15852f750b668e3ea51206dc00bfdac35dd3364e50288138ee30f0d7e171ebb1'

# name -> (prompt, sha256 of the admitted SKILL.md, annotations, required, (timeout min, max, default),
#          evidence_kind, hook text in the skill)
NEW_G = {
    'take_intake': (
        'take-intake', 'e9cd028bc5d2c08bb41a2e387d3763189fe7b78c830e3bca1a729ca310597334',
        {'readOnlyHint': False, 'destructiveHint': False, 'idempotentHint': True, 'openWorldHint': False},
        {'operation'}, (1, 900, 300), 'intake_plan_or_evidence_packet',
        '**Hook:** MCP tool `take_intake` (admitted as tool 43, experimental)'),
    'timing_calibration_analyze': (
        'timing-calibration', '19870fec044611e57a2a48e273dcb0eeb98e42737a97b4eab2cbb785f9ac3b37',
        {'readOnlyHint': True, 'destructiveHint': False, 'idempotentHint': False, 'openWorldHint': False},
        {'input', 'segments', 'distances', 'distance_method', 'amp_chain', 'setup_id', 'output_root'},
        (1, 600, 600), 'synthetic_validated_calibration_record_real_take_unvalidated',
        '**Hook:** MCP tools `timing_calibration_analyze` and `timing_calibration_apply` (admitted as tools 44 and 45, '
        'experimental)'),
    'timing_calibration_apply': (
        'timing-calibration', '19870fec044611e57a2a48e273dcb0eeb98e42737a97b4eab2cbb785f9ac3b37',
        {'readOnlyHint': True, 'destructiveHint': False, 'idempotentHint': False, 'openWorldHint': False},
        {'phrase_timing', 'calibration', 'setup_id', 'output_root'}, (1, 300, 60),
        'calibrated_click_relative_timing_hypothesis_unvalidated',
        '**Hook:** MCP tools `timing_calibration_analyze` and `timing_calibration_apply` (admitted as tools 44 and 45, '
        'experimental)'),
    'stems_estimate': (
        'stems-estimate', 'ec0f8dd3d67eef1f0d2b21e4586c93f5c9ea916f0c6028e55af63608ecf2839a',
        {'readOnlyHint': False, 'destructiveHint': False, 'idempotentHint': False, 'openWorldHint': False},
        {'run_dir', 'excerpt_start_seconds', 'excerpt_end_seconds'}, (1, 900, 660),
        'uncalibrated_model_stem_estimates_from_mono_mixture',
        '**Hook:** MCP tool `stems_estimate` (admitted as tool 46, experimental)'),
}
STEMS_MODEL_ID = 'demucs-htdemucs_6s-5c90dfd2'
ANALYZE = {'input': 'clip.wav', 'segments': 'seg.json', 'distances': 'mic_to_metronome=1.0,mic_to_amp=1.5',
           'distance_method': 'measured', 'amp_chain': 'analog', 'setup_id': 'room-a', 'output_root': 'artifacts/s3/tc'}
APPLY = {'phrase_timing': 'pt.json', 'calibration': 'cal.json', 'setup_id': 'room-a', 'output_root': 'artifacts/s3/tc'}
STEMS = {'run_dir': 'artifacts/runs/absent-s3g-admission', 'excerpt_start_seconds': 1.0, 'excerpt_end_seconds': 3.0}


def digest(tools, count, ascii_only):
    data = json.dumps(tools[:count], sort_keys=True, separators=(',', ':'), ensure_ascii=ascii_only)
    return hashlib.sha256(data.encode()).hexdigest()


def drafts():
    """The lane drafts the admitted descriptors must equal (take_intake tools[0], timing tools[], stems descriptor)."""
    take = json.loads((ROOT / 'program/tool-drafts/take_intake.json').read_text(encoding='utf-8'))['tools']
    timing = json.loads((ROOT / 'program/tool-drafts/timing_calibration.json').read_text(encoding='utf-8'))['tools']
    stems = json.loads((ROOT / 'program/tool-drafts/stems_estimate.json').read_text(encoding='utf-8'))['descriptor']
    return take + timing + [stems]


class S3GToolAdmissionTests(unittest.TestCase):
    # ----- registry freeze ----------------------------------------------------
    def test_first_42_descriptors_frozen_and_four_appended(self):
        tools = tool_api.descriptors()
        self.assertEqual(len(tools), 46)
        self.assertEqual(digest(tools, 42, False), ADMITTED_42_SHA256)
        self.assertEqual(digest(tools, 42, True), ADMITTED_42_ASCII_SHA256)
        self.assertEqual(digest(tools, 46, False), ADMITTED_46_SHA256)
        self.assertEqual(digest(tools, 46, True), ADMITTED_46_ASCII_SHA256)
        self.assertEqual([tool['name'] for tool in tools[42:]], list(NEW_G))
        self.assertEqual(len({tool['name'] for tool in tools}), 46)
        raw = (ROOT / 'program/tools.json').read_text(encoding='utf-8')
        self.assertEqual(json.dumps(json.loads(raw), indent=2) + '\n', raw)

    def test_freeze_hashes_match_the_s3_pins(self):
        import test_s3_tool_admission as s3
        self.assertEqual((s3.ADMITTED_42_SHA256, s3.ADMITTED_42_ASCII_SHA256),
                         (ADMITTED_42_SHA256, ADMITTED_42_ASCII_SHA256))

    def test_admitted_descriptors_equal_the_lane_drafts(self):
        tools = tool_api.descriptors()
        self.assertEqual(tools[42:], drafts())
        reference = list(tools[0])
        for tool in tools[42:]:
            self.assertEqual(list(tool), reference)

    # ----- descriptors and skills --------------------------------------------
    def test_new_descriptors_closed_bounded_experimental_and_skills_pinned(self):
        for name, (prompt, skill_sha, annotations, required, (low, high, default), evidence, hook) in NEW_G.items():
            with self.subTest(name=name):
                info = tool_api.descriptor(name)
                schema = info['inputSchema']
                tool_api.validate_schema(schema)
                self.assertIs(schema['additionalProperties'], False)
                self.assertEqual(set(schema['required']), required)
                self.assertNotIn('pattern', json.dumps(schema))
                timeout = schema['properties']['timeout_seconds']
                self.assertEqual((timeout['type'], timeout['minimum'], timeout['maximum'], timeout.get('default')),
                                 ('integer', low, high, default))
                self.assertEqual(info['implementation_status'], 'experimental')
                self.assertEqual(info['evidence_kind'], evidence)
                self.assertEqual(info['annotations'], annotations)
                self.assertFalse(info['dependencies']['enforced'])
                self.assertEqual(info['skill'], f'.agents/skills/{prompt}/SKILL.md')
                data = (ROOT / info['skill']).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), skill_sha)
                text = data.decode('utf-8')
                self.assertTrue(text.startswith(f'---\nname: {prompt}\ndescription: '))
                self.assertIn(hook, text)
                for stale in ('DRAFT', 'draft only', 'not yet admitted', 'root admits', 'Root still has to admit',
                              'not_claimed_by_lane'):
                    self.assertNotIn(stale, text)
                for key in ('identify', 'research', 'iterate', 'acceptance'):
                    self.assertTrue(info['agent_workflow'][key])
                self.assertNotIn(''.join(('/Us', 'ers/')), json.dumps(info))  # no host path
                with self.assertRaises(tool_api.ValidationError):
                    tool_api.validate({'unknown': True}, schema)
        # Only the plan/packet surface is an MCP tool; run/resume stay just/CLI actions.
        self.assertEqual(tool_api.descriptor('take_intake')['inputSchema']['properties']['operation']['enum'],
                         ['plan', 'packet'])
        # No model, runtime, gateway or output knob is exposed by stems_estimate.
        self.assertEqual(set(tool_api.descriptor('stems_estimate')['inputSchema']['properties']),
                         {'run_dir', 'input_role', 'excerpt_start_seconds', 'excerpt_end_seconds', 'timeout_seconds'})

    def test_descriptors_carry_the_evidence_boundaries(self):
        take = ' '.join(tool_api.descriptor('take_intake')['limitations'])
        for phrase in ('withheld_uncalibrated', 'draft_not_sent', 'needs_listening', 'No note-correctness'):
            self.assertIn(phrase, take)
        analyze = ' '.join(tool_api.descriptor('timing_calibration_analyze')['limitations'])
        for phrase in ('32.70 Hz content untouched', 'Abstains', 'human intent is not ground truth'):
            self.assertIn(phrase, analyze)
        apply = ' '.join(tool_api.descriptor('timing_calibration_apply')['limitations'])
        for phrase in ('never modified', 'within_uncertainty', 'never a performance grade',
                       'No real-take direction has been validated'):
            self.assertIn(phrase, apply)
        stems = ' '.join(tool_api.descriptor('stems_estimate')['limitations'])
        for phrase in ('not recovered original stems', 'low_end_preservation_verdict null', 'model_not_registered',
                       'default_adoption are always false', 'redistribution_permitted false'):
            self.assertIn(phrase, stems)

    def test_timing_calibration_fixed_unknown_uses_tool_level_wording(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('timing_calibration_s3g', ROOT / 'scripts/timing_calibration.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.FIXED_UNKNOWNS['real_take_direction'],
                         'not_claimed_without_operator_calibration_record')

    def test_phrase_timing_skill_points_at_the_calibrated_view_without_changing_its_policy(self):
        text = (ROOT / '.agents/skills/guitar-phrase-timing/SKILL.md').read_text(encoding='utf-8')
        limits = next(line for line in text.splitlines() if line.startswith('**Limits.**'))
        self.assertIn('`timing_calibration_apply`', limits)
        self.assertIn("this tool's own direction policy (`withheld_uncalibrated`) is unchanged", limits)
        self.assertEqual(tool_api.descriptor('phrase_timing')['inputSchema']['properties']['run_kind']['default'],
                         'real_take')

    def test_stems_model_stays_unregistered_and_draft_stays_a_draft(self):
        registry = json.loads((ROOT / 'program/models.json').read_text(encoding='utf-8'))
        self.assertNotIn(STEMS_MODEL_ID, registry['models'])
        draft = json.loads((ROOT / 'program/model-drafts/htdemucs_6s.json').read_text(encoding='utf-8'))
        self.assertIsNone(draft['entry']['sha256'])
        self.assertIsNone(draft['entry']['operator_terms_acknowledgement'])

    def test_just_entrypoints_are_wired(self):
        self.assertIn("import 'just/bazel.just'\nimport 'just/take.just'\n", (ROOT / 'justfile').read_text())
        take = (ROOT / 'just/take.just').read_text()
        for recipe in ('take-plan source', 'take-run source', 'take-resume intake_id', 'take-packet run_dir'):
            self.assertIn('\n' + recipe, take)
        workflow = (ROOT / 'just/workflow.just').read_text()
        for recipe in ('timing-calibration-analyze input segments', 'timing-calibration-apply phrase_timing',
                       'stems-estimate run_dir start end'):
            self.assertIn('\n' + recipe, workflow)
        self.assertEqual(workflow.count('timeout=600).returncode)'), 2)
        for name in NEW_G:  # `just tool-info NAME` runs exactly this command
            with self.subTest(name=name):
                process = subprocess.run([sys.executable, str(ROOT / 'scripts/tool_api.py'), 'describe', name],
                                         cwd=ROOT, capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
                self.assertEqual(process.returncode, 0, process.stderr)
                self.assertEqual(json.loads(process.stdout), tool_api.descriptor(name))

    # ----- argument refusals before any worker --------------------------------
    def test_invalid_arguments_refuse_before_worker(self):
        cases = [
            ('take_intake', {}),
            ('take_intake', {'operation': 'run', 'source': 'take.mov'}),
            ('take_intake', {'operation': 'plan'}),
            ('take_intake', {'operation': 'plan', 'source': 'take.mov', 'intake_dir': 'artifacts/take-intake/x'}),
            ('take_intake', {'operation': 'packet'}),
            ('take_intake', {'operation': 'packet', 'intake_dir': 'artifacts/x', 'source': 'take.mov'}),
            ('take_intake', {'operation': 'packet', 'intake_dir': 'artifacts/x', 'bpm': 178}),
            ('take_intake', {'operation': 'plan', 'source': '../take.mov'}),
            ('take_intake', {'operation': 'plan', 'source': 'https://example.invalid/take.mov'}),
            ('take_intake', {'operation': 'plan', 'source': 'take.mov', 'arrangement': 'a\\b.json'}),
            ('take_intake', {'operation': 'plan', 'source': 'take.mov', 'bpm': 19}),
            ('take_intake', {'operation': 'plan', 'source': 'take.mov', 'state_root': '/tmp/x'}),
            ('take_intake', {'operation': 'plan', 'source': 'take.mov', 'timeout_seconds': 901}),
            ('timing_calibration_analyze', dict(ANALYZE, distances='mic_to_metronome=1')),
            ('timing_calibration_analyze', dict(ANALYZE, distances='mic_to_metronome=1,mic_to_amp=1\n')),
            ('timing_calibration_analyze', dict(ANALYZE, distances='MIC=1,mic_to_amp=1')),
            ('timing_calibration_analyze', dict(ANALYZE, amp_chain='digital')),
            ('timing_calibration_analyze', dict(ANALYZE, amp_chain='declared:-3')),
            ('timing_calibration_analyze', dict(ANALYZE, distance_method='guessed')),
            ('timing_calibration_analyze', dict(ANALYZE, room_temp_c=46)),
            ('timing_calibration_analyze', dict(ANALYZE, input='../clip.wav')),
            ('timing_calibration_analyze', dict(ANALYZE, segments='https://example.invalid/seg.json')),
            ('timing_calibration_analyze', dict(ANALYZE, output_root='artifacts\\s3')),
            ('timing_calibration_analyze', dict(ANALYZE, timeout_seconds=601)),
            ('timing_calibration_analyze', dict(ANALYZE, device_label='phone')),
            ('timing_calibration_apply', dict(APPLY, phrase_timing='a/../pt.json')),
            ('timing_calibration_apply', dict(APPLY, timeout_seconds=301)),
            ('timing_calibration_apply', {key: value for key, value in APPLY.items() if key != 'setup_id'}),
            ('stems_estimate', {'run_dir': 'artifacts/runs/x'}),
            ('stems_estimate', dict(STEMS, timeout_seconds=901)),
            ('stems_estimate', dict(STEMS, input_role='stems')),
            ('stems_estimate', dict(STEMS, excerpt_end_seconds=0)),
            ('stems_estimate', dict(STEMS, model_id='other')),
            ('stems_estimate', dict(STEMS, run_dir='artifacts/runs/../runs/x')),
            ('stems_estimate', dict(STEMS, run_dir='artifacts\\runs\\x')),
        ]
        with patch.object(tool_api, 'run_report_bundle_worker') as run, patch.object(tool_api, 'run_worker') as generic, \
                patch.object(tool_api, 'worker_command') as command:
            for name, arguments in cases:
                with self.subTest(name=name, arguments=arguments):
                    with self.assertRaises(tool_api.ValidationError):
                        tool_api.execute(name, arguments)
            run.assert_not_called()
            generic.assert_not_called()
            command.assert_not_called()

    def test_timing_patterns_accept_the_declared_forms(self):
        for distances in ('mic_to_metronome=1,mic_to_amp=2.5',
                          'mic_to_metronome=1,mic_to_amp=2,ear_to_metronome=0.5,ear_to_amp=0.7'):
            for amp_chain in ('analog', 'unknown', 'declared:3.5'):
                tool_api.validate_tool_arguments('timing_calibration_analyze',
                                                 dict(ANALYZE, distances=distances, amp_chain=amp_chain))

    # ----- fixed argv ----------------------------------------------------------
    def test_worker_commands_are_fixed_argv(self):
        with tempfile.TemporaryDirectory(prefix='s3g admission ') as base:
            base = pathlib.Path(base).resolve()
            intake = base / 'intake'
            intake.mkdir()
            (intake / 'intake.json').write_text('{}')
            command = tool_api.worker_command('take_intake', {'operation': 'packet', 'intake_dir': str(intake)})
            self.assertEqual(command[1:], [str(ROOT / 'scripts/take_intake.py'), 'packet', str(intake)])
            with self.assertRaises(tool_api.ToolError):  # no intake.json: refused before any worker
                tool_api.worker_command('take_intake', {'operation': 'packet', 'intake_dir': str(base)})
        command = tool_api.worker_command('take_intake', {
            'operation': 'plan', 'source': 'take $(x);.mov', 'family': '--state-root=/elsewhere', 'bpm': 178,
            'features': 'extended', 'origin': 'synthetic_fixture', 'arrangement': 'ref one.json'})
        self.assertEqual(command[1:], [str(ROOT / 'scripts/take_intake.py'), 'plan', str(ROOT / 'take $(x);.mov'),
                                       '--family=--state-root=/elsewhere', '--arrangement=ref one.json',
                                       '--features=extended', '--origin=synthetic_fixture', '--bpm=178.0'])
        command = tool_api.worker_command('stems_estimate', dict(STEMS, input_role='source'))
        self.assertEqual(command[1:4], [str(ROOT / 'scripts/stems_estimate.py'), 'estimate', '--request-json'])
        self.assertEqual(len(command), 5)
        self.assertEqual(json.loads(command[4]), dict(STEMS, input_role='source'))
        for name in ('stems_estimate',):
            self.assertIn(name, tool_api.TRAVERSAL_GUARDED_RUN_TOOLS)
            self.assertIn(name, tool_api.TYPED_REFUSAL_TOOLS)
        self.assertEqual(tool_api.STDERR_REFUSAL_TOOLS, {'take_intake': 'reason', 'timing_calibration_analyze': 'refusal',
                                                         'timing_calibration_apply': 'refusal'})

    def test_timing_commands_use_s2_guards_and_fixed_argv(self):
        with tempfile.TemporaryDirectory(prefix='s3g admission ') as base:
            base = pathlib.Path(base).resolve()
            outputs = base / 'artifacts'
            outputs.mkdir()
            (base / 'seg.json').write_text('{}')
            (base / 'clip.wav').write_bytes(b'RIFF')
            with patch.object(tool_api, 'S2_OUTPUT_ROOT', outputs):
                command = tool_api.worker_command('timing_calibration_analyze', dict(
                    ANALYZE, input=str(base / 'clip.wav'), segments=str(base / 'seg.json'), setup_id='-x room',
                    output_root=str(outputs / 'tc'), room_temp_c=21))
                self.assertEqual(command[1:], [
                    str(ROOT / 'scripts/timing_calibration.py'), 'analyze', str(base / 'clip.wav'),
                    '--segments=' + str(base / 'seg.json'), '--distances=mic_to_metronome=1.0,mic_to_amp=1.5',
                    '--distance-method=measured', '--amp-chain=analog', '--setup-id=-x room',
                    '--output-root=' + str(outputs / 'tc'), '--room-temp-c=21.0'])
                command = tool_api.worker_command('timing_calibration_apply', dict(
                    APPLY, phrase_timing=str(base / 'seg.json'), calibration=str(base / 'seg.json'),
                    output_root=str(outputs / 'tc')))
                self.assertEqual(command[1:], [
                    str(ROOT / 'scripts/timing_calibration.py'), 'apply', '--phrase-timing=' + str(base / 'seg.json'),
                    '--calibration=' + str(base / 'seg.json'), '--setup-id=room-a',
                    '--output-root=' + str(outputs / 'tc')])
                (outputs / 'runs').mkdir()
                (base / 'linked.json').symlink_to(base / 'seg.json')
                (base / 'notes.txt').write_text('{}')
                refused = [
                    dict(APPLY, phrase_timing=str(base / 'seg.json'), calibration=str(base / 'seg.json'),
                         output_root=str(outputs / 'runs' / 'tc')),          # never beneath artifacts/runs
                    dict(APPLY, phrase_timing=str(base / 'seg.json'), calibration=str(base / 'seg.json'),
                         output_root=str(base / 'elsewhere')),               # outside artifacts/
                    dict(APPLY, phrase_timing=str(base / 'linked.json'), calibration=str(base / 'seg.json'),
                         output_root=str(outputs / 'tc')),                   # symlinked input
                    dict(APPLY, phrase_timing=str(base / 'notes.txt'), calibration=str(base / 'seg.json'),
                         output_root=str(outputs / 'tc')),                   # not .json
                    dict(APPLY, phrase_timing=str(base / 'absent.json'), calibration=str(base / 'seg.json'),
                         output_root=str(outputs / 'tc')),                   # missing input
                    dict(APPLY, phrase_timing=str(base / 'seg.json'), calibration=str(base / 'seg.json'),
                         output_root=str(outputs / 'absent' / 'tc')),        # parent must exist
                ]
                for arguments in refused:
                    with self.subTest(arguments=arguments), self.assertRaises(tool_api.ToolError):
                        tool_api.worker_command('timing_calibration_apply', arguments)
                with self.assertRaises(tool_api.ToolError):  # run directory without denoised.wav
                    run = base / 'run'
                    run.mkdir()
                    (run / 'manifest.json').write_text('{}')
                    tool_api.worker_command('timing_calibration_analyze', dict(
                        ANALYZE, input=str(run), segments=str(base / 'seg.json'), output_root=str(outputs / 'tc')))
            self.assertEqual(sorted(path.name for path in outputs.iterdir()), ['runs'])

    def test_execute_routes_and_outer_deadlines(self):
        with patch.object(tool_api, 'worker_command', return_value=['python', 'worker']), \
                patch.object(tool_api, 'run_report_bundle_worker', return_value={'status': 'ok'}) as run, \
                patch.object(tool_api, 'run_worker') as generic:
            tool_api.execute('stems_estimate', STEMS)
            self.assertEqual(run.call_args.args[1], 660)
            self.assertFalse(run.call_args.kwargs.get('failure_from_stderr', False))
            for name, arguments, timeout in (
                    ('take_intake', {'operation': 'plan', 'source': 'take.mov'}, 300),
                    ('take_intake', {'operation': 'packet', 'intake_dir': 'artifacts/x', 'timeout_seconds': 20}, 20),
                    ('timing_calibration_analyze', ANALYZE, 600),
                    ('timing_calibration_apply', APPLY, 60)):
                with self.subTest(name=name):
                    tool_api.execute(name, arguments)
                    self.assertEqual(run.call_args.args[1], timeout)
                    self.assertIs(run.call_args.kwargs['failure_from_stderr'], True)
            generic.assert_not_called()

    def test_stderr_refusal_relay_ignores_untyped_or_malformed_worker_output(self):
        with tempfile.TemporaryDirectory(prefix='s3g admission ') as base:
            worker = pathlib.Path(base) / 'worker.py'
            for tool, code, body, expected in (
                    ('take_intake', 2, 'noise line\n' + json.dumps({'status': 'refused', 'reason': 'source_missing',
                                                                     'message': 'm' * 5000}),
                     'take_intake refused: source_missing'),
                    ('timing_calibration_apply', 2, json.dumps({'refusal': 'setup_id_mismatch', 'message': 'x'}),
                     'timing_calibration_apply refused: setup_id_mismatch'),
                    ('take_intake', 2, json.dumps({'status': 'refused', 'reason': 'Bad Code; rm'}), 'worker failed (2)'),
                    ('take_intake', 2, json.dumps({'status': 'completed', 'reason': 'source_missing'}), 'worker failed (2)'),
                    ('timing_calibration_analyze', 2, 'usage: timing_calibration.py analyze ...', 'worker failed (2)'),
                    ('timing_calibration_analyze', 1, 'timing_calibration: [Errno 2] /srv/host-only-path',
                     'worker failed (1)'),
                    ('timing_calibration_analyze', 1, json.dumps({'refusal': 'input_invalid'}), 'worker failed (1)')):
                with self.subTest(tool=tool, body=body[:40]):
                    worker.write_text(f'import sys\nsys.stderr.write({body!r})\nsys.exit({code})\n')
                    with self.assertRaises(tool_api.ToolError) as caught:
                        tool_api.run_stderr_refusal_worker([sys.executable, str(worker)], 30, tool)
                    self.assertTrue(str(caught.exception).startswith(expected), str(caught.exception))
                    self.assertNotIn('/srv/host-only-path', str(caught.exception))
                    if 'refused:' in expected:
                        receipt = caught.exception.receipt
                        self.assertEqual((receipt['status'], receipt['tool'], receipt['worker_returncode']),
                                         ('refused', tool, 2))
                        self.assertLessEqual(len(receipt['message']), 1000)
                    else:
                        self.assertIsNone(caught.exception.receipt)

    # ----- real workers refuse typed through tool_api, writing nothing ---------
    def test_take_intake_real_worker_refusals_are_relayed(self):
        with self.assertRaises(tool_api.ToolError) as caught:
            tool_api.execute('take_intake', {'operation': 'plan', 'source': 'absent-s3g-admission-take.mov',
                                             'timeout_seconds': 60})
        self.assertEqual(caught.exception.receipt['refusal_code'], 'source_missing')
        self.assertEqual(str(caught.exception), 'take_intake refused: source_missing')
        with tempfile.TemporaryDirectory(prefix='s3g admission ') as base:
            intake = pathlib.Path(base).resolve()
            (intake / 'intake.json').write_text('{}')
            with self.assertRaises(tool_api.ToolError) as caught:
                tool_api.execute('take_intake', {'operation': 'packet', 'intake_dir': str(intake), 'timeout_seconds': 60})
            self.assertEqual(sorted(path.name for path in intake.iterdir()), ['intake.json'])
        self.assertEqual(caught.exception.receipt['refusal_code'], 'not_an_intake_run_dir')

    def test_timing_calibration_real_worker_refusals_are_relayed(self):
        with tempfile.TemporaryDirectory(prefix='s3g admission ') as base:
            base = pathlib.Path(base).resolve()
            outputs = base / 'artifacts'
            outputs.mkdir()
            (base / 'pt.json').write_text('{}')
            (base / 'cal.json').write_text('{}')
            (base / 'seg.json').write_text('{"schema_version": 1, "segments": []}')
            with wave.open(str(base / 'clip.wav'), 'wb') as stream:
                stream.setnchannels(1)
                stream.setsampwidth(2)
                stream.setframerate(16000)
                stream.writeframes(b'\0\0' * 1600)
            (base / 'clip.txt').write_text('not audio')
            cases = (
                ('timing_calibration_apply', dict(APPLY, phrase_timing=str(base / 'pt.json'),
                                                  calibration=str(base / 'cal.json'), output_root=str(outputs / 'tc')),
                 'calibration_record_invalid'),
                ('timing_calibration_analyze', dict(ANALYZE, input=str(base / 'clip.wav'), segments=str(base / 'seg.json'),
                                                    distances='mic_to_metronome=1,ear_to_amp=1',
                                                    output_root=str(outputs / 'tc'), timeout_seconds=60),
                 'distances_invalid'),
                ('timing_calibration_analyze', dict(ANALYZE, input=str(base / 'clip.txt'), segments=str(base / 'seg.json'),
                                                    output_root=str(outputs / 'tc'), timeout_seconds=60),
                 'input_invalid'))
            with patch.object(tool_api, 'S2_OUTPUT_ROOT', outputs):
                for name, arguments, code in cases:
                    with self.subTest(name=name, code=code):
                        with self.assertRaises(tool_api.ToolError) as caught:
                            tool_api.execute(name, arguments)
                        self.assertEqual(caught.exception.receipt['refusal_code'], code)
                        self.assertEqual(str(caught.exception), f'{name} refused: {code}')
            self.assertEqual(list(outputs.iterdir()), [])

    def test_stems_estimate_real_worker_refuses_typed(self):
        for arguments, code in ((STEMS, 'model_not_registered'),
                                (dict(STEMS, excerpt_start_seconds=0.0, excerpt_end_seconds=40.0), 'excerpt_too_long')):
            with self.subTest(code=code):
                with self.assertRaises(tool_api.ToolError) as caught:
                    tool_api.execute('stems_estimate', dict(arguments, timeout_seconds=60))
                receipt = caught.exception.receipt
                self.assertEqual((receipt['status'], receipt['tool'], receipt['refusal_code'], receipt['worker_returncode']),
                                 ('refused', 'stems_estimate', code, 2))
                self.assertEqual(str(caught.exception), f'stems_estimate refused: {code}')

    # ----- MCP readback --------------------------------------------------------
    def test_real_mcp_lists_46_tools_unique_prompts_and_reads_back_the_new_skills(self):
        prompts_new = list(dict.fromkeys(prompt for prompt, *_rest in NEW_G.values()))
        messages = [initialization(), {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
                    request(2, 'tools/list'), request(3, 'prompts/list')]
        messages += [request(10 + index, 'prompts/get', {'name': prompt}) for index, prompt in enumerate(prompts_new)]
        messages.append(request(20, 'tools/call', {'name': 'stems_estimate', 'arguments': dict(STEMS, model_id='x')}))
        messages.append(request(21, 'tools/call', {'name': 'timing_calibration_analyze',
                                                   'arguments': dict(ANALYZE, amp_chain='digital')}))
        messages.append(request(22, 'tools/call', {'name': 'stems_estimate', 'arguments': dict(STEMS, timeout_seconds=60)}))
        replies, stderr = exchange(messages, timeout=60)
        self.assertEqual(stderr, '')
        tools = {row['name']: row for row in replies[1]['result']['tools']}
        self.assertEqual(len(tools), 46)
        names = [row['name'] for row in replies[2]['result']['prompts']]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(len(names), 45)
        for name, (prompt, _sha, annotations, *_rest) in NEW_G.items():
            with self.subTest(name=name):
                self.assertIs(tools[name]['inputSchema']['additionalProperties'], False)
                self.assertEqual(tools[name]['annotations'], annotations)
                self.assertEqual(tools[name]['_meta']['video-utils']['implementationStatus'], 'experimental')
                self.assertEqual(tools[name]['_meta']['video-utils']['skill'], f'.agents/skills/{prompt}/SKILL.md')
                self.assertIn(prompt, names)
        for offset, prompt in enumerate(prompts_new):
            with self.subTest(prompt=prompt):
                text = replies[3 + offset]['result']['messages'][0]['content']['text']
                self.assertEqual(text, (ROOT / '.agents/skills' / prompt / 'SKILL.md').read_text(encoding='utf-8'))
        after = 3 + len(prompts_new)
        self.assertEqual(replies[after]['error']['code'], -32602)
        self.assertEqual(replies[after + 1]['error']['code'], -32602)
        refused = replies[after + 2]['result']
        self.assertTrue(refused['isError'])
        details = json.loads(refused['content'][0]['text'])
        self.assertEqual(details['receipt']['refusal_code'], 'model_not_registered')


class GuardedPartsTests(unittest.TestCase):
    """R6 (bazel_full-root-requests.json): a checkout under a dot-prefixed directory such as .local/ is not refused,
    while every hidden, staging or traversal component inside the argument still is."""

    CHECKOUT = pathlib.Path('/srv/.local/sprint3/worktree')

    def calibration(self, value):
        tool_api.validate_tool_arguments('phrase_evaluate', {'fixture_index': value, 'pilot_index': value,
                                                             'output': value[:-len('.json')] + '-out'})

    def test_components_below_the_checkout_are_the_only_ones_inspected(self):
        with patch.object(tool_api, 'ROOT', self.CHECKOUT):
            self.assertEqual(tool_api.guarded_parts(str(self.CHECKOUT / 'artifacts/benchmarks/x/i.json')),
                             ['artifacts', 'benchmarks', 'x', 'i.json'])
            self.assertEqual(tool_api.guarded_parts('/elsewhere/.local/x.json'), ['', 'elsewhere', '.local', 'x.json'])
            self.assertEqual(tool_api.guarded_parts('artifacts/.hidden/x.json'), ['artifacts', '.hidden', 'x.json'])
            # A sibling whose name merely starts with the checkout path is not inside it.
            self.assertEqual(tool_api.guarded_parts(str(self.CHECKOUT) + '-other/x.json')[:3], ['', 'srv', '.local'])

    def test_calibration_paths_accept_a_dot_checkout_and_refuse_hidden_components_inside(self):
        with patch.object(tool_api, 'ROOT', self.CHECKOUT):
            self.calibration(str(self.CHECKOUT / 'artifacts/benchmarks/x/i.json'))
            for value in (str(self.CHECKOUT / 'artifacts/benchmarks/.hidden/i.json'),
                          str(self.CHECKOUT / 'artifacts/benchmarks/x.partial/i.json'),
                          str(self.CHECKOUT / 'artifacts/benchmarks/../../.git/i.json'),
                          str(self.CHECKOUT) + '-other/artifacts/benchmarks/i.json',
                          '/elsewhere/.local/x.json', 'artifacts/benchmarks/.hidden/i.json'):
                with self.subTest(value=value), self.assertRaises(tool_api.ValidationError):
                    self.calibration(value)

    def test_arrangement_and_capture_application_guards(self):
        with patch.object(tool_api, 'ROOT', self.CHECKOUT):
            run = str(self.CHECKOUT / 'artifacts/runs/one')
            tool_api.validate_tool_arguments('arrangement_reference', {'run_dir': run, 'output': run + '/assessment'})
            tool_api.validate_tool_arguments('apply_capture_profile', {
                'input': str(self.CHECKOUT / 'take.mov'), 'authoring_dir': run + '/capture-profiles/p1',
                'receipt_sha256': 'a' * 64})
            for arguments in ({'run_dir': run, 'output': run + '/.assessment'},
                              {'run_dir': str(self.CHECKOUT / '.hidden/runs/one'), 'output': run + '/a'},
                              {'run_dir': '/elsewhere/.local/runs/one', 'output': run + '/a'},
                              {'run_dir': run, 'output': run + '/a', 'reference': str(self.CHECKOUT / 'x.partial.json')}):
                with self.subTest(arguments=arguments), self.assertRaises(tool_api.ValidationError):
                    tool_api.validate_tool_arguments('arrangement_reference', arguments)
            for field, value in (('input', str(self.CHECKOUT / '.cache/take.mov')),
                                 ('input', '/elsewhere/.local/take.mov'),
                                 ('authoring_dir', run + '/capture-profiles/.p1')):
                arguments = {'input': str(self.CHECKOUT / 'take.mov'), 'authoring_dir': run + '/capture-profiles/p1',
                             'receipt_sha256': 'a' * 64, field: value}
                with self.subTest(field=field, value=value), self.assertRaises(tool_api.ValidationError):
                    tool_api.validate_tool_arguments('apply_capture_profile', arguments)

    def test_this_checkout_is_accepted_wherever_it_lives(self):
        # From a .local worktree this is the case that failed before R6; from a dot-free checkout it already passed.
        self.calibration(str(ROOT / 'artifacts/benchmarks/x/i.json'))
        with self.assertRaises(tool_api.ValidationError):
            self.calibration(str(ROOT / 'artifacts/benchmarks/.x/i.json'))


if __name__ == '__main__':
    unittest.main()
