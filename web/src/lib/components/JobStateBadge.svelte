<script lang="ts">
	import { isTerminalState } from '$lib/polling.js';
	interface Props {
		state: string;
	}
	let { state }: Props = $props();
	const tone = $derived(
		state === 'succeeded'
			? 'preset-filled-success-500'
			: state === 'failed' || state === 'needs_reconciliation' || state === 'interrupted'
				? 'preset-filled-error-500'
				: isTerminalState(state)
					? 'preset-tonal-surface'
					: 'preset-tonal-warning'
	);
</script>

<span class="badge {tone}" data-job-state={state}>{state}</span>
