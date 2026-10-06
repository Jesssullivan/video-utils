<script lang="ts">
	interface Props {
		step: string;
		purpose: string;
		/** Inline label inside a bound page (no "screen" wording). */
		inline?: boolean;
	}
	let { step, purpose, inline = false }: Props = $props();
</script>

{#if inline}
	<section class="vu-panel card space-y-2 p-5" data-prototype="true">
		<p class="vu-eyebrow">Prototype</p>
		<h2 class="h4">{step}</h2>
		<p class="text-sm">{purpose}</p>
	</section>
{:else}
	<section class="vu-panel card p-6 space-y-3" data-prototype="true">
		<p class="vu-eyebrow">Prototype</p>
		<h1 class="h3">{step}</h1>
		<p><strong>Not implemented in S2.</strong> {purpose}</p>
		<p class="vu-muted text-sm">
			This label starts no processing, accepts no input and calls no mutating endpoint. Design
			reference: <code>docs/spec/future/WEB_UI_DESIGN.md</code>.
		</p>
	</section>
{/if}
