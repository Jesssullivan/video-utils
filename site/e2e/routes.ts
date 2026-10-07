// Route enumeration, viewport configurations and output locations for the site browser suites
// (SITE_VERIFY_S3.md sections 4.2, 5.1 and 6.3). Routes are read from the HTML files present in the build at run time;
// the route count R is never hardcoded. Outputs go only under SITE_VERIFY_OUT_DIR (never inside site/).
import { existsSync, mkdirSync, readdirSync, statSync, writeFileSync } from 'node:fs';
import { isAbsolute, join, relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

export const SITE_DIR = fileURLToPath(new URL('..', import.meta.url));
export const BUILD_DIR = join(SITE_DIR, 'build');
export const NOT_FOUND_PROBE = '/site-verify-not-found';
export const FALLBACK_HEADING = 'Page not found';
/** Section 5.4, frozen before any run: the build intends no request to any other origin. */
export const BUILD_INTENDED_EXTERNAL: readonly string[] = [];

export type Route = { id: string; path: string; file: string; kind: 'content' | 'not_found_probe'; expected_status: 200 | 404 };
export type Viewport = { id: string; width: number; height: number; deviceScaleFactor: number; meaning: string };

/** Section 5.1, frozen. `z200` is a viewport emulation of a 1280 x 800 window at 200 percent zoom. */
export const VIEWPORTS: readonly Viewport[] = [
	{ id: 'w375', width: 375, height: 812, deviceScaleFactor: 1, meaning: 'small phone width' },
	{ id: 'w390', width: 390, height: 844, deviceScaleFactor: 1, meaning: 'current phone width' },
	{ id: 'w768', width: 768, height: 1024, deviceScaleFactor: 1, meaning: 'tablet portrait' },
	{ id: 'w1280', width: 1280, height: 800, deviceScaleFactor: 1, meaning: 'desktop' },
	{ id: 'z200', width: 640, height: 400, deviceScaleFactor: 2, meaning: '1280 x 800 window at 200 percent zoom (viewport emulation)' }
];
export const viewport = (id: string): Viewport => {
	const found = VIEWPORTS.find((entry) => entry.id === id);
	if (!found) throw new Error(`unknown viewport ${id}`);
	return found;
};

/** Every HTML document in the build, excluding the hashed framework tree. */
export function htmlFiles(build: string = BUILD_DIR): string[] {
	const found: string[] = [];
	const visit = (directory: string) => {
		for (const name of readdirSync(directory).sort()) {
			const path = join(directory, name);
			if (statSync(path).isDirectory()) {
				if (name !== '_app') visit(path);
			} else if (name.endsWith('.html')) {
				found.push(relative(build, path).split(sep).join('/'));
			}
		}
	};
	visit(build);
	return found;
}

/** index.html -> '/', <name>.html -> '/<name>', <dir>/index.html -> '/<dir>', 404.html -> the not-found probe. */
export function routeFor(file: string): Route {
	if (file === '404.html') return { id: 'not-found', path: NOT_FOUND_PROBE, file, kind: 'not_found_probe', expected_status: 404 };
	const stem = file.replace(/(^|\/)index\.html$/, '').replace(/\.html$/, '');
	const path = `/${stem}`;
	return { id: stem === '' ? 'home' : stem.replace(/\//g, '-'), path, file, kind: 'content', expected_status: 200 };
}

export function readRoutes(build: string = BUILD_DIR): Route[] {
	if (!existsSync(join(build, 'index.html'))) throw new Error('site_build_missing: build/index.html is absent; run `pnpm run build` first');
	return htmlFiles(build).map(routeFor);
}

export const ROUTES: readonly Route[] = readRoutes();

export function outDir(): string {
	const value = process.env.SITE_VERIFY_OUT_DIR;
	if (!value || !isAbsolute(value)) {
		throw new Error('site_verify_out_dir_required: set SITE_VERIFY_OUT_DIR to an absolute directory outside site/');
	}
	const rel = relative(SITE_DIR, value);
	if (rel === '' || (!rel.startsWith('..') && !isAbsolute(rel))) {
		throw new Error('site_verify_out_dir_required: SITE_VERIFY_OUT_DIR must be outside site/');
	}
	return value;
}

export function writeJson(subdirectory: string, name: string, value: unknown): void {
	const directory = join(outDir(), subdirectory);
	mkdirSync(directory, { recursive: true });
	writeFileSync(join(directory, `${name}.json`), `${JSON.stringify(value, null, 2)}\n`);
}
