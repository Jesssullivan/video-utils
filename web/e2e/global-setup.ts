// Starts the replay mock (in this process) and two copies of the built app (own process groups), then publishes
// their loopback URLs to the workers through the environment (WEB_TESTS_S3.md section 4.7).
// It never builds: a missing or stale build is refused with the typed code web_build_stale.
import { spawn, type ChildProcess } from 'node:child_process';
import { mkdirSync, readdirSync, rmSync, statSync, writeFileSync, existsSync } from 'node:fs';
import { createServer } from 'node:net';
import { fileURLToPath } from 'node:url';
import { chooseBrowser } from '../tests/browser-ladder';
import { MOCK_TOKEN, RULES, startMock } from './mock-control-api.mjs';

const WEB = fileURLToPath(new URL('..', import.meta.url));
const OUT = fileURLToPath(new URL('../../artifacts/s2/web_tests/', import.meta.url));
const START_TIMEOUT_MS = 30_000;

type Started = { mock: Awaited<ReturnType<typeof startMock>>; children: ChildProcess[] };
const holder = globalThis as unknown as { __webTestsE2E?: Started };

function newestSource(): { path: string; mtimeMs: number } {
	let newest = { path: '', mtimeMs: 0 };
	const visit = (path: string) => {
		const info = statSync(path);
		if (info.isDirectory()) {
			for (const name of readdirSync(path)) visit(`${path}/${name}`);
		} else if (info.mtimeMs > newest.mtimeMs) {
			newest = { path: path.slice(WEB.length), mtimeMs: info.mtimeMs };
		}
	};
	for (const entry of ['src', 'serve.js', 'package.json']) visit(`${WEB}${entry}`);
	return newest;
}

function assertBuildFresh(): void {
	const built = `${WEB}build/index.js`;
	if (!existsSync(built)) throw new Error('web_build_stale: web/build/index.js is missing; run `pnpm run build` first (this suite never builds implicitly)');
	const newest = newestSource();
	if (newest.mtimeMs > statSync(built).mtimeMs) {
		throw new Error(`web_build_stale: ${newest.path} is newer than build/index.js; run \`pnpm run build\` first`);
	}
}

const freePort = () =>
	new Promise<number>((resolve, reject) => {
		const probe = createServer();
		probe.once('error', reject);
		probe.listen(0, '127.0.0.1', () => {
			const address = probe.address();
			const port = typeof address === 'object' && address !== null ? address.port : 0;
			probe.close(() => resolve(port));
		});
	});

async function startApp(extra: Record<string, string>): Promise<{ child: ChildProcess; url: string }> {
	const port = await freePort();
	const env: Record<string, string> = {};
	for (const [name, value] of Object.entries(process.env)) {
		// The app gets a clean configuration: no inherited origin, auth mode or control API settings.
		if (value !== undefined && name !== 'ORIGIN' && name !== 'SOCKET_PATH' && !name.startsWith('VIDEO_UTILS_')) env[name] = value;
	}
	Object.assign(env, { HOST: '127.0.0.1', PORT: String(port), ...extra });
	// detached: the app runs in its own process group, the only group global teardown signals.
	const child = spawn(process.execPath, ['serve.js'], { cwd: WEB, env, detached: true, stdio: ['ignore', 'ignore', 'pipe'] });
	let stderr = '';
	child.stderr?.on('data', (chunk: Buffer) => (stderr = (stderr + chunk.toString('utf8')).slice(-2000)));
	const url = `http://127.0.0.1:${port}`;
	const deadline = Date.now() + START_TIMEOUT_MS;
	for (;;) {
		if (child.exitCode !== null) throw new Error(`e2e_app_start_failed: serve.js exited with code ${child.exitCode}: ${stderr.trim()}`);
		try {
			const response = await fetch(`${url}/upload`, { signal: AbortSignal.timeout(2000) });
			await response.arrayBuffer();
			if (response.status === 200) return { child, url };
		} catch {
			// not listening yet
		}
		if (Date.now() > deadline) throw new Error('e2e_app_start_failed: the built app did not answer within 30 s');
		await new Promise((resolve) => setTimeout(resolve, 150));
	}
}

function stopGroup(child: ChildProcess): void {
	if (child.pid === undefined || child.exitCode !== null) return;
	try {
		process.kill(-child.pid, 'SIGTERM');
	} catch {
		// the group is already gone
	}
}

export default async function globalSetup(): Promise<void> {
	mkdirSync(`${OUT}e2e`, { recursive: true });
	mkdirSync(`${OUT}a11y`, { recursive: true });
	const browser = chooseBrowser();
	const project = process.argv.find((argument) => argument.startsWith('--project='))?.slice('--project='.length) ?? 'all';
	const run = { started_at_utc: new Date().toISOString(), project, node_version: process.version, browser_ladder_step: browser.step, browser_source: browser.source, download_performed: false, mock_rules: RULES };
	writeFileSync(`${OUT}run-${project}.json`, `${JSON.stringify(run, null, 2)}\n`);
	if (project !== 'a11y') rmSync(`${OUT}metrics.jsonl`, { force: true });
	if (project !== 'e2e') {
		// A missing per-scan file must mean "that scan did not execute in this run".
		for (const name of readdirSync(`${OUT}a11y`)) if (name.endsWith('.json') && name !== 'report.json') rmSync(`${OUT}a11y/${name}`, { force: true });
	}
	if (browser.step === 'e_skip') {
		// Typed skip: every test reports skipped with this code; nothing is started and nothing counts as passed.
		process.env.E2E_SKIP_CODE = browser.skip_code;
		return;
	}
	assertBuildFresh();
	const mock = await startMock();
	const children: ChildProcess[] = [];
	holder.__webTestsE2E = { mock, children };
	// Backstop for an interrupted run: the groups are also signalled when this runner process exits.
	process.once('exit', () => children.forEach(stopGroup));
	try {
		const app = await startApp({ VIDEO_UTILS_CONTROL_API_URL: mock.url, VIDEO_UTILS_CONTROL_API_TOKEN: MOCK_TOKEN });
		children.push(app.child);
		const bare = await startApp({});
		children.push(bare.child);
		process.env.E2E_BASE_URL = app.url;
		process.env.E2E_UNCONFIGURED_URL = bare.url;
		process.env.E2E_MOCK_URL = mock.url;
	} catch (error) {
		children.forEach(stopGroup);
		await mock.close();
		throw error;
	}
}
