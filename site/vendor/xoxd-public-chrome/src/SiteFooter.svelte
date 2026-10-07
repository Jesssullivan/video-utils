<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { SiteIdentity, FooterSection } from './types';
	interface Props {
		identity: SiteIdentity;
		tagline?: string;
		description?: string;
		licenseText?: string;
		sections?: readonly FooterSection[];
		copyright?: string;
		provenance?: Snippet;
		accent?: Snippet;
		contact?: Snippet;
	}
	let { identity, tagline, description, licenseText, sections = [], copyright = `Copyright ${new Date().getUTCFullYear()} ${identity.name}.`, provenance, accent, contact }: Props = $props();
</script>

<footer id="contact" class="site-footer border-surface-200-800 bg-surface-100-900/85 mt-16 border-t backdrop-blur-sm">
	<div class="site-footer__inner py-12 text-sm">
		<div class="public-footer-grid grid gap-9 sm:grid-cols-2 lg:grid-cols-4">
			<section class="space-y-4">
				<h2 class="site-footer__wordmark text-primary-500 dark:text-primary-400 font-mono font-bold tracking-tight">{identity.name}</h2>
				{#if tagline}<p class="text-surface-900-50 font-medium">{tagline}</p>{/if}
				{#if description}<p class="text-surface-700-300 max-w-xl leading-6">{description}</p>{/if}
				{#if licenseText}<p class="text-surface-600-400 text-xs">{licenseText}</p>{/if}
			</section>
			{#each sections as section (section.heading)}
				<nav aria-label={section.heading} class="site-footer__group">
					<h2 class="text-surface-900-50">{section.heading}</h2>
					{#if section.text}<p class="text-surface-700-300 mb-4 leading-6">{section.text}</p>{/if}
					<ul class="space-y-2">{#each section.links as link (link.href)}<li><a href={link.href} class="hover:text-primary-500 rounded-sm transition-colors hover:underline focus:outline-2 focus:outline-offset-4 focus:outline-primary-500">{link.label}</a></li>{/each}</ul>
				</nav>
			{/each}
			{@render contact?.()}
		</div>
		<div class="border-surface-200-800 mt-10 grid gap-5 border-t pt-6 sm:grid-cols-[1fr_auto] sm:items-end">
			<div>{@render provenance?.()}</div>
			<div class="flex flex-col gap-3 text-xs sm:items-end"><p class="text-surface-600-400 flex items-center gap-2">{@render accent?.()}<span>{copyright}</span></p></div>
		</div>
	</div>
</footer>
