import type { RequestHandler } from './$types';
import { runStream } from '$lib/server/control-client';
import { streamResponse } from '$lib/server/http';
import { openRunMedia } from '$lib/server/processing/client';

// Span-audition media proxy: a run WAV the control API re-hashes against its manifest and serves
// only when the run is bound to an admitted source. Ids and roles are checked before any upstream
// request; no path is accepted from the browser.
export const GET: RequestHandler = async ({ params, request }) =>
	streamResponse(await runStream(openRunMedia(params.run, params.role, request.signal), request.signal));
