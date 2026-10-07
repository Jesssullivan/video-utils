// The loopback guard stays on (WEB_TESTS_S3.md 5.2): Host check, same-origin mutations, no token in any response.
import http from 'node:http';
import { expect, fixture, forbiddenText, ids, MOCK_URL, record, ROUTES, test, UNCONFIGURED_URL } from '../tests/e2e-support';

type Reply = { status: number; headers: http.IncomingHttpHeaders; body: string };

/** A raw request so the Host and Origin headers are exactly what the test says (no browser normalisation). */
function raw(base: string, path: string, options: { method?: string; headers?: Record<string, string>; body?: string } = {}): Promise<Reply> {
	const url = new URL(path, base);
	return new Promise((resolve, reject) => {
		const request = http.request({ host: url.hostname, port: url.port, path: `${url.pathname}${url.search}`, method: options.method ?? 'GET', headers: options.headers ?? {}, timeout: 15_000 }, (response) => {
			const chunks: Buffer[] = [];
			response.on('data', (chunk: Buffer) => chunks.push(chunk));
			response.on('end', () => resolve({ status: response.statusCode ?? 0, headers: response.headers, body: Buffer.concat(chunks).toString('utf8') }));
		});
		request.on('timeout', () => request.destroy(new Error('request timed out')));
		request.on('error', reject);
		request.end(options.body);
	});
}

test('a request with a non-loopback Host is refused with 421 before routing', async ({ baseURL, mock }) => {
	const app = baseURL as string;
	const hosts = ['attacker.test', 'video.example.org:443', '192.168.1.10:3000', '127.0.0.1.attacker.test', 'localhost.attacker.test'];
	for (const host of hosts) {
		for (const path of ['/', '/api/sources', `/sources/${ids.source_reviewed}`]) {
			const reply = await raw(app, path, { headers: { host } });
			expect(reply.status, `${host} ${path}`).toBe(421);
			const body = JSON.parse(reply.body) as { code: string; status: string };
			expect(body).toMatchObject({ status: 'error', code: 'bff_host_refused' });
			expect(Object.keys(body).sort()).toEqual(['code', 'message', 'status', 'upstream_code', 'upstream_detail_code', 'upstream_status']);
			expect(reply.headers['cache-control']).toBe('no-store');
		}
	}
	// Nothing reached the control API for a refused Host.
	expect((await mock.log()).requests).toEqual([]);
	const port = new URL(app).port;
	expect((await raw(app, '/upload', { headers: { host: `127.0.0.1:${port}` } })).status).toBe(200);
	expect((await raw(app, '/upload', { headers: { host: `localhost:${port}` } })).status).toBe(200);
	record('headers', 'host_guard', { non_loopback_hosts: hosts.length, requests_refused_421: hosts.length * 3, upstream_requests: 0 });
});

test('a cross-origin POST to a BFF mutation route is refused with bff_cross_origin_refused', async ({ baseURL, mock }) => {
	const app = baseURL as string;
	const host = new URL(app).host;
	const job = JSON.stringify({ source_artifact_id: ids.source_reviewed, parameters: {}, idempotency_key: `ui-${'0'.repeat(31)}1` });
	const routes: Array<{ path: string; type: string; body: string }> = [
		{ path: '/api/jobs', type: 'application/json', body: job },
		{ path: '/api/sources', type: 'application/json', body: JSON.stringify({ selector: 'RUN/export/take.mov' }) },
		{ path: '/api/uploads', type: 'video/mp4', body: 'not media' },
		{ path: `/api/jobs/${ids.jobs.share_running}/cancel`, type: 'application/json', body: '{}' },
		{ path: `/api/jobs/${ids.jobs.share_failed}/retry`, type: 'application/json', body: '{}' },
		{ path: `/api/sources/${ids.source_reviewed}/annotations`, type: 'application/json', body: '{}' }
	];
	let refused = 0;
	for (const route of routes) {
		const headersFor = (extra: Record<string, string>) => ({ host, 'content-type': route.type, 'content-length': String(Buffer.byteLength(route.body)), ...extra });
		for (const extra of [{ origin: 'http://attacker.test' }, { origin: `https://${host}` }, { origin: 'null' }, {}, { 'sec-fetch-site': 'cross-site' }] as Array<Record<string, string>>) {
			const reply = await raw(app, route.path, { method: 'POST', headers: headersFor(extra), body: route.body });
			expect(reply.status, `${route.path} ${JSON.stringify(extra)}`).toBe(403);
			expect(JSON.parse(reply.body)).toMatchObject({ status: 'error', code: 'bff_cross_origin_refused' });
			refused += 1;
		}
	}
	expect((await mock.log()).requests.filter((entry) => entry.non_get)).toEqual([]);
	// The same request from this page's own origin passes the guard and reaches the control API (which refuses it by rule).
	const own = await raw(app, '/api/jobs', { method: 'POST', headers: { host, origin: app, 'content-type': 'application/json', 'content-length': String(Buffer.byteLength(job)) }, body: job });
	expect(own.status).toBe(409);
	expect(JSON.parse(own.body)).toMatchObject({ code: 'control_api_refused', upstream_code: 'capture_interval_required' });
	expect((await mock.log()).job_submissions).toBe(1);
	record('headers', 'cross_origin_guard', { mutation_routes: routes.length, refused_403: refused, same_origin_reaches_upstream: 1 });
});

test('SvelteKit form actions refuse a cross-origin post as well', async ({ baseURL, mock }) => {
	const app = baseURL as string;
	const host = new URL(app).host;
	const body = 'run_id=BASE-PLAIN&start_seconds=1&end_seconds=2';
	for (const action of [`/sources/${ids.source_plain}/capture?/save`, `/sources/${ids.source_plain}/capture?/measure`, `/sources/${ids.source_plain}/process?/denoise`]) {
		const reply = await raw(app, action, { method: 'POST', headers: { host, origin: 'http://attacker.test', 'content-type': 'application/x-www-form-urlencoded', 'content-length': String(Buffer.byteLength(body)) }, body });
		expect(reply.status, action).toBe(403);
	}
	expect((await mock.log()).requests.filter((entry) => entry.non_get)).toEqual([]);
});

test('the control API token, its URL and upstream error text never appear in any response', async ({ baseURL, mock }) => {
	const app = baseURL as string;
	const host = new URL(app).host;
	const secrets = forbiddenText();
	expect(secrets.length).toBeGreaterThanOrEqual(6);
	const paths = [
		...ROUTES.map((route) => route.path),
		`/sources/${ids.source_plain}`, `/sources/${ids.source_plain}/capture`, `/sources/${ids.source_plain}/process`, `/jobs/${ids.jobs.bad_unknown_key}`, `/runs/${ids.run_other}/review`,
		'/api/sources', '/api/capabilities', '/api/runs', `/api/runs/${ids.run_main}`, `/api/runs/${ids.run_main}/layers`, `/api/jobs/${ids.jobs.share_succeeded}`, `/api/jobs/${ids.jobs.bad_unknown_key}`,
		`/api/sources/${ids.source_plain}/annotations`, `/api/sources/${ids.source_reviewed}/jobs`, '/no-such-route', '/api/no-such-route'
	];
	let scanned = 0;
	for (const path of paths) {
		const reply = await raw(app, path, { headers: { host, accept: 'text/html,application/json' } });
		const blob = `${reply.body}\n${JSON.stringify(reply.headers)}`;
		for (const secret of secrets) expect(blob.includes(secret), `${path} contains ${secret.slice(0, 20)}…`).toBe(false);
		scanned += 1;
	}
	// The mock really was the upstream for these pages, and it saw the token on every call.
	const log = await mock.log();
	expect(log.requests.length).toBeGreaterThan(paths.length);
	expect(log.requests.every((entry) => entry.authorized)).toBe(true);
	expect(MOCK_URL.startsWith('http://127.0.0.1:')).toBe(true);
	expect(fixture<{ code: string }>('upload_refused.json').code).toBe('uploads_disabled');
	record('headers', 'no_token_in_responses', { responses_scanned: scanned, forbidden_strings: secrets.length, hits: 0 });
});

test('with no control API configured every page renders the typed configuration state', async ({ page }) => {
	expect(UNCONFIGURED_URL.startsWith('http://127.0.0.1:')).toBe(true);
	for (const path of ['/', '/upload', '/runs', '/jobs', '/tools']) {
		await page.goto(`${UNCONFIGURED_URL}${path}`, { waitUntil: 'networkidle' });
		const error = page.locator('[data-error-code="control_api_unconfigured"]').first();
		await expect(error, path).toBeVisible();
		await expect(error).toContainText('No control API is configured for this server.');
	}
});
