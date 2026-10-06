// Client-safe display helpers. Unknown stays unknown: callers render null through UnknownValue.
export const shortHash = (hash: string | null | undefined): string | null =>
	hash === null || hash === undefined ? null : `${hash.slice(0, 12)}…`;

export function bytes(value: number | null | undefined): string | null {
	if (value === null || value === undefined || !Number.isFinite(value)) return null;
	if (value < 1024) return `${value} B`;
	const units = ['KiB', 'MiB', 'GiB'];
	let scaled = value / 1024;
	let unit = 0;
	while (scaled >= 1024 && unit < units.length - 1) {
		scaled /= 1024;
		unit += 1;
	}
	return `${scaled.toFixed(scaled >= 100 ? 0 : 1)} ${units[unit]} (${value} B)`;
}

export const seconds = (value: number | null | undefined, digits = 3): string | null =>
	value === null || value === undefined || !Number.isFinite(value) ? null : value.toFixed(digits);
