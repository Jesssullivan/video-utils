<script lang="ts">
	// Basis badge: label, shape token and text per basis (annotation_v2.LABELS plus the S2 origin badges).
	import { BASIS_STYLE, ORIGIN_STYLE, type BasisKey } from './review-logic';
	interface Props {
		basis?: string | null;
		origin?: keyof typeof ORIGIN_STYLE | null;
		claimLabel?: string | null;
	}
	let { basis = null, origin = null, claimLabel = null }: Props = $props();
	const style = $derived(
		basis && basis in BASIS_STYLE
			? BASIS_STYLE[basis as BasisKey]
			: origin
				? ORIGIN_STYLE[origin]
				: { label: 'UNKNOWN BASIS', shape: 'plain', text: 'Basis not recorded', glyph: '?' }
	);
	const label = $derived(claimLabel && basis ? claimLabel : style.label);
</script>

<span class="vu-basis vu-shape-{style.shape}" data-basis={basis ?? origin ?? 'unknown'} data-shape={style.shape} title={style.text}>
	<span aria-hidden="true">{style.glyph}</span>
	{label}
	<span class="vu-basis-text">· {style.text}</span>
</span>
