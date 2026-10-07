import type { RequestHandler } from './$types';
import { runStream } from '$lib/server/control-client';
import { invalidRequest, streamResponse } from '$lib/server/http';
import { openRunArtifact } from '$lib/server/runs/client';

// Run file or bound attachment file by artifact ID only (re-hashed upstream). ?disposition=inline|attachment.
export const GET: RequestHandler = async ({ params, url, request }) => {
	const disposition = url.searchParams.get('disposition') ?? 'attachment';
	if (disposition !== 'inline' && disposition !== 'attachment') return invalidRequest('disposition must be inline or attachment.');
	return streamResponse(await runStream(openRunArtifact(params.id, params.artifact, disposition, request.signal), request.signal));
};
