// Regenerates requests.json from cases.json using the exact BFF module that builds
// POST /api/v1/jobs bodies (web/src/lib/server/job-request.ts). Run from web/:
//   node fixtures/parity/generate.mjs
// Idempotency keys are deterministic, low-entropy synthetic values (`ui-` + the 1-based case index
// as 32 zero-padded hex digits): distinct per case and valid for the UI_KEY_PATTERN, but never
// asserted by value and never mistaken for a credential by secret scanners. The runtime UI still
// draws random keys (web/src/lib/idempotency.ts). The source id is a placeholder that
// tests/test_web_parity.py replaces with a freshly admitted synthetic source.
import { readFileSync, writeFileSync } from 'node:fs';

const here = new URL('./', import.meta.url);
const module = await import(new URL('../../src/lib/server/job-request.ts', here).href);
const table = JSON.parse(readFileSync(new URL('cases.json', here), 'utf8'));
const placeholder = 'art_' + '0'.repeat(32);
const requests = table.cases.map((entry, index) => {
	const result = module.buildJobRequest({
		sourceArtifactId: placeholder,
		parameters: entry.parameters,
		idempotencyKey: 'ui-' + (index + 1).toString(16).padStart(32, '0')
	});
	if (!result.ok) throw new Error(`job-request refused case ${entry.case_id}: ${result.code}`);
	return { case_id: entry.case_id, body: result.body };
});
const document = {
	purpose: 'Exact POST /api/v1/jobs bodies the BFF sends for each frozen parity case.',
	generated_by: 'web/src/lib/server/job-request.ts via web/fixtures/parity/generate.mjs',
	claim_class: 'synthetic_fixture',
	placeholder_source_artifact_id: placeholder,
	requests
};
writeFileSync(new URL('requests.json', here), JSON.stringify(document, null, 2) + '\n');
console.log(JSON.stringify({ written: requests.length }));
