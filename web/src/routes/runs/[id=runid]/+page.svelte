<script lang="ts">
	// Run graph: stages with signal versions and re-hash state, edges as an ordered list (not a drawing),
	// processing knobs as recorded, evidence attachments, invalidation, listening acceptance and unknowns.
	import ControlApiError from '$lib/components/ControlApiError.svelte';
	import UnknownValue from '$lib/components/UnknownValue.svelte';
	import RunUnknowns from '$lib/components/review/RunUnknowns.svelte';
	import StateBadge from '$lib/components/review/StateBadge.svelte';
	import { bytes } from '$lib/format';
	import { fixed, human, shortSha } from '$lib/components/review/review-logic';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	const graph = $derived(data.graph);
	const processing = $derived(graph?.processing ?? null);
	const flagText = (value: boolean | null, yes: string, no: string, field: string) =>
		value === false ? `${no} (manifest: ${field} false)` : value === true ? `${yes} (manifest: ${field} true)` : `Unknown (manifest records no ${field})`;
</script>

<section class="space-y-5" data-run-graph="true">
	<div>
		<p class="vu-eyebrow">Run graph</p>
		<h1 class="h3 break-all"><code>{data.runId}</code></h1>
	</div>

	{#if data.graphError || !graph}
		{#if data.graphError}<ControlApiError error={data.graphError} />{/if}
	{:else}
		<dl class="vu-panel card grid grid-cols-1 gap-x-6 gap-y-1 p-4 text-sm sm:grid-cols-[14rem_1fr]">
			<dt class="vu-muted">Run status</dt><dd><UnknownValue value={graph.run_status} /></dd>
			<dt class="vu-muted">Manifest SHA-256</dt><dd class="vu-time" title={graph.manifest_sha256}>{shortSha(graph.manifest_sha256)}</dd>
			<dt class="vu-muted">Original source</dt><dd><UnknownValue value={graph.source_id} mono reason={graph.source_id === null ? 'manifest records no source sha256' : null} /></dd>
			<dt class="vu-muted">Native PCM</dt>
			<dd class="vu-time">{graph.pcm.sample_rate ?? 'Unknown'} Hz · {graph.pcm.channels ?? 'Unknown'} ch · {fixed(graph.pcm.duration_seconds, 3)} s</dd>
			<dt class="vu-muted">Timeline</dt>
			<dd>{graph.timeline.axis}; audio start {fixed(graph.timeline.audio_start_seconds)} s; no time stretch: {graph.timeline.no_time_stretch ?? 'Unknown'}</dd>
			<dt class="vu-muted">Admitted web sources</dt>
			<dd>
				{#if graph.admitted_sources_lookup === 'unavailable'}<span class="vu-unknown">Unknown</span> — source lookup unavailable
				{:else if graph.admitted_sources.length === 0}none (run_source_not_admitted)
				{:else}
					{#each graph.admitted_sources as source (source.source_artifact_id)}
						<a class="anchor" href={`/sources/${source.source_artifact_id}`}><code>{source.source_artifact_id.slice(0, 16)}…</code></a>
						<span class="vu-muted text-xs">(annotation clock: {source.has_annotation_clock === null ? 'unknown' : source.has_annotation_clock ? 'yes' : 'no'})</span>
					{/each}
				{/if}
			</dd>
		</dl>

		<section class="vu-panel card space-y-1 p-4 text-sm" data-listening-acceptance={graph.listening_acceptance.value}>
			<h2 class="h5">Listening acceptance</h2>
			<p><StateBadge state={graph.listening_acceptance.value} /> — {graph.listening_acceptance.reason}</p>
			{#if graph.listening_acceptance.scope}<p data-acceptance-scope="true">Scope (verbatim): “{graph.listening_acceptance.scope}”</p>{/if}
			<p class="vu-muted text-xs">Master adopted: no. Applies only to files whose SHA-256 the receipt names ({graph.listening_acceptance.accepted_file_sha256.length}).</p>
		</section>

		<section class="space-y-2">
			<h2 class="h4">Stages</h2>
			<div class="table-wrap vu-panel card overflow-x-auto">
				<table class="table text-sm">
					<thead><tr><th>Stage</th><th>Role</th><th>Signal version</th><th>State</th><th>Size</th></tr></thead>
					<tbody>
						{#each graph.stages as stage (stage.stage)}
							<tr data-stage={stage.stage} data-stage-state={stage.state}>
								<td><code>{stage.stage}</code></td>
								<td>{stage.file_role}<br /><span class="vu-muted text-xs">{stage.role_basis}</span></td>
								<td class="vu-time" title={stage.signal_version ?? 'no recorded hash'}>{stage.signal_version ? shortSha(stage.signal_version) : 'unbound'}</td>
								<td><StateBadge state={stage.state} /></td>
								<td class="vu-time"><UnknownValue value={bytes(stage.size_bytes)} /></td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
			<p class="vu-muted text-xs">current = bytes re-hash to the manifest; stale = bytes differ; missing = no regular file; unbound = no recorded hash.</p>
			<h3 class="h5">Edges</h3>
			<ol class="list-decimal pl-6 text-sm" data-edges="true">
				{#each graph.edges as edge (`${edge.from}->${edge.to}`)}
					<li><code>{edge.from}</code> → <code>{edge.to}</code> <span class="vu-muted text-xs">({edge.edge_basis})</span></li>
				{/each}
			</ol>
		</section>

		{#if processing}
			<section class="vu-panel card space-y-2 p-4 text-sm" data-processing="true">
				<h2 class="h4">Processing as recorded</h2>
				<p data-high-pass={processing.high_pass_applied}>{flagText(processing.high_pass_applied, 'High-pass applied', 'No high-pass', 'high_pass_applied')}</p>
				<p data-hum-notch={processing.hum_notches_applied}>{flagText(processing.hum_notches_applied, 'Hum notch applied', 'No hum notch', 'hum_notches_applied')}</p>
				<p>Intentional low fundamental: <UnknownValue value={processing.intentional_low_fundamental_hz} suffix=" Hz" /></p>
				<p>Profile: <UnknownValue value={processing.profile_name} mono /></p>
				<p>Denoise: <UnknownValue value={processing.denoise.filter} /> · delay <UnknownValue value={processing.denoise.delay_samples} suffix=" samples" /> · <UnknownValue value={processing.denoise.status} /></p>
				<p>Peaking EQ:
					{#if processing.tone.peaking_eq.length === 0}none recorded{/if}
					{#each processing.tone.peaking_eq as band, index (index)}
						<span class="vu-time">{fixed(band.frequency_hz, 0)} Hz {fixed(band.gain_db, 1)} dB Q {fixed(band.q, 2)}</span>{index < processing.tone.peaking_eq.length - 1 ? '; ' : ''}
					{/each}
				</p>
				<p>Compressor:
					{#if processing.tone.compressor}
						{#each Object.entries(processing.tone.compressor) as [key, value] (key)}<span class="vu-time">{human(key)} {value ?? 'unknown'}</span>; {/each}
					{:else}<span class="vu-unknown">Unknown</span>{/if}
				</p>
				<p>Loudness targets:
					{#each Object.entries(processing.loudness_targets) as [stage, targets] (stage)}
						<span class="vu-time">{stage}: {Object.entries(targets).map(([k, v]) => `${human(k)} ${v ?? 'unknown'}`).join(', ')}</span>;
					{/each}
				</p>
				<p>Noise capture interval: {processing.noise_capture.selected_seconds ? processing.noise_capture.selected_seconds.map((v) => fixed(v, 2)).join('–') + ' s' : 'Unknown'}</p>
				{#if processing.noise_capture.review}<p class="vu-muted text-xs">Capture review (verbatim): {processing.noise_capture.review}</p>{/if}
				<p class="vu-muted text-xs">DSP latency status: {Object.entries(processing.dsp_latency_status).map(([k, v]) => `${k} ${v ?? 'unknown'}`).join(' · ')}. Manifest listening_accepted field: {processing.manifest_listening_accepted_field ?? 'unknown'}.</p>
			</section>
		{/if}

		<section class="space-y-2" data-evidence="true">
			<h2 class="h4">Evidence attachments</h2>
			{#if graph.discovery_truncated}<p class="vu-error text-sm">Evidence discovery was truncated at its entry bound; some attachments may be missing.</p>{/if}
			{#if graph.evidence.length === 0}
				<p class="vu-muted text-sm">No evidence attachment under artifacts/s2, s3 or experiments binds to this run.</p>
			{:else}
				<ul class="space-y-1 text-sm">
					{#each graph.evidence as item (item.evidence_id)}
						<li data-evidence-id={item.evidence_id} data-evidence-state={item.state}>
							<code>{item.evidence_id}</code> · {human(item.kind)} · <StateBadge state={item.state} />
							{#if item.reason}<span class="vu-muted"> ({human(item.reason)})</span>{/if}
							{#if item.generated_utc}<span class="vu-muted text-xs"> · generated {item.generated_utc}</span>{/if}
							<span class="vu-muted text-xs"> · bound to {shortSha(item.bound_signal_version)}</span>
						</li>
					{/each}
				</ul>
			{/if}
			<h3 class="h5">Invalidation</h3>
			{#if graph.invalidation.length === 0}
				<p class="vu-muted text-sm" data-invalidation-empty="true">No bound attachment was invalidated by a changed input.</p>
			{:else}
				<ul class="space-y-1 text-sm" data-invalidation="true">
					{#each graph.invalidation as item (item.evidence_id)}
						<li><code>{item.evidence_id}</code>: {human(item.reason)} — was bound to {shortSha(item.was_bound_to)}, now {shortSha(item.now)}. Not drawn on any overlay.</li>
					{/each}
				</ul>
			{/if}
		</section>

		<p class="vu-muted text-xs">Claim boundary: musical verdict {graph.claim_boundary.musical_verdict}; note-level comparison {human(graph.claim_boundary.missed_or_extra_notes)}; default adopted: no; master changed: no.</p>
		<RunUnknowns fields={graph.unknown_fields} />
	{/if}
</section>
