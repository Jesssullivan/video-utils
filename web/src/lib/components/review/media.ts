// Client-safe media helpers. Exclusive playback: starting one player pauses the others. Nothing here starts
// playback; there is no autoplay attribute and no play call anywhere in the review components.
export function pauseOthers(current: EventTarget | null): void {
	if (typeof document === 'undefined') return;
	for (const element of document.querySelectorAll<HTMLMediaElement>('audio, video')) {
		if (element !== current && !element.paused) element.pause();
	}
}

export const layerMediaUrl = (runId: string, evidenceId: string, name: string): string =>
	`/api/runs/${encodeURIComponent(runId)}/layers/media/${evidenceId}/${encodeURIComponent(name)}`;

export const runArtifactUrl = (runId: string, artifactId: string, disposition: 'inline' | 'attachment' = 'attachment'): string =>
	`/api/runs/${encodeURIComponent(runId)}/artifacts/${artifactId}?disposition=${disposition}`;
