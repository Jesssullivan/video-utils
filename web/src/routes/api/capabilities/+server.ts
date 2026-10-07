import type { RequestHandler } from './$types';
import { runControl } from '$lib/server/control-client';
import { resultResponse } from '$lib/server/http';
import { getCapabilities } from '$lib/server/runs/client';

// Tools grouped by area, pilot capability metadata and the model registry (local presence not checked).
export const GET: RequestHandler = async ({ request }) => resultResponse(await runControl(getCapabilities, request.signal));
