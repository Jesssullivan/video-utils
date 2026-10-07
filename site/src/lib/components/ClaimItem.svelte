<script lang="ts">
	import { CLASS_LABELS, type Claim } from '$lib/content/claims';

	let { claim }: { claim: Claim } = $props();
</script>

<li
	class="claim card bg-surface-100-900 space-y-2 p-4"
	data-claim-id={claim.id}
	data-claim-class={claim.claim_class}
	data-unknown={claim.unknown ? claim.id : undefined}
>
	<p class="text-surface-700-300 font-mono text-xs font-semibold tracking-wide uppercase">
		{CLASS_LABELS[claim.claim_class]}
	</p>
	<p>{claim.text}</p>
</li>
