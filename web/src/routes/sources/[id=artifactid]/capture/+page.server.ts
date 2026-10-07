import { error, fail } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import { listSources, runControl } from '$lib/server/control-client';
import { createReview, getJobTypes, isRunId, listReviews, listRuns, measureInterval, submitProcessingJob } from '$lib/server/processing/client';
import { authorBody, echo, measurementBody, reviewBody } from '$lib/server/processing/forms';
import type { LaneJobProjection, Measurement, ReviewRecord } from '$lib/server/processing/schema';
import type { BffError } from '$lib/control-types';
import { newFormKey } from '$lib/idempotency';
import type { StepContext } from '$lib/components/review/step-context';

// Capture review (ROUTES_PROCESSING_S3 section 4): the interval is chosen by the operator on the
// baseline run's native timeline. Loads never write; nothing is prefilled, proposed or auto-saved.
const ECHO = ['run_id', 'start_seconds', 'end_seconds', 'review_status', 'authorization_scope', 'music_status', 'click_status',
	'ambient_music_status', 'note', 'setup_interval_acknowledged'];
const SHA256 = /^[0-9a-f]{64}$/;

export type CaptureOutcome = {
	action: 'measure' | 'save' | 'author';
	values: Record<string, string>;
	error: BffError | null;
	local: { code: string; message: string } | null;
	measurement: Measurement | null;
	review: ReviewRecord | null;
	job: LaneJobProjection | null;
};

const outcome = (action: CaptureOutcome['action'], values: Record<string, string>, extra: Partial<CaptureOutcome> = {}): CaptureOutcome => ({
	action, values, error: null, local: null, measurement: null, review: null, job: null, ...extra
});

export const load: PageServerLoad = async ({ params, url, request }) => {
	// serve.js sets a loopback http ORIGIN by default; tailnet mode carries an explicit https ORIGIN.
	// Only an https url.origin with no ORIGIN at all (adapter-node started without serve.js) is a misconfiguration.
	const originMisconfigured = url.protocol === 'https:' && !process.env.ORIGIN;
	const signal = request.signal;
	const [sources, runs, reviews, types] = await Promise.all([
		runControl(listSources, signal),
		runControl(listRuns(params.id), signal),
		runControl(listReviews(params.id), signal),
		runControl(getJobTypes, signal)
	]);
	const keys = { save: newFormKey(), author: newFormKey() };
	// Cross-lane step bar (ROUTES_REVIEW_S3 6.1); Review/Download need a selected run.
	const step = (runId: string | null): StepContext => ({ current: 'capture', source_artifact_id: params.id, run_id: runId, disabled_reasons: {} });
	if (!sources.ok) {
		return { sourceId: params.id, source: null, error: sources.error, runs: [], runsError: null, reviews: [], reviewsError: null,
			selectedRun: null, captureAdmission: null, typesError: null, keys, originMisconfigured, stepContext: step(null) };
	}
	const source = sources.data.sources.find((s) => s.source_artifact_id === params.id) ?? null;
	if (source === null) error(404, { message: 'The control API lists no such admitted source.', code: 'source_not_found' });
	const eligible = runs.ok ? runs.data.runs.filter((run) => run.role === 'baseline') : [];
	const requested = url.searchParams.get('run');
	const selectedRun = requested !== null && isRunId(requested) ? (eligible.find((run) => run.run_id === requested) ?? null) : null;
	const capture = types.ok ? types.data.job_types.find((entry) => entry.tool === 'capture_profile') ?? null : null;
	return {
		sourceId: params.id,
		source,
		error: null,
		runs: eligible,
		runsError: runs.ok ? null : runs.error,
		reviews: reviews.ok ? reviews.data.reviews : [],
		reviewsError: reviews.ok ? null : reviews.error,
		selectedRun,
		captureAdmission: capture?.admission_state ?? null,
		typesError: types.ok ? null : types.error,
		keys,
		originMisconfigured,
		stepContext: step(selectedRun?.run_id ?? null)
	};
};

export const actions: Actions = {
	measure: async ({ params, request }) => {
		const data = await request.formData();
		const values = echo(data, ECHO);
		const built = measurementBody(data);
		if (!built.ok) return fail(400, outcome('measure', values, { local: { code: built.code, message: built.message } }));
		const result = await runControl(measureInterval(params.id, built.body as { run_id: string; start_seconds: number; end_seconds: number }), request.signal);
		if (!result.ok) return fail(result.httpStatus, outcome('measure', values, { error: result.error }));
		return outcome('measure', values, { measurement: result.data });
	},
	save: async ({ params, request }) => {
		const data = await request.formData();
		const values = echo(data, ECHO);
		const expected = String(data.get('expected_source_sha256') ?? '');
		if (!SHA256.test(expected)) return fail(400, outcome('save', values, { local: { code: 'invalid_form_key', message: 'Reload the page.' } }));
		const built = reviewBody(data, expected);
		if (!built.ok) return fail(400, outcome('save', values, { local: { code: built.code, message: built.message } }));
		const result = await runControl(createReview(params.id, built.body), request.signal);
		if (!result.ok) return fail(result.httpStatus, outcome('save', values, { error: result.error }));
		return outcome('save', values, { review: result.data });
	},
	author: async ({ params, request }) => {
		const data = await request.formData();
		data.set('preset', 'fuller'); // capture page authors FULLER only; custom controls live on the process page
		const built = authorBody(data, params.id);
		const values = echo(data, ['capture_review_id']);
		if (!built.ok) return fail(400, outcome('author', values, { local: { code: built.code, message: built.message } }));
		const result = await runControl(submitProcessingJob(built.body), request.signal);
		if (!result.ok) return fail(result.httpStatus, outcome('author', values, { error: result.error }));
		return outcome('author', values, { job: result.data });
	}
};
