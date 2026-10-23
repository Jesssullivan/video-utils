#!/usr/bin/env bash
# The qwentts.cpp engine: its tts-server on loopback with the pinned Qwen3-TTS 1.7B Base GGUF
# (docs/spec/NARRATE.md, "Engine profiles" and "Host placement and memory"; receipts
# docs/agent-notes/2026-10-23-e2-cpu-engine.md and 2026-10-23-e2-review-fixes.md).
#
#   qwentts.sh build   clone qwentts.cpp at the commit pinned in narrate/bench/sources.json, apply the local
#                      patches (qwentts-threads.patch: a GGML CPU thread bound; qwentts-loopback.patch: no CORS,
#                      browser origins and non-loopback Host headers refused) and build tts-server, qwen-tts and
#                      qwen-codec for the device's backend, both cmake steps through narrate/bounded.sh. Rebuilds
#                      only when the commit, a patch or the backend changes; the stamp records the server's sha256.
#   qwentts.sh serve   hash the pinned weights, check the build is current and its tts-server matches the stamp's
#                      sha256 (serve never builds), then run tts-server on 127.0.0.1 through narrate/bounded.sh
#                      (nice 19, idle I/O, a MemoryMax scope where user systemd works).
#
# Both commands run only on a host the placement rule allows (the GPU host for its window, the Mac build host):
# the private allow file ${XDG_CONFIG_HOME:-~/.config}/narrate/tts-host must be the user's own, writable by no one
# else, and hold this host's machine id (/etc/machine-id, or IOPlatformUUID on macOS). No environment variable
# opens the gate, and no host name is in git. `serve` takes a GPU or Metal device only; CPU is a build target.
#   NARRATE_QWENTTS_DEVICE    required: Vulkan0 (GPU host), MTL0 (Mac build host); CPU for build only
#   NARRATE_WEIGHTS_DIR       required for serve: the private `just narrate-fetch --apply` destination
#   NARRATE_QWENTTS_BUILD     build tree, the user's own with mode 0700 (default ~/narrate-work/qwentts)
#   NARRATE_QWENTTS_THREADS   GGML CPU threads, 1 to 8 (default 4)
#   NARRATE_QWENTTS_JOBS      compile jobs, 1 to 8 (default 4)
#   NARRATE_QWENTTS_BUILD_MEMORY_MAX  the build steps' MemoryMax (default 8G)
#   NARRATE_QWENTTS_MEMORY_MAX  the server scope's MemoryMax (default 14G)
#   NARRATE_QWENTTS_CPUS      optional taskset CPU list for the server (Linux)
#   NARRATE_QWENTTS_PORT      loopback port (default 18089)
#   NARRATE_QWENTTS_LANG      language label for requests that send none (default English)
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/../.." && pwd)"
# Tests that source this file point these at fixtures; nothing in the environment changes them.
sources="$root/narrate/bench/sources.json"
host_root=/
patches=("$here/qwentts-threads.patch" "$here/qwentts-loopback.patch")
source_id="qwentts.cpp"
weights_id="qwen3-tts-1.7b-base-qwentts"
talker="qwen-talker-1.7b-base-BF16.gguf"
codec="qwen-tokenizer-12hz-F32.gguf"
max_threads=8

die() { echo "qwentts: $*" >&2; exit 2; }

device="${NARRATE_QWENTTS_DEVICE:-}"
build_dir="${NARRATE_QWENTTS_BUILD:-$HOME/narrate-work/qwentts}"
allow_file="${XDG_CONFIG_HOME:-$HOME/.config}/narrate/tts-host"
threads="${NARRATE_QWENTTS_THREADS:-4}"
jobs="${NARRATE_QWENTTS_JOBS:-4}"
port="${NARRATE_QWENTTS_PORT:-18089}"
lang="${NARRATE_QWENTTS_LANG:-English}"
memory_max="${NARRATE_QWENTTS_MEMORY_MAX:-14G}"
build_memory_max="${NARRATE_QWENTTS_BUILD_MEMORY_MAX:-8G}"
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
        "") die "set NARRATE_QWENTTS_DEVICE to Vulkan0 (GPU host) or MTL0 (Mac build host)" ;;
        *) die "NARRATE_QWENTTS_DEVICE must be Vulkan0..9, MTL0..9 or CPU, not $device" ;;
    esac
}

machine_id() {  # this host's machine id, or nothing
    if [[ -r "$host_root/etc/machine-id" ]]; then
        tr -d '[:space:]' < "$host_root/etc/machine-id"
    elif [[ "$host_root" == / ]] && command -v ioreg >/dev/null 2>&1; then
        ioreg -rd1 -c IOPlatformExpertDevice | awk -F'"' '/"IOPlatformUUID"/ { print $4 }'
    fi
}

host_gate() {  # refuse unless the private allow file names this host
    local why="TTS runs only on a host the placement rule allows (docs/spec/NARRATE.md, \"Host placement and memory\")"
    local id
    id="$(machine_id)"
    [[ "$id" =~ ^[0-9A-Fa-f-]{16,64}$ ]] || die "refused: cannot read this host's machine id; $why"
    [[ -f "$allow_file" && ! -L "$allow_file" ]] || die "refused: no allow file for this host; $why"
    [[ -O "$allow_file" ]] || die "refused: the allow file is not this user's own"
    python3 -I -c 'import os, sys; sys.exit(os.stat(sys.argv[1]).st_mode & 0o022 != 0)' "$allow_file" \
        || die "refused: the allow file is writable by another user"
    tr -d ' \t\r' < "$allow_file" | grep -qxiF -- "$id" || die "refused: the allow file does not name this host; $why"
}

pin() {  # the pinned url and commit of the runtime
    python3 -I -c 'import json,sys
d={s["id"]:s for s in json.load(open(sys.argv[1]))["sources"]}[sys.argv[2]]
print(d["url"], d["commit"])' "$sources" "$source_id"
}

digest() {  # sha256 of a file, streamed, on Linux and macOS alike
    python3 -I -c 'import hashlib, sys
h = hashlib.sha256()
with open(sys.argv[1], "rb") as f:
    for block in iter(lambda: f.read(1 << 20), b""):
        h.update(block)
print(h.hexdigest())' "$1"
}

build_paths() {  # sets src, out, cmake_flags and stamp_want for the device
    local flags suffix patch sums=""
    flags="$(backend_flags)"
    suffix="${flags%% *}"
    read -r -a cmake_flags <<< "${flags#* }"
    read -r url commit < <(pin)
    for patch in "${patches[@]}"; do sums+=" $(digest "$patch")"; done
    src="$build_dir/qwentts.cpp"
    out="$src/build-$suffix"
    stamp_want="$commit$sums ${cmake_flags[*]}"
}

build_current() {  # the build matches the pin, the patches and the backend, and tts-server matches its stamp
    [[ -x "$out/tts-server" && -f "$out/narrate-stamp" ]] || return 1
    local first second
    { read -r first; read -r second; } < "$out/narrate-stamp" || return 1
    [[ "$first" == "$stamp_want" && "$second" == "$(digest "$out/tts-server")" ]]
}

own_dir() {  # create or accept a directory only when it is this user's and closed to others
    [[ -e "$1" ]] || { mkdir -p "$(dirname "$1")" && mkdir -m 700 "$1"; }
    [[ -d "$1" && ! -L "$1" && -O "$1" ]] || die "$1 must be a directory of this user's own"
    python3 -I -c 'import os, sys; sys.exit(os.stat(sys.argv[1]).st_mode & 0o077 != 0)' "$1" \
        || die "$1 must have mode 0700"
}

cmake_run() {
    local -a tool=(cmake)
    command -v cmake >/dev/null || tool=(nix shell --inputs-from "$root" nixpkgs#cmake -c cmake)
    NARRATE_MEMORY_MAX="$build_memory_max" "$root/narrate/bounded.sh" "${tool[@]}" "$@"
}

build() {
    host_gate
    build_paths
    if build_current; then
        echo "qwentts: ${out##*/} build is current ($stamp_want)" >&2
        return
    fi
    own_dir "$build_dir"
    # No hooks run from the checkout, and only the pinned origin is ever fetched from.
    local -a git=(git -c core.hooksPath=/dev/null -c protocol.file.allow=never)
    [[ -d "$src/.git" ]] || "${git[@]}" clone --quiet --no-checkout "$url" "$src"
    [[ "$("${git[@]}" -C "$src" remote get-url origin)" == "$url" ]] \
        || die "$src: origin is not the pinned $url; remove the checkout"
    "${git[@]}" -C "$src" fetch --quiet origin "$commit" 2>/dev/null || true
    "${git[@]}" -C "$src" checkout --quiet --force "$commit"
    [[ "$("${git[@]}" -C "$src" rev-parse HEAD)" == "$commit" ]] || die "$src: HEAD is not the pinned $commit"
    "${git[@]}" -C "$src" submodule update --init --recursive --quiet
    "${git[@]}" -C "$src" checkout --quiet -- .
    "${git[@]}" -C "$src" apply "${patches[@]}"
    cmake_run -S "$src" -B "$out" -DCMAKE_BUILD_TYPE=Release "${cmake_flags[@]}" >&2
    cmake_run --build "$out" --config Release -j "$jobs" --target tts-server qwen-tts qwen-codec >&2
    printf '%s\n%s\n' "$stamp_want" "$(digest "$out/tts-server")" > "$out/narrate-stamp"
}

check_weights() {  # hash each pinned file and hold it to the pin and to the fetch receipt
    local dir="$1"
    nice -n 19 python3 -I - "$sources" "$weights_id" "$dir" "$talker" "$codec" <<'PY'
import hashlib, json, os, sys
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
    if not os.path.isfile(path) or os.path.getsize(path) != pinned["bytes"]:
        sys.exit(f"qwentts: {name}: missing or not the pinned size; run just narrate-fetch --apply")
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 22), b""):
            h.update(block)
    if h.hexdigest() != pinned["sha256"]:
        sys.exit(f"qwentts: {name}: sha256 differs from the pin; remove it and run just narrate-fetch --apply")
    if sums.get(name) != pinned["sha256"]:
        sys.exit(f"qwentts: {name}: the fetch receipt's sha256 differs from the pin")
PY
}

serve() {
    host_gate
    backend_flags >/dev/null
    [[ "$device" != CPU ]] || die "refused: serve takes Vulkan0..9 or MTL0..9; CPU is a build target only"
    [[ -n "${NARRATE_WEIGHTS_DIR:-}" ]] || die "set NARRATE_WEIGHTS_DIR to the private just narrate-fetch --apply destination"
    local weights="$NARRATE_WEIGHTS_DIR/hf/$weights_id"
    check_weights "$weights"
    build_paths
    build_current || die "the $device build is missing, stale or not the stamped binary; run just narrate-build-qwentts first"
    local -a pin_cpus=()
    [[ -z "${NARRATE_QWENTTS_CPUS:-}" ]] || pin_cpus=(taskset -c "$NARRATE_QWENTTS_CPUS")
    export QWENTTS_CPU_THREADS="$threads" OMP_NUM_THREADS="$threads" NARRATE_MEMORY_MAX="$memory_max"
    echo "qwentts: 127.0.0.1:$port, device $device, $threads CPU threads, MemoryMax $memory_max, model $weights_id" >&2
    exec "$root/narrate/bounded.sh" --no-lock ${pin_cpus[@]+"${pin_cpus[@]}"} "$out/tts-server" \
        --model "$weights/$talker" --codec "$weights/$codec" --device "$device" --alias "$weights_id" \
        --host 127.0.0.1 --port "$port" --lang "$lang"
}

main() {
    case "${1:-}" in
        build) build ;;
        serve) serve ;;
        *) die "usage: qwentts.sh build|serve" ;;
    esac
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
