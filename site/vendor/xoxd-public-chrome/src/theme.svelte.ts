const browser = typeof window !== 'undefined';
import { DEFAULT_THEME_ID, THEME_IDS, isThemeId, type ThemeId } from './theme/suite';


export type ColorMode = 'light' | 'dark' | 'system';

export const COLOR_MODES = ['light', 'dark', 'system'] as const;


export const DEFAULT_COLOR_MODE: ColorMode = 'dark';


export const KNOWN_THEMES: readonly ThemeId[] = THEME_IDS;
export const DEFAULT_THEME: ThemeId = DEFAULT_THEME_ID;

const THEME_KEY = 'skeleton-theme';
const MODE_KEY = 'color-mode';

function isColorMode(value: unknown): value is ColorMode {
	return typeof value === 'string' && (COLOR_MODES as readonly string[]).includes(value);
}

function readStorage(key: string): string | null {
	try {
		return localStorage.getItem(key);
	} catch {
		return null;
	}
}

function writeStorage(key: string, value: string) {
	try {
		localStorage.setItem(key, value);
	} catch {
	}
}

function removeStorage(key: string) {
	try {
		localStorage.removeItem(key);
	} catch {
	}
}

function prefersDark(): boolean {
	return browser && window.matchMedia('(prefers-color-scheme: dark)').matches;
}

class ThemeStore {
	mode = $state<ColorMode>(DEFAULT_COLOR_MODE);
	currentTheme = $state<ThemeId>(DEFAULT_THEME);
	private initialized = false;
	private systemDark = $state(false);
	isDark = $derived(this.mode === 'dark' || (this.mode === 'system' && this.systemDark));

	init() {
		if (!browser || this.initialized) return;
		this.initialized = true;
		this.systemDark = prefersDark();

		const storedMode = readStorage(MODE_KEY);
		const storedTheme = readStorage(THEME_KEY);

		this.mode = isColorMode(storedMode) ? storedMode : DEFAULT_COLOR_MODE;

		if (isThemeId(storedTheme)) {
			this.currentTheme = storedTheme;
		} else {
			if (storedTheme !== null) removeStorage(THEME_KEY);
			this.currentTheme = DEFAULT_THEME;
		}

		this.applyMode();
		this.applyTheme();

		window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (event) => {
			this.systemDark = event.matches;
			if (this.mode === 'system') this.applyMode();
		});
	}

	setMode(mode: ColorMode) {
		this.mode = mode;
		if (browser) {
			writeStorage(MODE_KEY, mode);
			this.applyMode();
		}
	}

	setTheme(themeId: ThemeId) {
		this.currentTheme = themeId;
		if (browser) {
			writeStorage(THEME_KEY, themeId);
			this.applyTheme();
		}
	}

	private applyMode() {
		if (!browser) return;
		const resolved = this.mode === 'system' ? (prefersDark() ? 'dark' : 'light') : this.mode;
		document.documentElement.setAttribute('data-mode', resolved);
		document.documentElement.style.colorScheme = resolved;
	}

	private applyTheme() {
		if (!browser) return;
		document.documentElement.setAttribute('data-theme', this.currentTheme);
	}
}

export const theme = new ThemeStore();
