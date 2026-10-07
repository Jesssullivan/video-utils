# S3 auth_hosting lane contract: private app behind the estate CF Access + tsidp pattern

Status: **Phase 1 contract freeze**, 2026-10-07. Lane `auth_hosting`, sprint
`20261007-s3`, branch `sprint/20261007-s3/auth_hosting`, worktree
`.local/sprint3/auth_hosting`. Tracker: Linear TIN-5720 (related TIN-5552).
Baseline: `4bd806db3944d05fb4b5cca16a87642a71f5458f`.
Authority: operator S3 decision "use our CF Access + tsidp auth pattern,
findable in xoxd.ai, gftb and others" (`docs/spec/sprints/20261007-S3.md`),
repository `AGENTS.md`, R-HOOK-CONVERGENCE-20261004 R-N11/R-N12/R-N13.
Root administers review, signed merge, `just` recipes, publication and Linear.
This lane never pushes, merges, writes Linear, edits root-owned files,
downloads models, starts a daemon, creates a tunnel, or applies anything to
Cloudflare or a cluster.

## 1. Scope

In scope:

1. **Research record** `docs/research/2026-10-07-estate-auth-hosting.md`: the
   estate CF Access + tsidp pattern exactly as found on remote default
   branches, with commit and commit date per source (section 3), separating
   what the sources state from what this lane infers.
2. **Auth modules** under `web/src/lib/server/auth/`: Cloudflare Access JWT
   verification (RS256 signature against the team JWKS with caching, strict
   `iss`/`aud`/`exp`/`nbf` checks, verified `email` claim), an operator
   allowlist read from configuration, a mode switch (`loopback` default,
   explicit `tailnet`), and a pure per-request gate decision.
3. **Enforcement** in `web/src/hooks.server.ts`: loopback mode keeps today's
   behaviour byte-for-byte in effect (non-loopback `Host` gets 421); tailnet
   mode denies by default (wrong `Host` 421, absent/invalid config 503,
   missing/invalid/non-allowlisted identity 403) before routing.
4. **Launcher** `web/serve.js`: loopback mode unchanged (refuses non-loopback
   `HOST`, exit 2); tailnet mode may bind a non-loopback `HOST` only when the
   complete tailnet configuration validates at startup, else exit 2.
5. **Container** `web/Containerfile`: adapter-node, multi-stage, base images
   pinned by digest, non-root numeric user, explicit `COPY` of build outputs
   only (no media, artifacts, fixtures, `.env` or models baked in).
6. **Deploy plan** under `deploy/`: RKE2 manifests (Namespace, Deployment with
   one replica, ClusterIP Service, PVC for artifacts, non-secret ConfigMap,
   NetworkPolicy) and a Cloudflare tunnel-route + Access-application plan
   modelled on tinyland.dev `infra/cloudflare/*.json` and tinyland-infra
   `tofu/stacks/xoxd-ai-edge`. A `deploy/README.md` states that applying any
   of it is an outward-facing action requiring a separate operator go.
7. **Tests** `tests/test_auth_hosting_s3.py` (section 6) and dated receipts
   under `docs/agent-notes/sprints/20261007-s3/auth_hosting-*.json`.

Out of scope (explicitly not claimed): any apply to Cloudflare, the tunnel or
the cluster; creating an Access application, AUD, tunnel route, DNS record,
namespace or Secret; real credentials; building or pushing the container image
to a registry; served proof; the control-API container (section 5.6);
Tailscale Serve identity headers (section 4.4); a public site; new npm
dependencies (`web/package.json` is not lane-owned, so verification uses
`node:crypto` instead of the estate's `jose`); UI that displays identity;
any DSP, analysis, detector/profile/master change, or listening claim.

## 2. Owned files

| Path | Role |
| --- | --- |
| `docs/spec/sprints/AUTH_HOSTING_S3.md` | This contract |
| `docs/research/2026-10-07-estate-auth-hosting.md` | Estate pattern record (section 3) |
| `web/src/lib/server/auth/mode.js` | Mode + tailnet config parsing (pure, env passed in) |
| `web/src/lib/server/auth/cf-access.js` | JWT parse/verify, JWKS cache (pure; fetch and clock injectable) |
| `web/src/lib/server/auth/allowlist.js` | Operator allowlist parsing and matching |
| `web/src/lib/server/auth/gate.js` | Pure per-request decision for both modes |
| `web/src/hooks.server.ts` | Reads `$env/dynamic/private` once per request, calls `gate.js` |
| `web/serve.js` | Mode-aware launcher |
| `web/Containerfile` | adapter-node image definition |
| `deploy/README.md` | Apply boundary, order, rollback, unknowns |
| `deploy/k8s/kustomization.yaml` | Strict-JSON content (JSON is valid YAML) |
| `deploy/k8s/{namespace,configmap,pvc,deployment,service,networkpolicy}.json` | RKE2 manifests |
| `deploy/cloudflare/video-utils-app-origin-routes.json` | Tunnel route contract (tinyland.dev schema shape) |
| `deploy/cloudflare/video-utils-access-plan.json` | Access application/policy plan (declarative, not tofu) |
| `tests/test_auth_hosting_s3.py` | Lane test module |
| `docs/agent-notes/sprints/20261007-s3/auth_hosting-*.json` | Dated receipts |

Auth modules are plain ES modules with JSDoc types (the `web/src/lib/polling.js`
precedent, `checkJs`), so `node` can import them in tests without a build or
type stripping. `deploy/` manifests are strict JSON because the stdlib test
must parse them (no YAML parser is available; `kubectl`/kustomize accept JSON).
Lane scratch outputs go only under
`.local/sprint3/auth_hosting/artifacts/s2/auth_hosting/` (gitignored).

## 3. Estate sources (remote default branches only; fetched 2026-10-07)

Read with `git fetch` then `git show <remote>/<default>:<path>`; local working
trees are not evidence. Commit = remote branch tip at read; per-path last
commit recorded where it differs.

| Repo (remote/branch) | Tip commit, date | Paths read (path commit, date) |
| --- | --- | --- |
| tinyland-inc/xoxd.ai `origin/main` | `cc570c3c1079cc5754840395184f0c1a6fece97f`, 2026-10-05 | `docs/agent-notes/2026-09-19-deploy-rulings.md`, `AGENTS.md` (Deploy Lane, plan site), `src/lib/components/PublicAccessDialog.svelte`, `.github/workflows/deploy-pages-plan.yml` |
| xoxd-ai/tinyland.dev `github/main` | `7422982619e357d31a0ddf0affdf8dedd0b51a93`, 2026-10-02 | `docs/plans/tinyland-auth-golden-convergence.md` (`4c7634228c64`, 2026-07-13), `infra/cloudflare/honey-ingress-mothership-xoxd-ai-routes.json` (`8a80a74805a2`, 2026-09-19), `infra/cloudflare/honey-ingress-broker-origin-routes.json`, `docs/runbooks/2026-09-19-mothership-identity-rotation.md` (`cf1cd8e634a5`, 2026-09-19), `infra/staging/sveltekit-deployment.yaml` (`f08b92827ce2`, 2026-09-21), `infra/staging/kustomization.yaml`, `ContainerFile` (`f4362f001ba8`, 2026-07-09) |
| Great-Falls-Tool-Bus/great-falls-tool-bus-infra `upstream/main` | `bb969bea496926b19f9350857a91da9d02a5f2c5`, 2026-10-06 | `docs/runbooks/cf-access-tsidp.md` (`3d0d02d6b6ae`, 2026-10-05) |
| Great-Falls-Tool-Bus/greatfallstoolbus.org `upstream/main` | `b7f5b29690c72dbe777f1058bf8e88acaca3ab31`, 2026-10-06 | grep for Access JWT handling (none at origin; app uses its own OIDC + edge Access) |
| Jesssullivan/gftb-site `origin/main` | `849af37beaaa8675a9115b741aeee7a0ba13b8f4`, 2026-09-22 | grep only (no auth matches) |
| tinyland-inc/massage-ithaca-portal `origin/main` | `fda9163fb9847c8b10a1b7ae4bc1fd8bddeb793e`, 2026-10-01 | `src/lib/server/auth/cf-access.ts`, `src/hooks.server.ts` (`c0f410ecb7fa`, 2026-09-27), `AGENTS.md` Authentication |
| xoxd-ai/lab `origin/main` | `8654d4a8d8ef5846492a1daa9c3e714883ac7706`, 2026-10-07 | `AGENTS.md` (secrets doctrine), `docs/operations/TAILNET_MEMBERSHIP_DETECTION_DESIGN_2026-10-03.md` |
| tinyland-inc/tinyland-infra `origin/main` | `a236992ade1fcef7e056d91077f1ed5aa4abea7c`, 2026-10-06 | `tofu/stacks/xoxd-ai-edge/README.md` (xoruby rows), `kohakuhub-tailnet.tf` header |
| tinyland-inc/GloriousFlywheel `origin/main` | `aacc52916c9160b178105e628ed18fb95c8338d1`, 2026-10-06 | grep only: tsidp named as a tailnet-native cold-start fallback (`docs/decisions/cold-start-enrollment-2026-06.md`); no app-auth pattern |

Facts frozen from those sources (the research doc carries quotations):

- **Edge gate.** Cloudflare Access applications are declared in tofu stacks
  (tinyland-infra `xoxd-ai-edge`, gftb-infra `tofu/stacks/edge`) and applied
  by the operator; app repos never touch the gate. Pattern for a private app
  (xoruby): zone-bound exact hostname, all paths, 24h session, HttpOnly,
  SameSite=Lax, exact-email allow policy, a narrow `bypass` application only
  for a health path.
- **Origin.** Dynamic apps are reached through the shared `honey-ingress`
  Cloudflare Tunnel to a ClusterIP Service; the route is a source-controlled
  JSON contract applied out of band (tinyland.dev `infra/cloudflare`).
- **tsidp.** tsidp is federated *into* Cloudflare Access as an OIDC IdP
  (gftb `cf-access-tsidp.md`): a dedicated tagged node behind Funnel,
  PKCE, claims trusted only with a `login_method = tsidp` requirement,
  `allowed_idps` pinned (Google Workspace, One-Time-PIN, tsidp), and never
  email-matched for tsidp logins because tsidp rewrites `@github`/`@passkey`
  logins to non-routable addresses. The app therefore sees a **Cloudflare
  Access JWT**, not a tsidp token.
- **Origin verification.** The MI portal verifies every
  `Cf-Access-Jwt-Assertion` against `https://<team>/cdn-cgi/access/certs`
  with `iss = https://<team>` and any-of case-sensitive AUDs, requires a
  verified non-empty `email` (lowercased), never trusts
  `Cf-Access-Authenticated-User-Email`, has **no dev bypass**, exempts only a
  health path, and requires a tunnel-only origin (direct-origin refusal).
- **Secrets.** Names only in git; values via sops/stdin/GitHub environment
  secrets set by the operator; automated readers use a review service token
  (`CF-Access-Client-Id`/`-Secret`) read from lab sops by name.
- **Defense in depth.** tinyland.dev doctrine keeps CF Access as the outer
  perimeter on every dynamic origin; origin auth is an inner layer, not a
  replacement.

## 4. Behaviour contract

### 4.1 Mode switch

`VIDEO_UTILS_AUTH_MODE`: unset or empty = `loopback` (default, today's
behaviour); `tailnet` = hosted mode; any other value = configuration error
(serve.js exit 2; hooks answer 503 to every request). The name `tailnet`
denotes "reachable only through the estate perimeter whose IdPs include
tsidp"; the in-app identity is the Access JWT (section 3).

### 4.2 Tailnet configuration (all required; any invalid value = fail closed)

| Variable | Rule |
| --- | --- |
| `VIDEO_UTILS_CF_ACCESS_TEAM_DOMAIN` | `^[a-z0-9-]+\.cloudflareaccess\.com$`; issuer `https://<domain>`; JWKS `https://<domain>/cdn-cgi/access/certs` (never configurable separately) |
| `VIDEO_UTILS_CF_ACCESS_AUDS` | comma-separated, trimmed, de-duplicated, case-sensitive, 1..8 entries of `[A-Za-z0-9]{16,128}` |
| `VIDEO_UTILS_OPERATOR_ALLOWLIST` | comma-separated emails, lowercased, 1..32 entries; no wildcards or domains |
| `VIDEO_UTILS_PUBLIC_HOSTS` | comma-separated exact hostnames (no port, no scheme), 1..4 |
| `ORIGIN` | `https://<one of VIDEO_UTILS_PUBLIC_HOSTS>` (adapter-node; keeps `crossOriginRefusal` correct) |

The control-API URL/token rules in `web/src/lib/server/config.ts` are
unchanged (loopback control API; in-cluster this means a same-pod sidecar).

### 4.3 JWT verification (`cf-access.js`)

Deny unless all hold: header `cf-access-jwt-assertion` present, <= 8 KiB,
three base64url segments; header `alg` exactly `RS256` (reject `none`, `HS*`,
`ES*`, `PS*`), `kid` present and resolvable; RSA-SHA256 signature valid via
`node:crypto` (`createPublicKey({format:'jwk'})`, `verify`), key `kty` `RSA`,
modulus >= 2048 bits; `iss` equals the configured issuer exactly; `aud`
(string or array) intersects the configured AUDs; `exp` present and
`now < exp + 60 s`; `nbf`/`iat`, when present, `<= now + 60 s`; `email`
claim a non-empty string. Identity = lowercased verified `email`; it must be
in the allowlist. `Cf-Access-Authenticated-User-Email` and the
`CF_Authorization` cookie are never read. Verification never throws to the
caller; it returns `{ok:false, reason}` and reasons are never sent to clients.

JWKS cache: one cache per team domain, module-level; fetch timeout 5 s, body
cap 64 KiB, `redirect: 'error'`, only RSA keys with `kid` retained; fresh TTL
10 min; an unknown `kid` triggers one refetch subject to a 30 s cooldown;
on refresh failure previously fetched keys stay usable up to 60 min old, then
deny; no keys ever fetched = deny. `fetch` and the clock are injectable.

### 4.4 Tailscale Serve identity headers: not accepted

`Tailscale-User-Login`/`-Name`/`Tailscale-App-Capabilities` are trusted in the
estate only by a loopback backend behind `tailscale serve` on the same node
(lab design, Feature A). The RKE2 pod model has no such guarantee, so this lane
never reads them; receipts carry `tailscale_serve_identity: "not_accepted"`.

### 4.5 Gate decisions (`gate.js`, called by `hooks.server.ts`)

| Mode / condition | Response |
| --- | --- |
| loopback, `Host` not loopback | 421 `bff_host_refused` (unchanged) |
| loopback, loopback `Host` | resolve (unchanged; no identity required) |
| invalid mode or tailnet config invalid | 503 `bff_auth_unconfigured`, every path |
| tailnet, `Host` not in `VIDEO_UTILS_PUBLIC_HOSTS` | 421 `bff_host_refused` |
| tailnet, assertion missing/invalid | 403 `bff_identity_refused` |
| tailnet, verified email not allowlisted | 403 `bff_identity_refused` (same body) |
| tailnet, verified and allowlisted | resolve |

No public path is exempt in tailnet mode (probes use `tcpSocket`, section 5).
Error bodies keep the six-key BFF error shape; the two new codes are emitted
by the auth module because `BffErrorCode` in `web/src/lib/control-types.ts`
is not lane-owned (root request, section 8).

## 5. Container and deploy contract

1. **Containerfile**: builder and runtime from the same `node:22` slim image
   pinned `@sha256:` (digest observed from the registry at implementation and
   recorded in a receipt; if unobservable, the receipt says `unknown` and the
   file is marked not buildable); `corepack` pnpm `11.25.0`;
   `pnpm install --frozen-lockfile`; `pnpm build`; runtime copies only
   `build/`, `serve.js`, `package.json`, production `node_modules`; `USER
   10001:10001`; `ENV VIDEO_UTILS_AUTH_MODE=tailnet HOST=0.0.0.0 PORT=3000`;
   no `ADD` of URLs; no `COPY` of `fixtures/`, `artifacts/`, media, `.env*`.
2. **Deployment**: `replicas: 1`, `strategy: Recreate`; pod
   `runAsNonRoot`, `runAsUser 10001`, `fsGroup 10001`, `seccompProfile
   RuntimeDefault`, `automountServiceAccountToken: false`; container
   `allowPrivilegeEscalation: false`, `readOnlyRootFilesystem: true`, all
   capabilities dropped; requests/limits set (cpu, memory, ephemeral-storage);
   no `nvidia.com/gpu` or any GPU resource, nodeSelector or toleration;
   image by digest (sentinel `@sha256:` of 64 zeros until built, so an apply
   before a build fails closed at pull); config via `envFrom` ConfigMap;
   tcpSocket startup/readiness/liveness probes; PVC mounted at
   `/srv/video-utils/artifacts`; `emptyDir` `/tmp`.
3. **Service**: `ClusterIP` only. No Ingress, NodePort, LoadBalancer,
   hostNetwork or hostPort anywhere (tunnel-only origin).
4. **PVC** `video-utils-artifacts`: `ReadWriteOnce`, explicit size request,
   `storageClassName` omitted (unknown, section 7).
5. **NetworkPolicy**: default-deny ingress for the namespace plus one allow
   from the cloudflared connector namespace selector (value unknown, carried
   as a placeholder label the README requires the operator to set).
6. **Control API**: not containerised by this lane. The BFF already renders
   `control_api_unconfigured` without it; colocation as a same-pod loopback
   sidecar is recorded as `control_api_colocation: "unresolved"`.
7. **Cloudflare plan**: route file in the tinyland.dev
   `tinyland.cloudflare-tunnel.app-origin.v1` shape (service
   `http://video-utils-web.video-utils.svc.cluster.local:3000`,
   `catchAllService: http_status:404`, hostname and tunnel id `null` pending
   operator decision); Access plan: self-hosted, exact hostname, all paths,
   24h session, HttpOnly, SameSite=Lax, allow policy by exact operator email
   (values supplied at apply, not committed), `allowed_idps` pinned to
   Google Workspace, One-Time-PIN and tsidp (ids `null`), optional review
   service-token policy by name only, no bypass application.
8. **README**: every apply step (namespace, ConfigMap values, image build and
   digest pin, PVC, Deployment, Service, NetworkPolicy, tunnel route, DNS,
   Access application) is listed as an operator act requiring a separate go;
   order is gate first, then route, then DNS (xoruby order); rollback in
   reverse; secret names only.

## 6. Test protocol

Module: `tests/test_auth_hosting_s3.py`, run from the worktree root as
`PYTHONPATH=tests python3 -m unittest test_auth_hosting_s3 -v`. Directly
affected modules also run: `test_web_stack` (static class; serve.js and
hooks contracts) with the same invocation. Stdlib only; every subprocess has
a timeout <= 60 s; node-gated tests skip with an explicit reason when `node`
is absent. No network: JWKS fetch is a stub; keys are generated per run by
`node:crypto.generateKeyPairSync('rsa', {modulusLength: 2048})` in the node
harness (no key material committed). Fixed clock `now = 1_900_000_000`.

| ID | Class | Case | Expected |
| --- | --- | --- | --- |
| J1 | node | valid token, allowlisted email | allow, email lowercased |
| J2 | node | wrong `aud` | deny |
| J3 | node | `aud` array containing one configured AUD | allow |
| J4 | node | wrong `iss` | deny |
| J5 | node | expired (`exp = now - 61`) | deny |
| J6 | node | within skew (`exp = now - 30`) | allow |
| J7 | node | `nbf = now + 120` | deny |
| J8 | node | header missing / empty | deny |
| J9 | node | malformed (2 segments, bad base64url, > 8 KiB) | deny each |
| J10 | node | `alg` `none` and `HS256` (HMAC with public key bytes) | deny each |
| J11 | node | signature from a second, unpublished key with same `kid` | deny |
| J12 | node | missing `email` / empty `email` | deny |
| J13 | node | valid token, email not allowlisted | deny |
| J14 | node | AUD case differs | deny |
| C1 | node | 10 verifications, same `kid` | 1 fetch |
| C2 | node | unknown `kid`, then again within 30 s | 1 refetch, second denied without fetch |
| C3 | node | TTL expiry then fetch failure, cache age < 60 min | allow with stale key |
| C4 | node | fetch failure, no keys ever fetched | deny |
| A1 | node | allowlist parsing: trim, lowercase, dedupe, reject wildcard/empty/>32 | as specified |
| M1 | node | mode unset/empty -> loopback; `tailnet` -> tailnet; other -> error | as specified |
| M2 | node | tailnet config: each variable missing/invalid in turn | `unconfigured` |
| G1 | node | gate matrix of section 4.5 (7 rows) | exact status and code |
| L1 | static + node | serve.js with mode unset: `HOST` unset -> 127.0.0.1; `0.0.0.0`, LAN, `localhost` refused exit 2; `SOCKET_PATH` refused | unchanged S2 behaviour |
| L2 | node | serve.js tailnet with incomplete config and `HOST=0.0.0.0` | exit 2 before import |
| L3 | static | hooks.server.ts still refuses non-loopback Host in loopback mode via `LOOPBACK_HOST`; imports only `gate.js` from auth | present |
| K1 | static | every `deploy/**/*.json` and `kustomization.yaml` parses as JSON; kustomization resources exist | all parse |
| K2 | static | Deployment invariants of section 5.2; Service ClusterIP; no Ingress/NodePort/LoadBalancer/hostNetwork/hostPort; PVC present | all hold |
| K3 | static | secret scan over `deploy/`, `web/Containerfile`, auth modules: no `kind: Secret` with data, no PEM blocks, no JWT-shaped strings, no `CF-Access-Client-Secret` values, no 32+ hex/base64 runs except the zero-digest sentinel, no host paths (`/Users/`) | zero findings |
| K4 | static | Containerfile: every `FROM` digest-pinned, non-root `USER`, no `ADD http`, no `COPY` of fixtures/artifacts/media/.env | all hold |
| K5 | static | README states the outward-facing apply boundary and lists each unknown of section 7 | present |
| R1 | static | research doc cites every section-3 repo with a 40-hex commit and a date | 9/9 |

## 7. Completion metrics and claim classes

Claim classes: **source-check** (static/unit result in this worktree),
**source-reading** (what a remote default-branch file says on the recorded
commit; not live state), **not-claimed** (stated so nobody infers it).

| Metric | Denominator | Class |
| --- | --- | --- |
| Estate repos recorded with commit + date | 9 sources in section 3 | source-reading |
| JWT decision cases matching expectation | 14 (J1..J14; J9/J10 sub-cases each counted) | source-check |
| JWKS cache fetch-count cases matching expectation | 4 (C1..C4) | source-check |
| Gate matrix rows matching status and code | 7 (section 4.5) | source-check |
| Loopback-default cases unchanged | L1..L3 sub-cases (counted in receipt) | source-check |
| Manifest files parsed / invariants holding | all files under `deploy/` / K2 checklist | source-check |
| Secret-scan findings | 0 of scanned files (count in receipt) | source-check |
| Applied to Cloudflare / cluster / tunnel; image built or pushed; served proof | n/a | **not-claimed** |

Unknown fields every receipt and the README must carry explicitly (value
`null` or the string shown, never omitted):
`public_hostname: null`, `cloudflare_tunnel_id: null`,
`access_application_aud: null`, `access_idp_ids: null`,
`cluster_target: "unknown"`, `namespace_exists: "unknown"`,
`storage_class: "unknown"`, `cloudflared_namespace: "unknown"`,
`container_base_digest` (observed or `"unknown"`),
`container_image_digest: null`, `container_built: false`,
`control_api_colocation: "unresolved"`,
`tsidp_claims_in_access_jwt: "unknown"` (whether Access forwards tsidp
OIDC claims into the app token is not established by the sources),
`assertion_idp_visible_to_app: "unknown"`,
`tailscale_serve_identity: "not_accepted"`,
`applied: false`, `served_proof: "not_run"`.

Experimental non-improvement is not applicable (no experiment); a blocked
item is valid completion when its receipt names the block.

## 8. Root-owned changes this lane may request (not made by the lane)

1. `web/src/lib/control-types.ts`: add `'bff_identity_refused' |
   'bff_auth_unconfigured'` to `BffErrorCode` (the auth module emits the
   same six-key shape meanwhile).
2. `web/.containerignore` (not lane-owned): exclude `node_modules`, `build`,
   `.svelte-kit`, `fixtures`, `.env*` from the build context.
3. `web/src/app.d.ts`: an `App.Locals.operator` type only if a later UI lane
   needs the verified identity; this lane does not stamp locals.
4. `just/*.just` (root-owned recipes): optional `auth-hosting-test` recipe
   wrapping the section-6 command.

## 9. Preregistration

None. This lane runs no experiment, numerics, media or model work; there are
no arms, seeds, held-out data or scoring to seal. `preregistered: false`.

## 10. Doctrine carried

No change to audio processing, detectors, profiles or masters; the ~32 Hz
low-string protection, no blanket high-pass and no mains-notch rules are
untouched by this lane. Real-take media are never baked into an image or
committed; whether the RKE2 cluster host counts as an operator-controlled host
for real-take media (V6) is an operator decision recorded as part of the
apply go, not inferred here.

## 11. Phase 2 implementation record (appended 2026-10-07; sections 1-10 unchanged)

Implemented on `sprint/20261007-s3/auth_hosting` on top of the freeze commit
`38d9ed92d81bc19d0c8bc4be617bf45d7dab01e5`. The receipt is
`docs/agent-notes/sprints/20261007-s3/auth_hosting-implementation-receipt.json`.
These are the deliberate deviations from, or readings of, the frozen text:

1. **Runtime image also copies `src/lib/server/auth/`** (four pure ES modules, no secrets).
   Section 4.1/L2 requires `serve.js` to validate the complete tailnet configuration at startup.
   It does this with `mode.js`, so the module has to be present next to `serve.js`. Section
   5.1's "copies only build/, serve.js, package.json, production node_modules" is widened by
   exactly that directory.
2. **K3 digest/commit exemption.** The 32+-hex rule exempts the zero sentinel, the one observed
   base-image index digest (`node:22.23.2-bookworm-slim`, `sha256:48e4b67d…f0f9`, read from
   registry-1.docker.io on 2026-10-07), and 40-hex git commit ids in plan/receipt JSON. All three
   are public provenance identifiers, not credentials.
3. **`VIDEO_UTILS_AUTH_MODE=loopback` (literal) is invalid.** Section 4.1 says "any other value",
   so only unset or empty selects loopback.
4. **Gate also refuses a loopback `Host` in tailnet mode with 421.** This follows from the
   public-host rule, since loopback names are not valid entries in `VIDEO_UTILS_PUBLIC_HOSTS`.
5. **`deploy/k8s/networkpolicy.json` is a `v1` `List`** of two NetworkPolicies (default-deny plus
   cloudflared allow), so the owned-file list stays at one file.
6. **Estate tips moved during the lane.** lab (`fdd75a3d019e`) and tinyland-infra (`336c159e5672`)
   advanced on 2026-10-07. Every path read from them has the same path commit at both tips. The
   research record lists both tips.
7. **hooks.server.ts** imports `CF_ACCESS_JWT_HEADER` and `gateRequest` from `gate.js` only (L3).
   It passes `LOOPBACK_HOST` from `$lib/server/http` into the gate, which keeps the S2 refusal body
   unchanged: same code, same message, same six keys, same `no-store` header.

## Root amendment 2026-10-07: gate before static files

Audit finding (auth_hosting and auth_token lanes): adapter-node's entry serves
`build/client` (`/_app/immutable/*`, `/_app/version.json`, `/favicon.svg`)
through sirv before the SvelteKit hooks run, so "every path" in the tables above
did not hold for static files. In tailnet mode, `web/serve.js` now imports
`build/handler.js` and runs `gateRequest` on every request before handing it to
the adapter handler. Static files answer 421 on a wrong Host, 503 when the
configuration is invalid and 403 without an approved identity, exactly like
pages. The hooks still gate again. The JWKS cache registry is keyed on a
process-global symbol so the source and bundled copies of `cf-access.js` share
one cache per team domain. Regression: `tests/test_auth_token_s3.py`
O1a–O1d and the ordering assertions in `tests/test_auth_hosting_s3.py` L3.
Loopback mode is unchanged.
