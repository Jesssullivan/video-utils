"""S5 admission (lane W7a, TIN-7090): freeze the first 57 descriptors and admit the four narration tools.

Tools 58-61 run ``python -m narrate COMMAND`` (docs/spec/NARRATE.md, "MCP tools"): narrate_render, narrate_voices,
narrate_engines and narrate_evaluate. Every path rule, the input/text exclusion, the registry-id form and unique
metrics are checked before a worker starts; those refusals run here with the worker patched out. The end-to-end
case builds a synthetic workspace (the committed Dhall example records, the generated sine voice, the fixture
lexicon) in a temporary directory, renders inline text with the fake engine through tool_api, then lists voices
and engines, evaluates the run and checks the typed refusals a real worker returns. It needs FFmpeg and skips,
naming it, without. No voice clip, model, network or GPU is used, and nothing is written in the repository.
"""
import copy
import hashlib
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import tool_api  # noqa: E402
from test_mcp import exchange, initialization, request  # noqa: E402
from test_s4a_tool_admission import digest  # noqa: E402

# tools[:57] as recorded by tests/test_s4b_tool_admission.py after its revision 1; this admission appends after it.
ADMITTED_57_SHA256 = '0464f644801f8106e08a656cd15b11908b322644c1f0210d09d44a5492c4b705'
ADMITTED_57_ASCII_SHA256 = 'fdb7c96127737e5fddab23e6313982c04dd50d51cdab0b908db448fa5546d1be'
# tools[:61] as admitted here, same two serializers (recorded for the next freeze).
ADMITTED_61_SHA256 = '401f5abfe1c4546bc7c8cf3d29c3e69273fa70df7842c0bf39bf46ca8029937a'
ADMITTED_61_ASCII_SHA256 = '583498249caf04f4e1c3703077f905d18b6f2f63aee3f7659c0d019e7ba2ddf6'
# name -> (sha256 of the admitted SKILL.md, required, (timeout max, default), evidence_kind, read only)
NEW = {
    'narrate_render': ('42e68b04bcd76cdf1a4e4df4c542147683cd4fe38c5bd7616ffc8805e0b38cdc', {'config'}, (900, 600), 'synthetic_narration_rendered_unreviewed', False),
    'narrate_voices': ('4a7381c859b13fadbc2c95b55e7ba663f946f9778a066343a98ead0b2151eeeb', {'config'}, (300, 60), 'consent_registry_listing', True),
    'narrate_engines': ('73618e793b85768478f8d7604670f060ca703c79c7364cd186df23b2ee040c7d', {'config'}, (120, 60), 'engine_registry_listing_with_tcp_reachability', True),
    'narrate_evaluate': ('625ecad9904ea05118ba2707d35d4e030c7c65fd3dceab2158d4b7cdd539e238', {'run_dir'}, (900, 600), 'measured_narration_scores_uncalibrated', True),
}
SPEECH_NOTE = (' Speech workflow, not a guitar default: the guitar axioms in AGENTS.md do not apply; every narration '
               'manifest says synthetic true and timeline mapping narration_v1, so no guitar tool accepts it '
               '(docs/spec/TIMELINE_CONTRACT.md).')
EXAMPLES = ROOT / 'narrate' / 'dhall' / 'examples'
LEXICAL = ROOT / 'narrate' / 'tests' / 'fixtures' / 'lexical'
TEXT = 'Narrate reads this line with the fake engine.\n\nThe second paragraph has 8% of stretch to spare.\n'
PRIVATE_ENV = ('NARRATE_STORE', 'NARRATE_LEXICAL_DIR', 'NARRATE_WHISPER_MODEL', 'WHISPER_MODEL', 'NARRATE_SIM_MODEL',
               'NARRATE_SIM_PYTHON', 'NARRATE_ENGINE_TOKEN')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def workspace(base):
    """A narrate.toml with the committed example records, the generated sine voice in a store and the fixture
    lexicon, under base. The job's input pin is cleared so inline text renders."""
    spec = importlib.util.spec_from_file_location('narrate_dhall_check', ROOT / 'narrate' / 'dhall' / 'check.py')
    check = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(check)
    store = base / 'store'
    store.mkdir(parents=True)
    for name, data in check.fixtures().items():
        (store / name).write_bytes(data)
    load = lambda name: json.loads((EXAMPLES / name).read_text())  # noqa: E731
    job = copy.deepcopy(load('jobs.json')[0])
    job['inputSha256'] = ''
    job['lexical'] = {'release': 'xoxd-lexical@0.0.0-fixture', 'commit': '0' * 40,
                      'lexiconSha256': sha((LEXICAL / 'estate-lexicon.json').read_bytes()),
                      'promptDigestSha256': sha((LEXICAL / 'prompt-digest.txt').read_bytes()),
                      'valeRegister': 'slides',
                      'valeRegisterSha256': sha((LEXICAL / 'vale' / 'registers' / 'slides.ini').read_bytes()),
                      'rewriteCheck': True}
    (base / 'jobs.json').write_text(json.dumps([job]))
    for name in ('engines.json', 'voices.json', 'consents.json', 'pronunciation.json'):
        shutil.copyfile(EXAMPLES / name, base / name)
    (base / 'narrate.toml').write_text(
        'job = "jobs.json"\nengines = "engines.json"\nvoices = "voices.json"\nconsents = "consents.json"\n'
        f'pronunciation = "pronunciation.json"\nstore = "store"\nlexical = "{LEXICAL}"\nout = "runs"\n'
        f'[whisper]\nmodel = "{base / "no-such-model.bin"}"\n')
    return base / 'narrate.toml'


class S5ToolAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.scratch.name)
        self.config = workspace(self.dir / 'ws')

    def tearDown(self):
        self.scratch.cleanup()

    # ----- registry freeze ----------------------------------------------------
    def test_first_57_descriptors_frozen_and_four_appended(self):
        tools = tool_api.descriptors()
        self.assertEqual(len(tools), 61)
        self.assertEqual(digest(tools, 57, False), ADMITTED_57_SHA256)
        self.assertEqual(digest(tools, 57, True), ADMITTED_57_ASCII_SHA256)
        self.assertEqual(digest(tools, 61, False), ADMITTED_61_SHA256)
        self.assertEqual(digest(tools, 61, True), ADMITTED_61_ASCII_SHA256)
        self.assertEqual([tool['name'] for tool in tools[57:]], list(NEW))
        self.assertEqual(len({tool['name'] for tool in tools}), 61)
        raw = (ROOT / 'program/tools.json').read_text(encoding='utf-8')
        self.assertEqual(json.dumps(json.loads(raw), indent=2) + '\n', raw)

    def test_freeze_hashes_match_the_s4b_record(self):
        import test_s4b_tool_admission as s4b
        self.assertEqual((s4b.ADMITTED_57_SHA256, s4b.ADMITTED_57_ASCII_SHA256),
                         (ADMITTED_57_SHA256, ADMITTED_57_ASCII_SHA256))

    def test_admitted_descriptors_equal_the_draft(self):
        draft = json.loads((ROOT / 'program/tool-drafts/narrate.json').read_text(encoding='utf-8'))
        self.assertEqual(draft['linear'], 'TIN-7090')
        tools = tool_api.descriptors()
        self.assertEqual(tools[57:], draft['tools'])
        for tool in tools[57:]:
            self.assertEqual(list(tool), list(tools[0]))

    def test_descriptors_closed_bounded_experimental_and_skills_pinned(self):
        for number, (name, (skill_sha, required, (high, default), evidence, read_only)) in enumerate(NEW.items(),
                                                                                                   start=58):
            with self.subTest(name=name):
                info = tool_api.descriptor(name)
                schema = info['inputSchema']
                tool_api.validate_schema(schema)
                self.assertIs(schema['additionalProperties'], False)
                self.assertEqual(set(schema['required']), required)
                timeout = schema['properties']['timeout_seconds']
                self.assertEqual((timeout['minimum'], timeout['maximum'], timeout['default']), (1, high, default))
                self.assertEqual((info['implementation_status'], info['evidence_kind']), ('experimental', evidence))
                self.assertIs(info['annotations']['readOnlyHint'], read_only)
                self.assertFalse(info['annotations']['destructiveHint'])
                self.assertTrue(info['description'].endswith(SPEECH_NOTE))
                for key in ('identify', 'research', 'iterate', 'acceptance'):
                    self.assertTrue(info['agent_workflow'][key])
                skill = f'.agents/skills/{name.replace("_", "-")}/SKILL.md'
                self.assertEqual(info['skill'], skill)
                data = (ROOT / skill).read_bytes()
                self.assertEqual(sha(data), skill_sha)
                text = data.decode('utf-8')
                self.assertIn(f'**Hook:** MCP tool `{name}` (admitted as tool {number}, experimental)', text)
                self.assertIn('**Capability:** ' + info['description'][:-len(SPEECH_NOTE)] + '\n', text)
                self.assertIn(info['agent_workflow']['identify'], text)
                for limitation in info['limitations']:
                    self.assertIn(f'- {limitation}\n', text)
                self.assertNotIn(''.join(('/Us', 'ers/')), json.dumps(info) + text)
                self.assertNotIn(''.join(('/sr', 'v/')), json.dumps(info) + text)
        render = tool_api.descriptor('narrate_render')['inputSchema']['properties']
        self.assertEqual(render['text']['maxLength'], 4000)
        self.assertEqual((render['confidential']['enum'], render['allow_hosted']['enum']), ([True], [False]))
        self.assertEqual((render['max_takes']['minimum'], render['max_takes']['maximum']), (1, 3))
        self.assertEqual(render['fit_max_stretch']['maximum'], 0.08)

    # ----- refusals before any worker -----------------------------------------
    def refuse(self, name, arguments, error=tool_api.ToolError, message=None):
        with patch.object(subprocess, 'Popen') as popen:
            with self.assertRaises(error) as caught:
                tool_api.execute(name, arguments)
            popen.assert_not_called()
        if message:
            self.assertIn(message, str(caught.exception))

    def test_schema_and_string_rules_refuse_before_any_worker(self):
        config = str(self.config)
        for name, arguments in [
            ('narrate_render', {}),
            ('narrate_render', {'config': 'a/../narrate.toml'}),
            ('narrate_render', {'config': 'https://example.invalid/narrate.toml'}),
            ('narrate_render', {'config': config, 'timeout_seconds': 901}),
            ('narrate_render', {'config': config, 'text': 'x' * 4001}),
            ('narrate_render', {'config': config, 'text': 'hi', 'input': config}),
            ('narrate_render', {'config': config, 'text': 'hi', 'input_kind': 'CondenseWords'}),
            ('narrate_render', {'config': config, 'confidential': False}),
            ('narrate_render', {'config': config, 'allow_hosted': True}),
            ('narrate_render', {'config': config, 'max_takes': 4}),
            ('narrate_render', {'config': config, 'fit_max_stretch': 0.09}),
            ('narrate_render', {'config': config, 'voice': '../voice'}),
            ('narrate_render', {'config': config, 'engine': 'fake sine'}),
            ('narrate_render', {'config': config, 'out': 'elsewhere'}),
            ('narrate_voices', {'config': config, 'paths': True}),
            ('narrate_engines', {'config': config, 'profile': 'Cloud'}),
            ('narrate_evaluate', {}),
            ('narrate_evaluate', {'run_dir': 'runs/../x'}),
            ('narrate_evaluate', {'run_dir': 'x', 'metrics': ['sim', 'sim']}),
            ('narrate_evaluate', {'run_dir': 'x', 'metrics': ['mos']}),
            ('narrate_evaluate', {'run_dir': 'x', 'metrics': []}),
            ('narrate_evaluate', {'run_dir': 'x', 'reference_voice': 'a/b'}),
        ]:
            with self.subTest(name=name, arguments=arguments):
                self.refuse(name, arguments, tool_api.ValidationError)

    def test_path_rules_refuse_before_any_worker(self):
        link = self.dir / 'link.toml'
        link.symlink_to(self.config)
        big = self.dir / 'big.toml'
        big.write_bytes(b'#' * (1024 * 1024 + 1))
        for name, arguments, message in [
            ('narrate_voices', {'config': str(link)}, 'narrate config must be an existing regular narrate.toml'),
            ('narrate_voices', {'config': str(self.dir / 'absent.toml')}, 'narrate config must be an existing'),
            ('narrate_engines', {'config': str(big)}, 'at most 1 MiB'),
            ('narrate_render', {'config': str(self.config), 'input': str(self.dir / 'absent.md')},
             'narrate_render input must be an existing regular file'),
            ('narrate_evaluate', {'run_dir': str(self.dir)}, 'with a manifest.json'),
            ('narrate_evaluate', {'run_dir': str(self.dir / 'absent')}, 'with a manifest.json'),
        ]:
            with self.subTest(name=name, arguments=arguments):
                self.refuse(name, arguments, message=message)

    def test_render_arguments_map_to_the_cli(self):
        with tempfile.TemporaryDirectory() as scratch:
            command = tool_api.narrate_command('narrate_render', {
                'config': str(self.config), 'text': TEXT, 'voice': 'voice-fixture-sine', 'seed': 7,
                'confidential': True, 'allow_hosted': False, 'max_takes': 1, 'min_sim': 0,
                'fit_max_stretch': 0.05}, scratch)
            script = pathlib.Path(command[command.index('--input') + 1])
            self.assertEqual((script.parent, script.suffix), (pathlib.Path(scratch), '.md'))  # the job's Markdown
            self.assertEqual(script.read_text(), TEXT)
        self.assertEqual(command[2:6], ['narrate', 'render', str(self.config), '--json'])
        tail = command[command.index('--input') + 2:]
        self.assertEqual(tail, ['--voice', 'voice-fixture-sine', '--seed', '7', '--confidential', '--no-hosted',
                                '--min-sim', '0', '--max-takes', '1', '--fit-max-stretch', '0.05'])

    # ----- end to end -----------------------------------------------------------
    def test_render_list_evaluate_and_refuse_through_tool_api(self):
        if shutil.which('ffmpeg') is None or shutil.which('ffprobe') is None:
            self.skipTest('ffmpeg unavailable')
        clean = {key: value for key, value in os.environ.items() if key not in PRIVATE_ENV}
        with patch.dict(os.environ, clean, clear=True):
            reply = tool_api.execute('narrate_render', {'config': str(self.config), 'text': TEXT, 'max_takes': 1,
                                                        'timeout_seconds': 300})
            self.assertEqual((reply['tool'], reply['status']), ('narrate_render', 'completed'))
            summary = reply['result']
            run_dir = pathlib.Path(summary['run_dir'])
            self.assertEqual(run_dir.parent, self.dir / 'ws' / 'runs')
            manifest = json.loads(pathlib.Path(summary['manifest']).read_text())
            self.assertEqual((manifest['kind'], manifest['synthetic']), ('narration_render', True))
            self.assertEqual((manifest['timeline']['mapping'], manifest['timeline']['no_time_stretch']),
                             ('narration_v1', False))
            self.assertEqual(summary['overrides'], {'max_takes': 1})
            self.assertEqual(manifest['input']['sha256'], sha(TEXT.encode()))
            self.assertIn('sim_not_measured', summary['flags'])
            self.assertNotIn(str(self.dir / 'ws' / 'store'), json.dumps(summary))

            voices = tool_api.execute('narrate_voices', {'config': str(self.config)})['result']['voices']
            self.assertEqual([(v['id'], v['consent_state'], v['ref_clip_stored']) for v in voices],
                             [('voice-fixture-sine', 'active', True)])
            self.assertNotIn(str(self.dir), json.dumps(voices))
            self.assertNotIn('Sha256', json.dumps(voices))
            engines = tool_api.execute('narrate_engines', {'config': str(self.config),
                                                           'probe_reachability': True})['result']['engines']
            self.assertEqual([(e['id'], e['reach']['reachable']) for e in engines], [('fake-sine', True)])
            self.assertNotIn('endpoint', json.dumps(engines))

            scores = tool_api.execute('narrate_evaluate', {'run_dir': str(run_dir), 'config': str(self.config)})
            metrics = scores['result']['metrics']
            self.assertTrue(scores['result']['ok'])
            self.assertTrue(metrics['loudness']['passed'])
            self.assertEqual(metrics['wer']['status'], 'not_measured')
            self.assertEqual(metrics['sim']['status'], 'not_measured')  # no model in this workspace

            with self.assertRaises(tool_api.ToolError) as caught:
                tool_api.execute('narrate_render', {'config': str(self.config), 'text': TEXT,
                                                    'voice': 'voice-nobody'})
            self.assertEqual(caught.exception.receipt['reason'], 'voice_unknown')
            with self.assertRaises(tool_api.ToolError) as caught:
                tool_api.execute('narrate_render', {'config': str(self.config), 'text': TEXT, 'engine': 'absent'})
            self.assertEqual(caught.exception.receipt['status'], 'refused')
            (run_dir / 'narration.srt').write_text('tampered\n')
            with self.assertRaises(tool_api.ToolError) as caught:
                tool_api.execute('narrate_evaluate', {'run_dir': str(run_dir), 'metrics': ['loudness']})
            self.assertEqual(caught.exception.receipt['reason'], 'run_unverified')
        self.assertEqual(sorted(p.name for p in (self.dir / 'ws' / 'runs').iterdir()), [run_dir.name])

    # ----- MCP readback ---------------------------------------------------------
    def test_real_mcp_lists_61_tools_and_reads_the_new_prompts(self):
        prompts = [name.replace('_', '-') for name in NEW]
        messages = [initialization(), {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
                    request(2, 'tools/list'), request(3, 'prompts/list')]
        messages += [request(10 + i, 'prompts/get', {'name': prompt}) for i, prompt in enumerate(prompts)]
        messages.append(request(30, 'tools/call', {'name': 'narrate_voices',
                                                   'arguments': {'config': str(self.dir / 'absent.toml')}}))
        replies, stderr = exchange(messages, timeout=60)
        self.assertEqual(stderr, '')
        tools = {row['name']: row for row in replies[1]['result']['tools']}
        self.assertEqual(len(tools), 61)
        names = [row['name'] for row in replies[2]['result']['prompts']]
        self.assertEqual(len(names), 59)
        for offset, name in enumerate(NEW):
            with self.subTest(name=name):
                self.assertIs(tools[name]['inputSchema']['additionalProperties'], False)
                self.assertEqual(tools[name]['_meta']['video-utils']['skill'], f'.agents/skills/{prompts[offset]}/SKILL.md')
                self.assertIn(prompts[offset], names)
                text = replies[3 + offset]['result']['messages'][0]['content']['text']
                self.assertIn(f'MCP tool `{name}` (admitted as tool {58 + offset}, experimental)', text)
        self.assertTrue(replies[-1]['result']['isError'])


if __name__ == '__main__':
    unittest.main()
