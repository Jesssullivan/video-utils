// Loopback mock of the control API for the Playwright suites (WEB_TESTS_S3.md 5.2). Replay only.
//
// GET routes replay the committed synthetic fixtures through fixtures/control-api/routes.json. The mock decides
// nothing about the product: the four write routes replay responses recorded from the real control API, chosen by
// the rules listed in RULES below (and in fixtures/README.json). Media bytes are synthesized here: a 0.5 s mono PCM16
// WAV carrying a 32.70 Hz sine (theoretical C1), so no fixture implies a high-passed signal. It is not a recording
// and supports no listening claim. Tests read the request log through /__mock/* on this port, never through the BFF.
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import http from 'node:http';
import { fileURLToPath } from 'node:url';

export const MOCK_TOKEN = `e2e-mock-token-${'e'.repeat(24)}`; // synthetic; never a real control-API token
export const MOCK_HOST = '127.0.0.1';
export const SCENARIOS = ['default', 'product_default_admission'];
export const RULES = {
	'POST /api/v1/uploads': 'drains the body, stores nothing, replays upload_refused.json (uploads_disabled)',
	'POST /api/v1/sources/{id}/capture-reviews':
		'replays review_refused_setup.json when start_seconds < 5 and setup_interval_acknowledged is not true, else review_saved_acknowledged.json (and counts one review record)',
	'POST /api/v1/sources/{id}/capture-measurements': 'replays measurement.json',
	'POST /api/v1/jobs': 'replays submit_refused.json (capture_interval_required) and counts one job submission',
	'GET /api/v1/job-types': 'scenario product_default_admission replays job_types_product_default.json',
	'GET media routes': 'synthesized 32.70 Hz WAV',
	'anything else': 'mock-synthesized typed 404 route_not_found, 405 method_not_allowed or 401 unauthorized'
};

const MAX_BODY_BYTES = 1_048_576;
const MEDIA_ROUTES = [
	/^\/api\/v1\/runs\/[A-Za-z0-9._-]+\/media\/[a-z]+$/,
	/^\/api\/v1\/runs\/[A-Za-z0-9._-]+\/layers\/media\/evd_[0-9a-f]{32}\/[A-Za-z0-9._-]+$/,
	/^\/api\/v1\/runs\/[A-Za-z0-9._-]+\/artifacts\/art_[0-9a-f]{32}$/,
	/^\/api\/v1\/sources\/art_[0-9a-f]{32}\/media$/,
	/^\/api\/v1\/artifacts\/art_[0-9a-f]{32}$/
];

/** 0.5 s, 8 kHz, mono PCM16: a 32.70 Hz sine at -10 dBFS peak. */
export function lowRegisterWav() {
	const rate = 8000;
	const frames = rate / 2;
	const data = Buffer.alloc(frames * 2);
	for (let index = 0; index < frames; index += 1) {
		data.writeInt16LE(Math.round(Math.sin((2 * Math.PI * 32.7 * index) / rate) * 0.316 * 32767), index * 2);
	}
	const header = Buffer.alloc(44);
	header.write('RIFF', 0, 'ascii');
	header.writeUInt32LE(36 + data.length, 4);
	header.write('WAVEfmt ', 8, 'ascii');
	header.writeUInt32LE(16, 16);
	header.writeUInt16LE(1, 20);
	header.writeUInt16LE(1, 22);
	header.writeUInt32LE(rate, 24);
	header.writeUInt32LE(rate * 2, 28);
	header.writeUInt16LE(2, 32);
	header.writeUInt16LE(16, 34);
	header.write('data', 36, 'ascii');
	header.writeUInt32LE(data.length, 40);
	return Buffer.concat([header, data]);
}

function normalise(rawUrl) {
	const url = new URL(rawUrl, `http://${MOCK_HOST}`);
	// Listing bounds, the selected evidence bundle and the download disposition do not change which fixture replays.
	for (const name of ['limit', 'evidence', 'disposition']) url.searchParams.delete(name);
	const query = url.searchParams.toString();
	return { path: url.pathname, key: query ? `${url.pathname}?${query}` : url.pathname };
}

async function readBody(request) {
	const chunks = [];
	let total = 0;
	for await (const chunk of request) {
		total += chunk.length;
		if (total <= MAX_BODY_BYTES) chunks.push(chunk);
	}
	return { bytes: total, text: total <= MAX_BODY_BYTES ? Buffer.concat(chunks).toString('utf8') : '' };
}

/**
 * @param {{ fixturesDir?: string }} [options]
 * @returns {Promise<{ port: number, url: string, token: string, close: () => Promise<void> }>}
 */
export async function startMock(options = {}) {
	const fixturesDir = options.fixturesDir ?? fileURLToPath(new URL('./fixtures/control-api/', import.meta.url));
	const load = (file) => readFileSync(`${fixturesDir.replace(/\/?$/, '/')}${file}`, 'utf8');
	const rows = JSON.parse(load('routes.json')).routes;
	const plain = new Map();
	const variants = new Map();
	for (const row of rows) {
		const key = `${row.method} ${row.path}`;
		if (row.variant === null) plain.set(key, row);
		else variants.set(`${key}#${row.variant}`, row);
	}
	const wav = lowRegisterWav();
	const wavSha = createHash('sha256').update(wav).digest('hex');
	const state = { scenario: 'default', requests: [], stored_upload_bytes: 0, review_records: 0, job_submissions: 0 };
	const reset = () => Object.assign(state, { scenario: 'default', requests: [], stored_upload_bytes: 0, review_records: 0, job_submissions: 0 });

	const sendJson = (response, status, text, file) => {
		const body = Buffer.from(text, 'utf8');
		response.writeHead(status, { 'content-type': 'application/json', 'content-length': body.length, 'cache-control': 'no-store' });
		response.end(body);
		return file;
	};
	const synthesized = (response, status, code) => sendJson(response, status, JSON.stringify({ status: 'error', code, error: 'mock-synthesized response' }), `(mock ${code})`);
	const replay = (response, row) => sendJson(response, row.status, load(row.file), row.file);

	const server = http.createServer(async (request, response) => {
		const method = request.method ?? 'GET';
		const { path, key } = normalise(request.url ?? '/');
		try {
			if (path.startsWith('/__mock/')) {
				const body = await readBody(request);
				if (method === 'GET' && path === '/__mock/log') return void sendJson(response, 200, JSON.stringify(state));
				if (method === 'POST' && path === '/__mock/reset') return void sendJson(response, 200, JSON.stringify({ reset: reset() && true }));
				if (method === 'POST' && path === '/__mock/scenario') {
					const name = JSON.parse(body.text || '{}').name;
					if (!SCENARIOS.includes(name)) return void synthesized(response, 400, 'unknown_scenario');
					state.scenario = name;
					return void sendJson(response, 200, JSON.stringify({ scenario: name }));
				}
				return void synthesized(response, 404, 'route_not_found');
			}
			const entry = { method, path: key, status: 0, file: null, non_get: method !== 'GET' && method !== 'HEAD', body_bytes: 0, authorized: request.headers.authorization === `Bearer ${MOCK_TOKEN}` };
			state.requests.push(entry);
			const body = await readBody(request);
			entry.body_bytes = body.bytes;
			const done = (file, status) => {
				entry.file = file;
				entry.status = status;
			};
			if (!entry.authorized) return void done(synthesized(response, 401, 'unauthorized'), 401);

			if (method === 'GET' && MEDIA_ROUTES.some((pattern) => pattern.test(path))) {
				response.writeHead(200, { 'content-type': 'audio/wav', 'content-length': wav.length, 'x-artifact-sha256': wavSha, 'accept-ranges': 'none', 'cache-control': 'no-store' });
				response.end(wav);
				return void done('(mock 32.70 Hz wav)', 200);
			}
			if (method === 'POST' && path === '/api/v1/uploads') {
				const row = plain.get('POST /api/v1/uploads');
				return void done(replay(response, row), row.status); // stored_upload_bytes stays 0: nothing is written
			}
			if (method === 'POST' && path === '/api/v1/jobs') {
				state.job_submissions += 1;
				const row = plain.get('POST /api/v1/jobs');
				return void done(replay(response, row), row.status);
			}
			if (method === 'POST' && /^\/api\/v1\/sources\/art_[0-9a-f]{32}\/capture-(reviews|measurements)$/.test(path)) {
				const kind = path.endsWith('reviews') ? 'reviews' : 'measurements';
				const candidates = rows.filter((item) => item.method === 'POST' && item.path.endsWith(`/capture-${kind}`));
				let sent = {};
				try {
					sent = JSON.parse(body.text || '{}');
				} catch {
					return void done(synthesized(response, 400, 'invalid_json'), 400);
				}
				entry.review_request = kind === 'reviews' ? { start_seconds: sent.start_seconds ?? null, setup_interval_acknowledged: sent.setup_interval_acknowledged ?? null, review_status: sent.review_status ?? null } : undefined;
				let row = candidates[0];
				if (kind === 'reviews') {
					const overlapsSetup = typeof sent.start_seconds === 'number' && sent.start_seconds < 5;
					const variant = overlapsSetup && sent.setup_interval_acknowledged !== true ? 'unacknowledged' : 'acknowledged';
					row = candidates.find((item) => item.variant === variant);
					if (variant === 'acknowledged') state.review_records += 1;
				}
				return void done(replay(response, row), row.status);
			}
			const variant = method === 'GET' && path === '/api/v1/job-types' && state.scenario === 'product_default_admission' ? variants.get(`${method} ${key}#product_default`) : undefined;
			const row = variant ?? plain.get(`${method} ${key}`);
			if (row) return void done(replay(response, row), row.status);
			const knownPath = rows.some((item) => item.path === key);
			return void done(synthesized(response, knownPath ? 405 : 404, knownPath ? 'method_not_allowed' : 'route_not_found'), knownPath ? 405 : 404);
		} catch {
			if (!response.headersSent) synthesized(response, 500, 'mock_internal_error');
			else response.destroy();
		}
	});
	await new Promise((resolve, reject) => {
		server.once('error', reject);
		server.listen(0, MOCK_HOST, () => resolve(undefined));
	});
	const address = server.address();
	const port = typeof address === 'object' && address !== null ? address.port : 0;
	return {
		port,
		url: `http://${MOCK_HOST}:${port}`,
		token: MOCK_TOKEN,
		close: () =>
			new Promise((resolve) => {
				server.closeAllConnections?.();
				server.close(() => resolve(undefined));
			})
	};
}

// `node e2e/mock-control-api.mjs` serves the fixtures in the foreground for manual inspection (Ctrl-C stops it).
if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
	const mock = await startMock();
	process.stdout.write(`${JSON.stringify({ url: mock.url, token_variable: 'MOCK_TOKEN (exported by this module)' })}\n`);
}
