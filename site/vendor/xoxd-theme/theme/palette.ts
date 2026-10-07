export const FAMILIES = ['primary', 'secondary', 'tertiary', 'success', 'warning', 'error', 'surface'] as const;
export type Family = (typeof FAMILIES)[number];

export const SHADES = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950] as const;
export type Shade = (typeof SHADES)[number];

export interface ShadeToken {
	
	readonly hex: string;
	
	readonly oklch: string;
	
	readonly text: 'light' | 'dark';
	
	readonly ratio: number;
}

export const palette: Record<Family, Record<Shade, ShadeToken>> = {
	primary: {
		50: { hex: '#fff1f1', oklch: 'oklch(97% 0.0146 18deg)', text: 'dark', ratio: 16.46 },
		100: { hex: '#ffdfdf', oklch: 'oklch(93% 0.0354 18deg)', text: 'dark', ratio: 14.54 },
		200: { hex: '#ffb4b5', oklch: 'oklch(84% 0.0882 18deg)', text: 'dark', ratio: 10.72 },
		300: { hex: '#ff767f', oklch: 'oklch(73% 0.1666 18deg)', text: 'dark', ratio: 7.02 },
		400: { hex: '#f5184c', oklch: 'oklch(62% 0.24 18deg)', text: 'dark', ratio: 4.41 },
		500: { hex: '#cc003b', oklch: 'oklch(53.6% 0.2147 18deg)', text: 'light', ratio: 5.26 },
		600: { hex: '#ab0030', oklch: 'oklch(47% 0.1882 18deg)', text: 'light', ratio: 6.89 },
		700: { hex: '#890024', oklch: 'oklch(40% 0.1602 18deg)', text: 'light', ratio: 9.14 },
		800: { hex: '#69001a', oklch: 'oklch(33% 0.1322 18deg)', text: 'light', ratio: 11.83 },
		900: { hex: '#4f0011', oklch: 'oklch(27% 0.1081 18deg)', text: 'light', ratio: 14.25 },
		950: { hex: '#360009', oklch: 'oklch(21% 0.0841 18deg)', text: 'light', ratio: 16.46 },
	},
	secondary: {
		50: { hex: '#f1f6fa', oklch: 'oklch(97% 0.008 250deg)', text: 'dark', ratio: 13.42 },
		100: { hex: '#d8e3ef', oklch: 'oklch(91.1% 0.02 250deg)', text: 'dark', ratio: 11.23 },
		200: { hex: '#b9d1eb', oklch: 'oklch(85.2% 0.045 250deg)', text: 'dark', ratio: 9.3 },
		300: { hex: '#9ac0e7', oklch: 'oklch(79.3% 0.07 250deg)', text: 'dark', ratio: 7.69 },
		400: { hex: '#7aaee3', oklch: 'oklch(73.4% 0.095 250deg)', text: 'dark', ratio: 6.25 },
		500: { hex: '#659bd2', oklch: 'oklch(67.5% 0.1 250deg)', text: 'dark', ratio: 4.99 },
		600: { hex: '#4f7eae', oklch: 'oklch(58% 0.09 250deg)', text: 'light', ratio: 3.92 },
		700: { hex: '#41668d', oklch: 'oklch(50% 0.075 250deg)', text: 'light', ratio: 5.5 },
		800: { hex: '#334f6d', oklch: 'oklch(42% 0.06 250deg)', text: 'light', ratio: 7.78 },
		900: { hex: '#283c51', oklch: 'oklch(35% 0.045 250deg)', text: 'light', ratio: 10.4 },
		950: { hex: '#1d2a37', oklch: 'oklch(28% 0.03 250deg)', text: 'light', ratio: 13.42 },
	},
	tertiary: {
		50: { hex: '#f8f2ff', oklch: 'oklch(97% 0.0182 307.7deg)', text: 'dark', ratio: 17.9 },
		100: { hex: '#d8cbe6', oklch: 'oklch(86.08% 0.04 307.7deg)', text: 'dark', ratio: 12.73 },
		200: { hex: '#c09de0', oklch: 'oklch(75.16% 0.1 307.7deg)', text: 'dark', ratio: 8.55 },
		300: { hex: '#a76ed7', oklch: 'oklch(64.24% 0.16 307.7deg)', text: 'dark', ratio: 5.48 },
		400: { hex: '#8c3fc4', oklch: 'oklch(53.32% 0.2 307.7deg)', text: 'light', ratio: 5.28 },
		500: { hex: '#682893', oklch: 'oklch(42.4% 0.169 307.7deg)', text: 'light', ratio: 8.27 },
		600: { hex: '#551e7b', oklch: 'oklch(37% 0.15 307.7deg)', text: 'light', ratio: 10.3 },
		700: { hex: '#421461', oklch: 'oklch(31% 0.13 307.7deg)', text: 'light', ratio: 12.72 },
		800: { hex: '#330d4c', oklch: 'oklch(26% 0.11 307.7deg)', text: 'light', ratio: 14.69 },
		900: { hex: '#220a34', oklch: 'oklch(21% 0.08 307.7deg)', text: 'light', ratio: 16.48 },
		950: { hex: '#140421', oklch: 'oklch(16% 0.06 307.7deg)', text: 'light', ratio: 17.9 },
	},
	success: {
		50: { hex: '#eaf5e9', oklch: 'oklch(96% 0.02 142.5deg)', text: 'dark', ratio: 15.56 },
		100: { hex: '#d6ecd4', oklch: 'oklch(92% 0.04 142.5deg)', text: 'dark', ratio: 13.96 },
		200: { hex: '#a1d89c', oklch: 'oklch(83% 0.1 142.5deg)', text: 'dark', ratio: 10.64 },
		300: { hex: '#62bd5c', oklch: 'oklch(72% 0.16 142.5deg)', text: 'dark', ratio: 7.43 },
		400: { hex: '#0d9b0b', oklch: 'oklch(60% 0.2 142.5deg)', text: 'dark', ratio: 4.74 },
		500: { hex: '#006e00', oklch: 'oklch(46.6% 0.1585 142.5deg)', text: 'light', ratio: 5.8 },
		600: { hex: '#005c00', oklch: 'oklch(41% 0.1394 142.5deg)', text: 'light', ratio: 7.4 },
		700: { hex: '#034b02', oklch: 'oklch(36% 0.12 142.5deg)', text: 'light', ratio: 9.32 },
		800: { hex: '#053c04', oklch: 'oklch(31% 0.1 142.5deg)', text: 'light', ratio: 11.32 },
		900: { hex: '#052d04', oklch: 'oklch(26% 0.08 142.5deg)', text: 'light', ratio: 13.54 },
		950: { hex: '#051f04', oklch: 'oklch(21% 0.06 142.5deg)', text: 'light', ratio: 15.56 },
	},
	warning: {
		50: { hex: '#f8f6e7', oklch: 'oklch(97% 0.02 98.8deg)', text: 'dark', ratio: 10.33 },
		100: { hex: '#f5edbf', oklch: 'oklch(94.02% 0.06 98.8deg)', text: 'dark', ratio: 9.48 },
		200: { hex: '#f5e382', oklch: 'oklch(91.04% 0.12 98.8deg)', text: 'dark', ratio: 8.65 },
		300: { hex: '#f4d834', oklch: 'oklch(88.06% 0.17 98.8deg)', text: 'dark', ratio: 7.87 },
		400: { hex: '#ecce00', oklch: 'oklch(85.08% 0.1762 98.8deg)', text: 'dark', ratio: 7.16 },
		500: { hex: '#e1c500', oklch: 'oklch(82.1% 0.17 98.8deg)', text: 'dark', ratio: 6.51 },
		600: { hex: '#b9a200', oklch: 'oklch(71% 0.147 98.8deg)', text: 'dark', ratio: 4.4 },
		700: { hex: '#9a8601', oklch: 'oklch(62% 0.1283 98.8deg)', text: 'light', ratio: 3.34 },
		800: { hex: '#7c6c00', oklch: 'oklch(53% 0.1097 98.8deg)', text: 'light', ratio: 4.83 },
		900: { hex: '#5f5300', oklch: 'oklch(44% 0.0911 98.8deg)', text: 'light', ratio: 7.1 },
		950: { hex: '#443b00', oklch: 'oklch(35% 0.0724 98.8deg)', text: 'light', ratio: 10.33 },
	},
	error: {
		50: { hex: '#fff1f6', oklch: 'oklch(97% 0.0164 351deg)', text: 'dark', ratio: 16.62 },
		100: { hex: '#fedeeb', oklch: 'oklch(93% 0.0398 351deg)', text: 'dark', ratio: 14.62 },
		200: { hex: '#fdb0d2', oklch: 'oklch(84% 0.0995 351deg)', text: 'dark', ratio: 10.68 },
		300: { hex: '#f871b5', oklch: 'oklch(73% 0.18 351deg)', text: 'dark', ratio: 6.95 },
		400: { hex: '#e62497', oklch: 'oklch(62% 0.24 351deg)', text: 'dark', ratio: 4.39 },
		500: { hex: '#c1077d', oklch: 'oklch(53.6% 0.22 351deg)', text: 'light', ratio: 5.33 },
		600: { hex: '#a20568', oklch: 'oklch(47% 0.1928 351deg)', text: 'light', ratio: 6.95 },
		700: { hex: '#820352', oklch: 'oklch(40% 0.1642 351deg)', text: 'light', ratio: 9.2 },
		800: { hex: '#63023e', oklch: 'oklch(33% 0.1354 351deg)', text: 'light', ratio: 11.91 },
		900: { hex: '#4a012d', oklch: 'oklch(27% 0.1108 351deg)', text: 'light', ratio: 14.37 },
		950: { hex: '#32001d', oklch: 'oklch(21% 0.0862 351deg)', text: 'light', ratio: 16.62 },
	},
	surface: {
		50: { hex: '#f7f3fc', oklch: 'oklch(97% 0.012 305deg)', text: 'dark', ratio: 19.02 },
		100: { hex: '#ede9f3', oklch: 'oklch(94% 0.014 305deg)', text: 'dark', ratio: 17.41 },
		200: { hex: '#dad5e0', oklch: 'oklch(88% 0.016 305deg)', text: 'dark', ratio: 14.46 },
		300: { hex: '#c0bbc7', oklch: 'oklch(80% 0.018 305deg)', text: 'dark', ratio: 11.08 },
		400: { hex: '#a19ba9', oklch: 'oklch(70% 0.02 305deg)', text: 'dark', ratio: 7.71 },
		500: { hex: '#746f7c', oklch: 'oklch(55% 0.022 305deg)', text: 'light', ratio: 4.45 },
		600: { hex: '#4a4551', oklch: 'oklch(40% 0.02 305deg)', text: 'light', ratio: 8.48 },
		700: { hex: '#2b2730', oklch: 'oklch(28% 0.018 305deg)', text: 'light', ratio: 13.36 },
		800: { hex: '#131017', oklch: 'oklch(18% 0.016 305deg)', text: 'light', ratio: 17.22 },
		900: { hex: '#07050a', oklch: 'oklch(12% 0.014 305deg)', text: 'light', ratio: 18.53 },
		950: { hex: '#020103', oklch: 'oklch(8% 0.012 305deg)', text: 'light', ratio: 19.02 },
	},
};


export const disclosedSubAaShades = [
	'primary-400',
	'secondary-600',
	'warning-600',
	'warning-700',
	'error-400',
	'surface-500',
] as const;


export const fillContrastExceptions = ['secondary', 'warning'] as const;


export const fillContrastExceptionsOnInk = ['tertiary'] as const;


export const pinnedTokens = {
	'--typo-heading--color-light': 'var(--color-primary-800)',
	'--typo-heading--color-dark': 'var(--color-primary-300)',
	'--typo-anchor--color-light': 'var(--color-primary-500)',
	'--typo-anchor--color-dark': 'var(--color-primary-400)',
	'--typo-anchor--hover--color-light': 'var(--color-primary-600)',
	'--typo-anchor--hover--color-dark': 'var(--color-primary-300)',
	'--color-root-bg-light': 'var(--color-surface-50)',
	'--color-root-bg-dark': 'var(--color-surface-950)',
	'--color-brand-light': 'var(--color-primary-500)',
	'--color-brand-dark': 'var(--color-primary-400)',
} as const;
