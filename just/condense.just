# Talk condensing (docs/spec/CONDENSE.md). Run inside `nix develop .#condense`.
# Root imports this file from the root justfile (`import 'just/condense.just'`).
# Every stage reads one talk.toml; recordings, transcripts and renders stay out of Git.
# Bounded defaults: 2 parts or whisper chunks at once, 4 whisper threads, and a 7200 s limit per tool
# call (CONDENSE_TOOL_TIMEOUT_S). Raise `[encode] jobs` and `[whisper] threads` in talk.toml on a larger host.

export WHISPER_MODEL := env("WHISPER_MODEL", justfile_directory() / "models/ggerganov-whisper-cpp-ggml-small.en.bin")

# Fetch the registered, hash-bound whisper model (465 MiB) into models/.
condense-model:
    python3 scripts/model_prefetch.py ggerganov-whisper-cpp-ggml-small.en

# Rebuild a truncated .mov from a long healthy recording made by the same device and app.
condense-recover ref broken fixed:
    python3 -m condense recover {{quote(ref)}} {{quote(broken)}} {{quote(fixed)}}

# 16 kHz audio, then two whisper passes per chunk: a beam pass and a DTW pass for word times.
condense-transcribe config="talk.toml":
    python3 -m condense transcribe {{quote(config)}}

# Silences, RMS, words, fillers, pauses and unworded bursts.
condense-events config="talk.toml":
    python3 -m condense events {{quote(config)}}

# The edit decision list: one speed for every span of every clip, validated by `video-utils timeline`.
condense-edl config="talk.toml": cli
    python3 -m condense edl {{quote(config)}}

# Mezzanines, part renders, the join, two-pass loudness and the final encode.
condense-render config="talk.toml":
    python3 -m condense render {{quote(config)}}

# Silence gate, loudness, A/V sync and whisper re-reads at the joins.
condense-check config="talk.toml" *names:
    python3 -m condense check {{quote(config)}} {{names}}

# SRT and WebVTT on the output clock.
condense-captions config="talk.toml":
    python3 -m condense captions {{quote(config)}}

# Burn the correction notes into a second file. The audio is copied.
condense-overlay config="talk.toml":
    python3 -m condense overlay {{quote(config)}}

# Every stage in order.
condense-all config="talk.toml": (condense-transcribe config) (condense-events config) (condense-edl config) (condense-render config) (condense-check config) (condense-captions config) (condense-overlay config)

# Lint and format check.
condense-lint:
    cd condense && ruff check . && ruff format --check .

# The synthetic-media tests: FFmpeg makes every input, no model and no recording.
condense-test: cli
    cd condense && python3 -m pytest -q
