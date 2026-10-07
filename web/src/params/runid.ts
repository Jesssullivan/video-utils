import type { ParamMatcher } from '@sveltejs/kit';

// Run IDs are one artifact_ids.COMPONENT (^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$) without `.partial`.
// Anything else 404s at routing time, before any control-API request.
export const RUN_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;

export const isRunId = (value: string): boolean => RUN_ID_PATTERN.test(value) && !value.includes('.partial');

export const match: ParamMatcher = (param) => isRunId(param);
