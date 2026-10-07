// Pure option builders of the process route (WEB_TESTS_S3.md 5.1; ROUTES_PROCESSING M6).
import fc from 'fast-check';
import { describe, expect, it } from 'vitest';
import { e2eFixture } from '../../../../tests/fixtures';
import { overlapsSetup as clientOverlapsSetup, SETUP_INTERVAL_SECONDS } from '../../components/processing/setup';
import { KNOB_GROUPS, boundsText, buildPresetOptions, groupKnobs, overlapsSetup, renderableReviews, type OptionInput, type ReviewLike } from './options';

const SHA = '0'.repeat(63) + '1';
const OTHER_SHA = '0'.repeat(63) + '2';
const review = (overrides: Partial<ReviewLike> = {}): ReviewLike => ({
	review_id: `rev_${'0'.repeat(31)}1`, source_sha256: SHA, review_status: 'reviewed_candidate', authorization_scope: 'experimental_capture_render', ...overrides
});
const input = (overrides: Partial<OptionInput> = {}): OptionInput => ({
	reviews: [], sourceSha256: SHA, denoiseProfiles: [], captureAdmission: 'admitted', denoiseAdmission: 'admitted', applyAdmission: 'admitted', ...overrides
});
const option = (options: ReturnType<typeof buildPresetOptions>, id: string) => {
	const found = options.find((item) => item.id === id);
	expect(found, id).toBeDefined();
	return found!;
};

describe('renderableReviews', () => {
	it('keeps only reviews of this exact source with render scope that are not rejected', () => {
		const reviews = [
			review(),
			review({ review_id: 'r2', source_sha256: OTHER_SHA }),
			review({ review_id: 'r3', authorization_scope: 'profile_authoring' }),
			review({ review_id: 'r4', review_status: 'rejected_contaminated' }),
			review({ review_id: 'r5', review_status: 'reviewed_possible_contamination' })
		];
		expect(renderableReviews(reviews, SHA).map((item) => item.review_id)).toEqual([reviews[0].review_id, 'r5']);
		expect(renderableReviews(reviews, '')).toEqual([]);
	});
});

describe('buildPresetOptions: FULLER requires a reviewed interval', () => {
	it('state 1: no current review -> FULLER is the default selection, disabled with capture_interval_required', () => {
		const fuller = option(buildPresetOptions(input()), 'fuller');
		expect(fuller.default).toBe(true);
		expect(fuller.enabled).toBe(false);
		expect(fuller.refusal_code).toBe('capture_interval_required');
		expect(fuller.reviewIds).toEqual([]);
		expect(fuller.jobPath).toEqual(['capture_profile', 'apply_capture_profile']);
		const custom = option(buildPresetOptions(input()), 'custom');
		expect(custom.enabled).toBe(false);
		expect(custom.refusal_code).toBe('capture_interval_required');
	});

	it('state 2: a valid experimental_capture_render review -> FULLER is enabled with that review', () => {
		const fuller = option(buildPresetOptions(input({ reviews: [review()] })), 'fuller');
		expect(fuller.enabled).toBe(true);
		expect(fuller.refusal_code).toBeNull();
		expect(fuller.reviewIds).toEqual([review().review_id]);
		expect(fuller.controls).toBe('fuller_verbatim');
	});

	it('a review that is rejected, of another source or only profile_authoring does not enable FULLER', () => {
		for (const blocked of [review({ review_status: 'rejected_contaminated' }), review({ source_sha256: OTHER_SHA }), review({ authorization_scope: 'profile_authoring' })]) {
			const fuller = option(buildPresetOptions(input({ reviews: [blocked] })), 'fuller');
			expect(fuller.enabled).toBe(false);
			expect(fuller.refusal_code).toBe('capture_interval_required');
		}
	});

	it('a pending web adapter disables FULLER with tool_pending_admission even with a review', () => {
		for (const pending of [{ captureAdmission: 'pending_root_admission' }, { applyAdmission: 'pending_root_admission' }, { applyAdmission: 'unknown' }]) {
			const fuller = option(buildPresetOptions(input({ reviews: [review()], ...pending })), 'fuller');
			expect(fuller.enabled).toBe(false);
			expect(fuller.refusal_code).toBe('tool_pending_admission');
			expect(fuller.reviewIds.length).toBe(1);
		}
	});

	it('agrees with the recorded fixtures: plain source refused, reviewed source enabled (test seam), pending in the product default', () => {
		const sources = (e2eFixture('sources.json') as { sources: Array<{ source_artifact_id: string; sha256: string }> }).sources;
		const ids = e2eFixture('ids.json') as { source_plain: string; source_reviewed: string };
		const types = (file: string) => (e2eFixture(file) as { job_types: Array<{ tool: string; admission_state: string; profiles?: Array<{ name: string; source_bound_sha256: string | null }> }> }).job_types;
		const build = (alias: 'plain' | 'reviewed', catalogue: string) => {
			const source = sources.find((item) => item.source_artifact_id === ids[`source_${alias}`])!;
			const reviews = (e2eFixture(`reviews_${alias}.json`) as { reviews: ReviewLike[] }).reviews;
			const entry = (tool: string) => types(catalogue).find((item) => item.tool === tool)!;
			return option(buildPresetOptions({
				reviews, sourceSha256: source.sha256, denoiseProfiles: entry('denoise').profiles ?? [],
				captureAdmission: entry('capture_profile').admission_state, denoiseAdmission: entry('denoise').admission_state, applyAdmission: entry('apply_capture_profile').admission_state
			}), 'fuller');
		};
		expect(build('plain', 'job_types.json')).toMatchObject({ enabled: false, refusal_code: 'capture_interval_required' });
		expect(build('reviewed', 'job_types.json')).toMatchObject({ enabled: true, refusal_code: null });
		const product = build('reviewed', 'job_types_product_default.json');
		const applyState = types('job_types_product_default.json').find((item) => item.tool === 'apply_capture_profile')!.admission_state;
		expect(product.enabled).toBe(applyState === 'admitted');
		expect(product.refusal_code).toBe(applyState === 'admitted' ? null : 'tool_pending_admission');
	});
});

describe('buildPresetOptions: other choices', () => {
	it('offers the three fixed denoise profiles explicitly and never as the default', () => {
		const options = buildPresetOptions(input());
		for (const id of ['conservative3', 'mild6', 'bypass']) {
			expect(option(options, id)).toMatchObject({ enabled: true, default: false, refusal_code: null, jobPath: ['denoise'], controls: 'fixed_profile' });
		}
		expect(options.filter((item) => item.default).map((item) => item.id)).toEqual(['fuller']);
		const pending = buildPresetOptions(input({ denoiseAdmission: 'pending_root_admission' }));
		expect(option(pending, 'bypass')).toMatchObject({ enabled: false, refusal_code: 'tool_pending_admission' });
	});

	it('a source-bound profile is offered only for its own source', () => {
		const profiles = [{ name: 'captured8', source_bound_sha256: OTHER_SHA }, { name: 'captured9', source_bound_sha256: SHA }, { name: 'bypass', source_bound_sha256: null }];
		const options = buildPresetOptions(input({ denoiseProfiles: profiles }));
		expect(option(options, 'captured8')).toMatchObject({ enabled: false, refusal_code: 'profile_source_mismatch' });
		expect(option(options, 'captured9')).toMatchObject({ enabled: true, refusal_code: null });
		expect(options.filter((item) => item.id === 'bypass').length).toBe(1);
	});

	it('the low shelf is never enabled and never a default', () => {
		for (const shelfAvailable of [false, true, undefined]) {
			const shelf = option(buildPresetOptions(input({ reviews: [review()], shelfAvailable })), 'fuller-shelf');
			expect(shelf.enabled).toBe(false);
			expect(shelf.default).toBe(false);
			expect(shelf.jobPath).toEqual([]);
			expect(shelf.refusal_code).toBe(shelfAvailable ? 'unreviewed_trial' : 'shelf_not_exposed');
		}
	});

	it('no option is labelled or keyed as a high-pass, low-cut or notch', () => {
		const options = buildPresetOptions(input({ reviews: [review()], denoiseProfiles: [{ name: 'captured9', source_bound_sha256: SHA }] }));
		for (const item of options) expect(`${item.id} ${item.label} ${item.reason}`).not.toMatch(/high.?pass|low.?cut|notch|hpf/i);
	});
});

describe('groupKnobs and boundsText', () => {
	it('groups the live capture_profile catalogue without inventing a knob or a bound', () => {
		const capture = (e2eFixture('job_types.json') as { job_types: Array<{ tool: string; knobs: Record<string, { group?: string }> }> }).job_types.find((item) => item.tool === 'capture_profile')!;
		const groups = groupKnobs(capture.knobs);
		expect(Object.keys(groups)).toEqual([...KNOB_GROUPS]);
		const grouped = Object.values(groups).flat();
		expect(new Set(grouped).size).toBe(grouped.length);
		for (const name of grouped) expect(name in capture.knobs, name).toBe(true);
		expect(grouped.some((name) => /high.?pass|low.?cut|notch/i.test(name))).toBe(false);
		expect(groupKnobs({ a: { group: 'tone' }, b: { group: 'elsewhere' }, c: {} })).toEqual({ cleanup: [], tone: ['a'], dynamics: [], delivery_loudness: [], supervision: [] });
	});
	it('shows bounds as text and says unknown when there is no descriptor', () => {
		expect(boundsText(undefined)).toBe('bounds unknown');
		expect(boundsText({ minimum: 1, maximum: 60, type: 'integer' })).toBe('1..60; integer');
		expect(boundsText({ enum: ['fuller', 'custom'], type: 'string' })).toBe('fuller / custom; string');
		expect(boundsText({ maximum: 0 })).toBe('−∞..0');
		expect(boundsText({})).toBe('');
	});
});

describe('overlapsSetup (property)', () => {
	it('is true exactly for intervals [start, end) that intersect the first five seconds [0, 5)', () => {
		expect(SETUP_INTERVAL_SECONDS).toBe(5);
		const start = fc.double({ min: 0, max: 600, noNaN: true });
		const length = fc.double({ min: 0.1, max: 10, noNaN: true });
		fc.assert(
			fc.property(start, length, (from, span) => {
				const to = from + span;
				const intersects = from < 5 && to > 0;
				expect(overlapsSetup(from)).toBe(intersects);
				expect(clientOverlapsSetup(from)).toBe(intersects);
			})
		);
	});
	it('boundary values: 4.999 overlaps, 5 does not; a non-finite start reports no overlap (the control API validates the number)', () => {
		expect(overlapsSetup(0)).toBe(true);
		expect(overlapsSetup(4.999)).toBe(true);
		expect(overlapsSetup(5)).toBe(false);
		expect(overlapsSetup(5.5)).toBe(false);
		expect(overlapsSetup(Number.NaN)).toBe(false);
		expect(clientOverlapsSetup(4.999)).toBe(true);
		expect(clientOverlapsSetup(5)).toBe(false);
	});
});
