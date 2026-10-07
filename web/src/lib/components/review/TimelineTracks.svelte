<script lang="ts">
	// Source-time tracks (port of the S2 coverage strip): INTENT units and joins, DETECTOR HYPOTHESIS spans,
	// triaged flags, the recorded click grid and saved annotations. The timeline pans inside its own labelled
	// viewport; the page itself never scrolls horizontally. Selecting an item seeks without playing.
	import type { AnnotationRecord } from '$lib/schema/control';
	import { BASIS_STYLE, ORIGIN_STYLE, clockText, type BasisKey, type DetectorSpan, type FlagItem, type IntentBoundary, type IntentUnit } from './review-logic';

	interface Props {
		min: number;
		max: number;
		position: number;
		zoom: number;
		units: IntentUnit[];
		boundaries: IntentBoundary[];
		detector: DetectorSpan[];
		flags: FlagItem[];
		ticks: number[];
		annotations: readonly AnnotationRecord[];
		spanStart: number | null;
		spanEnd: number | null;
		showUncertainJoins: boolean;
		showBreakdown: boolean;
		onseek: (seconds: number) => void;
	}
	let { min, max, position, zoom, units, boundaries, detector, flags, ticks, annotations, spanStart, spanEnd, showUncertainJoins, showBreakdown, onseek }: Props = $props();

	const extent = $derived(Math.max(0.001, max - min));
	const width = $derived(Math.max(320, Math.round(extent * zoom)));
	const x = (seconds: number) => Math.round(((Math.min(max, Math.max(min, seconds)) - min) / extent) * width);
	const w = (start: number, end: number) => Math.max(3, x(end) - x(start));
	const operator = $derived(annotations.filter((record) => record.basis === 'operator_assertion' || record.basis === 'operator_context'));
	const review = $derived(annotations.filter((record) => record.basis === 'detector_hypothesis' || record.basis === 'reference_comparison'));
	const style = (basis: string) => BASIS_STYLE[basis as BasisKey] ?? { label: 'UNKNOWN BASIS', shape: 'plain', text: 'basis not recorded', glyph: '?' };
</script>

<!-- svelte-ignore a11y_no_noninteractive_tabindex (the scrollable viewport must be keyboard reachable) -->
<div class="vu-timeline" role="region" aria-label="Source timeline in decoded source-audio seconds (pans horizontally)" tabindex="0" data-timeline="true">
	<div class="vu-timeline-inner" style:width={`${width}px`}>
		<div class="vu-lane" data-lane="intent">
			<span class="vu-lane-label">{ORIGIN_STYLE.intent_projected.glyph} INTENT · projected</span>
			{#each units as unit (unit.id)}
				<button type="button" class="vu-unit" style:left={`${x(unit.start)}px`} style:width={`${w(unit.start, unit.end)}px`}
					aria-label={`INTENT projected unit ${unit.label} ${clockText(unit.start)} to ${clockText(unit.end)}${unit.outside ? ' outside source' : ''}`}
					onclick={() => onseek(unit.start)}>{unit.label}{unit.outside ? ' · outside source' : ''}</button>
			{/each}
			{#each boundaries as row (row.id)}
				<span class="vu-join vu-join-{row.join}" class:vu-join-dashed={showUncertainJoins && row.join === 'uncertain'} style:left={`${x(row.seconds)}px`}
					role="img" aria-label={row.join === 'uncertain' ? 'uncertain join' : `${row.join} join`} title={`${row.id} · ${clockText(row.seconds)} · ${row.join} join`}>
					{#if showUncertainJoins && row.join === 'uncertain'}<span class="vu-join-text">uncertain join</span>{/if}
					{#if showBreakdown && row.breakdown}<span class="vu-join-text">≈ breakdown execution unknown</span>{/if}
				</span>
			{/each}
		</div>
		<div class="vu-lane" data-lane="detector">
			<span class="vu-lane-label">{ORIGIN_STYLE.detector.glyph} DETECTOR HYPOTHESIS</span>
			{#each detector as span, index (index)}
				<button type="button" class="vu-span vu-shape-dotted" style:left={`${x(span.start)}px`} style:width={`${w(span.start, span.end)}px`}
					aria-label={`DETECTOR HYPOTHESIS ${span.kind} ${clockText(span.start)} to ${clockText(span.end)}`} onclick={() => onseek(span.start)}>{span.label}</button>
			{/each}
		</div>
		<div class="vu-lane" data-lane="flags">
			<span class="vu-lane-label">{ORIGIN_STYLE.detector.glyph} Triaged flags</span>
			{#each flags as flag (flag.id)}
				{#if flag.start !== null}
					<button type="button" class="vu-flag vu-flag-{flag.group}" style:left={`${x(flag.start)}px`} style:width={`${w(flag.start, flag.end ?? flag.start)}px`}
						aria-label={`${flag.group === 'navigation' ? 'navigation proxy; not a confirmed bar' : flag.group === 'suppressed' ? 'suppressed flag' : 'shown flag'} ${flag.kind} ${clockText(flag.start)}`}
						onclick={() => flag.start !== null && onseek(flag.start)}>{flag.group === 'navigation' ? 'navigation proxy; not a confirmed bar' : flag.kind}</button>
				{/if}
			{/each}
		</div>
		{#if ticks.length}
			<div class="vu-lane vu-lane-thin" data-lane="click-grid">
				<span class="vu-lane-label">Click grid (recorded navigation grid; click identity unverified)</span>
				{#each ticks as tick, index (index)}<span class="vu-tick" style:left={`${x(tick)}px`}></span>{/each}
			</div>
		{/if}
		<div class="vu-lane" data-lane="operator">
			<span class="vu-lane-label">{BASIS_STYLE.operator_assertion.glyph} USER REPORTED / {BASIS_STYLE.operator_context.label}</span>
			{#each operator as record (record.id)}
				<span class="vu-mark vu-shape-{style(record.basis).shape}" style:left={`${x(record.source_span.start_seconds)}px`}
					style:width={record.source_span.extent_known ? `${w(record.source_span.start_seconds, record.source_span.end_seconds)}px` : undefined}
					role="img" aria-label={`${record.claim_label} ${style(record.basis).text} ${record.kind} ${clockText(record.source_span.start_seconds)}`}
					data-mark-basis={record.basis}>{style(record.basis).glyph} {record.claim_label}</span>
			{/each}
		</div>
		<div class="vu-lane" data-lane="review">
			<span class="vu-lane-label">{BASIS_STYLE.detector_hypothesis.glyph} REVIEW / {BASIS_STYLE.reference_comparison.label}</span>
			{#each review as record (record.id)}
				<span class="vu-mark vu-shape-{style(record.basis).shape}" style:left={`${x(record.source_span.start_seconds)}px`}
					role="img" aria-label={`${record.claim_label} ${style(record.basis).text} ${record.kind} ${clockText(record.source_span.start_seconds)}`}
					data-mark-basis={record.basis}>{style(record.basis).glyph} {record.claim_label}</span>
			{/each}
		</div>
		{#if spanStart !== null && spanEnd !== null && spanEnd > spanStart}
			<span class="vu-selection" style:left={`${x(spanStart)}px`} style:width={`${w(spanStart, spanEnd)}px`} aria-hidden="true"></span>
		{/if}
		<span class="vu-playhead" style:left={`${x(position)}px`} aria-hidden="true"></span>
	</div>
</div>
<p class="vu-muted text-xs">
	Ticks: solid = supported join; dashed = weak or uncertain join; overlap is not agreement, accuracy or correctness.
	Axis: decoded source-audio seconds {clockText(min)}–{clockText(max)}.
</p>

<style>
	.vu-timeline {
		max-width: 100%;
		overflow-x: auto;
		border: 1px solid var(--vu-line);
		border-radius: 6px;
	}
	.vu-timeline-inner {
		position: relative;
		padding: 0.25rem 0;
	}
	.vu-lane {
		position: relative;
		height: 2.6rem;
		border-bottom: 1px solid var(--vu-line);
	}
	.vu-lane-thin {
		height: 1.6rem;
	}
	.vu-lane-label {
		position: sticky;
		left: 0;
		z-index: 2;
		display: inline-block;
		padding: 0 0.4rem;
		font-size: 0.65rem;
		letter-spacing: 0.06em;
		background: var(--vu-panel);
		color: var(--vu-muted);
	}
	.vu-unit,
	.vu-span,
	.vu-flag,
	.vu-mark {
		position: absolute;
		top: 1.05rem;
		height: 1.35rem;
		overflow: hidden;
		white-space: nowrap;
		text-overflow: ellipsis;
		font-size: 0.68rem;
		padding: 0 0.25rem;
		border: 1px solid var(--vu-line);
		background: #2b261f;
		text-align: left;
	}
	.vu-unit {
		border-radius: 2px;
		border-color: var(--vu-gold);
	}
	.vu-flag-shown {
		border-style: dotted;
		border-color: var(--vu-coral);
	}
	.vu-flag-navigation,
	.vu-flag-suppressed {
		border-style: dotted;
		opacity: 0.75;
	}
	.vu-mark {
		min-width: 1.4rem;
		border-radius: 999px;
	}
	.vu-join {
		position: absolute;
		top: 0.9rem;
		width: 0;
		height: 1.7rem;
		border-left: 2px solid var(--vu-gold);
	}
	.vu-join-weak,
	.vu-join-uncertain,
	.vu-join-unknown {
		border-left-style: dashed;
	}
	.vu-join-dashed {
		border-left: 2px dashed var(--vu-coral);
	}
	.vu-join-text {
		position: absolute;
		top: -0.85rem;
		left: 0.15rem;
		font-size: 0.6rem;
		white-space: nowrap;
		color: var(--vu-coral);
	}
	.vu-tick {
		position: absolute;
		top: 1rem;
		width: 1px;
		height: 0.5rem;
		background: var(--vu-muted);
	}
	.vu-selection {
		position: absolute;
		top: 0;
		bottom: 0;
		background: rgba(214, 180, 116, 0.12);
		pointer-events: none;
	}
	.vu-playhead {
		position: absolute;
		top: 0;
		bottom: 0;
		width: 2px;
		background: var(--vu-gold);
		pointer-events: none;
	}
</style>
