# Native capture application qualification harness

Implementation-only release: root authorized this new dated harness and its
inert tests under R-HOOK-CONVERGENCE-20261004/R-N13. The source plan remains
immutable at SHA256
`f2aa237b4d7c0a34e93e5065e7436639a20311c7a81945de196c39c985ecd683`.
The original application `31eafcc8…` / 36-test readiness is historical: root
reopened it after publication-interruption reporting failures. Final corrected
application binding is now `00a03ef9fad8543be4335cb5cbcd3c9d9580a6b40b8faeb826811b105fd5daa6`,
independently confirmed by root and release_review: 46 application fixtures pass
in 26.087 seconds. A new revision receipt and metadata-only preregistration bind
this corrected source without changing the original plan. Author/media source
pins remain unchanged. No existing
worker, profile, preset, tool catalog, actual source/master or latest was edited.

The harness is
`docs/agent-notes/2026-10-06-capture-application-native-qualification.py`.
Its inert tests are the sibling `…-tests.py`; they do not generate fixture PCM,
run FFmpeg, apply DSP, or qualify numerical sound. They test exact frozen release
and settings identity, finite/duplicate/bounded metadata, output collision and
symlink rejection, nonzero VFR arithmetic/clock refusal, and preservation of
published-candidate recovery without falsely asserting candidate absence. Fourteen
inert tests pass on the final application binding in 0.245 seconds; the new
revision receipt records exact source hashes. No numerical media trial has run.

Fixed CLI:

```text
python3 docs/agent-notes/2026-10-06-capture-application-native-qualification.py preregister
  --trial-id native-<fixed-id> --ffmpeg <existing-pinned-binary>
  --ffprobe <existing-pinned-binary> --output <fresh-dated-note-json>

python3 docs/agent-notes/2026-10-06-capture-application-native-qualification.py execute
  --preregistration <exact-json> --release-receipt <root-exact-json>
```

Preregistration hashes source files, plan, bypass preset and existing binary
files only; it invokes no executable or media generator. It binds one fresh
trial beneath `artifacts/experiments/capture-application-native-qualification/`,
all fixed fixture/settings/support facts and explicit FFmpeg/FFprobe executable
paths/SHA. The required media version is 8.1.2, checked only after release.
Changing any pinned source, binary, preset, setting or preregistration rejects
execution. There are no arbitrary audio inputs, filters or additional controls.

The separate root release JSON has exactly these fields:
`schema_version: 1`, `action: execute_capture_application_native_qualification`,
`root_explicit_release: true`, `preregistration_sha256`, `harness_sha256`,
`plan_sha256`, `worker_sha256` (application/author/media map), `output`, and a
meaningful `authorization_reference`. A release is not produced by this harness;
elapsed time or an inert test pass supplies no execution authority. Validation
and fresh-path checks happen before application import or output creation.

Actual execution uses the existing application's `run_owned`/`private_media`
functions for generator, probe, baseline and exporter commands, with a 600-second
whole-job owned alarm, two threads and at most 4 MiB per subprocess stream.
Application commands use its own same-session/group runner and retained receipt.
The application deliberately ends its publication timer once committed; the
larger harness re-arms its own absolute deadline immediately afterward and after
each later owned probe cleanup. A qualification-only `media.run` wrapper preserves
the existing bounded runner and committed recovery state, and is restored on
context exit. The inert integration test exercises the actual cleanup context
twice with mocked timers; no process or media is launched by that test.
No packages, models, GPU or service are acquired. The generator creates only the
one preregistered 8-second stereo 44.1 kHz PCM fixture and 8.5-second VFR picture:
175 frames, picture origin 1, decoded audio origin 1.5, relative offset 0.5.
The reviewed interval is generator-inspected `[11025,44100)` samples, with
unauthenticated supplied identities and unknown music/click assertions retained;
no listening or artist-note reference is invented.

The existing bypass baseline, source-bound author (`authored_unrendered`) and
fixed application (`rendered_unreviewed`) are called without alternate DSP.
Generated s16 reference samples mapped exactly by `/32768` must equal the
baseline decoded float32 samples, then the candidate's decoded source must equal
the baseline. This independently gates gain, offset and stereo channel transport.
All post-stage native headers, exact sample arrays, capture/preroll/calibrated
delay, residue arithmetic, copied VFR packet/decoded clocks and last extent,
strict decoded AAC peak and final current identities are checked. A separate
AAC packet/frame timing table preserves priming/padding evidence rather than
equating raw decoded AAC sample count with the PCM master. First decoded AAC
frame PTS and first decoded picture PTS independently gate the known 0.5-second
relative offset within the frozen AAC tolerance; packet priming timestamps cannot
substitute for decoded origin. Application hashes
and current published artifact selectors are checked; historical command/probe
paths truthfully retain private staging execution locations.

The current latest pointer, actual source/master, rendered videos/report and
their named receipts are byte-hash guarded without decoding the actual take.
Generated parent/source/authoring artifacts receive their own before/after hash
guards. Protected actual byte hashing is identity checking only, not actual-take
processing or a new listening claim. There is no latest promotion or master
adoption. Candidate output remains a fresh immutable run returned by application.

Failure retains this trial's bounded `failure.json` and completed selectors;
publication recovery from the application is preserved. Candidate absence is
never asserted merely because an exception occurred. If timeout prevents a final
immutability recheck, that field stays null, not true. Interruption may leave a
confirmed committed candidate or an unknown publication outcome; the latter's
possible selectors remain separate from verified commit recovery. Inert tests
cover both reporting classes without promoting a possible candidate. Any
published unreviewed candidate remains for root inspection; a failed qualification does
not adopt it, overwrite it or silently rerun. Native/generated proof, actual-take
acceptance and later AU/Logic/native-editor proof remain separate states.

Status: implemented/inert-tested, numerical execution held. Root must pin the
corrected source revision, review final preregistration/hash and issue its exact
release before any generated audio, FFmpeg or DSP execution.
