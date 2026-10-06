"""Independent signal-ownership oracles; no audio, provenance or subprocess I/O."""
import importlib.util
from pathlib import Path
import signal
import unittest
from unittest.mock import patch


FILE = Path(__file__).resolve().parents[1] / 'docs/agent-notes/2026-10-06-nr8-nr10-comparison.py'
SPEC = importlib.util.spec_from_file_location('nr_pair_independent_audit', FILE)
worker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(worker)


class SignalOwnershipOracles(unittest.TestCase):
    def setUp(self):
        self.previous_handler = signal.getsignal(signal.SIGALRM)
        self.previous_timer = signal.getitimer(signal.ITIMER_REAL)
        if self.previous_timer != (0., 0.):
            self.skipTest('existing caller timer belongs to another operation')

    def tearDown(self):
        if self.previous_timer == (0., 0.):
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, self.previous_handler)

    def test_existing_interval_timer_and_handler_are_preserved_without_input_access(self):
        def external_handler(signum, frame):
            self.fail('external timer must not fire in this bounded fixture')

        signal.signal(signal.SIGALRM, external_handler)
        signal.setitimer(signal.ITIMER_REAL, 10, 7)
        with patch.object(worker, 'pinned') as pinned, patch.object(worker, 'load_module') as loader:
            result = worker.run('/never-read', '0' * 64, '/never-written')
        pinned.assert_not_called()
        loader.assert_not_called()
        self.assertIs(signal.getsignal(signal.SIGALRM), external_handler)
        remaining, interval = signal.getitimer(signal.ITIMER_REAL)
        self.assertGreater(remaining, 8)
        self.assertLessEqual(remaining, 10)
        self.assertEqual(interval, 7)
        self.assertEqual(result['status'], 'incomplete')
        self.assertIn('external alarm', result['error']['message'])
        self.assertFalse(result['comparison_delivery_eligible'])
        self.assertEqual(result['owned_subprocesses'], [])

    def test_owned_timer_precedes_first_hash_and_restores_custom_external_handler(self):
        def external_handler(signum, frame):
            self.fail('saved external handler must never be invoked')

        signal.signal(signal.SIGALRM, external_handler)
        observations = []

        def stop_before_read(*args):
            observations.append((signal.getitimer(signal.ITIMER_REAL), signal.getsignal(signal.SIGALRM)))
            raise worker.ComparisonError('inert hash-boundary stop; no bytes read')

        with patch.object(worker, 'pinned', side_effect=stop_before_read), patch.object(worker, 'load_module') as loader:
            result = worker.run('/never-read', '0' * 64, '/never-written')
        loader.assert_not_called()
        self.assertEqual(len(observations), 1)
        timer, installed_handler = observations[0]
        self.assertGreater(timer[0], 0)
        self.assertLessEqual(timer[0], worker.PROCESS_SECONDS)
        self.assertEqual(timer[1], 0)
        self.assertIsNot(installed_handler, external_handler)
        self.assertIs(signal.getsignal(signal.SIGALRM), external_handler)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0., 0.))
        self.assertEqual(result['error']['message'], 'inert hash-boundary stop; no bytes read')
        self.assertFalse(result['protected_after_verified'])
        self.assertFalse(result['comparison_delivery_eligible'])
        self.assertEqual(result['candidates'], [])


if __name__ == '__main__':
    unittest.main()
