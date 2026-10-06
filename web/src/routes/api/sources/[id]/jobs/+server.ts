import type { RequestHandler } from './$types';
import { listJobs, runControl } from '$lib/server/control-client';
import { resultResponse } from '$lib/server/http';

export const GET: RequestHandler = async ({ params, request }) =>
	resultResponse(await runControl(listJobs(params.id), request.signal));
