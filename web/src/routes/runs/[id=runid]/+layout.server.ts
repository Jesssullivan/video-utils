import { error } from '@sveltejs/kit';
import type { LayoutServerLoad } from './$types';
import { runControl } from '$lib/server/control-client';
import { getRun } from '$lib/server/runs/client';
import type { StepContext } from '$lib/components/review/step-context';

// Run graph for every run route plus the step-bar context (ROUTES_REVIEW_S3.md 6.1).
export const load: LayoutServerLoad = async ({ params, request, url }) => {
	const result = await runControl(getRun(params.id), request.signal);
	if (!result.ok && result.error.upstream_code === 'unknown_run') {
		error(404, { message: 'The control API reports no such run.', code: 'unknown_run' });
	}
	const graph = result.ok ? result.data : null;
	const clocked = graph?.admitted_sources.find((source) => source.has_annotation_clock) ?? null;
	const anySource = clocked ?? graph?.admitted_sources[0] ?? null;
	const tail = url.pathname.split('/').slice(3).join('/');
	const current: StepContext['current'] = tail.startsWith('deliver') ? 'download' : 'review';
	const reviewTab = tail.startsWith('compare') ? 'compare' : tail.startsWith('review') ? 'review' : tail === '' ? 'graph' : null;
	const sourceReason = graph === null ? 'run graph unavailable' : graph.admitted_sources_lookup === 'unavailable' ? 'source lookup unavailable' : 'run_source_not_admitted';
	const stepContext: StepContext = {
		current,
		source_artifact_id: anySource?.source_artifact_id ?? null,
		run_id: params.id,
		disabled_reasons: anySource ? {} : { clip: sourceReason, capture: sourceReason, process: sourceReason },
		review_tab: reviewTab
	};
	return { runId: params.id, graph, graphError: result.ok ? null : result.error, stepContext };
};
