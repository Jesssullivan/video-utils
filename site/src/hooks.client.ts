import type { HandleClientError } from '@sveltejs/kit';

// The not-found fallback (404.html) is served for every unknown path, and the client router then reports the
// unmatched route through this hook. A 404 is the designed outcome of that page, not a fault, so it is not written
// to the console (SITE_VERIFY_S3.md defect D1); every other client error is still logged.
export const handleError: HandleClientError = ({ error, status, message }) => {
	if (status !== 404) console.error(error);
	return { message };
};
