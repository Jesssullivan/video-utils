# Local agent tool hooks

`just mcp` starts a repository-local stdio MCP server. The client launches it as a
subprocess; there is no network listener or global configuration change. The
server uses Python standard-library JSON-RPC and fixed worker dispatch, with no
MCP SDK dependency. A configured client can use an absolute Python executable
and `/absolute/path/video-utils/scripts/mcp_server.py`; the worker root resolves
from the script location, independent of the client's working directory.

## Protocol and discovery

Supported protocol versions are `2025-11-25` and `2025-06-18`. Unsupported client
versions receive the newest supported version; the client must disconnect if it
cannot speak it. Send `initialize` with `protocolVersion`, `capabilities`, and
`clientInfo`, then `notifications/initialized`. This implements the official
[MCP lifecycle](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle).

Each UTF-8 JSON-RPC message occupies one line. Standard output contains protocol
messages only; worker logs are captured and diagnostics use standard error.
EOF terminates the server. There is no invented shutdown RPC, HTTP transport,
agent sampling, task capability, or protocol resource subscription. See the
[stdio transport](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports).

- `ping` returns an empty object.
- `tools/list` returns twelve typed tools, including schemas, annotations and
  `video-utils` metadata for skills, intent, dependency suggestions and status.
- `tools/call` dispatches a validated tool invocation to a fixed local worker.
- `prompts/list` lists the twelve skill directory names.
- `prompts/get` reads the actual skill file and adds optional string context
  `input`, `run_dir`, and `goal` as a separate user message containing JSON data.

Tools and prompts advertise a static finite catalog with `listChanged: false`;
nonempty cursors are rejected. Prompt arguments do not become worker arguments.
Protocol and schema errors use JSON-RPC errors. Worker failures use a successful
JSON-RPC response carrying `isError: true`, as specified by
[MCP tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools).
Successful calls contain both JSON text and the same object in
`structuredContent`, matching the advertised object `outputSchema`. Skill
messages follow the [MCP prompts](https://modelcontextprotocol.io/specification/2025-11-25/server/prompts)
interface.

## Tools and agent workflow

`program/tools.json` is the discoverable specification. Each tool records
purpose, strict input schema, limitations, implementation status, evidence kind,
repository skill, recommended predecessor tools and an identify/research/iterate
workflow. Recommended dependencies are discovery guidance, **not an enforced
processing DAG**. Independent worker calls remain supported. The `pipeline`
hook evaluates an existing artifact provenance DAG, checks processed-source
lineage, and creates reference-based review candidates. It does not run the
restoration and analysis workers in dependency order. The `markers` hook exports
existing flags as generic seconds-based JSON/CSV; native editor adapters remain
unvalidated.

| Tool | Worker behavior | Skill prompt | Status |
|---|---|---|---|
| `probe` | Streams, timeline and SHA-256 | `video-probe` | Available |
| `denoise` | Conservative restoration and residue | `guitar-denoise` | Available; listening pending |
| `bpm` | Periodicity/grid candidates | `guitar-bpm` | Experimental |
| `noise` | Quiet-region/spectral candidates | `guitar-noise` | Experimental |
| `tone` | Low-register and other band energy | `guitar-tone` | Experimental |
| `notes` | Candidate periodicity; transcription unknown | `guitar-notes` | Experimental |
| `rhythm` | Signed onset-to-grid offsets | `guitar-rhythm` | Experimental; no performance grade |
| `phrases` | Envelope boundary proposals | `guitar-phrases` | Experimental; musical phrase unknown |
| `export` | WAV run and synchronized-video export | `media-export` | Available; acceptance pending |
| `report` | Local audition/evidence HTML | `guitar-report` | Available |
| `pipeline` | Existing-artifact provenance and reference review | `guitar-pipeline` | Experimental |
| `markers` | Generic source-timestamp CSV/JSON | `phrase-markers` | Experimental; editor import unvalidated |

The music context is nine-string, downtuned deathcore/technical guitar, with
intentional fundamentals around 32 Hz. Hooks do not automatically high-pass,
notch mains frequencies, or infer tone quality from less distortion. An agent
reads the relevant skill, identifies the operator's intent, researches primary
sources, compares at most three candidates by default while changing one knob
at a time, and retains source/evidence and uncertainty. No inference becomes an
intended note, missed/skipped beat or musical phrase mistake without an approved
reference. Musical phrases and beat-grid phase are distinct from physical audio
phase.

Invocation examples (replace private paths locally):

```json
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"local-agent","version":"1"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"prompts/get","params":{"name":"guitar-denoise","arguments":{"goal":"Preserve 32 Hz guitar fundamentals and attacks"}}}
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"denoise","arguments":{"input":"/private/take.mov","profile":"conservative3","timeout_seconds":600}}}
```

Without an MCP client:

```bash
python3 scripts/tool_api.py list
python3 scripts/tool_api.py describe rhythm
python3 scripts/tool_api.py run rhythm --arguments '{"input":"/private/take.mov","run_dir":"/private/run-a","backend":"stdlib"}'
```

## Bounds, outputs and limitations

Inputs reject unknown keys, wrong types, nonfinite numbers and unsupported
knobs. The registry loader rejects unsupported input-schema keywords rather than
silently ignoring them. Dispatch always uses subprocess argument arrays and an
allowlist of repository workers; paths containing shell syntax are literal
paths. Denoise profiles are restricted to `bypass`, `conservative3`, and `mild6`.
BPM/rhythm accept `backend` and an optional 20–400 BPM seed. Noise/tone/notes/
phrases have fixed worker settings in this initial version; no extra knobs are
invented. `pipeline` accepts `run_dir` and an optional existing local `reference`
JSON; its worker validates approval and expected rhythm. `markers` accepts only
`run_dir` besides the common deadline; no editor-compatibility option is implied.
`FFMPEG`/`FFPROBE` overrides are host configuration supplied by the
operator, not tool parameters. No downloads occur through these hooks.

Tools execute serially. A hard per-call deadline defaults to 600 seconds and can
be set to 1–900 seconds. On expiry the server inspects and stops only the worker
process group it created. The returned tool error includes an actor/ownership/
reason/ruling/prior-state/result receipt with the observed PID and process group.
This targets the invocation's recorded ownership under
R-N11; it never signals other sessions. Worker output is file-backed and accepted
JSON is capped at 2 MiB; input messages are capped at 1 MiB. Trusted fixed workers
may write larger temporary log files before this check. Client cancellation
notifications are ignored in the serial implementation; they cannot interrupt a
running call, which completes or reaches its deadline. Choose a client timeout
at least as long as the worker deadline. There is no progress or task API.

Successful output envelopes identify `schema_version`, `tool`, `status`,
`evidence_kind`, `implementation_status`, `instrument_context`, nested worker
`result`, `limitations`, and `skill`. `completed` means execution succeeded; it
never means musical or listening acceptance. The worker's actual artifact paths,
source hashes and measurements remain inside `result`. Analysis/report reruns
can replace their named artifact files in `run_dir`; choose a fresh directory to
preserve comparison candidates. Raw recordings and artifacts stay outside Git.
AU rendering and Logic acceptance remain separate future integration evidence.

Tests exercise an actual stdio conversation, lifecycle/version negotiation,
notification behavior, prompt loading, schema errors versus tool errors, literal
paths, output limits, deadline cleanup and a real FFprobe call when available.
