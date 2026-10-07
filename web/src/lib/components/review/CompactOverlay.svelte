<script lang="ts">
	// The operator's compact default: "Compact: section/phrase label, BPM, and brief issue badges." It sits in a
	// top corner of the player, ignores pointer input and never covers the transport.
	interface Badge {
		text: string;
		basis: string;
		glyph: string;
	}
	interface Props {
		label: string | null;
		bpm: string;
		badges: Badge[];
		showLabel: boolean;
		showBpm: boolean;
		showBadges: boolean;
		clockNote: string;
	}
	let { label, bpm, badges, showLabel, showBpm, showBadges, clockNote }: Props = $props();
</script>

<div class="vu-overlay" aria-live="off" data-compact-overlay="true">
	{#if showLabel}<span class="vu-overlay-chip" data-overlay="label">[ ] INTENT · {label ?? 'no projected unit here'}</span>{/if}
	{#if showBpm}<span class="vu-overlay-chip" data-overlay="bpm">{bpm}</span>{/if}
	{#if showBadges}
		{#each badges.slice(0, 2) as badge, index (index)}
			<span class="vu-overlay-chip" data-overlay="badge" data-basis={badge.basis}>{badge.glyph} {badge.text}</span>
		{/each}
	{/if}
	<span class="vu-overlay-note">{clockNote}</span>
</div>

<style>
	.vu-overlay {
		position: absolute;
		top: 0.4rem;
		left: 0.4rem;
		right: 0.4rem;
		display: flex;
		flex-wrap: wrap;
		gap: 0.25rem;
		pointer-events: none;
	}
	.vu-overlay-chip {
		padding: 0.05rem 0.4rem;
		font-size: 0.7rem;
		background: rgba(22, 21, 18, 0.82);
		border: 1px solid var(--vu-line);
		border-radius: 4px;
	}
	.vu-overlay-note {
		font-size: 0.6rem;
		color: var(--vu-muted);
		background: rgba(22, 21, 18, 0.7);
		padding: 0 0.3rem;
	}
</style>
