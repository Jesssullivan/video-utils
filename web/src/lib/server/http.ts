// BFF request guards and response helpers (WEB_UI_S2.md section 5). Server-only.
import { json } from '@sveltejs/kit';
import type { BffError } from '$lib/control-types';
import { makeBffError, type BffResult, type StreamedResponse } from './control-client';

export const NO_STORE = { 'cache-control': 'no-store' } as const;
export const MAX_JSON_BODY = 16 * 1024;

export function errorResponse(httpStatus: number, error: BffError): Response {
	return json(error, { status: httpStatus, headers: NO_STORE });
}

export function resultResponse<A>(result: BffResult<A>): Response {
	return result.ok
		? json(result.data, { status: result.status, headers: NO_STORE })
		: errorResponse(result.httpStatus, result.error);
}

export function streamResponse(
	result: { ok: true; value: StreamedResponse } | { ok: false; httpStatus: number; error: BffError }
): Response {
	return result.ok
		? new Response(result.value.body, { status: result.value.status, headers: result.value.headers })
		: errorResponse(result.httpStatus, result.error);
}

export const LOOPBACK_HOST = /^(127\.0\.0\.1|\[::1\]|localhost)(:[0-9]{1,5})?$/;

/**
 * Mutations must come from this app: an `Origin` equal to the app origin, or (when the browser
 * sends no Origin) `Sec-Fetch-Site: same-origin`. A mismatched Origin is never rescued.
 * adapter-node reports `url.origin` as https unless ORIGIN is set, so `http://<Host>` is also the app
 * origin when Host is a loopback host (hooks.server.ts refuses any other Host, defeating DNS rebinding).
 */
export function crossOriginRefusal(request: Request, url: URL): Response | null {
	const origin = request.headers.get('origin');
	const host = request.headers.get('host') ?? '';
	const appOrigins = new Set([url.origin]);
	if (LOOPBACK_HOST.test(host)) appOrigins.add(`http://${host}`);
	const allowed = origin !== null ? appOrigins.has(origin) : request.headers.get('sec-fetch-site') === 'same-origin';
	if (allowed) return null;
	const { httpStatus, error } = makeBffError(403, 'bff_cross_origin_refused', 'Mutating requests must come from this app (same origin).');
	return errorResponse(httpStatus, error);
}

/** Bounded strict JSON object body; refusals never reach the control API. */
export async function readJsonObject(
	request: Request
): Promise<{ ok: true; value: Record<string, unknown> } | { ok: false; response: Response }> {
	const type = (request.headers.get('content-type') ?? '').split(';', 1)[0].trim().toLowerCase();
	if (type !== 'application/json') {
		const { httpStatus, error } = makeBffError(415, 'bff_content_type_refused', 'Content-Type must be application/json.');
		return { ok: false, response: errorResponse(httpStatus, error) };
	}
	const declared = Number(request.headers.get('content-length') ?? 'NaN');
	const tooLarge = () => {
		const { httpStatus, error } = makeBffError(413, 'bff_body_too_large', `JSON body exceeds ${MAX_JSON_BODY} bytes.`);
		return { ok: false as const, response: errorResponse(httpStatus, error) };
	};
	if (Number.isFinite(declared) && declared > MAX_JSON_BODY) return tooLarge();
	let text = '';
	if (request.body) {
		const reader = request.body.getReader();
		const chunks: Uint8Array[] = [];
		let total = 0;
		for (;;) {
			const { done, value } = await reader.read();
			if (done) break;
			total += value.byteLength;
			if (total > MAX_JSON_BODY) {
				await reader.cancel().catch(() => undefined);
				return tooLarge();
			}
			chunks.push(value);
		}
		const merged = new Uint8Array(total);
		let offset = 0;
		for (const chunk of chunks) {
			merged.set(chunk, offset);
			offset += chunk.byteLength;
		}
		text = new TextDecoder('utf-8', { fatal: false }).decode(merged);
	}
	try {
		const value: unknown = JSON.parse(text);
		if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
			return { ok: true, value: value as Record<string, unknown> };
		}
	} catch {
		// fall through to the typed refusal
	}
	const { httpStatus, error } = makeBffError(400, 'invalid_request', 'Request body must be a JSON object.');
	return { ok: false, response: errorResponse(httpStatus, error) };
}

export function invalidRequest(message: string): Response {
	const { httpStatus, error } = makeBffError(400, 'invalid_request', message);
	return errorResponse(httpStatus, error);
}
