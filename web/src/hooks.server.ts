// BFF-wide request gate (WEB_UI_S2.md appended 2026-10-06 section; AUTH_HOSTING_S3.md section 4.5).
// Loopback mode (default, VIDEO_UTILS_AUTH_MODE unset): any non-loopback Host header (for example a
// DNS-rebinding name) is refused with 421 before routing, exactly as in S2, using LOOPBACK_HOST.
// Tailnet mode: deny by default before routing; wrong Host 421, absent/invalid config 503, and a
// missing/invalid/non-allowlisted Cloudflare Access identity 403. The private env is read once per
// request here and handed to the pure gate; nothing from the decision reaches `locals`.
import type { Handle } from '@sveltejs/kit';
import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { CF_ACCESS_JWT_HEADER, gateRequest } from '$lib/server/auth/gate.js';
import { LOOPBACK_HOST, NO_STORE } from '$lib/server/http';

export const handle: Handle = async ({ event, resolve }) => {
	const decision = await gateRequest({
		env: { ...env },
		host: event.request.headers.get('host'),
		assertion: event.request.headers.get(CF_ACCESS_JWT_HEADER),
		loopbackHost: LOOPBACK_HOST
	});
	if (decision.action === 'refuse') {
		return json(decision.error, { status: decision.httpStatus, headers: NO_STORE });
	}
	return resolve(event);
};
