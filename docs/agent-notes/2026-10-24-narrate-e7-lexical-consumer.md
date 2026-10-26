# E7 narration lexical consumer source

repo | Jesssullivan/video-utils | branch feat/narrate-e7-lexical-narration-20261024 | integration main after E2/E4 | base 924209674ec40bccf41ae7c180b4593ec95f2b0c | active development existing remote development seat (private machine/path receipt on TIN-7097) | owner xoxd_lexical_contract | source only | next independent review and existing-owner integration

Authority: the operator-approved narration E7 plan and the October 24 instruction to continue the existing voiceover/character work. Root explicitly assigned this isolated source successor while preserving the original narration owner and E7-after-E2/E4 integration order. Existing main and unrelated dirty work were preserved. No model inference, engine service, real voice, media render, account operation or runtime activation occurred. This public repository holds no private lexical table, styles, source transcripts, voice clips, consent evidence, machine hostname or personal path.

## Actual change

The consumer still selected lexical 0.2.0 and the slides register, despite the released 0.3.0 narration register. The example now pins the actual v0.3.0 tag commit a054ff37082d3f89391d90de5665f0799cb7c87e, estate JSON SHA256 0337b0dcfefda437e6524310c8ba76f37d95aaf97f6ae1f55810b7282b2d5d10, narration prompt c51d15e97fccf5c0b479a7864bd0ef5cfb7c099da51f56d5d13be741680c01b0 and Vale narration register 380274db85557f01b8293fe308bcff6e3ba4233939fe8949e3082f6512d2c076. Generated example JSON came from the owning Dhall recipe.

Release selects the register-specific narration prompt, verifies its existing declared digest and refuses a missing or malformed shared pronunciation table. The table already lives inside the verified estate JSON. It is consumed from the explicit private release directory, never fetched implicitly or copied into this public source. Legacy register fixtures retain their existing prompt selection and no implicit shared pronunciation layer.

Written script RewriteCheck still runs before spoken normalization. The authenticated upstream pronunciation layer runs first, then the explicit local Dhall overlay. Longer written terms run first in each layer. Preview chunk sizing records no substitutions; committed normalization records separate local and upstream table digests and per-segment substitutions. The existing digit-sequence guard applies to both layers. It is not a complete quantity validator: inherited synthetic sign/unit changes can pass it. Entry review must preserve sign and unit meaning; actual pinned 47 entries passed the text-only qualification without such changes. This is a spoken projection, not a rewrite of factual transcripts or the canonical written script.

## Validation

Forty pure lexical/chunker tests passed through the normal bounded heavy-work entrypoint, including selected prompt/digest, malformed/missing table refusal, upstream-before-local order, preview evidence isolation and backward-compatible local-only behavior. Synthetic public fixtures carry no private vocabulary table. Ruff check/format and diff checks pass for the changed Python files.

The owning narrate-dhall-render and narrate-dhall-check recipes passed, including type/format checks, exact generated JSON comparison and 29 refusal mutations. No real clips or rendered speech were used. In a private disposable release fixture, a text-only qualification loaded the exact pinned release, checked all 47 upstream entries through the actual two-layer normalizer, confirmed longest-form order against the pinned narration projection and preserved every digit sequence. Its receipt SHA256 is 170ed584ec55c6db32ce8160a8a78d455e4b76703b38e135f1bf6c08f16ca40f; exact custody is recorded privately on TIN-7097. The private table and spoken outputs are not vendored here.

These checks qualify source and textual consumer behavior. They do not establish engine selection, listening/SIM acceptance, voice consent, a rendered presentation, character identity approval, realtime video or public launch. Those remain with their existing owners. This patch selects no voice and changes no consent record.

Independent review verified the prompt/register/lexicon pins, preview isolation, upstream-before-local evidence and the actual 47 table. It reproduced the inherited digit-only limit with synthetic sign/unit changes. The spec and this receipt state that limit explicitly; this migration does not claim general semantic quantity validation. The original source owner retains that separate hardening scope.

## Fix round (2026-10-26)

Rebased onto main 0a82673; #44 stays stacked on this branch. Commits carry `Signed-off-by` and stay signed. Review findings and their disposition:

- WER gate (high): per-chunk WER, in the render's best-of loop and in `narrate evaluate`, now scores the transcript against the written chunk (each applied entry's spoken words mapped back to its written form) and against the spoken projection, keeping the lower (`qa.chunk_wer`). A transcript that writes `MCP` or `M C P` for `MCP` no longer burns every take. A misread term still fails.
- Overlay (medium): a local entry whose written form matches an upstream entry's, ignoring case, now replaces that upstream entry; the manifest lists each replaced upstream entry in `pronunciation.upstream.overridden_by_local`. The spec says so.
- Tests (medium): synthetic tests now cover longest-first order with an overlapping prefix in both layers, `caseSensitive`, the overlay and the WER back-mapping; reversing the sort or ignoring the case flag fails them. A render-level test pins the synthetic narration register and checks the upstream record, the WER gate and verify together.
- `Release.record()` now names the prompt file it hashed; the `lexical.py` docstring names both prompt files.
- The order in the release's `narration.json` is still not read at load time; the consumer derives longest-first order from the authenticated lexicon. A `xoxd-lexical@0.4.0` pin needs a code change because its lexicon still reports version 0.3.0; the 0.3.0 pin stands.
- Missing spaces in this receipt are fixed, and two names that appear nowhere else in the public repository are removed.

Validation: `just narrate-lint narrate-test narrate-dhall-check` in the `condense` shell, inside a 6G user memory scope at low CPU and I/O priority: 259 passed, 1 skipped; Dhall check 29 mutations. Fake engine and injected transcribers only; no TTS model, voice or clip.
