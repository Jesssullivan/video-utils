# Report tools and optional analysis dependencies; no downloads or configuration changes.
doctor:
    python3 scripts/doctor.py

# Produce processed audio/video, rhythm measurements and a local comparison report.
demo input bpm="" backend="stdlib":
    if [[ -n {{quote(bpm)}} ]]; then python3 scripts/run_demo.py {{quote(input)}} --bpm {{quote(bpm)}} --backend {{quote(backend)}}; else python3 scripts/run_demo.py {{quote(input)}} --backend {{quote(backend)}}; fi

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

# Evaluate phrase/rhythm evidence and optional approved reference in an existing run.
dag run_dir reference="":
    if [[ -n {{quote(reference)}} ]]; then python3 scripts/dag.py {{quote(run_dir)}} --reference {{quote(reference)}}; else python3 scripts/dag.py {{quote(run_dir)}}; fi

# Generic source-time markers; editor-specific imports remain a separate milestone.
markers run_dir:
    python3 scripts/markers.py {{quote(run_dir)}}

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
benchmark output backend="stdlib":
    if [[ {{quote(backend)}} == librosa ]]; then "${VIDEO_UTILS_ANALYSIS_PYTHON:-python3}" scripts/benchmark.py run --output {{quote(output)}} --phrase-backend {{quote(backend)}}; else python3 scripts/benchmark.py run --output {{quote(output)}} --phrase-backend {{quote(backend)}}; fi

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
