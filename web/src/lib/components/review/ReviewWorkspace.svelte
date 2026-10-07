<script lang="ts">
	// /runs/[id]/review workspace (ROUTES_REVIEW_S3.md 6.4): player on the left with the compact overlay and the
	// source-time tracks below it; inspector on the right (Cleanup, Tone, Markers, Notes) with the selected span,
	// the source time and a persistent Mark here. One column below 768 px. Keys match the S2 practice UI and fire
	// only from the transport or the quick-mark bar. Nothing starts playback on its own; only the operator presses play.
	import { beforeNavigate } from '$app/navigation';
	import type { AnnotationClock, AnnotationStorePublic } from '$lib/schema/control';
	import BasisBadge from './BasisBadge.svelte';
	import CompactOverlay from './CompactOverlay.svelte';
	import FlagsList from './FlagsList.svelte';
	import MarkHere from './MarkHere.svelte';
	import QuickMarkBar from './QuickMarkBar.svelte';
	import SpectrogramView from './SpectrogramView.svelte';
	import TimelineTracks from './TimelineTracks.svelte';
	import TimingTable from './TimingTable.svelte';
	import { pauseOthers } from './media';
	import {
		BASIS_STYLE,
		ORIGIN_STYLE,
		clockText,
		detectorSpans,
		fixed,
		flagGroups,
		gridTicks,
		human,
		intentFiles,
		keyAction,
		nextTime,
		rec,
		shortSha,
		str,
		type BasisKey,
		type FlagItem
	} from './review-logic';
	import type { LayersView, ProcessingView, StageView } from './types';

	interface Props {
		runId: string;
		layers: LayersView;
		processing: ProcessingView | null;
		stages: readonly StageView[];
		videoSourceId: string | null;
		annotationSourceId: string | null;
		store: AnnotationStorePublic | null;
		clock: AnnotationClock | null;
		markDisabledReason: string | null;
	}
	let props: Props = $props();
	// The workspace owns the live store once a save returns a newer revision (the page re-keys this component
	// when the annotation source or bundle changes, so capturing the initial props here is intended).
	// svelte-ignore state_referenced_locally
	let store = $state<AnnotationStorePublic | null>(props.store);
	// svelte-ignore state_referenced_locally
	let clock = $state<AnnotationClock | null>(props.clock);

	// --------------------------------------------------------------------- clocks and position
	const extentStart = $derived(props.layers.source_extent.audio_start_seconds ?? 0);
	const extentEnd = $derived(extentStart + (props.layers.source_extent.duration_seconds ?? 0));
	const offset = $derived(clock?.source_start_seconds ?? 0);
	const hasVideo = $derived(props.videoSourceId !== null);
	let currentTime = $state(0);
	let manualPosition = $state(0);
	const position = $derived(hasVideo ? currentTime + offset : manualPosition);
	const timelineMin = $derived(Math.min(extentStart, clock?.source_start_seconds ?? extentStart));
	const timelineMax = $derived(Math.max(extentEnd, clock?.source_end_seconds ?? extentEnd, timelineMin + 1));
	function seek(target: number): void {
		const clamped = Math.min(timelineMax, Math.max(timelineMin, target));
		if (hasVideo) currentTime = Math.max(0, clamped - offset);
		else manualPosition = clamped;
	}

	// --------------------------------------------------------------------- span, loop and toggles
	let spanStart = $state<number | null>(null);
	let spanEnd = $state<number | null>(null);
	let looping = $state(false);
	const spanOrdered = $derived(spanStart !== null && spanEnd !== null && spanEnd > spanStart);
	$effect(() => {
		if (looping && spanOrdered && spanStart !== null && spanEnd !== null && position >= spanEnd) seek(spanStart);
	});
	const toggles = $state({
		label: true,
		bpm: true,
		badges: true,
		uncertainJoins: false,
		breakdown: false,
		clickGrid: false,
		navigation: false,
		suppressed: false,
		spectrogram: false
	});
	let matrix = $state<'log_power_db' | 'pcen'>('log_power_db');
	let zoom = $state(24);
	let tab = $state<'cleanup' | 'tone' | 'markers' | 'notes'>('markers');

	// --------------------------------------------------------------------- layers
	const coverage = $derived(props.layers.layers.coverage);
	const files = $derived(coverage.status === 'available' ? intentFiles(coverage.document) : []);
	let anchorIndex = $state<number | null>(null);
	const anchor = $derived(files.length ? files[Math.min(anchorIndex ?? Math.floor((files.length - 1) / 2), files.length - 1)] : null);
	const detector = $derived(coverage.status === 'available' ? detectorSpans(coverage.document) : []);
	const triage = $derived(props.layers.layers.flags_triage);
	const flags = $derived(triage.status === 'available' ? flagGroups(triage.document) : { shown: [], navigation: [], suppressed: [], denominators: {}, windowBasis: {} });
	const trackFlags = $derived([...flags.shown, ...(toggles.navigation ? flags.navigation : []), ...(toggles.suppressed ? flags.suppressed : [])]);
	const bpm = $derived(props.layers.layers.bpm);
	const ticks = $derived(toggles.clickGrid ? gridTicks(bpm.grid, timelineMin, timelineMax) : []);
	const annotations = $derived(store?.annotations ?? []);
	let lastFlag = $state<FlagItem | null>(null);
	const flagNote = $derived(lastFlag ? `near triaged flag ${lastFlag.id} (detector hypothesis)` : null);

	const currentUnit = $derived(anchor?.units.find((unit) => position >= unit.start && position < unit.end) ?? null);
	const bpmText = $derived(bpm.value !== null ? `BPM ${fixed(bpm.value, 1)} (copied; click identity unverified)` : 'BPM unknown');
	const badges = $derived.by(() => {
		const out: { text: string; basis: string; glyph: string }[] = [];
		for (const flag of flags.shown) {
			if (flag.start !== null && position >= flag.start - 0.05 && position <= (flag.end ?? flag.start) + 0.05) {
				out.push({ text: `${ORIGIN_STYLE.detector.label} · ${flag.kind}`, basis: 'detector', glyph: ORIGIN_STYLE.detector.glyph });
			}
		}
		for (const record of annotations) {
			const span = record.source_span;
			if (position >= span.start_seconds - 0.25 && position <= Math.max(span.end_seconds, span.start_seconds) + 0.25) {
				const style = BASIS_STYLE[record.basis as BasisKey];
				out.push({ text: `${record.claim_label} · ${human(record.kind)}`, basis: record.basis, glyph: style?.glyph ?? '?' });
			}
		}
		return out.slice(0, 2);
	});

	// --------------------------------------------------------------------- keys (S2 parity)
	let session = $state(false);
	let markBusy = $state(false);
	let queueBusy = $state(false);
	let queueLength = $state(0);
	let quick = $state<{ queueMark: (trigger: 'B' | 'I') => boolean; undo: () => boolean } | null>(null);
	let notice = $state('');
	const SESSION_ACTIONS = new Set(['queue_phrase_point', 'queue_selected_kind', 'next_boundary', 'prev_boundary', 'next_flag', 'prev_flag', 'undo']);

	function onkey(event: KeyboardEvent): void {
		const action = keyAction(event);
		if (action === null) return;
		if (SESSION_ACTIONS.has(action) && !session) return;
		event.preventDefault();
		const step = event.shiftKey ? 5 : 1;
		switch (action) {
			case 'seek_back':
				seek(position - step);
				break;
			case 'seek_forward':
				seek(position + step);
				break;
			case 'span_start':
				spanStart = Number(position.toFixed(3));
				break;
			case 'span_end':
				spanEnd = Number(position.toFixed(3));
				break;
			case 'loop':
				looping = !looping;
				break;
			case 'queue_phrase_point':
				quick?.queueMark('B');
				break;
			case 'queue_selected_kind':
				quick?.queueMark('I');
				break;
			case 'next_boundary':
			case 'prev_boundary': {
				const target = nextTime(anchor?.boundaries.map((row) => row.seconds) ?? [], position, action === 'next_boundary' ? 1 : -1);
				notice = target === null ? 'No intent boundary in that direction.' : `At intent boundary ${clockText(target)} (projected; not detected).`;
				if (target !== null) seek(target);
				break;
			}
			case 'next_flag':
			case 'prev_flag': {
				const shown = flags.shown.filter((flag) => flag.start !== null);
				const target = nextTime(shown.map((flag) => flag.start as number), position, action === 'next_flag' ? 1 : -1);
				const flag = shown.find((item) => item.start === target) ?? null;
				notice = flag ? `At ${flag.id} · ${flag.kind} (detector hypothesis).` : 'No shown flag in that direction.';
				if (flag && target !== null) {
					lastFlag = flag;
					seek(target);
				}
				break;
			}
			case 'undo':
				quick?.undo();
				break;
		}
	}

	// Unsaved quick marks: the standard prompt on navigation and on tab close while the queue is non-empty.
	beforeNavigate(({ cancel, type }) => {
		if (queueLength > 0 && type !== 'leave' && !confirm('Quick marks are queued and unsaved. Leave this page?')) cancel();
	});
	function beforeUnload(event: BeforeUnloadEvent): void {
		if (queueLength > 0) {
			event.preventDefault();
			event.returnValue = '';
		}
	}
	const clockNote = $derived(`layer/annotation clock alignment: unverified`);
	const mediaUrl = $derived(props.videoSourceId ? `/api/sources/${props.videoSourceId}/media` : null);
	const spanText = $derived(spanOrdered ? `${clockText(spanStart)}–${clockText(spanEnd)}` : spanStart !== null || spanEnd !== null ? 'span not ordered (start must precede end)' : 'no span selected');
	const savedSorted = $derived([...annotations].sort((a, b) => a.source_span.start_seconds - b.source_span.start_seconds));
</script>

<svelte:window onbeforeunload={beforeUnload} />

<div class="grid grid-cols-1 gap-4 md:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]" data-review-workspace="true">
	<div class="min-w-0 space-y-3">
		<div class="relative" data-player-box="true">
			{#if mediaUrl}
				<!-- svelte-ignore a11y_media_has_caption -->
				<video class="w-full" controls preload="metadata" src={mediaUrl} bind:currentTime data-player="review-source" onplay={(event) => pauseOthers(event.currentTarget)}></video>
			{:else}
				<div class="vu-panel card p-6 text-sm" data-player="none">
					No admitted source of this run is playable here ({props.markDisabledReason ?? 'run_source_not_admitted'}). The layers still render;
					move the position with the transport slider.
				</div>
			{/if}
			<CompactOverlay label={currentUnit?.label ?? null} bpm={bpmText} {badges} showLabel={toggles.label} showBpm={toggles.bpm} showBadges={toggles.badges} {clockNote} />
		</div>

		<div class="vu-panel card space-y-2 p-3 text-sm" role="toolbar" aria-label="Transport (keys: ← → [ ] L; with a labelling session also B I N P Shift+N Shift+P U)" tabindex="0" onkeydown={onkey} data-transport="true">
			<div class="flex flex-wrap items-center gap-2">
				<span>Source time <span class="vu-time" data-source-time={position.toFixed(3)}>{clockText(position)}</span></span>
				<button type="button" class="btn btn-sm preset-tonal" onclick={() => seek(position - 1)}>−1 s</button>
				<button type="button" class="btn btn-sm preset-tonal" onclick={() => seek(position + 1)}>+1 s</button>
				<button type="button" class="btn btn-sm preset-tonal" onclick={() => (spanStart = Number(position.toFixed(3)))}>[ start</button>
				<button type="button" class="btn btn-sm preset-tonal" onclick={() => (spanEnd = Number(position.toFixed(3)))}>] end</button>
				<label class="inline-flex items-center gap-1"><input type="checkbox" class="checkbox" bind:checked={looping} /> Loop span (L)</label>
				<button type="button" class="btn btn-sm preset-tonal" onclick={() => { spanStart = null; spanEnd = null; looping = false; }}>Clear span</button>
			</div>
			{#if !hasVideo}
				<label class="label"><span class="label-text text-xs">Position (source seconds)</span>
					<input type="range" class="w-full" min={timelineMin} max={timelineMax} step="0.01" bind:value={manualPosition} />
				</label>
			{/if}
			<p class="vu-muted text-xs">
				Span: {spanText}{looping ? ' · looping' : ''}. Player offset: {clock ? `${fixed(clock.source_start_seconds, 3)} s from the web clock manifest` : 'unknown (no annotation clock)'}; alignment unverified.
				{#if notice} · {notice}{/if}
			</p>
		</div>

		<QuickMarkBar bind:this={quick} sourceId={props.annotationSourceId} disabledReason={props.markDisabledReason} bind:store bind:clock {position}
			bounds={clock ? { min: clock.source_start_seconds, max: clock.source_end_seconds } : null} {flagNote} bind:session {markBusy} bind:queueBusy bind:queueLength {onkey} />

		<fieldset class="vu-panel card flex flex-wrap gap-x-4 gap-y-1 p-3 text-xs" data-overlay-toggles="true">
			<legend class="vu-eyebrow px-1">Compact overlay and tracks</legend>
			<label><input type="checkbox" class="checkbox" bind:checked={toggles.label} /> Phrase/section label</label>
			<label><input type="checkbox" class="checkbox" bind:checked={toggles.bpm} /> BPM</label>
			<label><input type="checkbox" class="checkbox" bind:checked={toggles.badges} /> Issue badges (≤ 2)</label>
			<label><input type="checkbox" class="checkbox" bind:checked={toggles.uncertainJoins} /> Uncertain joins</label>
			<label><input type="checkbox" class="checkbox" bind:checked={toggles.breakdown} /> Breakdown execution unknown</label>
			<label><input type="checkbox" class="checkbox" bind:checked={toggles.clickGrid} disabled={!bpm.grid} /> Click grid{bpm.grid ? '' : ' (none recorded)'}</label>
			<label><input type="checkbox" class="checkbox" bind:checked={toggles.navigation} /> Navigation proxies (navigation proxy; not a confirmed bar)</label>
			<label><input type="checkbox" class="checkbox" bind:checked={toggles.suppressed} /> Suppressed flags</label>
			<label><input type="checkbox" class="checkbox" bind:checked={toggles.spectrogram} /> Spectrogram</label>
			{#if toggles.spectrogram}
				<label>Matrix
					<select class="select select-sm" bind:value={matrix}>
						<option value="log_power_db">log-power dB (default)</option>
						<option value="pcen">PCEN (experimental)</option>
					</select>
				</label>
			{/if}
			<label>Zoom <input type="range" min="4" max="200" step="1" bind:value={zoom} aria-label="Timeline zoom (pixels per second)" /></label>
		</fieldset>

		{#if files.length > 1}
			<label class="label text-sm"><span class="label-text text-xs">Arrangement anchor (review candidate · not adopted · ±1 click alternatives)</span>
				<select class="select" value={String(files.indexOf(anchor as never))} onchange={(event) => (anchorIndex = Number(event.currentTarget.value))}>
					{#each files as file, index (index)}<option value={String(index)}>k{file.k0 ?? '?'} · {file.anchorStatus}</option>{/each}
				</select>
			</label>
		{/if}
		{#if coverage.status !== 'available'}<p class="vu-muted text-sm">Coverage layer unavailable: {human(coverage.reason)}.</p>{/if}
		<TimelineTracks min={timelineMin} max={timelineMax} {position} {zoom} units={anchor?.units ?? []} boundaries={anchor?.boundaries ?? []} {detector}
			flags={trackFlags} {ticks} {annotations} {spanStart} {spanEnd} showUncertainJoins={toggles.uncertainJoins} showBreakdown={toggles.breakdown} onseek={seek} />
		{#if toggles.clickGrid && bpm.grid}<p class="vu-muted text-xs">Click grid: period {fixed(bpm.grid.period_seconds, 4)} s from {bpm.grid.basis}. {bpm.reason}.</p>{/if}
		{#if toggles.spectrogram}<SpectrogramView runId={props.runId} meta={props.layers.spectrogram} {matrix} />{/if}
	</div>

	<aside class="min-w-0 space-y-3" aria-label="Inspector" data-inspector="true">
		<div class="vu-panel card space-y-2 p-3 text-sm" data-inspector-header="true">
			<p>Source time <span class="vu-time">{clockText(position)}</span> · span {spanText}</p>
			<MarkHere sourceId={props.annotationSourceId} disabledReason={props.markDisabledReason} bind:store bind:clock {position} {spanStart} {spanEnd} {flagNote} bind:markBusy {queueBusy} />
		</div>
		<div class="flex flex-wrap gap-1" role="tablist" aria-label="Inspector tabs">
			{#each [['cleanup', 'Cleanup'], ['tone', 'Tone'], ['markers', 'Markers'], ['notes', 'Notes']] as [key, label] (key)}
				<button type="button" role="tab" class="btn btn-sm {tab === key ? 'preset-filled-primary-300-700' : 'preset-tonal'}" aria-selected={tab === key}
					onclick={() => (tab = key as typeof tab)}>{label}</button>
			{/each}
		</div>
		<div class="vu-panel card space-y-3 p-3 text-sm" role="tabpanel" data-tab={tab}>
			{#if tab === 'cleanup'}
				{#if props.processing}
					<p>Denoise: {props.processing.denoise.filter ?? 'unknown'} · delay {props.processing.denoise.delay_samples ?? 'unknown'} samples · {human(props.processing.denoise.status)}</p>
					<p>{props.processing.high_pass_applied === false ? 'No high-pass (manifest field)' : `High-pass applied: ${props.processing.high_pass_applied ?? 'unknown'}`} · {props.processing.hum_notches_applied === false ? 'No hum notch (manifest field)' : `Hum notch applied: ${props.processing.hum_notches_applied ?? 'unknown'}`}</p>
					<p>Noise capture interval: {props.processing.noise_capture.selected_seconds?.map((v) => fixed(v, 2)).join('–') ?? 'unknown'} s</p>
				{:else}<p class="vu-muted">Processing record unavailable.</p>{/if}
				<ul class="space-y-1">
					{#each props.stages as stage (stage.stage)}<li><code>{stage.stage}</code> · {stage.file_role} · {shortSha(stage.signal_version)} · {stage.state}</li>{/each}
				</ul>
			{:else if tab === 'tone'}
				{@const tone = props.layers.layers.tone_ab}
				{#if props.processing}
					<p>Profile <code>{props.processing.profile_name ?? 'unknown'}</code>; peaking EQ {props.processing.tone.peaking_eq.map((b) => `${fixed(b.frequency_hz, 0)} Hz ${fixed(b.gain_db, 1)} dB`).join(', ') || 'none recorded'}.</p>
				{/if}
				<p>Matched A/B: {tone.status === 'available' ? `${human(rec(rec(tone.document).loudness_match).match_status)} (see Compare)` : `unavailable (${human(tone.reason)})`} · <a class="anchor" href={`/runs/${props.runId}/compare`}>open Compare</a></p>
				<p>Low-register spectrogram: {props.layers.spectrogram.status}{props.layers.spectrogram.reason ? ` (${props.layers.spectrogram.reason})` : ''}. Toggle “Spectrogram” under the player to draw it.</p>
				<p class="vu-muted text-xs">Perceived fullness, nasal quality and the presence of a played ~32 Hz fundamental are listening judgements; band levels are mixture energy.</p>
			{:else if tab === 'markers'}
				<FlagsList available={triage.status === 'available'} reason={triage.reason} shown={flags.shown} navigation={flags.navigation} suppressed={flags.suppressed}
					denominators={flags.denominators} windowKind={str(flags.windowBasis.kind) ?? 'unknown'} bind:showNavigation={toggles.navigation} bind:showSuppressed={toggles.suppressed}
					onseek={(seconds, flag) => { lastFlag = flag; seek(seconds); }} />
				<TimingTable layer={props.layers.layers.phrase_timing} onseek={seek} />
				{#if anchor}
					<details>
						<summary>Intent boundaries ({anchor.boundaries.length}) · k{anchor.k0 ?? '?'} · {anchor.anchorStatus}</summary>
						<ul class="space-y-1 text-xs">
							{#each anchor.boundaries as row (row.id)}
								<li>{row.id} · {clockText(row.seconds)} · {row.join} join{row.join === 'uncertain' ? ' · uncertain join' : ''}{row.breakdown ? ' · breakdown execution unknown' : ''} · {row.text}</li>
							{/each}
						</ul>
					</details>
				{/if}
			{:else}
				<p class="vu-muted text-xs">Saved notes from the annotation store ({annotations.length}). User reports and detector hypotheses are separate items with their own label and shape.</p>
				{#if store}
					<ul class="space-y-1" data-saved-notes="true">
						{#each savedSorted as record (record.id)}
							<li data-annotation-id={record.id} data-claim-label={record.claim_label}>
								<BasisBadge basis={record.basis} claimLabel={record.claim_label} />
								<span class="vu-time">{clockText(record.source_span.start_seconds)}{record.source_span.extent_known ? `–${clockText(record.source_span.end_seconds)}` : ' (point)'}</span>
								· {human(record.kind)}{record.operator_quote ? ` · “${record.operator_quote}”` : ''} · {record.note}
							</li>
						{/each}
					</ul>
					<p class="vu-muted text-xs">Store revision {store.revision} · listening acceptance {store.listening_acceptance} · musical verdict not established.</p>
				{:else}
					<p class="vu-muted">No annotation store is available ({props.markDisabledReason ?? 'annotation_source_clock_unknown'}).</p>
				{/if}
			{/if}
		</div>
	</aside>
</div>
