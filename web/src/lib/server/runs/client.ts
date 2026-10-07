// Server-only Effect client for the S3 runs read API (scripts/web_runs_api.py, ROUTES_REVIEW_S3.md section 5).
// `requestJson` in control-client.ts is module-private, so this module keeps an equivalent bounded fetch:
// 5 s whole-request timeout, a 4 MiB JSON cap counted while streaming (layers can exceed the 1 MiB default),
// a 30 s streaming idle timeout, the same bearer header and loopback config, no redirects, no retries.
// Failures reuse the control-client error classes, so `runControl`/`runStream`/`toBffError` map them to the
// same stable BFF codes. Upstream `error` text never leaves this module; only ^[a-z_]{1,64}$ codes are kept.
import { Duration, Effect, Schema, SchemaIssue } from 'effect';
import { readControlApiConfig, type ControlApiConfig } from '$lib/server/config';
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
	type ControlApiFailure,
	type StreamedResponse
} from '$lib/server/control-client';
import { JobList, KNOWN_FIELD_NAMES } from '$lib/schema/control';
import { Capabilities, KNOWN_RUN_FIELD_NAMES, RunGraph, RunLayers, RunList, isEvidenceId, isMediaName } from './schema';

export const RUNS_REQUEST_TIMEOUT_MS = 5000;
export const RUNS_RESPONSE_CAP_BYTES = 4 * 1_048_576;
export const RUNS_STREAM_IDLE_TIMEOUT_MS = 30_000;
const UPSTREAM_CODE = /^[a-z_]{1,64}$/;
const RUN_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const ARTIFACT_ID = /^art_[0-9a-f]{32}$/;
const PASS_THROUGH_HEADERS = ['content-type', 'content-length', 'x-artifact-sha256', 'content-disposition'] as const;

export const isRunIdText = (value: string): boolean => RUN_ID.test(value) && !value.includes('.partial');

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

type Capped = { readonly kind: 'ok'; readonly text: string } | { readonly kind: 'too_large' };

async function readCapped(response: Response, signal: AbortSignal, cap: number): Promise<Capped> {
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

/** Non-2xx upstream -> exactly one failure. Typed 4xx refusals keep their status and code (e.g. 404 unknown_run). */
async function upstreamFailure(response: Response, signal: AbortSignal): Promise<ControlApiFailure> {
	const capped = await readCapped(response, signal, 65_536).catch(() => ({ kind: 'too_large' }) as Capped);
	const { code, detail } = capped.kind === 'ok' ? typedCodes(capped.text) : { code: null, detail: null };
	const status = response.status;
	if (status === 401) return new ControlApiTokenRefused();
	if (status >= 400 && status <= 499 && code !== null && code !== 'route_not_found' && code !== 'method_not_allowed') {
		return new ControlApiRefused({ upstreamStatus: status, upstreamCode: code, upstreamDetailCode: detail });
	}
	return new ControlApiHttpError({ upstreamStatus: status, upstreamCode: code, upstreamDetailCode: detail });
}

const requestJson = (path: string) =>
	Effect.gen(function* () {
		const { baseUrl, token } = yield* Effect.suspend(() => configEffect(readControlApiConfig()));
		const outcome = yield* Effect.gen(function* () {
			const response = yield* Effect.tryPromise({
				try: (signal) =>
					fetch(`${baseUrl}${path}`, {
						method: 'GET',
						signal,
						redirect: 'manual',
						credentials: 'omit',
						headers: { accept: 'application/json', authorization: `Bearer ${token}` }
					}),
				catch: () => new ControlApiUnreachable()
			});
			if (response.status < 200 || response.status > 299) {
				const failure = yield* Effect.tryPromise({
					try: (signal) => upstreamFailure(response, signal),
					catch: () => new ControlApiUnreachable()
				});
				return yield* Effect.fail(failure);
			}
			const capped = yield* Effect.tryPromise({
				try: (signal) => readCapped(response, signal, RUNS_RESPONSE_CAP_BYTES),
				catch: () => new ControlApiUnreachable()
			});
			if (capped.kind === 'too_large') return yield* Effect.fail(new ControlApiTooLarge());
			return { status: response.status, text: capped.text };
		}).pipe(
			Effect.timeoutOrElse({
				duration: Duration.millis(RUNS_REQUEST_TIMEOUT_MS),
				orElse: () => Effect.fail(new ControlApiTimeout({ idle: false }))
			})
		);
		const parsed = yield* Effect.try({
			try: () => JSON.parse(outcome.text) as unknown,
			catch: () => new ControlApiDecodeError({ paths: ['(json)'] })
		});
		return { status: outcome.status, body: parsed };
	});

/** Keep only schema-known field names and indexes in issue paths; never echo upstream text or values. */
function sanitizePathSegment(segment: unknown): string {
	const key = typeof segment === 'object' && segment !== null && 'key' in segment ? (segment as { key: unknown }).key : segment;
	if (typeof key === 'number' && Number.isInteger(key)) return String(key);
	if (typeof key === 'string' && /^[0-9]{1,4}$/.test(key)) return key;
	if (typeof key === 'string' && (KNOWN_RUN_FIELD_NAMES.has(key) || KNOWN_FIELD_NAMES.has(key))) return key;
	return '<unexpected_key>';
}

const formatter = SchemaIssue.makeFormatterStandardSchemaV1();

function issuePaths(error: Schema.SchemaError): string[] {
	const paths = formatter(error.issue).issues.map((issue) => (issue.path ?? []).map(sanitizePathSegment).join('.') || '(root)');
	return [...new Set(paths)].slice(0, 16);
}

const DECODE_OPTIONS = { onExcessProperty: 'error', errors: 'all' } as const;

function decodeWith<S extends Schema.Top>(schema: S) {
	return (outcome: { status: number; body: unknown }) =>
		Schema.decodeUnknownEffect(schema as never)(outcome.body, DECODE_OPTIONS).pipe(
			Effect.map((data) => ({ status: outcome.status, data: data as S['Type'] })),
			Effect.mapError((error) => new ControlApiDecodeError({ paths: issuePaths(error as Schema.SchemaError) }))
		);
}

// IDs are validated before any upstream request. A run or evidence ID outside its pattern is reported as an
// invalid artifact-kind ID only where no route-level matcher already refused it (routes use [id=runid]).
const requireRunId = (runId: string) => (isRunIdText(runId) ? Effect.void : Effect.fail(new InvalidId({ kind: 'artifact' })));

// --------------------------------------------------------------------------- JSON reads

export const listRuns = (limit = 100) =>
	requestJson(`/api/v1/runs?limit=${Math.max(1, Math.min(500, Math.trunc(limit)))}`).pipe(Effect.flatMap(decodeWith(RunList)));

export const getRun = (runId: string) =>
	requireRunId(runId).pipe(Effect.andThen(requestJson(`/api/v1/runs/${runId}`)), Effect.flatMap(decodeWith(RunGraph)));

export const getLayers = (runId: string, evidenceId: string | null = null) =>
	requireRunId(runId).pipe(
		Effect.andThen(
			evidenceId !== null && !isEvidenceId(evidenceId) ? Effect.fail(new InvalidId({ kind: 'artifact' })) : Effect.void
		),
		Effect.andThen(requestJson(`/api/v1/runs/${runId}/layers${evidenceId ? `?evidence=${evidenceId}` : ''}`)),
		Effect.flatMap(decodeWith(RunLayers))
	);

export const getCapabilities = requestJson('/api/v1/capabilities').pipe(Effect.flatMap(decodeWith(Capabilities)));

/** The jobs index (all sources): GET /api/v1/jobs?limit=200 decoded with the existing JobList schema. */
export const listAllJobs = requestJson('/api/v1/jobs?limit=200').pipe(Effect.flatMap(decodeWith(JobList)));

// --------------------------------------------------------------------------- streamed reads

class IdleAbort {
	readonly controller = new AbortController();
	fired = false;
	private timer: ReturnType<typeof setTimeout> | undefined;
	constructor(
		private readonly ms: number,
		outer?: AbortSignal
	) {
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

const openStream = (path: string, signal?: AbortSignal) =>
	Effect.gen(function* () {
		const { baseUrl, token } = yield* Effect.suspend(() => configEffect(readControlApiConfig()));
		const idle = new IdleAbort(RUNS_STREAM_IDLE_TIMEOUT_MS, signal);
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
				try: () => upstreamFailure(response, idle.signal),
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

/** Layer media by evidence ID and media-table name only (re-hashed upstream; inline; X-Artifact-Sha256 kept). */
export const openLayerMedia = (runId: string, evidenceId: string, name: string, signal?: AbortSignal) =>
	requireRunId(runId).pipe(
		Effect.andThen(isEvidenceId(evidenceId) && isMediaName(name) ? Effect.void : Effect.fail(new InvalidId({ kind: 'artifact' }))),
		Effect.andThen(openStream(`/api/v1/runs/${runId}/layers/media/${evidenceId}/${name}`, signal))
	);

/** A run file or bound attachment file by artifact ID only (re-hashed upstream before sending). */
export const openRunArtifact = (runId: string, artifactId: string, disposition: 'inline' | 'attachment', signal?: AbortSignal) =>
	requireRunId(runId).pipe(
		Effect.andThen(ARTIFACT_ID.test(artifactId) ? Effect.void : Effect.fail(new InvalidId({ kind: 'artifact' }))),
		Effect.andThen(openStream(`/api/v1/runs/${runId}/artifacts/${artifactId}?disposition=${disposition}`, signal))
	);
