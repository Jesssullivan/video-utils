import type { HandleClientError } from '@sveltejs/kit/hooks';

// The not-found fallback (404.html) is served for every unknown path, and the client router then reports the
// unmatched route through this hook. A 404 is the designed outcome of that page, not a fault, so it is not written
// to the console (SITE_VERIFY_S3.md defect D1); every other client error is still logged. SvelteKit 3 passes the
// caught error with a `kind` discriminant (a 404 is a `framework` error) and keeps the default status and safe
// message when the hook returns nothing.
export const handleError: HandleClientError = ({ kind, error }) => {
	if (kind === 'framework' && error.status === 404) return;
	console.error(error);
};
