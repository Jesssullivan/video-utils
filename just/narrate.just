# Narration (docs/spec/NARRATE.md). Run inside `nix develop .#condense`: FFmpeg, whisper-cpp, python3, ruff,
# shellcheck.
# Root imports this file from the root justfile (`import 'just/narrate.just'`).
# One narrate.toml names the job and its rendered Dhall records. Reference clips, transcripts, consent evidence
# and the pinned xoxd-lexical release live outside git: NARRATE_STORE and NARRATE_LEXICAL_DIR.
# Runs land in artifacts/narrate/<run_id>/, outside artifacts/runs/; no guitar tool reads them.

# Per-chunk whisper runs inside a render, so it runs through narrate/bounded.sh (one step at a time, 6G MemoryMax,
# nice 19, idle I/O, started only below the memory-pressure threshold).
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

# Copy a verified run's narration.wav to a consumer folder as <stem>.wav, never replacing a file.
narrate-export run_dir to stem:
    python3 -m narrate export {{quote(run_dir)}} --to {{quote(to)}} --stem {{quote(stem)}}

# An AudioCppBatch engine (docs/spec/NARRATE.md, "Out-of-process batch engines"): write the request batch for a
# GPU window into a new directory; no audio, no engine. Then narrate/serve/audiocpp_batch.py on the GPU host and
# `just narrate-render CONFIG --prerendered DIR`.
narrate-plan config out *args:
    python3 -m narrate plan {{quote(config)}} --out {{quote(out)}} {{args}}

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
# --apply`), hashed before every start. Both recipes run only on a host whose machine id is in the private allow
# file ~/.config/narrate/tts-host (the GPU host for its window, the Mac build host). Knobs: narrate/serve/qwentts.sh.
# Start the stamped qwentts.cpp build on loopback, in the foreground (Vulkan0 or MTL0; never builds).
narrate-serve-qwentts:
    narrate/serve/qwentts.sh serve

# Build the qwentts.cpp engine for NARRATE_QWENTTS_DEVICE, bounded, before any window opens.
narrate-build-qwentts:
    narrate/serve/qwentts.sh build

# The engine bench. Lane W3 (TIN-7085) owns it; `just narrate-fetch` prints the pinned download plan.
narrate-bench *args:
    @echo "narrate-bench: not implemented yet; lane W3 (TIN-7085) fills this recipe. See just narrate-fetch." >&2
    @exit 2

# J130 (TIN-7564), run on the host the run runs on. RUN is a run id from `just narrate-runs`, or latest. It sends the
# runner SIGTERM, waits for it and its engine to be gone (SIGKILL after --grace-s), waits for a local lease helper to
# exit, and writes a values-free receipt. ARGS: --reason operator (the default), preempted [--call-id ID] or
# finished; --holder H selects by Lease holder.
# Stop an unattended narrate GPU run by hand so a live call can have the Lease.
narrate-finalize run="latest" *args:
    python3 narrate/serve/finalize.py finalize {{quote(run)}} {{ if args =~ '--reason' { '' } else { '--reason operator' } }} {{args}}

# The form the GPU Lease guard admits for narrate (TIN-7564 ec74214b); the same as
# narrate-bench-$(date -u +%Y%m%d-s%H%M%S).
# Print a new Lease holder for a narrate GPU run starting now: narrate-bench-YYYYMMDD-sHHMMSS (UTC).
narrate-holder:
    @python3 narrate/serve/finalize.py holder

# The run records on this host: id, kind, Lease holder, state (live, ended or stale) and whether it is finalized.
narrate-runs:
    python3 narrate/serve/finalize.py list

# docs/spec/PRESENTATION.md. OUTPUT is a new absolute directory outside the source project. Planning checks
# digests and prepares argument vectors; no media, provider or assembly command runs.
# Plan a private character presentation from a typed manifest.
narrate-presentation-plan manifest output:
    python3 -m narrate.presentation {{quote(manifest)}} {{quote(output)}}

# Print only the text a render voices, through the input's adapter (lines, json with cue ids, or srt).
narrate-spoken input *args:
    python3 -m narrate spoken {{quote(input)}} {{args}}

# Front matter, [at] and [clip:] directions, comments and Sources lines never reach the checker (TIN-7097). The
# release is the one a render pins: NARRATE_LEXICAL_DIR, else `lexical` in narrate.toml. The check reads it through
# a XOXD_LEXICAL_HOME whose dist/ is that directory, runs the bin/xoxd-lexical beside it, else xoxd-lexical from
# PATH, and refuses a CLI whose `version` is not that release's. With no CLI, no check subcommand, no Vale or another
# release, it says so and exits 0: lexical checks are advisory (R-N12). Otherwise the exit is the CLI's: 0, 1 for an
# Error-severity finding, 2 for a tool fault. ARGS go to `narrate spoken`, such as --adapter Dialog.
# Check only the voiced text with `xoxd-lexical check --register narration`.
narrate-lexical-check input *args:
    #!/usr/bin/env bash
    set -euo pipefail
    say() { echo "narrate-lexical-check: $*" >&2; }
    work="$(mktemp -d)"
    trap 'rm -rf "$work"' EXIT
    tool="" want="" status=0
    python3 -m narrate.spoken lexical narrate.toml > "$work/pin" || status=$?
    if [ "$status" -eq 0 ]; then
        { read -r dist; read -r want; } < "$work/pin"
        if [ -z "$want" ]; then say "$dist has no estate-lexicon.json; not checked (advisory)"; exit 0; fi
        mkdir "$work/lexicon"
        ln -s "$dist" "$work/lexicon/dist"
        export XOXD_LEXICAL_HOME="$work/lexicon"
        beside="$(dirname "$dist")/bin/xoxd-lexical"
        if [ -x "$beside" ]; then tool="$beside"; fi
    elif [ "$status" -eq 3 ]; then
        say "no NARRATE_LEXICAL_DIR and no lexical in narrate.toml; the CLI's own release is used"
    else
        exit "$status"
    fi
    if [ -z "$tool" ] && command -v xoxd-lexical >/dev/null 2>&1; then tool="$(command -v xoxd-lexical)"; fi
    if [ -z "$tool" ]; then
        say "no xoxd-lexical CLI beside the release or on PATH; not checked (advisory)"
        exit 0
    fi
    if ! "$tool" check --help >/dev/null 2>&1; then
        say "$tool has no check subcommand (xoxd-lexical 0.4.0 added it); not checked (advisory)"
        exit 0
    fi
    got="$("$tool" version 2>/dev/null || true)"
    if [ -n "$want" ] && [ "$got" != "$want" ]; then
        say "$tool reads ${got:-an unknown release}, the pinned release is $want; not checked (advisory)"
        exit 0
    fi
    say "$got, register narration"
    python3 -m narrate spoken {{quote(input)}} {{args}} > "$work/spoken.txt"
    status=0
    "$tool" check --register narration - < "$work/spoken.txt" 2> "$work/err" || status=$?
    cat "$work/err" >&2
    if [ "$status" -eq 2 ] && grep -q "vale not found" "$work/err"; then
        say "Vale is not on PATH; not checked (advisory)"
        exit 0
    fi
    exit "$status"

# Lint and format check: ruff over narrate/ (bench included), shellcheck over the narrate shell scripts.
narrate-lint:
    cd narrate && ruff check . && ruff format --check . && shellcheck bench/run-bench.sh bounded.sh serve/qwentts.sh

# The synthetic-fixture tests: the fake engine and FFmpeg make every take. No voice, model or network.
narrate-test:
    cd narrate && python3 -m pytest -q

# Fetch the registered speaker-verification model (SIM) into models/, hash-checked against program/models.json.
# Scoring runs in `nix develop .#ml` (torch, speechbrain) or with NARRATE_SIM_PYTHON naming that interpreter.
narrate-sim-model:
    python3 scripts/model_prefetch.py speechbrain-spkrec-ecapa-voxceleb-embedding
