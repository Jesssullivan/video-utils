// Form-data -> closed control-API bodies for the capture and process actions. Values the operator
// typed are forwarded as typed (numbers parsed, non-numeric text left as text) so the control API
// stays the single validator: nothing is clamped, defaulted or prefilled here.
import { UI_KEY_PATTERN } from '$lib/idempotency';
import { isReviewId, isRunId } from './client';

export type Built = { ok: true; body: Record<string, unknown> } | { ok: false; code: string; message: string };

const text = (data: FormData, name: string): string => {
	const value = data.get(name);
	return typeof value === 'string' ? value.trim() : '';
};

/** A typed number when the text parses finitely, else the raw text (refused upstream with a typed code). */
export function numeric(raw: string): number | string {
	if (raw === '') return raw;
	const value = Number(raw);
	return Number.isFinite(value) ? value : raw;
}

const key = (data: FormData): string | null => {
	const value = text(data, 'idempotency_key');
	return UI_KEY_PATTERN.test(value) ? value : null;
};

export function measurementBody(data: FormData): Built {
	const run = text(data, 'run_id');
	if (!isRunId(run)) return { ok: false, code: 'run_required', message: 'Choose a baseline run first.' };
	const start = text(data, 'start_seconds');
	const end = text(data, 'end_seconds');
	if (start === '' || end === '') return { ok: false, code: 'interval_required', message: 'Enter start and end seconds.' };
	return { ok: true, body: { run_id: run, start_seconds: numeric(start), end_seconds: numeric(end) } };
}

export function reviewBody(data: FormData, expectedSha256: string): Built {
	const measured = measurementBody(data);
	if (!measured.ok) return measured;
	const idempotency = key(data);
	if (idempotency === null) return { ok: false, code: 'invalid_form_key', message: 'Reload the page: the form key is invalid.' };
	return {
		ok: true,
		body: {
			idempotency_key: idempotency,
			...measured.body,
			expected_source_sha256: expectedSha256,
			review_status: text(data, 'review_status'),
			authorization_scope: text(data, 'authorization_scope'),
			music_status: text(data, 'music_status'),
			click_status: text(data, 'click_status'),
			ambient_music_status: text(data, 'ambient_music_status'),
			note: text(data, 'note'),
			setup_interval_acknowledged: data.get('setup_interval_acknowledged') === 'on'
		}
	};
}

const CAPTURE_CONTROLS = ['reduction_db', 'noise_floor_db', 'adaptivity', 'gain_smooth', 'integrated_lufs', 'true_peak_dbtp'] as const;
const COMPRESSOR = ['threshold_db', 'ratio', 'attack_ms', 'release_ms', 'knee_db'] as const;

function timeout(data: FormData, parameters: Record<string, unknown>): void {
	const raw = text(data, 'timeout_seconds');
	if (raw !== '') parameters.timeout_seconds = numeric(raw);
}

export function denoiseBody(data: FormData, sourceId: string): Built {
	const idempotency = key(data);
	if (idempotency === null) return { ok: false, code: 'invalid_form_key', message: 'Reload the page: the form key is invalid.' };
	const parameters: Record<string, unknown> = { profile: text(data, 'profile') };
	timeout(data, parameters);
	return { ok: true, body: { tool: 'denoise', source_artifact_id: sourceId, idempotency_key: idempotency, parameters } };
}

export function authorBody(data: FormData, sourceId: string): Built {
	const idempotency = key(data);
	if (idempotency === null) return { ok: false, code: 'invalid_form_key', message: 'Reload the page: the form key is invalid.' };
	const preset = text(data, 'preset');
	const parameters: Record<string, unknown> = { preset };
	if (preset === 'custom') {
		for (const name of CAPTURE_CONTROLS) {
			const raw = text(data, name);
			if (raw !== '') parameters[name] = numeric(raw);
		}
		const bands: Record<string, unknown>[] = [];
		for (let index = 0; index < 3; index += 1) {
			const band = ['frequency_hz', 'gain_db', 'q'].map((field) => text(data, `eq_${index}_${field}`));
			if (band.every((value) => value === '')) continue;
			bands.push({ frequency_hz: numeric(band[0]), gain_db: numeric(band[1]), q: numeric(band[2]) });
		}
		if (bands.length > 0) parameters.peaking_eq = bands;
		if (data.get('compressor_enabled') === 'on') {
			parameters.compressor = Object.fromEntries(COMPRESSOR.map((field) => [field, numeric(text(data, `compressor_${field}`))]));
		}
	}
	timeout(data, parameters);
	const body: Record<string, unknown> = { tool: 'capture_profile', source_artifact_id: sourceId, idempotency_key: idempotency, parameters };
	const review = text(data, 'capture_review_id');
	if (review !== '') {
		if (!isReviewId(review)) return { ok: false, code: 'invalid_review_id', message: 'Choose a saved review.' };
		body.capture_review_id = review;
	}
	return { ok: true, body };
}

export function applyBody(data: FormData, sourceId: string): Built {
	const idempotency = key(data);
	if (idempotency === null) return { ok: false, code: 'invalid_form_key', message: 'Reload the page: the form key is invalid.' };
	const parameters: Record<string, unknown> = {};
	timeout(data, parameters);
	const body: Record<string, unknown> = { tool: 'apply_capture_profile', source_artifact_id: sourceId, idempotency_key: idempotency, parameters };
	const parent = text(data, 'capture_profile_job_id');
	if (parent !== '') body.capture_profile_job_id = parent;
	return { ok: true, body };
}

/** Echo of what the operator typed (never a server proposal), for re-rendering after an action. */
export function echo(data: FormData, names: ReadonlyArray<string>): Record<string, string> {
	return Object.fromEntries(names.map((name) => [name, text(data, name)]));
}
