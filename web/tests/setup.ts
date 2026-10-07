// Sealed property-test parameters (WEB_TESTS_S3.md sections 4.4 and 9): one seed, 200 runs per property.
import fc from 'fast-check';

export const PROPERTY_SEED = 20261007;
export const PROPERTY_RUNS = 200;

fc.configureGlobal({ seed: PROPERTY_SEED, numRuns: PROPERTY_RUNS });
