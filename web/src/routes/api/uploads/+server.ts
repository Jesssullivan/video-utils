import type { RequestHandler } from './$types';
import { makeBffError, runControl, uploadSource } from '$lib/server/control-client';
import { crossOriginRefusal, errorResponse, invalidRequest, resultResponse } from '$lib/server/http';
import { UPLOAD_TYPES } from '$lib/upload-types';

const LABEL = /^[\x20-\x7e]{1,120}$/;

// Raw body streamed to the control API (never buffered here beyond adapter-node's BODY_SIZE_LIMIT
// check). Uploads above BODY_SIZE_LIMIT are refused by adapter-node with a plain 413 before this
// handler runs; the upload page maps that status to upload_too_large.
export const POST: RequestHandler = async ({ request, url }) => {
	const refused = crossOriginRefusal(request, url);
	if (refused) return refused;
	const type = (request.headers.get('content-type') ?? '').split(';', 1)[0].trim().toLowerCase();
	if (!(type in UPLOAD_TYPES)) {
		const { httpStatus, error } = makeBffError(415, 'bff_content_type_refused', `Content-Type must be one of: ${Object.keys(UPLOAD_TYPES).join(', ')}.`);
		return errorResponse(httpStatus, error);
	}
	const length = request.headers.get('content-length');
	if (length === null || !/^[0-9]{1,13}$/.test(length) || request.body === null) {
		const { httpStatus, error } = makeBffError(411, 'bff_length_required', 'Uploads need a Content-Length (no chunked bodies).');
		return errorResponse(httpStatus, error);
	}
	const label = request.headers.get('x-upload-label');
	if (label !== null && !LABEL.test(label)) return invalidRequest('X-Upload-Label must be 1..120 printable ASCII characters.');
	return resultResponse(await runControl(uploadSource(request.body, type, length, label, request.signal), request.signal));
};
