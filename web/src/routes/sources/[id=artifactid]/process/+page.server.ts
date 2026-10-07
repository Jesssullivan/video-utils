import { error, fail } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import { listSources, runControl } from '$lib/server/control-client';
import { getJobTypes, getLaneJob, listLaneJobs, listReviews, listRuns, submitProcessingJob } from '$lib/server/processing/client';
import { applyBody, authorBody, denoiseBody, echo, type Built } from '$lib/server/processing/forms';
import { buildPresetOptions, groupKnobs } from '$lib/server/processing/options';
import type { JobTypeEntry, LaneJobProjection } from '$lib/server/processing/schema';
import type { BffError } from '$lib/control-types';
import { newFormKey } from '$lib/idempotency';
import type { StepContext } from '$lib/components/review/step-context';

// Process (ROUTES_PROCESSING_S3 section 8): FULLER default (needs a saved reviewed interval),
// conservative3 / mild6 / bypass explicit, source-bound captured* only for their own source, no
// shelf until a typed tool exposes it. Nothing renders on knob change; every render is an explicit
// submit carrying a fresh ui-<32 hex> key. Renders are full-take only (no typed interval argument).
const PROJECTED = 12;

export type ProcessOutcome = {
	action: 'denoise' | 'author' | 'apply';
	values: Record<string, string>;
	error: BffError | null;
	local: { code: string; message: string } | null;
	job: LaneJobProjection | null;
};

const outcome = (action: ProcessOutcome['action'], values: Record<string, string>, extra: Partial<ProcessOutcome> = {}): ProcessOutcome => ({
	action, values, error: null, local: null, job: null, ...extra
});

const entry = (types: ReadonlyArray<JobTypeEntry>, tool: string) => types.find((item) => item.tool === tool) ?? null;

export const load: PageServerLoad = async ({ params, request, url }) => {
	// serve.js sets a loopback http ORIGIN by default; tailnet mode carries an explicit https ORIGIN.
	// Only an https url.origin with no ORIGIN at all (adapter-node started without serve.js) is a misconfiguration.
	const originMisconfigured = url.protocol === 'https:' && !process.env.ORIGIN;
	const signal = request.signal;
	const [sources, runs, reviews, types, jobs] = await Promise.all([
		runControl(listSources, signal),
		runControl(listRuns(params.id), signal),
		runControl(listReviews(params.id), signal),
		runControl(getJobTypes, signal),
		runControl(listLaneJobs(params.id), signal)
	]);
	const keys = { denoise: newFormKey(), author: newFormKey(), apply: newFormKey() };
	// Cross-lane step bar (ROUTES_REVIEW_S3 6.1): Review/Download point at the newest succeeded processing run, when any.
	const step = (runId: string | null): StepContext => ({ current: 'process', source_artifact_id: params.id, run_id: runId, disabled_reasons: {} });
	if (!sources.ok) {
		return { sourceId: params.id, source: null, error: sources.error, options: [], catalogue: null, typesError: null, groups: {},
			reviews: [], reviewsError: null, runs: [], jobsError: null, processing: [], keys, originMisconfigured, stepContext: step(null) };
	}
	const source = sources.data.sources.find((s) => s.source_artifact_id === params.id) ?? null;
	if (source === null) error(404, { message: 'The control API lists no such admitted source.', code: 'source_not_found' });
	const catalogue = types.ok ? types.data.job_types : [];
	const capture = entry(catalogue, 'capture_profile');
	const denoise = entry(catalogue, 'denoise');
	const apply = entry(catalogue, 'apply_capture_profile');
	const reviewList = reviews.ok ? reviews.data.reviews : [];
	const options = buildPresetOptions({
		reviews: reviewList,
		sourceSha256: source.sha256,
		denoiseProfiles: denoise?.profiles ?? [],
		captureAdmission: capture?.admission_state ?? 'unknown',
		denoiseAdmission: denoise?.admission_state ?? 'unknown',
		applyAdmission: apply?.admission_state ?? 'unknown',
		shelfAvailable: capture?.low_shelf?.available ?? false
	});
	const processingRows = jobs.ok ? jobs.data.jobs.filter((job) => job.tool !== undefined).slice(0, PROJECTED) : [];
	const projected = await Promise.all(processingRows.map((job) => runControl(getLaneJob(job.job_id), signal)));
	const processing = projected.flatMap((result) => (result.ok ? [result.data] : []));
	return {
		sourceId: params.id,
		source,
		error: null,
		options,
		catalogue: { capture, denoise, apply },
		typesError: types.ok ? null : types.error,
		groups: capture ? groupKnobs(capture.knobs) : {},
		reviews: reviewList,
		reviewsError: reviews.ok ? null : reviews.error,
		runs: runs.ok ? runs.data.runs : [],
		jobsError: jobs.ok ? null : jobs.error,
		processing,
		keys,
		originMisconfigured,
		stepContext: step(processing.find((job) => job.state === 'succeeded' && job.run_id)?.run_id ?? null)
	};
};

async function submit(action: ProcessOutcome['action'], built: Built, values: Record<string, string>, signal: AbortSignal) {
	if (!built.ok) return fail(400, outcome(action, values, { local: { code: built.code, message: built.message } }));
	const result = await runControl(submitProcessingJob(built.body), signal);
	if (!result.ok) return fail(result.httpStatus, outcome(action, values, { error: result.error }));
	return outcome(action, values, { job: result.data });
}

const CUSTOM_FIELDS = ['preset', 'capture_review_id', 'reduction_db', 'noise_floor_db', 'adaptivity', 'gain_smooth', 'integrated_lufs',
	'true_peak_dbtp', 'timeout_seconds', 'compressor_enabled', 'compressor_threshold_db', 'compressor_ratio', 'compressor_attack_ms',
	'compressor_release_ms', 'compressor_knee_db', ...[0, 1, 2].flatMap((i) => [`eq_${i}_frequency_hz`, `eq_${i}_gain_db`, `eq_${i}_q`])];

export const actions: Actions = {
	denoise: async ({ params, request }) => {
		const data = await request.formData();
		return submit('denoise', denoiseBody(data, params.id), echo(data, ['profile', 'timeout_seconds']), request.signal);
	},
	author: async ({ params, request }) => {
		const data = await request.formData();
		return submit('author', authorBody(data, params.id), echo(data, CUSTOM_FIELDS), request.signal);
	},
	apply: async ({ params, request }) => {
		const data = await request.formData();
		return submit('apply', applyBody(data, params.id), echo(data, ['capture_profile_job_id', 'timeout_seconds']), request.signal);
	}
};
