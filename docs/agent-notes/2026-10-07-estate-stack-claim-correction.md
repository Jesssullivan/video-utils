# Correction: false "estate standard" Skeleton 4 / Effect 3 claim

Owner: `/root` Claude session `video-utils-d6`. Authority: operator correction 2026-10-07 ("anything asserting this false info must be expunged right away"; "the full estate including xoxd.ai MUST be on the very latest Skeleton v5 and latest Effect"); R-HOOK-CONVERGENCE-20261004 R-N13.

## What was wrong

During the 2026-10-07 routing interview root stated that the estate standard was Skeleton 4.15.2 and Effect 3.x and that xoxd.ai defers Skeleton v5. Four committed documents carried the same stale snapshot from October 6 lanes:
`docs/research/2026-10-06-web-ui-framework-qualification.md`, `docs/research/2026-10-06-future-web-backend.md`, `docs/spec/future/WEB_BACKEND.md`, `docs/spec/future/WEB_UI_DESIGN.md`.

## Root cause

Read-only scouts read sibling working trees on stale feature branches instead of remote default branches: xoxd.ai was checked out at `codex/cloudflare-pages-projection-truth` `5e081b2` (2026-05-08) and site.scaffold at `tin-75/observability-consumption-pattern` (2026-08-22). Root repeated the result without verifying the remote head.

## Verified facts (remote default branches, fetched 2026-10-07)

| Repo | Default branch head | Skeleton | Effect |
| --- | --- | --- | --- |
| video-utils | `main` | 5.0.1 | 4.0.1 |
| xoxd.ai | `origin/main` `cc570c3` (2026-10-05) | 5.0.1 | ^3.22.2 |
| site.scaffold | `origin/main` `9fef9ee` (2026-10-05) | 5.0.1 | ^3.22.1 |
| tinyland.dev | `xoxd-ai/tinyland.dev` `main` `7422982` (2026-10-02) | ^4.15.2 | not a direct dependency |

npm latest on 2026-10-07: Skeleton 5.0.1, skeleton-svelte 5.0.1, Effect 4.0.1, Svelte 5.57.2, SvelteKit 3.0.1.

## Actions

- The four documents now carry the verified facts with a dated correction line; no remaining assertion of the stale pins exists in the repository (`git grep` for `4.15.2`, `3.21.2`, `Effect3` returns only the correction lines).
- Interview statements made in chat cannot be edited; this record supersedes them.
- Operator rule recorded: the whole estate uses the latest Skeleton v5 and the latest Effect. Remaining drift (xoxd.ai and site.scaffold on Effect 3; tinyland.dev on Skeleton 4) belongs to those repositories' owners and is raised in Linear; video-utils does not edit sibling repositories.
- Prevention: any estate or sibling-repository fact must be read from the remote default branch (`git fetch` then `git show origin/<default>:<path>`), recording the commit and date; a local working tree is never evidence of estate state.

## Broadcast and responses (2026-10-07 ~03:35–03:55Z)

At the operator's direction ("please message tinyland and other claude agents about this, this is a p0 level issue"; "same with gloriousflywheel agent, and others"), root sent the same P0 notice. Each notice quoted the operator verbatim and gave the verified table and the remote-default-branch rule.

Neo sessions:
- tinyland-dev-73
- gf-core-adoption-orchestration
- gftb-crank-deployment-lanes
- blahaj-estate-workstream-resume
- Subagent pool refactor and harness upgrade research

Sting sessions, over a LAN OpenSSH tunnel (cwd-verified):
- xoruby (PID 264882), together with the SSOT ACK
- llama (PID 132037)
- tummycrypt (PID 1742684)

Linear: TIN-5694 comment 1bce165f, and the new P0 tracker TIN-5716.

Responses so far:
- **gftb.** Upstream platform main b7f5b296 is on Skeleton 5.0.1 and Effect ^3.22.1, which is behind. Its Effect 4 upgrade lane is open. gftb-site is compliant. No false-standard docs.
- **blahaj.** No frontend and no Skeleton/Effect dependency. Nothing in its lane.
- **tinyland-dev-73.** Recorded as ruling RP1 on TIN-3692. It is launching a Wave C workflow that upgrades site.scaffold, xoxd.ai, tinyland.dev, blog, darkmap, the registry modules and unowned spokes to Skeleton 5.0.1 and Effect 4.0.1. The same wave expunges false-standard docs estate-wide, including its own 09-22 "Effect v4 NO-GO" and "every spoke on Effect ^3" lines. It also reports darkmap main on Skeleton 4.15.2 and blog-agent on Effect 4.0.0-beta.
- **xoruby.** SSOT ACK posted. D7 is accurate, with the precision that training is on operator-controlled lab hosts; the weights sentence is root's reading. The new P0 row was proposed to the document owner.
