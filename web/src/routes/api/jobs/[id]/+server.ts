import type { RequestHandler } from './$types';
import { getJob, runControl } from '$lib/server/control-client';
import { resultResponse } from '$lib/server/http';

// The id is validated inside getJob before any network call (invalid_job_id, 400).
export const GET: RequestHandler = async ({ params, request }) => resultResponse(await runControl(getJob(params.id), request.signal));
