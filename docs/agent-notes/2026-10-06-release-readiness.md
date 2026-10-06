# Independent pending 25-tool release audit

Owner: `/root/release_review`. Authority: operator parallel implementation goal;
R-HOOK-CONVERGENCE-20261004 / R-N13. Root owns integration and publication.

Definition of done: independently inspect pending source, privacy exclusions,
qualified model licensing and dependency identities, all tool/skill counts,
unchanged existing contracts, and exact baseline remote CI. Report actionable
blockers before push. Do not mutate implementation, stage, commit, install,
download weights, run inference or promote synthetic/runtime evidence into
musical/listening/Logic acceptance. Joint-suite verification remains root-owned.

## Verified baseline and source scope

Read-only `gh repo view`, `gh run list` and exact commit API readback verified
private `Jesssullivan/video-utils`, baseline
`c59d7024a9967b920747e07134c6c166c3ddb38d`, and successful completed
[Private offline checks run 37392676183](https://github.com/Jesssullivan/video-utils/actions/runs/37392676183).
That CI evidence belongs to the baseline, not the uncommitted additions. An
abbreviated `--commit c59d702` query returned no matches; exact head-SHA readback
resolved the query ambiguity without claiming missing or failed CI.

Pending registry contains 25 unique tools and 25 skill files, with no missing
skill. The original 23 descriptors are structurally unchanged. Shared dispatch
adds bounded typed arrays, fixed new worker routes and capture error envelopes;
no shell/argv/model/interpreter input was added to either new tool. Root's joint
suite remains the admission gate for shared-code behavior. Cargo.lock,
flake.lock, uv.lock and pyproject.toml are unchanged from the baseline. Optional
ONNX dependencies remain isolated and separately hash-bound.

## Privacy, model and rights evidence

No tracked recording or model binary was found. `/artifacts`, `/models`, private
input/cache directories and model/media extensions remain ignored; the actual
qualified ONNX is ignored. CI remains synthetic/offline, with no media upload or
implicit model acquisition. A bounded signature scan of 82 pending nonignored
files found no private-key, GitHub-token, AWS-key or long credential-assignment
signatures and no file over 2 MB. This is a scoped source check, not a universal
secret-detection guarantee.

Independently rehashed the official ONNX: 230,444 bytes,
`2c3c1d144bfa61ad236e92e169c13535c880469a12a047d4e73451f2c059a0ec`.
Registry pins Spotify's official commit
`9991303bba609a3b93089d13ec80d1d495083596` and states repository-wide Apache-2.0
with bundled-weight applicability **inferred**. Qualification/runtime receipts
retain actual LICENSE and Spotify NOTICE text; no independent weight license
is claimed. No model bytes are proposed for Git publication.

The recorded isolated runtime manifest matches its current file digest and
embedded durable snapshot. All five wheel archive hashes and byte extents match:
ONNX Runtime 1.30.0, NumPy 2.5.3, flatbuffers 25.12.19, packaging 26.3 and
protobuf 7.36.2. This audit did not install packages, import the optional runtime,
repeat inference or infer cross-platform availability.

Inspected learned comparator SHA
`8bc17166c48ff6dccf33fd0eb17d3257535d6d91c83df0afed51b9c59dc75ee1`
and capture authoring worker SHA
`5b79f13a32fd3f43d84f774f6be97fafe241d140e5ab41dbd05685fb1130ffe1`.
The former retains raw activations, sparse coverage, two project decoders and
ungraded/null note/string/performance interpretations. The latter binds current
original/run/PCM/review/context identities and emits authored-unrendered,
nonrunnable draft or reselection metadata without DSP. Existing near-32 Hz
protection and custom tuning remain explicit. Musical correctness, listening,
full-song transcription, native editor import and AU/Logic acceptance remain
separate and unestablished by these tools.

## Findings before publication

1. **Must fix current documentation:** README.md:144 claims no hash-qualified
   model, while registry now contains the qualified official model. README.md:147,
   docs/spec/PROJECT.md:69 and docs/spec/AGENT_TOOLS.md:43 describe the current
   catalog as twenty-three. Update current claims to 25 and optional local-only
   qualified inference; preserve dated historical checkpoints. Root was notified.
2. **Must fix source-time integrity:** comparator task construction defaults
   missing `timeline.audio_start_seconds` to zero. That fabricates source origin
   for malformed/legacy runs even though the actual native demos have an explicit
   origin. Require an explicit finite origin before processing, or preserve null
   source spans. Owner agrees and awaits root's release to amend frozen source;
   add a no-inference absent-origin regression.
3. **Pending verification, not a defect:** root must run the joint suite after
   all source freezes. Baseline successful hosted CI does not prove the new
   25-tool source or optional runtime on hosted/Linux machines.

No other material release blocker was found in this bounded review. Ready only
after findings 1–2 close and root's joint checks pass. Root retains publication
and actual-media/report update ownership; this lane changed this receipt only.
