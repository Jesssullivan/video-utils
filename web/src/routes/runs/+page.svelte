<script lang="ts">
	import ControlApiError from '$lib/components/ControlApiError.svelte';
	import UnknownValue from '$lib/components/UnknownValue.svelte';
	import type { PageProps } from './$types';
	let { data }: PageProps = $props();
</script>

<section class="space-y-4">
	<div>
		<p class="vu-eyebrow">Runs</p>
		<h1 class="h2">Processed runs</h1>
		<p class="vu-muted text-sm">Newest run ID first. The listing reads manifests only and does not re-hash stage files; open a run to re-verify.</p>
	</div>
	{#if data.error}
		<ControlApiError error={data.error} />
	{:else if data.runs && data.runs.length === 0}
		<p class="vu-muted" data-empty="true">No runs with a manifest exist under artifacts/runs.</p>
	{:else if data.runs}
		<div class="table-wrap vu-panel card overflow-x-auto">
			<table class="table">
				<thead><tr><th>Run</th><th>Status</th><th>Original source id</th><th>Stages</th><th>Open</th></tr></thead>
				<tbody>
					{#each data.runs as run (run.run_id)}
						<tr data-run-id={run.run_id}>
							<td><code>{run.run_id}</code></td>
							<td><UnknownValue value={run.run_status} reason={run.manifest_readable ? null : 'manifest unreadable'} /></td>
							<td><UnknownValue value={run.source_id} mono reason={run.source_id === null ? 'manifest records no source sha256' : null} /></td>
							<td class="vu-time"><UnknownValue value={run.stage_count} /></td>
							<td class="space-x-2 whitespace-nowrap">
								<a class="anchor" href={`/runs/${run.run_id}`}>Graph</a>
								<a class="anchor" href={`/runs/${run.run_id}/review`}>Review</a>
								<a class="anchor" href={`/runs/${run.run_id}/compare`}>Compare</a>
								<a class="anchor" href={`/runs/${run.run_id}/deliver`}>Deliver</a>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
		<p class="vu-muted text-xs">{data.runs[0]?.state_basis ?? ''}{data.truncated ? ' · listing truncated at 500 runs' : ''}</p>
	{/if}
</section>
