// Auth mode switch and tailnet configuration (AUTH_HOSTING_S3.md sections 4.1 and 4.2).
// Pure: the environment is passed in, never read here, so serve.js, hooks.server.ts and
// the node test harness share exactly one validator. Any invalid value fails closed.
// Error reasons carry variable NAMES only; configured values are never echoed.

import { parseAllowlist, ALLOWLIST_ENV } from './allowlist.js';

export const AUTH_MODE_ENV = 'VIDEO_UTILS_AUTH_MODE';
export const TEAM_DOMAIN_ENV = 'VIDEO_UTILS_CF_ACCESS_TEAM_DOMAIN';
export const AUDS_ENV = 'VIDEO_UTILS_CF_ACCESS_AUDS';
export const PUBLIC_HOSTS_ENV = 'VIDEO_UTILS_PUBLIC_HOSTS';
export const ORIGIN_ENV = 'ORIGIN';
export { ALLOWLIST_ENV };

export const MODE_LOOPBACK = 'loopback';
export const MODE_TAILNET = 'tailnet';

const TEAM_DOMAIN_PATTERN = /^[a-z0-9-]+\.cloudflareaccess\.com$/;
const AUD_PATTERN = /^[A-Za-z0-9]{16,128}$/;
const MAX_AUDS = 8;
// Exact DNS hostname: LDH labels, at least one dot, no port, no scheme, no trailing dot.
const HOSTNAME_PATTERN = /^(?=.{1,253}$)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$/;
const MAX_PUBLIC_HOSTS = 4;

/**
 * @typedef {{ kind: 'loopback' } | { kind: 'tailnet' } | { kind: 'invalid' }} AuthMode
 */

/**
 * Unset or empty = loopback (today's default); exactly `tailnet` = hosted mode; anything else invalid.
 * @param {string | undefined | null} raw
 * @returns {AuthMode}
 */
export function parseAuthMode(raw) {
	if (raw === undefined || raw === null || raw === '') return { kind: MODE_LOOPBACK };
	if (raw === MODE_TAILNET) return { kind: MODE_TAILNET };
	return { kind: 'invalid' };
}

/**
 * @typedef {object} TailnetConfig
 * @property {string} teamDomain
 * @property {string} issuer       `https://<teamDomain>`; compared exactly with the JWT `iss`.
 * @property {string} jwksUrl      `https://<teamDomain>/cdn-cgi/access/certs`; never configurable separately.
 * @property {readonly string[]} auds  Case-sensitive Access application AUD tags (any-of).
 * @property {ReadonlySet<string>} allowlist  Lowercased operator emails.
 * @property {readonly string[]} publicHosts  Exact lowercase hostnames.
 * @property {string} origin
 */

/**
 * @typedef {{ ok: true, config: TailnetConfig } | { ok: false, problems: string[] }} TailnetConfigResult
 */

/**
 * @param {string | undefined} raw
 * @returns {string[] | null} trimmed, de-duplicated entries in first-seen order; null if any entry is empty.
 */
function splitList(raw) {
	if (typeof raw !== 'string' || raw.trim() === '') return null;
	/** @type {string[]} */
	const out = [];
	for (const part of raw.split(',')) {
		const value = part.trim();
		if (value === '') return null;
		if (!out.includes(value)) out.push(value);
	}
	return out;
}

/**
 * Validate every tailnet variable; collect every problem (names only) so an operator sees them all.
 * @param {Record<string, string | undefined>} env
 * @returns {TailnetConfigResult}
 */
export function parseTailnetConfig(env) {
	/** @type {string[]} */
	const problems = [];

	const teamDomain = typeof env[TEAM_DOMAIN_ENV] === 'string' ? String(env[TEAM_DOMAIN_ENV]).trim() : '';
	if (!TEAM_DOMAIN_PATTERN.test(teamDomain)) problems.push(TEAM_DOMAIN_ENV);

	const auds = splitList(env[AUDS_ENV]);
	if (auds === null || auds.length < 1 || auds.length > MAX_AUDS || !auds.every((aud) => AUD_PATTERN.test(aud))) {
		problems.push(AUDS_ENV);
	}

	const allowlist = parseAllowlist(env[ALLOWLIST_ENV]);
	if (!allowlist.ok) problems.push(ALLOWLIST_ENV);

	const hosts = splitList(env[PUBLIC_HOSTS_ENV]);
	const publicHosts = hosts === null ? null : hosts.map((host) => host.toLowerCase());
	if (
		publicHosts === null ||
		publicHosts.length < 1 ||
		publicHosts.length > MAX_PUBLIC_HOSTS ||
		!publicHosts.every((host) => HOSTNAME_PATTERN.test(host))
	) {
		problems.push(PUBLIC_HOSTS_ENV);
	}

	const origin = typeof env[ORIGIN_ENV] === 'string' ? String(env[ORIGIN_ENV]) : '';
	const originHost = origin.startsWith('https://') ? origin.slice('https://'.length) : null;
	if (originHost === null || publicHosts === null || !publicHosts.includes(originHost)) {
		problems.push(ORIGIN_ENV);
	}

	if (problems.length > 0 || auds === null || publicHosts === null || !allowlist.ok) {
		return { ok: false, problems };
	}
	return {
		ok: true,
		config: Object.freeze({
			teamDomain,
			issuer: `https://${teamDomain}`,
			jwksUrl: `https://${teamDomain}/cdn-cgi/access/certs`,
			auds: Object.freeze([...auds]),
			allowlist: allowlist.emails,
			publicHosts: Object.freeze([...publicHosts]),
			origin
		})
	};
}

/**
 * @typedef {{ mode: 'loopback' }
 *   | { mode: 'tailnet', config: TailnetConfig }
 *   | { mode: 'unconfigured', problems: string[] }} AuthConfig
 */

/**
 * @param {Record<string, string | undefined>} env
 * @returns {AuthConfig}
 */
export function resolveAuthConfig(env) {
	const mode = parseAuthMode(env[AUTH_MODE_ENV]);
	if (mode.kind === MODE_LOOPBACK) return { mode: MODE_LOOPBACK };
	if (mode.kind === 'invalid') return { mode: 'unconfigured', problems: [AUTH_MODE_ENV] };
	const tailnet = parseTailnetConfig(env);
	return tailnet.ok ? { mode: MODE_TAILNET, config: tailnet.config } : { mode: 'unconfigured', problems: tailnet.problems };
}
