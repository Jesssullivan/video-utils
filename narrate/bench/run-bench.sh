#!/usr/bin/env bash
# The narrate bench window on the GPU host: run-bench.sh HOLDER [VOICE]
#
# Copied to the bench directory on the GPU host (beside job/ with host_run.py, host-job.json and chunks-v1.json)
# and started by the lease holder's helper once the Lease is held:
#   cd <bench dir> && NARRATE_BENCH_EXPECT_RUN_BENCH=<sha256> NARRATE_BENCH_EXPECT_HOST_RUN=<sha256> \
#     NARRATE_BENCH_EXPECT_JOB=<sha256> exec nice -n 19 timeout -k 15 1800 ./run-bench.sh <holder> <voice>
# It takes no Lease and opens no device node. Plan: docs/agent-notes/2026-10-22-narrate-bench-plan.md (window 2:
# its addendum of 2026-10-26).
#
# VOICE is the window's one cloning voice, a voice id of the private voices file; it replaces bench.env's
# NARRATE_BENCH_VOICE for this window, so each window names its voice on its own command line (window 2: one voice
# per window, a new holder each). Without VOICE, bench.env's value is used; with neither, host_run refuses the job.
#
# Outer stage: refuses root, a missing or malformed holder, an existing runs/<holder>, a bench.env line that is
# not one of the allowed keys (bench.env is parsed, never sourced), and any runner file (this script,
# job/host_run.py, job/host-job.json) whose sha256 is not the caller's NARRATE_BENCH_EXPECT_* value. It then runs
# itself in `systemd-run --user --scope -p MemoryMax=14G -p MemorySwapMax=0 -p CPUQuota=200%
# -p RuntimeMaxSec=1680` under `nice -n 19 ionice -c3`. If the scope cannot be made, it writes a minimal receipt.
#
# Inner stage: checks that /proc/self/cgroup is that unit's scope and that memory.max, memory.swap.max and
# cpu.max hold the requested limits, records them, hashes every input (exit 2 on a mismatch), runs A2-gpu-alt,
# A1-gpu, A3-gpu, A2-gpu-alt-cut and A1-gpu-cut one at a time within 1500 s of its start (an arm not started
# by then is recorded not_started), stops the window on host_run's window-stop code or
# a signal (HUP, TERM, INT), kills anything left in its scope (also from an EXIT trap) and writes
# runs/<holder>/receipt.json.
#
# Every path out prints `NARRATE-BENCH-DONE rc=N`: 0 at least one arm completed seed 1 and no window stop;
# 10 no arm completed; 20 window stop; 2 refused.
#
# Preflight, before the Lease: `run-bench.sh --preflight [VOICE]` (same NARRATE_BENCH_EXPECT_* values) parses bench.env,
# checks the runner hashes and runs `host_run.py verify` for the window's arms: every input's sha256 and each arm's
# reference policy (an oversized or missing reference cut is refused here, not in the window). No engine, no scope
# and no runs/ directory. Its only write is its own hash cache, preflight-verified.json, never the window's
# inputs-verified.json, so the window's verify still hashes every input it has not hashed itself. It prints the
# verified records and `NARRATE-BENCH-PREFLIGHT rc=N` (0 green, 2 refused).
#
# Test mode: NARRATE_BENCH_TEST_MODE=1 from the caller's environment (never from bench.env) allows
# NARRATE_BENCH_NO_SCOPE, NARRATE_BENCH_ARMS, NARRATE_BENCH_ARMS_S, NARRATE_BENCH_HARD_S, NARRATE_BENCH_PYTHON and
# host_run.py's own test settings, and every receipt records it. Without it those variables are cleared.
set -uo pipefail
trap '' PIPE

BENCH_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SELF=$BENCH_DIR/$(basename "${BASH_SOURCE[0]}")
HARD_MAX_S=1680
ARMS_MAX_S=1500
MEMORY_MAX=14G
MEMORY_MAX_BYTES=15032385536
CPU_MAX="200000 100000"
DEFAULT_ARMS="A2-gpu-alt A1-gpu A3-gpu A2-gpu-alt-cut A1-gpu-cut"
NAME_RE='^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$'
TEST_VARS=(NARRATE_BENCH_NO_SCOPE NARRATE_BENCH_ARMS NARRATE_BENCH_ARMS_S NARRATE_BENCH_HARD_S NARRATE_BENCH_PYTHON
    NARRATE_BENCH_DRM_ROOT NARRATE_BENCH_FORBIDDEN_DEV)
ENV_KEYS=" NARRATE_BENCH_VOICE NARRATE_BENCH_VOICES_FILE NARRATE_BENCH_VOICES_SHA256 NARRATE_BENCH_QWEN_TTS"
ENV_KEYS+=" NARRATE_BENCH_QWEN_TTS_SHA256 NARRATE_BENCH_QWEN_DEVICE NARRATE_BENCH_AUDIOCPP_CLI"
ENV_KEYS+=" NARRATE_BENCH_AUDIOCPP_CLI_SHA256 NARRATE_BENCH_AUDIOCPP_DEVICE NARRATE_BENCH_VK_ICD "

if [ "${NARRATE_BENCH_TEST_MODE:-}" = 1 ]; then
    TEST_MODE=1
else
    TEST_MODE=0
    unset NARRATE_BENCH_TEST_MODE "${TEST_VARS[@]}"
fi
PY=python3
[ "$TEST_MODE" = 1 ] && PY=${NARRATE_BENCH_PYTHON:-python3}

done_line() {
    printf 'NARRATE-BENCH-DONE rc=%s\n' "$1" 2>/dev/null
}

refuse_early() {  # before runs/<holder> exists: nothing is written
    printf 'run-bench: refused: %s\n' "$*" >&2 2>/dev/null
    done_line 2
    exit 2
}

json_str() {  # a JSON string of $1 (holder and messages are plain ASCII by construction)
    local s=${1//\\/\\\\}
    printf '"%s"' "${s//\"/\\\"}"
}

minimal_receipt() {  # $1 dir, $2 stop, $3 exit code, $4 detail
    printf '{"schema":"narrate-bench-window-receipt/1","holder":%s,"test_mode":%s,"stop":%s,"exit_code":%s,"detail":%s,"ended_utc":"%s"}\n' \
        "$(json_str "$holder")" "$([ "$TEST_MODE" = 1 ] && echo true || echo false)" "$(json_str "$2")" "$3" \
        "$(json_str "$4")" "$(date -u +%FT%TZ)" >"$1/receipt.json.tmp" && mv "$1/receipt.json.tmp" "$1/receipt.json"
}

runner_check() {  # prints runner.json content; returns 1 on a mismatch
    local name file var expected measured ok=0 parts=()
    for name in run-bench.sh:"$SELF":NARRATE_BENCH_EXPECT_RUN_BENCH \
        host_run.py:"$BENCH_DIR/job/host_run.py":NARRATE_BENCH_EXPECT_HOST_RUN \
        host-job.json:"$BENCH_DIR/job/host-job.json":NARRATE_BENCH_EXPECT_JOB; do
        IFS=: read -r label file var <<<"$name"
        expected=${!var:-}
        measured=$(sha256sum "$file" 2>/dev/null | cut -d' ' -f1)
        [ -n "$expected" ] && [ "$expected" = "$measured" ] || ok=1
        parts+=("$(printf '"%s":{"expected":%s,"measured":%s}' "$label" "$(json_str "$expected")" "$(json_str "$measured")")")
    done
    local IFS=,
    printf '{%s}\n' "${parts[*]}"
    return "$ok"
}

set_voice() {  # $1: the window's voice id from the command line, if any; it replaces bench.env's
    [ -n "${1:-}" ] || return 0
    [[ $1 =~ $NAME_RE ]] || { echo "voice must be letters, digits, '.', '_' or '-'"; return 1; }
    export NARRATE_BENCH_VOICE=$1
}

load_env() {  # bench.env: KEY=VALUE lines for the allowed keys only; never sourced
    local file=$BENCH_DIR/bench.env line key value n=0
    [ -f "$file" ] || return 0
    while IFS= read -r line || [ -n "$line" ]; do
        n=$((n + 1))
        [[ $line =~ ^[[:space:]]*(#.*)?$ ]] && continue
        if ! [[ $line =~ ^[[:space:]]*(export[[:space:]]+)?([A-Z0-9_]+)=(.*)$ ]]; then
            echo "bench.env line $n is not KEY=VALUE"
            return 1
        fi
        key=${BASH_REMATCH[2]}
        value=${BASH_REMATCH[3]}
        if [[ $ENV_KEYS != *" $key "* ]]; then
            echo "bench.env line $n sets $key, which is not an allowed key"
            return 1
        fi
        value=${value%\"}
        value=${value#\"}
        export "$key=$value"
    done <"$file"
}

if [ "${1:-}" = "--preflight" ] && [ -z "${NARRATE_BENCH_IN_SCOPE:-}" ]; then
    # ---- preflight: before the Lease; no engine, no scope, no runs/ directory; writes only its own cache ----
    preflight_refuse() {
        printf 'run-bench: preflight refused: %s\n' "$*" >&2 2>/dev/null
        printf 'NARRATE-BENCH-PREFLIGHT rc=2\n' 2>/dev/null
        exit 2
    }
    [ "$(id -u)" -ne 0 ] || preflight_refuse "never run as root"
    [ $# -le 2 ] || preflight_refuse "usage: run-bench.sh --preflight [VOICE]"
    why=$(load_env) || preflight_refuse "$why"
    load_env >/dev/null
    why=$(set_voice "${2:-}") || preflight_refuse "$why"
    set_voice "${2:-}"
    runner_check >/dev/null || preflight_refuse "a runner file's sha256 is not the caller's NARRATE_BENCH_EXPECT_* value"
    export NARRATE_BENCH_ROOT=$BENCH_DIR NARRATE_BENCH_JOB_DIR=$BENCH_DIR/job NARRATE_BENCH_WEIGHTS=$BENCH_DIR/weights/hf
    ARMS_TEXT=$DEFAULT_ARMS
    [ "$TEST_MODE" = 1 ] && ARMS_TEXT=${NARRATE_BENCH_ARMS:-$DEFAULT_ARMS}
    read -r -a ARMS <<<"$ARMS_TEXT"
    nice -n 19 ionice -c3 "$PY" "$BENCH_DIR/job/host_run.py" verify "$BENCH_DIR/job/host-job.json" \
        --cache "$BENCH_DIR/preflight-verified.json" "${ARMS[@]/#/--arm=}"
    rc=$?
    printf 'NARRATE-BENCH-PREFLIGHT rc=%s\n' "$rc" 2>/dev/null
    exit "$rc"
fi

if [ -z "${NARRATE_BENCH_IN_SCOPE:-}" ]; then
    # ---- outer stage ----
    holder=${1:-}
    [ "$(id -u)" -ne 0 ] || refuse_early "never run as root"
    [ $# -ge 1 ] && [ $# -le 2 ] ||
        refuse_early "usage: run-bench.sh HOLDER [VOICE] (the lease holder id, passed by the lease command)"
    [[ $holder =~ $NAME_RE ]] || refuse_early "holder must be letters, digits, '.', '_' or '-'"
    OUT=$BENCH_DIR/runs/$holder
    [ ! -e "$OUT" ] || refuse_early "runs/$holder already exists; every window gets a new holder"
    why=$(load_env) || refuse_early "$why"
    load_env >/dev/null
    why=$(set_voice "${2:-}") || refuse_early "$why"
    set_voice "${2:-}"
    runner_check >/dev/null || refuse_early "a runner file's sha256 is not the caller's NARRATE_BENCH_EXPECT_* value"
    hard=$HARD_MAX_S
    if [ "$TEST_MODE" = 1 ] && [ -n "${NARRATE_BENCH_HARD_S:-}" ] && [ "$NARRATE_BENCH_HARD_S" -lt "$hard" ]; then
        hard=$NARRATE_BENCH_HARD_S
    fi
    unit="narrate-bench-${holder//[^A-Za-z0-9-]/-}-$$"
    export NARRATE_BENCH_IN_SCOPE=1 NARRATE_BENCH_HOLDER=$holder NARRATE_BENCH_UNIT=$unit NARRATE_BENCH_TEST_MODE=$TEST_MODE
    export NARRATE_BENCH_ROOT=$BENCH_DIR NARRATE_BENCH_JOB_DIR=$BENCH_DIR/job NARRATE_BENCH_WEIGHTS=$BENCH_DIR/weights/hf
    trap 'outer_signal=1' HUP TERM INT  # the inner stage gets the same signal through the process group
    if [ "$TEST_MODE" = 1 ] && [ -n "${NARRATE_BENCH_NO_SCOPE:-}" ]; then
        nice -n 19 ionice -c3 "$SELF" "$holder"
        rc=$?
    else
        systemd-run --user --scope --quiet --collect --unit="$unit" \
            -p MemoryMax="$MEMORY_MAX" -p MemorySwapMax=0 -p CPUQuota=200% -p RuntimeMaxSec="$hard" \
            nice -n 19 ionice -c3 "$SELF" "$holder"
        rc=$?
    fi
    if [ ! -s "$OUT/receipt.json" ]; then
        mkdir -p "$OUT" 2>/dev/null
        minimal_receipt "$OUT" "scope_failed" 2 "the window scope did not start or ended without a receipt (exit $rc)"
        printf 'run-bench: the window scope did not start or ended without a receipt (exit %s)\n' "$rc" >&2 2>/dev/null
        done_line 2
        exit 2
    fi
    exit "$rc"
fi

# ---- inner stage (in the scope) ----
holder=$NARRATE_BENCH_HOLDER
[ "${1:-}" = "$holder" ] || refuse_early "inner stage holder mismatch"
OUT=$BENCH_DIR/runs/$holder
# shellcheck disable=SC2015  # either mkdir failing refuses
mkdir -p "$BENCH_DIR/runs" && mkdir "$OUT" 2>/dev/null || refuse_early "runs/$holder already exists"
JOB=$BENCH_DIR/job/host-job.json
HOST_RUN=$BENCH_DIR/job/host_run.py
CACHE=$BENCH_DIR/inputs-verified.json
ARMS_TEXT=$DEFAULT_ARMS
ARMS_S=$ARMS_MAX_S
if [ "$TEST_MODE" = 1 ]; then
    ARMS_TEXT=${NARRATE_BENCH_ARMS:-$DEFAULT_ARMS}
    if [ -n "${NARRATE_BENCH_ARMS_S:-}" ] && [ "$NARRATE_BENCH_ARMS_S" -lt "$ARMS_S" ]; then
        ARMS_S=$NARRATE_BENCH_ARMS_S
    fi
fi
read -r -a ARMS <<<"$ARMS_TEXT"
START=$(date +%s)
DEADLINE=$((START + ARMS_S))
stop=""
results=()
child=""
CGROUP_PROCS=""
log() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$*" >>"$OUT/window.log"; printf '%s %s\n' "$(date -u +%FT%TZ)" "$*" >&2 2>/dev/null; }

sweep() {  # kill anything but this shell left in the scope; records the pids
    [ -n "$CGROUP_PROCS" ] && [ -r "$CGROUP_PROCS" ] || return 0
    local pid left=()
    while read -r pid; do
        [ "$pid" = "$$" ] || left+=("$pid")
    done <"$CGROUP_PROCS"
    if [ "${#left[@]}" -gt 0 ]; then
        kill -KILL "${left[@]}" 2>/dev/null
        printf '{"pids":[%s]}\n' "$(IFS=,; echo "${left[*]}")" >"$OUT/leftovers.json"
        log "killed processes left in the scope: ${left[*]}"
    fi
}
trap sweep EXIT

# shellcheck disable=SC2329  # a trap handler
on_signal() {
    stop=${stop:-terminated}
    log "signal: stopping the running step"
    [ -n "$child" ] && kill -TERM "$child" 2>/dev/null
}
trap on_signal HUP TERM INT

finish() {
    local rc=$1
    sweep
    "$PY" "$HOST_RUN" vram --json >"$OUT/vram-end.json" 2>/dev/null
    if ! "$PY" "$HOST_RUN" summarize --out "$OUT" --holder "$holder" --started "$START" --ended "$(date +%s)" \
        --stop "$stop" --exit "$rc" "${results[@]}"; then
        [ "$rc" = 0 ] && rc=2
        minimal_receipt "$OUT" "${stop:-summarize_failed}" "$rc" "host_run.py summarize failed"
    fi
    log "NARRATE-BENCH-DONE rc=$rc"
    done_line "$rc"
    exit "$rc"
}

run_step() {  # run a host_run step in the background so a signal reaches its trap; sets step_rc
    "$@" &
    child=$!
    wait "$child"
    step_rc=$?
    while kill -0 "$child" 2>/dev/null; do  # a trapped signal ended wait early; collect the step's own exit
        wait "$child"
        step_rc=$?
    done
    child=""
}

# The scope this stage runs in, and its limits, as measured.
if [ "$TEST_MODE" = 1 ] && [ -n "${NARRATE_BENCH_NO_SCOPE:-}" ]; then
    printf '{"test_mode_no_scope":true}\n' >"$OUT/scope.json"
else
    cg=$(sed -n 's/^0:://p' /proc/self/cgroup)
    mem=$(cat "/sys/fs/cgroup$cg/memory.max" 2>/dev/null)
    swap=$(cat "/sys/fs/cgroup$cg/memory.swap.max" 2>/dev/null)
    cpu=$(cat "/sys/fs/cgroup$cg/cpu.max" 2>/dev/null)
    printf '{"cgroup":%s,"unit":%s,"memory_max":%s,"memory_swap_max":%s,"cpu_max":%s}\n' "$(json_str "$cg")" \
        "$(json_str "$NARRATE_BENCH_UNIT.scope")" "$(json_str "$mem")" "$(json_str "$swap")" "$(json_str "$cpu")" \
        >"$OUT/scope.json"
    if [[ $cg != */"$NARRATE_BENCH_UNIT.scope" ]] || [ "$mem" != "$MEMORY_MAX_BYTES" ] || [ "$swap" != 0 ] ||
        [ "$cpu" != "$CPU_MAX" ]; then
        log "refused: not in the window scope with MemoryMax=14G, MemorySwapMax=0 and CPUQuota=200% (scope.json)"
        stop="scope_unverified"
        finish 2
    fi
    CGROUP_PROCS=/sys/fs/cgroup$cg/cgroup.procs  # swept only once it is proven to be this window's own scope
fi
if ! runner_check >"$OUT/runner.json"; then
    log "refused: a runner file's sha256 is not the caller's expected value (runner.json)"
    stop="runner_unverified"
    finish 2
fi

log "window start: holder $holder, voice ${NARRATE_BENCH_VOICE:-none}, arms ${ARMS[*]}, arms deadline +$ARMS_S s, test mode $TEST_MODE"
run_step "$PY" "$HOST_RUN" verify "$JOB" --cache "$CACHE" "${ARMS[@]/#/--arm=}" >"$OUT/inputs.json" 2>>"$OUT/window.log"
if [ -n "$stop" ]; then
    finish 20
elif [ "$step_rc" != 0 ]; then
    log "inputs are not green (see above): no arm runs"
    stop="inputs_refused"
    finish 2
fi
"$PY" "$HOST_RUN" vram --json >"$OUT/vram-start.json" 2>/dev/null || log "no VRAM reading before the window"

completed=0
refused=0
for arm in "${ARMS[@]}"; do
    [ -z "$stop" ] || break
    if [ "$(date +%s)" -ge "$DEADLINE" ]; then
        log "arms deadline reached: $arm not started"
        results+=("--arm-result=$arm=not_started")
        continue
    fi
    log "arm $arm: start"
    run_step "$PY" "$HOST_RUN" run "$JOB" --arm "$arm" --out "$OUT" --cache "$CACHE" --deadline "$DEADLINE" \
        2>>"$OUT/window.log"
    results+=("--arm-result=$arm=$step_rc")
    log "arm $arm: exit $step_rc"
    case $step_rc in
        0) completed=$((completed + 1)) ;;
        10) ;;
        2) stop=${stop:-"inputs_refused_in_$arm"}; refused=1 ;;
        20) stop=${stop:-"window_stop_from_$arm"} ;;
        *) stop=${stop:-"unexpected_exit_${step_rc}_from_$arm"} ;;
    esac
done

if [ "$refused" = 1 ] && [ "${stop#inputs_refused}" != "$stop" ]; then
    finish 2
elif [ -n "$stop" ]; then
    finish 20
elif [ "$completed" -gt 0 ]; then
    finish 0
else
    finish 10
fi
