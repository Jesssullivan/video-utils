# Explicit optional runtime portability plan

Owner `/root/tonal_inference`; root release is **design/read-only only** for
runtime setup. Authority: operator's parallel goal and R-HOOK-CONVERGENCE-20261004
/R-N13. Root separately released the missing-source-origin fix, which is already
implemented and documented in the [fix receipt](2026-10-06-basic-pitch-source-origin-fix.json).
This document creates no installer, lock, recipe, dependency mutation or inference.

A fresh checkout currently lacks the ignored isolated runtime and its wheel
manifest, although explicit model-prefetch covers the weight. The repository's
normal Python minimum3.12 does not establish the optional runtime's qualified
CPython3.14.6/arm64 ABI. The missing-runtime error is honest; provide a distinct
operator setup entrypoint rather than runtime acquisition from the inference tool.

## Proposed smallest implementation

New owned files after root release:

- `program/basic-pitch-runtime.json`: copy the exact verified existing
  wheel-manifest-before-install.json bytes into Git. It already contains no
  private absolute paths: only qualification timestamp, Python/version/platform,
  official URLs, five filenames, sizes, SHA256 and dependency metadata. Preserve
  its SHA256 `c0e0a0f01023d5e701c13bcd092d23ef216dd3e96b2bc0320293c355252df23f`.
  Do not repurpose a large runtime receipt containing historical operator paths
  as the executable lock.
- `scripts/basic_pitch_runtime_setup.py`: standard-library explicit installer,
  requiring an already-installed CPython3.14.6 executable and existing uv.
  `--check` verifies the existing runtime without network or mutation.
  No model download and no arbitrary package/model selection.
- `tests/test_basic_pitch_runtime_setup.py`: platform/interpreter/lock/archive/
  installed-member integrity and existing-directory refusal tests with mocks;
  no implicit downloads or real environment mutation during ordinary tests.
- Root adds `just basic-pitch-runtime-setup python=...` and
  `just basic-pitch-runtime-check`; these are explicit operator operations,
  separate from MCP inference and ordinary analysis-setup.

Proposed fresh-checkout sequence:

```sh
just model-prefetch spotify-basic-pitch-0.4.0-onnx
just basic-pitch-runtime-setup /path/to/already-installed/python3.14
just basic-pitch-runtime-check
just tool-run basic_pitch_compare '{"run_dir":"artifacts/runs/EXISTING_RUN"}'
```

No alternate interpreter installation or platform fallback. Preflight requires
native Darwin arm64, macOS≥14, CPython3.14.6 with ordinary cp314 ABI (reject
free-threaded builds), existing uv, and exactly five reviewed lock entries.
Linux, Intel macOS and other Python versions fail with an actionable unsupported
runtime diagnostic. The system driver can remain Python≥3.12; it probes the
explicit qualified interpreter in a bounded subprocess.

## Artifact and installation boundaries

Stable layout remains
`artifacts/model-runtime-env/onnx-1.30.0-cp314/{wheels,python, wheel-manifest-before-install.json}`.
Copy the committed lock **byte-for-byte before installation** so the existing
worker/runtime manifest contract is unchanged. Explicitly download only the five
HTTPS files.pythonhosted.org wheels and require exact byte count and SHA before
ZIP inspection. Individual archive ceiling32MiB, aggregate wheel64MiB, ZIP
aggregate150MiB decoded and4,000 members; reject duplicate/absolute/traversal/
symlink/encrypted entries. Actual verified inventory is1,503 archive members
and119,178,259 uncompressed bytes, with34,171,831 compressed bytes.

Download sequentially to owned temporary files, with30second socket timeout and
600second overall setup bound; preserve bounded failure receipts. No shared cache
cleanup, host changes, source compilation or source distributions. Create the
venv **at its final stable path**, because relocating venv directories breaks
absolute interpreter/script bindings. Reject symlink ancestors and existing
incomplete/mismatched environments. Repeated setup on an already-qualified
runtime verifies and returns `already_qualified` without replacing anything;
repair/removal is a separate operator task. Only this invocation's new children
may be stopped under R-N11.

Install the five verified local wheels using explicit venv launcher and uv:
`uv --no-config --no-cache pip install --python VENV/bin/python --offline
--no-index --no-deps --no-build --no-python-downloads VERIFIED_WHEELS...`.
The existing `.venv`, main uv.lock/pyproject and any uv-managed interpreter remain
unchanged. Cache/config suppression and offline/local-wheel restriction are
supported by the [official uv CLI reference](https://docs.astral.sh/uv/reference/cli/).
Record the actual uv version and argv; no claim that different installers produce
byte-identical generated metadata. A256MiB runtime-plus-wheel on-disk cap is
proposed; bound setup process logs and record the measured size before declaring
completion. Existing shared caches are neither counted nor reclaimed.

After installation, check exact versions and every wheel-owned installed file
against its archive, excluding only installer-rewritten dist-info/RECORD. Preserve
an installed-member manifest with expected/actual hashes in the ignored runtime
receipt; current runtime has1,349 validated installed members. Probe imports in
that same venv and fixed numerical thread configuration. A zero-waveform model
smoke is a separate explicitly selected qualification operation using already-
prefetched verified weights, not an implicit model acquisition or acceptance
of music. Root currently prohibits further inference until its next release.

The worker accepts explicit-prefetch model cache
`models/spotify-basic-pitch-0.4.0-onnx.bin`; fresh checkouts therefore need no
private qualification-timestamp fallback. Existing qualified runtime/model/worker
files stay unchanged while this design is reviewed. If a future setup reproduces
the copied lock and installed bytes, the only subsequent worker change needed
for portability is clearer missing-runtime guidance; do not silently alter its
hash-bound execution contract.

## Acceptance before publishing setup

Verify unsupported-platform and missing-interpreter failures before downloads;
wrong SHA/ZIP safety failures before installation; exact local argv prevents
index resolution/build/download fallback; an existing qualified runtime is
read-only; all installed member hashes and stable launcher imports pass.
Root then explicitly releases a fresh isolated setup test. That test must avoid
replacing the current qualified stable directory, so it requires either a
separate checkout or a reviewed test root with its own final venv path; moving
the active directory to simulate freshness is outside this scope.
