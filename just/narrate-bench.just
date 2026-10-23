# Narrate engine bench (docs/agent-notes/2026-10-22-narrate-bench-plan.md).
# Root imports this file from the root justfile (`import 'just/narrate-bench.just'`).

# Print the pinned download plan for the bench arms and scoring models; nothing is fetched.
# --apply downloads into $NARRATE_WEIGHTS_DIR (or --dest), outside the repository, and records sha256 values.
# Filters: --arm A1 / --arm A2-mac, --only <source-id>, --include-optional (Drama 3, fish-speech, WavLM);
# an optional arm named with --arm (D3-rented, D3-gpu-experimental) brings its optional sources.
narrate-fetch *ARGS:
    python3 narrate/bench/fetch.py {{ARGS}}
