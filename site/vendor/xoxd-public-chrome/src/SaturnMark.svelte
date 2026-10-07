<script lang="ts">
	let { class: extraClass = '', decorative = true }: { class?: string; decorative?: boolean } = $props();
</script>

<svg
	class={`inline-block align-[-0.125em] ${extraClass}`}
	xmlns="http://www.w3.org/2000/svg"
	viewBox="0 0 24 24"
	role="img"
	aria-hidden={decorative ? 'true' : undefined}
	focusable="false"
	width="1em"
	height="1em"
	fill="none"
	stroke="currentColor"
	stroke-width="1.6"
	stroke-linecap="round"
>
	{#if !decorative}<title>Saturn mark</title>{/if}
	<!-- glyph -->
	<circle cx="12" cy="12" r="5" />
	<g transform="rotate(-22 12 12)">
		<ellipse cx="12" cy="12" rx="10.5" ry="3" />
	</g>
	<!-- /glyph -->
</svg>
