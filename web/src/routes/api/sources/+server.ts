import type { RequestHandler } from './$types';
import { admitSource, listSources, runControl } from '$lib/server/control-client';
import { crossOriginRefusal, invalidRequest, readJsonObject, resultResponse } from '$lib/server/http';

export const GET: RequestHandler = async ({ request }) => resultResponse(await runControl(listSources, request.signal));

// Admission by run-relative selector (RUN/.../file.mov). The browser never names a host path; absolute
// paths, `..`, symlinks and URLs are refused upstream by artifact_ids with typed codes.
export const POST: RequestHandler = async ({ request, url }) => {
	const refused = crossOriginRefusal(request, url);
	if (refused) return refused;
	const body = await readJsonObject(request);
	if (!body.ok) return body.response;
	const { selector, ...rest } = body.value;
	if (Object.keys(rest).length > 0 || typeof selector !== 'string' || selector.length < 1 || selector.length > 1024) {
		return invalidRequest('Body must be {"selector": "<run-relative selector>"} (1..1024 characters).');
	}
	return resultResponse(await runControl(admitSource(selector), request.signal));
};
