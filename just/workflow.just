# Report tools and optional analysis dependencies; no downloads or configuration changes.
doctor:
    python3 scripts/doctor.py

# Produce processed audio/video, rhythm measurements and a local comparison report.
demo input:
    python3 scripts/run_demo.py {{quote(input)}}

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
