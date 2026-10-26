---
status: active
summary: Bounded sign, numeric notation and recognized-unit preservation for narration pronunciation, following the accepted E7 consumer source.
---

# Narration quantity preservation (TIN-7097)

## Source lane and integration

Repository: `video-utils`; branch: `feat/narrate-quantity-guard-20261024`; isolated source worktree based on accepted E7 PR43, commit `113426f89fc4239514c62e201b3d6629f1d26f80`. The coordinator retains integration ownership. E7 still follows the existing E2/E4 integration order. Public receipts omit private machine/worktree paths; exact custody is recorded on the owning issue.

This successor owns only `narrate/normalise.py`, its dedicated synthetic test file and this receipt. It leaves the presentation adapter, Dhall source, private lexical catalog, rewritten-script check and original owner worktrees unchanged. Authority: the named E7 follow-up source assignment and R-HOOK-CONVERGENCE-20261004, with advisory hooks (R-N12) and durable evidence (R-N13).

## Behavior and limits

The previous digit-sequence check allowed `-16` to become `16` and `1 ms` to become `1 s`. It remains in place. Every applied pronunciation substitution now also compares ordered numeric literals and recognized units in the surrounding text before recording that substitution. This catches table entries that replace only a sign or unit as well as whole-quantity replacements. Both authenticated upstream and explicit local table layers use the same guard.

Numeric literals retain their spelling, attached or whitespace-separated signs, decimal/grouping punctuation and scientific exponent notation. The explicit unit alias map permits equivalent spoken forms such as `8%` to `8 percent`, `1 ms` to `1 milliseconds`, and `-16LUFS` to `-16 loudness units relative to full scale`. Different scales and storage prefixes stay distinct; no numeric conversion is inferred. Symbols are case sensitive. Unit matching applies to standalone numeric text, not numeric suffixes embedded in identifiers, so existing acronym spell-outs remain usable.

This is a conservative regex guard, not a general semantic parser or proof of factual equivalence. Unknown units, compound units and natural-language quantities are outside its guarantee. Numeric hyphens are retained without guessing whether they describe a range or an identifier; changing a hyphen to a word may be refused. Adding or removing a recognized unit is refused even if a human might infer it from context. The original written-script RewriteCheck remains before the spoken projection; this guard does not replace it or authorize rewriting records.

## Validation

The 78 targeted pure tests passed: dedicated adversarial sign/unit/notation fixtures plus existing lexical and chunker tests. They cover sign removal/insertion, Unicode minus, whitespace-separated signs, decimal/exponent changes, unit removal/insertion, millisecond-to-second and GiB-to-GB changes, ordered sign changes, equivalent spoken aliases, identifier spell-outs, unit-only replacements, upstream/local layering, and preview record isolation. Ruff check/format and diff checks passed.

A private disposable text-only fixture loaded the actual authenticated 47-entry upstream table, verified the pinned projection/order, ran the real two-layer normalizer, and preserved all digit sequences and new quantity signatures. Receipt SHA256: `b5db9882524560bbdefe04159032eb4a2b086c8924a7954b61052f57514ddec5`. The table, transcript, private paths and spoken outputs are not copied into Git. Pure checks used the existing bounded heavy-work entrypoint and already available Python/pytest tools; no dependency provisioning was needed. An initial attempt with the profile Python found pytest unavailable and executed no tests; the existing pytest-equipped environment then completed the checks.

These checks establish bounded source behavior only. No model, engine, audio, renderer, GPU job, service, publishing or runtime activity occurred. Listening and real narration acceptance remain separate with their existing owners.

## Fix round (2026-10-26)

Rebased onto the updated E7 branch (PR43), itself rebased onto main 0a82673. Commits carry `Signed-off-by` and stay signed. Review findings and their disposition:

- Sign words (low-medium): the guard rejected an entry that says a sign. Signs now have explicit spoken aliases, as units do: `-`, `−`, `minus` and `negative` are one sign, and `+`, `plus` and `positive` another, so `-16` may become `minus 16` but not `16` or `plus 16`. A numeric hyphen is still read as a sign; `3-5` to `3 to 5` and `x86-64` to `x86 64` stay refused rather than guessed.
- Unit lists (low): `lexical.UNITS` is now the one unit table. The RewriteCheck and the chunker protect each unit's symbols, now including MHz, GHz, bpm, B, kB and TiB, and the guard reads the same symbols and aliases, now including LU, px, x and KB. So `120 bpm` is no longer split across chunks, and a rewrite from `5 MHz` to `5 GHz` or from `−16 LUFS` to `16 LUFS` is refused.
- Not changed: an identifier spell-out whose number is followed by a unit symbol (`gfx1201 B`) is still refused; that is a safe false refusal and unlikely in a script. The RewriteCheck still accepts `v2` to `v3` and a sign separated from its number by a space (`- 16 LUFS` to `16 LUFS`); both are left for a follow-up on the written-script check.

Validation: `just narrate-lint narrate-test narrate-dhall-check` in the `condense` shell, inside a 6G user memory scope at low CPU and I/O priority: 314 passed, 1 skipped; Dhall check 29 mutations. Fake engine and synthetic fixtures only; no TTS model, voice or clip.
