<script lang="ts">
	import { page } from '$app/state';
	import { PublicNavigation, SiteFooter } from '@xoxd/public-chrome';
	import { SITE } from '$lib/content/claims';
	import '../app.css';

	let { children } = $props();

	const identity = { name: SITE.working_title, homeHref: '/' };
	const navLinks = [
		{ href: '/', label: 'Overview' },
		{ href: '/features', label: 'Features' },
		{ href: '/agents', label: 'Agent tools' },
		{ href: '/status', label: 'Status' }
	];
</script>

<div class="flex min-h-screen flex-col">
	<a href="#content" class="skip-link sr-only focus:not-sr-only">Skip to content</a>
	<PublicNavigation {identity} pathname={page.url.pathname} {navLinks} quickLinks={navLinks} />
	<main id="content" class="page-shell flex-1">
		{@render children?.()}
	</main>
	<SiteFooter
		{identity}
		tagline={SITE.tagline}
		description={SITE.footer_note}
		sections={[{ heading: 'Site', links: navLinks }]}
		copyright={SITE.footer_line}
	/>
</div>
