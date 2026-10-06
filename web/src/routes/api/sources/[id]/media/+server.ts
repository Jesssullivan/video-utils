import type { RequestHandler } from './$types';
import { openSourceMedia, runStream } from '$lib/server/control-client';
import { streamResponse } from '$lib/server/http';

// Source bytes for the compare/annotate player only (re-hashed upstream; inline; no Range in S2).
export const GET: RequestHandler = async ({ params, request }) =>
	streamResponse(await runStream(openSourceMedia(params.id, request.signal), request.signal));
