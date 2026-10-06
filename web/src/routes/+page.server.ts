import type { PageServerLoad } from './$types';
import { listSources, runControl } from '$lib/server/control-client';

export const load: PageServerLoad = async ({ request }) => {
	const result = await runControl(listSources, request.signal);
	return result.ok
		? { sources: [...result.data.sources], error: null }
		: { sources: null, error: result.error };
};
