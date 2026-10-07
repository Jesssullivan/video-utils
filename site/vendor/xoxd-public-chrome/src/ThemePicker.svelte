<script lang="ts">
	import { onMount } from 'svelte';
	import { Popover, Portal } from '@skeletonlabs/skeleton-svelte';
	import { Check, Monitor, Moon, Palette, Sun, type Icon as LucideIcon } from '@lucide/svelte';
	import { theme, type ColorMode } from './theme.svelte';
	import { THEMES, themeById, type ThemeId } from './theme/suite';


	interface Props {
		
		contained?: boolean;
	}

	let { contained = false }: Props = $props();
	let isOpen = $state(false);

	const MODES: { id: ColorMode; label: string; hint: string; icon: typeof LucideIcon }[] = [
		{ id: 'light', label: 'Light', hint: 'Light scheme', icon: Sun },
		{ id: 'dark', label: 'Dark', hint: 'Dark scheme, the default', icon: Moon },
		{ id: 'system', label: 'System', hint: 'Follows the OS preference', icon: Monitor },
	];

	const activeMode = $derived(MODES.find((mode) => mode.id === theme.mode) ?? MODES[1]);
	const activeTheme = $derived(themeById(theme.currentTheme));

	onMount(() => {
		theme.init();
	});

	function handleOpenChange(details: { open: boolean }) {
		isOpen = details.open;
	}

	function selectMode(mode: ColorMode) {
		theme.setMode(mode);
		isOpen = false;
	}

	function selectTheme(id: ThemeId) {
		theme.setTheme(id);
		isOpen = false;
	}
</script>

<Popover
	open={isOpen}
	onOpenChange={handleOpenChange}
	positioning={{ placement: 'bottom-end', gutter: 8 }}
	closeOnInteractOutside
	closeOnEscape
>
	<Popover.Trigger
		class="text-primary-600-400 hover:text-primary-500 inline-flex size-11 shrink-0 items-center justify-center rounded-sm leading-none transition-colors focus:outline-2 focus:outline-offset-4 focus:outline-primary-500"
		aria-label={`Theme: ${activeTheme.label}. Color mode: ${activeMode.label}. Choose theme and color mode`}
		title={`${activeTheme.label} theme, ${activeMode.label.toLowerCase()} color mode`}
		data-testid="theme-picker-trigger"
	>
		<span aria-hidden="true"><Palette class="size-5" strokeWidth={2} /></span>
	</Popover.Trigger>
	<Portal disabled={contained}>
		<!-- This picker also mounts inside the modal-tier mobile drawer. The
		     semantic tooltip tier keeps its portaled menu visible and clickable
		     without adding a one-off z-index. -->
		<Popover.Positioner class="z-(--z-tooltip)">
			<Popover.Content
				class="bg-surface-50-950 border-surface-300-700 max-h-[calc(100vh-5rem)] min-w-52 max-w-[calc(100vw-2rem)] overflow-y-auto overscroll-contain rounded-sm border py-2 shadow-lg"
				data-testid="theme-picker-content"
			>
				<Popover.Title class="text-surface-600-400 px-3 py-1 text-xs font-semibold tracking-wide uppercase"
					>Color mode</Popover.Title
				>
				{#each MODES as mode (mode.id)}
					{@const Icon = mode.icon}
					{@const active = theme.mode === mode.id}
					<button
						type="button"
						onclick={() => selectMode(mode.id)}
						aria-label={`Set color mode to ${mode.label}`}
						aria-pressed={active}
						title={mode.hint}
						class="hover:bg-surface-200-800 flex min-h-11 w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm transition-colors {active
							? 'text-primary-500 font-semibold'
							: ''}"
					>
						<span class="flex items-center gap-2">
							<Icon class="size-5" aria-hidden="true" />
							{mode.label}
						</span>
						{#if active}
							<Check class="size-4" aria-hidden="true" />
						{/if}
					</button>
				{/each}
				<div class="border-surface-300-700 my-1.5 border-t"></div>
				<p class="text-surface-600-400 px-3 py-1 text-xs font-semibold tracking-wide uppercase">Theme</p>
				{#each THEMES as option (option.id)}
					{@const active = theme.currentTheme === option.id}
					<button
						type="button"
						onclick={() => selectTheme(option.id)}
						aria-label={`Set theme to ${option.label}`}
						aria-pressed={active}
						class="hover:bg-surface-200-800 flex min-h-11 w-full items-center gap-3 px-3 py-2 text-left text-sm transition-colors {active
							? 'text-primary-500 font-semibold'
							: ''}"
					>
						<span class="flex gap-0.5" aria-hidden="true">
							{#each option.colors as color, index (`${option.id}-${index}`)}
								<span class="border-surface-300-700 size-2.5 rounded-full border" style="background: {color}"></span>
							{/each}
						</span>
						{option.label}
						{#if active}
							<Check class="ml-auto size-4" aria-hidden="true" />
						{/if}
					</button>
				{/each}
			</Popover.Content>
		</Popover.Positioner>
	</Portal>
</Popover>
