// Bazel runner for the SvelteKit app in web/ (adapted from site.scaffold's
// scripts/bazel/run-*.mjs). Copied into the web package by //web:sveltekit_runner
// so that Node resolves the CLIs from that package's node_modules link tree.
//
//   sync                                      svelte-kit sync in the current directory
//   check                                     svelte-check --tsconfig ./tsconfig.json
//   build --workspace <dir> --output-dir <dir>  vite build of a declared workspace
//
// No network, no dev server. Bazel bounds the action or test; this file adds no
// timeout of its own and starts exactly one child process per invocation.
import { spawn } from 'node:child_process';
import {
	chmodSync,
	cpSync,
	existsSync,
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

function cli(packageName, relativePath) {
	return resolve(dirname(require.resolve(`${packageName}/package.json`)), relativePath);
}

function run(script, args, options, after) {
	const child = spawn(process.execPath, [script, ...args], { stdio: 'inherit', ...options });
	child.on('error', (error) => {
		console.error(error);
		process.exit(1);
	});
	child.on('exit', (code, signal) => {
		let status = signal ? 1 : (code ?? 1);
		if (status === 0 && after) {
			try {
				after();
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
}

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

if (mode === 'sync') {
	run(cli('@sveltejs/kit', 'svelte-kit.js'), ['sync'], {}, () => {
		if (!existsSync('.svelte-kit/tsconfig.json')) {
			throw new Error('svelte-kit sync did not generate .svelte-kit/tsconfig.json');
		}
	});
} else if (mode === 'check') {
	run(cli('svelte-check', 'bin/svelte-check'), ['--tsconfig', './tsconfig.json', ...rest], {});
} else if (mode === 'build') {
	const declared = resolve(option('--workspace'));
	const output = resolve(option('--output-dir'));
	for (const required of ['src', 'svelte.config.js', 'vite.config.ts', '.svelte-kit/tsconfig.json']) {
		if (!existsSync(join(declared, required))) {
			throw new Error(`declared build workspace is missing ${required}`);
		}
	}
	const nodeModules = join(dirname(declared), 'node_modules');
	if (!existsSync(nodeModules)) {
		throw new Error('declared build inputs are missing node_modules');
	}
	const scratch = mkdtempSync(join(tmpdir(), 'video-utils-web-build-'));
	const workspace = join(scratch, 'workspace');
	process.once('exit', () => rmSync(scratch, { recursive: true, force: true }));
	cpSync(declared, workspace, { recursive: true, dereference: true });
	chmodTree(workspace);
	symlinkSync(nodeModules, join(workspace, 'node_modules'), 'dir');
	// web/svelte.config.js fixes the adapter-node output to ./build.
	run(cli('vite', 'bin/vite.js'), ['build'], { cwd: workspace }, () => {
		cpSync(join(workspace, 'build'), output, { recursive: true });
	});
} else {
	console.error('usage: sveltekit.mjs sync | check | build --workspace <dir> --output-dir <dir>');
	process.exit(2);
}
