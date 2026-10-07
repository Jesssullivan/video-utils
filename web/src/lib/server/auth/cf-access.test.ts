// Cloudflare Access assertion verification with a key generated at test run time (WEB_TESTS_S3.md 5.1; W6).
// 1 accepted token, 11 refusals and 4 JWKS cache cases (16 is the AUTH_TOKEN_S3 D1 regression). No key is written anywhere; the JWKS is exported as JWK.
import { createHmac, generateKeyPairSync, sign as cryptoSign, type KeyObject } from 'node:crypto';
import { beforeAll, describe, expect, it } from 'vitest';
import {
	CLOCK_SKEW_SECONDS,
	JWKS_FRESH_TTL_MS,
	JWKS_MAX_BODY_BYTES,
	JWKS_MAX_STALE_MS,
	JWKS_REFETCH_COOLDOWN_MS,
	MAX_ASSERTION_BYTES,
	MIN_RSA_MODULUS_BITS,
	createJwksCache,
	parseJwks,
	verifyAccessAssertion
} from './cf-access.js';

const ISSUER = 'https://example-team.cloudflareaccess.com';
const JWKS_URL = `${ISSUER}/cdn-cgi/access/certs`;
const AUD = 'a'.repeat(32);
const EMAIL = 'operator@example.org';
const NOW = 1_800_000_000;
const KID = 'unit-key-1';

const b64 = (value: unknown) => Buffer.from(JSON.stringify(value)).toString('base64url');

type Claims = Record<string, unknown>;
const claims = (overrides: Claims = {}): Claims => ({ iss: ISSUER, aud: [AUD], email: EMAIL, iat: NOW - 10, nbf: NOW - 10, exp: NOW + 300, ...overrides });

let privateKey: KeyObject;
let publicKey: KeyObject;
let weakPublic: KeyObject;
let weakPrivate: KeyObject;
let jwksText: string;

function token(payload: Claims, header: Record<string, unknown> = { alg: 'RS256', kid: KID, typ: 'JWT' }, key: KeyObject = privateKey): string {
	const signed = `${b64(header)}.${b64(payload)}`;
	return `${signed}.${cryptoSign('sha256', Buffer.from(signed, 'ascii'), key).toString('base64url')}`;
}

const jwk = (key: KeyObject, kid: string) => ({ ...key.export({ format: 'jwk' }), kid, use: 'sig', alg: 'RS256' });
const resolver = (keys: Map<string, KeyObject>) => async (kid: string) => keys.get(kid) ?? null;
const verify = (assertion: string | null, keys = parseJwks(jwksText), nowSeconds = NOW) =>
	verifyAccessAssertion(assertion, { issuer: ISSUER, auds: [AUD], resolveKey: resolver(keys), nowSeconds });

beforeAll(() => {
	({ privateKey, publicKey } = generateKeyPairSync('rsa', { modulusLength: 2048 }));
	({ privateKey: weakPrivate, publicKey: weakPublic } = generateKeyPairSync('rsa', { modulusLength: 1024 }));
	jwksText = JSON.stringify({ keys: [jwk(publicKey, KID)] });
});

describe('verifyAccessAssertion: accepted', () => {
	it('1. an RS256 token signed by the run-time 2048-bit key verifies and yields the lowercased email', async () => {
		expect(MIN_RSA_MODULUS_BITS).toBe(2048);
		expect(await verify(token(claims({ email: 'Operator@Example.org' })))).toEqual({ ok: true, email: EMAIL, exp: NOW + 300 });
		// A single-string audience and the clock-skew edges are accepted too.
		expect((await verify(token(claims({ aud: AUD })))).ok).toBe(true);
		expect((await verify(token(claims({ exp: NOW - CLOCK_SKEW_SECONDS + 1 })))).ok).toBe(true);
		expect((await verify(token(claims({ nbf: NOW + CLOCK_SKEW_SECONDS })))).ok).toBe(true);
	});
});

describe('verifyAccessAssertion: refused', () => {
	const refused = async (assertion: string | null, reason: string, keys?: Map<string, KeyObject>) => {
		const result = await verify(assertion, keys);
		expect(result).toEqual({ ok: false, reason });
	};

	it('2. wrong aud', async () => {
		await refused(token(claims({ aud: ['b'.repeat(32)] })), 'aud_mismatch');
		await refused(token(claims({ aud: [AUD.toUpperCase()] })), 'aud_mismatch');
		await refused(token(claims({ aud: undefined })), 'aud_mismatch');
	});
	it('3. wrong iss', async () => {
		await refused(token(claims({ iss: 'https://other-team.cloudflareaccess.com' })), 'iss_mismatch');
		await refused(token(claims({ iss: `${ISSUER}/` })), 'iss_mismatch');
	});
	it('4. expired', async () => {
		await refused(token(claims({ exp: NOW - CLOCK_SKEW_SECONDS })), 'expired');
		await refused(token(claims({ exp: undefined })), 'exp_missing');
	});
	it('5. nbf in the future beyond the skew', async () => {
		await refused(token(claims({ nbf: NOW + CLOCK_SKEW_SECONDS + 1 })), 'nbf_in_future');
		await refused(token(claims({ iat: NOW + CLOCK_SKEW_SECONDS + 1 })), 'iat_in_future');
	});
	it('6. tampered signature or payload', async () => {
		const good = token(claims());
		const [header, payload, signature] = good.split('.');
		const flipped = signature.startsWith('A') ? `B${signature.slice(1)}` : `A${signature.slice(1)}`;
		await refused(`${header}.${payload}.${flipped}`, 'signature_invalid');
		await refused(`${header}.${b64(claims({ email: 'intruder@example.org' }))}.${signature}`, 'signature_invalid');
	});
	it('7. alg none', async () => {
		await refused(`${b64({ alg: 'none', kid: KID })}.${b64(claims())}.AAAA`, 'alg_refused');
		await refused(token(claims(), { alg: 'None', kid: KID }), 'alg_refused');
	});
	it('8. HS256 with the public key as the HMAC secret', async () => {
		const signed = `${b64({ alg: 'HS256', kid: KID })}.${b64(claims())}`;
		const secret = JSON.stringify(publicKey.export({ format: 'jwk' }));
		await refused(`${signed}.${createHmac('sha256', secret).update(signed).digest('base64url')}`, 'alg_refused');
	});
	it('9. unknown kid', async () => {
		await refused(token(claims(), { alg: 'RS256', kid: 'unit-key-2' }), 'kid_unresolved');
		await refused(token(claims(), { alg: 'RS256' }), 'kid_missing');
	});
	it(`10. a JWKS key with a modulus below ${MIN_RSA_MODULUS_BITS} bits is never usable`, async () => {
		const weakKeys = parseJwks(JSON.stringify({ keys: [jwk(weakPublic, KID)] }));
		expect(weakKeys.size).toBe(0);
		await refused(token(claims(), undefined, weakPrivate), 'kid_unresolved', weakKeys);
	});
	it(`11. an assertion above ${MAX_ASSERTION_BYTES} bytes`, async () => {
		await refused(token(claims({ padding: 'p'.repeat(MAX_ASSERTION_BYTES) })), 'assertion_too_large');
	});
	it('12. missing email', async () => {
		await refused(token(claims({ email: undefined })), 'email_missing');
		await refused(token(claims({ email: '' })), 'email_missing');
		await refused(token(claims({ email: 42 })), 'email_missing');
	});
	it('also refuses a missing or malformed assertion and a crit header, and never throws', async () => {
		for (const missing of [null, undefined, '']) expect(await verifyAccessAssertion(missing, { issuer: ISSUER, auds: [AUD], resolveKey: resolver(new Map()), nowSeconds: NOW })).toEqual({ ok: false, reason: 'assertion_missing' });
		await refused('a.b', 'assertion_malformed');
		await refused('a.b.c.d', 'assertion_malformed');
		await refused('not base64!.b.c', 'assertion_malformed');
		await refused(token(claims(), { alg: 'RS256', kid: KID, crit: ['exp'] }), 'crit_refused');
		const throwing = await verifyAccessAssertion(token(claims()), { issuer: ISSUER, auds: [AUD], nowSeconds: NOW, resolveKey: async () => { throw new Error('resolver failure'); } });
		expect(throwing).toEqual({ ok: false, reason: 'verifier_error' });
	});
});

describe('parseJwks', () => {
	it('keeps only RSA signing keys with a kid and tolerates junk', () => {
		const good = jwk(publicKey, KID);
		expect([...parseJwks(jwksText).keys()]).toEqual([KID]);
		expect(parseJwks('not json').size).toBe(0);
		expect(parseJwks('{}').size).toBe(0);
		expect(parseJwks(JSON.stringify({ keys: [null, 7, { ...good, kid: '' }, { ...good, use: 'enc' }, { ...good, alg: 'RS512' }, { ...good, kty: 'EC' }, { ...good, n: 'AQAB' }] })).size).toBe(0);
	});
});

describe('createJwksCache', () => {
	function harness() {
		const state = { now: 1_000_000, fail: false, calls: 0 };
		const fetchImpl = async (input: string, init: RequestInit) => {
			state.calls += 1;
			expect(input).toBe(JWKS_URL);
			expect(init.redirect).toBe('error');
			if (state.fail) throw new Error('network down');
			return new Response(jwksText, { status: 200, headers: { 'content-type': 'application/json' } });
		};
		const cache = createJwksCache({ jwksUrl: JWKS_URL, fetchImpl, nowMs: () => state.now });
		return { state, cache };
	}

	it('13. a fresh hit does not refetch', async () => {
		const { state, cache } = harness();
		expect(await cache.resolveKey(KID)).not.toBeNull();
		expect(state.calls).toBe(1);
		state.now += JWKS_FRESH_TTL_MS - 1;
		expect(await cache.resolveKey(KID)).not.toBeNull();
		expect(await cache.resolveKey(KID)).not.toBeNull();
		expect(state.calls).toBe(1);
		// An unknown kid while fresh triggers at most one refetch per cooldown.
		state.now = 1_000_000 + JWKS_REFETCH_COOLDOWN_MS;
		expect(await cache.resolveKey('unit-key-2')).toBeNull();
		expect(await cache.resolveKey('unit-key-2')).toBeNull();
		expect(state.calls).toBe(2);
	});

	it('14. keys from the last successful fetch stay usable within JWKS_MAX_STALE_MS when a refresh fails', async () => {
		const { state, cache } = harness();
		expect(await cache.resolveKey(KID)).not.toBeNull();
		state.fail = true;
		state.now += JWKS_MAX_STALE_MS - 1;
		const key = await cache.resolveKey(KID);
		expect(key).not.toBeNull();
		expect(state.calls).toBe(2);
		expect(cache.stats).toEqual({ fetches: 2, failures: 1 });
		expect((await verifyAccessAssertion(token(claims()), { issuer: ISSUER, auds: [AUD], resolveKey: cache.resolveKey, nowSeconds: NOW })).ok).toBe(true);
	});

	it('15. beyond JWKS_MAX_STALE_MS, or with no successful fetch ever, the key is refused', async () => {
		const { state, cache } = harness();
		expect(await cache.resolveKey(KID)).not.toBeNull();
		state.fail = true;
		state.now += JWKS_MAX_STALE_MS;
		expect(await cache.resolveKey(KID)).toBeNull();
		expect(await verifyAccessAssertion(token(claims()), { issuer: ISSUER, auds: [AUD], resolveKey: cache.resolveKey, nowSeconds: NOW })).toEqual({ ok: false, reason: 'kid_unresolved' });
		const never = harness();
		never.state.fail = true;
		expect(await never.cache.resolveKey(KID)).toBeNull();
		expect(never.cache.stats).toEqual({ fetches: 1, failures: 1 });
	});

	// Regression (AUTH_TOKEN_S3 section 12, defect D1): an unread, paused undici body whose socket then
	// closed crashed the whole server process; every early exit must cancel the body it does not read.
	it('16. a declared-oversize or non-OK JWKS response has its unread body cancelled', async () => {
		for (const [status, length] of [[200, JWKS_MAX_BODY_BYTES + 1], [503, JWKS_MAX_BODY_BYTES + 1], [503, 10]] as const) {
			let cancelled = 0;
			const body = new ReadableStream<Uint8Array>({
				cancel: () => {
					cancelled += 1;
				}
			});
			const fetchImpl = async () => new Response(body, { status, headers: { 'content-length': String(length) } });
			const cache = createJwksCache({ jwksUrl: JWKS_URL, fetchImpl, nowMs: () => 1_000_000 });
			expect(await cache.resolveKey(KID)).toBeNull();
			expect(cache.stats).toEqual({ fetches: 1, failures: 1 });
			expect(cancelled).toBe(1);
		}
	});
});
