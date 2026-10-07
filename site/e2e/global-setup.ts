// Starts the read-only static server in this runner process and publishes its origin to the workers through the
// environment (SITE_VERIFY_S3.md section 4.2). It never builds: a missing or stale build is refused with a typed code.
// The browser ladder runs here once; a typed skip (e2e_browser_unavailable) starts nothing and passes nothing.
import { mkdirSync, readdirSync, rmSync, statSync, writeFileSync, existsSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { chooseBrowser } from '../tests/browser-ladder';
import { BUILD_DIR, ROUTES, SITE_DIR, outDir } from './routes';
import { ORIGIN_ENV, SKIP_ENV } from './support';
import { startStaticServer } from './static-server.mjs';

type Started = { close: () => Promise<void> };
const holder = globalThis as unknown as { __siteVerifyServer?: Started };

/** The newest authored input of the build; the build must be at least as new. */
function newestInput(): { path: string; mtimeMs: number } {
	let newest = { path: '', mtimeMs: 0 };
	const visit = (path: string) => {
		const info = statSync(path);
		if (info.isDirectory()) {
			for (const name of readdirSync(path)) visit(join(path, name));
		} else if (info.mtimeMs > newest.mtimeMs) {
			newest = { path: path.slice(SITE_DIR.length), mtimeMs: info.mtimeMs };
		}
	};
	for (const entry of ['src', 'static', 'vendor', 'package.json', 'svelte.config.js', 'vite.config.ts']) {
		if (existsSync(join(SITE_DIR, entry))) visit(join(SITE_DIR, entry));
	}
	return newest;
}

function assertBuildFresh(): void {
	const built = join(BUILD_DIR, 'index.html');
	if (!existsSync(built)) throw new Error('site_build_missing: build/index.html is absent; run `pnpm run build` first (this suite never builds)');
	const newest = newestInput();
	if (newest.mtimeMs > statSync(built).mtimeMs) {
		throw new Error(`site_build_stale: ${newest.path} is newer than build/index.html; run \`pnpm run build\` first`);
	}
}

/** Directory names in the Playwright browser cache, recorded before and after the run (V16: nothing downloaded). */
export function browserCacheEntries(): string[] {
	const root =
		process.env.PLAYWRIGHT_BROWSERS_PATH ||
		(process.platform === 'darwin' ? join(homedir(), 'Library', 'Caches', 'ms-playwright') : join(homedir(), '.cache', 'ms-playwright'));
	try {
		return readdirSync(root).filter((name) => !name.startsWith('.')).sort();
	} catch {
		return [];
	}
}

export default async function globalSetup(): Promise<void> {
	const out = outDir();
	mkdirSync(out, { recursive: true });
	// A missing per-case file must mean "that case did not execute in this run".
	for (const sub of ['smoke', 'skip-link', 'a11y']) rmSync(join(out, sub), { recursive: true, force: true });
	rmSync(join(out, 'browser-summary.json'), { force: true });
	const browser = chooseBrowser();
	const run = {
		started_at_utc: new Date().toISOString(),
		node_version: process.version,
		browser_ladder_step: browser.step,
		browser_source: browser.source,
		download_performed: false,
		browser_cache_entries_before: browserCacheEntries(),
		routes: ROUTES
	};
	writeFileSync(join(out, 'run.json'), `${JSON.stringify(run, null, 2)}\n`);
	if (browser.step === 'e_skip') {
		process.env[SKIP_ENV] = browser.skip_code;
		return;
	}
	assertBuildFresh();
	const server = await startStaticServer(BUILD_DIR);
	holder.__siteVerifyServer = server;
	process.env[ORIGIN_ENV] = server.origin;
}
