# Source-bound arrangement overlay and NR10 preview

Authority: the operator requested an arrangement-aware review video and selected
compact section/phrase labels, BPM and brief issue badges. Root released the
fresh NR10 assessment and separate preview on October 6. R-HOOK-CONVERGENCE-20261004
(R-N13) requires this durable receipt. This lane owns the arrangement marker
adapter, its tests and the renderer's narrow alternate-marker path; root owns
integration and publication.

## Frozen implementation and focused qualification

- `scripts/arrangement_markers.py`: SHA-256
  `cc1c513937605120fa743ef00c38c2f88ebb254b93df30879f1e572c8e5ca8be`.
- `scripts/marked_video.py`: SHA-256
  `1ef53c64fdf7939ed7bf62ddc085e0b766786933d22a1318d7c7539de1255419`.
- `tests/test_arrangement_markers.py`: SHA-256
  `a995915a511be5172120a41e5a2c84ce94a5fb54a914efa113598dca06927036`.
- Nine focused tests passed under Python 3.12 in 7.460 seconds. They exercise
  uncertain anchor intervals, separate intent/alignment labels, stale hashes,
  false correctness/count assertions, native bounds, forged phase/labels,
  selector/symlink/JSON limits and an actual tiny VFR/AAC preservation render.
  The renderer's thirteen existing tests previously passed with explicit FFmpeg.

The adapter verifies current manifest, analysis, phrases and pure-denoised PCM
byte identities, the exact repository arrangement reference, native extent and
source origin before deriving bounded markers. Intended labels cover only the
common core of the operator's uncertain anchor interval. Observed alignment
candidates remain separate; unmatched boundaries remain intervals. It never
chooses an exact first downbeat or interprets 404 intended clicks as detected.
Unit review candidates retain their full evidence separately from compact
picture labels. An alternate render requires explicit `all-review`; the normal
renderer path and canonical graph/marker files remain available.

## Actual bound input and marker conversion

Run: `artifacts/runs/20261006T034521Z-a0def0c43eac`.
Assessment: `arrangement-reference-20261006/assessment.json`, SHA-256
`834e9420ef10310c2e1df42f243af01f645de06a498e544f06ec1593cdd07028`.
Reference: `program/demo-arrangement.json`, SHA-256
`170a33eb9e5832cbc0a3309c6041b5ded06f5fc1265ba519a6633ab0f84e541a`.
Original MOV identity:
`a522115f4e72e19384fb341bc84369728eceefe49183b8c6367a1008a95176c6`.
Analyzed pure-denoised input:
`cb8a3fa559424810f206c94191a149156423770bbf91a13724a2ba28a44e879e`.

The actual adapter invocation succeeded and created the fresh same-run file
`arrangement-reference-20261006/arrangement-markers.json`, SHA-256
`b82c447dd48dabf6ed6bcc27b9784de34f73c4bfc2316b71d6d59638df630557`.
It contains 71 markers: 27 intended units, 16 candidate aligned units and 28
boundary review points/intervals. All 55 assessment review candidates are
represented, including 27 unit records. The two breakdown duration comparisons
are conditional reference-equivalent durations, not detected nine-click bars
or confirmed performance errors. The first breakdown's user-reported uncertainty
retains its attribution.

## Actual render plan

Use the typed `marked_video` entrypoint with the exact same-run marker selector,
explicit `all-review`, a fresh `reference-marked-preview` directory and a
900-second owned-worker deadline. FFmpeg and ffprobe use the already-qualified
Nix-store binaries. The renderer copies the existing delivery AAC and reencodes
only picture, then verifies VFR frame timestamps, AAC packet timing/payload,
decoded delivery PCM and unchanged bound inputs. Source, master, latest pointer,
canonical analysis/graph/report/markers and previous NR8 delivery are protected.

### First actual attempt: bounded inspection timeout

The typed `just tool-run marked_video` launch used explicit `all-review`, the
bound arrangement selector and `timeout_seconds: 900`. Owned execution session
62594 ended with exit 1. The initial decoded-frame ffprobe reached the renderer's
existing 120-second inner deadline before selection files or encoded picture
were created. `reference-marked-preview/outcome.json` has status
`failed_preview_preserving_inputs`, SHA-256
`657c832b2e480f6817a8e77f368ac019c2a94ba8210611e90f1e39d7bbfb738d`.
Its owned-child cleanup records the live PID/group check, direct child kill and
return code under R-N11. The failed directory is retained, rather than reused.

The typed arrangement schema was already present and accepted the exact
arguments, but its owner's final focused integration tests were still running
when this launch began; renderer/adapter qualification above preceded launch.
No broader typed-tool test completion is claimed retroactively. Root has been
asked to release a narrow bounded decoded-frame inspection timeout adjustment
and a fresh retry, preserving the full VFR verification and 900-second guardian.

Render completion and sampled frame review remain pending.
Even a transport-preserving render does not establish listening acceptance,
musical correctness, physical capture synchronization or native editor import.

### Released operational retry

Root released the narrow decoded-frame probe ceiling increase from 120 to
240 seconds. Other probe bounds, encoder ceiling and typed 900-second total
deadline remain unchanged. Renderer SHA-256 after this one-call adjustment is
`5335a3e0f21206c6daca277912d4fe66bd0275b77eb52772168d4e10fcb62dde`.
The existing owned-child output/deadline/cleanup test passed in 0.124 seconds;
the nine alternate-marker tests, including actual tiny media preservation,
passed again in 2.059 seconds. Adapter, test and actual marker payload hashes
remain unchanged. Independent readback verified all thirty first-attempt bound
input hashes unchanged. The fresh retry directory is
`reference-marked-preview-retry`; the failed directory remains intact.

### Verified first arrangement preview and concise revision

The retry completed successfully: 3,621 decoded VFR frames preserve every PTS,
first PTS 0 and last picture extent 150.885 seconds. AAC packet timing/payload/
padding and decoded 44,100 Hz mono delivery PCM remain identical. The decoded
PCM hash is `174a2876cec6d4c238fa3593c86b7a92a1a370482d9ebdc1da75a35e7e2b3d4f`.
Media subprocess elapsed times total 336.075 seconds, under the typed deadline.
`reference-marked-preview-retry/marked-video.mov` SHA-256:
`b0cf7a4d34956fcfa8ea1de7617654c87eaf79e1d315adfc1694ea8ebbde4228`;
its outcome SHA-256:
`60431e95b3dc663e702ad956b0590fedd9ecd1fa7c94221bf65161377ecdca13`.
All 71 markers intersect picture coverage and create 89 composed callouts.
Sixteen markers have partly suppressed overlap time; five have no visible
time under the existing two-marker limit. Full evidence and accounting remain
available; the movie is not an exhaustive visible candidate inventory.

The source-delivery/current-ASS preflight frame at an approximate 96.8-second
seek was inspected locally and by root: no clipping or guitar/hand obstruction,
but duplicated phrase wording was too wide for the agreed compact presentation.
It is a preflight image, not completed movie readback. Root authorized a narrow
display-only revision after the first render reached terminal success.

The revised header is `~178 BPM · expected arrangement`. Same-phrase alignment
and boundary labels become one phrase with `Timing review`; intent-only labels
retain `Expected`, unknown intervals retain `Expected boundary`, and the first
breakdown retains `Check breakdown length (user)`. Detailed original labels,
reference inheritance, uncertainty, evidence and source clocks stay in metadata.
Both visible marker IDs and all visibility accounting survive display deduplication.
The assessment, adapter and 71-marker payload are unchanged.

Revised renderer SHA-256:
`821b064809356481972ecbe5115568d15de15a2eeffd2f49b29f0ccf63350458`;
revised focused tests SHA-256:
`9edf6b23651612f73a47ea287278ced9a87cb82fc6c92191131c0ce785f83ccf`.
Eleven alternate-marker tests passed in 2.067 seconds, including deduplication,
distinct phrases, retained inheritance/user attribution and tiny actual VFR/AAC
preservation. The normal renderer's nine stdlib tests passed in 0.117 seconds;
four real-render tests explicitly skipped in that PATH-only invocation. This
does not replace their earlier explicit-media qualification.
One fresh concise preview is released at `reference-marked-preview-compact`
with the same exact selector, explicit `all-review` and typed 900-second limit.

During this concise render, root relayed the operator's explicit listening
acceptance of the separate FULLER audio variant. This preview still copies
NR10 delivery audio. The media-latency owner will assemble the verified concise
picture with that accepted FULLER AAC in a separate final presentation and
record the two branches explicitly. Neither FULLER listening acceptance nor a
shared original source rebinds these NR10 analysis/arrangement measurements to
the FULLER processed audio. No further picture render is planned for assembly.

### Final concise preview: qualified handoff

The concise typed render completed with exit 0. Media subprocess times total
680.608 seconds under its 900-second guardian. Its 3,621 decoded VFR frames,
all frame timestamps and final picture extent 150.885 seconds match the NR10
delivery exactly. Copied AAC packets/padding and decoded 44,100 Hz mono PCM
remain identical. All thirty bound inputs independently match their hashes.

Exact typed arguments to `just tool-run marked_video` (with the qualified
Nix-store `FFMPEG` and `FFPROBE` binaries named in the outcome commands):

```json
{"run_dir":"artifacts/runs/20261006T034521Z-a0def0c43eac","output":"artifacts/runs/20261006T034521Z-a0def0c43eac/reference-marked-preview-compact","selection":"all-review","arrangement_markers":"arrangement-reference-20261006/arrangement-markers.json","timeout_seconds":900}
```

Final parent files in `reference-marked-preview-compact`:

- `marked-video.mov`:
  `857285fd307ee95e3fedc84462f186ff1ed3deaf1cb96b2226167928e3ae89b3`.
- `outcome.json`:
  `3a8eacb79586a5946a1f013d1dc922ae10b9a875edd2b065514d228077d1821f`.
- `selection.json`:
  `0a14edb7c7d24856d86b57d0e7566bc1c4d2d7a016f0050956f556778d6c0da0`.
- `callouts.ass`:
  `90c3de715bf89e269f0b971eaa453dcc22ad424890f93f0fef6692dbf06bfa6b`.

Independent metadata comparison verifies exact non-display selected-marker
fields, callout timestamps/IDs, visibility accounting and exclusions versus the
first verified preview. All original display wording is retained. Display
deduplication changes no evidence span, marker count or claim boundary.

Three PNGs extracted from the **finished movie** were inspected locally:
decoded PTS 36.650000, 44.228333 and 96.828333 seconds. Text fits without
clipping and has clear contrast; the short chorus label and user-attributed
breakdown badge are readable. The brief widest two-distinct-phrase comparison
partly overlaps the lower guitar/picking-hand region. This remains a layout
limitation; these three samples are not continuous visual or musical acceptance.
The extraction commands, frame hashes, independent audit and exact parent
identities are durable in `2026-10-06-arrangement-markers-preview.json`; local
PNGs remain in the run's `visual-proof/` directory, outside Git.

The concise movie/outcome/selection/ASS are now frozen for the media-latency
owner's separate accepted-FULLER assembly. That handoff preserves NR10 analysis
and assessment provenance, expected-arrangement uncertainty and the different
accepted delivery-audio branch. No master/latest promotion or source overwrite
occurred in this lane.
