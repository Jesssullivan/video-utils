# Entry gates as task bodies (November 7, 2026)

Linear TIN-7788, ruling TIN-7125 `0690fe88`, plan items 2.1 and 2.2, video-utils half. Stacked on the typed findings
branch. Receipt cites R-HOOK-CONVERGENCE-20261004 (R-N13). Nothing ran on a GPU, an engine or a Hatchet row. Fixtures are
synthetic.

`entry gates | narrate lane | video-utils feat/tin-7788-claims-lexical-gates | local tests below | root integrates`

## What changed

| File | Change |
| --- | --- |
| `narrate/video/entry.py` | `claims`, `intake`, `preflight` and `lexical`, each a refusal with its findings recorded |
| `narrate/video/claims.py`, `bundle.py` | a claim's optional `source`, and `compare_values` |
| `narrate/lexical.py`, `narrate/video/speech.py` | `CheckTool` and `lexical_gate`. The `script` stage's bytes stay |
| `narrate/video/store.py`, `rerun.py`, `render_stage.py` | a refused bundle's digest stands in for the job in `findings` and `round`, and `campaign-bind --before-intake` |
| `narrate/video/cli.py`, `just/narrated-video.just`, `just/narrate.just` | `entry`, `nv-entry` and `NARRATE_LEXICAL_GATE=refuse` |

## Decisions in this draft

- Gates are commands, not stages. A stage key is cached, so a seat's advisory `script` run could leave a fresh node that
  a DAG mode flag would never re-read. A separate read moves no key and cannot be skipped by a cache hit.
- A claim with no `source` refuses in the DAG and passes for a person. A `source` on a person's `claims` run still
  compares, so a wrong number never passes either path.
- The measured number stays out of every report and row. A hardware job's numbers may be private.
- `lexical_tool_*` is a refusal with no row, so it reaches no fix author.
- `frames.py` is unchanged. An unchecked page still does not fail. That is plan item 2.6.

## What the producer template needs

The template's bundle builder stays with its owner seat and is unchanged here. Until it writes a `source` on every claim a
beat speaks, `entry claims` refuses `claim_value_unread` with reason `no_source` on each of its numbers, so no such bundle
passes the DAG. The builder must copy each receipt file into the bundle as JSON, write its sha256 and a pointer to the
measured number, and write `places` when the script says a rounded figure. It must also write `BUNDLES/<job>.entry.json`
beside the bundle, or the job reads `entry: none`, which Cade refuses on a campaign job.

## Open

A fix that rewrites voiced text should pass `lexical.rewrite_check` first, so a rewrite cannot change a protected number.
That belongs to the fix author, plan item 2.4. The row does not name these tasks yet: see the Cade pull request for the
row change, which moves with item 1.5's pin.

The real xoxd-lexical 0.8.0 CLI with Vale 3.14.2 reads as `CheckTool` expects on the `slides` register: clean text gives no
row, a planted attribution gives `XL-ATTR-002`, and no Vale refuses `lexical_tool_absent`. On the `narration` register I
could not produce an Error. `XL-ATTR-002` is off there, the three `Metric` rules gave no Error on a text with a sentence
above 60 words, and the other Error rules have no Vale file. Why the `Metric` rules stay quiet is unknown. So this gate may
refuse nothing on a narration script until the lexicon gives that register an Error it can read. The refusal path itself
is proved here on a stub.
