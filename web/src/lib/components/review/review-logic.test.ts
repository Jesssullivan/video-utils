// Client-safe review helpers (WEB_TESTS_S3.md 5.1): keys, timing rows, flags, annotation requests, click grid.
// Synthetic fixtures only. Nothing here grades a performance or states a note-level result.
import fc from 'fast-check';
import { describe, expect, it } from 'vitest';
import { e2eFixture, isRecord } from '../../../../tests/fixtures';
import {
	ANNOTATION_KINDS,
	BASIS_STYLE,
	DIRECTION_SYNTHETIC_SUFFIX,
	DIRECTION_WITHHELD,
	KEY_BINDINGS,
	ORIGIN_STYLE,
	annotationRequest,
	flagGroups,
	gridTicks,
	keyAction,
	spanFor,
	timingDirection,
	timingRows,
	type AnnotationDraft,
	type KeyAction
} from './review-logic';

type KeyInput = Parameters<typeof keyAction>[0];
const key = (value: string, extra: Partial<KeyInput> = {}): KeyInput => ({ key: value, shiftKey: false, altKey: false, ctrlKey: false, metaKey: false, target: null, ...extra });
const inside = (selector: string) => ({ matches: (query: string) => query.split(',').includes(selector) }) as unknown as EventTarget;

const layers = e2eFixture('layers_run_s3.json') as { layers: Record<string, { document: unknown }>; };
function timingDocument(): Record<string, unknown> {
	const files = (layers.layers.phrase_timing.document as { files: Array<{ document: Record<string, unknown> }> }).files;
	return files[0].document;
}

// Words that would turn a measurement into a verdict about the playing (AGENTS.md: no note correctness without a reference).
const VERDICT = /\b(missed|extra|wrong|incorrect|bad|sloppy|mistake)\b[^.]{0,20}\bnotes?\b|\bnote[- ]correct|\b(rushed|dragged|sloppy)\b/i;

describe('keyAction: the 12 bindings', () => {
	it('lists 12 bindings with 12 distinct actions', () => {
		expect(KEY_BINDINGS.length).toBe(12);
		expect(new Set(KEY_BINDINGS.map((binding) => binding.action)).size).toBe(12);
		expect(new Set(KEY_BINDINGS.map((binding) => `${binding.key}|${binding.shift}`)).size).toBe(12);
	});

	it('resolves each binding to its action, case-insensitively for letters', () => {
		for (const binding of KEY_BINDINGS) {
			expect(keyAction(key(binding.key, { shiftKey: binding.shift })), binding.text).toBe(binding.action);
			if (binding.key.length === 1 && /[a-z]/.test(binding.key)) {
				expect(keyAction(key(binding.key.toUpperCase(), { shiftKey: binding.shift })), binding.text).toBe(binding.action);
			}
		}
	});

	it('Shift selects the flag actions for N and P, and only widens the step for arrows', () => {
		expect(keyAction(key('n'))).toBe('next_boundary');
		expect(keyAction(key('N', { shiftKey: true }))).toBe('next_flag');
		expect(keyAction(key('p', { shiftKey: true }))).toBe('prev_flag');
		expect(keyAction(key('ArrowLeft', { shiftKey: true }))).toBe('seek_back');
		expect(keyAction(key('ArrowRight', { shiftKey: true }))).toBe('seek_forward');
		expect(keyAction(key('l', { shiftKey: true }))).toBeNull();
	});

	it('is inert inside input, select, textarea and contenteditable', () => {
		for (const selector of ['input', 'select', 'textarea', '[contenteditable="true"]']) {
			for (const binding of KEY_BINDINGS) {
				expect(keyAction(key(binding.key, { shiftKey: binding.shift, target: inside(selector) })), `${selector} ${binding.text}`).toBeNull();
			}
		}
		// A non-field target (the transport toolbar) leaves the bindings active.
		expect(keyAction(key('b', { target: inside('div') }))).toBe('queue_phrase_point');
	});

	it('is inert with Alt, Ctrl or Meta held', () => {
		for (const modifier of ['altKey', 'ctrlKey', 'metaKey'] as const) {
			for (const binding of KEY_BINDINGS) {
				expect(keyAction(key(binding.key, { shiftKey: binding.shift, [modifier]: true })), `${modifier} ${binding.text}`).toBeNull();
			}
		}
	});

	it('no binding is Space, Enter or a media key, and no action starts playback', () => {
		const actions: KeyAction[] = KEY_BINDINGS.map((binding) => binding.action);
		expect(actions.some((action) => /play|start_playback|toggle_play/.test(action))).toBe(false);
		for (const unbound of [' ', 'Enter', 'k', 'MediaPlayPause', 'Escape', 'Tab', 'a', '1']) expect(keyAction(key(unbound)), JSON.stringify(unbound)).toBeNull();
	});

	it('never returns an action outside the table (property)', () => {
		const known = new Set<string>(KEY_BINDINGS.map((binding) => binding.action));
		fc.assert(
			fc.property(fc.string({ maxLength: 12 }), fc.boolean(), fc.boolean(), fc.boolean(), fc.boolean(), (value, shiftKey, altKey, ctrlKey, metaKey) => {
				const action = keyAction(key(value, { shiftKey, altKey, ctrlKey, metaKey }));
				if (action !== null) {
					expect(known.has(action)).toBe(true);
					expect(altKey || ctrlKey || metaKey).toBe(false);
				}
			})
		);
	});
});

describe('timingDirection: withheld unless the row is a synthetic known-offset fixture', () => {
	it('withholds every real-take row, whatever direction the row carries', () => {
		for (const direction of ['ahead_of_click', 'behind_click', 'within_5_ms', null]) {
			for (const runKind of ['real_take', 'unknown', null, undefined]) {
				expect(timingDirection({ direction, direction_status: 'synthetic_known_offset_fixture' }, runKind)).toBe(DIRECTION_WITHHELD);
			}
			expect(timingDirection({ direction, direction_status: 'withheld_uncalibrated' }, 'synthetic_fixture')).toBe(DIRECTION_WITHHELD);
		}
		expect(timingDirection(null, 'synthetic_fixture')).toBe(DIRECTION_WITHHELD);
		expect(timingDirection({ direction: 'sideways', direction_status: 'synthetic_known_offset_fixture' }, 'synthetic_fixture')).toBe(DIRECTION_WITHHELD);
	});

	it('names a direction only with the synthetic-fixture suffix', () => {
		for (const direction of ['ahead_of_click', 'behind_click', 'within_5_ms']) {
			const text = timingDirection({ direction, direction_status: 'synthetic_known_offset_fixture' }, 'synthetic_fixture');
			expect(text.endsWith(DIRECTION_SYNTHETIC_SUFFIX)).toBe(true);
			expect(text).toContain('modelled click');
		}
	});
});

describe('timingRows on the recorded phrase_timing layer', () => {
	const rows = timingRows(timingDocument());

	it('reports the measured row as measurements with its count and a withheld direction', () => {
		expect(rows.length).toBe(2);
		const measured = rows[0];
		expect(measured).toMatchObject({ id: 'span-0', measured: true, count: '6', direction: DIRECTION_WITHHELD, abstain: null, span: [0.1, 0.5] });
		expect(measured.median).toBe('−14.2 ms (delay-compensated)');
		expect(measured.iqr).toBe('−18.2 … −11.2 ms');
	});

	it('shows an abstained row as a dash with its reason, never as 0', () => {
		const abstained = rows[1];
		expect(abstained).toMatchObject({ id: 'span-1', measured: false, median: '—', iqr: '—', direction: '—', count: '2' });
		expect(abstained.abstain).toBe('fewer than 4 click proximal onsets');
		expect(abstained.label).toBe('(unlabelled span-1)');
		for (const text of [abstained.median, abstained.iqr, abstained.direction]) expect(text).not.toMatch(/0/);
	});

	it('reads anything absent or malformed as unknown rather than a pass', () => {
		expect(timingRows(null)).toEqual([]);
		expect(timingRows({ phrases: 'nope' })).toEqual([]);
		const [row] = timingRows({ phrases: [{ status: 'measured' }] });
		expect(row).toMatchObject({ measured: false, median: '—', count: 'unknown', abstain: 'reason not recorded', span: [null, null] });
	});
});

describe('flagGroups on the recorded flags_triage layer', () => {
	const groups = flagGroups(layers.layers.flags_triage.document);

	it('keeps shown, navigation and suppressed flags apart with the producer denominators', () => {
		expect(groups.shown.map((flag) => flag.id)).toEqual(['flag-1']);
		expect(groups.navigation.map((flag) => flag.id)).toEqual(['flag-0']);
		expect(groups.suppressed.map((flag) => flag.id)).toEqual(['flag-2']);
		expect(groups.denominators).toMatchObject({ shown: 1, navigation_hidden: 1, suppressed_lower_priority: 1, total_flags: 3 });
		expect(groups.navigation[0].note).toBe('navigation proxy; not a confirmed bar');
		expect(groups.suppressed[0].note).toContain('flag-1');
	});

	it('returns empty groups for an unavailable or malformed layer', () => {
		for (const document of [null, undefined, 7, 'x', [], {}]) {
			const empty = flagGroups(document);
			expect([empty.shown, empty.navigation, empty.suppressed]).toEqual([[], [], []]);
		}
	});
});

describe('annotationRequest: operator authorship only', () => {
	const store = { revision: 3, source_sha256: '0'.repeat(63) + '1', manifest_sha256: '0'.repeat(63) + '2' };
	const draft = (overrides: Partial<AnnotationDraft> = {}): AnnotationDraft => ({
		kind: 'rhythm_timing', basis: 'operator_assertion', status: 'needs_review', source_span: spanFor(12.3456, null, null),
		reported_by: { actor: 'operator', via: 'browser' }, operator_certainty: 'uncertain', operator_quote: 'felt off here', note: '', ...overrides
	});

	it('builds the annotation_v2 request bound to the store revision and hashes', () => {
		const request = JSON.parse(annotationRequest(store, draft(), 'browser-key-1')) as Record<string, unknown>;
		expect(Object.keys(request).sort()).toEqual(['annotation', 'expected_revision', 'idempotency_key', 'manifest_sha256', 'schema_version', 'source_sha256']);
		expect(request).toMatchObject({ schema_version: 2, expected_revision: 3, idempotency_key: 'browser-key-1', source_sha256: store.source_sha256, manifest_sha256: store.manifest_sha256 });
		expect((request.annotation as AnnotationDraft).source_span).toEqual({ start_seconds: 12.346, end_seconds: 12.346, extent_known: false });
	});

	it('carries operator authorship with a USER REPORTED or INTENT basis and never a detector actor (property)', () => {
		expect(BASIS_STYLE.operator_assertion.label).toBe('USER REPORTED');
		expect(BASIS_STYLE.operator_context.label).toBe('INTENT');
		fc.assert(
			fc.property(fc.constantFrom(...ANNOTATION_KINDS), fc.constantFrom('operator_assertion', 'operator_context'), fc.double({ min: 0, max: 3600, noNaN: true }), fc.string({ maxLength: 40 }), (kind, basis, position, note) => {
				const request = JSON.parse(annotationRequest(store, draft({ kind, basis: basis as AnnotationDraft['basis'], source_span: spanFor(position, null, null), note }), 'browser-key-2')) as { annotation: Record<string, unknown> };
				expect(request.annotation.reported_by).toEqual({ actor: 'operator', via: 'browser' });
				expect(['operator_assertion', 'operator_context']).toContain(request.annotation.basis);
				expect(request.annotation.status).toBe('needs_review');
				expect(JSON.stringify(request.annotation.reported_by)).not.toMatch(/detector|agent/);
				expect('musical_verdict' in request.annotation).toBe(false);
			})
		);
	});

	it('spanFor keeps an ordered span and turns anything else into a point with unknown extent', () => {
		expect(spanFor(5, 1, 2)).toEqual({ start_seconds: 1, end_seconds: 2, extent_known: true });
		for (const [start, end] of [[2, 1], [2, 2], [null, 2], [1, null]] as Array<[number | null, number | null]>) {
			expect(spanFor(5, start, end)).toEqual({ start_seconds: 5, end_seconds: 5, extent_known: false });
		}
	});
});

describe('gridTicks', () => {
	it('places ticks at phase + k·period inside the window and nowhere else', () => {
		expect(gridTicks({ period_seconds: 0.25, phase_seconds: 0 }, 0, 1)).toEqual([0, 0.25, 0.5, 0.75, 1]);
		expect(gridTicks({ period_seconds: 0.5, phase_seconds: 0.1 }, 1, 2.2)).toEqual([1.1, 1.6, 2.1]);
	});

	it('returns nothing without a recorded grid or with a degenerate window', () => {
		expect(gridTicks(null, 0, 10)).toEqual([]);
		for (const period of [0, -1, Number.NaN]) expect(gridTicks({ period_seconds: period, phase_seconds: 0 }, 0, 10)).toEqual([]);
		expect(gridTicks({ period_seconds: 1, phase_seconds: 0 }, 5, 5)).toEqual([]);
		expect(gridTicks({ period_seconds: 1, phase_seconds: 0 }, 5, 1)).toEqual([]);
		expect(gridTicks({ period_seconds: 1, phase_seconds: 0 }, Number.NaN, 5)).toEqual([]);
	});

	it('never exceeds its cap and stays inside the window (property)', () => {
		const grid = fc.record({ period_seconds: fc.double({ min: 0.001, max: 10, noNaN: true }), phase_seconds: fc.double({ min: -5, max: 5, noNaN: true }) });
		fc.assert(
			fc.property(grid, fc.double({ min: 0, max: 100, noNaN: true }), fc.double({ min: 0.01, max: 50, noNaN: true }), fc.integer({ min: 1, max: 200 }), (value, min, width, cap) => {
				const ticks = gridTicks(value, min, min + width, cap);
				expect(ticks.length).toBeLessThanOrEqual(cap);
				for (const tick of ticks) {
					expect(tick).toBeGreaterThanOrEqual(min);
					expect(tick).toBeLessThanOrEqual(min + width);
				}
			})
		);
	});
});

describe('no output string asserts a missed, extra or wrong note', () => {
	function strings(value: unknown): string[] {
		if (typeof value === 'string') return [value];
		if (Array.isArray(value)) return value.flatMap(strings);
		return isRecord(value) ? Object.values(value).flatMap(strings) : [];
	}

	it('holds for every label, binding text, timing row and flag item this module produces from the fixtures', () => {
		const produced = [
			...strings(KEY_BINDINGS), ...strings(BASIS_STYLE), ...strings(ORIGIN_STYLE), DIRECTION_WITHHELD, DIRECTION_SYNTHETIC_SUFFIX,
			...strings(timingRows(timingDocument())), ...strings(flagGroups(layers.layers.flags_triage.document)),
			...['ahead_of_click', 'behind_click', 'within_5_ms'].map((direction) => timingDirection({ direction, direction_status: 'synthetic_known_offset_fixture' }, 'synthetic_fixture'))
		];
		expect(produced.length).toBeGreaterThan(40);
		for (const text of produced) expect(text, text).not.toMatch(VERDICT);
		expect('two missed notes in bar 3').toMatch(VERDICT);
		expect('the wrong note was held').toMatch(VERDICT);
	});
});
