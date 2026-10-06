import type { ParamMatcher } from '@sveltejs/kit';
import { isArtifactId } from '$lib/schema/control';

// Source artifact ids (art_ + 32 hex). Anything else 404s before any control-API request.
export const match: ParamMatcher = (param) => isArtifactId(param);
