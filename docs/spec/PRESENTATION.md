# Private character presentation adapter

The input planner joins an existing slide/capture project to approved character
manuscripts, narration and avatar inputs. It prepares the existing assembly
pipeline's files and argument vectors. It never generates speech, invokes a
provider, runs FFmpeg, publishes or changes the original client edition.

Run `just -f narrate/presentation.just plan MANIFEST NEW_PRIVATE_OUTPUT`, or
`python3 -m narrate.presentation MANIFEST NEW_PRIVATE_OUTPUT`. The output must be
a new absolute directory outside the source project. Files are0600 and directories
0700. Existing output is never overwritten. No private inputs belong in Git.

## Input and meaning

`narrate/dhall/Presentation.dhall` is the normalized input type. The synthetic
example lives in `narrate/dhall/examples/presentation.dhall`; the owning Dhall
recipes render/check it. Omitted optional media/script descriptors normalize to
null. The actual private normalized JSON can be checked with json-to-dhall against
`(./narrate/dhall/Presentation.dhall).Type`, without copying it into this repo.

| Field | Meaning |
| --- | --- |
| projectRoot, source | Existing private project and original repository/commit claim |
| clientConfig | Exact digest of the original voice-only/PIP-off config |
| sourceFiles | Explicit root-relative, digest-bound slide, HTML, clip-map and still inputs |
| expectedPages, pages | Unique page IDs, original script hashes, target seconds and capture hashes |
| assetsRoot | Explicit separate root for approved internal character inputs; null while absent |
| approvedScript | Separately authored character script, subject/scope and authority reference |
| narration | Approved audio, bound to the exact approved script digest |
| avatar | Approved image/video, subject/scope, authority reference and media kind |

Authority references are caller declarations, not manufactured human approval.
An existing internal authoring ruling can bind a reviewed script. This introduces
no new operator permission flow. It does not turn an unreviewed file into an
approved voice or character. The character and the operator's authorized clone
remain different identities. Original speaker claims must be adapted deliberately,
with factual review, rather than recited under another identity by accident.

## Stages and output

All declared input files are checked against their hashes. Paths stay inside
their declared roots; symlink file paths, traversal, duplicate page IDs and
foreign subject/scope inputs are refused. The original client config remains
voice-only with PIP off. Its files are never written.

Missing approved inputs produce a blocked plan, not fake readiness. Reviewed
scripts can still prepare provider input before media exists: preserve their exact
Markdown in the output manuscript folder and derive plain speech through the
existing Markdown adapter. Front matter, source trailers, headings, build comments
and clip/PIP control cues are not spoken. Both full-script and spoken-projection
digests are recorded; the canonical written script is not replaced by that projection.
Captions in the existing assembler use the exact approved character manuscript.

Once script/audio/avatar inputs are present, the adapter also checks the assembly
source bindings. Slide, HTML and clip-map files need explicit admitted hashes.
Still images need a separate digest inventory, because a deck hash does not
authenticate derivatives. Missing still evidence leaves assembly blocked. Config
paths cannot escape the project or fall back to arbitrary external files. The
supported clip map is an explicit `clips` list. Each row names `clip` and may
provide a root-relative `path`; otherwise the source is `clips_dir/<clip>.mp4`.
Alternate `media` maps are refused. Only admitted capture bytes are staged into
the internal clip directory, with hashes rechecked after copying. Generated clip
and capture maps point only at that namespace. Historical unselected media in
the source directory is retained and cannot be discovered by the internal cut.

A prepared internal config uses a separate manuscript/take/output namespace,
Cade's speaker identity, PIP in the chosen corner and no recording-drop, editing
push or publication destination. Argument vectors would mux approved narration
with the approved avatar, then call the existing project assembly code. Images
and short avatar videos repeat until narration ends; target duration is a planning
budget, never permission to cut spoken words. A repeated speaking avatar still
needs actual synchronization/visual review. No command is executed by planning.

`inputInspectionReady` means every declared character input is present and
hash-checked. It is not media probing, consent verification, engine readiness,
render authorization or a finished artifact. Every plan states that probing and
render authorization remain required. Source tests and typed inputs do not prove
listening acceptance, lip synchronization, captions in a rendered video or release.

## Validation

Pure synthetic fixtures cover missing-input readiness, exact source preservation,
private modes, source/output separation, identity/scope, script/audio binding,
symlink/traversal refusal, inherited config path containment, digest-bound stills,
source-trailer/control-cue exclusion and avatar/narration duration ordering. They
run through the existing bounded test entrypoint without any media decoder,
provider, model, real voice or GPU job.
