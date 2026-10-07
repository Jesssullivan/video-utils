// Cloudflare Access application-token verification (AUTH_HOSTING_S3.md section 4.3).
// Estate pattern: tinyland-inc/massage-ithaca-portal src/lib/server/auth/cf-access.ts (jose) and
// great-falls-tool-bus-infra docs/runbooks/cf-access-tsidp.md (tsidp federated INTO Access, so the
// app only ever sees an Access JWT). This module uses node:crypto instead of jose because
// web/package.json is not lane-owned (no new dependency).
//
// Deny by default, never throws to the caller, no development bypass. The plaintext
// `Cf-Access-Authenticated-User-Email` header and the `CF_Authorization` cookie are never read.
// Failure reasons are for server-side tests/logs only and are never sent to clients.

import { createPublicKey, verify as cryptoVerify } from 'node:crypto';

export const CF_ACCESS_JWT_HEADER = 'cf-access-jwt-assertion';
export const MAX_ASSERTION_BYTES = 8 * 1024;
export const CLOCK_SKEW_SECONDS = 60;
export const MIN_RSA_MODULUS_BITS = 2048;

export const JWKS_FETCH_TIMEOUT_MS = 5_000;
export const JWKS_MAX_BODY_BYTES = 64 * 1024;
export const JWKS_FRESH_TTL_MS = 10 * 60 * 1000;
export const JWKS_REFETCH_COOLDOWN_MS = 30 * 1000;
export const JWKS_MAX_STALE_MS = 60 * 60 * 1000;
const MAX_KID_LENGTH = 256;
const MAX_SHARED_CACHES = 4;

const SEGMENT = /^[A-Za-z0-9_-]+$/;

/**
 * @typedef {import('node:crypto').KeyObject} KeyObject
 * @typedef {(kid: string) => Promise<KeyObject | null>} KeyResolver
 * @typedef {(input: string, init: RequestInit) => Promise<Response>} FetchLike
 * @typedef {{ ok: true, email: string, exp: number } | { ok: false, reason: string }} VerifyResult
 */

/**
 * @param {string} segment
 * @returns {Record<string, unknown> | null}
 */
function decodeJsonSegment(segment) {
	try {
		const value = JSON.parse(Buffer.from(segment, 'base64url').toString('utf8'));
		return typeof value === 'object' && value !== null && !Array.isArray(value) ? value : null;
	} catch {
		return null;
	}
}

/**
 * @param {unknown} value
 * @returns {value is number}
 */
function isFiniteNumber(value) {
	return typeof value === 'number' && Number.isFinite(value);
}

/**
 * Verify one `Cf-Access-Jwt-Assertion` value.
 * @param {string | null | undefined} token
 * @param {{ issuer: string, auds: readonly string[], resolveKey: KeyResolver, nowSeconds: number }} options
 * @returns {Promise<VerifyResult>}
 */
export async function verifyAccessAssertion(token, options) {
	try {
		return await verifyUnsafe(token, options);
	} catch {
		return { ok: false, reason: 'verifier_error' };
	}
}

/**
 * @param {string | null | undefined} token
 * @param {{ issuer: string, auds: readonly string[], resolveKey: KeyResolver, nowSeconds: number }} options
 * @returns {Promise<VerifyResult>}
 */
async function verifyUnsafe(token, { issuer, auds, resolveKey, nowSeconds }) {
	if (typeof token !== 'string' || token === '') return { ok: false, reason: 'assertion_missing' };
	if (Buffer.byteLength(token, 'utf8') > MAX_ASSERTION_BYTES) return { ok: false, reason: 'assertion_too_large' };
	const parts = token.split('.');
	if (parts.length !== 3 || !parts.every((part) => SEGMENT.test(part))) {
		return { ok: false, reason: 'assertion_malformed' };
	}
	const [headerSegment, payloadSegment, signatureSegment] = parts;
	const header = decodeJsonSegment(headerSegment);
	const payload = decodeJsonSegment(payloadSegment);
	if (header === null || payload === null) return { ok: false, reason: 'assertion_malformed' };

	// Only RS256: refuses `none`, HS* (public-key-as-HMAC-secret confusion), ES*, PS*.
	if (header.alg !== 'RS256') return { ok: false, reason: 'alg_refused' };
	if ('crit' in header) return { ok: false, reason: 'crit_refused' };
	const kid = header.kid;
	if (typeof kid !== 'string' || kid === '' || kid.length > MAX_KID_LENGTH) return { ok: false, reason: 'kid_missing' };

	const key = await resolveKey(kid);
	if (key === null) return { ok: false, reason: 'kid_unresolved' };
	const signature = Buffer.from(signatureSegment, 'base64url');
	const signed = Buffer.from(`${headerSegment}.${payloadSegment}`, 'ascii');
	if (!cryptoVerify('sha256', signed, key, signature)) return { ok: false, reason: 'signature_invalid' };

	if (payload.iss !== issuer) return { ok: false, reason: 'iss_mismatch' };
	const audClaim = payload.aud;
	const tokenAuds = typeof audClaim === 'string' ? [audClaim] : Array.isArray(audClaim) ? audClaim : [];
	// Case-sensitive: an Access AUD is an opaque identifier and is never case-folded.
	if (!tokenAuds.some((aud) => typeof aud === 'string' && auds.includes(aud))) return { ok: false, reason: 'aud_mismatch' };

	if (!isFiniteNumber(payload.exp)) return { ok: false, reason: 'exp_missing' };
	if (!(nowSeconds < payload.exp + CLOCK_SKEW_SECONDS)) return { ok: false, reason: 'expired' };
	for (const claim of ['nbf', 'iat']) {
		if (claim in payload) {
			const value = payload[claim];
			if (!isFiniteNumber(value) || value > nowSeconds + CLOCK_SKEW_SECONDS) return { ok: false, reason: `${claim}_in_future` };
		}
	}

	const email = payload.email;
	if (typeof email !== 'string' || email === '') return { ok: false, reason: 'email_missing' };
	return { ok: true, email: email.toLowerCase(), exp: payload.exp };
}

/**
 * Release an unread response body. An unconsumed, paused undici body whose socket then closes trips
 * an internal assertion that crashes the process (AUTH_TOKEN_S3 E13), so every early exit cancels it.
 * @param {Response} response
 */
async function discardBody(response) {
	await response.body?.cancel().catch(() => undefined);
}

/**
 * Read a response body with a hard byte cap.
 * @param {Response} response
 * @param {number} cap
 * @returns {Promise<string | null>}
 */
async function readCapped(response, cap) {
	const declared = Number(response.headers.get('content-length') ?? 'NaN');
	if (Number.isFinite(declared) && declared > cap) {
		await discardBody(response);
		return null;
	}
	if (!response.body) return '';
	const reader = response.body.getReader();
	/** @type {Uint8Array[]} */
	const chunks = [];
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
	return Buffer.concat(chunks).toString('utf8');
}

/**
 * Parse a JWKS document, keeping only usable RSA signing keys that carry a `kid`.
 * @param {string} text
 * @returns {Map<string, KeyObject>}
 */
export function parseJwks(text) {
	/** @type {Map<string, KeyObject>} */
	const keys = new Map();
	/** @type {unknown} */
	let doc;
	try {
		doc = JSON.parse(text);
	} catch {
		return keys;
	}
	const list = typeof doc === 'object' && doc !== null ? /** @type {{ keys?: unknown }} */ (doc).keys : undefined;
	if (!Array.isArray(list)) return keys;
	for (const jwk of list) {
		if (typeof jwk !== 'object' || jwk === null) continue;
		const { kty, kid, use, alg, n, e } = /** @type {Record<string, unknown>} */ (jwk);
		if (kty !== 'RSA' || typeof kid !== 'string' || kid === '' || kid.length > MAX_KID_LENGTH) continue;
		if (use !== undefined && use !== 'sig') continue;
		if (alg !== undefined && alg !== 'RS256') continue;
		if (typeof n !== 'string' || typeof e !== 'string') continue;
		try {
			const key = createPublicKey({ key: { kty: 'RSA', n, e }, format: 'jwk' });
			const bits = key.asymmetricKeyDetails?.modulusLength ?? 0;
			if (key.asymmetricKeyType === 'rsa' && bits >= MIN_RSA_MODULUS_BITS) keys.set(kid, key);
		} catch {
			// unusable key material is skipped, never fatal
		}
	}
	return keys;
}

/**
 * JWKS cache for one Access team. Fresh for 10 min; an unknown kid triggers at most one refetch per
 * 30 s cooldown; when a refresh fails, keys from the last successful fetch stay usable until they are
 * 60 min old; no successful fetch ever = deny. `fetch` and the clock are injectable for tests.
 * @param {{ jwksUrl: string, fetchImpl?: FetchLike, nowMs?: () => number }} options
 */
export function createJwksCache({ jwksUrl, fetchImpl, nowMs }) {
	const doFetch = fetchImpl ?? /** @type {FetchLike} */ (globalThis.fetch);
	const clock = nowMs ?? Date.now;
	/** @type {Map<string, KeyObject>} */
	let keys = new Map();
	/** @type {number | null} */
	let fetchedAt = null;
	/** @type {number | null} */
	let lastAttemptAt = null;
	/** @type {Promise<void> | null} */
	let inflight = null;
	const stats = { fetches: 0, failures: 0 };

	async function refresh() {
		lastAttemptAt = clock();
		stats.fetches += 1;
		try {
			const response = await doFetch(jwksUrl, {
				method: 'GET',
				redirect: 'error',
				headers: { accept: 'application/json' },
				signal: AbortSignal.timeout(JWKS_FETCH_TIMEOUT_MS)
			});
			if (!response.ok) {
				await discardBody(response);
				throw new Error('jwks_http_status');
			}
			const text = await readCapped(response, JWKS_MAX_BODY_BYTES);
			if (text === null) throw new Error('jwks_too_large');
			const parsed = parseJwks(text);
			if (parsed.size === 0) throw new Error('jwks_no_usable_keys');
			keys = parsed;
			fetchedAt = clock();
		} catch {
			stats.failures += 1;
		}
	}

	function maybeRefresh() {
		if (inflight) return inflight;
		const now = clock();
		if (lastAttemptAt !== null && now - lastAttemptAt < JWKS_REFETCH_COOLDOWN_MS) return Promise.resolve();
		inflight = refresh().finally(() => {
			inflight = null;
		});
		return inflight;
	}

	/** @param {string} kid */
	function lookup(kid) {
		if (fetchedAt === null) return null;
		if (clock() - fetchedAt >= JWKS_MAX_STALE_MS) return null;
		return keys.get(kid) ?? null;
	}

	/** @type {KeyResolver} */
	async function resolveKey(kid) {
		const fresh = fetchedAt !== null && clock() - fetchedAt < JWKS_FRESH_TTL_MS;
		if (fresh && keys.has(kid)) return keys.get(kid) ?? null;
		// Expired, never fetched, or an unknown kid while fresh: one (cooldown-bounded) refetch.
		await maybeRefresh();
		return lookup(kid);
	}

	return { resolveKey, stats };
}

// Process-wide registry. serve.js (tailnet mode) gates with the source copy of this module and the
// built hooks gate with the bundled copy; keying the registry on a global symbol keeps ONE cache per
// team domain across both copies, so a JWKS document is fetched once, not once per copy.
const SHARED_CACHES_KEY = Symbol.for('video-utils.cf-access.jwks-caches');
/** @type {Map<string, ReturnType<typeof createJwksCache>>} */
const sharedCaches = (/** @type {any} */ (globalThis)[SHARED_CACHES_KEY] ??= new Map());

/**
 * The process-wide JWKS cache for a team domain (one per domain, shared across module copies).
 * @param {string} teamDomain
 * @param {string} jwksUrl
 */
export function sharedJwksCache(teamDomain, jwksUrl) {
	const existing = sharedCaches.get(teamDomain);
	if (existing) return existing;
	if (sharedCaches.size >= MAX_SHARED_CACHES) sharedCaches.clear();
	const cache = createJwksCache({ jwksUrl });
	sharedCaches.set(teamDomain, cache);
	return cache;
}
