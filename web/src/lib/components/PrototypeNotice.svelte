<script lang="ts">
	interface Props {
		step: string;
		purpose: string;
	}
	let { step, purpose }: Props = $props();
</script>

<section class="vu-panel card p-6 space-y-3" data-prototype="true">
	<p class="vu-eyebrow">Prototype</p>
	<h1 class="h3">{step}</h1>
	<p><strong>Not implemented in S2.</strong> {purpose}</p>
	<p class="vu-muted text-sm">
		This screen is a label only. It starts no processing, accepts no input and calls no
		mutating endpoint. Design reference: <code>docs/spec/future/WEB_UI_DESIGN.md</code>.
	</p>
</section>
