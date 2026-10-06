<!-- Index: download is bound per job by artifact ID (/jobs/{id}); bundles are a Prototype label. -->
<script lang="ts">
	import PrototypeNotice from '$lib/components/PrototypeNotice.svelte';
</script>

<section class="space-y-4">
	<p class="text-sm">Bound in S2: each job page lists its artifacts with SHA-256 and size and downloads by artifact ID only.</p>
	<PrototypeNotice step="Delivery bundle" purpose="Restored clip with WAV, marker interchange and review data as one delivery." />
</section>
