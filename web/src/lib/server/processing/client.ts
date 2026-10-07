// Lane-local server-only transport for the S3 processing routes. It mirrors the S2 rules of
// $lib/server/control-client.ts (loopback URL + bearer token from config.ts, no redirects, no
// browser credentials, 1 MiB body cap counted while streaming, typed failures mapped to the
// same BFF codes, upstream `error` text never surfaced). The shared requestJson/decodeWith are
// not exported (root-owned; export requested), so this module repeats the minimal transport.
import { Duration, Effect, Schema, SchemaIssue } from 'effect';
import {
	ControlApiDecodeError,
	ControlApiHttpError,
	ControlApiRefused,
	ControlApiRefusedHost,
	ControlApiTimeout,
	ControlApiTokenRefused,
	ControlApiTooLarge,
	ControlApiUnauthenticated,
	ControlApiUnconfigured,
	ControlApiUnreachable,
	InvalidId,
	NotFound,
	type ControlApiFailure,
	type StreamedResponse
} from '$lib/server/control-client';
import { readControlApiConfig } from '$lib/server/config';
import {
	JobTypes,
	LANE_FIELD_NAMES,
	LaneJobList,
	LaneJobProjection,
	MEDIA_ROLES,
	Measurement,
	REVIEW_ID_PATTERN,
	RUN_ID_PATTERN,
	ReviewList,
	ReviewRecord,
	RunList
} from './schema';

export const READ_TIMEOUT_MS = 5000;
// Capture writes, measurements and job submissions re-hash source/PCM bytes upstream.
export const WRITE_TIMEOUT_MS = 30_000;
export const RESPONSE_CAP_BYTES = 1_048_576;
export const STREAM_IDLE_TIMEOUT_MS = 30_000;
const UPSTREAM_CODE = /^[a-z_]{1,64}$/;
const ART_ID = /^art_[0-9a-f]{32}$/;
const JOB_ID = /^job_[0-9a-f]{32}$/;
const PASS_THROUGH = ['content-type', 'content-length', 'x-artifact-sha256', 'content-disposition'] as const;

type Config = { readonly baseUrl: string; readonly token: string };
type ConfigFailure = ControlApiUnconfigured | ControlApiRefusedHost | ControlApiUnauthenticated;

const config: Effect.Effect<Config, ConfigFailure> = Effect.suspend((): Effect.Effect<Config, ConfigFailure> => {
	const value = readControlApiConfig();
	switch (value.kind) {
		case 'configured':
			return Effect.succeed({ baseUrl: value.baseUrl, token: value.token });
		case 'unconfigured':
			return Effect.fail(new ControlApiUnconfigured());
		case 'refused':
			return Effect.fail(new ControlApiRefusedHost());
		case 'unauthenticated':
			return Effect.fail(new ControlApiUnauthenticated());
	}
});

async function readCapped(response: Response, cap: number): Promise<string | null> {
	const declared = Number(response.headers.get('content-length') ?? 'NaN');
	if (Number.isFinite(declared) && declared > cap) {
		await response.body?.cancel().catch(() => undefined);
		return null;
	}
	if (!response.body) return '';
	const reader = response.body.getReader();
	const chunks: Uint8Array[] = [];
	let total = 0;
	for (;;) {
		const { done, value } = await reader.read();
		if (done) break;
		total += value.byteLength;
		if (total > cap) {
			await reader.cancel().catch(() => undefined);
			return null;
		}
		chunks.push(value);
	}
	const merged = new Uint8Array(total);
	let offset = 0;
	for (const chunk of chunks) {
		merged.set(chunk, offset);
		offset += chunk.byteLength;
	}
	return new TextDecoder('utf-8', { fatal: false }).decode(merged);
}

function typedCodes(text: string | null): { code: string | null; detail: string | null } {
	if (text === null) return { code: null, detail: null };
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

const NOT_FOUND: Record<string, 'job' | 'source' | 'artifact'> = {
	unknown_job: 'job',
	unknown_source: 'source',
	unknown_artifact: 'artifact'
};

async function failureOf(response: Response): Promise<ControlApiFailure> {
	const { code, detail } = typedCodes(await readCapped(response, 65_536).catch(() => null));
	const status = response.status;
	if (status === 401) return new ControlApiTokenRefused();
	if (status === 404 && code !== null && code in NOT_FOUND) return new NotFound({ kind: NOT_FOUND[code], upstreamCode: code });
	if (status >= 400 && status <= 499 && code !== null && code !== 'route_not_found' && code !== 'method_not_allowed') {
		return new ControlApiRefused({ upstreamStatus: status, upstreamCode: code, upstreamDetailCode: detail });
	}
	return new ControlApiHttpError({ upstreamStatus: status, upstreamCode: code, upstreamDetailCode: detail });
}

function sanitize(segment: unknown): string {
	const key = typeof segment === 'object' && segment !== null && 'key' in segment ? (segment as { key: unknown }).key : segment;
	if (typeof key === 'number' && Number.isInteger(key)) return String(key);
	if (typeof key === 'string' && /^[0-9]{1,4}$/.test(key)) return key;
	if (typeof key === 'string' && LANE_FIELD_NAMES.has(key)) return key;
	return '<unexpected_key>';
}

const formatter = SchemaIssue.makeFormatterStandardSchemaV1();
const DECODE_OPTIONS = { onExcessProperty: 'error', errors: 'all' } as const;

function request<S extends Schema.Top>(
	method: 'GET' | 'POST',
	path: string,
	schema: S,
	body?: unknown,
	timeoutMs = READ_TIMEOUT_MS
): Effect.Effect<{ status: number; data: S['Type'] }, ControlApiFailure> {
	return Effect.gen(function* () {
		const { baseUrl, token } = yield* config;
		const outcome = yield* Effect.gen(function* () {
			const response = yield* Effect.tryPromise({
				try: (signal) =>
					fetch(`${baseUrl}${path}`, {
						method,
						signal,
						redirect: 'manual',
						credentials: 'omit',
						headers: {
							accept: 'application/json',
							authorization: `Bearer ${token}`,
							...(body !== undefined ? { 'content-type': 'application/json' } : {})
						},
						body: body !== undefined ? JSON.stringify(body) : undefined
					}),
				catch: () => new ControlApiUnreachable()
			});
			if (response.status < 200 || response.status > 299) {
				const failure = yield* Effect.tryPromise({ try: () => failureOf(response), catch: () => new ControlApiUnreachable() });
				return yield* Effect.fail(failure);
			}
			const text = yield* Effect.tryPromise({ try: () => readCapped(response, RESPONSE_CAP_BYTES), catch: () => new ControlApiUnreachable() });
			if (text === null) return yield* Effect.fail(new ControlApiTooLarge());
			return { status: response.status, text };
		}).pipe(
			Effect.timeoutOrElse({
				duration: Duration.millis(timeoutMs),
				orElse: () => Effect.fail(new ControlApiTimeout({ idle: false }))
			})
		);
		const parsed = yield* Effect.try({
			try: () => JSON.parse(outcome.text) as unknown,
			catch: () => new ControlApiDecodeError({ paths: ['(json)'] })
		});
		const data = yield* Schema.decodeUnknownEffect(schema as never)(parsed, DECODE_OPTIONS).pipe(
			Effect.mapError((error) => {
				const issues = formatter((error as Schema.SchemaError).issue).issues;
				const paths = issues.map((issue) => (issue.path ?? []).map(sanitize).join('.') || '(root)');
				return new ControlApiDecodeError({ paths: [...new Set(paths)].slice(0, 16) });
			})
		);
		return { status: outcome.status, data: data as S['Type'] };
	});
}

const requireSource = (id: string) => (ART_ID.test(id) ? Effect.void : Effect.fail(new InvalidId({ kind: 'source' })));
const requireJob = (id: string) => (JOB_ID.test(id) ? Effect.void : Effect.fail(new InvalidId({ kind: 'job' })));

// --------------------------------------------------------------------------- operations

export const getJobTypes = request('GET', '/api/v1/job-types', JobTypes);

export const listRuns = (sourceId: string) =>
	requireSource(sourceId).pipe(Effect.andThen(request('GET', `/api/v1/sources/${sourceId}/runs`, RunList)));

export const listReviews = (sourceId: string) =>
	requireSource(sourceId).pipe(Effect.andThen(request('GET', `/api/v1/sources/${sourceId}/capture-reviews`, ReviewList)));

export const createReview = (sourceId: string, body: Record<string, unknown>) =>
	requireSource(sourceId).pipe(
		Effect.andThen(request('POST', `/api/v1/sources/${sourceId}/capture-reviews`, ReviewRecord, body, WRITE_TIMEOUT_MS))
	);

export const measureInterval = (sourceId: string, body: { run_id: string; start_seconds: number; end_seconds: number }) =>
	requireSource(sourceId).pipe(
		Effect.andThen(request('POST', `/api/v1/sources/${sourceId}/capture-measurements`, Measurement, body, WRITE_TIMEOUT_MS))
	);

export const listLaneJobs = (sourceId: string) =>
	requireSource(sourceId).pipe(
		Effect.andThen(request('GET', `/api/v1/jobs?source_artifact_id=${sourceId}&limit=200`, LaneJobList))
	);

export const getLaneJob = (jobId: string) =>
	requireJob(jobId).pipe(Effect.andThen(request('GET', `/api/v1/jobs/${jobId}`, LaneJobProjection)));

export const submitProcessingJob = (body: Record<string, unknown>) =>
	request('POST', '/api/v1/jobs', LaneJobProjection, body, WRITE_TIMEOUT_MS);

/** Stream a bound run's re-hashed WAV for span audition (30 s idle timeout, no total cap). */
export const openRunMedia = (runId: string, role: string, signal?: AbortSignal) =>
	Effect.gen(function* () {
		if (!RUN_ID_PATTERN.test(runId) || !(MEDIA_ROLES as ReadonlyArray<string>).includes(role)) {
			return yield* Effect.fail(new InvalidId({ kind: 'artifact' }));
		}
		const { baseUrl, token } = yield* config;
		const controller = new AbortController();
		signal?.addEventListener('abort', () => controller.abort(), { once: true });
		let timer: ReturnType<typeof setTimeout> | undefined = setTimeout(() => controller.abort(), STREAM_IDLE_TIMEOUT_MS);
		const touch = () => {
			clearTimeout(timer);
			timer = setTimeout(() => controller.abort(), STREAM_IDLE_TIMEOUT_MS);
		};
		const response = yield* Effect.tryPromise({
			try: () =>
				fetch(`${baseUrl}/api/v1/runs/${runId}/media/${role}`, {
					method: 'GET',
					signal: controller.signal,
					redirect: 'manual',
					credentials: 'omit',
					headers: { authorization: `Bearer ${token}` }
				}),
			catch: () => new ControlApiUnreachable()
		});
		if (response.status !== 200) {
			clearTimeout(timer);
			return yield* Effect.fail(yield* Effect.tryPromise({ try: () => failureOf(response), catch: () => new ControlApiUnreachable() }));
		}
		const headers = new Headers({ 'cache-control': 'no-store', 'x-content-type-options': 'nosniff', 'accept-ranges': 'none' });
		for (const name of PASS_THROUGH) {
			const value = response.headers.get(name);
			if (value !== null) headers.set(name, value);
		}
		const reader = response.body?.getReader() ?? null;
		const body =
			reader === null
				? null
				: new ReadableStream<Uint8Array>({
						async pull(stream) {
							try {
								const { done, value } = await reader.read();
								if (done) {
									clearTimeout(timer);
									stream.close();
									return;
								}
								touch();
								stream.enqueue(value);
							} catch (error) {
								clearTimeout(timer);
								stream.error(error);
							}
						},
						cancel() {
							clearTimeout(timer);
							void reader.cancel().catch(() => undefined);
						}
					});
		return { status: 200, headers, body } satisfies StreamedResponse;
	});

export const isReviewId = (value: string): boolean => REVIEW_ID_PATTERN.test(value);
export const isRunId = (value: string): boolean => RUN_ID_PATTERN.test(value);
