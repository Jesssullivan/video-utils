# TIN-7994 narrate removals

Date: November 5, 2026. Base commit: `6eb14722`. Rulings: TIN-7125 `704438d7`,
`7958a23e`, `f98fd1ac`, `1287ff7e` and `af4ceb3b`, under R-HOOK-CONVERGENCE-20261004
(R-N13). This table is the narrate input for the TIN-7994 audit.

## Lifted

| Path at the base commit | What went | Ruling |
| --- | --- | --- |
| `narrate/policy.py:100-104` | `confidential_engine_refused` at render | `f98fd1ac`, `af4ceb3b` |
| `narrate/video/bundle.py:588-589` | `confidential_engine_refused` at intake | `f98fd1ac`, `af4ceb3b` |
| `narrate/video/bundle.py:608-609,1012-1013` | forced `confidential` true and `allowHosted` false | Narrate's inference, open for Jess. `af4ceb3b` does not name these flags, and both removal lists kept them. See "Open decisions" |
| `narrate/dhall/Engine.dhall:165-170` | `mayRunConfidential` beyond `consistent` | `f98fd1ac` |
| `narrate/dhall/check.py:291-292` | the refusal on rendered examples | `f98fd1ac` |
| `narrate/video/vrm.py:379-380` | `vrm_meta_missing` on absent licence fields | `704438d7` |

## Added

| Path | What came | Ruling |
| --- | --- | --- |
| `narrate/policy.py` `check_voice` | rented engines must pass `hostedAllowed` | `af4ceb3b` |
| `narrate/video/bundle.py` `narrate_jobs` | the same check at intake, plus `allowHosted` and `consistent` | `af4ceb3b` |
| `narrate/dhall/Engine.dhall` `isOffsite` | one predicate for rented or hosted, with the check.py port | `af4ceb3b` |
| `.huskycat-public` | an empty marker for this public repository, so hooks write a salted host label on its commits | J107 (a), TIN-7708 `6c90f0b5` |
| `RentedAudioCppBatch` backend | the batch on a rented card, under `RentedOpen` only, so no rented run is labelled `GpuDirect` and one changed field cannot drop the consent check | `704438d7` |

## Kept for the audit

The `confidential` job field, the `--confidential` flag, the report-only
`may_run_confidential` field, the MCP `confidential` input and the engine fields
`confidentialAllowed` and `estateControlled` stay, because their rows wait for the
audit. They refuse nothing.

Consent records and every consent check stay. `hostedAllowed` keeps its name, so no
record migration is needed. A private record with `hostedAllowed` false now refuses a
rented engine, which holds cloned audio until the signed hosted-scope record exists.

## Lost in this lift

| Item | State | Ruling |
| --- | --- | --- |
| SP-4 health rows on client renders | `af4ceb3b` lets client jobs render on rented hosts and be hosted and keeps SP-4 health rows. No code in narrate enforces that limit. Intake used to force `confidential` true, which kept such text local. The spec states the limit, and a job's author now holds it | `af4ceb3b` |

## Open decisions

| Item | Why it stays open | Effect today |
| --- | --- | --- |
| The forced bundle flags | Intake is Internal only and a rented engine never needed `allowHosted`, so the removal is not required for a rented render. Jess decides whether it stands | A client job with these flags changed fails closed in the cade reader, at `job_confidential_mismatch` and `job_allows_hosted` |

## Open across repositories

A hosted client job needs the cade client-video reader changed, because it pins
`allowHosted` false and pins `confidential` to the job's sensitivity. A bundle whose
template sets `confidential` false now keeps false, and a run rendered under the old
forced true no longer adopts by `voice --from-run`.
A run from a local engine whose `confidentialAllowed` was false records
`may_run_confidential` false, so it no longer adopts either, because that label is now
true for it. The private templates and engines were not read, so how many runs this
reaches is unknown.
