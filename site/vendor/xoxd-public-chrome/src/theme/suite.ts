export interface ThemeOption { readonly id: string; readonly label: string; readonly colors: readonly [string, string, string]; }
export const DEFAULT_THEME_ID = 'xoxd';
export const THEMES = [
	{ id: 'xoxd', label: 'xoxd.ai', colors: ['#cc003b', '#659bd2', '#682893'] },
	{ id: 'scaffold', label: 'Scaffold', colors: ['#5f636a', '#69615f', '#666167'] },
	{ id: 'pine', label: 'Pine', colors: ['#a0814d', '#57123c', '#878678'] },
	{ id: 'rose', label: 'Rose', colors: ['#d87bac', '#383fd2', '#b9b0e8'] },
	{ id: 'catppuccin', label: 'Catppuccin', colors: ['#7186ff', '#e977ca', '#0f9299'] },
	{ id: 'trans', label: 'Trans', colors: ['#00c3f1', '#f89dc9', '#00a1a9'] },
] as const satisfies readonly ThemeOption[];
export type ThemeId = (typeof THEMES)[number]['id'];
export const THEME_IDS = THEMES.map((option) => option.id) as readonly ThemeId[];
export function isThemeId(value: unknown): value is ThemeId { return typeof value === 'string' && THEMES.some((option) => option.id === value); }
export function themeById(id: ThemeId): ThemeOption { const option = THEMES.find((item) => item.id === id); if (!option) throw new Error(`Unknown theme: ${id}`); return option; }
