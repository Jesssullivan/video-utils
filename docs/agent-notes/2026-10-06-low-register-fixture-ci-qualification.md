# Low-register fixture CI qualification repair

Plan before change. Owner `clip_baseline`; root assigned only
`tests/test_low_register_fixtures.py` and this new receipt. Authority:
repository AGENTS.md and R-HOOK-CONVERGENCE-20261004 R-N13. Hosted run
37402577907 for source `27eaa824f` reported six fixture-oracle setup errors
because its deliberately stdlib-only Python environment lacks NumPy.
Root reported the qualified analysis suite had already passed.

Add an explicit NumPy/SciPy package-availability gate to the numeric oracle
class only. Keep four stdlib metadata tests active. Do not catch fixture
failures or corrupt installed dependencies, change the generator, install
packages or modify CI/locks/DSP/media/defaults. Verify this module under
default Python 3.12 (four pass, six explicit skips) and qualified `.venv`
(all ten pass; two numerical threads). No full-suite rerun in this lane.

## Result

Repair complete. `NUMERIC_AVAILABLE` checks `importlib.util.find_spec` for
both NumPy and SciPy. A class-level `unittest.skipUnless` applies only to
`OracleTests`; `MetadataTests` remains unconditional. The skip reason is
`Optional NumPy/SciPy fixture-oracle environment required`.

No dependency imports or test failures are caught. If the packages are
discoverable but their imports/APIs are broken, `bank.numeric()` still raises
in setup. Fixture corruption, incorrect source accounting and violated
oracle assertions still fail in the qualified environment. This gate does
not install dependencies or qualify numerical coverage in stdlib-only CI.

## Targeted live verification

| Environment | Availability | Module result |
| --- | --- | --- |
| `/Users/jess/.nix-profile/bin/python3.12`, Python 3.12.14 | NumPy/SciPy both absent | Four metadata tests pass; six oracle tests explicitly skip; 0.012 seconds |
| Repository `.venv/bin/python`, Python 3.14.6; NumPy 2.5.3, SciPy 1.18.1 | Both available | All ten tests pass; no skips; 7.509 seconds; numerical threads capped at two |

Commands executed:

```sh
python3.12 -m unittest discover -s tests -p test_low_register_fixtures.py -v
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 NUMBA_NUM_THREADS=2 .venv/bin/python -m unittest discover -s tests -p test_low_register_fixtures.py -v
```

Both exited zero. The default module output lists all four successful
metadata tests and all six named skips. The qualified module actually
executes native fixture synthesis, waveform roundtrips, additive/collision
oracles, missing-F0 negative controls and corruption checks. These temporary
test fixtures do not modify the frozen bank or process the real recording.

## Frozen handoff

| File | SHA-256 |
| --- | --- |
| Repaired fixture test module | `58d7067e9773b94cd54ce9f458e02bf4f4f9ff8e07267e028b4b37842664bc51` |
| Unchanged fixture generator | `06d08ad703bb17d7bc53863e5dfa53b117172d9498ec780f6338f6a5f60d3e7c` |
| Unchanged probe worker | `384a99bca9e72212b5d9631e9b425424ea7b08fc41ce6eb4dde4d647b3ba3bc6` |

Only the test module and this new receipt were changed in this lane. No CI,
locks, dependency installation, worker, media or default changes occurred;
no broad suite was rerun. Root owns publication and hosted rerun/readback.
The targeted local pass does not claim the subsequent hosted run passed.
