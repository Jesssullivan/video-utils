<script lang="ts">
	import type { Claim } from '$lib/content/claims';
	import ClaimItem from './ClaimItem.svelte';

	let { claims, label }: { claims: readonly Claim[]; label: string } = $props();
</script>

<ul class="mt-4 grid list-none gap-3 p-0" aria-label={label} data-prose-measure="none">
	{#each claims as claim (claim.id)}
		<ClaimItem {claim} />
	{/each}
</ul>
