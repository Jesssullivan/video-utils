<script lang="ts">
	import type { BffError } from '$lib/control-types';
	interface Props {
		error: BffError;
	}
	let { error }: Props = $props();
</script>

<div class="vu-panel vu-error card p-4 space-y-1" role="status" data-error-code={error.code}>
	<p class="vu-eyebrow">Control API status</p>
	<p><code>{error.code}</code></p>
	<p class="text-sm">{error.message}</p>
	{#if error.upstream_status !== null}
		<p class="vu-muted text-sm">Upstream HTTP status: <span class="vu-time">{error.upstream_status}</span></p>
	{/if}
</div>
