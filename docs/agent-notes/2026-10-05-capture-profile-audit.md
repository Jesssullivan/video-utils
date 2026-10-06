# Independent capture-profile authoring audit

Date: October 5, 2026, America/New_York (initial inspection at 2026-10-06 00:28 UTC). Actor: `/root/rhythm_analysis/capture_profile_tests`, reattached directly by root as the independent audit lane. Authority: repository `AGENTS.md`, the operator's authorized parallel project, and R-HOOK-CONVERGENCE-20261004 / R-N13. Own files are this receipt and `tests/test_capture_profile_audit.py`; the released worker, 33 qualification tests, media validator, presets and existing recordings remain outside this lane's edit scope.

## Findings and disposition

**Final disposition: all three reproduced defects fixed by the worker owner after root release; 45/45 combined tests pass.** This lane added twelve independent tests and changed no released worker, media validator, preset or original qualification test.

Three direct-worker boundary defects were reproduced and reported to root before edits to any released file:

1. A requested and reviewed 0.2–0.3 s capture at 16 kHz has exactly 1,600 native samples, but floating subtraction yields `0.09999999999999998` and the worker rejects it. This violates the inclusive 0.1 s minimum at an ordinary decimal boundary. The MCP preflight already tolerates this floating-point edge. The worker owner now validates duration in native integer samples, records requested seconds separately, and encodes sample-equivalent profile seconds so the frozen validator also accepts the boundary. Both 0.2–0.3 s minimum and 8.1–18.1 s maximum regressions pass; authored profile native bounds remain unchanged.
2. A numeric argument `10 ** 400` raises raw `OverflowError` through the frozen media validator's `math.isfinite`, rather than `CaptureError`. Reproductions include top-level NR, noise floor, capture start, and nested EQ/compressor controls. MCP number validation rejects oversized integers upstream; the direct author API still requires a bounded domain error. The worker owner now maps top-level and nested validator overflow to `CaptureError` locally; frozen media DSP remains unchanged.
3. A path such as `~__capture_audit_nonexistent_user__/missing.wav` raises raw `RuntimeError` from home expansion. The direct CLI catches domain/I/O errors, so this malformed bounded path can produce a traceback. MCP path preflight already wraps this case. The worker owner now wraps failed normalization into `CaptureError`.

Initial independent suite: 11 tests, seven passing tests and seven failing subcases across the four regression tests for these three defects. No original media, existing run or global configuration was changed. After the root-authorized worker fixes, `.venv/bin/python -m unittest discover -s tests -p 'test_capture_profile*.py' -v` passed **45 tests in 8.223 seconds**: all 33 unchanged qualification tests plus twelve independent audit tests. The audited worker SHA-256 was `7d2820878826c87aabf2ab60b73c997b9d406b7f3ff8943d6012ed967444c355`; frozen media validator SHA-256 was `91443154251888c9e74670790766b289a2618f85f3be806d60ca26882faa9d94`. No unresolved must-fix remained in this bounded audit.

## Qualified behavior and evidence limits

The independent tests additionally prove that a missing review or authorization field publishes no profile; a `profile_authoring` proposal is rejected by the frozen media profile loader; unknown/suspected capture music/click content remains an explicit render-scoped experiment with `noise_only_verified: false`; whole-take ambient music is retained with a warning and no separation/DSP claim; changed JSON between its hash and payload read rejects; the 1 GiB PCM ceiling is checked before payload reading; and an extensible float-PCM native header is accepted while an unsupported subformat GUID rejects. These cases supplement, rather than edit, the released 33-test suite.

Source inspection confirms current original path plus computed SHA must match the baseline, source PCM and review carry separate hashes, the manifest/native header must agree on integer rate/channels/count, the review interval agrees after native rounding, and all input/context/producer files are hashed again before publication. JSON reads have exact byte ceilings, reject duplicate keys/nonfinite constants and compare their actual bytes with the initially hashed bytes. The CLI owns a bounded alarm; the MCP adapter also bounds the subprocess. Direct Python `author` calls use cooperative deadline checks rather than the CLI's blocking-read interruption.

These checks establish observed byte identity and native-header consistency. They do not independently rerun original-to-PCM decoding, authenticate supplied reviewer/authorization assertions, prove that a quiet span is fan-only, learn the noise shape, separate guitar/fan/ambient music, accept a master or verify listening quality. Sequential rechecks are not a lock or an atomic multi-file snapshot against adversarial concurrent filesystem replacement. Context receipts snapshot the current repository registries with basic shape checks; they are not measured played notes or a canonical tuning measurement.

The released hook and skill retain three nested worker outcomes. `authored_unrendered` requires supplied render scope; `draft_authorization_incomplete` has no runnable profile; `needs_reselection` has no runnable profile/proposal. A successful dispatcher envelope does not upgrade any nested state. Captured-profile authoring does not add custom paths to the existing denoise enum or admit the separate application route.

## Reproduction

`.venv/bin/python -m unittest discover -s tests -p test_capture_profile_audit.py -v`

All fixtures are generated local WAV/header and review metadata. Authoring creates metadata only; no FFmpeg, model, audio rendering, plugin/host installation, network upload or real-take audition occurs in this lane.

Receipt: `capture-profile-audit | new audit tests and dated note only | independent qualification after root release | R-N13 | worker/33 tests frozen, hooks+skill release in progress | three direct-worker boundary defects reproduced, fixed by the worker owner after root release and verified by 45 passing combined tests; source/provenance semantics retained for root actual authoring`.
