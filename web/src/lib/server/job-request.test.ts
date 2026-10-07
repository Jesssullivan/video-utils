// The one share_export job request builder (WEB_TESTS_S3.md 5.1). Pure: nothing is sent from here.
import fc from 'fast-check';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { IDEMPOTENCY_KEY_PATTERN, JOB_TOOL, KNOB_KEYS, MAX_PARAMETERS, buildJobRequest } from './job-request';

const SOURCE = `art_${'0'.repeat(31)}1`;
const KEY = `ui-${'0'.repeat(31)}1`;

afterEach(() => vi.restoreAllMocks());

describe('buildJobRequest', () => {
	it('accepts and forwards exactly the knobs the user set, with their JSON types unchanged', () => {
		const built = buildJobRequest({ sourceArtifactId: SOURCE, parameters: { height: 480, crf: 27.5, codec: 'h264', audio_kbps: '96' }, idempotencyKey: KEY });
		expect(built).toEqual({ ok: true, body: { tool: 'share_export', source_artifact_id: SOURCE, parameters: { height: 480, crf: 27.5, codec: 'h264', audio_kbps: '96' }, idempotency_key: KEY } });
		expect(JOB_TOOL).toBe('share_export');
		expect([...KNOB_KEYS]).toEqual(['height', 'crf', 'audio_kbps', 'codec', 'timeout_seconds']);
	});

	it('treats omitted parameters as none set (descriptor defaults apply upstream)', () => {
		const built = buildJobRequest({ sourceArtifactId: SOURCE, parameters: undefined, idempotencyKey: KEY });
		expect(built.ok && built.body.parameters).toEqual({});
	});

	it('refuses a bad source id', () => {
		for (const bad of [undefined, null, 42, '', 'art_1', `job_${'0'.repeat(32)}`, `art_${'0'.repeat(32)}/..`]) {
			expect(buildJobRequest({ sourceArtifactId: bad, parameters: {}, idempotencyKey: KEY })).toEqual({ ok: false, code: 'invalid_source_id' });
		}
	});

	it('refuses a bad idempotency key', () => {
		for (const bad of [undefined, 7, '', 'ui-', `ui-${'0'.repeat(31)}`, `ui-ann-${'0'.repeat(32)}`, `UI-${'0'.repeat(32)}`, `ui-${'z'.repeat(32)}`]) {
			expect(buildJobRequest({ sourceArtifactId: SOURCE, parameters: {}, idempotencyKey: bad })).toEqual({ ok: false, code: 'invalid_idempotency_key' });
		}
	});

	it('refuses a parameter name outside ^[a-z_]{1,64}$ and non-scalar values', () => {
		const shape = { ok: false, code: 'invalid_parameters_shape' };
		for (const parameters of [{ 'Bad-Knob': 1 }, { '': 1 }, { ['x'.repeat(65)]: 1 }, { height: [480] }, { height: { value: 480 } }, { height: null }, { height: Number.NaN }, { codec: 'x'.repeat(65) }, [], 'height=480', 12]) {
			expect(buildJobRequest({ sourceArtifactId: SOURCE, parameters, idempotencyKey: KEY })).toEqual(shape);
		}
	});

	it('forwards a well-formed but unknown knob unchanged: the control API is the single validator', () => {
		// Recorded behaviour, not a refusal: the frozen contract text lists "unknown knob" under refusals, but the
		// builder checks only the request shape and leaves knob names and ranges to WebJobs.normalize_parameters.
		const built = buildJobRequest({ sourceArtifactId: SOURCE, parameters: { not_a_share_knob: 1 }, idempotencyKey: KEY });
		expect(built.ok && built.body.parameters).toEqual({ not_a_share_knob: 1 });
	});

	it(`refuses more than MAX_PARAMETERS (${MAX_PARAMETERS}) parameters`, () => {
		const make = (count: number) => Object.fromEntries(Array.from({ length: count }, (_, index) => [`knob_${String.fromCharCode(97 + index)}`, index]));
		expect(buildJobRequest({ sourceArtifactId: SOURCE, parameters: make(MAX_PARAMETERS), idempotencyKey: KEY }).ok).toBe(true);
		expect(buildJobRequest({ sourceArtifactId: SOURCE, parameters: make(MAX_PARAMETERS + 1), idempotencyKey: KEY })).toEqual({ ok: false, code: 'invalid_parameters_shape' });
	});

	it('every refusal is one of three typed codes and no request is made (property)', () => {
		const fetchSpy = vi.spyOn(globalThis, 'fetch');
		const anything = fc.oneof(fc.string({ maxLength: 40 }), fc.integer(), fc.constant(null), fc.constant(undefined), fc.dictionary(fc.string({ maxLength: 8 }), fc.oneof(fc.string({ maxLength: 8 }), fc.integer(), fc.constant(null)), { maxKeys: 20 }));
		fc.assert(
			fc.property(anything, anything, anything, (sourceArtifactId, parameters, idempotencyKey) => {
				const built = buildJobRequest({ sourceArtifactId, parameters, idempotencyKey });
				if (built.ok) {
					expect(Object.keys(built.body).sort()).toEqual(['idempotency_key', 'parameters', 'source_artifact_id', 'tool']);
					expect(IDEMPOTENCY_KEY_PATTERN.test(built.body.idempotency_key)).toBe(true);
				} else {
					expect(['invalid_source_id', 'invalid_idempotency_key', 'invalid_parameters_shape']).toContain(built.code);
					expect(Object.keys(built).sort()).toEqual(['code', 'ok']);
				}
			})
		);
		expect(fetchSpy).not.toHaveBeenCalled();
	});
});
