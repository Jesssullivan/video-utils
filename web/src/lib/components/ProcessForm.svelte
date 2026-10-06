<script lang="ts">
	// One form for the one admitted job type (share_export). Knob bounds and defaults come from the
	// tool descriptor mirror (share-export-knobs.json, checked against tool_api by test_web_parity).
	// Only knobs the user sets are sent; the control API is the single validator (novalidate), so
	// out-of-range values come back as typed refusals rather than being silently corrected here.
	import { goto } from '$app/navigation';
	import ControlApiError from './ControlApiError.svelte';
	import { isBffError, type BffError } from '$lib/control-types';
	import knobs from '$lib/share-export-knobs.json';

	interface Props {
		sourceId: string;
		formKey: string;
		initial?: Record<string, string | number> | null;
		heading?: string;
	}
	let { sourceId, formKey, initial = null, heading = 'Process: share preview (share_export)' }: Props = $props();

	type KnobKey = 'height' | 'crf' | 'audio_kbps' | 'codec' | 'timeout_seconds';
	type Knob = { type: string; minimum?: number; maximum?: number; enum?: string[]; default: string | number; description: string };
	const order = knobs.order as KnobKey[];
	const spec = knobs.knobs as unknown as Record<KnobKey, Knob>;

	const initialValues = () =>
		Object.fromEntries(order.map((key) => [key, initial && initial[key] !== undefined ? String(initial[key]) : ''])) as Record<KnobKey, string>;
	let values = $state<Record<KnobKey, string>>(initialValues());
	let pending = $state(false);
	let error = $state<BffError | null>(null);

	function parameters(): Record<string, string | number> {
		const out: Record<string, string | number> = {};
		for (const key of order) {
			const raw = values[key].trim();
			if (raw === '') continue; // unset: the descriptor default applies upstream
			out[key] = spec[key].type === 'integer' ? Number(raw) : raw;
		}
		return out;
	}

	async function submit(event: SubmitEvent) {
		event.preventDefault();
		if (pending) return;
		pending = true;
		error = null;
		try {
			const response = await fetch('/api/jobs', {
				method: 'POST',
				headers: { 'content-type': 'application/json', accept: 'application/json' },
				body: JSON.stringify({ source_artifact_id: sourceId, parameters: parameters(), idempotency_key: formKey })
			});
			const body: unknown = await response.json().catch(() => null);
			if (response.ok && body && !isBffError(body)) {
				await goto(`/jobs/${(body as { job_id: string }).job_id}`);
				return;
			}
			error = isBffError(body) ? body : null;
		} finally {
			pending = false;
		}
	}
</script>

<form class="vu-panel card space-y-4 p-5" novalidate onsubmit={submit} data-process-form="share_export" data-form-key={formKey}>
	<div>
		<p class="vu-eyebrow">Process</p>
		<h2 class="h4">{heading}</h2>
		<p class="vu-muted text-sm">
			Lossy sharing derivative (<code>{knobs.evidence_kind}</code>, {knobs.implementation_status}). Leave a knob blank to
			use the tool default shown. The master is never modified or adopted.
		</p>
	</div>
	<div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
		{#each order as key (key)}
			<label class="label space-y-1">
				<span class="label-text"><code>{key}</code></span>
				{#if spec[key].enum}
					<select class="select" name={key} bind:value={values[key]}>
						<option value="">default ({spec[key].default})</option>
						{#each spec[key].enum ?? [] as option (option)}<option value={option}>{option}</option>{/each}
					</select>
				{:else}
					<input
						class="input"
						type="number"
						name={key}
						inputmode="numeric"
						min={spec[key].minimum}
						max={spec[key].maximum}
						step={key === 'height' ? 2 : 1}
						placeholder={`default ${spec[key].default}`}
						bind:value={values[key]}
					/>
				{/if}
				<span class="vu-muted block text-xs">
					{#if spec[key].minimum !== undefined}{spec[key].minimum}..{spec[key].maximum}{key === 'height' ? ', even' : ''}; {/if}default {spec[key].default}
				</span>
			</label>
		{/each}
	</div>
	<div class="flex items-center gap-3">
		<button class="btn preset-filled-primary-500" type="submit" disabled={pending}>{pending ? 'Submitting…' : 'Submit share preview job'}</button>
		<span class="vu-muted text-xs">Form key <code class="vu-time">{formKey.slice(0, 11)}…</code> — a double submit replays the same job.</span>
	</div>
	{#if error}<ControlApiError {error} />{/if}
</form>
