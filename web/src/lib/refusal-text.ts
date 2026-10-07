// Client-safe plain-language text for typed codes (control API upstream codes and BFF codes).
// Codes come from the closed allowlist pattern ^[a-z_]{1,64}$; upstream `error` text is never shown.
const TEXT: Readonly<Record<string, string>> = {
	// uploads / admission
	uploads_disabled: 'Uploads are off. The operator enables them by starting the control API with --allow-uploads.',
	upload_too_large: 'The file is larger than the upload bound; it was refused before any byte was stored.',
	upload_type_refused: 'Only .mov, .mp4, .m4v, .mkv or .webm video files are accepted.',
	upload_incomplete: 'The upload ended before all bytes arrived; nothing was kept.',
	upload_empty: 'The upload was empty.',
	upload_label_refused: 'The upload label must be 1..120 printable ASCII characters.',
	upload_hash_mismatch: 'The stored bytes did not match the streamed bytes; nothing was kept.',
	length_required: 'The request needs a Content-Length (no chunked bodies).',
	not_media: 'The file does not start with the container signature for its type (ftyp or EBML).',
	path_escape: 'The selector must be relative to artifacts/runs: no absolute path, "..", symbolic link or URL.',
	admission_refused: 'The source was refused by artifact-id admission.',
	not_regular_file: 'The selector does not name an existing regular file.',
	executable_refused: 'Executable files are refused.',
	too_large: 'The source exceeds the admitted size bound.',
	changed_during_hash: 'The source changed while it was being hashed.',
	unknown_source: 'This source id is not admitted in this state root.',
	source_stale: 'The admitted source bytes changed; admit the new version.',
	source_missing: 'The admitted source is no longer present.',
	confinement_refused: 'The file location is not confined to the expected directory.',
	// jobs
	invalid_parameters: 'The control API refused these settings (the same validation as the CLI and MCP tool).',
	idempotency_conflict: 'This form key already names a different request; adjust settings again for a new key.',
	queue_full: 'The job queue is full; wait for a queued job to start.',
	not_retryable: 'Only failed or interrupted jobs can be retried.',
	prior_worker_alive: 'An earlier worker may still be running; it is not signalled by the service.',
	tool_not_admitted: 'Only share_export is admitted as a web job.',
	unknown_job: 'This job id is not known to the control API.',
	artifact_private: 'This artifact is listed but never served (it records host paths).',
	artifact_stale: 'The published artifact bytes changed; it is not served.',
	artifact_missing: 'The published artifact is missing.',
	unknown_artifact: 'This artifact id is not a published job artifact.',
	// annotations
	annotation_source_clock_unknown: 'Source clock unknown — run the share preview first.',
	annotation_actor_refused: 'The browser can only write operator notes (USER REPORTED or INTENT).',
	stale_annotation_revision: 'Notes changed since this view loaded. Your draft is kept and the list was refreshed.',
	source_span_out_of_bounds: 'The note time is outside the source clock extent.',
	idempotency_key_conflict: 'This note key was already used for a different note; edit and save again.',
	annotation_store_busy_retry: 'The note store is busy; try again.',
	// BFF / configuration
	control_api_unconfigured: 'No control API is configured for this server.',
	control_api_refused_host: 'The configured control API URL is not a loopback address.',
	control_api_unauthenticated: 'The control API token is missing in the server environment.',
	control_api_token_refused: 'The control API refused the configured token.',
	control_api_unreachable: 'The control API could not be reached.',
	control_api_timeout: 'The control API did not answer in time.',
	bff_host_refused: 'This app answers only on a loopback host (127.0.0.1, [::1] or localhost).',
	bff_cross_origin_refused: 'Requests that change anything must come from this page.',
	bff_identity_refused: 'This app could not verify an allowed operator identity for this request.',
	bff_auth_unconfigured: 'Hosted sign-in is not configured for this server; nothing is served.',
	bff_content_type_refused: 'The request content type is not accepted.',
	bff_length_required: 'The upload needs a Content-Length.',
	invalid_request: 'The request was malformed and was not sent to the control API.'
};

export function refusalText(code: string): string {
	return TEXT[code] ?? 'Refused with a typed code; see the code shown.';
}
