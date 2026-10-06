# Arrangement-reference skill preparation

Current checkpoint: root releases the new
[guitar-arrangement-reference skill](../../.agents/skills/guitar-arrangement-reference/SKILL.md)
against qualified worker `c6bdc899…`. Earlier preparation-only checkpoints below
remain historical. The local typed route is now integrated; final all29
prompt/validator readback follows the
sole additive same-run arrangement marker selector in the marked-video skill.
No new metadata
evaluation, DSP, render or listening action is performed by this skill lane.

Owner `/root/tool_skills`; worker owner `/root/rhythm_analysis`; hook owner
`/root/tool_hooks`. Root releases coordination after tool28 prompt closure.
This new document owns skill intent only: no worker, API, registry, recipe,
render, inference, annotation or original27 skill changes. Tool29 is not yet
admitted; exact supported schema and frozen qualification precede its skill.

## Definition of done before skill implementation

- Match the frozen worker and closed typed reference/run/output contract, with
  concrete bounded paths, defaults, deadline and receipt schema.
- Distinguish supplied expected arrangement from extracted observations and
  approximate pulse/tempo/anchor evidence; expected counts are never detections.
- Preserve source/native hashes, coverage, boundary latency, null/ambiguous
  alignment alternatives and source-time uncertainty in review candidates.
- Explain supported iteration through fresh output/reference inputs, leaving
  intended score, waveform timing, DSP and listening acceptance separate.
- Validate the new skill, obtain independent forward review and read back the
  complete admitted MCP prompt catalog after hook freeze. Do not advertise29
  or introduce an unsupported observations fixture field into the typed route.

## Concrete worker and proposed route

Current direct worker is `scripts/arrangement_reference.py`:

```text
python3 scripts/arrangement_reference.py REFERENCE --run-dir RUN --output NEW_DIR
```

The direct fixture alternative is `--observations JSON` instead of `--run-dir`.
It is not automatically a public hook capability. The worker owner proposes
typed fields `reference`, `run_dir`, `output`, strings 1–4,096 characters;
reference default `program/demo-arrangement.json`. Exact required/default/path
boundaries, timeout and source freeze await the hook/worker owners. No arbitrary
alignment cost, detector threshold, tempo override, model, interpreter or audio
processing knob is implied.

## Intended skill decisions

Use an explicitly supplied source-bound expected arrangement to compare existing
cached phrase boundaries, not to synthesize detections or constrain automatic
phrase discovery. Validate the reference's provenance, approximate tempo,
anchor interval, section counts and clicks per unit; keep assumptions visible.
Source-specific demo values are reference data, not universal nine-string rules.
An inferred half-time pulse is separate from a declared click tempo; click counts
do not establish meter, note count, downbeats or musical bars.

The run adapter binds manifest/analysis/phrase identities and verifies the
canonical analyzed PCM's bytes/hash. It does not rehash the original encoded
media or decode/audio-extract new boundaries. Record that identity scope rather
than calling it independent original-source or listening verification. Native
PCM, source origin, analyzed coverage and lineage must remain coherent.

Monotonic alignment retains unavailable/ambiguous alternatives. A unit duration
divided by reference click period is `reference_equivalent_clicks`, not an
observed click count. Observed click count remains null. Missing coverage or
uncalibrated boundary latency cannot become a precise performance verdict.
All flags remain review candidates with `performance_issue_confirmed:false`;
expected arrangement assertions plus metadata alignment do not establish a real
missed note, skipped phrase or correct performance without supporting evidence
and listening.

Outputs are a fresh assessment/review-candidates/receipt directory, not a master,
native-editor import or audio correction. Current worker caps reference64KiB,
manifest1MiB, analysis16MiB, phrases4MiB, analyzed PCM1GiB, two result artifacts
2MiB each and receipt64KiB; final hook may narrow these. Expected units are
bounded128 and observed boundaries2048. Read compact status/hash pointers and
full artifacts when needed; do not overwrite an existing evaluation.

For iteration, inspect coverage, candidate timestamps, uncertainty and alternative
alignments first. Research actual boundary/tempo methods through the repo's
primary-source research. Recompute stale upstream phrase evidence through its
supported tool, or refine a reference only using actual supplied intent; keep
each input/version/hash and create a fresh output. Never move the intended anchor
or count solely to improve a score or pretend a reference assumption was observed.
Retain automatic discovery when no intended arrangement exists.

Worker qualification and deterministic randomized metadata properties are pending
final freeze. Such properties concern metadata alignment/marker invariants, not
end-to-end audio extraction, generated music accuracy, actual-take quality,
listening acceptance or master adoption. Skill implementation/readback awaits
that concrete qualification and root's release.

## Released source and confirmed interface

Source readback verifies worker SHA256
`c6bdc8991b6e378f2ab54873e94e23b1cff63073056e4f32b05ab5f7b58f89ae`.
Root/owner attributes forty-eight checks and 320 deterministic randomized
metadata properties to worker qualification, with independent same-source
readback reported separately. These do not establish extraction accuracy,
real performance truth or listening acceptance. The owner reports an authorized
cached NR8 assessment with fifty-five review candidates; that is evaluation
output, not a detected expected click/phrase count or confirmed mistakes.

The owner confirms optional `reference` default `program/demo-arrangement.json`,
required `run_dir`/`output`, path strings1–4,096 and wrapper integer timeout1–120,
default120. Output is a fresh child of the selected run, enforced by the hook;
this is intentionally narrower than the direct CLI's fresh local output route.
The fixed alignment stage's thirty-second limit is distinct from the outer
wrapper. Canonical PCM bytes are read for hashing; audio decoding and DSP remain
false. No public fixture-observations field is added.

The new source skill passes the bundled validator and whitespace check. Independent
read-only forward review and actual initialized all29 prompt/validator proof
follow final typed integration/source freeze; no tool29 availability is inferred
from this source draft alone. Existing twenty-eight skills remain untouched.

## Local integration and final catalog proof

The hook owner freezes the local twenty-ninth typed route and records six
focused tests passing in2.427 seconds, including actual initialized MCP cached
metadata success and stale/hash refusal. Its current
[hook contract](ARRANGEMENT_REFERENCE_TOOL_CONTRACT.md) SHA256 is
`f574350a802b162cca54e46f4dceb3d48f059888563ee9c40a8347f67deef029`.
Root separately authorizes the existing marked-video skill's sole additive
`arrangement_markers` selector: exact same-run-relative JSON1–1,024 characters,
explicit `all-review`, current assessment/reference/artifact hashes, arrangement
marker set selection rather than merging canonical markers. Existing picture,
delivery-audio/source-clock checks and uncertain review claims remain intact;
no recurring operator permission is introduced.

Initial integration locked-venv/file-backed proof validates all29 skill bundles and links,
initializes actual MCP, and reads all29 prompt texts exactly with empty stderr
and zero tool calls. New arrangement skill SHA256:
`e85880cc2f87501a5120471ea5ada390f4d59b3478e2cd92d3cfecfe4a09629f`.
Marked-video skill SHA256:
`149fc96e4e6a2b56b9dd818dff14ddd1f36db130ba3d69f3ab01eef68c5d5648`.
Ordered catalog skill digest:
`030403c0f6148ebd385af5cc3576de62ee7e6014ca1fd66745c2603d61679f4f`.
Whitespace checks pass. This lane performs no metadata assessment, audio decode,
render, model inference, master adoption, installation or publication; actual
cached assessments and video/runtime evidence stay with their owning lanes.

Independent final review identifies one overlay-scope clarification: the current
arrangement marker validator accepts only the demo reference and current pure
`denoised.wav` assessment, whereas the evaluator supports other references and
canonical PCM inputs. The marked-video skill now states that narrower overlay
capability explicitly. This changes guidance only, without worker/schema changes.

Final same-source proof after that clarification again validates all29 bundles/
links and exact initialized MCP prompt texts with empty stderr, zero tool calls
and passing whitespace checks. Arrangement skill hash remains `e85880cc…629f`.
Final marked-video skill SHA256:
`eb51008e3f0bf860ea9e0ea9f8c5e07ef9492741a2301fafa805c9cb22ab0ce2`.
Final ordered catalog skill digest:
`d9271208fe7ffa3e2abd703df4f7429110fe2ca92d2ad581f1a29117bd9a45f1`.
The prior marked-video/aggregate hashes above identify the preclarification
prompt checkpoint. No music quality, actual audio processing, adoption or
publication is inferred from either prompt proof.

Independent read-only exact-sentence closure verifies final marked-video hash
`eb51008e…0ce2` and finds no remaining concrete gap. No edits or worker/MCP calls
occur in that review. The skill lane is source-ready for root publication;
publication itself remains root-owned evidence.
