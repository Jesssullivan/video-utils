// Lane-local closed Effect 4 Schemas for the S3 processing routes of scripts/web_api.py
// (ROUTES_PROCESSING_S3 section 5). Top-level structs decode closed (onExcessProperty: "error");
// nested worker/knob blocks the UI only displays are decoded as bounded records. These exist
// because the shared web/src/lib/schema/control.ts decodes only share_export jobs (root-owned;
// widening requested in the lane results). Null/unknown fields stay null and keep their reasons.
import { Schema } from 'effect';

const pattern = (re: RegExp) => Schema.String.check(Schema.isPattern(re));
const JobId = pattern(/^job_[0-9a-f]{32}$/);
const ArtifactId = pattern(/^art_[0-9a-f]{32}$/);
const ReviewId = pattern(/^rev_[0-9a-f]{32}$/);
const RunId = pattern(/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/);
const Sha256 = pattern(/^[0-9a-f]{64}$/);
const Code = pattern(/^[a-z_]{1,64}$/);
const IsoUtc = pattern(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,9})?Z$/);
const Text = (max: number) => Schema.String.check(Schema.isMaxLength(max));
const NonNegativeInt = Schema.Int.check(Schema.isGreaterThanOrEqualTo(0));
const Open = Schema.Record(Schema.String, Schema.Unknown);

export const PROCESSING_TOOLS = ['denoise', 'capture_profile', 'apply_capture_profile'] as const;
export const ALL_TOOLS = ['share_export', ...PROCESSING_TOOLS] as const;
const JobState = Schema.Literals(['queued', 'running', 'succeeded', 'failed', 'cancelled', 'interrupted']);
const Admission = Schema.Literals(['admitted', 'pending_root_admission']);

// --------------------------------------------------------------------------- catalogue

export const JobTypeEntry = Schema.Struct({
	tool: Schema.Literals(ALL_TOOLS),
	admission_state: Admission,
	capability_state: Schema.NullOr(Text(32)),
	resource_class: Schema.Literals(['media', 'analysis']),
	bound_field: Schema.NullOr(Text(64)),
	knobs: Schema.Record(Schema.String, Open),
	web_only_constraints: Schema.Array(Text(400)).check(Schema.isMaxLength(16)),
	timeout_seconds: Schema.Struct({ minimum: Schema.Int, maximum: Schema.Int, default: Schema.Int }),
	outer_headroom_seconds: Schema.Finite,
	implementation_status: Text(64),
	evidence_kind: Text(100),
	capability_revision: Sha256,
	profiles: Schema.optionalKey(Schema.Array(Schema.Struct({ name: Text(64), source_bound_sha256: Schema.NullOr(Sha256) }))),
	presets: Schema.optionalKey(Open),
	low_shelf: Schema.optionalKey(Schema.Struct({ available: Schema.Boolean, reason: Text(400) }))
});
export type JobTypeEntry = typeof JobTypeEntry.Type;

export const JobTypes = Schema.Struct({
	schema_version: Schema.Literal(1),
	job_types: Schema.Array(JobTypeEntry).check(Schema.isMaxLength(8)),
	allowlist: Schema.Array(Schema.Literals(ALL_TOOLS)),
	claim_class: Schema.Literal('contract_catalogue')
});
export type JobTypes = typeof JobTypes.Type;

// --------------------------------------------------------------------------- runs

const RunOutput = Schema.Struct({
	role: Text(32),
	artifact_id: ArtifactId,
	sha256_claimed: Sha256,
	served_via_run_media: Schema.Boolean
});

export const RunRecord = Schema.Struct({
	run_id: RunId,
	role: Schema.Literals(['baseline', 'capture_candidate', 'other']),
	baseline_eligible: Schema.Boolean,
	baseline_eligibility_reason: Text(300),
	profile_name: Schema.NullOr(Text(128)),
	status: Schema.NullOr(Text(64)),
	pcm: Open,
	manifest_sha256: Sha256,
	outputs: Schema.Array(RunOutput).check(Schema.isMaxLength(16)),
	output_hash_basis: Text(300)
});
export type RunRecord = typeof RunRecord.Type;

export const RunList = Schema.Struct({
	schema_version: Schema.Literal(1),
	source_artifact_id: ArtifactId,
	runs: Schema.Array(RunRecord).check(Schema.isMaxLength(4096)),
	scanned_entries: NonNegativeInt,
	truncated: Schema.Boolean,
	unknowns: Schema.Struct({ probe_duration_seconds: Schema.Null, probe_duration_seconds_reason: Text(300) })
});
export type RunList = typeof RunList.Type;

// --------------------------------------------------------------------------- capture reviews

const Interval = Schema.Struct({
	start_seconds: Schema.Finite,
	end_seconds: Schema.Finite,
	start_sample: NonNegativeInt,
	end_sample: NonNegativeInt,
	sample_rate: NonNegativeInt,
	time_axis: Schema.Literal('decoded_source_audio_samples'),
	duration_seconds: Schema.Finite
});

export const ReviewRecord = Schema.Struct({
	review_id: ReviewId,
	source_artifact_id: ArtifactId,
	source_sha256: Sha256,
	run_id: RunId,
	manifest_sha256: Sha256,
	pcm_sha256: Sha256,
	review_sha256: Sha256,
	interval: Interval,
	review_status: Schema.Literals(['reviewed_candidate', 'reviewed_possible_contamination', 'rejected_contaminated']),
	authorization_scope: Schema.Literals(['profile_authoring', 'experimental_capture_render']),
	music_status: Text(64),
	click_status: Text(64),
	ambient_music_status: Text(64),
	note: Text(2000),
	overlaps_setup_interval: Schema.Boolean,
	setup_interval_acknowledged: Schema.Boolean,
	selected_by: Text(128),
	reviewed_by: Text(128),
	authorization_reference: Text(512),
	identity_authenticated: Schema.Literal(false),
	created_at: IsoUtc,
	renderable: Schema.Boolean,
	rechecked: Schema.Literal(false),
	rechecked_reason: Text(300),
	claim_class: Schema.Literal('operator_assertion_record'),
	unknowns: Open,
	replayed: Schema.optionalKey(Schema.Boolean)
});
export type ReviewRecord = typeof ReviewRecord.Type;

export const ReviewList = Schema.Struct({
	schema_version: Schema.Literal(1),
	source_artifact_id: ArtifactId,
	reviews: Schema.Array(ReviewRecord).check(Schema.isMaxLength(200)),
	truncated: Schema.Boolean
});
export type ReviewList = typeof ReviewList.Type;

// --------------------------------------------------------------------------- measurement

const ChannelStats = Schema.Struct({
	sample_peak_dbfs: Schema.Finite,
	sample_peak_is_true_peak: Schema.Literal(false),
	rms_dbfs: Schema.Finite,
	frame_rms_dbfs: Schema.Struct({
		min: Schema.NullOr(Schema.Finite),
		median: Schema.NullOr(Schema.Finite),
		max: Schema.NullOr(Schema.Finite),
		spread_db: Schema.NullOr(Schema.Finite)
	}),
	frame_count: NonNegativeInt,
	frame_samples: NonNegativeInt,
	unframed_tail_samples: NonNegativeInt,
	transient_frames: NonNegativeInt,
	transient_frames_label: Text(300),
	clipped_samples: NonNegativeInt,
	clip_threshold_fs: Schema.Finite,
	sample_count: NonNegativeInt
});
export type ChannelStats = typeof ChannelStats.Type;

export const Measurement = Schema.Struct({
	schema_version: Schema.Literal(1),
	claim_class: Schema.Literal('measurement_of_mixture'),
	source_artifact_id: ArtifactId,
	source_sha256: Sha256,
	run_id: RunId,
	manifest_sha256: Sha256,
	pcm_sha256: Sha256,
	pcm_rehashed: Schema.Boolean,
	interval: Schema.Struct({ ...Interval.fields, channels: NonNegativeInt, codec: Text(32) }),
	overlaps_setup_interval: Schema.Boolean,
	setup_interval_note: Text(300),
	channels: Schema.Array(ChannelStats).check(Schema.isMaxLength(8)),
	selects_interval: Schema.Literal(false),
	run_noise_json: Open,
	unknowns: Open,
	writes: Schema.Literal('none')
});
export type Measurement = typeof Measurement.Type;

// --------------------------------------------------------------------------- jobs (widened union)

/** /api/v1/jobs rows: share_export rows keep the S2 shape; processing rows add tool and bound_input. */
export const LaneJobSummary = Schema.Struct({
	job_id: JobId,
	state: JobState,
	reason_code: Schema.NullOr(Code),
	parameters: Open,
	created_at: IsoUtc,
	updated_at: IsoUtc,
	attempt_count: Schema.Int.check(Schema.isBetween({ minimum: 1, maximum: 1000 })),
	artifact_count: NonNegativeInt,
	tool: Schema.optionalKey(Schema.Literals(PROCESSING_TOOLS)),
	bound_input: Schema.optionalKey(Schema.NullOr(Open))
});
export type LaneJobSummary = typeof LaneJobSummary.Type;

export const LaneJobList = Schema.Struct({
	schema_version: Schema.Literal(1),
	jobs: Schema.Array(LaneJobSummary).check(Schema.isMaxLength(200)),
	truncated: Schema.Boolean
});
export type LaneJobList = typeof LaneJobList.Type;

export const OutputRow = Schema.Struct({
	role: Text(32),
	name: Text(64),
	artifact_id: ArtifactId,
	sha256: Sha256,
	size_bytes: NonNegativeInt,
	content_type: Text(100),
	served_via_run_media: Schema.Boolean
});
export type OutputRow = typeof OutputRow.Type;

/** v1 projection of a processing job (or a share_export job decoded loosely for listing only). */
export const LaneJobProjection = Schema.Struct({
	job_id: JobId,
	tool: Schema.Literals(ALL_TOOLS),
	state: JobState,
	reason_code: Schema.NullOr(Code),
	source_artifact_id: ArtifactId,
	source_id: Schema.NullOr(Text(64)),
	source_binding: Schema.Literals(['bound', 'unknown']),
	parameters: Open,
	capability_revision: Sha256,
	idempotency_key: Text(128),
	cancel_requested: Schema.Boolean,
	attempts: Schema.Array(Open).check(Schema.isMaxLength(64)),
	artifacts: Schema.Array(Open).check(Schema.isMaxLength(192)),
	claim_class: Schema.Literal('job_state_record'),
	unknowns: Open,
	bound_input: Schema.optionalKey(Schema.NullOr(Open)),
	run_id: Schema.optionalKey(Schema.NullOr(RunId)),
	authoring_id: Schema.optionalKey(Schema.NullOr(RunId)),
	worker_status: Schema.optionalKey(Schema.NullOr(Text(64))),
	outputs: Schema.optionalKey(Schema.Array(OutputRow).check(Schema.isMaxLength(16))),
	admission_state: Schema.optionalKey(Admission),
	schema_version: Schema.Literal(1),
	phase: Schema.NullOr(Code),
	phase_reason: Text(300),
	progress: Schema.NullOr(Open),
	progress_reason: Text(300),
	eta_seconds: Schema.Null,
	eta_seconds_reason: Text(300),
	created_at: IsoUtc,
	updated_at: IsoUtc,
	tool_envelope: Open,
	replayed: Schema.optionalKey(Schema.Boolean),
	late_cancel: Schema.optionalKey(Schema.Boolean)
});
export type LaneJobProjection = typeof LaneJobProjection.Type;

const structs = [JobTypeEntry, JobTypes, RunOutput, RunRecord, RunList, Interval, ReviewRecord, ReviewList, ChannelStats,
	Measurement, LaneJobSummary, LaneJobList, OutputRow, LaneJobProjection];

/** Every field name the lane schemas know (error paths never echo upstream keys). */
export const LANE_FIELD_NAMES: ReadonlySet<string> = new Set(structs.flatMap((s) => Object.keys(s.fields)));

export const RUN_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
export const REVIEW_ID_PATTERN = /^rev_[0-9a-f]{32}$/;
export const MEDIA_ROLES = ['source', 'denoised', 'cleaned', 'processed', 'residue'] as const;
