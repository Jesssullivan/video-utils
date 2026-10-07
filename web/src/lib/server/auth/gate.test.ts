// Auth mode, tailnet configuration, operator allowlist and the per-request gate (WEB_TESTS_S3.md 5.1).
// Unit level only: no Cloudflare Access team, tailnet or network is involved (tailnet_mode_e2e stays unknown).
import { generateKeyPairSync, sign as cryptoSign, type KeyObject } from 'node:crypto';
import { beforeAll, describe, expect, it } from 'vitest';
import { LOOPBACK_HOST } from '../http';
import { MAX_ALLOWLIST_ENTRIES, isAllowlisted, parseAllowlist } from './allowlist.js';
import { DEFAULT_LOOPBACK_HOST, IDENTITY_MESSAGE, gateRequest } from './gate.js';
import { ALLOWLIST_ENV, AUDS_ENV, AUTH_MODE_ENV, ORIGIN_ENV, PUBLIC_HOSTS_ENV, TEAM_DOMAIN_ENV, parseAuthMode, parseTailnetConfig, resolveAuthConfig } from './mode.js';

const TEAM = 'example-team.cloudflareaccess.com';
const AUD = 'a'.repeat(32);
const EMAIL = 'operator@example.org';
const HOST = 'video.example.org';
const NOW = 1_800_000_000;
const KID = 'unit-key-1';
const WILDCARD_HOST = ['0', '0', '0', '0'].join('.');

const tailnetEnv = (overrides: Record<string, string | undefined> = {}): Record<string, string | undefined> => ({
	[AUTH_MODE_ENV]: 'tailnet', [TEAM_DOMAIN_ENV]: TEAM, [AUDS_ENV]: AUD, [ALLOWLIST_ENV]: EMAIL, [PUBLIC_HOSTS_ENV]: HOST, [ORIGIN_ENV]: `https://${HOST}`, ...overrides
});

let privateKey: KeyObject;
let publicKey: KeyObject;
const b64 = (value: unknown) => Buffer.from(JSON.stringify(value)).toString('base64url');
function assertion(email: string, overrides: Record<string, unknown> = {}): string {
	const signed = `${b64({ alg: 'RS256', kid: KID })}.${b64({ iss: `https://${TEAM}`, aud: [AUD], email, exp: NOW + 300, iat: NOW - 5, ...overrides })}`;
	return `${signed}.${cryptoSign('sha256', Buffer.from(signed, 'ascii'), privateKey).toString('base64url')}`;
}
const deps = () => ({
	nowSeconds: () => NOW,
	keyResolverFor: (teamDomain: string, jwksUrl: string) => {
		expect(teamDomain).toBe(TEAM);
		expect(jwksUrl).toBe(`https://${TEAM}/cdn-cgi/access/certs`);
		return async (kid: string) => (kid === KID ? publicKey : null);
	}
});

beforeAll(() => {
	({ privateKey, publicKey } = generateKeyPairSync('rsa', { modulusLength: 2048 }));
});

describe('parseAuthMode', () => {
	it('defaults to loopback, accepts exactly "tailnet" and fails closed on anything else', () => {
		for (const raw of [undefined, null, '']) expect(parseAuthMode(raw)).toEqual({ kind: 'loopback' });
		expect(parseAuthMode('tailnet')).toEqual({ kind: 'tailnet' });
		for (const raw of ['Tailnet', 'tailnet ', 'loopback', 'off', 'none', 'public', '1']) expect(parseAuthMode(raw), raw).toEqual({ kind: 'invalid' });
	});
});

describe('parseAllowlist and isAllowlisted', () => {
	it('accepts exact addresses, lowercased and de-duplicated', () => {
		const parsed = parseAllowlist(' Operator@Example.org , second@example.org,operator@example.org ');
		expect(parsed.ok && [...parsed.emails].sort()).toEqual(['operator@example.org', 'second@example.org']);
	});
	it('refuses wildcard and bare-domain entries, and the whole list with them', () => {
		expect(parseAllowlist('*@example.org')).toEqual({ ok: false, reason: 'allowlist_wildcard' });
		expect(parseAllowlist('operator@example.org,*')).toEqual({ ok: false, reason: 'allowlist_wildcard' });
		expect(parseAllowlist('example.org')).toEqual({ ok: false, reason: 'allowlist_invalid_entry' });
		expect(parseAllowlist('@example.org')).toEqual({ ok: false, reason: 'allowlist_invalid_entry' });
		expect(parseAllowlist('operator@example.org,example.org')).toEqual({ ok: false, reason: 'allowlist_invalid_entry' });
		expect(parseAllowlist('Operator <operator@example.org>')).toEqual({ ok: false, reason: 'allowlist_invalid_entry' });
		expect(parseAllowlist('operator@localhost')).toEqual({ ok: false, reason: 'allowlist_invalid_entry' });
	});
	it('refuses a missing list, an empty entry and more than the maximum', () => {
		for (const raw of [undefined, null, '', '  ']) expect(parseAllowlist(raw)).toEqual({ ok: false, reason: 'allowlist_missing' });
		expect(parseAllowlist('operator@example.org,,second@example.org')).toEqual({ ok: false, reason: 'allowlist_empty_entry' });
		const many = Array.from({ length: MAX_ALLOWLIST_ENTRIES + 1 }, (_, index) => `user${index}@example.org`).join(',');
		expect(parseAllowlist(many)).toEqual({ ok: false, reason: 'allowlist_too_many' });
	});
	it('reasons never echo a configured value', () => {
		const parsed = parseAllowlist('secret-person@example.org,*');
		expect(JSON.stringify(parsed)).not.toContain('secret-person');
	});
	it('membership is exact and case-insensitive on the verified email only', () => {
		const emails = new Set([EMAIL]);
		expect(isAllowlisted(emails, 'OPERATOR@example.org')).toBe(true);
		for (const other of ['operator@example.org.evil.test', 'xoperator@example.org', '', null, undefined]) expect(isAllowlisted(emails, other)).toBe(false);
	});
});

describe('parseTailnetConfig and resolveAuthConfig', () => {
	it('accepts a complete configuration and derives the issuer and JWKS URL from the team domain', () => {
		const parsed = parseTailnetConfig(tailnetEnv());
		expect(parsed.ok).toBe(true);
		if (!parsed.ok) return;
		expect(parsed.config.issuer).toBe(`https://${TEAM}`);
		expect(parsed.config.jwksUrl).toBe(`https://${TEAM}/cdn-cgi/access/certs`);
		expect([...parsed.config.auds]).toEqual([AUD]);
		expect([...parsed.config.publicHosts]).toEqual([HOST]);
		expect(resolveAuthConfig(tailnetEnv()).mode).toBe('tailnet');
	});
	it('names every missing or invalid variable, never a value', () => {
		expect(parseTailnetConfig({})).toEqual({ ok: false, problems: [TEAM_DOMAIN_ENV, AUDS_ENV, ALLOWLIST_ENV, PUBLIC_HOSTS_ENV, ORIGIN_ENV] });
		const cases: Array<[Record<string, string | undefined>, string[]]> = [
			[{ [TEAM_DOMAIN_ENV]: 'example-team.example.org' }, [TEAM_DOMAIN_ENV]],
			[{ [AUDS_ENV]: 'short' }, [AUDS_ENV]],
			[{ [ALLOWLIST_ENV]: '*@example.org' }, [ALLOWLIST_ENV]],
			[{ [PUBLIC_HOSTS_ENV]: `${HOST}:443` }, [PUBLIC_HOSTS_ENV, ORIGIN_ENV]],
			// Observation reported to root: a dotted IPv4 literal (even the wildcard address) matches the "DNS hostname"
			// pattern, so only the ORIGIN mismatch is named here. The request still needs a verified, allowlisted identity.
			[{ [PUBLIC_HOSTS_ENV]: WILDCARD_HOST }, [ORIGIN_ENV]],
			[{ [PUBLIC_HOSTS_ENV]: 'localhost' }, [PUBLIC_HOSTS_ENV, ORIGIN_ENV]],
			[{ [PUBLIC_HOSTS_ENV]: `https://${HOST}` }, [PUBLIC_HOSTS_ENV, ORIGIN_ENV]],
			[{ [ORIGIN_ENV]: `http://${HOST}` }, [ORIGIN_ENV]],
			[{ [ORIGIN_ENV]: 'https://other.example.org' }, [ORIGIN_ENV]]
		];
		for (const [override, problems] of cases) {
			const parsed = parseTailnetConfig(tailnetEnv(override));
			expect(parsed, JSON.stringify(Object.keys(override))).toEqual({ ok: false, problems });
			expect(resolveAuthConfig(tailnetEnv(override))).toEqual({ mode: 'unconfigured', problems });
		}
	});
	it('loopback is the default and an unknown mode is unconfigured', () => {
		expect(resolveAuthConfig({})).toEqual({ mode: 'loopback' });
		expect(resolveAuthConfig({ [AUTH_MODE_ENV]: 'public' })).toEqual({ mode: 'unconfigured', problems: [AUTH_MODE_ENV] });
	});
});

describe('gateRequest: loopback mode (default)', () => {
	it('resolves a loopback Host with no identity', async () => {
		for (const host of ['127.0.0.1:3000', '[::1]:3000', 'localhost:5173', '127.0.0.1']) {
			expect(await gateRequest({ env: {}, host, assertion: null })).toEqual({ action: 'resolve', mode: 'loopback', operator: null });
		}
	});
	it('refuses a non-loopback Host with 421 bff_host_refused', async () => {
		for (const host of ['video.example.org', 'attacker.test:3000', '192.168.1.10:3000', `${WILDCARD_HOST}:3000`, '127.0.0.1.attacker.test', '', null]) {
			const decision = await gateRequest({ env: {}, host, assertion: assertion(EMAIL) });
			expect(decision.action).toBe('refuse');
			if (decision.action !== 'refuse') continue;
			expect(decision.httpStatus).toBe(421);
			expect(decision.error.code).toBe('bff_host_refused');
		}
	});
	it('uses the same loopback pattern as the BFF http helpers', () => {
		expect(DEFAULT_LOOPBACK_HOST.source).toBe(LOOPBACK_HOST.source);
	});
});

describe('gateRequest: tailnet mode', () => {
	const refusedAs = async (request: Parameters<typeof gateRequest>[0], status: number, code: string) => {
		const decision = await gateRequest(request, deps());
		expect(decision.action).toBe('refuse');
		if (decision.action !== 'refuse') return null;
		expect(decision.httpStatus).toBe(status);
		expect(decision.error.code).toBe(code);
		expect(Object.keys(decision.error)).toEqual(['status', 'code', 'message', 'upstream_status', 'upstream_code', 'upstream_detail_code']);
		return decision.error;
	};

	it('answers 503 bff_auth_unconfigured on every request when the configuration is incomplete or the mode is unknown', async () => {
		await refusedAs({ env: tailnetEnv({ [ALLOWLIST_ENV]: undefined }), host: HOST, assertion: assertion(EMAIL) }, 503, 'bff_auth_unconfigured');
		await refusedAs({ env: { [AUTH_MODE_ENV]: 'tailnet' }, host: '127.0.0.1:3000', assertion: null }, 503, 'bff_auth_unconfigured');
		await refusedAs({ env: { [AUTH_MODE_ENV]: 'open' }, host: '127.0.0.1:3000', assertion: null }, 503, 'bff_auth_unconfigured');
	});
	it('refuses a Host outside the public host list with 421, including loopback', async () => {
		await refusedAs({ env: tailnetEnv(), host: 'other.example.org', assertion: assertion(EMAIL) }, 421, 'bff_host_refused');
		await refusedAs({ env: tailnetEnv(), host: '127.0.0.1:3000', assertion: assertion(EMAIL) }, 421, 'bff_host_refused');
	});
	it('resolves a verified, allowlisted operator', async () => {
		expect(await gateRequest({ env: tailnetEnv(), host: HOST, assertion: assertion('Operator@Example.org') }, deps())).toEqual({ action: 'resolve', mode: 'tailnet', operator: EMAIL });
		expect(await gateRequest({ env: tailnetEnv(), host: HOST.toUpperCase(), assertion: assertion(EMAIL) }, deps())).toMatchObject({ action: 'resolve' });
	});
	it('refuses a valid token for a non-allowlisted email with 403, with the same body as an invalid token', async () => {
		const unlisted = await refusedAs({ env: tailnetEnv(), host: HOST, assertion: assertion('visitor@example.org') }, 403, 'bff_identity_refused');
		const missing = await refusedAs({ env: tailnetEnv(), host: HOST, assertion: null }, 403, 'bff_identity_refused');
		const expired = await refusedAs({ env: tailnetEnv(), host: HOST, assertion: assertion(EMAIL, { exp: NOW - 3600 }) }, 403, 'bff_identity_refused');
		const wrongAud = await refusedAs({ env: tailnetEnv(), host: HOST, assertion: assertion(EMAIL, { aud: ['b'.repeat(32)] }) }, 403, 'bff_identity_refused');
		const garbage = await refusedAs({ env: tailnetEnv(), host: HOST, assertion: 'not.a.token' }, 403, 'bff_identity_refused');
		for (const body of [missing, expired, wrongAud, garbage]) expect(body).toEqual(unlisted);
		expect(unlisted?.message).toBe(IDENTITY_MESSAGE);
		// Nothing about the failure, the identity or the configuration reaches the client body.
		const text = JSON.stringify(unlisted);
		for (const secret of ['visitor', EMAIL, AUD, TEAM, 'allowlist', 'expired', 'aud_']) expect(text).not.toContain(secret);
	});
});
