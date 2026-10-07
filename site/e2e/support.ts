// Shared helpers for the site browser suites (SITE_VERIFY_S3.md sections 5 and 6): the server origin published by
// global setup, the typed browser skip, a context that aborts every request leaving the local origin (never fulfilled
// from the network) and records it, and hydration evidence. No request is ever allowed to reach another origin.
import { test, type Browser, type BrowserContext, type Page } from '@playwright/test';
import type { Viewport } from './routes';

export const SKIP_ENV = 'SITE_VERIFY_SKIP_CODE';
export const ORIGIN_ENV = 'SITE_VERIFY_ORIGIN';
export const START_MODULE = /\/_app\/immutable\/entry\/start\.[^/]+\.js$/;

export function origin(): string {
	const value = process.env[ORIGIN_ENV];
	if (!value) throw new Error('site_verify_origin_missing: global setup did not publish the local server origin');
	return value;
}

/** Typed skip when the browser ladder found no Chromium (nothing counts as passed). */
export function skipWhenNoBrowser(): void {
	const code = process.env[SKIP_ENV];
	test.skip(Boolean(code), code ?? '');
}

export type Traffic = { requests: string[]; external: string[]; startModuleStatus: number | null };

const isLocal = (url: URL, base: string) => url.origin === base || url.protocol === 'data:' || url.protocol === 'blob:';

export async function openContext(
	browser: Browser,
	view: Viewport,
	options: { colorScheme?: 'light' | 'dark'; storedMode?: 'light' | 'dark' } = {}
): Promise<{ context: BrowserContext; page: Page; traffic: Traffic }> {
	const base = origin();
	const context = await browser.newContext({
		viewport: { width: view.width, height: view.height },
		deviceScaleFactor: view.deviceScaleFactor,
		colorScheme: options.colorScheme,
		serviceWorkers: 'block'
	});
	const traffic: Traffic = { requests: [], external: [], startModuleStatus: null };
	// Every request to another origin is aborted here and listed; nothing is fetched from the network.
	await context.route(
		(url) => !isLocal(url, base),
		async (route) => {
			traffic.external.push(route.request().url());
			await route.abort('blockedbyclient');
		}
	);
	context.on('request', (request) => traffic.requests.push(request.url()));
	context.on('response', (response) => {
		const url = new URL(response.url());
		if (url.origin === base && START_MODULE.test(url.pathname)) traffic.startModuleStatus = response.status();
	});
	if (options.storedMode) {
		await context.addInitScript((mode: string) => {
			try {
				localStorage.setItem('color-mode', mode);
			} catch {
				// storage unavailable: the mode assertion will fail the scan
			}
		}, options.storedMode);
	}
	const page = await context.newPage();
	return { context, page, traffic };
}

/** Navigates and waits for the client to render the route heading (the fallback renders it client-side). */
export async function visit(page: Page, path: string): Promise<number | null> {
	const response = await page.goto(`${origin()}${path}`, { waitUntil: 'load' });
	await page.waitForLoadState('networkidle');
	await page
		.locator('main#content h1')
		.first()
		.waitFor({ state: 'visible', timeout: 10_000 })
		.catch(() => undefined);
	return response ? response.status() : null;
}
