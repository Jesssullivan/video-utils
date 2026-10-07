// Closed Effect Schema decoders of the S2 control API (WEB_TESTS_S3.md 5.1; metrics W4, W5).
// Fixtures are synthetic: nothing here states a fact about a recording.
import fc from 'fast-check';
import { describe, expect, it } from 'vitest';
import { decodeClosed, e2eFixture, e2eFixtureNames, isRecord, recorded, s2Fixture } from '../../../tests/fixtures';
import {
	AnnotationRead,
	AnnotationWrite,
	ApplyParameters,
	CaptureParameters,
	DenoiseParameters,
	JobList,
	JobProjection,
	JobSummary,
	KNOWN_FIELD_NAMES,
	SourceList,
	UploadResult,
	isArtifactId,
	isJobId
} from './control';

// web/fixtures/control-api/README.json "cases": 5 accepted, 2 refused.
const README_CASES = [
	{ file: 'sources.json', schema: SourceList, accept: true },
	{ file: 'job_queued.json', schema: JobProjection, accept: true },
	{ file: 'job_running.json', schema: JobProjection, accept: true },
	{ file: 'job_succeeded.json', schema: JobProjection, accept: true },
	{ file: 'job_failed.json', schema: JobProjection, accept: true },
	{ file: 'job_bad_unknown_key.json', schema: JobProjection, accept: false },
	{ file: 'job_bad_enum.json', schema: JobProjection, accept: false }
] as const;

describe('web/fixtures/control-api decode agreement', () => {
	it('lists exactly the 7 README cases', () => {
		const readme = s2Fixture('README.json') as { cases: Record<string, string> };
		expect(Object.keys(readme.cases).sort()).toEqual(README_CASES.map((row) => row.file).sort());
	});
	for (const row of README_CASES) {
		it(`${row.file} is ${row.accept ? 'accepted' : 'refused'}`, () => {
			expect(decodeClosed(row.schema, s2Fixture(row.file)).ok).toBe(row.accept);
		});
	}
});

describe('e2e fixtures decode with the schemas the pages use', () => {
	it('source list keeps null source_id and duration_seconds with their reasons', () => {
		const decoded = decodeClosed(SourceList, e2eFixture('sources.json'));
		expect(decoded.ok).toBe(true);
		if (!decoded.ok) return;
		const unknown = decoded.value.sources.filter((source) => source.duration_seconds === null);
		expect(unknown.length).toBeGreaterThan(0);
		for (const source of unknown) {
			expect(source.source_id).toBeNull();
			expect(source.source_id_reason.length).toBeGreaterThan(0);
			expect(source.duration_seconds_reason.length).toBeGreaterThan(0);
		}
		const s2 = decodeClosed(SourceList, s2Fixture('sources.json'));
		expect(s2.ok && s2.value.sources.some((source) => source.source_id === null && source.duration_seconds === null)).toBe(true);
	});

	it('every recorded job list decodes as JobList and every row as JobSummary', () => {
		const lists = recorded(/^\/api\/v1\/jobs(\?|$)/);
		expect(lists.length).toBeGreaterThanOrEqual(3);
		let rows = 0;
		for (const [file, body] of lists) {
			const decoded = decodeClosed(JobList, body);
			expect(decoded.ok, file).toBe(true);
			for (const row of (body as { jobs: unknown[] }).jobs) {
				expect(decodeClosed(JobSummary, row).ok, file).toBe(true);
				rows += 1;
			}
		}
		expect(rows).toBeGreaterThan(0);
	});

	it('every recorded job projection decodes, except the closed-schema violation', () => {
		const jobs = recorded(/^\/api\/v1\/jobs\/job_[0-9a-f]{32}$/);
		expect(jobs.length).toBe(8);
		for (const [file, body] of jobs) {
			expect(decodeClosed(JobProjection, body).ok, file).toBe(file !== 'job_bad_unknown_key.json');
		}
	});

	it('keeps unknown job fields null with reasons (eta, low-register preservation, musical review)', () => {
		const decoded = decodeClosed(JobProjection, e2eFixture('job_share_succeeded.json'));
		expect(decoded.ok).toBe(true);
		if (!decoded.ok) return;
		expect(decoded.value.eta_seconds).toBeNull();
		expect(decoded.value.eta_seconds_reason.length).toBeGreaterThan(0);
		const unknowns = decoded.value.unknowns as Record<string, unknown>;
		expect(unknowns.low_register_preservation).toBeNull();
		expect(unknowns.musical_review).toBeNull();
		expect(unknowns.master_adopted).toBe(false);
		expect(String(unknowns.low_register_preservation_reason).length).toBeGreaterThan(0);
	});

	it('job parameters decode with their per-tool parameter schema', () => {
		const parameters = (file: string) => (e2eFixture(file) as { parameters: unknown }).parameters;
		expect(decodeClosed(DenoiseParameters, parameters('job_denoise_succeeded.json')).ok).toBe(true);
		expect(decodeClosed(CaptureParameters, parameters('job_capture_profile_succeeded.json')).ok).toBe(true);
		expect(decodeClosed(ApplyParameters, parameters('job_apply_succeeded.json')).ok).toBe(true);
		// A capture parameter block is not a denoise block (closed, not structural).
		expect(decodeClosed(DenoiseParameters, parameters('job_capture_profile_succeeded.json')).ok).toBe(false);
	});

	it('annotation read decodes; a write envelope built from it decodes; a detector actor is not a legal record', () => {
		const read = e2eFixture('annotations_reviewed.json') as { store: { annotations: Array<Record<string, unknown>> }; clock: unknown };
		expect(decodeClosed(AnnotationRead, read).ok).toBe(true);
		expect(read.store.annotations.length).toBe(1);
		const record = read.store.annotations[0];
		expect(record.musical_verdict).toBe('not_established');
		const write = { ...read, mutation: { outcome: 'saved', annotation_id: record.id, committed_revision: 1 } };
		expect(decodeClosed(AnnotationWrite, write).ok).toBe(true);
		const verdict = { ...read, store: { ...read.store, annotations: [{ ...record, musical_verdict: 'confirmed' }] } };
		expect(decodeClosed(AnnotationRead, verdict).ok).toBe(false);
	});

	it('upload result: a schema-shaped admission decodes and an unknown key is refused', () => {
		const sha = '0'.repeat(63) + '1';
		const result = {
			schema_version: 1,
			upload: { upload_id: `upl_${'0'.repeat(15)}1`, bytes: 4121, sha256: sha, deduplicated: false },
			source: { source_artifact_id: `art_${'0'.repeat(31)}1`, source_id: null, source_binding: 'unknown', kind: 'video', sha256: sha, size_bytes: 4121, state: 'current' }
		};
		expect(decodeClosed(UploadResult, result).ok).toBe(true);
		expect(decodeClosed(UploadResult, { ...result, upload: { ...result.upload, path: 'x' } }).ok).toBe(false);
		// The recorded upload response is a typed refusal, not an UploadResult.
		expect(decodeClosed(UploadResult, e2eFixture('upload_refused.json')).ok).toBe(false);
	});

	it('every committed e2e fixture file is strict JSON', () => {
		const names = e2eFixtureNames();
		expect(names.length).toBeGreaterThanOrEqual(40);
		for (const name of names) expect(isRecord(e2eFixture(name)), name).toBe(true);
	});
});

describe('closed schemas (property)', () => {
	const unknownKey = fc.string({ minLength: 1, maxLength: 24 }).filter((key) => !KNOWN_FIELD_NAMES.has(key) && key !== '__proto__');
	const value = fc.oneof(fc.constant(null), fc.boolean(), fc.integer(), fc.string({ maxLength: 16 }));

	it('adding any unknown key to an accepted object is refused', () => {
		const sources = e2eFixture('sources.json') as { sources: Array<Record<string, unknown>> };
		const job = e2eFixture('job_share_succeeded.json') as Record<string, unknown>;
		const read = e2eFixture('annotations_reviewed.json') as Record<string, unknown>;
		fc.assert(
			fc.property(unknownKey, value, (key, extra) => {
				expect(decodeClosed(SourceList, { ...sources, [key]: extra }).ok).toBe(false);
				expect(decodeClosed(SourceList, { ...sources, sources: [{ ...sources.sources[0], [key]: extra }] }).ok).toBe(false);
				expect(decodeClosed(JobProjection, { ...job, [key]: extra }).ok).toBe(false);
				expect(decodeClosed(AnnotationRead, { ...read, [key]: extra }).ok).toBe(false);
			})
		);
	});
});

describe('id predicates', () => {
	it('accept only the exact id shapes', () => {
		expect(isJobId(`job_${'0'.repeat(32)}`)).toBe(true);
		expect(isArtifactId(`art_${'a'.repeat(32)}`)).toBe(true);
		for (const bad of ['', 'job_', `job_${'0'.repeat(31)}`, `job_${'0'.repeat(33)}`, `JOB_${'0'.repeat(32)}`, `job_${'g'.repeat(32)}`, `../job_${'0'.repeat(32)}`, `job_${'0'.repeat(32)}\n`]) {
			expect(isJobId(bad), JSON.stringify(bad)).toBe(false);
			expect(isArtifactId(bad.replace('job_', 'art_')), JSON.stringify(bad)).toBe(false);
		}
	});
});
