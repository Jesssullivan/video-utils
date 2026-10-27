# Narrated video (docs/spec/NARRATED_VIDEO.md), lane L3: the stage graph's init, plan, status, explain and verify.
# Run inside `nix develop .#condense` (FFmpeg, python3, pytest).
# Root imports this file from the root justfile (`import 'just/narrated-video.just'`).
# Jobs and their stage directories land in artifacts/narrated/<job_id>/ (NARRATED_VIDEO_ROOT), outside
# artifacts/runs/ and artifacts/narrate/. Records come from NARRATED_VIDEO_RECORDS (dhall-to-json renders), the
# private kitpip pin from NARRATED_VIDEO_EXTERNALS and the binary from KITPIP_BIN. A job holds digests and record ids,
# never a path. nv-quick, nv-run, nv-stage, nv-bed and kitpip-pin-check come with lanes L4 to L6.

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

# Plan the committed card example against the committed records: a fixture check with no private input.
nv-fixture:
    #!/usr/bin/env bash
    set -euo pipefail
    root="$(mktemp -d)"
    trap 'rm -rf "$root"' EXIT
    records=narrate/dhall/examples
    python3 -m narrate video init --root "$root" --records "$records" --job nv-fixture-card \
        --from "$records/narrated-videos.json"
    python3 -m narrate video plan nv-fixture-card --root "$root" --records "$records"

# The graph-core tests: keys, invalidation rows, freshness, admit, the CLI and the kitpip stub stage.
nv-test:
    cd narrate && python3 -m pytest -q tests/test_narrated_video_graph.py tests/test_narrated_video_types.py
