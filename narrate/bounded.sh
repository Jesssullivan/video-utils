#!/usr/bin/env bash
# Run one heavy narrate step bounded (docs/spec/NARRATE.md, "Host placement and memory"): wait for any other
# bounded step of this user on this host to finish, wait while the host's memory pressure is high, then run the
# command at nice 19 with the idle I/O class, inside a transient user scope with a memory ceiling when
# `systemd-run --user` works. Without a user systemd (macOS, a CI container) the command runs at nice 19 without a
# ceiling, and without flock it is not serialised; the script says so on stderr in both cases.
#
#   bounded.sh [--no-lock] <command> [args...]
#
#   --no-lock            do not take the one-at-a-time lock: for a long-lived server (the qwentts.cpp engine),
#                        which would otherwise hold every scoring step back for as long as it serves
#   NARRATE_MEMORY_MAX   the scope's MemoryMax (default 6G)
#   NARRATE_PSI_MAX      wait while "full avg10" of the pressure file is above this (default 10)
#   NARRATE_PSI_WAIT_S   stop waiting after this many seconds and exit 75 without running (default 600)
#   NARRATE_PSI_FILE     the pressure file (default /proc/pressure/memory; absent: no wait)
#   NARRATE_LOCK_WAIT_S  wait this long for the step holding the lock, then exit 75 without running (default 3600)
#   NARRATE_HEAVY_LOCK   the lock file (default $XDG_RUNTIME_DIR/narrate-heavy.lock, else
#                        ${TMPDIR:-/tmp}/narrate-heavy-<uid>.lock)
#
# Pressure is read before the step starts, not while it runs: the scope's MemoryMax is the bound during the run.
# The bounded command and its children see NARRATE_BOUNDED_PID, the step's own pid (systemd-run --scope, nice and
# ionice all exec, so it is the command's pid). A nested call that has that pid, or an ancestor with it, is inside the
# step's scope and lock, so it only re-applies nice and the idle I/O class. A pid that is not an ancestor (a
# variable leaked into an unrelated process) counts for nothing, and the call gets the full treatment.
set -euo pipefail

die() { echo "bounded: $*" >&2; exit 2; }
lock=1
if [[ "${1:-}" == --no-lock ]]; then
    lock=0
    shift
fi
[[ $# -gt 0 ]] || die "usage: bounded.sh [--no-lock] <command> [args...]"

lower=(nice -n 19)
if command -v ionice >/dev/null 2>&1; then
    lower+=(ionice -c3)
fi

parent_of() {  # the parent pid of a pid, on Linux and macOS alike
    if [[ -r "/proc/$1/stat" ]]; then
        local stat
        stat="$(< "/proc/$1/stat")"
        stat="${stat##*) }"  # the command name may hold spaces and parentheses; the fields after it do not
        read -r _state ppid _ <<< "$stat"
        echo "$ppid"
    else
        ps -o ppid= -p "$1" 2>/dev/null | tr -d ' '
    fi
}

inside_a_step() {  # true when NARRATE_BOUNDED_PID is this process (a shell exec'd it) or a real ancestor
    local want="${NARRATE_BOUNDED_PID:-}" pid="$PPID" hops=0
    [[ "$want" =~ ^[0-9]+$ ]] && (( want > 1 )) || return 1
    (( want == $$ )) && return 0
    while [[ "$pid" =~ ^[0-9]+$ ]] && (( pid > 1 && hops < 64 )); do
        (( pid == want )) && return 0
        pid="$(parent_of "$pid")"
        hops=$((hops + 1))
    done
    return 1
}

if inside_a_step; then
    exec "${lower[@]}" "$@"
fi

mem="${NARRATE_MEMORY_MAX:-6G}"
psi_max="${NARRATE_PSI_MAX:-10}"
wait_s="${NARRATE_PSI_WAIT_S:-600}"
psi_file="${NARRATE_PSI_FILE:-/proc/pressure/memory}"
lock_wait="${NARRATE_LOCK_WAIT_S:-3600}"
if [[ -n "${XDG_RUNTIME_DIR:-}" && -d "${XDG_RUNTIME_DIR}" ]]; then
    lock_file="${NARRATE_HEAVY_LOCK:-$XDG_RUNTIME_DIR/narrate-heavy.lock}"
else
    lock_file="${NARRATE_HEAVY_LOCK:-${TMPDIR:-/tmp}/narrate-heavy-$(id -u).lock}"
fi
[[ "$mem" =~ ^[1-9][0-9]{0,5}[KMGT]?$ ]] || die "NARRATE_MEMORY_MAX must look like 6G"
[[ "$psi_max" =~ ^[0-9]{1,3}(\.[0-9]{1,2})?$ ]] || die "NARRATE_PSI_MAX must be a percentage such as 10"
[[ "$wait_s" =~ ^[0-9]{1,5}$ ]] || die "NARRATE_PSI_WAIT_S must be whole seconds"
[[ "$lock_wait" =~ ^[0-9]{1,6}$ ]] || die "NARRATE_LOCK_WAIT_S must be whole seconds"

if (( lock )); then
    if command -v flock >/dev/null 2>&1; then
        if [[ -e "$lock_file" && ! -O "$lock_file" ]]; then
            die "the lock file $lock_file belongs to another user"
        fi
        # fd 9 stays open through exec, so the lock is held until the step and every child of it have exited.
        exec 9>>"$lock_file"
        if ! flock -n 9; then
            echo "bounded: another narrate step holds $lock_file; waiting up to ${lock_wait}s" >&2
            if ! flock -w "$lock_wait" 9; then
                echo "bounded: the other narrate step still holds the lock after ${lock_wait}s; not starting" >&2
                exit 75
            fi
        fi
    else
        echo "bounded: no flock here; this step is not serialised with other narrate steps" >&2
    fi
fi

pressure() {  # "full avg10" of the pressure file, or nothing when the file is absent
    [[ -r "$psi_file" ]] || return 0
    awk '$1 == "full" { for (i = 2; i <= NF; i++) if ($i ~ /^avg10=/) { sub(/^avg10=/, "", $i); print $i } }' \
        "$psi_file"
}
above() { awk -v p="$1" -v m="$psi_max" 'BEGIN { exit !(p > m) }'; }

waited=0
while p="$(pressure)" && [[ -n "$p" ]] && above "$p"; do
    if (( waited >= wait_s )); then
        echo "bounded: memory pressure full avg10=$p stayed above $psi_max for ${waited}s; not starting" >&2
        exit 75
    fi
    (( waited > 0 )) || echo "bounded: memory pressure full avg10=$p is above $psi_max; waiting" >&2
    sleep 5
    waited=$((waited + 5))
done

export NARRATE_BOUNDED_PID=$$
if command -v systemd-run >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
    exec systemd-run --user --scope --quiet --collect --unit="narrate-bounded-$$" -p MemoryMax="$mem" \
        "${lower[@]}" "$@"
fi
echo "bounded: no user systemd here; running at nice 19 without a memory ceiling" >&2
exec "${lower[@]}" "$@"
