<script lang="ts">
	// Run picker: choose the run whose compare page to open.
	import ControlApiError from '$lib/components/ControlApiError.svelte';
	import type { PageProps } from './$types';
	let { data }: PageProps = $props();
</script>

<section class="space-y-4" data-run-picker="compare">
	<div>
		<p class="vu-eyebrow">Compare at matched presentation level</p>
		<h1 class="h3">Choose a run</h1>
	</div>
	{#if data.error}
		<ControlApiError error={data.error} />
	{:else if data.runs && data.runs.length === 0}
		<p class="vu-muted" data-empty="true">No runs with a manifest exist yet. Admit a clip and process it first.</p>
	{:else if data.runs}
		<ul class="space-y-1 text-sm">
			{#each data.runs as run (run.run_id)}
				<li><a class="anchor" href={`/runs/${run.run_id}/compare`}><code>{run.run_id}</code></a> <span class="vu-muted text-xs">{run.run_status ?? 'status unknown'}</span></li>
			{/each}
		</ul>
		{#if data.truncated}<p class="vu-muted text-xs">Listing truncated at 500 runs.</p>{/if}
	{/if}
</section>
