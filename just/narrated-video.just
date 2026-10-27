# Narrated video (docs/spec/NARRATED_VIDEO.md), lanes L3 and L4: the stage graph's init, plan, status, explain and
# verify, and the simple path's run, stage and quick recipes (script, voice, voice_qa, base, place, music and mix).
# Run inside `nix develop .#condense` (FFmpeg, python3, pytest).
# Root imports this file from the root justfile (`import 'just/narrated-video.just'`).
# Jobs and their stage directories land in artifacts/narrated/<job_id>/ (NARRATED_VIDEO_ROOT), outside
# artifacts/runs/ and artifacts/narrate/. Records come from NARRATED_VIDEO_RECORDS (dhall-to-json renders), sources
# from the private store NARRATE_STORE, the lexical release from NARRATE_LEXICAL_DIR, the private kitpip pin from
# NARRATED_VIDEO_EXTERNALS and the binary from KITPIP_BIN. A job holds digests and record ids, never a path.
# Runs go through narrate/bounded.sh (nice 19, a 6G memory scope, one heavy narrate step at a time).
# nv-bed and kitpip-pin-check come with lanes L5 and L6.

# The defaults: one segment voiced by NARRATE_JOB, a #101820 card (or --still SHA), no avatar unless --avatar
# --persona P (opt-in until L6, docs/spec/NARRATED_VIDEO.md), the bed only with --bed ID, edition Internal and tighten
# off (NV-2). admit refuses a voice without consent before anything is written.
# Write a simple job from the defaults into the store and record its first plan.
nv-init job narrate_job script *args:
    python3 -m narrate video init --job {{quote(job)}} --narrate-job {{quote(narrate_job)}} --script {{quote(script)}} {{args}}

# Key every stage of a job and print its state, reason and key. Read-only; --record also writes graph.json.
nv-plan job *args:
    python3 -m narrate video plan {{quote(job)}} {{args}}

# Print the last recorded graph.json, with the operator gates still open (pending_operator).
nv-status job *args:
    python3 -m narrate video status {{quote(job)}} {{args}}

# Print one stage's key inputs and what changed since its last fresh run. ARGS: --segment ID for a fan-out stage.
nv-explain job stage *args:
    python3 -m narrate video explain {{quote(job)}} {{quote(stage)}} {{args}}

# Re-hash a stage directory, or every current stage of a job directory.
nv-verify dir:
    python3 -m narrate video verify {{quote(dir)}}

# Run the stale stages of a job: lane L4 runs script to mix and stops at the first refusal; finished stages stay
# fresh. ARGS: --stages S,... | --until STAGE | --force S,... | --json.
nv-run job *args:
    narrate/bounded.sh python3 -m narrate video run {{quote(job)}} {{args}}

# Run one stage node when its inputs are fresh. ARGS: --segment ID for a fan-out stage, --json.
nv-stage job stage *args:
    narrate/bounded.sh python3 -m narrate video stage {{quote(job)}} {{quote(stage)}} {{args}}

# A simple job in one step: init from the defaults, then run. ARGS go to init (--card, --still SHA, --bed ID,
# --edition E); the store, records and lexical release come from the environment.
nv-quick job narrate_job script *args:
    python3 -m narrate video init --job {{quote(job)}} --narrate-job {{quote(narrate_job)}} --script {{quote(script)}} {{args}}
    narrate/bounded.sh python3 -m narrate video run {{quote(job)}}

# Plan the committed card example against the committed records, then run nv-quick end to end on a synthetic
# workspace (generated sine voice, generated E-major bed loops, a colour card) and print the mix measurements.
# Whisper is pointed at no model: the fixture voice is a sine, not speech, so WER stays not_measured.
nv-fixture:
    #!/usr/bin/env bash
    set -euo pipefail
    root="$(mktemp -d)"
    trap 'rm -rf "$root"' EXIT
    records=narrate/dhall/examples
    python3 -m narrate video init --root "$root/plan" --records "$records" --job nv-fixture-card \
        --from "$records/narrated-videos.json"
    python3 -m narrate video plan nv-fixture-card --root "$root/plan" --records "$records"
    python3 -m narrate video fixture --out "$root/ws" > "$root/fixture.json"
    export NARRATED_VIDEO_ROOT="$root/narrated" NARRATED_VIDEO_RECORDS="$root/ws/records"
    export NARRATE_STORE="$root/ws/store" NARRATE_LEXICAL_DIR="$root/ws/lexical"
    export NARRATE_WHISPER_MODEL="$root/no-whisper-model.bin"
    just nv-quick nv-fixture-quick job-fixture-fake "$root/ws/store/script.md" --bed bed-fixture-emaj
    python3 -m narrate video verify "$root/narrated/nv-fixture-quick"
    python3 - "$root/narrated/nv-fixture-quick" <<'PY'
    import json, sys
    from pathlib import Path
    job = Path(sys.argv[1])
    entry = json.loads((job / "current.json").read_text())["stages"]["mix"]
    m = json.loads((job / entry["dir"] / "manifest.json").read_text())["measurements"]
    keep = ("integrated_lufs", "drift_lu", "true_peak_dbtp", "voice_integrated_lufs", "bed_below_voice_lu",
            "duck_depth_db", "length_s", "channels", "flags")
    print(json.dumps({k: m[k] for k in keep}, sort_keys=True))
    PY

# The graph-core and simple-path tests: keys, invalidation rows, freshness, admit, the CLI, the kitpip stub stage and
# the L4 stages on synthetic fixtures (levels, duck, placement property, editions at Place, labels, bases, the bed).
nv-test:
    cd narrate && python3 -m pytest -q tests/test_narrated_video_graph.py tests/test_narrated_video_types.py \
        tests/test_narrated_video_simple.py
