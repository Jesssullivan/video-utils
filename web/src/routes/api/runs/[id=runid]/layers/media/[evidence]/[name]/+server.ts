import type { RequestHandler } from './$types';
import { makeBffError, runStream } from '$lib/server/control-client';
import { errorResponse, streamResponse } from '$lib/server/http';
import { openLayerMedia } from '$lib/server/runs/client';
import { isEvidenceId, isMediaName } from '$lib/server/runs/schema';

// Streaming pass-through of re-hashed layer media; X-Artifact-Sha256 is kept. IDs only, never a path.
export const GET: RequestHandler = async ({ params, request }) => {
	if (!isEvidenceId(params.evidence) || !isMediaName(params.name)) {
		const { httpStatus, error } = makeBffError(404, 'artifact_not_found', 'No such layer media for this run.');
		return errorResponse(httpStatus, error);
	}
	return streamResponse(await runStream(openLayerMedia(params.id, params.evidence, params.name, request.signal), request.signal));
};
