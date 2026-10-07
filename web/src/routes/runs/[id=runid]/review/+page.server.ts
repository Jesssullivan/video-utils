import type { PageServerLoad } from './$types';
import { readAnnotations, runControl } from '$lib/server/control-client';
import { getLayers } from '$lib/server/runs/client';
import { isEvidenceId } from '$lib/server/runs/schema';

// Layers for the review workspace plus the annotation store of the admitted source that has a clock.
// When several sources qualify the operator picks one (?source=); the default is the most recent.
export const load: PageServerLoad = async ({ params, url, request, parent }) => {
	const { graph } = await parent();
	const requested = url.searchParams.get('evidence');
	const evidence = requested !== null && isEvidenceId(requested) ? requested : null;
	const layers = await runControl(getLayers(params.id, evidence), request.signal);
	const admitted = graph?.admitted_sources ?? [];
	const clocked = admitted.filter((source) => source.has_annotation_clock === true);
	const picked = url.searchParams.get('source');
	const annotationSource = clocked.find((source) => source.source_artifact_id === picked) ?? clocked[0] ?? null;
	const videoSource = annotationSource ?? admitted[0] ?? null;
	let annotations = null;
	let markDisabledReason: string | null = null;
	if (graph === null) markDisabledReason = 'run_graph_unavailable';
	else if (admitted.length === 0) markDisabledReason = 'run_source_not_admitted';
	else if (annotationSource === null) markDisabledReason = 'annotation_source_clock_unknown';
	else {
		const result = await runControl(readAnnotations(annotationSource.source_artifact_id), request.signal);
		if (result.ok) annotations = result.data;
		else markDisabledReason = result.error.upstream_code ?? result.error.code;
	}
	return {
		layers: layers.ok ? layers.data : null,
		layersError: layers.ok ? null : layers.error,
		clockedSources: clocked.map((source) => source.source_artifact_id),
		annotationSourceId: annotations ? (annotationSource?.source_artifact_id ?? null) : null,
		videoSourceId: videoSource?.source_artifact_id ?? null,
		annotations,
		markDisabledReason: annotations ? null : markDisabledReason
	};
};
