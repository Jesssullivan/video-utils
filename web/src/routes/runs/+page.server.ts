import type { PageServerLoad } from './$types';
import { runControl } from '$lib/server/control-client';
import { listRuns } from '$lib/server/runs/client';

export const load: PageServerLoad = async ({ request }) => {
	const result = await runControl(listRuns(500), request.signal);
	return result.ok ? { runs: [...result.data.runs], truncated: result.data.truncated, error: null } : { runs: null, truncated: false, error: result.error };
};
