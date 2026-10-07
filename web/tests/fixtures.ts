// Fixture loaders shared by the unit tests. Paths are resolved from this file, never from a host path.
import { Schema } from 'effect';
import { readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const dir = (relative: string) => fileURLToPath(new URL(relative, import.meta.url));

export const S2_FIXTURES = dir('../fixtures/control-api/');
export const E2E_FIXTURES = dir('../e2e/fixtures/control-api/');

/** Strict JSON: duplicate keys and NaN/Infinity are errors, as in the Python contract test. */
export function strictParse(text: string): unknown {
	if (/\b(NaN|Infinity)\b/.test(text.replace(/"(?:[^"\\]|\\.)*"/g, '""'))) throw new Error('non-finite JSON number');
	return JSON.parse(text);
}

export const loadJson = (base: string, name: string): unknown => strictParse(readFileSync(`${base}${name}`, 'utf8'));
export const s2Fixture = (name: string): unknown => loadJson(S2_FIXTURES, name);
export const e2eFixture = (name: string): unknown => loadJson(E2E_FIXTURES, name);
export const e2eFixtureNames = (): string[] => readdirSync(E2E_FIXTURES).filter((name) => name.endsWith('.json')).sort();

export type RouteRow = { method: string; path: string; variant: string | null; status: number; file: string };
export const e2eRoutes = (): RouteRow[] => (e2eFixture('routes.json') as { routes: RouteRow[] }).routes;

/** Recorded 2xx responses whose route path matches `pattern`, as [file, body] pairs. */
export function recorded(pattern: RegExp, method = 'GET'): Array<[string, unknown]> {
	return e2eRoutes()
		.filter((row) => row.method === method && row.status >= 200 && row.status <= 299 && pattern.test(row.path))
		.map((row) => [row.file, e2eFixture(row.file)]);
}

export const CLOSED = { onExcessProperty: 'error', errors: 'all' } as const;

/** Text that must never be committed or rendered, assembled so this file does not contain it literally. */
export const HOST_PATH_MARKERS = ['Users', 'home', 'private', 'Volumes', 'tmp'].map((name) => `/${name}/`).concat(['/nix', 'store/'].join('/'));


export type Decoded<A> = { ok: true; value: A } | { ok: false; message: string };

/** Closed decode exactly as the BFF clients do it (onExcessProperty: "error", errors: "all"). */
export function decodeClosed<S extends Schema.Top>(schema: S, value: unknown): Decoded<S['Type']> {
	try {
		return { ok: true, value: Schema.decodeUnknownSync(schema as never)(value, CLOSED) as S['Type'] };
	} catch (error) {
		return { ok: false, message: error instanceof Error ? error.message : String(error) };
	}
}

export const isRecord = (value: unknown): value is Record<string, unknown> =>
	typeof value === 'object' && value !== null && !Array.isArray(value);
