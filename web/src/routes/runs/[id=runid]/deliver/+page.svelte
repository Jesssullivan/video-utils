<script lang="ts">
	// Delivery: restored video, delivery WAV, share MP4s, marked compact movie and marker files, each by artifact
	// or evidence ID through the BFF pass-through. The accepted-listening label appears only on the exact files the
	// pinned receipt names. FCPXML and Resolve files are labelled import unverified.
	import ControlApiError from '$lib/components/ControlApiError.svelte';
	import { bytes } from '$lib/format';
	import { bareSha, shortSha } from '$lib/components/review/review-logic';
	import { runArtifactUrl } from '$lib/components/review/media';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	const graph = $derived(data.graph);
	const accepted = $derived(new Set(graph?.listening_acceptance.accepted_file_sha256 ?? []));
	const videos = $derived((graph?.stages ?? []).filter((stage) => stage.stage.startsWith('export/')));
	const wav = $derived((graph?.stages ?? []).find((stage) => stage.stage === 'cleaned.wav') ?? null);
	const markers = $derived((graph?.evidence ?? []).filter((item) => item.kind === 'editor_marker_export' && item.state === 'current'));
	const compact = $derived((graph?.evidence ?? []).filter((item) => item.kind === 'marked_compact' && item.state === 'current'));
	const IMPORT = 'import unverified (no editor application proof)';
	const acceptedLabel = (sha: string | null) => (sha && accepted.has(sha) ? 'listening accepted (exact file named by the pinned receipt; scope below)' : null);
</script>

<section class="space-y-4" data-deliver-page="true">
	<div>
		<p class="vu-eyebrow">Deliver</p>
		<h1 class="h3 break-all">Run <code>{data.runId}</code></h1>
		<p class="vu-muted text-sm">Every download goes through the BFF by ID and is re-hashed before sending. Nothing here adopts a master.</p>
	</div>
	{#if data.graphError || !graph}
		{#if data.graphError}<ControlApiError error={data.graphError} />{/if}
	{:else}
		{#if graph.listening_acceptance.scope}<p class="vu-panel card p-3 text-sm" data-acceptance-scope="true">Listening acceptance scope (verbatim): “{graph.listening_acceptance.scope}”</p>{/if}
		<div class="table-wrap vu-panel card overflow-x-auto">
			<table class="table text-sm" data-deliverables="true">
				<thead><tr><th>Item</th><th>ID</th><th>SHA-256</th><th>Size</th><th>Download</th></tr></thead>
				<tbody>
					{#each videos as stage (stage.stage)}
						<tr data-deliverable="restored-video">
							<td>Restored video <code>{stage.stage}</code> · {stage.state}{#if acceptedLabel(bareSha(stage.signal_version))}<br /><span class="text-xs">{acceptedLabel(bareSha(stage.signal_version))}</span>{/if}</td>
							<td><code>{stage.artifact_id ?? 'none'}</code></td>
							<td class="vu-time" title={stage.signal_version ?? ''}>{shortSha(stage.signal_version)}</td>
							<td class="vu-time">{bytes(stage.size_bytes) ?? 'Unknown'}</td>
							<td>{#if stage.artifact_id && stage.state !== 'missing'}<a class="anchor" href={runArtifactUrl(data.runId, stage.artifact_id)} download>Download</a>{:else}not available{/if}</td>
						</tr>
					{/each}
					{#if wav}
						<tr data-deliverable="delivery-wav">
							<td>Delivery WAV <code>cleaned.wav</code> · native {graph.pcm.sample_rate ?? 'unknown'} Hz, {graph.pcm.channels ?? 'unknown'} ch · {wav.state}{#if acceptedLabel(bareSha(wav.signal_version))}<br /><span class="text-xs">{acceptedLabel(bareSha(wav.signal_version))}</span>{/if}</td>
							<td><code>{wav.artifact_id ?? 'none'}</code></td>
							<td class="vu-time" title={wav.signal_version ?? ''}>{shortSha(wav.signal_version)}</td>
							<td class="vu-time">{bytes(wav.size_bytes) ?? 'Unknown'}</td>
							<td>{#if wav.artifact_id && wav.state === 'current'}<a class="anchor" href={runArtifactUrl(data.runId, wav.artifact_id)} download>Download</a>{:else}not available ({wav.state}){/if}</td>
						</tr>
					{/if}
					{#each data.shares as share (share.artifact_id)}
						<tr data-deliverable="share-mp4">
							<td>Share MP4 (job <a class="anchor" href={`/jobs/${share.job_id}`}><code>{share.job_id.slice(0, 12)}…</code></a>) · lossy sharing derivative; low-register preservation not claimed</td>
							<td><code>{share.artifact_id}</code></td>
							<td class="vu-time" title={share.sha256}>{shortSha(share.sha256)}</td>
							<td class="vu-time">{bytes(share.size_bytes)}</td>
							<td><a class="anchor" href={`/api/artifacts/${share.artifact_id}`} download>Download</a></td>
						</tr>
					{/each}
					{#each compact as item (item.evidence_id)}
						{#each item.files as file (file.artifact_id)}
							<tr data-deliverable="marked-compact">
								<td>{file.role} · evidence <code>{item.evidence_id.slice(0, 12)}…</code></td>
								<td><code>{file.artifact_id}</code></td>
								<td class="vu-time" title={file.sha256}>{shortSha(file.sha256)}</td>
								<td class="vu-time">{bytes(file.size_bytes) ?? 'Unknown'}</td>
								<td><a class="anchor" href={runArtifactUrl(data.runId, file.artifact_id)} download>Download</a></td>
							</tr>
						{/each}
					{/each}
					{#each markers as item (item.evidence_id)}
						{#each item.files as file (file.artifact_id)}
							<tr data-deliverable="marker-file" data-import-verified={file.import_verified === false ? 'false' : 'n/a'}>
								<td>{file.role} <code>{file.name}</code>{#if file.import_verified === false}<br /><span class="text-xs" data-import-unverified="true">{IMPORT}</span>{/if}</td>
								<td><code>{file.artifact_id}</code></td>
								<td class="vu-time" title={file.sha256}>{shortSha(file.sha256)}</td>
								<td class="vu-time">{bytes(file.size_bytes) ?? 'Unknown'}</td>
								<td><a class="anchor" href={runArtifactUrl(data.runId, file.artifact_id)} download>Download</a>{#if file.import_verified === false} <span class="vu-muted text-xs">({IMPORT})</span>{/if}</td>
							</tr>
						{/each}
					{/each}
				</tbody>
			</table>
		</div>
		{#if markers.length === 0}<p class="text-sm" data-markers-none="true">Marker files: not exported or calibration_required. No marker download is offered.</p>{/if}
		{#if compact.length === 0}<p class="vu-muted text-sm">Marked compact movie: none bound to this run's current delivery master.</p>{/if}
		{#if data.shares.length === 0}<p class="vu-muted text-sm">Share MP4: no succeeded share_export job for an admitted source of this run.</p>{/if}
		{#if data.shareError}<ControlApiError error={data.shareError} />{/if}
		<p class="vu-muted text-xs">FCPXML and Resolve marker files are previews of an unverified editor contract: {IMPORT}. A share MP4 is a lossy AAC derivative; ~32 Hz preservation in it is not claimed.</p>
	{/if}
</section>
