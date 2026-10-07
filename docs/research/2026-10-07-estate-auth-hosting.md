# Estate auth and hosting pattern: Cloudflare Access + tsidp (2026-10-07)

Lane `auth_hosting`, sprint `20261007-s3`, Linear TIN-5720 (related TIN-5552). Contract:
[`docs/spec/sprints/AUTH_HOSTING_S3.md`](../spec/sprints/AUTH_HOSTING_S3.md). Operator S3 decision:
"use our CF Access + tsidp auth pattern, findable in xoxd.ai, gftb and others"
(`docs/spec/sprints/20261007-S3.md`).

## Method and limits

- Evidence comes **only from remote default branches**. For each repo the lane ran
  `git fetch <remote> <branch>`, then `git show <remote>/<branch>:<path>` or
  `git grep <pattern> <remote>/<branch>`. Local working trees were never read. Fetch time:
  2026-10-07 about 05:15Z.
- Each source has a branch tip commit and date. Where a file's last commit differs from the tip,
  the per-path commit and date are listed as well. These are what the files *say* on that commit
  (claim class **source-reading**). They are not live Cloudflare, tailnet or cluster state, and
  this lane made no live reads of any of those.
- The lab and tinyland-infra tips moved after the contract freeze on the same day. Both tips are
  recorded. Every path read from those two repos has the same path commit at both tips, so the
  frozen facts still hold.
- Quotations are verbatim excerpts. Ellipses mark omissions.

## Sources

| Repo (remote/branch) | Tip commit, date | Paths read (path commit, date) |
| --- | --- | --- |
| tinyland-inc/xoxd.ai `origin/main` | `cc570c3c1079cc5754840395184f0c1a6fece97f`, 2026-10-05 | `docs/agent-notes/2026-09-19-deploy-rulings.md` (`eab7161a9fab`, 2026-09-19); `AGENTS.md` (`8bbcd3aeb9dc`, 2026-10-02); `src/lib/components/PublicAccessDialog.svelte` (`8279fc3567dd`, 2026-09-22); `.github/workflows/deploy-pages-plan.yml` (`eabc429c5d55`, 2026-10-05) |
| xoxd-ai/tinyland.dev `github/main` | `7422982619e357d31a0ddf0affdf8dedd0b51a93`, 2026-10-02 | `docs/plans/tinyland-auth-golden-convergence.md` (`4c7634228c64`, 2026-07-13); `infra/cloudflare/honey-ingress-mothership-xoxd-ai-routes.json` (`8a80a74805a2`, 2026-09-19); `infra/cloudflare/honey-ingress-broker-origin-routes.json` (`14479365bf9c`, 2026-09-22); `docs/runbooks/2026-09-19-mothership-identity-rotation.md` (`cf1cd8e634a5`, 2026-09-19); `infra/staging/sveltekit-deployment.yaml` (`f08b92827ce2`, 2026-09-21); `infra/staging/kustomization.yaml` (`7c74d31c9036`, 2026-08-22); `infra/staging/network-policy.yaml` (`722fecdc4d80`, 2026-09-26); `ContainerFile` (`f4362f001ba8`, 2026-07-09) |
| Great-Falls-Tool-Bus/great-falls-tool-bus-infra `upstream/main` | `bb969bea496926b19f9350857a91da9d02a5f2c5`, 2026-10-06 | `docs/runbooks/cf-access-tsidp.md` (`3d0d02d6b6ae`, 2026-10-05); file listing of `tofu/stacks/edge/` |
| Great-Falls-Tool-Bus/greatfallstoolbus.org `upstream/main` | `b7f5b29690c72dbe777f1058bf8e88acaca3ab31`, 2026-10-06 | grep for Access JWT handling: no origin verifier. Matches only in `e2e/member-onboarding.spec.ts` and `scripts/production-health-probe*.sh` (redirect to `*.cloudflareaccess.com/cdn-cgi/access/login/`). `src/lib/identity/policy.ts` (`b751f71d299b`, 2026-10-02): the app's own Keycloak OIDC realm |
| Jesssullivan/gftb-site `origin/main` | `849af37beaaa8675a9115b741aeee7a0ba13b8f4`, 2026-09-22 | grep `cf-access`, `jwt-assertion`, `cloudflareaccess`, `tsidp`: no matches |
| tinyland-inc/massage-ithaca-portal `origin/main` | `fda9163fb9847c8b10a1b7ae4bc1fd8bddeb793e`, 2026-10-01 | `src/lib/server/auth/cf-access.ts` and `src/hooks.server.ts` (both `c0f410ecb7fa`, 2026-09-27); `AGENTS.md` "Authentication (MVP)" |
| xoxd-ai/lab `origin/main` | freeze `8654d4a8d8ef5846492a1daa9c3e714883ac7706`, 2026-10-07; re-read `fdd75a3d019ea81b5c986f67dfbfc0312ab0a11f`, 2026-10-07 | `AGENTS.md` (secrets doctrine; `24877626cda3` at freeze, `e12aa5a8c5f3` at re-read, both 2026-10-06); `docs/operations/TAILNET_MEMBERSHIP_DETECTION_DESIGN_2026-10-03.md` (`59dd2a6dc3ab`, 2026-10-05, unchanged) |
| tinyland-inc/tinyland-infra `origin/main` | freeze `a236992ade1fcef7e056d91077f1ed5aa4abea7c`, 2026-10-06; re-read `336c159e56723e3da85ec760c6aa557b6ebc296f`, 2026-10-07 | `tofu/stacks/xoxd-ai-edge/README.md` xoruby rows (`21264731bd9d`, 2026-10-05, unchanged); `xoruby-clients.tf` (`301beeb45543`, 2026-10-03); `kohakuhub-tailnet.tf` header (`0e91f2728290`, 2026-10-05, unchanged) |
| tinyland-inc/GloriousFlywheel `origin/main` | `aacc52916c9160b178105e628ed18fb95c8338d1`, 2026-10-06 | grep `tsidp`: only `docs/decisions/cold-start-enrollment-2026-06.md` (`32c1e6fb6d6c`, 2026-09-04), which names tsidp as a tailnet-native cold-start fallback. No app-auth pattern |

## Measured (source-reading: what the files state on the recorded commits)

### 1. Cloudflare Access is the perimeter, declared in operator-applied stacks

- xoxd.ai deploy rulings, E3: "DNS, the www redirect and the Access gate are the tinyland-infra
  stack tofu/stacks/xoxd-ai-edge, applied by the operator". E5: "xoxd.ai is gated behind
  Cloudflare Access exactly as glorious.build is … an automated reader passes with the xoxd review
  service token (client id and secret in lab sops, names cloudflare_access_review_client_id_xoxd
  and cloudflare_access_review_client_secret_xoxd), never in this repository."
- xoxd.ai `deploy-pages-plan.yml` header: "The hostname is fronted by a permanent Cloudflare Access
  application in tinyland-infra's xoxd-ai-edge stack; this workflow never touches that gate."
- xoxd.ai `AGENTS.md` Deploy Lane: "To LOOK at a gated surface as an automated reader, send
  `CF-Access-Client-Id` and `CF-Access-Client-Secret`, read from the lab sops store by name, never
  committed here." `PublicAccessDialog.svelte`, as the user sees it: "Cloudflare Access will
  verify your approved email before it lets you in."
- tinyland-infra `xoxd-ai-edge` README, xoruby record: an `allow` policy with "Exact `email`
  selectors only … Never the shared operators group", and an application that is "Zone-bound,
  exact hostname, all paths. 24h session, HttpOnly, SameSite=Lax". A separate `bypass`
  application exists "for `/healthz` only. Access picks the most specific matching path." The DNS
  record is a "Proxied CNAME to the honey-ingress tunnel". The order is "1. Apply the gate and read
  it back … 2. … applies the tunnel rule … 3. Once the origin Service answers, flip
  `xoruby_dns_enabled` …". "Rollback runs in reverse." The header of `xoruby-clients.tf` says:
  "GATE FIRST, RECORD LATER", and "an Access service token is a new credential and gets its own
  ruling".
- tinyland-infra `kohakuhub-tailnet.tf` header: "These records name an existing tailnet ingress.
  They do not provision a Cloudflare Tunnel, Funnel, Access application, or public ingress route."
  This is a separate tailnet-only DNS pattern, not an Access pattern.

### 2. Origins are reached through the shared tunnel, by a source-controlled route contract

- tinyland.dev `infra/cloudflare/honey-ingress-mothership-xoxd-ai-routes.json`: `schemaVersion`
  `tinyland.cloudflare-tunnel.app-origin.v1`, `tunnelName` `honey-ingress`, `service`
  `http://sveltekit.tinyland-staging.svc.cluster.local:3000`, `catchAllService`
  `http_status:404`. Its notes say: "Applied today … by hand against the shared honey-ingress
  Cloudflare Tunnel … out of band from this repo. No script or GitHub Actions workflow in
  tinyland.dev reads or applies this file; it is the source-controlled expected route contract
  only", and "Reachability still requires the pre-launch Cloudflare Access gate … to stay enabled
  until an on-cluster served proof exists".
- tinyland.dev `infra/staging/network-policy.yaml`: `staging-default-deny-ingress` with
  `podSelector: {}`, then an allow from namespace `cloudflared` /
  `app.kubernetes.io/name: cloudflared` on TCP 3000 only, commented "The retained Cloudflare
  Tunnel connector … reaches SvelteKit directly on port 3000".
- tinyland.dev `infra/staging/sveltekit-deployment.yaml`: `replicas: 1`, `strategy: Recreate`,
  a ClusterIP Service on 3000, PVCs with `storageClassName: openebs-bumble-zfs`, Secrets by
  `secretKeyRef` name, and `httpGet /api/health` probes with a startupProbe. The comment explains
  that adapter-node "does not bind :3000 until `await server.init()` resolves". Image
  `ghcr.io/xoxd-ai/tinyland.dev:latest`.
- tinyland.dev `ContainerFile` header: "Production image authority is Bazel/rules_img … Keep this
  file for the local/containerized development target only."

### 3. tsidp is federated into Access; the app never sees a tsidp token

- gftb-infra `docs/runbooks/cf-access-tsidp.md`: `cloudflare_zero_trust_access_identity_provider.tsidp`
  is "type `oidc` … endpoints `<issuer>/authorize`, `<issuer>/token`,
  `<issuer>/.well-known/jwks.json`, scopes `openid email profile`, PKCE on". Group membership
  uses "the OIDC claim `gftb_member` = `"true"` … Never an email: tsidp rewrites `@github` and
  `@passkey` logins to non-routable addresses, so email matching would be wrong both ways." The
  policy "**requires** the tsidp login method, so the claim is trusted from tsidp only". The
  existing email policy "gains `exclude = [login_method tsidp]`". "`allowed_idps` is pinned to
  exactly Google Workspace, One-Time-PIN and tsidp (the TIN-2660 pattern)". The redirect URI is
  "`https://sulliwood.cloudflareaccess.com/cdn-cgi/access/callback`", and tsidp runs on "a new tag
  `tag:gftb-idp` … the `funnel` node attribute". Custody: "Never paste either value into a command
  line, a ticket, a chat or an agent session … (with no `--body`, `gh secret set` reads stdin)".
  Rollback: "Deleting the IdP does not end Access sessions (24h) or `CF_Authorization` cookies
  already minted through it … **Revoke existing tokens**".
- lab `TAILNET_MEMBERSHIP_DETECTION_DESIGN_2026-10-03.md`: Feature A is a probe whose "loopback
  backend reads the Serve identity header `Tailscale-User-Login`". The rule is "Serve strips any
  client-supplied `Tailscale-User-*` … Anything else is no, including … anything that reached the
  loopback port without passing through Serve." Feature B is "tsidp as an Access IdP … with Funnel
  so that Cloudflare's servers can reach its" endpoints.

### 4. Origin verification of the Access JWT (the in-app layer)

- massage-ithaca-portal `src/lib/server/auth/cf-access.ts`: "every request Cloudflare lets through
  carries a signed identity assertion in the `Cf-Access-Jwt-Assertion` header … verifies that
  assertion — cryptographically, against the team's JWKS, with audience (AUD) and issuer checks".
  It states: "The plaintext `Cf-Access-Authenticated-User-Email` header is NEVER trusted", "There
  is deliberately no development shortcut", and "The origin is expected to be tunnel-only
  (TIN-2446)". JWKS: `createRemoteJWKSet(new URL(\`https://${teamDomain}/cdn-cgi/access/certs\`))`,
  cached module-level per team domain. Issuer: "`https://sulliwood.cloudflareaccess.com` …
  a token with any other issuer, or none, is refused". AUDs: "trimmed, de-duplicated array. It
  does NOT lowercase: an Access application AUD is an opaque, case-sensitive identifier", any-of.
  Email: "Its *verified* `email` claim must be a non-empty string", lowercased. Public path
  `DEFAULT_PUBLIC_PATHS = ["/api/health"]` ("K8s liveness/readiness only"). A failure returns 403
  and "Never leaks the reason".
- massage-ithaca-portal `src/hooks.server.ts`: "This file owns the ONLY `$env` reads … the pure
  modules stay env-free … Deny-by-default: absent config → every non-public request is refused."
  Env names: `CF_ACCESS_TEAM_DOMAIN`, `CF_ACCESS_AUDS`, `CF_ACCESS_AUD`.
- massage-ithaca-portal `AGENTS.md`: "The origin must be **tunnel-only** — never trust CF headers
  while the origin is directly reachable … `jose` is a NEW dependency".
- greatfallstoolbus.org has no origin Access-JWT verifier on `upstream/main`. Its probes treat
  "302 → `*.cloudflareaccess.com/cdn-cgi/access/login/`" as gate reachability, and member sign-in
  is the app's own Keycloak OIDC (`OIDC_ISSUER` `https://id.greatfallstoolbus.org/realms/...`).

### 5. Defense in depth and secrets

- tinyland.dev `tinyland-auth-golden-convergence.md`: "keep CF Access as the defense-in-depth
  perimeter on all dynamic/preview origins + a DO-NOT-REPLACE list (MI CF-Access-JWT TIN-2442, GFTB
  apex, alerting 302 probe)". "Edge CF Access fails CLOSED".
- tinyland.dev mothership identity-rotation runbook: "No private key is generated, printed, or
  committed by this PR or this doc". Secrets live in the Kubernetes Secret `sveltekit-secrets` and
  are written by an operator `kubectl` dry-run/apply pipeline.
- lab `AGENTS.md`: secrets are split by concern and sops-nix materializes them per host.
  "`sops -d file.yaml | grep <term>` prints **secret values**. Redact first".

## Inferred (this lane's reading; not stated verbatim by one source)

1. **One identity input at the origin.** Because tsidp is an IdP *inside* Access (section 3), a
   video-utils origin behind Access receives a Cloudflare Access application JWT whatever IdP the
   operator used. The origin therefore verifies the Access JWT the way the MI portal does and has
   no separate tsidp verifier. `VIDEO_UTILS_AUTH_MODE=tailnet` means "reachable only through the
   estate perimeter whose IdPs include tsidp". It does not mean "trust tailnet headers".
2. **Tailscale Serve headers are not usable in a pod.** The lab design trusts `Tailscale-User-*`
   only for a loopback backend behind `tailscale serve` on the same node. An RKE2 pod reached
   through cloudflared has no such guarantee, so the lane never reads those headers.
3. **No health bypass.** The xoruby `/healthz` bypass and the MI `/api/health` exemption exist for
   HTTP probes. video-utils uses `tcpSocket` probes, so it needs no unauthenticated path at either
   layer.
4. **Service tokens.** A non-identity service-token Access JWT presumably carries no user `email`.
   Under the MI rule ("verified email claim must be a non-empty string") such a reader would be
   refused at the origin. This was not verified against a live token.
5. **Inner allowlist.** The MI portal authorizes the verified email against tenant membership
   rows. video-utils has no database, so the equivalent inner layer is an exact-email operator
   allowlist from configuration, mirroring the exact-email Access policy (xoruby).

## Unknown (carried explicitly in receipts and `deploy/README.md`)

- `tsidp_claims_in_access_jwt: "unknown"`: no source states whether Access copies tsidp OIDC claims
  (for example `gftb_member`) into the application token the origin receives.
- `assertion_idp_visible_to_app: "unknown"`: no source shows the origin reading which IdP was used.
- What `email` an Access JWT carries for a tsidp sign-in. gftb says tsidp rewrites `@github` and
  `@passkey` logins, so the operator's allowlist entry for a tsidp login is unknown.
- `public_hostname`, `cloudflare_tunnel_id`, `access_application_aud`, `access_idp_ids`: `null`.
  `cluster_target`, `namespace_exists`, `storage_class`, `cloudflared_namespace`: `"unknown"`.
  `control_api_colocation: "unresolved"`. `tailscale_serve_identity: "not_accepted"`.

## How video-utils implements the pattern (S3, source-checked only)

| Estate element | video-utils |
| --- | --- |
| Access app: exact host, all paths, 24h, HttpOnly, Lax, exact-email allow (xoruby) | `deploy/cloudflare/video-utils-access-plan.json` (plan; values at apply) |
| `allowed_idps` = Google Workspace, One-Time-PIN, tsidp; tsidp excluded from email policy, admitted only by claim + login method (gftb) | Same in the plan. The tsidp policy is off by default. IdP ids are `null` |
| Tunnel route contract `app-origin.v1`, applied out of band (tinyland.dev) | `deploy/cloudflare/video-utils-app-origin-routes.json`, hostname and tunnel `null` |
| ClusterIP-only Service, default-deny plus cloudflared allow (tinyland.dev staging) | `deploy/k8s/*.json` |
| Origin JWT verification via `jose` against `https://<team>/cdn-cgi/access/certs`, `iss`, any-of case-sensitive AUD, verified lowercased email, never the plaintext email header, no dev bypass (MI portal) | `web/src/lib/server/auth/cf-access.js` with `node:crypto` (RS256 only, modulus >= 2048, `exp`/`nbf`/`iat` with 60 s skew, JWKS cache 10 min fresh / 30 s unknown-kid cooldown / 60 min stale ceiling, 5 s timeout, 64 KiB cap, `redirect: 'error'`) |
| `$env` read only in hooks; pure modules env-free (MI portal) | `web/src/hooks.server.ts` reads `$env/dynamic/private` once per request; `mode.js` / `gate.js` are pure |
| Secrets by name only; values by stdin/sops (gftb, xoxd.ai, lab) | No secrets are needed or committed. ConfigMap values are non-secret and set at apply |

Deviations from the estate, each deliberate: `node:crypto` instead of `jose`, because
`web/package.json` is not lane-owned. No `/api/health` exemption, because the probes are tcpSocket.
A real multi-stage `web/Containerfile`, whereas tinyland.dev's `ContainerFile` is dev-only and its
production authority is Bazel/rules_img, which has no video-utils equivalent. The image digest is
a fail-closed sentinel rather than `:latest`.

Not claimed: any apply, tunnel, DNS, Access application, image build or push, served proof, or
live behaviour of Cloudflare or tsidp.
