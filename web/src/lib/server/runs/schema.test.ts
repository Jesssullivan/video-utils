// Closed schemas of the S3 runs read API (WEB_TESTS_S3.md 5.1; metrics W4, W5).
import { describe, expect, it } from 'vitest';
import { decodeClosed, e2eFixture, recorded } from '../../../../tests/fixtures';
import {
	Capabilities,
	RunGraph,
	RunLayers,
	RunList,
	RunSummary,
	S2_UNKNOWN_KEYS,
	S3_UNKNOWN_KEYS,
	UnknownFields,
	isEvidenceId,
	isMediaName
} from './schema';

const ALL_UNKNOWN_KEYS = [...S2_UNKNOWN_KEYS, ...S3_UNKNOWN_KEYS];

describe('run list and summaries', () => {
	it('decodes; lists two or more runs so the pickers render instead of redirecting', () => {
		const body = e2eFixture('runs_list.json') as { runs: unknown[] };
		const decoded = decodeClosed(RunList, body);
		expect(decoded.ok).toBe(true);
		expect(body.runs.length).toBeGreaterThanOrEqual(2);
		for (const row of body.runs) expect(decodeClosed(RunSummary, row).ok).toBe(true);
		expect(decodeClosed(RunList, { ...body, extra_key: 1 }).ok).toBe(false);
	});
});

describe('run graphs', () => {
	const graphs = recorded(/^\/api\/v1\/runs\/[A-Za-z0-9._-]+$/);

	it('every recorded graph decodes and carries all 33 unknown keys with a value and a reason slot', () => {
		expect(graphs.length).toBe(6);
		expect(ALL_UNKNOWN_KEYS.length).toBe(33);
		for (const [file, body] of graphs) {
			const decoded = decodeClosed(RunGraph, body);
			expect(decoded.ok, file).toBe(true);
			if (!decoded.ok) continue;
			const fields = decoded.value.unknown_fields as Record<string, { value: unknown; reason: string | null }>;
			expect(Object.keys(fields).sort(), file).toEqual([...ALL_UNKNOWN_KEYS].sort());
			for (const key of ALL_UNKNOWN_KEYS) expect('value' in fields[key] && 'reason' in fields[key], `${file} ${key}`).toBe(true);
			expect(decoded.value.claim_boundary.musical_verdict).toBe('not_established');
			expect(decoded.value.claim_boundary.missed_or_extra_notes).toBe('not_assessed_no_approved_reference');
			expect(decoded.value.claim_boundary.default_adopted).toBe(false);
			expect(decoded.value.listening_acceptance.master_adopted).toBe(false);
		}
	});

	it('a missing unknown key or a note-level verdict is refused', () => {
		const body = e2eFixture('run_run_s3.json') as { unknown_fields: Record<string, unknown>; claim_boundary: Record<string, unknown> };
		const { bpm: _dropped, ...rest } = body.unknown_fields;
		expect(decodeClosed(RunGraph, { ...body, unknown_fields: rest }).ok).toBe(false);
		expect(decodeClosed(RunGraph, { ...body, claim_boundary: { ...body.claim_boundary, missed_or_extra_notes: 'two_missed_notes' } }).ok).toBe(false);
		expect(decodeClosed(UnknownFields, body.unknown_fields).ok).toBe(true);
	});

	it('records no high-pass and no hum notch on the synthetic run, with the low fundamental kept', () => {
		const decoded = decodeClosed(RunGraph, e2eFixture('run_run_s3.json'));
		expect(decoded.ok).toBe(true);
		if (!decoded.ok) return;
		expect(decoded.value.processing.high_pass_applied).toBe(false);
		expect(decoded.value.processing.hum_notches_applied).toBe(false);
		expect(decoded.value.processing.intentional_low_fundamental_hz).toBe(32);
		// A run whose manifest records nothing keeps these null rather than false.
		const bare = decodeClosed(RunGraph, e2eFixture('run_run_other.json'));
		expect(bare.ok && bare.value.processing.high_pass_applied).toBeNull();
		expect(bare.ok && bare.value.processing.intentional_low_fundamental_hz).toBeNull();
	});
});

describe('run layers', () => {
	const layers = recorded(/^\/api\/v1\/runs\/[A-Za-z0-9._-]+\/layers$/);

	it('every recorded layers document decodes with all unknown keys', () => {
		expect(layers.length).toBe(6);
		for (const [file, body] of layers) {
			const decoded = decodeClosed(RunLayers, body);
			expect(decoded.ok, file).toBe(true);
			if (!decoded.ok) continue;
			expect(Object.keys(decoded.value.unknown_fields).sort(), file).toEqual([...ALL_UNKNOWN_KEYS].sort());
			expect(decoded.value.clock.alignment).toBe('unverified');
		}
	});

	it('nullable BPM stays null with its reason; an abstained phrase row keeps null measurements', () => {
		const body = e2eFixture('layers_run_s3.json');
		const decoded = decodeClosed(RunLayers, body);
		expect(decoded.ok).toBe(true);
		if (!decoded.ok) return;
		expect(decoded.value.layers.bpm.value).toBeNull();
		expect(decoded.value.layers.bpm.reason.length).toBeGreaterThan(0);
		expect((decoded.value.unknown_fields as Record<string, { value: unknown }>).bpm.value).toBeNull();
		const text = JSON.stringify(decoded.value.layers.phrase_timing.document);
		expect(text).toContain('"status":"abstained"');
		expect(text).toContain('"median_offset_ms":null');
		// A run with no bound bundle reports every layer unavailable instead of an empty success.
		const bare = decodeClosed(RunLayers, e2eFixture('layers_run_other.json'));
		expect(bare.ok && bare.value.layers.tone_ab.status).toBe('unavailable');
		expect(bare.ok && bare.value.layers.bpm.value).toBeNull();
	});
});

describe('capabilities', () => {
	it('tool_count equals the tool array length (42 at generation time) and every area tool is listed', () => {
		const body = e2eFixture('capabilities.json') as { tools: Array<{ name: string }>; areas: Array<{ tools: string[] }> };
		const decoded = decodeClosed(Capabilities, body);
		expect(decoded.ok).toBe(true);
		if (!decoded.ok) return;
		expect(decoded.value.tool_count).toBe(body.tools.length);
		expect(decoded.value.tool_count).toBe(42);
		const names = new Set(body.tools.map((tool) => tool.name));
		expect(names.size).toBe(42);
		const grouped = body.areas.flatMap((area) => area.tools);
		expect(grouped.length).toBe(42);
		expect(new Set(grouped)).toEqual(names);
		for (const key of ['model_local_presence', 'model_gate_state', 'tool_area_basis'] as const) {
			expect('value' in decoded.value.unknown_fields[key]).toBe(true);
		}
		expect(decoded.value.models.every((model) => model.local_presence === 'not_checked')).toBe(true);
	});
});

describe('id predicates', () => {
	it('isEvidenceId and isMediaName accept only safe single components', () => {
		expect(isEvidenceId(`evd_${'0'.repeat(31)}1`)).toBe(true);
		for (const bad of ['', `evd_${'0'.repeat(31)}`, `art_${'0'.repeat(32)}`, `evd_${'0'.repeat(32)}/x`]) expect(isEvidenceId(bad), bad).toBe(false);
		expect(isMediaName('excerpt-1-X.wav')).toBe(true);
		for (const bad of ['', '.hidden', 'a/b', '..', 'a b', 'x'.repeat(97)]) expect(isMediaName(bad), JSON.stringify(bad)).toBe(false);
	});
});
