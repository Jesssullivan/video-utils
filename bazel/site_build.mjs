// Bazel runner for the static site in site/ (S3 bazel_full lane; SvelteKit 3
// and TypeScript 7 since the RU1 uplift, 2026-10-10).
//
// Copied into the site package by //site:site_build_runner so that Node
// resolves @sveltejs/kit, svelte-check and vite from that package's
// node_modules link tree. The site no longer reuses the web runner
// (//tools/bazel:web/sveltekit.mjs): SvelteKit 3 writes its generated
// tsconfig into node_modules/$app instead of .svelte-kit/tsconfig.json, and
// svelte-check runs in its TypeScript 7 native mode (`--tsgo`), which writes
// into .svelte-kit, so check and build need a writable scratch copy whose
// node_modules is a real directory (patterned on site.scaffold's
// scripts/bazel/*.mjs, U1).
//
//   sync                                        svelte-kit sync in the current directory
//   check --workspace <dir> [--canary]          svelte-check --tsgo on a scratch copy
//   build --workspace <dir> --registry <tools.json> --output-dir <dir>
//
// The build lays out <scratch>/site (a dereferenced copy of the declared
// workspace, with each declared node_modules entry linked in) and
// <scratch>/program/tools.json (a copy of the declared registry): the agents
// page's `prerender` remote function reads the registry from
// `<site>/../program/tools.json` at build time. It runs `vite build` in
// <scratch>/site and copies its build/ to the declared output directory.
// No network, no dev server, exactly one child process; Bazel bounds the
// action or test.
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
	symlinkSync,
	writeFileSync
} from 'node:fs';
import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';

const require = createRequire(import.meta.url);
const [mode, ...rest] = process.argv.slice(2);

function cli(packageName, relativePath) {
	return resolve(dirname(require.resolve(`${packageName}/package.json`)), relativePath);
}

function option(name) {
	const index = rest.indexOf(name);
	if (index < 0 || index + 1 >= rest.length) {
		throw new Error(`missing ${name} <value>`);
	}
	return rest[index + 1];
}

/**
 * Copy a declared tree into writable scratch as real files and directories.
 * Bazel hands actions their inputs as symlinks into read-only trees, and on
 * Node 22.22+ `cpSync(..., { dereference: true })` dereferences only the
 * top-level path, so nested symlinks would stay links into the read-only
 * sandbox. `statSync` and `copyFileSync` follow every symlink.
 */
function copyTreeDereferenced(source, destination) {
	if (statSync(source).isDirectory()) {
		mkdirSync(destination, { recursive: true });
		chmodSync(destination, 0o755);
		for (const entry of readdirSync(source)) {
			copyTreeDereferenced(join(source, entry), join(destination, entry));
		}
		return;
	}
	copyFileSync(source, destination);
	chmodSync(destination, 0o644);
}

/**
 * Give the scratch copy a real node_modules directory: SvelteKit 3 writes
 * node_modules/$app during sync and build. The declared node_modules/$app
 * (copied in with the workspace) is kept; every other declared entry is
 * symlinked in.
 */
function linkDeclaredNodeModules(declaredNodeModules, workspaceNodeModules) {
	mkdirSync(workspaceNodeModules, { recursive: true });
	for (const entry of readdirSync(declaredNodeModules)) {
		const target = join(workspaceNodeModules, entry);
		if (existsSync(target)) continue;
		symlinkSync(join(declaredNodeModules, entry), target);
	}
}

/** A writable scratch copy of a declared workspace; returns the copy's directory. */
function scratchCopy(declared, required, name) {
	for (const path of required) {
		if (!existsSync(join(declared, path))) {
			throw new Error(`declared site workspace is missing ${path}`);
		}
	}
	const nodeModules = join(dirname(declared), 'node_modules');
	if (!existsSync(nodeModules)) {
		throw new Error('declared inputs are missing node_modules');
	}
	const scratch = mkdtempSync(join(process.env.TEST_TMPDIR ?? tmpdir(), 'video-utils-site-'));
	process.once('exit', () => rmSync(scratch, { recursive: true, force: true }));
	const site = join(scratch, name);
	copyTreeDereferenced(declared, site);
	linkDeclaredNodeModules(nodeModules, join(site, 'node_modules'));
	return { scratch, site };
}

function run(script, args, options, after) {
	const child = spawn(process.execPath, [script, ...args], { stdio: 'inherit', ...options });
	child.on('error', (error) => {
		console.error(error);
		process.exit(1);
	});
	child.on('exit', (code, signal) => {
		let status = signal ? 1 : (code ?? 1);
		if (after) {
			try {
				status = after(status) ?? status;
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
	return child;
}

const REQUIRED = ['src', 'tsconfig.json', 'vite.config.ts', 'node_modules/$app/tsconfig.json', 'scripts/leak-scan-rules.json'];

if (mode === 'sync') {
	run(cli('@sveltejs/kit', 'svelte-kit.js'), ['sync', '--mode', 'production'], {}, (status) => {
		if (status !== 0) return status;
		// SvelteKit 3 writes the parent tsconfig ("$app/tsconfig") and the `$app/types`
		// declarations under node_modules/$app, and the route types under .svelte-kit.
		for (const generated of ['node_modules/$app/tsconfig.json', 'node_modules/$app/types', '.svelte-kit/types']) {
			if (!existsSync(generated)) throw new Error(`svelte-kit sync did not generate ${generated}`);
		}
		return 0;
	});
} else if (mode === 'check') {
	// RU13: TypeScript 7.0.2 is the site's `typescript`, so svelte-check runs in its
	// native mode (`--tsgo`); site/patches/svelte-check-4.7.6.patch lets it find
	// TypeScript 7 as `typescript`. --canary seeds one .ts and one .svelte type
	// error and fails unless both are reported: under --tsgo a tsconfig that
	// checks nothing reports 0 errors (sveltejs/language-tools#3136).
	const canary = rest.includes('--canary');
	const { site } = scratchCopy(resolve(option('--workspace')), REQUIRED, 'site');
	const seeded = ['src/lib/__tsgo_canary__.ts', 'src/lib/__TsgoCanary__.svelte'];
	if (canary) {
		writeFileSync(join(site, seeded[0]), "export const canary: number = 'not a number';\n");
		writeFileSync(join(site, seeded[1]), "<script lang=\"ts\">\n\tconst canary: number = 'not a number';\n</script>\n\n<p>{canary}</p>\n");
	}
	const args = ['--tsgo', '--tsconfig', './tsconfig.json', ...(canary ? ['--output', 'machine'] : [])];
	const child = spawn(process.execPath, [cli('svelte-check', 'bin/svelte-check'), ...args], {
		stdio: canary ? ['ignore', 'pipe', 'inherit'] : 'inherit',
		cwd: site
	});
	let output = '';
	child.stdout?.on('data', (chunk) => {
		output += chunk;
		process.stdout.write(chunk);
	});
	child.on('error', (error) => {
		console.error(error);
		process.exit(1);
	});
	child.on('exit', (code, signal) => {
		if (!canary) process.exit(signal ? 1 : (code ?? 1));
		const errors = output.split('\n').filter((line) => / ERROR /u.test(line));
		const missing = seeded.filter((file) => !errors.some((line) => line.includes(file)));
		if (code === 0 || missing.length > 0) {
			console.error(`svelte-check --tsgo canary FAILED: exit ${code}; seeded errors not reported in ${missing.join(', ') || '(none)'}`);
			process.exit(1);
		}
		console.log('svelte-check --tsgo canary: both seeded type errors were reported, the gate is live');
		process.exit(0);
	});
} else if (mode === 'build') {
	const registry = resolve(option('--registry'));
	const output = resolve(option('--output-dir'));
	if (!existsSync(registry)) {
		throw new Error('declared tool registry is missing');
	}
	const { scratch, site } = scratchCopy(resolve(option('--workspace')), REQUIRED, 'site');
	mkdirSync(join(scratch, 'program'));
	copyFileSync(registry, join(scratch, 'program', 'tools.json'));
	run(cli('vite', 'bin/vite.js'), ['build'], { cwd: site }, (status) => {
		if (status !== 0) return status;
		// site/vite.config.ts fixes the adapter-static output to ./build.
		cpSync(join(site, 'build'), output, { recursive: true });
		return 0;
	});
} else {
	console.error('usage: site_build.mjs sync | check --workspace <dir> [--canary] | build --workspace <dir> --registry <tools.json> --output-dir <dir>');
	process.exit(2);
}
