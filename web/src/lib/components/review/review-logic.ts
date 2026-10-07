// Client-safe review helpers: Svelte 5 ports of review/practice_s2.js behaviours (ROUTES_REVIEW_S3.md 6.3-6.4).
// No server import, no network, no playback. Copied producer documents are read defensively: anything absent
// or malformed reads as unknown, never as 0 or as a pass.

// --------------------------------------------------------------------------- defensive readers

export type Json = unknown;
export const rec = (value: Json): Record<string, Json> =>
	typeof value === 'object' && value !== null && !Array.isArray(value) ? (value as Record<string, Json>) : {};
export const arr = (value: Json): Json[] => (Array.isArray(value) ? value : []);
export const num = (value: Json): number | null => (typeof value === 'number' && Number.isFinite(value) ? value : null);
export const str = (value: Json): string | null => (typeof value === 'string' ? value : null);
export const human = (value: Json): string => (value === null || value === undefined ? 'unknown' : String(value).replaceAll('_', ' '));
export const fixed = (value: Json, digits = 3): string => {
	const n = num(value);
	return n === null ? 'unknown' : n.toFixed(digits);
};
export const signed = (value: Json, digits = 1): string => {
	const n = num(value);
	if (n === null) return 'unknown';
	const text = Math.abs(n).toFixed(digits);
	return (Number(text) === 0 ? '±' : n < 0 ? '−' : '+') + text;
};
export const shortSha = (value: Json): string => {
	const text = str(value);
	if (text === null) return 'unknown';
	const bare = text.startsWith('sha256:') ? text.slice(7) : text;
	return /^[0-9a-f]{64}$/.test(bare) ? `${bare.slice(0, 12)}…` : 'unknown';
};
export const bareSha = (value: Json): string | null => {
	const text = str(value);
	if (text === null) return null;
	const bare = text.startsWith('sha256:') ? text.slice(7) : text;
	return /^[0-9a-f]{64}$/.test(bare) ? bare : null;
};
export const clockText = (seconds: number | null): string => {
	if (seconds === null || !Number.isFinite(seconds)) return 'unknown';
	const sign = seconds < 0 ? '−' : '';
	const abs = Math.abs(seconds);
	const minutes = Math.floor(abs / 60);
	return `${sign}${minutes}:${(abs - minutes * 60).toFixed(3).padStart(6, '0')}`;
};

// --------------------------------------------------------------------------- basis labels

/** annotation_v2.LABELS with a distinct shape token and text per basis (never colour alone). */
export const BASIS_STYLE = {
	operator_assertion: { label: 'USER REPORTED', shape: 'solid', text: 'User report', glyph: '●' },
	operator_context: { label: 'INTENT', shape: 'bracket', text: 'Operator intent', glyph: '[ ]' },
	detector_hypothesis: { label: 'REVIEW', shape: 'hollow', text: 'Review candidate', glyph: '○' },
	reference_comparison: { label: 'REFERENCE REVIEW', shape: 'double', text: 'Reference review', glyph: '◎' }
} as const;
export type BasisKey = keyof typeof BASIS_STYLE;
export const BASES = Object.keys(BASIS_STYLE) as BasisKey[];

/** Non-store records keep the S2 badge table: projected intent units and detector spans/flags. */
export const ORIGIN_STYLE = {
	intent_projected: { label: 'INTENT · projected', shape: 'bracket', text: 'Arrangement intent projected on the fitted grid', glyph: '[ ]' },
	detector: { label: 'DETECTOR HYPOTHESIS', shape: 'dotted', text: 'Automatic review candidate', glyph: '◌' }
} as const;

export const ANNOTATION_KINDS = [
	'phrase_duration',
	'phrase_omission',
	'rhythm_timing',
	'rhythm_pattern',
	'melodic_pitch',
	'articulation',
	'rest_execution',
	'meter_mismatch',
	'tone',
	'noise',
	'other'
] as const;
export type AnnotationKind = (typeof ANNOTATION_KINDS)[number];

// --------------------------------------------------------------------------- phrase timing (schema 2)

export const DIRECTION_WITHHELD = 'direction withheld (uncalibrated)';
export const DIRECTION_SYNTHETIC_SUFFIX = 'synthetic known-offset fixture';
const DIRECTION_TEXT: Record<string, string> = {
	within_5_ms: 'within ±5 ms of modelled click',
	ahead_of_click: 'ahead of modelled click',
	behind_click: 'behind modelled click'
};

/** A direction class only for a synthetic known-offset fixture row; every real-take row is withheld. */
export function timingDirection(row: Json, runKind: Json): string {
	const r = rec(row);
	const direction = str(r.direction);
	if (runKind === 'synthetic_fixture' && r.direction_status === 'synthetic_known_offset_fixture' && direction && direction in DIRECTION_TEXT) {
		return `${DIRECTION_TEXT[direction]} · ${DIRECTION_SYNTHETIC_SUFFIX}`;
	}
	return DIRECTION_WITHHELD;
}

export type TimingRow = {
	id: string;
	label: string;
	labelBasis: string;
	span: [number | null, number | null];
	status: string;
	measured: boolean;
	median: string;
	iqr: string;
	count: string;
	direction: string;
	abstain: string | null;
	start: number | null;
};

/** Measurements only: signed median, IQR and count; an abstained row shows — and its reason, never 0. */
export function timingRows(document: Json): TimingRow[] {
	const doc = rec(document);
	return arr(doc.phrases).map((item, index) => {
		const row = rec(item);
		const compensated = num(row.median_offset_ms_delay_compensated) !== null;
		const median = compensated ? row.median_offset_ms_delay_compensated : row.median_offset_ms;
		const iqr = arr(compensated ? row.iqr_ms_delay_compensated : row.iqr_ms);
		const span = arr(row.span_source_seconds);
		const measured = row.status === 'measured' && num(median) !== null;
		const count = num(row.click_proximal_onset_count);
		return {
			id: str(row.phrase_id) ?? `row-${index}`,
			label: str(row.label) ?? `(unlabelled ${str(row.phrase_id) ?? index})`,
			labelBasis: human(row.label_basis),
			span: [num(span[0]), num(span[1])],
			status: human(row.status),
			measured,
			median: measured ? `${signed(median)} ms${compensated ? ' (delay-compensated)' : ' (not delay-compensated)'}` : '—',
			iqr: measured && iqr.length === 2 ? `${signed(iqr[0])} … ${signed(iqr[1])} ms` : '—',
			count: count === null ? 'unknown' : String(count),
			direction: measured ? timingDirection(row, doc.run_kind) : '—',
			abstain: measured ? null : human(row.abstain_reason ?? 'reason not recorded'),
			start: num(span[0])
		};
	});
}

// --------------------------------------------------------------------------- coverage (phrase_anchor projection)

export type IntentUnit = { id: string; label: string; start: number; end: number; outside: boolean; sectionId: string | null };
export type IntentBoundary = { id: string; seconds: number; join: 'supported' | 'weak' | 'uncertain' | 'unknown'; breakdown: boolean; text: string };
export type IntentFile = { k0: number | null; anchorStatus: string; units: IntentUnit[]; boundaries: IntentBoundary[]; file: string };
export type DetectorSpan = { label: string; kind: string; start: number; end: number };

export function intentFiles(coverage: Json): IntentFile[] {
	const intent = rec(rec(coverage).intent);
	return arr(intent.files).map((item) => {
		const file = rec(item);
		const units: IntentUnit[] = [];
		for (const raw of arr(file.units)) {
			const unit = rec(raw);
			const start = num(unit.start_source_seconds);
			const end = num(unit.end_source_seconds);
			if (start === null || end === null) continue;
			const section = str(unit.section_id);
			const index = num(unit.section_unit_index);
			units.push({
				id: str(unit.id) ?? `${start}`,
				label: section ? `${human(section)}${index !== null ? ` ${index}` : ''}` : (str(unit.id) ?? 'unit'),
				start,
				end,
				outside: unit.coverage !== 'within_source',
				sectionId: section
			});
		}
		const boundaries: IntentBoundary[] = [];
		for (const raw of arr(file.boundaries)) {
			const row = rec(raw);
			const seconds = num(row.source_seconds);
			if (seconds === null) continue;
			const join = row.join_confidence === 'supported' || row.join_confidence === 'weak' || row.join_confidence === 'uncertain' ? row.join_confidence : 'unknown';
			const structural = arr(row.structural_status).map((value) => String(value));
			boundaries.push({
				id: str(row.id) ?? `${seconds}`,
				seconds,
				join,
				breakdown: structural.includes('breakdown_execution_uncertain') || structural.includes('uncertain_upstream_breakdown'),
				text: structural.map(human).join(', ')
			});
		}
		boundaries.sort((a, b) => a.seconds - b.seconds);
		return { k0: num(file.k0), anchorStatus: human(file.anchor_status), units, boundaries, file: str(file.file) ?? 'spans' };
	});
}

export function detectorSpans(coverage: Json): DetectorSpan[] {
	const detector = rec(rec(coverage).detector);
	if (detector.status !== 'available') return [];
	const spans: DetectorSpan[] = [];
	for (const raw of arr(detector.proposed_review_spans)) {
		const item = rec(raw);
		const start = num(item.source_start_seconds);
		const end = num(item.source_end_seconds);
		if (start === null || end === null) continue;
		spans.push({ label: str(item.label) ?? human(item.kind), kind: human(item.kind), start, end });
	}
	return spans;
}

// --------------------------------------------------------------------------- triaged flags

export type FlagItem = { id: string; group: 'shown' | 'navigation' | 'suppressed'; kind: string; start: number | null; end: number | null; window: string; tier: string; note: string | null };

export function flagGroups(document: Json): { shown: FlagItem[]; navigation: FlagItem[]; suppressed: FlagItem[]; denominators: Record<string, Json>; windowBasis: Record<string, Json> } {
	const doc = rec(document);
	const read = (items: Json, group: FlagItem['group']): FlagItem[] =>
		arr(items).map((raw, index) => {
			const item = rec(raw);
			const flag = rec(item.flag);
			const start = num(flag.source_time_seconds);
			const end = num(flag.end_seconds) ?? start;
			return {
				id: str(item.flag_id) ?? `${group}-${index}`,
				group,
				kind: human(flag.kind),
				start,
				end,
				window: group === 'navigation' ? 'navigation proxy' : (str(item.window_id) ?? 'window unknown'),
				tier: item.tier ? `tier ${String(item.tier)} ${human(item.tier_name ?? '')}`.trim() : '',
				note:
					group === 'suppressed'
						? `lower priority in window; shown instead: ${str(item.winner_flag_id) ?? 'unknown'}`
						: group === 'navigation'
							? 'navigation proxy; not a confirmed bar'
							: null
			};
		});
	return {
		shown: read(doc.shown, 'shown'),
		navigation: read(doc.hidden_navigation, 'navigation'),
		suppressed: read(doc.suppressed, 'suppressed'),
		denominators: rec(doc.denominators),
		windowBasis: rec(doc.window_basis)
	};
}

// --------------------------------------------------------------------------- click grid

/** Ticks at phase + k·period inside [min, max] (a recorded navigation grid; never fitted here). */
export function gridTicks(grid: { period_seconds: number; phase_seconds: number } | null, min: number, max: number, cap = 4000): number[] {
	if (!grid || !(grid.period_seconds > 0) || !Number.isFinite(min) || !Number.isFinite(max) || max <= min) return [];
	const first = Math.ceil((min - grid.phase_seconds) / grid.period_seconds);
	const ticks: number[] = [];
	for (let k = first; ticks.length < cap; k += 1) {
		const t = grid.phase_seconds + k * grid.period_seconds;
		if (t > max) break;
		if (t >= min) ticks.push(t);
	}
	return ticks;
}

// --------------------------------------------------------------------------- keyboard parity with S2

export type KeyAction =
	| 'seek_back'
	| 'seek_forward'
	| 'span_start'
	| 'span_end'
	| 'loop'
	| 'queue_phrase_point'
	| 'queue_selected_kind'
	| 'next_boundary'
	| 'prev_boundary'
	| 'next_flag'
	| 'prev_flag'
	| 'undo';

/** The 12 S2 practice bindings. They fire only from the transport or the quick-mark bar (callers attach them there). */
export const KEY_BINDINGS: ReadonlyArray<{ key: string; shift: boolean; action: KeyAction; text: string }> = [
	{ key: 'ArrowLeft', shift: false, action: 'seek_back', text: '← seek back one step' },
	{ key: 'ArrowRight', shift: false, action: 'seek_forward', text: '→ seek forward one step' },
	{ key: '[', shift: false, action: 'span_start', text: '[ set span start' },
	{ key: ']', shift: false, action: 'span_end', text: '] set span end' },
	{ key: 'l', shift: false, action: 'loop', text: 'L loop the selected span' },
	{ key: 'b', shift: false, action: 'queue_phrase_point', text: 'B queue a phrase_duration point mark' },
	{ key: 'i', shift: false, action: 'queue_selected_kind', text: 'I queue a mark of the selected kind' },
	{ key: 'n', shift: false, action: 'next_boundary', text: 'N next intent boundary' },
	{ key: 'p', shift: false, action: 'prev_boundary', text: 'P previous intent boundary' },
	{ key: 'n', shift: true, action: 'next_flag', text: 'Shift+N next shown flag' },
	{ key: 'p', shift: true, action: 'prev_flag', text: 'Shift+P previous shown flag' },
	{ key: 'u', shift: false, action: 'undo', text: 'U undo the last queued mark' }
];

type KeyLike = { key: string; shiftKey: boolean; altKey: boolean; ctrlKey: boolean; metaKey: boolean; target: EventTarget | null };

/** Never fires in input/select/textarea or with Alt, Ctrl or Meta held. No action starts playback. */
export function keyAction(event: KeyLike): KeyAction | null {
	const target = event.target as { matches?: (selector: string) => boolean } | null;
	if (target && typeof target.matches === 'function' && target.matches('input,select,textarea,[contenteditable="true"]')) return null;
	if (event.altKey || event.ctrlKey || event.metaKey || typeof event.key !== 'string') return null;
	const key = event.key.length === 1 ? event.key.toLowerCase() : event.key;
	// Arrows keep the S1 behaviour: Shift widens the step (1 s -> 5 s) instead of selecting another action.
	const binding = KEY_BINDINGS.find((item) => item.key === key && (key.startsWith('Arrow') || item.shift === event.shiftKey));
	return binding ? binding.action : null;
}

export function nextTime(marks: number[], reference: number, direction: 1 | -1): number | null {
	const sorted = [...marks].filter(Number.isFinite).sort((a, b) => a - b);
	const found = direction > 0 ? sorted.find((value) => value > reference + 0.01) : [...sorted].reverse().find((value) => value < reference - 0.01);
	return found === undefined ? null : found;
}

// --------------------------------------------------------------------------- annotation requests (annotation_v2)

export type AnnotationDraft = {
	kind: AnnotationKind;
	basis: 'operator_assertion' | 'operator_context';
	status: 'needs_review';
	source_span: { start_seconds: number; end_seconds: number; extent_known: boolean };
	reported_by: { actor: 'operator'; via: 'browser' };
	operator_certainty: 'uncertain' | 'confirmed' | null;
	operator_quote: string | null;
	note: string;
};

export function newKey(): string {
	const uuid =
		typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
			? crypto.randomUUID()
			: `${Date.now().toString(16)}-${Math.random().toString(16).slice(2, 14)}`;
	return `browser-${uuid}`;
}

export function annotationRequest(
	store: { revision: number; source_sha256: string; manifest_sha256: string },
	annotation: AnnotationDraft,
	key: string
): string {
	return JSON.stringify({
		schema_version: 2,
		expected_revision: store.revision,
		idempotency_key: key,
		source_sha256: store.source_sha256,
		manifest_sha256: store.manifest_sha256,
		annotation
	});
}

/** Point or ordered span; an unordered or zero-length span becomes a point (extent unknown). */
export function spanFor(position: number, spanStart: number | null, spanEnd: number | null): AnnotationDraft['source_span'] {
	const round = (value: number) => Number(value.toFixed(3));
	if (spanStart !== null && spanEnd !== null && spanEnd > spanStart) {
		return { start_seconds: round(spanStart), end_seconds: round(spanEnd), extent_known: true };
	}
	return { start_seconds: round(position), end_seconds: round(position), extent_known: false };
}

// --------------------------------------------------------------------------- spectrogram matrices

/** float64 little-endian, row-major frames × bands (lowreg-render-v1). Returns null on a size mismatch. */
export function decodeMatrix(buffer: ArrayBuffer, frames: number, bands: number): Float64Array | null {
	if (!(frames > 0 && bands > 0) || buffer.byteLength !== frames * bands * 8) return null;
	const view = new DataView(buffer);
	const out = new Float64Array(frames * bands);
	for (let i = 0; i < out.length; i += 1) out[i] = view.getFloat64(i * 8, true);
	return out;
}

/** Fixed colour ramp (dark → amber → pale) for a value clamped to [lo, hi]. */
export function rampColour(value: number, lo: number, hi: number): [number, number, number] {
	const t = Number.isFinite(value) ? Math.min(1, Math.max(0, (value - lo) / (hi - lo))) : 0;
	const stops: Array<[number, number, number]> = [
		[22, 21, 18],
		[60, 42, 70],
		[160, 70, 60],
		[214, 180, 116],
		[250, 245, 225]
	];
	const scaled = t * (stops.length - 1);
	const index = Math.min(stops.length - 2, Math.floor(scaled));
	const f = scaled - index;
	const a = stops[index];
	const b = stops[index + 1];
	return [Math.round(a[0] + (b[0] - a[0]) * f), Math.round(a[1] + (b[1] - a[1]) * f), Math.round(a[2] + (b[2] - a[2]) * f)];
}
