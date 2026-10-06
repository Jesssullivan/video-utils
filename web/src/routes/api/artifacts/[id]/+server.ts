import type { RequestHandler } from './$types';
import { openArtifact, runStream } from '$lib/server/control-client';
import { streamResponse } from '$lib/server/http';

// Download by artifact ID only: no URL, form or endpoint here accepts a path.
export const GET: RequestHandler = async ({ params, request }) =>
	streamResponse(await runStream(openArtifact(params.id, request.signal), request.signal));
