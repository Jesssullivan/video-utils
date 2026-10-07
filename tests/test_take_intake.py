"""S3 take_intake lane tests (docs/spec/sprints/TAKE_INTAKE_S3.md sections 8 and 10).

Synthetic fixtures only; generated here with lavfi (and, for the `take` fixture's
musical events, a deterministic stdlib PCM writer). The real take is never
opened or hashed. Media tests skip with reason `ffmpeg_unavailable` only when
FFmpeg/FFprobe cannot be resolved. The end-to-end class is gated by
TAKE_INTAKE_E2E=1.

Run from the worktree root: PYTHONPATH=tests python3 -m unittest test_take_intake -v
Build the sealed e2e fixture: python3 tests/test_take_intake.py build-take OUT.mov
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import time
import unittest
import wave

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / 'scripts'
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import take_intake as ti  # noqa: E402

QUALIFIED_BIN = Path('/nix/store/mv3x2v2pr6pwvwj7cdyh8nci2q1wpnjq-ffmpeg-headless-8.1.2-bin/bin')
LANE = REPO / 'artifacts' / 's2' / 'take_intake'
RESULTS = LANE / 'test-results.json'
E2E_RESULTS = LANE / 'e2e-results.json'
E2E_RECEIPT = REPO / 'docs' / 'agent-notes' / 'sprints' / '20261007-s3' / 'take_intake-e2e.json'
REVIEW = 'synthetic fixture: pink noise only by construction (seed 5186)'
SOURCE_IDENTITIES: list = []


def media_environment() -> dict | None:
    environment = {}
    for name in ('FFMPEG', 'FFPROBE'):
        chosen = os.environ.get(name)
        if not chosen and (QUALIFIED_BIN / name.lower()).is_file():
            chosen = str(QUALIFIED_BIN / name.lower())
        if not chosen or shutil.which(chosen) is None:
            return None
        environment[name] = chosen
    return environment


MEDIA = media_environment()
if MEDIA:
    os.environ.update(MEDIA)


def snapshot(*roots: Path) -> dict:
    found = {}
    for root in roots:
        if not root.exists():
            found[str(root)] = None
            continue
        for path in sorted([root, *root.rglob('*')]):
            stat = path.lstat()
            found[str(path)] = (stat.st_size if path.is_file() else -1, stat.st_mtime_ns)
    return found


def identity(path: Path) -> tuple:
    stat = path.stat()
    return hashlib.sha256(path.read_bytes()).hexdigest(), stat.st_size, stat.st_mtime_ns


def ffmpeg(arguments: list[str], timeout: int = 120):
    command = [MEDIA['FFMPEG'], '-hide_banner', '-nostdin', '-loglevel', 'error', '-y', *arguments]
    subprocess.run(command, check=True, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout)


def build_tiny(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg(['-threads', '1', '-f', 'lavfi', '-i', 'testsrc2=size=320x240:rate=24000/1001:duration=3',
            '-f', 'lavfi', '-i', 'anoisesrc=color=pink:amplitude=0.02:seed=5186:duration=3:sample_rate=44100',
            '-map', '0:v', '-map', '1:a', '-c:v', 'libx264', '-threads', '1', '-c:a', 'aac', '-ac', '1',
            '-fflags', '+bitexact', '-flags:v', '+bitexact', '-flags:a', '+bitexact', '-shortest', str(path)])
    return path


TAKE_SPEC = {
    'duration_seconds': 12.0, 'sample_rate': 44100, 'video': '480x320 testsrc2 24000/1001 fps H.264',
    'noise': 'lavfi anoisesrc pink amplitude 0.02 seed 5186 throughout (fan stand-in)',
    'setup_window': {'span_seconds': [0.0, 5.0], 'thump_at_seconds': 1.5, 'thump_length_seconds': 0.3,
                     'thump_partials_hz': [32.703 * h for h in range(1, 7)]},
    'noise_only_seconds': [5.0, 7.0],
    'click_grid': {'start_seconds': 7.0, 'period_seconds': 0.674, 'count': 8, 'burst': '5 ms 2 kHz Hann, peak 0.5'},
    'phrases': {'count': 2, 'attacks_per_phrase': 4, 'attack_spacing_seconds': 0.337,
                'starts_seconds': [7.0, 9.696], 'note': 'C1-rooted harmonic stack 32.703 Hz, harmonics 1-8 (2-8 decaying faster), 0.3 s',
                'interpretation': ("contract '4-click riff phrases' read as 4 attacks per phrase at half-click spacing so two "
                                   "identical phrases and a click-only rest fit in 7.0-12.0 s")},
    'rest_seconds': [11.0, 12.0],
}


def take_events_pcm(sample_rate: int = 44100, duration: float = 12.0) -> list[float]:
    total = int(round(sample_rate * duration))
    samples = [0.0] * total

    def add(start_seconds, length_seconds, function):
        first = int(round(start_seconds * sample_rate))
        for index in range(int(round(length_seconds * sample_rate))):
            if first + index < total:
                samples[first + index] += function(index / sample_rate)

    def thump(t):
        envelope = min(1.0, t / 0.005) * math.exp(-t / 0.1)
        return envelope * sum(0.25 / h * math.sin(2 * math.pi * 32.703 * h * t) for h in range(1, 7))

    def click(t):
        window = 0.5 - 0.5 * math.cos(2 * math.pi * t / 0.005)
        return 0.5 * window * math.sin(2 * math.pi * 2000.0 * t)

    def note(t):
        attack = min(1.0, t / 0.003)
        return attack * sum(0.3 / h * math.exp(-t * (1 + 0.3 * (h - 1)) / 0.12) * math.sin(2 * math.pi * 32.703 * h * t)
                            for h in range(1, 9))

    add(1.5, 0.3, thump)
    for k in range(8):
        add(7.0 + k * 0.674, 0.005, click)
    for start in (7.0, 9.696):
        for j in range(4):
            add(start + j * 0.337, 0.3, note)
    return samples


def build_take(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    events = path.with_suffix('.events.wav')
    pcm = take_events_pcm()
    with wave.open(str(events), 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(44100)
        handle.writeframes(b''.join(struct.pack('<h', max(-32767, min(32767, int(round(x * 32767))))) for x in pcm))
    ffmpeg(['-threads', '1', '-f', 'lavfi', '-i', 'testsrc2=size=480x320:rate=24000/1001:duration=12',
            '-f', 'lavfi', '-i', 'anoisesrc=color=pink:amplitude=0.02:seed=5186:duration=12:sample_rate=44100',
            '-i', str(events), '-filter_complex', '[1:a][2:a]amix=inputs=2:normalize=0:duration=first[a]',
            '-map', '0:v', '-map', '[a]', '-c:v', 'libx264', '-threads', '1', '-c:a', 'aac', '-ac', '1', '-ar', '44100',
            '-fflags', '+bitexact', '-flags:v', '+bitexact', '-flags:a', '+bitexact', '-t', '12', str(path)], timeout=300)
    events.unlink()
    return path


def needs_media(test):
    return unittest.skipIf(MEDIA is None, 'ffmpeg_unavailable')(test)


class LaneTemp:
    """A per-process lane directory under ignored artifacts/s2/take_intake/tests-<pid>/."""
    base: Path | None = None

    @classmethod
    def get(cls) -> Path:
        if cls.base is None:
            LANE.mkdir(parents=True, exist_ok=True)
            cls.base = LANE / f'tests-{os.getpid()}'
            cls.base.mkdir(exist_ok=True)
        return cls.base

    @classmethod
    def fresh(cls, name: str) -> Path:
        return Path(tempfile.mkdtemp(prefix=name + '-', dir=cls.get()))


def tiny_fixture() -> Path:
    path = LaneTemp.get() / 'fixtures' / 'tiny.mov'
    if not path.exists():
        build_tiny(path)
    return path


def cli(*arguments, timeout=300, cwd=REPO):
    return subprocess.run([sys.executable, str(SCRIPTS / 'take_intake.py'), *arguments], cwd=cwd,
                          stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout,
                          env={**os.environ, **(MEDIA or {})})


def refusal_reason(result) -> str | None:
    try:
        return json.loads(result.stderr.strip().splitlines()[-1]).get('reason')
    except (ValueError, IndexError):
        return None


# ------------------------------------------------------------------ stubs

def stub(name, code, outputs, dependencies=()):
    def run(ctx):
        if any(not ctx.ok(dependency) for dependency in dependencies):
            return ctx.skip(name, dependencies)
        result = ctx.execute(name, [sys.executable, '-c', code, str(ctx.intake_dir)], 30)
        if result['entry']['status'] == 'completed':
            ctx.finish(name, outputs)
    return ti.Stage(name, run, lambda ctx: list(outputs), timeout=30)


WRITE = "import json,sys,pathlib; p=pathlib.Path(sys.argv[1])/{rel!r}; p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps({payload!r}))"
KILL_ONCE = ("import os,signal,sys,pathlib,json; d=pathlib.Path(sys.argv[1]); m=d/'s2.marker'\n"
             "if not m.exists():\n    m.write_text('x'); os.kill(os.getpid(), signal.SIGKILL)\n"
             "(d/'s2.json').write_text(json.dumps({'stub': 's2'}))")


def stub_table(kill_once=False):
    return [stub('s1', WRITE.format(rel='s1.json', payload={'stub': 's1'}), ['intake:s1.json']),
            stub('s2', KILL_ONCE if kill_once else WRITE.format(rel='s2.json', payload={'stub': 's2'}), ['intake:s2.json'], ('s1',)),
            stub('s3', WRITE.format(rel='s3.json', payload={'stub': 's3'}), ['intake:s3.json'], ('s2',)),
            ti.Stage('packet', ti.packet_stage)]


PHRASE_TIMING_STUB = {
    'run_kind': 'real_take', 'phrase_basis': 'automatic_review_span', 'click_reference': {'basis': 'constant_click_grid'},
    'summary': {'phrase_count': 2, 'measured_count': 1, 'abstained_count': 1,
                'abstain_reason_counts': {'fewer_than_4_click_proximal_onsets': 1}},
    'inputs': {'analyzed_input_sha256': None},
    'phrases': [{'phrase_id': 'span-0', 'status': 'measured', 'median_offset_ms': -3.5, 'iqr_ms': [-5.0, -1.0],
                 'click_proximal_onset_count': 4, 'direction': None, 'direction_status': 'withheld_uncalibrated',
                 'span_source_seconds': [7.0, 8.4]},
                {'phrase_id': 'span-1', 'status': 'abstained', 'abstain_reason': 'fewer_than_4_click_proximal_onsets',
                 'direction': None, 'span_source_seconds': [9.7, 11.1]}]}
TRIAGE_STUB = {'denominators': {'total_flags': 5, 'shown': 2, 'suppressed_lower_priority': 1, 'navigation_hidden': 2},
               'view': 'default_review_ordering_not_verdict'}


def packet_table():
    return [stub('flags_triage', WRITE.format(rel='flags-triage.json', payload=TRIAGE_STUB), ['intake:flags-triage.json']),
            stub('phrase_timing', WRITE.format(rel='phrase-timing/r1/phrase-timing.json', payload=PHRASE_TIMING_STUB),
                 ['intake:phrase-timing/r1/phrase-timing.json']),
            ti.Stage('packet', ti.packet_stage)]


def run_stubs(state_root, source, *, kill_once=False, stages=None, interval=(5.2, 6.8), setup=False, family=None):
    before = identity(source)
    code, state = ti.run_intake(source, capture_interval=list(interval) if interval else None, capture_review=REVIEW,
                                interval_reviewed_includes_setup=setup, origin='synthetic_fixture', state_root=state_root,
                                family=family, stages=stages or stub_table(kill_once))
    SOURCE_IDENTITIES.append(before == identity(source))
    return code, state


def statuses(state):
    return {name: entry.get('status') for name, entry in state['stages'].items()}


# ------------------------------------------------------------------ tests

class FamilyIdTests(unittest.TestCase):
    """M2: derivation equals the section 4 formula on 3 fixed vectors."""
    VECTORS = (hashlib.sha256(b'').hexdigest(), 'a' * 64, ti.FIRST_TAKE_SHA256)

    def test_formula_and_identifier(self):
        for vector in self.VECTORS:
            expected = 'take-' + hashlib.sha256(b'video-utils/take-family/v1\x00' + vector.encode('ascii')).hexdigest()[:16]
            self.assertEqual(ti.family_id_for(vector), expected)
            self.assertEqual(ti.corpus.identifier(expected), expected)
            self.assertRegex(expected, r'^take-[0-9a-f]{16}$')
        self.assertEqual(len({ti.family_id_for(v) for v in self.VECTORS}), 3)

    def test_first_take_is_not_a_new_family(self):
        registry = ti.registry_entries(REPO, None)
        with self.assertRaises(ti.IntakeRefusal) as caught:
            ti.resolve_family(ti.FIRST_TAKE_SHA256, None, registry)
        self.assertEqual(caught.exception.code, 'source_already_registered')


@needs_media
class PlanTests(unittest.TestCase):
    """M1 and the plan refusals of M3."""

    def setUp(self):
        self.source = tiny_fixture()
        self.state = LaneTemp.fresh('plan-state')

    def test_plan_byte_identical_three_invocations(self):
        outputs = [cli('plan', str(self.source), '--origin', 'synthetic_fixture', '--state-root', str(self.state)) for _ in range(3)]
        for result in outputs:
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len({result.stdout for result in outputs}), 1)
        plan = json.loads(outputs[0].stdout)
        self.assertEqual(plan['schema_id'], ti.SCHEMA_PLAN)
        self.assertIsNone(plan['corpus_row_draft']['row']['split'])
        self.assertEqual(plan['corpus_row_draft']['split_status'], 'pending_operator_choice')
        self.assertEqual(plan['corpus_row_admissibility']['status'], 'admissible_once_split_chosen')
        self.assertEqual([step['name'] for step in plan['steps']], list(ti.STAGE_NAMES))
        self.assertIn('<CAPTURE_START>', plan['steps'][0]['argv'])
        self.assertEqual(plan['required_operator_inputs']['capture_interval']['required'], True)
        self.assertEqual(ti.absolute_paths_in(plan), [])
        self.assertNotIn('generated_at', outputs[0].stdout)
        self.assertFalse((self.state / '.scratch').exists())

    def test_same_bytes_two_paths(self):
        other = LaneTemp.fresh('copy') / 'tiny.mov'
        shutil.copyfile(self.source, other)
        first = json.loads(cli('plan', str(self.source), '--state-root', str(self.state)).stdout)
        second = json.loads(cli('plan', str(other), '--state-root', str(self.state)).stdout)
        for key in ('take_family_id', 'source', 'corpus_row_draft'):
            self.assertEqual(first[key], second[key], key)

    def assert_refused(self, reason, *arguments, roots=()):
        before = snapshot(self.state, self.source.parent, *roots)
        result = cli('plan', *arguments, '--state-root', str(self.state))
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(refusal_reason(result), reason, result.stderr)
        self.assertEqual(result.stdout, '')
        self.assertEqual(before, snapshot(self.state, self.source.parent, *roots))

    def test_source_missing(self):
        self.assert_refused('source_missing', str(self.source.parent / 'absent.mov'))

    def test_source_is_symlink(self):
        directory = LaneTemp.fresh('link')
        link = directory / 'link.mov'
        link.symlink_to(self.source)
        self.assert_refused('source_is_symlink', str(link), roots=(directory,))

    def test_source_is_derived_artifact(self):
        directory = LaneTemp.fresh('derived')
        target = directory / 'artifacts' / 'runs' / 'r1' / 'tiny.mov'
        target.parent.mkdir(parents=True)
        shutil.copyfile(self.source, target)
        self.assert_refused('source_is_derived_artifact', str(target), roots=(directory,))

    def test_source_in_repository_tracked_path(self):
        repo = LaneTemp.fresh('repo')
        if subprocess.run(['git', 'init', '-q', str(repo)], capture_output=True, timeout=30).returncode:
            self.skipTest('git_unavailable')
        target = repo / 'take.mov'
        shutil.copyfile(self.source, target)
        before = snapshot(self.state, repo)
        with self.assertRaises(ti.IntakeRefusal) as caught:
            ti.build_plan(target, state_root=self.state, repo_root=repo)
        self.assertEqual(caught.exception.code, 'source_in_repository_tracked_path')
        self.assertEqual(before, snapshot(self.state, repo))
        (repo / '.gitignore').write_text('*.mov\n')
        plan = ti.build_plan(target, state_root=self.state, repo_root=repo)
        self.assertTrue(plan['source']['location_check']['ignored'])

    def test_family_collision(self):
        self.assert_refused('family_collision', str(self.source), '--family', 'october5-demo')

    def test_source_already_registered(self):
        root = LaneTemp.fresh('registry-root')
        (root / 'artifacts').mkdir()
        registry = root / 'docs' / 'spec' / 'examples' / 'corpus-split'
        registry.mkdir(parents=True)
        digest = hashlib.sha256(self.source.read_bytes()).hexdigest()
        (registry / 'injected.json').write_text(json.dumps({'records': [{'take_family_id': 'injected-family',
                                                                        'source_sha256': digest}]}))
        before = snapshot(root / 'artifacts', self.source.parent)
        with self.assertRaises(ti.IntakeRefusal) as caught:
            ti.build_plan(self.source, root=root)
        self.assertEqual(caught.exception.code, 'source_already_registered')
        self.assertEqual(before, snapshot(root / 'artifacts', self.source.parent))

    def test_arrangement_source_mismatch(self):
        self.assert_refused('arrangement_source_mismatch', str(self.source), '--arrangement', ti.FIRST_TAKE_ARRANGEMENT)


@needs_media
class RunRefusalTests(unittest.TestCase):
    """Remaining M3 refusals, M4 setup override and M10 source protection."""

    def setUp(self):
        self.source = tiny_fixture()
        self.state = LaneTemp.fresh('run-state')

    def assert_refused(self, reason, *arguments):
        before_source = identity(self.source)
        before = snapshot(self.state, self.source.parent)
        result = cli('run', *arguments, '--state-root', str(self.state))
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(refusal_reason(result), reason, result.stderr)
        self.assertEqual(before, snapshot(self.state, self.source.parent))
        SOURCE_IDENTITIES.append(before_source == identity(self.source))

    def test_capture_interval_required(self):
        self.assert_refused('capture_interval_required', str(self.source), '--capture-review', REVIEW)

    def test_capture_review_required(self):
        self.assert_refused('capture_review_required', str(self.source), '--capture-interval', '5.2', '6.0',
                            '--capture-review', ' ')

    def test_capture_interval_invalid_duration(self):
        self.assert_refused('capture_interval_invalid', str(self.source), '--capture-interval', '5.2', '5.25',
                            '--capture-review', REVIEW)

    def test_capture_interval_invalid_negative(self):
        self.assert_refused('capture_interval_invalid', str(self.source), '--capture-interval', '-1', '0.5',
                            '--capture-review', REVIEW, '--interval-reviewed-includes-setup')

    def test_capture_interval_in_setup_window(self):
        self.assert_refused('capture_interval_in_setup_window', str(self.source), '--capture-interval', '0.2', '1.0',
                            '--capture-review', REVIEW)

    def test_capture_interval_outside_source(self):
        self.assert_refused('capture_interval_outside_source', str(self.source), '--capture-interval', '5.2', '6.0',
                            '--capture-review', REVIEW)

    def test_anchor_requires_arrangement(self):
        self.assert_refused('anchor_requires_arrangement', str(self.source), '--capture-interval', '0.5', '1.5',
                            '--capture-review', REVIEW, '--interval-reviewed-includes-setup', '--anchor-seconds', '7.0',
                            '--anchor-source', 'operator', '--clicks-per-grid-period', '1')

    def test_state_root_invalid(self):
        for value in (str(REPO / 'artifacts' / 'runs' / 'take-intake-x'), str(REPO / 'docs' / 'take-intake-x'), str(REPO / 'artifacts')):
            before = snapshot(self.state, self.source.parent)
            result = cli('run', str(self.source), '--capture-interval', '0.5', '1.5', '--capture-review', REVIEW,
                         '--interval-reviewed-includes-setup', '--state-root', value)
            self.assertEqual(refusal_reason(result), 'state_root_invalid', result.stderr)
            self.assertEqual(before, snapshot(self.state, self.source.parent))
        self.assertFalse((REPO / 'artifacts' / 'runs' / 'take-intake-x').exists())
        self.assertFalse((REPO / 'docs' / 'take-intake-x').exists())

    def test_resume_settings_conflict(self):
        result = cli('run', '--resume', '20261007T000000Z-000000000000', '--features', 'base', '--state-root', str(self.state))
        self.assertEqual(refusal_reason(result), 'resume_settings_conflict', result.stderr)
        self.assertEqual(list(self.state.iterdir()), [])

    def test_setup_override_recorded_in_state_and_packet(self):
        code, state = run_stubs(self.state, self.source, interval=(0.2, 1.0), setup=True)
        self.assertEqual(code, 0)
        intake = self.state / state['take_family_id'] / state['intake_id']
        recorded = json.loads((intake / 'intake.json').read_text())['capture_interval_setup_override']
        packet = json.loads((intake / 'evidence-packet.json').read_text())
        for record in (recorded, packet['capture']['setup_override']):
            self.assertEqual(record['start_seconds'], 0.2)
            self.assertEqual(record['setup_window_seconds'], [0.0, 5.0])
            self.assertTrue(record['operator_flag'])
        self.assertFalse(packet['capture']['noise_only_verified_by_worker'])

    def test_intake_exists_on_rerun(self):
        code, state = run_stubs(self.state, self.source, interval=(0.2, 1.0), setup=True)
        self.assertEqual(code, 0)
        with self.assertRaises(ti.IntakeRefusal) as caught:
            run_stubs(self.state, self.source, interval=(0.2, 1.0), setup=True)
        self.assertEqual(caught.exception.code, 'intake_exists')
        self.assertEqual(caught.exception.details['intake_ids'], [state['intake_id']])


@needs_media
class ResumeTests(unittest.TestCase):
    """M5 resume scenarios with stub stages; M6 demo-invocation binding."""

    def setUp(self):
        self.source = tiny_fixture()
        self.state = LaneTemp.fresh('resume-state')
        reference_state = LaneTemp.fresh('reference-state')
        code, reference = run_stubs(reference_state, self.source, interval=(0.2, 1.0), setup=True)
        self.assertEqual(code, 0)
        self.uninterrupted = statuses(reference)

    def intake_dir(self, state):
        return self.state / state['take_family_id'] / state['intake_id']

    def resume(self, state, kill_once=False):
        before = identity(self.source)
        result = ti.resume_intake(state['intake_id'], state_root=self.state, stages=stub_table(kill_once))
        SOURCE_IDENTITIES.append(before == identity(self.source))
        return result

    def test_a_child_sigkilled_mid_stage(self):
        code, state = run_stubs(self.state, self.source, kill_once=True, interval=(0.2, 1.0), setup=True)
        self.assertEqual(code, 1)
        self.assertEqual(state['stages']['s2']['status'], 'killed')
        self.assertEqual(state['stages']['s2']['signal'], signal.SIGKILL)
        self.assertEqual(state['stages']['s3']['status'], 'skipped_dependency_failed')
        self.assertEqual(state['status'], 'partial')
        code, state = self.resume(state, kill_once=True)
        self.assertEqual(code, 0)
        history = state['resume_history'][-1]
        self.assertEqual(history['skipped_stages'], ['s1'])
        self.assertEqual(history['rerun_stages'], ['s2', 's3'])
        self.assertEqual(statuses(state), self.uninterrupted)

    def test_b_running_with_dead_orchestrator(self):
        code, state = run_stubs(self.state, self.source, interval=(0.2, 1.0), setup=True)
        self.assertEqual(code, 0)
        dead = subprocess.Popen([sys.executable, '-c', 'pass'])
        dead.wait()
        directory = self.intake_dir(state)
        recorded = json.loads((directory / 'intake.json').read_text())
        recorded['stages']['s2'].update(status='running', child_pid=dead.pid)
        recorded['status'] = 'running'
        (directory / 'intake.json').write_text(json.dumps(recorded))
        (directory / '.lock').write_text(json.dumps({'pid': dead.pid}))
        code, state = self.resume(state)
        self.assertEqual(code, 0)
        history = state['resume_history'][-1]
        self.assertEqual(history['lock']['status'], 'stale_taken_over')
        self.assertEqual(history['skipped_stages'], ['s1'])
        self.assertEqual(history['rerun_reasons'], {'s2': 'running'})
        self.assertIn('intake:s2.json', history['displaced'])
        self.assertTrue((directory / 'resume-1' / 'displaced' / 'intake' / 's2.json').is_file())
        self.assertEqual(statuses(state), self.uninterrupted)
        self.assertFalse((directory / '.lock').exists())

    def test_c_tampered_completed_output(self):
        code, state = run_stubs(self.state, self.source, interval=(0.2, 1.0), setup=True)
        (self.intake_dir(state) / 's1.json').write_text('{"tampered": true}')
        code, state = self.resume(state)
        self.assertEqual(code, 0)
        history = state['resume_history'][-1]
        self.assertEqual(history['invalidated'], {'s1': 'output_hash_mismatch'})
        self.assertEqual(history['skipped_stages'], [])
        self.assertEqual(history['rerun_stages'], ['s1', 's2', 's3'])
        displaced = self.intake_dir(state) / 'resume-1' / 'displaced' / 'intake' / 's1.json'
        self.assertEqual(json.loads(displaced.read_text()), {'tampered': True})
        self.assertEqual(statuses(state), self.uninterrupted)

    def test_d_missing_output(self):
        code, state = run_stubs(self.state, self.source, interval=(0.2, 1.0), setup=True)
        (self.intake_dir(state) / 's2.json').unlink()
        code, state = self.resume(state)
        self.assertEqual(code, 0)
        history = state['resume_history'][-1]
        self.assertEqual(history['invalidated'], {'s2': 'output_missing'})
        self.assertEqual(history['skipped_stages'], ['s1'])
        self.assertEqual(statuses(state), self.uninterrupted)

    def test_e_live_lock_refusal(self):
        code, state = run_stubs(self.state, self.source, interval=(0.2, 1.0), setup=True)
        directory = self.intake_dir(state)
        (directory / '.lock').write_text(json.dumps({'pid': os.getpid()}))
        before = snapshot(directory)
        with self.assertRaises(ti.IntakeRefusal) as caught:
            self.resume(state)
        self.assertEqual(caught.exception.code, 'intake_locked')
        self.assertEqual(before, snapshot(directory))
        result = cli('run', '--resume', state['intake_id'], '--state-root', str(self.state))
        self.assertEqual(refusal_reason(result), 'intake_locked')


class DemoBindingTests(unittest.TestCase):
    """M6: exactly-one-candidate binding; zero and two candidates refuse demo_invocation_unbound."""

    def setUp(self):
        self.root = LaneTemp.fresh('binding-root')
        self.invocations = self.root / 'artifacts' / 'demo-invocations'
        self.invocations.mkdir(parents=True)
        self.sha = 'b' * 64

    def add(self, name, sha, interval, pointer=False):
        directory = self.invocations / name
        directory.mkdir()
        receipt = {'invocation_id': name, 'resume_arguments': {'input_sha256': sha, 'capture_interval': interval}}
        if pointer:
            run = self.root / 'artifacts' / 'runs' / 'r' / 'demo-invocations' / name
            run.mkdir(parents=True)
            (run / 'receipt.json').write_text(json.dumps(receipt))
            receipt = {'schema_version': 1, 'invocation_id': name, 'run_dir': str(self.root / 'artifacts/runs/r'),
                       'receipt': str(run / 'receipt.json')}
        (directory / 'receipt.json').write_text(json.dumps(receipt))

    def test_one_zero_two_candidates(self):
        before = ti.list_invocations(self.root)
        self.add('20261007T000000Z-aaaaaaaaaaaa', 'c' * 64, [5.2, 6.8])        # other source
        self.add('20261007T000001Z-bbbbbbbbbbbb', self.sha, [5.0, 6.0])        # other interval
        with self.assertRaises(ti.IntakeRefusal) as zero:
            ti.bind_demo_invocation(self.root, before, self.sha, [5.2, 6.8])
        self.assertEqual(zero.exception.code, 'demo_invocation_unbound')
        self.add('20261007T000002Z-cccccccccccc', self.sha, [5.2, 6.8], pointer=True)
        self.assertEqual(ti.bind_demo_invocation(self.root, before, self.sha, [5.2, 6.8]), '20261007T000002Z-cccccccccccc')
        self.add('20261007T000003Z-dddddddddddd', self.sha, [5.2, 6.8])
        with self.assertRaises(ti.IntakeRefusal) as two:
            ti.bind_demo_invocation(self.root, before, self.sha, [5.2, 6.8])
        self.assertEqual(two.exception.details['candidates'], 2)
        prior = ti.list_invocations(self.root)
        with self.assertRaises(ti.IntakeRefusal):
            ti.bind_demo_invocation(self.root, prior, self.sha, [5.2, 6.8])


@needs_media
class PacketTests(unittest.TestCase):
    """M7 packet completeness, M8 V6 draft, M9 no absolute host paths."""

    @classmethod
    def setUpClass(cls):
        cls.source = tiny_fixture()
        cls.state = LaneTemp.fresh('packet-state')
        code, cls.result = run_stubs(cls.state, cls.source, stages=packet_table(), interval=(0.2, 1.0), setup=True)
        cls.code = code
        cls.directory = cls.state / cls.result['take_family_id'] / cls.result['intake_id']
        cls.packet = json.loads((cls.directory / 'evidence-packet.json').read_text())
        cls.draft = json.loads((cls.directory / 'tin-5186-message-draft.json').read_text())

    def test_m7_packet_keys_and_unknowns(self):
        required = ('intake', 'stage_hashes', 'signal_versions_consumed', 'tool_versions', 'capture', 'phrase_timing',
                    'phrase_anchor', 'flags_triage', 'deliverables', 'claims', 'unknowns', 'corpus_row_draft')
        present = [key for key in required if key in self.packet]
        self.assertEqual(present, list(required))
        for name, row in ti.UNKNOWNS.items():
            self.assertIn(name, self.packet['unknowns'])
            self.assertTrue(self.packet['unknowns'][name]['reason'])
        self.assertEqual(self.packet['phrase_timing']['direction_status'], 'withheld_uncalibrated')
        self.assertIsNone(self.packet['phrase_timing']['ahead_behind_label'])
        self.assertEqual((self.packet['phrase_timing']['phrases_measured'], self.packet['phrase_timing']['phrases_total']), (1, 2))
        self.assertEqual((self.packet['flags_triage']['shown'], self.packet['flags_triage']['total']), (2, 5))
        self.assertFalse(self.packet['phrase_anchor']['adopted'])
        self.assertIsNone(self.packet['corpus_row_draft']['row']['split'])
        self.assertEqual({claim['class'] for claim in self.packet['claims']}, set(ti.CLAIM_CLASSES))
        self.assertEqual(self.packet['intake']['stage_counts']['completed_over_planned'], '3/3')
        self.assertEqual(self.packet['unknowns']['default_adoption']['value'], 'none')

    def test_m8_v6_draft(self):
        self.assertEqual(set(self.draft), ti.DRAFT_KEYS)
        self.assertEqual(self.draft['status'], 'draft_not_sent')
        self.assertIsNone(self.draft['split'])
        self.assertEqual(ti.draft_violations(self.draft), [])
        self.assertLessEqual(len(json.dumps(self.draft, sort_keys=True).encode()), 4096)
        text = json.dumps(self.draft)
        self.assertNotIn(self.result['intake_id'], text)
        self.assertNotIn(self.result['source']['sha256'], text)
        controls = {'absolute_path': ('note', 'see /Users/someone/take.txt'),
                    'hex64': ('note', 'f' * 64), 'media_file_name': ('note', 'clip.wav'),
                    'src_or_art_id': ('note', 'src_0123abcd'), 'seconds_timestamp_or_span': ('note', 'at 12.5 s'),
                    'key_set_not_closed': ('capture_interval', 'x')}
        for label, (key, value) in controls.items():
            planted = dict(self.draft, **{key: value})
            self.assertIn(label, ti.draft_violations(planted), label)
        span = dict(self.draft, probe_class=dict(self.draft['probe_class'], channel_count=[5.2, 6.8]))
        self.assertIn('seconds_timestamp_or_span', ti.draft_violations(span))

    def test_m9_no_absolute_paths(self):
        for name in ('intake.json', 'evidence-packet.json', 'tin-5186-message-draft.json'):
            text = (self.directory / name).read_text()
            self.assertEqual(ti.ABS_PATH.findall(text), [], name)
            for fragment in (str(REPO), str(self.source), '/Users/', '/private/', '/nix/store'):
                self.assertNotIn(fragment, text, name)
        replay = json.loads((self.directory / 'replay-arguments.local.json').read_text())
        self.assertEqual(replay['scope'], 'local only; never copied into the packet or draft')

    def test_packet_cli_refuses_pipeline_run_dir(self):
        result = cli('packet', str(self.state))
        self.assertEqual(refusal_reason(result), 'not_an_intake_run_dir')
        rebuilt = cli('packet', str(self.directory))
        self.assertEqual(rebuilt.returncode, 0, rebuilt.stderr)

    def test_low_register_guard_patterns(self):
        documents = [{'commands': [['/x/ffmpeg', '-af', 'highpass=f=80'], ['/x/ffmpeg', '-af', 'equalizer=f=60:t=q:w=1:g=-30'],
                                   ['/x/ffmpeg', '-af', 'lowpass=f=40'], ['/x/ffmpeg', '-af', 'equalizer=f=160:t=q:w=0.7:g=2']]}]
        guard = ti.low_register_guard(documents)
        self.assertEqual(guard['filter_graphs_inspected'], 4)
        self.assertEqual(guard['violation_kinds'], ['highpass', 'lowpass_below_60_hz', 'mains_notch'])
        self.assertEqual(ti.low_register_guard([{'c': [['ffmpeg', '-af', 'equalizer=f=160:g=2']]}])['violations'], 0)


@unittest.skipUnless(os.environ.get('TAKE_INTAKE_E2E') == '1', 'e2e_gated_set_TAKE_INTAKE_E2E_1')
@needs_media
class EndToEndTests(unittest.TestCase):
    """M10/M11/M12: one sealed synthetic `take` fixture through `run` in an isolated copied ROOT."""

    PREDICTED = {'demo': 'completed', 'flags_triage': 'completed', 'arrangement_reference': 'abstained_no_reference',
                 'arrangement_markers': 'abstained_no_reference', 'phrase_anchor': 'abstained_no_reference',
                 'phrase_timing': 'completed', 'marked_video': 'completed',
                 'marked_compact': 'abstained_arrangement_markers_required', 'share_export': 'completed',
                 'packet': 'completed'}

    def test_sealed_take_run(self):
        started = time.monotonic()
        stamp = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
        base = LANE / f'e2e-{stamp}'
        fixture = Path(os.environ['TAKE_INTAKE_E2E_FIXTURE']) if os.environ.get('TAKE_INTAKE_E2E_FIXTURE') else build_take(base / 'fixture' / 'take.mov')
        expected_sha = os.environ.get('TAKE_INTAKE_E2E_FIXTURE_SHA256')
        fixture_identity = identity(fixture)
        if expected_sha:
            self.assertEqual(fixture_identity[0], expected_sha, 'sealed fixture changed')
        root = base / 'root'
        for name in ('scripts', 'profiles', 'program'):
            shutil.copytree(REPO / name, root / name, ignore=shutil.ignore_patterns('__pycache__'))
        arguments = ['run', str(fixture), '--capture-interval', '5.2', '6.8', '--capture-review', REVIEW,
                     '--features', 'base', '--origin', 'synthetic_fixture']
        result = subprocess.run([sys.executable, str(root / 'scripts' / 'take_intake.py'), *arguments], cwd=root,
                                stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=1800,
                                env={**os.environ, **MEDIA})
        after = identity(fixture)
        summary = json.loads(result.stdout)
        intake = root / 'artifacts' / 'take-intake' / summary['take_family_id'] / summary['intake_id']
        state = json.loads((intake / 'intake.json').read_text())
        packet = json.loads((intake / 'evidence-packet.json').read_text())
        draft = json.loads((intake / 'tin-5186-message-draft.json').read_text())
        observed = statuses(state)
        scoring = {name: {'predicted': self.PREDICTED[name], 'observed': observed.get(name),
                          'score': 'as_predicted' if observed.get(name) == self.PREDICTED[name] else 'differs',
                          'reason': state['stages'][name].get('reason')}
                   for name in ti.STAGE_NAMES}
        timing = packet['phrase_timing']
        payload = {
            'schema_version': 1, 'receipt': 'take_intake sealed end-to-end synthetic run (TAKE_INTAKE_S3 section 11)',
            'fixture': {'kind': 'take', 'sha256': fixture_identity[0], 'size_bytes': fixture_identity[1], 'spec': TAKE_SPEC,
                        'origin': 'synthetic_fixture_not_derived_from_a_real_take'},
            'arguments': ['run', '<FIXTURE>', *arguments[2:]],
            'exit_code': result.returncode, 'intake_status': state['status'], 'take_family_id': state['take_family_id'],
            'stage_scoring': scoring,
            'stage_counts': packet['intake']['stage_counts'],
            'predicted_counts': {'completed': 6, 'abstained': 4, 'failed': 0, 'planned': 10},
            'run_demo_stage_status': packet['intake']['run_demo_stage_status'],
            'measurements': packet['measurements'],
            'phrase_timing': {'phrases_measured': timing.get('phrases_measured'), 'phrases_total': timing.get('phrases_total'),
                              'abstain_reason_counts': timing.get('abstain_reason_counts'),
                              'direction_status': timing.get('direction_status')},
            'flags_triage': {'shown': packet['flags_triage']['shown'], 'total': packet['flags_triage']['total']},
            'low_register_guard': packet['low_register_guard'],
            'signal_versions_consumed': [{k: row.get(k) for k in ('artifact', 'status')} for row in packet['signal_versions_consumed']],
            'source_unchanged': {'invocations': 1, 'unchanged': int(after == fixture_identity),
                                 'intake_source_checks': packet['intake']['source_checks']},
            'v6_draft_violations': ti.draft_violations(draft),
            'absolute_paths_in_packet_and_state': len(ti.absolute_paths_in(packet)) + len(ti.absolute_paths_in(state)),
            'elapsed_seconds': round(time.monotonic() - started, 1),
            'tool_versions': {key: packet['tool_versions'][key] for key in ('repository', 'python_version', 'ffmpeg', 'ffprobe', 'profile')},
            'interpretation_boundary': ('A synthetic fixture result says the orchestration, refusals, resume and packet work; '
                                        'it says nothing about restoration quality, detection accuracy or musical correctness '
                                        'on the real second take. Everything audible is needs_listening.'),
            'retained_lane_dir': f'artifacts/s2/take_intake/{base.name}',
        }
        payload = ti.Scrubber(root, fixture).deep(payload)
        E2E_RESULTS.write_text(json.dumps(payload, indent=2) + '\n')
        # The tracked receipt is sealed; reruns write only the ignored lane copy.
        if os.environ.get('TAKE_INTAKE_E2E_RESEAL') == '1':
            E2E_RECEIPT.write_text(json.dumps(payload, indent=2) + '\n')
        self.assertEqual(after, fixture_identity)
        self.assertEqual(ti.draft_violations(draft), [])
        self.assertEqual(payload['absolute_paths_in_packet_and_state'], 0)
        self.assertTrue(all(row['unchanged'] for row in state['source_checks']))


def tearDownModule():
    try:
        LANE.mkdir(parents=True, exist_ok=True)
        RESULTS.write_text(json.dumps({'source_identity_checks': {'unchanged': sum(SOURCE_IDENTITIES),
                                                                  'total': len(SOURCE_IDENTITIES)},
                                       'media': 'available' if MEDIA else 'ffmpeg_unavailable',
                                       'real_take_opened': False}, indent=2) + '\n')
    finally:
        if LaneTemp.base is not None and os.environ.get('TAKE_INTAKE_KEEP') != '1':
            shutil.rmtree(LaneTemp.base, ignore_errors=True)


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == 'build-take':
        if MEDIA is None:
            raise SystemExit('ffmpeg_unavailable')
        out = build_take(Path(sys.argv[2]).resolve())
        print(json.dumps({'fixture': out.name, 'sha256': hashlib.sha256(out.read_bytes()).hexdigest(),
                          'size_bytes': out.stat().st_size, 'spec': TAKE_SPEC}, indent=2))
    else:
        unittest.main()
