# Marked review preview hook

Authority: the operator's evening annotated-MVP request, active parallel goal,
R-HOOK-CONVERGENCE-20261004 and repository `AGENTS.md`. Root owns actual preview
selection, integration, user-facing delivery and publication. The media lane owns
the renderer, tests and rendering specification. The hook lane owns typed
registry/dispatch, related contract tests and this interface receipt.

Definition of done, before integration: expose implemented `marked_video` through
one typed MCP operation and a matching `guitar-marked-video` prompt after worker
verification. Keep calibration's verified twenty-two-tool checkpoint independent
of this subsequent twenty-third operation. Require an existing hash-bound run,
an explicit fresh output directory and the worker's fixed marker-selection enum.
Bound paths, markers, worker duration and result size. Exercise actual subprocess
summary and provenance/output errors, then read the new skill back exactly.

The agreed worker command is
`scripts/marked_video.py --run-dir DIR --selection phrase-review|recurrences|all-review --output NEW_DIR`.
Selection defaults to `phrase-review`. Fresh output must remain under repository
`artifacts/runs`; it is a separate burned review preview. The renderer does not
rerun discovery or replace the master, original video or original media. Current
verified DAG/flags/markers/export receipts are prerequisites. Candidate callouts
remain review hypotheses, not confirmed note or performance errors.

Worker limits are at most 5,000 input markers, at most 128 selected callouts
except `all-review` (up to 5,000), source duration at most 600 seconds and two
codec/filter threads. The fixed output set is `marked-video.mov`, `callouts.ass`,
`selection.json` and `outcome.json`. Compact stdout reports paths, status,
selected-marker and callout counts, and `listening_accepted: false`.

VFR frame timestamps/count and AAC packet payload/timing verification belong to
the implemented renderer's acceptance checks; this planning contract does not
establish their success on a real recording. Burned H264 overlays require a new
picture encode while AAC is copied. Timeline preservation, provenance, successful
rendering, listening acceptance and native editor/AU compatibility stay separate.

Renderer handoff, October 5, 2026: the media lane froze worker SHA-256
`a39280f22b60814b31a7f1bff2bfce693aacfa3e82c148df82a3513862fba300`
after thirteen passing worker tests. Its reusable fixture is generated two-second
VFR media with twenty-one decoded frames and a nonzero source origin. Tests cover
picture timestamps, AAC packets and decoded PCM identity, stale source/marker
rejection, retained failure diagnostics, bounded child execution and symlink
rejection including the `artifacts/runs` boundary. These are worker-owner local
proofs, not hook invocation, publication or real-take listening acceptance.

The typed hook requires `run_dir` and `output`, each a string of 1–4096 characters.
Both must name children of repository `artifacts/runs`; `run_dir` must exist and
`output` must be fresh. Relative paths use the repository root. Optional
`selection` uses the three worker choices above and defaults to `phrase-review`.
Optional integer `timeout_seconds` is 1–900, default 600. Additional fields are
rejected. The outer owned process-group deadline includes worker descendants;
the renderer's direct children remain in that group. Internal probe and render
deadlines are 120 and 600 seconds respectively. The fixed compact result remains
subject to the dispatcher’s 2 MiB output bound. Root released catalog activation
into the same upcoming bundle as the twenty-two-tool calibration checkpoint;
the previous checkpoint remains independent evidence.

Hook verification, October 5, 2026: all **58 targeted tests passed**, comprising
39 tool contracts, 11 dispatcher tests and 8 MCP tests, with locked Python 3.14
and explicit pinned FFmpeg/FFprobe 8.1.2; no media checks skipped. The four added
preview contract tests also passed separately. Actual initialized stdio execution
rendered the generated two-second, twenty-one-frame VFR fixture with source
origin 2 seconds. The result verified identical decoded frame PTS, AAC packet
payload/timing and decoded PCM; source-time 2.25 seconds mapped to video-time
0.25 seconds. Every preexisting fixture input hash stayed unchanged. Reusing an
output directory and changing marker evidence both returned tool errors; stale
markers created no output directory. Negative schemas, literal path dispatch,
the default deadline, traversal, symlink and non-directory ancestry were checked.

The skill lane independently verified all twenty-three bundled skills,
twenty-three tools/prompts and every exact prompt body through initialized stdio,
with empty stderr. This is local source/hook proof. Root owns publication and the
actual annotated take; fixture success establishes no real-performance or
listening acceptance. Captured-noise profile activation is recorded below as a
separate existing-tool update.

Source-bound denoise update: root authorized `captured8`, `captured12` and
`captured8-clarity` after actual preset files and worker checks were ready. The
existing denoise `profile` enum now includes them; the benchmark enum remains
`bypass`, `conservative3`, `mild6`. No new primitive or arbitrary DSP knobs were
added. Captured profiles bind original SHA-256
`a522115f4e72e19384fb341bc84369728eceefe49183b8c6367a1008a95176c6`
and root-reviewed audio-relative interval 4.10–4.95 seconds. The interval is not
operator-exact or proven free of guitar sustain. Pure denoise/residue remain
separate from clarity's fixed EQ/compression `processed.wav` and the final
normalized `cleaned.wav`.

Two additional contract tests verify all three literal profile dispatches,
benchmark rejection and actual initialized MCP wrong-source rejection. Even
with deliberately unavailable FFmpeg/FFprobe, the worker rejects the source
hash first. Direct worker checks also prove no probe or artifact-directory
creation; the input bytes remain unchanged. This protects binding and does not
establish favorable sound or absence of denoising damage on the real take.
