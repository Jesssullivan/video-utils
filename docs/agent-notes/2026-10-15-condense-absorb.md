# Absorb talk-condense as ./condense (2026-10-15)

Authority: operator decision 2026-10-15; Linear TIN-6503 (milestone "Absorb talk-condense",
initiative I-78); R-N13.

Source: `Jesssullivan/talk-condense` at `bf5b9dc` (3 commits). Destination: `condense/`.

## Per-file comparison

The source hash is of the file at `bf5b9dc`. "imports renamed only" means the destination equals the
source with `talk_condense` replaced by `condense`, and nothing else.

| Source | Destination | Source sha256 | Destination sha256 | State |
| --- | --- | --- | --- | --- |
| `talk_condense/__init__.py` | `condense/__init__.py` | `ecbd5b8902ee` | `ecbd5b8902ee` | identical |
| `talk_condense/__main__.py` | `condense/__main__.py` | `3cb194efb0dd` | `3cb194efb0dd` | identical |
| `talk_condense/audio.py` | `condense/audio.py` | `0d76e9e1187c` | `0d76e9e1187c` | identical |
| `talk_condense/avsync.py` | `condense/avsync.py` | `d4153ca7eb77` | `d4153ca7eb77` | identical |
| `talk_condense/captions.py` | `condense/captions.py` | `be1613669fc5` | `be1613669fc5` | identical |
| `talk_condense/check.py` | `condense/check.py` | `a4507953c439` | `a4507953c439` | identical |
| `talk_condense/config.py` | `condense/config.py` | `4f7bc0182d24` | `4f7bc0182d24` | identical |
| `talk_condense/edl.py` | `condense/edl.py` | `5ebf516f64a2` | `5ebf516f64a2` | identical |
| `talk_condense/events.py` | `condense/events.py` | `e093d7f41e12` | `e093d7f41e12` | identical |
| `talk_condense/overlay.py` | `condense/overlay.py` | `6d200fa32532` | `6d200fa32532` | identical |
| `talk_condense/recover.py` | `condense/recover.py` | `a249b2775479` | `a249b2775479` | identical |
| `talk_condense/render.py` | `condense/render.py` | `058634180f7d` | `058634180f7d` | identical |
| `talk_condense/transcribe.py` | `condense/transcribe.py` | `46140351bf10` | `46140351bf10` | identical |
| `tests/conftest.py` | `condense/tests/conftest.py` | `911625cf514a` | `20d4f97396bc` | imports renamed only |
| `tests/test_avsync.py` | `condense/tests/test_avsync.py` | `7682dd42e084` | `94bc9c8b6d91` | imports renamed only |
| `tests/test_captions.py` | `condense/tests/test_captions.py` | `d7b704f7c9ff` | `4685e397b739` | imports renamed only |
| `tests/test_edl.py` | `condense/tests/test_edl.py` | `f7cc30c09734` | `43528cf2ee2e` | imports renamed only |
| `tests/test_events.py` | `condense/tests/test_events.py` | `ee77458c2277` | `8b7b54d77dcf` | imports renamed only |
| `tests/test_recover.py` | `condense/tests/test_recover.py` | `7b57afa84d09` | `ddb879a839f8` | imports renamed only |
| `tests/test_render.py` | `condense/tests/test_render.py` | `d6b9d615dcc2` | `46e4765ea0e3` | imports renamed only |

Not carried over: `flake.nix` and `flake.lock` (replaced by the `condense` dev shell), `Justfile`
(replaced by `just/condense.just`), `pyproject.toml` (replaced by `condense/pytest.ini` and
`condense/ruff.toml`) and `.gitignore` (merged into the root one). `README.md` moved to
`condense/README.md` with the recipe names, the model acquisition and the layout updated, and the
anecdotes reworded so they name no recording.

## Gates

- `just condense-lint`: ruff check and format check pass on 20 files.
- `just condense-test`: 41 passed.
- `tests/test_condense_public_surface.py`: the site's leak-scan rules find nothing under `condense/`
  or in `just/condense.just`. A planted private address made it fail, then was removed.

Deferred: a `condense/BUILD.bazel` target. The Bazel job is non-blocking, its hermetic Python has no
pytest, and the CI `condense` job is the gate.
