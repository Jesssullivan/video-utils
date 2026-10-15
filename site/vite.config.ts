import adapter from '@sveltejs/adapter-static';
import { sveltekit } from '@sveltejs/kit/vite';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';

/**
 * Static public landing. Every route is prerendered (src/routes/+layout.ts);
 * there is no server, no endpoint and no form action. Derived from the
 * site.scaffold public template, with stricter prerender handling and no
 * precompression (compressed twins would be opaque to the leak scanner).
 *
 * SvelteKit 3 no longer reads svelte.config.js: the former `kit.*` options are
 * top-level options of the sveltekit() plugin, beside compilerOptions and
 * preprocess. No source maps reach the published build.
 */
export default defineConfig({
	plugins: [
		tailwindcss(),
		sveltekit({
			preprocess: vitePreprocess(),
			compilerOptions: {
				runes: true,
				// Remote functions (RU3) need Svelte's async mode: the agents page
				// awaits its build-time `prerender` remote function directly.
				experimental: { async: true }
			},
			// RU3: SvelteKit remote functions are the estate pattern for server
			// data. Still behind the experimental flag in Kit 3.0.x.
			experimental: { remoteFunctions: true },
			adapter: adapter({
				pages: 'build',
				assets: 'build',
				fallback: '404.html',
				precompress: false,
				strict: true
			}),
			paths: {
				base: ''
			},
			prerender: {
				handleHttpError: 'fail',
				handleMissingId: 'fail',
				handleUnseenRoutes: 'fail'
			}
		})
	],
	build: { sourcemap: false }
});
