<script lang="ts">
	import ControlApiError from '$lib/components/ControlApiError.svelte';
	import UnknownValue from '$lib/components/UnknownValue.svelte';
	import { bytes, seconds, shortHash } from '$lib/format';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
</script>

<section class="space-y-4">
	<div>
		<p class="vu-eyebrow">Sources</p>
		<h1 class="h2">Admitted sources</h1>
		<p class="vu-muted text-sm">
			Listed by the control API without re-hashing (submit and media re-verify). Media facts are reported by the
			control API, not measured by this page. <a class="anchor" href="/upload">Upload or admit a source</a>.
		</p>
	</div>

	<aside class="vu-panel card space-y-1 p-4 text-sm" data-runs-entry="true">
		<p class="vu-eyebrow">Runs</p>
		<p>
			Processed takes live in <a class="anchor" href="/runs">Runs</a>: each run has a graph (stages, signal versions,
			evidence), matched-level compare, review (phrase/BPM overlays, triaged flags, Mark here) and deliver pages.
		</p>
	</aside>

	{#if data.error}
		<ControlApiError error={data.error} />
	{:else if data.sources && data.sources.length === 0}
		<p class="vu-muted" data-empty="true">No sources are admitted yet. Start with <a class="anchor" href="/upload">Upload / admit</a>.</p>
	{:else if data.sources}
		<div class="table-wrap vu-panel card overflow-x-auto">
			<table class="table">
				<thead>
					<tr><th>Source</th><th>Origin</th><th>Original source id</th><th>SHA-256</th><th>Size</th><th>Duration (s)</th><th>Admitted (UTC)</th></tr>
				</thead>
				<tbody>
					{#each data.sources as source (source.source_artifact_id)}
						<tr data-source-artifact-id={source.source_artifact_id}>
							<td><a class="anchor" href={`/sources/${source.source_artifact_id}`}><code>{source.source_artifact_id}</code></a></td>
							<td>{source.origin}</td>
							<td><UnknownValue value={source.source_id} mono reason={source.source_id === null ? source.source_id_reason : null} /></td>
							<td class="vu-time" title={source.sha256}>{shortHash(source.sha256)}</td>
							<td class="vu-time">{bytes(source.size_bytes)}</td>
							<td><UnknownValue value={seconds(source.duration_seconds)} mono reason={source.duration_seconds === null ? source.duration_seconds_reason : null} /></td>
							<td class="vu-time">{source.admitted_at}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
		{#if data.truncated}<p class="vu-muted text-xs">Listing truncated at 500 sources.</p>{/if}
	{/if}
</section>
