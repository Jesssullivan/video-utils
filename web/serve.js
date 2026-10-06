// Loopback-only launcher for the adapter-node build (WEB_STACK_S2.md section 5.4).
// adapter-node defaults HOST to the all-interfaces wildcard; this wrapper defaults it to 127.0.0.1 and
// refuses any other host with exit code 2 BEFORE the server module is imported.
const LOOPBACK_HOSTS = new Set(['127.0.0.1', '::1']);
const REFUSAL_EXIT_CODE = 2;

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

await import('./build/index.js');
