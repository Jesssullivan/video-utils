# Capture application adapter independent audit

Status: independent source audit complete; inert observational supervision qualified within the scope below. No unresolved source blocker was found in final adapter SHA `ea2d27400b98a2c7285f068501100c222fbb969a56d53d497a3b141b1c70f5a8`. This lane owns only this receipt. Native restoration acceptance, public tool-28 admission and publication remain root-owned separate evidence. No real take, model acquisition or host configuration was performed by this audit.

Authority: repository `AGENTS.md`; operator-authorized parallel implementation/research lanes; R-HOOK-CONVERGENCE-20261004, TIN-3692 comment `98cf680c-7299-4949-bfb2-60079053ad43`. R-N11 requires recorded ownership and live checks before signals; R-N12 hooks are advisory; R-N13 requires this durable evidence.

## Scope and initial baseline

The audited proposal is `docs/spec/APPLY_CAPTURE_PROFILE_TOOL_CONTRACT.md`, specifically the application-only outer supervisor. The current 27 tools retain their existing runner. The application worker's native processing qualification, observed candidate publication, master adoption and listening acceptance are separate from supervisor source and inert cleanup evidence.

Initial baseline on this macOS host:

| File | SHA-256 |
| --- | --- |
| `program/tools.json` | `a4feec5463051a5dcea165c14e8bbcf4b2f3fa59b946b0148a8952db78dd2d6a` |
| `scripts/tool_api.py` | `e99933b5eb68743a85d497c23427b94f4bf7650ddd8543dca5fd323ba622015d` |
| `tests/test_tool_contracts.py` | `0448169d60a306f48ecd0f659d7768b0a0e908734c699ce9e50c02f1d8d5e96b` |

Design review concerns delivered to the source owner before implementation review:

- Freeze and revalidate the direct owned root before losing PPID ancestry. Retain the birth/session identity and exact observed ancestry of discovered descendants, including previously observed orphan sessions.
- Before a process-group signal, validate every live member against retained ownership. An unproven member, changed birth token, missing identity or inconsistent session is grounds to refuse that group signal and report incomplete/unknown cleanup.
- Bound native identity work as well as the process-table subprocess. A timeout on `ps` alone does not bound subsequent native process inspection.
- Early worker exit with surviving descendants must use an absolute cleanup end no later than `min(outer_deadline, now + 5 seconds)`; it must not consume hundreds of seconds remaining on a default request.
- Preserve candidate publication as unknown on outer timeout until exact local pinned evidence is inspected. Cleanup observations cannot establish publication or erase a committed candidate.

## Platform source checks

The local Xcode macOS SDK exposes public `proc_pidinfo` and `PROC_PIDTBSDINFO=3`. Its `proc_bsdinfo` contains PID, PPID, PGID, process status and `pbi_start_tvsec`/`pbi_start_tvusec`. These support a high-resolution start token; they are not a kernel containment handle. The unique-identifier structure appears under `PRIVATE` in the referenced archived Apple source, so a portable implementation must not silently assume that private flavor is public or supported. [Apple process structures](https://github.com/apple/darwin-xnu/blob/main/bsd/sys/proc_info.h).

Linux documents PID, PPID, process group, session and kernel start time in `/proc/PID/stat`. Parsing must handle the parenthesized command field and retain the start token, rather than use command names or second-resolution process listings as ownership. [Linux kernel proc documentation](https://www.kernel.org/doc/html/latest/filesystems/proc.html).

The check-to-signal interval is inherently a user-space race. Sampling can miss a child that rapidly orphans or changes session before observation. Successful observed-session cleanup must remain scoped to retained identities; unavailable or incomplete inspection cannot become an absence claim.

## Implementation findings and correction review

The source owner released the new helper/tests for review without releasing the old 27 contracts. The first source checkpoint inspected was adapter SHA `2b067db3625a93df70f39f8d07721d5c8d44a3deb992642213ac0e0080035e06` and test SHA `494bb97f3ef2a05e48414cad3743aa9237f6280521900ddebb0e4f26c084b181`; these are historical review identities, not a frozen qualified release.

1. **False absence for a retained process moving group/session.** Original final verification scanned only old numeric groups. A pure in-memory fixture retained PID 20 with birth `['fixture', 1]` in old PGID/SID 20, while the same live identity moved to PGID/SID 30. Original verification returned `([], [])` with `inventory.incomplete=false`. No process was launched or signalled for this diagnostic. Follow-up review found both cleanup and normal exit needed that check. The shared `unresolved_retained` correction now covers both paths and conservatively reports live/moved/changed-birth identities. The actual MCP escaped-session regression passes and retains unknown cleanup without signalling the moved target.
2. **Inspection phases lacked an absolute one-second cap.** Original `ps` wait was capped, while parsing/native ancestry work could use the whole outer deadline. The first correction supplies a one-second absolute phase end through snapshot/observation, and caps group verification. Native blocking and OS scheduling still prevent a hard real-time guarantee.
3. **Launch and result/cap failures lacked final durable supervision state.** Original `Popen` was outside the reporting handler, and a blanket `except AdapterError: raise` bypassed failure recording. First correction records launch failures and only rethrows adapter errors that already carry a finalized receipt.
4. **Available recovery result was transient.** Original code discarded parsed worker success/domain diagnostics after transport. First correction saves bounded `worker-result.json` and its SHA before return/error, retaining available exact recovery evidence without claiming publication from a timeout.
5. **Final compact response could exceed its ceiling.** Original code checked raw worker JSON, then appended supervision fields without rechecking. First correction caps the merged response to 16 KiB.

The owner was asked to cover normal-exit moved identities, actual cleanup refusal on birth/group ambiguity, default and minimum budgets, inventory/output/receipt bounds, slow/unavailable inspection, shared-budget exhaustion, and publication-before-timeout recovery. The actual MCP inert harness must exercise the application adapter internally, rather than test only a fabricated error envelope. No public executable or inspector knob is admitted.

Further design consistency checks sent to the owner: ordering only the root group last does not establish leaves-to-root ordering for nested child sessions; recorded identities need first/last observation metadata and a reconstructable birth-qualified root ancestry graph; metadata writes and final signals require the same shared absolute budget. The source owner is adding reporting-budget checks, a qualified production-worker identity guard and further refusal/boundary fixtures. User-space observation does not become kernel containment after these changes.

A later reviewed correction records first/last observations and ancestor PID/birth pairs, orders descendant groups by recorded depth, pins the production worker SHA, and checks the shared deadline before metadata writes. Review then found a new exception-path risk: a reporting-budget error can carry the previous `starting` receipt, and the blanket “has receipt” bypass can incorrectly treat it as finalized, skipping cleanup of a live launched worker. A prior durable receipt is not evidence that cleanup ran. The owner added an explicit `AdapterError.finalized` marker and a real inert launched-root regression. Nonfinal receipt/budget errors now enter cleanup; the regression passes with an observed root return code. NUL path controls also reject before launch, and launcher encoding/value failures have bounded launch-failure reporting.

The review distinguishes the mocked process-inspection timeout-budget test from actual slow native-inspection latency. Similarly, durable preservation of synthetic worker diagnostics is a metadata/transport proof; it is not proof that a real candidate published or that its canonical recovery hashes verified. An exhausted cleanup end deliberately refuses further signals and reports unknown; this does not promise direct-root or descendant absence in every failure mode.

## Frozen identities and test attribution

| Artifact | SHA-256 |
| --- | --- |
| Final `scripts/capture_application_adapter.py` | `ea2d27400b98a2c7285f068501100c222fbb969a56d53d497a3b141b1c70f5a8` |
| `tests/test_capture_application_adapter.py` | `049cb92ae4688044fd4596826081966917ab4f4ef8c375d99b815dbbbbf0dc87` |
| Independent `tests/test_capture_application_adapter_audit.py` | `d205c5689d62454f4fceb7f962bbfc8dbcbd7dce1829ec14cfe9b3493d4b6100` |
| Pinned application worker | `790ac58f1924db2607087c6ab1cdae5d813ba24eda610af1f396d77e93d06584` |

This audit directly ran `.venv/bin/python -m unittest discover -s tests -p 'test_capture_application_adapter*.py' -v`: **23/23 passed in 42.990 seconds**, no skips. Its starting adapter hash was `7df85ee66f621e6f0b21f467146444904d9c7e994fe992fecf181d2857a573a3`; the source owner's allowed worker-pin release occurred during the run, producing final `ea2d274…`. This is explicitly a mixed-pin run, not an exact single-SHA qualification. Replacing only final `QUALIFIED_WORKER_SHA256=790ac58…` with the previous `00a03ef…` reproduces the exact `7df85ee…` file hash. The supervision implementation body and both test files remained unchanged. The final production pin equals the current application file hash, verified by this lane without invoking that production worker.

The source owner subsequently reported **23/23 passed in 48.475 seconds on exact final `ea2d274…`**. The independent release-review owner reported its **3/3 audit cases passed in 5.609 seconds on exact `ea2d274…`**. These final exact-source runs are attributed owner reports, not additional executions by this lane. The three independent cases qualify bounded root waiting after signal refusal, initial identity failure reporting, and reuse of one cleanup end after metadata failure.

The actual initialized MCP fixture bootstrap privately substitutes this adapter into `tools/call`; callers receive no executable or inspector field, and the shared registry/API remains unchanged during these tests. This exercises MCP transport plus the new supervisor, rather than claiming an admitted public tool-28 schema/routing. Meaningful inert cases include worker-owned inner cleanup, a genuinely stopped root and new-SID child reaching fallback, retained orphan-group cleanup after leader exit, a recorded orphan moving SID with refusal/unknown outcome, an unrelated same-command sentinel surviving, inspection failure, PID-birth refusal, minimum/default budget mapping, exhausted cleanup budget, identity/group/table bounds, response/receipt caps, interrupted reporting and durable synthetic canonical recovery selectors. The suite preserves an already written test-owned candidate manifest across outer timeout; it does not infer whether production publication occurred.

Two additional pure mocked-native probes were run directly on final `ea2d274…`, with group signals mocked and asserted unused:

- A protected `proc_pidinfo` row with `EPERM` retains PID 42 / PGID 20, `ppid=-1`, and `identity_unavailable=true`. When it is in the target group, fresh ownership inspection fails and cleanup returns `unknown`; no group signal is authorized.
- A readable target-group row whose `getsid` is unavailable also yields `unknown` with no group signal. An unavailable SID cannot confer ownership.

The final native macOS snapshot uses cached public `proc_listallpids` enumeration, rather than spawning `ps` on every sample. Local SDK declarations and native runtime tests support this host path. The kernel birth token still comes from public BSDINFO3, followed by current PGID/SID checks. Protected unrelated rows remain visible to membership verification rather than being silently erased. Linux stat parsing received source/mock review; this receipt does not claim live Linux runtime qualification.

Before root began the separately released tool-28 integration, the catalog, dispatcher and old contract-test hashes still matched the three initial baseline hashes above. This audit changed only its owned receipt; it did not change those 27 contracts, helper code, tests or application source.

## Evidence boundary and disposition

All concrete findings raised in this lane are closed in the reviewed final implementation or explicitly retained as conservative failure/observation limits. Root may proceed to the separately authorized hook integration using the frozen helper. Typed tool admission, native processing behavior and future production MCP fixtures remain separate checks.

Process escape-hatch receipt: `audit/parent-owned inert suite | freshly recorded fixture roots and descendants with birth/ancestry/session checks | test deadline, identity refusal and cleanup recovery | R-N11, R-HOOK-CONVERGENCE-20261004 | live inert workers/new sessions, no media/model action | verified retained groups stopped in positive cases; ambiguous, moved, unavailable or exhausted cases remained unknown; fixture harness cleaned only its separately owned known processes`.

No kernel containment, escaped/unobserved-descendant absence, hard real-time OS behavior, actual candidate publication, adopted master, listening acceptance, media inference or public tool-28 runtime acceptance follows from this audit. Publication remains unknown on an outer timeout unless exact pinned durable candidate evidence is independently verified; no newest-run discovery or committed-candidate deletion is used.
