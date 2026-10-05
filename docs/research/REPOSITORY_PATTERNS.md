# Corroborated repository patterns

Read-only source comparison, October 5, 2026, completed at approximately
22:50 UTC. The useful shared shape is a Just entrypoint, pinned tooling,
explicit ownership, machine-readable interfaces and provenance, bounded optional
workers, and separate source/runtime evidence. This project adopts that shape
without copying the static-site, Rails, fleet-management or driver product stacks.

The operator requested site.scaffold, Legalab/ASFW, xoxd-ai and recent Sting/XORuby
patterns. AGENTS was read before each pattern inspection, with Lab root read
before the Lab diagnostic worktree. Files below were inspected from committed
`HEAD` using `git show HEAD:<path>`; working-tree instructions were separately
read for authority. Local links are navigation aids and may show later edits;
the recorded commit is the citation revision. No sibling files were changed.

## Source identity and limits

| Source key | Inspected checkout and exact HEAD | Identity/status at inspection |
| --- | --- | --- |
| S | `/Users/jess/git/site.scaffold` — `b9820dc67fa92789ab8a14ce61eddae1d992eb06` | Canonical checkout on `tin-75/observability-consumption-pattern`; two untracked directories. Selected committed files only. |
| X | `/Users/jess/git/xoxd.ai` — `5e081b2b1f8a69f69b1236057eb397954a84be5a` | Canonical checkout on `codex/cloudflare-pages-projection-truth`; tracked/untracked status clean. |
| L | `/Users/jess/git/legalab` — `bcbfc58e8b9013c39cb46e858a9101baacd2eace` | Canonical checkout on `feat/weekend-ls56-dcx-delivery-20260905`; staged owner work includes AGENTS, Justfile and Bazel files. Do not equate its live files with this commit. |
| LR | `/Users/jess/git/legalab-reset-20261004` — `f873cf2772d3a6bcddb4075dd27ab19c99af9ad1` | Clean linked worktree; common Git directory is `/Users/jess/git/legalab/.git`. Its October 4 reset explicitly differs from the older canonical branch. |
| A | `/Users/jess/git/asfirewire-legalab` — `9b317a1b5f33844f966ec46a879d693d87277076` | Clean canonical ASFW checkout on `feat/ls56-clock-au-weekend-20260905`. |
| B | `/Users/jess/git/lab` — `c7b68973ec1774be788b3369c42d07a9e7740bab` | Clean canonical Lab checkout on `work/pzm-legalab-cache-split-20261005`; local declaration source, not fleet readback. |
| BD | `/Users/jess/git/lab-asfw-diagnostic-app-20261004` — `f39df96a0c129b053c2fe894400b1b8ec2fa828a` | Clean linked worktree; common Git directory is `/Users/jess/git/lab/.git`. Diagnostic signing source is branch-specific. |
| R | `/Users/jess/git/xoruby-2026-tin5092-codespace-startup-20260930` — `e9ce2d0abb88560001e33bdbebffab5e35d12a6f` | Independent topic clone with its own `.git`, not a linked worktree. Dirty devcontainer and untracked dated notes were not treated as committed evidence. |
| R2 | `/Users/jess/git/xoruby-2026-tin5128` — `05a9dfe1aec8124e2b0c059125449a9739228e13` | Clean independent topic clone. Identity/status checked only; pattern conclusions use R. No unqualified canonical XORuby checkout was located in the bounded local sibling enumeration. |
| V | `/Users/jess/git/video-utils` — `2ff896751e283090de0612384ce2aa65284322d1` | Comparison snapshot on `main`; parallel integration work is dirty. Adoption claims below describe this committed checkpoint, not uncommitted/newly published changes. |

No Sting-host repository was inspected or located through this local sibling
inventory, and no SSH session was opened. B does contain Sting host and worker
declarations. Those establish source patterns, not current remote checkouts,
installed software, workload capacity, admitted jobs or live ML results.

## What is adopted, and what is deferred

| Pattern | Exact source evidence | video-utils at V; decision |
| --- | --- | --- |
| A small Just router with explicit recipes | L [Justfile](/Users/jess/git/legalab/Justfile:1), imports at lines 6–16; LR [Justfile](/Users/jess/git/legalab-reset-20261004/Justfile:6). X [Justfile](/Users/jess/git/xoxd.ai/Justfile:20) separately wraps package-manager commands. | Adopted: [justfile](../../justfile:1) routes [just/workflow.just](../../just/workflow.just:1). Shell errors propagate, argument quoting is explicit, dotenv auto-loading is disabled. Media processing is not hidden in shell startup. |
| Locked, role-specific Nix tooling | S [flake.nix](/Users/jess/git/site.scaffold/flake.nix:103) separates normal and Playwright shells. R [flake.nix](/Users/jess/git/xoruby-2026-tin5092-codespace-startup-20260930/flake.nix:16) separates default/research/Playwright/ML environments and bounds ML threads. | Adopted: [flake.nix](../../flake.nix:9) separates default, analysis, report and Linux-only ML shells. `flake.lock`, `uv.lock` and `Cargo.lock` are committed; [analysis-setup](../../just/workflow.just:71) uses a frozen lock. No shell evaluation/build was performed in this lane. |
| Independent local and remote evidence | LR [just/repo.just](/Users/jess/git/legalab-reset-20261004/just/repo.just:1) explicitly selects local development and separate REAPI recipes. Its [AGENTS](/Users/jess/git/legalab-reset-20261004/AGENTS.md:49) revises the older executor-first posture seen in L's live contract. | Adopted: [test/check/test-rust](../../just/workflow.just:23) and [CI](../../.github/workflows/ci.yml:20) declare actual commands. No RBE enrollment or remote-execution claim is inherited. Builder placement remains an explicit later decision for heavy work. |
| Machine-readable authority and evidence graphs | L [program/index.json](/Users/jess/git/legalab/program/index.json:8) indexes authority/research/tracker digests. S [tinyland.repo.json](/Users/jess/git/site.scaffold/tinyland.repo.json:15) declares repo role and boundaries. | Adopted in smaller form: [program/tools.json](../../program/tools.json), [program/linear.json](../../program/linear.json), instrument/model registries, run manifests and [DAG selectors](../../scripts/dag.py:243). V's tool registry contains 20 tools. A Legalab-sized program ontology or complete Tinyland taxonomy validator is not implied. |
| Canonical agent skills backed by actual commands | S [AGENTS](/Users/jess/git/site.scaffold/AGENTS.md:68) names `.agents/skills` as the canonical source and describes command-backed validation; Legalab uses the same canonical skill location. | Adopted: repository `.agents/skills`, [tool API schema/skill validation](../../scripts/tool_api.py:80), and [tool-info/tool-run/MCP recipes](../../just/workflow.just:34). Claude aliases and a marketplace package are deferred, not assumed shipped. |
| Immutable source bytes and bounded worker interfaces | R [remote worker contract](/Users/jess/git/xoruby-2026-tin5092-codespace-startup-20260930/docs/development/remote-worker-contract.md:57) requires exact manifest bytes/hashes, bounded attempts and validated outputs. R [audio worker](</Users/jess/git/xoruby-2026-tin5092-codespace-startup-20260930/ml/inquiry/audio/worker.py:99>) rejects escaped paths and binds feature caches to source/region/recipe. | Adopted locally: [media source/output checks](../../scripts/media.py:359), [DAG provenance](../../scripts/dag.py:234), bounded artifacts and atomic output publication. Remote job leases, authenticated uploads, Rails/SQLite authority and audience enrollment are deferred; the take is processed locally. |
| Source-group separation and explicit annotation uncertainty | R [audio worker validation](/Users/jess/git/xoruby-2026-tin5092-codespace-startup-20260930/ml/inquiry/audio/worker.py:49) rejects byte/source/group leakage across splits. Its [dataset lock](/Users/jess/git/xoruby-2026-tin5092-codespace-startup-20260930/ml/data_sources/guitar-speech-v1.lock.json:14) separately records dataset/license evidence, grouped selection and archive-checksum status. | Partially adopted: [corpus.py](../../scripts/corpus.py:288) binds sparse reviewer assertions to source/run/annotation revisions and retains ambiguity. A trained/evaluated guitar model and train/test group partitioner are future work. R's corpus is guitar-presence/speech work, not validation of C1 deathcore phrase or pitch detection. |
| Model preparation is explicit and distinct from a job | R [remote contract](/Users/jess/git/xoruby-2026-tin5092-codespace-startup-20260930/docs/development/remote-worker-contract.md:64) prevents unbounded checkpoint acquisition during claims. | Adopted: [model_prefetch.py](../../scripts/model_prefetch.py:21) requires a registered HTTPS URL, checksum and byte bound before downloading. [program/models.json](../../program/models.json:1) is empty at V. No checkpoint acquisition or FOSS-weight qualification is claimed. |
| Native Apple integration stays distinct from reusable processing | LR [AGENTS](/Users/jess/git/legalab-reset-20261004/AGENTS.md:59) prefers Rust systems code, Swift Apple integration and bounded Python tooling. A [clock AU](/Users/jess/git/asfirewire-legalab/ASFWControl/LS56ClockAudioUnit.swift:6) is an actual `AUAudioUnit` source implementation; its [state methods](/Users/jess/git/asfirewire-legalab/ASFWControl/LS56ClockAudioUnit.swift:40) preserve clock intent separately from rendering. | Adopted architecture, limited implementation: [Cargo.toml](../../Cargo.toml:1) and pinned [Rust toolchain](../../rust-toolchain.toml:1), bounded Python media/MIR, and [native Swift gain scaffold](../../native/au-spike/apple/GuitarGainAudioUnit.swift:5). The ASFW MIDI/clock effect is not a denoiser. Native gain/automation/state experiments are not an installed AU, completed Rust restoration engine or Logic acceptance. |
| Ownership, clock and lifetime seams are explicit | A [AGENTS](/Users/jess/git/asfirewire-legalab/AGENTS.md) separates payload-opaque transport, audio framing, neutral lifetime-owned interfaces and hardware versus host tests. A [HostClockAnchor](</Users/jess/git/asfirewire-legalab/ASFWDriver/Audio/Runtime/HostClockAnchor.hpp:36>) stores a generation-bound snapshot; real timing remains subject to clocks and drops. | Adopted as a design boundary: DSP stays outside media orchestration and future host wrappers; [native bus validation](../../native/au-spike/apple/GuitarGainAudioUnit.swift:31) checks formats before rendering. DriverKit/OHCI/CIP code, HAL clock control, system extensions and ASFW teardown infrastructure are outside scope. |
| A candidate artifact is distinct from installation/readiness | BD [diagnostic signer](/Users/jess/git/lab-asfw-diagnostic-app-20261004/scripts/validation/pzm_asfw_signed_build.py:1) describes candidate signing without installation; [tests](/Users/jess/git/lab-asfw-diagnostic-app-20261004/tests/unit/test_pzm_asfw_signed_build.py:340) target exact bundle/version/identity drift. | Adopted evidence discipline: run artifacts, synthetic checks, source-native experiments, listening review and host acceptance remain separate states. Signing/entitlement profile handling and DriverKit repair are deferred; this repo grants no host mutation authority. |
| Bound resource use instead of importing an entire fleet | B [Sting declaration](/Users/jess/git/lab/nix/hosts/sting.nix:91), [heavy-job module](/Users/jess/git/lab/nix/home-manager/heavy-job-slice.nix:120) and [wrapper](/Users/jess/git/lab/nix/home-manager/scripts/tinyland-heavy.sh:15) declare scoped limits; default heavy slice values are 14/18 GiB in source. | Adopted locally: one Cargo build job, optional bounded analysis and two-thread analysis/ML shells. Sting execution, GPU admission and its live slice settings remain unverified. No fleet daemon, new runner, cluster manifest or Linux systemd requirement is introduced for a macOS utility. |
| Validation is composed, with product-specific boundaries | S [Justfile](/Users/jess/git/site.scaffold/Justfile:89) separates lint/format/security/conformance recipes. LR [just/repo.just](/Users/jess/git/legalab-reset-20261004/just/repo.just:45) composes static and test checks. | Partially adopted: [check](../../just/workflow.just:27) runs synthetic/source checks plus required media tooling; [CI](../../.github/workflows/ci.yml:18) pins actions and invokes locked Nix/Just checks, Rust tests and redacted secret scanning. Rustfmt/clippy/shellcheck being available in Nix does not mean `just check` invokes them. A composed lint/format/skill/privacy gate remains a concrete follow-up. |

These are corroborated similarities and explicit decisions, not a claim that
implementation code was copied from sibling repositories. Canonical Legalab and
its reset worktree are both useful sources, but their execution policies cannot
be blended into one allegedly current rule. Source links to staged canonical
files require `git show <recorded-sha>:<path>` when reproducing this comparison.

## Scope decisions for the next week

Retain the small local CLI/report utility and its current JSON contracts. Extend
the existing day-one/day-seven interface and provenance work with a composed
lint/format/skill/privacy check, coherent dependency/toolchain readback, and
explicit compatibility versions. Extend the day-six corpus work with recording
and performer grouping before any model training/evaluation. This replaces part
of the already approved work, adding no hours to the 35+35-hour allocation.

R/Quarto is this project's explicit research-report requirement: [report shell](../../flake.nix:20),
[Quarto source](../../reports/demo.qmd:16) and [R plots](../../reports/plots.R)
exist. It was not corroborated as a shared convention in the bounded selected
sibling files. Actual Quarto rendering is separate evidence; the usable plain
HTML fallback does not prove it. Zig likewise has no confirmed implementation
role in the inspected video-utils checkpoint; Rust/Swift/Python boundaries are
the committed choice. Neither omission justifies an unbounded language rewrite.

Defer static-site rebranding, Svelte/Skeleton/Tailwind, Bazel/RBE enrollment,
OpenTofu, Rails/Active Storage, remote authenticated training, dataset/checkpoint
downloads and DriverKit installation. Adopt each only when a product requirement
and bounded acceptance justify it. The future editor marker/AU workflows keep
their own application validation milestones; a sibling's source implementation
cannot qualify ours.

## Inspection receipt

`clip_baseline | assigned two documentation files; sibling repositories read-only
| corroborate user-requested repo patterns | operator goal;
R-HOOK-CONVERGENCE-20261004 R-N12/R-N13 | named sources had mixed clean/dirty/topic
states | exact HEAD/source comparison complete; no sibling mutation or runtime
acceptance claim`

Read-only operations were `rg --files`, instruction/file reads, Git status,
worktree/common-directory/HEAD readbacks and committed file reads. Git status
used `GIT_OPTIONAL_LOCKS=0`. No recipes, builds, installers, model downloads,
network mutations, remote host probes, service signals or application API writes
were executed. The [dated receipt](../agent-notes/2026-10-05-repository-pattern-corroboration.md)
records verification of this documentation handoff.
