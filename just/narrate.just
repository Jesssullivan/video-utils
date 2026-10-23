# Narration (docs/spec/NARRATE.md). Run inside `nix develop .#condense`: FFmpeg, whisper-cpp, python3, ruff.
# Root imports this file from the root justfile (`import 'just/narrate.just'`).
# One narrate.toml names the job and its rendered Dhall records. Reference clips, transcripts, consent evidence
# and the pinned xoxd-lexical release live outside git: NARRATE_STORE and NARRATE_LEXICAL_DIR.
# Runs land in artifacts/narrate/<run_id>/, outside artifacts/runs/; no guitar tool reads them.

# Per-chunk whisper runs inside a render, so it runs through narrate/bounded.sh (6G MemoryMax, nice 19, idle I/O).
# Render a job: adapters, lexical pass, chunker, engine, per-chunk QA, timing fit, loudness, verify.
narrate-render config="narrate.toml" *args:
    narrate/bounded.sh python3 -m narrate render {{quote(config)}} {{args}}

# Bounded like narrate-render (whisper reads the delivered audio).
# Score a rendered run without changing it: loudness, overruns, WER (whisper when present), SIM.
narrate-eval run_dir config="":
    narrate/bounded.sh python3 -m narrate evaluate {{quote(run_dir)}} {{ if config == "" { "" } else { "--config " + quote(config) } }}

# Re-hash and re-check a run.
narrate-verify run_dir:
    python3 -m narrate verify {{quote(run_dir)}}

# Voices with consent state, and engines with confidentiality eligibility. Never a path or a clip.
narrate-voices config="narrate.toml":
    python3 -m narrate voices {{quote(config)}}

# Engine profiles with confidentiality eligibility and availability.
narrate-engines config="narrate.toml":
    python3 -m narrate engines {{quote(config)}}

# Copy a 10 to 30 s consented reference clip and its verified transcript into the private store by sha256,
# and print the Voice record for the private registry. The consent record is added separately.
narrate-voice-add config clip transcript id consent *args:
    python3 -m narrate voices {{quote(config)}} add --clip {{quote(clip)}} --transcript {{quote(transcript)}} --id {{quote(id)}} --consent {{quote(consent)}} {{args}}

# qwentts.cpp tts-server on 127.0.0.1 (default port 18089) with at most 8 CPU threads and the pinned Qwen3-TTS
# 1.7B Base GGUF from NARRATE_WEIGHTS_DIR (`just narrate-fetch --only qwen3-tts-1.7b-base-qwentts --apply`). It
# builds the pinned commit in $TMPDIR first when needed. Paths and knobs come from the environment only (see
# narrate/serve/qwentts-cpu.sh); an engine record with backend QwenTtsCpp points at the printed address.
# Start the CPU engine (qwentts.cpp, loopback, at most 8 threads) in the foreground.
narrate-serve-cpu:
    narrate/serve/qwentts-cpu.sh serve

# Build the CPU engine without starting it.
narrate-build-cpu:
    narrate/serve/qwentts-cpu.sh build

# The engine bench. Lane W3 (TIN-7085) owns it; `just narrate-fetch` prints the pinned download plan.
narrate-bench *args:
    @echo "narrate-bench: not implemented yet; lane W3 (TIN-7085) fills this recipe. See just narrate-fetch." >&2
    @exit 2

# Lint and format check: ruff over narrate/ (bench included), shellcheck over the bench window runner.
narrate-lint:
    cd narrate && ruff check . && ruff format --check . && shellcheck bench/run-bench.sh

# The synthetic-fixture tests: the fake engine and FFmpeg make every take. No voice, model or network.
narrate-test:
    cd narrate && python3 -m pytest -q

# Fetch the registered speaker-verification model (SIM) into models/, hash-checked against program/models.json.
# Scoring runs in `nix develop .#ml` (torch, speechbrain) or with NARRATE_SIM_PYTHON naming that interpreter.
narrate-sim-model:
    python3 scripts/model_prefetch.py speechbrain-spkrec-ecapa-voxceleb-embedding
