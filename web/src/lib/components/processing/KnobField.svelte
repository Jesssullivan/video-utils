<script lang="ts">
	// One numeric knob with its schema bounds shown as text. No min/max attributes: the control API
	// is the single validator and out-of-range values come back as typed refusals (never clamped).
	interface Spec {
		type?: string;
		minimum?: number;
		maximum?: number;
		description?: string;
	}
	interface Props {
		name: string;
		label?: string;
		spec: Spec | undefined;
		value?: string;
		presetValue?: string | number | null;
		disabled?: boolean;
	}
	let { name, label = name, spec, value = $bindable(''), presetValue = null, disabled = false }: Props = $props();
	const bounds = $derived(spec ? `${spec.minimum ?? '−∞'}..${spec.maximum ?? '∞'} (${spec.type ?? 'number'})` : 'bounds unknown');
</script>

<label class="label space-y-1" data-knob={name}>
	<span class="label-text"><code>{label}</code></span>
	<input class="input vu-time" type="number" step="any" {name} bind:value {disabled} placeholder={presetValue !== null ? `FULLER ${presetValue}` : ''} />
	<span class="vu-muted block text-xs">schema {bounds}{presetValue !== null ? `; FULLER value ${presetValue}` : ''}</span>
</label>
