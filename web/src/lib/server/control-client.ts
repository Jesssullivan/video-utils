// Server-only Effect client for the merged S2 control API (scripts/web_api.py /api/v1).
// JSON calls: 5000 ms timeout over the whole request, 1 MiB body cap counted while streaming,
// no redirects followed, no browser credentials forwarded, no retries. Streamed media, upload and
// download use a 30 s idle timeout and no total cap beyond upstream Content-Length. Every failure is
// a tagged error mapped to exactly one stable BFF code. Raw upstream bodies and `error` text never
// leave this module; only typed codes matching ^[a-z_]{1,64}$ are surfaced as upstream_code.
import { Data, Duration, Effect, Result, Schema, SchemaIssue } from 'effect';
import {
	AdmissionRecord,
	AnnotationRead,
	AnnotationWrite,
	JobList,
	JobProjection,
	KNOWN_FIELD_NAMES,
	SourceList,
	UploadResult,
	isArtifactId,
	isJobId
} from '$lib/schema/control';
import { readControlApiConfig, type ControlApiConfig } from './config';
import type { JobRequestBody } from './job-request';
import type { BffError, BffErrorCode } from '$lib/control-types';

export type { BffError, BffErrorCode };

export const REQUEST_TIMEOUT_MS = 5000;
export const RESPONSE_CAP_BYTES = 1_048_576;
export const STREAM_IDLE_TIMEOUT_MS = 30_000;
const UPSTREAM_CODE = /^[a-z_]{1,64}$/;
const PASS_THROUGH_HEADERS = ['content-type', 'content-length', 'x-artifact-sha256', 'content-disposition'] as const;

type IdKind = 'job' | 'source' | 'artifact';

export class ControlApiUnconfigured extends Data.TaggedError('ControlApiUnconfigured')<{}> {}
export class ControlApiRefusedHost extends Data.TaggedError('ControlApiRefusedHost')<{}> {}
export class ControlApiUnauthenticated extends Data.TaggedError('ControlApiUnauthenticated')<{}> {}
export class ControlApiTokenRefused extends Data.TaggedError('ControlApiTokenRefused')<{}> {}
export class ControlApiUnreachable extends Data.TaggedError('ControlApiUnreachable')<{}> {}
export class ControlApiTimeout extends Data.TaggedError('ControlApiTimeout')<{ readonly idle: boolean }> {}
export class ControlApiHttpError extends Data.TaggedError('ControlApiHttpError')<{
	readonly upstreamStatus: number;
	readonly upstreamCode: string | null;
	readonly upstreamDetailCode: string | null;
}> {}
export class ControlApiRefused extends Data.TaggedError('ControlApiRefused')<{
	readonly upstreamStatus: number;
	readonly upstreamCode: string;
	readonly upstreamDetailCode: string | null;
}> {}
export class ControlApiTooLarge extends Data.TaggedError('ControlApiTooLarge')<{}> {}
export class ControlApiDecodeError extends Data.TaggedError('ControlApiDecodeError')<{
	readonly paths: ReadonlyArray<string>;
}> {}
export class InvalidId extends Data.TaggedError('InvalidId')<{ readonly kind: IdKind }> {}
export class NotFound extends Data.TaggedError('NotFound')<{
	readonly kind: IdKind;
	readonly upstreamCode: string | null;
}> {}

export type ControlApiFailure =
	| ControlApiUnconfigured
	| ControlApiRefusedHost
	| ControlApiUnauthenticated
	| ControlApiTokenRefused
	| ControlApiUnreachable
	| ControlApiTimeout
	| ControlApiHttpError
	| ControlApiRefused
	| ControlApiTooLarge
	| ControlApiDecodeError
	| InvalidId
	| NotFound;

export type BffResult<A> =
	| { readonly ok: true; readonly status: number; readonly data: A }
	| { readonly ok: false; readonly httpStatus: number; readonly error: BffError };

export function makeBffError(
	httpStatus: number,
	code: BffErrorCode,
	message: string,
	upstream: { status?: number | null; code?: string | null; detail?: string | null } = {}
): { httpStatus: number; error: BffError } {
	return {
		httpStatus,
		error: {
			status: 'error',
			code,
			message,
			upstream_status: upstream.status ?? null,
			upstream_code: upstream.code ?? null,
			upstream_detail_code: upstream.detail ?? null
		}
	};
}

const ID_TEXT: Record<IdKind, { code: BffErrorCode; pattern: string; missing: BffErrorCode }> = {
	job: { code: 'invalid_job_id', pattern: '^job_[0-9a-f]{32}$', missing: 'job_not_found' },
	source: { code: 'invalid_source_id', pattern: '^art_[0-9a-f]{32}$', missing: 'source_not_found' },
	artifact: { code: 'invalid_artifact_id', pattern: '^art_[0-9a-f]{32}$', missing: 'artifact_not_found' }
};

export function toBffError(failure: ControlApiFailure): { httpStatus: number; error: BffError } {
	switch (failure._tag) {
		case 'ControlApiUnconfigured':
			return makeBffError(503, 'control_api_unconfigured', 'VIDEO_UTILS_CONTROL_API_URL is not set; no control API is configured.');
		case 'ControlApiRefusedHost':
			return makeBffError(503, 'control_api_refused_host', 'Control API URL refused: only http://127.0.0.1:<port> or http://[::1]:<port> is accepted.');
		case 'ControlApiUnauthenticated':
			return makeBffError(503, 'control_api_unauthenticated', 'The control API bearer token is missing or malformed in the server environment.');
		case 'ControlApiTokenRefused':
			return makeBffError(502, 'control_api_token_refused', 'The control API refused the configured bearer token.', { status: 401 });
		case 'ControlApiUnreachable':
			return makeBffError(502, 'control_api_unreachable', 'Control API could not be reached.');
		case 'ControlApiTimeout':
			return failure.idle
				? makeBffError(504, 'control_api_timeout', `Control API stream was idle for ${STREAM_IDLE_TIMEOUT_MS} ms.`)
				: makeBffError(504, 'control_api_timeout', `Control API did not answer within ${REQUEST_TIMEOUT_MS} ms.`);
		case 'ControlApiHttpError':
			return makeBffError(502, 'control_api_http_error', 'Control API returned a non-success HTTP status.', {
				status: failure.upstreamStatus,
				code: failure.upstreamCode,
				detail: failure.upstreamDetailCode
			});
		case 'ControlApiRefused':
			return makeBffError(failure.upstreamStatus, 'control_api_refused', 'The control API refused this request with a typed code.', {
				status: failure.upstreamStatus,
				code: failure.upstreamCode,
				detail: failure.upstreamDetailCode
			});
		case 'ControlApiTooLarge':
			return makeBffError(502, 'control_api_too_large', `Control API response exceeded ${RESPONSE_CAP_BYTES} bytes.`);
		case 'ControlApiDecodeError':
			return makeBffError(502, 'control_api_decode_error', `Control API response did not match the expected schema at: ${failure.paths.join(', ') || '(root)'}`);
		case 'InvalidId': {
			const text = ID_TEXT[failure.kind];
			return makeBffError(400, text.code, `The ${failure.kind} id must match ${text.pattern}.`);
		}
		case 'NotFound':
			return makeBffError(404, ID_TEXT[failure.kind].missing, `Control API reports no such ${failure.kind}.`, {
				status: 404,
				code: failure.upstreamCode
			});
	}
}

const configEffect = (
	config: ControlApiConfig
): Effect.Effect<{ baseUrl: string; token: string }, ControlApiUnconfigured | ControlApiRefusedHost | ControlApiUnauthenticated> => {
	switch (config.kind) {
		case 'configured':
			return Effect.succeed({ baseUrl: config.baseUrl, token: config.token });
		case 'unconfigured':
			return Effect.fail(new ControlApiUnconfigured());
		case 'refused':
			return Effect.fail(new ControlApiRefusedHost());
		case 'unauthenticated':
			return Effect.fail(new ControlApiUnauthenticated());
	}
};

/** Configuration check with no network access (pages that must render the config state). */
export const controlConfigured = Effect.suspend(() => configEffect(readControlApiConfig())).pipe(Effect.asVoid);

type CappedBody = { readonly kind: 'ok'; readonly text: string } | { readonly kind: 'too_large' };

async function readCapped(response: Response, signal: AbortSignal, cap = RESPONSE_CAP_BYTES): Promise<CappedBody> {
	const declared = Number(response.headers.get('content-length') ?? 'NaN');
	if (Number.isFinite(declared) && declared > cap) {
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
			if (total > cap) {
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

/** Typed upstream code/detail only; anything else (including `error` text) is discarded. */
function typedCodes(text: string): { code: string | null; detail: string | null } {
	try {
		const parsed: unknown = JSON.parse(text);
		if (typeof parsed !== 'object' || parsed === null) return { code: null, detail: null };
		const { code, detail_code: detail } = parsed as { code?: unknown; detail_code?: unknown };
		return {
			code: typeof code === 'string' && UPSTREAM_CODE.test(code) ? code : null,
			detail: typeof detail === 'string' && UPSTREAM_CODE.test(detail) ? detail : null
		};
	} catch {
		return { code: null, detail: null };
	}
}

const NOT_FOUND_CODES: Record<string, IdKind> = {
	unknown_job: 'job',
	unknown_source: 'source',
	unknown_artifact: 'artifact'
};

/** Map a non-2xx upstream response to exactly one failure. */
async function upstreamFailure(response: Response, signal: AbortSignal, notFound: IdKind | null): Promise<ControlApiFailure> {
	const capped = await readCapped(response, signal, 65_536).catch(() => ({ kind: 'too_large' }) as CappedBody);
	const { code, detail } = capped.kind === 'ok' ? typedCodes(capped.text) : { code: null, detail: null };
	const status = response.status;
	if (status === 401) return new ControlApiTokenRefused();
	if (status === 404 && code !== null && code in NOT_FOUND_CODES) {
		return new NotFound({ kind: NOT_FOUND_CODES[code], upstreamCode: code });
	}
	if (status === 404 && notFound !== null && code === null) return new NotFound({ kind: notFound, upstreamCode: null });
	if (status >= 400 && status <= 499 && code !== null && code !== 'route_not_found' && code !== 'method_not_allowed') {
		return new ControlApiRefused({ upstreamStatus: status, upstreamCode: code, upstreamDetailCode: detail });
	}
	return new ControlApiHttpError({ upstreamStatus: status, upstreamCode: code, upstreamDetailCode: detail });
}

export type JsonCall = {
	readonly method: 'GET' | 'POST';
	readonly path: string;
	readonly body?: unknown;
	readonly notFound?: IdKind;
};

export const requestJson = (call: JsonCall) =>
	Effect.gen(function* () {
		const { baseUrl, token } = yield* Effect.suspend(() => configEffect(readControlApiConfig()));
		const outcome = yield* Effect.gen(function* () {
			const response = yield* Effect.tryPromise({
				try: (signal) =>
					fetch(`${baseUrl}${call.path}`, {
						method: call.method,
						signal,
						redirect: 'manual',
						credentials: 'omit',
						headers: {
							accept: 'application/json',
							authorization: `Bearer ${token}`,
							...(call.body !== undefined ? { 'content-type': 'application/json' } : {})
						},
						body: call.body !== undefined ? JSON.stringify(call.body) : undefined
					}),
				catch: () => new ControlApiUnreachable()
			});
			if (response.status < 200 || response.status > 299) {
				const failure = yield* Effect.tryPromise({
					try: (signal) => upstreamFailure(response, signal, call.notFound ?? null),
					catch: () => new ControlApiUnreachable()
				});
				return yield* Effect.fail(failure);
			}
			const capped = yield* Effect.tryPromise({
				try: (signal) => readCapped(response, signal),
				catch: () => new ControlApiUnreachable()
			});
			if (capped.kind === 'too_large') return yield* Effect.fail(new ControlApiTooLarge());
			return { status: response.status, text: capped.text };
		}).pipe(
			Effect.timeoutOrElse({
				duration: Duration.millis(REQUEST_TIMEOUT_MS),
				orElse: () => Effect.fail(new ControlApiTimeout({ idle: false }))
			})
		);
		const parsed = yield* Effect.try({
			try: () => JSON.parse(outcome.text) as unknown,
			catch: () => new ControlApiDecodeError({ paths: ['(json)'] })
		});
		return { status: outcome.status, body: parsed };
	});

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
	const paths = formatter(error.issue).issues.map((issue) => (issue.path ?? []).map(sanitizePathSegment).join('.') || '(root)');
	return [...new Set(paths)].slice(0, 16);
}

const DECODE_OPTIONS = { onExcessProperty: 'error', errors: 'all' } as const;

export function decodeWith<S extends Schema.Top>(schema: S) {
	return (outcome: { status: number; body: unknown }) =>
		Schema.decodeUnknownEffect(schema as never)(outcome.body, DECODE_OPTIONS).pipe(
			Effect.map((data) => ({ status: outcome.status, data: data as S['Type'] })),
			Effect.mapError((error) => new ControlApiDecodeError({ paths: issuePaths(error as Schema.SchemaError) }))
		);
}

const requireId = (kind: IdKind, value: string) => {
	const ok = kind === 'job' ? isJobId(value) : isArtifactId(value);
	return ok ? Effect.void : Effect.fail(new InvalidId({ kind }));
};

// --------------------------------------------------------------------------- JSON operations

export const listSources = requestJson({ method: 'GET', path: '/api/v1/sources?limit=500' }).pipe(
	Effect.flatMap(decodeWith(SourceList))
);

export const admitSource = (selector: string) =>
	requestJson({ method: 'POST', path: '/api/v1/sources', body: { selector } }).pipe(Effect.flatMap(decodeWith(AdmissionRecord)));

export const getJob = (jobId: string) =>
	requireId('job', jobId).pipe(
		Effect.andThen(requestJson({ method: 'GET', path: `/api/v1/jobs/${jobId}`, notFound: 'job' })),
		Effect.flatMap(decodeWith(JobProjection))
	);

export const listJobs = (sourceId: string) =>
	requireId('source', sourceId).pipe(
		Effect.andThen(requestJson({ method: 'GET', path: `/api/v1/jobs?source_artifact_id=${sourceId}&limit=200` })),
		Effect.flatMap(decodeWith(JobList))
	);

export const submitJob = (body: JobRequestBody) =>
	requestJson({ method: 'POST', path: '/api/v1/jobs', body }).pipe(Effect.flatMap(decodeWith(JobProjection)));

export const jobAction = (jobId: string, action: 'cancel' | 'retry') =>
	requireId('job', jobId).pipe(
		Effect.andThen(requestJson({ method: 'POST', path: `/api/v1/jobs/${jobId}/${action}`, body: {}, notFound: 'job' })),
		Effect.flatMap(decodeWith(JobProjection))
	);

export const readAnnotations = (sourceId: string) =>
	requireId('source', sourceId).pipe(
		Effect.andThen(requestJson({ method: 'GET', path: `/api/v1/sources/${sourceId}/annotations`, notFound: 'source' })),
		Effect.flatMap(decodeWith(AnnotationRead))
	);

export const writeAnnotation = (sourceId: string, request: Record<string, unknown>) =>
	requireId('source', sourceId).pipe(
		Effect.andThen(
			requestJson({ method: 'POST', path: `/api/v1/sources/${sourceId}/annotations`, body: request, notFound: 'source' })
		),
		Effect.flatMap(decodeWith(AnnotationWrite))
	);

// --------------------------------------------------------------------------- streamed operations

/** Aborts after `ms` without progress; `touch()` on every chunk. */
class IdleAbort {
	readonly controller = new AbortController();
	fired = false;
	private timer: ReturnType<typeof setTimeout> | undefined;
	constructor(private readonly ms: number, outer?: AbortSignal) {
		outer?.addEventListener('abort', () => this.controller.abort(), { once: true });
		this.touch();
	}
	get signal(): AbortSignal {
		return this.controller.signal;
	}
	touch(): void {
		clearTimeout(this.timer);
		this.timer = setTimeout(() => {
			this.fired = true;
			this.controller.abort();
		}, this.ms);
	}
	done(): void {
		clearTimeout(this.timer);
	}
}

function watched(body: ReadableStream<Uint8Array>, idle: IdleAbort): ReadableStream<Uint8Array> {
	const reader = body.getReader();
	return new ReadableStream<Uint8Array>({
		async pull(controller) {
			try {
				const { done, value } = await reader.read();
				if (done) {
					idle.done();
					controller.close();
					return;
				}
				idle.touch();
				controller.enqueue(value);
			} catch (cause) {
				idle.done();
				controller.error(cause);
			}
		},
		cancel(reason) {
			idle.done();
			return reader.cancel(reason);
		}
	});
}

export type StreamedResponse = { readonly status: number; readonly headers: Headers; readonly body: ReadableStream<Uint8Array> | null };

const openStream = (path: string, notFound: IdKind, signal?: AbortSignal) =>
	Effect.gen(function* () {
		const { baseUrl, token } = yield* Effect.suspend(() => configEffect(readControlApiConfig()));
		const idle = new IdleAbort(STREAM_IDLE_TIMEOUT_MS, signal);
		const response = yield* Effect.tryPromise({
			try: () =>
				fetch(`${baseUrl}${path}`, {
					method: 'GET',
					signal: idle.signal,
					redirect: 'manual',
					credentials: 'omit',
					headers: { authorization: `Bearer ${token}` }
				}),
			catch: () => (idle.fired ? new ControlApiTimeout({ idle: true }) : new ControlApiUnreachable())
		});
		if (response.status !== 200) {
			const failure = yield* Effect.tryPromise({
				try: () => upstreamFailure(response, idle.signal, notFound),
				catch: () => new ControlApiUnreachable()
			});
			idle.done();
			return yield* Effect.fail(failure);
		}
		const headers = new Headers({ 'cache-control': 'no-store', 'x-content-type-options': 'nosniff' });
		for (const name of PASS_THROUGH_HEADERS) {
			const value = response.headers.get(name);
			if (value !== null) headers.set(name, value);
		}
		if (response.headers.get('accept-ranges') === 'none') headers.set('accept-ranges', 'none');
		return { status: 200, headers, body: response.body ? watched(response.body, idle) : null } satisfies StreamedResponse;
	});

export const openArtifact = (artifactId: string, signal?: AbortSignal) =>
	requireId('artifact', artifactId).pipe(Effect.andThen(openStream(`/api/v1/artifacts/${artifactId}`, 'artifact', signal)));

export const openSourceMedia = (sourceId: string, signal?: AbortSignal) =>
	requireId('source', sourceId).pipe(Effect.andThen(openStream(`/api/v1/sources/${sourceId}/media`, 'source', signal)));

/** Stream a raw upload body upstream (never buffered here) and decode the JSON admission result. */
export const uploadSource = (
	body: ReadableStream<Uint8Array>,
	contentType: string,
	contentLength: string,
	label: string | null,
	signal?: AbortSignal
) =>
	Effect.gen(function* () {
		const { baseUrl, token } = yield* Effect.suspend(() => configEffect(readControlApiConfig()));
		const idle = new IdleAbort(STREAM_IDLE_TIMEOUT_MS, signal);
		const response = yield* Effect.tryPromise({
			try: () =>
				fetch(`${baseUrl}/api/v1/uploads`, {
					method: 'POST',
					signal: idle.signal,
					redirect: 'manual',
					credentials: 'omit',
					headers: {
						accept: 'application/json',
						authorization: `Bearer ${token}`,
						'content-type': contentType,
						'content-length': contentLength,
						...(label !== null ? { 'x-upload-label': label } : {})
					},
					body: watched(body, idle),
					duplex: 'half'
				} as RequestInit & { duplex: 'half' }),
			catch: () => (idle.fired ? new ControlApiTimeout({ idle: true }) : new ControlApiUnreachable())
		});
		if (response.status < 200 || response.status > 299) {
			const failure = yield* Effect.tryPromise({
				try: () => upstreamFailure(response, idle.signal, null),
				catch: () => new ControlApiUnreachable()
			});
			idle.done();
			return yield* Effect.fail(failure);
		}
		const capped = yield* Effect.tryPromise({
			try: () => readCapped(response, idle.signal),
			catch: () => new ControlApiUnreachable()
		});
		idle.done();
		if (capped.kind === 'too_large') return yield* Effect.fail(new ControlApiTooLarge());
		const parsed = yield* Effect.try({
			try: () => JSON.parse(capped.text) as unknown,
			catch: () => new ControlApiDecodeError({ paths: ['(json)'] })
		});
		return yield* decodeWith(UploadResult)({ status: response.status, body: parsed });
	});

// --------------------------------------------------------------------------- running

/**
 * Run a client effect to a plain result. Aborting `signal` (browser navigation or tab close)
 * interrupts only the outgoing request; it never implies job cancellation.
 */
export async function runControl<A>(
	effect: Effect.Effect<{ status: number; data: A }, ControlApiFailure>,
	signal?: AbortSignal
): Promise<BffResult<A>> {
	try {
		const result = await Effect.runPromise(Effect.result(effect), signal ? { signal } : undefined);
		if (Result.isSuccess(result)) return { ok: true, status: result.success.status, data: result.success.data };
		const mapped = toBffError(result.failure);
		return { ok: false, httpStatus: mapped.httpStatus, error: mapped.error };
	} catch {
		const mapped = toBffError(new ControlApiUnreachable());
		return { ok: false, httpStatus: mapped.httpStatus, error: mapped.error };
	}
}

/** Run a streamed effect; failures become BFF JSON errors. */
export async function runStream(
	effect: Effect.Effect<StreamedResponse, ControlApiFailure>,
	signal?: AbortSignal
): Promise<{ ok: true; value: StreamedResponse } | { ok: false; httpStatus: number; error: BffError }> {
	try {
		const result = await Effect.runPromise(Effect.result(effect), signal ? { signal } : undefined);
		if (Result.isSuccess(result)) return { ok: true, value: result.success };
		const mapped = toBffError(result.failure);
		return { ok: false, httpStatus: mapped.httpStatus, error: mapped.error };
	} catch {
		const mapped = toBffError(new ControlApiUnreachable());
		return { ok: false, httpStatus: mapped.httpStatus, error: mapped.error };
	}
}
