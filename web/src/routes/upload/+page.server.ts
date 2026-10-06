import type { PageServerLoad } from './$types';
import { controlConfigured, runControl } from '$lib/server/control-client';
import { Effect } from 'effect';

// Configuration state only (no network): the page renders typed config refusals before any upload.
export const load: PageServerLoad = async () => {
	const result = await runControl(controlConfigured.pipe(Effect.as({ status: 200, data: null })));
	return { error: result.ok ? null : result.error };
};
