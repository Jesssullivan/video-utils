#!/usr/bin/env bash
# Run one heavy narrate step bounded (docs/spec/NARRATE.md, "Host placement and memory"): wait while the host's
# memory pressure is high, then run the command at nice 19 with the idle I/O class, inside a transient user
# scope with a memory ceiling when `systemd-run --user` works. Without a user systemd (macOS, a CI container)
# the command runs at nice 19 without a ceiling, and the script says so on stderr.
#
#   bounded.sh <command> [args...]
#
#   NARRATE_MEMORY_MAX   the scope's MemoryMax (default 6G)
#   NARRATE_PSI_MAX      wait while "full avg10" of the pressure file is above this (default 10)
#   NARRATE_PSI_WAIT_S   stop waiting after this many seconds and exit 75 without running (default 600)
#   NARRATE_PSI_FILE     the pressure file (default /proc/pressure/memory; absent: no wait)
#
# The bounded command sees NARRATE_BOUNDED=1, so a nested call runs its command directly instead of opening a
# second scope beside the first.
set -euo pipefail

die() { echo "bounded: $*" >&2; exit 2; }
[[ $# -gt 0 ]] || die "usage: bounded.sh <command> [args...]"
if [[ "${NARRATE_BOUNDED:-}" == 1 ]]; then
    exec "$@"
fi

mem="${NARRATE_MEMORY_MAX:-6G}"
psi_max="${NARRATE_PSI_MAX:-10}"
wait_s="${NARRATE_PSI_WAIT_S:-600}"
psi_file="${NARRATE_PSI_FILE:-/proc/pressure/memory}"
[[ "$mem" =~ ^[1-9][0-9]{0,5}[KMGT]?$ ]] || die "NARRATE_MEMORY_MAX must look like 6G"
[[ "$psi_max" =~ ^[0-9]{1,3}(\.[0-9]{1,2})?$ ]] || die "NARRATE_PSI_MAX must be a percentage such as 10"
[[ "$wait_s" =~ ^[0-9]{1,5}$ ]] || die "NARRATE_PSI_WAIT_S must be whole seconds"

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

export NARRATE_BOUNDED=1
lower=(nice -n 19)
if command -v ionice >/dev/null 2>&1; then
    lower+=(ionice -c3)
fi
if command -v systemd-run >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
    exec systemd-run --user --scope --quiet --collect -p MemoryMax="$mem" "${lower[@]}" "$@"
fi
echo "bounded: no user systemd here; running at nice 19 without a memory ceiling" >&2
exec "${lower[@]}" "$@"
