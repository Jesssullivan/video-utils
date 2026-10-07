// Client-safe structural views of the runs read API (the closed Effect Schemas live server-side in
// $lib/server/runs/schema.ts; pages pass decoded data into components typed by these supertypes).
export interface Envelope {
	readonly status: string;
	readonly reason: string | null;
	readonly document: unknown;
}
export interface BpmView {
	readonly value: number | null;
	readonly reason: string;
	readonly basis: string | null;
	readonly grid: { readonly period_seconds: number; readonly phase_seconds: number; readonly window_seconds: number | null; readonly basis: string } | null;
}
export interface UnknownEntryView {
	readonly value: unknown;
	readonly reason: string | null;
	readonly basis?: string;
}
export interface SpectrogramView {
	readonly status: string;
	readonly reason: string | null;
	readonly evidence_id: string | null;
	readonly signal_version: string | null;
	readonly stage: string | null;
	readonly shape: { readonly frames: number | null; readonly bands: number | null } | null;
	readonly band_centre_hz: readonly number[];
	readonly hop_seconds: number | null;
	readonly window_seconds: number | null;
	readonly first_frame_centre_seconds: number | null;
	readonly axis_offset_seconds: number | null;
	readonly matrices: readonly { readonly name: 'log_power_db' | 'pcen'; readonly media_name: string; readonly status: string }[];
	readonly reference_lines: readonly { readonly label: string; readonly hz: number }[];
	readonly claim: string;
	readonly pcen_status: string | null;
}
export interface LayersView {
	readonly run_id: string;
	readonly selected_evidence_id: string | null;
	readonly selected_generated_utc: string | null;
	readonly alternatives: readonly string[];
	readonly layers: {
		readonly tone_ab: Envelope;
		readonly coverage: Envelope;
		readonly flags_triage: Envelope;
		readonly phrase_timing: Envelope;
		readonly bpm: BpmView;
	};
	readonly media: Readonly<Record<string, { readonly evidence_id: string; readonly sha256: string }>>;
	readonly spectrogram: SpectrogramView;
	readonly clock: { readonly layer_axis: string; readonly annotation_axis: string; readonly alignment: string; readonly reason: string };
	readonly source_extent: { readonly audio_start_seconds: number | null; readonly duration_seconds: number | null };
	readonly unknown_fields: Readonly<Record<string, UnknownEntryView>>;
}
export interface ProcessingView {
	readonly profile_name: string | null;
	readonly denoise: { readonly filter: string | null; readonly delay_samples: number | null; readonly status: string | null };
	readonly tone: {
		readonly peaking_eq: readonly { readonly frequency_hz: number | null; readonly gain_db: number | null; readonly q: number | null }[];
		readonly compressor: Readonly<Record<string, number | null>> | null;
	};
	readonly high_pass_applied: boolean | null;
	readonly hum_notches_applied: boolean | null;
	readonly intentional_low_fundamental_hz: number | null;
	readonly noise_capture: { readonly selected_seconds: readonly (number | null)[] | null; readonly review: string | null };
}
export interface StageView {
	readonly stage: string;
	readonly file_role: string;
	readonly signal_version: string | null;
	readonly state: string;
}
