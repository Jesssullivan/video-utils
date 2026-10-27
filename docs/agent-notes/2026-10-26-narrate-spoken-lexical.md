# narrate spoken and the narration lexical check (2026-10-26)

Ticket TIN-7097 (parent TIN-7084), from the field report in TIN-7097 comment 723dd1b6. Authority:
R-HOOK-CONVERGENCE-20261004 (R-N12, R-N13) and the root task for this lane.

| stream | owner | repo/branch | state/evidence | next |
| --- | --- | --- | --- | --- |
| voiced-text check | narrate W5 | video-utils `feat/narrate-spoken-lexical-tin-7097` | source and synthetic tests | root review and landing |

## What changed

- `python -m narrate spoken INPUT [--adapter KIND] [--format lines|json|srt]` (`narrate/spoken.py`) loads the
  input with the render's adapter and prints only the IR's segment text.
- `just narrate-spoken` and `just narrate-lexical-check` (`just/narrate.just`). The check reads the release a
  render pins (`NARRATE_LEXICAL_DIR`, else `lexical` in `narrate.toml`), links it as `dist/` in a temporary
  `XOXD_LEXICAL_HOME` and runs `bin/xoxd-lexical` beside it, else the one on PATH. It refuses a CLI whose
  `version` is not the release's. Without a CLI or Vale it prints a notice and exits 0.
- `narrate/tests/test_spoken.py`: a synthetic manuscript page with front matter, two `[at]` beats, a
  `[clip: ...]` line, HTML comments and a `Sources:` line; SRT, WebVTT and dialog round trips; cue ids in JSON.
- The MCP tool drafts are unchanged (W7 owns admission).

## Evidence

A manual run against an export of the xoxd-lexical `v0.4.0` tag with Vale 3.14.2. On the fixture page the raw
check gave 7 info findings, all on lines no render voices. `just narrate-lexical-check` on the same page gave 0.
An em dash added to a spoken line gave 1 finding, XL-PUNC-001, at `<stdin>:1:37`.

Review round (PR #55): the fixture page is now invented text. The recipe was rerun against the Nix
`xoxd-lexical-0.4.0` and `-0.5.0` packages. A release directory not named `dist`, with 0.5.0 first on PATH,
now checks with `xoxd-lexical@0.4.0+sha256:76240f8b...`. A CLI without Vale, a CLI that reports another
release and no CLI each print a notice and exit 0. On the new page the raw check gives 7 info findings and
the recipe 0. An em dash in its first spoken line gives XL-PUNC-001 at `<stdin>:1:40`.

## Open

- The `v0.4.0` dist reports `xoxd-lexical@0.3.0+sha256:0337b0dc...` from `version`, as TIN-7097 comment
  ce40f785 records for its lexicon.
- The recipe does not verify the job's pinned digests. A render still does.
- A direction line with a nested `[` or `]` is not a direction to the Markdown adapter, so a render voices it.
  `narrate spoken` shows the same text, so the check flags it too.
- XL-VOC-006 on a hyphenated compound (item 2 of comment 723dd1b6) is upstream in xoxd-lexical.
