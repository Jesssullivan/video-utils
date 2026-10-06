<script lang="ts">
	import ControlApiError from '$lib/components/ControlApiError.svelte';
	import UnknownValue from '$lib/components/UnknownValue.svelte';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	const shortHash = (hash: string | null) => (hash === null ? null : `${hash.slice(0, 12)}…`);
	const seconds = (value: number | null) => (value === null ? null : value.toFixed(3));
</script>

<section class="space-y-4">
	<div>
		<p class="vu-eyebrow">Sources</p>
		<h1 class="h2">Registered sources</h1>
		<p class="vu-muted text-sm">
			Listed by the control API. Validation state and media facts are reported by the control
			API, not measured by this page.
		</p>
	</div>

	{#if data.error}
		<ControlApiError error={data.error} />
	{:else if data.sources && data.sources.length === 0}
		<p class="vu-muted" data-empty="true">The control API reports no sources.</p>
	{:else if data.sources}
		<div class="table-wrap vu-panel card overflow-x-auto">
			<table class="table">
				<thead>
					<tr>
						<th>Label</th>
						<th>Source id</th>
						<th>Validation</th>
						<th>SHA-256</th>
						<th>Duration (s)</th>
						<th>Sample rate (Hz)</th>
						<th>Channels</th>
					</tr>
				</thead>
				<tbody>
					{#each data.sources as source (source.source_id)}
						<tr data-source-id={source.source_id}>
							<td>{source.label}</td>
							<td><code>{source.source_id}</code></td>
							<td>{source.validation_state}</td>
							<td title={source.source_sha256 ?? 'Unknown'}><UnknownValue value={shortHash(source.source_sha256)} mono /></td>
							<td><UnknownValue value={seconds(source.duration_seconds)} mono /></td>
							<td><UnknownValue value={source.sample_rate_hz} mono /></td>
							<td><UnknownValue value={source.channels} mono /></td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
</section>
