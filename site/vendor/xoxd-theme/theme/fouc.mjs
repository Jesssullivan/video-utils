export const THEME_ID = 'xoxd';


export const COLOR_MODE_KEY = 'color-mode';


export const DEFAULT_MODE = 'dark';

export const FOUC_SCRIPT = `(function () {
	try {
		var stored = localStorage.getItem('${COLOR_MODE_KEY}');
		var mode = '${DEFAULT_MODE}';
		if (stored === 'light' || stored === 'dark') {
			mode = stored;
		} else if (stored === 'system') {
			mode = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
		}
		document.documentElement.setAttribute('data-mode', mode);
		document.documentElement.style.colorScheme = mode;
		document.documentElement.setAttribute('data-theme', '${THEME_ID}');
	} catch (e) {
	}
})();`;
