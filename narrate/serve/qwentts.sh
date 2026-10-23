#!/usr/bin/env bash
# The qwentts.cpp engine: its tts-server on loopback with the pinned Qwen3-TTS 1.7B Base GGUF
# (docs/spec/NARRATE.md, "Engine profiles" and "Host placement and memory"; receipt
# docs/agent-notes/2026-10-23-e2-cpu-engine.md).
#
#   qwentts.sh build   clone qwentts.cpp at the commit pinned in narrate/bench/sources.json, apply
#                      qwentts-threads.patch and build tts-server, qwen-tts and qwen-codec for the device's
#                      backend. Rebuilds only when the commit, the patch or the backend changes.
#   qwentts.sh serve   build if needed, check the pinned weights, then run tts-server on 127.0.0.1 through
#                      narrate/bounded.sh (nice 19, idle I/O, a MemoryMax scope where user systemd works).
#
# Synthesis runs only where the host placement rule allows it: the GPU host (in its window) or the Mac build
# host. `serve` refuses unless NARRATE_TTS_HOST_ALLOWED=1, which only that host's private start script sets.
# Every host path comes from the environment; nothing private is in this file.
#   NARRATE_TTS_HOST_ALLOWED  1 on a host the placement rule allows; serve refuses otherwise
#   NARRATE_QWENTTS_DEVICE    required: Vulkan0 (GPU host), MTL0 (Mac build host) or CPU; the build follows it
#   NARRATE_WEIGHTS_DIR       required for serve: the private `just narrate-fetch --apply` destination
#   NARRATE_QWENTTS_BUILD     build tree (default $TMPDIR/narrate-qwentts); the checkout is <build>/qwentts.cpp
#   NARRATE_QWENTTS_THREADS   GGML CPU threads, 1 to 8 (default 4)
#   NARRATE_QWENTTS_JOBS      compile jobs, 1 to 8 (default 4)
#   NARRATE_QWENTTS_MEMORY_MAX  the server scope's MemoryMax (default 14G)
#   NARRATE_QWENTTS_CPUS      optional taskset CPU list for the server (Linux)
#   NARRATE_QWENTTS_PORT      loopback port (default 18089)
#   NARRATE_QWENTTS_LANG      language label for requests that send none (default English)
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/../.." && pwd)"
sources="$root/narrate/bench/sources.json"
patch="$here/qwentts-threads.patch"
source_id="qwentts.cpp"
weights_id="qwen3-tts-1.7b-base-qwentts"
talker="qwen-talker-1.7b-base-BF16.gguf"
codec="qwen-tokenizer-12hz-F32.gguf"
max_threads=8

die() { echo "qwentts: $*" >&2; exit 2; }

device="${NARRATE_QWENTTS_DEVICE:-}"
build_dir="${NARRATE_QWENTTS_BUILD:-${TMPDIR:-/tmp}/narrate-qwentts}"
threads="${NARRATE_QWENTTS_THREADS:-4}"
jobs="${NARRATE_QWENTTS_JOBS:-4}"
port="${NARRATE_QWENTTS_PORT:-18089}"
lang="${NARRATE_QWENTTS_LANG:-English}"
memory_max="${NARRATE_QWENTTS_MEMORY_MAX:-14G}"
bounded() {  # bounded VALUE MAX: a whole number from 1 to MAX
    [[ "$1" =~ ^[1-9][0-9]{0,5}$ ]] && (( $1 <= $2 ))
}
if ! bounded "$threads" "$max_threads"; then die "NARRATE_QWENTTS_THREADS must be 1 to $max_threads"; fi
if ! bounded "$jobs" 8; then die "NARRATE_QWENTTS_JOBS must be 1 to 8"; fi
if ! bounded "$port" 65535; then die "NARRATE_QWENTTS_PORT must be a port number"; fi

backend_flags() {  # cmake flags and the build directory suffix for the device
    case "$device" in
        Vulkan[0-9]) echo "vulkan -DGGML_VULKAN=ON -DGGML_METAL=OFF -DGGML_CUDA=OFF" ;;
        MTL[0-9]) echo "metal -DGGML_METAL=ON -DGGML_VULKAN=OFF -DGGML_CUDA=OFF" ;;
        CPU) echo "cpu -DGGML_NATIVE=ON -DGGML_VULKAN=OFF -DGGML_METAL=OFF -DGGML_CUDA=OFF -DGGML_BLAS=OFF" ;;
        "") die "set NARRATE_QWENTTS_DEVICE to Vulkan0 (GPU host), MTL0 (Mac build host) or CPU" ;;
        *) die "NARRATE_QWENTTS_DEVICE must be Vulkan0..9, MTL0..9 or CPU, not $device" ;;
    esac
}

pin() {  # the pinned url and commit of the runtime
    python3 -I -c 'import json,sys
d={s["id"]:s for s in json.load(open(sys.argv[1]))["sources"]}[sys.argv[2]]
print(d["url"], d["commit"])' "$sources" "$source_id"
}

digest() {  # sha256 of a file, on Linux and macOS alike
    python3 -I -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$1"
}

cmake_run() {
    if command -v cmake >/dev/null; then
        nice -n 10 cmake "$@"
    else
        nice -n 10 nix shell --inputs-from "$root" nixpkgs#cmake -c cmake "$@"
    fi
}

build() {
    local flags suffix url commit
    flags="$(backend_flags)"
    suffix="${flags%% *}"
    read -r -a cmake_flags <<< "${flags#* }"
    read -r url commit < <(pin)
    local src="$build_dir/qwentts.cpp"
    out="$src/build-$suffix"
    local stamp_want
    stamp_want="$commit $(digest "$patch") ${cmake_flags[*]}"
    if [[ -x "$out/tts-server" && -f "$out/narrate-stamp" && "$(cat "$out/narrate-stamp")" == "$stamp_want" ]]; then
        echo "qwentts: $suffix build is current ($commit)" >&2
        return
    fi
    mkdir -p "$build_dir"
    [[ -d "$src/.git" ]] || git clone --quiet "$url" "$src"
    git -C "$src" fetch --quiet origin "$commit" 2>/dev/null || true
    git -C "$src" checkout --quiet --force "$commit"
    git -C "$src" submodule update --init --recursive --quiet
    git -C "$src" checkout --quiet -- src/backend.h
    git -C "$src" apply "$patch"
    cmake_run -S "$src" -B "$out" -DCMAKE_BUILD_TYPE=Release "${cmake_flags[@]}" >&2
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
        sys.exit(f"qwentts: {name}: size differs from the pin; run just narrate-fetch --apply")
    if sums.get(name) != pinned["sha256"]:
        sys.exit(f"qwentts: {name}: the fetch receipt's sha256 differs from the pin")
PY
}

serve() {
    [[ "${NARRATE_TTS_HOST_ALLOWED:-}" == 1 ]] || die "refused: TTS synthesis runs only on the GPU host or the Mac \
build host (docs/spec/NARRATE.md, \"Host placement and memory\"); that host's private start script sets \
NARRATE_TTS_HOST_ALLOWED=1"
    backend_flags >/dev/null
    [[ -n "${NARRATE_WEIGHTS_DIR:-}" ]] || die "set NARRATE_WEIGHTS_DIR to the private just narrate-fetch --apply destination"
    local weights="$NARRATE_WEIGHTS_DIR/hf/$weights_id"
    check_weights "$weights"
    build
    local -a pin_cpus=()
    [[ -z "${NARRATE_QWENTTS_CPUS:-}" ]] || pin_cpus=(taskset -c "$NARRATE_QWENTTS_CPUS")
    export QWENTTS_CPU_THREADS="$threads" OMP_NUM_THREADS="$threads" NARRATE_MEMORY_MAX="$memory_max"
    echo "qwentts: 127.0.0.1:$port, device $device, $threads CPU threads, MemoryMax $memory_max, model $weights_id" >&2
    exec "$root/narrate/bounded.sh" ${pin_cpus[@]+"${pin_cpus[@]}"} "$out/tts-server" --model "$weights/$talker" \
        --codec "$weights/$codec" --device "$device" --alias "$weights_id" --host 127.0.0.1 --port "$port" \
        --lang "$lang"
}

case "${1:-}" in
    build) build ;;
    serve) serve ;;
    *) die "usage: qwentts.sh build|serve" ;;
esac
