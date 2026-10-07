# S3 take_intake (docs/spec/sprints/TAKE_INTAKE_S3.md): one-command intake for a NEW take.
# Root imports this file from the root justfile (`import 'just/take.just'`).
# Real-take outputs stay private beneath ignored artifacts/ (V6); the source is never written.

#   just take-plan SOURCE [--arrangement REF] [--bpm X] [--features extended] [--family ID]
# Read-only plan: sha256, probe, proposed take_family_id, corpus row draft (split null), steps, required inputs.
[positional-arguments]
take-plan source *ARGS:
    python3 scripts/take_intake.py plan "$@"

#   just take-run SOURCE START END "REVIEW TEXT" [--arrangement REF --anchor-seconds S --anchor-source TEXT
#                 --clicks-per-grid-period 1|2] [--bpm X] [--features extended] [--interval-reviewed-includes-setup]
# Refuses without a reviewed interval or inside the 0-5 s setup window unless the setup flag is recorded.
# New take: FULLER with a reviewed fan interval, phrase timing, marked preview and sharing export.
[positional-arguments]
take-run source start end review *ARGS:
    python3 scripts/take_intake.py run "$1" --capture-interval "$2" "$3" --capture-review "$4" "${@:5}"

# Crash-recover one recorded intake in place; replays recorded settings (only --state-root may be added).
[positional-arguments]
take-resume intake_id *ARGS:
    python3 scripts/take_intake.py run --resume "$@"

# Rebuild the evidence packet and the TIN-5186 message draft (not sent) for an intake run directory.
take-packet run_dir:
    python3 scripts/take_intake.py packet {{quote(run_dir)}}

# Owned lane tests; the sealed end-to-end class needs TAKE_INTAKE_E2E=1 and FFMPEG/FFPROBE.
take-intake-test:
    PYTHONPATH=tests python3 -m unittest test_take_intake -v
