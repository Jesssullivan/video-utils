// Control-API URL configuration (WEB_STACK_S2.md section 4). Server-only.
import { env } from '$env/dynamic/private';

export const CONTROL_API_ENV = 'VIDEO_UTILS_CONTROL_API_URL';

// http only; host exactly 127.0.0.1 or [::1]; explicit port; no userinfo/path/query/fragment.
const LOOPBACK_URL = /^http:\/\/(127\.0\.0\.1|\[::1\]):([0-9]{1,5})\/?$/;

export type ControlApiConfig =
	| { readonly kind: 'configured'; readonly baseUrl: string }
	| { readonly kind: 'unconfigured' }
	| { readonly kind: 'refused' };

/** Pure validation; no network access. `localhost`, the wildcard address, LAN and public hosts are refused. */
export function parseControlApiUrl(raw: string | undefined): ControlApiConfig {
	if (raw === undefined || raw.trim() === '') return { kind: 'unconfigured' };
	const match = LOOPBACK_URL.exec(raw.trim());
	if (!match) return { kind: 'refused' };
	const port = Number(match[2]);
	if (!Number.isInteger(port) || port < 1 || port > 65535) return { kind: 'refused' };
	return { kind: 'configured', baseUrl: `http://${match[1]}:${port}` };
}

export function readControlApiConfig(): ControlApiConfig {
	return parseControlApiUrl(env[CONTROL_API_ENV]);
}
