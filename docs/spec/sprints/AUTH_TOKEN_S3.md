# S3 auth_token lane contract: valid-token Cloudflare Access path, end to end on the built server

Status: **Phase 1 contract freeze**, 2026-10-07. Lane `auth_token`, sprint
`20261007-s3`, branch `sprint/20261007-s3/auth_token`, worktree
`.local/sprint3/auth_token`. Tracker: Linear TIN-5720 (root writes Linear).
Baseline: `549a14dea88f6b7951a81f2c2fa0718cb83a1c21`.
Authority: the operator's S3 decision to use the estate CF Access + tsidp pattern
(`docs/spec/sprints/20261007-S3.md`), repository `AGENTS.md`, and
R-HOOK-CONVERGENCE-20261004 R-N11/R-N12/R-N13.
Predecessor: `docs/spec/sprints/AUTH_HOSTING_S3.md`. Its receipt
`auth_hosting-implementation-receipt.json` records "Valid-token path not
exercised end to end (would need JWKS network)". This lane closes that gap.

The lane never pushes, merges, touches `main`, writes Linear, edits root-owned
files, changes `deploy/`, applies manifests, contacts Cloudflare or any external
host, downloads models, or starts a daemon. Root reviews, signs the merge and
publishes.

## 1. Scope

In scope:

1. Run the valid-token Access path **end to end** against the **built**
   adapter-node server (`web/build`), started via `node serve.js` in
   `VIDEO_UTILS_AUTH_MODE=tailnet` mode. Requests carry real RS256 assertions,
   signed by RSA key pairs **generated at test time**. The server fetches keys
   from a **loopback JWKS HTTP server**.
2. Cover these case groups (section 6):
   - J1 (valid token, allowlisted, mixed-case email);
   - J13 (valid token, not allowlisted);
   - expired, not yet valid, wrong `aud`, wrong `iss`;
   - unknown `kid` (one refetch, then deny);
   - rotated key;
   - `alg` `none` and HS256 confusion;
   - oversize JWKS;
   - JWKS endpoint down (stale-within-max allows, then deny).

   Host-precedence controls and one static-asset observation are also included.
3. Add a test-only seam (section 4) that redirects the derived JWKS URL to
   loopback and supplies a virtual clock. The seam lives **outside `web/`** and
   is generated at test runtime. It refuses production and pod shapes and
   changes no production source.
4. Fix any defect found in the auth source (`web/src/lib/server/auth/*.js`) in
   that source, with a regression test (section 8).
5. Write durable receipts under `docs/agent-notes/sprints/20261007-s3/` with
   the per-case expected/observed table and numerators/denominators.

Out of scope:

- Real Cloudflare JWKS, TLS to Cloudflare, DNS, and real Access-issued tokens.
- The tsidp claim shape.
- Any deploy, cluster or tunnel action, and container builds.
- Changes to `serve.js`, `hooks.server.ts`, `deploy/`, `Containerfile` or root
  files (any needed changes go to section 9 as requests).
- Audio, media, detector or model work.

## 2. Owned files

| Path | Use in this lane |
| --- | --- |
| `docs/spec/sprints/AUTH_TOKEN_S3.md` | This contract (Phase 2 appends section 12 only). |
| `tests/test_auth_token_s3.py` | The single runner: static checks, seam guards, end-to-end case table. Stdlib only. |
| `docs/agent-notes/sprints/20261007-s3/auth_token-*.json` | Receipts (`auth_token-implementation-receipt.json`). |
| `web/src/lib/server/auth/` (existing four modules and their vitest files) | Edited **only** to fix a defect found by section 6, with a regression test. No new `.js` file. This directory is copied into the runtime image, and `test_auth_hosting_s3.HooksStaticTests.test_l4` pins its file set to four modules. |
| `web/e2e/auth-token.spec.ts`, `web/tests/auth-token-support.ts` | **Reserved, not created this sprint.** One runner avoids two drifting copies of the key, JWKS and clock harness. Playwright's global setup starts a loopback-mode server that this lane does not need. Root may later ask for a Playwright mirror. |

Generated at test time and never committed (gitignored, under
`artifacts/s2/auth_token/<UTC-stamp>/`):

- the preload seam `seam.mjs`;
- `clock.json`, `jwks-attempts.log`, `egress-refused.log`;
- per-process server stderr logs;
- `case-table.json` (observed table).

No private key, token or JWKS private member is ever written to disk.

## 3. Existing behaviour relied on (read on the baseline)

- `mode.js` derives `issuer = https://<team>` and
  `jwksUrl = https://<team>/cdn-cgi/access/certs` from
  `VIDEO_UTILS_CF_ACCESS_TEAM_DOMAIN`, which must match
  `^[a-z0-9-]+\.cloudflareaccess\.com$`. The JWKS URL is never separately
  configurable. **There is no supported configuration that points the JWKS at
  loopback.**
- `cf-access.js` details:
  - RS256 only.
  - `crit` refused.
  - `kid` is resolved through a module-level per-team cache that captures
    `globalThis.fetch` and `Date.now` when first used.
  - Fresh TTL 10 min; unknown-`kid` refetch bounded by a 30 s cooldown; stale
    keys usable for up to 60 min after the last successful fetch.
  - Body cap 65 536 bytes: a declared `content-length` above the cap is
    refused, and so is a streamed total above the cap.
  - Fetch uses `redirect: 'error'` and a 5 s abort.
  - Clock skew 60 s on `exp`, `nbf` and `iat`.
  - The email is lowercased before allowlist membership is checked.
- `gate.js` + `hooks.server.ts` order: Host is checked first (421), then
  identity (403 `bff_identity_refused`, same six-key body for every reason,
  `Cache-Control: no-store`).
- adapter-node `build/handler.js` (read from the main checkout build) runs
  `sequence([serve(client), serve_prerendered(), ssr])`. Client assets are
  therefore answered by sirv **before** SvelteKit hooks run. This is an
  inference from reading the build and is measured as O1 (section 6.5).
- Node 22.23.2 bundles undici 6.28.0. Its connection timers advance by a tick
  counter (`fastNow += TICK_MS`), not `Date.now`, so a virtual wall clock does
  not fire undici timeouts. This is a source reading; the JWKS server also
  answers with `Connection: close`, so no pooled socket spans a clock jump.

## 4. Test-only seam (preload, outside the server)

The server has no loopback JWKS option, so the smallest explicit seam is a
**Node `--import` preload module**. `tests/test_auth_token_s3.py` writes it at
run time to `artifacts/s2/auth_token/<stamp>/seam.mjs`. The server is launched
as:

```
cd web && node --import file://<abs>/seam.mjs serve.js
```

The launch environment is scrubbed: no `NODE_OPTIONS`, no inherited `VIDEO_UTILS_*`.

The seam changes exactly two things:

1. **JWKS destination.** It wraps `globalThis.fetch`.
   - The exact URL `https://videoutils-authtoken-test.cloudflareaccess.com/cdn-cgi/access/certs`
     is re-issued with the **original** fetch to
     `http://127.0.0.1:<jwks_port>/cdn-cgi/access/certs`, with the caller's
     `init` unchanged (`redirect: 'error'`, the abort `signal`, headers). Each
     attempt appends one line to `jwks-attempts.log`.
   - Any other URL whose host is not `127.0.0.1` is rejected with a `TypeError`
     and appended to `egress-refused.log` (expected count 0).
2. **Wall clock.** It replaces `Date.now` with
   `virtual_ms + (realNow() - set_at_real_ms)`. The two values come from
   `clock.json`, which is read synchronously on every call. The runner writes
   the file atomically (`os.replace`). If the file cannot be read, `Date.now`
   throws, so the failure is loud, never a silent fallback.

Everything else is the production path. That includes:

- serve.js tailnet validation;
- hooks;
- gate;
- verifier;
- JWKS cache;
- `readCapped`;
- `parseJwks`;
- undici fetch.

The issuer stays the production derivation
`https://videoutils-authtoken-test.cloudflareaccess.com`.

**Refusal guards.** The seam throws at import, so node exits non-zero before
`serve.js` runs, and stderr carries `auth_token test seam refused: <rule>` with
rule names only. The guards refuse when:

- `NODE_ENV === 'production'` (the runtime image sets this).
- `KUBERNETES_SERVICE_HOST` or `KUBERNETES_PORT` is set (pod/ConfigMap shape).
- `process.cwd()` is `/app` (the image `WORKDIR`).
- `HOST !== '127.0.0.1'`.
- `VIDEO_UTILS_CF_ACCESS_TEAM_DOMAIN` is not the reserved test domain
  `videoutils-authtoken-test.cloudflareaccess.com`.
- `VIDEO_UTILS_AUTH_TOKEN_SEAM_NONCE` does not equal the random 128-bit nonce
  baked into that run's generated file. The environment variable alone does
  nothing, and the file alone does nothing.

The seam cannot ship by accident:

- It is never under `web/`, so it is outside the image build context, and the
  `Containerfile` copies only `build/`, `node_modules`, `package.json`,
  `serve.js` and `src/lib/server/auth/`.
- The image `CMD` has no `--import`.
- No production source references it. Static check SG6 asserts this.

Production validation is unchanged: zero lines change in `mode.js`,
`cf-access.js`, `gate.js`, `allowlist.js`, `serve.js` and `hooks.server.ts`,
unless section 8 records a defect fix.

## 5. Fixtures (all generated per run; nothing committed)

- **Keys.** A one-shot `node --input-type=module -` subprocess (script on stdin,
  timeout 60 s) generates RSA-2048 key pairs with
  `generateKeyPairSync('rsa', {modulusLength: 2048})`:
  - `k1` (kid `kid-a`);
  - `k2` (kid `kid-b`);
  - `kx`, unpublished, used to sign under kid `kid-a`.

  It mints every token for the preplanned virtual timeline and prints JSON:
  public JWKS documents and compact tokens. Private keys exist only in that
  process's memory and die with it. Tokens pass to the Python runner over stdout
  and are never written to disk or logged.
- **Configuration** (all reserved or example names):

  | Variable | Value |
  | --- | --- |
  | Team | `videoutils-authtoken-test.cloudflareaccess.com` |
  | `VIDEO_UTILS_CF_ACCESS_AUDS` | `AudTokenLaneA0123456789abcdef,AudTokenLaneB9876543210fedcba` |
  | `VIDEO_UTILS_OPERATOR_ALLOWLIST` | ` Operator@Example.org , second@example.org` (mixed case and spaces on purpose) |
  | `VIDEO_UTILS_PUBLIC_HOSTS` | `video-utils.example.org` |
  | `ORIGIN` | `https://video-utils.example.org` |
  | `HOST` | `127.0.0.1` |
  | `PORT` | free ephemeral port |
- **Base claims.**
  - `iss` = `https://videoutils-authtoken-test.cloudflareaccess.com`
  - `aud` = `[AUD_A]`
  - `sub` = `synthetic`
  - `iat` = `nbf` = `now - 10`
  - `exp` = `now + 600`

  Here `now` is the step's virtual time in seconds.
- **Virtual epoch** `V0 = 1_900_000_000_000` ms. This is fixed and matches the
  `auth_hosting` harness `NOW`.
- **Loopback JWKS server.** Python `http.server` in a thread on `127.0.0.1:0`
  with these switchable modes:
  - `serve(doc)`;
  - `oversize_declared(n)` (a valid JWKS padded with JSON whitespace to `n`
    bytes, with `Content-Length`);
  - `oversize_chunked(n)` (same body, chunked, no `Content-Length`);
  - `status(503)`;
  - `closed` (listener shut down: connection refused).

  It counts requests (server side) and sets `Connection: close`.
- **Request.** `GET /` with `Host: video-utils.example.org`, optional
  `Cf-Access-Jwt-Assertion`, `http.client` timeout 10 s.
- **Decision observables.**
  - **allow** = status not in {403, 421} and the JSON `code` (if any) not in
    {`bff_identity_refused`, `bff_host_refused`, `bff_auth_unconfigured`}. The
    gate passed; the page's own result is recorded but not judged.
  - **deny** = 403 with body exactly
    `{status:"error", code:"bff_identity_refused", message:<IDENTITY_MESSAGE>, upstream_status:null, upstream_code:null, upstream_detail_code:null}`
    (key order checked), plus `Cache-Control: no-store`.
  - **host** = 421 `bff_host_refused`.
  - **Δfetch** = new lines in `jwks-attempts.log` caused by the case. The
    server-side request count must agree whenever the listener is up.

## 6. Test protocol (case table, expectations frozen here before any run)

Module `tests/test_auth_token_s3.py`, run from the worktree root:

```
PYTHONPATH=tests python3 -m unittest test_auth_token_s3 -v
```

The directly affected module, run with the same invocation, is
`test_auth_hosting_s3` (auth-source regressions and the `test_l4` file-set pin).

Prerequisites:

- `node` on PATH;
- `web/build/index.js` present and newer than every file in `web/src` and
  `serve.js`. This is the same staleness rule as `BuiltHooksTests`.

Otherwise the end-to-end and guard classes skip with an explicit reason.
Phase 2 builds the worktree with these two commands, run in `web/` with a
600 s timeout each:

```
pnpm install --frozen-lockfile --offline
pnpm run build
```

If the offline store cannot satisfy that, the lane records
`blocked: build_prerequisite` in its receipt. It does not symlink the main
checkout's `node_modules`, because the build would write to the main checkout.

Limits:

- Every subprocess has a timeout of 60 s or less.
- Server listen-wait is 30 s or less.
- Only one server process runs at a time.
- Expected module wall time is under 180 s.

Classes:

- `SeamStaticTests` (always runs).
- `SeamGuardTests` (node + build).
- `AccessTokenE2ETests` (node + build, one method per process, cases as
  `subTest`).
- `StaticAssetObservationTests` (node + build).

Step times are virtual offsets from `V0`. Cooldown, TTL and stale boundaries
are approached with margins of at least 10 s, so real elapsed time inside a
step (seconds) cannot cross a boundary.

### 6.1 Process P_A: decisions, unknown kid, rotation (JWKS starts as `{k1}`)

| ID | Step | Case (maps to) | Expected | Δfetch |
| --- | --- | --- | --- | --- |
| E00a | +0 s | valid k1 token, Host `rebind.example.org` | host 421 | 0 |
| E00b | +0 s | valid k1 token, Host `127.0.0.1:<port>` | host 421 | 0 |
| E01 | +0 s | **J1** valid k1, `email: "Operator@EXAMPLE.org"` | allow | 1 (cold) |
| E02 | +0 s | **J13** valid k1, `email: "stranger@example.org"` | deny | 0 |
| E03 | +0 s | **expired** `exp = now - 61` | deny | 0 |
| E03c | +0 s | control: `exp = now - 30` (within skew) | allow | 0 |
| E04 | +0 s | **not yet valid** `nbf = now + 120` | deny | 0 |
| E04b | +0 s | `iat = now + 120` | deny | 0 |
| E04c | +0 s | control: `nbf = now + 30` | allow | 0 |
| E05 | +0 s | **wrong aud** `aud: ["AudTokenLaneZ0000000000000000"]` | deny | 0 |
| E05b | +0 s | AUD case-folded (`AUD_A.toLowerCase()`) | deny | 0 |
| E06 | +0 s | **wrong iss** `https://other-team.cloudflareaccess.com` | deny | 0 |
| E06b | +0 s | iss with trailing `/` | deny | 0 |
| E06c | +0 s | iss with `http://` scheme | deny | 0 |
| E07a | +0 s | **alg none**, empty signature segment (`h.p.`) | deny | 0 |
| E07b | +0 s | alg none, non-empty garbage signature | deny | 0 |
| E07c | +0 s | **HS256**, HMAC key = k1 public SPKI PEM bytes, kid `kid-a` | deny | 0 |
| E07d | +0 s | HS256, HMAC key = the served JWKS JSON bytes | deny | 0 |
| E07e | +0 s | RS256 kid `kid-a` signed by unpublished `kx` | deny | 0 |
| E08 | +0 s | **unknown kid** `kid-zzz` within cooldown of the cold fetch | deny | 0 (cooldown) |
| E09 | +40 s | unknown kid `kid-zzz` | deny | **1** (one refetch) |
| E09b | +40 s | same again immediately | deny | 0 |
| E10 | +80 s, JWKS → `{k1,k2}` | **rotated key**: valid k2 (`kid-b`) | allow | 1 |
| E10b | +80 s | valid k1 | allow | 0 |
| E11 | +120 s, JWKS → `{k2}` | retired k1 within fresh TTL | allow | 0 |
| E12 | +80 s + 660 s | retired k1 after fresh TTL | deny | 1 |
| E12b | same | valid k2 | allow | 0 |

E11 is the designed retirement lag: up to 10 min of fresh TTL, documented in
`cf-access.js`. It is recorded as a property, not a defect.

### 6.2 Process P_B: oversize JWKS, cold cache

| ID | Step | JWKS mode | Expected | Δfetch |
| --- | --- | --- | --- | --- |
| E13 | +0 s | `oversize_declared(65 537)` | deny | 1 |
| E13b | +40 s | `oversize_chunked(65 537)` | deny | 1 |
| E13c | +80 s | control at cap: `oversize_declared(65 536)` | allow | 1 |

### 6.3 Process P_C: endpoint down, stale-within-max, then deny (JWKS `{k1}`)

| ID | Step | JWKS mode | Expected | Δfetch |
| --- | --- | --- | --- | --- |
| E14a | +0 s | serve | allow | 1 |
| E14b | +660 s | `status(503)` | allow (stale) | 1 (failed) |
| E14c | +670 s | `status(503)` | allow (stale) | 0 (cooldown) |
| E14d | +1 800 s | `closed` | allow (stale) | 1 (failed) |
| E14e | +3 540 s | `closed` | allow (stale, age < 60 min) | 1 (failed) |
| E14f | +3 660 s | `closed` | **deny** (age > 60 min) | 1 (failed) |
| E14g | +3 720 s | serve again (same port) | allow (recovered) | 1 |

### 6.4 Seam guards and static checks

| ID | Check | Expected |
| --- | --- | --- |
| SG1 | seam + `NODE_ENV=production` | exit ≠ 0, port never listens, stderr names `NODE_ENV` |
| SG2 | seam + `KUBERNETES_SERVICE_HOST=10.0.0.1` | refused likewise |
| SG3 | seam + all-interfaces `HOST` | refused likewise |
| SG4 | seam + wrong nonce | refused likewise |
| SG5 | seam + non-reserved team domain | refused likewise |
| SG6 | static: no file under `web/` (excluding `node_modules`, `build`, `.svelte-kit`) contains the seam nonce variable name, `seam.mjs` or `--import`. `Containerfile` has no `--import`/`NODE_OPTIONS`. The `mode.js` `jwksUrl` derivation line is unchanged. Auth dir has exactly 4 `.js` modules. | all hold |
| SG7 | `egress-refused.log` line count over all processes | 0 |
| SH1 | secret hygiene over owned files and the receipt: no PEM block, no JWK private member (`"d"`, `"p"`, `"q"`, `"dp"`, `"dq"`, `"qi"`) next to `"kty"`, no JWT-shaped `eyJ…​.eyJ…​.…` string, no nonce value | 0 findings |

### 6.5 Observation (spec-divergence probe, not in the decision denominator)

| ID | Request (no assertion, public Host) | Per AUTH_HOSTING_S3 §4.5 | Prediction from build reading |
| --- | --- | --- | --- |
| O1a | `GET /favicon.svg` | 403 | 200 (sirv before hooks) |
| O1b | `GET /_app/version.json` | 403 | 200 |

The test asserts only that the observed status is in {200, 403} and that it is
recorded. If the observed status is 200, the lane files the section 9 request
and does not change `serve.js`. Severity is an inference, not a measurement:
public build assets contain no operator data, and the Access edge and
NetworkPolicy sit in front of the origin.

## 7. Completion metrics and claim classes

Claim classes:

- **e2e-local**: the built server on loopback with synthetic keys, the seam's
  JWKS redirect, and a virtual clock.
- **source-check**: static/unit checks in this worktree.
- **source-reading**: what a file or bundle says; not executed.
- **not-claimed**: stated so nobody infers it.

| Metric | Denominator | Class |
| --- | --- | --- |
| Decision cases matching expected status, code and body | **37** (E00a..E14g: 14 allow, 21 identity-deny, 2 host) | e2e-local |
| Δfetch matching expectation | **37** | e2e-local |
| Distinct identity-deny bodies (uniformity, no reason leak) | 1 distinct body across **21** denies | e2e-local |
| DoD groups covered (J1, J13, expired, nbf, aud, iss, unknown kid, rotation, alg none/HS256, oversize, down/stale) | **11** | e2e-local |
| Seam guard refusals | **5** (SG1..SG5) | e2e-local |
| Static seam/secret checks holding | SG6 sub-checks + SH1 files scanned (counts in receipt) | source-check |
| Egress attempts to non-loopback hosts | 0 of all fetches (count in receipt) | e2e-local |
| Auth-source defects found / fixed with regression test | n found (expected 0) / n | source-check |
| Static asset gate observation | 2 paths, observed status recorded | e2e-local observation |
| Real Cloudflare JWKS/TLS/DNS, real Access token, tsidp claims, hosted or served proof, deploy applied | n/a | **not-claimed** |

Every metric reports both numerator and denominator. A failed case is reported
as failed with its observed values; it is never dropped from the denominator.
This lane runs no experiment, so experimental non-improvement does not apply.
A blocked prerequisite with a named receipt reason is valid completion.

### 7.1 Unknown and explicit fields (every receipt and `case-table.json`)

Value `null` or the string shown; never omitted:

```
public_hostname: null              cloudflare_tunnel_id: null
access_application_aud: null       access_idp_ids: null
tsidp_claims_in_access_jwt: "unknown"
assertion_idp_visible_to_app: "unknown"
real_access_token_claim_shape: "unknown"
real_cloudflare_jwks_contacted: false
jwks_tls_path: "not_exercised"     dns_resolution: "not_exercised"
jwks_transport: "loopback_http_via_test_seam"
clock: "virtual_via_test_seam"     virtual_epoch_ms: 1900000000000
jwks_fetch_timeout_5s: "not_exercised"
tailscale_serve_identity: "not_accepted"
applied: false                     served_proof: "not_run"
container_built: false
static_asset_gate: <observed O1 statuses or "not_run">
```

Also recorded:

- `web/build` source commit;
- `node --version`;
- adapter-node and kit versions from `web/package.json`;
- keys generated per run (count, modulus bits);
- `committed_key_material: false`.

## 8. Defect handling

If a decision case fails because the auth source is wrong (not the harness):

1. Fix the defect in the existing module under `web/src/lib/server/auth/`.
2. Add a regression test for it in `tests/test_auth_token_s3.py` (node-level,
   loading the module directly as the `auth_hosting` harness does), plus the
   module's vitest file when one exists.
3. Rebuild, re-run sections 6.1 to 6.5, and run `test_auth_hosting_s3`.
4. Record the defect, its root cause, and the before/after observations in the
   receipt.

No production check is relaxed to make a case pass. If an expectation in
section 6 turns out to be wrong against the frozen behaviour contract, it is
corrected in section 12 with the reason. It is never silently edited.

## 9. Root-owned changes this lane may request (not made by the lane)

1. `just/*.just`: an optional `auth-token-test` recipe wrapping the section 6
   command.
2. If O1 observes 200, one of the following:
   - (a) `web/serve.js`, tailnet mode only: serve through a small `node:http`
     server that runs the same `gateRequest` before adapter-node's exported
     `handler`. Loopback mode stays unchanged.
   - (b) Amend AUTH_HOSTING_S3 §4.5 to state the client-asset exemption
     explicitly.

   The operator or root chooses; the lane does neither.
3. If a defect fix ever needs a new module in `web/src/lib/server/auth/`:
   update the `test_auth_hosting_s3.test_l4` file-set pin (the lane will
   request this, not do it).

## 10. Preregistration

None. This is deterministic conformance testing, not an experiment. There are
no arms, seeds that select data, held-out sets or scores to tune. Key
generation is random per run by design, and outcomes must not depend on it.
The expected value of every case (section 6), including the O1 prediction, is
frozen in this commit before any run. `preregistered: false`.

## 11. Doctrine carried

No change to audio processing, detectors, profiles or masters. The ~32 Hz
low-string protection, and the bans on a blanket high-pass and a mains notch,
are untouched. The real take and the accepted FULLER run
(`artifacts/runs/20261006T041633Z-990aa1bd6737`) are not read or written by
this lane. Nothing here makes a note-correctness or listening claim.
Measurements (e2e-local), readings (source-reading) and non-claims stay
separate in every receipt.

## 12. Implementation record (Phase 2, 2026-10-07)

Implementation commit `f4782d1e4148a4e2ffc1f706b23dea02304c1cea`. Receipt:
`docs/agent-notes/sprints/20261007-s3/auth_token-implementation-receipt.json`. Final
run stamp `20261007T153003Z-6500a5` (gitignored artifacts). Prerequisites were met:
`pnpm install --frozen-lockfile --offline` reused 174 packages from the store and
downloaded none, and `pnpm run build` succeeded. No `blocked: build_prerequisite`.

### 12.1 Results (e2e-local unless marked)

| Metric | Observed |
| --- | --- |
| Decision cases matching expected status, code and body | 37 / 37 (14 allow, 21 identity-deny, 2 host) |
| Δfetch matching expectation (seam log; server count agrees whenever the listener is up) | 37 / 37 |
| Distinct identity-deny bodies | 1 across 21 denies |
| DoD groups covered | 11 / 11 |
| Seam guard refusals (SG1..SG5: exit ≠ 0, never listened, stderr names the rule) | 5 / 5 |
| JWKS attempts carrying `redirect: 'error'`, an AbortSignal, GET and `accept: application/json` | 13 / 13 |
| Egress refused by the seam (non-loopback attempts) | 0 of 13 JWKS attempts; O1 process 0 |
| SG6 sub-checks holding (source-check) | 8 / 8; 219 `web/` files scanned |
| SH1 findings (source-check) | 0 over 8 owned files + 40 run artifact files; gitleaks clean |
| Auth-source defects found / fixed with regression test (source-check) | 1 / 1 (D1, expected 0 at freeze) |
| O1 static asset observation | `/favicon.svg` 200, `/_app/version.json` 200 (root `/` 403 in the same process) |
| `test_auth_token_s3` / `test_auth_hosting_s3` / vitest auth / svelte-check | 14/14 / 39/39 / 34/34 / 0 errors |

### 12.2 Defect D1 (fixed in `cf-access.js`)

- **Found by:** E13. The built server process exited mid-request on a JWKS
  response that declared `Content-Length: 65537`. Its stderr showed an uncaught
  `AssertionError assert(!this.paused)` at `Parser.finish` in node's bundled
  undici.
- **Root cause:** two early exits left the response body unread and
  uncancelled:
  - `readCapped` returned `null` on a declared length above the cap;
  - `refresh` threw on a non-OK status.

  The paused undici parser then saw the peer close the socket, and the internal
  assertion threw outside any promise chain.
- **Measured before the fix** (standalone module, real loopback socket, 3 runs per
  shape):

  | Response | Crashes |
  | --- | --- |
  | Declared 65 537, status 200 | 3/3 |
  | 65 537 body, status 503 | 3/3 |
  | 1 000 000, status 200 | 0/3 |
  | 200 000, status 503 | 0/3 |
  | 1 000 000, status 503 | 0/3 |

- **Measured after the fix:** 0/3 crashes on each shape tried, and the built
  server reran clean.
- **Fix:** `discardBody(response)` cancels the unread body on both early exits.
  No validation rule, limit, timeout or cache rule changed.
- **Regression tests:**
  - `CfAccessRegressionTests.test_d1_unread_jwks_body_cannot_crash_process`
    (node, module loaded directly, 2 shapes);
  - `cf-access.test.ts` case 16 (3 shapes).

  Both fail on the pre-fix source and pass after it.
- **Severity (inference):**
  - Hosted, only the Cloudflare JWKS response over TLS can trigger it.
  - A client cannot choose that response. An unknown `kid` can prompt at most one
    refetch per 30 s.
  - The effect was termination of the whole BFF process, not an authentication
    bypass.

### 12.3 Deviations and additions (none relax a production check)

1. Classes added beyond section 6:
   - `CfAccessRegressionTests` (section 8 regression);
   - `ReceiptTests` (receipt keeps the 7.1 fields and the denominators; skips until
     the receipt exists);
   - `SeamStaticTests.test_sg6b_seam_template_guards_present` (every refusal
     precedes any patch).
2. The seam is generated per server process: its own directory, nonce, clock
   and logs. The JWKS port is baked in, so P_C reuses one port after `closed`.
3. Seam details:
   - It deletes the nonce variable from `process.env` after checking it.
   - It records each JWKS attempt's `method`, `redirect`, signal presence and
     `accept`, but never the URL query or any header value beyond `accept`.
   - It refuses other egress by returning a rejected promise (fetch semantics)
     with a `TypeError`.
4. Section 5 base claims gave no email. Every token carries
   `email: "Operator@EXAMPLE.org"`, except E02 (`stranger@example.org`), so each
   deny is attributable to the claim under test.
5. O1 runs in its own seam process with the JWKS listener answering 503. It
   asserts 0 JWKS attempts and 0 refused egress, and controls with `/` (403).
6. `cf-access.test.ts` changed only by the regression import and case 16.
   svelte-check still reports 0 errors.

### 12.4 Requests filed under section 9 (root decides; the lane made none of these changes)

1. `just/workflow.just`, after the `auth-hosting-test` recipe:

   ```
   # S3 valid-token Access path end to end on the built server (loopback JWKS seam, virtual clock; no network)
   auth-token-test:
       PYTHONPATH=tests python3 -m unittest test_auth_token_s3 -v
   ```

2. O1 observed 200 for both client assets. Choose one:
   - (a) a tailnet-mode `node:http` front in `web/serve.js` that runs
     `gateRequest` before adapter-node's exported `handler`;
   - (b) amend AUTH_HOSTING_S3 §4.5 to exempt `build/client` assets explicitly.

   Severity is an inference: the assets carry no operator data, and the Access
   edge and NetworkPolicy sit in front.

### 12.5 Still not claimed

These remain not exercised:

- real Cloudflare JWKS, TLS, DNS and the 5 s fetch timeout;
- real Access tokens and the tsidp claim shape;
- the production image (whose `NODE_ENV=production` refuses the seam);
- any deploy or served proof.

Unknown fields are as listed in 7.1, with `static_asset_gate = {O1a: 200, O1b: 200}`.
