<script lang="ts">
	// Source-timed operator notes (annotation_v2 semantics through the control API). The browser writes
	// only operator records (USER REPORTED or INTENT); detector hypotheses (REVIEW) are never created here.
	// Player time -> source time: span seconds = player currentTime + clock.source_start_seconds. Whether
	// the browser media clock matches the container presentation timeline is NOT verified.
	import ControlApiError from './ControlApiError.svelte';
	import { isBffError, type BffError } from '$lib/control-types';
	import { seconds } from '$lib/format';
	import { newFormKey } from '$lib/idempotency';
	import { ANNOTATION_KINDS, type AnnotationClock, type AnnotationRecord, type AnnotationStorePublic } from '$lib/schema/control';

	interface Props {
		sourceId: string;
		store: AnnotationStorePublic | null;
		clock: AnnotationClock | null;
		error: BffError | null;
	}
	let props: Props = $props();

	let live = $state<{ store: AnnotationStorePublic; clock: AnnotationClock } | null>(null);
	const store = $derived(live?.store ?? props.store);
	const clock = $derived(live?.clock ?? props.clock);
	let currentTime = $state(0);
	let draft = $state({
		kind: 'rhythm_timing' as (typeof ANNOTATION_KINDS)[number],
		basis: 'operator_assertion' as 'operator_assertion' | 'operator_context',
		certainty: 'uncertain' as 'uncertain' | 'confirmed',
		quote: '',
		note: '',
		spanLength: ''
	});
	let draftKey = $state(newFormKey('ui-ann'));
	let pending = $state(false);
	let error = $state<BffError | null>(null);
	let message = $state<string | null>(null);

	const operatorTrack = $derived((store?.annotations ?? []).filter((r) => r.reported_by.actor === 'operator'));
	const detectorTrack = $derived((store?.annotations ?? []).filter((r) => r.basis === 'detector_hypothesis'));
	const otherTrack = $derived(
		(store?.annotations ?? []).filter((r) => r.reported_by.actor !== 'operator' && r.basis !== 'detector_hypothesis')
	);
	const sourceTime = $derived(clock ? Number((currentTime + clock.source_start_seconds).toFixed(6)) : null);

	async function refresh(): Promise<void> {
		const response = await fetch(`/api/sources/${props.sourceId}/annotations`, { headers: { accept: 'application/json' } });
		const body: unknown = await response.json().catch(() => null);
		if (response.ok && body && !isBffError(body)) live = body as { store: AnnotationStorePublic; clock: AnnotationClock };
	}

	async function save(event: SubmitEvent) {
		event.preventDefault();
		if (!store || !clock || sourceTime === null || pending) return;
		pending = true;
		error = null;
		message = null;
		const length = draft.spanLength.trim() === '' ? 0 : Number(draft.spanLength);
		const assertion = draft.basis === 'operator_assertion';
		const request = {
			schema_version: 2,
			expected_revision: store.revision,
			idempotency_key: draftKey,
			source_sha256: store.source_sha256,
			manifest_sha256: store.manifest_sha256,
			annotation: {
				kind: draft.kind,
				basis: draft.basis,
				status: 'needs_review',
				source_span: {
					start_seconds: sourceTime,
					end_seconds: length > 0 ? Number((sourceTime + length).toFixed(6)) : sourceTime,
					extent_known: length > 0
				},
				reported_by: { actor: 'operator', via: 'browser' },
				operator_certainty: assertion ? draft.certainty : null,
				operator_quote: assertion ? draft.quote : null,
				note: draft.note
			}
		};
		try {
			const response = await fetch(`/api/sources/${props.sourceId}/annotations`, {
				method: 'POST',
				headers: { 'content-type': 'application/json', accept: 'application/json' },
				body: JSON.stringify(request)
			});
			const body: unknown = await response.json().catch(() => null);
			if (response.ok && body && !isBffError(body)) {
				const result = body as { store: AnnotationStorePublic; clock: AnnotationClock; mutation: { outcome: string } };
				live = { store: result.store, clock: result.clock };
				message = result.mutation.outcome === 'replayed' ? 'Already saved (replayed).' : 'Note saved.';
				draft = { ...draft, quote: '', note: '', spanLength: '' };
				draftKey = newFormKey('ui-ann');
				return;
			}
			error = isBffError(body) ? body : null;
			if (error?.upstream_code === 'stale_annotation_revision') await refresh(); // the draft is kept
		} finally {
			pending = false;
		}
	}

	const span = (r: AnnotationRecord) =>
		r.source_span.extent_known
			? `${seconds(r.source_span.start_seconds)}–${seconds(r.source_span.end_seconds)} s`
			: `${seconds(r.source_span.start_seconds)} s (point; extent unknown)`;
</script>

<section class="vu-panel card space-y-4 p-5" data-annotate="true">
	<div>
		<p class="vu-eyebrow">Annotate</p>
		<h2 class="h4">Source-timed notes</h2>
	</div>

	<figure class="space-y-1">
		<figcaption class="vu-muted text-xs">Source player (admitted bytes; no gain or EQ applied)</figcaption>
		<!-- svelte-ignore a11y_media_has_caption -->
		<video class="w-full max-w-3xl" controls preload="metadata" src={`/api/sources/${props.sourceId}/media`} bind:currentTime data-player="annotate-source"></video>
	</figure>

	{#if props.error && !store}
		<div data-annotation-state="unavailable"><ControlApiError error={props.error} /></div>
	{:else if store && clock}
		<p class="vu-muted text-xs" data-clock-basis="true">
			Source clock {seconds(clock.source_start_seconds)}–{seconds(clock.source_end_seconds)} s from job
			<a class="anchor" href={`/jobs/${clock.job_id}`}><code>{clock.job_id.slice(0, 12)}…</code></a>: {clock.clock_basis}.
			Player-to-source clock offset verified: <strong data-player-clock-verified="false">no</strong>.
			Listening acceptance: <code>{store.listening_acceptance}</code>.
		</p>
		<form class="grid grid-cols-1 gap-3 sm:grid-cols-2" novalidate onsubmit={save} data-annotation-form="true">
			<p class="sm:col-span-2 text-sm">
				Note time (source seconds): <span class="vu-time" data-note-time={sourceTime}>{seconds(sourceTime)}</span>
				<span class="vu-muted text-xs">= player {seconds(currentTime)} s + source start {seconds(clock.source_start_seconds)} s</span>
			</p>
			<label class="label"><span class="label-text">Kind</span>
				<select class="select" bind:value={draft.kind}>{#each ANNOTATION_KINDS as kind (kind)}<option value={kind}>{kind}</option>{/each}</select>
			</label>
			<label class="label"><span class="label-text">Basis</span>
				<select class="select" bind:value={draft.basis}>
					<option value="operator_assertion">USER REPORTED (operator assertion)</option>
					<option value="operator_context">INTENT (operator context)</option>
				</select>
			</label>
			{#if draft.basis === 'operator_assertion'}
				<label class="label"><span class="label-text">Certainty</span>
					<select class="select" bind:value={draft.certainty}><option value="uncertain">uncertain</option><option value="confirmed">confirmed</option></select>
				</label>
				<label class="label"><span class="label-text">Your words (literal quote)</span>
					<input class="input" bind:value={draft.quote} maxlength="4000" />
				</label>
			{/if}
			<label class="label"><span class="label-text">Span length (s, optional; blank = point)</span>
				<input class="input" type="number" min="0" step="0.01" value={draft.spanLength} oninput={(event) => (draft.spanLength = event.currentTarget.value)} />
			</label>
			<label class="label sm:col-span-2"><span class="label-text">Note</span>
				<textarea class="textarea" rows="2" bind:value={draft.note} maxlength="4000"></textarea>
			</label>
			<div class="sm:col-span-2 flex items-center gap-3">
				<button class="btn preset-filled-primary-300-700" type="submit" disabled={pending}>Add note at current time</button>
				{#if message}<span class="text-sm" data-annotation-message="true">{message}</span>{/if}
			</div>
		</form>
		{#if error}<ControlApiError {error} />{/if}
	{/if}

	<div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
		<section class="space-y-2 rounded border border-dashed p-3" data-track="operator">
			<h3 class="h5">User reported / Intent <span class="vu-muted text-xs">(operator)</span></h3>
			{#if operatorTrack.length === 0}
				<p class="vu-muted text-sm">No operator notes yet.</p>
			{:else}
				<ul class="space-y-2 text-sm">
					{#each operatorTrack as record (record.id)}
						<li data-annotation-id={record.id} data-claim-label={record.claim_label}>
							<span class="badge preset-tonal-primary">{record.claim_label}</span>
							<span class="vu-time">{span(record)}</span> · <code>{record.kind}</code>
							{#if record.operator_certainty}· {record.operator_certainty}{/if}
							<br />{#if record.operator_quote}“{record.operator_quote}” — {/if}{record.note}
							<br /><span class="vu-muted text-xs">musical_verdict: {record.musical_verdict}</span>
						</li>
					{/each}
				</ul>
			{/if}
		</section>
		<section class="space-y-2 rounded border border-dotted p-3" data-track="detector">
			<h3 class="h5">Detector hypotheses (REVIEW)</h3>
			{#if detectorTrack.length === 0}
				<p class="vu-muted text-sm" data-detector-empty="true">No detector hypotheses for this job type (share_export runs no detector). This is not an empty pass.</p>
			{:else}
				<ul class="space-y-2 text-sm">
					{#each detectorTrack as record (record.id)}
						<li data-annotation-id={record.id} data-claim-label={record.claim_label}>
							<span class="badge preset-tonal-warning">{record.claim_label}</span>
							<span class="vu-time">{span(record)}</span> · <code>{record.kind}</code> · {record.note}
							<br /><span class="vu-muted text-xs">musical_verdict: {record.musical_verdict}</span>
						</li>
					{/each}
				</ul>
			{/if}
		</section>
	</div>
	{#if otherTrack.length > 0}
		<section class="space-y-2 text-sm" data-track="other">
			<h3 class="h5">Other records (agent or reference)</h3>
			<ul>{#each otherTrack as record (record.id)}<li><span class="badge preset-tonal-surface">{record.claim_label}</span> <span class="vu-time">{span(record)}</span> {record.note}</li>{/each}</ul>
		</section>
	{/if}
</section>
