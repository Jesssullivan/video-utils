---
name: guitar-flags-triage
description: Order an existing run's guitar review flags into a compact default view with at most one shown flag per phrase span or 16-period click-grid navigation window by the frozen rule flags-triage-priority-v1; navigation proxies hidden but retained; no new kinds, no verdict.
---

# Triage review flags into a default order

Hook `flags_triage`; prompt `guitar-flags-triage`. The worker is `scripts/flags_triage.py`; operators run `just flags-triage RUN_DIR OUTPUT`. Read [the frozen contract, section 2](../../../docs/spec/sprints/ANNOT_CORPUS_S2.md) before relying on the order.

**Intent.** A take can carry many overlapping review hypotheses. This view shows a musician one flag per window to review first, while keeping every other flag reachable with its reason.

**Knobs.** None beyond paths and `timeout_seconds` (1–900, default 120). The rule `flags-triage-priority-v1` is frozen: tier by existing kind (T1 within-take comparison differences, T2 automatic recurrence candidates, T3 low-register riff/breakdown and bright ending texture, T4 spectral texture regions, T5 any other kind, kept eligible), then flags with a hash-bound `selected_evidence_slot`, then earlier source time, kind and original index. Numeric `confidence` and `similarity` values are uncalibrated and never used.

**Paths.** `run_dir` must hold a regular `flags.json`; traversal, URL and symlink components reject, and relative paths resolve from the repository root. `output` must be a fresh `.json` file beneath repository `artifacts/`, with an existing parent and outside `run_dir`. The run is never written.

**Dependencies.** The window basis is hash-bound semantic phrase spans from `phrases.json` (checked against `dag.json` when present) or else the click grid bound in `flags.evidence_artifacts.clicks`. Run `phrases` and `clicks` first if neither exists. Without a basis the tool refuses with `triage_window_basis_unavailable` instead of inventing windows. Feature segments are not phrase spans.

**Evidence.** Grid windows are 16 consecutive click periods: navigation aids, not bars, downbeats or meter (`bar_or_downbeat_identified: false`). Navigation proxies (four-pulse groups) are hidden by default but retained verbatim in `hidden_navigation`. Suppressed flags record `lower_priority_in_window` and their `winner_flag_id`. Check the denominators: `shown + suppressed_lower_priority + navigation_hidden == total_flags`. The view adds no flag kind and assigns no grade; `performance_grade` is `not_assigned` and `musical_verdict` is `not_established`.

**Research and iteration.** Tiers reorder existing hypotheses; they never identify an error type, a missed or extra note, or a technique. Heavy distortion, near-32 Hz low strings, palm mutes, rests, tuplets, tapping, sweeps and legato all shift detector attacks, so a shown flag is a place to listen, not a finding. After upstream flags, phrases or clicks change, rerun into a fresh output and compare the shown set and denominators. Keep both receipts.
