# NR8 / NR10 bounded comparison driver source checkpoint

Owner `audio_research`; authority root's explicit new-driver implementation
delegation under the operator's active restoration scope and repository
R-HOOK-CONVERGENCE-20261004 R-N11/R-N12/R-N13. Owned files are the new dated
[driver](2026-10-06-nr8-nr10-comparison.py),
[method tests](../../tests/test_nr8_nr10_comparison.py), and this receipt.
The [October 5 method](2026-10-05-nr10-restoration-comparison-method.md) remains
frozen at SHA256 `9c06f5094966f4b24d832e4b2034810fe9e77300e21ae364c4b9bb41f58d2d0a`;
its filename preserves local-date history. No authoring/profile/runtime
application, original movie decoding or actual-take measurement occurred here.

## Exact source and evidence

Driver SHA256:
`7f46a7010f42558bf8d39f8a94fc9b0a6f513a12242e61d6be553267d6e9b26e`.
Test SHA256:
`cd819f20f73a79ebae94f32c1275bb9635622de3bbae46b1ac9aabcb445fe47e`.
Locked `.venv/bin/python -m unittest discover -s tests -p
test_nr8_nr10_comparison.py -v`, with the four numeric thread variables set to2,
passed **17 tests in15.386 seconds**. Tests use synthetic in-memory arrays,
temporary metadata placeholders/mocked native dimensions, mocked meters and one
owned inert Python process. They do not decode the actual recording or run
FFmpeg. Final standard-library invocation ran17 tests in1.150 seconds, with14
passes and three explicit optional-NumPy/SciPy skips; no installation was
attempted. Final source
and test `py_compile`, exact hash readback, owned whitespace/newline checks and
local documentation links passed on the corrected7f46 source. Independent
audit closure remains separate from those checks.

Meaningful oracles cover inclusive AAC −18±0.3 LUFS / ≤−1.75dBTP delivery limits,
unreviewed acceptance flags, nonfinite/bool meter rejection, measurement input
versus simulated normalization output, fixed candidate timing/spacing, closed
one-knob profiles, changed-media hashes, native extent/capture uncertainty/AAC
padding refusals, exact packet timeline despite a20ms MOV header difference,
and a32Hz signal attenuated6dB while coherence remains1.0. Short windows retain
native indices and levels; zero-power coherence is null rather than NaN.

The first expanded suite had14 passes and one valid-fixture error because macOS
`TemporaryDirectory` used `/var`, a symlink. Canonicalizing owned fixture roots
allowed the intended valid packet case and structural refusals to be tested;
the path guard was not weakened. Independent reviewer then found two source
defects in the superseded `af5f6c…` candidate: the hard timer started after
preflight/import/header work, and mid-role interruption could drop completed
statistics. Both were corrected before release. Accelerated80ms inert
preflight/import stalls now interrupt under the owned timer and restore the
previous handler; a mocked mid-panel failure retains completed role statistics
and the first panel in the new failure receipt. Independent exact-byte closure
is still pending at this source checkpoint.

## Runtime contract, not execution evidence

CLI: `.venv/bin/python docs/agent-notes/2026-10-06-nr8-nr10-comparison.py
--release RELEASE.json --release-sha256 SHA256 --output-dir NEWDIR`.
The root-authored immutable release is required, with exactly these top-level
keys:

```json
{
  "schema_version": 1,
  "authority": "root_nr8_nr10_measurement_release",
  "driver_sha256": "<exact driver hash>",
  "method_sha256": "9c06f5094966f4b24d832e4b2034810fe9e77300e21ae364c4b9bb41f58d2d0a",
  "output_dir": "/Users/jess/git/video-utils/artifacts/experiments/<new-directory>",
  "ffmpeg": {"path": "<existing binary>", "sha256": "<binary hash>"},
  "candidates": [
    {"label": "nr8", "manifest": {"path": "<manifest>", "sha256": "<hash>"},
     "application_receipt": {"path": "<receipt>", "sha256": "<hash>"},
     "export_outcome": {"path": "<outcome>", "sha256": "<hash>"}},
    {"label": "nr10", "manifest": {"path": "<manifest>", "sha256": "<hash>"},
     "application_receipt": {"path": "<receipt>", "sha256": "<hash>"},
     "export_outcome": {"path": "<outcome>", "sha256": "<hash>"}}
  ],
  "protected": [{"path": "<protected file>", "sha256": "<hash>"}]
}
```

`protected` requires7–24 distinct regular identities, including the original
source and native source WAV, plus root's current master/latest/parent evidence.
The single entry above illustrates shape only; it is not an executable release.
Existing candidate manifest/application/export identities bind current qualified
producer source, exact settings, all six WAV roles and exported video bytes.
Original and copied source PCM hashes must match the known actual take. Both
profiles must match outside NR/name/description; EQ/compression and −18/−1.75
presentation controls are exact. Unknown capture contamination is retained.
All native headers must be44,100Hz mono6,657,385 samples at unchanged origin.
Video packet payload/clock/count and AAC-offset/duration receipts are validated;
no fresh video probe or original-movie decode is performed. These are readbacks
of hash-bound producer evidence, not an independent acoustic synchronization
experiment.

The driver installs its owned55-second processing alarm before any preflight,
refuses an existing active external timer, and restores the saved handler even
when dependency import fails. Qualified application `00a03e…` `run_owned`
meters only the two new PCM masters and two final AAC files with remaining
deadline, bounded logs, owned POSIX sessions and verified cleanup. Its existing
up-to5-second exceptional cleanup is reserved inside the nominal60-second job.
Scheduling/system-call timing is not hard real-time; actual elapsed is recorded,
and a budget overrun makes the receipt incomplete and delivery ineligible.
No historical unbounded meter helper, mutable media runner or new DSP is used.

Source WAV is loaded numerically once, with both candidate copies hash-identical.
Pinned dated helpers supply native float decoding, whole-take Hann Welch/window
statistics; pinned segment equations supply fixed local PSD/coherence. Results
retain quiet/opening/capture/tail/active/end-gesture panels, uncertain historical
NR8 broadband anchors, native short attack/tail windows and20ms envelopes.
Completed candidate/role/panel coverage survives an interruption. All identity
bindings and protected files are rehashed before a complete comparison result;
failure leaves `protected_after_verified=false` rather than claiming readback.

Fresh private output is exclusive and canonical, with `results.json` retaining
complete or incomplete outcome and bounded error/process evidence. Candidates
remain unreviewed; full AAC input loudness and true peak establish only delivery
eligibility at meter precision. Fan/music isolated gain stays null. The existing
master/latest/default, archived profiles, worker/report/catalog sources and
published evidence remain unchanged. Exact source plus exact root input release
and positive independent audit are required before actual measurement.

Process receipt: actor audio_research | target delegated new comparison driver
and recorded inert fixture processes | reason controlled NR10 comparison
readback | ruling R-N11/R-N12/R-N13 | prior_state frozen method, implementation
released but actual measurement unreleased | result17 fixture oracles pass;
corrected source frozen for independent review; no actual audio execution.

## Historical independent closure and successor hold

Independent [source audit](2026-10-06-nr8-nr10-comparison-source-audit.md), current
readback SHA256 `2103ef490cea3576cd8f45c9eb2053f7e1935fa0e15fa9e8eb82ad77605fc3d2`,
closed the timer and partial-coverage
findings on exact driver7f46 / owner-testcd819 bytes. Owner17 plus two independent
signal-ownership oracles passed19 in16.541 seconds. The added independent test
source SHA256 is `332f6af6d62dc343f68c8c2d9afefe43a830fd965d25f8fddaeea026f26f005a`.
These additional oracles prove that an existing
external interval timer/custom handler is preserved without reading inputs,
and that the first hash sees the owned one-shot timer before restoring the saved
custom handler. This closure used inert fixtures only; it performed no real
audio or FFmpeg measurement.

Root subsequently reported actual NR8 application success on the original
qualified application producer and NR10 failure after completed FFmpeg but an
OS process-inspection timeout during cleanup. No NR10 candidate was published;
root reported protected identities unchanged. Those are root-supplied execution
facts, not this lane's independent readback. Root requires a separately qualified
resource-only application revision and explicit NR10 retry. Historical7f46
is not released for actual measurement and its single-producer pin is not
silently broadened. A successor driver will require exact root-approved NR8/NR10
producer identities, unchanged authoring/media/DSP controls, new source/tests
and independent closure before any source-and-input measurement release. This
lane is waiting for that exact successor application source freeze.
