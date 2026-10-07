<script lang="ts">
	// A typed refusal from the control API (or a local form check) with the lane's explanation.
	import ControlApiError from '$lib/components/ControlApiError.svelte';
	import { displayCode, type BffError } from '$lib/control-types';
	import { processingText } from './processing-text';

	interface Props {
		error?: BffError | null;
		local?: { code: string; message: string } | null;
	}
	let { error = null, local = null }: Props = $props();
	const code = $derived(error ? displayCode(error) : (local?.code ?? ''));
</script>

{#if error}
	<div class="space-y-2" data-refusal-code={code}>
		<ControlApiError {error} />
		<p class="vu-muted text-sm" data-lane-refusal-text="true">{processingText(code)}</p>
	</div>
{:else if local}
	<div class="vu-panel vu-error card space-y-1 p-4" role="status" data-refusal-code={local.code}>
		<p class="vu-eyebrow">Not sent</p>
		<p><code>{local.code}</code></p>
		<p class="text-sm">{local.message}</p>
	</div>
{/if}
