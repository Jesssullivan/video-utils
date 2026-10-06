# Holdout source release and portability audit

Authority: root's reattached reproducibility lane and subsequently explicit
test-only fix release; R-HOOK-CONVERGENCE-20261004 / R-N12 / R-N13. At inspection
the shared single worktree was `main`, HEAD
`c59d7024a9967b920747e07134c6c166c3ddb38d`. Parallel tool/profile/skill/tracker
writers were dirty and preserved. The bank is complete and frozen; no full bank
generation, inference, model access, dependency installation or remote mutation
was repeated in this audit.

## Result and bounded correction

Source-only metadata reproduction passes. An isolated copied checkout with no
saved artifact directory reconstructs exact admitted plan SHA256
`495ad2f3f553b0bd7030ac797b6e8589f37748df657219c075d0fc4ce7491e74` from a different
working directory. Saving and validating a canonical absolute output path with
spaces also passes; saved metadata has mode0600, validation preserves bytes,
overwrite is rejected and no WAV is produced.

Found and reproduced a clean-checkout test defect: `HoldoutTests.setUp` created
a temporary directory under ignored `artifacts/benchmarks` without first
creating that parent. A selected metadata-only test failed with
`FileNotFoundError` before any renderer ran. Root expressly released the minimal
test-only correction; the setup now creates the parent. Added
`tests/test_holdout_release.py` to check actual source-only CLI reproduction and
that existing metadata test in a fresh isolated checkout. This catches reliance
on ignored operator artifacts rather than duplicating generator arithmetic.

Validation:

- New source-only release tests: **2PASS**,1.179seconds.
- Existing holdout focused tests after the setup correction: **14PASS**,6.941seconds.
- Generator remains SHA256
  `051d8689364564513c34a1ab00a2c23560407e474da12c2bf25e7513dbc81709`.
- Corrected existing test SHA256:
  `acbe87d85888ddc9e1373ea1d1641f64ba66972adddce0122fb4fe91c9221050`.
- New source-only test SHA256:
  `414487c7cbc7b30f0d3a570aa49d21d17680d805048277b3e31c5d6674e99960`.
- Complete bank index remains SHA256
  `3828ef756c3b2d36890e5b2f444c9323960ec9c0b358d02fe02a8c13ba89936b`.

The existing suite's one-case construction test still executes its bounded
temporary timing-errors fixture. The complete12/120 bank was not regenerated
or changed; the new source-only tests generate metadata only.

## Publication omissions at this checkpoint

`git ls-files` showed the holdout worker/test/spec/receipts absent from the
published source, with their current copies untracked. Root must include the
following intended sources when integrating this lane:

```text
scripts/benchmark_holdout.py
tests/test_benchmark_holdout.py
tests/test_holdout_release.py
docs/spec/HOLDOUT_BANK_LANE.md
docs/agent-notes/2026-10-05-holdout-bank-admission.md
docs/agent-notes/2026-10-06-heldout-bank-generation.md
docs/agent-notes/2026-10-06-holdout-release-audit.md
```

`git check-ignore` confirms generated bank index and WAV paths are excluded;
`git ls-files artifacts '*.wav' '*.WAV'` returned no tracked media/artifacts.
Keep those exclusions and existing immutable bank files. The admitted metadata
is reconstructible from source/dependency snapshots; Git must not absorb the
generated bank to conceal a missing source publication.

The existing typed MCP benchmark/skill contract retains technical-v1/v2 scope.
This holdout renderer is a preregistered research command, not a newly advertised
MCP capability. Any later typed exposure requires its separate reviewed contract;
do not imply the existing benchmark hook accepts this suite.

## Minimal Just integration, root owned

Root `justfile` already uses strict Bash, disables dotenv and routes
`just/workflow.just`. Existing benchmark recipes do not route this holdout script.
The minimal three additional recipes are:

```just
# Frozen generated holdout metadata; saves a new bounded local file.
holdout-plan output:
    python3 scripts/benchmark_holdout.py plan --output {{quote(output)}}

holdout-validate plan:
    python3 scripts/benchmark_holdout.py validate {{quote(plan)}}

# Explicit serial twelve-case generation, never inference or model downloads.
holdout-generate plan output timeout="600":
    python3 scripts/benchmark_holdout.py generate --plan {{quote(plan)}} --output {{quote(output)}} --timeout-seconds {{quote(timeout)}}
```

No worker/recipe change is needed for optional analysis Python or FFmpeg: this
renderer uses only the Python standard library. No default recipe should rerun
the full bank. This audit did not edit either Just file.

## Portability and determinism boundaries

Actual source-only tests ran on macOS under Nix CPython3.12.14. The worker uses
stdlib primitives available on the declared Darwin/Linux flake targets, explicit
little-endian PCM and local path bounds; no macOS-only executable or FFmpeg is
required. Linux execution of this new lane is not independently demonstrated
here; publication followed by hosted CI is its next runtime evidence. Windows
is outside the declared flake platforms and the POSIX `O_NOFOLLOW` file contract.

macOS `/var` commonly aliases `/private/var`; `ROOT` resolves the script's real
path while output paths deliberately reject symlink components. Tests use the
canonical resolved checkout/output path, preserving that contract. A path through
the alias is rejected instead of silently weakening symlink checks. Run Just
from the repository, or supply canonical absolute artifact paths outside it.

The SHA recipe/admitted metadata bytes are deterministic and reproduced by the
source-only tests. The complete index records observed `elapsed_seconds`, so
regeneration cannot promise the same index SHA even on the same machine.
Truth/index source hashes also bind the exact renderer/dependency revision.
Waveform bit identity across arbitrary Python/platform versions is unqualified:
Python documents a limited reproducibility guarantee for compatible seeded
`random()` streams, and its math functions largely wrap the platform C library.
[Python random reproducibility](https://docs.python.org/3.12/library/random.html#notes-on-reproducibility),
[Python math implementation details](https://docs.python.org/3.12/library/math.html).
Preserve the qualified artifact hashes and use measured coefficient/timing/error
bounds for new-runtime comparisons; do not promote source portability into
verified cross-platform audio byte identity.

Receipt: `repo_patterns | new release audit/source-only tests and root-released
existing-test parent setup only | clean checkout reproduction and publication
inventory | R-N12/R-N13, R-HOOK-CONVERGENCE-20261004 | bank frozen verified,
sources pending integration | metadata reproduction PASS, fresh-test defect
fixed, generator/complete bank unchanged; source publication/Just integration
and Linux runtime evidence remain root-owned`.
