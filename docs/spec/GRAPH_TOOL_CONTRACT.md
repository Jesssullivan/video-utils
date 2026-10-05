# Explicit evidence selection through the pipeline hook

Authority: operator-authorized parallel graph integration,
R-HOOK-CONVERGENCE-20261004 and repository `AGENTS.md`. The existing `pipeline`
tool and `guitar-pipeline` prompt carry this interface; the catalog remains
nineteen tools. This is a provenance evaluator for already-produced local
artifacts, not an execution scheduler or audio renderer.

| MCP argument | Direct `dag.py` flag | Graph slot |
| --- | --- | --- |
| `clicks_artifact` | `--clicks-artifact REL` | `clicks` |
| `pitch_artifact` | `--pitch-artifact REL` | `pitch` |
| `meter_artifact` | `--meter-artifact REL` | `meter` |
| `tonal_artifact` | `--tonal-artifact REL` | `tonal` |
| `comparisons_artifact` | `--comparisons-artifact REL` | `comparisons` |

Each optional field is one string of 1–1024 characters selecting an exact JSON
path relative to `run_dir`. The existing required `run_dir`, optional approved
`reference` and integer `timeout_seconds` 1–900 (default 600) are unchanged.
Unknown arguments, array selectors, booleans and oversized strings are rejected.
No implicit newest-path discovery or file globbing occurs.

Selectors cannot be absolute, contain colon or backslash, empty slash components,
dot-prefixed components, traversal or a `.partial` staging substring. They must
end in `.json`. The dispatcher checks the original path components for symlinks
before resolving anything that could conceal their identity. Missing, directory,
broken-link and linked-component selections fail before launch. Paths are passed
as literal individual argv values to the fixed local `scripts/dag.py` worker;
the caller cannot select a command or shell. The worker independently validates
path safety and caps selected JSON to 20 MB each and 40 MB in aggregate.

The durable graph's `selected_evidence` maps the five slots to receipts containing
`status`, `selector`, `artifact_sha256`, `payload_status`,
`analysis_input_sha256`, `timing_status`, `metadata`, `upstream_hashes` and
`external_context_hashes`.
Unrequested slots are `not_selected`. A `verified` slot passed the worker's
source, upstream, settings and timeline checks. A syntactically valid artifact
with mismatched provenance is recorded as `rejected_*`; unrelated graph evidence
remains available. Only verified selections and their validated upstream hashes
enter `artifact_hashes` as active graph inputs for downstream freshness checks.
Rejected selections keep an artifact hash for audit with null metadata; their
payloads never become trusted inputs. Consult [the worker contract](GRAPH_FEATURES.md)
for exact per-family proof rules and rejected status names.

Successful MCP execution is an execution receipt, not acceptance of every slot.
The wrapper preserves worker output and graph artifact paths without rewriting
nulls, sparse coverage or rejected statuses. Consumers read the durable graph;
they must not bypass it by presenting an unverified selected payload directly.
The full pitch artifact can exceed the MCP stdout bound and remains local.

External instrument context is bound separately to the fixed tuning registry;
it is not an arbitrary caller-selected file. Timing status distinguishes legacy
uncalibrated DSP delay from a measured-and-compensated bulk derivative mapping.
Neither mapping proves detector latency, acoustic travel or physical A/V sync.
Before replacing an existing graph, the worker archives prior graph, flags,
report and generic marker evidence into run-local immutable history. A history
snapshot preserves bytes, not listening acceptance.

Protect intentional low-C1 content and the custom nine-string tuning. Click
identity, candidate pitch/string mapping, notated meter, tonic, mode and intended
notes remain uncertain. Sampling only part of a take is not whole-take
transcription. A confirmed performance error still needs appropriate reference,
calibration and human evidence. Source tests, publication, hosted CI, listening,
native editor compatibility and AU/Logic acceptance are separate states.

Definition of done: all five supported fields appear in live `tools/list`; exact
skill content is returned by `prompts/get`; invalid paths fail without launching
a worker; real worker calls preserve verified, rejected and unknown receipts;
stale evidence cannot become usable through path normalization. Root owns the
integration receipt and publication.

Local hook verification passed 43 targeted tests in the locked Python 3.14
environment: 24 contract tests, 11 dispatcher tests and 8 MCP conversation tests,
with no skips. FFmpeg/FFprobe were explicitly selected from the pinned Nix
FFmpeg 8.1.2 installation. The actual meter-selection conversation verified its
immutable hash, null notation and uncalibrated DSP timing; changing its upstream
analysis then produced rejected evidence without changing the selected artifact
or media, and preserved the prior graph in history. All nineteen skill prompts
were read back exactly through stdio. This is local source/fixture evidence;
root records actual-demo integration, publication and hosted CI separately.
