<script lang="ts">
	import { bytes, shortHash } from '$lib/format';
	import type { JobArtifact } from '$lib/schema/control';
	interface Props {
		artifacts: readonly JobArtifact[];
	}
	let { artifacts }: Props = $props();
</script>

{#if artifacts.length === 0}
	<p class="vu-muted text-sm" data-artifacts="none">No published artifacts for this job.</p>
{:else}
	<div class="table-wrap overflow-x-auto">
		<table class="table text-sm">
			<thead><tr><th>Role</th><th>Attempt</th><th>SHA-256</th><th>Size</th><th>Download</th></tr></thead>
			<tbody>
				{#each artifacts as artifact (artifact.artifact_id)}
					<tr data-artifact-id={artifact.artifact_id} data-role={artifact.role}>
						<td><code>{artifact.role}</code></td>
						<td class="vu-time">{artifact.attempt}</td>
						<td class="vu-time" title={artifact.sha256}>{shortHash(artifact.sha256)}</td>
						<td class="vu-time">{bytes(artifact.size_bytes)}</td>
						<td>
							{#if artifact.downloadable}
								<a class="anchor" href={`/api/artifacts/${artifact.artifact_id}`} download data-download={artifact.artifact_id}>Download</a>
							{:else if artifact.role === 'share_receipt'}
								<span class="vu-muted" data-private="true">private (contains host paths)</span>
							{:else}
								<span class="vu-muted">not served</span>
							{/if}
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
{/if}
