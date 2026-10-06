---
name: guitar-annotation-v2
description: Read or save structured source-bound guitar practice annotations with explicit issue kind, assertion basis, revisions and replay handling; preserve user reports separately from detector hypotheses.
---

# Structured practice issues

Hook `annotation_v2`; prompt `guitar-annotation-v2`. Inspect the current catalog before invocation. This separate version2 store leaves version1 review annotations intact; it does not render video or start a server.

Use required `run_dir`, optional `operation` (`read` default or `write`), and `input` only for a write. `timeout_seconds` bounds the worker. Read the current store first. The worker validates a closed JSON request containing version2, source and manifest SHA256, expected revision, idempotency key and one annotation. Read [the implemented contract](../../../docs/spec/sprints/ANNOTATIONS_S1.md) for the current body schema and supported kinds/bases; do not guess extra fields.

Keep original-source seconds, including stream offsets. Preserve unknown point extent rather than inventing a phrase duration. Preserve the operator's words and reported attribution; a structured user issue is not a detector-confirmed mistake. `accepted_observation` does not accept a master, verify intended notes or establish rhythmic correctness. Distorted nine-string C1 sustain, fan overlap, tapping and legato remain ambiguous audio contexts.

Both audio and format start times must be explicit finite values, with a finite declared or native-derived audio duration. An unknown source clock refuses version2 operations; it is not guessed as zero. The CLI snapshots at most20MB per metadata file and40MB aggregate, and bounds lineage hashing at512MiB across256 files. Hashing may read existing media for identity; this tool performs no audio processing.

A literal retry of the same request/key returns the original committed ID/revision and current store without a second write. A changed request using the same key conflicts. On stale revision, reread and reconcile the intended edit; do not automatically overwrite another annotation or issue a changed request under an old key. Keep the key and exact body across a transport timeout until readback/reconciliation resolves the outcome. Limits are200 records,512 replay receipts and1MB store; reaching a limit refuses the write rather than evicting history.

Requests are at most20000bytes. Use fresh request files and exact local regular paths; traversal, symlink and nonregular inputs are refused by the admitted hook. The worker binds source/manifest and candidate provenance, checks finite ordered source spans and retains explicit assertion basis. It authenticates neither the named reporter nor musical truth. Read back saved ID, revision and source identities after a successful write.

For iteration, identify the musician's intended observation, inspect current source clock and store, change one supported record and compare the saved receipt. Research clock/basis semantics in the worker when uncertain. Keep private request/store artifacts local and ignored; record the operation and limitations in the owning durable receipt. Do not infer missing/extra notes from attack density or upgrade an expected arrangement into observed performance.
