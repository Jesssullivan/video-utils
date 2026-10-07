<script lang="ts">
	// Shown when SvelteKit sees an https app origin on a loopback http listener (ORIGIN unset under
	// adapter-node): its CSRF check then refuses every form POST with 403. Root-owned fix requested.
	interface Props {
		show: boolean;
	}
	let { show }: Props = $props();
</script>

{#if show}
	<p class="vu-panel vu-error card p-3 text-sm" data-origin-warning="true">
		Form submissions on this page will be refused (HTTP 403, cross-site form check) because the app origin is not
		configured. Start the app with <code>ORIGIN=http://127.0.0.1:&lt;port&gt;</code> (requested as the
		<code>serve.js</code> default) and open it at that exact address.
	</p>
{/if}
