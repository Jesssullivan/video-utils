// Control-API URL and token validation (WEB_TESTS_S3.md 5.1). Pure: the env stand-in is empty.
import { describe, expect, it } from 'vitest';
import { CONTROL_API_ENV, CONTROL_API_TOKEN_ENV, parseControlApiConfig, readControlApiConfig } from './config';

const TOKEN = `unit-token-${'u'.repeat(20)}`; // synthetic; never a real control-API token

describe('parseControlApiConfig', () => {
	it('is unconfigured without a URL', () => {
		for (const raw of [undefined, '', '   ']) expect(parseControlApiConfig(raw, TOKEN)).toEqual({ kind: 'unconfigured' });
	});

	it('accepts only an http loopback URL with an explicit port', () => {
		expect(parseControlApiConfig('http://127.0.0.1:8765', TOKEN)).toEqual({ kind: 'configured', baseUrl: 'http://127.0.0.1:8765', token: TOKEN });
		expect(parseControlApiConfig(' http://127.0.0.1:8765/ ', TOKEN)).toEqual({ kind: 'configured', baseUrl: 'http://127.0.0.1:8765', token: TOKEN });
		expect(parseControlApiConfig('http://[::1]:9000', TOKEN)).toEqual({ kind: 'configured', baseUrl: 'http://[::1]:9000', token: TOKEN });
	});

	it('refuses every non-loopback, non-http or decorated URL', () => {
		const wildcard = ['0', '0', '0', '0'].join('.');
		const refused = [
			'http://localhost:8765', `http://${wildcard}:8765`, 'http://192.168.1.10:8765', 'http://example.org:8765', 'https://127.0.0.1:8765',
			'http://127.0.0.1', 'http://127.0.0.1:0', 'http://127.0.0.1:65536', 'http://127.0.0.1:8765/api', 'http://127.0.0.1:8765?x=1',
			'http://127.0.0.1:8765#f', 'http://user@127.0.0.1:8765', 'http://127.0.0.1.example.org:8765', '127.0.0.1:8765', 'ftp://127.0.0.1:8765'
		];
		for (const raw of refused) expect(parseControlApiConfig(raw, TOKEN), raw).toEqual({ kind: 'refused' });
	});

	it('reports a missing or malformed token without echoing it', () => {
		for (const token of [undefined, '', 'short', 'has space in the token value', `${'t'.repeat(257)}`, 'tok/en-with-slash-characters']) {
			const parsed = parseControlApiConfig('http://127.0.0.1:8765', token);
			expect(parsed).toEqual({ kind: 'unauthenticated' });
			expect(Object.keys(parsed)).toEqual(['kind']);
		}
	});

	it('a refused URL wins over a missing token (no token hint for a non-loopback host)', () => {
		expect(parseControlApiConfig('http://example.org:8765', undefined)).toEqual({ kind: 'refused' });
	});
});

describe('readControlApiConfig', () => {
	it('is unconfigured when the private env has no control API variables', () => {
		expect(CONTROL_API_ENV).toBe('VIDEO_UTILS_CONTROL_API_URL');
		expect(CONTROL_API_TOKEN_ENV).toBe('VIDEO_UTILS_CONTROL_API_TOKEN');
		expect(readControlApiConfig()).toEqual({ kind: 'unconfigured' });
	});
});
