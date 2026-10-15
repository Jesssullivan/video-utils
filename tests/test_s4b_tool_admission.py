"""S4 admission B: freeze the first 48 descriptors and admit the nine condense stage tools.

Tools 49-57 run ``python -m condense STAGE`` (docs/spec/CONDENSE_TOOL_CONTRACT.md). Every talk.toml path rule is
checked before a worker starts; those refusals run here with the worker patched out. The end-to-end case runs the
events, edl, captions, render and publish stages on a synthetic talk and removes the one run it published. It needs FFmpeg, numpy in the worker interpreter
(VIDEO_UTILS_PYTHON or this interpreter; the CI condense job provides both) and the video-utils binary, and
skips with the missing one named otherwise.

Synthetic media only; no recording, run or repository artifact is read or written.
"""
import hashlib
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
from test_s4a_tool_admission import binary, digest  # noqa: E402

# tools[:48] as recorded by tests/test_s4a_tool_admission.py; this admission appends after index 47 and changes none.
ADMITTED_48_SHA256 = '7489cc74678cba2d2de7317a517964dfbde339b4d2004a1a9da9f8d93c884cda'
ADMITTED_48_ASCII_SHA256 = '39bb9db5d08fae1eb6c5699d6933a6362c4c2ab79f2532ca96e29a2f633a5c09'
# tools[:57] as admitted here, same two serializers (recorded for the next freeze).
ADMITTED_57_SHA256 = '965921ff7dbef76d1b5a686c286187dd5f5ab14a0e2a1b7506f021f39984318e'
ADMITTED_57_ASCII_SHA256 = 'a434c898ee97beccf3e897e7c1fcb6bf91f73f135035b8a7a92bec60c7ef004b'
CONFIG = {'config'}
# name -> (sha256 of the admitted SKILL.md, required, (timeout max, default), evidence_kind)
NEW = {
    'condense_transcribe': ('41de64463fef81c0e50246f7cbee6d866493d01dfe7c8b5c042e773cc8f6629c', CONFIG, (14400, 7200),
                            'whisper_cpp_word_timings'),
    'condense_events': ('c8320021c0b2d5a21328ef7eb67925d37d125c411d3f4cef98dde3e358060cb3', CONFIG, (3600, 600),
                        'heuristic_speech_events'),
    'condense_edl': ('98073d4eba0f2a26994c497a18bf25d0aee92adbf3fe63763e7e27b1686a994e', CONFIG, (7200, 1800),
                     'rust_validated_edl'),
    'condense_render': ('77cce7364332160ced6bde5f75554f12ee1fa2dd35ae6b1ece80215ea659c250', CONFIG, (14400, 7200),
                        'rendered_media_unreviewed'),
    'condense_check': ('67429e9e9bd8e33921d475592731be1486ad434b4830837f505d712bdc5c62b0', CONFIG, (7200, 3600),
                       'measured_gates_and_human_review_text'),
    'condense_captions': ('4d1051e1f06df631344b6713ddaf8d2868913e2193881bc8f461a74d1b26b935', CONFIG, (1800, 300),
                          'derived_captions_unreviewed'),
    'condense_overlay': ('9250250b14e6b5ea19569519712c6b30ba499d395c04760eef52b2718bbb149e', CONFIG, (7200, 3600),
                         'rendered_media_unreviewed'),
    'condense_recover': ('44e12f8ad6211d2e88a38f56b363290a703722b8027134bfce604eae1a27b86e',
                         {'reference', 'broken', 'fixed'}, (7200, 3600), 'untrunc_rebuild_with_byte_share'),
    'condense_publish': ('1c9e2c1483546a9388f46b882de533cd403c2c15ed93610c2afe2dbe7bd36497', CONFIG, (3600, 600),
                         'hash_bound_condense_manifest'),
}
TOTAL = 12.0
SPEECH = {(1.0, 3.5): 'Hello and welcome everyone.', (5.5, 8.0): 'This is the first point.',
          (9.0, 11.0): 'Thanks for watching.'}
TOML = """work = "work"
out = "out/talk.mp4"
[encode]
width = 320
height = 180
preset = "ultrafast"
[[clip]]
name = "talk"
file = "talk.mkv"
speed = 2.0
"""


def worker_ready():
    """None when the end-to-end case can run, else the missing dependency."""
    interpreter = os.environ.get('VIDEO_UTILS_PYTHON', sys.executable)
    if shutil.which('ffmpeg') is None or shutil.which('ffprobe') is None:
        return 'ffmpeg unavailable'
    probe = subprocess.run([interpreter, '-c', 'import numpy'], capture_output=True, timeout=60)
    if probe.returncode:
        return 'numpy unavailable in the worker interpreter'
    if binary() is None:
        return 'cargo unavailable: the video-utils binary could not be built'
    return None


def fake_whisper():
    """whisper.cpp full JSON: one segment per word, offsets in ms, t_dtw in 1/100 s."""
    segs = []
    for (a, b), text in SPEECH.items():
        words = text.split()
        step = (b - a) / len(words)
        for i, word in enumerate(words):
            start, end = a + i * step, a + (i + 1) * step - 0.1
            offsets = {'from': round(start * 1000), 'to': round(end * 1000)}
            token = {'text': ' ' + word, 'offsets': offsets, 't_dtw': round(start * 100)}
            segs.append({'text': ' ' + word, 'offsets': offsets, 'tokens': [token]})
    return {'transcription': segs}


class S4BToolAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.scratch.name)
        (self.dir / 'talk.mkv').write_bytes(b'not media; refusals never read it')
        self.config = self.dir / 'talk.toml'
        self.config.write_text(TOML)

    def tearDown(self):
        self.scratch.cleanup()

    def toml(self, text, name='talk.toml'):
        path = self.dir / name
        path.write_text(text)
        return str(path)

    # ----- registry freeze ----------------------------------------------------
    def test_first_48_descriptors_frozen_and_nine_appended(self):
        tools = tool_api.descriptors()
        self.assertEqual(len(tools), 57)
        self.assertEqual(digest(tools, 48, False), ADMITTED_48_SHA256)
        self.assertEqual(digest(tools, 48, True), ADMITTED_48_ASCII_SHA256)
        self.assertEqual(digest(tools, 57, False), ADMITTED_57_SHA256)
        self.assertEqual(digest(tools, 57, True), ADMITTED_57_ASCII_SHA256)
        self.assertEqual([tool['name'] for tool in tools[48:]], list(NEW))
        self.assertEqual(len({tool['name'] for tool in tools}), 57)

    def test_freeze_hashes_match_the_s4a_record(self):
        import test_s4a_tool_admission as s4a
        self.assertEqual((s4a.ADMITTED_48_SHA256, s4a.ADMITTED_48_ASCII_SHA256),
                         (ADMITTED_48_SHA256, ADMITTED_48_ASCII_SHA256))

    def test_admitted_descriptors_equal_the_draft(self):
        draft = json.loads((ROOT / 'program/tool-drafts/condense.json').read_text(encoding='utf-8'))['tools']
        tools = tool_api.descriptors()
        self.assertEqual(tools[48:], draft[2:])
        for tool in tools[48:]:
            self.assertEqual(list(tool), list(tools[0]))

    def test_descriptors_closed_bounded_experimental_and_skills_pinned(self):
        for number, (name, (skill_sha, required, (high, default), evidence)) in enumerate(NEW.items(), start=49):
            with self.subTest(name=name):
                info = tool_api.descriptor(name)
                schema = info['inputSchema']
                tool_api.validate_schema(schema)
                self.assertIs(schema['additionalProperties'], False)
                self.assertEqual(set(schema['required']), required)
                timeout = schema['properties']['timeout_seconds']
                self.assertEqual((timeout['minimum'], timeout['maximum'], timeout['default']), (1, high, default))
                self.assertEqual((info['implementation_status'], info['evidence_kind']), ('experimental', evidence))
                self.assertFalse(info['annotations']['readOnlyHint'])
                self.assertEqual(info['annotations']['idempotentHint'], name not in {'condense_recover', 'condense_publish'})
                self.assertFalse(info['annotations']['openWorldHint'])
                skill = f'.agents/skills/{name.replace("_", "-")}/SKILL.md'
                self.assertEqual(info['skill'], skill)
                data = (ROOT / skill).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), skill_sha)
                text = data.decode('utf-8')
                self.assertIn(f'**Hook:** MCP tool `{name}` (admitted as tool {number}, experimental)', text)
                self.assertNotIn('Hook (draft)', text)
                self.assertNotIn(''.join(('/Us', 'ers/')), json.dumps(info))

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
            ('condense_edl', {}),
            ('condense_edl', {'config': 'a/../talk.toml'}),
            ('condense_edl', {'config': 'https://example.invalid/talk.toml'}),
            ('condense_edl', {'config': 'a\\talk.toml'}),
            ('condense_edl', {'config': config, 'timeout_seconds': 7201}),
            ('condense_edl', {'config': config, 'stage': 'render'}),
            ('condense_check', {'config': config, 'checks': ['silence', 'silence']}),
            ('condense_check', {'config': config, 'checks': ['listen']}),
            ('condense_check', {'config': config, 'checks': []}),
            ('condense_recover', {'reference': 'a.mov', 'broken': 'b.mov'}),
            ('condense_recover', {'reference': '../a.mov', 'broken': 'b.mov', 'fixed': 'c.mov'}),
        ]:
            with self.subTest(name=name, arguments=arguments):
                self.refuse(name, arguments, tool_api.ValidationError)

    def test_config_file_rules(self):
        link = self.dir / 'link.toml'
        link.symlink_to(self.config)
        for value, message in [(str(link), 'condense config must be an existing regular talk.toml'),
                               (str(self.dir / 'absent.toml'), 'condense config must be an existing regular talk.toml'),
                               (self.toml('[[clip]\n', 'bad.toml'), 'condense config is not valid TOML'),
                               (self.toml('out = "out/x.mp4"\n', 'none.toml'), 'at least one [[clip]] table')]:
            with self.subTest(value=value):
                self.refuse('condense_edl', {'config': value}, message=message)

    def test_paths_named_by_the_config_stay_beneath_it(self):
        with tempfile.NamedTemporaryFile(suffix='.mkv', delete=False) as outside:
            self.addCleanup(os.unlink, outside.name)
        (self.dir / 'sub').mkdir()
        (self.dir / 'sub' / 'talk.mkv').write_bytes(b'x')
        (self.dir / 'linked').symlink_to(self.dir / 'sub')
        clip = '[[clip]]\nname = "talk"\nfile = "{}"\n'
        for text, message in [
            (clip.format(outside.name), 'must stay beneath the config directory'),
            (clip.format('sub/../talk.mkv'), 'without traversal'),
            (clip.format('linked/talk.mkv'), 'cannot contain a symlink component'),
            (clip.format('missing.mkv'), 'must be an existing regular file'),
            ('work = "talk.mkv"\n' + clip.format('talk.mkv'), 'must not be a clip file'),
            ('out = "talk.mkv"\n' + clip.format('talk.mkv'), 'must not be a clip file'),
            ('out = "sub/talk.mp4"\n' + clip.format('sub/talk.srt'), None),
            ('work = "../work"\n' + clip.format('talk.mkv'), 'without traversal'),
            ('out = "/tmp/elsewhere.mp4"\n' + clip.format('talk.mkv'), 'must stay beneath the config directory'),
        ]:
            if message is None:  # a clip named where captions would be written
                (self.dir / 'sub' / 'talk.srt').write_bytes(b'x')
                message = 'must not be a clip file'
            with self.subTest(text=text):
                self.refuse('condense_captions', {'config': self.toml(text)}, message=message)

    def test_transcribe_refuses_without_the_registered_model(self):
        with patch.object(tool_api, 'ROOT', self.dir), patch.object(tool_api, 'load_registry_models',
                                                                    return_value={}), \
                patch.object(tool_api, 'condense_config_paths', return_value=self.config):
            (self.dir / 'condense').mkdir()
            (self.dir / 'condense' / '__main__.py').write_text('')
            self.refuse('condense_transcribe', {'config': str(self.config)}, message='run just condense-model')

    def test_recover_rules(self):
        ref, broken = self.dir / 'ref.mov', self.dir / 'broken.mov'
        ref.write_bytes(b'r')
        broken.write_bytes(b'b')
        (self.dir / 'done.mov').write_bytes(b'd')
        base = {'reference': str(ref), 'broken': str(broken)}
        for arguments, message in [
            (dict(base, reference=str(self.dir / 'absent.mov'), fixed=str(self.dir / 'f.mov')),
             'reference must be an existing regular file'),
            (dict(base, fixed=str(self.dir / 'done.mov')), 'fixed must be a fresh path'),
            (dict(base, fixed=str(self.dir / 'nowhere' / 'f.mov')), 'fixed must be a fresh path'),
            (dict(base, fixed=str(broken)), 'fixed must be a fresh path'),
        ]:
            with self.subTest(arguments=arguments):
                self.refuse('condense_recover', arguments, message=message)

    # ----- end to end -----------------------------------------------------------
    def test_events_edl_and_captions_run_on_a_synthetic_talk(self):
        missing = worker_ready()
        if missing:
            self.skipTest(missing)
        gate = '+'.join(f'between(t,{a},{b})' for a, b in SPEECH)
        sound = (f'sine=f=220:r=48000:d={TOTAL}[s];anoisesrc=c=pink:r=48000:a=0.5:d={TOTAL}:seed=1[n];'
                 f"[s][n]amix=inputs=2,volume='if({gate},1,0)':eval=frame")
        ff = ['ffmpeg', '-v', 'error', '-y']
        subprocess.run([*ff, '-f', 'lavfi', '-i', sound, '-f', 'lavfi', '-i', f'testsrc2=s=320x180:r=30:d={TOTAL}',
                        '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'pcm_s16le', '-shortest',
                        str(self.dir / 'talk.mkv')], check=True, timeout=120)
        work = self.dir / 'work'
        work.mkdir()
        subprocess.run([*ff, '-i', str(self.dir / 'talk.mkv'), '-map', '0:a:0', '-vn', '-ac', '1', '-ar', '16000',
                        '-c:a', 'pcm_s16le', str(work / 'talk.16k.wav')], check=True, timeout=120)
        (work / 'talk.dtw.json').write_text(json.dumps(fake_whisper()))
        logs, video_utils = {}, binary()
        with patch.dict(os.environ, {'VIDEO_UTILS_BIN': str(video_utils)}):
            for name in ('condense_events', 'condense_edl', 'condense_captions', 'condense_render', 'condense_publish'):
                reply = tool_api.execute(name, {'config': str(self.config), 'timeout_seconds': 300})
                self.assertEqual((reply['tool'], reply['status'], reply['result']['exit_code']),
                                 (name, 'completed', 0))
                logs[name] = reply['result']['log_tail']
        built = json.loads((work / 'edl.json').read_text())
        self.assertEqual(built['clips'][0]['name'], 'talk')
        self.assertIn('validated by video-utils timeline', logs['condense_edl'])
        srt = (self.dir / 'out' / 'talk.srt').read_text()
        self.assertIn('Hello', srt)
        self.assertTrue((self.dir / 'out' / 'talk.vtt').read_text().startswith('WEBVTT'))
        published = pathlib.Path(logs['condense_publish'].strip().splitlines()[-1].split(':', 1)[0])
        self.assertEqual(published.parent, ROOT / 'artifacts' / 'condense')
        self.addCleanup(shutil.rmtree, published)  # the exact run this test published
        self.assertIn('verified', logs['condense_publish'])
        manifest = json.loads((published / 'manifest.json').read_text())
        self.assertEqual((manifest['timeline']['mapping'], manifest['timeline']['no_time_stretch']), ('edl_v1', False))
        verify = subprocess.run([str(video_utils), 'verify-run', '--timeline', 'edl_v1', str(published)],
                                capture_output=True, timeout=120)
        self.assertEqual(verify.returncode, 0, verify.stderr)

    # ----- MCP readback ---------------------------------------------------------
    def test_real_mcp_lists_57_tools_and_reads_the_new_prompts(self):
        prompts = [name.replace('_', '-') for name in NEW]
        messages = [initialization(), {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
                    request(2, 'tools/list'), request(3, 'prompts/list')]
        messages += [request(10 + i, 'prompts/get', {'name': prompt}) for i, prompt in enumerate(prompts)]
        messages.append(request(30, 'tools/call', {'name': 'condense_edl',
                                                   'arguments': {'config': str(self.dir / 'absent.toml')}}))
        replies, stderr = exchange(messages, timeout=60)
        self.assertEqual(stderr, '')
        tools = {row['name'] for row in replies[1]['result']['tools']}
        self.assertEqual(len(tools), 57)
        names = [row['name'] for row in replies[2]['result']['prompts']]
        self.assertEqual(len(names), 55)
        for offset, name in enumerate(NEW):
            with self.subTest(name=name):
                self.assertIn(name, tools)
                self.assertIn(prompts[offset], names)
                text = replies[3 + offset]['result']['messages'][0]['content']['text']
                self.assertIn(f'MCP tool `{name}` (admitted as tool {49 + offset}, experimental)', text)
        self.assertTrue(replies[-1]['result']['isError'])


if __name__ == '__main__':
    unittest.main()
