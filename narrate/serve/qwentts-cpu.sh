#!/usr/bin/env bash
# The narrate CPU engine: qwentts.cpp tts-server, CPU only, on loopback (docs/spec/NARRATE.md, "Engine
# profiles"; receipt docs/agent-notes/2026-10-23-e2-cpu-engine.md).
#
#   qwentts-cpu.sh build   clone qwentts.cpp at the commit pinned in narrate/bench/sources.json, apply
#                          qwentts-cpu-threads.patch and build tts-server, qwen-tts and qwen-codec (CPU, native
#                          SIMD, no BLAS). Rebuilds only when the commit or the patch changes.
#   qwentts-cpu.sh serve   build if needed, check the pinned weights, then exec tts-server on 127.0.0.1.
#
# Every host path comes from the environment; nothing private is in this file.
#   NARRATE_WEIGHTS_DIR      required for serve: the private `just narrate-fetch --apply` destination
#   NARRATE_QWENTTS_BUILD    build tree (default $TMPDIR/narrate-qwentts); the checkout is <build>/qwentts.cpp
#   NARRATE_QWENTTS_THREADS  GGML CPU threads, 1 to 8 (default 8)
#   NARRATE_QWENTTS_JOBS     compile jobs (default 8)
#   NARRATE_QWENTTS_CPUS     optional taskset CPU list for the server, e.g. one NUMA node's cores
#   NARRATE_QWENTTS_PORT     loopback port (default 18089)
#   NARRATE_QWENTTS_LANG     default language label for requests that send none (default English)
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/../.." && pwd)"
sources="$root/narrate/bench/sources.json"
patch="$here/qwentts-cpu-threads.patch"
source_id="qwentts.cpp"
weights_id="qwen3-tts-1.7b-base-qwentts"
talker="qwen-talker-1.7b-base-BF16.gguf"
codec="qwen-tokenizer-12hz-F32.gguf"
max_threads=8

die() { echo "qwentts-cpu: $*" >&2; exit 2; }

build_dir="${NARRATE_QWENTTS_BUILD:-${TMPDIR:-/tmp}/narrate-qwentts}"
threads="${NARRATE_QWENTTS_THREADS:-$max_threads}"
jobs="${NARRATE_QWENTTS_JOBS:-8}"
port="${NARRATE_QWENTTS_PORT:-18089}"
lang="${NARRATE_QWENTTS_LANG:-English}"
bounded() {  # bounded VALUE MAX: a whole number from 1 to MAX
    [[ "$1" =~ ^[1-9][0-9]{0,5}$ ]] && (( $1 <= $2 ))
}
if ! bounded "$threads" "$max_threads"; then die "NARRATE_QWENTTS_THREADS must be 1 to $max_threads"; fi
if ! bounded "$jobs" 8; then die "NARRATE_QWENTTS_JOBS must be 1 to 8"; fi
if ! bounded "$port" 65535; then die "NARRATE_QWENTTS_PORT must be a port number"; fi

pin() {  # the pinned url and commit of the runtime
    python3 -I -c 'import json,sys
d={s["id"]:s for s in json.load(open(sys.argv[1]))["sources"]}[sys.argv[2]]
print(d["url"], d["commit"])' "$sources" "$source_id"
}

cmake_run() {
    if command -v cmake >/dev/null; then
        nice -n 10 cmake "$@"
    else
        nice -n 10 nix shell --inputs-from "$root" nixpkgs#cmake -c cmake "$@"
    fi
}

build() {
    read -r url commit < <(pin)
    local src="$build_dir/qwentts.cpp" out="$build_dir/qwentts.cpp/build-cpu"
    local stamp_want
    stamp_want="$commit $(sha256sum "$patch" | cut -d' ' -f1)"
    if [[ -x "$out/tts-server" && -f "$out/narrate-stamp" && "$(cat "$out/narrate-stamp")" == "$stamp_want" ]]; then
        echo "qwentts-cpu: build is current ($commit)" >&2
        return
    fi
    mkdir -p "$build_dir"
    [[ -d "$src/.git" ]] || git clone --quiet "$url" "$src"
    git -C "$src" fetch --quiet origin "$commit" 2>/dev/null || true
    git -C "$src" checkout --quiet --force "$commit"
    git -C "$src" submodule update --init --recursive --quiet
    git -C "$src" checkout --quiet -- src/backend.h
    git -C "$src" apply "$patch"
    cmake_run -S "$src" -B "$out" -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=ON -DGGML_CUDA=OFF -DGGML_VULKAN=OFF \
        -DGGML_METAL=OFF -DGGML_BLAS=OFF >&2
    cmake_run --build "$out" --config Release -j "$jobs" --target tts-server qwen-tts qwen-codec >&2
    echo "$stamp_want" > "$out/narrate-stamp"
}

check_weights() {  # sizes on disk and the fetch receipt's sums against the pinned sources
    local dir="$1"
    python3 -I - "$sources" "$weights_id" "$dir" "$talker" "$codec" <<'PY'
import json, os, sys
sources, sid, d, *names = sys.argv[1:]
src = {s["id"]: s for s in json.load(open(sources))["sources"]}[sid]
files = {f["path"]: f for f in src["files"]}
sums = {}
with open(os.path.join(d, "SHA256SUMS")) as f:
    for line in f:
        digest, _, name = line.strip().partition("  ")
        sums[name] = digest
for name in names:
    path, pinned = os.path.join(d, name), files[name]
    if os.path.getsize(path) != pinned["bytes"]:
        sys.exit(f"qwentts-cpu: {name}: size differs from the pin; run just narrate-fetch --apply")
    if sums.get(name) != pinned["sha256"]:
        sys.exit(f"qwentts-cpu: {name}: the fetch receipt's sha256 differs from the pin")
PY
}

serve() {
    [[ -n "${NARRATE_WEIGHTS_DIR:-}" ]] || die "set NARRATE_WEIGHTS_DIR to the private just narrate-fetch --apply destination"
    local weights="$NARRATE_WEIGHTS_DIR/hf/$weights_id"
    check_weights "$weights"
    build
    local server="$build_dir/qwentts.cpp/build-cpu/tts-server"
    local -a pin_cpus=()
    [[ -z "${NARRATE_QWENTTS_CPUS:-}" ]] || pin_cpus=(taskset -c "$NARRATE_QWENTTS_CPUS")
    export QWENTTS_CPU_THREADS="$threads" OMP_NUM_THREADS="$threads"
    echo "qwentts-cpu: 127.0.0.1:$port, $threads threads, model $weights_id" >&2
    exec "${pin_cpus[@]}" "$server" --model "$weights/$talker" --codec "$weights/$codec" --device CPU \
        --alias "$weights_id" --host 127.0.0.1 --port "$port" --lang "$lang"
}

case "${1:-}" in
    build) build ;;
    serve) serve ;;
    *) die "usage: qwentts-cpu.sh build|serve" ;;
esac
