import type { RequestHandler } from './$types';
import { runControl } from '$lib/server/control-client';
import { invalidRequest, resultResponse } from '$lib/server/http';
import { listRuns } from '$lib/server/runs/client';

// GET only (SvelteKit answers 405 for other methods). ?limit=1..500, validated before any upstream call.
export const GET: RequestHandler = async ({ url, request }) => {
	const text = url.searchParams.get('limit');
	const limit = text === null ? 100 : /^[1-9][0-9]{0,2}$/.test(text) ? Number(text) : NaN;
	if (!Number.isInteger(limit) || limit < 1 || limit > 500) return invalidRequest('limit must be an integer in 1..500.');
	return resultResponse(await runControl(listRuns(limit), request.signal));
};
