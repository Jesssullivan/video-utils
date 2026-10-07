import { error } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';
import { getJob, listSources, readAnnotations, runControl } from '$lib/server/control-client';
import { getLaneJob, listLaneJobs, listReviews, listRuns } from '$lib/server/processing/client';
import type { LaneJobProjection } from '$lib/server/processing/schema';
import type { JobProjection } from '$lib/schema/control';
import type { BffError } from '$lib/control-types';
import { newFormKey } from '$lib/idempotency';
import type { StepContext } from '$lib/components/review/step-context';

const PROJECTED_JOBS = 12; // projections for the newest jobs; every job stays listed

type Projection = { tool: string; share: JobProjection | null; lane: LaneJobProjection | null; error: BffError | null };

export const load: PageServerLoad = async ({ params, request }) => {
	const signal = request.signal;
	// Cross-lane step bar (ROUTES_REVIEW_S3 6.1); no run is selected on the clip page.
	const stepContext: StepContext = { current: 'clip', source_artifact_id: params.id, run_id: null, disabled_reasons: {} };
	const [sources, jobs, annotations, runs, reviews] = await Promise.all([
		runControl(listSources, signal),
		runControl(listLaneJobs(params.id), signal),
		runControl(readAnnotations(params.id), signal),
		runControl(listRuns(params.id), signal),
		runControl(listReviews(params.id), signal)
	]);
	if (!sources.ok) {
		return {
			sourceId: params.id, source: null, error: sources.error, jobs: null, jobsError: null, projections: {} as Record<string, Projection>,
			annotations: null, annotationError: null, runs: null, runsError: null, reviews: null, reviewsError: null, formKey: newFormKey(), stepContext
		};
	}
	const source = sources.data.sources.find((s) => s.source_artifact_id === params.id) ?? null;
	if (source === null) error(404, { message: 'The control API lists no such admitted source.', code: 'source_not_found' });
	const projections: Record<string, Projection> = {};
	if (jobs.ok) {
		const newest = jobs.data.jobs.slice(0, PROJECTED_JOBS);
		const results = await Promise.all(
			newest.map(async (job) => {
				const tool = job.tool ?? 'share_export';
				if (tool === 'share_export') {
					const result = await runControl(getJob(job.job_id), signal);
					return { tool, share: result.ok ? (result.data as JobProjection) : null, lane: null, error: result.ok ? null : result.error };
				}
				const result = await runControl(getLaneJob(job.job_id), signal);
				return { tool, share: null, lane: result.ok ? result.data : null, error: result.ok ? null : result.error };
			})
		);
		newest.forEach((job, index) => (projections[job.job_id] = results[index]));
	}
	return {
		sourceId: params.id,
		source,
		error: null,
		jobs: jobs.ok ? jobs.data : null,
		jobsError: jobs.ok ? null : jobs.error,
		projections,
		annotations: annotations.ok ? annotations.data : null,
		annotationError: annotations.ok ? null : annotations.error,
		runs: runs.ok ? runs.data : null,
		runsError: runs.ok ? null : runs.error,
		reviews: reviews.ok ? reviews.data : null,
		reviewsError: reviews.ok ? null : reviews.error,
		formKey: newFormKey(),
		stepContext
	};
};
