# Narrate engine bench (docs/agent-notes/2026-10-22-narrate-bench-plan.md).
# Root imports this file from the root justfile (`import 'just/narrate-bench.just'`).

# Print the pinned download plan for the bench arms and scoring models; nothing is fetched.
# --apply downloads into $NARRATE_WEIGHTS_DIR (or --dest), outside the repository, and records sha256 values.
# Filters: --arm A1 / --arm A2-mac, --only <source-id>, --include-optional (Drama 3, fish-speech, WavLM);
# an optional arm named with --arm (D3-rented, D3-gpu-experimental) brings its optional sources.
narrate-fetch *ARGS:
    python3 narrate/bench/fetch.py {{ARGS}}

# Regenerate the bench's fixed chunk list (narrate/bench/chunks-v1.json) from text-v1; --check only compares.
narrate-bench-chunks *ARGS:
    python3 narrate/bench/prepare.py {{ARGS}}

# run-bench.sh goes at DEST's top; host_run.py, host-job.json and chunks-v1.json under DEST/job/. The private
# bench.env (binary paths and sha256 values, NARRATE_BENCH_VOICE) is written beside it on the host, never here.
# Stage the GPU-host window files into DEST.
narrate-bench-host-pack dest:
    install -d {{quote(dest)}}/job
    install -m 0755 narrate/bench/run-bench.sh {{quote(dest)}}/run-bench.sh
    install -m 0755 narrate/bench/host_run.py {{quote(dest)}}/job/host_run.py
    install -m 0644 narrate/bench/host-job.json narrate/bench/chunks-v1.json {{quote(dest)}}/job/

# SRC is host:dir, a local runs/<holder> directory, or - to score DEST as it is (already pulled); DEST must be
# outside every git work tree. Scoring is off the GPU: whisper WER with numeral normalisation, catastrophic chunks,
# RTF, VRAM, and SIM (median, minimum, wSIM and the decoy 1/2 checks) with --reference CLIP --sim-model CKPT
# --sim-python PY. Run inside `nix develop .#condense` for whisper-cli; on the shared CPU host, inside a 6G memory
# scope, one scorer at a time. ARGS: --reference --sim-model --sim-python --sim-threads --decoys --arm A.
# Pull a window's outputs back into DEST and score them: DEST/scored.json and DEST/scored.md.
narrate-bench-score src dest *ARGS:
    python3 narrate/bench/score.py {{quote(dest)}} {{ if src == "-" { "" } else { "--pull " + quote(src) } }} {{ARGS}}
