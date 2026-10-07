// Lane-local closed schemas of the S3 processing routes (WEB_TESTS_S3.md 5.1; metrics W4, W5).
import fc from 'fast-check';
import { describe, expect, it } from 'vitest';
import { decodeClosed, e2eFixture, recorded } from '../../../../tests/fixtures';
import {
	JobTypes,
	LANE_FIELD_NAMES,
	LaneJobList,
	LaneJobProjection,
	Measurement,
	REVIEW_ID_PATTERN,
	RUN_ID_PATTERN,
	ReviewList,
	ReviewRecord,
	RunList
} from './schema';

describe('e2e fixtures of each processing shape decode', () => {
	it('job-type catalogues: the test-seam catalogue and the product-default catalogue', () => {
		for (const file of ['job_types.json', 'job_types_product_default.json']) {
			const decoded = decodeClosed(JobTypes, e2eFixture(file));
			expect(decoded.ok, file).toBe(true);
			if (!decoded.ok) continue;
			expect(decoded.value.job_types.map((entry) => entry.tool).sort()).toEqual(['apply_capture_profile', 'capture_profile', 'denoise', 'share_export']);
		}
		const product = decodeClosed(JobTypes, e2eFixture('job_types_product_default.json'));
		// Recorded at the lane baseline: the product never self-admits; the seam catalogue is test-only.
		expect(product.ok && product.value.job_types.every((entry) => ['admitted', 'pending_root_admission'].includes(entry.admission_state))).toBe(true);
	});

	it('source run lists', () => {
		const lists = recorded(/^\/api\/v1\/sources\/art_[0-9a-f]{32}\/runs$/);
		expect(lists.length).toBe(2);
		for (const [file, body] of lists) {
			const decoded = decodeClosed(RunList, body);
			expect(decoded.ok, file).toBe(true);
			if (!decoded.ok) continue;
			// The probe duration is unknown by contract: null with its reason, never a default.
			expect(decoded.value.unknowns.probe_duration_seconds).toBeNull();
			expect(decoded.value.unknowns.probe_duration_seconds_reason.length).toBeGreaterThan(0);
		}
	});

	it('capture review lists (one saved review; one empty list)', () => {
		const lists = recorded(/^\/api\/v1\/sources\/art_[0-9a-f]{32}\/capture-reviews$/);
		expect(lists.length).toBe(2);
		const counts = lists.map(([file, body]) => {
			const decoded = decodeClosed(ReviewList, body);
			expect(decoded.ok, file).toBe(true);
			return decoded.ok ? decoded.value.reviews.length : -1;
		});
		expect(counts.sort()).toEqual([0, 1]);
	});

	it('the recorded saved review and measurement keep their unknown blocks verbatim', () => {
		const review = e2eFixture('review_saved_acknowledged.json') as { unknowns: Record<string, unknown> };
		const decodedReview = decodeClosed(ReviewRecord, review);
		expect(decodedReview.ok).toBe(true);
		if (decodedReview.ok) {
			expect(decodedReview.value.unknowns).toEqual(review.unknowns);
			expect(decodedReview.value.identity_authenticated).toBe(false);
			expect(decodedReview.value.setup_interval_acknowledged).toBe(true);
			expect(decodedReview.value.overlaps_setup_interval).toBe(true);
			expect(decodedReview.value.review_status).not.toBe('reviewed_candidate');
		}
		const measurement = e2eFixture('measurement.json') as { unknowns: Record<string, unknown> };
		const decoded = decodeClosed(Measurement, measurement);
		expect(decoded.ok).toBe(true);
		if (decoded.ok) {
			expect(decoded.value.unknowns).toEqual(measurement.unknowns);
			expect(Object.keys(measurement.unknowns).length).toBeGreaterThan(0);
			expect(decoded.value.selects_interval).toBe(false);
			expect(decoded.value.writes).toBe('none');
			expect(decoded.value.claim_class).toBe('measurement_of_mixture');
		}
	});

	it('job lists and projections decode with the widened lane schemas', () => {
		for (const [file, body] of recorded(/^\/api\/v1\/jobs(\?|$)/)) expect(decodeClosed(LaneJobList, body).ok, file).toBe(true);
		const jobs = recorded(/^\/api\/v1\/jobs\/job_[0-9a-f]{32}$/);
		expect(jobs.length).toBe(8);
		for (const [file, body] of jobs) {
			const decoded = decodeClosed(LaneJobProjection, body);
			expect(decoded.ok, file).toBe(file !== 'job_bad_unknown_key.json');
			if (!decoded.ok) continue;
			const sent = (body as { unknowns: Record<string, unknown> }).unknowns;
			// Unknown blocks are preserved, not defaulted: same keys, nulls stay null.
			expect(decoded.value.unknowns).toEqual(sent);
			expect(Object.values(sent).some((value) => value === null)).toBe(true);
		}
	});

	it('the typed refusals are not decodable as success shapes', () => {
		expect(decodeClosed(ReviewRecord, e2eFixture('review_refused_setup.json')).ok).toBe(false);
		expect(decodeClosed(LaneJobProjection, e2eFixture('submit_refused.json')).ok).toBe(false);
	});
});

describe('closed top-level structs (property)', () => {
	const unknownKey = fc.string({ minLength: 1, maxLength: 24 }).filter((key) => !LANE_FIELD_NAMES.has(key) && key !== '__proto__');

	it('an unknown top-level key is refused for every shape', () => {
		const cases: Array<[Parameters<typeof decodeClosed>[0], Record<string, unknown>]> = [
			[JobTypes, e2eFixture('job_types.json') as Record<string, unknown>],
			[RunList, e2eFixture('source_runs_reviewed.json') as Record<string, unknown>],
			[ReviewList, e2eFixture('reviews_reviewed.json') as Record<string, unknown>],
			[Measurement, e2eFixture('measurement.json') as Record<string, unknown>],
			[LaneJobProjection, e2eFixture('job_denoise_succeeded.json') as Record<string, unknown>]
		];
		for (const [schema, body] of cases) expect(decodeClosed(schema, body).ok).toBe(true);
		fc.assert(
			fc.property(unknownKey, (key) => {
				for (const [schema, body] of cases) expect(decodeClosed(schema, { ...body, [key]: null }).ok).toBe(false);
			})
		);
	});
});

describe('id patterns', () => {
	it('RUN_ID_PATTERN is one safe path component', () => {
		for (const good of ['RUN-S3', 'BASE-PLAIN', '20261006T041633Z-990aa1bd6737', 'a']) expect(RUN_ID_PATTERN.test(good), good).toBe(true);
		for (const bad of ['', '.hidden', '-lead', 'a/b', '..', 'a b', 'x'.repeat(129), 'a\n']) expect(RUN_ID_PATTERN.test(bad), JSON.stringify(bad)).toBe(false);
	});
	it('REVIEW_ID_PATTERN is rev_ + 32 hex', () => {
		expect(REVIEW_ID_PATTERN.test(`rev_${'0'.repeat(31)}1`)).toBe(true);
		for (const bad of ['', 'rev_', `rev_${'0'.repeat(31)}`, `rev_${'G'.repeat(32)}`, `art_${'0'.repeat(32)}`]) expect(REVIEW_ID_PATTERN.test(bad), bad).toBe(false);
	});
});
