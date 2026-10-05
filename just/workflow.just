# Report tools and optional analysis dependencies; no downloads or configuration changes.
doctor:
    python3 scripts/doctor.py

# Produce processed audio/video, rhythm measurements and a local comparison report.
demo input bpm="" backend="stdlib" features="base":
    if [[ -n {{quote(bpm)}} ]]; then python3 scripts/run_demo.py {{quote(input)}} --bpm {{quote(bpm)}} --backend {{quote(backend)}} --features {{quote(features)}}; else python3 scripts/run_demo.py {{quote(input)}} --backend {{quote(backend)}} --features {{quote(features)}}; fi

# Preserve the input and create a new private run directory.
clean input profile="conservative3":
    python3 scripts/media.py clean {{quote(input)}} {{quote(profile)}}

# Keep analysis copies separate from the full-quality audio master.
analyze input run_dir="":
    if [[ -n {{quote(run_dir)}} ]]; then python3 scripts/rhythm.py {{quote(input)}} --run-dir {{quote(run_dir)}}; else python3 scripts/rhythm.py {{quote(input)}}; fi

report run_dir:
    python3 scripts/report.py {{quote(run_dir)}}

export run_dir:
    python3 scripts/media.py export {{quote(run_dir)}}

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

phrase-evaluate fixture_index pilot_index output:
    python3 scripts/phrase_evaluate.py --fixture-index {{quote(fixture_index)}} --pilot-index {{quote(pilot_index)}} --output {{quote(output)}} --summary

# Manual local video/audio review with source-bound annotations.
review run_dir port="8765":
    python3 scripts/review_server.py serve {{quote(run_dir)}} --port {{quote(port)}}

# Darwin development harness; no plugin registration or Logic host operation.
au-spike-check:
    python3 native/au-spike/check.py

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
