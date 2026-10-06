import type { RequestHandler } from './$types';
import { runControl, submitJob } from '$lib/server/control-client';
import { crossOriginRefusal, invalidRequest, readJsonObject, resultResponse } from '$lib/server/http';
import { buildJobRequest } from '$lib/server/job-request';

// One admitted job type. The body sent upstream is built only by job-request.ts (parity fixtures).
export const POST: RequestHandler = async ({ request, url }) => {
	const refused = crossOriginRefusal(request, url);
	if (refused) return refused;
	const body = await readJsonObject(request);
	if (!body.ok) return body.response;
	const { source_artifact_id, parameters, idempotency_key, ...rest } = body.value;
	if (Object.keys(rest).length > 0) return invalidRequest('Body accepts only source_artifact_id, parameters and idempotency_key.');
	const built = buildJobRequest({ sourceArtifactId: source_artifact_id, parameters, idempotencyKey: idempotency_key });
	if (!built.ok) return invalidRequest(`Job request refused before any upstream call: ${built.code}.`);
	return resultResponse(await runControl(submitJob(built.body), request.signal));
};
