import type { RequestHandler } from './$types';
import { runControl } from '$lib/server/control-client';
import { resultResponse } from '$lib/server/http';
import { getRun } from '$lib/server/runs/client';

// Run graph (stages, signal versions, evidence, invalidation). Invalid run IDs 404 at routing time.
export const GET: RequestHandler = async ({ params, request }) => resultResponse(await runControl(getRun(params.id), request.signal));
