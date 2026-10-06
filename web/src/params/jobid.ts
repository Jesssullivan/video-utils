import type { ParamMatcher } from '@sveltejs/kit';
import { isOpaqueId } from '$lib/schema/control';

// Invalid job ids 404 at routing time, before any control-API request.
export const match: ParamMatcher = (param) => isOpaqueId(param);
