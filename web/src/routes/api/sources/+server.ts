import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { listSources, runControl } from '$lib/server/control-client';

const NO_STORE = { 'cache-control': 'no-store' };

export const GET: RequestHandler = async ({ request }) => {
	const result = await runControl(listSources, request.signal);
	return result.ok
		? json(result.data, { headers: NO_STORE })
		: json(result.error, { status: result.httpStatus, headers: NO_STORE });
};
