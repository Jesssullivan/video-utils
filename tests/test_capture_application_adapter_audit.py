"""Independent new-adapter audit fixtures; no media/model/host work."""
import importlib.util
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location('independent_application_adapter', ROOT / 'scripts/capture_application_adapter.py')
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class AdapterIndependentAuditTests(unittest.TestCase):
    def test_initial_identity_failure_and_signal_refusal_retains_wait_and_receipt(self):
        class UnavailableInspector:
            def identity(self, pid):
                raise worker.InspectionError('inert initial identity unavailable')
        spawned = []
        original_popen = worker.subprocess.Popen
        def recorded(*args, **kwargs):
            process = original_popen(*args, **kwargs)
            identity = worker.ProcessInspector().identity(process.pid)
            self.assertIsNotNone(identity)
            spawned.append((process, identity, process.wait))
            return process
        with tempfile.TemporaryDirectory(prefix='adapter-initial-audit-') as name:
            root = Path(name)
            code = root / 'owned-sleeping-worker.py'
            code.write_text('import time; time.sleep(30)\n')
            adapter = worker.ApplicationAdapter(root, worker_path=code, inspector=UnavailableInspector())
            arguments = {'input': 'inert-source', 'authoring_dir': 'inert-authoring',
                         'receipt_sha256': 'a' * 64, 'timeout_seconds': 12}
            def recorded_and_refused(*args, **kwargs):
                process = recorded(*args, **kwargs)
                process.kill = unittest.mock.Mock(side_effect=PermissionError('inert initial direct signal refusal'))
                process.wait = unittest.mock.Mock(wraps=spawned[-1][2])
                return process
            try:
                with patch.object(worker.subprocess, 'Popen', side_effect=recorded_and_refused):
                    try:
                        adapter.run(arguments)
                    except BaseException as error:
                        caught = error
                    else:
                        self.fail('initial failed ownership observation cannot succeed')
                process = spawned[0][0]
                self.assertTrue(process.wait.called, 'initial identity refusal must still attempt bounded direct wait')
                self.assertIsInstance(caught, worker.AdapterError)
                self.assertIsNotNone(caught.receipt, 'failed startup must preserve a terminal diagnostic receipt')
            finally:
                for process, identity, original_wait in spawned:
                    current = worker.ProcessInspector().identity(process.pid)
                    if current and current['birth'] == identity['birth'] and current['pgid'] == identity['pgid'] and current['sid'] == identity['sid']:
                        os.kill(process.pid, signal.SIGKILL)
                    original_wait(timeout=2)

    def test_receipt_failure_after_early_cleanup_reuses_one_absolute_end(self):
        class Inspector:
            def identity(self, pid):
                return {'pid': pid, 'ppid': 1, 'pgid': pid, 'sid': pid,
                        'birth': ['inert_control_flow_fixture', 1], 'state': 'S'}
            def snapshot(self, end):
                raise worker.InspectionError('inert early inspection failure')
        class Adapter(worker.ApplicationAdapter):
            ends = []
            receipt_attempts = 0
            def cleanup(self, process, inventory, end, events):
                self.ends.append(end)
                process.returncode = -9
                return 'unknown'
            def inventory_receipt(self, directory, inventory, data):
                self.receipt_attempts += 1
                if self.receipt_attempts == 1:
                    raise OSError('inert metadata publication failure after cleanup')
                return super().inventory_receipt(directory, inventory, data)
        with tempfile.TemporaryDirectory(prefix='adapter-budget-audit-') as name:
            root = Path(name)
            code = root / 'inert-never-executed.py'
            code.write_text('# metadata fixture; never executed\n')
            process = SimpleNamespace(pid=99321, returncode=None)
            adapter = Adapter(root, worker_path=code, inspector=Inspector())
            arguments = {'input': 'inert-source', 'authoring_dir': 'inert-authoring',
                         'receipt_sha256': 'a' * 64, 'timeout_seconds': 12}
            with patch.object(worker.subprocess, 'Popen', return_value=process):
                with self.assertRaises(worker.AdapterError) as caught:
                    adapter.run(arguments)
            self.assertEqual(len(adapter.ends), 2)
            self.assertEqual(adapter.ends[0], adapter.ends[1],
                             'fallback failure must not reset the five-second cleanup allowance')
            self.assertEqual(adapter.receipt_attempts, 2)
            self.assertIsNotNone(caught.exception.receipt)

    def test_inspection_and_direct_signal_failure_still_attempts_owned_root_wait(self):
        process = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'],
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, start_new_session=True)
        inspector = worker.ProcessInspector()
        identity = inspector.identity(process.pid)
        self.assertIsNotNone(identity)
        self.assertEqual(identity['pgid'], process.pid)
        self.assertEqual(identity['sid'], process.pid)
        inventory = worker.Inventory(inspector, identity)
        events = []
        original_wait = process.wait
        try:
            with patch.object(inspector, 'snapshot', side_effect=worker.InspectionError('inert unavailable inspection')), \
                 patch.object(process, 'kill', side_effect=PermissionError('inert direct signal refusal')), \
                 patch.object(process, 'wait', wraps=original_wait) as wait:
                try:
                    outcome = worker.ApplicationAdapter(inspector=inspector).cleanup(
                        process, inventory, time.monotonic() + .05, events)
                except BaseException as error:
                    outcome = error
                self.assertTrue(wait.called, 'a direct signal refusal must not bypass bounded root wait')
                self.assertEqual(outcome, 'unknown', 'unproved cleanup must retain uncertainty')
                self.assertTrue(inventory.incomplete)
        finally:
            # Only this fixture's recorded fresh session/direct child is ours.
            current = inspector.identity(process.pid)
            if current and current['birth'] == identity['birth'] and current['pgid'] == identity['pgid'] and current['sid'] == identity['sid']:
                os.kill(process.pid, signal.SIGKILL)
            original_wait(timeout=2)


if __name__ == '__main__':
    unittest.main()
