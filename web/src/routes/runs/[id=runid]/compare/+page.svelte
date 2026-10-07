<script lang="ts">
	import ControlApiError from '$lib/components/ControlApiError.svelte';
	import ABCompare from '$lib/components/review/ABCompare.svelte';
	import EvidencePicker from '$lib/components/review/EvidencePicker.svelte';
	import type { PageProps } from './$types';
	let { data }: PageProps = $props();
</script>

<section class="space-y-4" data-compare-page="true">
	<div>
		<p class="vu-eyebrow">Compare · matched presentation level</p>
		<h1 class="h3 break-all">Run <code>{data.runId}</code></h1>
		<p class="vu-muted text-sm">Source, pure denoise, FULLER delivery master and unreviewed trials, cut and level-matched by tone_ab. Listening acceptance is a separate state; nothing here records a preference.</p>
	</div>
	{#if data.layersError}
		<ControlApiError error={data.layersError} />
		<p class="text-sm">Open the <a class="anchor" href={`/runs/${data.runId}`}>run graph</a> for bound evidence.</p>
	{:else if data.layers}
		<EvidencePicker runId={data.runId} path="compare" selected={data.layers.selected_evidence_id} alternatives={data.layers.alternatives} generated={data.layers.selected_generated_utc} />
		<ABCompare runId={data.runId} layer={data.layers.layers.tone_ab} media={data.layers.media} browserLevelMatch={data.layers.unknown_fields.browser_level_match} />
	{/if}
</section>
