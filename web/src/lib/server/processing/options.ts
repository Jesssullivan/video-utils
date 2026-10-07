// Pure option builders for the process route (ROUTES_PROCESSING_S3 sections 4 and 8).
// No imports and no I/O: node can import this file with type stripping, so the Python suite
// checks the same builder the page uses (M6). The control API stays the single validator:
// these builders only decide what is offered and which typed refusal a disabled option shows.

export type ReviewLike = {
	readonly review_id: string;
	readonly source_sha256: string;
	readonly review_status: string;
	readonly authorization_scope: string;
	readonly overlaps_setup_interval?: boolean;
};

export type ProfileLike = { readonly name: string; readonly source_bound_sha256: string | null };

export type OptionInput = {
	readonly reviews: ReadonlyArray<ReviewLike>;
	readonly sourceSha256: string;
	readonly denoiseProfiles: ReadonlyArray<ProfileLike>;
	readonly captureAdmission: string;
	readonly denoiseAdmission: string;
	readonly applyAdmission: string;
	readonly shelfAvailable?: boolean;
};

export type PresetOption = {
	readonly id: string;
	readonly label: string;
	readonly jobPath: ReadonlyArray<string>;
	readonly enabled: boolean;
	readonly default: boolean;
	readonly refusal_code: string | null;
	readonly reason: string;
	readonly reviewIds: ReadonlyArray<string>;
	readonly controls: 'fuller_verbatim' | 'custom_explicit' | 'fixed_profile' | 'none';
};

const FIXED_DENOISE = ['conservative3', 'mild6', 'bypass'] as const;

/** Saved reviews that may author a renderable profile for this exact source. */
export function renderableReviews(reviews: ReadonlyArray<ReviewLike>, sourceSha256: string): ReviewLike[] {
	return reviews.filter(
		(review) =>
			review.source_sha256 === sourceSha256 &&
			review.authorization_scope === 'experimental_capture_render' &&
			review.review_status !== 'rejected_contaminated'
	);
}

function captureOption(id: string, label: string, controls: PresetOption['controls'], input: OptionInput, isDefault: boolean): PresetOption {
	const usable = renderableReviews(input.reviews, input.sourceSha256);
	const ids = usable.map((review) => review.review_id);
	if (usable.length === 0) {
		return {
			id, label, jobPath: ['capture_profile', 'apply_capture_profile'], enabled: false, default: isDefault,
			refusal_code: 'capture_interval_required',
			reason: 'Save a reviewed capture interval (scope experimental_capture_render, not rejected) on the capture page first.',
			reviewIds: [], controls
		};
	}
	if (input.captureAdmission !== 'admitted' || input.applyAdmission !== 'admitted') {
		return {
			id, label, jobPath: ['capture_profile', 'apply_capture_profile'], enabled: false, default: isDefault,
			refusal_code: 'tool_pending_admission',
			reason: 'capture_profile / apply_capture_profile web adapters await root admission.',
			reviewIds: ids, controls
		};
	}
	return {
		id, label, jobPath: ['capture_profile', 'apply_capture_profile'], enabled: true, default: isDefault,
		refusal_code: null, reason: 'Author from a saved review, then render the full take from the authored profile.',
		reviewIds: ids, controls
	};
}

/** Preset choices in display order. FULLER is the default selection even while disabled. */
export function buildPresetOptions(input: OptionInput): PresetOption[] {
	const options: PresetOption[] = [
		captureOption('fuller', 'FULLER (default; reviewed interval required)', 'fuller_verbatim', input, true),
		captureOption('custom', 'Custom capture (every control explicit)', 'custom_explicit', input, false)
	];
	for (const name of FIXED_DENOISE) {
		const admitted = input.denoiseAdmission === 'admitted';
		options.push({
			id: name,
			label: name === 'conservative3' ? 'conservative3 (explicit, no capture binding)' : `${name} (explicit)`,
			jobPath: ['denoise'], enabled: admitted, default: false,
			refusal_code: admitted ? null : 'tool_pending_admission',
			reason: admitted ? 'Fixed denoise profile; no knobs except the timeout.' : 'The denoise web adapter awaits root admission.',
			reviewIds: [], controls: 'fixed_profile'
		});
	}
	for (const profile of input.denoiseProfiles) {
		if (profile.source_bound_sha256 === null || (FIXED_DENOISE as ReadonlyArray<string>).includes(profile.name)) continue;
		const matches = profile.source_bound_sha256 === input.sourceSha256;
		const admitted = input.denoiseAdmission === 'admitted';
		options.push({
			id: profile.name,
			label: `${profile.name} (source-bound experimental)`,
			jobPath: ['denoise'],
			enabled: matches && admitted,
			default: false,
			refusal_code: !matches ? 'profile_source_mismatch' : admitted ? null : 'tool_pending_admission',
			reason: matches
				? 'Bound to this source sha256 and its reviewed 4.10–4.95 s interval.'
				: `Unavailable: bound to source ${profile.source_bound_sha256.slice(0, 12)}…, not this recording.`,
			reviewIds: [], controls: 'fixed_profile'
		});
	}
	options.push({
		id: 'fuller-shelf',
		label: 'Fuller + low shelf',
		jobPath: [],
		enabled: false,
		default: false,
		refusal_code: input.shelfAvailable ? 'unreviewed_trial' : 'shelf_not_exposed',
		reason: 'Unavailable — no typed tool exposes the shelf. Never a default.',
		reviewIds: [], controls: 'none'
	});
	return options;
}

export type KnobSpec = {
	readonly type?: string;
	readonly minimum?: number;
	readonly maximum?: number;
	readonly enum?: ReadonlyArray<string>;
	readonly default?: unknown;
	readonly description?: string;
	readonly group?: string;
	readonly items?: unknown;
	readonly properties?: unknown;
};

export const KNOB_GROUPS = ['cleanup', 'tone', 'dynamics', 'delivery_loudness', 'supervision'] as const;

/** Knob names per display group, from the live catalogue (never a hard-coded bound). */
export function groupKnobs(knobs: Readonly<Record<string, KnobSpec>>): Record<string, string[]> {
	const groups: Record<string, string[]> = {};
	for (const group of KNOB_GROUPS) groups[group] = [];
	for (const [name, spec] of Object.entries(knobs)) {
		const group = spec.group ?? 'other';
		if (group in groups) groups[group].push(name);
	}
	return groups;
}

/** "min..max" text from a descriptor knob (bounds shown, never enforced client-side). */
export function boundsText(spec: KnobSpec | undefined): string {
	if (!spec) return 'bounds unknown';
	const parts: string[] = [];
	if (spec.minimum !== undefined || spec.maximum !== undefined) parts.push(`${spec.minimum ?? '−∞'}..${spec.maximum ?? '∞'}`);
	if (spec.enum) parts.push(spec.enum.join(' / '));
	if (spec.type) parts.push(spec.type);
	return parts.join('; ');
}

/** True when [start, end) in decoded-source seconds overlaps the first five seconds [0, 5). */
export function overlapsSetup(start: number): boolean {
	return Number.isFinite(start) && start < 5;
}
