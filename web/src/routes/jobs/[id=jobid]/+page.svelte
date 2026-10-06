<script lang="ts">
	import { Progress } from '@skeletonlabs/skeleton-svelte';
	import ControlApiError from '$lib/components/ControlApiError.svelte';
	import JobStateBadge from '$lib/components/JobStateBadge.svelte';
	import UnknownValue from '$lib/components/UnknownValue.svelte';
	import type { BffError } from '$lib/control-types';
	import { nextPollDecision } from '$lib/polling.js';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	type Snapshot = NonNullable<typeof data.job>;
	// UI state only. Job authority stays in the control API; this page never mutates a job.
	let live = $state<{ jobId: string; job: Snapshot | null; error: BffError | null } | null>(null);
	let pollStatus = $state('waiting');
	let refresh: (() => void) | null = null;

	const current = $derived(live !== null && live.jobId === data.jobId ? live : { jobId: data.jobId, job: data.job, error: data.error });
	const job = $derived(current.job);
	const elapsedSeconds = $derived(
		job ? Math.max(0, (Date.parse(job.updated_utc) - Date.parse(job.created_utc)) / 1000) : null
	);

	function isBffError(value: unknown): value is BffError {
		return typeof value === 'object' && value !== null && (value as { status?: unknown }).status === 'error' && typeof (value as { code?: unknown }).code === 'string';
	}

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
			const decision = nextPollDecision({
				lastState,
				consecutiveErrors,
				hidden: document.visibilityState === 'hidden'
			});
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
				const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`, {
					signal: controller.signal,
					headers: { accept: 'application/json' }
				});
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
</script>

<section class="space-y-4">
	<div>
		<p class="vu-eyebrow">Job status</p>
		<h1 class="h2"><code>{data.jobId}</code></h1>
		<p class="vu-muted text-sm" data-poll-status={pollStatus}>
			Polling: {pollStatus}.
			<button type="button" class="btn btn-sm preset-tonal" onclick={() => refresh?.()}>Refresh</button>
		</p>
	</div>

	{#if current.error}
		<ControlApiError error={current.error} />
	{/if}

	{#if job}
		<dl class="vu-panel card grid grid-cols-1 gap-x-6 gap-y-2 p-5 sm:grid-cols-[12rem_1fr]">
			<dt class="vu-muted">State</dt>
			<dd><JobStateBadge state={job.state} /></dd>
			<dt class="vu-muted">Tool</dt>
			<dd><code>{job.tool}</code></dd>
			<dt class="vu-muted">Phase</dt>
			<dd><UnknownValue value={job.phase} /></dd>
			<dt class="vu-muted">Source id</dt>
			<dd><UnknownValue value={job.source_id} mono /></dd>
			<dt class="vu-muted">Created (UTC)</dt>
			<dd class="vu-time" data-field="created_utc">{job.created_utc}</dd>
			<dt class="vu-muted">Updated (UTC)</dt>
			<dd class="vu-time" data-field="updated_utc">{job.updated_utc}</dd>
			<dt class="vu-muted">Elapsed (from snapshot timestamps)</dt>
			<dd><UnknownValue value={elapsedSeconds === null ? null : elapsedSeconds.toFixed(1)} suffix=" s" mono /></dd>
			<dt class="vu-muted">Progress</dt>
			<dd>
				{#if job.progress}
					<span class="vu-time" data-progress="reported">{job.progress.completed} / {job.progress.denominator} {job.progress.unit}</span>
					<Progress value={job.progress.completed} max={job.progress.denominator} class="mt-2 max-w-md">
						<Progress.Track>
							<Progress.Range />
						</Progress.Track>
					</Progress>
				{:else}
					<span class="vu-unknown" data-progress="unknown">Unknown</span>
					<span class="vu-muted text-xs">(no denominator reported; no fraction is shown)</span>
				{/if}
			</dd>
			<dt class="vu-muted">ETA</dt>
			<dd>
				{#if job.eta_seconds !== null}
					<span class="vu-time">{job.eta_seconds.toFixed(0)} s</span> <span class="vu-muted text-xs">(estimate)</span>
				{:else}
					<span class="vu-unknown">Unknown</span>
				{/if}
			</dd>
			<dt class="vu-muted">Error class</dt>
			<dd><UnknownValue value={job.error_class} /></dd>
			<dt class="vu-muted">Limitations</dt>
			<dd>
				{#if job.limitations.length === 0}
					<span class="vu-muted">None reported</span>
				{:else}
					<ul class="list-inside list-disc">
						{#each job.limitations as limitation, index (index)}<li>{limitation}</li>{/each}
					</ul>
				{/if}
			</dd>
		</dl>
	{/if}
</section>
