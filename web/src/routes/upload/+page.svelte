<script lang="ts">
	import ControlApiError from '$lib/components/ControlApiError.svelte';
	import { isBffError, makeClientError, type BffError } from '$lib/control-types';
	import { bytes } from '$lib/format';
	import { UPLOAD_ACCEPT, uploadContentType } from '$lib/upload-types';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	let file = $state<File | null>(null);
	let label = $state('');
	let selector = $state('');
	let pending = $state(false);
	let error = $state<BffError | null>(null);
	let admitted = $state<{ id: string; status: number; deduplicated: boolean | null; bytes: number; sha256: string } | null>(null);
	const ADVISORY_MAX = 3 * 1024 ** 3;

	function pick(event: Event) {
		const input = event.currentTarget as HTMLInputElement;
		file = input.files?.[0] ?? null;
		error = null;
		admitted = null;
	}

	async function finish(response: Response) {
		const body: unknown = await response.json().catch(() => null);
		if (response.ok && body && !isBffError(body)) {
			const value = body as { source?: { source_artifact_id: string; size_bytes: number; sha256: string }; upload?: { deduplicated: boolean }; source_artifact_id?: string; size_bytes?: number; sha256?: string };
			const record = value.source ?? (value as { source_artifact_id: string; size_bytes: number; sha256: string });
			admitted = { id: record.source_artifact_id, status: response.status, deduplicated: value.upload?.deduplicated ?? null, bytes: record.size_bytes, sha256: record.sha256 };
			return;
		}
		// adapter-node refuses bodies above BODY_SIZE_LIMIT with a plain (non-JSON) 413.
		error = isBffError(body) ? body : response.status === 413 ? makeClientError('upload_too_large', 413) : makeClientError('http_error', response.status);
	}

	async function upload(event: SubmitEvent) {
		event.preventDefault();
		if (!file || pending) return;
		const type = uploadContentType(file.name, file.type);
		if (type === null) {
			error = makeClientError('upload_type_refused', 415);
			return;
		}
		pending = true;
		error = null;
		admitted = null;
		try {
			const headers: Record<string, string> = { 'content-type': type, accept: 'application/json' };
			if (label.trim() !== '') headers['x-upload-label'] = label.trim();
			await finish(await fetch('/api/uploads', { method: 'POST', headers, body: file }));
		} finally {
			pending = false;
		}
	}

	async function admit(event: SubmitEvent) {
		event.preventDefault();
		if (pending) return;
		pending = true;
		error = null;
		admitted = null;
		try {
			await finish(
				await fetch('/api/sources', {
					method: 'POST',
					headers: { 'content-type': 'application/json', accept: 'application/json' },
					body: JSON.stringify({ selector })
				})
			);
		} finally {
			pending = false;
		}
	}
</script>

<section class="space-y-4">
	<div>
		<p class="vu-eyebrow">Upload / admit</p>
		<h1 class="h2">Add a take</h1>
		<p class="vu-muted text-sm">
			Uploads are written into a private staging run and admitted by content hash; they are off unless the operator
			starts the control API with <code>--allow-uploads</code>. The browser never names a host path: the second form
			takes a selector relative to <code>artifacts/runs</code>.
		</p>
	</div>

	{#if data.error}
		<ControlApiError error={data.error} />
	{/if}

	<form class="vu-panel card space-y-3 p-5" onsubmit={upload} data-upload-form="true">
		<h2 class="h4">Upload a video file</h2>
		<input class="input" type="file" accept={UPLOAD_ACCEPT} onchange={pick} />
		<label class="label"><span class="label-text">Label (optional, kept only in the upload receipt)</span>
			<input class="input" bind:value={label} maxlength="120" />
		</label>
		{#if file}
			<p class="vu-muted text-xs">
				{bytes(file.size)}{#if file.size > ADVISORY_MAX} — larger than the default 3 GiB bound (advisory; the control API decides){/if}
			</p>
		{/if}
		<button class="btn preset-filled-primary-500" type="submit" disabled={!file || pending}>Upload and admit</button>
	</form>

	<form class="vu-panel card space-y-3 p-5" onsubmit={admit} data-selector-form="true">
		<h2 class="h4">Admit an existing run file</h2>
		<label class="label"><span class="label-text">Run-relative selector (RUN/…/file.mov)</span>
			<input class="input" bind:value={selector} maxlength="1024" placeholder="RUN/export/cleaned-video.mov" />
		</label>
		<button class="btn preset-filled-primary-500" type="submit" disabled={selector.trim() === '' || pending}>Admit selector</button>
	</form>

	{#if error}<ControlApiError {error} />{/if}
	{#if admitted}
		<div class="vu-panel card space-y-1 p-4" data-admitted={admitted.id}>
			<p class="vu-eyebrow">Admitted (HTTP {admitted.status}{admitted.deduplicated ? ', same bytes as an earlier upload' : ''})</p>
			<p><a class="anchor" href={`/sources/${admitted.id}`}><code>{admitted.id}</code></a></p>
			<p class="vu-muted text-xs vu-time">{bytes(admitted.bytes)} · sha256 {admitted.sha256}</p>
		</div>
	{/if}
</section>
