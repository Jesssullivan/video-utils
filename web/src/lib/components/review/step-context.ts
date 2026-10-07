// Cross-lane step-bar interface (ROUTES_REVIEW_S3.md 6.1). Client-safe; routes_processing may provide the same
// shape from source routes as `page.data.stepContext`.
export type StepKey = 'clip' | 'capture' | 'process' | 'review' | 'download';

export interface StepContext {
	current: StepKey;
	source_artifact_id: string | null;
	run_id: string | null;
	disabled_reasons: Partial<Record<StepKey, string>>;
	/** Review sub-tab within the run routes (Review, Compare, Graph); optional for other lanes. */
	review_tab?: 'review' | 'compare' | 'graph' | null;
}

export const STEP_ORDER: ReadonlyArray<{ key: StepKey; label: string }> = [
	{ key: 'clip', label: 'Clip' },
	{ key: 'capture', label: 'Capture' },
	{ key: 'process', label: 'Process' },
	{ key: 'review', label: 'Review' },
	{ key: 'download', label: 'Download' }
];

const SOURCE = /^art_[0-9a-f]{32}$/;
const RUN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;

/** Target route of a step, or null with the reason shown instead (never a dead link). */
export function stepTarget(context: StepContext, key: StepKey): { href: string | null; reason: string | null } {
	const disabled = context.disabled_reasons?.[key] ?? null;
	const source = context.source_artifact_id && SOURCE.test(context.source_artifact_id) ? context.source_artifact_id : null;
	const run = context.run_id && RUN.test(context.run_id) && !context.run_id.includes('.partial') ? context.run_id : null;
	let href: string | null = null;
	if (key === 'clip' && source) href = `/sources/${source}`;
	if (key === 'capture' && source) href = `/sources/${source}/capture`;
	if (key === 'process' && source) href = `/sources/${source}/process`;
	if (key === 'review' && run) href = `/runs/${run}/review`;
	if (key === 'download' && run) href = `/runs/${run}/deliver`;
	if (disabled) return { href: null, reason: disabled };
	if (href === null) {
		return { href: null, reason: key === 'review' || key === 'download' ? 'no run selected' : 'run_source_not_admitted' };
	}
	return { href, reason: null };
}

export function isStepContext(value: unknown): value is StepContext {
	if (typeof value !== 'object' || value === null) return false;
	const context = value as Record<string, unknown>;
	return typeof context.current === 'string' && STEP_ORDER.some((step) => step.key === context.current);
}
