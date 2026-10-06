import { error } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';
import { getJob, runControl } from '$lib/server/control-client';

export const load: PageServerLoad = async ({ params, request }) => {
	const result = await runControl(getJob(params.id), request.signal);
	if (!result.ok && result.error.code === 'job_not_found') {
		error(404, { message: result.error.message, code: result.error.code });
	}
	return result.ok
		? { jobId: params.id, job: result.data, error: null }
		: { jobId: params.id, job: null, error: result.error };
};
