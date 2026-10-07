import type { RequestHandler } from './$types';
import { runControl } from '$lib/server/control-client';
import { invalidRequest, resultResponse } from '$lib/server/http';
import { getLayers } from '$lib/server/runs/client';
import { isEvidenceId } from '$lib/server/runs/schema';

// Bound review layers. ?evidence=evd_... selects an alternative practice bundle explicitly.
export const GET: RequestHandler = async ({ params, url, request }) => {
	const evidence = url.searchParams.get('evidence');
	if (evidence !== null && !isEvidenceId(evidence)) return invalidRequest('evidence must match ^evd_[0-9a-f]{32}$.');
	return resultResponse(await runControl(getLayers(params.id, evidence), request.signal));
};
