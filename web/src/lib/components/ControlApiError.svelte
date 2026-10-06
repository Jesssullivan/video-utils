<script lang="ts">
	import { displayCode, type BffError } from '$lib/control-types';
	import { refusalText } from '$lib/refusal-text';
	interface Props {
		error: BffError;
	}
	let { error }: Props = $props();
	const shown = $derived(displayCode(error));
</script>

<div class="vu-panel vu-error card p-4 space-y-1" role="status" data-error-code={error.code} data-upstream-code={error.upstream_code ?? ''}>
	<p class="vu-eyebrow">Refused</p>
	<p><code>{shown}</code>{#if error.upstream_detail_code} <code class="vu-muted">({error.upstream_detail_code})</code>{/if}</p>
	<p class="text-sm">{refusalText(shown)}</p>
	{#if error.upstream_code}
		<p class="vu-muted text-xs">BFF code <code>{error.code}</code>; control API HTTP status <span class="vu-time">{error.upstream_status}</span>.</p>
	{:else}
		<p class="vu-muted text-xs">{error.message}{#if error.upstream_status !== null} (upstream HTTP <span class="vu-time">{error.upstream_status}</span>){/if}</p>
	{/if}
</div>
