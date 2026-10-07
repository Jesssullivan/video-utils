// Client-safe copy of the server rule (scripts/web_jobs.py overlaps_setup): [start, end) overlaps [0, 5).
export const SETUP_INTERVAL_SECONDS = 5;
export const overlapsSetup = (start: number): boolean => Number.isFinite(start) && start < SETUP_INTERVAL_SECONDS;
