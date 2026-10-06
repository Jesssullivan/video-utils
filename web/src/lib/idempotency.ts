// Client-safe idempotency keys for the process form (WEB_UI_S2.md section 5): `ui-` + 32 hex,
// generated once per rendered form. A double submit of the same form replays the same job; a
// re-rendered form (changed knob) gets a new key and therefore a new job.
export const UI_KEY_PATTERN = /^ui-[0-9a-f]{32}$/;

export function newFormKey(prefix: 'ui' | 'ui-ann' = 'ui'): string {
	const bytes = new Uint8Array(16);
	globalThis.crypto.getRandomValues(bytes);
	return `${prefix}-${Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')}`;
}
