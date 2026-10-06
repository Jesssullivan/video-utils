"""Independent control-flow and PSD endpoint checks; no bank DSP rerun."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

AVAILABLE = (importlib.util.find_spec('numpy') is not None
             and importlib.util.find_spec('scipy') is not None)
if AVAILABLE:
    import numpy as np
    path = Path(__file__).resolve().parents[1] / 'scripts/low_register_denoise_probe.py'
    spec = importlib.util.spec_from_file_location('low_register_probe_independent_audit', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)


@unittest.skipUnless(AVAILABLE, 'Optional locked NumPy/SciPy environment required')
class LowRegisterProbeAuditTests(unittest.TestCase):
    def test_all_arrays_are_hash_sealed_before_first_oracle_index_access(self):
        """Mock DSP only: intercept the first oracle access and inspect disk seal."""
        class StopAfterBoundary(Exception):
            pass

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            discovery = root / 'discovery.json'
            oracle = root / 'unread-oracle.json'
            output = root / 'run'
            rows = []
            for number in range(1, 9):
                pcm = root / f'lr{number:02d}.wav'
                pcm.write_bytes(f'mocked mixture {number}'.encode())
                rows.append({'alias': f'lr{number:02d}', 'sample_rate': 44100,
                             'sample_frames': 8 * 44100, 'channels': 1,
                             'capture_samples': [0, 35280],
                             'mixture': {'path': pcm.name,
                                         'sha256': hashlib.sha256(pcm.read_bytes()).hexdigest()}})
            discovery.write_text(json.dumps({'truth_supplied': False, 'cases': rows}))
            original_digest = module.digest
            original_json = module.bounded_json
            boundary_seen = []

            def inspect_boundary():
                stages = list(root.glob('.run-stage-*'))
                self.assertEqual(len(stages), 1)
                seal = json.loads((stages[0] / 'masks-sealed.json').read_text())
                self.assertEqual(len(seal['jobs']), 32)
                self.assertTrue(seal['settings_frozen_before_truth'])
                self.assertFalse(seal['truth_components_read'])
                self.assertEqual(len({job['variant'] for job in seal['jobs']}), 32)
                arrays = list(stages[0].glob('*/*.npy'))
                self.assertEqual(len(arrays), 128)
                for job in seal['jobs']:
                    self.assertEqual(set(job['hashes']),
                                     {'mask', 'density', 'processed', 'residue'})
                    for key, expected in job['hashes'].items():
                        self.assertEqual(original_digest(stages[0] / job['variant'] / (key + '.npy')),
                                         expected)
                boundary_seen.append(True)

            def checked_digest(candidate):
                if Path(candidate) == oracle:
                    inspect_boundary()
                    raise StopAfterBoundary('first oracle-index hash access')
                return original_digest(candidate)

            def checked_json(candidate):
                if Path(candidate) == oracle:
                    self.fail('Oracle JSON reached before intercepted hash boundary')
                return original_json(candidate)

            # Native decoding/reconstruction belongs to separate numerical tests.
            # Tiny placeholders isolate run() ordering and persisted array hashes.
            frame = SimpleNamespace(left_padding=8192, right_padding=8192,
                                    native_starts=np.array([0]))
            capture = SimpleNamespace(density=np.zeros((1, 2)), full_frame_count=14)
            gain = SimpleNamespace(gains=np.ones((1, 1, 2)))
            with patch.object(module, 'ARTIFACTS', root), \
                    patch.object(module, 'digest', side_effect=checked_digest), \
                    patch.object(module, 'bounded_json', side_effect=checked_json), \
                    patch.object(module, 'read_pcm', return_value=np.zeros((1, 1))), \
                    patch.object(module, 'analyze_native', return_value=frame), \
                    patch.object(module, 'fit_capture_density', return_value=capture), \
                    patch.object(module, 'derive_gain', return_value=gain), \
                    patch.object(module, 'apply_frozen_gain', side_effect=lambda pcm, *a, **k: pcm), \
                    patch.object(module, 'evaluate_known_components') as evaluator:
                with self.assertRaisesRegex(RuntimeError, 'first oracle-index hash access'):
                    module.run(discovery, oracle, output)
                evaluator.assert_not_called()
            self.assertEqual(boundary_seen, [True])
            self.assertFalse(output.exists())

    def test_density_does_not_double_dc_or_nyquist(self):
        rate = 48000
        config = module.MaskConfig(rate)
        length = config.frame_samples
        signal = .13 + .07 * (-1.) ** np.arange(length)
        coefficients = np.fft.rfft(signal * module.window(config))[None, None, :]
        integrated = float(module.density(coefficients, config).sum() * rate / length)
        self.assertAlmostEqual(integrated, .13 ** 2 + .07 ** 2, places=13)
        # This fixture catches accidental one-sided doubling at both endpoints.
        doubled = 2 * np.abs(coefficients) ** 2 / (rate * np.sum(module.window(config) ** 2))
        self.assertGreater(float(doubled.sum() * rate / length) - integrated, .01)


if __name__ == '__main__':
    unittest.main()
