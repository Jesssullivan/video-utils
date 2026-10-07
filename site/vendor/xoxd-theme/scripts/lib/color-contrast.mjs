/**
 * WCAG 2.2 colour maths for the shipped design tokens.
 *
 * Deliberately dependency-free and pure so the acceptance suite can assert
 * contrast on the tokens declared in `src/app.css` without booting a browser.
 * The browser-side spot checks in `e2e/` duplicate none of this: they read
 * *computed* colours and feed them through the same ratio definition.
 *
 * Test-only, so it lives here rather than under `src/lib` (the SvelteKit
 * library root): nothing the site ships needs colour maths at run time, and a
 * module that cannot be imported by a route cannot be bundled by accident.
 * Plain ESM so `node` and `vitest` load the same bytes with no transpile step.
 */

/**
 * @typedef {object} Rgb
 * @property {number} red
 * @property {number} green
 * @property {number} blue
 * @property {number} alpha 0..1; 1 for fully opaque colours.
 */

/** WCAG 2.2 SC 1.4.3 , normal body text. */
export const TEXT_AA_RATIO = 4.5;
/** WCAG 2.2 SC 1.4.3 , large text (>=24px, or >=18.66px bold). */
export const LARGE_TEXT_AA_RATIO = 3;
/** WCAG 2.2 SC 1.4.11 , user-interface components and graphical objects. */
export const NON_TEXT_RATIO = 3;

const HEX_RE = /^#(?:[0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})$/i;
const FUNCTIONAL_RE = /^rgba?\(([^)]*)\)$/i;
const OKLCH_RE = /^oklch\(([^)]*)\)$/i;
const OKLAB_RE = /^oklab\(([^)]*)\)$/i;
const COLOR_SRGB_RE = /^color\(\s*srgb\s+([^)]*)\)$/i;

/** CSS maps `100%` on an oklab/oklch chroma axis to this much chroma. */
const OK_CHROMA_FULL = 0.4;

/**
 * @param {number} value
 * @returns {number}
 */
function clampChannel(value) {
	return Math.min(255, Math.max(0, value));
}

/**
 * Splits a functional colour's argument list into its components and its
 * optional alpha, accepting both the legacy comma form and the modern
 * space-plus-slash form.
 *
 * @param {string} args
 * @returns {{ components: string[], alpha: string | undefined }}
 */
function splitComponents(args) {
	const [head, alphaPart] = args.split('/');
	const components = head
		.trim()
		.split(/[\s,]+/)
		.filter(Boolean);
	return { components, alpha: alphaPart === undefined ? components[3] : alphaPart };
}

/**
 * `none` is a real CSS keyword in the modern colour functions and behaves as 0
 * for our purposes (we never carry a missing component forward).
 *
 * @param {string | undefined} token
 * @param {number} percentScale What `100%` means on this axis.
 * @returns {number}
 */
function parseAxis(token, percentScale) {
	if (token === undefined || token.toLowerCase() === 'none') return 0;
	const trimmed = token.trim();
	if (trimmed.endsWith('%')) return (Number.parseFloat(trimmed) / 100) * percentScale;
	return Number.parseFloat(trimmed);
}

/**
 * @param {string | undefined} token
 * @returns {number}
 */
function parseAlpha(token) {
	if (token === undefined) return 1;
	return Math.min(1, Math.max(0, parseAxis(token, 1)));
}

/**
 * Angle in any CSS angle unit, in degrees.
 *
 * @param {string | undefined} token
 * @returns {number}
 */
function parseHue(token) {
	if (token === undefined || token.toLowerCase() === 'none') return 0;
	const value = Number.parseFloat(token);
	// `grad` is tested first: it ends in `rad`, so a `/rad$/` probe matches it and
	// would read 104.544grad as radians. 400grad = 360deg; 1rad = 180/PI deg.
	if (/grad$/i.test(token)) return value * 0.9;
	if (/rad$/i.test(token)) return (value * 180) / Math.PI;
	if (/turn$/i.test(token)) return value * 360;
	return value;
}

/**
 * Linear-light sRGB channel to an 8-bit sRGB channel, gamut-clipped.
 *
 * Rounded to a whole channel on purpose: WCAG's relative-luminance definition is
 * written over 8-bit sRGB values, and rounding here is what makes an `oklch()`
 * token measure identically to the hex `src/lib/theme/palette.ts` documents for
 * it. Carrying the fractional channel forward moves ratios by ~0.05, which is
 * enough for the unit gate and the browser gate to disagree about a number.
 *
 * @param {number} value
 * @returns {number}
 */
function linearToSrgb255(value) {
	const clamped = Math.min(1, Math.max(0, value));
	const encoded = clamped <= 0.0031308 ? 12.92 * clamped : 1.055 * clamped ** (1 / 2.4) - 0.055;
	return Math.round(encoded * 255);
}

/**
 * Ottosson OKLab to sRGB. This is the single copy of the transform:
 * `src/lib/theme/palette.test.ts` proves the palette's documented hexes
 * through `parseCssColor`/`formatRgb` rather than restating the matrix.
 *
 * Needed because Chromium serialises a computed `oklch()`/`color-mix(in oklab, ...)`
 * colour *as* `oklch(...)`/`oklab(...)` rather than converting it to `rgb()`.
 * A parser that only understands `rgb()` silently reads an OKLab lightness of
 * 0.38 as a red channel of 0.38/255 , which is how a fully-passing palette can
 * measure as a 1.0:1 contrast failure.
 *
 * @param {number} lightness 0..1
 * @param {number} a
 * @param {number} b
 * @param {number} alpha 0..1
 * @returns {Rgb}
 */
function oklabToRgb(lightness, a, b, alpha) {
	const lCube = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3;
	const mCube = (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3;
	const sCube = (lightness - 0.0894841775 * a - 1.291485548 * b) ** 3;
	return {
		red: linearToSrgb255(4.0767416621 * lCube - 3.3077115913 * mCube + 0.2309699292 * sCube),
		green: linearToSrgb255(-1.2684380046 * lCube + 2.6097574011 * mCube - 0.3413193965 * sCube),
		blue: linearToSrgb255(-0.0041960863 * lCube - 0.7034186147 * mCube + 1.707614701 * sCube),
		alpha,
	};
}

/**
 * @param {string} value
 * @returns {Rgb}
 */
function parseHex(value) {
	const digits = value.slice(1);
	/** @param {string} pair */
	const expand = (pair) => Number.parseInt(pair.length === 1 ? pair + pair : pair, 16);
	if (digits.length <= 4) {
		const [r, g, b, a] = digits.split('');
		return {
			red: expand(r),
			green: expand(g),
			blue: expand(b),
			alpha: a === undefined ? 1 : expand(a) / 255,
		};
	}
	return {
		red: expand(digits.slice(0, 2)),
		green: expand(digits.slice(2, 4)),
		blue: expand(digits.slice(4, 6)),
		alpha: digits.length === 8 ? expand(digits.slice(6, 8)) / 255 : 1,
	};
}

/**
 * @param {string} token
 * @param {number} scale
 * @returns {number}
 */
function parseComponent(token, scale) {
	const trimmed = token.trim();
	if (trimmed.endsWith('%')) return (Number.parseFloat(trimmed) / 100) * scale;
	return Number.parseFloat(trimmed);
}

/**
 * Accepts the colour spellings this codebase actually ships:
 *
 * - authored in `src/app.css` / `src/lib/styles/theme-gf.css`: `#rgb`,
 *   `#rrggbb`, `#rrggbbaa`, `rgb(r g b / a%)`, `rgb(r, g, b)`, `rgba(...)`,
 *   `oklch(L% C Hdeg)`;
 * - returned by `getComputedStyle` in Chromium for those same declarations:
 *   `oklch(L C H)` for a plain `oklch()` value and `oklab(L a b / A)` for a
 *   `color-mix(in oklab, ...)` one. Chromium does **not** down-convert either
 *   to `rgb()`, so a browser-side measurement that assumes `rgb()` reads an
 *   OKLab lightness as a red channel and reports nonsense.
 *
 * `color(srgb ...)` is accepted too, since it is an exact sRGB spelling. Other
 * `color()` spaces (display-p3 and friends) still throw rather than being
 * converted with the wrong matrix.
 *
 * @param {string} input
 * @returns {Rgb}
 */
export function parseCssColor(input) {
	const value = input.trim();
	if (value.toLowerCase() === 'white') return { red: 255, green: 255, blue: 255, alpha: 1 };
	if (value.toLowerCase() === 'black') return { red: 0, green: 0, blue: 0, alpha: 1 };
	if (value.toLowerCase() === 'transparent') return { red: 0, green: 0, blue: 0, alpha: 0 };
	if (HEX_RE.test(value)) return parseHex(value);

	const oklch = OKLCH_RE.exec(value);
	if (oklch) {
		const { components, alpha } = splitComponents(oklch[1]);
		if (components.length < 3) throw new Error(`Unsupported CSS colour: ${input}`);
		const lightness = parseAxis(components[0], 1);
		const chroma = parseAxis(components[1], OK_CHROMA_FULL);
		const hue = (parseHue(components[2]) * Math.PI) / 180;
		return oklabToRgb(lightness, chroma * Math.cos(hue), chroma * Math.sin(hue), parseAlpha(alpha));
	}

	const oklab = OKLAB_RE.exec(value);
	if (oklab) {
		const { components, alpha } = splitComponents(oklab[1]);
		if (components.length < 3) throw new Error(`Unsupported CSS colour: ${input}`);
		return oklabToRgb(
			parseAxis(components[0], 1),
			parseAxis(components[1], OK_CHROMA_FULL),
			parseAxis(components[2], OK_CHROMA_FULL),
			parseAlpha(alpha),
		);
	}

	const srgb = COLOR_SRGB_RE.exec(value);
	if (srgb) {
		const { components, alpha } = splitComponents(srgb[1]);
		if (components.length < 3) throw new Error(`Unsupported CSS colour: ${input}`);
		return {
			red: clampChannel(parseAxis(components[0], 1) * 255),
			green: clampChannel(parseAxis(components[1], 1) * 255),
			blue: clampChannel(parseAxis(components[2], 1) * 255),
			alpha: parseAlpha(alpha),
		};
	}

	const functional = FUNCTIONAL_RE.exec(value);
	if (!functional) throw new Error(`Unsupported CSS colour: ${input}`);
	const [channels, alphaPart] = functional[1].split('/');
	const parts = channels
		.trim()
		.split(/[\s,]+/)
		.filter(Boolean);
	if (parts.length < 3) throw new Error(`Unsupported CSS colour: ${input}`);
	const alphaToken = alphaPart ?? parts[3];
	return {
		red: clampChannel(parseComponent(parts[0], 255)),
		green: clampChannel(parseComponent(parts[1], 255)),
		blue: clampChannel(parseComponent(parts[2], 255)),
		alpha: alphaToken === undefined ? 1 : Math.min(1, Math.max(0, parseComponent(alphaToken, 1))),
	};
}

/**
 * Simple (non-premultiplied) source-over composite of `foreground` onto `backdrop`.
 *
 * @param {Rgb} foreground
 * @param {Rgb} backdrop
 * @returns {Rgb}
 */
export function compositeOver(foreground, backdrop) {
	const alpha = foreground.alpha;
	return {
		red: foreground.red * alpha + backdrop.red * (1 - alpha),
		green: foreground.green * alpha + backdrop.green * (1 - alpha),
		blue: foreground.blue * alpha + backdrop.blue * (1 - alpha),
		alpha: 1,
	};
}

/**
 * WCAG 2.x relative luminance.
 *
 * @param {Rgb | string} color
 * @returns {number}
 */
export function relativeLuminance(color) {
	const rgb = typeof color === 'string' ? parseCssColor(color) : color;
	const linear = [rgb.red, rgb.green, rgb.blue].map((channel) => {
		const normalized = channel / 255;
		return normalized <= 0.04045 ? normalized / 12.92 : ((normalized + 0.055) / 1.055) ** 2.4;
	});
	return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
}

/**
 * WCAG contrast ratio. Translucent inputs are composited over `background`
 * first, because a ratio computed against an un-composited alpha colour is
 * meaningless , and quietly optimistic.
 *
 * @param {Rgb | string} foreground
 * @param {Rgb | string} background
 * @returns {number}
 */
export function contrastRatio(foreground, background) {
	const backdrop = typeof background === 'string' ? parseCssColor(background) : background;
	if (backdrop.alpha < 1) throw new Error('The background of a contrast pair must be opaque');
	const rawForeground = typeof foreground === 'string' ? parseCssColor(foreground) : foreground;
	const front = rawForeground.alpha < 1 ? compositeOver(rawForeground, backdrop) : rawForeground;
	const lighter = Math.max(relativeLuminance(front), relativeLuminance(backdrop));
	const darker = Math.min(relativeLuminance(front), relativeLuminance(backdrop));
	return (lighter + 0.05) / (darker + 0.05);
}

/**
 * Renders a parsed colour as `#rrggbb` (or `rgb(r g b / a)` when translucent)
 * so a failure message names a colour a person can look up, not an OKLab
 * triple.
 *
 * @param {Rgb | string} color
 * @returns {string}
 */
export function formatRgb(color) {
	const rgb = typeof color === 'string' ? parseCssColor(color) : color;
	const channels = [rgb.red, rgb.green, rgb.blue].map((channel) => Math.round(channel));
	if (rgb.alpha < 1) return `rgb(${channels.join(' ')} / ${Math.round(rgb.alpha * 1000) / 1000})`;
	return `#${channels.map((channel) => channel.toString(16).padStart(2, '0')).join('')}`;
}

/**
 * Ratios are reported to two decimals so failure messages stay readable.
 *
 * @param {number} ratio
 * @returns {number}
 */
export function roundRatio(ratio) {
	return Math.round(ratio * 100) / 100;
}

/**
 * @param {Rgb | string} foreground
 * @param {Rgb | string} background
 * @returns {boolean}
 */
export function meetsTextAA(foreground, background) {
	return contrastRatio(foreground, background) >= TEXT_AA_RATIO;
}

/**
 * @param {Rgb | string} foreground
 * @param {Rgb | string} background
 * @returns {boolean}
 */
export function meetsLargeTextAA(foreground, background) {
	return contrastRatio(foreground, background) >= LARGE_TEXT_AA_RATIO;
}

/**
 * @param {Rgb | string} foreground
 * @param {Rgb | string} background
 * @returns {boolean}
 */
export function meetsNonTextContrast(foreground, background) {
	return contrastRatio(foreground, background) >= NON_TEXT_RATIO;
}
