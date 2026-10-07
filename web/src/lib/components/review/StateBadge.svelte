<script lang="ts">
	// State badge: text plus a shape glyph (never colour alone).
	interface Props {
		state: string;
	}
	let { state }: Props = $props();
	const SHAPES: Record<string, string> = {
		current: '●',
		accepted: '●',
		available: '●',
		stale: '◐',
		invalidated: '◐',
		missing: '○',
		unavailable: '○',
		unbound: '◇',
		refused: '✕',
		not_established: '◇'
	};
	const shape = $derived(SHAPES[state] ?? '?');
</script>

<span class="vu-state vu-state-{state}" data-state={state}><span aria-hidden="true">{shape}</span> {state.replaceAll('_', ' ')}</span>
