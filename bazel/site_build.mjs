// Bazel build runner for the static site in site/ (S3 bazel_full lane).
//
// Copied into the site package by //site:site_build_runner so that Node
// resolves vite from that package's node_modules link tree. Type checking and
// `svelte-kit sync` reuse the shared runner //tools/bazel:web/sveltekit.mjs
// unchanged; only the build needs this file, because the site's agents page
// reads the repository tool registry at prerender time from
// `<site>/../program/tools.json` (site/src/routes/agents/+page.server.ts), and
// the shared runner builds in a scratch directory with no such sibling.
//
//   build --workspace <dir> --registry <tools.json> --output-dir <dir>
//
// Lays out <scratch>/site (a dereferenced copy of the declared workspace, with
// node_modules symlinked) and <scratch>/program/tools.json (a copy of the
// declared registry), runs `vite build` in <scratch>/site and copies its
// build/ to the declared output directory. No network, no dev server, exactly
// one child process; Bazel bounds the action.
import { spawn } from 'node:child_process';
import {
	chmodSync,
	copyFileSync,
	cpSync,
	existsSync,
	mkdirSync,
	mkdtempSync,
	readdirSync,
	rmSync,
	statSync,
	symlinkSync
} from 'node:fs';
import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';

const require = createRequire(import.meta.url);
const [mode, ...rest] = process.argv.slice(2);

function option(name) {
	const index = rest.indexOf(name);
	if (index < 0 || index + 1 >= rest.length) {
		throw new Error(`missing ${name} <value>`);
	}
	return rest[index + 1];
}

function chmodTree(path) {
	if (statSync(path).isDirectory()) {
		chmodSync(path, 0o755);
		for (const entry of readdirSync(path)) {
			chmodTree(join(path, entry));
		}
	} else {
		chmodSync(path, 0o644);
	}
}

if (mode !== 'build') {
	console.error('usage: site_build.mjs build --workspace <dir> --registry <tools.json> --output-dir <dir>');
	process.exit(2);
}

const declared = resolve(option('--workspace'));
const registry = resolve(option('--registry'));
const output = resolve(option('--output-dir'));
for (const required of ['src', 'svelte.config.js', 'vite.config.ts', '.svelte-kit/tsconfig.json', 'scripts/leak-scan-rules.json']) {
	if (!existsSync(join(declared, required))) {
		throw new Error(`declared site workspace is missing ${required}`);
	}
}
if (!existsSync(registry)) {
	throw new Error('declared tool registry is missing');
}
const nodeModules = join(dirname(declared), 'node_modules');
if (!existsSync(nodeModules)) {
	throw new Error('declared build inputs are missing node_modules');
}

const scratch = mkdtempSync(join(tmpdir(), 'video-utils-site-build-'));
const site = join(scratch, 'site');
process.once('exit', () => rmSync(scratch, { recursive: true, force: true }));
cpSync(declared, site, { recursive: true, dereference: true });
chmodTree(site);
symlinkSync(nodeModules, join(site, 'node_modules'), 'dir');
mkdirSync(join(scratch, 'program'));
copyFileSync(registry, join(scratch, 'program', 'tools.json'));

const vite = resolve(dirname(require.resolve('vite/package.json')), 'bin/vite.js');
const child = spawn(process.execPath, [vite, 'build'], { stdio: 'inherit', cwd: site });
child.on('error', (error) => {
	console.error(error);
	process.exit(1);
});
child.on('exit', (code, signal) => {
	let status = signal ? 1 : (code ?? 1);
	if (status === 0) {
		try {
			// site/svelte.config.js fixes the adapter-static output to ./build.
			cpSync(join(site, 'build'), output, { recursive: true });
		} catch (error) {
			console.error(error);
			status = 1;
		}
	}
	process.exit(status);
});
for (const signal of ['SIGINT', 'SIGTERM']) {
	process.once(signal, () => child.kill(signal));
}
