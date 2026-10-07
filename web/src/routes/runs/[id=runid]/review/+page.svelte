<script lang="ts">
	import ControlApiError from '$lib/components/ControlApiError.svelte';
	import EvidencePicker from '$lib/components/review/EvidencePicker.svelte';
	import ReviewWorkspace from '$lib/components/review/ReviewWorkspace.svelte';
	import RunUnknowns from '$lib/components/review/RunUnknowns.svelte';
	import { KEY_BINDINGS } from '$lib/components/review/review-logic';
	import type { PageProps } from './$types';
	let { data }: PageProps = $props();
</script>

<section class="space-y-4" data-review-page="true">
	<div>
		<p class="vu-eyebrow">Review · phrase and rhythm evidence</p>
		<h1 class="h3 break-all">Run <code>{data.runId}</code></h1>
		<p class="vu-muted text-sm">
			INTENT spans are the operator arrangement projected on a fitted grid; DETECTOR HYPOTHESIS items are automatic review
			candidates; USER REPORTED items are your notes. None of them is a note-correctness or phrase verdict.
		</p>
	</div>
	{#if data.layersError}
		<ControlApiError error={data.layersError} />
	{:else if data.layers}
		<EvidencePicker runId={data.runId} path="review" selected={data.layers.selected_evidence_id} alternatives={data.layers.alternatives} generated={data.layers.selected_generated_utc} />
		{#if data.clockedSources.length > 1}
			<p class="text-xs">Annotation source:
				{#each data.clockedSources as id (id)}<a class="anchor" href={`/runs/${data.runId}/review?source=${id}`} aria-current={id === data.annotationSourceId ? 'true' : undefined}><code>{id.slice(0, 16)}…</code></a> {/each}
			</p>
		{/if}
		<p class="vu-muted text-xs" data-clock-alignment="unverified">Clock: layers use {data.layers.clock.layer_axis}; annotations use {data.layers.clock.annotation_axis}; alignment {data.layers.clock.alignment}.</p>
		{#key `${data.annotationSourceId}|${data.layers.selected_evidence_id}`}
			<ReviewWorkspace runId={data.runId} layers={data.layers} processing={data.graph?.processing ?? null} stages={data.graph?.stages ?? []}
				videoSourceId={data.videoSourceId} annotationSourceId={data.annotationSourceId} store={data.annotations?.store ?? null}
				clock={data.annotations?.clock ?? null} markDisabledReason={data.markDisabledReason} />
		{/key}
		<details class="vu-panel card p-3 text-xs" data-keymap="true">
			<summary>Keyboard (focus the transport or the quick-mark bar; never in text fields or with Alt/Ctrl/Meta; no key starts playback)</summary>
			<ul class="mt-2 grid grid-cols-1 gap-1 sm:grid-cols-2">{#each KEY_BINDINGS as binding (binding.action)}<li>{binding.text}</li>{/each}</ul>
		</details>
		<RunUnknowns fields={data.layers.unknown_fields} />
	{/if}
</section>
