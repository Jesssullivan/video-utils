<script lang="ts">
	import AnnotationPanel from '$lib/components/AnnotationPanel.svelte';
	import ArtifactTable from '$lib/components/ArtifactTable.svelte';
	import ControlApiError from '$lib/components/ControlApiError.svelte';
	import JobStateBadge from '$lib/components/JobStateBadge.svelte';
	import ProcessForm from '$lib/components/ProcessForm.svelte';
	import UnknownValue from '$lib/components/UnknownValue.svelte';
	import { bytes, seconds } from '$lib/format';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	const params = (p: Record<string, string | number>) => Object.entries(p).map(([k, v]) => `${k}=${v}`).join(' ');
</script>

<section class="space-y-6">
	<div>
		<p class="vu-eyebrow">Source</p>
		<h1 class="h3"><code>{data.sourceId}</code></h1>
	</div>

	{#if data.error}
		<ControlApiError error={data.error} />
	{:else if data.source}
		<dl class="vu-panel card grid grid-cols-1 gap-x-6 gap-y-1 p-5 text-sm sm:grid-cols-[14rem_1fr]" data-source-facts="true">
			<dt class="vu-muted">Origin</dt><dd>{data.source.origin}</dd>
			<dt class="vu-muted">SHA-256 (admission)</dt><dd class="vu-time">{data.source.sha256}</dd>
			<dt class="vu-muted">Size</dt><dd class="vu-time">{bytes(data.source.size_bytes)}</dd>
			<dt class="vu-muted">Original source id</dt><dd><UnknownValue value={data.source.source_id} mono reason={data.source.source_id === null ? data.source.source_id_reason : null} /></dd>
			<dt class="vu-muted">Duration (s)</dt><dd><UnknownValue value={seconds(data.source.duration_seconds)} mono reason={data.source.duration_seconds_reason} /></dd>
			<dt class="vu-muted">State</dt><dd>{data.source.state} <span class="vu-muted text-xs">— {data.source.state_reason}</span></dd>
		</dl>

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
					<article class="vu-panel card space-y-2 p-4" data-job-row={job.job_id}>
						<p class="flex flex-wrap items-center gap-3">
							<a class="anchor" href={`/jobs/${job.job_id}`}><code>{job.job_id}</code></a>
							<JobStateBadge state={job.state} />
							<span class="vu-time text-xs">{params(job.parameters)}</span>
							<span class="vu-muted text-xs">created {job.created_at} · attempts {job.attempt_count}</span>
						</p>
						{#if data.projections[job.job_id]?.job}
							<ArtifactTable artifacts={data.projections[job.job_id].job?.artifacts ?? []} />
						{:else if data.projections[job.job_id]?.error}
							<ControlApiError error={data.projections[job.job_id].error!} />
						{:else}
							<p class="vu-muted text-xs">{job.artifact_count} artifact(s); open the job for downloads.</p>
						{/if}
					</article>
				{/each}
				{#if data.jobs.truncated}<p class="vu-muted text-xs">Listing truncated at 200 jobs.</p>{/if}
			{/if}
		</section>
	{/if}
</section>
