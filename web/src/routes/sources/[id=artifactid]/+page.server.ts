import { error } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';
import { getJob, listJobs, listSources, readAnnotations, runControl } from '$lib/server/control-client';
import { newFormKey } from '$lib/idempotency';

const PROJECTED_JOBS = 12; // artifacts are listed for the newest jobs; every job stays listed

export const load: PageServerLoad = async ({ params, request }) => {
	const signal = request.signal;
	const [sources, jobs, annotations] = await Promise.all([
		runControl(listSources, signal),
		runControl(listJobs(params.id), signal),
		runControl(readAnnotations(params.id), signal)
	]);
	if (!sources.ok) {
		return { sourceId: params.id, source: null, jobs: null, projections: {}, annotations: null, annotationError: null, error: sources.error, formKey: newFormKey() };
	}
	const source = sources.data.sources.find((s) => s.source_artifact_id === params.id) ?? null;
	if (source === null) error(404, { message: 'The control API lists no such admitted source.', code: 'source_not_found' });
	const projections: Record<string, Awaited<ReturnType<typeof runControl>>> = {};
	if (jobs.ok) {
		const newest = jobs.data.jobs.slice(0, PROJECTED_JOBS);
		const results = await Promise.all(newest.map((job) => runControl(getJob(job.job_id), signal)));
		newest.forEach((job, index) => (projections[job.job_id] = results[index]));
	}
	return {
		sourceId: params.id,
		source,
		jobs: jobs.ok ? jobs.data : null,
		jobsError: jobs.ok ? null : jobs.error,
		projections: Object.fromEntries(
			Object.entries(projections).map(([id, result]) => [id, result.ok ? { job: result.data as import('$lib/schema/control').JobProjection, error: null } : { job: null, error: result.error }])
		),
		annotations: annotations.ok ? annotations.data : null,
		annotationError: annotations.ok ? null : annotations.error,
		error: null,
		formKey: newFormKey()
	};
};
