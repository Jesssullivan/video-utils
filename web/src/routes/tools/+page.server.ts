import type { PageServerLoad } from './$types';
import { runControl } from '$lib/server/control-client';
import { getCapabilities } from '$lib/server/runs/client';

export const load: PageServerLoad = async ({ request }) => {
	const result = await runControl(getCapabilities, request.signal);
	return result.ok ? { capabilities: result.data, error: null } : { capabilities: null, error: result.error };
};
