# Web UI framework and workflow research

Read-only investigation, October6,2026. Owner: `web_ui_future`. Assigned outputs
are this research note and `docs/spec/future/WEB_UI_DESIGN.md`. No sibling repo,
dependency environment, running service or tracker was changed.

## Local evidence

The live video-utils worktree is shared and dirty. Inspection used `AGENTS.md`,
`README.md`, `scripts/review_server.py`, `scripts/report.py`, and the HTML/JS review
assets. Their current source implements an existing-run loopback review screen,
not a clip-upload/processing app. The design records actual players, span looping,
candidate filters, five note topics, three note states, optimistic revisions and
JSON download. Browser visual/runtime acceptance was not rerun in this lane.

The sibling xoxd contract was read before inspecting its files.

**Correction 2026-10-07:** an earlier version of this passage reported Effect `^3.21.2` and Skeleton `4.15.2` for xoxd.ai. That came from a stale local checkout (branch `codex/cloudflare-pages-projection-truth`, `5e081b2`, 2026-05-08), not the default branch, and was wrong as an estate statement. Verified against remote default branches on 2026-10-07: xoxd.ai `main` `cc570c3` declares Skeleton `5.0.1` and Effect `^3.22.2`; site.scaffold `main` `9fef9ee` declares Skeleton `5.0.1` and Effect `^3.22.1`; tinyland.dev (`xoxd-ai/tinyland.dev` `main` `7422982`) declares Skeleton `^4.15.2`. The operator rule is that the whole estate uses the latest Skeleton v5 and latest Effect (npm latest on 2026-10-07: Skeleton `5.0.1`, Effect `4.0.1`); video-utils `web/` complies (Skeleton `5.0.1`, Effect `4.0.1`), and the Effect 3 and Skeleton 4 declarations above are estate drift tracked separately. `AGENTS.md` explicitly calls it a static brand/project
site and forbids adding runtime business/auth/data responsibilities there.

`src/routes/+layout.svelte` demonstrates `$props`/`$state`, skip navigation,
responsive navigation/dialog patterns and theme choice. `src/lib/effect/schema.ts`
provides schema decoding/error formatting; `runtime.ts` has an empty placeholder
layer and a top-level runner. Useful patterns are explicit entrypoints, schema
boundaries, local reactive state and theme/accessibility conventions. Their source
is not evidence of durable media jobs, an Effect4 migration, or a safe environment
cast for the future service. No code was copied or sibling tests executed.

The repository's existing `docs/research/REPOSITORY_PATTERNS.md` corroborates the
same source identity. `docs/research/XOD_SPECTROGRAM.md` records the actual private
`xoxd-ai/xoxd-spectrogram` identity, lack of an explicit redistribution license,
feature conventions and selected PCEN experiment limits. This lane reused that
repo-local study; it did not reacquire the private package or execute its models.
No spectrogram implementation was found in the bounded xoxd.ai/xoxd.ai-site
source scan; that does not imply the private package is absent elsewhere.

## Current primary sources

Links were opened through the web tool on October6,2026. They establish available
official features, not local compatibility or production readiness.

| Source | Dated finding / consequence |
| --- | --- |
| [Svelte runes](https://svelte.dev/docs/svelte/what-are-runes) | Runes supply Svelte's compiler-supported reactive constructs. Proposed use is draft/selection/player state; job authority remains server-side. |
| [SvelteKit remote functions](https://svelte.dev/docs/kit/remote-functions) | Still experimental; input validation matters. Current docs specify remote-functions and async opt-ins in Vite configuration and note Kit3's configuration change. Pin Kit major before applying examples; retain stable actions/endpoints fallback. |
| [SvelteKit Node adapter](https://svelte.dev/docs/kit/adapter-node) | Official standalone Node server adapter exists. It differs from local xoxd's static adapter; upload/body limits and serving origin need explicit qualification in the backend lane. |
| [Effect4 September recap](https://effect.website/blog/effect-v4-rc-september-recap) | Updated October1,2026; explicitly reports stable Effect4.0. Availability is established; this repo's combined version/validation adapter remains unqualified. |
| [Skeleton5 migration](https://www.skeleton.dev/docs/svelte/get-started/migrate-from-v4) | Official guide explicitly describes v4→v5 and theme/core API changes. Existing custom themes/components need migration review. |
| [Skeleton SvelteKit installation](https://www.skeleton.dev/docs/svelte/get-started/installation/sveltekit) | Official integration path exists. A locked SSR/accessibility fixture must qualify the selected versions here. |
| [ezgif video conversion](https://ezgif.com/video-to-gif) | Public file/URL upload followed by conversion choices supplies a familiar task sequence. The practice UI adapts the staged interaction, with local/private processing; no recording was sent there. |

The requested Effect4/Skeleton5 direction is reasonable to qualify. The local
scaffold does not already use those versions. The investigation also found an
Effect Standard Schema page that redirected to v3 documentation; it is
insufficient proof of a v4 remote-function input adapter. Prove that exact adapter
in the future fixture instead of copying a version-mismatched example.

## Bounded recommendation and receipt

Prioritize current local tone/arrangement review; optional later framework
qualification isolates Svelte5, a pinned Kit major, Effect4 and Skeleton5 with
render/hydration, schema errors, interactive focus and stable fallback checks.
Do not migrate DSP into TypeScript, treat experimental RPC serialization as a
public agent API, or make hosted-runtime claims from a component fixture.

`web_ui_future | owns two documentation files; xoxd sibling inspection read-only
| operator-requested future UI and framework design | video-utils AGENTS;
R-HOOK-CONVERGENCE-20261004 R-N12/R-N13 | shared dirty video-utils; xoxd source
identity inspected | design/research recorded; no app implementation, external
messages, publication, model acquisition, service signal or host mutation`
