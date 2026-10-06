// Client-safe upload allowlist (mirrors scripts/web_api.py UPLOAD_TYPES). The client-side size
// pre-check is advisory only; the control API enforces the bound before writing any byte.
export const UPLOAD_TYPES: Readonly<Record<string, string>> = {
	'video/quicktime': '.mov',
	'video/mp4': '.mp4',
	'video/x-m4v': '.m4v',
	'video/x-matroska': '.mkv',
	'video/webm': '.webm'
};
export const UPLOAD_ACCEPT = Object.keys(UPLOAD_TYPES).join(',') + ',' + Object.values(UPLOAD_TYPES).join(',');

/** Browser `File.type` is sometimes empty (e.g. .mkv); fall back to the extension. */
export function uploadContentType(name: string, browserType: string): string | null {
	if (browserType in UPLOAD_TYPES) return browserType;
	const lower = name.toLowerCase();
	for (const [type, suffix] of Object.entries(UPLOAD_TYPES)) {
		if (lower.endsWith(suffix)) return type;
	}
	return null;
}
