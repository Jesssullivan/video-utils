// Client-safe text for the S3 processing refusal codes (scripts/web_jobs.py). The code itself is
// always shown; this text explains it. Unknown codes fall back to a neutral sentence.
const TEXT: Record<string, string> = {
	capture_interval_required:
		'A saved, reviewed capture interval with scope experimental_capture_render is required. FULLER never runs without one.',
	tool_pending_admission: 'This job type is allowlisted but its web adapter awaits root admission; nothing was queued.',
	tool_not_admitted: 'This tool is not in the closed web job allowlist.',
	profile_source_mismatch: 'This source-bound profile belongs to another recording.',
	preset_controls_forbidden: 'FULLER is expanded verbatim from profiles/fuller.json; explicit controls are refused.',
	invalid_parameters: 'A knob is missing, of the wrong type or outside the tool schema bounds. Nothing was clamped.',
	review_stale: 'The source, baseline manifest, source.wav or review file changed since the review was saved.',
	authoring_stale: 'The authored capture profile receipt changed or is missing.',
	authoring_not_renderable: 'The authoring job did not produce an authored_unrendered profile with render scope.',
	capture_review_rejected: 'This review is rejected_contaminated and cannot author a profile.',
	review_source_mismatch: 'This review is bound to another source.',
	parent_job_mismatch: 'The chosen authoring job belongs to another tool or source.',
	setup_interval_unacknowledged:
		'The interval overlaps the first five seconds (setup guitar/amp sounds, possible windup). Acknowledge it explicitly.',
	setup_interval_status_refused:
		'An interval overlapping the first five seconds can only be reviewed_possible_contamination or rejected_contaminated.',
	interval_out_of_range: 'The interval must be 0.1–10 s long and inside the baseline run native extent.',
	run_not_bound: 'This run is not bound to the admitted source file.',
	run_not_baseline: 'This run has no bounded native source.wav baseline.',
	unknown_run: 'No such run.',
	source_stale: 'The admitted source bytes changed; admit the new version.',
	source_missing: 'The admitted source is no longer present.',
	invalid_review: 'A review field is missing or not a capture_profile enumeration value; the note must be non-empty.',
	idempotency_conflict: 'This form key already names a different request; reload the page.',
	queue_full: 'The job queue is full; wait for queued jobs to finish.',
	pcm_format_unsupported: 'The baseline source.wav is not s16/s24/s32/f32 PCM.',
	run_required: 'Choose a baseline run first.',
	interval_required: 'Enter both start and end seconds.',
	invalid_form_key: 'Reload the page: the form key is invalid.',
	invalid_review_id: 'Choose a saved review.'
};

export function processingText(code: string): string {
	return Object.hasOwn(TEXT, code) ? TEXT[code] : 'The control API refused this request with a typed code.';
}
