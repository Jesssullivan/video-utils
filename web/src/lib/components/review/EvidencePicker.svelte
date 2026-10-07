<script lang="ts">
	// Selected practice bundle and its current alternatives (newest generated_utc wins; ties -> lowest ID).
	interface Props {
		runId: string;
		path: 'compare' | 'review';
		selected: string | null;
		alternatives: readonly string[];
		generated: string | null;
	}
	let { runId, path, selected, alternatives, generated }: Props = $props();
</script>

<div class="vu-muted text-xs" data-evidence-picker="true">
	{#if selected}
		Bound practice bundle <code>{selected}</code>{generated ? ` (generated ${generated})` : ''}.
		{#if alternatives.length}
			Current alternatives:
			{#each alternatives as id (id)}<a class="anchor" href={`/runs/${runId}/${path}?evidence=${id}`}><code>{id}</code></a> {/each}
			{#if selected}· <a class="anchor" href={`/runs/${runId}/${path}`}>default selection</a>{/if}
		{/if}
	{:else}
		No current practice bundle is bound to this run; layers that need it are unavailable.
	{/if}
</div>
