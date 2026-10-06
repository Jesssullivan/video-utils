// Effect Schemas for the ASSUMED S2 control-API subset (WEB_STACK_S2.md section 4).
// control_api_contract_source: assumed_s2_subset_pending_web_jobs. These shapes are
// an assumption until the web_jobs contract is merged and aligned by root.
// Structs are decoded closed (onExcessProperty: "error"); nullable fields stay nullable.
import { Schema } from 'effect';

export const OPAQUE_ID_PATTERN = /^[A-Za-z0-9_-]{1,128}$/;
const ISO_UTC_PATTERN = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,9})?Z$/;

export const OpaqueId = Schema.String.check(Schema.isPattern(OPAQUE_ID_PATTERN));
const BoundedText = (max: number) => Schema.String.check(Schema.isMinLength(1), Schema.isMaxLength(max));
const IsoUtc = Schema.String.check(Schema.isPattern(ISO_UTC_PATTERN));
const NonNegativeFinite = Schema.Finite.check(Schema.isGreaterThanOrEqualTo(0));
const IntBetween = (minimum: number, maximum: number) =>
	Schema.Int.check(Schema.isBetween({ minimum, maximum }));

export const ValidationState = Schema.Literals(['pending', 'valid', 'rejected', 'unknown']);

export const SourceSummary = Schema.Struct({
	source_id: OpaqueId,
	label: BoundedText(200),
	validation_state: ValidationState,
	source_sha256: Schema.NullOr(Schema.String.check(Schema.isPattern(/^[0-9a-f]{64}$/))),
	duration_seconds: Schema.NullOr(NonNegativeFinite),
	sample_rate_hz: Schema.NullOr(IntBetween(1, 768000)),
	channels: Schema.NullOr(IntBetween(1, 64))
});
export type SourceSummary = typeof SourceSummary.Type;

export const SourceList = Schema.Struct({
	schema_version: Schema.Literal(1),
	sources: Schema.Array(SourceSummary).check(Schema.isMaxLength(500))
});
export type SourceList = typeof SourceList.Type;

export const JOB_STATES = [
	'queued',
	'validating',
	'running',
	'finalizing',
	'succeeded',
	'failed',
	'interrupted',
	'needs_reconciliation',
	'cancelling',
	'cancelled'
] as const;
export const JobState = Schema.Literals(JOB_STATES);
export type JobState = typeof JobState.Type;

export const JobProgress = Schema.Struct({
	completed: Schema.Int.check(Schema.isGreaterThanOrEqualTo(0)),
	denominator: Schema.Int.check(Schema.isGreaterThanOrEqualTo(1)),
	unit: BoundedText(64)
});

export const JobSnapshot = Schema.Struct({
	schema_version: Schema.Literal(1),
	job_id: OpaqueId,
	tool: BoundedText(64),
	state: JobState,
	phase: Schema.NullOr(Schema.String.check(Schema.isMaxLength(200))),
	source_id: Schema.NullOr(OpaqueId),
	created_utc: IsoUtc,
	updated_utc: IsoUtc,
	progress: Schema.NullOr(JobProgress),
	eta_seconds: Schema.NullOr(NonNegativeFinite),
	error_class: Schema.NullOr(Schema.String.check(Schema.isMaxLength(200))),
	limitations: Schema.Array(Schema.String.check(Schema.isMaxLength(500))).check(Schema.isMaxLength(32))
});
export type JobSnapshot = typeof JobSnapshot.Type;

/** Every field name the closed schemas know; used to keep error paths free of upstream text. */
export const KNOWN_FIELD_NAMES: ReadonlySet<string> = new Set([
	...Object.keys(SourceList.fields),
	...Object.keys(SourceSummary.fields),
	...Object.keys(JobSnapshot.fields),
	...Object.keys(JobProgress.fields)
]);

export function isOpaqueId(value: string): boolean {
	return OPAQUE_ID_PATTERN.test(value);
}
