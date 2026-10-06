import type { RequestHandler } from './$types';
import { readAnnotations, runControl, writeAnnotation } from '$lib/server/control-client';
import { crossOriginRefusal, readJsonObject, resultResponse } from '$lib/server/http';

export const GET: RequestHandler = async ({ params, request }) =>
	resultResponse(await runControl(readAnnotations(params.id), request.signal));

// annotation_v2 request passed through unchanged; the control API enforces operator/browser
// authorship, source-clock bounds, expected_revision and idempotent replay.
export const POST: RequestHandler = async ({ params, request, url }) => {
	const refused = crossOriginRefusal(request, url);
	if (refused) return refused;
	const body = await readJsonObject(request);
	if (!body.ok) return body.response;
	return resultResponse(await runControl(writeAnnotation(params.id, body.value), request.signal));
};
