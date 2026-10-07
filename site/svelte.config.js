import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/**
 * Static public landing. Every route is prerendered (src/routes/+layout.ts);
 * there is no server, no endpoint and no form action. Derived from the
 * site.scaffold public template, with stricter prerender handling and no
 * precompression (compressed twins would be opaque to the leak scanner).
 * @type {import('@sveltejs/kit').Config}
 */
const config = {
	preprocess: vitePreprocess(),
	compilerOptions: {
		runes: true
	},
	kit: {
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
	}
};

export default config;
