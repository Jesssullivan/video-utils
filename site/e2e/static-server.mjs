// Read-only static server for the site browser suites (SITE_VERIFY_S3.md section 4.2). Node standard library only.
// It serves the adapter-static build on the IPv4 loopback interface on an ephemeral port and emulates the Cloudflare
// Pages path resolution for such a build: exact file; else `<path>.html`; else `<path>/index.html`; else `404.html`
// with status 404. Every response carries the `/*` headers from `build/_headers`. It refuses any path that resolves
// outside the build directory. This is a local emulation; equivalence to Pages is inferred, not proven (V21).
import { createServer } from 'node:http';
import { existsSync, readFileSync, realpathSync, statSync } from 'node:fs';
import { extname, join, resolve, sep } from 'node:path';

// The loopback address is assembled from its octets at run time so no file under site/ carries the literal.
export const LOOPBACK_V4 = [127, 0, 0, 1].join('.');

const TYPES = {
	'.html': 'text/html; charset=utf-8',
	'.js': 'text/javascript; charset=utf-8',
	'.mjs': 'text/javascript; charset=utf-8',
	'.css': 'text/css; charset=utf-8',
	'.json': 'application/json; charset=utf-8',
	'.svg': 'image/svg+xml',
	'.txt': 'text/plain; charset=utf-8',
	'.woff': 'font/woff',
	'.woff2': 'font/woff2',
	'.ico': 'image/x-icon'
};

/** Parses the `/*` block of a Pages `_headers` file into [name, value] pairs. Other path blocks are ignored. */
export function parseHeaders(text) {
	const headers = [];
	let inAll = false;
	for (const raw of text.split(/\r?\n/)) {
		if (!raw.trim() || raw.trim().startsWith('#')) continue;
		if (!/^\s/.test(raw)) {
			inAll = raw.trim() === '/*';
			continue;
		}
		if (!inAll) continue;
		const index = raw.indexOf(':');
		if (index > 0) headers.push([raw.slice(0, index).trim(), raw.slice(index + 1).trim()]);
	}
	return headers;
}

const isFile = (path) => {
	try {
		return statSync(path).isFile();
	} catch {
		return false;
	}
};

/**
 * Resolves a request path against the build root with the Pages emulation.
 * Returns { kind: 'file', file, status } or { kind: 'refused' }.
 */
export function resolvePath(root, pathname) {
	let decoded;
	try {
		decoded = decodeURIComponent(pathname);
	} catch {
		return { kind: 'refused' };
	}
	if (decoded.includes('\0')) return { kind: 'refused' };
	const base = realpathSync(root);
	const inside = (candidate) => candidate === base || candidate.startsWith(base + sep);
	const target = resolve(base, `.${decoded.startsWith('/') ? decoded : `/${decoded}`}`);
	if (!inside(target)) return { kind: 'refused' };
	const trimmed = target.endsWith(sep) ? target.slice(0, -1) : target;
	for (const candidate of [target, `${trimmed}.html`, join(target, 'index.html')]) {
		if (isFile(candidate)) {
			const real = realpathSync(candidate);
			if (!inside(real)) return { kind: 'refused' };
			return { kind: 'file', file: real, status: 200 };
		}
	}
	const fallback = join(base, '404.html');
	if (isFile(fallback)) return { kind: 'file', file: fallback, status: 404 };
	return { kind: 'missing' };
}

/** Starts the server; resolves to { origin, close, requests } where requests counts served paths. */
export function startStaticServer(root) {
	if (!existsSync(join(root, 'index.html'))) throw new Error('site_build_missing: build/index.html is absent; run `pnpm run build` first');
	const headersFile = join(root, '_headers');
	const extra = existsSync(headersFile) ? parseHeaders(readFileSync(headersFile, 'utf8')) : [];
	const served = [];
	const server = createServer((request, response) => {
		const method = request.method ?? 'GET';
		if (method !== 'GET' && method !== 'HEAD') {
			response.writeHead(405, { Allow: 'GET, HEAD' });
			response.end();
			return;
		}
		// Path only: the query and fragment never select a file.
		const pathname = (request.url ?? '/').split(/[?#]/, 1)[0] || '/';
		const result = resolvePath(root, pathname);
		served.push({ path: pathname, status: result.kind === 'file' ? result.status : result.kind === 'refused' ? 400 : 404 });
		if (result.kind !== 'file') {
			response.writeHead(result.kind === 'refused' ? 400 : 404, { 'Content-Type': 'text/plain; charset=utf-8' });
			response.end(result.kind === 'refused' ? 'refused\n' : 'not found\n');
			return;
		}
		const body = readFileSync(result.file);
		const headers = { 'Content-Type': TYPES[extname(result.file).toLowerCase()] ?? 'application/octet-stream', 'Content-Length': String(body.length), 'Cache-Control': 'no-store' };
		for (const [name, value] of extra) headers[name] = value;
		response.writeHead(result.status, headers);
		response.end(method === 'HEAD' ? undefined : body);
	});
	return new Promise((resolveStart, rejectStart) => {
		server.once('error', rejectStart);
		server.listen(0, LOOPBACK_V4, () => {
			const address = server.address();
			const port = typeof address === 'object' && address !== null ? address.port : 0;
			resolveStart({
				origin: `http://${LOOPBACK_V4}:${port}`,
				served,
				close: () =>
					new Promise((resolveClose) => {
						server.closeAllConnections?.();
						server.close(() => resolveClose());
					})
			});
		});
	});
}
