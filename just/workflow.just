# Report tools and optional analysis dependencies; no downloads or configuration changes.
doctor:
    python3 scripts/doctor.py

# Extra ARGS pass through to run_demo.py, e.g.
#   just demo IN "" stdlib base fuller --capture-interval START END --capture-review TEXT
# Without an interval the default refuses (capture_interval_required); pass profile conservative3 instead.
# Produce processed audio/video and analysis; default fuller needs a reviewed --capture-interval.
[positional-arguments]
demo input bpm="" backend="stdlib" features="base" profile="fuller" *ARGS:
    options=(--backend "$3" --features "$4" --profile "$5" "${@:6}"); if [[ -n "$2" ]]; then options+=(--bpm "$2"); fi; python3 scripts/run_demo.py "$1" "${options[@]}"

# Default fuller otherwise refuses (capture_interval_required); pass profile conservative3 for no capture binding.
# Preserve the input and create a new private run; default fuller needs --capture-interval START END --capture-review TEXT.
[positional-arguments]
clean input profile="fuller" *ARGS:
    python3 scripts/media.py clean "$@"

# Keep analysis copies separate from the full-quality audio master.
analyze input run_dir="":
    if [[ -n {{quote(run_dir)}} ]]; then python3 scripts/rhythm.py {{quote(input)}} --run-dir {{quote(run_dir)}}; else python3 scripts/rhythm.py {{quote(input)}}; fi

report run_dir:
    python3 scripts/report.py {{quote(run_dir)}}

# Metadata-only, hash-bound bundle for the optional Quarto report; never copies media.
report-bundle run_dir:
    python3 scripts/report_bundle.py build --run-dir {{quote(run_dir)}}

report-bundle-verify bundle_dir:
    python3 scripts/report_bundle.py verify --bundle-dir {{quote(bundle_dir)}} --check-origin

export run_dir:
    python3 scripts/media.py export {{quote(run_dir)}}

# Smaller sharing copy: preserve aspect/timing, compress AAC, retain the master.
export-share input output height="720" audio_kbps="96" codec="h264" crf="27" timeout="900":
    python3 scripts/share_export.py {{quote(input)}} {{quote(output)}} --height {{quote(height)}} --audio-kbps {{quote(audio_kbps)}} --codec {{quote(codec)}} --crf {{quote(crf)}} --timeout-seconds {{quote(timeout)}}

# Meaningful synthetic media/rhythm/tooling cases; no compilation required.
test:
    python3 -m unittest discover -s tests -p 'test_*.py' -v

check: test
    python3 scripts/doctor.py --require-media

# Only explicitly registered, hash-bound artifacts may be downloaded.
model-prefetch model:
    python3 scripts/model_prefetch.py {{quote(model)}}

# Inspect one stable agent-facing tool schema without running a job.
tool-info name:
    python3 scripts/tool_api.py describe {{quote(name)}}

# Run a typed agent tool using its published JSON argument schema.
tool-run name arguments:
    python3 scripts/tool_api.py run {{quote(name)}} --arguments {{quote(arguments)}}

# Evaluate provenance with an optional reference and explicit run-relative evidence.
dag run_dir reference="" clicks="" pitch="" meter="" tonal="" comparisons="":
    #!/usr/bin/env bash
    set -euo pipefail
    graph_args=({{quote(run_dir)}})
    if [[ -n {{quote(reference)}} ]]; then graph_args+=(--reference {{quote(reference)}}); fi
    if [[ -n {{quote(clicks)}} ]]; then graph_args+=(--clicks-artifact {{quote(clicks)}}); fi
    if [[ -n {{quote(pitch)}} ]]; then graph_args+=(--pitch-artifact {{quote(pitch)}}); fi
    if [[ -n {{quote(meter)}} ]]; then graph_args+=(--meter-artifact {{quote(meter)}}); fi
    if [[ -n {{quote(tonal)}} ]]; then graph_args+=(--tonal-artifact {{quote(tonal)}}); fi
    if [[ -n {{quote(comparisons)}} ]]; then graph_args+=(--comparisons-artifact {{quote(comparisons)}}); fi
    python3 scripts/dag.py "${graph_args[@]}"

# Generic source-time markers; editor-specific imports remain a separate milestone.
markers run_dir:
    python3 scripts/markers.py {{quote(run_dir)}}

# Burn selected review hypotheses into a separate synchronized video preview.
marked-video run_dir output selection="phrase-review":
    python3 scripts/marked_video.py --run-dir {{quote(run_dir)}} --output {{quote(output)}} --selection {{quote(selection)}}

# Copy-only compact marked movie: RUN_DIR audio + verified arrangement preview picture.
# Pass --picture-preview DIR --arrangement-markers SELECTOR [--output DIR] [--timeout-seconds N].
[positional-arguments]
marked-compact run_dir *ARGS:
    python3 scripts/marked_compact.py "$@"

# Local stdio MCP; stdout is reserved exclusively for JSON-RPC messages.
mcp:
    @python3 scripts/mcp_server.py

# Explicit optional local Rust build. Routine Python recipes never compile Rust.
cli:
    CARGO_BUILD_JOBS=1 cargo build --locked -j 1

# Hosted/approved builder verification; never a default local compilation.
test-rust:
    CARGO_BUILD_JOBS=1 cargo test --locked -j 1

# Explicit optional dependency installation from the complete committed lock.
analysis-setup:
    uv sync --extra analysis --frozen --no-python-downloads

# Detection only; optional analysis Python is explicit, and audio stays unchanged.
clicks input run_dir bpm="":
    if [[ -n {{quote(bpm)}} ]]; then "${VIDEO_UTILS_ANALYSIS_PYTHON:-python3}" scripts/clicks.py {{quote(input)}} --run-dir {{quote(run_dir)}} --bpm {{quote(bpm)}}; else "${VIDEO_UTILS_ANALYSIS_PYTHON:-python3}" scripts/clicks.py {{quote(input)}} --run-dir {{quote(run_dir)}}; fi

# Compare discovered recurring regions without a predefined score.
phrase-compare run_dir:
    python3 scripts/phrase_compare.py {{quote(run_dir)}}

# Bounded generated fixtures; output must be a new directory under artifacts/.
benchmark output backend="stdlib" suite="technical-v1":
    if [[ {{quote(backend)}} == librosa ]]; then "${VIDEO_UTILS_ANALYSIS_PYTHON:-python3}" scripts/benchmark.py run --output {{quote(output)}} --phrase-backend {{quote(backend)}} --suite {{quote(suite)}}; else python3 scripts/benchmark.py run --output {{quote(output)}} --phrase-backend {{quote(backend)}} --suite {{quote(suite)}}; fi

# Generate source/component truth only; reference labels remain outside discovery.
benchmark-fixtures output suite="technical-v2":
    python3 scripts/benchmark.py fixtures --output {{quote(output)}} --suite {{quote(suite)}}

# Unseeded generated discovery, then evaluation; explicit optional interpreter.
calibrate fixture_index output backend="librosa" timeout="900":
    #!/usr/bin/env bash
    set -euo pipefail
    : "${VIDEO_UTILS_ANALYSIS_PYTHON:?Set VIDEO_UTILS_ANALYSIS_PYTHON to the locked analysis interpreter}"
    python3 scripts/calibration_pilot.py --fixture-index {{quote(fixture_index)}} --output {{quote(output)}} --analysis-python "$VIDEO_UTILS_ANALYSIS_PYTHON" --backend {{quote(backend)}} --overall-timeout {{quote(timeout)}}

# Score existing hash-bound generated receipts; no inference or real-note grade.
pitch-evaluate fixture_index pilot_index output:
    python3 scripts/pitch_evaluate.py --fixture-index {{quote(fixture_index)}} --pilot-index {{quote(pilot_index)}} --output {{quote(output)}} --summary

# Pure comparison of existing generated receipts; no inference or model setup.
learned-pitch-evaluate fixture_index pyin_pilot_index learned_pilot_index output:
    python3 scripts/learned_pitch_evaluate.py --fixture-index {{quote(fixture_index)}} --pyin-pilot-index {{quote(pyin_pilot_index)}} --learned-pilot-index {{quote(learned_pilot_index)}} --output {{quote(output)}} --summary

phrase-evaluate fixture_index pilot_index output:
    python3 scripts/phrase_evaluate.py --fixture-index {{quote(fixture_index)}} --pilot-index {{quote(pilot_index)}} --output {{quote(output)}} --summary

# Optional qualified CPU comparator; no model or runtime installation is implicit.
basic-pitch run_dir seconds="20":
    python3 scripts/basic_pitch_compare.py {{quote(run_dir)}} --max-analysis-seconds {{quote(seconds)}}

# Explicit optional five-wheel setup using an existing qualified native interpreter.
basic-pitch-runtime-setup python:
    python3 scripts/basic_pitch_runtime_setup.py --python {{quote(python)}}

# Verify the isolated runtime without downloads, installation or model inference.
basic-pitch-runtime-check:
    python3 scripts/basic_pitch_runtime_setup.py --check

# Optional experimental Beat This comparator; no model or runtime installation is implicit.
beat-this-compare run_dir:
    python3 scripts/beat_this_compare.py compare --run-dir {{quote(run_dir)}}

# Explicit Linux-only runtime setup from the flake ml shell python (run on honey inside nix develop .#ml).
beat-this-runtime-setup python:
    python3 scripts/beat_this_runtime_setup.py --python {{quote(python)}}

# Verify the isolated Beat This runtime without downloads, installation or model inference.
beat-this-runtime-check:
    python3 scripts/beat_this_runtime_setup.py --check

# Refuses until root registers the hash-bound model, the operator acknowledges the weights' terms and a runtime
# lane qualifies the runtime.
# Optional experimental htdemucs_6s stem estimates (never recovered stems, never a default).
stems-estimate run_dir start end input_role="denoised":
    python3 -c 'import json, sys; print(json.dumps({"run_dir": sys.argv[1], "excerpt_start_seconds": float(sys.argv[2]), "excerpt_end_seconds": float(sys.argv[3]), "input_role": sys.argv[4]}))' {{quote(run_dir)}} {{quote(start)}} {{quote(end)}} {{quote(input_role)}} | python3 scripts/stems_estimate.py estimate --request -

# Experimental guitar_noul gateway client (TIN-5619); refuses unless VIDEO_UTILS_GUITAR_NOUL_GATEWAY is configured.
guitar-noul-decide request:
    python3 scripts/guitar_noul_client.py --request {{quote(request)}}

# Metadata planning only; no editor API, import file or native execution.
editor-marker-plan run_dir selection profile:
    python3 scripts/editor_marker_plan.py {{quote(run_dir)}} {{quote(selection)}} {{quote(profile)}} --summary

# Uniform-grid-gated local marker preview; abstains for VFR/unknown cadence; never imports.
editor-marker-export run_dir selection profile format output_dir:
    python3 scripts/editor_marker_export.py {{quote(run_dir)}} {{quote(selection)}} {{quote(profile)}} --format {{quote(format)}} --output-dir {{quote(output_dir)}} --summary

# Author source-bound settings only; the review records existing scoped authority.
capture-profile input run_dir review start end nr="8" nf="-40" ad="0" gs="0" lufs="-18" peak="-1.5":
    python3 scripts/capture_profile.py {{quote(input)}} --run-dir {{quote(run_dir)}} --review {{quote(review)}} --capture-start {{quote(start)}} --capture-end {{quote(end)}} --reduction-db {{quote(nr)}} --noise-floor-db {{quote(nf)}} --adaptivity {{quote(ad)}} --gain-smooth {{quote(gs)}} --integrated-lufs {{quote(lufs)}} --true-peak-dbtp {{quote(peak)}}

# Frozen generated holdout metadata; no inference or musical grading.
holdout-plan output:
    python3 scripts/benchmark_holdout.py plan --output {{quote(output)}}

holdout-validate plan:
    python3 scripts/benchmark_holdout.py validate {{quote(plan)}}

holdout-generate plan output timeout="600":
    python3 scripts/benchmark_holdout.py generate --plan {{quote(plan)}} --output {{quote(output)}} --timeout-seconds {{quote(timeout)}}

# Manual local video/audio review with source-bound annotations.
review run_dir port="8765":
    python3 scripts/review_server.py serve {{quote(run_dir)}} --port {{quote(port)}}

# Darwin development harness; no plugin registration or Logic host operation.
au-spike-check:
    python3 native/au-spike/check.py

# Inspect a native AUv3 bundle plan; no launch, installation or registration.
au-package-plan:
    python3 native/au-spike/packaging/build.py --dry-run

# Metadata/signature contract checks; independent from Logic acceptance.
au-package-check:
    python3 native/au-spike/packaging/tests.py

# Explicit development bundle build; no host activation.
au-package-build:
    python3 native/au-spike/packaging/build.py --build

# Optional analysis interpreter is explicit; sampled notes are hypotheses.
pitch input run_dir seconds="20":
    "${VIDEO_UTILS_ANALYSIS_PYTHON:-python3}" scripts/pitch.py {{quote(input)}} --run-dir {{quote(run_dir)}} --max-analysis-seconds {{quote(seconds)}}

# Existing verified features; no inferred four-beat default.
meter run_dir:
    python3 scripts/meter.py --run-dir {{quote(run_dir)}}

# Verified chroma evidence; tuning never establishes tonic or mode.
tonal run_dir:
    python3 scripts/tonal.py {{quote(run_dir)}}

# Isolated native sample-event/ramp checks; no AU installation or host operation.
au-automation-check:
    python3 native/au-spike/automation/check.py

# Isolated typed state/lifecycle experiment; no AU preset or Logic integration.
au-state-check:
    python3 native/au-spike/state/check.py

# Extend a validated rendered run through all optional evidence stages.
evaluate run_dir bpm="" backend="librosa" seconds="20":
    if [[ -n {{quote(bpm)}} ]]; then python3 scripts/run_demo.py --existing-run {{quote(run_dir)}} --features extended --backend {{quote(backend)}} --pitch-seconds {{quote(seconds)}} --bpm {{quote(bpm)}}; else python3 scripts/run_demo.py --existing-run {{quote(run_dir)}} --features extended --backend {{quote(backend)}} --pitch-seconds {{quote(seconds)}}; fi

# Validate source-bound sparse annotation metadata; no recording is read.
corpus manifest local_root="":
    if [[ -n {{quote(local_root)}} ]]; then python3 scripts/corpus.py validate {{quote(manifest)}} --root {{quote(local_root)}} --summary; else python3 scripts/corpus.py validate {{quote(manifest)}} --summary; fi

# Source-bound full-take candidate through the application-specific supervisor.
apply-capture-profile input authoring_dir receipt_sha256 timeout="600":
    @python3 -c 'import json,sys;sys.path.insert(0,"scripts");from tool_api import execute;print(json.dumps(execute("apply_capture_profile",{"input":sys.argv[1],"authoring_dir":sys.argv[2],"receipt_sha256":sys.argv[3],"timeout_seconds":int(sys.argv[4])}),allow_nan=False))' {{quote(input)}} {{quote(authoring_dir)}} {{quote(receipt_sha256)}} {{quote(timeout)}}

# Fresh reference-conditioned metadata assessment; no audio decoding or inference.
arrangement-reference run_dir output reference="program/demo-arrangement.json":
    python3 scripts/arrangement_reference.py {{quote(reference)}} --run-dir {{quote(run_dir)}} --output {{quote(output)}}

# Existing renderer with an explicit validated same-run-relative marker selector.
marked-arrangement run_dir output arrangement_markers:
    python3 scripts/marked_video.py --run-dir {{quote(run_dir)}} --selection all-review --output {{quote(output)}} --arrangement-markers {{quote(arrangement_markers)}}

# Convert a source-bound assessment into a fresh same-run marker JSON.
arrangement-markers run_dir assessment output:
    python3 scripts/arrangement_markers.py {{quote(run_dir)}} --assessment {{quote(assessment)}} --output {{quote(output)}}

# Separate structured user issues; legacy review annotations are retained.
annotations-v2 run_dir:
    python3 scripts/annotation_v2.py read {{quote(run_dir)}}

annotate-v2 run_dir request:
    python3 scripts/annotation_v2.py write {{quote(run_dir)}} --input {{quote(request)}}

# Read-only authored take-family split validation; no automatic data assignment.
corpus-split manifest local_root=".":
    python3 scripts/corpus_split_s1.py validate {{quote(manifest)}} --root {{quote(local_root)}} --summary

# Sha256-pinned v2 annotations as generic markers; basis labels are not verdicts.
annotation-markers run_dir store_sha256 output_dir:
    python3 scripts/annotation_markers.py {{quote(run_dir)}} --store-sha256 {{quote(store_sha256)}} --output-dir {{quote(output_dir)}}

# Default review ordering of existing flags by frozen rule v1; no new kinds or verdict.
flags-triage run_dir output:
    python3 scripts/flags_triage.py {{quote(run_dir)}} --output {{quote(output)}}

# Coverage-first sparse evaluation of untouched proposals; precision null, no negatives.
corpus-eval-s2 manifest proposals proposals_sha256 output local_root=".":
    python3 scripts/corpus_eval_s2.py evaluate {{quote(manifest)}} --root {{quote(local_root)}} --proposals {{quote(proposals)}} --proposals-sha256 {{quote(proposals_sha256)}} --output {{quote(output)}}

# Stream SHA-256 of one or more files (shasum -a 256 compatible lines)
hash +FILES:
    CARGO_BUILD_JOBS=1 cargo run --locked -j 1 --quiet -- hash {{FILES}}

# Metadata-only, read-only hash/typed-field verification of a run directory
verify-run RUN_DIR:
    CARGO_BUILD_JOBS=1 cargo run --locked -j 1 --quiet -- verify-run "{{RUN_DIR}}"

# Closed-schema capability metadata check and static worker/skill/test traversal.
capabilities-check:
    python3 scripts/capabilities.py validate && python3 scripts/capabilities.py traverse

# Project stable artifact IDs for explicit run selectors; read-only.
artifact-id SELECTOR:
    python3 scripts/artifact_ids.py project {{quote(SELECTOR)}}

# Experimental per-phrase onset offsets from the recorded click; descriptive, never a grade or verdict.
phrase-timing analysis phrases output_root run_kind="real_take":
    python3 scripts/phrase_timing.py --analysis {{quote(analysis)}} --phrases {{quote(phrases)}} --output-root {{quote(output_root)}} --run-kind {{quote(run_kind)}}

# Extra ARGS: --room-temp-c C, --device-label/--app-label/--metronome-label/--placement-note TEXT. 600 s bound.
# Experimental capture-latency calibration record from an operator clip; analysis only, abstains beyond 5 ms.
[positional-arguments]
timing-calibration-analyze input segments distances method amp_chain setup_id output_root *ARGS:
    python3 -c 'import subprocess, sys; sys.exit(subprocess.run(sys.argv[1:], stdin=subprocess.DEVNULL, timeout=600).returncode)' python3 scripts/timing_calibration.py analyze "$1" --segments="$2" --distances="$3" --distance-method="$4" --amp-chain="$5" --setup-id="$6" --output-root="$7" "${@:8}"

# Calibrated phrase-timing view; a direction only beyond the stated uncertainty, never a grade. 600 s bound.
timing-calibration-apply phrase_timing calibration setup_id output_root:
    python3 -c 'import subprocess, sys; sys.exit(subprocess.run(sys.argv[1:], stdin=subprocess.DEVNULL, timeout=600).returncode)' python3 scripts/timing_calibration.py apply --phrase-timing={{quote(phrase_timing)}} --calibration={{quote(calibration)}} --setup-id={{quote(setup_id)}} --output-root={{quote(output_root)}}

# Level-matched stage tone A/B with one unreviewed low-shelf trial; never adopts a master.
tone-ab run_dir start end timeout="1200":
    python3 scripts/tone_ab.py run --run-dir {{quote(run_dir)}} --common-region-start {{quote(start)}} --common-region-end {{quote(end)}} --timeout-seconds {{quote(timeout)}}

# A running share_export worker keeps its own session and may outlive the server up to its own timeout (<= 900 s).
# Private loopback job control API, foreground only (Ctrl-C stops the server, not a running job). Not a daemon.
web-jobs-serve port="0" state_root="artifacts/web-jobs":
    python3 scripts/web_api.py serve --port {{quote(port)}} --state-root {{quote(state_root)}}

# Read-only job store counts (no lock, no reconciliation).
web-jobs-status state_root="artifacts/web-jobs":
    python3 scripts/web_jobs.py --state-root {{quote(state_root)}} status

# S2 web reliability demo + failure injections (in-process loopback; foreground; no daemon)
web-reliability-test:
    PYTHONPATH=tests python3 -m unittest test_web_reliability -v

# Local web fixture (prototype): frozen-lockfile install. Loopback only; no hosted deployment.
web-install:
    cd web && pnpm install --frozen-lockfile

# Local web fixture dev server bound to 127.0.0.1 (prototype).
web-dev port="5173":
    cd web && pnpm exec vite dev --host 127.0.0.1 --port {{quote(port)}} --strictPort

# Offline frozen install, type check and build of the local web fixture.
web-build:
    cd web && pnpm install --frozen-lockfile --offline && pnpm run check && pnpm run build

# Serve the built web fixture on loopback; optional control API URL from web-jobs-serve.
web-serve port="3000" control_api="":
    cd web && HOST=127.0.0.1 PORT={{quote(port)}} VIDEO_UTILS_CONTROL_API_URL={{quote(control_api)}} node serve.js

# Web fixture behaviour tests (loopback enforcement, BFF limits, pins).
web-test:
    PYTHONPATH=tests python3 -m unittest test_web_stack -v

# S3 routes_review read API and route tests (foreground, synthetic fixtures only)
web-runs-test:
    PYTHONPATH=tests python3 -m unittest test_web_runs_s3 -v

# S3 processing job types, capture reviews and capture/process routes (foreground, synthetic fixtures only)
web-processing-test:
    PYTHONPATH=tests python3 -m unittest test_web_processing_s3 -v

# S3 auth modes, Access JWT gate, container and deploy-plan static checks (no network, nothing applied)
auth-hosting-test:
    PYTHONPATH=tests python3 -m unittest test_auth_hosting_s3 -v

# Build the web BFF image locally from web/Containerfile. Local build only: no push, no registry login, no deploy.
web-image-build tag="video-utils-web:local" engine="podman":
    {{quote(engine)}} build -f web/Containerfile -t {{quote(tag)}} web

# Print the reviewed hosted deploy plan and its file hashes. Read-only: applies nothing to a cluster or Cloudflare.
deploy-plan:
    @cat deploy/README.md
    @echo
    @echo "deploy plan files (sha256); nothing here has been applied:"
    @shasum -a 256 deploy/k8s/* deploy/cloudflare/* web/Containerfile

# Read-only AU discovery/auval step; never installs, registers or repairs.
au-auval-step:
    python3 native/au-spike/host/auval_step.py

# Crash-recover one recorded demo invocation in place (same run_dir and ID); replays recorded settings.
# Typed refusals (exit 1) write nothing; see docs/spec/sprints/ROBUSTNESS_S2.md section 3.6.
demo-resume invocation_id:
    python3 scripts/run_demo.py --resume {{quote(invocation_id)}}

# Public static landing site (S3 public_site; docs/spec/sprints/PUBLIC_SITE_S3.md). Never deployed by these recipes.
site-install:
    cd site && pnpm install --frozen-lockfile

site-check:
    cd site && pnpm run check

site-build:
    cd site && pnpm run build

site-leak-scan:
    cd site && pnpm run leak-scan

site-test:
    PYTHONPATH=tests python3 -m unittest test_public_site_s3 -v

# Deploying is an outward-facing action: this recipe only refuses and points at the plan.
site-pages-deploy:
    @echo "refused: deploying the public site needs an explicit operator go; see docs/spec/sprints/PUBLIC_SITE_S3.md" && exit 2

# Web app tests (S3 web_tests; docs/spec/sprints/WEB_TESTS_S3.md). Loopback only; mocked control API.
web-unit:
    cd web && pnpm run test:unit

web-e2e:
    cd web && pnpm run build && pnpm run test:e2e

web-a11y:
    cd web && pnpm run build && pnpm run test:a11y

web-house-stack-test:
    PYTHONPATH=tests python3 -m unittest test_web_house_stack_s3 -v
