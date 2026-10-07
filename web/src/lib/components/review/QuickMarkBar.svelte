<script lang="ts">
	// Labelling session (port of practice_s2.js 5.7): queue point marks with keys, then save them in order.
	// Each save carries its own browser-<uuid> key and the latest revision. Transport errors, 5xx and malformed
	// receipts freeze the head with its exact bytes and key (Retry same mark); stale_annotation_revision refreshes
	// the store and keeps the rest of the queue with fresh keys; any other 4xx keeps that mark with its code.
	import type { AnnotationClock, AnnotationStorePublic } from '$lib/schema/control';
	import { postAnnotation, readStore } from './annotations-client';
	import BasisBadge from './BasisBadge.svelte';
	import { ANNOTATION_KINDS, annotationRequest, clockText, human, newKey, type AnnotationDraft, type AnnotationKind } from './review-logic';

	interface Queued {
		annotation: AnnotationDraft;
		trigger: 'B' | 'I';
		error: string | null;
	}
	interface Props {
		sourceId: string | null;
		disabledReason: string | null;
		store: AnnotationStorePublic | null;
		clock: AnnotationClock | null;
		position: number;
		bounds: { min: number; max: number } | null;
		flagNote: string | null;
		session: boolean;
		markBusy: boolean;
		queueBusy: boolean;
		queueLength: number;
		onkey: (event: KeyboardEvent) => void;
	}
	let {
		sourceId, disabledReason, store = $bindable(), clock = $bindable(), position, bounds, flagNote,
		session = $bindable(), markBusy, queueBusy = $bindable(), queueLength = $bindable(), onkey
	}: Props = $props();

	let template = $state('');
	let kind = $state<AnnotationKind>('phrase_duration');
	let certainty = $state<'uncertain' | 'confirmed'>('uncertain');
	let queue = $state<Queued[]>([]);
	let frozen = $state<string | null>(null);
	let uncertain = $state(false);
	let notice = $state('');
	const locked = $derived(queueBusy || uncertain);
	$effect(() => {
		queueLength = queue.length;
	});

	export function queueMark(trigger: 'B' | 'I'): boolean {
		if (!session) return false;
		if (disabledReason || !store) {
			notice = `Quick marks are disabled: ${disabledReason ?? 'annotation_source_clock_unknown'}.`;
			return false;
		}
		if (locked || markBusy) {
			notice = 'A save is in progress or awaiting a retry; finish it before queueing more marks.';
			return false;
		}
		if (!template.trim()) {
			notice = 'Type your template text first; it is saved verbatim as your words.';
			return false;
		}
		const time = Number(position.toFixed(3));
		if (!bounds || !(time >= bounds.min && time <= bounds.max)) {
			notice = 'The current position is outside the annotation clock extent.';
			return false;
		}
		let note = `quick mark (key ${trigger}) at ${clockText(time)}; template text`;
		if (flagNote) note += `; ${flagNote}`;
		queue = [...queue, {
			trigger, error: null,
			annotation: {
				kind: trigger === 'B' ? 'phrase_duration' : kind, basis: 'operator_assertion', status: 'needs_review',
				source_span: { start_seconds: time, end_seconds: time, extent_known: false },
				reported_by: { actor: 'operator', via: 'browser' }, operator_certainty: certainty, operator_quote: template, note
			}
		}];
		notice = `Queued ${queue.length} unsaved mark${queue.length === 1 ? '' : 's'}. Save queued marks when ready.`;
		return true;
	}

	export function undo(): boolean {
		if (locked || queue.length === 0) return false;
		queue = queue.slice(0, -1);
		notice = 'Removed the last unsaved mark.';
		return true;
	}

	async function save(): Promise<void> {
		if (queueBusy || queue.length === 0 || !sourceId || !store) return;
		if (markBusy) {
			notice = 'Mark here is saving; finish it first.';
			return;
		}
		queueBusy = true;
		let saved = 0;
		let replayed = 0;
		try {
			while (queue.length && store) {
				const head = queue[0];
				if (!frozen) frozen = annotationRequest(store, head.annotation, newKey());
				const result = await postAnnotation(sourceId, frozen, store);
				if (result.kind === 'uncertain') {
					uncertain = true;
					notice = `Save outcome unclear for the first queued mark (${human(result.code)}). Retry the same mark; its bytes and key are held.`;
					return;
				}
				if (result.kind === 'stale') {
					frozen = null;
					uncertain = false;
					const fresh = await readStore(sourceId);
					if (fresh) {
						store = fresh.store;
						clock = fresh.clock;
					}
					notice = 'Saved notes changed elsewhere. The remaining queue is kept with fresh keys; press Save queued marks again.';
					return;
				}
				if (result.kind === 'refused') {
					frozen = null;
					uncertain = false;
					queue = [{ ...head, error: result.code }, ...queue.slice(1)];
					notice = `The first queued mark was refused (${human(result.code)}); it stays in the queue and saving stopped.`;
					return;
				}
				store = result.store;
				clock = result.clock;
				frozen = null;
				uncertain = false;
				queue = queue.slice(1);
				if (result.outcome === 'replayed') replayed += 1;
				else saved += 1;
			}
			notice = `Saved ${saved} new mark${saved === 1 ? '' : 's'}${replayed ? ` and reconciled ${replayed} replay${replayed === 1 ? '' : 's'} without duplicates` : ''}. Musical verdict remains unestablished.`;
		} finally {
			queueBusy = false;
		}
	}
</script>

<section class="space-y-2 text-sm" data-labelling-session={session}>
	<label class="flex items-center gap-2"><input type="checkbox" class="checkbox" bind:checked={session} /> Labelling session (quick marks B / I, navigation N / P, Shift+N / Shift+P, undo U)</label>
	{#if session}
		<div class="vu-panel card space-y-2 p-3" role="toolbar" aria-label="Quick-mark bar" tabindex="0" onkeydown={onkey} data-quick-mark-bar="true">
			<div class="grid grid-cols-1 gap-2 sm:grid-cols-3">
				<label class="label"><span class="label-text text-xs">Template text (your words)</span><input class="input" maxlength="4000" bind:value={template} disabled={locked} placeholder="phrase boundary" /></label>
				<label class="label"><span class="label-text text-xs">Kind for I</span>
					<select class="select" bind:value={kind} disabled={locked}>{#each ANNOTATION_KINDS as item (item)}<option value={item}>{human(item)}</option>{/each}</select>
				</label>
				<label class="label"><span class="label-text text-xs">Certainty</span>
					<select class="select" bind:value={certainty} disabled={locked}><option value="uncertain">uncertain</option><option value="confirmed">confirmed</option></select>
				</label>
			</div>
			<ol class="space-y-1" data-queue="true">
				{#each queue as item, index (index)}
					<li><BasisBadge basis="operator_assertion" /> {clockText(item.annotation.source_span.start_seconds)} · {human(item.annotation.kind)} · point (extent unknown) · key {item.trigger} · “{item.annotation.operator_quote}”
						{#if index === 0 && uncertain}<span class="vu-error"> · held for retry with its original key</span>{/if}
						{#if item.error}<span class="vu-error"> · refused: {human(item.error)}</span>{/if}
					</li>
				{/each}
			</ol>
			<div class="flex flex-wrap items-center gap-2">
				<span data-queue-count={queue.length}>{queue.length} queued</span>
				<button type="button" class="btn btn-sm preset-filled-primary-500" disabled={queueBusy || markBusy || queue.length === 0 || !!disabledReason} onclick={save}>{uncertain ? 'Retry same mark' : 'Save queued marks'}</button>
				<button type="button" class="btn btn-sm preset-tonal" disabled={locked || queue.length === 0} onclick={undo}>Undo last</button>
			</div>
			{#if notice}<p class="text-xs" role="status">{notice}</p>{/if}
		</div>
	{/if}
</section>
