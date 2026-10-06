import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { getJob, runControl } from '$lib/server/control-client';

const NO_STORE = { 'cache-control': 'no-store' };

// The id is validated inside getJob before any network call (invalid_job_id, 400).
export const GET: RequestHandler = async ({ params, request }) => {
	const result = await runControl(getJob(params.id), request.signal);
	return result.ok
		? json(result.data, { headers: NO_STORE })
		: json(result.error, { status: result.httpStatus, headers: NO_STORE });
};
