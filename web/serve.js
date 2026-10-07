// Mode-aware launcher for the adapter-node build (WEB_STACK_S2.md section 5.4; AUTH_HOSTING_S3.md 4.1).
// Loopback mode (VIDEO_UTILS_AUTH_MODE unset or empty, the default) is unchanged from S2: adapter-node
// defaults HOST to the all-interfaces wildcard; this wrapper defaults it to 127.0.0.1 and refuses any
// other host with exit code 2 BEFORE the server module is imported.
// Tailnet mode (VIDEO_UTILS_AUTH_MODE=tailnet) may bind a non-loopback HOST only when the complete
// tailnet configuration validates at startup; otherwise it exits 2 before the server is imported.
// Any other mode value exits 2. Diagnostics name variables only, never their values.
const LOOPBACK_HOSTS = new Set(['127.0.0.1', '::1']);
const REFUSAL_EXIT_CODE = 2;
const MODE_ENV = 'VIDEO_UTILS_AUTH_MODE';
// An IP literal or DNS name to bind; no scheme, port, path or whitespace.
const BIND_HOST_PATTERN = /^[A-Za-z0-9.:-]{1,253}$/;

const mode = process.env[MODE_ENV] ?? '';

if (mode === '') {
	if (process.env.HOST === undefined || process.env.HOST === '') {
		process.env.HOST = '127.0.0.1';
	}
	const host = process.env.HOST;
	if (!LOOPBACK_HOSTS.has(host)) {
		console.error(
			`serve.js: refusing HOST=${JSON.stringify(host)}; only 127.0.0.1 or ::1 are supported (no hosted deployment).`
		);
		process.exit(REFUSAL_EXIT_CODE);
	}
	if (process.env.SOCKET_PATH) {
		console.error('serve.js: refusing SOCKET_PATH; S2 serves only a loopback TCP port.');
		process.exit(REFUSAL_EXIT_CODE);
	}
	// SvelteKit's CSRF check compares a form POST's Origin with url.origin; adapter-node reports
	// https:// unless ORIGIN is set, which refuses every form action on this http loopback listener.
	// Loopback mode only: tailnet mode requires an explicit https ORIGIN validated by auth/mode.js.
	if (!process.env.ORIGIN) {
		const port = process.env.PORT || '3000';
		process.env.ORIGIN = `http://${host === '::1' ? '[::1]' : host}:${port}`;
	}
} else if (mode === 'tailnet') {
	if (process.env.SOCKET_PATH) {
		console.error('serve.js: refusing SOCKET_PATH; tailnet mode serves only a TCP port.');
		process.exit(REFUSAL_EXIT_CODE);
	}
	const host = process.env.HOST ?? '';
	if (!BIND_HOST_PATTERN.test(host)) {
		console.error('serve.js: refusing tailnet mode without an explicit, valid HOST.');
		process.exit(REFUSAL_EXIT_CODE);
	}
	const { resolveAuthConfig } = await import('./src/lib/server/auth/mode.js');
	const auth = resolveAuthConfig(process.env);
	if (auth.mode !== 'tailnet') {
		const problems = auth.mode === 'unconfigured' ? auth.problems.join(', ') : MODE_ENV;
		console.error(`serve.js: refusing tailnet mode; invalid or missing configuration: ${problems}.`);
		process.exit(REFUSAL_EXIT_CODE);
	}
} else {
	console.error(`serve.js: refusing ${MODE_ENV}; supported values are unset (loopback) or tailnet.`);
	process.exit(REFUSAL_EXIT_CODE);
}

if (mode === 'tailnet') {
	// adapter-node's own entry serves build/client (/_app/*, favicon, version.json) through sirv BEFORE
	// the SvelteKit hooks run, so the hook gate alone would leave static files reachable without an
	// Access identity. In tailnet mode this wrapper applies the same gate to EVERY request first and
	// only then hands it to the adapter's handler; the hooks still gate again (defence in depth).
	const http = await import('node:http');
	const { gateRequest, CF_ACCESS_JWT_HEADER } = await import('./src/lib/server/auth/gate.js');
	const { handler } = await import('./build/handler.js');
	const NO_STORE = { 'content-type': 'application/json', 'cache-control': 'no-store' };
	const server = http.createServer(async (req, res) => {
		let decision;
		try {
			const assertion = req.headers[CF_ACCESS_JWT_HEADER];
			decision = await gateRequest({
				env: { ...process.env },
				host: req.headers.host ?? null,
				assertion: typeof assertion === 'string' ? assertion : null
			});
		} catch {
			decision = null;
		}
		if (decision === null || decision.action !== 'resolve') {
			const status = decision === null ? 503 : decision.httpStatus;
			const body = decision === null ? { status: 'error', code: 'bff_auth_unconfigured',
				message: 'This app is not configured for hosted access.', upstream_status: null, upstream_code: null,
				upstream_detail_code: null } : decision.error;
			res.writeHead(status, NO_STORE);
			res.end(JSON.stringify(body));
			return;
		}
		handler(req, res, () => {
			res.writeHead(404, NO_STORE);
			res.end('{"status":"error","code":"not_found"}');
		});
	});
	const port = Number.parseInt(process.env.PORT || '3000', 10);
	server.listen(port, process.env.HOST, () => {
		console.log(`Listening on http://${process.env.HOST}:${port} (tailnet mode, gate before static files)`);
	});
	const close = () => server.close(() => process.exit(0));
	process.once('SIGTERM', close);
	process.once('SIGINT', close);
} else {
	await import('./build/index.js');
}
