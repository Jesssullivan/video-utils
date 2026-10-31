# Narrated video (docs/spec/NARRATED_VIDEO.md), lanes L3 to L6: the stage graph's init, plan, status, explain and
# verify, the run, stage and quick recipes (script, voice, voice_qa, base, place, music, mix, avatar, avatar_check,
# compose, deliver_check and handoff), the kitpip pin check, and demo bundle intake with its claims gate (TIN-7735).
# Run inside `nix develop .#condense` (FFmpeg, python3, pytest).
# Root imports this file from the root justfile (`import 'just/narrated-video.just'`).
# Jobs and their stage directories land in artifacts/narrated/<job_id>/ (NARRATED_VIDEO_ROOT), outside
# artifacts/runs/ and artifacts/narrate/. Records come from NARRATED_VIDEO_RECORDS (dhall-to-json renders), sources
# from the private store NARRATE_STORE, the lexical release from NARRATE_LEXICAL_DIR, the private kitpip pin from
# NARRATED_VIDEO_EXTERNALS and the binary from KITPIP_BIN (the VRM renderer draft from VRM_RENDERER_BIN). A job holds
# digests and record ids, never a path.
# Runs go through narrate/bounded.sh (nice 19, a 6G memory scope, one heavy narrate step at a time).

# The defaults: one segment voiced by NARRATE_JOB, a #101820 card (or --still SHA), the kitpip avatar on where the
# edition allows one (NV-8: pass --persona P, or --no-avatar), the bed only with --bed ID, edition Internal and tighten
# off (NV-2). --client makes a client delivery: edition ClientNarrated (NV-6). A ClientVoiceOnly job comes only
# through python -m narrate video init --from FILE. admit refuses a voice without consent, or an avatar without a
# persona, before anything is written.
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

# Check the private kitpip pin (NARRATED_VIDEO_EXTERNALS) against its public registration in program/externals.json,
# then KITPIP_BIN against the pin's digest and size. Refuses kitpip_pin_pending while the release digest is pending.
kitpip-pin-check *args:
    python3 -m narrate video pin-check {{args}}

# Check the private VRM renderer pin (the vrm entry of NARRATED_VIDEO_EXTERNALS) against its public registration, then
# VRM_RENDERER_BIN against the pin's digest and size (SPR-128, a draft). Refuses vrm_pin_pending until a renderer exists.
vrm-pin-check *args:
    python3 -m narrate video pin-check --external vrm {{args}}

# Record the operator's acceptance of one operator gate (listening or lip_sync) of the job's current deliver_check
# render. DECISION is the Softproxy decision id of the operator's accept (sp:dec:<ulid>) and nothing else: free text,
# an empty or malformed id, a machine gate, the visible_text gate and an unknown gate refuse. VIDEO is the sha256 of
# the cut the decision saw; it refuses unless it is the current composed video. The same gate and decision again is a no-op. ARGS: --root DIR.
nv-accept job gate decision video *args:
    python3 -m narrate video accept {{quote(job)}} --gate {{quote(gate)}} --decision {{quote(decision)}} \
        --video-sha256 {{quote(video)}} {{args}}

# Re-hash a stage directory, or every current stage of a job directory.
nv-verify dir:
    python3 -m narrate video verify {{quote(dir)}}

# Run the stale stages of a job, script to handoff, and stop at the first refusal; finished stages stay fresh. The
# avatar and avatar_check stages run when the job has an avatar and KITPIP_BIN resolves to its pin; compose waits
# for them. ARGS: --stages S,... | --until STAGE | --force S,... | --json.
nv-run job *args:
    narrate/bounded.sh python3 -m narrate video run {{quote(job)}} {{args}}

# Run one stage node when its inputs are fresh. ARGS: --segment ID for a fan-out stage, --json.
nv-stage job stage *args:
    narrate/bounded.sh python3 -m narrate video stage {{quote(job)}} {{quote(stage)}} {{args}}

# Adopt a narrate run already rendered and verified elsewhere (an AudioCppBatch engine's `just narrate-render CONFIG
# --prerendered DIR`) as the job's voice node instead of voicing it again. The run is copied into the stage
# directory, re-verified there and bound to what the stage would render (narrate job and gates, script, engine record
# and knobs, voices by speaker with clips and consents, lexical release, pronunciation), after narrate's consent
# policy admits the job against this job's own records and store. It refuses a policy failure, a run that fails
# narrate verify, a test-mode batch (prerendered_test_mode), a failed chunk gate or a run that differs. ARGS:
# --segment ID (default the job's only segment), --replace to archive a fresh voice node once the new run passes
# every check, --json.
# Record an already rendered narrate run as a job's voice stage output.
nv-stage-voice-from-run job run_dir *args:
    narrate/bounded.sh python3 -m narrate video stage {{quote(job)}} voice --from-run {{quote(run_dir)}} {{args}}

# The Cade render stage's task body (docs/spec/RENDER_STAGE.md, TIN-7788). Check a request of ids and digests and
# print its phases; it writes nothing and never takes the GPU Lease. ARGS: --inputs DIR re-hashes each input at
# DIR/<sha256>.
nv-render-stage-check request *args:
    python3 -m narrate video render-stage check --request {{quote(request)}} {{args}}

# Report a job that ran to deliver_check, every output by digest, for the request that started it. Refuses unless
# VIDEO_UTILS_COMMIT is the request's commit. ARGS: --export DIR copies the video, the report and the result there
# by sha256, --root DIR.
nv-render-stage-result job request *args:
    python3 -m narrate video render-stage result {{quote(job)}} --request {{quote(request)}} {{args}}

# A simple job in one step: init from the defaults, then run. ARGS go to init (--card, --still SHA, --bed ID,
# --edition E, --persona P or --no-avatar); the store, records and lexical release come from the environment.
nv-quick job narrate_job script *args:
    python3 -m narrate video init --job {{quote(job)}} --narrate-job {{quote(narrate_job)}} --script {{quote(script)}} {{args}}
    narrate/bounded.sh python3 -m narrate video run {{quote(job)}}

# Plan the committed card example against the committed records, then run nv-quick end to end on a synthetic
# workspace (generated sine voice, generated E-major bed loops, a colour card, --no-avatar: no kitpip binary) through
# compose and deliver_check, and print the mix measurements and the delivery gates.
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
    just nv-quick nv-fixture-quick job-fixture-fake "$root/ws/store/script.md" --bed bed-fixture-emaj --no-avatar
    python3 -m narrate video verify "$root/narrated/nv-fixture-quick"
    python3 - "$root/narrated/nv-fixture-quick" <<'PY'
    import json, sys
    from pathlib import Path
    job = Path(sys.argv[1])
    stages = json.loads((job / "current.json").read_text())["stages"]
    m = json.loads((job / stages["mix"]["dir"] / "manifest.json").read_text())["measurements"]
    keep = ("integrated_lufs", "drift_lu", "true_peak_dbtp", "voice_integrated_lufs", "bed_below_voice_lu",
            "duck_depth_db", "length_s", "channels", "flags")
    d = json.loads((job / stages["deliver_check"]["dir"] / "manifest.json").read_text())["measurements"]
    print(json.dumps({"mix": {k: m[k] for k in keep}, "deliver_check": {k: d[k] for k in ("gates", "delivery_gate")}},
                     sort_keys=True))
    PY

# Demo bundle intake (docs/spec/NARRATED_VIDEO.md, "Demo bundle intake", TIN-7735). A bundle is a directory with
# manifest.json, script.md, claims.json and its PNG, MP4 and GIF assets. The claims gate refuses a segment that speaks
# a number no cited, receipted claims.json entry backs. Run both on the private bundle where it lives; nothing renders.
# Run the spoken-number claims gate alone: one row per segment; exit 1 when a segment refuses. ARGS: [--denylist
# FILE] (or NARRATED_VIDEO_DENYLIST), needed when the manifest declares ip_private or never_name, and
# [--denylist-sha256 HEX] (or NARRATED_VIDEO_DENYLIST_SHA256), the operator's pin for a private lane.
narrated-video-claims bundle *args:
    python3 -m narrate video claims {{quote(bundle)}} {{args}}

# One NarratedVideo job (edition Internal) and one confidential narrate job per beat, written only after the claims
# gate, every asset digest and admit pass. OUT is a new or empty directory. ARGS: --records DIR (or
# NARRATED_VIDEO_RECORDS) --narrate-template ID --voice ID --engine ID (--persona P | --no-avatar) [--job ID]
# [--store DIR, default OUT/store] [--tail-s S] [--denylist FILE] [--denylist-sha256 HEX] [--json]. Then `python3 -m narrate video init --job ID --from
# OUT/narrated-video.json --records OUT/records` and `just nv-run ID`.
# Turn a demo bundle into a narrated-video job and its narrate jobs, claims gated; nothing is written on a refusal.
narrated-video-intake bundle out *args:
    python3 -m narrate video intake {{quote(bundle)}} --out {{quote(out)}} {{args}}

# The synthetic demo-fixture bundle and workspace: claims gate, intake, then init (which plans) against the intake's
# records. No render; tests/test_narrated_video_intake.py runs the job through deliver_check.
# Run the claims gate, intake and init on the synthetic demo-fixture bundle.
nv-intake-fixture:
    #!/usr/bin/env bash
    set -euo pipefail
    root="$(mktemp -d)"
    trap 'rm -rf "$root"' EXIT
    python3 -m narrate video fixture --out "$root/ws" --bundle > /dev/null
    bundle="$root/ws/bundle/demo-fixture"
    python3 -m narrate video claims "$bundle" > "$root/claims.json"
    python3 -m narrate video intake "$bundle" --out "$root/out" --records "$root/ws/records" \
        --narrate-template job-fixture-fake --voice voice-fixture-sine --engine fake-sine --no-avatar \
        --store "$root/ws/store"
    python3 -m narrate video init --root "$root/narrated" --records "$root/out/records" --store "$root/ws/store" \
        --job demo-fixture --from "$root/out/narrated-video.json"

# The graph-core, simple-path, avatar and compose tests: keys, invalidation rows, freshness, admit, the CLI, the
# kitpip pin and avatar stages on the stub, the L4 stages on synthetic fixtures (levels, duck, placement property,
# editions at Place, labels, bases, the bed) and the L6 stages (alpha, captions, labels, profiles, slides, the flash
# gate, avatarOff and handoff), voice --from-run adoption with its refusals, the demo bundle intake and claims
# gate with its units and its private-terms guard (with the slides' visible text and the metadata strip), the VRM renderer
# draft on its stub (pin, avatar.manifest/v1, face timeline, gates) and operator acceptance by Softproxy decision id with
# its refusals.
nv-test:
    cd narrate && python3 -m pytest -q tests/test_narrated_video_graph.py tests/test_narrated_video_types.py \
        tests/test_narrated_video_simple.py tests/test_narrated_video_avatar.py tests/test_narrated_video_compose.py \
        tests/test_narrated_video_adopt.py tests/test_narrated_video_intake.py \
        tests/test_narrated_video_claims_units.py tests/test_narrated_video_private_terms.py \
        tests/test_narrated_video_vrm.py tests/test_narrated_video_visible_text.py tests/test_narrated_video_accept.py
