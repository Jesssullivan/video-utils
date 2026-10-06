// BFF-wide Host guard (WEB_UI_S2.md appended 2026-10-06 section): the app is served on loopback only,
// so any other Host header (for example a DNS-rebinding name) is refused before routing.
import type { Handle } from '@sveltejs/kit';
import { makeBffError } from '$lib/server/control-client';
import { LOOPBACK_HOST, errorResponse } from '$lib/server/http';

export const handle: Handle = async ({ event, resolve }) => {
	const host = event.request.headers.get('host') ?? '';
	if (!LOOPBACK_HOST.test(host)) {
		const { error } = makeBffError(421, 'bff_host_refused', 'This app answers only on a loopback Host (127.0.0.1, [::1] or localhost).');
		return errorResponse(421, error);
	}
	return resolve(event);
};
