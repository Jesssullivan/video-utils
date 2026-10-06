// Server-only Effect client for the assumed S2 control-API subset (WEB_STACK_S2.md section 4).
// Bounded: 5000 ms timeout over the whole request, 1 MiB body cap counted while streaming,
// no redirects followed, no credentials forwarded, no retries. Every failure is a tagged
// error mapped to exactly one stable BFF code. Raw upstream bodies never leave this module.
import { Data, Duration, Effect, Result, Schema, SchemaIssue } from 'effect';
import { JobSnapshot, KNOWN_FIELD_NAMES, SourceList, isOpaqueId } from '$lib/schema/control';
import { readControlApiConfig, type ControlApiConfig } from './config';
import type { BffError, BffErrorCode } from '$lib/control-types';

export type { BffError, BffErrorCode };

export const REQUEST_TIMEOUT_MS = 5000;
export const RESPONSE_CAP_BYTES = 1_048_576;

export class ControlApiUnconfigured extends Data.TaggedError('ControlApiUnconfigured')<{}> {}
export class ControlApiRefusedHost extends Data.TaggedError('ControlApiRefusedHost')<{}> {}
export class ControlApiUnreachable extends Data.TaggedError('ControlApiUnreachable')<{}> {}
export class ControlApiTimeout extends Data.TaggedError('ControlApiTimeout')<{}> {}
export class ControlApiHttpError extends Data.TaggedError('ControlApiHttpError')<{
	readonly upstreamStatus: number;
}> {}
export class ControlApiTooLarge extends Data.TaggedError('ControlApiTooLarge')<{}> {}
export class ControlApiDecodeError extends Data.TaggedError('ControlApiDecodeError')<{
	readonly paths: ReadonlyArray<string>;
}> {}
export class InvalidJobId extends Data.TaggedError('InvalidJobId')<{}> {}
export class JobNotFound extends Data.TaggedError('JobNotFound')<{}> {}

export type ControlApiFailure =
	| ControlApiUnconfigured
	| ControlApiRefusedHost
	| ControlApiUnreachable
	| ControlApiTimeout
	| ControlApiHttpError
	| ControlApiTooLarge
	| ControlApiDecodeError
	| InvalidJobId
	| JobNotFound;

export type BffResult<A> =
	| { readonly ok: true; readonly data: A }
	| { readonly ok: false; readonly httpStatus: number; readonly error: BffError };

export function toBffError(failure: ControlApiFailure): { httpStatus: number; error: BffError } {
	const make = (httpStatus: number, code: BffErrorCode, message: string, upstream: number | null = null) => ({
		httpStatus,
		error: { status: 'error' as const, code, message, upstream_status: upstream }
	});
	switch (failure._tag) {
		case 'ControlApiUnconfigured':
			return make(503, 'control_api_unconfigured', 'VIDEO_UTILS_CONTROL_API_URL is not set; no control API is configured.');
		case 'ControlApiRefusedHost':
			return make(503, 'control_api_refused_host', 'Control API URL refused: only http://127.0.0.1:<port> or http://[::1]:<port> is accepted.');
		case 'ControlApiUnreachable':
			return make(502, 'control_api_unreachable', 'Control API could not be reached.');
		case 'ControlApiTimeout':
			return make(504, 'control_api_timeout', `Control API did not answer within ${REQUEST_TIMEOUT_MS} ms.`);
		case 'ControlApiHttpError':
			return make(502, 'control_api_http_error', 'Control API returned a non-success HTTP status.', failure.upstreamStatus);
		case 'ControlApiTooLarge':
			return make(502, 'control_api_too_large', `Control API response exceeded ${RESPONSE_CAP_BYTES} bytes.`);
		case 'ControlApiDecodeError':
			return make(502, 'control_api_decode_error', `Control API response did not match the expected schema at: ${failure.paths.join(', ') || '(root)'}`);
		case 'InvalidJobId':
			return make(400, 'invalid_job_id', 'Job id must match ^[A-Za-z0-9_-]{1,128}$.');
		case 'JobNotFound':
			return make(404, 'job_not_found', 'Control API reports no such job.', 404);
	}
}

const configEffect = (config: ControlApiConfig): Effect.Effect<string, ControlApiUnconfigured | ControlApiRefusedHost> => {
	switch (config.kind) {
		case 'configured':
			return Effect.succeed(config.baseUrl);
		case 'unconfigured':
			return Effect.fail(new ControlApiUnconfigured());
		case 'refused':
			return Effect.fail(new ControlApiRefusedHost());
	}
};

type CappedBody = { readonly kind: 'ok'; readonly text: string } | { readonly kind: 'too_large' };

async function readCapped(response: Response, signal: AbortSignal): Promise<CappedBody> {
	const declared = Number(response.headers.get('content-length') ?? 'NaN');
	if (Number.isFinite(declared) && declared > RESPONSE_CAP_BYTES) {
		await response.body?.cancel().catch(() => undefined);
		return { kind: 'too_large' };
	}
	if (!response.body) return { kind: 'ok', text: '' };
	const reader = response.body.getReader();
	const chunks: Uint8Array[] = [];
	let total = 0;
	const onAbort = () => void reader.cancel().catch(() => undefined);
	signal.addEventListener('abort', onAbort, { once: true });
	try {
		for (;;) {
			const { done, value } = await reader.read();
			if (done) break;
			total += value.byteLength;
			if (total > RESPONSE_CAP_BYTES) {
				await reader.cancel().catch(() => undefined);
				return { kind: 'too_large' };
			}
			chunks.push(value);
		}
	} finally {
		signal.removeEventListener('abort', onAbort);
	}
	const merged = new Uint8Array(total);
	let offset = 0;
	for (const chunk of chunks) {
		merged.set(chunk, offset);
		offset += chunk.byteLength;
	}
	return { kind: 'ok', text: new TextDecoder('utf-8', { fatal: false }).decode(merged) };
}

/** Keep only schema-known field names and indexes in issue paths; never echo upstream text. */
function sanitizePathSegment(segment: unknown): string {
	const key = typeof segment === 'object' && segment !== null && 'key' in segment ? (segment as { key: unknown }).key : segment;
	if (typeof key === 'number' && Number.isInteger(key)) return String(key);
	if (typeof key === 'string' && /^[0-9]{1,4}$/.test(key)) return key;
	if (typeof key === 'string' && KNOWN_FIELD_NAMES.has(key)) return key;
	return '<unexpected_key>';
}

const formatter = SchemaIssue.makeFormatterStandardSchemaV1();

function issuePaths(error: Schema.SchemaError): string[] {
	const paths = formatter(error.issue).issues.map((issue) =>
		(issue.path ?? []).map(sanitizePathSegment).join('.') || '(root)'
	);
	return [...new Set(paths)].slice(0, 16);
}

const getJson = (path: string, notFound: 'job_not_found' | 'http_error') =>
	Effect.gen(function* () {
		const baseUrl = yield* configEffect(readControlApiConfig());
		const body = yield* Effect.gen(function* () {
			const response = yield* Effect.tryPromise({
				try: (signal) =>
					fetch(`${baseUrl}${path}`, {
						method: 'GET',
						signal,
						redirect: 'manual',
						credentials: 'omit',
						headers: { accept: 'application/json' }
					}),
				catch: () => new ControlApiUnreachable()
			});
			if (response.status === 404 && notFound === 'job_not_found') {
				yield* Effect.promise(() => response.body?.cancel().catch(() => undefined) ?? Promise.resolve());
				return yield* Effect.fail(new JobNotFound());
			}
			if (response.status < 200 || response.status > 299) {
				yield* Effect.promise(() => response.body?.cancel().catch(() => undefined) ?? Promise.resolve());
				return yield* Effect.fail(new ControlApiHttpError({ upstreamStatus: response.status }));
			}
			const capped = yield* Effect.tryPromise({
				try: (signal) => readCapped(response, signal),
				catch: () => new ControlApiUnreachable()
			});
			if (capped.kind === 'too_large') return yield* Effect.fail(new ControlApiTooLarge());
			return capped.text;
		}).pipe(
			Effect.timeoutOrElse({
				duration: Duration.millis(REQUEST_TIMEOUT_MS),
				orElse: () => Effect.fail(new ControlApiTimeout())
			})
		);
		const parsed = yield* Effect.try({
			try: () => JSON.parse(body) as unknown,
			catch: () => new ControlApiDecodeError({ paths: ['(json)'] })
		});
		return parsed;
	});

const DECODE_OPTIONS = { onExcessProperty: 'error', errors: 'all' } as const;
const toDecodeError = (error: Schema.SchemaError) => new ControlApiDecodeError({ paths: issuePaths(error) });

const decodeSourceList = (input: unknown) =>
	Schema.decodeUnknownEffect(SourceList)(input, DECODE_OPTIONS).pipe(Effect.mapError(toDecodeError));

const decodeJobSnapshot = (input: unknown) =>
	Schema.decodeUnknownEffect(JobSnapshot)(input, DECODE_OPTIONS).pipe(Effect.mapError(toDecodeError));

export const listSources = getJson('/api/v1/sources', 'http_error').pipe(Effect.flatMap(decodeSourceList));

export const getJob = (jobId: string) =>
	Effect.gen(function* () {
		if (!isOpaqueId(jobId)) return yield* Effect.fail(new InvalidJobId());
		const raw = yield* getJson(`/api/v1/jobs/${encodeURIComponent(jobId)}`, 'job_not_found');
		return yield* decodeJobSnapshot(raw);
	});

/**
 * Run a client effect to a plain result. Aborting `signal` (browser navigation or tab close)
 * interrupts only the outgoing fetch; it never implies job cancellation.
 */
export async function runControl<A>(
	effect: Effect.Effect<A, ControlApiFailure>,
	signal?: AbortSignal
): Promise<BffResult<A>> {
	try {
		const result = await Effect.runPromise(Effect.result(effect), signal ? { signal } : undefined);
		if (Result.isSuccess(result)) return { ok: true, data: result.success };
		const mapped = toBffError(result.failure);
		return { ok: false, httpStatus: mapped.httpStatus, error: mapped.error };
	} catch {
		const mapped = toBffError(new ControlApiUnreachable());
		return { ok: false, httpStatus: mapped.httpStatus, error: mapped.error };
	}
}
