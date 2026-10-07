import { redirect } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';
import { runControl } from '$lib/server/control-client';
import { listRuns } from '$lib/server/runs/client';

// Run picker replacing the S2 prototype stub: exactly one run redirects (303) to /runs/[id]/deliver.
export const load: PageServerLoad = async ({ request }) => {
	const result = await runControl(listRuns(500), request.signal);
	if (result.ok && result.data.runs.length === 1) redirect(303, `/runs/${result.data.runs[0].run_id}/deliver`);
	return result.ok ? { runs: [...result.data.runs], truncated: result.data.truncated, error: null } : { runs: null, truncated: false, error: result.error };
};
