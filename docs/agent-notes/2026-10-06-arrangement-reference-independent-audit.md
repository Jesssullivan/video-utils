# Arrangement reference: independent source audit

Actor `phrase_dag`; authority is the root's arrangement independent-audit assignment, R-HOOK-CONVERGENCE-20261004 and R-N13. This is checker-source and constructed-metadata evidence. Actual musical boundary acceptance remains separate.

Thirty-one independent tests passed under Python 3.12.14 with `-S`, without site packages, waveform decoding, feature extraction or model inference. The final source was rehashed before and after the run and remained `c6bdc8991b6e378f2ab54873e94e23b1cff63073056e4f32b05ab5f7b58f89ae`. The test runner reported 0.500 seconds; import and execution together took 1.272 seconds. The expected output-collision negative case prints “output must be a fresh directory” and passes by requiring rejection and unchanged prior output.

The independent fixtures test expected half-open click arithmetic, exact source binding, nonfinite and oversized metadata, approximate anchor intervals, one-to-one monotonic matches, equally supported assignment alternatives, repeated-riff joins without novelty, missing/extra changes, intentional rests, censored tails and propagated boundary uncertainty. Fixed randomized properties (seeds 46021 and 98410) exercise cumulative counts and absent joins; common source-origin shifts preserve alignment and differences. Altering an unverified candidate pulse alias leaves reference comparison unchanged. CLI fixtures check fresh immutable publication, input/output hashes and collision rejection.

The review found and the worker owner corrected four issues before this final run: a tiny resampling tail previously rejected canonical coverage; overflow exponents or optional metadata could retain nonfinite numbers; unit center durations initially omitted boundary uncertainty ranges; cached reversed spans and fractional native sample counts needed explicit rejection. The tail fix permits at most one 16 kHz analysis sample and preserves the original edge plus its adjustment. It does not establish physical detector latency.

The corrected real reference expands to 24 musical phrases, two breakdown groups, a four-click rest and 404 **intended** clicks. The initial verse's articulation remains unspecified. The second chorus is a presumed repeat with explicit provenance. The first phrase anchor is the supplied approximately 10–11 second interval and 178 BPM remains approximate intent. Neither arithmetic nor fixture success forces a detected count, correct phrase or confirmed timing error.

A cached actual artifact was inspected for interface design only. Its approximately 88.8009 BPM periodic candidate remains separate from the supplied approximately 178 BPM click unit, and its metronome identity is unverified. No fresh real-take processing or arrangement assessment was run by this auditor. The run adapter's canonical PCM hash read and original-media identity assertion are explicitly different proof scopes. Intended-only navigation spans must retain their time-basis label; no novelty at a repeated join means unknown boundary support, not a missed phrase.

Exact frozen bindings:

| Artifact | SHA-256 |
| --- | --- |
| `scripts/arrangement_reference.py` | `c6bdc8991b6e378f2ab54873e94e23b1cff63073056e4f32b05ab5f7b58f89ae` |
| [Independent tests](../../tests/test_arrangement_reference_audit.py) | `8ab795a97bd1afbe9cc3d42e5c0a1bd05cc6305c89458f0f5fc7be6a0db67942` |
| Worker-owner tests | `5c0c537772c35f14d5e87c88b85e92db4a00e1fd9ccd0ace34fba9a5ab82577b` |
| `program/demo-arrangement.json` | `170a33eb9e5832cbc0a3309c6041b5ded06f5fc1265ba519a6633ab0f84e541a` |
| [Integration specification](../spec/ARRANGEMENT_REFERENCE_LANE.md) | `7920f5bf561e5464317ceb159b363cd6c696507bf468890db2967b216c5b90ec` |
| [Machine-readable audit](2026-10-06-arrangement-reference-independent-audit.json) | `31b78fb693ef08b4dd0f8b2453e3aa0ad2acb2ee3c3cc98857d4780a285631dd` |

No unresolved blocking source finding remains for this frozen contract. Root integrates the standalone output selectors, checks actual source-bound assessments and publishes. The unsupervised baseline, current recording, historical markers and canonical defaults were preserved. No listening, native editor import or actual performance acceptance is claimed.
