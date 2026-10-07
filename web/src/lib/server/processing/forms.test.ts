// Form-data -> control-API body builders for the capture and process actions (WEB_TESTS_S3.md 5.1).
import fc from 'fast-check';
import { describe, expect, it } from 'vitest';
import { applyBody, authorBody, denoiseBody, echo, measurementBody, numeric, reviewBody, type Built } from './forms';

const SOURCE = `art_${'0'.repeat(31)}1`;
const REVIEW = `rev_${'0'.repeat(31)}1`;
const KEY = `ui-${'0'.repeat(31)}1`;
const SHA = '0'.repeat(63) + '1';
// Any key spelling of a high-pass, low-cut or notch control; none may ever appear in a built body.
const FORBIDDEN_KEY = /high.?pass|low.?cut|notch|hpf|highpass|lowcut|hum/i;
const FORBIDDEN_NAMES = ['high_pass', 'high_pass_hz', 'highpass', 'hpf_hz', 'low_cut', 'low_cut_hz', 'lowcut', 'notch', 'notch_hz', 'mains_notch', 'hum_notch_hz'];

function form(entries: Record<string, string>): FormData {
	const data = new FormData();
	for (const [name, value] of Object.entries(entries)) data.set(name, value);
	return data;
}

function body(built: Built): Record<string, unknown> {
	expect(built.ok).toBe(true);
	return built.ok ? built.body : {};
}

function refusal(built: Built): string {
	expect(built.ok).toBe(false);
	if (built.ok) return '';
	expect(built.message.length).toBeGreaterThan(0);
	return built.code;
}

function allKeys(value: unknown): string[] {
	if (Array.isArray(value)) return value.flatMap(allKeys);
	if (typeof value !== 'object' || value === null) return [];
	return Object.entries(value).flatMap(([key, item]) => [key, ...allKeys(item)]);
}

describe('numeric', () => {
	it('parses finite numbers and leaves everything else as typed text (never clamps or defaults)', () => {
		expect(numeric('5.5')).toBe(5.5);
		expect(numeric('-18')).toBe(-18);
		expect(numeric('1e3')).toBe(1000);
		expect(numeric('')).toBe('');
		expect(numeric('abc')).toBe('abc');
		expect(numeric('Infinity')).toBe('Infinity');
		expect(numeric('NaN')).toBe('NaN');
		expect(numeric('99999')).toBe(99999);
	});
});

describe('measurementBody', () => {
	it('refuses a missing or malformed run with run_required', () => {
		expect(refusal(measurementBody(form({ start_seconds: '5.5', end_seconds: '6.4' })))).toBe('run_required');
		expect(refusal(measurementBody(form({ run_id: '../x', start_seconds: '5.5', end_seconds: '6.4' })))).toBe('run_required');
	});
	it('refuses a missing bound with interval_required and never fills one in', () => {
		expect(refusal(measurementBody(form({ run_id: 'BASE-PLAIN', start_seconds: '5.5' })))).toBe('interval_required');
		expect(refusal(measurementBody(form({ run_id: 'BASE-PLAIN', end_seconds: '6.4' })))).toBe('interval_required');
		expect(refusal(measurementBody(form({ run_id: 'BASE-PLAIN', start_seconds: ' ', end_seconds: ' ' })))).toBe('interval_required');
	});
	it('builds exactly run_id, start_seconds and end_seconds', () => {
		const built = body(measurementBody(form({ run_id: 'BASE-PLAIN', start_seconds: '5.5', end_seconds: '6.4', high_pass_hz: '80' })));
		expect(built).toEqual({ run_id: 'BASE-PLAIN', start_seconds: 5.5, end_seconds: 6.4 });
	});
});

describe('reviewBody', () => {
	const base = { run_id: 'BASE-PLAIN', start_seconds: '1', end_seconds: '2', idempotency_key: KEY, review_status: 'reviewed_possible_contamination', authorization_scope: 'profile_authoring', music_status: 'unknown', click_status: 'unknown', ambient_music_status: 'not_reported', note: ' heard a fan ' };

	it('refuses an invalid form key with invalid_form_key', () => {
		for (const key of ['', 'ui-', `ui-${'0'.repeat(31)}`, `ui-${'G'.repeat(32)}`, `UI-${'0'.repeat(32)}`]) {
			expect(refusal(reviewBody(form({ ...base, idempotency_key: key }), SHA))).toBe('invalid_form_key');
		}
	});
	it('inherits the run and interval refusals', () => {
		expect(refusal(reviewBody(form({ ...base, run_id: '' }), SHA))).toBe('run_required');
		expect(refusal(reviewBody(form({ ...base, end_seconds: '' }), SHA))).toBe('interval_required');
	});
	it('builds exactly the 12 review keys; the acknowledgement is false unless the box was ticked', () => {
		const built = body(reviewBody(form(base), SHA));
		expect(Object.keys(built).sort()).toEqual(['ambient_music_status', 'authorization_scope', 'click_status', 'end_seconds', 'expected_source_sha256', 'idempotency_key', 'music_status', 'note', 'review_status', 'run_id', 'setup_interval_acknowledged', 'start_seconds']);
		expect(built.setup_interval_acknowledged).toBe(false);
		expect(built.note).toBe('heard a fan');
		expect(built.expected_source_sha256).toBe(SHA);
		expect(body(reviewBody(form({ ...base, setup_interval_acknowledged: 'on' }), SHA)).setup_interval_acknowledged).toBe(true);
		// Any other value of the field is not an acknowledgement.
		for (const value of ['true', '1', 'yes', 'off', '']) {
			expect(body(reviewBody(form({ ...base, setup_interval_acknowledged: value }), SHA)).setup_interval_acknowledged).toBe(false);
		}
	});
	it('never invents a status or scope the operator did not choose', () => {
		const { review_status: _status, authorization_scope: _scope, ...rest } = base;
		const built = body(reviewBody(form(rest), SHA));
		expect(built.review_status).toBe('');
		expect(built.authorization_scope).toBe('');
	});
});

describe('denoiseBody', () => {
	it('builds the denoise request with only the profile and an optional timeout', () => {
		expect(body(denoiseBody(form({ profile: 'bypass', idempotency_key: KEY }), SOURCE))).toEqual({ tool: 'denoise', source_artifact_id: SOURCE, idempotency_key: KEY, parameters: { profile: 'bypass' } });
		expect(body(denoiseBody(form({ profile: 'conservative3', timeout_seconds: '30', idempotency_key: KEY, notch_hz: '60' }), SOURCE)).parameters).toEqual({ profile: 'conservative3', timeout_seconds: 30 });
		expect(refusal(denoiseBody(form({ profile: 'bypass' }), SOURCE))).toBe('invalid_form_key');
	});
});

describe('authorBody', () => {
	const custom = { preset: 'custom', idempotency_key: KEY, capture_review_id: REVIEW, reduction_db: '6', noise_floor_db: '-40', adaptivity: '0.5', gain_smooth: '8', integrated_lufs: '-18', true_peak_dbtp: '-1.75' };

	it('FULLER forwards no control even when the form carries them', () => {
		const built = body(authorBody(form({ ...custom, preset: 'fuller', eq_0_frequency_hz: '160', eq_0_gain_db: '2', eq_0_q: '0.7', compressor_enabled: 'on' }), SOURCE));
		expect(built).toEqual({ tool: 'capture_profile', source_artifact_id: SOURCE, idempotency_key: KEY, parameters: { preset: 'fuller' }, capture_review_id: REVIEW });
	});
	it('custom forwards exactly the typed controls, bands and compressor fields', () => {
		const built = body(authorBody(form({ ...custom, eq_0_frequency_hz: '160', eq_0_gain_db: '2', eq_0_q: '0.7', eq_2_frequency_hz: '900', eq_2_gain_db: '-1.5', eq_2_q: '1', compressor_enabled: 'on', compressor_threshold_db: '-18', compressor_ratio: '2', compressor_attack_ms: '20', compressor_release_ms: '200', compressor_knee_db: '6', timeout_seconds: '45' }), SOURCE));
		expect(built.parameters).toEqual({
			preset: 'custom', reduction_db: 6, noise_floor_db: -40, adaptivity: 0.5, gain_smooth: 8, integrated_lufs: -18, true_peak_dbtp: -1.75,
			peaking_eq: [{ frequency_hz: 160, gain_db: 2, q: 0.7 }, { frequency_hz: 900, gain_db: -1.5, q: 1 }],
			compressor: { threshold_db: -18, ratio: 2, attack_ms: 20, release_ms: 200, knee_db: 6 },
			timeout_seconds: 45
		});
		expect(Object.keys(built).sort()).toEqual(['capture_review_id', 'idempotency_key', 'parameters', 'source_artifact_id', 'tool']);
	});
	it('omits unset controls instead of defaulting them, and forwards out-of-range text unchanged', () => {
		const built = body(authorBody(form({ preset: 'custom', idempotency_key: KEY, reduction_db: '50', adaptivity: 'lots' }), SOURCE));
		expect(built.parameters).toEqual({ preset: 'custom', reduction_db: 50, adaptivity: 'lots' });
		expect('capture_review_id' in built).toBe(false);
	});
	it('refuses a malformed review id with invalid_review_id and a bad key with invalid_form_key', () => {
		expect(refusal(authorBody(form({ ...custom, capture_review_id: 'rev_1' }), SOURCE))).toBe('invalid_review_id');
		expect(refusal(authorBody(form({ ...custom, capture_review_id: `art_${'0'.repeat(32)}` }), SOURCE))).toBe('invalid_review_id');
		expect(refusal(authorBody(form({ ...custom, idempotency_key: 'nope' }), SOURCE))).toBe('invalid_form_key');
	});
});

describe('applyBody', () => {
	it('builds the apply request with an optional parent job and timeout only', () => {
		expect(body(applyBody(form({ idempotency_key: KEY }), SOURCE))).toEqual({ tool: 'apply_capture_profile', source_artifact_id: SOURCE, idempotency_key: KEY, parameters: {} });
		const parent = `job_${'0'.repeat(31)}2`;
		expect(body(applyBody(form({ idempotency_key: KEY, capture_profile_job_id: parent, timeout_seconds: '30', low_cut_hz: '80' }), SOURCE))).toEqual({ tool: 'apply_capture_profile', source_artifact_id: SOURCE, idempotency_key: KEY, parameters: { timeout_seconds: 30 }, capture_profile_job_id: parent });
		expect(refusal(applyBody(form({}), SOURCE))).toBe('invalid_form_key');
	});
});

describe('echo', () => {
	it('returns only what was typed for the named fields', () => {
		expect(echo(form({ a: ' 1 ', b: 'two', c: 'x' }), ['a', 'b', 'missing'])).toEqual({ a: '1', b: 'two', missing: '' });
	});
});

describe('no high-pass, low-cut or notch key can be produced (property)', () => {
	const DOCUMENTED = new Set([
		'run_id', 'start_seconds', 'end_seconds', 'idempotency_key', 'expected_source_sha256', 'review_status', 'authorization_scope', 'music_status', 'click_status', 'ambient_music_status', 'note', 'setup_interval_acknowledged',
		'tool', 'source_artifact_id', 'parameters', 'profile', 'timeout_seconds', 'preset', 'reduction_db', 'noise_floor_db', 'adaptivity', 'gain_smooth', 'integrated_lufs', 'true_peak_dbtp', 'peaking_eq', 'frequency_hz', 'gain_db', 'q',
		'compressor', 'threshold_db', 'ratio', 'attack_ms', 'release_ms', 'knee_db', 'capture_review_id', 'capture_profile_job_id'
	]);
	const knownNames = ['run_id', 'start_seconds', 'end_seconds', 'profile', 'timeout_seconds', 'preset', 'reduction_db', 'noise_floor_db', 'adaptivity', 'gain_smooth', 'integrated_lufs', 'true_peak_dbtp', 'eq_0_frequency_hz', 'eq_0_gain_db', 'eq_0_q', 'eq_1_frequency_hz', 'compressor_enabled', 'compressor_threshold_db', 'compressor_ratio', 'capture_review_id', 'capture_profile_job_id', 'note', 'review_status'];
	const name = fc.oneof(fc.constantFrom(...FORBIDDEN_NAMES), fc.constantFrom(...knownNames), fc.string({ minLength: 1, maxLength: 20 }));
	const value = fc.oneof(fc.constantFrom('on', 'custom', 'fuller', '80', '60', '-3', 'BASE-PLAIN', REVIEW), fc.string({ maxLength: 12 }));
	const entries = fc.dictionary(name, value, { maxKeys: 24 });

	it('holds for every builder over arbitrary form entries', () => {
		expect(FORBIDDEN_NAMES.every((item) => FORBIDDEN_KEY.test(item))).toBe(true);
		expect([...DOCUMENTED].some((item) => FORBIDDEN_KEY.test(item))).toBe(false);
		fc.assert(
			fc.property(entries, fc.constantFrom(...FORBIDDEN_NAMES), (fields, forbidden) => {
				const data = form({ ...fields, [forbidden]: '80', idempotency_key: KEY });
				const built = [measurementBody(data), reviewBody(data, SHA), denoiseBody(data, SOURCE), authorBody(data, SOURCE), applyBody(data, SOURCE)];
				for (const result of built) {
					if (!result.ok) continue;
					for (const key of allKeys(result.body)) {
						expect(DOCUMENTED.has(key), key).toBe(true);
						expect(FORBIDDEN_KEY.test(key), key).toBe(false);
					}
				}
			})
		);
	});
});
