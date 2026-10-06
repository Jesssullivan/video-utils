import type { RequestHandler } from './$types';
import { jobAction, runControl } from '$lib/server/control-client';
import { crossOriginRefusal, invalidRequest, readJsonObject, resultResponse } from '$lib/server/http';

// Explicit operator action (closing a tab never cancels anything). Body must be {}.
export const POST: RequestHandler = async ({ params, request, url }) => {
	const refused = crossOriginRefusal(request, url);
	if (refused) return refused;
	const body = await readJsonObject(request);
	if (!body.ok) return body.response;
	if (Object.keys(body.value).length > 0) return invalidRequest('Body must be {}.');
	return resultResponse(await runControl(jobAction(params.id, 'cancel'), request.signal));
};
