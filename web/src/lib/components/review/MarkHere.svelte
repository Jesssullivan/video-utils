<script lang="ts">
	// Persistent "Mark here": one operator annotation at the current source time (point) or the selected ordered
	// span, through the existing /api/sources/{id}/annotations (annotation_v2; no new route). The time is the
	// player currentTime plus the clock's source_start_seconds; the layer/annotation clock alignment is unverified.
	import type { AnnotationClock, AnnotationStorePublic } from '$lib/schema/control';
	import { postAnnotation, readStore } from './annotations-client';
	import { ANNOTATION_KINDS, BASIS_STYLE, annotationRequest, clockText, human, newKey, spanFor, type AnnotationKind } from './review-logic';

	interface Props {
		sourceId: string | null;
		disabledReason: string | null;
		store: AnnotationStorePublic | null;
		clock: AnnotationClock | null;
		position: number;
		spanStart: number | null;
		spanEnd: number | null;
		flagNote: string | null;
		markBusy: boolean;
		queueBusy: boolean;
	}
	let { sourceId, disabledReason, store = $bindable(), clock = $bindable(), position, spanStart, spanEnd, flagNote, markBusy = $bindable(), queueBusy }: Props = $props();

	let kind = $state<AnnotationKind>('rhythm_timing');
	let basis = $state<'operator_assertion' | 'operator_context'>('operator_assertion');
	let certainty = $state<'uncertain' | 'confirmed'>('uncertain');
	let quote = $state('');
	let note = $state('');
	let referenceFlag = $state(false);
	let frozen = $state<string | null>(null);
	let uncertain = $state(false);
	let message = $state<string | null>(null);
	const span = $derived(spanFor(position, spanStart, spanEnd));
	const reason = $derived(disabledReason ?? (!store || !sourceId ? 'annotation_source_clock_unknown' : null));
	const blocked = $derived(reason !== null || markBusy || queueBusy);

	async function mark(): Promise<void> {
		if (blocked || !store || !sourceId) return;
		markBusy = true;
		message = null;
		try {
			if (!frozen) {
				const assertion = basis === 'operator_assertion';
				const text = [note.trim(), referenceFlag && flagNote ? flagNote : ''].filter(Boolean).join('; ');
				frozen = annotationRequest(store, {
					kind, basis, status: 'needs_review', source_span: span,
					reported_by: { actor: 'operator', via: 'browser' },
					operator_certainty: assertion ? certainty : null,
					operator_quote: assertion ? quote : null,
					note: text || `Mark here at ${clockText(span.start_seconds)}`
				}, newKey());
			}
			const result = await postAnnotation(sourceId, frozen, store);
			if (result.kind === 'ok') {
				store = result.store;
				clock = result.clock;
				frozen = null;
				uncertain = false;
				quote = '';
				note = '';
				message = result.outcome === 'replayed' ? 'Already saved (replayed without a duplicate).' : 'Saved. Musical verdict remains unestablished.';
			} else if (result.kind === 'uncertain') {
				uncertain = true;
				message = `Save outcome unclear (${human(result.code)}). Retry the same mark; its bytes and key are held.`;
			} else if (result.kind === 'stale') {
				frozen = null;
				uncertain = false;
				const fresh = await readStore(sourceId);
				if (fresh) {
					store = fresh.store;
					clock = fresh.clock;
				}
				message = 'Saved notes changed elsewhere. The store was refreshed; press Mark here again.';
			} else {
				frozen = null;
				uncertain = false;
				message = `Refused: ${human(result.code)}. Nothing was saved.`;
			}
		} finally {
			markBusy = false;
		}
	}
</script>

<section class="space-y-2 rounded border p-3 text-sm" data-mark-here="true" aria-label="Mark here">
	<div class="flex flex-wrap items-center gap-2">
		<button type="button" class="btn btn-sm preset-filled-primary-500" disabled={blocked} onclick={mark} data-mark-here-button="true">
			{uncertain ? 'Retry same mark' : 'Mark here'}
		</button>
		<span class="vu-time">{span.extent_known ? `${clockText(span.start_seconds)}–${clockText(span.end_seconds)} (span)` : `${clockText(span.start_seconds)} (point; extent unknown)`}</span>
		{#if reason}<span class="vu-muted text-xs" data-mark-disabled={reason}>disabled: {reason}</span>{/if}
	</div>
	<div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
		<label class="label"><span class="label-text text-xs">Basis</span>
			<select class="select" bind:value={basis} disabled={blocked}>
				<option value="operator_assertion">{BASIS_STYLE.operator_assertion.glyph} {BASIS_STYLE.operator_assertion.label} ({BASIS_STYLE.operator_assertion.text})</option>
				<option value="operator_context">{BASIS_STYLE.operator_context.glyph} {BASIS_STYLE.operator_context.label} ({BASIS_STYLE.operator_context.text})</option>
			</select>
		</label>
		<label class="label"><span class="label-text text-xs">Kind</span>
			<select class="select" bind:value={kind} disabled={blocked}>{#each ANNOTATION_KINDS as item (item)}<option value={item}>{human(item)}</option>{/each}</select>
		</label>
		{#if basis === 'operator_assertion'}
			<label class="label"><span class="label-text text-xs">Certainty</span>
				<select class="select" bind:value={certainty} disabled={blocked}><option value="uncertain">uncertain</option><option value="confirmed">confirmed</option></select>
			</label>
			<label class="label"><span class="label-text text-xs">Your words (saved verbatim)</span><input class="input" maxlength="4000" bind:value={quote} disabled={blocked} /></label>
		{/if}
		<label class="label sm:col-span-2"><span class="label-text text-xs">Note</span><input class="input" maxlength="3000" bind:value={note} disabled={blocked} /></label>
	</div>
	<p class="vu-muted text-xs">
		Candidate link: none available — a web annotation source has no marker candidates, so no candidate_id is sent.
		<label class="inline-flex items-center gap-1"><input type="checkbox" class="checkbox" bind:checked={referenceFlag} disabled={blocked || !flagNote} /> reference the last selected flag in the note</label>
	</p>
	{#if message}<p class="text-xs" role="status" data-mark-message="true">{message}</p>{/if}
</section>
