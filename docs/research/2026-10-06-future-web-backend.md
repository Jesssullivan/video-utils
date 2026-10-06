# Future web backend research and interface audit

Date: October 6, 2026. Lane: `web_backend_future`. Status: documentation only;
read-only repository/estate inspection and primary-document review. No service
deployment, sibling repository edits, tracker writes or media processing.

## Current source evidence

- `program/tools.json` contains 28 descriptors, including the new experimental
  `apply_capture_profile`; this is a mutable shared-worktree snapshot.
- `scripts/tool_api.py` validates a deliberately restricted schema vocabulary,
  constructs fixed allowlisted commands and returns bounded JSON. It exposes
  local paths, not uploaded-artifact authorization. Generic supervision checks
  owned process-group identity on hard timeout; this is not the newer capture
  application's full resource/ownership/publication qualification.
- `scripts/mcp_server.py` implements local serial stdio tools/prompts with a
  1 MiB message limit. It explicitly ignores cancellation notifications and
  advertises no tasks/progress capability.
- `scripts/review_server.py` binds loopback with 16 bounded handler workers,
  Host/Origin checks, mutation token, range playback and source-bound revisioned
  annotations. It has no upload or durable processing-job endpoint.
- `docs/spec/APPLY_CAPTURE_PROFILE_TOOL_CONTRACT.md` documents the separate
  application adapter, 12–600 s outer budget, source/PCM/log limits, two threads
  and pinned recovery receipts. These guarantees do not cover all other tools.
- Read-only `/Users/jess/git/xoxd.ai/package.json`, `svelte.config.js`,
  `src/lib/effect/{schema,runtime}.ts` show Effect `^3.21.2`, Skeleton `4.15.2`,
  Svelte `^5.55.5`, Kit `^2.59.1`, static adapter and runes. Its June 5 Skeleton
  watch document is a historical upgrade policy, not proof of today's upgrade.

## Primary sources checked October 6

| Primary source | Supported observation | Architecture implication / limitation |
| --- | --- | --- |
| [SvelteKit remote functions](https://svelte.dev/docs/kit/remote-functions) | Typed server calls offer query/form/command/prerender, runtime input validation, and remain experimental; current docs describe v3 configuration | Thin submission/review BFF only; ordinary endpoints/actions remain fallback; match locked Kit version |
| [SvelteKit Node adapter](https://svelte.dev/docs/kit/adapter-node) | A server adapter builds a Node server with deployment/body-limit configuration | Static xoxd scaffolding needs explicit dynamic-server qualification; it is not already a job backend |
| [Effect September recap, updated October 1](https://effect.website/blog/effect-v4-rc-september-recap) | Reports stable Effect 4.0 and v3 migration changes | v4 is available upstream; local v3 helpers/lock and schema interop still need qualification |
| [Skeleton migrate from v4](https://www.skeleton.dev/docs/svelte/get-started/migrate-from-v4) | Documents v5 migration and API/theme changes | Reuse design intent with deliberate component/token migration, not assumed drop-in compatibility |
| [FastAPI background tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/) | Suggests separate larger tools for heavy computation beyond simple in-process background work | Proposed durable workers are outside HTTP process; FastAPI supplies the control surface, not processing durability |
| [Flask async/await](https://flask.palletsprojects.com/en/stable/async-await/) | Async requests still occupy a worker and spawned tasks can be cancelled when the request event loop ends; advises a task queue | Flask remains viable as a control API, never a media scheduler implemented by spawning request tasks |
| [Rails Active Job](https://guides.rubyonrails.org/active_job_basics.html) | Provides background jobs and Solid Queue; enqueue/database transaction behavior needs attention | Ruby is plausible if estate reuse justifies it; preserve independent source-bound worker protocol |
| [MCP 2025-11-25 transports](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports) | Defines stdio and Streamable HTTP with transport-specific security requirements | Remote MCP needs a separate authenticated adapter/qualification; local stdio is not web support |

The recommendation in [WEB_BACKEND.md](../spec/future/WEB_BACKEND.md) is an
engineering inference from the current Rust/FFmpeg/Python split, the user's
Svelte/Effect preferences, local estate patterns and these primary docs. It is
not an upstream endorsement of this exact combination or a measured superiority
claim. FastAPI/SQLite/private filesystem minimizes the first Python job-adapter
boundary; a qualified Effect control backend could replace that HTTP layer
without rewriting DSP. A second scheduler would add inconsistent ownership.

Framework availability does not solve distorted nine-string accuracy, unknown
tonic/meter, performance grading, output mastering or missing low-string weight.
Those remain source-bound processing/evaluation/listening milestones. The web
design carries explicit evidence, ambiguity and matched-level comparisons rather
than silently changing their interpretation.

## Durable receipt

`web_backend_future | video-utils owned WEB_BACKEND.md and this note |
future architecture requested by operator | R-N13; R-HOOK-CONVERGENCE-20261004;
TIN-3692 98cf680c-7299-4949-bfb2-60079053ad43 | existing local interfaces only |
proposed design and measurable untested SLOs; no runtime activation`
