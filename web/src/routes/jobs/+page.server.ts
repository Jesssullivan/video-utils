import type { PageServerLoad } from './$types';
import { runControl } from '$lib/server/control-client';
import { listAllJobs } from '$lib/server/runs/client';

// GET /api/v1/jobs?limit=200 decoded with the existing JobList schema. Cancel and retry stay on /jobs/[id].
export const load: PageServerLoad = async ({ request }) => {
	const result = await runControl(listAllJobs, request.signal);
	return result.ok ? { jobs: [...result.data.jobs], truncated: result.data.truncated, error: null } : { jobs: null, truncated: false, error: result.error };
};
