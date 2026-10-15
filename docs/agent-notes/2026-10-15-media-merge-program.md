# Media merge program: talk-condense into video-utils (2026-10-15)

Authority: operator decision 2026-10-15 (Linear initiative I-78, milestone "Absorb talk-condense");
R-N13. Every commit is signed with sign-off only; every PR landed by fast-forward on green hosted CI
(offline, web, condense, bazel).

## Decisions

- video-utils is the one host for media tooling. talk-condense moved in as `./condense` and was retired
  (archived, private, not deleted) after a verified mirror bundle went to private backup.
- tubebrain stays a separate product. A tubebrain-stt backend for transcription is backlog (TIN-6514).
- Rust owns the timeline. It validates every EDL the edl stage writes and verifies condense runs.
  `edl.py` keeps an in-process copy of the map for per-word loops, tied to Rust by exact parity tests.
- Run manifests declare `timeline.mapping`: identity for guitar takes, `edl_v1` for condense runs
  (`docs/spec/TIMELINE_CONTRACT.md`). Every guitar consumer refuses a condense manifest
  (`tests/test_timeline_contract.py`).

## PRs

| Issue | PR | Change |
| --- | --- | --- |
| C1 TIN-6500 | #5 | public-repository rule, condense scope, CONDENSE and TIMELINE_CONTRACT specs |
| C2 TIN-6501 | #2 | `condense` dev shell (FFmpeg 8.1.2, whisper-cpp 1.8.4) |
| C3 TIN-6502 | #4 | whisper.cpp ggml-small.en registered and hash-bound |
| C4 TIN-6503 | #7 | talk-condense bf5b9dc moved byte-identical into `condense/` |
| C5 TIN-6504 | #9 | release 0.2.0, signed tag `v0.2.0`; talk-condense retired |
| C6 TIN-6505 | #3 | strict JSON reader moved to `crate::json` |
| C7 TIN-6506 | #6 | `src/timeline.rs`, bit-exact with the frozen oracle |
| C8 TIN-6507 | #8 | `video-utils timeline` CLI |
| C9 TIN-6508 | #11 | edl stage validates with Rust; Python/Rust map parity |
| C10 TIN-6509 | #13 | `verify-run --timeline edl_v1` and the refusal matrix |
| C11 TIN-6510 | #14 | condense publish stage |
| C12 TIN-6511 | #12, #15, #16 | tool drafts, then tools 47 to 57 admitted |
| C13 TIN-6512 | none | cancelled: `scripts/media.py` helpers do not fit condense |
| C14 TIN-6513 | #10 | bounded condense defaults and tool timeouts |

## Not established

Listening quality of a condensed talk, ASR accuracy, and physical A/V sync beyond the avsync probe.
No real recording was run through `./condense` in this program; every gate used synthetic media.
