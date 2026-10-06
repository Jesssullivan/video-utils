// Control-API URL and bearer-token configuration (WEB_STACK_S2.md section 4, WEB_UI_S2.md section 5).
// Server-only. The token is never logged, serialized to the client or placed in an error body.
import { env } from '$env/dynamic/private';

export const CONTROL_API_ENV = 'VIDEO_UTILS_CONTROL_API_URL';
export const CONTROL_API_TOKEN_ENV = 'VIDEO_UTILS_CONTROL_API_TOKEN';

// http only; host exactly 127.0.0.1 or [::1]; explicit port; no userinfo/path/query/fragment.
const LOOPBACK_URL = /^http:\/\/(127\.0\.0\.1|\[::1\]):([0-9]{1,5})\/?$/;
// 16..256 URL-safe characters (scripts/web_api.py issues secrets.token_urlsafe(32)).
const TOKEN_PATTERN = /^[A-Za-z0-9_-]{16,256}$/;

export type ControlApiConfig =
	| { readonly kind: 'configured'; readonly baseUrl: string; readonly token: string }
	| { readonly kind: 'unconfigured' }
	| { readonly kind: 'refused' }
	| { readonly kind: 'unauthenticated' };

/** Pure validation; no network access. `localhost`, the wildcard address, LAN and public hosts are refused. */
export function parseControlApiConfig(raw: string | undefined, token: string | undefined): ControlApiConfig {
	if (raw === undefined || raw.trim() === '') return { kind: 'unconfigured' };
	const match = LOOPBACK_URL.exec(raw.trim());
	if (!match) return { kind: 'refused' };
	const port = Number(match[2]);
	if (!Number.isInteger(port) || port < 1 || port > 65535) return { kind: 'refused' };
	if (token === undefined || !TOKEN_PATTERN.test(token)) return { kind: 'unauthenticated' };
	return { kind: 'configured', baseUrl: `http://${match[1]}:${port}`, token };
}

export function readControlApiConfig(): ControlApiConfig {
	return parseControlApiConfig(env[CONTROL_API_ENV], env[CONTROL_API_TOKEN_ENV]);
}
