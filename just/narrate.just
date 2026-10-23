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

# The qwentts.cpp engine (backend QwenTtsCpp): its tts-server on 127.0.0.1 (default port 18089) with the pinned
# Qwen3-TTS 1.7B Base GGUF from NARRATE_WEIGHTS_DIR (`just narrate-fetch --only qwen3-tts-1.7b-base-qwentts
# --apply`), built for NARRATE_QWENTTS_DEVICE (Vulkan0, MTL0 or CPU) in $TMPDIR when needed. It runs only on a
# host the placement rule allows (the GPU host in its window, the Mac build host): the host's private start script
# sets NARRATE_TTS_HOST_ALLOWED=1, and serve refuses without it. Knobs: narrate/serve/qwentts.sh.
# Start the qwentts.cpp engine on loopback, in the foreground (allowed hosts only).
narrate-serve-qwentts:
    narrate/serve/qwentts.sh serve

# Build the qwentts.cpp engine for NARRATE_QWENTTS_DEVICE without starting it.
narrate-build-qwentts:
    narrate/serve/qwentts.sh build

# The engine bench. Lane W3 (TIN-7085) owns it; `just narrate-fetch` prints the pinned download plan.
narrate-bench *args:
    @echo "narrate-bench: not implemented yet; lane W3 (TIN-7085) fills this recipe. See just narrate-fetch." >&2
    @exit 2

# Lint and format check.
narrate-lint:
    cd narrate && ruff check . && ruff format --check .

# The synthetic-fixture tests: the fake engine and FFmpeg make every take. No voice, model or network.
narrate-test:
    cd narrate && python3 -m pytest -q
