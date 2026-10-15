"""S4 admission A: freeze the first 46 descriptors and admit the two Rust timeline tools.

Tools 47-48 are ``timeline_validate`` and ``timeline_map`` (docs/spec/CONDENSE_TOOL_CONTRACT.md). Both run this
checkout's ``video-utils timeline`` binary and share the edl-timeline skill and MCP prompt. The end-to-end cases
build the binary with cargo when it is absent and skip, with that reason, when cargo is unavailable.

Synthetic EDLs only; no recording, run or repository artifact is read or written.
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

# tools[:46] as recorded by tests/test_s3g_tool_admission.py; this admission appends after index 45 and changes none.
ADMITTED_46_SHA256 = 'ed2494b5e259ffac5d98ab554ac8e0b55b21119c948f49829a31170a5c7e6a4b'
ADMITTED_46_ASCII_SHA256 = '15852f750b668e3ea51206dc00bfdac35dd3364e50288138ee30f0d7e171ebb1'
# tools[:48] as admitted here, same two serializers (recorded for the next freeze).
ADMITTED_48_SHA256 = '7489cc74678cba2d2de7317a517964dfbde339b4d2004a1a9da9f8d93c884cda'
ADMITTED_48_ASCII_SHA256 = '39bb9db5d08fae1eb6c5699d6933a6362c4c2ab79f2532ca96e29a2f633a5c09'
SKILL = '.agents/skills/edl-timeline/SKILL.md'
SKILL_SHA256 = '54aec7c826b71d702dc615edd71ae836002cfd4a5267f78ded05e8d9cd7078a7'
HOOK = '**Hook:** MCP tools `timeline_validate` and `timeline_map` (admitted as tools 47 and 48, implemented)'
READ_ONLY = {'readOnlyHint': True, 'destructiveHint': False, 'idempotentHint': True, 'openWorldHint': False}
NEW = {'timeline_validate': ({'edl'}, 'rust_timeline_validation_receipt'),
       'timeline_map': ({'edl', 'queries'}, 'rust_timeline_time_map')}


def digest(tools, count, ascii_only):
    data = json.dumps(tools[:count], sort_keys=True, separators=(',', ':'), ensure_ascii=ascii_only)
    return hashlib.sha256(data.encode()).hexdigest()


def edl(frames=60):
    """One 4 s speech clip at 2x: 60 frames at 30 fps."""
    return {'fps': 30, 'rules': {}, 'expected_total_s': frames / 30,
            'clips': [{'name': 'a', 'duration': 4.0, 'speed': 2.0, 'shift': 0.0, 'welcome': None,
                       'expected_s': frames / 30, 'out_s_by_kind': {'speech': frames / 30},
                       'segments': [{'src': 'a', 'inp': 0.0, 'out': 4.0, 'speed': 2.0, 'kind': 'speech',
                                     'frames': frames, 'out_dur': frames / 30}]}]}


def binary():
    """The checkout's debug build, built here when absent; None when cargo is unavailable."""
    path = ROOT / 'target/debug/video-utils'
    if not path.is_file():
        cargo = shutil.which('cargo')
        if cargo is None:
            return None
        built = subprocess.run([cargo, 'build', '--locked', '-j', '1', '-q'], cwd=ROOT, capture_output=True,
                               timeout=900, stdin=subprocess.DEVNULL, env=dict(os.environ, CARGO_BUILD_JOBS='1'))
        if built.returncode or not path.is_file():
            return None
    return path


class S4AToolAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = tempfile.TemporaryDirectory()
        cls.dir = pathlib.Path(cls.scratch.name)
        cls.edl = cls.dir / 'edl.json'
        cls.edl.write_text(json.dumps(edl()))
        cls.bad = cls.dir / 'bad.json'
        broken = edl()
        broken['clips'][0]['segments'][0]['src'] = 'b'  # a segment that names another clip
        cls.bad.write_text(json.dumps(broken))
        cls.binary = binary()

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def need_binary(self):
        if self.binary is None:
            self.skipTest('cargo unavailable: the video-utils binary could not be built')

    # ----- registry freeze ----------------------------------------------------
    def test_first_46_descriptors_frozen_and_two_appended(self):
        tools = tool_api.descriptors()
        self.assertEqual(len(tools), 48)
        self.assertEqual(digest(tools, 46, False), ADMITTED_46_SHA256)
        self.assertEqual(digest(tools, 46, True), ADMITTED_46_ASCII_SHA256)
        self.assertEqual(digest(tools, 48, False), ADMITTED_48_SHA256)
        self.assertEqual(digest(tools, 48, True), ADMITTED_48_ASCII_SHA256)
        self.assertEqual([tool['name'] for tool in tools[46:]], list(NEW))
        self.assertEqual(len({tool['name'] for tool in tools}), 48)

    def test_freeze_hashes_match_the_s3g_record(self):
        import test_s3g_tool_admission as s3g
        self.assertEqual((s3g.ADMITTED_46_SHA256, s3g.ADMITTED_46_ASCII_SHA256),
                         (ADMITTED_46_SHA256, ADMITTED_46_ASCII_SHA256))

    def test_admitted_descriptors_equal_the_draft(self):
        draft = json.loads((ROOT / 'program/tool-drafts/condense.json').read_text(encoding='utf-8'))['tools']
        tools = tool_api.descriptors()
        self.assertEqual(tools[46:48], draft[:2])
        for tool in tools[46:48]:
            self.assertEqual(list(tool), list(tools[0]))

    def test_descriptors_closed_bounded_read_only_and_skill_pinned(self):
        data = (ROOT / SKILL).read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), SKILL_SHA256)
        text = data.decode('utf-8')
        self.assertTrue(text.startswith('---\nname: edl-timeline\ndescription: '))
        self.assertIn(HOOK, text)
        for stale in ('DRAFT', 'draft', 'Not admitted', 'not admitted'):
            self.assertNotIn(stale, text)
        for name, (required, evidence) in NEW.items():
            with self.subTest(name=name):
                info = tool_api.descriptor(name)
                schema = info['inputSchema']
                tool_api.validate_schema(schema)
                self.assertIs(schema['additionalProperties'], False)
                self.assertEqual(set(schema['required']), required)
                timeout = schema['properties']['timeout_seconds']
                self.assertEqual((timeout['minimum'], timeout['maximum'], timeout['default']), (1, 300, 60))
                self.assertEqual((info['implementation_status'], info['evidence_kind']), ('implemented', evidence))
                self.assertEqual(info['annotations'], READ_ONLY)
                self.assertEqual(info['skill'], SKILL)
                self.assertFalse(info['dependencies']['enforced'])
                self.assertNotIn(''.join(('/Us', 'ers/')), json.dumps(info))

    # ----- refusals before any worker -----------------------------------------
    def test_invalid_arguments_refuse_before_any_worker(self):
        edl_path = str(self.edl)
        cases = [
            ('timeline_validate', {}),
            ('timeline_validate', {'edl': ''}),
            ('timeline_validate', {'edl': 'a/../edl.json'}),
            ('timeline_validate', {'edl': 'https://example.invalid/edl.json'}),
            ('timeline_validate', {'edl': 'a\\edl.json'}),
            ('timeline_validate', {'edl': edl_path, 'timeout_seconds': 301}),
            ('timeline_validate', {'edl': edl_path, 'output': 'x'}),
            ('timeline_map', {'edl': edl_path}),
            ('timeline_map', {'edl': edl_path, 'queries': []}),
            ('timeline_map', {'edl': edl_path, 'queries': [{'op': 'to_out', 'clip': 'a', 'source_s': 0.0}] * 129}),
            ('timeline_map', {'edl': edl_path, 'queries': [{'op': 'warp', 'clip': 'a', 'source_s': 1.0}]}),
            ('timeline_map', {'edl': edl_path, 'queries': [{'op': 'to_out', 'clip': 'a'}]}),
            ('timeline_map', {'edl': edl_path, 'queries': [{'op': 'to_src', 'output_s': 1.0, 'clip': 'a'}]}),
            ('timeline_map', {'edl': edl_path, 'queries': [{'op': 'row', 'clip': 'a', 'source_s': 1.0, 'snap': True}]}),
            ('timeline_map', {'edl': edl_path, 'queries': [{'op': 'to_src', 'output_s': -1.0}]}),
        ]
        for name, arguments in cases:
            with self.subTest(name=name, arguments=str(arguments)[:80]), \
                    patch.object(tool_api, 'run_timeline_tool') as worker:
                with self.assertRaises(tool_api.ValidationError):
                    tool_api.execute(name, arguments)
                worker.assert_not_called()

    def test_symlink_missing_and_oversized_edl_refuse_without_running_the_binary(self):
        link = self.dir / 'link.json'
        if not link.exists():
            link.symlink_to(self.edl)
        for value in (str(link), str(self.dir / 'absent.json'), str(self.dir)):
            with self.subTest(value=value), patch.object(subprocess, 'run') as run:
                with self.assertRaisesRegex(tool_api.ToolError, 'timeline edl must be an existing regular file'):
                    tool_api.execute('timeline_validate', {'edl': value})
                run.assert_not_called()

    def test_absent_binary_refuses_typed(self):
        with patch.object(tool_api, 'ROOT', self.dir), patch.dict(os.environ, {'VIDEO_UTILS_BIN': ''}):
            with self.assertRaisesRegex(tool_api.ToolError, 'video-utils binary unavailable: run just cli'):
                tool_api.video_utils_binary()

    # ----- real runs ------------------------------------------------------------
    def test_validate_returns_the_rust_receipt(self):
        self.need_binary()
        with patch.dict(os.environ, {'VIDEO_UTILS_BIN': str(self.binary)}):
            reply = tool_api.execute('timeline_validate', {'edl': str(self.edl)})
        result = reply['result']
        self.assertEqual((reply['tool'], reply['status'], reply['implementation_status']),
                         ('timeline_validate', 'completed', 'implemented'))
        self.assertEqual((result['status'], result['total_frames'], result['fps'], result['clips']), ('ok', 60, 30, 1))
        self.assertEqual(result['edl_sha256'], hashlib.sha256(self.edl.read_bytes()).hexdigest())

    def test_map_answers_every_query_in_order(self):
        self.need_binary()
        queries = [{'op': 'to_out', 'clip': 'a', 'source_s': 1.0}, {'op': 'to_out', 'clip': 'a', 'source_s': 5.0},
                   {'op': 'to_src', 'output_s': 1.0}, {'op': 'row', 'clip': 'a', 'source_s': 3.9}]
        with patch.dict(os.environ, {'VIDEO_UTILS_BIN': str(self.binary)}):
            results = tool_api.execute('timeline_map', {'edl': str(self.edl), 'queries': queries})['result']['results']
        self.assertEqual(results[0], 0.5)
        self.assertIsNone(results[1])
        self.assertEqual((results[2]['source_s'], results[2]['segment_index']), (2.0, 0))
        self.assertEqual((results[3]['kind'], results[3]['start_frame'], results[3]['end_frame']), ('speech', 0, 60))

    def test_invalid_edl_and_unknown_clip_relay_the_typed_reason(self):
        self.need_binary()
        with patch.dict(os.environ, {'VIDEO_UTILS_BIN': str(self.binary)}):
            with self.assertRaises(tool_api.ToolError) as caught:
                tool_api.execute('timeline_validate', {'edl': str(self.bad)})
            receipt = caught.exception.receipt
            self.assertEqual((receipt['status'], receipt['tool']), ('refused', 'timeline_validate'))
            self.assertRegex(receipt['reason'], r'^[a-z_]+$')
            self.assertEqual(str(caught.exception), f'timeline_validate refused: {receipt["reason"]}')
            with self.assertRaises(tool_api.ToolError) as caught:
                tool_api.execute('timeline_map', {'edl': str(self.edl),
                                                  'queries': [{'op': 'to_out', 'clip': 'b', 'source_s': 1.0}]})
            self.assertEqual(caught.exception.receipt['reason'], 'clip_unknown')

    # ----- MCP readback ---------------------------------------------------------
    def test_real_mcp_lists_48_tools_one_shared_prompt_and_reads_the_skill(self):
        messages = [initialization(), {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
                    request(2, 'tools/list'), request(3, 'prompts/list'),
                    request(4, 'prompts/get', {'name': 'edl-timeline'}),
                    request(5, 'tools/call', {'name': 'timeline_map',
                                              'arguments': {'edl': str(self.edl), 'queries': [{'op': 'to_out'}]}})]
        replies, stderr = exchange(messages, timeout=60)
        self.assertEqual(stderr, '')
        tools = {row['name']: row for row in replies[1]['result']['tools']}
        self.assertEqual(len(tools), 48)
        names = [row['name'] for row in replies[2]['result']['prompts']]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(len(names), 46)
        self.assertIn('edl-timeline', names)
        for name in NEW:
            with self.subTest(name=name):
                self.assertEqual(tools[name]['annotations'], READ_ONLY)
                self.assertEqual(tools[name]['_meta']['video-utils']['skill'], SKILL)
        prompt = replies[3]['result']['messages'][0]['content']['text']
        self.assertIn(HOOK, prompt)
        self.assertEqual(replies[4]['error']['code'], -32602)  # schema/per-op refusal before any worker


if __name__ == '__main__':
    unittest.main()
