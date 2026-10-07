// Client-safe annotation saves through the existing BFF route /api/sources/{id}/annotations (annotation_v2
// semantics, no new route). Outcomes follow REVIEW_UI_S2 5.7: a transport error, a 5xx or a malformed success is
// "uncertain" (retry the same bytes and key); stale_annotation_revision is "stale"; any other 4xx is "refused".
import type { AnnotationClock, AnnotationStorePublic } from '$lib/schema/control';
import { isBffError } from '$lib/control-types';

export type SaveOutcome =
	| { kind: 'ok'; store: AnnotationStorePublic; clock: AnnotationClock; outcome: 'saved' | 'replayed' }
	| { kind: 'uncertain'; code: string }
	| { kind: 'stale' }
	| { kind: 'refused'; code: string };

export async function postAnnotation(sourceId: string, body: string, expected: { source_sha256: string; manifest_sha256: string }): Promise<SaveOutcome> {
	let response: Response;
	let value: unknown;
	try {
		response = await fetch(`/api/sources/${sourceId}/annotations`, {
			method: 'POST',
			headers: { 'content-type': 'application/json', accept: 'application/json' },
			body
		});
		value = await response.json().catch(() => null);
	} catch {
		return { kind: 'uncertain', code: 'transport_error' };
	}
	if (response.status >= 500) return { kind: 'uncertain', code: isBffError(value) ? (value.upstream_code ?? value.code) : `status_${response.status}` };
	if (!response.ok) {
		const code = isBffError(value) ? (value.upstream_code ?? value.code) : `status_${response.status}`;
		return code === 'stale_annotation_revision' ? { kind: 'stale' } : { kind: 'refused', code };
	}
	const result = value as { store?: AnnotationStorePublic; clock?: AnnotationClock; mutation?: { outcome?: string; annotation_id?: string } } | null;
	if (
		!result?.store ||
		!result.clock ||
		result.store.source_sha256 !== expected.source_sha256 ||
		result.store.manifest_sha256 !== expected.manifest_sha256 ||
		!result.mutation?.annotation_id
	) {
		return { kind: 'uncertain', code: 'receipt_identity_unclear' };
	}
	return { kind: 'ok', store: result.store, clock: result.clock, outcome: result.mutation.outcome === 'replayed' ? 'replayed' : 'saved' };
}

export async function readStore(sourceId: string): Promise<{ store: AnnotationStorePublic; clock: AnnotationClock } | null> {
	try {
		const response = await fetch(`/api/sources/${sourceId}/annotations`, { headers: { accept: 'application/json' } });
		const value: unknown = await response.json().catch(() => null);
		if (!response.ok || !value || isBffError(value)) return null;
		return value as { store: AnnotationStorePublic; clock: AnnotationClock };
	} catch {
		return null;
	}
}
