# AUv3 packaging developer check

`python3 native/au-spike/packaging/build.py --dry-run` prints the target contract and source hashes without running build tools. `--build` compiles hash-bound copies, creates an ad-hoc signed app containing a non-UI extension, and inspects both without launching them. Output and `receipt.json` remain in ignored `.cache/au-packaging/`.

This is a manual arm64/macOS 26 deployment prototype using the installed SDK, not an installed plugin or a tested Logic product. The frozen AU's generic fullState setter is unqualified; checked private stopped-state restore remains available. No host or plugin registration commands are invoked. Root owns a future `just` developer recipe and publication.

Plan: `docs/spec/AU_PACKAGING_LANE.md`. Tests: `python3 native/au-spike/packaging/tests.py`.
