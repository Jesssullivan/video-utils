<script lang="ts">
	import AnnotationPanel from '$lib/components/AnnotationPanel.svelte';
	import ArtifactTable from '$lib/components/ArtifactTable.svelte';
	import ControlApiError from '$lib/components/ControlApiError.svelte';
	import JobStateBadge from '$lib/components/JobStateBadge.svelte';
	import ProcessForm from '$lib/components/ProcessForm.svelte';
	import UnknownValue from '$lib/components/UnknownValue.svelte';
	import { bytes, seconds, shortHash } from '$lib/format';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	const params = (p: Record<string, unknown>) => Object.entries(p).map(([k, v]) => `${k}=${typeof v === 'object' ? 'set' : v}`).join(' ');
	const baselines = $derived((data.runs?.runs ?? []).filter((run) => run.role === 'baseline'));
	const probe = $derived(baselines[0]?.pcm ?? null);
	const num = (value: unknown): number | null => (typeof value === 'number' && Number.isFinite(value) ? value : null);
	const probeReason = 'unknown until a bound run manifest or worker proof exists; admission does not probe';
</script>

<section class="space-y-6">
	<div>
		<p class="vu-eyebrow">Source</p>
		<h1 class="h3"><code>{data.sourceId}</code></h1>
		<nav class="mt-3 flex flex-wrap gap-2 text-sm" aria-label="Source steps" data-source-steps="true">
			<a class="btn btn-sm preset-tonal" href={`/sources/${data.sourceId}/capture`}>1 · Capture review</a>
			<a class="btn btn-sm preset-tonal" href={`/sources/${data.sourceId}/process`}>2 · Process</a>
		</nav>
	</div>

	{#if data.error}
		<ControlApiError error={data.error} />
	{:else if data.source}
		<dl class="vu-panel card grid grid-cols-1 gap-x-6 gap-y-1 p-5 text-sm sm:grid-cols-[14rem_1fr]" data-source-facts="true">
			<dt class="vu-muted">Origin</dt><dd>{data.source.origin}</dd>
			<dt class="vu-muted">SHA-256 (admission)</dt><dd class="vu-time" title={data.source.sha256}>{shortHash(data.source.sha256)}</dd>
			<dt class="vu-muted">Size</dt><dd class="vu-time">{bytes(data.source.size_bytes)}</dd>
			<dt class="vu-muted">Original source id</dt><dd><UnknownValue value={data.source.source_id} mono reason={data.source.source_id === null ? data.source.source_id_reason : null} /></dd>
			<dt class="vu-muted">Share-preview extent (s)</dt><dd><UnknownValue value={seconds(data.source.duration_seconds)} mono reason={data.source.duration_seconds_reason} /></dd>
			<dt class="vu-muted">State</dt><dd>{data.source.state} <span class="vu-muted text-xs">— {data.source.state_reason}</span></dd>
		</dl>

		<section class="vu-panel card space-y-2 p-5 text-sm" data-probe-summary="true">
			<p class="vu-eyebrow">Probe summary (from bound run manifests only)</p>
			<dl class="grid grid-cols-1 gap-x-6 gap-y-1 sm:grid-cols-[14rem_1fr]">
				<dt class="vu-muted">Decoded duration (s)</dt><dd><UnknownValue value={seconds(num(probe?.duration_seconds))} mono reason={probe ? null : probeReason} /></dd>
				<dt class="vu-muted">Sample rate (Hz)</dt><dd><UnknownValue value={num(probe?.sample_rate)} mono reason={probe ? null : probeReason} /></dd>
				<dt class="vu-muted">Channels</dt><dd><UnknownValue value={num(probe?.channels)} mono reason={probe ? null : probeReason} /></dd>
			</dl>
			{#if baselines.length > 1}<p class="vu-muted text-xs">{baselines.length} baseline runs are bound; values shown from the first listed.</p>{/if}
		</section>

		<section class="space-y-3" data-bound-runs="true">
			<div><p class="vu-eyebrow">Bound runs</p><h2 class="h4">Runs whose manifest names this source sha256</h2></div>
			{#if data.runsError}
				<ControlApiError error={data.runsError} />
			{:else if data.runs && data.runs.runs.length === 0}
				<p class="vu-muted" data-runs-empty="true">No run is bound to this source yet. A denoise job (for example the explicit <code>bypass</code> profile) creates a baseline run.</p>
			{:else if data.runs}
				<div class="overflow-x-auto">
					<table class="table text-sm">
						<thead><tr><th>Run</th><th>Kind</th><th>Profile</th><th>Status</th><th>Capture baseline</th></tr></thead>
						<tbody>
							{#each data.runs.runs as run (run.run_id)}
								<tr data-run={run.run_id}>
									<td><code>{run.run_id}</code></td><td>{run.role}</td>
									<td><UnknownValue value={run.profile_name} /></td><td><UnknownValue value={run.status} /></td>
									<td>{run.baseline_eligible ? 'eligible' : 'not eligible'} <span class="vu-muted text-xs">— {run.baseline_eligibility_reason}</span></td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/if}
		</section>

		<section class="space-y-3" data-capture-reviews="true">
			<div><p class="vu-eyebrow">Capture reviews</p><h2 class="h4">Operator review records (immutable)</h2></div>
			{#if data.reviewsError}
				<ControlApiError error={data.reviewsError} />
			{:else if data.reviews && data.reviews.reviews.length === 0}
				<p class="vu-muted">No capture review saved. Nothing is created automatically.</p>
			{:else if data.reviews}
				<ul class="space-y-1 text-sm">
					{#each data.reviews.reviews as review (review.review_id)}
						<li data-review={review.review_id}>
							<code>{review.review_id}</code> · <span class="vu-time">{review.interval.start_seconds.toFixed(3)}–{review.interval.end_seconds.toFixed(3)} s</span>
							· {review.review_status} · {review.authorization_scope} · music {review.music_status} · clicks {review.click_status} · ambient {review.ambient_music_status}
							{#if review.overlaps_setup_interval}<strong> · overlaps first 5 s</strong>{/if}
						</li>
					{/each}
				</ul>
			{/if}
		</section>

		<ProcessForm sourceId={data.sourceId} formKey={data.formKey} />

		<AnnotationPanel sourceId={data.sourceId} store={data.annotations?.store ?? null} clock={data.annotations?.clock ?? null} error={data.annotationError} />

		<section class="space-y-3" data-iterate="true">
			<div>
				<p class="vu-eyebrow">Iterate</p>
				<h2 class="h4">Jobs for this source</h2>
				<p class="vu-muted text-sm">Every job stays listed; earlier artifacts are never replaced by a new run.</p>
			</div>
			{#if data.jobsError}
				<ControlApiError error={data.jobsError} />
			{:else if data.jobs && data.jobs.jobs.length === 0}
				<p class="vu-muted" data-jobs-empty="true">No jobs yet for this source.</p>
			{:else if data.jobs}
				{#each data.jobs.jobs as job (job.job_id)}
					{@const projection = data.projections[job.job_id]}
					<article class="vu-panel card space-y-2 p-4" data-job-row={job.job_id} data-job-tool={job.tool ?? 'share_export'}>
						<p class="flex flex-wrap items-center gap-3">
							<a class="anchor" href={`/jobs/${job.job_id}`}><code>{job.job_id}</code></a>
							<code>{job.tool ?? 'share_export'}</code>
							<JobStateBadge state={job.state} />
							{#if projection?.lane}<span class="vu-muted text-xs">phase <code>{projection.lane.phase ?? 'unknown'}</code></span>{/if}
							<span class="vu-time text-xs">{params(job.parameters)}</span>
							<span class="vu-muted text-xs">created {job.created_at} · attempts {job.attempt_count}</span>
						</p>
						{#if projection?.share}
							<ArtifactTable artifacts={projection.share.artifacts ?? []} />
						{:else if projection?.lane}
							<p class="vu-muted text-xs">
								{#if projection.lane.run_id}run <code>{projection.lane.run_id}</code> · {/if}
								{(projection.lane.outputs ?? []).length} output(s) · worker status <UnknownValue value={projection.lane.worker_status ?? null} />
								· master adopted: false · listening acceptance: not performed
							</p>
						{:else if projection?.error}
							<ControlApiError error={projection.error} />
						{:else}
							<p class="vu-muted text-xs">{job.artifact_count} artifact(s); open the job for details.</p>
						{/if}
					</article>
				{/each}
				{#if data.jobs.truncated}<p class="vu-muted text-xs">Listing truncated at 200 jobs.</p>{/if}
			{/if}
		</section>
	{/if}
</section>
