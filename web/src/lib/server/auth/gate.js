// Per-request gate decision for both auth modes (AUTH_HOSTING_S3.md section 4.5).
// Pure apart from the injectable JWKS resolver: hooks.server.ts passes the private env, the Host
// header and the assertion header; tests pass stubs. The decision never carries a failure reason,
// a configured value or the assertion back to the client.
//
//   loopback, Host not loopback                 -> 421 bff_host_refused (unchanged S2 behaviour)
//   loopback, loopback Host                     -> resolve (no identity required)
//   invalid mode or tailnet config invalid      -> 503 bff_auth_unconfigured (every path)
//   tailnet, Host not in VIDEO_UTILS_PUBLIC_HOSTS -> 421 bff_host_refused
//   tailnet, assertion missing/invalid          -> 403 bff_identity_refused
//   tailnet, verified email not allowlisted     -> 403 bff_identity_refused (same body)
//   tailnet, verified and allowlisted           -> resolve
//
// Tailscale Serve identity headers (Tailscale-User-Login etc.) are never read (section 4.4).

import { resolveAuthConfig, MODE_LOOPBACK } from './mode.js';
import { verifyAccessAssertion, sharedJwksCache, CF_ACCESS_JWT_HEADER } from './cf-access.js';
import { isAllowlisted } from './allowlist.js';

export { CF_ACCESS_JWT_HEADER };

// Same pattern as LOOPBACK_HOST in $lib/server/http.ts (asserted equal by tests); hooks passes that one.
export const DEFAULT_LOOPBACK_HOST = /^(127\.0\.0\.1|\[::1\]|localhost)(:[0-9]{1,5})?$/;

export const LOOPBACK_HOST_MESSAGE =
	'This app answers only on a loopback Host (127.0.0.1, [::1] or localhost).';
export const PUBLIC_HOST_MESSAGE = 'This app answers only on its configured public hostname.';
export const UNCONFIGURED_MESSAGE = 'This app is not configured for hosted access.';
export const IDENTITY_MESSAGE = 'Access to this app requires an approved operator identity.';

/**
 * Six-key BFF error body (same key order as makeBffError in control-client.ts).
 * @typedef {{ status: 'error', code: string, message: string, upstream_status: null,
 *   upstream_code: null, upstream_detail_code: null }} GateError
 * @typedef {{ action: 'resolve', mode: 'loopback' | 'tailnet', operator: string | null }
 *   | { action: 'refuse', httpStatus: number, error: GateError }} GateDecision
 * @typedef {(kid: string) => Promise<import('node:crypto').KeyObject | null>} KeyResolver
 */

/**
 * @param {number} httpStatus
 * @param {string} code
 * @param {string} message
 * @returns {GateDecision}
 */
function refuse(httpStatus, code, message) {
	return {
		action: 'refuse',
		httpStatus,
		error: {
			status: 'error',
			code,
			message,
			upstream_status: null,
			upstream_code: null,
			upstream_detail_code: null
		}
	};
}

/**
 * @param {{ env: Record<string, string | undefined>, host: string | null, assertion: string | null,
 *   loopbackHost?: RegExp }} request
 * @param {{ keyResolverFor?: (teamDomain: string, jwksUrl: string) => KeyResolver,
 *   nowSeconds?: () => number }} [deps]
 * @returns {Promise<GateDecision>}
 */
export async function gateRequest(request, deps = {}) {
	const auth = resolveAuthConfig(request.env);
	const host = request.host ?? '';

	if (auth.mode === MODE_LOOPBACK) {
		const loopbackHost = request.loopbackHost ?? DEFAULT_LOOPBACK_HOST;
		if (!loopbackHost.test(host)) return refuse(421, 'bff_host_refused', LOOPBACK_HOST_MESSAGE);
		return { action: 'resolve', mode: MODE_LOOPBACK, operator: null };
	}
	if (auth.mode === 'unconfigured') return refuse(503, 'bff_auth_unconfigured', UNCONFIGURED_MESSAGE);

	const config = auth.config;
	if (!config.publicHosts.includes(host.toLowerCase())) return refuse(421, 'bff_host_refused', PUBLIC_HOST_MESSAGE);

	const keyResolverFor =
		deps.keyResolverFor ?? ((teamDomain, jwksUrl) => sharedJwksCache(teamDomain, jwksUrl).resolveKey);
	const nowSeconds = deps.nowSeconds ?? (() => Math.floor(Date.now() / 1000));
	const verified = await verifyAccessAssertion(request.assertion, {
		issuer: config.issuer,
		auds: config.auds,
		resolveKey: keyResolverFor(config.teamDomain, config.jwksUrl),
		nowSeconds: nowSeconds()
	});
	if (!verified.ok || !isAllowlisted(config.allowlist, verified.email)) {
		return refuse(403, 'bff_identity_refused', IDENTITY_MESSAGE);
	}
	return { action: 'resolve', mode: 'tailnet', operator: verified.email };
}
