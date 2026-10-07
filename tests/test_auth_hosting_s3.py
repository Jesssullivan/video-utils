"""S3 auth_hosting lane tests (docs/spec/sprints/AUTH_HOSTING_S3.md section 6).

Stdlib only. Static checks always run. Node-gated checks run the pure ES auth modules under
web/src/lib/server/auth/ with plain `node` (no build, no network) and skip with an explicit reason
when `node` is absent. RSA keys are generated per run inside the node harness
(`generateKeyPairSync('rsa', {modulusLength: 2048})`); no key material is committed. The JWKS
fetch is a stub; the clock is fixed at now = 1_900_000_000. Every subprocess has a timeout <= 60 s.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WEB = REPO / "web"
AUTH = WEB / "src" / "lib" / "server" / "auth"
DEPLOY = REPO / "deploy"
K8S = DEPLOY / "k8s"
CLOUDFLARE = DEPLOY / "cloudflare"
RESEARCH = REPO / "docs" / "research" / "2026-10-07-estate-auth-hosting.md"
RECEIPT_DIR = REPO / "docs" / "agent-notes" / "sprints" / "20261007-s3"
NODE_TIMEOUT_S = 60

ERROR_KEYS = ["status", "code", "message", "upstream_status", "upstream_code", "upstream_detail_code"]
S2_LOOPBACK_MESSAGE = "This app answers only on a loopback Host (127.0.0.1, [::1] or localhost)."
ZERO_DIGEST = "sha256:" + "0" * 64
ALL_INTERFACES = ".".join(["0"] * 4)  # assembled so no web/ file needs the literal

UNKNOWN_FIELDS = {
    "public_hostname": None,
    "cloudflare_tunnel_id": None,
    "access_application_aud": None,
    "access_idp_ids": None,
    "cluster_target": "unknown",
    "namespace_exists": "unknown",
    "storage_class": "unknown",
    "cloudflared_namespace": "unknown",
    "container_image_digest": None,
    "container_built": False,
    "control_api_colocation": "unresolved",
    "tsidp_claims_in_access_jwt": "unknown",
    "assertion_idp_visible_to_app": "unknown",
    "tailscale_serve_identity": "not_accepted",
    "applied": False,
    "served_proof": "not_run",
}

# Section-3 estate sources: repo identifier -> remote default-branch tip recorded at the freeze.
ESTATE_SOURCES = {
    "tinyland-inc/xoxd.ai": "cc570c3c1079cc5754840395184f0c1a6fece97f",
    "xoxd-ai/tinyland.dev": "7422982619e357d31a0ddf0affdf8dedd0b51a93",
    "Great-Falls-Tool-Bus/great-falls-tool-bus-infra": "bb969bea496926b19f9350857a91da9d02a5f2c5",
    "Great-Falls-Tool-Bus/greatfallstoolbus.org": "b7f5b29690c72dbe777f1058bf8e88acaca3ab31",
    "Jesssullivan/gftb-site": "849af37beaaa8675a9115b741aeee7a0ba13b8f4",
    "tinyland-inc/massage-ithaca-portal": "fda9163fb9847c8b10a1b7ae4bc1fd8bddeb793e",
    "xoxd-ai/lab": None,  # tip moved during the lane; any recorded 40-hex commit is accepted
    "tinyland-inc/tinyland-infra": None,
    "tinyland-inc/GloriousFlywheel": "aacc52916c9160b178105e628ed18fb95c8338d1",
}

# --------------------------------------------------------------------------------------
# Node harness (one run per test session; results cached)
# --------------------------------------------------------------------------------------

HARNESS = r"""
import { generateKeyPairSync, sign, createHmac } from 'node:crypto';
import { pathToFileURL } from 'node:url';

const dir = process.env.AUTH_DIR;
const load = (name) => import(pathToFileURL(`${dir}/${name}`).href);
const cf = await load('cf-access.js');
const al = await load('allowlist.js');
const md = await load('mode.js');
const gt = await load('gate.js');

const NOW = 1_900_000_000;
const TEAM = 'videoutils-test.cloudflareaccess.com';
const ISS = `https://${TEAM}`;
const AUD = 'AudTagVideoUtils0123456789abcdefXYZ';
const AUD2 = 'SecondAudTag9876543210fedcba';
const KID = 'kid-test-1';
const HOST = 'video-utils.example.org';
const OPERATOR = 'operator@example.org';
const ENV = {
	VIDEO_UTILS_AUTH_MODE: 'tailnet',
	VIDEO_UTILS_CF_ACCESS_TEAM_DOMAIN: TEAM,
	VIDEO_UTILS_CF_ACCESS_AUDS: ` ${AUD} , ${AUD2},${AUD}`,
	VIDEO_UTILS_OPERATOR_ALLOWLIST: ` ${OPERATOR.toUpperCase()} , second@example.org`,
	VIDEO_UTILS_PUBLIC_HOSTS: HOST,
	ORIGIN: `https://${HOST}`,
};

const kp = generateKeyPairSync('rsa', { modulusLength: 2048 });
const kp2 = generateKeyPairSync('rsa', { modulusLength: 2048 });
const weak = generateKeyPairSync('rsa', { modulusLength: 1024 });
const jwk = { ...kp.publicKey.export({ format: 'jwk' }), kid: KID, use: 'sig', alg: 'RS256' };
const b64 = (v) => Buffer.from(typeof v === 'string' ? v : JSON.stringify(v)).toString('base64url');
function token(claims, { header = { alg: 'RS256', kid: KID, typ: 'JWT' }, key = kp.privateKey } = {}) {
	const h = b64(header);
	const p = b64(claims);
	return `${h}.${p}.${sign('sha256', Buffer.from(`${h}.${p}`), key).toString('base64url')}`;
}
const base = { iss: ISS, aud: [AUD], email: 'Operator@Example.org', sub: 'synthetic', iat: NOW - 10, nbf: NOW - 10, exp: NOW + 600 };
const staticResolver = async (kid) => (kid === KID ? kp.publicKey : null);

async function gate(assertion, { env = ENV, host = HOST, resolver = staticResolver } = {}) {
	return gt.gateRequest(
		{ env, host, assertion },
		{ keyResolverFor: () => resolver, nowSeconds: () => NOW }
	);
}
async function verify(assertion, resolveKey = staticResolver) {
	return cf.verifyAccessAssertion(assertion, { issuer: ISS, auds: [AUD, AUD2], resolveKey, nowSeconds: NOW });
}
const summarize = async (assertion) => {
	const v = await verify(assertion);
	const g = await gate(assertion);
	return { verify: v, gate: g.action === 'resolve' ? { action: 'resolve', operator: g.operator } : { action: 'refuse', httpStatus: g.httpStatus, code: g.error.code } };
};

const out = {};
// ---- J cases -------------------------------------------------------------------------
const hdrNone = b64({ alg: 'none', kid: KID });
const hsHeader = b64({ alg: 'HS256', kid: KID, typ: 'JWT' });
const hsPayload = b64(base);
const hsSecret = kp.publicKey.export({ format: 'pem', type: 'spki' });
const hsSig = createHmac('sha256', hsSecret).update(`${hsHeader}.${hsPayload}`).digest('base64url');
const big = token({ ...base, pad: 'x'.repeat(9000) });
out.J1 = await summarize(token(base));
out.J2 = await summarize(token({ ...base, aud: 'WrongAudTag0123456789' }));
out.J3 = await summarize(token({ ...base, aud: ['UnrelatedAudTag000000', AUD2] }));
out.J4 = await summarize(token({ ...base, iss: 'https://other-team.cloudflareaccess.com' }));
out.J5 = await summarize(token({ ...base, exp: NOW - 61 }));
out.J6 = await summarize(token({ ...base, exp: NOW - 30 }));
out.J7 = await summarize(token({ ...base, nbf: NOW + 120 }));
out.J8 = { missing: await summarize(null), empty: await summarize('') };
out.J9 = {
	two_segments: await summarize('abc.def'),
	bad_base64url: await summarize('ab$c.d*ef.ghi'),
	too_large: await summarize(big),
	too_large_bytes: Buffer.byteLength(big),
};
out.J10 = {
	none_empty_sig: await summarize(`${hdrNone}.${b64(base)}.`),
	none_fake_sig: await summarize(`${hdrNone}.${b64(base)}.AAAA`),
	hs256_public_key_secret: await summarize(`${hsHeader}.${hsPayload}.${hsSig}`),
};
out.J11 = await summarize(token(base, { key: kp2.privateKey }));
out.J12 = { missing: await summarize(token({ ...base, email: undefined })), empty: await summarize(token({ ...base, email: '' })) };
out.J13 = await summarize(token({ ...base, email: 'stranger@example.org' }));
out.J14 = await summarize(token({ ...base, aud: [AUD.toLowerCase()] }));
out.J_extra = {
	aud_string: await summarize(token({ ...base, aud: AUD })),
	iat_future: await summarize(token({ ...base, iat: NOW + 120 })),
	exp_missing: await summarize(token({ ...base, exp: undefined })),
	es256_alg: await summarize(token(base, { header: { alg: 'ES256', kid: KID } })),
	kid_missing: await summarize(token(base, { header: { alg: 'RS256' } })),
};

// ---- C cases: JWKS cache ----------------------------------------------------------------
function stubFetch(body = JSON.stringify({ keys: [jwk] })) {
	const s = { calls: 0, fail: false, body, urls: [], inits: [] };
	s.fn = async (url, init) => {
		s.calls += 1;
		s.urls.push(url);
		s.inits.push({ redirect: init.redirect, hasSignal: init.signal instanceof AbortSignal, method: init.method });
		if (s.fail) throw new TypeError('synthetic network failure');
		return new Response(s.body, { status: 200, headers: { 'content-type': 'application/json' } });
	};
	return s;
}
const JWKS_URL = `https://${TEAM}/cdn-cgi/access/certs`;
function cache(stub, clock) {
	return cf.createJwksCache({ jwksUrl: JWKS_URL, fetchImpl: stub.fn, nowMs: () => clock.t });
}
const good = token(base);
const unknownKid = token(base, { header: { alg: 'RS256', kid: 'kid-unknown' }, key: kp2.privateKey });
{
	const s = stubFetch(); const clock = { t: 1_000_000 }; const c = cache(s, clock);
	const results = [];
	for (let i = 0; i < 10; i++) { results.push((await verify(good, c.resolveKey)).ok); clock.t += 1000; }
	out.C1 = { fetches: s.calls, all_ok: results.every(Boolean), url: s.urls[0], init: s.inits[0] };
}
{
	const s = stubFetch(); const clock = { t: 1_000_000 }; const c = cache(s, clock);
	const first = (await verify(good, c.resolveKey)).ok;
	clock.t += 31_000;
	const a = await verify(unknownKid, c.resolveKey);
	const afterFirstUnknown = s.calls;
	clock.t += 5_000;
	const b = await verify(unknownKid, c.resolveKey);
	out.C2 = { first_ok: first, unknown_1: a, unknown_2: b, fetches_after_first_unknown: afterFirstUnknown, fetches_after_second_unknown: s.calls };
}
{
	const s = stubFetch(); const clock = { t: 1_000_000 }; const c = cache(s, clock);
	const first = (await verify(good, c.resolveKey)).ok;
	clock.t += 11 * 60_000; s.fail = true;
	const stale = await verify(good, c.resolveKey);
	const fetchesAtStale = s.calls;
	clock.t += 50 * 60_000;
	const tooOld = await verify(good, c.resolveKey);
	out.C3 = { first_ok: first, stale_allowed: stale, fetches_at_stale: fetchesAtStale, beyond_60_min: tooOld };
}
{
	const s = stubFetch(); s.fail = true; const clock = { t: 1_000_000 }; const c = cache(s, clock);
	out.C4 = { result: await verify(good, c.resolveKey), fetches: s.calls };
}
{
	const huge = JSON.stringify({ keys: [jwk], pad: 'x'.repeat(70 * 1024) });
	const s = stubFetch(huge); const clock = { t: 1_000_000 }; const c = cache(s, clock);
	const weakJwk = { ...weak.publicKey.export({ format: 'jwk' }), kid: KID };
	const s2 = stubFetch(JSON.stringify({ keys: [weakJwk, { kty: 'EC', kid: 'ec', crv: 'P-256', x: 'a', y: 'b' }] }));
	const c2 = cache(s2, { t: 1_000_000 });
	const weakToken = token(base, { key: weak.privateKey });
	out.C_extra = { body_over_cap: await verify(good, c.resolveKey), weak_and_non_rsa_keys_ignored: await verify(weakToken, c2.resolveKey) };
}

// ---- A1 allowlist ----------------------------------------------------------------------
const many = (n) => Array.from({ length: n }, (_, i) => `op${i}@example.org`).join(',');
const parsed = al.parseAllowlist(' A@Example.org , b@example.org,a@example.org ');
out.A1 = {
	normalized: parsed.ok ? [...parsed.emails].sort() : parsed,
	wildcard: al.parseAllowlist('*@example.org'),
	star_domain: al.parseAllowlist('a@*.example.org'),
	domain_only_at: al.parseAllowlist('@example.org'),
	bare_domain: al.parseAllowlist('example.org'),
	empty_entry: al.parseAllowlist('a@example.org,,b@example.org'),
	empty: al.parseAllowlist(''),
	undefined: al.parseAllowlist(undefined),
	thirty_two: al.parseAllowlist(many(32)).ok,
	thirty_three: al.parseAllowlist(many(33)),
	display_name: al.parseAllowlist('Op <op@example.org>'),
	match_case_insensitive: parsed.ok && al.isAllowlisted(parsed.emails, 'A@EXAMPLE.ORG'),
	non_member: parsed.ok && al.isAllowlisted(parsed.emails, 'c@example.org'),
	empty_identity: parsed.ok && al.isAllowlisted(parsed.emails, ''),
};

// ---- M1/M2 mode + config -----------------------------------------------------------------
out.M1 = Object.fromEntries(
	[['unset', undefined], ['empty', ''], ['tailnet', 'tailnet'], ['upper', 'TAILNET'], ['loopback_literal', 'loopback'], ['padded', ' tailnet'], ['public', 'public']]
		.map(([k, v]) => [k, md.parseAuthMode(v).kind])
);
const complete = md.resolveAuthConfig(ENV);
out.M_complete = complete.mode === 'tailnet'
	? { mode: complete.mode, issuer: complete.config.issuer, jwksUrl: complete.config.jwksUrl, auds: complete.config.auds, allowlist: [...complete.config.allowlist].sort(), publicHosts: complete.config.publicHosts }
	: complete;
const variants = {
	team_missing: { VIDEO_UTILS_CF_ACCESS_TEAM_DOMAIN: undefined },
	team_other_domain: { VIDEO_UTILS_CF_ACCESS_TEAM_DOMAIN: 'evil.example.com' },
	team_with_scheme: { VIDEO_UTILS_CF_ACCESS_TEAM_DOMAIN: `https://${TEAM}` },
	team_suffix_trick: { VIDEO_UTILS_CF_ACCESS_TEAM_DOMAIN: 'x.cloudflareaccess.com.evil.example' },
	auds_missing: { VIDEO_UTILS_CF_ACCESS_AUDS: undefined },
	auds_short: { VIDEO_UTILS_CF_ACCESS_AUDS: 'short' },
	auds_bad_chars: { VIDEO_UTILS_CF_ACCESS_AUDS: 'AudTag-with-dashes-0123' },
	auds_too_many: { VIDEO_UTILS_CF_ACCESS_AUDS: Array.from({ length: 9 }, (_, i) => `AudTagNumber${i}abcdefgh`).join(',') },
	auds_empty_entry: { VIDEO_UTILS_CF_ACCESS_AUDS: `${AUD},,${AUD2}` },
	allowlist_missing: { VIDEO_UTILS_OPERATOR_ALLOWLIST: undefined },
	allowlist_wildcard: { VIDEO_UTILS_OPERATOR_ALLOWLIST: '*@example.org' },
	allowlist_domain: { VIDEO_UTILS_OPERATOR_ALLOWLIST: '@example.org' },
	hosts_missing: { VIDEO_UTILS_PUBLIC_HOSTS: undefined },
	hosts_with_port: { VIDEO_UTILS_PUBLIC_HOSTS: `${HOST}:443` },
	hosts_with_scheme: { VIDEO_UTILS_PUBLIC_HOSTS: `https://${HOST}` },
	hosts_too_many: { VIDEO_UTILS_PUBLIC_HOSTS: 'a.example.org,b.example.org,c.example.org,d.example.org,e.example.org' },
	origin_missing: { ORIGIN: undefined },
	origin_http: { ORIGIN: `http://${HOST}` },
	origin_other_host: { ORIGIN: 'https://elsewhere.example.org' },
	origin_with_path: { ORIGIN: `https://${HOST}/` },
};
const variableFor = (k) => ({ team: 'VIDEO_UTILS_CF_ACCESS_TEAM_DOMAIN', auds: 'VIDEO_UTILS_CF_ACCESS_AUDS', allowlist: 'VIDEO_UTILS_OPERATOR_ALLOWLIST', hosts: 'VIDEO_UTILS_PUBLIC_HOSTS', origin: 'ORIGIN' })[k.split('_')[0]];
out.M2 = {};
for (const [name, patch] of Object.entries(variants)) {
	const env = { ...ENV, ...patch };
	for (const [k, v] of Object.entries(patch)) if (v === undefined) delete env[k];
	const r = md.resolveAuthConfig(env);
	const g = await gate(token(base), { env });
	out.M2[name] = { mode: r.mode, names_variable: r.mode === 'unconfigured' && r.problems.includes(variableFor(name)), gate_status: g.action === 'refuse' ? g.httpStatus : 200, gate_code: g.action === 'refuse' ? g.error.code : null, problems_text: r.mode === 'unconfigured' ? r.problems.join(',') : '' };
}

// ---- G1 gate matrix ---------------------------------------------------------------------
const row = (g) => (g.action === 'refuse' ? { status: g.httpStatus, code: g.error.code, body: g.error, keys: Object.keys(g.error) } : { status: 'resolve', operator: g.operator, mode: g.mode });
out.G1 = {
	loopback_foreign_host: row(await gate(null, { env: {}, host: 'rebind.example.org' })),
	loopback_missing_host: row(await gate(null, { env: {}, host: null })),
	loopback_loopback_host: row(await gate(null, { env: {}, host: '127.0.0.1:5173' })),
	loopback_ipv6_host: row(await gate(null, { env: {}, host: '[::1]:3000' })),
	invalid_mode: row(await gate(token(base), { env: { VIDEO_UTILS_AUTH_MODE: 'public' }, host: '127.0.0.1' })),
	tailnet_unconfigured: row(await gate(token(base), { env: { VIDEO_UTILS_AUTH_MODE: 'tailnet' }, host: HOST })),
	tailnet_wrong_host: row(await gate(token(base), { host: 'other.example.org' })),
	tailnet_loopback_host: row(await gate(token(base), { host: '127.0.0.1' })),
	tailnet_missing_assertion: row(await gate(null)),
	tailnet_invalid_assertion: row(await gate(token({ ...base, aud: 'WrongAudTag0123456789' }))),
	tailnet_not_allowlisted: row(await gate(token({ ...base, email: 'stranger@example.org' }))),
	tailnet_allowed: row(await gate(token(base))),
	tailnet_host_case_insensitive: row(await gate(token(base), { host: HOST.toUpperCase() })),
};
out.constants = { loopback_message: gt.LOOPBACK_HOST_MESSAGE, default_loopback_source: gt.DEFAULT_LOOPBACK_HOST.source, header: gt.CF_ACCESS_JWT_HEADER };
process.stdout.write(JSON.stringify(out));
"""

_HARNESS_CACHE: dict[str, object] = {}


def _node_results(case: unittest.TestCase) -> dict:
    if shutil.which("node") is None:
        case.skipTest("node not on PATH")
    if "results" not in _HARNESS_CACHE:
        proc = subprocess.run(
            ["node", "--input-type=module", "-"],
            input=HARNESS,
            capture_output=True,
            text=True,
            timeout=NODE_TIMEOUT_S,
            env={**_clean_env(), "AUTH_DIR": str(AUTH)},
        )
        if proc.returncode != 0:
            _HARNESS_CACHE["results"] = {"__error__": proc.stderr[-4000:]}
        else:
            _HARNESS_CACHE["results"] = json.loads(proc.stdout)
    results = _HARNESS_CACHE["results"]
    assert isinstance(results, dict)
    if "__error__" in results:
        case.fail(f"node harness failed:\n{results['__error__']}")
    return results


def _clean_env(**overrides: str | None) -> dict[str, str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in {"HOST", "PORT", "SOCKET_PATH", "ORIGIN"} and not k.startswith("VIDEO_UTILS_")
    }
    for key, value in overrides.items():
        if value is not None:
            env[key] = value
    return env


def _denied(result: dict) -> bool:
    return result["verify"]["ok"] is False and result["gate"] == {
        "action": "refuse", "httpStatus": 403, "code": "bff_identity_refused"}


# --------------------------------------------------------------------------------------
# J: JWT verification (node)
# --------------------------------------------------------------------------------------


class JwtVerificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.r = _node_results(self)

    def test_j01_valid_allowlisted_lowercased(self) -> None:
        j = self.r["J1"]
        self.assertTrue(j["verify"]["ok"])
        self.assertEqual(j["verify"]["email"], "operator@example.org")
        self.assertEqual(j["gate"], {"action": "resolve", "operator": "operator@example.org"})

    def test_j02_wrong_aud(self) -> None:
        self.assertTrue(_denied(self.r["J2"]))
        self.assertEqual(self.r["J2"]["verify"]["reason"], "aud_mismatch")

    def test_j03_aud_array_one_configured(self) -> None:
        self.assertEqual(self.r["J3"]["gate"]["action"], "resolve")
        self.assertEqual(self.r["J_extra"]["aud_string"]["gate"]["action"], "resolve")

    def test_j04_wrong_iss(self) -> None:
        self.assertTrue(_denied(self.r["J4"]))
        self.assertEqual(self.r["J4"]["verify"]["reason"], "iss_mismatch")

    def test_j05_expired_beyond_skew(self) -> None:
        self.assertTrue(_denied(self.r["J5"]))
        self.assertEqual(self.r["J5"]["verify"]["reason"], "expired")

    def test_j06_within_skew(self) -> None:
        self.assertEqual(self.r["J6"]["gate"]["action"], "resolve")

    def test_j07_nbf_future(self) -> None:
        self.assertTrue(_denied(self.r["J7"]))
        self.assertTrue(_denied(self.r["J_extra"]["iat_future"]))

    def test_j08_missing_or_empty_header(self) -> None:
        for sub in ("missing", "empty"):
            with self.subTest(sub=sub):
                self.assertTrue(_denied(self.r["J8"][sub]))
                self.assertEqual(self.r["J8"][sub]["verify"]["reason"], "assertion_missing")

    def test_j09_malformed(self) -> None:
        j = self.r["J9"]
        self.assertGreater(j["too_large_bytes"], 8 * 1024)
        for sub, reason in (("two_segments", "assertion_malformed"), ("bad_base64url", "assertion_malformed"),
                            ("too_large", "assertion_too_large")):
            with self.subTest(sub=sub):
                self.assertTrue(_denied(j[sub]))
                self.assertEqual(j[sub]["verify"]["reason"], reason)

    def test_j10_alg_none_and_hs256(self) -> None:
        for sub in ("none_empty_sig", "none_fake_sig", "hs256_public_key_secret"):
            with self.subTest(sub=sub):
                self.assertTrue(_denied(self.r["J10"][sub]))
        self.assertEqual(self.r["J10"]["hs256_public_key_secret"]["verify"]["reason"], "alg_refused")
        self.assertEqual(self.r["J10"]["none_fake_sig"]["verify"]["reason"], "alg_refused")
        self.assertTrue(_denied(self.r["J_extra"]["es256_alg"]))
        self.assertTrue(_denied(self.r["J_extra"]["kid_missing"]))

    def test_j11_unpublished_key_same_kid(self) -> None:
        self.assertTrue(_denied(self.r["J11"]))
        self.assertEqual(self.r["J11"]["verify"]["reason"], "signature_invalid")

    def test_j12_missing_or_empty_email(self) -> None:
        for sub in ("missing", "empty"):
            with self.subTest(sub=sub):
                self.assertTrue(_denied(self.r["J12"][sub]))
                self.assertEqual(self.r["J12"][sub]["verify"]["reason"], "email_missing")
        self.assertTrue(_denied(self.r["J_extra"]["exp_missing"]))

    def test_j13_not_allowlisted(self) -> None:
        j = self.r["J13"]
        self.assertTrue(j["verify"]["ok"], "signature and claims verify; the allowlist denies")
        self.assertEqual(j["gate"], {"action": "refuse", "httpStatus": 403, "code": "bff_identity_refused"})

    def test_j14_aud_case_differs(self) -> None:
        self.assertTrue(_denied(self.r["J14"]))


# --------------------------------------------------------------------------------------
# C: JWKS cache (node, stub fetch, injected clock)
# --------------------------------------------------------------------------------------


class JwksCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.r = _node_results(self)

    def test_c1_single_fetch_for_ten_verifications(self) -> None:
        c = self.r["C1"]
        self.assertEqual(c["fetches"], 1)
        self.assertTrue(c["all_ok"])
        self.assertEqual(c["url"], "https://videoutils-test.cloudflareaccess.com/cdn-cgi/access/certs")
        self.assertEqual(c["init"], {"redirect": "error", "hasSignal": True, "method": "GET"})

    def test_c2_unknown_kid_one_refetch_then_cooldown(self) -> None:
        c = self.r["C2"]
        self.assertTrue(c["first_ok"])
        self.assertEqual(c["fetches_after_first_unknown"], 2, "initial fetch plus exactly one refetch")
        self.assertEqual(c["fetches_after_second_unknown"], 2, "second unknown kid within 30 s: no fetch")
        self.assertEqual(c["unknown_1"]["reason"], "kid_unresolved")
        self.assertEqual(c["unknown_2"]["reason"], "kid_unresolved")

    def test_c3_stale_keys_on_refresh_failure(self) -> None:
        c = self.r["C3"]
        self.assertTrue(c["first_ok"])
        self.assertTrue(c["stale_allowed"]["ok"])
        self.assertEqual(c["fetches_at_stale"], 2)
        self.assertFalse(c["beyond_60_min"]["ok"])

    def test_c4_no_keys_ever_fetched(self) -> None:
        c = self.r["C4"]
        self.assertFalse(c["result"]["ok"])
        self.assertEqual(c["result"]["reason"], "kid_unresolved")
        self.assertEqual(c["fetches"], 1)

    def test_c_extra_body_cap_and_key_filtering(self) -> None:
        c = self.r["C_extra"]
        self.assertFalse(c["body_over_cap"]["ok"])
        self.assertFalse(c["weak_and_non_rsa_keys_ignored"]["ok"])


# --------------------------------------------------------------------------------------
# A/M/G: allowlist, mode/config and the gate matrix (node)
# --------------------------------------------------------------------------------------


class AllowlistModeGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.r = _node_results(self)

    def test_a1_allowlist_parsing(self) -> None:
        a = self.r["A1"]
        self.assertEqual(a["normalized"], ["a@example.org", "b@example.org"])
        for sub, reason in (("wildcard", "allowlist_wildcard"), ("star_domain", "allowlist_wildcard"),
                            ("domain_only_at", "allowlist_invalid_entry"), ("bare_domain", "allowlist_invalid_entry"),
                            ("empty_entry", "allowlist_empty_entry"), ("empty", "allowlist_missing"),
                            ("undefined", "allowlist_missing"), ("thirty_three", "allowlist_too_many"),
                            ("display_name", "allowlist_invalid_entry")):
            with self.subTest(sub=sub):
                self.assertEqual(a[sub], {"ok": False, "reason": reason})
        self.assertTrue(a["thirty_two"])
        self.assertTrue(a["match_case_insensitive"])
        self.assertFalse(a["non_member"])
        self.assertFalse(a["empty_identity"])

    def test_m1_mode_parsing(self) -> None:
        self.assertEqual(self.r["M1"], {
            "unset": "loopback", "empty": "loopback", "tailnet": "tailnet", "upper": "invalid",
            "loopback_literal": "invalid", "padded": "invalid", "public": "invalid"})

    def test_m2_each_variable_missing_or_invalid(self) -> None:
        complete = self.r["M_complete"]
        self.assertEqual(complete["mode"], "tailnet")
        self.assertEqual(complete["issuer"], "https://videoutils-test.cloudflareaccess.com")
        self.assertEqual(complete["jwksUrl"], "https://videoutils-test.cloudflareaccess.com/cdn-cgi/access/certs")
        self.assertEqual(complete["auds"], ["AudTagVideoUtils0123456789abcdefXYZ", "SecondAudTag9876543210fedcba"])
        self.assertEqual(complete["allowlist"], ["operator@example.org", "second@example.org"])
        self.assertGreaterEqual(len(self.r["M2"]), 15)
        for name, result in self.r["M2"].items():
            with self.subTest(variant=name):
                self.assertEqual(result["mode"], "unconfigured")
                self.assertTrue(result["names_variable"], result["problems_text"])
                self.assertEqual((result["gate_status"], result["gate_code"]), (503, "bff_auth_unconfigured"))
                for leak in ("evil", "short", "@", "https", "443"):
                    self.assertNotIn(leak, result["problems_text"], "problems name variables only")

    def test_g1_gate_matrix(self) -> None:
        g = self.r["G1"]
        expected = {
            "loopback_foreign_host": (421, "bff_host_refused"),
            "loopback_missing_host": (421, "bff_host_refused"),
            "invalid_mode": (503, "bff_auth_unconfigured"),
            "tailnet_unconfigured": (503, "bff_auth_unconfigured"),
            "tailnet_wrong_host": (421, "bff_host_refused"),
            "tailnet_loopback_host": (421, "bff_host_refused"),
            "tailnet_missing_assertion": (403, "bff_identity_refused"),
            "tailnet_invalid_assertion": (403, "bff_identity_refused"),
            "tailnet_not_allowlisted": (403, "bff_identity_refused"),
        }
        for name, (status, code) in expected.items():
            with self.subTest(row=name):
                self.assertEqual((g[name]["status"], g[name]["code"]), (status, code))
                self.assertEqual(g[name]["keys"], ERROR_KEYS)
                self.assertEqual([g[name]["body"][k] for k in ERROR_KEYS[3:]], [None, None, None])
        for name in ("loopback_loopback_host", "loopback_ipv6_host"):
            self.assertEqual(g[name], {"status": "resolve", "operator": None, "mode": "loopback"})
        self.assertEqual(g["tailnet_allowed"], {"status": "resolve", "operator": "operator@example.org", "mode": "tailnet"})
        self.assertEqual(g["tailnet_host_case_insensitive"]["status"], "resolve")
        # Unchanged S2 loopback refusal body; invalid and non-allowlisted identities are indistinguishable.
        self.assertEqual(g["loopback_foreign_host"]["body"]["message"], S2_LOOPBACK_MESSAGE)
        self.assertEqual(g["tailnet_missing_assertion"]["body"], g["tailnet_not_allowlisted"]["body"])
        self.assertEqual(g["tailnet_invalid_assertion"]["body"], g["tailnet_not_allowlisted"]["body"])

    def test_g2_constants(self) -> None:
        c = self.r["constants"]
        self.assertEqual(c["loopback_message"], S2_LOOPBACK_MESSAGE)
        self.assertEqual(c["header"], "cf-access-jwt-assertion")
        http_ts = (WEB / "src" / "lib" / "server" / "http.ts").read_text()
        match = re.search(r"export const LOOPBACK_HOST = /(.+)/;", http_ts)
        self.assertIsNotNone(match)
        self.assertEqual(c["default_loopback_source"], match.group(1))


# --------------------------------------------------------------------------------------
# L: launcher and hooks (node subprocess on a copy of serve.js with a stub build)
# --------------------------------------------------------------------------------------

STUB_BUILD = "console.log(JSON.stringify({ started: true, host: process.env.HOST }));\n"
TAILNET_ENV = {
    "VIDEO_UTILS_AUTH_MODE": "tailnet",
    "VIDEO_UTILS_CF_ACCESS_TEAM_DOMAIN": "videoutils-test.cloudflareaccess.com",
    "VIDEO_UTILS_CF_ACCESS_AUDS": "AudTagVideoUtils0123456789abcdefXYZ",
    "VIDEO_UTILS_OPERATOR_ALLOWLIST": "operator@example.org",
    "VIDEO_UTILS_PUBLIC_HOSTS": "video-utils.example.org",
    "ORIGIN": "https://video-utils.example.org",
}


class LauncherTests(unittest.TestCase):
    tmp: tempfile.TemporaryDirectory
    root: Path

    @classmethod
    def setUpClass(cls) -> None:
        if shutil.which("node") is None:
            raise unittest.SkipTest("node not on PATH")
        cls.tmp = tempfile.TemporaryDirectory(prefix="auth-hosting-serve-")
        cls.root = Path(cls.tmp.name)
        shutil.copy(WEB / "serve.js", cls.root / "serve.js")
        (cls.root / "package.json").write_text('{"type": "module"}\n')
        (cls.root / "build").mkdir()
        (cls.root / "build" / "index.js").write_text(STUB_BUILD)
        shutil.copytree(AUTH, cls.root / "src" / "lib" / "server" / "auth")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def _serve(self, **env: str | None) -> subprocess.CompletedProcess:
        return subprocess.run(["node", "serve.js"], cwd=self.root, capture_output=True, text=True,
                              timeout=20, env=_clean_env(**env))

    def _started(self, proc: subprocess.CompletedProcess) -> dict | None:
        line = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
        return json.loads(line) if line.startswith("{") else None

    def test_l1_loopback_default_unchanged(self) -> None:
        for env, host in (({}, "127.0.0.1"), ({"HOST": "::1"}, "::1"), ({"VIDEO_UTILS_AUTH_MODE": ""}, "127.0.0.1")):
            with self.subTest(env=env):
                proc = self._serve(**env)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(self._started(proc), {"started": True, "host": host})
        for host in (ALL_INTERFACES, "localhost", "192.0.2.1"):
            with self.subTest(host=host):
                proc = self._serve(HOST=host)
                self.assertEqual(proc.returncode, 2, proc.stderr)
                self.assertIn("refusing HOST", proc.stderr)
                self.assertIsNone(self._started(proc))
        proc = self._serve(SOCKET_PATH="/tmp/video-utils.sock")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("refusing SOCKET_PATH", proc.stderr)
        self.assertIsNone(self._started(proc))

    def test_l2_tailnet_requires_complete_config(self) -> None:
        proc = self._serve(**TAILNET_ENV, HOST=ALL_INTERFACES)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self._started(proc), {"started": True, "host": ALL_INTERFACES})
        for missing in [k for k in TAILNET_ENV if k != "VIDEO_UTILS_AUTH_MODE"]:
            with self.subTest(missing=missing):
                env = {**TAILNET_ENV, missing: None, "HOST": ALL_INTERFACES}
                proc = self._serve(**env)
                self.assertEqual(proc.returncode, 2, proc.stderr)
                self.assertIsNone(self._started(proc))
                self.assertIn(missing, proc.stderr)
                for value in TAILNET_ENV.values():
                    if value != "tailnet":
                        self.assertNotIn(value, proc.stderr, "diagnostics never echo configured values")
        for extra in ({"HOST": None}, {"HOST": "http://x"}, {"SOCKET_PATH": "/tmp/x.sock", "HOST": ALL_INTERFACES}):
            with self.subTest(extra=extra):
                proc = self._serve(**{**TAILNET_ENV, **extra})
                self.assertEqual(proc.returncode, 2, proc.stderr)
                self.assertIsNone(self._started(proc))
        for mode in ("public", "TAILNET", "loopback"):
            with self.subTest(mode=mode):
                proc = self._serve(VIDEO_UTILS_AUTH_MODE=mode, HOST="127.0.0.1")
                self.assertEqual(proc.returncode, 2, proc.stderr)
                self.assertIsNone(self._started(proc))


class HooksStaticTests(unittest.TestCase):
    def test_l3_hooks_uses_loopback_host_and_only_gate(self) -> None:
        hooks = (WEB / "src" / "hooks.server.ts").read_text()
        self.assertRegex(hooks, r"import \{[^}]*LOOPBACK_HOST[^}]*\} from '\$lib/server/http'")
        self.assertIn("loopbackHost: LOOPBACK_HOST", hooks)
        auth_imports = re.findall(r"from '\$lib/server/auth/([^']+)'", hooks)
        self.assertEqual(auth_imports, ["gate.js"])
        self.assertIn("$env/dynamic/private", hooks)
        self.assertEqual(len(re.findall(r"headers\.get\(", hooks)), 2, "only Host and the Access assertion are read")
        self.assertNotIn("locals", hooks.split("export const handle", 1)[1])
        serve = (WEB / "serve.js").read_text()
        self.assertLess(serve.index("process.exit(REFUSAL_EXIT_CODE)"), serve.index("import('./build/index.js')"))

    def test_l4_untrusted_identity_inputs_never_read(self) -> None:
        sources = {p.name: p.read_text() for p in AUTH.glob("*.js")}
        self.assertEqual(set(sources), {"mode.js", "cf-access.js", "allowlist.js", "gate.js"})
        code_only = {
            name: "\n".join(line for line in text.splitlines() if not line.lstrip().startswith(("//", "*", "/*")))
            for name, text in sources.items()
        }
        for name, text in {**code_only, "hooks.server.ts": (WEB / "src" / "hooks.server.ts").read_text()}.items():
            with self.subTest(file=name):
                for needle in ("cf-access-authenticated-user-email", "cf_authorization", "tailscale-user",
                               "tailscale-app-capabilities", "process.env", "cookies"):
                    self.assertNotIn(needle, text.lower())
        # The only header read inside the auth modules is the JWKS response's content-length cap.
        header_reads = re.findall(r"headers\.get\(([^)]*)\)", "".join(code_only.values()))
        self.assertEqual(header_reads, ["'content-length'"])


# --------------------------------------------------------------------------------------
# K: deploy manifests, Containerfile and secret scan (static)
# --------------------------------------------------------------------------------------


def _deploy_json_files() -> list[Path]:
    return sorted([*DEPLOY.rglob("*.json"), K8S / "kustomization.yaml"])


def _k8s_objects() -> list[dict]:
    objects: list[dict] = []
    for path in sorted(K8S.glob("*.json")):
        doc = json.loads(path.read_text())
        objects.extend(doc["items"] if doc.get("kind") == "List" else [doc])
    return objects


def _walk(value: object):
    if isinstance(value, dict):
        for k, v in value.items():
            yield k, v
            yield from _walk(v)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


class DeployStaticTests(unittest.TestCase):
    def test_k1_manifests_parse(self) -> None:
        files = _deploy_json_files()
        self.assertGreaterEqual(len(files), 9)
        for path in files:
            with self.subTest(file=str(path.relative_to(REPO))):
                json.loads(path.read_text())
        kustomization = json.loads((K8S / "kustomization.yaml").read_text())
        self.assertEqual(kustomization["kind"], "Kustomization")
        self.assertEqual(kustomization["namespace"], "video-utils")
        for resource in kustomization["resources"]:
            self.assertTrue((K8S / resource).is_file(), resource)
        self.assertEqual(set(kustomization["resources"]), {p.name for p in K8S.glob("*.json")})

    def test_k2_deployment_invariants(self) -> None:
        objects = _k8s_objects()
        kinds = sorted(o["kind"] for o in objects)
        self.assertEqual(kinds, ["ConfigMap", "Deployment", "Namespace", "NetworkPolicy", "NetworkPolicy",
                                 "PersistentVolumeClaim", "Service"])
        for obj in objects:
            if obj["kind"] != "Namespace":
                self.assertEqual(obj["metadata"]["namespace"], "video-utils")
        dep = next(o for o in objects if o["kind"] == "Deployment")
        spec = dep["spec"]
        pod = spec["template"]["spec"]
        self.assertEqual(spec["replicas"], 1)
        self.assertEqual(spec["strategy"], {"type": "Recreate"})
        self.assertIs(pod["automountServiceAccountToken"], False)
        psc = pod["securityContext"]
        self.assertIs(psc["runAsNonRoot"], True)
        self.assertEqual((psc["runAsUser"], psc["fsGroup"]), (10001, 10001))
        self.assertEqual(psc["seccompProfile"], {"type": "RuntimeDefault"})
        for key in ("nodeSelector", "tolerations", "affinity", "hostNetwork", "hostPID", "hostIPC"):
            self.assertNotIn(key, pod)
        self.assertEqual(len(pod["containers"]), 1)
        c = pod["containers"][0]
        sc = c["securityContext"]
        self.assertIs(sc["allowPrivilegeEscalation"], False)
        self.assertIs(sc["readOnlyRootFilesystem"], True)
        self.assertEqual(sc["capabilities"], {"drop": ["ALL"]})
        for bound in ("requests", "limits"):
            self.assertEqual(set(c["resources"][bound]), {"cpu", "memory", "ephemeral-storage"})
        self.assertTrue(c["image"].endswith("@" + ZERO_DIGEST), c["image"])
        self.assertEqual(c["envFrom"], [{"configMapRef": {"name": "video-utils-web-config"}}])
        self.assertNotIn("env", c)
        for probe in ("startupProbe", "readinessProbe", "livenessProbe"):
            self.assertIn("tcpSocket", c[probe])
            self.assertNotIn("httpGet", c[probe])
        mounts = {m["mountPath"]: m["name"] for m in c["volumeMounts"]}
        volumes = {v["name"]: v for v in pod["volumes"]}
        self.assertEqual(volumes[mounts["/srv/video-utils/artifacts"]]["persistentVolumeClaim"]["claimName"],
                         "video-utils-artifacts")
        self.assertIn("emptyDir", volumes[mounts["/tmp"]])
        for key, value in _walk(objects):
            self.assertNotIn("gpu", str(key).lower())
            self.assertNotIn(key, ("hostPort", "hostNetwork", "nodePort", "hostPath"))
            if key == "type":
                self.assertNotIn(value, ("NodePort", "LoadBalancer"))
        svc = next(o for o in objects if o["kind"] == "Service")
        self.assertEqual(svc["spec"]["type"], "ClusterIP")
        self.assertFalse(any(o["kind"] in ("Ingress", "Secret", "Route", "IngressRoute") for o in objects))
        pvc = next(o for o in objects if o["kind"] == "PersistentVolumeClaim")
        self.assertEqual(pvc["metadata"]["name"], "video-utils-artifacts")
        self.assertEqual(pvc["spec"]["accessModes"], ["ReadWriteOnce"])
        self.assertIn("storage", pvc["spec"]["resources"]["requests"])
        self.assertNotIn("storageClassName", pvc["spec"])
        policies = [o for o in objects if o["kind"] == "NetworkPolicy"]
        deny = next(p for p in policies if "ingress" not in p["spec"])
        self.assertEqual((deny["spec"]["podSelector"], deny["spec"]["policyTypes"]), ({}, ["Ingress"]))
        allow = next(p for p in policies if "ingress" in p["spec"])
        self.assertEqual(len(allow["spec"]["ingress"]), 1)
        cm = next(o for o in objects if o["kind"] == "ConfigMap")
        self.assertEqual(cm["data"]["VIDEO_UTILS_AUTH_MODE"], "tailnet")
        for key in ("VIDEO_UTILS_CF_ACCESS_TEAM_DOMAIN", "VIDEO_UTILS_CF_ACCESS_AUDS",
                    "VIDEO_UTILS_OPERATOR_ALLOWLIST", "VIDEO_UTILS_PUBLIC_HOSTS", "ORIGIN"):
            self.assertEqual(cm["data"][key], "", f"{key} is supplied by the operator at apply")

    def test_k2b_cloudflare_plan_shape(self) -> None:
        route = json.loads((CLOUDFLARE / "video-utils-app-origin-routes.json").read_text())
        self.assertEqual(route["schemaVersion"], "tinyland.cloudflare-tunnel.app-origin.v1")
        self.assertEqual(route["service"], "http://video-utils-web.video-utils.svc.cluster.local:3000")
        self.assertEqual(route["catchAllService"], "http_status:404")
        for key in ("hostname", "tunnelId", "publicAppOrigin"):
            self.assertIsNone(route[key])
        self.assertIs(route["applied"], False)
        plan = json.loads((CLOUDFLARE / "video-utils-access-plan.json").read_text())
        app = plan["application"]
        self.assertEqual((app["type"], app["paths"], app["session_duration"]), ("self_hosted", "all", "24h"))
        self.assertIs(app["http_only_cookie_attribute"], True)
        self.assertEqual(app["same_site_cookie_attribute"], "lax")
        self.assertEqual([i["name"] for i in app["allowed_idps"]], ["Google Workspace", "One-Time-PIN", "tsidp"])
        self.assertTrue(all(i["id"] is None for i in app["allowed_idps"]))
        self.assertIsNone(app["domain"])
        self.assertEqual(plan["bypass_applications"], [])
        allow = plan["policies"][0]
        self.assertEqual((allow["decision"], allow["include"]["selector"]), ("allow", "email"))
        self.assertIsNone(allow["include"]["values"])
        self.assertIs(plan["applied"], False)
        for doc in (route, plan):
            for key, value in UNKNOWN_FIELDS.items():
                if key in doc["unknowns"]:
                    self.assertEqual(doc["unknowns"][key], value)

    def test_k3_secret_scan(self) -> None:
        files = [*_deploy_json_files(), DEPLOY / "README.md", WEB / "Containerfile", *sorted(AUTH.glob("*.js")),
                 WEB / "serve.js", WEB / "src" / "hooks.server.ts", *sorted(RECEIPT_DIR.glob("auth_hosting-*.json"))]
        patterns = [
            re.compile(r"-----BEGIN"),
            re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}"),
            re.compile(r"(?i)cf-access-client-secret\"?\s*[:=]\s*\"?[A-Za-z0-9]"),
            re.compile(r"/Users/|/home/|/private/|/nix/store/"),
            re.compile(r"(?i)\b(api[_-]?token|client[_-]?secret|password)\"?\s*[:=]\s*\"[^\"]+\""),
            re.compile(r"ghp_|github_pat_|AKIA[0-9A-Z]{16}"),
        ]
        hex_run = re.compile(r"(?<![A-Za-z0-9])[0-9a-f]{32,}(?![A-Za-z0-9])")
        b64_run = re.compile(r"[A-Za-z0-9+_=-]{32,}")  # "/" excluded so file paths split into segments
        allowed_hex = {"0" * 64, "48e4b67d85f87bd551df43704e24d252f56cc5f8e9718841aace50f19948f0f9"}
        hits: list[str] = []
        for path in files:
            text = path.read_text()
            rel = str(path.relative_to(REPO))
            for pattern in patterns:
                if pattern.search(text):
                    hits.append(f"{rel}: {pattern.pattern}")
            for match in hex_run.finditer(text):
                token = match.group(0)
                # 40-hex git commit ids are public provenance in plan/receipt files, not secrets.
                if token in allowed_hex or (len(token) == 40 and path.suffix == ".json"):
                    continue
                hits.append(f"{rel}: hex run {token[:8]}...")
            for match in b64_run.finditer(text):
                token = match.group(0)
                if re.fullmatch(r"[0-9a-f]+", token):
                    continue  # judged by the hex rule
                if re.search(r"[A-Z]", token) and re.search(r"[a-z]", token) and re.search(r"[0-9]", token):
                    hits.append(f"{rel}: high-entropy run {token[:8]}...")
        for obj in _k8s_objects():
            self.assertNotEqual(obj["kind"], "Secret")
        self.assertEqual(hits, [], f"scanned {len(files)} files")
        _SCAN_COUNTS["k3_files_scanned"] = len(files)

    def test_k4_containerfile(self) -> None:
        text = (WEB / "Containerfile").read_text()
        lines = [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith("#")]
        froms = [line for line in lines if line.upper().startswith("FROM ")]
        self.assertEqual(len(froms), 3)
        for line in froms:
            self.assertRegex(line, r"@sha256:[0-9a-f]{64}( |$)")
        digests = {re.search(r"@sha256:([0-9a-f]{64})", line).group(1) for line in froms}
        self.assertEqual(len(digests), 1, "builder and runtime share one pinned base")
        users = [line for line in lines if line.upper().startswith("USER ")]
        self.assertEqual(users, ["USER 10001:10001"])
        self.assertGreater(lines.index(users[0]), max(lines.index(f) for f in froms))
        self.assertIn("corepack prepare pnpm@11.25.0", text)
        self.assertIn("pnpm install --frozen-lockfile", text)
        self.assertIn("ENV VIDEO_UTILS_AUTH_MODE=tailnet HOST=" + ALL_INTERFACES + " PORT=3000", text)
        for line in lines:
            upper = line.upper()
            self.assertFalse(upper.startswith("ADD "), line)
            if upper.startswith("COPY "):
                self.assertNotRegex(line, r"(fixtures|artifacts|\.env|\.mov|\.mp4|\.wav|models|\s\.\s)", line)
                self.assertNotRegex(line, r"^COPY \. ", line)
        self.assertEqual(lines[-1], 'CMD ["node", "serve.js"]')

    def test_k5_readme_boundary_and_unknowns(self) -> None:
        readme = (DEPLOY / "README.md").read_text()
        self.assertIn("outward-facing", readme)
        self.assertIn("separate operator go", readme)
        for key in UNKNOWN_FIELDS:
            self.assertIn(f"`{key}`", readme, key)
        self.assertIn("container_base_digest", readme)
        for step in ("Namespace", "ConfigMap", "image", "PersistentVolumeClaim", "Deployment", "Service",
                     "NetworkPolicy", "tunnel route", "DNS", "Access application"):
            self.assertIn(step, readme)
        self.assertIn("Rollback", readme)


# --------------------------------------------------------------------------------------
# R: research record (static)
# --------------------------------------------------------------------------------------


class ResearchRecordTests(unittest.TestCase):
    def test_r1_every_estate_source_has_commit_and_date(self) -> None:
        text = RESEARCH.read_text()
        cited = 0
        for repo, tip in ESTATE_SOURCES.items():
            with self.subTest(repo=repo):
                rows = [line for line in text.splitlines() if repo in line and re.search(r"\b[0-9a-f]{40}\b", line)
                        and re.search(r"\b20\d\d-\d\d-\d\d\b", line)]
                self.assertTrue(rows, f"{repo} lacks a row with a 40-hex commit and a date")
                if tip is not None:
                    self.assertTrue(any(tip in row for row in rows), f"{repo} tip {tip[:12]} not cited")
                cited += 1
        self.assertEqual(cited, 9)
        for heading in ("Measured", "Inferred", "Unknown"):
            self.assertIn(heading, text)

    def test_r2_receipts_carry_unknown_fields(self) -> None:
        receipts = sorted(RECEIPT_DIR.glob("auth_hosting-*.json"))
        self.assertTrue(receipts, "at least one dated auth_hosting receipt")
        for path in receipts:
            with self.subTest(receipt=path.name):
                doc = json.loads(path.read_text())
                unknowns = doc["unknowns"]
                for key, value in UNKNOWN_FIELDS.items():
                    self.assertIn(key, unknowns)
                    self.assertEqual(unknowns[key], value, key)
                self.assertIn("container_base_digest", unknowns)


_SCAN_COUNTS: dict[str, int] = {}

if __name__ == "__main__":
    unittest.main()
