<script lang="ts">
	import ControlApiError from '$lib/components/ControlApiError.svelte';
	import JobStateBadge from '$lib/components/JobStateBadge.svelte';
	import UnknownValue from '$lib/components/UnknownValue.svelte';
	import type { PageProps } from './$types';
	let { data }: PageProps = $props();
</script>

<section class="space-y-4" data-jobs-page="true">
	<div>
		<p class="vu-eyebrow">Jobs</p>
		<h1 class="h2">All jobs</h1>
		<p class="vu-muted text-sm">Newest first, as listed by the control API. Cancel and retry live on each job page.</p>
	</div>
	{#if data.error}
		<ControlApiError error={data.error} />
	{:else if data.jobs && data.jobs.length === 0}
		<p class="vu-muted" data-empty="true">No jobs have been submitted.</p>
	{:else if data.jobs}
		<div class="table-wrap vu-panel card overflow-x-auto">
			<table class="table text-sm">
				<thead><tr><th>Job</th><th>State</th><th>Tool</th><th>Reason code</th><th>Attempts</th><th>Artifacts</th><th>Created (UTC)</th><th>Updated (UTC)</th></tr></thead>
				<tbody>
					{#each data.jobs as job (job.job_id)}
						<tr data-job-id={job.job_id}>
							<td><a class="anchor" href={`/jobs/${job.job_id}`}><code>{job.job_id.slice(0, 16)}…</code></a></td>
							<td><JobStateBadge state={job.state} /></td>
							<td>{job.tool ?? 'share_export'}</td>
							<td><UnknownValue value={job.reason_code} reason={job.reason_code === null ? 'none recorded' : null} /></td>
							<td class="vu-time">{job.attempt_count}</td>
							<td class="vu-time">{job.artifact_count}</td>
							<td class="vu-time">{job.created_at}</td>
							<td class="vu-time">{job.updated_at}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
		{#if data.truncated}<p class="vu-muted text-xs" data-truncated="true">The upstream list is truncated at 200 jobs.</p>{/if}
	{/if}
</section>
