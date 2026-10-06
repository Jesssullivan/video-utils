# phrase_anchor_riff phase 4 repair: sealed pins on current main

Date: 2026-10-06. Sprint 20261006-s2, Linear TIN-5603. Ruling: R-HOOK-CONVERGENCE-20261004 (R-N13).

## Audit must_fix

On main, rhythm_clicks (736f406) rewrote `scripts/rhythm.py` (264b723c… → cd719914…). Root
then vendored the original as `scripts/frozen/rhythm_264b723c.py` and routed the S1 worker
to it (8483cc8, merged in ccf47b3), which changed `scripts/phrase_proposal_s1.py` from 38b73654…
to 85a2ba1d…. `phrase_riff_s2.verify_pins()` and `s1_module()` still required the original
bytes at the logical paths. As a result, tests 14, 15 and 16 raised `pinned_source_changed:scripts/rhythm.py`
after a merge. The S1 worker pin would have failed next.

## Change (commit b421040)

- `PINS` is unchanged, so `dependency_sha256 == PINS` in the sealed release binding still compares equal.
- `FROZEN = {"scripts/rhythm.py": "scripts/frozen/rhythm_264b723c.py"}` is the same map as root's.
  `pinned_file()` uses the frozen copy when it exists and otherwise uses the logical path. Either
  file must hash to the pinned 264b723c… value.
- `S1_ROUTING_PATCH` records root's three exact substitutions from 8483cc8 and the routed hash 85a2ba1d….
  `s1_worker_identity()` accepts either the pinned 38b73654… bytes or the routed bytes. For the
  routed bytes, each substitution must reverse exactly once and the result must re-hash to 38b73654…,
  and the frozen rhythm copy must be present. Any other edit is refused.
- New tests: `test_19` covers both the routed tree and the pre-vendor tree. `test_19b` covers
  an unvendored rhythm change, a drifted frozen copy, an extra S1 edit, a changed routing line
  and a wrong routed hash.

## Measured results

| Tree | Interpreter | Modules | Result |
|---|---|---|---|
| Lane worktree (base 4b87484) | python3 | test_phrase_anchor, test_phrase_riff_s2 | Ran 26, OK (skipped=2: numpy-only) |
| Lane worktree | .venv analysis python | test_phrase_riff_s2 | Ran 12, OK |
| Scratch clone: local main ccf47b3 + lane b421040 (conflict-free merge) | python3 | both | Ran 26, OK (skipped=2) |
| Same merge clone | .venv analysis python | test_phrase_riff_s2 | Ran 12, OK |

On the merge clone, `s1_worker_identity()` returned `root_routing_8483cc8` and `verify_pins()` passed.

## Limits

- The worker file changed: 67cedeca… is now 6e2628a6…. Any worker change, including the audit's
  suggested FROZEN-map fix, means the sealed `phrase_anchor_riff-release.json`
  (`worker_sha256` 67cedeca…) no longer authorizes this worker. The held-out seeds 1511/1613 are
  already consumed and scored. Those recorded results stand as receipts and are not replayed.
  A replay would need the 096b7d7 worker on the 4b87484 tree.
- Detector, profile and default behaviour are unchanged. No new measurements of musical content.
