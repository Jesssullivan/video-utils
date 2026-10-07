import { FOUC_SCRIPT } from '@xoxd/public-chrome/fouc';
import type { Handle } from '@sveltejs/kit';

// Template convention: the shared pre-paint theme script is injected at build
// time so the theme list lives in one place (the chrome), not in app.html.
export const handle: Handle = async ({ event, resolve }) =>
	resolve(event, {
		transformPageChunk: ({ html }) =>
			html.replace('</head>', `<script>${FOUC_SCRIPT.replace(/<\/script/gi, '<\\/script')}</script></head>`)
	});
