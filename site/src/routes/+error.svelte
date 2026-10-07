<script lang="ts">
	import { SITE } from '$lib/content/claims';
</script>

<svelte:head>
	<title>Page not found | {SITE.working_title}</title>
	<meta name="robots" content="noindex" />
</svelte:head>

<h1>Page not found</h1>
<p class="mt-6">There is nothing at this address. <a class="anchor" href="/">Return to the overview</a>.</p>
