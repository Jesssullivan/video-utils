<script lang="ts">
	import { Progress } from '@skeletonlabs/skeleton-svelte';
	import ArtifactTable from '$lib/components/ArtifactTable.svelte';
	import ComparePanel from '$lib/components/ComparePanel.svelte';
	import ControlApiError from '$lib/components/ControlApiError.svelte';
	import JobStateBadge from '$lib/components/JobStateBadge.svelte';
	import ProcessForm from '$lib/components/ProcessForm.svelte';
	import UnknownValue from '$lib/components/UnknownValue.svelte';
	import UnknownsBlock from '$lib/components/UnknownsBlock.svelte';
	import { isBffError, type BffError } from '$lib/control-types';
	import { newFormKey } from '$lib/idempotency';
	import { nextPollDecision } from '$lib/polling.js';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	type Snapshot = NonNullable<typeof data.job>;
	// UI state only. Job authority stays in the control API; closing the tab never cancels a job.
	let live = $state<{ jobId: string; job: Snapshot | null; error: BffError | null } | null>(null);
	let pollStatus = $state('waiting');
	let actionError = $state<BffError | null>(null);
	let actionPending = $state(false);
	let adjustKey = $state<string | null>(null);
	let refresh: (() => void) | null = null;

	const current = $derived(live !== null && live.jobId === data.jobId ? live : { jobId: data.jobId, job: data.job, error: data.error });
	const job = $derived(current.job);
	const elapsedSeconds = $derived(job ? Math.max(0, (Date.parse(job.updated_at) - Date.parse(job.created_at)) / 1000) : null);

	$effect(() => {
		const jobId = data.jobId;
		let lastState: string | null = data.job?.state ?? null;
		let consecutiveErrors = data.error ? 1 : 0;
		let lastJob: Snapshot | null = data.job;
		let timer: ReturnType<typeof setTimeout> | undefined;
		let controller: AbortController | null = null;
		let disposed = false;

		const schedule = () => {
			clearTimeout(timer);
			timer = undefined;
			if (disposed) return;
			const decision = nextPollDecision({ lastState, consecutiveErrors, hidden: document.visibilityState === 'hidden' });
			if (decision.action === 'poll') {
				pollStatus = `next check in ${decision.delayMs / 1000} s (${decision.reason})`;
				timer = setTimeout(tick, decision.delayMs);
			} else {
				pollStatus = decision.reason;
			}
		};

		const tick = async () => {
			timer = undefined;
			controller?.abort();
			controller = new AbortController();
			try {
				const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`, { signal: controller.signal, headers: { accept: 'application/json' } });
				const body: unknown = await response.json();
				if (disposed) return;
				if (response.ok && !isBffError(body)) {
					lastJob = body as Snapshot;
					lastState = lastJob.state;
					consecutiveErrors = 0;
					live = { jobId, job: lastJob, error: null };
				} else {
					consecutiveErrors += 1;
					live = { jobId, job: lastJob, error: isBffError(body) ? body : null };
				}
			} catch (cause) {
				if (disposed || (cause instanceof DOMException && cause.name === 'AbortError')) return;
				consecutiveErrors += 1;
			}
			schedule();
		};

		const onVisibility = () => {
			if (document.visibilityState === 'hidden') {
				clearTimeout(timer);
				timer = undefined;
				pollStatus = 'hidden';
			} else if (timer === undefined) {
				schedule();
			}
		};

		refresh = () => {
			consecutiveErrors = 0;
			lastState = null;
			clearTimeout(timer);
			void tick();
		};

		document.addEventListener('visibilitychange', onVisibility);
		schedule();
		return () => {
			disposed = true;
			clearTimeout(timer);
			// Aborts only the outgoing status fetch; never implies job cancellation.
			controller?.abort();
			document.removeEventListener('visibilitychange', onVisibility);
			refresh = null;
		};
	});

	async function act(action: 'cancel' | 'retry') {
		if (actionPending) return;
		actionPending = true;
		actionError = null;
		try {
			const response = await fetch(`/api/jobs/${data.jobId}/${action}`, {
				method: 'POST',
				headers: { 'content-type': 'application/json', accept: 'application/json' },
				body: '{}'
			});
			const body: unknown = await response.json().catch(() => null);
			if (response.ok && body && !isBffError(body)) live = { jobId: data.jobId, job: body as Snapshot, error: null };
			else actionError = isBffError(body) ? body : null;
			refresh?.();
		} finally {
			actionPending = false;
		}
	}
</script>

<section class="space-y-5">
	<div>
		<p class="vu-eyebrow">Job</p>
		<h1 class="h3"><code>{data.jobId}</code></h1>
		<p class="vu-muted text-sm" data-poll-status={pollStatus}>
			Polling: {pollStatus}.
			<button type="button" class="btn btn-sm preset-tonal" onclick={() => refresh?.()}>Refresh</button>
			Closing this tab never cancels the job.
		</p>
	</div>

	{#if current.error}
		<ControlApiError error={current.error} />
	{/if}

	{#if job}
		<dl class="vu-panel card grid grid-cols-1 gap-x-6 gap-y-2 p-5 sm:grid-cols-[13rem_1fr]" data-job-facts="true">
			<dt class="vu-muted">State</dt>
			<dd><JobStateBadge state={job.state} /> {#if job.reason_code}<code class="text-xs">{job.reason_code}</code>{/if}</dd>
			<dt class="vu-muted">Tool</dt>
			<dd><code>{job.tool}</code> <span class="vu-muted text-xs">({job.tool_envelope.evidence_kind}, {job.tool_envelope.implementation_status})</span></dd>
			<dt class="vu-muted">Source</dt>
			<dd><a class="anchor" href={`/sources/${job.source_artifact_id}`}><code>{job.source_artifact_id}</code></a></dd>
			<dt class="vu-muted">Parameters</dt>
			<dd class="vu-time text-sm">{Object.entries(job.parameters).map(([k, v]) => `${k}=${v}`).join(' ')}</dd>
			<dt class="vu-muted">Phase</dt>
			<dd><UnknownValue value={job.phase} reason={job.phase === null ? 'no job event recorded' : null} /> <span class="vu-muted text-xs">— {job.phase_reason}</span></dd>
			<dt class="vu-muted">Progress</dt>
			<dd>
				{#if job.progress}
					<span class="vu-time" data-progress="reported">{job.progress.completed} / {job.progress.denominator} lifecycle steps</span>
					<Progress value={job.progress.completed} max={job.progress.denominator} class="mt-2 max-w-md">
						<Progress.Track><Progress.Range /></Progress.Track>
					</Progress>
				{:else}
					<span class="vu-unknown" data-progress="unknown">Unknown</span>
				{/if}
				<span class="vu-muted block text-xs">{job.progress_reason}</span>
			</dd>
			<dt class="vu-muted">ETA</dt>
			<dd><span class="vu-unknown" data-eta="unknown">Unknown</span> <span class="vu-muted text-xs">— {job.eta_seconds_reason}</span></dd>
			<dt class="vu-muted">Created / updated (UTC)</dt>
			<dd class="vu-time text-sm"><span data-field="created_at">{job.created_at}</span> / <span data-field="updated_at">{job.updated_at}</span></dd>
			<dt class="vu-muted">Elapsed (from row timestamps)</dt>
			<dd><UnknownValue value={elapsedSeconds === null ? null : elapsedSeconds.toFixed(1)} suffix=" s" mono /></dd>
		</dl>

		<div class="flex flex-wrap gap-3" data-job-actions="true">
			{#if job.state === 'queued' || job.state === 'running'}
				<button class="btn preset-tonal-error" type="button" disabled={actionPending} onclick={() => act('cancel')}>Cancel job</button>
			{/if}
			{#if job.state === 'failed' || job.state === 'interrupted'}
				<button class="btn preset-tonal-warning" type="button" disabled={actionPending} onclick={() => act('retry')}>Retry (new attempt)</button>
			{/if}
			<button class="btn preset-tonal" type="button" onclick={() => (adjustKey = newFormKey())}>Adjust settings</button>
		</div>
		{#if actionError}<ControlApiError error={actionError} />{/if}
		{#if adjustKey}
			{#key adjustKey}
				<ProcessForm sourceId={job.source_artifact_id} formKey={adjustKey} initial={job.parameters} heading="Adjust settings (creates a new job; this job and its artifacts are kept)" />
			{/key}
		{/if}

		<ComparePanel {job} />

		<section class="vu-panel card space-y-3 p-5" data-download="true">
			<p class="vu-eyebrow">Download</p>
			<p class="vu-muted text-sm">By artifact ID only; sizes and hashes are from the job record and re-verified when served.</p>
			<ArtifactTable artifacts={job.artifacts} />
		</section>

		<section class="vu-panel card space-y-3 p-5" data-attempts="true">
			<p class="vu-eyebrow">Attempts</p>
			{#each job.attempts as attempt (attempt.attempt)}
				<div class="space-y-1 text-sm" data-attempt={attempt.attempt}>
					<p>
						#{attempt.attempt} <JobStateBadge state={attempt.state} />
						{#if attempt.reason_code}<code>{attempt.reason_code}</code>{/if}
						<span class="vu-muted text-xs">worker {attempt.worker_kind ?? 'not launched'} · liveness <UnknownValue value={attempt.liveness} /> · started <UnknownValue value={attempt.started_at} mono /> · ended <UnknownValue value={attempt.ended_at} mono />{#if attempt.reconciled_publication} · reconciled publication{/if}</span>
					</p>
					{#if attempt.cancel}
						<pre class="vu-time overflow-x-auto text-xs" data-cancel-receipt="true">{JSON.stringify(attempt.cancel, null, 2)}</pre>
					{/if}
					{#if attempt.worker_checks}
						<details><summary class="vu-muted text-xs">worker_checks (structural measurements reported by the worker)</summary>
							<pre class="vu-time overflow-x-auto text-xs" data-worker-checks="true">{JSON.stringify(attempt.worker_checks, null, 2)}</pre>
						</details>
					{/if}
				</div>
			{/each}
		</section>

		<section class="vu-panel card space-y-3 p-5">
			<p class="vu-eyebrow">Unknown and not-claimed</p>
			<UnknownsBlock unknowns={job.unknowns} />
			<details class="text-xs"><summary class="vu-muted">Tool limitations (from the tool envelope, same as CLI/MCP)</summary>
				<ul class="list-inside list-disc">{#each job.tool_envelope.limitations as limitation, index (index)}<li>{limitation}</li>{/each}</ul>
			</details>
		</section>
	{/if}
</section>
