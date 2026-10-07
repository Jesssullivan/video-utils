<script lang="ts">
	// Shown when SvelteKit sees an https app origin on a loopback http listener (ORIGIN unset under
	// adapter-node started without serve.js): its CSRF check then refuses every form POST with 403.
	// serve.js sets ORIGIN=http://<loopback host>:<port> by default in loopback mode, so this is rare.
	interface Props {
		show: boolean;
	}
	let { show }: Props = $props();
</script>

{#if show}
	<p class="vu-panel vu-error card p-3 text-sm" data-origin-warning="true">
		Form submissions on this page will be refused (HTTP 403, cross-site form check) because the app origin is not
		configured. Start the app with <code>ORIGIN=http://127.0.0.1:&lt;port&gt;</code> (the
		<code>serve.js</code> default; use <code>just web-serve</code>) and open it at that exact address.
	</p>
{/if}
