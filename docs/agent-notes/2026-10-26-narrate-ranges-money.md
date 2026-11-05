---
status: active
summary: Narration says numeric ranges and dollar amounts in words, reads each expansion back to its written value, and keeps WER, the chunker and the RewriteCheck consistent with it (TIN-7087 follow-up).
---

# Narration ranges and money (TIN-7087)

## Source lane

Repository: `video-utils`; branch `feat/narrate-ranges-money-20261026` from `origin/main` 8791973 (which carries
the v0.3.0 narration register, the shared `lexical.UNITS` table, the quantity guard and the sign aliases).
Authority: the TIN-7087 follow-up assignment and R-HOOK-CONVERGENCE-20261004 (R-N12 advisory hooks, R-N13
receipts). The request came from a confidential script. No text, name, address or amount from it is in this
repository; every fixture is synthetic.

## Behaviour

- `narrate/amounts.py` finds ranges (en dash, `to`, `through`, and a hyphen-minus when `$` or a unit marks it)
  and dollar amounts, and says them in words before both pronunciation layers. A unit after a range comes from
  `lexical.UNITS`.
- Each expansion is read back by a separate parser to its values, unit and connector, and refused
  (`NormaliseError`) on any difference. It is not a table substitution, so the digit guard does not refuse it.
  A table entry still cannot turn `3-5` into `3 to 5`.
- `pronunciation.expansions` in the manifest records segment, kind, written, spoken, connector, values and
  count. `recorded_aliases` and `Normaliser.aliases` include the expansions, so WER maps a spoken expansion back
  to its written form.
- `qa.chunk_wer` also scores the transcript with any range or amount it wrote in digits said in words; whisper
  may write numerals or words for the same correct reading.
- The chunker blocks splits inside a written range or amount.
- The RewriteCheck puts a range or amount said in words back to the original's written form when the words read
  back to the same values, then runs its byte-for-byte check.

Limits are listed in `docs/spec/NARRATE.md`, "Ranges and money". Signed amounts, identifiers, dates, times,
versions, bare hyphen pairs, other currencies and money with scale words stay as written. A bare range with an
ungrouped four-digit integer (a year, phone number or standard) stays as written, and a pronunciation entry with
digits in its written form keeps its span for the table. A rewrite that adds a number in words is outside the
RewriteCheck, as it was before.

## Review round 1

The PR review found two blockers and seven smaller findings. All are fixed in the rewritten commit:

| Finding | Fix |
| --- | --- |
| Example values copied from the request | Replaced with synthetic values in code, spec and tests |
| RewriteCheck took a partial number phrase | `restore` maps back only a whole phrase: no sign before, no extension after |
| Tables ran on expanded words | Expansions are held out of the text while both table layers run |
| Other currency signs and `§` | Excluded on both sides of an amount |
| Years, phone numbers, standards | Bare ranges with an ungrouped four-digit integer stay written; digit-keyed table entries opt a span out |
| `B`, `x`, `dB` as markers | Not hyphen-minus markers; `B` never a range unit; `x` only against the digits; ranges must ascend |
| Spaced and em dashes | A spaced en dash is a range; em dash and spaced hyphen-minus stay written |
| `$5-year` | A hyphen-minus and a word after an amount keep it written |

## Validation

Synthetic fixtures and the fake engine only; no TTS model, voice or clip ran. Gates ran in the `condense` dev
shell inside a 6G user memory scope with no swap at low CPU and I/O priority. Results are on the PR.
