import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';

// No source maps reach the published build.
export default defineConfig({
	plugins: [tailwindcss(), sveltekit()],
	build: { sourcemap: false }
});
