// Shared (client-safe) BFF types. No server code, no env access.
export type BffErrorCode =
	| 'control_api_unconfigured'
	| 'control_api_refused_host'
	| 'control_api_unreachable'
	| 'control_api_timeout'
	| 'control_api_http_error'
	| 'control_api_too_large'
	| 'control_api_decode_error'
	| 'invalid_job_id'
	| 'job_not_found';

/** BFF error body: exactly these four keys. */
export interface BffError {
	readonly status: 'error';
	readonly code: BffErrorCode;
	readonly message: string;
	readonly upstream_status: number | null;
}
