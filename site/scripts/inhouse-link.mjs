// `just site-install` step 2: build the in-house packages through Bazel and
// materialise each into site/node_modules/<package> for the plain pnpm/Vite
// loop (rulings N2 and RU9; the xoxd.ai pattern).
//
// site/BUILD.bazel links each registry module with
// `npm_link_package(name = "node_modules/<package>", src = "@<module>//:pkg")`.
// This script builds those `:pkg` targets through the bounded launcher
// (tools/bazel/run.py), copies each output directory (dereferencing
// symlinks) into site/node_modules/<package>, and asserts that each copied
// package.json carries the name and the exact version MODULE.bazel pins, so a
// stale Bazel output cannot masquerade as the pin. site/package.json and
// site/pnpm-lock.yaml carry no in-house package, so run this AFTER
// `pnpm install --frozen-lockfile`: pnpm never installs, prunes or shadows
// these directories. It never touches the network itself; Bazel fetches the
// module archives from the pinned registry and checks their integrity.
//
//   node scripts/inhouse-link.mjs            build, materialise and verify
//   node scripts/inhouse-link.mjs --verify   verify the materialised copies only
import { execFileSync } from 'node:child_process';
import { chmodSync, cpSync, existsSync, mkdirSync, readFileSync, readdirSync, rmSync, statSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const SITE = fileURLToPath(new URL('..', import.meta.url));
const REPO = dirname(SITE.replace(/\/$/, ''));

function readLinks() {
	const build = readFileSync(join(SITE, 'BUILD.bazel'), 'utf8');
	const links = new Map();
	const pattern = /npm_link_package\(\s*name = "node_modules\/([^"]+)",\s*src = "@([A-Za-z0-9_.-]+)\/\/:pkg",\s*\)/g;
	for (const match of build.matchAll(pattern)) links.set(match[1], match[2]);
	return links;
}

function readPins() {
	const module = readFileSync(join(REPO, 'MODULE.bazel'), 'utf8');
	const pins = new Map();
	for (const match of module.matchAll(/bazel_dep\(name = "([^"]+)", version = "([^"]+)"\)/g)) pins.set(match[1], match[2]);
	return pins;
}

function makeWritable(path) {
	const info = statSync(path);
	chmodSync(path, info.isDirectory() ? 0o755 : 0o644);
	if (info.isDirectory()) for (const entry of readdirSync(path)) makeWritable(join(path, entry));
}

function main() {
	const verifyOnly = process.argv.includes('--verify');
	const links = readLinks();
	const pins = readPins();
	if (links.size === 0) throw new Error('inhouse-link: site/BUILD.bazel links no in-house package');
	if (!existsSync(join(SITE, 'node_modules'))) {
		throw new Error('inhouse-link: site/node_modules is missing; run `pnpm install --frozen-lockfile` in site/ first');
	}
	const packages = [...links].sort(([a], [b]) => a.localeCompare(b));
	if (!verifyOnly) {
		// The module `:pkg` directories are what get copied, so they are built as
		// top-level targets: on a disk-cache hit Bazel materialises only top-level
		// outputs, which can leave an intermediate tree artifact empty on disk.
		execFileSync(
			'python3',
			[
				join(REPO, 'tools/bazel/run.py'),
				'--timeout',
				'1800',
				'build',
				...packages.map(([, module]) => `@${module}//:pkg`),
				...packages.map(([name]) => `//site:node_modules/${name}`)
			],
			{ cwd: REPO, stdio: 'inherit' }
		);
	}
	const failures = [];
	for (const [name, module] of packages) {
		const target = join(SITE, 'node_modules', name);
		if (!verifyOnly) {
			// .bazelrc puts the convenience symlinks under .local/bazel/; a bazel_dep's
			// canonical repository name is `<module>+` under Bzlmod.
			const output = join(REPO, '.local/bazel/bin/external', `${module}+`, 'pkg');
			if (!existsSync(join(output, 'package.json'))) {
				failures.push(`@${module}//:pkg produced no package directory at ${output.slice(REPO.length + 1)}`);
				continue;
			}
			rmSync(target, { recursive: true, force: true });
			mkdirSync(dirname(target), { recursive: true });
			cpSync(output, target, { recursive: true, dereference: true });
			// Bazel outputs are read-only; make the copy writable so the next run can replace it.
			makeWritable(target);
		}
		if (!existsSync(join(target, 'package.json'))) {
			failures.push(`${name} is not materialised in site/node_modules`);
			continue;
		}
		const manifest = JSON.parse(readFileSync(join(target, 'package.json'), 'utf8'));
		if (manifest.name !== name) failures.push(`@${module}//:pkg is "${manifest.name}", expected "${name}"`);
		if (manifest.version !== pins.get(module)) {
			failures.push(`${name}@${manifest.version} is materialised, MODULE.bazel pins ${module} ${pins.get(module)}`);
		}
	}
	if (failures.length > 0) {
		console.error('inhouse-link: the materialised in-house packages do not match the pins');
		for (const failure of failures) console.error(`  - ${failure}`);
		process.exit(1);
	}
	console.log(`inhouse-link: ${packages.map(([name]) => `${name}@${pins.get(links.get(name))}`).join(', ')} ${verifyOnly ? 'verified' : 'linked from Bazel'} in site/node_modules`);
}

main();
