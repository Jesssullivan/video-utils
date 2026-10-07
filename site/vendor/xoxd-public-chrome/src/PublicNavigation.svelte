<script lang="ts">
	import { onMount, tick, type Snippet } from 'svelte';
	import { Dialog, Navigation, Portal } from '@skeletonlabs/skeleton-svelte';
	import { Menu, X } from '@lucide/svelte';
	import SaturnMark from './SaturnMark.svelte';
	import ThemePicker from './ThemePicker.svelte';
	import type { SiteIdentity, NavigationLink } from './types';

	interface Props {
		identity: SiteIdentity;
		pathname?: string;
		navLinks: readonly NavigationLink[];
		quickLinks?: readonly NavigationLink[];
		externalLinks?: readonly NavigationLink[];
		action?: { label: string; onselect: () => void };
		brand?: Snippet;
		trailing?: Snippet;
		mobileSection?: Snippet<[() => void]>;
	}
	let { identity, pathname = '/', navLinks, quickLinks = [], externalLinks = [], action, brand, trailing, mobileSection }: Props = $props();
	let mobileOpen = $state(false);
	let compact = $state(false);
	const isCurrent = (link: NavigationLink) => link.current ?? (pathname === link.href || (link.href !== '/' && pathname.startsWith(`${link.href.replace(/\/$/, '')}/`)));
	const closeDrawer = () => { mobileOpen = false; };
	async function selectAction() {
		closeDrawer();
		await tick();
		action?.onselect();
	}
	onMount(() => {
		const update = () => { compact = window.scrollY > 32; };
		update();
		window.addEventListener('scroll', update, { passive: true });
		return () => window.removeEventListener('scroll', update);
	});
</script>

<header class:site-chrome--compact={compact} class="site-chrome sticky top-0 z-(--z-sticky)" data-testid="public-navigation">
	<div class="site-chrome__bar saturn-nav">
		<div class="site-header__inner flex min-h-14 items-center gap-3 py-2">
			<a href={identity.homeHref} class="site-chrome__brand hover:text-primary-500 inline-flex items-center gap-2 rounded-sm font-mono text-lg font-bold tracking-tight transition-colors focus:outline-2 focus:outline-offset-4 focus:outline-primary-500" aria-label={`${identity.name} home`}>
				{#if brand}{@render brand()}{:else}<SaturnMark class="text-primary-500 dark:text-primary-400 h-[1.05em] w-[1.05em]" />{/if}
				<span class="site-chrome__wordmark">{identity.name}</span>
			</a>
			<nav class="site-chrome__full ml-auto hidden items-center gap-5 text-sm lg:flex" aria-label="Primary navigation">
				{#each [...navLinks, ...externalLinks] as link (link.href)}
					<a href={link.href} aria-current={isCurrent(link) ? 'page' : undefined} class="hover:text-primary-500 rounded-sm transition-colors focus:outline-2 focus:outline-offset-4 focus:outline-primary-500">{link.label}</a>
				{/each}
				{#if action}<button type="button" class="hover:text-primary-500 rounded-sm transition-colors focus:outline-2 focus:outline-offset-4 focus:outline-primary-500" onclick={action.onselect}>{action.label}</button>{/if}
				<ThemePicker />
			</nav>
			<nav class="site-chrome__quick ml-auto items-center gap-3 text-sm" aria-label="Quick navigation">
				{#each quickLinks as link (link.href)}
					<a href={link.href} aria-current={isCurrent(link) ? 'page' : undefined} class="site-chrome__quick-link hover:text-primary-500 rounded-sm whitespace-nowrap transition-colors focus:outline-2 focus:outline-offset-4 focus:outline-primary-500" data-testid="quick-link">{link.label}</a>
				{/each}
			</nav>
			<div class="site-chrome__theme"><ThemePicker /></div>
			{#if trailing}<div class="site-chrome__trailing">{@render trailing()}</div>{/if}
			<Dialog open={mobileOpen} onOpenChange={(details: { open: boolean }) => { mobileOpen = details.open; }} closeOnInteractOutside closeOnEscape preventScroll>
				<button type="button" class="site-chrome__menu hover:bg-surface-200-800 rounded-sm p-2 focus:outline-2 focus:outline-offset-4 focus:outline-primary-500" aria-label="Open navigation" onclick={() => { mobileOpen = true; }}><Menu class="size-5" /></button>
				<Portal>
					<Dialog.Backdrop class="fixed inset-0 z-(--z-modal-backdrop) bg-black/45" />
					<Dialog.Positioner class="fixed inset-y-0 right-0 z-(--z-modal) flex w-80 max-w-[90vw]">
						<Dialog.Content class="bg-surface-50-950 flex w-full flex-col shadow-2xl">
							<div class="border-surface-200-800 flex items-center justify-between border-b px-4 py-3">
								<Dialog.Title class="font-mono text-sm font-semibold">{identity.name} navigation</Dialog.Title>
								<Dialog.CloseTrigger class="hover:bg-surface-200-800 rounded-sm p-2" aria-label="Close navigation"><X class="size-5" /></Dialog.CloseTrigger>
							</div>
							<Navigation layout="sidebar">
								<Navigation.Content><Navigation.Menu>
									{#each [...navLinks, ...externalLinks] as link (link.href)}
										<Navigation.TriggerAnchor href={link.href} aria-current={isCurrent(link) ? 'page' : undefined} onclick={closeDrawer}><Navigation.TriggerText>{link.label}</Navigation.TriggerText></Navigation.TriggerAnchor>
									{/each}
									{#if action}<button type="button" class="text-surface-950-50 hover:bg-surface-100-900 flex min-h-11 w-full items-center px-3 py-2 text-left text-sm" onclick={selectAction}>{action.label}</button>{/if}
								</Navigation.Menu>{@render mobileSection?.(closeDrawer)}</Navigation.Content>
								<Navigation.Footer><div class="flex justify-center py-3"><ThemePicker contained /></div></Navigation.Footer>
							</Navigation>
						</Dialog.Content>
					</Dialog.Positioner>
				</Portal>
			</Dialog>
		</div>
	</div>
</header>

<style>
	.site-chrome__bar {
		transition:
			min-height 180ms ease,
			margin 180ms ease,
			border-radius 180ms ease,
			box-shadow 180ms ease;
	}

	
	:global(.site-chrome__menu) {
		display: inline-flex;
		margin-left: 0;
	}

	.site-chrome__theme {
		display: flex;
	}

	.site-chrome__quick {
		display: flex;
	}

	.site-chrome__quick-link[aria-current='page'] {
		color: var(--color-primary-500);
		text-decoration: underline;
		text-underline-offset: 0.35em;
	}

	:global([data-mode='dark']) .site-chrome__quick-link[aria-current='page'] {
		color: var(--color-primary-400);
	}

	
	@media (max-width: 400px) {
		.site-chrome__wordmark {
			position: absolute;
			width: 1px;
			height: 1px;
			overflow: hidden;
			clip: rect(0 0 0 0);
			white-space: nowrap;
		}
	}

	@media (min-width: 1024px) {
		:global(.site-chrome__menu) {
			display: none;
		}
		.site-chrome__theme {
			display: none;
		}
		.site-chrome__quick {
			display: none;
		}
		.site-chrome--compact .site-chrome__quick {
			display: flex;
		}
		.site-chrome--compact .site-chrome__bar {
			margin-top: 0.5rem;
			margin-inline: auto;
			width: fit-content;
			border-radius: 9999px;
			box-shadow: 0 8px 24px color-mix(in oklch, var(--color-surface-950) 18%, transparent);
		}
		
		.site-chrome--compact .site-header__inner {
			width: auto;
			min-height: 3rem;
			padding-inline: 1.5rem;
		}
		.site-chrome--compact .site-chrome__full {
			display: none;
		}
		.site-chrome--compact :global(.site-chrome__menu) {
			display: inline-flex;
			margin-left: 0;
		}
		.site-chrome--compact .site-chrome__theme {
			display: flex;
		}
		.site-chrome--compact .site-chrome__wordmark {
			position: absolute;
			width: 1px;
			height: 1px;
			overflow: hidden;
			clip: rect(0 0 0 0);
			white-space: nowrap;
		}
	}

	

	@media (prefers-reduced-motion: reduce) {
		.site-chrome__bar {
			transition: none;
		}
	}
</style>
