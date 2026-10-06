---
name: guitar-report-bundle
description: Build and verify a metadata-only, hash-bound evidence bundle for one run so the optional R/Quarto report (and agents) read only verified values, with receipt figures, synthetic banks, operator labels and unknowns kept distinct.
---

# Package a run's bound evidence for the optional Quarto report without copying media.

**Hook:** MCP tool `report_bundle` (once admitted by root). Fallback: `just report-bundle "<run-dir>"`, then `just report-bundle-verify "<bundle-dir>"`.

**Capability:** Experimental. The plain `report.html` from `scripts/report.py` remains the primary report; the Quarto view is optional and separately verified.

## Use and controls

Give an existing run directory. The builder stream-hashes the manifest-listed stage WAVs (names and sha256 only), binds `analysis.json` through `scripts/report.py` lineage rules (run-local, explicit `--analysis-run-dir`, or the capture-profile parent run), accepts dag/flags/markers only when `report.auxiliary_evidence` binds them and the dag names the bound analysis hash, copies the fixed S2 receipt registry with computed binding classes, and projects only structured fields of a bound annotation store. Output is a fresh directory under `artifacts/s2/report_d6/bundles/`; run directories are never written. Refusals are stable codes (`stage_hash_mismatch`, `receipt_missing`, `media_member_refused`, `input_changed_during_build`, ...). Rebuild instead of editing a bundle. Run `verify --check-origin` before relying on one; render with `quarto render reports/demo.qmd -P run_dir=<bundle>` inside `nix develop .#report`.

Read [the bundle contract](../../../docs/spec/sprints/REPORT_S2.md).

## Guitar-specific interpretation

Receipt figures are quoted, not re-measured; show their binding class (`run_bound`, `source_bound_different_analyzed_input`, `metadata_bound`, `synthetic_bank_not_take`, `unbound_context_only`). Generated-bank results are never operator-labelled coverage or real-take accuracy. Operator coverage of this take is small (one INTENT noise annotation over 0-5 s, no phrase or note labels); absence of labels is not evidence of correctness. Keep listening acceptance, note correctness, meter, tonic, mode and 32.7 Hz fundamental presence as unknowns. Detector review flags stay separate from user-reported annotations.

## Agent iteration

Change one input at a time and rebuild into a fresh directory; compare bundles by `bundle_sha256` and member hashes. Never adopt a detector, profile or master default from a bundle. Record the bundle sha256 and verify status in receipts.
