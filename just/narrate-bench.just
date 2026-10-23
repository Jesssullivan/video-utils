# Narrate engine bench (docs/agent-notes/2026-10-22-narrate-bench-plan.md).
# Root imports this file from the root justfile (`import 'just/narrate-bench.just'`).

# Print the pinned download plan for the bench arms and scoring models; nothing is fetched.
# --apply downloads into $NARRATE_WEIGHTS_DIR (or --dest), outside the repository, and records sha256 values.
# Filters: --arm A1 / --arm A2-mac, --only <source-id>, --include-optional (Drama 3, fish-speech, WavLM);
# an optional arm named with --arm (D3-rented, D3-gpu-experimental) brings its optional sources.
narrate-fetch *ARGS:
    python3 narrate/bench/fetch.py {{ARGS}}

# Examples (outputs stay private, outside the repository):
#   just narrate-bench-arm chunks
#   just narrate-bench-arm run --endpoint URL --model M --arm A2-mac --voice ID --clip WAV --transcript TXT --seed 1 --out DIR
#   just narrate-bench-arm score --out DIR --whisper-model models/ggerganov-whisper-cpp-ggml-small.en.bin
# On a shared CPU host, score inside a bounded scope, one scorer at a time (whisper uses at most 4 threads):
#   systemd-run --user --scope -p MemoryMax=6G nice -n 19 ionice -c3 just narrate-bench-arm score ...
# Run and score one bench arm against a speech endpoint on loopback or through an SSH forward.
narrate-bench-arm *ARGS:
    python3 narrate/bench/run_arm.py {{ARGS}}
