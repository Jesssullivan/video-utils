// Shared (client-safe) BFF types. No server code, no env access.
export type BffErrorCode =
	| 'control_api_unconfigured'
	| 'control_api_refused_host'
	| 'control_api_unauthenticated'
	| 'control_api_token_refused'
	| 'control_api_unreachable'
	| 'control_api_timeout'
	| 'control_api_http_error'
	| 'control_api_refused'
	| 'control_api_too_large'
	| 'control_api_decode_error'
	| 'bff_cross_origin_refused'
	| 'bff_host_refused'
	| 'bff_identity_refused'
	| 'bff_auth_unconfigured'
	| 'bff_content_type_refused'
	| 'bff_length_required'
	| 'bff_body_too_large'
	| 'invalid_request'
	| 'invalid_job_id'
	| 'invalid_artifact_id'
	| 'invalid_source_id'
	| 'job_not_found'
	| 'source_not_found'
	| 'artifact_not_found';

/**
 * BFF error body: exactly these six keys. `upstream_code` / `upstream_detail_code` carry the
 * control API's typed code only when it matches ^[a-z_]{1,64}$; upstream `error` text is never echoed.
 */
export interface BffError {
	readonly status: 'error';
	readonly code: BffErrorCode;
	readonly message: string;
	readonly upstream_status: number | null;
	readonly upstream_code: string | null;
	readonly upstream_detail_code: string | null;
}

export function isBffError(value: unknown): value is BffError {
	return (
		typeof value === 'object' &&
		value !== null &&
		(value as { status?: unknown }).status === 'error' &&
		typeof (value as { code?: unknown }).code === 'string'
	);
}

/** The code to show a person: the upstream typed refusal when present, else the BFF code. */
export function displayCode(error: BffError): string {
	return error.upstream_code ?? error.code;
}

/**
 * A client-side typed error for responses without a BFF JSON body: adapter-node refuses bodies above
 * BODY_SIZE_LIMIT with a plain 413 (shown as upload_too_large); a type outside the allowlist is refused
 * before sending (upload_type_refused); anything else is a generic HTTP error with no typed code.
 */
export function makeClientError(kind: 'upload_too_large' | 'upload_type_refused' | 'http_error', httpStatus: number): BffError {
	const typed = kind !== 'http_error';
	return {
		status: 'error',
		code: typed ? 'control_api_refused' : 'control_api_http_error',
		message: typed ? 'Refused before the control API answered with JSON.' : 'The server answered without a typed JSON body.',
		upstream_status: httpStatus,
		upstream_code: typed ? kind : null,
		upstream_detail_code: null
	};
}
