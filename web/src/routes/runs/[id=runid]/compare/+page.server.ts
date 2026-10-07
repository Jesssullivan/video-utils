import type { PageServerLoad } from './$types';
import { runControl } from '$lib/server/control-client';
import { getLayers } from '$lib/server/runs/client';
import { isEvidenceId } from '$lib/server/runs/schema';

export const load: PageServerLoad = async ({ params, url, request }) => {
	const requested = url.searchParams.get('evidence');
	const evidence = requested !== null && isEvidenceId(requested) ? requested : null;
	const result = await runControl(getLayers(params.id, evidence), request.signal);
	return result.ok ? { layers: result.data, layersError: null } : { layers: null, layersError: result.error };
};
